import asyncio
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field

from ..auth import require_key
from ..manager import Manager
from ..process_utils import kill_process_safely
from ..settings import settings
from .check import get_manager

router = APIRouter()
MODULE_RE = re.compile(r"^[A-Za-z0-9_.]+$")


class AstModuleRequest(BaseModel):
    modules: list[str] = Field(
        ..., description="Lean module names, e.g., 'Lean' or 'Mathlib.Data.List.Basic'"
    )
    one: bool = True
    timeout: int = 3600


class AstModuleResult(BaseModel):
    module: str
    ast: dict[str, Any] | None = None
    error: str | None = None
    time: float = 0.0
    diagnostics: dict[str, Any] | None = None


class AstModuleResponse(BaseModel):
    results: list[AstModuleResult]


class AstCodeRequest(BaseModel):
    code: str = Field(..., description="Lean code (can include import lines)")
    module: str = Field("User.Code", description="Virtual module name to assign")
    timeout: int = 3600


async def run_ast_one(module: str, one: bool, timeout: float) -> AstModuleResult:
    if not MODULE_RE.match(module):
        return AstModuleResult(module=module, error="Invalid module name")
    # Type assertion: path is set by Settings model_validator
    assert settings.ast_export_project_dir is not None, (
        "ast_export_project_dir should be set by Settings"
    )
    cwd = settings.ast_export_project_dir
    args = ["lake", "exe", "ast-export"] + (["--one", module] if one else [module])
    try:
        logger.info("[AST] Exporting module: {} (one={})", module, one)
        t0 = time.perf_counter()
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.error("[AST] Timeout exporting module {} after {}s, killing process", module, timeout)
            await kill_process_safely(proc, use_process_group=True, logger_instance=logger)
            return AstModuleResult(
                module=module,
                error=f"timed out after {timeout}s",
                time=round(time.perf_counter() - t0, 6),
            )
        if proc.returncode != 0:
            err = stderr_bytes.decode()
            logger.error("[AST] Export failed for module {}: {}", module, err)
            return AstModuleResult(
                module=module,
                error=err or "ast-export failed",
                time=round(time.perf_counter() - t0, 6),
            )
        # For --one, file path is deterministic:
        rel = module.replace(".", "/") + ".out.json"
        out_path = Path(cwd) / ".lake/build/lib" / rel
        try:
            raw = out_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            logger.info("[AST] Success for module {}", module)
            return AstModuleResult(
                module=module,
                ast=data,
                time=round(time.perf_counter() - t0, 6),
                diagnostics={"ast_bytes": len(raw)},
            )
        except Exception as e:
            logger.error("[AST] Failed to read AST for module {}: {}", module, e)
            return AstModuleResult(
                module=module,
                error=f"failed to read AST: {e}",
                time=round(time.perf_counter() - t0, 6),
            )
    except Exception as e:
        logger.exception("[AST] Unexpected error for module {}: {}", module, e)
        return AstModuleResult(module=module, error=str(e))


@router.post("/ast", response_model=AstModuleResponse, response_model_exclude_none=True)
async def ast_modules(
    body: AstModuleRequest,
    manager: Manager = Depends(get_manager),
    _: str = Depends(require_key),
) -> AstModuleResponse:
    async def worker(m: str) -> AstModuleResult:
        async with manager.ast_semaphore:
            return await run_ast_one(m, body.one, float(body.timeout))

    results = await asyncio.gather(*(worker(m) for m in body.modules))
    return AstModuleResponse(results=list(results))


@router.get("/ast", response_model=AstModuleResponse, response_model_exclude_none=True)
async def ast_module(
    module: str = Query(..., description="Lean module name"),
    one: bool = Query(True),
    timeout: int = Query(3600),
    manager: Manager = Depends(get_manager),
    _: str = Depends(require_key),
) -> AstModuleResponse:
    async with manager.ast_semaphore:
        result = await run_ast_one(module, one, float(timeout))
    return AstModuleResponse(results=[result])


@router.post(
    "/ast_code", response_model=AstModuleResponse, response_model_exclude_none=True
)
async def ast_from_code(
    body: AstCodeRequest,
    manager: Manager = Depends(get_manager),
    _: str = Depends(require_key),
) -> AstModuleResponse:
    if not MODULE_RE.match(body.module):
        raise HTTPException(400, "Invalid module name")

    # IMPORTANT: Always use a unique module name per request.
    #
    # ast-export writes to a deterministic output path under `.lake/build/lib/<module>.out.json`.
    # If multiple concurrent requests share the same module name (the default is "User.Code"),
    # they will race on the same output file and can return an AST for the wrong request.
    effective_module = f"{body.module}_{uuid4().hex}"

    # Type assertion: paths are set by Settings model_validator
    assert settings.ast_export_bin is not None, (
        "ast_export_bin should be set by Settings"
    )
    assert settings.ast_export_project_dir is not None, (
        "ast_export_project_dir should be set by Settings"
    )
    assert settings.project_dir is not None, "project_dir should be set by Settings"
    if not settings.ast_export_bin.exists():
        raise HTTPException(500, f"ast-export not found at {settings.ast_export_bin}")

    # Build temp module file structure
    tmpdir = Path(tempfile.mkdtemp(prefix="ast_code_"))
    try:
        src_dir = tmpdir / "src"
        mod_rel = Path(*effective_module.split("."))  # e.g. User/Code
        file_path = src_dir / f"{mod_rel}.lean"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(body.code, encoding="utf-8")

        # Make temp output dir consistent with exporter
        out_rel = Path(".lake/build/lib") / f"{mod_rel}.out.json"
        out_path = tmpdir / out_rel
        # Ensure the exporter output directory exists
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Extend source search path with our temp src and the repo's mathlib root and its dependencies
        env = os.environ.copy()
        src_paths = [str(src_dir), str(settings.project_dir)]
        packages_root = settings.project_dir / ".lake" / "packages"
        if packages_root.is_dir():
            for pkg in packages_root.iterdir():
                pkg_src = pkg / "src"
                if pkg_src.is_dir():
                    src_paths.append(str(pkg_src))
        env["LEAN_SRC_PATH"] = os.pathsep.join(src_paths)

        # Also add compiled libraries (.olean) so imported notations/macros are available during header processing
        lib_paths: list[str] = [str(settings.project_dir / ".lake" / "build" / "lib")]
        if packages_root.is_dir():
            for pkg in packages_root.iterdir():
                pkg_lib = pkg / ".lake" / "build" / "lib"
                if pkg_lib.is_dir():
                    lib_paths.append(str(pkg_lib))
        # Prepend any existing LEAN_PATH to preserve sysroot paths if set
        existing_lean_path = env.get("LEAN_PATH")
        lean_path = os.pathsep.join(
            lib_paths + ([existing_lean_path] if existing_lean_path else [])
        )
        env["LEAN_PATH"] = lean_path

        logger.info(
            "[AST] Exporting from code for module {} (len={})",
            effective_module,
            len(body.code),
        )
        # Ensure output directory exists inside ast_export project build dir
        rel = Path(*effective_module.split("."))
        out_dir = settings.ast_export_project_dir / ".lake/build/lib" / rel.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        # Run ast-export via lake in the ast_export project so Lake resolves deps
        async with manager.ast_semaphore:
            t0 = time.perf_counter()
            proc = await asyncio.create_subprocess_exec(
                "lake",
                "exe",
                "ast-export",
                "--one",
                effective_module,
                cwd=str(settings.ast_export_project_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        try:
            _stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=float(body.timeout)
            )
        except asyncio.TimeoutError:
            logger.error(
                "[AST] Timeout exporting code module {} after {}s, killing process",
                body.module,
                body.timeout,
            )
            await kill_process_safely(proc, use_process_group=True, logger_instance=logger)
            return AstModuleResponse(
                results=[
                    AstModuleResult(
                        module=effective_module,
                        error=f"timed out after {body.timeout}s",
                        time=round(time.perf_counter() - t0, 6),
                    )
                ]
            )

        if proc.returncode != 0:
            err = stderr_bytes.decode()
            logger.error(
                "[AST] Export from code failed for module {}: {}", effective_module, err
            )
            return AstModuleResponse(
                results=[
                    AstModuleResult(
                        module=effective_module,
                        error=(err or "ast-export failed"),
                        time=round(time.perf_counter() - t0, 6),
                    )
                ]
            )

        try:
            # Output is written under the ast_export project build dir when using lake
            out_path = (
                settings.ast_export_project_dir / ".lake/build/lib" / f"{rel}.out.json"
            )
            raw = out_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            logger.info("[AST] Success for code module {}", effective_module)
            return AstModuleResponse(
                results=[
                    AstModuleResult(
                        module=effective_module,
                        ast=data,
                        time=round(time.perf_counter() - t0, 6),
                        diagnostics={"ast_bytes": len(raw)},
                    )
                ]
            )
        except Exception as e:
            logger.error(
                "[AST] Failed to read AST for code module {}: {}", effective_module, e
            )
            return AstModuleResponse(
                results=[
                    AstModuleResult(
                        module=effective_module,
                        error=f"failed to read AST: {e}",
                        time=round(time.perf_counter() - t0, 6),
                    )
                ]
            )
    finally:
        # Best-effort cleanup
        try:
            for p in sorted(tmpdir.rglob("*"), reverse=True):
                try:
                    p.unlink() if p.is_file() else p.rmdir()
                except Exception:
                    pass
            tmpdir.rmdir()
        except Exception:
            pass

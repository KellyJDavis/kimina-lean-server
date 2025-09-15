import asyncio
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from ..auth import require_key
from ..settings import settings
from ..manager import Manager
from .check import get_manager
from loguru import logger

router = APIRouter()
MODULE_RE = re.compile(r"^[A-Za-z0-9_.]+$")

class AstModuleRequest(BaseModel):
    modules: list[str] = Field(..., description="Lean module names, e.g., 'Lean' or 'Mathlib.Data.List.Basic'")
    one: bool = True
    timeout: int = 60

class AstModuleResult(BaseModel):
    module: str
    ast: dict[str, Any] | None = None
    error: str | None = None

class AstModuleResponse(BaseModel):
    results: list[AstModuleResult]

class AstCodeRequest(BaseModel):
    code: str = Field(..., description="Lean code (can include import lines)")
    module: str = Field("User.Code", description="Virtual module name to assign")
    timeout: int = 60

async def run_ast_one(module: str, one: bool, timeout: float) -> AstModuleResult:
    if not MODULE_RE.match(module):
        return AstModuleResult(module=module, error="Invalid module name")
    cwd = settings.ast_export_project_dir
    args = ["lake", "exe", "ast-export"] + (["--one", module] if one else [module])
    try:
        logger.info("[AST] Exporting module: {} (one={})", module, one)
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            logger.error("[AST] Timeout exporting module {} after {}s", module, timeout)
            return AstModuleResult(module=module, error=f"timed out after {timeout}s")
        if proc.returncode != 0:
            err = stderr_bytes.decode()
            logger.error("[AST] Export failed for module {}: {}", module, err)
            return AstModuleResult(module=module, error=err or "ast-export failed")
        # For --one, file path is deterministic:
        rel = module.replace(".", "/") + ".out.json"
        out_path = Path(cwd) / ".lake/build/lib" / rel
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
            logger.info("[AST] Success for module {}", module)
            return AstModuleResult(module=module, ast=data)
        except Exception as e:
            logger.error("[AST] Failed to read AST for module {}: {}", module, e)
            return AstModuleResult(module=module, error=f"failed to read AST: {e}")
    except Exception as e:
        logger.exception("[AST] Unexpected error for module {}: {}", module, e)
        return AstModuleResult(module=module, error=str(e))

@router.post("/ast", response_model=AstModuleResponse, response_model_exclude_none=True)
async def ast_modules(body: AstModuleRequest, manager: Manager = Depends(get_manager), _: str = Depends(require_key)) -> AstModuleResponse:
    async def worker(m: str) -> AstModuleResult:
        async with manager.ast_semaphore:
            return await run_ast_one(m, body.one, float(body.timeout))
    results = await asyncio.gather(*(worker(m) for m in body.modules))
    return AstModuleResponse(results=list(results))

@router.get("/ast", response_model=AstModuleResponse, response_model_exclude_none=True)
async def ast_module(
    module: str = Query(..., description="Lean module name"),
    one: bool = Query(True),
    timeout: int = Query(60),
    manager: Manager = Depends(get_manager),
    _: str = Depends(require_key),
) -> AstModuleResponse:
    async with manager.ast_semaphore:
        result = await run_ast_one(module, one, float(timeout))
    return AstModuleResponse(results=[result])

@router.post("/ast_code", response_model=AstModuleResponse, response_model_exclude_none=True)
async def ast_from_code(body: AstCodeRequest, manager: Manager = Depends(get_manager), _: str = Depends(require_key)) -> AstModuleResponse:
    if not MODULE_RE.match(body.module):
        raise HTTPException(400, "Invalid module name")
    if not settings.ast_export_bin.exists():
        raise HTTPException(500, f"ast-export not found at {settings.ast_export_bin}")

    # Build temp module file structure
    tmpdir = Path(tempfile.mkdtemp(prefix="ast_code_"))
    try:
        src_dir = tmpdir / "src"
        mod_rel = Path(*body.module.split("."))  # e.g. User/Code
        file_path = src_dir / f"{mod_rel}.lean"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(body.code, encoding="utf-8")

        # Make temp output dir consistent with exporter
        out_rel = Path(".lake/build/lib") / f"{mod_rel}.out.json"
        out_path = tmpdir / out_rel
        # Ensure the exporter output directory exists
        out_path.parent.mkdir(parents=True, exist_ok=True)

        # Extend source search path with our temp src and the repo's mathlib root
        env = os.environ.copy()
        src_paths = [str(src_dir)]
        # Allow `import Mathlib ...` directly from the local checkout
        src_paths.append(str(settings.project_dir))
        env["LEAN_SRC_PATH"] = os.pathsep.join(src_paths)

        logger.info("[AST] Exporting from code for module {} (len={})", body.module, len(body.code))
        # Run the ast-export binary in the temp directory
        async with manager.ast_semaphore:
            proc = await asyncio.create_subprocess_exec(
                str(settings.ast_export_bin),
                "--one", body.module,
                cwd=str(tmpdir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )
        try:
            _stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=float(body.timeout))
        except asyncio.TimeoutError:
            proc.kill()
            logger.error("[AST] Timeout exporting code module {} after {}s", body.module, body.timeout)
            return AstModuleResponse(results=[AstModuleResult(module=body.module, error=f"timed out after {body.timeout}s")])

        if proc.returncode != 0:
            err = stderr_bytes.decode()
            logger.error("[AST] Export from code failed for module {}: {}", body.module, err)
            return AstModuleResponse(results=[AstModuleResult(module=body.module, error=(err or "ast-export failed"))])

        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
            logger.info("[AST] Success for code module {}", body.module)
            return AstModuleResponse(results=[AstModuleResult(module=body.module, ast=data)])
        except Exception as e:
            logger.error("[AST] Failed to read AST for code module {}: {}", body.module, e)
            return AstModuleResponse(results=[AstModuleResult(module=body.module, error=f"failed to read AST: {e}")])
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
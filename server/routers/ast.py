import asyncio
import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from ..auth import require_key
from ..settings import settings

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

async def run_ast_one(module: str, one: bool, timeout: float) -> AstModuleResult:
    if not MODULE_RE.match(module):
        return AstModuleResult(module=module, error="Invalid module name")
    cwd = settings.ast_export_project_dir
    args = ["lake", "exe", "ast-export"] + (["--one", module] if one else [module])
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            return AstModuleResult(module=module, error=f"timed out after {timeout}s")
        if proc.returncode != 0:
            return AstModuleResult(module=module, error=stderr.decode() or "ast-export failed")
        # For --one, file path is deterministic:
        rel = module.replace(".", "/") + ".out.json"
        out_path = Path(cwd) / ".lake/build/lib" / rel
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
            return AstModuleResult(module=module, ast=data)
        except Exception as e:
            return AstModuleResult(module=module, error=f"failed to read AST: {e}")
    except Exception as e:
        return AstModuleResult(module=module, error=str(e))

@router.post("/ast", response_model=AstModuleResponse, response_model_exclude_none=True)
async def ast_modules(body: AstModuleRequest, _: str = Depends(require_key)) -> AstModuleResponse:
    sem = asyncio.Semaphore(4)
    async def worker(m: str) -> AstModuleResult:
        async with sem:
            return await run_ast_one(m, body.one, float(body.timeout))
    results = await asyncio.gather(*(worker(m) for m in body.modules))
    return AstModuleResponse(results=list(results))

@router.get("/ast", response_model=AstModuleResponse, response_model_exclude_none=True)
async def ast_module(
    module: str = Query(..., description="Lean module name"),
    one: bool = Query(True),
    timeout: int = Query(60),
    _: str = Depends(require_key),
) -> AstModuleResponse:
    result = await run_ast_one(module, one, float(timeout))
    return AstModuleResponse(results=[result])
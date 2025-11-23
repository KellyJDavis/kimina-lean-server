from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from loguru import logger


def _prisma_schema_path() -> Path:
    """Return the absolute path to the packaged Prisma schema."""
    pkg_root = Path(__file__).resolve().parent.parent
    schema_candidates = [
        pkg_root / "server" / "prisma" / "schema.prisma",
        pkg_root / "prisma" / "schema.prisma",
        Path(__file__).resolve().parent.parent / "prisma" / "schema.prisma",
    ]
    for schema in schema_candidates:
        if schema.exists():
            return schema
    raise RuntimeError(
        "Could not locate Prisma schema in the installed package. "
        "Please reinstall `kimina-ast-server` or file an issue."
    )


def _generate_prisma_client() -> None:
    """Generate the Prisma client in the current environment."""
    schema_path = _prisma_schema_path()
    logger.info("Generating Prisma client from schema at {}", schema_path)
    env = os.environ.copy()
    env.setdefault("PRISMA_PY_GENERATE_SKIP_WARNING", "1")
    try:
        subprocess.run(
            [sys.executable, "-m", "prisma", "generate", "--schema", str(schema_path)],
            check=True,
            env=env,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise RuntimeError(
            "Failed to generate Prisma client. "
            "Ensure the 'prisma' CLI is installed (pip install prisma) "
            f"and accessible in the current environment. Original error: {exc}"
        ) from exc


def _import_prisma() -> Any:
    """Import Prisma client, generating it first if necessary."""
    try:
        from prisma import Prisma  # type: ignore
    except RuntimeError as exc:
        message = str(exc)
        if "Client hasn't been generated yet" in message:
            _generate_prisma_client()
            import prisma as prisma_module  # type: ignore

            importlib.reload(prisma_module)
            from prisma import Prisma  # type: ignore
        else:
            raise
    return Prisma()


prisma: Any = _import_prisma()

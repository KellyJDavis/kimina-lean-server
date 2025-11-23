from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from loguru import logger


def _prisma_schema_path() -> Path:
    """Return the absolute path to the packaged Prisma schema."""
    # `server` package lives at <site-packages>/server/
    # The schema is packaged under <site-packages>/prisma/schema.prisma
    pkg_root = Path(__file__).resolve().parent.parent
    schema = pkg_root / "prisma" / "schema.prisma"
    if not schema.exists():
        raise RuntimeError(
            f"Could not locate Prisma schema at '{schema}'. "
            "Please ensure the package was installed correctly."
        )
    return schema


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
            "Ensure the 'prisma' package is installed and accessible. "
            f"Original error: {exc}"
        ) from exc


def _import_prisma() -> "Prisma":
    """Import Prisma client, generating it first if necessary."""
    try:
        from prisma import Prisma  # type: ignore
    except RuntimeError as exc:
        message = str(exc)
        if "Client hasn't been generated yet" in message:
            _generate_prisma_client()
            from prisma import Prisma  # type: ignore
        else:
            raise
    return Prisma()


prisma = _import_prisma()

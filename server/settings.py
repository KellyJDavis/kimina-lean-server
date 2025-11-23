import os
import re
from enum import Enum
from pathlib import Path
from typing import cast

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    dev = "dev"
    prod = "prod"


def find_workspace() -> Path | None:
    """Find the Lean workspace directory using auto-discovery.

    Checks in order:
    1. LEAN_SERVER_WORKSPACE environment variable
    2. Current working directory (if it contains mathlib4/ or repl/)
    3. Common locations (~/kimina-workspace, ~/lean-workspace)

    Returns None if no workspace is found.
    """
    # 1. Check environment variable
    workspace_env = os.getenv("LEAN_SERVER_WORKSPACE")
    if workspace_env:
        workspace_path = Path(workspace_env).expanduser().resolve()
        if workspace_path.exists():
            return workspace_path

    # 2. Check current directory
    cwd = Path.cwd()
    if (cwd / "mathlib4").exists() or (cwd / "repl").exists():
        return cwd

    # 3. Check common locations
    home = Path.home()
    for common_name in ["kimina-workspace", "lean-workspace", "workspace"]:
        common_path = home / common_name
        if common_path.exists() and (
            (common_path / "mathlib4").exists() or (common_path / "repl").exists()
        ):
            return common_path

    return None


def get_workspace_base() -> Path:
    """Get the base directory for workspace paths.

    In development (from source), this is the repository root.
    When installed as a package, this uses workspace auto-discovery.
    """
    # Check if we're in development mode (BASE_DIR has the expected structure)
    base_dir = Path(__file__).resolve().parent.parent
    if (base_dir / "mathlib4").exists() or (base_dir / "repl").exists():
        return base_dir

    # Try to find workspace
    workspace = find_workspace()
    if workspace:
        return workspace

    # Fallback to BASE_DIR (will fail at runtime with clear error)
    return base_dir


BASE_DIR = get_workspace_base()


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    api_key: str | None = None

    environment: Environment = Environment.dev

    lean_version: str = "v4.15.0"
    repl_path: Path | None = None
    ast_export_bin: Path | None = None
    ast_export_project_dir: Path | None = None
    project_dir: Path | None = None

    max_repls: int = max((os.cpu_count() or 1) - 1, 1)
    max_repl_uses: int = -1
    max_repl_mem: int = 8
    max_wait: int = 3600
    max_ast_jobs: int = max((os.cpu_count() or 1) - 1, 1)

    init_repls: dict[str, int] = {}

    database_url: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_prefix="LEAN_SERVER_"
    )

    @field_validator("max_repl_mem", mode="before")
    def _parse_max_mem(cls, v: str) -> int:
        if isinstance(v, int):
            return cast(int, v * 1024)
        m = re.fullmatch(r"(\d+)([MmGg])", v)
        if m:
            n, unit = m.groups()
            n = int(n)
            return n if unit.lower() == "m" else n * 1024
        raise ValueError("max_repl_mem must be an int or '<number>[M|G]'")

    @field_validator("max_repls", mode="before")
    @classmethod
    def _parse_max_repls(cls, v: int | str) -> int:
        if isinstance(v, str) and v.strip() == "":
            return os.cpu_count() or 1
        return cast(int, v)

    @field_validator("max_ast_jobs", mode="before")
    @classmethod
    def _parse_max_ast_jobs(cls, v: int | str) -> int:
        if isinstance(v, str) and v.strip() == "":
            return os.cpu_count() or 1
        return cast(int, v)

    @model_validator(mode="after")
    def _set_default_paths(self) -> "Settings":
        """Set default paths from workspace if not explicitly provided."""
        # Recompute BASE_DIR in case environment changed
        base_dir = get_workspace_base()

        # Set default paths from workspace if not explicitly provided
        if self.repl_path is None:
            self.repl_path = base_dir / "repl/.lake/build/bin/repl"
        if self.ast_export_bin is None:
            self.ast_export_bin = base_dir / "ast_export/.lake/build/bin/ast-export"
        if self.ast_export_project_dir is None:
            self.ast_export_project_dir = base_dir / "ast_export"
        if self.project_dir is None:
            self.project_dir = base_dir / "mathlib4"

        # Validate paths exist (with helpful error messages)
        self._validate_paths()
        return self

    def _validate_paths(self) -> None:
        """Validate that required paths exist, with helpful error messages."""
        missing_paths = []

        # After model_validator, these should never be None, but type checker needs help
        assert self.repl_path is not None, "repl_path should be set by model_validator"
        assert self.ast_export_bin is not None, (
            "ast_export_bin should be set by model_validator"
        )
        assert self.ast_export_project_dir is not None, (
            "ast_export_project_dir should be set by model_validator"
        )
        assert self.project_dir is not None, (
            "project_dir should be set by model_validator"
        )

        if not self.repl_path.exists():
            missing_paths.append(("REPL", self.repl_path))
        if not self.ast_export_bin.exists():
            missing_paths.append(("AST Export Binary", self.ast_export_bin))
        if not self.ast_export_project_dir.exists():
            missing_paths.append(("AST Export Project", self.ast_export_project_dir))
        if not self.project_dir.exists():
            missing_paths.append(("Mathlib4 Project", self.project_dir))

        if missing_paths:
            workspace = find_workspace()
            error_msg = "Missing required Lean workspace components:\n"
            for name, path in missing_paths:
                error_msg += f"  - {name}: {path}\n"

            error_msg += "\nTo fix this:\n"
            if workspace:
                error_msg += f"  1. Workspace found at: {workspace}\n"
                error_msg += "     Run: kimina-ast-server setup\n"
            else:
                error_msg += "  1. Set up workspace: kimina-ast-server setup\n"
                error_msg += "  2. Or set LEAN_SERVER_WORKSPACE=/path/to/workspace\n"
                error_msg += "  3. Or set individual paths:\n"
                error_msg += "     - LEAN_SERVER_REPL_PATH\n"
                error_msg += "     - LEAN_SERVER_AST_EXPORT_BIN\n"
                error_msg += "     - LEAN_SERVER_AST_EXPORT_PROJECT_DIR\n"
                error_msg += "     - LEAN_SERVER_PROJECT_DIR\n"

            raise ValueError(error_msg)


settings = Settings()

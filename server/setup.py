"""Setup command for kimina-ast-server workspace initialization."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from loguru import logger


def find_setup_script() -> Path:
    """Find the setup.sh script.
    
    Looks for setup.sh in:
    1. Package installation directory (when installed from PyPI)
    2. Repository root (when running from source)
    3. Current directory
    """
    # When installed as a package, __file__ points to:
    # site-packages/server/setup.py
    # setup.sh should be at the package root level
    server_package_dir = Path(__file__).parent
    
    # Try multiple locations relative to the installed package
    # Option 1: Same directory as server package (site-packages/server/setup.sh)
    setup_sh = server_package_dir / "setup.sh"
    if setup_sh.exists():
        return setup_sh
    
    # Option 2: Parent directory (site-packages/setup.sh)
    setup_sh = server_package_dir.parent / "setup.sh"
    if setup_sh.exists():
        return setup_sh
    
    # Try repository root (development mode)
    # server/setup.py -> server/ -> repo root
    repo_root = server_package_dir.parent
    setup_sh = repo_root / "setup.sh"
    if setup_sh.exists():
        return setup_sh
    
    # Last resort: current directory
    setup_sh = Path.cwd() / "setup.sh"
    if setup_sh.exists():
        return setup_sh
    
    # If still not found, try to download it from the repository
    logger.warning("setup.sh not found in package. Attempting to download from repository...")
    try:
        import urllib.request
        setup_url = "https://raw.githubusercontent.com/project-numina/kimina-lean-server/main/setup.sh"
        setup_sh = Path.cwd() / "setup.sh"
        urllib.request.urlretrieve(setup_url, setup_sh)
        setup_sh.chmod(0o755)  # Make it executable
        logger.info(f"Downloaded setup.sh to {setup_sh}")
        return setup_sh
    except Exception as e:
        logger.error(f"Failed to download setup.sh: {e}")
    
    raise FileNotFoundError(
        "Could not find setup.sh. "
        "Please ensure you have installed kimina-ast-server correctly, "
        "or run this from the repository root. "
        f"Checked locations: {server_package_dir / 'setup.sh'}, "
        f"{server_package_dir.parent / 'setup.sh'}, "
        f"{repo_root / 'setup.sh'}, {Path.cwd() / 'setup.sh'}"
    )


def check_prerequisites() -> tuple[bool, list[str]]:
    """Check if required prerequisites are available.
    
    Returns:
        (all_available, missing_tools)
    """
    required_tools = ["curl", "git"]
    missing = []
    
    for tool in required_tools:
        result = subprocess.run(
            ["which", tool],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            missing.append(tool)
    
    return len(missing) == 0, missing


def setup_workspace(
    workspace: Optional[Path] = None,
    save_config: bool = False,
    lean_version: Optional[str] = None,
) -> None:
    """Set up the Lean workspace by running setup.sh.
    
    Args:
        workspace: Path to workspace directory. If None, uses current directory
                  or LEAN_SERVER_WORKSPACE environment variable.
        save_config: If True, create .env file with LEAN_SERVER_WORKSPACE
        lean_version: Lean version to install (defaults to v4.15.0)
    """
    # Check prerequisites
    all_available, missing = check_prerequisites()
    if not all_available:
        logger.error(f"Missing required tools: {', '.join(missing)}")
        logger.error("Please install them and try again.")
        sys.exit(1)
    
    # Determine workspace location
    if workspace:
        workspace_path = Path(workspace).expanduser().resolve()
    elif os.getenv("LEAN_SERVER_WORKSPACE"):
        workspace_path = Path(os.getenv("LEAN_SERVER_WORKSPACE")).expanduser().resolve()
    else:
        workspace_path = Path.cwd()
    
    workspace_path.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Setting up workspace at: {workspace_path}")
    
    # Find setup script
    try:
        setup_sh = find_setup_script()
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(1)
    
    # Prepare environment
    env = os.environ.copy()
    if lean_version:
        env["LEAN_SERVER_LEAN_VERSION"] = lean_version
    
    # Run setup.sh
    logger.info("Running setup.sh (this may take a while)...")
    logger.info("This will install Elan, Lean, and build repl, ast_export, and mathlib4.")
    
    try:
        result = subprocess.run(
            ["bash", str(setup_sh)],
            cwd=str(workspace_path),
            env=env,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        logger.error(f"Setup failed with exit code {e.returncode}")
        logger.error("Please check the output above for errors.")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.warning("Setup interrupted by user")
        sys.exit(1)
    
    # Save config if requested
    if save_config:
        env_file = workspace_path / ".env"
        with open(env_file, "a") as f:
            f.write(f"LEAN_SERVER_WORKSPACE={workspace_path}\n")
        logger.info(f"✓ Configuration saved to {env_file}")
    
    logger.info(f"✓ Workspace setup complete at {workspace_path}")
    logger.info("")
    logger.info("Next steps:")
    if not save_config:
        logger.info(f"  To use from anywhere, set: export LEAN_SERVER_WORKSPACE={workspace_path}")
        logger.info(f"  Or run the server from: {workspace_path}")
    logger.info("  Start the server with: kimina-ast-server")


def main() -> None:
    """Main entry point for setup command."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Set up Lean workspace for kimina-ast-server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Setup in current directory
  kimina-ast-server setup
  
  # Setup in specific directory
  kimina-ast-server setup --workspace ~/lean-workspace
  
  # Setup and save config
  kimina-ast-server setup --workspace ~/lean-workspace --save-config
  
  # Setup with specific Lean version
  kimina-ast-server setup --lean-version v4.21.0
        """,
    )
    parser.add_argument(
        "--workspace",
        type=str,
        help="Path to workspace directory (default: current directory or LEAN_SERVER_WORKSPACE)",
    )
    parser.add_argument(
        "--save-config",
        action="store_true",
        help="Create .env file with LEAN_SERVER_WORKSPACE setting",
    )
    parser.add_argument(
        "--lean-version",
        type=str,
        help="Lean version to install (default: v4.15.0)",
    )
    
    args = parser.parse_args()
    
    workspace_path = Path(args.workspace) if args.workspace else None
    setup_workspace(
        workspace=workspace_path,
        save_config=args.save_config,
        lean_version=args.lean_version,
    )


if __name__ == "__main__":
    main()


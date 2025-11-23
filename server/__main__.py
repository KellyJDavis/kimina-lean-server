import logging
import sys
from types import FrameType
from typing import Any

import uvicorn
from loguru import logger

from .main import app
from .settings import Environment, settings


class InterceptHandler(logging.Handler):
    def emit(self, record: Any) -> None:
        try:
            lvl = logger.level(record.levelname).name
        except ValueError:
            lvl = record.levelno
        frame: FrameType | None = logging.currentframe()
        depth = 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(lvl, record.getMessage())


def run_server() -> None:
    """Run the FastAPI server."""
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        backlog=4096,  # On Google Cloud VMs: `cat /proc/sys/net/core/somaxconn` = 4096
        use_colors=settings.environment != Environment.prod,
        log_config=None,
    )


def main() -> None:
    """Main entry point for kimina-ast-server command.
    
    Supports subcommands:
    - kimina-ast-server (or kimina-ast-server run) - Start the server
    - kimina-ast-server setup - Set up workspace
    """
    # Check for subcommands
    if len(sys.argv) > 1:
        subcommand = sys.argv[1]
        
        if subcommand == "setup":
            # Import and run setup command
            from .setup import main as setup_main
            
            # Remove 'setup' from argv so argparse in setup.py works correctly
            sys.argv = [sys.argv[0]] + sys.argv[2:]
            setup_main()
            return
        elif subcommand in ("--help", "-h", "help"):
            print("""kimina-ast-server - Kimina Lean Server

Commands:
  kimina-ast-server          Start the server (default)
  kimina-ast-server run      Start the server
  kimina-ast-server setup    Set up Lean workspace

Options:
  --help, -h                 Show this help message

For more information, see: https://github.com/project-numina/kimina-lean-server
""")
            return
        elif subcommand == "run":
            # Remove 'run' from argv
            sys.argv = sys.argv[:1] + sys.argv[2:]
            run_server()
            return
        elif subcommand.startswith("-"):
            # It's a flag, pass through to server (though server doesn't use any)
            run_server()
            return
        else:
            # Unknown subcommand
            logger.error(f"Unknown subcommand: {subcommand}")
            logger.info("Use 'kimina-ast-server --help' for usage information")
            sys.exit(1)
    else:
        # No arguments, just run the server
        run_server()


if __name__ == "__main__":
    main()

# Kimina AST Server

FastAPI server for checking Lean 4 code at scale via REPL and AST export.

## Installation

Install from PyPI:

```sh
pip install kimina-ast-server
```

## Quick Start

### 1. Set up the workspace

The server requires a Lean workspace with `repl`, `ast_export`, and `mathlib4` repositories. 
Set it up automatically:

```sh
# Setup in current directory
kimina-ast-server setup

# Or setup in a specific directory
kimina-ast-server setup --workspace ~/lean-workspace

# Setup and save configuration
kimina-ast-server setup --workspace ~/lean-workspace --save-config
```

This will:
- Install Elan (Lean version manager)
- Clone and build the `repl` repository
- Clone and build the `ast_export` repository  
- Clone and build `mathlib4` (this may take a while)

### 2. Start the server

```sh
# If you ran setup in current directory, just run:
kimina-ast-server

# If workspace is elsewhere, set the environment variable:
export LEAN_SERVER_WORKSPACE=~/lean-workspace
kimina-ast-server

# Or if you used --save-config, run from the workspace directory:
cd ~/lean-workspace
kimina-ast-server
```

The server will start on `http://0.0.0.0:8000` by default.

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LEAN_SERVER_WORKSPACE` | Auto-detected | Path to workspace directory containing `repl/`, `ast_export/`, and `mathlib4/` |
| `LEAN_SERVER_HOST` | `0.0.0.0` | Host address to bind the server |
| `LEAN_SERVER_PORT` | `8000` | Port number for the server |
| `LEAN_SERVER_LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `ERROR`, etc.) |
| `LEAN_SERVER_ENVIRONMENT` | `dev` | Environment `dev` or `prod` |
| `LEAN_SERVER_LEAN_VERSION` | `v4.15.0` | Lean version to use |
| `LEAN_SERVER_MAX_REPLS` | CPU count - 1 | Maximum number of REPLs |
| `LEAN_SERVER_MAX_REPL_USES` | `-1` | Maximum number of uses per REPL (-1 is no limit) |
| `LEAN_SERVER_MAX_REPL_MEM` | `8G` | Maximum memory limit for each REPL (Linux-only) |
| `LEAN_SERVER_MAX_WAIT` | `3600` | Maximum wait time for a REPL (in seconds) |
| `LEAN_SERVER_API_KEY` | `None` | Optional API key for authentication |
| `LEAN_SERVER_DATABASE_URL` | `None` | URL for the database (if using one) |

### Workspace Auto-Discovery

The server automatically discovers the workspace in this order:

1. `LEAN_SERVER_WORKSPACE` environment variable
2. Current working directory (if it contains `mathlib4/` or `repl/`)
3. Common locations: `~/kimina-workspace`, `~/lean-workspace`, `~/workspace`

### Individual Path Overrides

If you have a non-standard layout, you can override individual paths:

- `LEAN_SERVER_REPL_PATH` - Path to REPL binary
- `LEAN_SERVER_AST_EXPORT_BIN` - Path to AST export binary
- `LEAN_SERVER_AST_EXPORT_PROJECT_DIR` - Path to AST export project directory
- `LEAN_SERVER_PROJECT_DIR` - Path to mathlib4 directory

## Commands

### `kimina-ast-server`

Start the FastAPI server. This is the default command.

```sh
kimina-ast-server
# or
kimina-ast-server run
```

### `kimina-ast-server setup`

Set up the Lean workspace. This installs Elan, Lean, and builds the required repositories.

```sh
# Basic usage
kimina-ast-server setup

# Specify workspace location
kimina-ast-server setup --workspace ~/lean-workspace

# Save configuration to .env file
kimina-ast-server setup --workspace ~/lean-workspace --save-config

# Specify Lean version
kimina-ast-server setup --lean-version v4.21.0
```

Options:
- `--workspace PATH` - Path to workspace directory (default: current directory or `LEAN_SERVER_WORKSPACE`)
- `--save-config` - Create `.env` file with `LEAN_SERVER_WORKSPACE` setting
- `--lean-version VERSION` - Lean version to install (default: v4.15.0)

## API Endpoints

Once the server is running, you can access:

- **API Documentation**: `http://localhost:8000/docs` (Swagger UI)
- **ReDoc**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/api/openapi.json`

### Main Endpoints

- `POST /api/check` - Check Lean 4 code snippets
- `POST /api/ast` - Get AST for existing modules
- `POST /api/ast_code` - Get AST from raw code
- `GET /health` - Health check endpoint

## Manual Setup

If you prefer to set up the workspace manually:

1. Install [Elan](https://github.com/leanprover/elan) and Lean 4
2. Clone and build the required repositories:
   ```sh
   git clone https://github.com/leanprover-community/repl.git
   cd repl && lake build
   
   git clone https://github.com/KellyJDavis/ast_export.git
   cd ast_export && lake build
   
   git clone https://github.com/leanprover-community/mathlib4.git
   cd mathlib4 && lake exe cache get && lake build
   ```
3. Set `LEAN_SERVER_WORKSPACE` to the directory containing these repositories

## Prerequisites

- Python 3.9+
- `git` and `curl` (for setup command)
- Elan and Lean 4 (installed automatically by setup command)
- Sufficient disk space (~10GB+ for mathlib4)

## Troubleshooting

### "Missing required Lean workspace components"

The server couldn't find the required repositories. Solutions:

1. Run `kimina-ast-server setup` to set up the workspace
2. Set `LEAN_SERVER_WORKSPACE=/path/to/workspace`
3. Set individual path environment variables (see Configuration section)

### "setup.sh not found"

The setup script should be included with the package. If you see this error:

1. Ensure you installed from PyPI: `pip install kimina-ast-server`
2. If installing from source, ensure `setup.sh` is in the repository root

### Server fails to start

Check that:
- All required paths exist and are accessible
- `lake` command is in your PATH (should be after running setup)
- You have sufficient disk space and memory

## Development

For development setup, see the main [README.md](../README.md).

## License

MIT License - see [LICENSE](../LICENSE) file.

## Links

- **Homepage**: https://github.com/project-numina/kimina-lean-server
- **Issues**: https://github.com/project-numina/kimina-lean-server/issues
- **Client SDK**: https://pypi.org/project/kimina-ast-client


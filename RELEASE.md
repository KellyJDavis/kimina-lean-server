# Release Guide

This guide explains how to bump versions and publish both `kimina-ast-client` and `kimina-ast-server` packages to PyPI.

## Current Versions

- **Client**: `0.2.2` (in `pyproject.toml`)
- **Server**: `2.0.0` (in `pyproject-server.toml` and `server/__version__.py`)

## Release Process

### Option 1: Publish via GitHub Release (Recommended)

Both packages will be published automatically when you create a GitHub release:

1. **Bump versions** in the relevant files (see below)
2. **Commit and push** the version changes
3. **Create a GitHub release** with a tag (e.g., `v0.2.3` or `v2.0.1`)
4. **Both workflows will trigger** and publish to PyPI

### Option 2: Manual Workflow Dispatch

Publish packages individually using GitHub Actions:

1. **Bump versions** in the relevant files
2. **Commit and push** the version changes
3. **Go to GitHub Actions** → Select the workflow → "Run workflow"
4. **Choose which package** to publish (or publish both separately)

## Version Bump Steps

### For Client Package (`kimina-ast-client`)

1. **Update version in `pyproject.toml`**:
   ```toml
   [project]
   name = "kimina-ast-client"
   version = "0.2.3"  # Bump version here
   ```

2. **Update lock file** (if using uv):
   ```sh
   uv lock
   ```

3. **Commit the changes**:
   ```sh
   git add pyproject.toml uv.lock
   git commit -m "[kimina-ast-client] Bump version to 0.2.3"
   ```

### For Server Package (`kimina-ast-server`)

1. **Update version in `pyproject-server.toml`**:
   ```toml
   [project]
   name = "kimina-ast-server"
   version = "2.0.1"  # Bump version here
   ```

2. **Update version in `server/__version__.py`**:
   ```python
   __version__ = "2.0.1"  # Must match pyproject-server.toml
   ```

3. **Commit the changes**:
   ```sh
   git add pyproject-server.toml server/__version__.py
   git commit -m "[kimina-ast-server] Bump version to 2.0.1"
   ```

### For Both Packages

If releasing both packages together:

```sh
# Update client version
# Edit pyproject.toml
uv lock

# Update server version  
# Edit pyproject-server.toml and server/__version__.py

# Commit
git add pyproject.toml pyproject-server.toml server/__version__.py uv.lock
git commit -m "[release] Bump client to 0.2.3 and server to 2.0.1"
```

## Publishing to PyPI

### Automatic (via GitHub Release)

1. **Push version changes** to the repository
2. **Create a new release** on GitHub:
   - Go to Releases → "Draft a new release"
   - Create a new tag (e.g., `v0.2.3` or `v2.0.1`)
   - Fill in release notes
   - Click "Publish release"
3. **Both workflows will automatically run** and publish to PyPI

### Manual (via Workflow Dispatch)

1. **Push version changes** to the repository
2. **Trigger client workflow**:
   - Go to Actions → "Publish Client to PyPI"
   - Click "Run workflow"
   - Select branch and set `publish: true`
   - Click "Run workflow"
3. **Trigger server workflow**:
   - Go to Actions → "Publish Server to PyPI"
   - Click "Run workflow"
   - Select branch and set `publish: true`
   - Click "Run workflow"

## Version Numbering

Follow [Semantic Versioning](https://semver.org/):
- **MAJOR** (1.0.0): Breaking changes
- **MINOR** (0.1.0): New features, backward compatible
- **PATCH** (0.0.1): Bug fixes, backward compatible

## Important Notes

1. **Version synchronization**: Server version in `pyproject-server.toml` and `server/__version__.py` must match
2. **Prisma client**: Server workflow generates Prisma client before building - ensure `prisma/schema.prisma` is up to date
3. **Tag format**: GitHub releases use tags like `v0.2.3` or `v2.0.1` (with `v` prefix)
4. **Both packages publish on release**: Currently, both packages publish when any release is created. To publish independently, use manual workflow dispatch or filter by tag name
5. **PyPI API token**: Ensure `PYPI_API_TOKEN` secret is configured in GitHub repository settings

## Verification

After publishing, verify packages are available:

```sh
# Check client
pip index versions kimina-ast-client

# Check server
pip index versions kimina-ast-server
```

Or visit:
- Client: https://pypi.org/project/kimina-ast-client/
- Server: https://pypi.org/project/kimina-ast-server/


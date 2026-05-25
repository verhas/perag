#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Syncing dependencies ==="
uv sync --all-extras

echo "=== Running tests ==="
uv run pytest tests/ -v

echo "=== Building distribution ==="
uv build

echo "=== Uploading to PyPI ==="
VERSION=$(uv run python -c "from importlib.metadata import version; print(version('perag'))")
PYPI_TOKEN=$(python3 -c "import configparser,os; c=configparser.ConfigParser(); c.read(os.path.expanduser('~/.pypirc')); print(c['pypi']['password'])")
uv publish dist/perag-"$VERSION"* --username __token__ --password "$PYPI_TOKEN"

echo "=== Released perag $VERSION ==="

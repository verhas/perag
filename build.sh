#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Syncing dependencies ==="
uv sync --all-extras --python /opt/homebrew/bin/python3

echo "=== Running tests ==="
uv run pytest tests/ -v

echo "=== Building distribution ==="
uv build

echo "=== Built perag $VERSION ==="

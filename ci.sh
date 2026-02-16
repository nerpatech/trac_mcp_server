#!/bin/bash
# Local CI — mirrors GitHub Actions checks
# Run before pushing to catch issues locally
set -e

echo "=== Lint ==="
ruff check src/ tests/ scripts/
ruff format --check src/ tests/ scripts/

echo ""
echo "=== Unit Tests ==="
pytest tests/

echo ""
echo "=== Build Verification ==="
bash build.sh

echo ""
echo "=== All checks passed ==="

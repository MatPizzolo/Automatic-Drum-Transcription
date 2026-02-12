#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# cleanup.sh — Remove build artifacts, caches, and temporary files
# Usage: ./scripts/cleanup.sh [--deep]
#   --deep: also remove node_modules, .venv, and Docker volumes
# ============================================================================

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEEP=false
[[ "${1:-}" == "--deep" ]] && DEEP=true

echo "==> Cleaning build artifacts and caches..."

# Python
find "$ROOT/backend" -type d -name "__pycache__" -not -path "*/.venv/*" -exec rm -rf {} + 2>/dev/null || true
find "$ROOT/backend" -type f -name "*.pyc" -not -path "*/.venv/*" -delete 2>/dev/null || true
find "$ROOT/backend" -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
rm -rf "$ROOT/backend/.pytest_cache"
rm -rf "$ROOT/backend/.mypy_cache"
rm -rf "$ROOT/backend/.ruff_cache"

# Frontend
rm -rf "$ROOT/frontend/.next"
rm -rf "$ROOT/frontend/out"
rm -rf "$ROOT/frontend/.turbo"

# Docker
echo "==> Pruning dangling Docker images..."
docker image prune -f 2>/dev/null || true

# Temp/artifacts (local dev only)
rm -rf "$ROOT/artifacts"
rm -rf "$ROOT/model_cache"

if $DEEP; then
    echo "==> Deep clean: removing node_modules, .venv, Docker volumes..."
    rm -rf "$ROOT/frontend/node_modules"
    rm -rf "$ROOT/backend/.venv"
    docker compose -f "$ROOT/docker-compose.yml" down -v 2>/dev/null || true
fi

echo "==> Done."

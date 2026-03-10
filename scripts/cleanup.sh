#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# cleanup.sh — Remove build artifacts, caches, and temporary files
# Usage: ./scripts/cleanup.sh [--deep] [--nuke]
#   --deep: also remove node_modules, .venv, and Docker volumes
#   --nuke: everything in --deep PLUS wipe the Docker builder cache and all
#           project images (forces 100% fresh pip install on next build)
# ============================================================================

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEEP=false
NUKE=false

for arg in "$@"; do
    case "$arg" in
        --deep) DEEP=true ;;
        --nuke) NUKE=true; DEEP=true ;;
    esac
done

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

if $NUKE; then
    echo "==> NUKE: removing project images..."
    docker images --format '{{.Repository}}:{{.Tag}}' \
        | grep -E '^(automatic-drum-transcription|drumscribe)' \
        | xargs docker rmi -f 2>/dev/null || true

    echo "==> NUKE: pruning entire Docker builder cache..."
    docker builder prune -af
fi

# Temp/artifacts (local dev only)
rm -rf "$ROOT/artifacts"
rm -rf "$ROOT/model_cache"

if $DEEP; then
    echo "==> Deep clean: removing node_modules, .venv, Docker volumes..."
    rm -rf "$ROOT/frontend/node_modules"
    rm -rf "$ROOT/backend/.venv"
    docker compose -f "$ROOT/docker-compose.yml" down -v 2>/dev/null || true
fi

if $NUKE; then
    echo "==> NUKE complete — run './scripts/start.sh --nuke' for a fully fresh build."
fi

echo "==> Done."

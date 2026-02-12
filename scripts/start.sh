#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# start.sh — Start the full DrumScribe stack for development
# Usage: ./scripts/start.sh [--prod] [--observability]
#   --prod:          use production compose only (no dev overrides)
#   --observability: include Jaeger tracing UI
# ============================================================================

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PROD=false
OBS_PROFILE=""

for arg in "$@"; do
    case "$arg" in
        --prod) PROD=true ;;
        --observability) OBS_PROFILE="--profile observability" ;;
    esac
done

# Ensure .env exists
if [ ! -f "$ROOT/.env" ]; then
    echo "==> No .env found. Copying from .env.example..."
    cp "$ROOT/.env.example" "$ROOT/.env"
fi

# Build and start
if $PROD; then
    echo "==> Starting in PRODUCTION mode (no dev overrides)..."
    docker compose -f "$ROOT/docker-compose.yml" $OBS_PROFILE up --build -d
else
    echo "==> Starting in DEVELOPMENT mode (with hot-reload)..."
    docker compose -f "$ROOT/docker-compose.yml" -f "$ROOT/docker-compose.override.yml" $OBS_PROFILE up --build
fi

#!/usr/bin/env bash
set -euo pipefail

# Worker entrypoint — download models before starting Celery.
# This ensures the CNN model (.h5) and Demucs weights are cached
# in the persistent volume before any job is processed.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CACHE_DIR="${MODEL_CACHE_DIR:-/data/models}"

echo "==> DrumScribe worker entrypoint"
echo "    MODEL_URI=${MODEL_URI:-<not set>}"
echo "    MODEL_VERSION=${MODEL_VERSION:-v1.0.0}"
echo "    MODEL_CACHE_DIR=${CACHE_DIR}"

# Run model download (idempotent — skips if already cached)
if [ -f "$SCRIPT_DIR/download_models.sh" ]; then
    bash "$SCRIPT_DIR/download_models.sh" "$CACHE_DIR"
else
    echo "    WARNING: download_models.sh not found at $SCRIPT_DIR"
fi

echo "==> Starting Celery worker..."
exec "$@"

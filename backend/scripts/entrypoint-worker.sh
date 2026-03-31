#!/usr/bin/env bash
set -euo pipefail

# Worker Entrypoint
#
# Ensures the model cache directory is ready and optionally pre-warms ML models,
# then starts the Celery worker.
#
# Exit codes:
#   0: Success
#   1: Critical failure (model setup failed)
#   2: Setup script not found

# Fix PYTHONPATH for dev mode when ./backend is bind-mounted over /app
export PYTHONPATH="${PYTHONPATH:-/usr/local/lib/python3.11/site-packages}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> DrumScribe Worker Entrypoint"
echo "    Environment:"
echo "      MODEL_CACHE_DIR=${MODEL_CACHE_DIR:-/data/models}"
echo "      STORAGE_BACKEND=${STORAGE_BACKEND:-local}"
echo "      WORKER_MODE=${WORKER_MODE:-false}"
echo ""

# Verify setup script exists
if [ ! -f "$SCRIPT_DIR/download_models.sh" ]; then
    echo "✗ FATAL ERROR: download_models.sh not found at $SCRIPT_DIR"
    echo "  This indicates a build or packaging issue."
    exit 2
fi

# Run model setup
if bash "$SCRIPT_DIR/download_models.sh"; then
    echo ""
    echo "==> ✓ Worker initialization complete"
    echo "==> Starting Celery worker..."
    echo ""
    exec "$@"
else
    EXIT_CODE=$?
    echo ""
    echo "==> ✗ FATAL ERROR: Model setup failed (exit code: $EXIT_CODE)"
    echo ""
    echo "Troubleshooting:"
    echo "  1. Check logs above for specific Python errors"
    echo "  2. Verify MODEL_CACHE_DIR is writable"
    echo "  3. Ensure network connectivity for HuggingFace / audio-separator downloads"
    echo ""
    exit 1
fi

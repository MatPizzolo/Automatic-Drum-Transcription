#!/usr/bin/env bash
set -euo pipefail

# Worker Entrypoint - Production-grade model initialization
#
# This entrypoint delegates all model setup to the Python model_manager module
# via download_models.sh. No inline Python code here - all logic is in proper
# Python modules with structured logging and error handling.
#
# Exit codes:
#   0: Success, worker can start
#   1: Critical failure (model setup failed)
#   2: Model setup script not found

# Fix PYTHONPATH for dev mode when ./backend is bind-mounted over /app
# This ensures Python can find packages installed in /usr/local/lib/python3.11/site-packages
export PYTHONPATH="${PYTHONPATH:-/usr/local/lib/python3.11/site-packages}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> DrumScribe Worker Entrypoint"
echo "    Environment:"
echo "      MODEL_URI=${MODEL_URI:-<not set>}"
echo "      MODEL_CACHE_DIR=${MODEL_CACHE_DIR:-/data/models}"
echo "      TORCH_HOME=${TORCH_HOME:-<not set>}"
echo "      STORAGE_BACKEND=${STORAGE_BACKEND:-local}"
echo ""

# Verify model setup script exists
if [ ! -f "$SCRIPT_DIR/download_models.sh" ]; then
    echo "✗ FATAL ERROR: download_models.sh not found at $SCRIPT_DIR"
    echo "  This indicates a build or packaging issue."
    exit 2
fi

# Run model setup (delegates to Python model_manager)
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
    echo "  2. Verify MODEL_URI is set correctly in docker-compose.yml"
    echo "  3. Ensure network connectivity for remote models"
    echo "  4. Check TORCH_HOME directory permissions"
    echo "  5. Review app/core/model_manager.py logs for details"
    echo ""
    exit 1
fi

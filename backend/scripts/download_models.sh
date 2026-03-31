#!/usr/bin/env bash
set -euo pipefail

# Model Warm-Up Script
#
# Ensures the model cache directory exists and pre-warms ML models
# so the first job doesn't pay a cold-start penalty.
#
# Models are fetched automatically from their respective sources:
#   - BS-Roformer: downloaded by audio-separator on first use
#   - AST (MIT/ast-finetuned-audioset-10-10-0.4593): downloaded from HuggingFace
#
# Environment variables:
#   MODEL_CACHE_DIR: Directory for model caching (default: /data/models)
#   WORKER_MODE: Set to "true" to trigger model preloading (default: false)

CACHE_DIR="${MODEL_CACHE_DIR:-/data/models}"

echo "==> DrumScribe Model Setup"
echo "    MODEL_CACHE_DIR=${CACHE_DIR}"
echo ""

# Ensure cache directory exists with correct permissions
mkdir -p "${CACHE_DIR}"

# Pre-warm models if running as a heavy-compute worker
if [ "${WORKER_MODE:-false}" = "true" ]; then
    echo "==> Pre-warming ML models (WORKER_MODE=true)..."
    python3 -c "
import sys
sys.path.insert(0, '/app')
try:
    from app.ml.registry import preload_models
    preload_models()
    print('==> Models pre-warmed successfully')
except Exception as e:
    print(f'==> Warning: Model pre-warming failed: {e}', file=sys.stderr)
    print('==> Models will load lazily on first task execution')
"
else
    echo "==> Skipping model pre-warm (WORKER_MODE != true)"
    echo "    Models will load lazily on first task execution"
fi

echo ""
echo "==> ✓ Model setup complete"

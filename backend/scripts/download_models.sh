#!/usr/bin/env bash
set -euo pipefail

# Model Setup Script - Delegates to Python model_manager module
# 
# This script is a thin wrapper around the production-grade Python model manager.
# All model initialization logic has been moved to app/core/model_manager.py
# for better error handling, logging, and maintainability.
#
# Usage: ./scripts/download_models.sh
#
# Environment variables (read by model_manager.py):
#   MODEL_URI: URL/path to CNN model
#   MODEL_CACHE_DIR: Directory for model caching
#   TORCH_HOME: Directory for torch.hub cache
#   STORAGE_BACKEND: Storage backend type (local, s3)

echo "==> DrumScribe Model Setup"
echo "==> Delegating to Python model manager..."
echo ""

# Execute the Python model manager
# This handles all model initialization with proper error handling
python3 -m app.core.model_manager

# Capture exit code
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo "==> ✓ Model setup completed successfully"
    exit 0
else
    echo ""
    echo "==> ✗ Model setup failed (exit code: $EXIT_CODE)"
    exit $EXIT_CODE
fi

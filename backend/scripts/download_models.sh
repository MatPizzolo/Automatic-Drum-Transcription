#!/usr/bin/env bash
set -euo pipefail

# Download pre-trained models for the DrumScribe ML pipeline.
# Usage: ./scripts/download_models.sh [CACHE_DIR]
#
# Downloads:
#   1. Demucs htdemucs weights (auto-downloaded by torch.hub on first run)
#   2. AnNOTEator CNN model (complete_network.h5)

CACHE_DIR="${1:-./model_cache}"
mkdir -p "$CACHE_DIR"

echo "==> Model cache directory: $CACHE_DIR"

# --- 1. Demucs: trigger torch.hub download ---
echo "==> Pre-downloading Demucs (htdemucs) weights..."
python3 -c "
from demucs import pretrained
model = pretrained.get_model('htdemucs')
print(f'Demucs model loaded: {model.name}, samplerate={model.samplerate}')
" && echo "    Demucs weights cached." || echo "    WARNING: Demucs download failed (will retry at worker startup)."

# --- 2. CNN model ---
MODEL_URI="${MODEL_URI:-}"
MODEL_VERSION="${MODEL_VERSION:-v1.0.0}"
CNN_DIR="$CACHE_DIR/complete_network/$MODEL_VERSION"
mkdir -p "$CNN_DIR"

if [ -n "$MODEL_URI" ]; then
    CNN_DEST="$CNN_DIR/$(basename "$MODEL_URI")"
    if [ -f "$CNN_DEST" ] && [ -s "$CNN_DEST" ]; then
        echo "==> CNN model already cached: $CNN_DEST"
    else
        echo "==> Downloading CNN model from $MODEL_URI..."
        if [[ "$MODEL_URI" == http* ]]; then
            curl -fSL --progress-bar -o "$CNN_DEST" "$MODEL_URI"
        elif [[ "$MODEL_URI" == s3://* ]]; then
            aws s3 cp "$MODEL_URI" "$CNN_DEST"
        else
            cp "$MODEL_URI" "$CNN_DEST"
        fi
        echo "    CNN model saved: $CNN_DEST ($(du -h "$CNN_DEST" | cut -f1))"
    fi
else
    echo "==> MODEL_URI not set — skipping CNN download."
    echo "    Set MODEL_URI to the path/URL of complete_network.h5"
fi

echo ""
echo "==> Done. Models cached in: $CACHE_DIR"
ls -lhR "$CACHE_DIR" 2>/dev/null || true

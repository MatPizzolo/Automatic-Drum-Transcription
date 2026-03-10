# DrumScribe Inference Models

This directory contains ML model files and cached weights for DrumScribe's drum transcription pipeline.

## 📁 Directory Structure

```
inference/
├── pretrained_models/
│   └── annoteators/
│       └── complete_network.h5    # AnNOTEator CNN weights (2 MB)
└── demucs/                         # Demucs model cache (~300 MB)
    └── htdemucs.th                 # Downloaded on first run
```

## 🎯 Models Used

### 1. AnNOTEator CNN (Hit Classification)

**Purpose:** Classifies individual drum hits into instrument categories

**Details:**
- Architecture: Convolutional Neural Network
- Input: Mel-spectrogram frames
- Output: 26 drum instrument classes
- Size: ~2 MB
- Source: [AnNOTEator Research](https://github.com/cb-42/AnNOTEator)

**Classes:**
- Kick, Snare, Hi-Hat (closed/open/pedal)
- Toms (high/mid/low/floor)
- Cymbals (crash/ride/china/splash)
- Percussion (cowbell, tambourine, etc.)

### 2. Demucs (Source Separation)

**Purpose:** Isolates drum track from full mix

**Details:**
- Architecture: Hybrid Transformer Demucs (htdemucs)
- Input: Stereo audio (any sample rate)
- Output: 4 stems (drums, bass, vocals, other)
- Size: ~300 MB
- Auto-downloaded on first worker start

**Configuration:**
```python
DEMUCS_MODEL_NAME=htdemucs  # or htdemucs_ft, mdx_extra
```

## 🚀 Setup

### Option 1: Manual Download (Recommended for Production)

```bash
# Create directory
mkdir -p inference/pretrained_models/annoteators

# Download AnNOTEator weights
cd inference/pretrained_models/annoteators
wget https://your-model-host.com/complete_network.h5

# Verify checksum (optional but recommended)
sha256sum complete_network.h5
```

### Option 2: Auto-Download (Development)

Set `MODEL_URI` in `.env` to an HTTP/S3 URL:

```bash
# .env
MODEL_URI=https://your-bucket.s3.amazonaws.com/models/v1.0.0/complete_network.h5
MODEL_VERSION=v1.0.0
MODEL_SHA256=<optional-checksum>
```

Workers will auto-download on first start.

### Option 3: S3 URI (Production)

```bash
# .env
MODEL_URI=s3://drumscribe-models/v1.0.0/complete_network.h5
MODEL_VERSION=v1.0.0
MODEL_SHA256=<checksum>
```

Requires AWS credentials configured in environment.

## 🔧 Model Management

### Caching Strategy

**AnNOTEator CNN:**
- Loaded once per worker process (singleton pattern)
- Cached in memory for lifetime of worker
- Workers recycle after processing N jobs to prevent memory leaks

**Demucs:**
- Downloaded to `TORCH_HOME` directory
- Shared across all worker processes
- Persisted in Docker volume

### Version Control

Models are versioned via `MODEL_VERSION` environment variable:

```bash
MODEL_VERSION=v1.0.0  # Triggers cache invalidation on change
```

### Integrity Verification

Optional SHA256 checksum verification:

```bash
MODEL_SHA256=abc123...  # Fails fast if download corrupted
```

## 📊 Resource Requirements

| Model | Memory | Disk | Load Time |
|-------|--------|------|-----------|
| AnNOTEator CNN | ~100 MB | 2 MB | ~1s |
| Demucs htdemucs | ~3 GB | 300 MB | ~5s |

**Recommendations:**
- MVP mode: 4 GB RAM minimum
- Production: 8 GB RAM recommended
- Disk: 1 GB for models + artifacts

## 🐛 Troubleshooting

### Model file not found

```bash
# Check if file exists
ls -lh inference/pretrained_models/annoteators/complete_network.h5

# Verify permissions
chmod 644 inference/pretrained_models/annoteators/complete_network.h5
```

### Demucs download fails

```bash
# Check TORCH_HOME directory
echo $TORCH_HOME

# Manually download
python -c "import demucs.pretrained; demucs.pretrained.get_model('htdemucs')"
```

### Out of memory during inference

```bash
# Reduce worker concurrency
# In docker-compose.yml:
worker-heavy:
  command: celery -A app.worker worker --concurrency=1 --max-memory-per-child=4000000
```

## 🔐 Security

**Do NOT commit model files to Git:**
- Models are large binary files (2-300 MB)
- Use Git LFS or external hosting
- `.gitignore` already excludes `*.h5` and `*.th` files

**Production checklist:**
- ✅ Use SHA256 verification
- ✅ Host models on private S3/CDN
- ✅ Use signed URLs with expiration
- ✅ Scan models for malware before deployment

## 📚 References

- [AnNOTEator Paper](https://github.com/cb-42/AnNOTEator) - Original research
- [Demucs](https://github.com/facebookresearch/demucs) - Source separation
- [Model Registry](../backend/app/ml/registry.py) - DrumScribe model management code

## 🤝 Contributing

When updating models:

1. Increment `MODEL_VERSION` in `.env.example`
2. Update SHA256 checksum
3. Document architecture changes in `docs/ML_PIPELINE.md`
4. Test with `make init` to verify auto-download
5. Update this README with new model details

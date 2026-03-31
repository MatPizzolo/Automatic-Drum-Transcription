# Modal Serverless GPU Deployment Guide

This guide explains how to deploy and use the Modal serverless GPU infrastructure for DrumScribe's ML pipeline.

## 📋 Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Deployment Steps](#deployment-steps)
- [Configuration](#configuration)
- [Usage Modes](#usage-modes)
- [Cost Analysis](#cost-analysis)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

---

## Overview

Modal provides serverless GPU infrastructure that allows DrumScribe to:

- **Scale to zero**: Pay only for actual inference time (no idle GPU costs)
- **Auto-scale**: Handle 0 to 1000s of concurrent requests automatically
- **Optimize cold starts**: Pre-cached model weights enable <2 second boot times
- **Reduce costs**: ~90-95% cost reduction vs. always-on GPU instances

### Architecture

```
┌─────────────┐
│   Frontend  │
└──────┬──────┘
       │
       ▼
┌─────────────┐      ┌──────────────────┐
│  FastAPI    │─────▶│  Celery Worker   │
│   Backend   │      └────────┬─────────┘
└─────────────┘               │
                              │ USE_MODAL=true
                              ▼
                    ┌──────────────────────┐
                    │   Modal Serverless   │
                    │   GPU (NVIDIA T4)    │
                    │                      │
                    │  • BS-Roformer       │
                    │  • AST Transformer   │
                    │  • ML Guardrails     │
                    └──────────────────────┘
```

---

## Prerequisites

### 1. Modal Account

```bash
# Sign up at https://modal.com
# Free tier includes $30/month credits

# Install Modal CLI
pip install modal

# Authenticate
modal token new
```

### 2. Backend Dependencies

```bash
# Install Modal SDK (already in requirements-api.txt)
pip install modal>=0.63.0
```

---

## Deployment Steps

### Step 1: Deploy Modal App

```bash
# From project root
cd backend/infrastructure

# Deploy the Modal app (builds Docker image with cached weights)
modal deploy modal_app.py
```

**What happens during deployment:**

1. **Image Build** (~5-10 minutes first time):
   - Installs Python 3.11 + system dependencies (ffmpeg, libsndfile1)
   - Installs ML packages (torch, torchaudio, transformers, audio-separator, etc.)
   - **Downloads and caches model weights** (AST + BS-Roformer)
   - Saves image to Modal's registry

2. **Function Registration**:
   - Registers `process_audio_pipeline` function
   - Configures GPU (T4), memory (8GB), timeout (600s)
   - Makes function callable via Modal SDK

**Output:**
```
✓ Created objects.
├── 🔨 Created mount /Users/.../infrastructure
├── 🔨 Created download_model_weights => download_model_weights
└── 🔨 Created process_audio_pipeline => process_audio_pipeline
✓ App deployed! 🎉

View Deployment: https://modal.com/apps/drumscribe-ml
```

### Step 2: Verify Deployment

```bash
# Test the deployed function
modal run backend/infrastructure/modal_app.py --audio-url "https://example.com/test.mp3"
```

### Step 3: Enable in Backend

Update `.env`:

```bash
# Enable Modal serverless GPU
USE_MODAL=true
MODAL_APP_NAME=drumscribe-ml
MODAL_FUNCTION_NAME=process_audio_pipeline
```

### Step 4: Restart Workers

```bash
# If using Docker Compose
docker compose restart worker-default worker-heavy

# If running locally
celery -A app.worker worker --loglevel=info
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_MODAL` | `false` | Enable Modal serverless GPU inference |
| `MODAL_APP_NAME` | `drumscribe-ml` | Name of deployed Modal app |
| `MODAL_FUNCTION_NAME` | `process_audio_pipeline` | Name of serverless function |

### Modal App Configuration

Edit `backend/infrastructure/modal_app.py` to customize:

```python
@app.function(
    image=image,
    gpu="T4",              # Options: "T4", "A10G", "A100"
    timeout=600,           # Max execution time (seconds)
    memory=8192,           # RAM in MB
    cpu=2.0,               # Number of vCPUs
)
```

**GPU Options:**

| GPU | vRAM | Cost/hour | Best For |
|-----|------|-----------|----------|
| **T4** | 16GB | ~$0.60 | Cost-effective (recommended) |
| **A10G** | 24GB | ~$1.10 | Faster inference |
| **A100** | 40GB | ~$4.00 | Batch processing |

---

## Usage Modes

### Mode 1: Local Inference (Default)

```bash
USE_MODAL=false
```

- Runs ML pipeline on local GPU/CPU
- No external dependencies
- Good for development

### Mode 2: Modal Serverless (Production)

```bash
USE_MODAL=true
```

- Offloads inference to Modal's GPUs
- Automatic scaling and cost optimization
- Recommended for production

### Mode 3: Hybrid (Fallback)

The `ModalClient` automatically falls back to local inference if:

- Modal SDK not installed
- Modal function unavailable
- Network errors

```python
# Automatic fallback logic in modal_client.py
if self.use_modal and self._modal_function is not None:
    try:
        return self._process_audio_modal(...)
    except Exception as e:
        logger.error("modal_inference_failed", error=str(e))
        # Falls back to local inference
```

---

## Cost Analysis

### Pricing Breakdown

**Modal T4 GPU:**
- **Compute**: ~$0.60/hour
- **Typical track**: 30-120 seconds inference
- **Cost per track**: $0.02-$0.04

**Monthly Costs (1000 tracks):**

| Deployment | Monthly Cost | Notes |
|------------|--------------|-------|
| **Always-on GPU (AWS g4dn.xlarge)** | $432/month | 24/7 running |
| **Modal Serverless** | $20-$40/month | Pay per inference |
| **Savings** | **$390-$410/month** | 90-95% reduction |

### Cold Start Optimization Impact

**Without weight caching:**
- Cold start: 30-60 seconds
- GPU idle cost: $0.50-$1.00 per cold start
- 100 cold starts/day = **$50-$100/day wasted**

**With weight caching (our implementation):**
- Cold start: <2 seconds
- GPU idle cost: $0.01-$0.03 per cold start
- 100 cold starts/day = **$1-$3/day**
- **Savings: $47-$97/day** (~$1,500-$3,000/month)

### Example Cost Calculation

**Scenario: 5,000 tracks/month**

```
Inference time per track: 60 seconds average
GPU cost: $0.60/hour = $0.01/minute

Total inference time: 5,000 tracks × 1 minute = 5,000 minutes
Total cost: 5,000 minutes × $0.01 = $50/month

Cold starts (10% of requests): 500 cold starts × $0.03 = $15/month

Total Modal cost: $65/month
```

**vs. Always-on GPU:**
```
AWS g4dn.xlarge: $432/month
Savings: $367/month (85% reduction)
```

---

## Monitoring

### Modal Dashboard

View real-time metrics at: `https://modal.com/apps/drumscribe-ml`

**Metrics available:**
- Function invocations (count, duration)
- GPU utilization
- Cold start frequency
- Error rates
- Cost breakdown

### Backend Logs

```bash
# Check worker logs for Modal usage
docker compose logs -f worker-default

# Look for these log events:
# - modal_inference_start
# - modal_inference_complete
# - modal_inference_failed (fallback to local)
```

### Example Log Output

```json
{
  "event": "modal_inference_start",
  "job_id": "abc123",
  "drums_path": "/tmp/drums.wav"
}

{
  "event": "modal_inference_complete",
  "job_id": "abc123",
  "total_hits": 245,
  "bpm": 128,
  "duration_ms": 45230
}
```

---

## Troubleshooting

### Issue: Modal function not found

**Error:**
```
modal.exception.NotFoundError: App 'drumscribe-ml' not found
```

**Solution:**
```bash
# Redeploy the Modal app
modal deploy backend/infrastructure/modal_app.py

# Verify deployment
modal app list
```

### Issue: Cold starts taking >10 seconds

**Cause:** Model weights not cached in image

**Solution:**
```bash
# Rebuild image with weight caching
modal deploy backend/infrastructure/modal_app.py --force-build

# Verify weights are cached
modal run backend/infrastructure/modal_app.py --audio-url "test.mp3"
# Should see: "✅ AST model cached" and "✅ BS-Roformer cached"
```

### Issue: GPU timeout errors

**Error:**
```
TimeoutError: Function exceeded 600 second timeout
```

**Solution:**

1. **Increase timeout** (for very long tracks):
   ```python
   @app.function(
       gpu="T4",
       timeout=900,  # 15 minutes
   )
   ```

2. **Or use faster GPU**:
   ```python
   @app.function(
       gpu="A10G",  # 2-3x faster than T4
       timeout=600,
   )
   ```

### Issue: Automatic fallback to local inference

**Log:**
```
modal_inference_failed: Connection timeout
local_inference_start: Falling back to local GPU
```

**Causes:**
- Network connectivity issues
- Modal service outage
- Rate limiting

**Solution:**
- Check Modal status: https://status.modal.com
- Verify network connectivity
- Local fallback ensures service continuity

---

## Best Practices

### 1. Development vs. Production

**Development:**
```bash
USE_MODAL=false  # Use local inference for fast iteration
```

**Production:**
```bash
USE_MODAL=true   # Use Modal for cost optimization
```

### 2. Image Versioning

Tag your Modal deployments:

```bash
# Deploy with version tag
modal deploy backend/infrastructure/modal_app.py --name drumscribe-ml-v1.2.0

# Update .env to use specific version
MODAL_APP_NAME=drumscribe-ml-v1.2.0
```

### 3. Cost Optimization

- **Use T4 GPUs** for most workloads (cost-effective)
- **Monitor cold start frequency** (optimize if >20% of requests)
- **Set appropriate timeouts** (don't pay for stuck jobs)
- **Use Modal's free tier** ($30/month credits for testing)

### 4. Monitoring Alerts

Set up alerts in Modal dashboard:
- Error rate >5%
- Average duration >2 minutes
- Cold start rate >30%

---

## Migration Checklist

- [ ] Modal account created and authenticated
- [ ] Modal app deployed successfully
- [ ] Test inference with sample audio
- [ ] Update `.env` with `USE_MODAL=true`
- [ ] Restart backend workers
- [ ] Monitor logs for successful Modal calls
- [ ] Verify cost savings in Modal dashboard
- [ ] Set up monitoring alerts
- [ ] Document any custom configurations

---

## Additional Resources

- **Modal Documentation**: https://modal.com/docs
- **Modal Pricing**: https://modal.com/pricing
- **Modal Status**: https://status.modal.com
- **DrumScribe ML Pipeline**: `docs/ML_PIPELINE.md`

---

## Support

For issues or questions:

1. Check Modal logs: `https://modal.com/apps/drumscribe-ml`
2. Check backend logs: `docker compose logs worker-default`
3. Review this troubleshooting guide
4. Contact Modal support: support@modal.com

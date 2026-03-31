# Production Deployment Guide

Complete guide for deploying DrumScribe to production using Vercel, Fly.io, Modal, and Cloudflare R2.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Deployment Steps](#deployment-steps)
- [Environment Configuration](#environment-configuration)
- [Monitoring & Maintenance](#monitoring--maintenance)
- [Troubleshooting](#troubleshooting)

---

## Architecture Overview

DrumScribe uses a fully decoupled serverless architecture:

```
┌─────────────────┐
│  Vercel (Edge)  │  Frontend (Next.js 15)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Fly.io (Edge)  │  API (FastAPI + PostgreSQL)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Modal (GPU)    │  ML Inference (ONNX Runtime)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Cloudflare R2   │  Object Storage (Audio + Results)
└─────────────────┘
```

**Benefits:**
- **Scale-to-Zero**: All services scale to zero when idle
- **Global Edge**: Sub-100ms latency worldwide
- **Cost-Effective**: 87-92% cheaper than always-on GPU
- **Zero Ops**: No infrastructure management

---

## Prerequisites

### Required Accounts

1. **Vercel** (Frontend)
   - Sign up: https://vercel.com/signup
   - Free tier: Unlimited deployments

2. **Fly.io** (API + Database)
   - Sign up: https://fly.io/app/sign-up
   - Free tier: 3 shared-cpu VMs + 3GB PostgreSQL

3. **Modal** (Serverless GPU)
   - Sign up: https://modal.com
   - Free tier: $30/month credits

4. **Cloudflare** (R2 Storage)
   - Sign up: https://dash.cloudflare.com/sign-up
   - Free tier: 10GB storage + 1M requests/month

### Required Tools

```bash
# Vercel CLI
npm install -g vercel

# Fly.io CLI
curl -L https://fly.io/install.sh | sh

# Modal CLI
pip install modal
```

---

## Deployment Steps

### Step 1: Deploy Cloudflare R2 (Storage)

**1.1 Create R2 Bucket:**

```bash
# Login to Cloudflare dashboard
# Navigate to R2 Object Storage
# Click "Create bucket"
# Name: drumscribe-artifacts
# Region: Automatic (global)
```

**1.2 Generate API Tokens:**

```bash
# Navigate to R2 > Manage R2 API Tokens
# Click "Create API Token"
# Permissions: Object Read & Write
# Copy: Access Key ID, Secret Access Key, Endpoint URL
```

**1.3 Configure Lifecycle Policy:**

```json
{
  "Rules": [
    {
      "Id": "DeleteOldJobs",
      "Status": "Enabled",
      "Expiration": {
        "Days": 7
      },
      "Filter": {
        "Prefix": "jobs/"
      }
    }
  ]
}
```

**1.4 Enable Public Access (for downloads):**

```bash
# Navigate to bucket settings
# Enable "Public Access" for read operations
# Configure CORS:
```

```json
[
  {
    "AllowedOrigins": ["https://drumscribe.ai"],
    "AllowedMethods": ["GET"],
    "AllowedHeaders": ["*"],
    "MaxAgeSeconds": 3600
  }
]
```

---

### Step 2: Deploy Modal (Serverless GPU)

**2.1 Authenticate Modal:**

```bash
modal token new
```

**2.2 Deploy Modal App:**

```bash
cd backend/infrastructure
modal deploy modal_app.py
```

**Expected output:**
```
✓ Created objects.
├── 🔨 Created download_model_weights => download_model_weights
└── 🔨 Created process_audio_pipeline => process_audio_pipeline
✓ App deployed! 🎉

View Deployment: https://modal.com/apps/drumscribe-ml
```

**2.3 Verify Deployment:**

```bash
# Test with sample audio
modal run modal_app.py --audio-url "https://example.com/test.mp3"
```

**2.4 Note Deployment Details:**

- App Name: `drumscribe-ml`
- Function Name: `process_audio_pipeline`
- These will be used in backend environment variables

---

### Step 3: Deploy Fly.io (API + Database)

**3.1 Initialize Fly.io App:**

```bash
cd backend
fly launch

# Follow prompts:
# - App name: drumscribe-api
# - Region: Choose closest to your users
# - PostgreSQL: Yes (create new database)
# - Redis: No (not needed)
```

**3.2 Configure fly.toml:**

```toml
app = "drumscribe-api"
primary_region = "iad"

[build]
  dockerfile = "infrastructure/Dockerfile.api"

[env]
  PORT = "8000"
  ENVIRONMENT = "production"

[[services]]
  internal_port = 8000
  protocol = "tcp"

  [[services.ports]]
    port = 80
    handlers = ["http"]

  [[services.ports]]
    port = 443
    handlers = ["tls", "http"]

  [services.concurrency]
    type = "connections"
    hard_limit = 1000
    soft_limit = 500

[[vm]]
  cpu_kind = "shared"
  cpus = 1
  memory_mb = 512

[metrics]
  port = 9091
  path = "/metrics"
```

**3.3 Set Environment Variables:**

```bash
# Database (auto-configured by Fly.io)
fly secrets set DATABASE_URL="postgresql://..."

# Storage (Cloudflare R2)
fly secrets set STORAGE_BACKEND=s3
fly secrets set S3_BUCKET=drumscribe-artifacts
fly secrets set S3_ENDPOINT_URL=https://...r2.cloudflarestorage.com
fly secrets set S3_ACCESS_KEY_ID=...
fly secrets set S3_SECRET_ACCESS_KEY=...

# Modal
fly secrets set USE_MODAL=true
fly secrets set MODAL_APP_NAME=drumscribe-ml
fly secrets set MODAL_FUNCTION_NAME=process_audio_pipeline

# Limits
fly secrets set MAX_FILE_SIZE_MB=50
fly secrets set ARTIFACT_TTL_HOURS=24
```

**3.4 Deploy:**

```bash
fly deploy
```

**3.5 Run Database Migrations:**

```bash
fly ssh console
cd /app
alembic upgrade head
exit
```

**3.6 Verify Deployment:**

```bash
# Check health
curl https://drumscribe-api.fly.dev/api/health

# View logs
fly logs
```

**3.7 Configure Custom Domain (Optional):**

```bash
fly certs create api.drumscribe.ai
# Add DNS record: CNAME api.drumscribe.ai -> drumscribe-api.fly.dev
```

---

### Step 4: Deploy Vercel (Frontend)

**4.1 Connect GitHub Repository:**

```bash
# Push code to GitHub
git remote add origin https://github.com/your-org/drumscribe.git
git push -u origin main
```

**4.2 Import Project to Vercel:**

```bash
# Via CLI
cd frontend
vercel

# Or via Dashboard:
# 1. Go to https://vercel.com/new
# 2. Import GitHub repository
# 3. Select "drumscribe" repository
# 4. Framework: Next.js
# 5. Root Directory: frontend
```

**4.3 Configure Environment Variables:**

```bash
# Production
vercel env add NEXT_PUBLIC_API_URL production
# Value: https://api.drumscribe.ai (or https://drumscribe-api.fly.dev)

vercel env add API_URL production
# Value: https://api.drumscribe.ai
```

**4.4 Deploy:**

```bash
vercel --prod
```

**4.5 Configure Custom Domain:**

```bash
# Via Vercel Dashboard:
# 1. Go to Project Settings > Domains
# 2. Add domain: drumscribe.ai
# 3. Add DNS records as instructed
```

**4.6 Verify Deployment:**

```bash
# Visit your domain
open https://drumscribe.ai

# Check build logs
vercel logs
```

---

## Environment Configuration

### Complete Environment Variables

#### Backend (Fly.io)

```bash
# Application
APP_NAME="DrumScribe API"
APP_VERSION="2.0.0"
ENVIRONMENT=production

# Database (auto-configured)
DATABASE_URL=postgresql+asyncpg://...

# Storage (Cloudflare R2)
STORAGE_BACKEND=s3
S3_BUCKET=drumscribe-artifacts
S3_ENDPOINT_URL=https://...r2.cloudflarestorage.com
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
S3_REGION=auto

# Modal Serverless GPU
USE_MODAL=true
MODAL_APP_NAME=drumscribe-ml
MODAL_FUNCTION_NAME=process_audio_pipeline

# ML Pipeline
ONSET_SENSITIVITY=0.05
LOW_CONFIDENCE_THRESHOLD=0.5

# Limits
MAX_FILE_SIZE_MB=50
MAX_CONCURRENT_JOBS_PER_USER=3
ARTIFACT_TTL_HOURS=24

# Logging
LOG_LEVEL=INFO
```

#### Frontend (Vercel)

```bash
# API Endpoints
NEXT_PUBLIC_API_URL=https://api.drumscribe.ai
API_URL=https://api.drumscribe.ai
```

#### Modal (Serverless GPU)

No environment variables needed - configuration is in `modal_app.py`.

---

## Monitoring & Maintenance

### Health Checks

**API Health:**
```bash
curl https://api.drumscribe.ai/api/health
```

**Expected Response:**
```json
{
  "status": "healthy",
  "checks": {
    "database": {"status": "healthy"},
    "storage": {"status": "healthy"},
    "modal": {"status": "healthy"}
  }
}
```

### Logging

**Fly.io Logs:**
```bash
fly logs --app drumscribe-api
```

**Vercel Logs:**
```bash
vercel logs --app drumscribe
```

**Modal Logs:**
```bash
# Via Modal Dashboard
# https://modal.com/apps/drumscribe-ml
```

### Metrics

**Prometheus Metrics:**
```bash
curl https://api.drumscribe.ai/metrics
```

**Vercel Analytics:**
- Visit: https://vercel.com/your-org/drumscribe/analytics

**Modal Dashboard:**
- Visit: https://modal.com/apps/drumscribe-ml

### Database Backups

**Fly.io PostgreSQL:**
```bash
# Create backup
fly postgres backup create --app drumscribe-api-db

# List backups
fly postgres backup list --app drumscribe-api-db

# Restore backup
fly postgres backup restore <backup-id> --app drumscribe-api-db
```

### Scaling

**Fly.io:**
```bash
# Scale up
fly scale count 2 --app drumscribe-api

# Scale down
fly scale count 1 --app drumscribe-api

# Scale to zero (when idle)
fly scale count 0 --min-machines-running 0
```

**Vercel:**
- Automatic scaling (no configuration needed)

**Modal:**
- Automatic scaling (no configuration needed)

---

## Troubleshooting

### Issue: API Returns 503 Service Unavailable

**Cause:** Fly.io machine scaled to zero and taking time to wake up.

**Solution:**
```bash
# Keep minimum 1 machine running
fly scale count 1 --min-machines-running 1
```

### Issue: Modal Cold Starts Taking >10 Seconds

**Cause:** Model weights not cached in Docker image.

**Solution:**
```bash
# Rebuild Modal app with weight caching
modal deploy backend/infrastructure/modal_app.py --force-build
```

### Issue: R2 Upload Fails with CORS Error

**Cause:** CORS not configured for your domain.

**Solution:**
```json
// Add to R2 bucket CORS configuration
{
  "AllowedOrigins": ["https://drumscribe.ai"],
  "AllowedMethods": ["GET", "PUT", "POST"],
  "AllowedHeaders": ["*"]
}
```

### Issue: Database Connection Errors

**Cause:** Connection pool exhausted.

**Solution:**
```bash
# Increase connection pool size
fly secrets set DATABASE_POOL_SIZE=20
fly deploy
```

### Issue: Jobs Stuck in "Processing" Status

**Cause:** Modal function timeout or error.

**Solution:**
```bash
# Check Modal logs
# https://modal.com/apps/drumscribe-ml

# Increase timeout in modal_app.py
@app.function(timeout=900)  # 15 minutes
```

---

## Cost Optimization

### Expected Monthly Costs (1000 tracks/month)

| Service | Cost | Notes |
|---------|------|-------|
| **Vercel** | $0 | Free tier (hobby) |
| **Fly.io** | $0-5 | Free tier + minimal overages |
| **Modal** | $35-55 | GPU inference only |
| **Cloudflare R2** | $0.08 | Storage + zero egress |
| **Total** | **$35-60/month** | vs $432/month always-on GPU |

### Optimization Tips

1. **Enable Scale-to-Zero:**
   ```bash
   fly scale count 0 --min-machines-running 0
   ```

2. **Optimize Modal Cold Starts:**
   - Ensure model weights are cached in Docker image
   - Use T4 GPUs (most cost-effective)

3. **Set Aggressive R2 Lifecycle:**
   - Delete artifacts after 7 days
   - Reduces storage costs

4. **Monitor Usage:**
   - Set up billing alerts in each service
   - Review Modal dashboard weekly

---

## CI/CD Pipeline

### GitHub Actions (Recommended)

```yaml
# .github/workflows/deploy.yml
name: Deploy

on:
  push:
    branches: [main]

jobs:
  deploy-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: superfly/flyctl-actions/setup-flyctl@master
      - run: flyctl deploy --remote-only
        env:
          FLY_API_TOKEN: ${{ secrets.FLY_API_TOKEN }}

  deploy-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: amondnet/vercel-action@v25
        with:
          vercel-token: ${{ secrets.VERCEL_TOKEN }}
          vercel-org-id: ${{ secrets.VERCEL_ORG_ID }}
          vercel-project-id: ${{ secrets.VERCEL_PROJECT_ID }}

  deploy-modal:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: pip install modal
      - run: modal deploy backend/infrastructure/modal_app.py
        env:
          MODAL_TOKEN_ID: ${{ secrets.MODAL_TOKEN_ID }}
          MODAL_TOKEN_SECRET: ${{ secrets.MODAL_TOKEN_SECRET }}
```

---

## Security Checklist

- [ ] HTTPS enforced on all services
- [ ] Environment variables stored as secrets
- [ ] Database backups enabled
- [ ] CORS configured correctly
- [ ] Rate limiting enabled
- [ ] API keys rotated regularly
- [ ] Monitoring alerts configured
- [ ] Error tracking enabled (Sentry recommended)

---

## Related Documentation

- **[System Architecture](ARCHITECTURE.md)** — Serverless design overview
- **[Modal Deployment](MODAL_DEPLOYMENT.md)** — Detailed Modal setup
- **[API Reference](API_REFERENCE.md)** — REST API documentation
- **[Backend Guide](../backend/README.md)** — Backend development

---

**Last Updated:** March 2026

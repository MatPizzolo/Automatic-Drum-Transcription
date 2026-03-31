# Backend

**FastAPI + PostgreSQL** backend for DrumScribe's AI-powered drum transcription service.

---

## Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| **Framework** | FastAPI | 0.109+ |
| **Database** | PostgreSQL | 16+ |
| **ORM** | SQLAlchemy (async) | 2.0+ |
| **Validation** | Pydantic | 2.0+ |
| **Audio Processing** | torchaudio | 2.0+ |
| **ML Models** | ONNX Runtime, transformers | Latest |
| **Logging** | structlog | Latest |

---

## Project Structure

```
backend/
├── app/
│   ├── api/v1/routes/          # REST API endpoints
│   │   ├── jobs.py             # Job CRUD operations
│   │   └── health.py           # Health checks
│   │
│   ├── ml/                     # Machine learning pipeline
│   │   ├── engine.py           # Audio processing (torchaudio + ONNX)
│   │   ├── guardrails.py       # ML output validation
│   │   ├── modal_client.py     # Modal serverless GPU client
│   │   └── onset_detection.py  # PyTorch-native onset detection
│   │
│   ├── services/               # Business logic
│   │   ├── audio_ingestion.py  # File upload, validation
│   │   ├── transcription.py    # symusic MIDI generation
│   │   └── export.py           # MusicXML/PDF export
│   │
│   ├── schemas/                # Pydantic models
│   │   ├── job.py              # API request/response schemas
│   │   └── ml_contracts.py     # ML pipeline contracts (DrumHit, PredictionResult)
│   │
│   ├── models/                 # SQLAlchemy ORM models
│   │   └── job.py              # Job database model
│   │
│   ├── storage/                # Storage abstraction
│   │   ├── local.py            # Local filesystem
│   │   └── s3.py               # S3-compatible (Cloudflare R2)
│   │
│   └── core/                   # Core utilities
│       ├── config.py           # Settings (Pydantic BaseSettings)
│       ├── database.py         # Database session management
│       └── logging.py          # Structured logging setup
│
├── infrastructure/             # Deployment
│   ├── modal_app.py            # Modal serverless GPU definition
│   ├── Dockerfile.api          # API container
│   └── Dockerfile.worker       # Worker container (local mode)
│
├── scripts/                    # Utilities
│   ├── export_ast_to_onnx.py   # ONNX model optimization
│   └── README.md               # Scripts documentation
│
├── tests/                      # Test suite
│   ├── unit/                   # Unit tests
│   ├── integration/            # Integration tests
│   └── regression/             # Regression tests
│
├── requirements-api.txt        # API dependencies
├── requirements-worker.txt     # Worker dependencies (ML models)
└── README.md                   # This file
```

---

## Local Development

### Prerequisites

- Python 3.11+
- PostgreSQL 16+
- Docker & Docker Compose (recommended)

### Setup

```bash
# 1. Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements-api.txt
pip install -r requirements-worker.txt  # For ML pipeline

# 3. Configure environment
cp ../.env.example ../.env
# Edit .env with your settings

# 4. Start PostgreSQL (via Docker)
docker run -d \
  --name drumscribe-postgres \
  -e POSTGRES_USER=drumscribe \
  -e POSTGRES_PASSWORD=drumscribe \
  -e POSTGRES_DB=drumscribe \
  -p 5432:5432 \
  postgres:16-alpine

# 5. Run database migrations
alembic upgrade head

# 6. Start API server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**API will be available at:**
- API: http://localhost:8000
- Interactive docs: http://localhost:8000/docs
- OpenAPI schema: http://localhost:8000/openapi.json

---

## Configuration

All configuration via environment variables (see `app/core/config.py`):

### Core Settings

```bash
# Application
APP_NAME="DrumScribe API"
APP_VERSION="2.0.0"
ENVIRONMENT=development  # development, staging, production

# Database
DATABASE_URL=postgresql+asyncpg://drumscribe:drumscribe@localhost:5432/drumscribe

# Storage
STORAGE_BACKEND=local  # local or s3
ARTIFACTS_DIR=./artifacts

# S3 (Cloudflare R2)
S3_BUCKET=drumscribe-artifacts
S3_ENDPOINT_URL=https://...r2.cloudflarestorage.com
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
```

### Modal Serverless GPU

```bash
# Enable Modal for GPU inference
USE_MODAL=true
MODAL_APP_NAME=drumscribe-ml
MODAL_FUNCTION_NAME=process_audio_pipeline
```

### ML Pipeline

```bash
# Onset detection sensitivity (lower = more sensitive)
ONSET_SENSITIVITY=0.05

# Confidence threshold for predictions
LOW_CONFIDENCE_THRESHOLD=0.5
```

### Limits

```bash
# File upload limits
MAX_FILE_SIZE_MB=50
MAX_CONCURRENT_JOBS_PER_USER=3

# Cleanup
ARTIFACT_TTL_HOURS=24
```

---

## API Endpoints

### Jobs

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/jobs` | Create transcription job |
| `GET` | `/api/jobs/{id}` | Get job status |
| `GET` | `/api/jobs/{id}/result` | Get prediction results |
| `GET` | `/api/jobs/{id}/download/{format}` | Download MusicXML or PDF |
| `DELETE` | `/api/jobs/{id}` | Cancel/delete job |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/health` | Health check (database, storage, models) |
| `GET` | `/metrics` | Prometheus metrics |

**Full API documentation:** [docs/API_REFERENCE.md](../docs/API_REFERENCE.md)

---

## ML Pipeline Integration

### Local Inference (Default)

```python
# app/ml/engine.py
from app.ml.engine import run_drum_separation, run_prediction
from app.ml.guardrails import apply_ml_guardrails

# 1. Separate drums
run_drum_separation(input_path, drums_path)

# 2. Detect hits
result = run_prediction(drums_path, user_bpm=120)

# 3. Apply guardrails
result = apply_ml_guardrails(result)
```

### Modal Serverless (Production)

```python
# app/ml/modal_client.py
from app.ml.modal_client import get_modal_client

client = get_modal_client()
result = client.process_audio(
    audio_path=drums_path,
    user_bpm=120,
)
```

**Automatic Fallback:**
- Modal client automatically falls back to local inference if Modal is unavailable
- No code changes needed to switch between modes

---

## Database Schema

### Jobs Table

```sql
CREATE TABLE jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status VARCHAR(20) NOT NULL,  -- pending, processing, completed, failed
    progress INTEGER DEFAULT 0,    -- 0-100
    
    -- ML Results
    detected_bpm INTEGER,
    bpm_unreliable BOOLEAN DEFAULT false,
    confidence_score FLOAT,
    
    -- User Input
    user_bpm INTEGER,
    
    -- Error Handling
    error_message TEXT,
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_jobs_status ON jobs(status);
CREATE INDEX idx_jobs_created_at ON jobs(created_at);
```

### Migrations

```bash
# Create new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

## Testing

### Run Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/

# Integration tests
pytest tests/integration/

# With coverage
pytest --cov=app --cov-report=html
```

### Test Structure

```python
# tests/unit/test_guardrails.py
import pytest
from app.ml.guardrails import apply_ml_guardrails

def test_bpm_halving():
    result = {"detected_bpm": 240, "hits": []}
    result = apply_ml_guardrails(result)
    assert result["detected_bpm"] == 120

def test_polyphony_limiter():
    hits = [
        {"time": 0.0, "instrument": "kick", "velocity": 0.9},
        {"time": 0.0, "instrument": "snare", "velocity": 0.8},
        # ... 6 simultaneous hits
    ]
    result = {"detected_bpm": 120, "hits": hits}
    result = apply_ml_guardrails(result)
    assert len(result["hits"]) <= 4  # Max 4 simultaneous
```

---

## Logging

### Structured Logging

```python
import structlog

logger = structlog.get_logger(__name__)

logger.info(
    "job_created",
    job_id=job.id,
    user_bpm=user_bpm,
    file_size=audio.size,
)
```

### Log Levels

```bash
# Development: human-readable
LOG_LEVEL=DEBUG
ENVIRONMENT=development

# Production: JSON
LOG_LEVEL=INFO
ENVIRONMENT=production
```

### Example Output

```json
{
  "event": "job_created",
  "job_id": "abc123",
  "user_bpm": 120,
  "file_size": 5242880,
  "timestamp": "2026-03-26T11:55:00Z",
  "level": "info"
}
```

---

## Performance Optimization

### Database Connection Pooling

```python
# app/core/database.py
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=20,          # Max connections
    max_overflow=10,       # Extra connections when pool full
    pool_pre_ping=True,    # Verify connections before use
)
```

### Async I/O

```python
# All I/O operations are async
async def create_job(audio: UploadFile, db: AsyncSession):
    # Non-blocking database operations
    async with db.begin():
        job = Job(status="pending")
        db.add(job)
        await db.commit()
    
    # Non-blocking storage operations
    await storage.upload(job.id, audio)
```

### Response Caching

```python
from fastapi_cache import FastAPICache
from fastapi_cache.decorator import cache

@app.get("/api/jobs/{id}")
@cache(expire=60)  # Cache for 60 seconds
async def get_job(id: str):
    pass
```

---

## Deployment

### Docker Build

```bash
# Build API image
docker build -f infrastructure/Dockerfile.api -t drumscribe-api .

# Build worker image (local mode)
docker build -f infrastructure/Dockerfile.worker -t drumscribe-worker .
```

### Fly.io Deployment

```bash
# Initialize Fly.io app
fly launch

# Deploy
fly deploy

# Scale to zero when idle
fly scale count 0 --min-machines-running 0

# View logs
fly logs
```

**See [docs/DEPLOYMENT.md](../docs/DEPLOYMENT.md) for complete deployment guide.**

---

## ONNX Model Optimization

### Export AST Model to ONNX

```bash
# Run export script
python scripts/export_ast_to_onnx.py

# Output: models/ast_optimized.onnx (~350MB)
```

**Benefits:**
- 2.7x faster inference
- 40% memory reduction
- <2s cold starts on Modal

**See [scripts/README.md](scripts/README.md) for details.**

---

## Related Documentation

- **[System Architecture](../docs/ARCHITECTURE.md)** — Serverless design overview
- **[ML Pipeline](../docs/ML_PIPELINE.md)** — torchaudio → ONNX → symusic
- **[Modal Deployment](../docs/MODAL_DEPLOYMENT.md)** — Serverless GPU setup
- **[API Reference](../docs/API_REFERENCE.md)** — Complete REST API docs
- **[Deployment Guide](../docs/DEPLOYMENT.md)** — Production deployment

---

**Last Updated:** March 2026

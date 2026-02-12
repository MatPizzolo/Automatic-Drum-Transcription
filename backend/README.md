# Backend

FastAPI + Celery backend for DrumScribe. Handles job management, ML inference orchestration, and file serving.

## Structure

```
app/
  api/v1/routes/      REST endpoints (jobs, health)
  ml/                 ML pipeline
    engine.py          Demucs separation + CNN prediction
    registry.py        Model resolution, caching, remote download
  services/
    transcription.py   music21 sheet music generation
    export.py          MusicXML + PDF export (LilyPond/MuseScore)
    audio_ingestion.py YouTube download + audio validation
    webhook.py         Job completion notifications
  storage/
    backend.py         Storage abstraction (local / S3)
  core/
    config.py          Pydantic settings (all env vars)
    database.py        Async SQLAlchemy engine
    database_sync.py   Sync engine for Celery workers
    security.py        Redis-based per-user concurrency limits
    telemetry.py       Prometheus metrics + OpenTelemetry tracing
  models/job.py        SQLAlchemy Job model
  schemas/job.py       Pydantic request/response schemas
  worker.py            Celery app, task definitions, pipeline chain
infrastructure/        Dockerfiles (API, Worker)
scripts/               Model download, worker entrypoint, seed data
tests/                 Unit and integration tests
```

## Local Development

```bash
# Prerequisites: PostgreSQL and Redis running locally or via Docker

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env    # adjust DB/Redis URLs as needed

alembic upgrade head
uvicorn app.main:app --reload --port 8000

# In separate terminals:
celery -A app.worker worker --queues=default --loglevel=info
celery -A app.worker worker --queues=heavy-compute --concurrency=1 --loglevel=info
celery -A app.worker beat --loglevel=info
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/jobs` | Create transcription job (file upload or YouTube URL) |
| `GET` | `/api/v1/jobs/{id}` | Poll job status + progress percentage |
| `GET` | `/api/v1/jobs/{id}/result` | Get result (hits, BPM, confidence, summary) |
| `GET` | `/api/v1/jobs/{id}/download/{fmt}` | Download `musicxml` or `pdf` |
| `DELETE` | `/api/v1/jobs/{id}` | Cancel or delete job |
| `GET` | `/api/v1/health` | Health check (DB, Redis, model status) |
| `GET` | `/metrics` | Prometheus metrics |

## Task Pipeline

Jobs execute as a Celery chain across two queues:

```
ingest_audio (default) → separate_drums (heavy) → predict_hits (heavy) → transcribe_and_export (default)
```

See [`../docs/ML_PIPELINE.md`](../docs/ML_PIPELINE.md) for the full ML pipeline breakdown.

## Requirements

- **`requirements-api.txt`** — API-only deps (~400 MB image): FastAPI, SQLAlchemy, Redis, observability
- **`requirements-worker.txt`** — Inherits API + ML stack (~3 GB image): Demucs, TensorFlow, librosa, music21

## Configuration

All settings are in `app/core/config.py` as Pydantic fields with defaults. See [`../.env.example`](../.env.example) for the full list.

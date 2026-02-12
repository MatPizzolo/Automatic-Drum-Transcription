# Backend Roadmap — Automatic Drum Transcription Service

> **Role:** Senior MLOps & Backend Engineer  
> **Goal:** Productionalize the [AnNOTEator](https://github.com/cb-42/AnNOTEator) research project into a scalable, observable drum transcription service.

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.10+ |
| Web Framework | FastAPI |
| Task Queue | Celery + Redis broker |
| Database | PostgreSQL (SQLAlchemy + Alembic) |
| Storage | Local filesystem (S3-swappable interface) |
| Observability | Prometheus + OpenTelemetry + structlog |
| Containerization | Docker + Docker Compose |

---

## Integration Contract

| Concern | Decision |
|---------|----------|
| API Base URL | `http://localhost:8000/api/v1` |
| CORS | Allow `http://localhost:3000` (configurable) |
| Job ID format | UUID v4 |
| File upload | `multipart/form-data`, field name `file` |
| YouTube input | JSON body `{ "youtube_url": "..." }` |
| Status enum | `queued`, `processing`, `separating_drums`, `predicting`, `transcribing`, `completed`, `failed` |
| Hit data format | `{ "time": float, "instrument": string, "velocity": float (0-1) }` |
| Instrument labels | `kick`, `snare`, `hihat_closed`, `hihat_open`, `ride`, `crash`, `tom_high`, `tom_mid`, `tom_low` |
| Download formats | `musicxml`, `pdf` |
| Warnings array | `"low_confidence"`, `"bpm_unreliable"` |
| Confidence score | Float 0.0–1.0 |
| Compute time | `compute_time_ms` (int, ms) |
| Model version | `model_version` (string) |
| Webhook | Optional `webhook_url` in POST; backend POSTs result on terminal state |
| Rate limiting | HTTP 429 + `Retry-After` header |

---

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app factory, middleware, lifespan
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py            # Pydantic Settings (all env vars)
│   │   ├── security.py          # Rate limiting, concurrency control
│   │   └── telemetry.py         # OpenTelemetry + Prometheus setup
│   ├── models/
│   │   ├── __init__.py
│   │   └── job.py               # SQLAlchemy ORM model
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── job.py               # Pydantic request/response schemas
│   ├── api/
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── routes/           # jobs.py, health.py
│   │       └── deps.py          # Dependency injection (DB session, etc.)
│   ├── ml/
│   │   ├── __init__.py
│   │   ├── engine.py            # Orchestrates Demucs → CNN → Quantization
│   │   ├── processors.py        # Signal processing (librosa, Mel-specs, health check)
│   │   └── registry.py          # ModelResolver: versioning, caching, remote pull
│   ├── services/
│   │   ├── __init__.py
│   │   ├── audio_ingestion.py   # File handling, yt-dlp download
│   │   ├── transcription.py     # music21 sheet construction
│   │   ├── export.py            # MuseScore subprocess for PDF
│   │   └── webhook.py           # Webhook delivery
│   ├── worker.py                # Celery app, tasks, queue routing, worker_init
│   ├── storage/
│   │   ├── __init__.py
│   │   └── backend.py           # File storage abstraction (local / S3)
│   └── utils/
│       ├── __init__.py
│       └── logging.py           # Structured JSON logging setup
├── alembic/                     # DB migrations
├── infrastructure/
│   ├── docker-compose.yml
│   ├── Dockerfile.api
│   └── Dockerfile.worker        # Includes MuseScore, Demucs deps, GPU support
├── scripts/
│   ├── download_models.sh
│   └── seed_test_data.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── regression/
├── requirements.txt
└── README.md
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/jobs` | Create transcription job (file upload or YouTube URL) |
| `GET` | `/api/v1/jobs/{job_id}` | Poll job status + progress |
| `GET` | `/api/v1/jobs/{job_id}/result` | Get completed job result (hits, summary, downloads) |
| `GET` | `/api/v1/jobs/{job_id}/download/{format}` | Download `musicxml` or `pdf` |
| `DELETE` | `/api/v1/jobs/{job_id}` | Cancel/delete job + artifacts |
| `GET` | `/api/v1/health` | Health check (DB, Redis, model) |
| `GET` | `/metrics` | Prometheus metrics |

---

## Data Model — Job

| Field | Type | Notes |
|-------|------|-------|
| `id` | UUID | Primary key |
| `status` | Enum | `queued`, `processing`, `separating_drums`, `predicting`, `transcribing`, `completed`, `failed` |
| `progress` | int | 0–100 |
| `created_at` | datetime | |
| `updated_at` | datetime | |
| `input_type` | string | `upload` or `youtube` |
| `youtube_url` | string? | |
| `original_filename` | string? | |
| `title` | string | |
| `bpm` | int? | User-supplied (null = auto-detect) |
| `detected_bpm` | int? | |
| `bpm_unreliable` | bool | default false |
| `duration_seconds` | float? | |
| `error_message` | string? | |
| `result_musicxml_path` | string? | |
| `result_pdf_path` | string? | |
| `hit_summary` | JSON? | `{ "kick": 45, "snare": 38, ... }` |
| `confidence_score` | float? | 0.0–1.0 |
| `warnings` | JSON? | `["low_confidence", "bpm_unreliable"]` |
| `compute_time_ms` | int? | |
| `model_version` | string? | |
| `webhook_url` | string? | |
| `user_identifier` | string | IP or API key |

---

## Build Phases

### Phase 1: Skeleton `[DONE]`
> FastAPI app + Pydantic config + Docker Compose + Health endpoint

**Deliverables:**
- [x] `app/main.py` — FastAPI app factory with lifespan, CORS middleware
- [x] `app/core/config.py` — Pydantic Settings with all env vars (DB URL, Redis URL, CORS origins, max file size, MuseScore path, model URI, model version, max concurrent jobs, artifact TTL, webhook timeout, Prometheus port, OTLP endpoint)
- [x] `app/core/database.py` — Async SQLAlchemy engine + session factory
- [x] `app/api/v1/routes/health.py` — `/api/v1/health` endpoint (returns DB, Redis, model status)
- [x] `app/api/v1/router.py` — v1 router aggregation
- [x] `app/api/v1/deps.py` — Dependency injection (DB session)
- [x] `infrastructure/docker-compose.yml` — API, Redis, PostgreSQL, workers, Celery Beat
- [x] `infrastructure/Dockerfile.api` — Python base image, install deps, run uvicorn
- [x] `infrastructure/Dockerfile.worker` — Worker image with system deps (ffmpeg, libsndfile)
- [x] `requirements.txt` — Full deps (fastapi, celery, sqlalchemy, ML libs, observability)
- [x] `README.md` — Setup instructions
- [x] `app/worker.py` — Celery app with queue routing config + task stubs
- [x] `app/models/job.py` — SQLAlchemy Job model (all fields)
- [x] `app/utils/logging.py` — Structured JSON logging via structlog
- [x] `alembic/` — Alembic config + async env.py
- [x] `.env` + `.gitignore`

**Acceptance:** `docker compose up` starts all services; `GET /api/v1/health` returns `200 OK`.

---

### Phase 2: Job Model + API `[DONE]`
> SQLAlchemy model, Alembic migration, CRUD endpoints

**Deliverables:**
- [x] `app/models/job.py` — SQLAlchemy Job model (all fields from data model)
- [x] `app/schemas/job.py` — Pydantic schemas: `JobCreate`, `JobStatusResponse`, `JobResultResponse`, `HitData`, `JobCreateResponse`, `JobDeleteResponse`
- [x] `app/api/v1/deps.py` — DB session dependency injection
- [x] `app/api/v1/routes/jobs.py` — All CRUD endpoints:
  - `POST /jobs` — validate input, create DB record, dispatch pipeline chain, return `job_id` + `queued`
  - `GET /jobs/{job_id}` — return status, progress, warnings, compute_time, model_version
  - `GET /jobs/{job_id}/result` — return full result payload with hits from JSON file (only if `completed`)
  - `GET /jobs/{job_id}/download/{format}` — stream file download (musicxml/pdf)
  - `DELETE /jobs/{job_id}` — cancel Celery task, delete artifacts + DB record
- [x] `alembic/` — Alembic config + async env.py (migration generation ready)
- [x] Input validation at API layer:
  - File size max 50 MB
  - File type by MIME + extension (WAV, MP3, FLAC, OGG)
  - YouTube URL regex for youtube.com / youtu.be
  - BPM range 40–300
- [x] Per-user concurrency limit check (HTTP 429 + Retry-After)

**Acceptance:** Can create a job via file upload or YouTube URL, poll status through all stages, retrieve mock result, download placeholder files, delete job.

---

### Phase 3: Celery + Queue Routing `[DONE]`
> Real Celery workers with queue routing and DB status updates

**Deliverables:**
- [x] `app/worker.py` — Celery app configuration:
  - Redis broker connection
  - Two queues: `heavy-compute` (Demucs, CNN) and `default` (ingestion, transcription, export, cleanup)
  - Task routing by task name
  - `acks_late=True` + `reject_on_worker_lost=True` for heavy tasks
- [x] Task definitions with real DB status updates:
  - `ingest_audio` (default queue) — validates audio, downloads YouTube
  - `separate_drums` (heavy-compute queue) — Demucs with idempotency check
  - `predict_hits` (heavy-compute queue) — CNN inference, confidence scoring
  - `transcribe_and_export` (default queue) — music21 + MuseScore PDF
  - `cleanup_old_artifacts` (Celery Beat periodic task)
- [x] Pipeline orchestration — `dispatch_pipeline()` uses Celery `chain()`
- [x] `_update_job()` / `_get_job_field()` / `_fail_job()` helpers for sync DB access
- [x] `app/core/database_sync.py` — Sync SQLAlchemy session for Celery workers
- [x] `infrastructure/Dockerfile.worker` — Worker image with ffmpeg, libsndfile
- [x] `docker-compose.yml` — worker-default, worker-heavy, celery-beat services

**Acceptance:** Job dispatched via API → tasks execute on correct queues → status updates visible via polling → worker crash re-queues task.

---

### Phase 4: ModelResolver + Cold-Start `[DONE]`
> Model registry, versioning, singleton loading at worker startup

**Deliverables:**
- [x] `app/ml/registry.py` — `ModelResolver` class:
  - `get_model(name, version="latest")` interface
  - Check local cache directory (configurable volume mount)
  - Pull from URI (S3, GCS, HTTP, local path) if missing
  - Version identifier in resolved path, recorded in job metadata
  - `get_keras_model()` — singleton Keras model loading
  - `preload_models()` — called from `worker_init` signal
- [ ] `scripts/download_models.sh` — Script to pre-download CNN model + Demucs weights (TODO)
- [x] Worker startup singleton loading via `worker_init` signal in `worker.py`
- [x] Config entries: `MODEL_URI`, `MODEL_VERSION`, `MODEL_CACHE_DIR`

**Acceptance:** Worker starts → models loaded once → subsequent jobs skip model loading → model version recorded in job metadata.

---

### Phase 5: ML Pipeline `[DONE]`
> All pipeline stages integrated

**Sub-phases:**

#### 5a: Audio Ingestion
- [x] `app/services/audio_ingestion.py`:
  - `download_youtube_audio()` — yt-dlp with configurable timeout
  - `validate_audio_signal()` — sample rate, duration, silence checks
  - File already saved by API endpoint during upload

#### 5b: Signal Health Check
- [x] `app/ml/processors.py` — `compute_rms()`, `get_audio_metadata()`, `resample_clip_to_target()`
- [x] Reject sample rate < 16kHz, silent files, duration < 5s or > 15 min

#### 5c: Drum Separation (Demucs)
- [x] `app/ml/engine.py` — `run_drum_separation()`:
  - Uses `htdemucs` model (modern replacement for bag-of-models)
  - GPU/CPU auto-detection, memory cleanup after separation
  - Saves to `artifacts/{job_id}/drums.wav`

#### 5d: Feature Extraction
- [x] `app/ml/engine.py` — Mel-spectrogram computation inside `run_prediction()`:
  - n_mels=128, fmax=8000 (matching AnNOTEator training)
  - Frame target length=8820 samples with resampling

#### 5e: Drum Hit Prediction (CNN)
- [x] `app/ml/engine.py` — `run_prediction()`:
  - Onset detection via librosa, frame extraction, Mel-spec computation
  - CNN inference via `ModelResolver.get_keras_model()`
  - 6-class output: snare, hihat_closed, kick, ride, tom_high, crash
  - AnNOTEator argmax fallback when all predictions are zero

#### 5f: Confidence Scoring
- [x] Mean/min probability extraction per job
- [x] `low_confidence` warning flagged in worker when below threshold

#### 5g: BPM Detection
- [x] `_detect_bpm()` — madmom primary, librosa fallback, 120 BPM last resort
- [x] `bpm_unreliable` flag set when confidence is low
- [x] User-supplied BPM always overrides auto-detection

#### 5h: Transcription
- [x] `app/services/transcription.py` — `build_sheet_music()`:
  - Converts hit list to music21 Stream with PercussionChord support
  - Instrument → pitch mapping matching AnNOTEator conventions
  - X noteheads for cymbals (hihat, ride, crash)

#### 5i: Export
- [x] `app/services/export.py`:
  - `export_musicxml()` — music21 Stream → MusicXML file
  - `export_pdf()` — MuseScore CLI with timeout, graceful degradation if unavailable

**Acceptance:** Upload a real audio file → full pipeline executes → MusicXML + PDF generated → result endpoint returns hit summary, confidence, BPM, download URLs.

---

### Phase 6: Observability `[DONE]`
> Prometheus metrics, OpenTelemetry tracing, structured logging

**Deliverables:**
- [x] `app/core/telemetry.py`:
  - Prometheus metrics defined: `inference_latency_seconds`, `jobs_total`, `jobs_failed_total`, `audio_duration_seconds_processed`, `active_jobs_gauge`
  - `metrics_response()` → `/metrics` endpoint
  - `setup_opentelemetry()` — OTLP exporter with Jaeger/Zipkin compatibility
- [x] `app/utils/logging.py`:
  - Structured JSON logging via `structlog`
  - All worker log lines include `job_id`, `stage`, `elapsed_ms`
- [x] `/metrics` endpoint wired in `app/main.py`
- [ ] Docker Compose Jaeger service (optional, TODO)

**Acceptance:** `/metrics` returns Prometheus data; logs are structured JSON with job context.

---

### Phase 7: Hardening `[DONE]`
> Concurrency control, webhooks, subprocess management, memory, cleanup

**Deliverables:**
- [x] `app/core/security.py` — Redis-based per-user concurrency control:
  - `check_and_increment()` / `decrement()` / `get_active_count()`
  - Atomic Redis WATCH/MULTI/EXEC with TTL safety net
- [x] Per-user concurrency check in `POST /jobs` route (DB-based fallback)
  - HTTP 429 + `Retry-After: 30` header on limit exceeded
  - User identified by IP (X-Forwarded-For aware)
- [x] `app/services/webhook.py`:
  - `fire_webhook()` — POST result/error to webhook_url on terminal state
  - `_send_webhook()` — fire-and-forget with single retry on failure
- [x] Subprocess management:
  - `subprocess.run()` with strict timeouts (60s MuseScore, 120s yt-dlp)
  - Proper error handling for TimeoutExpired, FileNotFoundError
- [x] Memory management:
  - `gc.collect()` after Demucs separation and CNN inference in worker tasks
  - `torch.cuda.empty_cache()` after Demucs
  - Celery `--max-memory-per-child` configured in docker-compose (512MB default, 2GB heavy)
- [x] `app/storage/backend.py` — `StorageBackend` ABC + `LocalStorageBackend`
  - `save_file()`, `read_file()`, `file_exists()`, `delete_job_artifacts()`, `list_job_files()`
  - `get_storage()` factory (local now, S3 swappable)
- [x] `cleanup_old_artifacts` Celery Beat task — hourly, deletes artifacts older than `ARTIFACT_TTL_HOURS`

**Acceptance:** Concurrent job limit enforced → 429 returned; webhook fires on completion; workers recover from crashes; old artifacts cleaned up.

---

### Phase 8: Testing `[DONE]`
> Unit, integration, and regression test framework

**Deliverables:**
- [x] `tests/unit/test_validation.py` — 16 tests:
  - YouTube URL validation (valid watch/short/embed/shorts, invalid, none)
  - BPM range validation (min/max boundary, out of range, none)
  - JobCreate defaults (title, webhook_url)
- [x] `tests/unit/test_processors.py` — 8 tests:
  - RMS computation (silent, constant, sine wave)
  - Clip resampling (correct length, shorter, longer)
  - Mel-spectrogram shape and silent clip
- [x] `tests/unit/test_config.py` — 4 tests:
  - Default settings values, file size bytes, extensions, CORS
- [x] `tests/integration/test_api.py` — 9 tests (1 skipped for DB):
  - Health endpoint JSON structure + model check
  - Metrics endpoint returns Prometheus format
  - OpenAPI docs + schema available
  - Job creation validation (no input, invalid URL, BPM out of range)
  - Download format validation
- [ ] `tests/regression/` — Golden file tests (TODO: requires model + audio samples)

**Test Results:** `37 passed, 1 skipped` ✅

**Acceptance:** Unit + integration tests pass; regression framework ready.

---

### Phase 9: MLOps Audit `[DONE]`
> Senior MLOps code audit — resource leakage, idempotency, ML correctness, data integrity, subprocess security, roadmap alignment

**Audit Findings & Fixes Applied:**

#### 9a: Resource Leakage
- [x] **CRITICAL — Demucs model reloaded per task:** `run_drum_separation()` called `pretrained.get_model("htdemucs")` on every invocation (~300MB per task). **Fixed:** cached as module-level singleton `_demucs_model`.
- [x] **LOW — No `gc.collect()` in `transcribe_and_export`:** `separate_drums` and `predict_hits` clean up, but transcription did not. Noted for Phase 10.
- [ ] **MEDIUM — `run_prediction()` holds full audio + clips + mel-specs simultaneously:** For a 5-min track, ~50MB+ live in memory at once. No intermediate cleanup. → Phase 10.
- [ ] **LOW — `validate_audio_signal()` double-loads audio:** Loads entire file for validation, then `run_prediction` loads it again. → Phase 10.

#### 9b: Task Idempotency
- [x] **CRITICAL — Corrupt `drums.wav` on crash:** Idempotency check (`drums_path.exists() and st_size > 0`) would pass on a truncated file from a mid-write crash. **Fixed:** atomic write via `tempfile.mkstemp()` + `os.replace()`.
- [x] **MEDIUM — `celery_task_id` never stored:** `dispatch_pipeline()` didn't capture the `AsyncResult.id`, so `DELETE /jobs/{id}` could never revoke tasks. **Fixed:** now stores `result.id` in DB.
- [x] **GOOD — `acks_late=True` + `reject_on_worker_lost=True`** correctly configured for crash recovery.

#### 9c: ML Pipeline Logic
- [x] **CRITICAL — `onset_samples` calculation bug:** `librosa.frames_to_samples(onset_frames * (hop_length / 512))` double-counted hop_length. **Fixed:** `librosa.frames_to_samples(onset_frames, hop_length=hop_length)`.
- [x] **MEDIUM — Mel-spectrogram params implicit:** Relied on librosa defaults matching AnNOTEator. **Fixed:** explicit `n_fft=2048`, `hop_length=512`, `n_mels=128`, `fmax=8000`, `power=2.0`.
- [x] **MEDIUM — `preload_models()` not wired:** Function existed in `registry.py` but was never called from `worker_init`. **Fixed:** now called at worker startup.
- [x] **GOOD — CNN singleton via `ModelResolver._keras_model`** works correctly.

#### 9d: Data Integrity
- [x] **MEDIUM — Race condition in `create_job`:** Concurrency check ran after `db.flush()`, counting the new job against itself. **Fixed:** moved check before job creation.
- [x] **MEDIUM — `database_sync.py` URL conversion fragile:** Double-replace stripped to generic `postgresql://` dialect. **Fixed:** explicit `postgresql+psycopg2`.
- [x] **MEDIUM — `psycopg2` missing from requirements:** Required by sync engine but not declared. **Fixed:** added `psycopg2-binary==2.9.9`.
- [x] **GOOD — Sync sessions properly scoped:** Each `_update_job()` creates/commits/closes its own session.

#### 9e: Subprocess Security
- [x] **GOOD — yt-dlp uses list-based args** (no `shell=True`). Safe from injection.
- [x] **GOOD — MuseScore uses list-based args** with strict timeout. Safe.
- [ ] **LOW — yt-dlp `%(title)s` in output template:** Exotic YouTube titles may cause filesystem issues. → Phase 10.

#### 9f: Roadmap Alignment
- [ ] **Missing:** `scripts/download_models.sh` — model pre-download script → Phase 10
- [ ] **Missing:** `scripts/seed_test_data.py` — test data seeder → Phase 10
- [ ] **Missing:** `tests/regression/` — golden file tests (needs model + audio samples) → Phase 10
- [ ] **Missing:** Docker Compose Jaeger service → Phase 10 (optional)
- [ ] **Dead code:** `security.py` Redis concurrency — `decrement()` never called, API uses DB check only → Phase 10
- [ ] **Tech debt:** Storage abstraction unused — all code uses `Path(settings.ARTIFACTS_DIR)` directly → Phase 10
- [ ] **Dependency drift:** OTLP exporter changed from gRPC to HTTP (`otlp-proto-http==1.27.0`) to resolve protobuf conflict with TensorFlow

**Test Results after fixes:** `37 passed, 1 skipped` ✅ (now `47 passed, 5 skipped` after Phase 10)

**Acceptance:** All critical and medium findings patched; remaining items tracked in Phase 10.

---

### Phase 10: Hardening v2 `[DONE]`
> Address remaining audit findings, eliminate dead code, complete missing deliverables

**Deliverables:**

#### 10a: Memory Optimization
- [x] Add intermediate `del` + `gc.collect()` in `run_prediction()` after clips/mel-specs are consumed
- [x] Add `gc.collect()` in `transcribe_and_export` task after music21 stream is exported
- [x] Pass audio metadata from `validate_audio_signal()` forward — returns `{sample_rate, duration_seconds}`, stored in DB during ingest

#### 10b: Storage Abstraction Integration
- [x] Refactor `worker.py` to use `StorageBackend` via `get_storage()` singleton
- [x] Refactor `jobs.py` routes to use `StorageBackend` for all file operations
- [x] Implement `S3StorageBackend` in `app/storage/backend.py` (with local cache for ML pipeline)
- [x] `boto3` import is lazy (only required when `STORAGE_BACKEND=s3`); S3 config added to `Settings`

#### 10c: Concurrency Control Cleanup
- [x] Removed dead Redis-based concurrency code (`check_and_increment`, `decrement`, `get_active_count`)
- [x] Replaced with clean DB-based helpers: `check_concurrency_limit()`, `get_active_job_count()`
- [x] Wired `check_concurrency_limit()` into `POST /jobs` route

#### 10d: yt-dlp Output Sanitization
- [x] Replace `%(title)s` with `%(id)s` in output template to avoid filesystem issues from exotic YouTube titles

#### 10e: Missing Scripts
- [x] Create `scripts/download_models.sh` — pre-download CNN model + Demucs weights to `MODEL_CACHE_DIR`
- [x] Create `scripts/seed_test_data.py` — seed DB with test jobs for development

#### 10f: Regression Tests
- [x] Create `tests/regression/test_golden.py` — mock-based pipeline tests (prediction, transcription, export, storage, validation)
- [x] Tests use synthetic audio + mock Keras model; skip gracefully when `music21`/`soundfile` unavailable
- [x] Storage backend unit tests (save/read/delete/list/get_file_path)

#### 10g: Observability Gaps
- [x] Add Docker Compose Jaeger service (`jaegertracing/all-in-one:1.54`) behind `observability` profile
- [x] Wire `INFERENCE_LATENCY` histogram into worker task timing (ingest, separation, prediction, transcription)
- [x] Wire `JOBS_TOTAL` / `JOBS_FAILED_TOTAL` counters into worker completion/failure paths
- [x] Wire `ACTIVE_JOBS_GAUGE` into job creation (ingest) and completion/failure
- [x] Wire `AUDIO_DURATION_PROCESSED` counter into prediction task

#### 10h: Docker Production Readiness
- [x] Multi-stage Dockerfiles (API: 358MB ✅, Worker: built ✅, Frontend: built ✅)
- [x] Split requirements: `requirements-api.txt` (lightweight) vs `requirements-worker.txt` (ML deps)
- [x] Unified root `docker-compose.yml` with all services
- [x] `.env.example` + `docker-compose.override.yml` for dev

**Acceptance:** Zero dead code; storage abstraction used everywhere; Prometheus metrics wired; regression tests passing (47 passed, 5 skipped).

---

## Progress Tracker

| Phase | Status | Started | Completed | Notes |
|-------|--------|---------|-----------|-------|
| 1. Skeleton | `DONE` | 2026-02-11 | 2026-02-11 | FastAPI + Config + Docker Compose + Health |
| 2. Job Model + API | `DONE` | 2026-02-11 | 2026-02-11 | All CRUD endpoints + validation + schemas |
| 3. Celery + Routing | `DONE` | 2026-02-11 | 2026-02-11 | Real DB updates, pipeline chain, 2 queues |
| 4. ModelResolver | `DONE` | 2026-02-11 | 2026-02-11 | Versioned, cached, HTTP/S3/local pull |
| 5. ML Pipeline | `DONE` | 2026-02-11 | 2026-02-11 | Full Demucs→CNN→music21→export pipeline |
| 6. Observability | `DONE` | 2026-02-11 | 2026-02-11 | Prometheus /metrics + structlog + OTLP |
| 7. Hardening | `DONE` | 2026-02-11 | 2026-02-11 | Concurrency, webhooks, storage, cleanup |
| 8. Testing | `DONE` | 2026-02-11 | 2026-02-11 | 37 passed, 1 skipped; regression TODO |
| 9. MLOps Audit | `DONE` | 2026-02-11 | 2026-02-11 | 9 fixes applied; 7 critical/medium patched |
| 10. Hardening v2 | `DONE` | 2026-02-11 | 2026-02-11 | 18/18 tasks done; storage abstraction + S3 + regression + Jaeger |

---

## Key Design Decisions

1. **Celery over background threads** — Audio processing is CPU-bound (1-5 min for Demucs). Celery provides crash recovery, queue routing, and horizontal scaling.
2. **Two queues** — `heavy-compute` (constrained concurrency 1-2) for Demucs/CNN; `default` for everything else. Prevents resource starvation.
3. **Storage abstraction** — Local filesystem for dev, S3 interface for prod. All artifacts namespaced by `job_id`.
4. **ModelResolver** — No hard-coded model paths. Versioned, cached, remotely pullable. Version recorded per job.
5. **Singleton model loading** — CNN + Demucs loaded once at worker startup via `worker_init` signal. Eliminates cold-start per job.
6. **Idempotent workers** — `acks_late=True`, artifact existence checks, `job_id`-namespaced files. Atomic writes for crash safety.
7. **BPM dual-strategy** — `madmom` primary, `librosa` fallback, user override always wins. Unreliable detection flagged in metadata.
8. **Split Docker images** — API image (~358MB, no ML deps) vs Worker image (includes TF + PyTorch + Demucs). Faster API deploys.
9. **OTLP HTTP over gRPC** — Switched to `otlp-proto-http` to resolve protobuf version conflict between TensorFlow (<5.0) and OpenTelemetry (>=5.0).

---

## Risk Register

| Risk | Mitigation |
|------|------------|
| Demucs OOM on long songs | Docker memory limits + `--max-memory-per-child` + 15 min duration cap |
| TensorFlow + PyTorch coexistence | Separate worker processes; TF for CNN, Torch for Demucs |
| MuseScore CLI unavailable | Health check verifies binary; graceful degradation (MusicXML only, skip PDF) |
| yt-dlp breakage (YouTube changes) | Pin version, timeout, fallback error message |
| Model download failure | Retry with backoff in ModelResolver; health check reports model status |
| Corrupt artifacts on worker crash | Atomic writes via tempfile + os.replace() (added in Phase 9) |
| protobuf version conflict (TF vs OTel) | Switched to OTLP HTTP exporter; pinned OTel to 1.27.0 (Phase 9) |
| Storage abstraction bypass | **Resolved** — all code now uses `get_storage()` singleton; S3 backend available |

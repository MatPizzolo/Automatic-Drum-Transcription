# DEVOPS.md — Operational Manual

> **System:** DrumScribe — Automatic Drum Transcription
> **Stack:** FastAPI + Celery + Redis + PostgreSQL + Next.js
> **Orchestration:** Docker Compose (dev + prod), GitHub Actions CI

---

## 1. Architecture Overview

```
                          ┌──────────────┐
                          │   Frontend   │
                          │  (Next.js)   │
                          └──────┬───────┘
                                 │ HTTP
                          ┌──────▼───────┐
                          │   API        │
                          │  (FastAPI)   │
                          └──┬───────┬───┘
                             │       │
                    ┌────────▼─┐   ┌─▼────────┐
                    │  Redis   │   │ Postgres  │
                    │ (broker) │   │  (state)  │
                    └────┬─────┘   └───────────┘
                         │
              ┌──────────┼──────────┐
              │                     │
     ┌────────▼────────┐  ┌────────▼────────┐
     │ worker-default   │  │  worker-heavy   │
     │ queue: default    │  │ queue: heavy-   │
     │ concurrency: 4   │  │   compute       │
     │                   │  │ concurrency: 1  │
     │ • ingest_audio    │  │                 │
     │ • transcribe_and_ │  │ • separate_drums│
     │   export          │  │   (Demucs)      │
     │ • cleanup_old_    │  │ • predict_hits  │
     │   artifacts       │  │   (Keras CNN)   │
     └───────────────────┘  └─────────────────┘
```

### Decoupled Worker Strategy

The system uses **two Celery worker pools** to isolate resource-intensive ML inference from lightweight I/O tasks:

| Worker | Queue | Concurrency | Purpose |
|--------|-------|-------------|---------|
| `worker-default` | `default` | 4 | Audio ingestion (yt-dlp), music21 transcription, MusicXML/PDF export, artifact cleanup |
| `worker-heavy` | `heavy-compute` | 1 | Demucs source separation (~2-4 GB RAM), Keras CNN hit prediction (~500 MB RAM) |

Tasks are routed automatically via `celery_app.conf.task_routes` in `app/worker.py`. The pipeline executes as a Celery chain: `ingest_audio → separate_drums → predict_hits → transcribe_and_export`.

### Why Concurrency=1 on Heavy Workers

Demucs loads a bag of 4 transformer models into memory simultaneously. Running two concurrent Demucs jobs on a 4 GB container **will** OOM-kill the worker. The `--concurrency=1` flag combined with `--max-memory-per-child=2048000` (2 GB) ensures the child process is recycled if it leaks memory across jobs.

---

## 2. Service Inventory

| Service | Image / Build | Ports | Volumes | Health Check |
|---------|--------------|-------|---------|-------------|
| `frontend` | `./frontend` (Dockerfile) | `3000` | — | `node fetch()` on `/` |
| `api` | `./backend` (Dockerfile.api) | `8000` | `artifacts`, `models` | `curl /api/v1/health` |
| `worker-default` | `./backend` (Dockerfile.worker) | — | `artifacts`, `models` | `celery inspect ping` |
| `worker-heavy` | `./backend` (Dockerfile.worker) | — | `artifacts`, `models` | `celery inspect ping` |
| `celery-beat` | `./backend` (Dockerfile.worker) | — | — | PID file check |
| `postgres` | `postgres:16-alpine` | `5432` | `pgdata` | `pg_isready` |
| `redis` | `redis:7-alpine` | `6379` | `redisdata` | `redis-cli ping` |
| `jaeger` | `jaegertracing/all-in-one:1.54` | `16686`, `4318` | — | — |

Jaeger is behind the `observability` profile — start with `docker compose --profile observability up`.

---

## 3. Resource Management

### Memory & CPU Limits (Production)

| Service | CPU Limit | Memory Limit | Memory Reservation | `max-memory-per-child` |
|---------|-----------|-------------|-------------------|----------------------|
| `api` | 2.0 | 512 MB | 256 MB | — |
| `worker-default` | 2.0 | 1 GB | 512 MB | 512 MB |
| `worker-heavy` | 4.0 | **4 GB** | 2 GB | 2 GB |

### OOM Risk During Source Separation

Demucs (`htdemucs`) peak memory consumption depends on audio duration:

| Audio Duration | Approximate Peak RAM |
|---------------|---------------------|
| 1 min | ~1.5 GB |
| 3 min | ~2.5 GB |
| 5 min | ~3.5 GB |
| 10+ min | **>4 GB** (OOM risk) |

**Mitigations in place:**
- `--max-memory-per-child=2048000` recycles the child process after each job, preventing cumulative leaks.
- `stop_grace_period: 300s` gives a running Demucs job 5 minutes to finish before `SIGKILL`.
- `task_acks_late=True` + `reject_on_worker_lost=True` ensures a killed job is re-queued, not lost.
- `MAX_DURATION_SECONDS=900` (15 min) caps input length at the API layer.

**If you see OOM kills:** Increase `worker-heavy` memory limit or reduce `MAX_DURATION_SECONDS`.

<details>
<summary><strong>Dev override: relaxed limits</strong></summary>

`docker-compose.override.yml` (applied automatically in dev) sets:
- `worker-heavy` memory limit: **8 GB**
- `api` and `worker-default`: resource limits cleared (`deploy: {}`)
- All services: `read_only: false` (needed for hot-reload volume mounts)

To run with production limits locally:
```bash
docker compose -f docker-compose.yml up --build
```
</details>

---

## 4. ML Artifact Lifecycle

### Model Inventory

| Model | Format | Size | Loaded By | Cache Path |
|-------|--------|------|-----------|-----------|
| AnNOTEator CNN | `.h5` (Keras) | ~15 MB | `ModelResolver.get_keras_model()` | `/data/models/complete_network/{version}/` |
| Demucs htdemucs | PyTorch checkpoints | ~300 MB | `torch.hub` (auto-download) | `~/.cache/torch/hub/` inside container |

### Pre-Seeding Models (Avoid Cold-Start Delays)

On first worker startup, `preload_models()` is called via the `worker_init` signal. If models aren't cached, the worker blocks on download — adding 30-120s to the first job.

**Pre-seed with the download script:**

```bash
# Run inside the worker container
docker compose exec worker-heavy bash -c \
  "MODEL_URI=https://your-bucket.s3.amazonaws.com/models/v1.0.0/complete_network.h5 \
   scripts/download_models.sh /data/models"
```

This downloads both the CNN `.h5` weights and triggers the Demucs `torch.hub` cache.

<details>
<summary><strong>ModelResolver resolution flow</strong></summary>

```
1. Check /data/models/complete_network/{MODEL_VERSION}/complete_network.h5
2. If cache miss → parse MODEL_URI scheme:
   - http(s):// → httpx streaming download
   - s3://      → boto3 download_file
   - file:// or local path → shutil.copy2
3. Load into Keras → singleton cached for process lifetime
```

**Environment variables:**
```bash
MODEL_URI=https://bucket.s3.amazonaws.com/models/v1.0.0/complete_network.h5
MODEL_VERSION=v1.0.0
MODEL_CACHE_DIR=/data/models
```
</details>

### Artifact Storage

Job artifacts (uploaded audio, `drums.wav`, `hits.json`, `sheet_music.musicxml`, `sheet_music.pdf`) are stored in the `artifacts` volume at `/data/artifacts/{job_id}/`.

- **Automatic cleanup:** `celery-beat` runs `cleanup_old_artifacts` every hour, deleting artifacts older than `ARTIFACT_TTL_HOURS` (default: 24h).
- **Manual cleanup:** See [Disaster Recovery](#7-disaster-recovery).

---

## 5. Scaling & Concurrency

### Horizontal Scaling: `worker-default`

Default workers are stateless and I/O-bound. Scale freely:

```bash
# Scale to 3 replicas
docker compose up -d --scale worker-default=3
```

Each replica runs `--concurrency=4`, giving 12 parallel lightweight tasks.

### Vertical Scaling: `worker-heavy`

Heavy workers are **memory-bound** (Demucs). Do **not** increase `--concurrency` beyond 1. Scale by adding replicas:

```bash
# Scale to 2 replicas (each with concurrency=1)
docker compose up -d --scale worker-heavy=2
```

Each replica needs its own 4 GB memory allocation. On a 16 GB host, you can run ~3 heavy workers.

### Scaling Constraints

| Dimension | `worker-default` | `worker-heavy` |
|-----------|-----------------|----------------|
| Scale axis | Horizontal (replicas) | Horizontal (replicas) |
| Concurrency per replica | 4 (configurable) | **1 (fixed)** |
| Memory per replica | 1 GB | 4 GB |
| Bottleneck | I/O (yt-dlp, disk) | RAM (Demucs models) |
| Shared state | Redis queues | Redis queues |

### PaaS Considerations (Railway, ECS, K8s)

Named Docker volumes (`artifacts`, `models`) are **local-only**. On multi-node platforms:
- Replace `STORAGE_BACKEND=local` with `STORAGE_BACKEND=s3`.
- Use `MODEL_URI` pointing to an HTTP/S3 URL (each worker downloads independently).
- `models` volume becomes a per-node download cache — no cross-node sharing needed.

---

## 6. Health & Monitoring

### Health Check Summary

| Service | Mechanism | Interval | Start Period | Failure Threshold |
|---------|-----------|----------|-------------|-------------------|
| `api` | `curl -f http://localhost:8000/api/v1/health` | 15s | 10s | 3 |
| `frontend` | `node -e "fetch('http://localhost:3000/')..."` | 15s | 15s | 3 |
| `worker-default` | `celery inspect ping --destination=default@$$HOSTNAME` | 30s | 60s | 3 |
| `worker-heavy` | `celery inspect ping --destination=heavy@$$HOSTNAME` | 30s | **120s** | 3 |
| `celery-beat` | PID file existence + `kill -0` | 30s | 15s | 3 |
| `postgres` | `pg_isready` | 5s | — | 5 |
| `redis` | `redis-cli ping` | 5s | — | 5 |

**Why 120s start period on `worker-heavy`?** TensorFlow + Keras model loading and Demucs weight initialization can take 60-90s on cold start.

### Interpreting Worker Health Failures

If `celery inspect ping` fails:
1. **During start period** — Normal. Model preloading is still running.
2. **After start period** — Worker process crashed or is hung. Check logs:

```bash
# Tail worker-heavy logs
docker compose logs -f worker-heavy --tail=100

# Check if the process is stuck on a specific job
docker compose exec worker-heavy celery -A app.worker inspect active
```

3. **Repeated failures** — Likely OOM. Check `docker stats` for memory usage, then review `dmesg | grep -i oom`.

### Accessing Logs for Failed ML Jobs

All tasks emit structured JSON logs via `structlog`. Key log events:

| Event | Meaning |
|-------|---------|
| `separation_start` | Demucs job began |
| `separation_failed` | Demucs crashed (check `error` field) |
| `prediction_failed` | CNN inference failed |
| `model_cache_miss` | Model not in cache, downloading |
| `model_preload_failed` | Worker startup model load failed |

```bash
# Find all failed jobs in the last hour
docker compose logs worker-heavy --since=1h 2>&1 | grep '"status": "failed"'

# Get full context for a specific job
docker compose logs worker-heavy 2>&1 | grep "job_id.*<JOB_UUID>"
```

### Prometheus Metrics

The API exposes metrics at `http://localhost:8000/metrics`:

| Metric | Type | Description |
|--------|------|-------------|
| `drumscribe_jobs_total` | Counter | Jobs by status (`completed`, `failed`) |
| `drumscribe_jobs_failed_total` | Counter | Failures by stage (`ingest`, `separation`, `prediction`, `transcription`) |
| `drumscribe_active_jobs` | Gauge | Currently processing jobs |
| `drumscribe_inference_latency_seconds` | Histogram | Latency per pipeline stage |
| `drumscribe_audio_duration_processed_seconds` | Counter | Total audio seconds processed |

### Distributed Tracing (Jaeger)

```bash
# Start with tracing enabled
docker compose --profile observability up

# Jaeger UI: http://localhost:16686
# OTLP HTTP receiver: port 4318
```

Set `OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318` in worker/API environment to send traces.

---

## 7. Disaster Recovery

### Reset Procedure: Stalled Redis Queues

If jobs are stuck in `processing`/`separating_drums` state and workers aren't picking them up:

<details>
<summary><strong>Step-by-step: Purge Celery queues</strong></summary>

```bash
# 1. Stop all workers (gracefully — waits for current task)
docker compose stop worker-default worker-heavy celery-beat

# 2. Purge all pending tasks from Redis
docker compose exec redis redis-cli FLUSHDB

# 3. Verify queues are empty
docker compose exec redis redis-cli LLEN default
docker compose exec redis redis-cli LLEN heavy-compute
# Both should return 0

# 4. Restart workers
docker compose up -d worker-default worker-heavy celery-beat
```

**Warning:** `FLUSHDB` clears Redis DB 0 (the broker). Task results in DB 1 are preserved. If you need to clear results too:
```bash
docker compose exec redis redis-cli -n 1 FLUSHDB
```
</details>

### Reset Procedure: Orphaned Artifacts

If disk usage is growing and automatic cleanup isn't keeping up:

<details>
<summary><strong>Step-by-step: Manual artifact cleanup</strong></summary>

```bash
# 1. Check current artifact volume usage
docker compose exec api du -sh /data/artifacts/

# 2. Trigger manual cleanup (runs the periodic task immediately)
docker compose exec worker-default celery -A app.worker call app.worker.cleanup_old_artifacts

# 3. Nuclear option — delete ALL artifacts (jobs will lose their files)
docker compose exec api find /data/artifacts -mindepth 1 -maxdepth 1 -type d -mtime +1 -exec rm -rf {} +
```
</details>

### Reset Procedure: Corrupted Model Cache

If workers fail to start with model loading errors:

<details>
<summary><strong>Step-by-step: Clear and re-seed model cache</strong></summary>

```bash
# 1. Stop workers
docker compose stop worker-default worker-heavy

# 2. Clear the model cache volume
docker compose exec api rm -rf /data/models/*

# 3. Re-seed models
docker compose run --rm worker-heavy bash -c \
  "scripts/download_models.sh /data/models"

# 4. Restart workers
docker compose up -d worker-default worker-heavy
```
</details>

### Reset Procedure: Stuck Job in Database

If a job is permanently stuck (worker died mid-task, `task_reject_on_worker_lost` didn't fire):

<details>
<summary><strong>Step-by-step: Mark job as failed via SQL</strong></summary>

```bash
# Connect to PostgreSQL
docker compose exec postgres psql -U drumscribe -d drumscribe

# Find stuck jobs (processing for >30 minutes)
SELECT id, status, created_at FROM jobs
WHERE status IN ('processing', 'separating_drums', 'predicting', 'transcribing')
AND created_at < NOW() - INTERVAL '30 minutes';

# Force-fail them
UPDATE jobs SET status = 'failed', error_message = 'Manual reset: worker lost'
WHERE status IN ('processing', 'separating_drums', 'predicting', 'transcribing')
AND created_at < NOW() - INTERVAL '30 minutes';
```
</details>

---

## 8. CI/CD Pipeline

Configuration: `.github/workflows/ci.yml`

### Pipeline Jobs

| Job | Trigger | What It Does |
|-----|---------|-------------|
| `compose-validate` | push, PR | `docker compose config --quiet` — catches YAML errors |
| `backend-test` | push, PR | `pytest tests/unit/` with `requirements-api.txt` |
| `frontend-test` | push, PR | `npm run lint` + `npm run test` |
| `docker-build` | push, PR | Matrix build (API, Worker, Frontend) with Buildx + GHA cache, reports image sizes |
| `security-scan` | push, PR | Trivy CVE scan on API + Worker images (HIGH/CRITICAL) |

### Build Optimizations

- **Docker layer caching:** `cache-from: type=gha` reuses layers across CI runs. Scoped per image (`scope=${{ matrix.name }}`).
- **Dependency caching:** `actions/setup-python` caches pip, `actions/setup-node` caches npm.
- **Matrix strategy:** API, Worker, and Frontend build in parallel.

### Security Scanning

Trivy runs in **report-only mode** (`exit-code: 0`). To enforce blocking on vulnerabilities:

```yaml
# In .github/workflows/ci.yml, change:
exit-code: 0  # report only
# To:
exit-code: 1  # fail build on HIGH/CRITICAL CVEs
```

---

## 9. Security Hardening

All application services (frontend, api, workers, beat) enforce:

| Control | Value | Purpose |
|---------|-------|---------|
| `cap_drop` | `ALL` | Drop all Linux capabilities |
| `security_opt` | `no-new-privileges:true` | Prevent privilege escalation |
| `read_only` | `true` | Immutable root filesystem |
| `tmpfs` | `/tmp` | Writable scratch space only in tmpfs |
| `USER` | `appuser` (UID 1001) | Non-root execution |

Base images are pinned by SHA256 digest for reproducible builds. OCI labels (`org.opencontainers.image.*`) are set on all images.

---

## 10. Quick Reference

### Common Commands

```bash
# Start (dev, with hot-reload)
docker compose up --build

# Start (production, no dev overrides)
docker compose -f docker-compose.yml up --build -d

# Start with observability stack (Jaeger)
docker compose --profile observability up

# View worker logs
docker compose logs -f worker-heavy worker-default

# Scale workers
docker compose up -d --scale worker-default=3 --scale worker-heavy=2

# Inspect active Celery tasks
docker compose exec worker-heavy celery -A app.worker inspect active

# Check queue depths
docker compose exec redis redis-cli LLEN default
docker compose exec redis redis-cli LLEN heavy-compute

# Pre-seed model cache
docker compose exec worker-heavy scripts/download_models.sh /data/models

# Run database migrations
docker compose exec api alembic upgrade head

# Validate compose file
docker compose config --quiet
```

### Environment Variables (Operational)

| Variable | Default | Impact |
|----------|---------|--------|
| `MODEL_URI` | local path | **Must be HTTP/S3 URL in production** |
| `MODEL_VERSION` | `v1.0.0` | Change to trigger model re-download |
| `MODEL_CACHE_DIR` | `/data/models` | Volume mount point |
| `ARTIFACTS_DIR` | `/data/artifacts` | Volume mount point |
| `STORAGE_BACKEND` | `local` | Set to `s3` for PaaS deployment |
| `ARTIFACT_TTL_HOURS` | `24` | Automatic cleanup threshold |
| `MAX_DURATION_SECONDS` | `900` | Input length cap (OOM protection) |
| `MAX_CONCURRENT_JOBS_PER_USER` | `3` | Per-user rate limit |
| `LOG_LEVEL` | `INFO` | Set to `DEBUG` for troubleshooting |

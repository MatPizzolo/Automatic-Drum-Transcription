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
          ┌──────────────┼──────────────┐
          │              │              │
 ┌────────▼───────┐ ┌────▼────────┐ ┌──▼──────────────┐
 │  worker-io     │ │worker-default│ │  worker-heavy   │
 │ queue: io      │ │queue: default│ │queue:heavy-comp │
 │ concurrency: 8 │ │concurrency:4 │ │ concurrency: 1  │
 │                │ │              │ │                 │
 │ • ingest_audio │ │•transcribe_  │ │• separate_drums │
 │   (yt-dlp,     │ │  and_export  │ │  (Demucs)       │
 │   validation)  │ │•cleanup_old_ │ │• predict_hits   │
 │                │ │  artifacts   │ │  (Keras CNN)    │
 └────────────────┘ └──────────────┘ └─────────────────┘
```

### Three-Queue Worker Strategy

The system uses **three Celery worker pools**, each sized for its workload class:

| Worker | Queue | Concurrency | Memory Limit | Purpose |
|--------|-------|-------------|--------------|---------|
| `worker-io` | `io` | 8 | 512 MB | YouTube download (yt-dlp), audio validation — high-concurrency, I/O-bound |
| `worker-default` | `default` | 4 | 1 GB | music21 transcription, MusicXML/PDF export, artifact cleanup — CPU-light |
| `worker-heavy` | `heavy-compute` | 1 | 4 GB | Demucs source separation (~2–4 GB RAM), Keras CNN inference (~500 MB RAM) |

Task routing is declared in `celery_app.conf.task_routes` inside `app/worker.py`. The pipeline executes as a Celery chain:

```python
ingest_audio (io) → separate_drums (heavy-compute) → predict_hits (heavy-compute) → transcribe_and_export (default)
```

### Why Concurrency=1 on `worker-heavy`

Demucs (`htdemucs`) loads a bag of 4 transformer models simultaneously. Running two concurrent jobs on a 4 GB container **will** OOM-kill the worker. `--concurrency=1` combined with `--max-memory-per-child=2048000` (2 GB) recycles the child process after each job, preventing cumulative memory leaks.

### Why `worker-io` Is Separate

YouTube downloads are network-bound and frequently block on I/O. Mixing them with compute tasks on `worker-default` would starve the transcription queue during burst traffic. Isolating them with `--concurrency=8` allows saturating network bandwidth without touching ML workers.

---

## 2. Service Inventory

| Service | Image / Build | Ports | Volumes | Health Check |
|---------|--------------|-------|---------|-------------|
| `frontend` | `./frontend` (Dockerfile) | `3000` | — | `node fetch()` on `/` |
| `api` | `./backend` (Dockerfile.api) | `8000` | `artifacts`, `models` | `curl /api/health` |
| `worker-io` | `./backend` (Dockerfile.worker) | — | `artifacts` | `celery inspect ping` |
| `worker-default` | `./backend` (Dockerfile.worker) | — | `artifacts`, `models` | `celery inspect ping` |
| `worker-heavy` | `./backend` (Dockerfile.worker) | — | `artifacts`, `models`, `./inference` | `celery inspect ping` |
| `celery-beat` | `./backend` (Dockerfile.worker) | — | `./inference` | PID file check |
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
| `worker-io` | 2.0 | 512 MB | 128 MB | 256 MB |
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
- `api`, `worker-io`, and `worker-default`: resource limits cleared (`deploy: {}`)
- All services: `read_only: false` (needed for hot-reload volume mounts)
- `worker-default` and `worker-heavy`: bind-mount `./inference:/app/inference` for live model edits

To run with production limits locally:
```bash
docker compose -f docker-compose.yml up --build
```
</details>

---

## 4. Docker Build Architecture

Both `Dockerfile.api` and `Dockerfile.worker` use a **strict two-stage build** pattern:

```
builder  (python:3.11-slim + build tools)
  └── pip install → system site-packages (/usr/local/lib/python3.11/site-packages)

runtime (python:3.11-slim, no compiler)
  └── COPY --from=builder /usr/local/lib/python3.11/site-packages
  └── COPY --from=builder /usr/local/bin
```

### Key Design Decisions

**No `--prefix` / no `PYTHONPATH` hacks in the image itself.** Dependencies are installed directly to the builder's system Python (no `--prefix=/install`). The runtime stage copies from those exact paths. This means:
- `importlib` resolution is identical between build and runtime.
- No need for `PYTHONPATH=/install/lib/python3.11/site-packages` in the image.
- Avoids the class of bugs where a sub-dependency (e.g. `packaging`, required by `kombu`/`celery[redis]`) is missing from a prefixed layout.

> **Note:** `entrypoint-worker.sh` does set `PYTHONPATH` as a dev-mode guard for when the `./backend` source tree is bind-mounted over `/app` in `docker-compose.override.yml`. This is a runtime workaround only — the production image does not require it.

### Worker Build: `madmom` Isolation

`madmom==0.16.1` uses a legacy `setup.py` that imports `numpy` and `Cython` at **metadata-collection time** — before pip's build-isolation sandbox installs them. The worker Dockerfile resolves this with a tiered install:

```
Tier 0: pip install --upgrade pip setuptools wheel
Tier 1: pip install "Cython>=3.0.0,<4" "numpy==1.26.4"     ← pre-seed build deps
Tier 2: pip install -r req-no-madmom.txt                    ← all other packages (isolated)
Tier 3: pip install --no-build-isolation "madmom==0.16.1"   ← uses Tier 1 env
```

This keeps `celery[redis]` and the full transitive tree resolved cleanly in Tier 2, while giving `madmom` the pre-seeded NumPy it needs in Tier 3.

### Runtime Shared Libraries

| Library | Package | Required By |
|---------|---------|-------------|
| `libpq5` | `apt` | asyncpg / psycopg2 |
| `libsndfile1` | `apt` | soundfile (audio I/O) |
| `ffmpeg` | `apt` | demucs / librosa |
| `lilypond` | `apt` | PDF export (`PDF_BACKEND=lilypond`) |
| `curl` | `apt` | Docker health checks |

---

## 5. ML Artifact Lifecycle

### Model Inventory

| Model | Format | Size | Loaded By | Cache Location |
|-------|--------|------|-----------|----------------|
| AnNOTEator CNN | `.h5` (Keras) | ~15 MB | `ModelResolver.get_keras_model()` | `/data/models/complete_network/{MODEL_VERSION}/` (named volume) |
| Demucs `htdemucs` | PyTorch checkpoints | ~300 MB | `demucs.pretrained.get_model()` via `torch.hub` | `TORCH_HOME=/app/inference/demucs` (bind-mount) |

### `inference/` Bind-Mount Cache Strategy

`worker-default`, `worker-heavy`, and `celery-beat` all mount the host directory `./inference` to `/app/inference` inside the container:

```yaml
volumes:
  - ./inference:/app/inference
```

`TORCH_HOME` is set to `/app/inference/demucs`, so `torch.hub` caches Demucs weights **on the host filesystem**, not inside a Docker volume. This means:

- Weights survive `docker compose down -v` (they live in the repo directory, not a volume).
- The same download is shared across all worker replicas on the same host without re-downloading.
- Developers can pre-populate `./inference/demucs/` manually to avoid the first-run network fetch.

### CNN Model: Graceful Missing-Weights Behavior

`app/core/model_manager.py` (`ModelManager.verify_cnn_model()`) distinguishes between **critical** and **optional** model failures:

| Scenario | Demucs | CNN (`.h5`) | Container outcome |
|----------|--------|-------------|-------------------|
| Both available | ✓ | ✓ | Worker starts normally |
| CNN file missing (local path) | ✓ | ✗ (warning) | **Worker starts** — logs `cnn_model_missing`, hit classification tasks will fail at runtime |
| CNN is remote URI | ✓ | deferred | Worker starts — `ModelResolver` downloads on first job |
| Demucs fails to load | ✗ (critical) | any | Worker **refuses to start** (exit code 1) |

This allows running the full stack during local development without providing custom weights — the container won't crash on startup just because `complete_network.h5` is absent.

### Pre-Seeding Models

On first worker startup, `entrypoint-worker.sh` calls `python -m app.core.model_manager`, which triggers `setup_demucs()` (downloads Demucs weights to `TORCH_HOME`) and `verify_cnn_model()` (validates the CNN path or defers to runtime). Run model setup without starting a worker:

```bash
docker compose run --rm worker-heavy python -m app.core.model_manager
```

### ModelResolver Resolution Flow

```
1. Check /data/models/complete_network/{MODEL_VERSION}/complete_network.h5
2. Cache hit  → return path
3. Cache miss → parse MODEL_URI scheme:
     http(s):// → httpx streaming download (with SHA256 verification if MODEL_SHA256 set)
     s3://      → boto3 download_file
     file://    → shutil.copy2
4. Load into Keras → singleton cached for process lifetime
```

Change `MODEL_VERSION` to force a fresh download on next worker startup.

### Artifact Storage

Job artifacts (`drums.wav`, `hits.json`, `sheet_music.musicxml`, `sheet_music.pdf`) are stored in the `artifacts` named volume at `/data/artifacts/{job_id}/`.

- **Automatic cleanup:** `celery-beat` runs `cleanup_old_artifacts` every hour (jobs older than `ARTIFACT_TTL_HOURS`, default 24h) and `expire_stale_jobs` every 5 minutes (jobs stuck in active states for >30 min).
- **Manual cleanup:** See [Disaster Recovery](#8-disaster-recovery).

---

## 6. Scaling & Concurrency

### Scaling Rules by Worker Type

| Dimension | `worker-io` | `worker-default` | `worker-heavy` |
|-----------|-------------|-----------------|----------------|
| Scale axis | Horizontal | Horizontal | Horizontal |
| Concurrency per replica | 8 | 4 | **1 (fixed)** |
| Memory per replica | 512 MB | 1 GB | 4 GB |
| Bottleneck | Network / disk | CPU (music21) | RAM (Demucs) |
| Shared state | Redis queues | Redis queues | Redis queues |

```bash
# Scale I/O workers for high YouTube-download traffic
docker compose up -d --scale worker-io=4

# Scale default workers for transcription backlog
docker compose up -d --scale worker-default=3

# Scale heavy workers for parallel Demucs jobs (each needs 4 GB)
docker compose up -d --scale worker-heavy=2
```

Do **not** increase `--concurrency` on `worker-heavy` — each Demucs job requires up to 3.5 GB alone. Use additional replicas instead.

### PaaS Considerations (Railway, ECS, K8s)

Named Docker volumes (`artifacts`, `models`) are **local-only**. On multi-node platforms:
- Replace `STORAGE_BACKEND=local` with `STORAGE_BACKEND=s3`.
- Point `MODEL_URI` to an HTTP/S3 URL — each worker downloads independently on startup.
- The `./inference` bind-mount strategy does not apply; provide `TORCH_HOME` pointing to a persistent volume per node.

---

## 7. Health & Monitoring

### Health Check Summary

| Service | Mechanism | Interval | Start Period | Failure Threshold |
|---------|-----------|----------|-------------|-------------------|
| `api` | `curl -f http://localhost:8000/api/health` | 15s | 10s | 3 |
| `frontend` | `node fetch()` on `/` | 15s | 15s | 3 |
| `worker-io` | `celery inspect ping --destination=io@$$HOSTNAME` | 30s | 30s | 3 |
| `worker-default` | `celery inspect ping --destination=default@$$HOSTNAME` | 30s | 60s | 3 |
| `worker-heavy` | `celery inspect ping --destination=heavy@$$HOSTNAME` | 30s | **120s** | 3 |
| `celery-beat` | PID file existence + `kill -0` | 30s | 15s | 3 |
| `postgres` | `pg_isready` | 5s | — | 5 |
| `redis` | `redis-cli ping` | 5s | — | 5 |

**Why 120s start period on `worker-heavy`?** `entrypoint-worker.sh` calls `python -m app.core.model_manager` synchronously before starting Celery. Demucs weight download + Keras model preload can take 60–90 s on cold start.

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

## 8. Disaster Recovery

### Reset Procedure: Stalled Redis Queues

If jobs are stuck in active states and workers aren't picking them up:

<details>
<summary><strong>Step-by-step: Purge Celery queues</strong></summary>

```bash
# 1. Stop all workers (gracefully — waits for current task)
docker compose stop worker-io worker-default worker-heavy celery-beat

# 2. Purge all pending tasks from Redis
docker compose exec redis redis-cli FLUSHDB

# 3. Verify all three queues are empty
docker compose exec redis redis-cli LLEN io
docker compose exec redis redis-cli LLEN default
docker compose exec redis redis-cli LLEN heavy-compute
# All should return 0

# 4. Restart workers
docker compose up -d worker-io worker-default worker-heavy celery-beat
```

**Warning:** `FLUSHDB` clears Redis DB 0 (the broker). Task results in DB 1 are preserved. To clear results too:
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

If workers fail to start with Demucs or CNN loading errors:

<details>
<summary><strong>Step-by-step: Clear and re-seed model cache</strong></summary>

```bash
# 1. Stop workers
docker compose stop worker-default worker-heavy celery-beat

# 2a. Clear the Demucs bind-mount cache (host directory)
rm -rf ./inference/demucs/*

# 2b. Clear the CNN model volume cache
docker compose exec api rm -rf /data/models/*

# 3. Re-seed all models (runs model_manager without starting Celery)
docker compose run --rm worker-heavy python -m app.core.model_manager

# 4. Restart workers
docker compose up -d worker-default worker-heavy celery-beat
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

## 9. CI/CD Pipeline

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

## 10. Security Hardening

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

## 11. Quick Reference

### Common Commands

```bash
# Start (dev, with hot-reload)
docker compose up --build

# Start (production, no dev overrides)
docker compose -f docker-compose.yml up --build -d

# Start with observability stack (Jaeger)
docker compose --profile observability up

# View all worker logs
docker compose logs -f worker-io worker-default worker-heavy

# Scale workers independently
docker compose up -d --scale worker-io=4 --scale worker-default=3 --scale worker-heavy=2

# Inspect active Celery tasks per worker
docker compose exec worker-heavy celery -A app.worker inspect active

# Check all three queue depths
docker compose exec redis redis-cli LLEN io
docker compose exec redis redis-cli LLEN default
docker compose exec redis redis-cli LLEN heavy-compute

# Re-seed model cache (Demucs + CNN check)
docker compose run --rm worker-heavy python -m app.core.model_manager

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

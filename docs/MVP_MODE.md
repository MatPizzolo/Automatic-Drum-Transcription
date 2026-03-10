# MVP Mode: Simplified Docker Setup

## Overview

The MVP mode provides a lightweight Docker execution environment for rapid prototyping and local ML model iteration. It runs only the essential services (Frontend, API, and Database) while bypassing the distributed task queue architecture.

## Architecture Comparison

### Full Production Stack (`make dev-full`)
```
┌──────────┐     ┌─────────┐     ┌───────┐     ┌──────────────┐
│ Frontend │────▶│   API   │────▶│ Redis │────▶│ Celery       │
└──────────┘     └─────────┘     └───────┘     │ Workers      │
                      │                         │ (io, default,│
                      ▼                         │  heavy)      │
                 ┌──────────┐                   └──────────────┘
                 │ Postgres │
                 └──────────┘
```

**Services**: 8 containers (frontend, api, postgres, redis, worker-io, worker-default, worker-heavy, celery-beat)
**Resource Usage**: ~6-8 GB RAM, 4-6 CPU cores
**Use Case**: Production-like testing, full observability, distributed workloads

### MVP Stack (`make dev-mvp`)
```
┌──────────┐     ┌─────────────────────────┐
│ Frontend │────▶│   API (with embedded    │
└──────────┘     │   ML pipeline)          │
                 └────────────┬────────────┘
                              ▼
                         ┌──────────┐
                         │ Postgres │
                         └──────────┘
```

**Services**: 3 containers (frontend, api, postgres)
**Resource Usage**: ~2-4 GB RAM, 2-3 CPU cores
**Use Case**: Local development, ML model experimentation, rapid iteration

## Quick Start

### Start MVP Stack
```bash
make dev-mvp
```

This will:
- Build and start Frontend, API (with ML dependencies), and Postgres
- Set `USE_CELERY=false` automatically
- Run ML pipeline in-process using FastAPI BackgroundTasks

### Start Full Stack
```bash
make dev-full
```

This will:
- Build and start all 8 services
- Use Celery for distributed task processing
- Enable full production-like architecture

### Stop All Services
```bash
make down
```

### Monitor Logs
```bash
make logs-api        # Tail API logs (great for ML pipeline debugging)
make logs-frontend   # Tail Frontend logs
make logs-postgres   # Tail Postgres logs
```

## How It Works

### 1. Environment Variable: `USE_CELERY`

The `USE_CELERY` flag in `app/core/config.py` controls execution mode:

```python
# In docker-compose.mvp.yml
USE_CELERY: "false"

# In docker-compose.yml (full stack)
USE_CELERY: "true"  # (default)
```

### 2. Conditional Pipeline Execution

In `app/api/routes/jobs.py`, the job submission endpoint checks this flag:

```python
if settings.USE_CELERY:
    # Production: dispatch to Celery workers via Redis
    dispatch_pipeline(str(job.id))
else:
    # MVP: run pipeline in FastAPI BackgroundTasks
    background_tasks.add_task(_run_pipeline_sync, str(job.id))
```

### 3. Event-Driven Real-Time Updates

**Architecture**: Both modes use an event-driven approach for Server-Sent Events (SSE), avoiding database polling.

**Full Stack Mode** (`USE_CELERY=true`):
- Uses **Redis Pub/Sub** for event distribution
- Workers publish status updates to `job:{id}:events` channel
- SSE endpoint subscribes to Redis channel
- Scales horizontally across multiple API instances

**MVP Mode** (`USE_CELERY=false`):
- Uses **in-memory `asyncio.Queue`** per job
- Background tasks put status updates into job-specific queues
- SSE endpoint gets updates from the queue
- No Redis dependency, no database polling
- Automatic queue cleanup on job completion

**Event Publisher** (`app/core/events.py`):
```python
# Unified interface - automatically routes to correct backend
from app.core.events import publish_job_event_sync

# In worker tasks
publish_job_event_sync(job_id, status="processing", progress=50)
```

**SSE Endpoint** (`app/api/v1/routes/events.py`):
```python
# Event-driven subscription (no polling!)
async with subscribe_job_events(job_id) as events:
    async for event in events:
        yield f"data: {json.dumps(event)}\n\n"
```

**Benefits**:
- ✅ No connection pool exhaustion
- ✅ No database thrashing
- ✅ Memory efficient with automatic cleanup
- ✅ Same API for both MVP and full stack modes
- ✅ Real-time updates without polling overhead

### 4. MVP Dockerfile

The `infrastructure/Dockerfile.mvp` combines API and worker dependencies:
- Includes all ML libraries (TensorFlow, PyTorch, Demucs, librosa, madmom)
- Includes audio processing tools (ffmpeg, lilypond)
- Single worker process to avoid memory overhead

## Trade-offs

| Feature | MVP Mode | Full Stack |
|---------|----------|------------|
| **Startup Time** | ~30 seconds | ~2 minutes |
| **Memory Usage** | 2-4 GB | 6-8 GB |
| **Concurrency** | Single job at a time | Multiple parallel jobs |
| **Fault Tolerance** | None (in-process) | Task retry, worker restart |
| **Observability** | Basic logs | Celery Flower, Jaeger tracing |
| **Real-time Updates** | In-memory Queue | Redis Pub/Sub |
| **Horizontal Scaling** | No (single instance) | Yes (multiple workers/APIs) |
| **Best For** | Local dev, ML iteration | Staging, production |

## Limitations

### MVP Mode Limitations
1. **No Concurrency**: Jobs run sequentially in the API process
2. **No Retry Logic**: Failed jobs don't automatically retry
3. **API Blocking**: Long-running jobs may impact API responsiveness
4. **No Task Routing**: All pipeline stages run in the same process

### When to Use Full Stack
- Testing distributed workloads
- Benchmarking performance under load
- Validating task queue behavior
- Production deployment

## Development Workflow

### Typical ML Iteration Cycle (MVP Mode)
```bash
# 1. Start MVP stack
make dev-mvp

# 2. Make changes to ML code (e.g., app/ml/engine.py)

# 3. Rebuild and restart
make down
make dev-mvp

# 4. Monitor pipeline execution
make logs-api

# 5. Test via API or Frontend
curl -X POST http://localhost:8000/api/jobs \
  -F "file=@test_audio.wav" \
  -F "title=Test"
```

### Transitioning to Full Stack
```bash
# Stop MVP
make down

# Start full stack for integration testing
make dev-full

# Verify Celery workers are running
docker ps | grep worker
```

## Configuration

### Environment Variables

Both modes respect the same `.env` file. Key variables:

```bash
# Database
POSTGRES_USER=drumscribe
POSTGRES_PASSWORD=drumscribe
POSTGRES_DB=drumscribe

# Storage
ARTIFACTS_DIR=/data/artifacts
MODEL_CACHE_DIR=/data/models

# Model
MODEL_URI=/app/inference/pretrained_models/annoteators/complete_network.h5
MODEL_VERSION=v1.0.0

# PDF Export
PDF_BACKEND=lilypond

# MVP-specific (set automatically by docker-compose.mvp.yml)
USE_CELERY=false
```

### Resource Limits

**MVP Mode** (`docker-compose.mvp.yml`):
```yaml
api:
  deploy:
    resources:
      limits:
        cpus: "4.0"
        memory: 4G
      reservations:
        cpus: "1.0"
        memory: 1G
```

Adjust these based on your machine's capacity.

## Troubleshooting

### API Container OOM (Out of Memory)
```bash
# Increase memory limit in docker-compose.mvp.yml
memory: 6G  # Increase from 4G
```

### Pipeline Hangs or Times Out
```bash
# Check API logs
make logs-api

# Look for memory warnings or GPU issues
```

### Models Not Found
```bash
# Ensure inference/ directory is mounted
ls -la inference/pretrained_models/

# Check MODEL_URI in .env
echo $MODEL_URI
```

### Database Connection Issues
```bash
# Verify Postgres is healthy
docker ps | grep postgres

# Check DATABASE_URL
docker exec -it <api-container> env | grep DATABASE_URL
```

## Next Steps

1. **Add GPU Support**: Modify `docker-compose.mvp.yml` to enable GPU passthrough for faster inference
2. **Optimize Memory**: Profile pipeline stages and adjust worker count
3. **Add Caching**: Implement model caching to speed up repeated runs
4. **Hybrid Mode**: Run some tasks in-process, others via Celery

## Related Documentation

- `README.md` - Main project documentation
- `docs/ARCHITECTURE.md` - Full system architecture
- `docs/DEPLOYMENT.md` - Production deployment guide

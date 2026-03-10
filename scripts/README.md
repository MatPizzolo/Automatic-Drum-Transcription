# DrumScribe Scripts

Production-grade orchestration scripts for DrumScribe MVP.

## Quick Start

```bash
# First time setup (recommended)
make init              # MVP mode (default)
make init MODE=full    # Full stack with Celery/Redis

# Daily workflow
make up                # Start MVP stack
make up MODE=full      # Start full stack
make health            # Verify health
make down              # Stop stack
```

## Scripts Overview

### `init-mvp.sh` - Smart Initialization

**What it does:**
- ✅ Validates `.env` file exists
- ✅ Creates inference directories
- ✅ Checks model file presence
- ✅ Starts containers
- ✅ Waits for PostgreSQL to be ready
- ✅ Waits for API to be healthy
- ✅ Verifies database tables exist
- ✅ Runs final health check
- ✅ Displays startup summary

**Usage:**
```bash
./scripts/init-mvp.sh
# or
make init
```

**When to use:**
- First time setup
- After `make clean`
- When troubleshooting startup issues
- After pulling new code

### `health-check.sh` - Comprehensive Diagnostics

**What it does:**
- ✅ Checks API server health
- ✅ Verifies database connectivity
- ✅ Tests frontend availability
- ✅ Shows container status
- ✅ Displays detailed health metrics

**Usage:**
```bash
./scripts/health-check.sh
# or
make health
```

**Exit codes:**
- `0` - All services healthy
- `1` - One or more services unhealthy

### `init.sh` - Full Stack Initialization

**What it does:**
- ✅ Validates `.env` file exists
- ✅ Sets `USE_CELERY=true` for full stack mode
- ✅ Creates inference directories
- ✅ Checks model file presence
- ✅ Starts all containers (API, Workers, Redis, Postgres, Frontend)
- ✅ Waits for PostgreSQL to be ready
- ✅ Waits for Redis to be ready
- ✅ Waits for API to be healthy
- ✅ Waits for Celery workers to be ready
- ✅ Runs final health check
- ✅ Displays startup summary

**Usage:**
```bash
./scripts/init.sh
# or
make init MODE=full

# With observability (Jaeger tracing)
./scripts/init.sh --observability

# Nuclear option (clean rebuild)
./scripts/init.sh --nuke
```

**When to use:**
- First time setup for production mode
- After `make clean MODE=full`
- When switching from MVP to full stack
- After pulling new code that affects workers

### `cleanup.sh` - Resource Cleanup

**What it does:**
- Stops all containers
- Removes volumes
- Cleans up artifacts

**Usage:**
```bash
./scripts/cleanup.sh
# or
make clean
```

## Makefile Commands

### Quick Start
```bash
make init              # Initialize and start MVP (first run)
make init MODE=full    # Initialize and start full stack
make up                # Start MVP stack (fast)
make up MODE=full      # Start full stack
make status            # Show container status
make health            # Run health check
```

### Development
```bash
make build             # Build images without starting
make rebuild           # Rebuild images and restart
make rebuild MODE=full # Rebuild full stack
make restart           # Restart containers
```

### Debugging
```bash
make logs              # Tail all logs
make logs SERVICE=api  # Tail API logs
make logs JOB=<id>     # Filter logs by job ID
make shell             # Open bash in API container
make shell SERVICE=db  # Open psql shell
```

### Cleanup
```bash
make down              # Stop containers
make down MODE=full    # Stop full stack
make clean             # Stop and remove volumes
make clean MODE=full   # Clean full stack volumes
```

## Troubleshooting

### Database tables not created

```bash
# Check if migrations ran
make shell-api
python -c "from app.core.database import Base; print(Base.metadata.tables.keys())"

# Manually trigger migration
docker-compose -f docker-compose.mvp.yml restart api
```

### API not responding

```bash
# Check logs
make logs-api

# Verify health
curl http://localhost:8000/api/health

# Check database connection
make shell-db
\dt  # List tables
```

### Frontend CORS errors

```bash
# Verify API is running with correct routes
curl http://localhost:8000/api/health

# Check CORS configuration
make shell-api
env | grep CORS
```

### Model file missing

```bash
# Check model file exists
ls -lh inference/pretrained_models/annoteators/

# Download model (if missing)
cd inference/pretrained_models/annoteators
wget https://your-model-url/complete_network.h5
```

## Architecture

### Startup Flow

```
make init
  ├─> Validate .env
  ├─> Create directories
  ├─> Check model file
  ├─> Start containers
  ├─> Wait for PostgreSQL (30s timeout)
  ├─> Wait for API (30s timeout)
  ├─> Verify database tables
  └─> Run health check
```

### Health Check Flow

```
make health
  ├─> Check API (/api/health)
  │   ├─> Database status
  │   ├─> Redis status (skipped in MVP)
  │   └─> Model status
  ├─> Check Frontend (http://localhost:3000)
  ├─> Check PostgreSQL (pg_isready)
  └─> Show container status
```

## Best Practices

### Daily Development

```bash
# Morning - MVP mode
make up           # Start stack (10s)
make health       # Verify (5s)

# Morning - Full stack mode
make up MODE=full # Start all services
make health       # Verify

# Work on code...

# Evening
make down         # Stop stack
```

### After Code Changes

```bash
# Backend changes (MVP)
make rebuild      # Rebuild images (6min)
make up           # Start with new images
make health       # Verify

# Backend changes (Full stack)
make rebuild MODE=full  # Rebuild all images
make up MODE=full       # Start
make health             # Verify
```

### Troubleshooting Session

```bash
make status       # Check containers
make health       # Run diagnostics
make logs-api     # Check API logs
make shell-api    # Debug inside container
make shell-db     # Check database
```

### Clean Slate

```bash
make clean        # Remove everything
make init         # Fresh start
```

## Environment Variables

Key variables checked by scripts:

```bash
# Required
DATABASE_URL              # PostgreSQL connection
MODEL_URI                 # Path to model file
NEXT_PUBLIC_API_URL       # Frontend API URL

# Optional
USE_CELERY=false          # MVP mode (no Redis/Celery)
CORS_ORIGINS              # Allowed origins
LOG_LEVEL=INFO            # Logging verbosity
```

## Exit Codes

All scripts follow standard exit codes:

- `0` - Success
- `1` - General error
- `2` - Missing dependency/file

## Contributing

When adding new scripts:

1. Add shebang: `#!/usr/bin/env bash`
2. Use `set -euo pipefail`
3. Add colored logging functions
4. Include error handling
5. Document in this README
6. Add to Makefile if user-facing
7. Make executable: `chmod +x scripts/your-script.sh`

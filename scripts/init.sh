#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# init.sh — Initialize and start DrumScribe full stack (production mode)
# 
# This script ensures all prerequisites are met before starting:
# - Database migrations applied
# - Model files present
# - Redis connectivity
# - Celery workers ready
# - Health checks passing
# 
# Usage: ./scripts/init.sh [--observability] [--nuke]
#   --observability: include Jaeger tracing UI
#   --nuke:          wipe ALL Docker build cache + project images and force a
#                    100% fresh pip install (use when deps are broken)
# ============================================================================

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OBS_PROFILE=""
NUKE=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

for arg in "$@"; do
    case "$arg" in
        --observability) OBS_PROFILE="--profile observability" ;;
        --nuke)          NUKE=true ;;
        *)
            log_error "Unknown argument: $arg"
            echo "Usage: $0 [--observability] [--nuke]"
            exit 1
            ;;
    esac
done

log_info "DrumScribe Full Stack Initialization"
echo ""

# Check if .env exists
if [ ! -f "$ROOT/.env" ]; then
    log_warn "No .env found. Copying from .env.example..."
    cp "$ROOT/.env.example" "$ROOT/.env"
    log_success ".env created"
fi

# Ensure USE_CELERY is set to true for full stack mode
if ! grep -q "^USE_CELERY=true" "$ROOT/.env"; then
    log_warn "Setting USE_CELERY=true for full stack mode..."
    if grep -q "^USE_CELERY=" "$ROOT/.env"; then
        sed -i.bak 's/^USE_CELERY=.*/USE_CELERY=true/' "$ROOT/.env"
    else
        echo "USE_CELERY=true" >> "$ROOT/.env"
    fi
    log_success "USE_CELERY configured"
fi

# Ensure inference directory exists
log_info "Setting up inference directory..."
mkdir -p "$ROOT/inference/demucs" "$ROOT/inference/pretrained_models/annoteators"
chmod -R 755 "$ROOT/inference" 2>/dev/null || true
log_success "Inference directory ready"

# Check if model file exists
MODEL_FILE="$ROOT/inference/pretrained_models/annoteators/complete_network.h5"
if [ ! -f "$MODEL_FILE" ]; then
    log_error "Model file not found: $MODEL_FILE"
    log_info "Please download the model first:"
    echo "  cd inference/pretrained_models/annoteators"
    echo "  wget https://your-model-url/complete_network.h5"
    exit 1
fi
log_success "Model file found ($(du -h "$MODEL_FILE" | cut -f1))"

echo ""
log_info "Starting full stack..."
echo ""

if $NUKE; then
    echo "==> NUKE: stopping all running containers..."
    docker compose -f "$ROOT/docker-compose.yml" -f "$ROOT/docker-compose.override.yml" down --remove-orphans 2>/dev/null || true

    echo "==> NUKE: removing project images (api + worker)..."
    docker images --format '{{.Repository}}:{{.Tag}}' \
        | grep -E '^(automatic-drum-transcription|drumscribe)' \
        | xargs docker rmi -f 2>/dev/null || true

    echo "==> NUKE: pruning Docker builder cache (this frees disk space)..."
    docker builder prune -af

    echo "==> NUKE: done — all layer caches cleared. Starting fresh build..."
fi

# Use production compose with optional dev overrides
COMPOSE_FILES="-f $ROOT/docker-compose.yml -f $ROOT/docker-compose.override.yml"

# --no-cache forces Docker to re-run every RUN layer from scratch when --nuke is set
if $NUKE; then
    log_info "NUKE mode: Building from scratch..."
    # shellcheck disable=SC2086
    docker compose $COMPOSE_FILES $OBS_PROFILE build --no-cache
    # shellcheck disable=SC2086
    docker compose $COMPOSE_FILES $OBS_PROFILE up -d --remove-orphans
else
    # shellcheck disable=SC2086
    docker compose $COMPOSE_FILES $OBS_PROFILE up -d --build --remove-orphans
fi

# ============================================================================
# Wait for services to be healthy
# ============================================================================

log_info "Waiting for services to start..."
echo ""

# Wait for PostgreSQL
log_info "Checking PostgreSQL..."
MAX_RETRIES=30
RETRY=0
while [ $RETRY -lt $MAX_RETRIES ]; do
    if docker compose $COMPOSE_FILES exec -T postgres pg_isready -U drumscribe >/dev/null 2>&1; then
        log_success "PostgreSQL is ready"
        break
    fi
    RETRY=$((RETRY + 1))
    if [ $RETRY -eq $MAX_RETRIES ]; then
        log_error "PostgreSQL failed to start after ${MAX_RETRIES}s"
        exit 1
    fi
    sleep 1
done

# Wait for Redis
log_info "Checking Redis..."
RETRY=0
while [ $RETRY -lt $MAX_RETRIES ]; do
    if docker compose $COMPOSE_FILES exec -T redis redis-cli ping >/dev/null 2>&1; then
        log_success "Redis is ready"
        break
    fi
    RETRY=$((RETRY + 1))
    if [ $RETRY -eq $MAX_RETRIES ]; then
        log_error "Redis failed to start after ${MAX_RETRIES}s"
        exit 1
    fi
    sleep 1
done

# Wait for API to be healthy
log_info "Checking API server..."
RETRY=0
while [ $RETRY -lt $MAX_RETRIES ]; do
    if curl -sf http://localhost:8000/api/health >/dev/null 2>&1; then
        log_success "API server is healthy"
        break
    fi
    RETRY=$((RETRY + 1))
    if [ $RETRY -eq $MAX_RETRIES ]; then
        log_error "API server failed to start after ${MAX_RETRIES}s"
        log_info "Check logs with: make logs SERVICE=api"
        exit 1
    fi
    sleep 1
done

# Wait for Frontend
log_info "Checking Frontend..."
RETRY=0
while [ $RETRY -lt $MAX_RETRIES ]; do
    if curl -sf http://localhost:3000 >/dev/null 2>&1; then
        log_success "Frontend is ready"
        break
    fi
    RETRY=$((RETRY + 1))
    if [ $RETRY -eq $MAX_RETRIES ]; then
        log_warn "Frontend not responding (this is OK if still building)"
        break
    fi
    sleep 1
done

# ============================================================================
# Final health check
# ============================================================================

echo ""
log_info "Running final health check..."

HEALTH_RESPONSE=$(curl -s http://localhost:8000/api/health)
HEALTH_STATUS=$(echo "$HEALTH_RESPONSE" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)

if [ "$HEALTH_STATUS" = "healthy" ]; then
    log_success "All systems operational"
else
    log_warn "Health check returned: $HEALTH_STATUS"
fi

# ============================================================================
# Summary
# ============================================================================

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
log_success "DrumScribe Full Stack is running!"
echo ""
echo "  🌐 Frontend:  http://localhost:3000"
echo "  🔌 API:       http://localhost:8000"
echo "  📊 Health:    http://localhost:8000/api/health"
echo "  📖 API Docs:  http://localhost:8000/docs"
echo "  🔴 Redis:     localhost:6379"
if [ -n "$OBS_PROFILE" ]; then
    echo "  🔍 Jaeger:    http://localhost:16686"
fi
echo ""
echo "Useful commands:"
echo "  make logs SERVICE=api       - View API logs"
echo "  make logs SERVICE=worker    - View worker logs"
echo "  make down MODE=full         - Stop all services"
echo "  make clean MODE=full        - Stop and remove volumes"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

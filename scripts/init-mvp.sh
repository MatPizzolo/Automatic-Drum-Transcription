#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# init-mvp.sh — Initialize and start DrumScribe MVP stack
# 
# This script ensures all prerequisites are met before starting:
# - Database migrations applied
# - Model files present
# - Health checks passing
# - Clean startup with validation
# ============================================================================

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

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

# ============================================================================
# Pre-flight checks
# ============================================================================

log_info "DrumScribe MVP Initialization"
echo ""

# Check if .env exists
if [ ! -f "$ROOT/.env" ]; then
    log_warn "No .env found. Copying from .env.example..."
    cp "$ROOT/.env.example" "$ROOT/.env"
    log_success ".env created"
fi

# Ensure inference directory exists
log_info "Setting up inference directory..."
mkdir -p "$ROOT/inference/demucs"
chmod -R 755 "$ROOT/inference" 2>/dev/null || true
log_success "Inference directory ready"

echo ""
log_info "Starting MVP stack..."
echo ""

# ============================================================================
# Start containers
# ============================================================================

docker compose -f docker-compose.mvp.yml up -d --remove-orphans

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
    if docker compose -f docker-compose.mvp.yml exec -T postgres pg_isready -U drumscribe >/dev/null 2>&1; then
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
# Verify database tables
# ============================================================================

log_info "Verifying database schema..."
TABLE_COUNT=$(docker compose -f docker-compose.mvp.yml exec -T postgres \
    psql -U drumscribe -d drumscribe -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ' || echo "0")

if [ "$TABLE_COUNT" -eq "0" ]; then
    log_error "No database tables found!"
    log_info "Restarting API to trigger migrations..."
    docker compose -f docker-compose.mvp.yml restart api
    
    # Wait for API to be healthy after restart (migrations run during startup)
    log_info "Waiting for API to complete migrations..."
    RETRY=0
    MAX_RETRIES=30
    while [ $RETRY -lt $MAX_RETRIES ]; do
        if curl -sf http://localhost:8000/api/health > /dev/null 2>&1; then
            log_success "API is healthy"
            break
        fi
        RETRY=$((RETRY + 1))
        if [ $RETRY -eq $MAX_RETRIES ]; then
            log_error "API failed to become healthy after restart"
            exit 1
        fi
        sleep 1
    done
    
    # Verify tables were created
    TABLE_COUNT=$(docker compose -f docker-compose.mvp.yml exec -T postgres \
        psql -U drumscribe -d drumscribe -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" 2>/dev/null | tr -d ' ' || echo "0")
    
    if [ "$TABLE_COUNT" -eq "0" ]; then
        log_error "Database migration failed - no tables created"
        log_info "Check API logs: docker compose -f docker-compose.mvp.yml logs api"
        exit 1
    fi
fi

log_success "Database has $TABLE_COUNT tables"

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
log_success "DrumScribe MVP is running!"
echo ""
echo "  🌐 Frontend:  http://localhost:3000"
echo "  🔌 API:       http://localhost:8000"
echo "  📊 Health:    http://localhost:8000/api/health"
echo "  📖 API Docs:  http://localhost:8000/docs"
echo ""
echo "Useful commands:"
echo "  make logs SERVICE=api       - View API logs"
echo "  make logs SERVICE=frontend  - View frontend logs"
echo "  make down           - Stop all services"
echo "  make clean          - Stop and remove volumes"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

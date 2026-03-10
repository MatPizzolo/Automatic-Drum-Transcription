#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# API Entrypoint - Production-grade initialization
# ============================================================================

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

log_error() {
    echo -e "${RED}✗${NC} $1"
}

echo "="
log_info "DrumScribe API Entrypoint"
log_info "Environment: ${ENVIRONMENT:-development}"
log_info "USE_CELERY: ${USE_CELERY:-true}"
echo "="
echo ""

# ============================================================================
# Wait for PostgreSQL to be ready
# ============================================================================

log_info "Waiting for PostgreSQL..."
MAX_RETRIES=30
RETRY=0

while [ $RETRY -lt $MAX_RETRIES ]; do
    if python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
import os

async def check():
    engine = create_async_engine(os.environ['DATABASE_URL'])
    async with engine.connect() as conn:
        pass
    await engine.dispose()

asyncio.run(check())
" 2>/dev/null; then
        log_success "PostgreSQL is ready"
        break
    fi
    RETRY=$((RETRY + 1))
    if [ $RETRY -eq $MAX_RETRIES ]; then
        log_error "PostgreSQL failed to become ready after ${MAX_RETRIES}s"
        exit 1
    fi
    sleep 1
done

# ============================================================================
# Run database migrations
# ============================================================================

log_info "Running database migrations..."

python -c "
import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.core.database import Base
from app.models.job import Job  # Import models so SQLAlchemy knows about them
import os

async def init_database():
    try:
        engine = create_async_engine(os.environ['DATABASE_URL'], echo=False)
        
        # Create tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        # Verify tables exist
        async with engine.connect() as conn:
            result = await conn.execute(
                text(\"SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public'\")
            )
            table_count = result.scalar()
            print(f'✓ Database initialized with {table_count} tables')
            
            if table_count == 0:
                print('✗ ERROR: No tables created!', file=sys.stderr)
                sys.exit(1)
        
        await engine.dispose()
        return 0
        
    except Exception as e:
        print(f'✗ Database initialization failed: {e}', file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

sys.exit(asyncio.run(init_database()))
" || {
    log_error "Database migration failed"
    exit 1
}

log_success "Database migrations complete"

# ============================================================================
# Verify model file exists (if not using remote URI)
# ============================================================================

if [[ "${MODEL_URI:-}" != http* ]] && [[ "${MODEL_URI:-}" != s3://* ]]; then
    if [ -n "${MODEL_URI:-}" ]; then
        # Handle both absolute and relative paths
        if [[ "${MODEL_URI}" = /* ]]; then
            MODEL_PATH="${MODEL_URI}"
        else
            MODEL_PATH="/app/${MODEL_URI}"
        fi
        
        if [ -f "$MODEL_PATH" ]; then
            MODEL_SIZE=$(du -h "$MODEL_PATH" | cut -f1)
            log_success "Model file found: $MODEL_PATH ($MODEL_SIZE)"
        else
            log_error "Model file not found: $MODEL_PATH"
            log_info "Please ensure the model file is mounted or downloaded"
            exit 1
        fi
    fi
fi

# ============================================================================
# Start API server
# ============================================================================

echo ""
log_success "Initialization complete. Starting API server..."
echo ""

# Execute the CMD from Dockerfile
exec "$@"

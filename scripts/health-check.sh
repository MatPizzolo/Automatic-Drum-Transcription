#!/usr/bin/env bash
set -euo pipefail

# ============================================================================
# health-check.sh — Comprehensive health check for DrumScribe stack
# ============================================================================

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check_service() {
    local name=$1
    local url=$2
    
    if curl -sf "$url" >/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} $name is healthy"
        return 0
    else
        echo -e "${RED}✗${NC} $name is not responding"
        return 1
    fi
}

echo "DrumScribe Health Check"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

HEALTHY=true

# Check API
if check_service "API Server" "http://localhost:8000/api/health"; then
    HEALTH_JSON=$(curl -s http://localhost:8000/api/health)
    echo "  Status: $(echo "$HEALTH_JSON" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)"
    echo "  Database: $(echo "$HEALTH_JSON" | grep -o '"database":{[^}]*}' | grep -o '"status":"[^"]*"' | cut -d'"' -f4)"
    echo "  Model: $(echo "$HEALTH_JSON" | grep -o '"model":{[^}]*}' | grep -o '"status":"[^"]*"' | cut -d'"' -f4)"
else
    HEALTHY=false
fi

echo ""

# Check Frontend
check_service "Frontend" "http://localhost:3000" || HEALTHY=false

echo ""

# Check Database
if docker compose ps --format json 2>/dev/null | grep -q postgres; then
    if docker compose exec -T postgres pg_isready -U drumscribe >/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} PostgreSQL is ready"
    else
        echo -e "${RED}✗${NC} PostgreSQL is not ready"
        HEALTHY=false
    fi
else
    echo -e "${YELLOW}⚠${NC} PostgreSQL container not found"
fi

echo ""

# Check Redis (if running in full mode)
if docker compose ps --format json 2>/dev/null | grep -q redis; then
    if docker compose exec -T redis redis-cli ping >/dev/null 2>&1; then
        echo -e "${GREEN}✓${NC} Redis is ready"
    else
        echo -e "${RED}✗${NC} Redis is not ready"
        HEALTHY=false
    fi
fi

echo ""

# Check containers
echo "Container Status:"
docker compose ps

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if $HEALTHY; then
    echo -e "${GREEN}✓ All services are healthy${NC}"
    exit 0
else
    echo -e "${RED}✗ Some services are unhealthy${NC}"
    exit 1
fi

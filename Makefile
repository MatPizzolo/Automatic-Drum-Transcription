# ============================================================================
# DrumScribe Makefile
# ============================================================================

# Configuration
MODE ?= mvp
COMPOSE_FILE_MVP = docker-compose.mvp.yml
COMPOSE_FILE_FULL = docker-compose.yml
COMPOSE_FILE = $(if $(filter full,$(MODE)),$(COMPOSE_FILE_FULL),$(COMPOSE_FILE_MVP))
COMPOSE = docker compose -f $(COMPOSE_FILE)

# Service names
SERVICE_API = api
SERVICE_FRONTEND = frontend
SERVICE_DB = postgres

# Colors for output (optional, for better UX)
BOLD := $(shell tput bold 2>/dev/null)
RESET := $(shell tput sgr0 2>/dev/null)

.DEFAULT_GOAL := help

.PHONY: help init status health up build rebuild down clean restart logs shell

# ============================================================================
# Help
# ============================================================================

help:
	@echo "$(BOLD)DrumScribe Docker Orchestration$(RESET)"
	@echo "================================"
	@echo ""
	@echo "$(BOLD)🚀 Quick Start:$(RESET)"
	@echo "  make init              - Initialize and start MVP (MODE=mvp|full, default: mvp)"
	@echo "  make up                - Start services (MODE=mvp|full, default: mvp)"
	@echo "  make status            - Show container status"
	@echo "  make health            - Run comprehensive health check"
	@echo ""
	@echo "$(BOLD)🔧 Development:$(RESET)"
	@echo "  make build             - Build images without starting"
	@echo "  make rebuild           - Rebuild images and restart services"
	@echo "  make restart           - Restart running containers"
	@echo "  make down              - Stop all containers"
	@echo "  make clean             - Stop and remove all volumes (fresh start)"
	@echo ""
	@echo "$(BOLD)🔍 Debugging:$(RESET)"
	@echo "  make logs              - Tail all logs (SERVICE=api|frontend|postgres)"
	@echo "  make logs SERVICE=api  - Tail specific service logs"
	@echo "  make logs JOB=<id>     - Filter logs for specific job ID"
	@echo "  make shell             - Open shell (SERVICE=api|db, default: api)"
	@echo ""
	@echo "$(BOLD)📊 Monitoring:$(RESET)"
	@echo "  See docs/LOGGING_GUIDE.md for detailed logging documentation"
	@echo ""
	@echo "$(BOLD)💡 Examples:$(RESET)"
	@echo "  make up MODE=mvp       - Start MVP stack (default)"
	@echo "  make up MODE=full      - Start full production stack"
	@echo "  make rebuild MODE=full - Rebuild and restart full stack"
	@echo "  make logs SERVICE=api  - Tail API logs"
	@echo ""

init:
	@if [ "$(MODE)" = "full" ]; then \
		echo "🚀 Initializing DrumScribe Full Stack..."; \
		bash scripts/init.sh; \
	else \
		echo "🚀 Initializing DrumScribe MVP..."; \
		bash scripts/init-mvp.sh; \
	fi

# ============================================================================
# Core Commands
# ============================================================================

status:
	@echo "📊 Container Status (MODE=$(MODE)):"
	@$(COMPOSE) ps

health:
	@echo "🏥 Running health check..."
	@bash scripts/health-check.sh

up:
	@echo "🚀 Starting $(MODE) stack..."
	@$(COMPOSE) up -d
	@echo "✅ $(MODE) stack is running!"
	@echo "   Frontend: http://localhost:3000"
	@echo "   API:      http://localhost:8000"
	@echo "   Health:   http://localhost:8000/api/health"
	@if [ "$(MODE)" = "full" ]; then \
		echo "   Redis:    localhost:6379"; \
		echo "   Jaeger:   http://localhost:16686 (if observability enabled)"; \
	fi
	@echo ""
	@echo "💡 Run 'make health' to verify all services are ready"

build:
	@echo "🔨 Building $(MODE) stack images..."
	@$(COMPOSE) build
	@echo "✅ Images built!"

rebuild: build
	@echo "🔄 Restarting services..."
	@$(COMPOSE) up -d
	@echo "✅ Services rebuilt and restarted!"

down:
	@echo "🛑 Stopping containers (MODE=$(MODE))..."
	@$(COMPOSE) down
	@echo "✅ Containers stopped"

restart:
	@echo "🔄 Restarting containers (MODE=$(MODE))..."
	@$(COMPOSE) restart
	@echo "✅ Containers restarted"

clean:
	@echo "🧹 Cleaning containers and volumes (MODE=$(MODE))..."
	@$(COMPOSE) down -v
	@echo "✅ All containers and volumes removed"
	@echo "⚠️  Run 'make init' or 'make up' to start fresh"

# ============================================================================
# Debugging & Monitoring
# ============================================================================

logs:
	@if [ -n "$(JOB)" ]; then \
		echo "� Filtering logs for job: $(JOB)"; \
		$(COMPOSE) logs $(SERVICE_API) | grep "$(JOB)"; \
	elif [ -n "$(SERVICE)" ]; then \
		echo "📋 Tailing $(SERVICE) logs (Ctrl+C to exit)..."; \
		$(COMPOSE) logs -f $(SERVICE); \
	else \
		echo "📋 Tailing all logs (Ctrl+C to exit)..."; \
		$(COMPOSE) logs -f; \
	fi

shell:
	@if [ "$(SERVICE)" = "db" ]; then \
		echo "🐚 Opening PostgreSQL shell..."; \
		$(COMPOSE) exec $(SERVICE_DB) psql -U drumscribe -d drumscribe; \
	else \
		SVC=$${SERVICE:-$(SERVICE_API)}; \
		echo "🐚 Opening shell in $$SVC container..."; \
		$(COMPOSE) exec $$SVC /bin/bash; \
	fi

db-reset:
	@echo "🗑️  Resetting database..."
	@echo "⚠️  This will delete all jobs, artifacts, and data!"
	@read -p "Are you sure? [y/N] " -n 1 -r; \
	echo; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		echo "Dropping and recreating database..."; \
		$(COMPOSE) exec -T $(SERVICE_DB) psql -U drumscribe -d postgres -c "DROP DATABASE IF EXISTS drumscribe;"; \
		$(COMPOSE) exec -T $(SERVICE_DB) psql -U drumscribe -d postgres -c "CREATE DATABASE drumscribe;"; \
		echo "Running migrations..."; \
		$(COMPOSE) exec -T $(SERVICE_API) alembic upgrade head; \
		echo "✅ Database reset complete!"; \
	else \
		echo "❌ Database reset cancelled"; \
	fi

# ============================================================================
# Backward Compatibility (deprecated, will be removed)
# ============================================================================

dev-mvp: up
	@echo "⚠️  'make dev-mvp' is deprecated. Use 'make up MODE=mvp' instead."

dev-full:
	@$(MAKE) up MODE=full
	@echo "⚠️  'make dev-full' is deprecated. Use 'make up MODE=full' instead."

rebuild-mvp: rebuild
	@echo "⚠️  'make rebuild-mvp' is deprecated. Use 'make rebuild MODE=mvp' instead."

rebuild-full:
	@$(MAKE) rebuild MODE=full
	@echo "⚠️  'make rebuild-full' is deprecated. Use 'make rebuild MODE=full' instead."

logs-api:
	@$(MAKE) logs SERVICE=api

logs-frontend:
	@$(MAKE) logs SERVICE=frontend

logs-postgres:
	@$(MAKE) logs SERVICE=postgres

logs-all:
	@$(MAKE) logs

logs-job:
	@if [ -z "$(JOB)" ]; then \
		echo "❌ Error: Please specify JOB=<job-id>"; \
		echo "Example: make logs JOB=abc-123"; \
		exit 1; \
	fi
	@$(MAKE) logs JOB=$(JOB)

shell-api:
	@$(MAKE) shell SERVICE=api

shell-db:
	@$(MAKE) shell SERVICE=db

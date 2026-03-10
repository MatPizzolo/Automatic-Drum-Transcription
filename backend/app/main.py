import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.api.v1.router import api_v1_router
from app.core.config import settings
from app.core.telemetry import metrics_response, setup_opentelemetry
from app.utils.logging import setup_logging, get_logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan — startup and shutdown events."""
    setup_logging()
    logger = get_logger("app.main")
    logger.info(
        "application_startup",
        app_name=settings.APP_NAME,
        version=settings.APP_VERSION,
    )
    setup_opentelemetry()
    yield
    logger.info("application_shutdown")


def create_app() -> FastAPI:
    """FastAPI application factory."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # HTTP request logging middleware
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """Log all HTTP requests with timing and correlation ID."""
        request_id = str(uuid.uuid4())
        start = time.monotonic()
        
        # Add request_id to structlog context for this request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        
        response = await call_next(request)
        
        duration_ms = int((time.monotonic() - start) * 1000)
        
        # Skip logging health checks and metrics to reduce noise
        if request.url.path not in ["/api/health", "/metrics"]:
            logger = get_logger("http")
            logger.info(
                "http_request",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                client_ip=request.client.host if request.client else "unknown",
            )
        
        # Add correlation ID to response headers for debugging
        response.headers["X-Request-ID"] = request_id
        return response

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(api_v1_router)

    # Prometheus metrics endpoint (outside /api prefix)
    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics():
        return metrics_response()

    return app


app = create_app()

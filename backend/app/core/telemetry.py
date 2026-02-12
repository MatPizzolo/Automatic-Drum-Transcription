"""
Observability setup — Prometheus metrics + OpenTelemetry tracing.
"""

from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from fastapi import Response

from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Prometheus Metrics
# ---------------------------------------------------------------------------

INFERENCE_LATENCY = Histogram(
    "inference_latency_seconds",
    "Latency of each pipeline stage in seconds",
    labelnames=["stage"],
    buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0),
)

JOBS_TOTAL = Counter(
    "jobs_total",
    "Total number of jobs by terminal status",
    labelnames=["status"],
)

JOBS_FAILED_TOTAL = Counter(
    "jobs_failed_total",
    "Total number of failed jobs by failure stage",
    labelnames=["failure_stage"],
)

AUDIO_DURATION_PROCESSED = Counter(
    "audio_duration_seconds_processed",
    "Total seconds of audio processed",
)

ACTIVE_JOBS_GAUGE = Gauge(
    "active_jobs_gauge",
    "Number of currently in-flight jobs",
)


def metrics_response() -> Response:
    """Generate Prometheus metrics response."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


def setup_opentelemetry() -> None:
    """Configure OpenTelemetry tracing (optional — only if OTLP endpoint is set)."""
    from app.core.config import settings

    if not settings.OTLP_ENDPOINT:
        logger.info("otel_disabled", reason="OTLP_ENDPOINT not configured")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": "drumscribe-api"})
        provider = TracerProvider(resource=resource)

        exporter = OTLPSpanExporter(endpoint=f"{settings.OTLP_ENDPOINT}/v1/traces")
        provider.add_span_processor(BatchSpanProcessor(exporter))

        trace.set_tracer_provider(provider)
        logger.info("otel_configured", endpoint=settings.OTLP_ENDPOINT)

    except Exception as e:
        logger.warning("otel_setup_failed", error=str(e))

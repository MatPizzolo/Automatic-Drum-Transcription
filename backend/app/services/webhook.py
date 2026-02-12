"""
Webhook service — fire-and-forget notification to user-configured URLs.

Single retry on failure. Does not block the pipeline.
"""

import json
from typing import Optional

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def fire_webhook(job_id: str, webhook_url: str) -> None:
    """POST job result (or error) to the configured webhook URL."""
    from app.core.database_sync import get_sync_db
    from app.models.job import Job

    db = get_sync_db()
    try:
        job = db.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none()
        if job is None:
            logger.warning("webhook_job_not_found", job_id=job_id)
            return

        payload = {
            "job_id": str(job.id),
            "status": job.status.value if hasattr(job.status, "value") else str(job.status),
            "title": job.title,
            "detected_bpm": job.detected_bpm,
            "duration_seconds": job.duration_seconds,
            "confidence_score": job.confidence_score,
            "hit_summary": job.hit_summary,
            "warnings": job.warnings or [],
            "compute_time_ms": job.compute_time_ms,
            "model_version": job.model_version,
            "error_message": job.error_message,
        }

        if job.result_musicxml_path:
            payload["download_urls"] = {
                "musicxml": f"/api/v1/jobs/{job.id}/download/musicxml",
            }
            if job.result_pdf_path:
                payload["download_urls"]["pdf"] = f"/api/v1/jobs/{job.id}/download/pdf"

    finally:
        db.close()

    _send_webhook(webhook_url, payload, job_id=job_id)


def _send_webhook(
    url: str,
    payload: dict,
    job_id: str = "",
    max_retries: int = 1,
) -> None:
    """Send webhook with a single retry on failure."""
    timeout = settings.WEBHOOK_TIMEOUT_SECONDS

    for attempt in range(1 + max_retries):
        try:
            response = httpx.post(
                url,
                json=payload,
                timeout=timeout,
                headers={"Content-Type": "application/json"},
            )
            logger.info(
                "webhook_sent",
                job_id=job_id,
                url=url,
                status_code=response.status_code,
                attempt=attempt + 1,
            )
            return
        except Exception as e:
            logger.warning(
                "webhook_failed",
                job_id=job_id,
                url=url,
                attempt=attempt + 1,
                error=str(e),
            )

    logger.error(
        "webhook_exhausted_retries",
        job_id=job_id,
        url=url,
        max_retries=max_retries,
    )

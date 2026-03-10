"""
Server-Sent Events endpoint for real-time job status updates.

Event-driven architecture:
- Full mode (USE_CELERY=true): Redis Pub/Sub
- MVP mode (USE_CELERY=false): In-memory asyncio.Queue

No database polling - all updates are pushed via events.
"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db
from app.core.events import subscribe_job_events, cleanup_job_queue
from app.models.job import Job, JobStatus
from app.utils.logging import get_logger

router = APIRouter(prefix="/jobs", tags=["events"])
logger = get_logger(__name__)

TERMINAL_STATUSES = {
    JobStatus.COMPLETED.value,
    JobStatus.FAILED.value,
    JobStatus.CANCELLED.value,
}


@router.get("/{job_id}/events")
async def job_events(
    job_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Stream job status updates as Server-Sent Events.

    Event-driven: subscribes to Redis Pub/Sub (full mode) or asyncio.Queue (MVP mode).
    No database polling - all updates are pushed by worker tasks.
    
    The client should connect once after job creation and keep the stream open.
    The stream closes automatically when the job reaches a terminal status.
    """
    # Initial DB query to verify job exists and get current state
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    job_id_str = str(job_id)

    async def event_stream():
        # Always emit the current state immediately on connect
        snapshot = {
            "job_id": job_id_str,
            "status": job.status.value,
            "progress": job.progress,
        }
        yield f"data: {json.dumps(snapshot)}\n\n"

        # If already terminal, close immediately
        if job.status.value in TERMINAL_STATUSES:
            return

        # Subscribe to event stream (Redis or Queue depending on mode)
        try:
            async with subscribe_job_events(job_id_str) as events:
                async for event in events:
                    # Check if client disconnected
                    if await request.is_disconnected():
                        logger.debug("sse_client_disconnected", job_id=job_id_str)
                        break
                    
                    # Stream event to client
                    yield f"data: {json.dumps(event)}\n\n"
                    
                    # Close stream on terminal status
                    if event.get("status") in TERMINAL_STATUSES:
                        logger.debug("sse_terminal_status", job_id=job_id_str, status=event.get("status"))
                        break
        except Exception as e:
            logger.error("sse_stream_error", job_id=job_id_str, error=str(e), error_type=type(e).__name__)
            # Send error event to client
            error_event = {
                "job_id": job_id_str,
                "error": "Stream interrupted",
            }
            yield f"data: {json.dumps(error_event)}\n\n"
        finally:
            # Cleanup queue if in MVP mode
            await cleanup_job_queue(job_id_str)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

"""
Event bus for job status updates.

Provides a unified interface for publishing job events that works in both:
- MVP mode: In-memory asyncio.Queue per job
- Full mode: Redis Pub/Sub
"""

import asyncio
import json
from typing import Dict, Optional
from contextlib import asynccontextmanager

from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

# In-memory event bus for MVP mode (USE_CELERY=false)
# Maps job_id -> asyncio.Queue
_job_queues: Dict[str, asyncio.Queue] = {}
_queue_lock = asyncio.Lock()


async def get_job_queue(job_id: str) -> asyncio.Queue:
    """Get or create an asyncio.Queue for a specific job.
    
    Used in MVP mode for in-memory event distribution.
    """
    async with _queue_lock:
        if job_id not in _job_queues:
            _job_queues[job_id] = asyncio.Queue(maxsize=100)
            logger.debug("job_queue_created", job_id=job_id)
        return _job_queues[job_id]


async def cleanup_job_queue(job_id: str) -> None:
    """Remove a job's queue after completion.
    
    Called when job reaches terminal status to prevent memory leaks.
    """
    async with _queue_lock:
        if job_id in _job_queues:
            queue = _job_queues.pop(job_id)
            # Drain any remaining items
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            logger.debug("job_queue_cleaned", job_id=job_id)


async def publish_job_event(job_id: str, status: str, progress: int = 0) -> None:
    """Publish a job status update event.
    
    Routes to either Redis Pub/Sub (full mode) or in-memory Queue (MVP mode).
    
    Args:
        job_id: Job identifier
        status: Job status (queued, processing, completed, failed, etc.)
        progress: Progress percentage (0-100)
    """
    payload = json.dumps({
        "job_id": job_id,
        "status": status,
        "progress": progress,
    })
    
    if settings.USE_CELERY:
        # Full mode: Publish to Redis
        try:
            import redis.asyncio as aioredis
            redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
            channel = f"job:{job_id}:events"
            await redis_client.publish(channel, payload)
            await redis_client.aclose()
            logger.debug("event_published_redis", job_id=job_id, status=status)
        except Exception as e:
            logger.warning("redis_publish_failed", job_id=job_id, error=str(e))
    else:
        # MVP mode: Put into in-memory queue
        try:
            queue = await get_job_queue(job_id)
            # Non-blocking put - if queue is full, drop oldest event
            try:
                queue.put_nowait(payload)
                logger.debug("event_published_queue", job_id=job_id, status=status)
            except asyncio.QueueFull:
                # Drop oldest event and add new one
                try:
                    queue.get_nowait()
                    queue.put_nowait(payload)
                    logger.warning("event_queue_full_dropped_oldest", job_id=job_id)
                except Exception:
                    pass
        except Exception as e:
            logger.error("queue_publish_failed", job_id=job_id, error=str(e))


def publish_job_event_sync(job_id: str, status: str, progress: int = 0) -> None:
    """Synchronous wrapper for publish_job_event.
    
    Used by worker tasks that run in sync context.
    """
    payload = json.dumps({
        "job_id": job_id,
        "status": status,
        "progress": progress,
    })
    
    if settings.USE_CELERY:
        # Full mode: Use sync Redis client
        try:
            import redis as sync_redis
            r = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)
            channel = f"job:{job_id}:events"
            r.publish(channel, payload)
            r.close()
            logger.debug("event_published_redis_sync", job_id=job_id, status=status)
        except Exception as e:
            logger.warning("redis_publish_failed_sync", job_id=job_id, error=str(e))
    else:
        # MVP mode: Direct queue access (thread-safe)
        # In MVP mode, background tasks run in the same process as the API
        # so we can directly access the queue dictionary
        try:
            # Check if queue exists for this job
            if job_id in _job_queues:
                queue = _job_queues[job_id]
                # Use put_nowait which is thread-safe
                try:
                    queue.put_nowait(payload)
                    logger.debug("event_published_queue_sync", job_id=job_id, status=status)
                except asyncio.QueueFull:
                    # Drop oldest event
                    try:
                        queue.get_nowait()
                        queue.put_nowait(payload)
                        logger.warning("event_queue_full_dropped_oldest_sync", job_id=job_id)
                    except Exception:
                        pass
            else:
                # Queue doesn't exist yet - SSE hasn't connected
                # This is fine, SSE will get current state from DB on connect
                logger.debug("queue_not_ready_yet", job_id=job_id, status=status)
        except Exception as e:
            logger.error("queue_publish_failed_sync", job_id=job_id, error=str(e))


@asynccontextmanager
async def subscribe_job_events(job_id: str):
    """Subscribe to job events as an async context manager.
    
    Yields an async iterator that produces event payloads.
    
    Usage:
        async with subscribe_job_events(job_id) as events:
            async for event in events:
                # event is a dict with job_id, status, progress
                yield f"data: {json.dumps(event)}\\n\\n"
    """
    if settings.USE_CELERY:
        # Full mode: Subscribe to Redis Pub/Sub
        import redis.asyncio as aioredis
        redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        channel = f"job:{job_id}:events"
        
        async def redis_event_generator():
            async with redis_client.pubsub() as pubsub:
                await pubsub.subscribe(channel)
                try:
                    async for message in pubsub.listen():
                        if message["type"] == "message":
                            try:
                                yield json.loads(message["data"])
                            except (json.JSONDecodeError, TypeError):
                                continue
                finally:
                    await pubsub.unsubscribe(channel)
            await redis_client.aclose()
        
        yield redis_event_generator()
    else:
        # MVP mode: Subscribe to in-memory queue
        queue = await get_job_queue(job_id)
        
        async def queue_event_generator():
            while True:
                try:
                    # Wait for next event with timeout
                    payload = await asyncio.wait_for(queue.get(), timeout=30.0)
                    try:
                        yield json.loads(payload)
                    except (json.JSONDecodeError, TypeError):
                        continue
                except asyncio.TimeoutError:
                    # No events for 30s - yield a heartbeat or continue
                    continue
                except Exception as e:
                    logger.error("queue_get_failed", job_id=job_id, error=str(e))
                    break
        
        yield queue_event_generator()

"""
Concurrency control — DB-based per-user job limits.

The API layer checks active job count via DB query in the POST /jobs route.
This module provides helper utilities for concurrency enforcement.
"""

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.job import Job, JobStatus
from app.utils.logging import get_logger

logger = get_logger(__name__)

ACTIVE_STATUSES = [
    JobStatus.QUEUED,
    JobStatus.PROCESSING,
    JobStatus.SEPARATING_DRUMS,
    JobStatus.PREDICTING,
    JobStatus.TRANSCRIBING,
]


async def get_active_job_count(db: AsyncSession, user_id: str) -> int:
    """Count active (non-terminal) jobs for a user."""
    result = await db.execute(
        select(func.count(Job.id)).where(
            Job.user_identifier == user_id,
            Job.status.in_(ACTIVE_STATUSES),
        )
    )
    return result.scalar_one()


async def check_concurrency_limit(db: AsyncSession, user_id: str) -> bool:
    """
    Check if user is under the concurrency limit.

    Returns True if a new job is allowed, False if limit exceeded.
    """
    count = await get_active_job_count(db, user_id)
    if count >= settings.MAX_CONCURRENT_JOBS_PER_USER:
        logger.info(
            "concurrency_limit_hit",
            user=user_id,
            active=count,
            limit=settings.MAX_CONCURRENT_JOBS_PER_USER,
        )
        return False
    return True

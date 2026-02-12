import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_db
from app.core.config import settings
from app.models.job import InputType, Job, JobStatus
from app.schemas.job import (
    JobCreate,
    JobCreateResponse,
    JobDeleteResponse,
    JobResultResponse,
    JobStatusResponse,
    HitData,
)
from app.core.security import check_concurrency_limit
from app.storage.backend import get_storage
from app.utils.logging import get_logger
from app.worker import celery_app, dispatch_pipeline

router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = get_logger(__name__)


def _get_user_identifier(request: Request) -> str:
    """Extract user identifier from request (IP-based for now)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _validate_file(file: UploadFile) -> None:
    """Validate uploaded file type and size."""
    if file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=422,
                detail=f"File type '.{ext}' not allowed. Accepted: {settings.ALLOWED_EXTENSIONS}",
            )

    if file.content_type and file.content_type not in settings.ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"MIME type '{file.content_type}' not allowed.",
        )


async def _save_upload(job_id: uuid.UUID, file: UploadFile) -> str:
    """Save uploaded file via storage backend. Returns the saved path."""
    storage = get_storage()
    filename = file.filename or "upload.audio"

    content = await file.read()
    if len(content) > settings.max_file_size_bytes:
        raise HTTPException(
            status_code=422,
            detail=f"File exceeds maximum size of {settings.MAX_FILE_SIZE_MB} MB.",
        )

    return storage.save_file(str(job_id), filename, content)


@router.post("", response_model=JobCreateResponse, status_code=201)
async def create_job(
    request: Request,
    file: Optional[UploadFile] = File(None),
    youtube_url: Optional[str] = Form(None),
    title: Optional[str] = Form("Untitled"),
    bpm: Optional[int] = Form(None),
    webhook_url: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Create a new transcription job from file upload or YouTube URL."""
    user_id = _get_user_identifier(request)

    # Must provide either file or youtube_url
    if file is None and youtube_url is None:
        raise HTTPException(
            status_code=422,
            detail="Must provide either a file upload or a youtube_url.",
        )

    if file is not None and youtube_url is not None:
        raise HTTPException(
            status_code=422,
            detail="Provide either a file upload or a youtube_url, not both.",
        )

    # Validate BPM range if provided
    if bpm is not None and (bpm < 40 or bpm > 300):
        raise HTTPException(
            status_code=422,
            detail="BPM must be between 40 and 300.",
        )

    # Validate YouTube URL
    if youtube_url is not None:
        try:
            job_create = JobCreate(youtube_url=youtube_url, title=title or "Untitled", bpm=bpm, webhook_url=webhook_url)
        except Exception as e:
            raise HTTPException(status_code=422, detail=str(e))
        input_type = InputType.YOUTUBE
    else:
        input_type = InputType.UPLOAD

    # Validate file if uploaded
    if file is not None:
        _validate_file(file)

    # Check per-user concurrency limit BEFORE creating the job
    if not await check_concurrency_limit(db, user_id):
        raise HTTPException(
            status_code=429,
            detail=f"Concurrent job limit ({settings.MAX_CONCURRENT_JOBS_PER_USER}) exceeded. Please wait.",
            headers={"Retry-After": "30"},
        )

    # Create job record
    job = Job(
        status=JobStatus.QUEUED,
        progress=0,
        input_type=input_type,
        youtube_url=youtube_url,
        original_filename=file.filename if file else None,
        title=title or "Untitled",
        bpm=bpm,
        webhook_url=webhook_url,
        user_identifier=user_id,
        model_version=settings.MODEL_VERSION,
        warnings=[],
    )

    db.add(job)
    await db.flush()

    logger.info(
        "job_created",
        job_id=str(job.id),
        input_type=input_type.value,
        user=user_id,
    )

    # Save uploaded file
    if file is not None:
        await _save_upload(job.id, file)

    # Dispatch Celery pipeline
    dispatch_pipeline(str(job.id))

    return JobCreateResponse(id=job.id, status="queued")


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Poll job status."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(
        id=job.id,
        status=job.status.value,
        progress=job.progress,
        created_at=job.created_at,
        updated_at=job.updated_at,
        title=job.title,
        error_message=job.error_message,
        compute_time_ms=job.compute_time_ms,
        model_version=job.model_version,
        warnings=job.warnings or [],
    )


@router.get("/{job_id}/result", response_model=JobResultResponse)
async def get_job_result(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get completed job result with hit data and download URLs."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Job is not completed. Current status: {job.status.value}",
        )

    # Build download URLs
    download_urls = {}
    if job.result_musicxml_path:
        download_urls["musicxml"] = f"/api/v1/jobs/{job.id}/download/musicxml"
    if job.result_pdf_path:
        download_urls["pdf"] = f"/api/v1/jobs/{job.id}/download/pdf"

    # Load hits from JSON file produced by the prediction stage
    import json
    storage = get_storage()
    hits = []
    hits_path = storage.get_file_path(str(job.id), "hits.json")
    if storage.file_exists(hits_path):
        try:
            raw_hits = json.loads(storage.read_file(hits_path))
            hits = [
                HitData(time=h["time"], instrument=h["instrument"], velocity=h["velocity"])
                for h in raw_hits
            ]
        except Exception:
            pass  # Graceful — return empty hits if file is corrupt

    return JobResultResponse(
        id=job.id,
        detected_bpm=job.detected_bpm,
        bpm_unreliable=job.bpm_unreliable,
        duration_seconds=job.duration_seconds,
        confidence_score=job.confidence_score,
        warnings=job.warnings or [],
        compute_time_ms=job.compute_time_ms,
        model_version=job.model_version,
        hit_summary=job.hit_summary,
        hits=hits,
        download_urls=download_urls,
    )


@router.get("/{job_id}/download/{format}")
async def download_result(
    job_id: uuid.UUID,
    format: str,
    db: AsyncSession = Depends(get_db),
):
    """Download result file (musicxml or pdf)."""
    if format not in ("musicxml", "pdf"):
        raise HTTPException(status_code=422, detail="Format must be 'musicxml' or 'pdf'")

    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Job is not completed. Current status: {job.status.value}",
        )

    if format == "musicxml":
        file_path = job.result_musicxml_path
        media_type = "application/vnd.recordare.musicxml+xml"
        filename = f"{job.title}.musicxml"
    else:
        file_path = job.result_pdf_path
        media_type = "application/pdf"
        filename = f"{job.title}.pdf"

    storage = get_storage()
    if not file_path or not storage.file_exists(file_path):
        raise HTTPException(status_code=404, detail=f"{format} file not found")

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=filename,
    )


@router.delete("/{job_id}", response_model=JobDeleteResponse)
async def delete_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Cancel a queued/processing job or delete a completed job and its artifacts."""
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    # Cancel Celery task if still running
    if job.status in (JobStatus.QUEUED, JobStatus.PROCESSING, JobStatus.SEPARATING_DRUMS, JobStatus.PREDICTING, JobStatus.TRANSCRIBING):
        if job.celery_task_id:
            celery_app.control.revoke(job.celery_task_id, terminate=True)
            logger.info("job_cancelled", job_id=str(job.id), task_id=job.celery_task_id)

    # Clean up artifacts
    storage = get_storage()
    deleted = storage.delete_job_artifacts(str(job.id))
    if deleted > 0:
        logger.info("job_artifacts_deleted", job_id=str(job.id), files=deleted)

    # Delete from DB
    await db.delete(job)

    return JobDeleteResponse(id=job.id, message="Job deleted successfully")

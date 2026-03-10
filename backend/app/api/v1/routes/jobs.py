import hashlib
import io
import uuid
from pathlib import Path
from typing import Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import structlog
import sys

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

router = APIRouter(prefix="/jobs", tags=["jobs"])
logger = get_logger(__name__)


def _run_pipeline_sync(job_id: str) -> None:
    """Run the full ML pipeline synchronously without Celery (MVP mode).
    
    This executes all pipeline stages in sequence within the API process.
    Used when USE_CELERY=false for rapid local development.
    """
    import traceback
    import time
    
    # Global exception catch to prevent silent hangs
    try:
        logger.info("pipeline_sync_started", job_id=job_id)
        
        try:
            from app.worker import ingest_audio, separate_drums, predict_hits, transcribe_and_export
            logger.info("worker_imports_successful", job_id=job_id)
        except Exception as import_error:
            print(f"FATAL THREAD CRASH - Import failed: {repr(import_error)}", flush=True)
            logger.error("worker_import_failed", job_id=job_id, error=str(import_error))
            raise
        
        start_time = time.monotonic()
        
        logger.info(
            "PIPELINE START",
            job_id=job_id,
            mode="mvp_sync",
        )
        
        logger.info(
            "[1/4] INGESTING AUDIO",
            job_id=job_id,
            stage="ingest",
            progress="5%",
        )
        ingest_audio(job_id)
        
        logger.info(
            "[2/4] SEPARATING DRUMS",
            job_id=job_id,
            stage="separation",
            progress="20%",
        )
        separate_drums(job_id)
        
        logger.info(
            "[3/4] DETECTING HITS",
            job_id=job_id,
            stage="prediction",
            progress="55%",
        )
        predict_hits(job_id)
        
        logger.info(
            "[4/4] GENERATING SHEET MUSIC",
            job_id=job_id,
            stage="transcription",
            progress="80%",
        )
        transcribe_and_export(job_id)
        
        elapsed_s = int(time.monotonic() - start_time)
        logger.info(
            "PIPELINE COMPLETE",
            job_id=job_id,
            total_duration_s=elapsed_s,
            progress="100%",
        )
        
    except Exception as e:
        print(f"FATAL THREAD CRASH: {repr(e)}", flush=True)
        print(f"TRACEBACK: {traceback.format_exc()}", flush=True)
        try:
            elapsed_s = int(time.monotonic() - start_time) if 'start_time' in locals() else 0
            logger.error(
                "PIPELINE FAILED",
                job_id=job_id,
                error=str(e),
                error_type=type(e).__name__,
                duration_s=elapsed_s,
            )
        except Exception as log_error:
            print(f"FATAL: Could not log error: {repr(log_error)}", flush=True)


def _get_user_identifier(request: Request) -> str:
    """Extract user identifier from request (IP-based for now)."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _extract_title_from_filename(filename: str) -> str:
    """Extract a human-readable title from a filename.
    
    Strips extension, replaces dashes/underscores with spaces, and applies title casing.
    Example: 'despiertate-nena-corto.mp3' -> 'Despiertate Nena Corto'
    """
    if not filename:
        return "Untitled"
    
    name = Path(filename).stem
    name = name.replace("-", " ").replace("_", " ")
    return name.title()


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


async def _save_upload(
    job_id: uuid.UUID, file: UploadFile, request: Request
) -> Tuple[str, str]:
    """Save uploaded file via storage backend using chunked streaming.

    Validates size via Content-Length header before reading, then enforces
    the limit during streaming so the full file is never buffered in RAM.
    Returns (saved_path, sha256_hex).
    """
    storage = get_storage()
    filename = file.filename or "upload.audio"
    max_bytes = settings.max_file_size_bytes

    # Fast path: reject immediately if Content-Length declares an oversized file
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError:
            declared_size = None
        if declared_size is not None and declared_size > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum size of {settings.MAX_FILE_SIZE_MB} MB.",
            )

    # Stream-read in 64 KB chunks; accumulate SHA-256 hash and byte counter
    chunk_size = 64 * 1024
    buffer = io.BytesIO()
    hasher = hashlib.sha256()
    total_bytes = 0

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum size of {settings.MAX_FILE_SIZE_MB} MB.",
            )
        hasher.update(chunk)
        buffer.write(chunk)

    content_hash = hasher.hexdigest()
    saved_path = await storage.save_file_async(str(job_id), filename, buffer.getvalue())
    return saved_path, content_hash


@router.post("", response_model=JobCreateResponse, status_code=201)
async def create_job(
    request: Request,
    background_tasks: BackgroundTasks,
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
    
    # Extract title from filename if no title provided and file is uploaded
    if not title or title == "Untitled":
        if file is not None and file.filename:
            title = _extract_title_from_filename(file.filename)
        else:
            title = "Untitled"

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
        title=title,
        bpm=bpm,
        webhook_url=webhook_url,
        user_identifier=user_id,
        model_version=settings.MODEL_VERSION,
        warnings=[],
    )

    db.add(job)
    await db.flush()

    # Get correlation ID from structlog context if available
    request_id = structlog.contextvars.get_contextvars().get("request_id", "unknown")
    
    logger.info(
        "job_created",
        job_id=str(job.id),
        input_type=input_type.value,
        user=user_id,
        filename=file.filename if file else youtube_url,
    )

    # Idempotency check for file uploads — return existing job if same hash is already active
    if file is not None:
        # Peek at the hash without saving yet by reading into a temp buffer
        # The full read + hash happens inside _save_upload via a placeholder job id.
        # We save under a temp id, check for collision, then either keep or discard.
        temp_job_id = uuid.uuid4()
        _, content_hash = await _save_upload(temp_job_id, file, request)

        # Check if this user already has a non-terminal job with the same file
        existing = await db.execute(
            select(Job).where(
                Job.user_identifier == user_id,
                Job.content_hash == content_hash,
                Job.status.notin_([
                    JobStatus.COMPLETED, JobStatus.FAILED,
                    JobStatus.CANCELLED, JobStatus.CANCELLING,
                ]),
            )
        )
        existing_job = existing.scalar_one_or_none()
        if existing_job is not None:
            # Refresh to avoid lazy loading issues
            await db.refresh(existing_job)
            logger.info(
                "duplicate_upload_returning_existing",
                job_id=str(existing_job.id),
                content_hash=content_hash[:16],
                existing_status=existing_job.status.value,
            )
            await db.rollback()
            return JobCreateResponse(id=existing_job.id, status=existing_job.status.value)

        # No duplicate — rename temp artifact dir to the real job id and persist hash
        from app.storage.backend import LocalStorageBackend, S3StorageBackend
        storage = get_storage()
        if isinstance(storage, LocalStorageBackend):
            import shutil
            temp_dir = Path(storage.get_job_dir(str(temp_job_id)))
            real_dir = Path(storage.base_dir) / str(job.id)
            if temp_dir.exists():
                shutil.move(str(temp_dir), str(real_dir))
        job.content_hash = content_hash
    
    job_id_for_response = job.id
    job_id_str = str(job.id)

    # Commit the transaction BEFORE dispatching background task
    # This ensures the job exists in the DB when the background task runs
    await db.commit()
    
    # Dispatch pipeline: Celery (production) or BackgroundTasks (MVP mode)
    if settings.USE_CELERY:
        from app.worker import dispatch_pipeline
        dispatch_pipeline(job_id_str)
        logger.info(
            "job_dispatched_to_celery",
            job_id=job_id_str,
            mode="celery",
        )
    else:
        background_tasks.add_task(_run_pipeline_sync, job_id_str)
        logger.info(
            "job_dispatched_to_background_task",
            job_id=job_id_str,
            mode="mvp_sync",
        )

    return JobCreateResponse(id=job_id_for_response, status="queued")


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

    # For S3 backend: redirect to a pre-signed URL so the API doesn't proxy bytes
    from app.storage.backend import S3StorageBackend
    if isinstance(storage, S3StorageBackend):
        artifact_filename = Path(file_path).name
        presigned = storage.generate_presigned_url(str(job_id), artifact_filename, expires=900)
        if presigned:
            return RedirectResponse(url=presigned, status_code=302)

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

    ACTIVE_STATUSES = (
        JobStatus.QUEUED,
        JobStatus.PROCESSING,
        JobStatus.SEPARATING_DRUMS,
        JobStatus.PREDICTING,
        JobStatus.TRANSCRIBING,
    )

    # Transition to CANCELLING before revoking so the worker can detect and
    # self-terminate gracefully rather than writing to a deleted DB row.
    if job.status in ACTIVE_STATUSES:
        job.status = JobStatus.CANCELLING
        await db.flush()
        if settings.USE_CELERY and job.celery_task_id:
            from app.worker import celery_app
            celery_app.control.revoke(job.celery_task_id, terminate=False)
            logger.info("job_cancelling", job_id=str(job.id), task_id=job.celery_task_id)

    # Clean up artifacts
    storage = get_storage()
    deleted = storage.delete_job_artifacts(str(job.id))
    if deleted > 0:
        logger.info("job_artifacts_deleted", job_id=str(job.id), files=deleted)

    # Delete from DB
    await db.delete(job)

    return JobDeleteResponse(id=job.id, message="Job deleted successfully")

import gc
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psutil
from celery import Celery, chain
from celery.signals import worker_init
from sqlalchemy import select

from app.core.config import settings
from app.core.telemetry import (
    INFERENCE_LATENCY,
    JOBS_TOTAL,
    JOBS_FAILED_TOTAL,
    ACTIVE_JOBS_GAUGE,
    AUDIO_DURATION_PROCESSED,
)

celery_app = Celery(
    "drumscribe",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Queue routing configuration
celery_app.conf.task_routes = {
    "app.worker.ingest_audio": {"queue": "io"},
    "app.worker.separate_drums": {"queue": "heavy-compute"},
    "app.worker.predict_hits": {"queue": "heavy-compute"},
    "app.worker.transcribe_and_export": {"queue": "default"},
    "app.worker.cleanup_old_artifacts": {"queue": "default"},
}

celery_app.conf.task_default_queue = "default"

# Task reliability settings
celery_app.conf.task_acks_late = True
celery_app.conf.task_reject_on_worker_lost = True
celery_app.conf.worker_prefetch_multiplier = 1
celery_app.conf.broker_connection_retry_on_startup = True

# Serialization
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]

# Periodic tasks (Celery Beat)
celery_app.conf.beat_schedule = {
    "cleanup-old-artifacts": {
        "task": "app.worker.cleanup_old_artifacts",
        "schedule": 3600.0,  # Every hour
    },
    "expire-stale-jobs": {
        "task": "app.worker.expire_stale_jobs",
        "schedule": 300.0,  # Every 5 minutes
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log_memory_usage(logger, stage: str) -> None:
    """Log current memory usage for performance monitoring.
    
    Args:
        logger: Structlog logger instance.
        stage: Description of current pipeline stage.
    """
    try:
        process = psutil.Process(os.getpid())
        mem_info = process.memory_info()
        logger.debug(
            stage,
            rss_mb=round(mem_info.rss / 1024 / 1024, 2),
            vms_mb=round(mem_info.vms / 1024 / 1024, 2),
        )
    except Exception as e:
        logger.warning("memory_logging_failed", error=str(e))


def _update_job(job_id: str, **kwargs) -> None:
    """Update job fields in the database (sync, for Celery workers)."""
    from app.core.database_sync import get_sync_db
    from app.models.job import Job

    db = get_sync_db()
    try:
        job = db.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none()
        if job is None:
            return
        for key, value in kwargs.items():
            setattr(job, key, value)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _get_job_field(job_id: str, field: str):
    """Read a single field from a job record."""
    from app.core.database_sync import get_sync_db
    from app.models.job import Job

    db = get_sync_db()
    try:
        job = db.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none()
        if job is None:
            return None
        return getattr(job, field, None)
    finally:
        db.close()


def _publish_status(job_id: str, status: str, progress: int = 0) -> None:
    """Publish job status update via event bus.
    
    Routes to Redis Pub/Sub (full mode) or asyncio.Queue (MVP mode).
    """
    from app.core.events import publish_job_event_sync
    publish_job_event_sync(job_id, status, progress)


def _fail_job(job_id: str, error_message: str, stage: str) -> None:
    """Mark a job as failed with error details."""
    _update_job(
        job_id,
        status="failed",
        error_message=error_message,
    )
    JOBS_FAILED_TOTAL.labels(failure_stage=stage).inc()
    JOBS_TOTAL.labels(status="failed").inc()
    ACTIVE_JOBS_GAUGE.dec()


class JobCancelledError(Exception):
    """Raised when a task detects the job has been set to CANCELLING."""


def _check_cancellation(job_id: str) -> None:
    """Read current job status and raise JobCancelledError if CANCELLING.

    Call this at the start of each pipeline task so that a revoked job
    terminates before doing any expensive work.
    """
    status = _get_job_field(job_id, "status")
    if status in ("cancelling", "cancelled"):
        _update_job(job_id, status="cancelled")
        ACTIVE_JOBS_GAUGE.dec()
        raise JobCancelledError(f"Job {job_id} was cancelled before task started")


def dispatch_pipeline(job_id: str) -> None:
    """Dispatch the full transcription pipeline as a Celery chain."""
    pipeline = chain(
        ingest_audio.s(job_id).set(queue="io"),
        separate_drums.s().set(queue="heavy-compute"),
        predict_hits.s().set(queue="heavy-compute"),
        transcribe_and_export.s().set(queue="default"),
    )
    result = pipeline.apply_async()

    # Store the root task ID for cancellation support
    _update_job(job_id, celery_task_id=result.id)


# ---------------------------------------------------------------------------
# Worker init signal — preload models at startup (Phase 4 will fill this in)
# ---------------------------------------------------------------------------

@worker_init.connect
def on_worker_init(**kwargs):
    """Called once when a Celery worker process starts — preload ML models."""
    import structlog
    logger = structlog.get_logger("worker_init")
    logger.info("worker_starting", queues=kwargs.get("sender", ""))

    if os.getenv("WORKER_MODE", "false").lower() != "true":
        logger.info("worker_mode_disabled_skipping_model_preload")
        return

    from app.ml.registry import preload_models
    preload_models()


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@celery_app.task(name="app.worker.ingest_audio")
def ingest_audio(job_id: str) -> str:
    """Audio ingestion — validate uploaded file or download from YouTube."""
    import structlog
    logger = structlog.get_logger("task.ingest_audio")
    start = time.monotonic()

    try:
        _check_cancellation(job_id)
        ACTIVE_JOBS_GAUGE.inc()
        _update_job(job_id, status="processing", progress=5)
        _publish_status(job_id, "processing", 5)
        logger.info("ingest_start", job_id=job_id)

        from app.storage.backend import get_storage
        storage = get_storage()

        input_type = _get_job_field(job_id, "input_type")
        job_dir = storage.get_job_dir(job_id)

        if input_type == "youtube":
            youtube_url = _get_job_field(job_id, "youtube_url")
            logger.info("youtube_download_start", job_id=job_id, url=youtube_url)
            from app.services.audio_ingestion import download_youtube_audio
            audio_path = download_youtube_audio(youtube_url, job_dir)
            _update_job(job_id, original_filename=Path(audio_path).name)
        else:
            # File already saved by the API endpoint during upload
            files = list(Path(job_dir).glob("*"))
            audio_files = [f for f in files if f.suffix.lower() in (".wav", ".mp3", ".flac", ".ogg")]
            if not audio_files:
                raise FileNotFoundError(f"No audio file found in {job_dir}")
            audio_path = str(audio_files[0])

        # Signal health check — returns metadata to avoid re-loading downstream
        from app.services.audio_ingestion import validate_audio_signal
        audio_meta = validate_audio_signal(audio_path)
        _update_job(job_id, duration_seconds=audio_meta.get("duration_seconds"))

        elapsed = int((time.monotonic() - start) * 1000)
        INFERENCE_LATENCY.labels(stage="ingest").observe(elapsed / 1000)
        _update_job(job_id, progress=15)
        _publish_status(job_id, "processing", 15)
        logger.info("ingest_complete", job_id=job_id, elapsed_ms=elapsed)

    except JobCancelledError:
        raise
    except Exception as e:
        logger.error("ingest_failed", job_id=job_id, error=str(e))
        _fail_job(job_id, f"Audio ingestion failed: {e}", "ingest")
        raise

    return job_id


@celery_app.task(
    name="app.worker.separate_drums",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    acks_late=True,
    reject_on_worker_lost=True,
)
def separate_drums(self, job_id: str) -> str:
    """Demucs drum separation (heavy-compute queue)."""
    import structlog
    logger = structlog.get_logger("task.separate_drums")
    start = time.monotonic()

    try:
        _check_cancellation(job_id)
        from app.storage.backend import get_storage
        storage = get_storage()

        _update_job(job_id, status="separating_drums", progress=20)
        _publish_status(job_id, "separating_drums", 20)
        logger.info("separation_start", job_id=job_id)
        _log_memory_usage(logger, "separator_memory_before")

        job_dir = storage.get_job_dir(job_id)
        drums_path = Path(storage.get_file_path(job_id, "drums.wav"))

        # Skip if already separated (idempotency)
        if drums_path.exists() and drums_path.stat().st_size > 0:
            logger.info("separation_skipped_existing", job_id=job_id)
        else:
            from app.ml.engine import run_drum_separation
            audio_files = [f for f in Path(job_dir).glob("*") if f.suffix.lower() in (".wav", ".mp3", ".flac", ".ogg") and f.name != "drums.wav"]
            if not audio_files:
                raise FileNotFoundError(f"No source audio in {job_dir}")
            
            logger.info("starting_separator_separation", input_file=str(audio_files[0]))
            run_drum_separation(str(audio_files[0]), str(drums_path))
            _log_memory_usage(logger, "separator_separation_complete_memory")

        gc.collect()
        _log_memory_usage(logger, "separator_cleanup_memory")

        elapsed = int((time.monotonic() - start) * 1000)
        INFERENCE_LATENCY.labels(stage="separation").observe(elapsed / 1000)
        _update_job(job_id, progress=50)
        _publish_status(job_id, "separating_drums", 50)
        logger.info("separation_complete", job_id=job_id, elapsed_ms=elapsed)

    except JobCancelledError:
        raise
    except Exception as e:
        logger.error("separation_failed", job_id=job_id, error=str(e))
        _fail_job(job_id, f"Drum separation failed: {e}", "separation")
        raise

    return job_id


@celery_app.task(
    name="app.worker.predict_hits",
    bind=True,
    max_retries=5,
    default_retry_delay=30,
    acks_late=True,
    reject_on_worker_lost=True,
)
def predict_hits(self, job_id: str) -> str:
    """CNN drum hit prediction (heavy-compute queue)."""
    import structlog
    logger = structlog.get_logger("task.predict_hits")
    start = time.monotonic()

    try:
        _check_cancellation(job_id)
        from app.storage.backend import get_storage
        storage = get_storage()

        _update_job(job_id, status="predicting", progress=55)
        _publish_status(job_id, "predicting", 55)
        logger.info("prediction_start", job_id=job_id)
        _log_memory_usage(logger, "cnn_memory_before")

        drums_path = storage.get_file_path(job_id, "drums.wav")

        if not storage.file_exists(drums_path):
            raise FileNotFoundError(f"Drums file not found: {drums_path}")

        user_bpm = _get_job_field(job_id, "bpm")
        if user_bpm:
            logger.info("using_user_supplied_bpm", bpm=user_bpm)

        from app.ml.engine import run_prediction
        from app.ml.guardrails import apply_ml_guardrails
        from app.schemas.ml_contracts import PredictionResult
        import json
        
        # Phase 3: Idempotency check - skip expensive GPU inference if hits.json exists
        hits_path = storage.get_file_path(job_id, "hits.json")
        result = None
        
        if storage.file_exists(hits_path):
            logger.info(
                "idempotency_check_found_existing_hits",
                job_id=job_id,
                hits_path=hits_path
            )
            try:
                # Attempt to load and validate existing hits.json
                hits_json = storage.read_file(hits_path)
                existing_data = json.loads(hits_json)
                
                # Validate against Pydantic schema (ensures data integrity)
                validated = PredictionResult.model_validate(existing_data)
                
                # Convert back to dict for compatibility with rest of pipeline
                result = validated.model_dump()
                
                logger.info(
                    "prediction_skipped_existing",
                    job_id=job_id,
                    schema_version=result.get("schema_version"),
                    model_version=result.get("model_version"),
                    total_hits=len(result.get("hits", [])),
                    message="Reusing existing prediction results (idempotent retry)"
                )
            except (json.JSONDecodeError, ValueError, Exception) as e:
                # Corrupted or invalid hits.json - fall back to re-running prediction
                logger.warning(
                    "idempotency_validation_failed",
                    job_id=job_id,
                    error=str(e),
                    message="Existing hits.json is corrupted or invalid, re-running prediction"
                )
                result = None
        
        # Run prediction if no valid cached result exists
        if result is None:
            # Use Modal serverless GPU if enabled, otherwise run locally
            if settings.USE_MODAL:
                logger.info("starting_modal_inference", drums_path=drums_path)
                from app.ml.modal_client import get_modal_client
                
                modal_client = get_modal_client()
                result = modal_client.process_audio(
                    audio_path=drums_path,
                    user_bpm=user_bpm,
                )
                # Modal already applies guardrails internally
            else:
                logger.info("starting_local_inference", drums_path=drums_path)
                result = run_prediction(drums_path, user_bpm=user_bpm)
                
                # Apply ML guardrails before saving/transcription
                # This prevents catastrophic failures from BPM hallucinations, 
                # impossible polyphony, and low-confidence noise
                logger.info("applying_ml_guardrails")
                result = apply_ml_guardrails(result)
        
        _log_memory_usage(logger, "cnn_prediction_complete_memory")
        
        # Log prediction results
        total_hits = sum(result.get("hit_summary", {}).values())
        logger.info(
            "cnn_prediction_results",
            total_hits=total_hits,
            detected_bpm=result.get("detected_bpm"),
            bpm_unreliable=result.get("bpm_unreliable", False),
            confidence_score=result.get("confidence_score"),
        )

        # Save prediction results to job (including schema/model versions)
        warnings = []
        if result.get("bpm_unreliable", False):
            warnings.append("bpm_unreliable")
        if result.get("confidence_score", 1.0) < settings.LOW_CONFIDENCE_THRESHOLD:
            warnings.append("low_confidence")

        _update_job(
            job_id,
            detected_bpm=result.get("detected_bpm"),
            bpm_unreliable=result.get("bpm_unreliable", False),
            duration_seconds=result.get("duration_seconds"),
            confidence_score=result.get("confidence_score"),
            hit_summary=result.get("hit_summary"),
            warnings=warnings,
            progress=75,
        )

        # Phase 3: Save complete prediction result with schema versioning
        # This includes schema_version and model_version for future compatibility
        hits_data = json.dumps(result, indent=2).encode()
        storage.save_file(job_id, "hits.json", hits_data)
        
        logger.info(
            "prediction_saved_with_versioning",
            schema_version=result.get("schema_version"),
            model_version=result.get("model_version")
        )

        gc.collect()
        _log_memory_usage(logger, "cnn_cleanup_memory")

        elapsed = int((time.monotonic() - start) * 1000)
        INFERENCE_LATENCY.labels(stage="prediction").observe(elapsed / 1000)
        if result.get("duration_seconds"):
            AUDIO_DURATION_PROCESSED.inc(result["duration_seconds"])
        _publish_status(job_id, "predicting", 75)
        logger.info("prediction_complete", job_id=job_id, elapsed_ms=elapsed)

    except JobCancelledError:
        raise
    except Exception as e:
        logger.error("prediction_failed", job_id=job_id, error=str(e))
        _fail_job(job_id, f"Prediction failed: {e}", "prediction")
        raise

    return job_id


@celery_app.task(name="app.worker.transcribe_and_export")
def transcribe_and_export(job_id: str) -> str:
    """Transcription (symusic) + MusicXML/PDF export."""
    import structlog
    logger = structlog.get_logger("task.transcribe_export")
    start = time.monotonic()

    try:
        _check_cancellation(job_id)
        from app.storage.backend import get_storage
        storage = get_storage()

        _update_job(job_id, status="transcribing", progress=80)
        _publish_status(job_id, "transcribing", 80)
        logger.info("transcription_start", job_id=job_id)
        logger.info("starting_quantization_and_export")

        from app.services.transcription import build_sheet_music
        from app.services.export import export_musicxml, export_pdf

        # Load prediction data
        import json
        hits_path = storage.get_file_path(job_id, "hits.json")

        if not storage.file_exists(hits_path):
            raise FileNotFoundError(f"Hits data not found: {hits_path}")

        prediction_data = json.loads(storage.read_file(hits_path))
        hits = prediction_data.get("hits", []) if isinstance(prediction_data, dict) else prediction_data
        detected_bpm = _get_job_field(job_id, "detected_bpm") or 120
        title = _get_job_field(job_id, "title") or "Untitled"
        
        logger.info("building_sheet_music", total_hits=len(hits), bpm=detected_bpm, title=title)

        # Build sheet music using symusic
        symusic_score = build_sheet_music(hits, detected_bpm, title)
        logger.info("sheet_music_built")

        # Export MusicXML
        musicxml_path = storage.get_file_path(job_id, "sheet_music.musicxml")
        export_musicxml(symusic_score, musicxml_path)
        logger.info("musicxml_exported", path=musicxml_path)

        # Export PDF (may fail if MuseScore not installed — graceful degradation)
        pdf_path = storage.get_file_path(job_id, "sheet_music.pdf")
        pdf_ok = export_pdf(musicxml_path, pdf_path)
        if pdf_ok:
            logger.info("pdf_export_successful", path=pdf_path)
        else:
            logger.warning("pdf_export_skipped_or_failed", backend=settings.PDF_BACKEND)

        elapsed = int((time.monotonic() - start) * 1000)

        # Calculate total compute time from job creation
        from app.core.database_sync import get_sync_db
        from app.models.job import Job
        db = get_sync_db()
        try:
            job = db.execute(select(Job).where(Job.id == job_id)).scalar_one_or_none()
            total_ms = None
            if job and job.created_at:
                total_ms = int((datetime.now(timezone.utc) - job.created_at).total_seconds() * 1000)
        finally:
            db.close()

        update_fields = dict(
            status="completed",
            progress=100,
            result_musicxml_path=musicxml_path,
            compute_time_ms=total_ms,
        )
        if pdf_ok:
            update_fields["result_pdf_path"] = pdf_path

        _update_job(job_id, **update_fields)

        del symusic_score, hits
        gc.collect()

        INFERENCE_LATENCY.labels(stage="transcription").observe(elapsed / 1000)
        JOBS_TOTAL.labels(status="completed").inc()
        ACTIVE_JOBS_GAUGE.dec()
        _publish_status(job_id, "completed", 100)
        logger.info("transcription_complete", job_id=job_id, elapsed_ms=elapsed)

        # Fire webhook if configured
        webhook_url = _get_job_field(job_id, "webhook_url")
        if webhook_url:
            from app.services.webhook import fire_webhook
            fire_webhook(job_id, webhook_url)

    except JobCancelledError:
        raise
    except Exception as e:
        logger.error("transcription_failed", job_id=job_id, error=str(e))
        _fail_job(job_id, f"Transcription/export failed: {e}", "transcription")
        raise

    return job_id


@celery_app.task(name="app.worker.expire_stale_jobs")
def expire_stale_jobs() -> dict:
    """Mark jobs stuck in active states for >30 minutes as FAILED."""
    import structlog
    logger = structlog.get_logger("task.expire_stale_jobs")

    from app.core.database_sync import get_sync_db
    from app.models.job import Job, JobStatus
    from sqlalchemy import update

    ACTIVE_STATUSES = [
        JobStatus.QUEUED,
        JobStatus.PROCESSING,
        JobStatus.SEPARATING_DRUMS,
        JobStatus.PREDICTING,
        JobStatus.TRANSCRIBING,
        JobStatus.CANCELLING,
    ]
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
    expired = 0

    db = get_sync_db()
    try:
        result = db.execute(
            update(Job)
            .where(Job.status.in_(ACTIVE_STATUSES))
            .where(Job.created_at < cutoff)
            .values(
                status=JobStatus.FAILED,
                error_message="Job timed out after 30 minutes without completing.",
            )
            .returning(Job.id)
        )
        expired = len(result.fetchall())
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error("expire_stale_jobs_failed", error=str(e))
    finally:
        db.close()

    if expired:
        logger.info("stale_jobs_expired", count=expired)
    return {"expired": expired}


@celery_app.task(name="app.worker.cleanup_old_artifacts")
def cleanup_old_artifacts() -> dict:
    """Periodic cleanup of job artifacts older than ARTIFACT_TTL_HOURS."""
    import structlog
    logger = structlog.get_logger("task.cleanup")

    from app.core.database_sync import get_sync_db
    from app.models.job import Job

    from app.storage.backend import get_storage
    storage = get_storage()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.ARTIFACT_TTL_HOURS)
    cleaned = 0

    db = get_sync_db()
    try:
        old_jobs = db.execute(
            select(Job).where(Job.created_at < cutoff)
        ).scalars().all()

        for job in old_jobs:
            count = storage.delete_job_artifacts(str(job.id))
            if count > 0:
                cleaned += 1
                logger.info("artifact_cleaned", job_id=str(job.id))
    finally:
        db.close()

    logger.info("cleanup_complete", cleaned=cleaned)
    return {"cleaned": cleaned}

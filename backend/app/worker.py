import gc
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
    "app.worker.separate_drums": {"queue": "heavy-compute"},
    "app.worker.predict_hits": {"queue": "heavy-compute"},
    "app.worker.ingest_audio": {"queue": "default"},
    "app.worker.transcribe_and_export": {"queue": "default"},
    "app.worker.cleanup_old_artifacts": {"queue": "default"},
}

celery_app.conf.task_default_queue = "default"

# Task reliability settings
celery_app.conf.task_acks_late = True
celery_app.conf.task_reject_on_worker_lost = True
celery_app.conf.worker_prefetch_multiplier = 1

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
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def dispatch_pipeline(job_id: str) -> None:
    """Dispatch the full transcription pipeline as a Celery chain."""
    pipeline = chain(
        ingest_audio.s(job_id),
        separate_drums.s(),
        predict_hits.s(),
        transcribe_and_export.s(),
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
        ACTIVE_JOBS_GAUGE.inc()
        _update_job(job_id, status="processing", progress=5)
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
        logger.info("ingest_complete", job_id=job_id, elapsed_ms=elapsed)

    except Exception as e:
        logger.error("ingest_failed", job_id=job_id, error=str(e))
        _fail_job(job_id, f"Audio ingestion failed: {e}", "ingest")
        raise

    return job_id


@celery_app.task(
    name="app.worker.separate_drums",
    bind=True,
    max_retries=1,
    acks_late=True,
    reject_on_worker_lost=True,
)
def separate_drums(self, job_id: str) -> str:
    """Demucs drum separation (heavy-compute queue)."""
    import structlog
    logger = structlog.get_logger("task.separate_drums")
    start = time.monotonic()

    try:
        from app.storage.backend import get_storage
        storage = get_storage()

        _update_job(job_id, status="separating_drums", progress=20)
        logger.info("separation_start", job_id=job_id)

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
            run_drum_separation(str(audio_files[0]), str(drums_path))

        gc.collect()

        elapsed = int((time.monotonic() - start) * 1000)
        INFERENCE_LATENCY.labels(stage="separation").observe(elapsed / 1000)
        _update_job(job_id, progress=50)
        logger.info("separation_complete", job_id=job_id, elapsed_ms=elapsed)

    except Exception as e:
        logger.error("separation_failed", job_id=job_id, error=str(e))
        _fail_job(job_id, f"Drum separation failed: {e}", "separation")
        raise

    return job_id


@celery_app.task(
    name="app.worker.predict_hits",
    bind=True,
    max_retries=1,
    acks_late=True,
    reject_on_worker_lost=True,
)
def predict_hits(self, job_id: str) -> str:
    """CNN drum hit prediction (heavy-compute queue)."""
    import structlog
    logger = structlog.get_logger("task.predict_hits")
    start = time.monotonic()

    try:
        from app.storage.backend import get_storage
        storage = get_storage()

        _update_job(job_id, status="predicting", progress=55)
        logger.info("prediction_start", job_id=job_id)

        drums_path = storage.get_file_path(job_id, "drums.wav")

        if not storage.file_exists(drums_path):
            raise FileNotFoundError(f"Drums file not found: {drums_path}")

        user_bpm = _get_job_field(job_id, "bpm")

        from app.ml.engine import run_prediction
        result = run_prediction(drums_path, user_bpm=user_bpm)

        # Save prediction results to job
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

        # Save raw hits data as JSON for the result endpoint
        import json
        hits_data = json.dumps(result.get("hits", [])).encode()
        storage.save_file(job_id, "hits.json", hits_data)

        gc.collect()

        elapsed = int((time.monotonic() - start) * 1000)
        INFERENCE_LATENCY.labels(stage="prediction").observe(elapsed / 1000)
        if result.get("duration_seconds"):
            AUDIO_DURATION_PROCESSED.inc(result["duration_seconds"])
        logger.info("prediction_complete", job_id=job_id, elapsed_ms=elapsed)

    except Exception as e:
        logger.error("prediction_failed", job_id=job_id, error=str(e))
        _fail_job(job_id, f"Prediction failed: {e}", "prediction")
        raise

    return job_id


@celery_app.task(name="app.worker.transcribe_and_export")
def transcribe_and_export(job_id: str) -> str:
    """Transcription (music21) + MusicXML/PDF export."""
    import structlog
    logger = structlog.get_logger("task.transcribe_export")
    start = time.monotonic()

    try:
        from app.storage.backend import get_storage
        storage = get_storage()

        _update_job(job_id, status="transcribing", progress=80)
        logger.info("transcription_start", job_id=job_id)

        from app.services.transcription import build_sheet_music
        from app.services.export import export_musicxml, export_pdf

        # Load prediction data
        import json
        hits_path = storage.get_file_path(job_id, "hits.json")

        if not storage.file_exists(hits_path):
            raise FileNotFoundError(f"Hits data not found: {hits_path}")

        hits = json.loads(storage.read_file(hits_path))
        detected_bpm = _get_job_field(job_id, "detected_bpm") or 120
        title = _get_job_field(job_id, "title") or "Untitled"

        # Build sheet music
        music21_stream = build_sheet_music(hits, detected_bpm, title)

        # Export MusicXML
        musicxml_path = storage.get_file_path(job_id, "sheet_music.musicxml")
        export_musicxml(music21_stream, musicxml_path)

        # Export PDF (may fail if MuseScore not installed — graceful degradation)
        pdf_path = storage.get_file_path(job_id, "sheet_music.pdf")
        pdf_ok = export_pdf(musicxml_path, pdf_path)

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

        del music21_stream, hits
        gc.collect()

        INFERENCE_LATENCY.labels(stage="transcription").observe(elapsed / 1000)
        JOBS_TOTAL.labels(status="completed").inc()
        ACTIVE_JOBS_GAUGE.dec()
        logger.info("transcription_complete", job_id=job_id, elapsed_ms=elapsed)

        # Fire webhook if configured
        webhook_url = _get_job_field(job_id, "webhook_url")
        if webhook_url:
            from app.services.webhook import fire_webhook
            fire_webhook(job_id, webhook_url)

    except Exception as e:
        logger.error("transcription_failed", job_id=job_id, error=str(e))
        _fail_job(job_id, f"Transcription/export failed: {e}", "transcription")
        raise

    return job_id


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

#!/usr/bin/env python3
"""
Seed the database with test jobs for local development.

Usage:
    python scripts/seed_test_data.py

Requires a running PostgreSQL instance (uses DATABASE_URL from .env).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.job import Job, JobStatus, InputType
from app.core.database import Base

# Sync engine for seeding
sync_url = settings.DATABASE_URL.replace("postgresql+asyncpg", "postgresql+psycopg2")
engine = create_engine(sync_url)
SessionFactory = sessionmaker(bind=engine)

SEED_JOBS = [
    {
        "status": JobStatus.COMPLETED,
        "progress": 100,
        "input_type": InputType.UPLOAD,
        "original_filename": "rock_beat.wav",
        "title": "Rock Beat Demo",
        "detected_bpm": 120,
        "duration_seconds": 30.5,
        "confidence_score": 0.87,
        "hit_summary": {"kick": 16, "snare": 16, "hihat_closed": 32},
        "warnings": [],
        "compute_time_ms": 45000,
        "model_version": settings.MODEL_VERSION,
        "user_identifier": "127.0.0.1",
    },
    {
        "status": JobStatus.COMPLETED,
        "progress": 100,
        "input_type": InputType.YOUTUBE,
        "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "title": "YouTube Import Test",
        "detected_bpm": 113,
        "bpm_unreliable": True,
        "duration_seconds": 212.0,
        "confidence_score": 0.62,
        "hit_summary": {"kick": 120, "snare": 95, "hihat_closed": 210, "crash": 8},
        "warnings": ["bpm_unreliable"],
        "compute_time_ms": 180000,
        "model_version": settings.MODEL_VERSION,
        "user_identifier": "127.0.0.1",
    },
    {
        "status": JobStatus.FAILED,
        "progress": 20,
        "input_type": InputType.UPLOAD,
        "original_filename": "silence.wav",
        "title": "Failed Job (Silent Audio)",
        "error_message": "Audio appears silent (RMS=0.000012, threshold=0.001)",
        "user_identifier": "127.0.0.1",
    },
    {
        "status": JobStatus.QUEUED,
        "progress": 0,
        "input_type": InputType.UPLOAD,
        "original_filename": "jazz_groove.flac",
        "title": "Queued Job",
        "bpm": 140,
        "user_identifier": "192.168.1.100",
    },
]


def seed():
    Base.metadata.create_all(engine)
    db: Session = SessionFactory()
    try:
        for job_data in SEED_JOBS:
            job = Job(**job_data)
            db.add(job)
            print(f"  + {job.title} [{job.status.value}]")
        db.commit()
        print(f"\nSeeded {len(SEED_JOBS)} test jobs.")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("Seeding test data...\n")
    seed()

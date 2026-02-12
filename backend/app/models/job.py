import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    Integer,
    String,
    Boolean,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSON

from app.core.database import Base


class JobStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    SEPARATING_DRUMS = "separating_drums"
    PREDICTING = "predicting"
    TRANSCRIBING = "transcribing"
    COMPLETED = "completed"
    FAILED = "failed"


class InputType(str, enum.Enum):
    UPLOAD = "upload"
    YOUTUBE = "youtube"


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status = Column(
        Enum(JobStatus, name="job_status"),
        nullable=False,
        default=JobStatus.QUEUED,
        index=True,
    )
    progress = Column(Integer, nullable=False, default=0)

    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    # Input
    input_type = Column(Enum(InputType, name="input_type"), nullable=False)
    youtube_url = Column(String(512), nullable=True)
    original_filename = Column(String(255), nullable=True)
    title = Column(String(255), nullable=False, default="Untitled")

    # BPM
    bpm = Column(Integer, nullable=True)  # User-supplied
    detected_bpm = Column(Integer, nullable=True)
    bpm_unreliable = Column(Boolean, nullable=False, default=False)

    # Audio metadata
    duration_seconds = Column(Float, nullable=True)

    # Error
    error_message = Column(Text, nullable=True)

    # Result paths
    result_musicxml_path = Column(String(512), nullable=True)
    result_pdf_path = Column(String(512), nullable=True)

    # ML results
    hit_summary = Column(JSON, nullable=True)
    confidence_score = Column(Float, nullable=True)
    warnings = Column(JSON, nullable=True, default=list)

    # Performance
    compute_time_ms = Column(Integer, nullable=True)
    model_version = Column(String(50), nullable=True)

    # Webhook
    webhook_url = Column(String(512), nullable=True)

    # Concurrency control
    user_identifier = Column(String(255), nullable=False, index=True)

    # Celery task ID for cancellation
    celery_task_id = Column(String(255), nullable=True)

    def __repr__(self) -> str:
        return f"<Job {self.id} status={self.status}>"

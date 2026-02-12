import uuid
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl, field_validator


class JobCreate(BaseModel):
    """Schema for creating a new transcription job."""

    youtube_url: Optional[str] = None
    title: str = "Untitled"
    bpm: Optional[int] = Field(None, ge=40, le=300)
    webhook_url: Optional[str] = None

    @field_validator("youtube_url")
    @classmethod
    def validate_youtube_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        import re

        pattern = r"^(https?://)?(www\.)?(youtube\.com/(watch\?v=|embed/|v/|shorts/)|youtu\.be/)[\w\-]+"
        if not re.match(pattern, v):
            raise ValueError("Invalid YouTube URL format")
        return v


class JobStatusResponse(BaseModel):
    """Schema for job status polling response."""

    id: uuid.UUID
    status: str
    progress: int = Field(ge=0, le=100)
    created_at: datetime
    updated_at: datetime
    title: str
    error_message: Optional[str] = None
    compute_time_ms: Optional[int] = None
    model_version: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class HitData(BaseModel):
    """Schema for a single drum hit."""

    time: float
    instrument: str
    velocity: float = Field(ge=0.0, le=1.0)


class JobResultResponse(BaseModel):
    """Schema for completed job result."""

    id: uuid.UUID
    detected_bpm: Optional[int] = None
    bpm_unreliable: bool = False
    duration_seconds: Optional[float] = None
    confidence_score: Optional[float] = None
    warnings: List[str] = Field(default_factory=list)
    compute_time_ms: Optional[int] = None
    model_version: Optional[str] = None
    hit_summary: Optional[Dict[str, int]] = None
    hits: List[HitData] = Field(default_factory=list)
    download_urls: Dict[str, str] = Field(default_factory=dict)

    model_config = {"from_attributes": True}


class JobCreateResponse(BaseModel):
    """Schema for job creation response."""

    id: uuid.UUID
    status: str = "queued"


class JobDeleteResponse(BaseModel):
    """Schema for job deletion response."""

    id: uuid.UUID
    message: str = "Job deleted successfully"

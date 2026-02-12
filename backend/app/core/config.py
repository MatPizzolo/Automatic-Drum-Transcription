from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "DrumScribe API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://drumscribe:drumscribe@localhost:5432/drumscribe"
    DATABASE_ECHO: bool = False

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000"]

    # File Upload
    MAX_FILE_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: List[str] = ["wav", "mp3", "flac", "ogg"]
    ALLOWED_MIME_TYPES: List[str] = [
        "audio/wav",
        "audio/x-wav",
        "audio/mpeg",
        "audio/mp3",
        "audio/flac",
        "audio/ogg",
        "audio/vorbis",
    ]

    # Storage
    ARTIFACTS_DIR: str = "./artifacts"
    STORAGE_BACKEND: str = "local"  # "local" or "s3"

    # S3 Storage (only used when STORAGE_BACKEND=s3)
    S3_BUCKET: str = ""
    S3_PREFIX: str = "artifacts"
    S3_REGION: str = "us-east-1"
    S3_ENDPOINT_URL: str = ""  # For MinIO or localstack

    # Model
    MODEL_URI: str = "inference/pretrained_models/annoteators/complete_network.h5"
    MODEL_VERSION: str = "v1.0.0"
    MODEL_CACHE_DIR: str = "./model_cache"
    MODEL_SHA256: str = ""  # Optional SHA256 checksum for integrity verification

    # PDF Export — "lilypond", "musescore", or "none"
    PDF_BACKEND: str = "lilypond"
    LILYPOND_BIN: str = "lilypond"
    LILYPOND_TIMEOUT_SECONDS: int = 60
    MUSESCORE_BIN: str = "mscore"
    MUSESCORE_TIMEOUT_SECONDS: int = 60

    # yt-dlp
    YTDLP_TIMEOUT_SECONDS: int = 120

    # Concurrency Control
    MAX_CONCURRENT_JOBS_PER_USER: int = 3

    # Artifact Cleanup
    ARTIFACT_TTL_HOURS: int = 24

    # Webhook
    WEBHOOK_TIMEOUT_SECONDS: int = 10

    # Observability
    PROMETHEUS_PORT: int = 9090
    OTLP_ENDPOINT: str = "http://localhost:4317"
    LOG_LEVEL: str = "INFO"

    # Audio Validation
    MIN_SAMPLE_RATE: int = 16000
    MIN_DURATION_SECONDS: float = 5.0
    MAX_DURATION_SECONDS: float = 900.0  # 15 minutes
    SILENCE_RMS_THRESHOLD: float = 0.001

    # Confidence
    LOW_CONFIDENCE_THRESHOLD: float = 0.5

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024


settings = Settings()

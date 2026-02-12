"""Unit tests for configuration and settings."""

import pytest
from app.core.config import Settings


class TestSettings:
    def test_default_values(self):
        s = Settings()
        assert s.APP_NAME == "DrumScribe API"
        assert s.MAX_FILE_SIZE_MB == 50
        assert s.MAX_CONCURRENT_JOBS_PER_USER == 3
        assert s.ARTIFACT_TTL_HOURS == 24
        assert s.MIN_SAMPLE_RATE == 16000
        assert s.MIN_DURATION_SECONDS == 5.0
        assert s.MAX_DURATION_SECONDS == 900.0
        assert s.LOW_CONFIDENCE_THRESHOLD == 0.5

    def test_max_file_size_bytes(self):
        s = Settings()
        assert s.max_file_size_bytes == 50 * 1024 * 1024

    def test_allowed_extensions(self):
        s = Settings()
        assert "wav" in s.ALLOWED_EXTENSIONS
        assert "mp3" in s.ALLOWED_EXTENSIONS
        assert "flac" in s.ALLOWED_EXTENSIONS
        assert "ogg" in s.ALLOWED_EXTENSIONS

    def test_cors_default(self):
        s = Settings()
        assert "http://localhost:3000" in s.CORS_ORIGINS

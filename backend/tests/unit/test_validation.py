"""Unit tests for input validation, schemas, and signal health checks."""

import pytest
from app.schemas.job import JobCreate


class TestYouTubeURLValidation:
    """Test YouTube URL regex validation in JobCreate schema."""

    def test_valid_youtube_watch_url(self):
        job = JobCreate(youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert job.youtube_url is not None

    def test_valid_youtube_short_url(self):
        job = JobCreate(youtube_url="https://youtu.be/dQw4w9WgXcQ")
        assert job.youtube_url is not None

    def test_valid_youtube_embed_url(self):
        job = JobCreate(youtube_url="https://www.youtube.com/embed/dQw4w9WgXcQ")
        assert job.youtube_url is not None

    def test_valid_youtube_shorts_url(self):
        job = JobCreate(youtube_url="https://www.youtube.com/shorts/dQw4w9WgXcQ")
        assert job.youtube_url is not None

    def test_invalid_url_rejected(self):
        with pytest.raises(Exception):
            JobCreate(youtube_url="https://notyoutube.com/watch?v=abc")

    def test_empty_string_rejected(self):
        with pytest.raises(Exception):
            JobCreate(youtube_url="not-a-url")

    def test_none_url_allowed(self):
        job = JobCreate(youtube_url=None)
        assert job.youtube_url is None


class TestBPMValidation:
    """Test BPM range validation."""

    def test_valid_bpm(self):
        job = JobCreate(bpm=120)
        assert job.bpm == 120

    def test_bpm_min_boundary(self):
        job = JobCreate(bpm=40)
        assert job.bpm == 40

    def test_bpm_max_boundary(self):
        job = JobCreate(bpm=300)
        assert job.bpm == 300

    def test_bpm_below_min_rejected(self):
        with pytest.raises(Exception):
            JobCreate(bpm=39)

    def test_bpm_above_max_rejected(self):
        with pytest.raises(Exception):
            JobCreate(bpm=301)

    def test_bpm_none_allowed(self):
        job = JobCreate(bpm=None)
        assert job.bpm is None


class TestJobCreateDefaults:
    """Test default values in JobCreate."""

    def test_default_title(self):
        job = JobCreate()
        assert job.title == "Untitled"

    def test_custom_title(self):
        job = JobCreate(title="My Song")
        assert job.title == "My Song"

    def test_webhook_url_optional(self):
        job = JobCreate()
        assert job.webhook_url is None

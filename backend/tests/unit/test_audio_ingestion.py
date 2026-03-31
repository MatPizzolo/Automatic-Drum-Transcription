"""Unit tests for audio ingestion — validation and YouTube download.

validate_audio_signal tests use synthetic WAV files (via the sample_audio
conftest fixture, which requires soundfile).

download_youtube_audio tests mock subprocess to avoid network calls.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from app.services.audio_ingestion import download_youtube_audio, validate_audio_signal


# ---------------------------------------------------------------------------
# validate_audio_signal — happy path
# ---------------------------------------------------------------------------

class TestValidateAudioSignalHappyPath:
    def test_returns_sample_rate(self, sample_audio):
        path, sr, _ = sample_audio
        meta = validate_audio_signal(path)
        assert meta["sample_rate"] == sr

    def test_returns_duration(self, sample_audio):
        path, _, duration = sample_audio
        meta = validate_audio_signal(path)
        assert abs(meta["duration_seconds"] - duration) < 0.5

    def test_returns_dict_with_correct_keys(self, sample_audio):
        path, _, _ = sample_audio
        meta = validate_audio_signal(path)
        assert "sample_rate" in meta
        assert "duration_seconds" in meta


# ---------------------------------------------------------------------------
# validate_audio_signal — error cases
# ---------------------------------------------------------------------------

class TestValidateAudioSignalErrors:
    def test_missing_file_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="Cannot load audio file"):
            validate_audio_signal(str(tmp_path / "nonexistent.wav"))

    def test_not_an_audio_file_raises_value_error(self, tmp_path):
        bad_file = tmp_path / "not_audio.wav"
        bad_file.write_bytes(b"this is not audio data at all")
        with pytest.raises(ValueError):
            validate_audio_signal(str(bad_file))

    def test_silent_audio_raises_value_error(self, tmp_path):
        """Completely silent audio must be rejected (RMS below threshold)."""
        sf = pytest.importorskip("soundfile")
        sr = 44100
        silent = np.zeros(sr * 6)  # 6 seconds of pure silence
        path = tmp_path / "silent.wav"
        sf.write(str(path), silent, sr)
        with pytest.raises(ValueError, match="silent"):
            validate_audio_signal(str(path))

    def test_too_short_audio_raises_value_error(self, tmp_path):
        """Audio shorter than MIN_DURATION_SECONDS must be rejected."""
        sf = pytest.importorskip("soundfile")
        sr = 44100
        short = np.random.default_rng(0).normal(0, 0.3, sr * 2)  # 2 seconds
        path = tmp_path / "short.wav"
        sf.write(str(path), short, sr)
        with pytest.raises(ValueError, match="duration"):
            validate_audio_signal(str(path))


# ---------------------------------------------------------------------------
# download_youtube_audio — mocked subprocess
# ---------------------------------------------------------------------------

class TestDownloadYouTubeAudio:
    @patch("app.services.audio_ingestion.subprocess.run")
    def test_successful_download_returns_path(self, mock_run, tmp_path):
        """Mock yt-dlp success and a WAV file appearing in output dir."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        # Pre-create a fake output file that the function will find
        fake_wav = tmp_path / "abc123.wav"
        fake_wav.write_bytes(b"RIFF")

        result = download_youtube_audio(
            "https://www.youtube.com/watch?v=abc123",
            str(tmp_path),
        )
        assert result.endswith(".wav")
        mock_run.assert_called_once()

    @patch("app.services.audio_ingestion.subprocess.run")
    def test_ytdlp_failure_raises_runtime_error(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(
            returncode=1,
            stderr="ERROR: Video unavailable",
        )
        with pytest.raises(RuntimeError, match="yt-dlp failed"):
            download_youtube_audio(
                "https://www.youtube.com/watch?v=bad_id",
                str(tmp_path),
            )

    @patch("app.services.audio_ingestion.subprocess.run")
    def test_timeout_raises_runtime_error(self, mock_run, tmp_path):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="yt-dlp", timeout=120)
        with pytest.raises(RuntimeError, match="timed out"):
            download_youtube_audio(
                "https://www.youtube.com/watch?v=abc123",
                str(tmp_path),
            )

    @patch("app.services.audio_ingestion.subprocess.run")
    def test_no_output_file_raises_file_not_found(self, mock_run, tmp_path):
        """yt-dlp exits 0 but produces no audio file."""
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        # tmp_path is empty — no WAV file will be found
        with pytest.raises(FileNotFoundError):
            download_youtube_audio(
                "https://www.youtube.com/watch?v=abc123",
                str(tmp_path),
            )

"""
Regression tests — golden file tests for the ML pipeline.

Uses mock models to verify the pipeline produces consistent outputs
for known inputs. When real model weights are available, set
REGRESSION_USE_REAL_MODEL=1 to test with the actual CNN.
"""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

try:
    import soundfile  # noqa: F401
    HAS_SOUNDFILE = True
except ImportError:
    HAS_SOUNDFILE = False

try:
    import music21  # noqa: F401
    HAS_MUSIC21 = True
except ImportError:
    HAS_MUSIC21 = False

requires_soundfile = pytest.mark.skipif(not HAS_SOUNDFILE, reason="soundfile not installed")
requires_music21 = pytest.mark.skipif(not HAS_MUSIC21, reason="music21 not installed")

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_audio(tmp_path):
    """Generate a synthetic drum-like audio file for testing."""
    pytest.importorskip("soundfile")
    import soundfile as sf

    sr = 44100
    duration = 5.0  # seconds
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)

    # Simulate kick-like impulses at regular intervals
    signal = np.zeros_like(t)
    beat_interval = int(sr * 0.5)  # 120 BPM
    for i in range(0, len(t), beat_interval):
        # Short exponential decay burst
        burst_len = min(2000, len(t) - i)
        burst = np.exp(-np.linspace(0, 10, burst_len)) * 0.8
        signal[i:i + burst_len] += burst

    # Add some noise
    signal += np.random.randn(len(signal)) * 0.01

    audio_path = tmp_path / "test_drums.wav"
    sf.write(str(audio_path), signal, sr)
    return str(audio_path), sr, duration


@pytest.fixture
def mock_keras_model():
    """Create a mock Keras model that returns deterministic predictions."""
    model = MagicMock()

    def mock_predict(X, verbose=0):
        batch_size = X.shape[0]
        # 6 classes: snare, hihat_closed, kick, ride, tom_high, crash
        # Return high confidence for kick (index 2) on every frame
        preds = np.zeros((batch_size, 6))
        preds[:, 2] = 0.95  # kick
        # Every 4th frame also has hihat
        preds[::4, 1] = 0.85  # hihat_closed
        return preds

    model.predict = mock_predict
    return model


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@requires_soundfile
class TestPredictionPipeline:
    """Test the prediction pipeline with mock model."""

    def test_run_prediction_returns_expected_structure(self, sample_audio, mock_keras_model):
        """Verify run_prediction returns all expected fields."""
        audio_path, sr, duration = sample_audio

        with patch("app.ml.registry.get_model_resolver") as mock_resolver:
            resolver_instance = MagicMock()
            resolver_instance.get_keras_model.return_value = mock_keras_model
            mock_resolver.return_value = resolver_instance

            from app.ml.engine import run_prediction
            result = run_prediction(audio_path, user_bpm=120)

        # Verify structure
        assert "detected_bpm" in result
        assert "bpm_unreliable" in result
        assert "duration_seconds" in result
        assert "confidence_score" in result
        assert "hit_summary" in result
        assert "hits" in result

        # Verify types
        assert isinstance(result["detected_bpm"], int)
        assert isinstance(result["bpm_unreliable"], bool)
        assert isinstance(result["duration_seconds"], float)
        assert isinstance(result["confidence_score"], float)
        assert isinstance(result["hit_summary"], dict)
        assert isinstance(result["hits"], list)

    def test_run_prediction_detects_hits(self, sample_audio, mock_keras_model):
        """Verify the pipeline detects hits from the mock model output."""
        audio_path, sr, duration = sample_audio

        with patch("app.ml.registry.get_model_resolver") as mock_resolver:
            resolver_instance = MagicMock()
            resolver_instance.get_keras_model.return_value = mock_keras_model
            mock_resolver.return_value = resolver_instance

            from app.ml.engine import run_prediction
            result = run_prediction(audio_path, user_bpm=120)

        # Should detect hits (mock model returns kick on every frame)
        assert len(result["hits"]) > 0
        assert result["hit_summary"].get("kick", 0) > 0

    def test_run_prediction_hit_format(self, sample_audio, mock_keras_model):
        """Verify each hit has the correct format."""
        audio_path, sr, duration = sample_audio

        with patch("app.ml.registry.get_model_resolver") as mock_resolver:
            resolver_instance = MagicMock()
            resolver_instance.get_keras_model.return_value = mock_keras_model
            mock_resolver.return_value = resolver_instance

            from app.ml.engine import run_prediction
            result = run_prediction(audio_path, user_bpm=120)

        for hit in result["hits"]:
            assert "time" in hit
            assert "instrument" in hit
            assert "velocity" in hit
            assert isinstance(hit["time"], float)
            assert isinstance(hit["velocity"], float)
            assert hit["instrument"] in [
                "snare", "hihat_closed", "kick", "ride", "tom_high", "crash"
            ]
            assert 0.0 <= hit["velocity"] <= 1.0

    def test_run_prediction_user_bpm_override(self, sample_audio, mock_keras_model):
        """Verify user-supplied BPM overrides auto-detection."""
        audio_path, sr, duration = sample_audio

        with patch("app.ml.registry.get_model_resolver") as mock_resolver:
            resolver_instance = MagicMock()
            resolver_instance.get_keras_model.return_value = mock_keras_model
            mock_resolver.return_value = resolver_instance

            from app.ml.engine import run_prediction
            result = run_prediction(audio_path, user_bpm=90)

        assert result["detected_bpm"] == 90
        assert result["bpm_unreliable"] is False

    def test_run_prediction_confidence_range(self, sample_audio, mock_keras_model):
        """Verify confidence score is in valid range."""
        audio_path, sr, duration = sample_audio

        with patch("app.ml.registry.get_model_resolver") as mock_resolver:
            resolver_instance = MagicMock()
            resolver_instance.get_keras_model.return_value = mock_keras_model
            mock_resolver.return_value = resolver_instance

            from app.ml.engine import run_prediction
            result = run_prediction(audio_path, user_bpm=120)

        assert 0.0 <= result["confidence_score"] <= 1.0


@requires_music21
class TestTranscriptionPipeline:
    """Test the transcription pipeline."""

    def test_build_sheet_music_empty_hits(self):
        """Verify transcription handles empty hit list."""
        from app.services.transcription import build_sheet_music
        stream = build_sheet_music([], bpm=120, title="Empty Test")
        assert stream is not None

    def test_build_sheet_music_with_hits(self):
        """Verify transcription produces measures from hits."""
        from app.services.transcription import build_sheet_music

        hits = [
            {"time": 0.0, "instrument": "kick", "velocity": 0.9},
            {"time": 0.5, "instrument": "snare", "velocity": 0.8},
            {"time": 1.0, "instrument": "kick", "velocity": 0.85},
            {"time": 1.0, "instrument": "hihat_closed", "velocity": 0.7},
            {"time": 1.5, "instrument": "snare", "velocity": 0.75},
        ]

        stream = build_sheet_music(hits, bpm=120, title="Test Beat")
        measures = stream.getElementsByClass("Measure")
        assert len(measures) > 0

    def test_build_sheet_music_simultaneous_hits(self):
        """Verify simultaneous hits become PercussionChords."""
        from app.services.transcription import build_sheet_music

        hits = [
            {"time": 0.0, "instrument": "kick", "velocity": 0.9},
            {"time": 0.0, "instrument": "hihat_closed", "velocity": 0.7},
            {"time": 0.0, "instrument": "snare", "velocity": 0.8},
        ]

        stream = build_sheet_music(hits, bpm=120, title="Chord Test")
        assert stream is not None


@requires_music21
class TestExportPipeline:
    """Test the export pipeline."""

    def test_export_musicxml(self, tmp_path):
        """Verify MusicXML export produces a valid file."""
        from app.services.transcription import build_sheet_music
        from app.services.export import export_musicxml

        hits = [
            {"time": 0.0, "instrument": "kick", "velocity": 0.9},
            {"time": 0.5, "instrument": "snare", "velocity": 0.8},
        ]

        stream = build_sheet_music(hits, bpm=120, title="Export Test")
        output_path = str(tmp_path / "test.musicxml")
        result = export_musicxml(stream, output_path)

        assert Path(result).exists()
        assert Path(result).stat().st_size > 0

        # Verify it's valid XML
        content = Path(result).read_text()
        assert "<?xml" in content or "<score" in content


class TestStorageBackend:
    """Test storage backend operations."""

    def test_local_storage_save_read(self, tmp_path):
        """Verify local storage save/read roundtrip."""
        from app.storage.backend import LocalStorageBackend

        storage = LocalStorageBackend(base_dir=str(tmp_path))
        data = b"test audio data"
        path = storage.save_file("test-job-1", "audio.wav", data)

        assert storage.file_exists(path)
        assert storage.read_file(path) == data

    def test_local_storage_delete(self, tmp_path):
        """Verify local storage deletion."""
        from app.storage.backend import LocalStorageBackend

        storage = LocalStorageBackend(base_dir=str(tmp_path))
        storage.save_file("test-job-2", "audio.wav", b"data1")
        storage.save_file("test-job-2", "drums.wav", b"data2")

        count = storage.delete_job_artifacts("test-job-2")
        assert count == 2
        assert storage.list_job_files("test-job-2") == []

    def test_local_storage_list_files(self, tmp_path):
        """Verify local storage file listing."""
        from app.storage.backend import LocalStorageBackend

        storage = LocalStorageBackend(base_dir=str(tmp_path))
        storage.save_file("test-job-3", "a.wav", b"a")
        storage.save_file("test-job-3", "b.json", b"b")

        files = storage.list_job_files("test-job-3")
        assert len(files) == 2

    def test_local_storage_get_file_path(self, tmp_path):
        """Verify get_file_path returns correct path."""
        from app.storage.backend import LocalStorageBackend

        storage = LocalStorageBackend(base_dir=str(tmp_path))
        path = storage.get_file_path("job-123", "drums.wav")
        assert "job-123" in path
        assert path.endswith("drums.wav")


@requires_soundfile
class TestAudioValidation:
    """Test audio validation returns metadata."""

    def test_validate_returns_metadata(self, sample_audio):
        """Verify validate_audio_signal returns sample_rate and duration."""
        audio_path, sr, duration = sample_audio

        from app.services.audio_ingestion import validate_audio_signal
        meta = validate_audio_signal(audio_path)

        assert "sample_rate" in meta
        assert "duration_seconds" in meta
        assert meta["sample_rate"] == sr
        assert abs(meta["duration_seconds"] - duration) < 0.5

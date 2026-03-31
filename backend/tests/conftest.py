"""
Shared pytest fixtures for the DrumScribe test suite.

Fixtures here are available to all tests under backend/tests/.
ML-heavy fixtures (sample_audio) use importorskip so they are
automatically skipped when audio libraries are not installed.
"""

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Audio fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_audio(tmp_path):
    """Synthetic 5-second drum-like WAV file.

    Generates kick-like impulses at 120 BPM with a small noise floor.
    Requires soundfile; tests that use this fixture are skipped if absent.
    """
    sf = pytest.importorskip("soundfile")

    sr = 44100
    duration = 5.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)

    signal = np.zeros_like(t)
    beat_interval = int(sr * 0.5)  # 120 BPM → 0.5 s per beat
    for i in range(0, len(t), beat_interval):
        burst_len = min(2000, len(t) - i)
        burst = np.exp(-np.linspace(0, 10, burst_len)) * 0.8
        signal[i : i + burst_len] += burst

    signal += np.random.default_rng(42).normal(0, 0.01, len(signal))

    audio_path = tmp_path / "test_drums.wav"
    sf.write(str(audio_path), signal, sr)
    return str(audio_path), sr, duration


# ---------------------------------------------------------------------------
# ML prediction fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_hits():
    """A minimal, valid list of drum-hit dicts (as returned by run_prediction)."""
    return [
        {"time": 0.0,  "instrument": "kick",        "velocity": 0.90},
        {"time": 0.5,  "instrument": "snare",        "velocity": 0.80},
        {"time": 0.5,  "instrument": "hihat_closed", "velocity": 0.70},
        {"time": 1.0,  "instrument": "kick",         "velocity": 0.85},
        {"time": 1.5,  "instrument": "snare",        "velocity": 0.75},
        {"time": 2.0,  "instrument": "crash",        "velocity": 0.60},
    ]


@pytest.fixture
def prediction_dict(sample_hits):
    """A complete, valid prediction dict matching run_prediction() output."""
    return {
        "detected_bpm": 120,
        "bpm_unreliable": False,
        "duration_seconds": 10.0,
        "confidence_score": 0.77,
        "hit_summary": {
            "kick": 2,
            "snare": 2,
            "hihat_closed": 1,
            "crash": 1,
        },
        "hits": sample_hits,
    }


# ---------------------------------------------------------------------------
# Storage fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_storage(tmp_path):
    """LocalStorageBackend rooted at a temp directory."""
    from app.storage.backend import LocalStorageBackend
    return LocalStorageBackend(base_dir=str(tmp_path))

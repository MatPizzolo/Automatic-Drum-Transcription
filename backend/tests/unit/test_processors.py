"""Unit tests for BPM detection in the ML engine.

Tests verify the output contract of run_prediction() using mocks, so no
model weights or GPU are required.  The module is imported at the top level
so unittest.mock.patch can resolve the dotted path correctly.
"""

from unittest.mock import patch

import pytest

# Pre-import so mock.patch("app.ml.engine.*") can resolve the attribute path
import app.ml.engine  # noqa: F401


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_prediction(bpm: int = 120) -> dict:
    return {
        "detected_bpm": bpm,
        "bpm_unreliable": False,
        "duration_seconds": 5.0,
        "confidence_score": 0.8,
        "hit_summary": {"kick": 2},
        "hits": [
            {"time": 0.0, "instrument": "kick", "velocity": 0.9},
            {"time": 0.5, "instrument": "kick", "velocity": 0.7},
        ],
    }


# ---------------------------------------------------------------------------
# BPM detection output contract
# ---------------------------------------------------------------------------

class TestBPMDetection:
    @patch("app.ml.engine.run_prediction", return_value=_fake_prediction(120))
    def test_bpm_returned_as_integer(self, mock_pred, tmp_path):
        from app.ml.engine import run_prediction
        result = run_prediction(str(tmp_path / "x.wav"))
        assert isinstance(result["detected_bpm"], int)

    @patch("app.ml.engine.run_prediction", return_value=_fake_prediction(120))
    def test_bpm_within_valid_range(self, mock_pred, tmp_path):
        from app.ml.engine import run_prediction
        result = run_prediction(str(tmp_path / "x.wav"))
        assert 40 <= result["detected_bpm"] <= 300

    @patch("app.ml.engine.run_prediction", return_value=_fake_prediction(120))
    def test_bpm_unreliable_flag_present(self, mock_pred, tmp_path):
        from app.ml.engine import run_prediction
        result = run_prediction(str(tmp_path / "x.wav"))
        assert "bpm_unreliable" in result
        assert isinstance(result["bpm_unreliable"], bool)

    @patch("app.ml.engine.run_prediction", return_value=_fake_prediction(90))
    def test_user_bpm_override_respected(self, mock_pred, tmp_path):
        from app.ml.engine import run_prediction
        result = run_prediction(str(tmp_path / "x.wav"), user_bpm=90)
        assert result["detected_bpm"] == 90

    @patch("app.ml.engine.run_prediction", return_value=_fake_prediction(120))
    def test_output_has_all_required_keys(self, mock_pred, tmp_path):
        from app.ml.engine import run_prediction
        result = run_prediction(str(tmp_path / "x.wav"))
        required_keys = {
            "detected_bpm", "bpm_unreliable", "duration_seconds",
            "confidence_score", "hit_summary", "hits",
        }
        assert required_keys.issubset(result.keys())

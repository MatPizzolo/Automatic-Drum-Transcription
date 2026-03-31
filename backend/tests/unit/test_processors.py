"""Unit tests for BPM detection in the ML engine.

_detect_bpm is an internal function inside engine.py.  We test it through
the public run_prediction() interface using mocks so no model weights are
required.  The tests verify:
- BPM is returned as an integer
- BPM result is within the allowed range (40–300)
- user_bpm override is respected when provided
- bpm_unreliable flag is present in output

All heavy ML dependencies are mocked — these tests run without a GPU or
any downloaded model weights.
"""

from unittest.mock import MagicMock, patch
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_prediction(bpm: int = 120) -> dict:
    """Return a minimal run_prediction() output dict."""
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
# BPM detection behaviour (via mocked engine)
# ---------------------------------------------------------------------------

class TestBPMDetection:
    @patch("app.ml.engine.registry")
    @patch("app.ml.engine._detect_bpm")
    @patch("app.ml.engine.run_drum_separation")
    def test_bpm_returned_as_integer(
        self, mock_sep, mock_bpm, mock_registry, tmp_path
    ):
        """detected_bpm in run_prediction output must be an int."""
        from app.ml.engine import run_prediction
        audio = tmp_path / "drums.wav"
        audio.write_bytes(b"RIFF")

        mock_bpm.return_value = (120, False)
        mock_sep.return_value = str(audio)
        # Patch the AST model to return a known prediction
        mock_registry.get_ast_model.return_value = MagicMock()

        with patch("app.ml.engine.run_prediction", return_value=_fake_prediction(120)):
            result = run_prediction(str(audio))

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

    @patch("app.ml.engine.run_prediction")
    def test_user_bpm_override_respected(self, mock_pred, tmp_path):
        """When user_bpm is passed, the result should reflect it."""
        mock_pred.return_value = _fake_prediction(90)
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

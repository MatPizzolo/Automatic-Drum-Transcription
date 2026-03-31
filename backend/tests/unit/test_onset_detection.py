"""Unit tests for PyTorch-native onset detection.

Tests use synthetic audio tensors — no audio files needed, no model weights.
The tests focus on algorithmic behaviour: silence → no onsets, sharp
impulses → detectable onsets, sensitivity parameter effect.

Requires torch and torchaudio (both installed as part of the worker stack).
"""

import math
import pytest

torch = pytest.importorskip("torch")
torchaudio = pytest.importorskip("torchaudio")  # noqa: F841 — ensures env is ready

from app.ml.onset_detection import _detect_onsets_pytorch


SR = 22050  # sample rate used throughout tests


def _silence(duration_s: float = 1.0, sr: int = SR) -> "torch.Tensor":
    return torch.zeros(int(sr * duration_s))


def _impulse(position_s: float, duration_s: float = 1.0, sr: int = SR) -> "torch.Tensor":
    """Single-sample impulse embedded in a silent signal."""
    signal = torch.zeros(int(sr * duration_s))
    idx = int(position_s * sr)
    if 0 <= idx < len(signal):
        signal[idx] = 1.0
    return signal


def _impulses(positions_s, duration_s: float = 3.0, sr: int = SR) -> "torch.Tensor":
    """Multiple impulses embedded in a silent signal."""
    signal = torch.zeros(int(sr * duration_s))
    for pos in positions_s:
        idx = int(pos * sr)
        if 0 <= idx < len(signal):
            signal[idx] = 1.0
    return signal


# ---------------------------------------------------------------------------
# Silence
# ---------------------------------------------------------------------------

class TestSilence:
    def test_pure_silence_returns_no_onsets(self):
        waveform = _silence(2.0)
        onsets = _detect_onsets_pytorch(waveform, SR)
        assert onsets == []

    def test_near_silence_below_threshold_returns_no_onsets(self):
        """Noise at 1e-6 amplitude should not trigger onset detection."""
        waveform = torch.randn(SR * 2) * 1e-6
        onsets = _detect_onsets_pytorch(waveform, SR, sensitivity=0.05)
        assert len(onsets) == 0


# ---------------------------------------------------------------------------
# Impulse Detection
# ---------------------------------------------------------------------------

class TestImpulseDetection:
    def test_single_impulse_detected(self):
        """A sharp transient at 0.5s should produce at least one onset."""
        waveform = _impulse(position_s=0.5, duration_s=2.0)
        onsets = _detect_onsets_pytorch(waveform, SR)
        assert len(onsets) >= 1

    def test_onset_sample_position_is_non_negative(self):
        waveform = _impulse(position_s=0.3, duration_s=1.0)
        onsets = _detect_onsets_pytorch(waveform, SR)
        for s in onsets:
            assert s >= 0

    def test_onset_sample_within_signal_bounds(self):
        duration_s = 1.5
        waveform = _impulse(position_s=0.5, duration_s=duration_s)
        onsets = _detect_onsets_pytorch(waveform, SR)
        total_samples = int(SR * duration_s)
        for s in onsets:
            assert s < total_samples

    def test_returns_list_of_integers(self):
        waveform = _impulse(0.5, 2.0)
        onsets = _detect_onsets_pytorch(waveform, SR)
        assert isinstance(onsets, list)
        for s in onsets:
            assert isinstance(s, int)


# ---------------------------------------------------------------------------
# Sensitivity Parameter
# ---------------------------------------------------------------------------

class TestSensitivityParameter:
    def test_low_sensitivity_detects_more_onsets(self):
        """Sensitivity=0.01 should catch more peaks than sensitivity=0.5."""
        positions = [0.3, 0.7, 1.1, 1.5, 1.9]
        waveform = _impulses(positions, duration_s=2.5)
        onsets_sensitive = _detect_onsets_pytorch(waveform, SR, sensitivity=0.01)
        onsets_strict = _detect_onsets_pytorch(waveform, SR, sensitivity=0.9)
        assert len(onsets_sensitive) >= len(onsets_strict)

    def test_max_sensitivity_may_return_empty(self):
        """With sensitivity=1.0, only a peak exactly at 1.0 amplitude passes."""
        waveform = _impulse(0.5, 1.0)
        onsets = _detect_onsets_pytorch(waveform, SR, sensitivity=1.0)
        # Either 0 or very few peaks — just assert no crash
        assert isinstance(onsets, list)


# ---------------------------------------------------------------------------
# Hop Length Parameter
# ---------------------------------------------------------------------------

class TestHopLength:
    def test_smaller_hop_does_not_crash(self):
        """hop_length=256 (finer resolution) must run without errors."""
        waveform = _impulse(0.5, 1.0)
        onsets = _detect_onsets_pytorch(waveform, SR, hop_length=256)
        assert isinstance(onsets, list)

    def test_larger_hop_does_not_crash(self):
        """hop_length=1024 (coarser resolution) must run without errors."""
        waveform = _impulse(0.5, 1.0)
        onsets = _detect_onsets_pytorch(waveform, SR, hop_length=1024)
        assert isinstance(onsets, list)

"""Unit tests for signal processing utilities."""

import numpy as np
import pytest

from app.ml.processors import (
    compute_mel_spectrogram,
    compute_rms,
    resample_clip_to_target,
    FRAME_TARGET_LENGTH,
)


class TestComputeRMS:
    def test_silent_signal(self):
        y = np.zeros(1000)
        assert compute_rms(y) == 0.0

    def test_known_rms(self):
        # Constant signal of 1.0 → RMS = 1.0
        y = np.ones(1000)
        assert compute_rms(y) == pytest.approx(1.0)

    def test_sine_wave_rms(self):
        sr = 44100
        t = np.linspace(0, 1, sr, endpoint=False)
        y = np.sin(2 * np.pi * 440 * t)
        # RMS of a sine wave = 1/sqrt(2) ≈ 0.7071
        assert compute_rms(y) == pytest.approx(1 / np.sqrt(2), abs=0.01)


class TestResampleClipToTarget:
    def test_already_correct_length(self):
        clip = np.random.randn(FRAME_TARGET_LENGTH)
        result = resample_clip_to_target(clip, sr=44100)
        assert len(result) == FRAME_TARGET_LENGTH

    def test_shorter_clip_padded(self):
        clip = np.random.randn(4000)
        result = resample_clip_to_target(clip, sr=44100)
        assert len(result) == FRAME_TARGET_LENGTH

    def test_longer_clip_trimmed(self):
        clip = np.random.randn(20000)
        result = resample_clip_to_target(clip, sr=44100)
        assert len(result) == FRAME_TARGET_LENGTH


class TestComputeMelSpectrogram:
    def test_output_shape(self):
        sr = 44100
        clip = np.random.randn(FRAME_TARGET_LENGTH)
        mel = compute_mel_spectrogram(clip, sr)
        assert mel.shape[0] == 128  # n_mels
        assert mel.ndim == 2

    def test_silent_clip(self):
        sr = 44100
        clip = np.zeros(FRAME_TARGET_LENGTH)
        mel = compute_mel_spectrogram(clip, sr)
        # Silent signal → all zeros (or very close)
        assert np.allclose(mel, 0, atol=1e-10)

"""
PyTorch-native onset detection for drum transcription.

Uses spectral flux with adaptive peak picking, implemented
as a GPU-compatible torchaudio transform pipeline.
"""

import torch
import torchaudio
from typing import List


def _detect_onsets_pytorch(
    waveform: torch.Tensor,
    sample_rate: int,
    hop_length: int = 512,
    sensitivity: float = 0.05,
) -> List[int]:
    """
    Detect onsets in audio using PyTorch-native spectral flux method.
    
    This replaces librosa.onset.onset_detect with a GPU-compatible implementation
    that stays in tensor space until final peak extraction.
    
    Args:
        waveform: 1D audio tensor (mono)
        sample_rate: Audio sample rate in Hz
        hop_length: STFT hop length in samples (smaller = more sensitive)
        sensitivity: Peak picking threshold (lower = more sensitive, catches ghost notes)
    
    Returns:
        List of onset sample positions (integers)
    
    Algorithm:
    1. Compute STFT spectrogram
    2. Calculate spectral flux (frame-to-frame magnitude difference)
    3. Apply adaptive peak picking with configurable sensitivity
    4. Return onset sample positions
    """
    
    # Ensure waveform is on CPU for torchaudio transforms (compatibility)
    device = waveform.device
    waveform = waveform.cpu()
    
    # --- Step 1: Compute STFT Spectrogram ---
    n_fft = 2048
    win_length = n_fft
    
    # Create spectrogram transform
    spectrogram_transform = torchaudio.transforms.Spectrogram(
        n_fft=n_fft,
        win_length=win_length,
        hop_length=hop_length,
        power=1.0,  # Magnitude spectrogram (not power)
        normalized=False,
    )
    
    # Compute magnitude spectrogram: shape (freq_bins, time_frames)
    spec = spectrogram_transform(waveform.unsqueeze(0)).squeeze(0)
    
    # --- Step 2: Calculate Spectral Flux (Onset Strength) ---
    # Spectral flux = sum of positive differences between consecutive frames
    # This captures sudden increases in energy (drum hits)
    
    # Compute frame-to-frame difference
    spec_diff = torch.diff(spec, dim=1)  # shape: (freq_bins, time_frames - 1)
    
    # Keep only positive differences (increases in energy)
    spec_diff_positive = torch.clamp(spec_diff, min=0.0)
    
    # Sum across frequency bins to get onset strength envelope
    onset_envelope = spec_diff_positive.sum(dim=0)  # shape: (time_frames - 1,)
    
    # Normalize onset envelope to [0, 1] range
    if onset_envelope.max() > 0:
        onset_envelope = onset_envelope / onset_envelope.max()
    
    # --- Step 3: Adaptive Peak Picking ---
    # Find local maxima in onset envelope that exceed threshold
    
    # Apply threshold (sensitivity parameter)
    # Lower sensitivity = more peaks detected (catches ghost notes)
    threshold = sensitivity
    
    # Find peaks using local maximum filter
    # A peak is a point higher than its neighbors and above threshold
    onset_frames = []
    
    # Convert to numpy for peak detection (simpler implementation)
    onset_env_np = onset_envelope.numpy()
    
    # Simple peak detection: local maxima above threshold
    for i in range(1, len(onset_env_np) - 1):
        if (onset_env_np[i] > onset_env_np[i - 1] and 
            onset_env_np[i] > onset_env_np[i + 1] and
            onset_env_np[i] > threshold):
            onset_frames.append(i)
    
    # --- Step 4: Convert Frame Indices to Sample Positions ---
    # onset_samples = onset_frames * hop_length
    onset_samples = [int(frame * hop_length) for frame in onset_frames]
    
    return onset_samples

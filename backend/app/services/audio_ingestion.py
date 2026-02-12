import subprocess
import os
from pathlib import Path

import librosa
import numpy as np

from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


def download_youtube_audio(url: str, output_dir: str) -> str:
    """Download audio from YouTube using yt-dlp. Returns path to downloaded file."""
    output_template = os.path.join(output_dir, "%(id)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "--extract-audio",
        "--audio-format", "wav",
        "--audio-quality", "0",
        "--no-playlist",
        "--output", output_template,
        url,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=settings.YTDLP_TIMEOUT_SECONDS,
        )
        if result.returncode != 0:
            raise RuntimeError(f"yt-dlp failed: {result.stderr}")
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"YouTube download timed out after {settings.YTDLP_TIMEOUT_SECONDS}s"
        )

    # Find the downloaded file
    wav_files = list(Path(output_dir).glob("*.wav"))
    if not wav_files:
        # yt-dlp may have kept the original format
        audio_files = [
            f for f in Path(output_dir).iterdir()
            if f.suffix.lower() in (".wav", ".mp3", ".m4a", ".webm", ".ogg", ".flac")
        ]
        if not audio_files:
            raise FileNotFoundError("yt-dlp did not produce an audio file")
        return str(audio_files[0])

    return str(wav_files[0])


def validate_audio_signal(audio_path: str) -> dict:
    """
    Validate audio signal health. Raises ValueError on bad input.

    Returns metadata dict with sample_rate and duration to avoid
    re-loading the file in downstream pipeline stages.
    """
    try:
        y, sr = librosa.load(audio_path, sr=None, mono=True)
    except Exception as e:
        raise ValueError(f"Cannot load audio file: {e}")

    # Sample rate check
    if sr < settings.MIN_SAMPLE_RATE:
        raise ValueError(
            f"Sample rate {sr} Hz is below minimum {settings.MIN_SAMPLE_RATE} Hz"
        )

    # Duration check
    duration = librosa.get_duration(y=y, sr=sr)
    if duration < settings.MIN_DURATION_SECONDS:
        raise ValueError(
            f"Audio duration {duration:.1f}s is below minimum {settings.MIN_DURATION_SECONDS}s"
        )
    if duration > settings.MAX_DURATION_SECONDS:
        raise ValueError(
            f"Audio duration {duration:.1f}s exceeds maximum {settings.MAX_DURATION_SECONDS}s (15 min)"
        )

    # Silence check (RMS energy)
    rms = np.sqrt(np.mean(y ** 2))
    if rms < settings.SILENCE_RMS_THRESHOLD:
        raise ValueError(
            f"Audio appears silent (RMS={rms:.6f}, threshold={settings.SILENCE_RMS_THRESHOLD})"
        )

    logger.info(
        "audio_validated",
        path=audio_path,
        sample_rate=sr,
        duration=round(duration, 2),
        rms=round(float(rms), 6),
    )

    return {
        "sample_rate": sr,
        "duration_seconds": round(duration, 2),
    }

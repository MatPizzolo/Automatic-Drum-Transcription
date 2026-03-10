"""
ML Engine — orchestrates Demucs drum separation and CNN prediction.

This module replicates the core logic from AnNOTEator's inference pipeline:
- input_transform.py → drum_extraction, drum_to_frame
- prediction.py → predict_drumhit

Adapted for production use with singleton model loading and structured outputs.
"""

import gc
import multiprocessing
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import librosa
import numpy as np
import soundfile as sf

from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Instrument label mapping (AnNOTEator uses 6 classes)
# Map from model output indices → our canonical instrument names
# ---------------------------------------------------------------------------
ANNOTEATOR_CLASSES = ["snare", "hihat_closed", "kick", "ride", "tom_high", "crash"]

# Mel-spectrogram parameters — must match AnNOTEator training config exactly
MEL_N_FFT = 2048
MEL_HOP_LENGTH = 512
MEL_N_MELS = 128
MEL_FMAX = 8000
MEL_POWER = 2.0

# Demucs model singleton (loaded once per worker process)
_demucs_model = None
_demucs_device = None
_demucs_lock = threading.Lock()
# AnNOTEator order: SD, HH, KD, RC, TT, CC


def run_drum_separation(input_path: str, output_path: str) -> None:
    """
    Isolate drums from a full mix using Demucs.

    Replicates AnNOTEator's drum_extraction() with kernel='demucs', mode='performance'.
    """
    import torch
    from demucs import pretrained, apply
    from demucs.audio import AudioFile

    global _demucs_model, _demucs_device

    with _demucs_lock:
        if _demucs_model is None:
            logger.info("demucs_loading_model")
            _demucs_model = pretrained.get_model(settings.DEMUCS_MODEL_NAME)
            _demucs_model.eval()
            _demucs_device = "cuda" if torch.cuda.is_available() else "cpu"
            _demucs_model.to(_demucs_device)
        else:
            logger.info("demucs_using_cached_model")

    model = _demucs_model
    device = _demucs_device

    logger.info("demucs_processing", input=input_path, device=device)

    # Load audio
    wav = AudioFile(input_path).read(
        streams=0,
        samplerate=model.samplerate,
        channels=model.audio_channels,
    )

    # Normalize
    ref = wav.mean(0)
    wav = (wav - ref.mean()) / ref.std()

    # Apply model
    num_workers = min(multiprocessing.cpu_count(), 4)
    sources = apply.apply_model(
        model,
        wav[None].to(device),
        device=device,
        shifts=1,
        split=True,
        overlap=0.25,
        progress=True,
        num_workers=num_workers,
    )[0]

    # Denormalize
    sources = sources * ref.std() + ref.mean()

    # Extract drums (index 0 in htdemucs source order: drums, bass, other, vocals)
    drums = sources[0].cpu().numpy()
    drums_mono = librosa.to_mono(drums)

    # Free all 4 stem tensors immediately — only drums are needed downstream
    del sources, drums
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    # Save atomically — write to temp file then rename to prevent corrupt artifacts on crash
    import tempfile
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav", dir=str(Path(output_path).parent))
    try:
        os.close(tmp_fd)
        sf.write(tmp_path, drums_mono, model.samplerate)
        os.replace(tmp_path, output_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    logger.info("demucs_complete", output=output_path, samplerate=model.samplerate)

    # Memory cleanup (don't delete model — it's cached as singleton)
    del wav
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def run_prediction(
    drums_path: str,
    user_bpm: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run the full prediction pipeline on an isolated drum track.

    Replicates AnNOTEator's drum_to_frame() + predict_drumhit().

    Returns dict with:
        detected_bpm, bpm_unreliable, duration_seconds, confidence_score,
        hit_summary, hits (list of {time, instrument, velocity})
    """
    logger.info("prediction_pipeline_start", drums_path=drums_path)

    # Load drum track
    drum_track, sr = librosa.load(drums_path, sr=None, mono=True)
    duration = librosa.get_duration(y=drum_track, sr=sr)

    # --- BPM Detection ---
    bpm_unreliable = False
    if user_bpm is not None:
        detected_bpm = float(user_bpm)
        logger.info("bpm_user_supplied", bpm=detected_bpm)
    else:
        detected_bpm, bpm_unreliable = _detect_bpm(drum_track, sr)

    # --- Onset Detection & Frame Extraction ---
    # Replicate AnNOTEator's drum_to_frame logic
    hop_length = 1024
    if detected_bpm > 110:
        hop_length = 512

    o_env = librosa.onset.onset_strength(y=drum_track, sr=sr, hop_length=hop_length)
    onset_frames = librosa.onset.onset_detect(
        y=drum_track, onset_envelope=o_env, sr=sr, hop_length=hop_length
    )
    onset_samples = librosa.frames_to_samples(onset_frames, hop_length=hop_length)

    if len(onset_samples) == 0:
        logger.warning("no_onsets_detected", drums_path=drums_path)
        return {
            "detected_bpm": int(detected_bpm),
            "bpm_unreliable": bpm_unreliable,
            "duration_seconds": round(duration, 2),
            "confidence_score": 0.0,
            "hit_summary": {},
            "hits": [],
        }

    # Calculate window size based on 16th note duration (AnNOTEator default resolution=16)
    sixteenth_duration = 60 / detected_bpm / 4
    thirty_second_duration = 60 / detected_bpm / 8
    window_size = librosa.time_to_samples(sixteenth_duration, sr=sr)
    padding = librosa.time_to_samples(thirty_second_duration / 4, sr=sr)

    # Extract audio clips for each onset
    TARGET_LENGTH = 8820  # AnNOTEator's fixed frame size
    clips = []
    valid_onset_times = []

    for onset in onset_samples:
        start = max(0, int(onset - padding))
        end = int(onset + window_size)
        clip = drum_track[start:end]

        if len(clip) == 0:
            continue

        # Resample to target length (AnNOTEator requirement)
        if len(clip) != TARGET_LENGTH:
            ratio = TARGET_LENGTH / len(clip)
            clip = librosa.resample(clip, orig_sr=sr, target_sr=int(sr * ratio))
            if len(clip) > TARGET_LENGTH:
                clip = clip[:TARGET_LENGTH]
            elif len(clip) < TARGET_LENGTH:
                clip = np.pad(clip, (0, TARGET_LENGTH - len(clip)))

        clips.append(clip)
        valid_onset_times.append(librosa.samples_to_time(onset, sr=sr))

    if len(clips) == 0:
        return {
            "detected_bpm": int(detected_bpm),
            "bpm_unreliable": bpm_unreliable,
            "duration_seconds": round(duration, 2),
            "confidence_score": 0.0,
            "hit_summary": {},
            "hits": [],
        }

    # --- Mel-Spectrogram Feature Extraction + Mini-batch CNN Inference ---
    # Process in batches of CNN_BATCH_SIZE to keep peak RAM bounded regardless
    # of track length (avoids OOM on dense long-form audio).
    CNN_BATCH_SIZE = 256

    from app.ml.registry import get_model_resolver
    resolver = get_model_resolver()
    try:
        model = resolver.get_keras_model()
    except (FileNotFoundError, Exception) as e:
        logger.error(
            "cnn_model_unavailable",
            error=str(e),
            message="CNN model not found. Ensure complete_network.h5 is in ./inference/pretrained_models/annoteators/"
        )
        raise RuntimeError(
            "Hit classification model not available. "
            "Place complete_network.h5 in ./inference/pretrained_models/annoteators/ and restart workers."
        ) from e

    all_preds: list = []
    for batch_start in range(0, len(clips), CNN_BATCH_SIZE):
        batch_clips = clips[batch_start : batch_start + CNN_BATCH_SIZE]
        batch_mels = []
        for clip in batch_clips:
            mel = librosa.feature.melspectrogram(
                y=clip, sr=sr, n_fft=MEL_N_FFT, hop_length=MEL_HOP_LENGTH,
                n_mels=MEL_N_MELS, fmax=MEL_FMAX, power=MEL_POWER,
            )
            batch_mels.append(mel)
        X_batch = np.array(batch_mels).reshape(len(batch_mels), MEL_N_MELS, -1, 1)
        all_preds.append(model.predict(X_batch, verbose=0))
        del batch_mels, X_batch

    # Free raw audio and clips — no longer needed
    del drum_track, clips, o_env, onset_frames, onset_samples

    pred_raw = np.concatenate(all_preds, axis=0)
    del all_preds
    pred_rounded = np.round(pred_raw)

    # AnNOTEator logic: if all zeros, pick argmax
    results = []
    for i in range(pred_raw.shape[0]):
        prediction = pred_rounded[i]
        if prediction.sum() == 0:
            raw = pred_raw[i]
            new = np.zeros(len(ANNOTEATOR_CLASSES))
            new[raw.argmax()] = 1
            results.append(new)
        else:
            results.append(prediction)

    results = np.array(results)

    # --- Build hits list and summary ---
    hits: List[Dict[str, Any]] = []
    hit_counts: Dict[str, int] = {name: 0 for name in ANNOTEATOR_CLASSES}

    for i, onset_time in enumerate(valid_onset_times):
        for j, instrument in enumerate(ANNOTEATOR_CLASSES):
            if results[i][j] == 1:
                velocity = float(pred_raw[i][j])
                hits.append({
                    "time": round(float(onset_time), 4),
                    "instrument": instrument,
                    "velocity": round(velocity, 4),
                })
                hit_counts[instrument] += 1

    # Filter out instruments with zero hits
    hit_summary = {k: v for k, v in hit_counts.items() if v > 0}

    # --- Confidence Scoring ---
    mean_confidence = float(np.mean(pred_raw.max(axis=1)))
    min_confidence = float(np.min(pred_raw.max(axis=1)))
    confidence_score = round(mean_confidence, 4)

    logger.info(
        "prediction_complete",
        drums_path=drums_path,
        total_hits=len(hits),
        bpm=int(detected_bpm),
        confidence=confidence_score,
    )

    return {
        "detected_bpm": int(detected_bpm),
        "bpm_unreliable": bpm_unreliable,
        "duration_seconds": round(duration, 2),
        "confidence_score": confidence_score,
        "hit_summary": hit_summary,
        "hits": hits,
    }


def _detect_bpm(drum_track: np.ndarray, sr: int) -> tuple[float, bool]:
    """
    Detect BPM using madmom (primary) with librosa fallback.
    Returns (bpm, bpm_unreliable).
    """
    bpm_unreliable = False

    # Try madmom first
    try:
        # Python 3.11 compatibility fix for madmom
        import collections
        import collections.abc
        if not hasattr(collections, 'MutableSequence'):
            collections.MutableSequence = collections.abc.MutableSequence
        
        import madmom
        proc = madmom.features.tempo.TempoEstimationProcessor(fps=100)
        act = madmom.features.beats.RNNBeatProcessor()(drum_track)
        tempi = proc(act)
        if len(tempi) > 0:
            bpm = float(tempi[0][0])
            strength = float(tempi[0][1])
            if strength < 0.5:
                bpm_unreliable = True
            logger.info("bpm_madmom", bpm=bpm, strength=strength)
            return bpm, bpm_unreliable
    except Exception as e:
        logger.warning("bpm_madmom_failed", error=str(e))

    # Fallback to librosa
    try:
        tempo = librosa.beat.tempo(y=drum_track, sr=sr)
        bpm = float(tempo[0]) if hasattr(tempo, '__len__') else float(tempo)
        logger.info("bpm_librosa_fallback", bpm=bpm)
        # librosa fallback is less reliable
        bpm_unreliable = True
        return bpm, bpm_unreliable
    except Exception as e:
        logger.warning("bpm_librosa_failed", error=str(e))

    # Last resort
    logger.warning("bpm_defaulting_to_120")
    return 120.0, True

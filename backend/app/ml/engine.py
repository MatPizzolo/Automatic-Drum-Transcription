"""
ML Engine — orchestrates BS-Roformer drum separation and AST prediction.

Responsibilities:
- Singleton model loading for BS-Roformer and AST
- Strict Pydantic validation (PredictionResult)
- High-performance torchaudio tensor pipeline
- Minimal CPU/GPU memory transfers
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
import torch
import torchaudio
from transformers import ASTFeatureExtractor, ASTForAudioClassification

from app.core.config import settings
from app.ml.onset_detection import _detect_onsets_pytorch
from app.schemas.ml_contracts import PredictionResult
from app.utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Instrument label mapping (7 drum classes)
# Map from model output indices → our canonical instrument names
# ---------------------------------------------------------------------------
DRUM_CLASSES = ["snare", "hihat_closed", "hihat_open", "kick", "ride", "tom_high", "crash"]

# AudioSet class mapping to drum instruments
# Based on AudioSet ontology - map relevant audio event classes to drum types
AUDIOSET_TO_DRUM_MAP = {
    # Bass drum / Kick drum class indices
    "Bass drum": "kick",
    "Kick drum": "kick",
    # Snare drum class indices
    "Snare drum": "snare",
    # Hi-hat class indices (closed vs open based on label keywords)
    "Hi-hat": "hihat_closed",  # Default to closed
    "Closed hi-hat": "hihat_closed",
    "Open hi-hat": "hihat_open",
    "Cymbal": "hihat_closed",  # Generic cymbal defaults to closed hi-hat
    # Ride cymbal
    "Ride cymbal": "ride",
    # Crash cymbal
    "Crash cymbal": "crash",
    # Tom drums
    "Tom-tom": "tom_high",
    "Drum": "snare",  # Generic drum, default to snare
}

# Audio-separator singleton (loaded once per worker process)
_separator_instance = None
_separator_lock = threading.Lock()

# AST model singleton (loaded once per worker process)
_ast_model = None
_ast_feature_extractor = None
_ast_lock = threading.Lock()
_ast_device = None


def run_drum_separation(input_path: str, output_path: str) -> None:
    """
    Isolate drums from a full mix using BS-Roformer via audio-separator.

    Isolate drums from a full mix using BS-Roformer via audio-separator.
    """
    from audio_separator.separator import Separator
    import torch
    import tempfile

    global _separator_instance

    with _separator_lock:
        if _separator_instance is None:
            logger.info("separator_loading_model")
            
            # Initialize Separator with output_dir set to parent of output_path
            output_dir = str(Path(output_path).parent)
            _separator_instance = Separator(
                output_dir=output_dir,
                output_format="wav",
                output_single_stem="Drums",  # BS-Roformer uses "Drums" (capital D)
                model_file_dir=settings.MODEL_CACHE_DIR,  # Use existing cache dir
            )
            
            # Load BS-Roformer model
            _separator_instance.load_model(model_filename="model_bs_roformer_ep_368_sdr_12.9628.ckpt")
            logger.info("separator_model_loaded")
        else:
            logger.info("separator_using_cached_instance")

    logger.info("separator_processing", input=input_path)

    # audio-separator returns list of output file paths
    output_files = _separator_instance.separate(input_path)

    # Find the drums output file
    drums_output = None
    for f in output_files:
        if "Drums" in f or "drums" in f:
            drums_output = f
            break

    if drums_output is None or not Path(drums_output).exists():
        raise RuntimeError(f"Separator did not produce drums output. Got: {output_files}")

    # Load separated drums using torchaudio (keeps data as tensors)
    drums_tensor, sr = torchaudio.load(drums_output)

    # Convert to mono via tensor operations (avoid NumPy conversion)
    if drums_tensor.shape[0] > 1:
        # Stereo to mono: average across channels
        drums_mono = drums_tensor.mean(dim=0, keepdim=False)
    else:
        drums_mono = drums_tensor.squeeze(0)
    
    # Convert to NumPy only for final write (soundfile requires NumPy)
    drums_mono_np = drums_mono.cpu().numpy()

    # Atomic write (preserve existing pattern)
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav", dir=str(Path(output_path).parent))
    try:
        os.close(tmp_fd)
        sf.write(tmp_path, drums_mono_np, sr)
        os.replace(tmp_path, output_path)
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    finally:
        # Clean up separator's original output file
        if drums_output and Path(drums_output).exists() and drums_output != output_path:
            Path(drums_output).unlink()

    logger.info("separator_complete", output=output_path, samplerate=sr)

    # Memory cleanup (don't delete model — it's cached as singleton)
    del drums_tensor, drums_mono, drums_mono_np
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _load_ast_model():
    """
    Load Audio Spectrogram Transformer model (singleton pattern).
    Returns (model, feature_extractor, device).
    """
    global _ast_model, _ast_feature_extractor, _ast_device, _ast_lock

    with _ast_lock:
        if _ast_model is not None:
            logger.info("ast_using_cached_instance")
            return _ast_model, _ast_feature_extractor, _ast_device

        logger.info("ast_loading_model")
        
        # Determine device
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _ast_device = device
        
        try:
            # Load pre-trained AST model from HuggingFace
            model_name = "MIT/ast-finetuned-audioset-10-10-0.4593"
            
            _ast_feature_extractor = ASTFeatureExtractor.from_pretrained(
                model_name,
                cache_dir=settings.MODEL_CACHE_DIR,
            )
            
            _ast_model = ASTForAudioClassification.from_pretrained(
                model_name,
                cache_dir=settings.MODEL_CACHE_DIR,
            )
            
            _ast_model.to(device)
            _ast_model.eval()
            
            logger.info(
                "ast_model_loaded",
                model=model_name,
                device=device,
                num_labels=_ast_model.config.num_labels,
            )
            
        except Exception as e:
            logger.error("ast_model_load_failed", error=str(e))
            raise RuntimeError(
                f"Failed to load AST model. Ensure transformers and torch are installed. Error: {e}"
            ) from e
        
        return _ast_model, _ast_feature_extractor, _ast_device


def run_prediction(
    drums_path: str,
    user_bpm: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Run the full prediction pipeline on an isolated drum track.

    Returns dict with:
        detected_bpm, bpm_unreliable, duration_seconds, confidence_score,
        hit_summary, hits (list of {time, instrument, velocity})
    """
    logger.info("prediction_pipeline_start", drums_path=drums_path)

    # Load drum track using torchaudio (keeps data as tensors)
    drum_track_tensor, sr = torchaudio.load(drums_path)
    
    # Convert to mono via tensor operations
    if drum_track_tensor.shape[0] > 1:
        drum_track_tensor = drum_track_tensor.mean(dim=0, keepdim=True)
    
    # Calculate duration from tensor shape
    duration = drum_track_tensor.shape[1] / sr
    
    # Convert to NumPy only for BPM detection (madmom requires NumPy)
    drum_track_np = drum_track_tensor.squeeze(0).numpy()
    sr = int(sr)

    # --- BPM Detection ---
    bpm_unreliable = False
    if user_bpm is not None:
        detected_bpm = float(user_bpm)
        logger.info("bpm_user_supplied", bpm=detected_bpm)
    else:
        detected_bpm, bpm_unreliable = _detect_bpm(drum_track_np, sr)

    # --- Onset Detection ---
    hop_length = 1024
    if detected_bpm > 110:
        hop_length = 512

    # Detect onsets using PyTorch-native spectral flux method
    onset_samples = _detect_onsets_pytorch(
        drum_track_tensor.squeeze(0),
        sr,
        hop_length=hop_length,
        sensitivity=settings.ONSET_SENSITIVITY
    )

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

    logger.info(
        "onsets_detected_pytorch",
        total_onsets=len(onset_samples),
        sensitivity=settings.ONSET_SENSITIVITY
    )

    # Calculate window size based on 16th note duration
    sixteenth_duration = 60 / detected_bpm / 4
    thirty_second_duration = 60 / detected_bpm / 8
    window_size = int(sixteenth_duration * sr)
    padding = int(thirty_second_duration / 4 * sr)

    # Extract audio clips for each onset
    TARGET_LENGTH = 8820  # Fixed frame size for AST input normalization
    clips = []
    valid_onset_times = []

    # Convert tensor to NumPy for clip extraction (required for compatibility)
    drum_track_np_full = drum_track_tensor.squeeze(0).numpy()
    
    for onset in onset_samples:
        start = max(0, int(onset - padding))
        end = int(onset + window_size)
        clip = drum_track_np_full[start:end]

        if len(clip) == 0:
            continue

        # Resample to target length using tensor operations (avoid librosa)
        if len(clip) != TARGET_LENGTH:
            # Convert clip to tensor for resampling
            clip_tensor = torch.from_numpy(clip).unsqueeze(0)  # Add channel dim
            
            # Use torchaudio's Resample transform
            ratio = TARGET_LENGTH / len(clip)
            target_sr_temp = int(sr * ratio)
            resampler = torchaudio.transforms.Resample(orig_freq=sr, new_freq=target_sr_temp)
            clip_resampled = resampler(clip_tensor).squeeze(0)
            
            # Ensure exact target length via padding/truncation
            if clip_resampled.shape[0] > TARGET_LENGTH:
                clip = clip_resampled[:TARGET_LENGTH].numpy()
            elif clip_resampled.shape[0] < TARGET_LENGTH:
                zero_pad_length = TARGET_LENGTH - clip_resampled.shape[0]
                clip = torch.nn.functional.pad(clip_resampled, (0, zero_pad_length)).numpy()
            else:
                clip = clip_resampled.numpy()

        clips.append(clip)
        valid_onset_times.append(onset / sr)  # Convert samples to seconds

    if len(clips) == 0:
        return {
            "detected_bpm": int(detected_bpm),
            "bpm_unreliable": bpm_unreliable,
            "duration_seconds": round(duration, 2),
            "confidence_score": 0.0,
            "hit_summary": {},
            "hits": [],
        }

    # --- AST-Based Hit Classification ---
    # Process in batches to keep peak RAM bounded
    AST_BATCH_SIZE = 32  # Transformers are more memory-intensive than CNNs

    # Load AST model
    try:
        model, feature_extractor, device = _load_ast_model()
    except Exception as e:
        logger.error(
            "ast_model_unavailable",
            error=str(e),
            message="AST model failed to load. Ensure transformers and torch are installed."
        )
        raise RuntimeError(
            "Hit classification model not available. "
            "AST model could not be loaded. Check worker logs for details."
        ) from e

    # AST expects 16kHz audio - resample using torchaudio if necessary
    target_sr = 16000
    if sr != target_sr:
        logger.info("ast_resampling_audio", original_sr=sr, target_sr=target_sr)
        
        # Use torchaudio Resample transform (GPU-compatible)
        resampler = torchaudio.transforms.Resample(orig_freq=sr, new_freq=target_sr)
        clips_resampled = []
        
        for clip in clips:
            # Convert to tensor, resample, convert back to NumPy for feature extractor
            clip_tensor = torch.from_numpy(clip).unsqueeze(0)
            clip_resampled_tensor = resampler(clip_tensor).squeeze(0)
            clips_resampled.append(clip_resampled_tensor.numpy())
        
        clips = clips_resampled
        sr = target_sr

    # Process clips in batches through AST
    all_predictions = []
    
    for batch_start in range(0, len(clips), AST_BATCH_SIZE):
        batch_clips = clips[batch_start : batch_start + AST_BATCH_SIZE]
        
        # Prepare inputs using feature extractor
        inputs = feature_extractor(
            batch_clips,
            sampling_rate=sr,
            return_tensors="pt",
            padding=True,
        )
        
        # Move to device
        inputs = {k: v.to(device) for k, v in inputs.items()}
        
        # Run inference
        with torch.no_grad():
            outputs = model(**inputs)
            logits = outputs.logits
            # Apply sigmoid for multi-label classification (one onset can have multiple drums)
            probs = torch.sigmoid(logits).cpu().numpy()
        
        all_predictions.append(probs)
        
        del inputs, outputs, logits
        if device == "cuda":
            torch.cuda.empty_cache()

    # Free raw audio and clips — no longer needed
    del drum_track_tensor, drum_track_np, drum_track_np_full, clips, onset_samples

    # Concatenate all batch predictions
    pred_raw = np.concatenate(all_predictions, axis=0)
    del all_predictions

    # Map AudioSet predictions to drum instruments
    # Get model's label mapping
    id2label = model.config.id2label
    
    # For each onset, extract drum hits based on confidence threshold
    CONFIDENCE_THRESHOLD = 0.3
    results = []
    
    for i in range(pred_raw.shape[0]):
        onset_probs = pred_raw[i]
        onset_hits = {inst: 0.0 for inst in DRUM_CLASSES}
        
        # Get top predictions above threshold
        top_indices = np.where(onset_probs > CONFIDENCE_THRESHOLD)[0]
        
        for idx in top_indices:
            label = id2label.get(idx, "Unknown")
            confidence = onset_probs[idx]
            
            # Map AudioSet label to drum instrument
            drum_instrument = None
            for audioset_label, drum_name in AUDIOSET_TO_DRUM_MAP.items():
                if audioset_label.lower() in label.lower():
                    drum_instrument = drum_name
                    break
            
            # Update with highest confidence for each instrument
            if drum_instrument and confidence > onset_hits[drum_instrument]:
                onset_hits[drum_instrument] = confidence
        
        # Convert to binary array format (compatible with existing code)
        onset_result = np.array([onset_hits[inst] for inst in DRUM_CLASSES])
        results.append(onset_result)
    
    results = np.array(results)

    # --- Build hits list and summary ---
    hits: List[Dict[str, Any]] = []
    hit_counts: Dict[str, int] = {name: 0 for name in DRUM_CLASSES}

    for i, onset_time in enumerate(valid_onset_times):
        for j, instrument in enumerate(DRUM_CLASSES):
            # AST outputs confidence values (0.0-1.0), not binary
            confidence = results[i][j]
            if confidence > 0.0:  # Only include detected instruments
                hits.append({
                    "time": round(float(onset_time), 4),
                    "instrument": instrument,
                    "velocity": round(confidence, 4),
                })
                hit_counts[instrument] += 1

    # Filter out instruments with zero hits
    hit_summary = {k: v for k, v in hit_counts.items() if v > 0}

    # --- Confidence Scoring ---
    # For multi-label predictions, use mean of all positive predictions
    positive_confidences = results[results > 0.0]
    if len(positive_confidences) > 0:
        mean_confidence = float(np.mean(positive_confidences))
        confidence_score = round(mean_confidence, 4)
    else:
        confidence_score = 0.0

    # Memory cleanup
    del pred_raw, results
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()

    logger.info(
        "prediction_complete",
        drums_path=drums_path,
        total_hits=len(hits),
        bpm=int(detected_bpm),
        confidence=confidence_score,
    )

    # Build raw prediction dict
    raw_prediction = {
        "detected_bpm": int(detected_bpm),
        "bpm_unreliable": bpm_unreliable,
        "duration_seconds": round(duration, 2),
        "confidence_score": confidence_score,
        "hit_summary": hit_summary,
        "hits": hits,
    }

    # Validate output against Pydantic schema before returning
    # This catches any schema violations early (e.g., unsorted hits, invalid BPM)
    try:
        validated = PredictionResult.model_validate(raw_prediction)
        logger.info(
            "prediction_validated",
            schema_version=validated.schema_version,
            model_version=validated.model_version,
        )
        # Return as dict for backward compatibility with worker.py
        return validated.model_dump()
    except Exception as e:
        logger.error(
            "prediction_validation_failed",
            error=str(e),
            message="ML output failed Pydantic validation - this indicates a bug in the pipeline"
        )
        raise RuntimeError(f"Prediction output validation failed: {e}") from e


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

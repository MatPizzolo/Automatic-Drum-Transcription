"""
ML Guardrails — Heuristic sanity checks for AI model outputs.

Transformers are powerful but occasionally fail spectacularly. This module
wraps ML predictions with algorithmic validation to catch:
- BPM hallucinations (counting 16th notes instead of quarter notes)
- Physically impossible polyphony (>4 simultaneous hits)
- Low-confidence noise predictions

These guardrails prevent downstream crashes in symusic's C++ bindings and
ensure musically plausible sheet music output.
"""

from typing import Dict, Any, List
from app.utils.logging import get_logger

logger = get_logger(__name__)


def apply_ml_guardrails(prediction: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply heuristic sanity checks to ML predictions before transcription.
    
    This function modifies the prediction dict in-place and returns it.
    
    Guardrails applied:
    1. BPM Doubling Detection - Halves BPM if > 200 (likely 16th note counting)
    2. Polyphony Limiter - Max 4 simultaneous hits (drummer has 4 limbs)
    3. Confidence Filter - Drops hits below minimum velocity threshold
    
    Args:
        prediction: Raw output dict from run_prediction() with keys:
                   detected_bpm, bpm_unreliable, hits, etc.
    
    Returns:
        Modified prediction dict with guardrails applied.
    
    Example:
        >>> result = run_prediction(drums_path)
        >>> result = apply_ml_guardrails(result)  # Apply sanity checks
        >>> validated = PredictionResult.model_validate(result)
    """
    
    # -------------------------------------------------------------------------
    # Guardrail 1: BPM Doubling Detection
    # -------------------------------------------------------------------------
    # Problem: Onset detection sometimes counts 16th notes instead of quarter notes
    # Solution: If BPM > 200, it's likely doubled - halve it
    # Rationale: Very few drum tracks exceed 200 BPM (extreme metal/EDM only)
    
    bpm = prediction["detected_bpm"]
    if bpm > 200:
        corrected_bpm = bpm // 2  # Integer division for clean BPM values
        logger.warning(
            "bpm_halved_by_guardrail",
            original_bpm=bpm,
            corrected_bpm=corrected_bpm,
            reason="BPM > 200 suggests 16th note counting instead of quarter notes"
        )
        prediction["detected_bpm"] = corrected_bpm
        prediction["bpm_unreliable"] = True  # Flag for user awareness
    
    # -------------------------------------------------------------------------
    # Guardrail 2: Polyphony Limiter (Max 4 Simultaneous Hits)
    # -------------------------------------------------------------------------
    # Problem: AST can predict 7+ simultaneous drum hits at same millisecond
    # Solution: Group hits by 10ms buckets, keep top 4 by velocity
    # Rationale: Drummer has 4 limbs (2 hands, 2 feet) - physical constraint
    
    hits = prediction["hits"]
    cleaned_hits = []
    
    # Group hits by time window (10ms tolerance for "simultaneous")
    # 10ms = typical human timing precision for "same moment"
    time_groups: Dict[int, List[Dict[str, Any]]] = {}
    
    for hit in hits:
        time_bucket = round(hit["time"] * 100)  # Convert to 10ms buckets
        if time_bucket not in time_groups:
            time_groups[time_bucket] = []
        time_groups[time_bucket].append(hit)
    
    # Process each time bucket
    total_dropped = 0
    for time_bucket, simultaneous_hits in time_groups.items():
        if len(simultaneous_hits) > 4:
            # Keep top 4 hits by velocity (highest confidence predictions)
            sorted_hits = sorted(
                simultaneous_hits,
                key=lambda h: h["velocity"],
                reverse=True
            )
            kept = sorted_hits[:4]
            dropped = len(simultaneous_hits) - 4
            total_dropped += dropped
            
            logger.warning(
                "polyphony_limited_by_guardrail",
                time_seconds=time_bucket / 100.0,
                original_count=len(simultaneous_hits),
                kept_count=4,
                dropped_count=dropped,
                reason="Drummer only has 4 limbs - physically impossible polyphony"
            )
            cleaned_hits.extend(kept)
        else:
            cleaned_hits.extend(simultaneous_hits)
    
    if total_dropped > 0:
        logger.info(
            "polyphony_guardrail_summary",
            total_hits_dropped=total_dropped,
            original_hit_count=len(hits),
            final_hit_count=len(cleaned_hits)
        )
    
    prediction["hits"] = cleaned_hits
    
    # -------------------------------------------------------------------------
    # Guardrail 3: Minimum Confidence/Velocity Filter
    # -------------------------------------------------------------------------
    # Problem: AST outputs low-confidence "ghost notes" that pollute sheet music
    # Solution: Drop hits below minimum velocity threshold
    # Rationale: Velocity < 0.15 is typically noise or model uncertainty
    
    MIN_VELOCITY = 0.15  # Empirically tuned threshold
    original_count = len(prediction["hits"])
    
    prediction["hits"] = [
        h for h in prediction["hits"]
        if h["velocity"] >= MIN_VELOCITY
    ]
    
    filtered_count = original_count - len(prediction["hits"])
    
    if filtered_count > 0:
        logger.info(
            "low_confidence_hits_filtered",
            filtered_count=filtered_count,
            threshold=MIN_VELOCITY,
            remaining_hits=len(prediction["hits"])
        )
    
    # -------------------------------------------------------------------------
    # Recalculate hit_summary after guardrails
    # -------------------------------------------------------------------------
    # hit_summary must match the cleaned hits list for Pydantic validation
    
    hit_counts: Dict[str, int] = {}
    for hit in prediction["hits"]:
        instrument = hit["instrument"]
        hit_counts[instrument] = hit_counts.get(instrument, 0) + 1
    
    # Only include instruments with non-zero counts
    prediction["hit_summary"] = {k: v for k, v in hit_counts.items() if v > 0}
    
    # Recalculate confidence score (mean of remaining hits)
    if len(prediction["hits"]) > 0:
        total_velocity = sum(h["velocity"] for h in prediction["hits"])
        prediction["confidence_score"] = round(
            total_velocity / len(prediction["hits"]),
            4
        )
    else:
        prediction["confidence_score"] = 0.0
    
    logger.info(
        "guardrails_applied",
        final_hit_count=len(prediction["hits"]),
        final_confidence=prediction["confidence_score"],
        bpm=prediction["detected_bpm"]
    )
    
    return prediction

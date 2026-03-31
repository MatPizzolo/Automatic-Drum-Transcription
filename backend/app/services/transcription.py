"""
Transcription service — builds sheet music from predicted hits using symusic.

Converts AST hit predictions to quantized MIDI sheet music
with strict Pydantic typing.
"""

from typing import Any, Dict, List, Union

import symusic

from app.schemas.ml_contracts import DrumHit
from app.utils.logging import get_logger

logger = get_logger(__name__)

# Mapping from our canonical instrument names → General MIDI percussion note numbers
DRUM_MIDI_MAP = {
    "kick": 36,           # Bass Drum 1
    "snare": 38,          # Acoustic Snare
    "hihat_closed": 42,   # Closed Hi-Hat
    "hihat_open": 46,     # Open Hi-Hat
    "ride": 51,           # Ride Cymbal 1
    "crash": 49,          # Crash Cymbal 1
    "tom_high": 50,       # High Tom
    "tom_mid": 47,        # Low-Mid Tom
    "tom_low": 45,        # Low Tom
}


def build_sheet_music(
    hits: Union[List[DrumHit], List[Dict[str, Any]]],
    bpm: int,
    title: str = "Drum Sheet Music",
    beats_per_measure: int = 4,
    note_value: int = 4,
) -> symusic.Score:
    """
    Build a symusic Score from a list of drum hits.

    Args:
        hits: List of DrumHit Pydantic models or dicts with keys:
              {time: float (seconds), instrument: str, velocity: float}
        bpm: Tempo in beats per minute
        title: Score title for metadata
        beats_per_measure: Time signature numerator (default 4/4)
        note_value: Time signature denominator (default 4/4)

    Returns:
        symusic.Score object with proper MIDI percussion notation.
        
    Note:
        Accepts both Pydantic DrumHit objects and raw dicts for backward
        compatibility during migration. New code should use DrumHit objects.
    """
    logger.info(
        "transcription_start",
        total_hits=len(hits),
        bpm=bpm,
        title=title,
    )

    # Create symusic Score with standard MIDI resolution
    score = symusic.Score(ticks_per_quarter=480)
    
    # Add tempo (quarter notes per minute)
    score.tempos.append(symusic.Tempo(time=0, qpm=bpm))
    
    # Add time signature
    score.time_signatures.append(symusic.TimeSignature(
        time=0,
        numerator=beats_per_measure,
        denominator=note_value
    ))

    # Create drum track (MIDI Channel 10 for percussion)
    drum_track = symusic.Track(
        name="Drums",
        program=0,
        is_drum=True  # Critical: marks track as percussion
    )

    if not hits:
        score.tracks.append(drum_track)
        logger.info("transcription_complete", total_notes=0, total_events=0)
        return score

    # Sort hits by time
    # Handle both Pydantic DrumHit objects and raw dicts
    hits_sorted = sorted(hits, key=lambda h: h.time if isinstance(h, DrumHit) else h["time"])

    # Track quantization drift for each note
    quantization_drifts = []  # Store drift in milliseconds for each note

    # Convert hits to symusic Notes
    for hit in hits_sorted:
        # Extract fields (support both Pydantic and dict)
        if isinstance(hit, DrumHit):
            time_seconds = hit.time
            instrument = hit.instrument
            velocity_raw = hit.velocity
        else:
            time_seconds = hit["time"]
            instrument = hit["instrument"]
            velocity_raw = hit["velocity"]
        
        # Convert time to ticks (symusic uses integer tick-based timing)
        # Formula: ticks = seconds * (bpm / 60.0) * ticks_per_quarter
        time_ticks_original = time_seconds * (bpm / 60.0) * score.ticks_per_quarter
        time_ticks = int(time_ticks_original)
        
        # Map instrument to MIDI note number
        midi_note = DRUM_MIDI_MAP.get(instrument, 38)  # Default to snare
        
        # Convert velocity (0.0-1.0 float) to MIDI velocity (0-127 int)
        velocity_midi = int(min(127, max(1, velocity_raw * 127)))
        
        # Create Note object with eighth note duration
        note = symusic.Note(
            time=time_ticks,
            duration=score.ticks_per_quarter // 2,  # Eighth note duration
            pitch=midi_note,
            velocity=velocity_midi
        )
        
        drum_track.notes.append(note)
        
        # Store original unquantized time for drift calculation
        note._original_time_ticks = time_ticks_original

    # Apply symusic's native quantization to 16th note grid
    quantize_unit = score.ticks_per_quarter // 4  # 16th note
    
    # Calculate quantization drift for each note
    for note in drum_track.notes:
        original_time = getattr(note, '_original_time_ticks', note.time)
        quantized_time = round(note.time / quantize_unit) * quantize_unit
        
        # Calculate drift in ticks
        drift_ticks = abs(quantized_time - original_time)
        
        # Convert drift to milliseconds
        # Formula: ms = (ticks / ticks_per_quarter) * (60000 / bpm)
        drift_ms = (drift_ticks / score.ticks_per_quarter) * (60000 / bpm)
        quantization_drifts.append(drift_ms)
        
        # Apply quantization
        note.time = quantized_time
    
    # Sort notes by time (symusic requires sorted notes)
    drum_track.notes.sort(key=lambda n: n.time)

    # Add track to score
    score.tracks.append(drum_track)

    # Calculate and log quantization drift metrics
    if quantization_drifts:
        avg_drift_ms = sum(quantization_drifts) / len(quantization_drifts)
        max_drift_ms = max(quantization_drifts)
        
        logger.info(
            "quantization_applied",
            avg_drift_ms=round(avg_drift_ms, 2),
            max_drift_ms=round(max_drift_ms, 2),
            total_notes=len(drum_track.notes),
            message=f"Average timing error from quantization: {avg_drift_ms:.2f}ms"
        )
    
    logger.info(
        "transcription_complete",
        total_notes=len(drum_track.notes),
        total_events=len(hits_sorted),
    )

    return score

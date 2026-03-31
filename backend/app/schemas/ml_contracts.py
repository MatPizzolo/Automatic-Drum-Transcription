"""
ML Pipeline Data Contracts — Strict Pydantic models for ML stage outputs.

These models enforce type safety and validation between pipeline stages:
- AST model output → Guardrails → Transcription
- Prevents runtime crashes from malformed ML predictions
- Enables schema versioning for model upgrades
"""

from typing import List, Dict
from pydantic import BaseModel, Field, field_validator


class DrumHit(BaseModel):
    """
    Single drum hit prediction from AST model.
    
    Represents one detected drum strike with timing, instrument classification,
    and confidence/velocity information.
    """
    time: float = Field(
        ge=0.0,
        description="Time in seconds from start of audio"
    )
    instrument: str = Field(
        pattern="^(kick|snare|hihat_closed|hihat_open|ride|crash|tom_high|tom_mid|tom_low)$",
        description="Drum instrument classification"
    )
    velocity: float = Field(
        ge=0.0,
        le=1.0,
        description="Hit velocity/confidence (0.0-1.0)"
    )

    model_config = {"frozen": True}  # Immutable after creation


class PredictionResult(BaseModel):
    """
    Complete output contract from run_prediction() ML pipeline stage.
    
    This model enforces:
    - Valid BPM range (40-300)
    - Confidence scores in [0.0, 1.0]
    - Chronologically sorted hits (required for quantization)
    - Schema versioning for backward compatibility
    """
    schema_version: str = Field(
        default="1.0",
        description="Schema version for backward compatibility tracking"
    )
    model_version: str = Field(
        default="MIT/ast-finetuned-audioset-10-10-0.4593",
        description="ML model identifier for reproducibility"
    )
    detected_bpm: int = Field(
        ge=40,
        le=300,
        description="Detected tempo in beats per minute"
    )
    bpm_unreliable: bool = Field(
        description="Flag indicating low confidence in BPM detection"
    )
    duration_seconds: float = Field(
        ge=0.0,
        description="Total audio duration in seconds"
    )
    confidence_score: float = Field(
        ge=0.0,
        le=1.0,
        description="Overall prediction confidence (mean of all hits)"
    )
    hit_summary: Dict[str, int] = Field(
        description="Count of hits per instrument type"
    )
    hits: List[DrumHit] = Field(
        description="Chronologically sorted list of detected drum hits"
    )

    @field_validator('hits')
    @classmethod
    def validate_hits_sorted(cls, v: List[DrumHit]) -> List[DrumHit]:
        """
        Ensure hits are sorted by time for downstream processing.
        
        Quantization and MIDI export require chronological ordering.
        Raises ValueError if hits are out of order.
        """
        if len(v) > 1:
            times = [hit.time for hit in v]
            if times != sorted(times):
                raise ValueError(
                    "Hits must be sorted chronologically by time. "
                    f"Found out-of-order sequence at indices with times: {times[:5]}..."
                )
        return v

    @field_validator('hit_summary')
    @classmethod
    def validate_hit_summary_matches_hits(cls, v: Dict[str, int], info) -> Dict[str, int]:
        """
        Validate that hit_summary counts match actual hits list.
        
        This catches data corruption or incomplete processing.
        """
        if 'hits' in info.data:
            hits = info.data['hits']
            actual_counts = {}
            for hit in hits:
                actual_counts[hit.instrument] = actual_counts.get(hit.instrument, 0) + 1
            
            # Verify summary matches reality
            for instrument, count in v.items():
                if actual_counts.get(instrument, 0) != count:
                    raise ValueError(
                        f"hit_summary mismatch for {instrument}: "
                        f"summary says {count}, but found {actual_counts.get(instrument, 0)} hits"
                    )
        
        return v

    model_config = {"frozen": True}  # Immutable after validation

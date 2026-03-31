"""Unit tests for ML data contracts (Pydantic models).

DrumHit and PredictionResult enforce the schema contract between the AST
model output and the downstream transcription service.  These tests cover
field constraints, enum validation, sort-order enforcement, and the
hit_summary cross-validation.

No external dependencies — pure Python + Pydantic.
"""

import pytest
from pydantic import ValidationError

from app.schemas.ml_contracts import DrumHit, PredictionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hit(time=0.0, instrument="kick", velocity=0.8):
    return DrumHit(time=time, instrument=instrument, velocity=velocity)


def _result(**overrides):
    """Build a minimal valid PredictionResult, overriding fields as needed."""
    defaults = {
        "detected_bpm": 120,
        "bpm_unreliable": False,
        "duration_seconds": 10.0,
        "confidence_score": 0.8,
        "hit_summary": {"kick": 1},
        "hits": [_hit(0.0, "kick", 0.8)],
    }
    defaults.update(overrides)
    return PredictionResult(**defaults)


# ---------------------------------------------------------------------------
# DrumHit — field constraints
# ---------------------------------------------------------------------------

class TestDrumHitValidation:
    def test_valid_hit(self):
        h = _hit(0.5, "snare", 0.75)
        assert h.time == 0.5
        assert h.instrument == "snare"
        assert h.velocity == 0.75

    def test_time_must_be_non_negative(self):
        with pytest.raises(ValidationError):
            DrumHit(time=-0.001, instrument="kick", velocity=0.5)

    def test_time_zero_is_valid(self):
        h = DrumHit(time=0.0, instrument="kick", velocity=0.5)
        assert h.time == 0.0

    def test_velocity_below_zero_rejected(self):
        with pytest.raises(ValidationError):
            DrumHit(time=0.0, instrument="kick", velocity=-0.01)

    def test_velocity_above_one_rejected(self):
        with pytest.raises(ValidationError):
            DrumHit(time=0.0, instrument="kick", velocity=1.01)

    def test_velocity_zero_is_valid(self):
        h = DrumHit(time=0.0, instrument="kick", velocity=0.0)
        assert h.velocity == 0.0

    def test_velocity_one_is_valid(self):
        h = DrumHit(time=0.0, instrument="kick", velocity=1.0)
        assert h.velocity == 1.0

    def test_all_valid_instruments(self):
        instruments = [
            "kick", "snare", "hihat_closed", "hihat_open",
            "ride", "crash", "tom_high", "tom_mid", "tom_low",
        ]
        for inst in instruments:
            h = DrumHit(time=0.0, instrument=inst, velocity=0.5)
            assert h.instrument == inst

    def test_unknown_instrument_rejected(self):
        with pytest.raises(ValidationError):
            DrumHit(time=0.0, instrument="cowbell", velocity=0.5)

    def test_empty_instrument_rejected(self):
        with pytest.raises(ValidationError):
            DrumHit(time=0.0, instrument="", velocity=0.5)

    def test_frozen_model_immutable(self):
        h = _hit()
        with pytest.raises(Exception):
            h.time = 99.0


# ---------------------------------------------------------------------------
# PredictionResult — BPM constraints
# ---------------------------------------------------------------------------

class TestPredictionResultBPM:
    def test_valid_bpm(self):
        r = _result(detected_bpm=120)
        assert r.detected_bpm == 120

    def test_bpm_min_boundary(self):
        r = _result(detected_bpm=40)
        assert r.detected_bpm == 40

    def test_bpm_max_boundary(self):
        r = _result(detected_bpm=300)
        assert r.detected_bpm == 300

    def test_bpm_below_40_rejected(self):
        with pytest.raises(ValidationError):
            _result(detected_bpm=39)

    def test_bpm_above_300_rejected(self):
        with pytest.raises(ValidationError):
            _result(detected_bpm=301)


# ---------------------------------------------------------------------------
# PredictionResult — confidence_score constraints
# ---------------------------------------------------------------------------

class TestPredictionResultConfidence:
    def test_confidence_zero_valid(self):
        r = _result(
            confidence_score=0.0,
            hits=[],
            hit_summary={},
        )
        assert r.confidence_score == 0.0

    def test_confidence_one_valid(self):
        r = _result(confidence_score=1.0, hits=[_hit(0.0, "kick", 1.0)], hit_summary={"kick": 1})
        assert r.confidence_score == 1.0

    def test_confidence_above_one_rejected(self):
        with pytest.raises(ValidationError):
            _result(confidence_score=1.001)

    def test_confidence_negative_rejected(self):
        with pytest.raises(ValidationError):
            _result(confidence_score=-0.001)


# ---------------------------------------------------------------------------
# PredictionResult — hits sort-order enforcement
# ---------------------------------------------------------------------------

class TestHitsSortOrder:
    def test_sorted_hits_accepted(self):
        hits = [_hit(0.0), _hit(0.5), _hit(1.0)]
        r = _result(hits=hits, hit_summary={"kick": 3})
        assert len(r.hits) == 3

    def test_unsorted_hits_rejected(self):
        hits = [_hit(1.0), _hit(0.0)]  # out of order
        with pytest.raises(ValidationError, match="sorted chronologically"):
            _result(hits=hits, hit_summary={"kick": 2})

    def test_single_hit_always_sorted(self):
        r = _result(hits=[_hit(5.0)], hit_summary={"kick": 1})
        assert r.hits[0].time == 5.0

    def test_ties_in_time_are_allowed(self):
        """Simultaneous hits (same time) are valid — order is ambiguous but not wrong."""
        hits = [
            DrumHit(time=0.5, instrument="kick",  velocity=0.9),
            DrumHit(time=0.5, instrument="snare", velocity=0.8),
        ]
        r = _result(hits=hits, hit_summary={"kick": 1, "snare": 1})
        assert len(r.hits) == 2


# ---------------------------------------------------------------------------
# PredictionResult — hit_summary cross-validation
# ---------------------------------------------------------------------------

class TestHitSummaryValidation:
    def test_matching_summary_accepted(self):
        hits = [_hit(0.0, "kick"), _hit(0.5, "snare")]
        r = _result(hits=hits, hit_summary={"kick": 1, "snare": 1})
        assert r.hit_summary == {"kick": 1, "snare": 1}

    def test_wrong_count_in_summary_rejected(self):
        hits = [_hit(0.0, "kick")]
        with pytest.raises(ValidationError, match="hit_summary mismatch"):
            _result(hits=hits, hit_summary={"kick": 2})  # claims 2 but only 1 hit

    def test_extra_instrument_in_summary_rejected(self):
        hits = [_hit(0.0, "kick")]
        with pytest.raises(ValidationError):
            # snare in summary but no snare in hits
            _result(hits=hits, hit_summary={"kick": 1, "snare": 1})

    def test_empty_hits_requires_empty_summary(self):
        r = _result(hits=[], hit_summary={}, confidence_score=0.0)
        assert r.hit_summary == {}

    def test_multi_hit_same_instrument_counted_correctly(self):
        hits = [_hit(0.0, "kick"), _hit(0.5, "kick"), _hit(1.0, "kick")]
        r = _result(hits=hits, hit_summary={"kick": 3})
        assert r.hit_summary["kick"] == 3

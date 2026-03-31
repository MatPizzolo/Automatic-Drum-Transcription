"""Unit tests for ML guardrails.

Guardrails are heuristic safety nets that prevent bad model output from
crashing the downstream symusic C++ bindings or producing unusable sheet music.
These tests cover every guardrail rule with boundary conditions.

No special dependencies — pure Python + the guardrails module.
"""

import copy
import pytest
from app.ml.guardrails import apply_ml_guardrails


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prediction(bpm=120, hits=None, bpm_unreliable=False):
    """Build a minimal prediction dict for guardrail testing."""
    if hits is None:
        hits = []
    hit_summary = {}
    for h in hits:
        hit_summary[h["instrument"]] = hit_summary.get(h["instrument"], 0) + 1
    confidence = (
        round(sum(h["velocity"] for h in hits) / len(hits), 4) if hits else 0.0
    )
    return {
        "detected_bpm": bpm,
        "bpm_unreliable": bpm_unreliable,
        "duration_seconds": 10.0,
        "confidence_score": confidence,
        "hit_summary": hit_summary,
        "hits": hits,
    }


def _hit(time=0.0, instrument="kick", velocity=0.8):
    return {"time": time, "instrument": instrument, "velocity": velocity}


# ---------------------------------------------------------------------------
# Guardrail 1: BPM Doubling Detection
# ---------------------------------------------------------------------------

class TestBPMGuardrail:
    def test_bpm_above_200_is_halved(self):
        pred = _make_prediction(bpm=240)
        result = apply_ml_guardrails(pred)
        assert result["detected_bpm"] == 120

    def test_bpm_201_is_halved(self):
        """Boundary: 201 is strictly > 200, so it gets halved."""
        pred = _make_prediction(bpm=201)
        result = apply_ml_guardrails(pred)
        assert result["detected_bpm"] == 100

    def test_bpm_exactly_200_is_unchanged(self):
        """Boundary: 200 is not strictly > 200, so no halving."""
        pred = _make_prediction(bpm=200)
        result = apply_ml_guardrails(pred)
        assert result["detected_bpm"] == 200

    def test_bpm_120_unchanged(self):
        pred = _make_prediction(bpm=120)
        result = apply_ml_guardrails(pred)
        assert result["detected_bpm"] == 120

    def test_bpm_40_unchanged(self):
        pred = _make_prediction(bpm=40)
        result = apply_ml_guardrails(pred)
        assert result["detected_bpm"] == 40

    def test_high_bpm_sets_bpm_unreliable_true(self):
        pred = _make_prediction(bpm=240, bpm_unreliable=False)
        result = apply_ml_guardrails(pred)
        assert result["bpm_unreliable"] is True

    def test_normal_bpm_does_not_change_unreliable_flag(self):
        """A normal BPM must not override an already-set unreliable flag."""
        pred = _make_prediction(bpm=120, bpm_unreliable=True)
        result = apply_ml_guardrails(pred)
        assert result["bpm_unreliable"] is True

    def test_integer_division_preserves_clean_bpm(self):
        """Odd BPM 241 → 241//2 = 120 (integer division)."""
        pred = _make_prediction(bpm=241)
        result = apply_ml_guardrails(pred)
        assert result["detected_bpm"] == 120


# ---------------------------------------------------------------------------
# Guardrail 2: Polyphony Limiter
# ---------------------------------------------------------------------------

class TestPolyphonyGuardrail:
    def test_four_simultaneous_hits_pass_through(self):
        hits = [_hit(0.0, "kick"), _hit(0.0, "snare"), _hit(0.0, "hihat_closed"), _hit(0.0, "crash")]
        pred = _make_prediction(hits=hits)
        result = apply_ml_guardrails(pred)
        assert len(result["hits"]) == 4

    def test_five_simultaneous_hits_capped_at_four(self):
        hits = [
            _hit(0.0, "kick",         velocity=0.9),
            _hit(0.0, "snare",        velocity=0.8),
            _hit(0.0, "hihat_closed", velocity=0.7),
            _hit(0.0, "crash",        velocity=0.6),
            _hit(0.0, "ride",         velocity=0.5),  # lowest — should be dropped
        ]
        pred = _make_prediction(hits=hits)
        result = apply_ml_guardrails(pred)
        assert len(result["hits"]) == 4

    def test_polyphony_keeps_highest_velocity(self):
        """When 5 simultaneous hits are reduced to 4, the lowest-velocity hit is dropped."""
        hits = [
            _hit(0.0, "kick",         velocity=0.9),
            _hit(0.0, "snare",        velocity=0.8),
            _hit(0.0, "hihat_closed", velocity=0.7),
            _hit(0.0, "crash",        velocity=0.6),
            _hit(0.0, "ride",         velocity=0.2),  # lowest → dropped
        ]
        pred = _make_prediction(hits=hits)
        result = apply_ml_guardrails(pred)
        remaining_instruments = {h["instrument"] for h in result["hits"]}
        assert "ride" not in remaining_instruments

    def test_hits_at_different_times_not_grouped(self):
        """Hits separated by >10 ms are in different time buckets — polyphony doesn't apply."""
        hits = [_hit(t, "kick") for t in [0.00, 0.10, 0.20, 0.30, 0.40, 0.50]]
        pred = _make_prediction(hits=hits)
        result = apply_ml_guardrails(pred)
        assert len(result["hits"]) == 6

    def test_hits_within_10ms_grouped_together(self):
        """Hits within 10 ms of each other share a time bucket.

        The guardrail uses round(time * 100) for bucket assignment, so all
        times that round to the same integer land in the same bucket.
        Times 0.000–0.004 all round to bucket 0 → 5 hits in one bucket → capped to 4.
        """
        hits = [
            _hit(0.000, "kick",         velocity=0.9),
            _hit(0.001, "snare",        velocity=0.8),
            _hit(0.002, "hihat_closed", velocity=0.7),
            _hit(0.003, "crash",        velocity=0.6),
            _hit(0.004, "ride",         velocity=0.3),
        ]
        pred = _make_prediction(hits=hits)
        result = apply_ml_guardrails(pred)
        assert len(result["hits"]) <= 4


# ---------------------------------------------------------------------------
# Guardrail 3: Confidence / Velocity Filter
# ---------------------------------------------------------------------------

class TestConfidenceGuardrail:
    def test_hits_below_015_are_dropped(self):
        hits = [_hit(0.0, "kick", velocity=0.14)]
        pred = _make_prediction(hits=hits)
        result = apply_ml_guardrails(pred)
        assert len(result["hits"]) == 0

    def test_hits_at_exactly_015_are_kept(self):
        hits = [_hit(0.0, "kick", velocity=0.15)]
        pred = _make_prediction(hits=hits)
        result = apply_ml_guardrails(pred)
        assert len(result["hits"]) == 1

    def test_hits_above_015_are_kept(self):
        hits = [_hit(0.0, "kick", velocity=0.9), _hit(0.5, "snare", velocity=0.8)]
        pred = _make_prediction(hits=hits)
        result = apply_ml_guardrails(pred)
        assert len(result["hits"]) == 2

    def test_mixed_velocities_partial_filter(self):
        hits = [
            _hit(0.0, "kick",  velocity=0.9),
            _hit(0.5, "snare", velocity=0.1),  # below threshold
            _hit(1.0, "kick",  velocity=0.8),
        ]
        pred = _make_prediction(hits=hits)
        result = apply_ml_guardrails(pred)
        assert len(result["hits"]) == 2
        assert all(h["velocity"] >= 0.15 for h in result["hits"])

    def test_all_hits_filtered_returns_empty_list(self):
        hits = [_hit(t, "kick", velocity=0.05) for t in [0.0, 0.5, 1.0]]
        pred = _make_prediction(hits=hits)
        result = apply_ml_guardrails(pred)
        assert result["hits"] == []
        assert result["confidence_score"] == 0.0


# ---------------------------------------------------------------------------
# Summary + Confidence recalculation
# ---------------------------------------------------------------------------

class TestSummaryRecalculation:
    def test_hit_summary_updated_after_filter(self):
        hits = [
            _hit(0.0, "kick",  velocity=0.9),
            _hit(0.5, "snare", velocity=0.1),  # filtered
            _hit(1.0, "kick",  velocity=0.8),
        ]
        pred = _make_prediction(hits=hits)
        result = apply_ml_guardrails(pred)
        assert result["hit_summary"] == {"kick": 2}

    def test_confidence_score_recalculated(self):
        hits = [_hit(0.0, "kick", velocity=0.8), _hit(0.5, "snare", velocity=0.6)]
        pred = _make_prediction(hits=hits)
        result = apply_ml_guardrails(pred)
        expected = round((0.8 + 0.6) / 2, 4)
        assert result["confidence_score"] == expected

    def test_empty_hits_returns_zero_confidence(self):
        pred = _make_prediction(hits=[])
        result = apply_ml_guardrails(pred)
        assert result["confidence_score"] == 0.0
        assert result["hit_summary"] == {}

    def test_original_dict_is_modified_in_place(self):
        """apply_ml_guardrails modifies and returns the same dict."""
        pred = _make_prediction(bpm=120)
        result = apply_ml_guardrails(pred)
        assert result is pred

    def test_no_mutation_to_passing_hits(self):
        """Hits that pass all guardrails must be returned unchanged."""
        hits = [
            _hit(0.0, "kick",  velocity=0.9),
            _hit(0.5, "snare", velocity=0.8),
        ]
        pred = _make_prediction(hits=copy.deepcopy(hits))
        result = apply_ml_guardrails(pred)
        for orig, kept in zip(hits, result["hits"]):
            assert orig == kept

"""Unit tests for the transcription service.

build_sheet_music converts hit dicts to a symusic.Score.  Tests verify:
- MIDI note mapping (kick=36, snare=38, etc.)
- BPM → tempo event
- Velocity scaling (0.0–1.0 float → 1–127 MIDI int)
- Note sort order in the output track
- Empty-hit edge case
- Dict and Pydantic DrumHit input types both accepted

Requires symusic — skip if not installed.
"""

import pytest

symusic = pytest.importorskip("symusic")

from app.services.transcription import build_sheet_music, DRUM_MIDI_MAP


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hit(time=0.0, instrument="kick", velocity=0.8):
    return {"time": time, "instrument": instrument, "velocity": velocity}


# ---------------------------------------------------------------------------
# Basic structure
# ---------------------------------------------------------------------------

class TestBuildSheetMusicStructure:
    def test_returns_symusic_score(self):
        score = build_sheet_music([_hit()], bpm=120)
        assert isinstance(score, symusic.Score)

    def test_score_has_one_drum_track(self):
        score = build_sheet_music([_hit()], bpm=120)
        assert len(score.tracks) == 1
        assert score.tracks[0].is_drum is True

    def test_empty_hits_still_returns_score(self):
        score = build_sheet_music([], bpm=120)
        assert isinstance(score, symusic.Score)
        assert len(score.tracks) == 1
        assert len(score.tracks[0].notes) == 0

    def test_tempo_event_added(self):
        bpm = 140
        score = build_sheet_music([_hit()], bpm=bpm)
        assert len(score.tempos) >= 1
        assert score.tempos[0].qpm == bpm

    def test_time_signature_event_added(self):
        score = build_sheet_music([_hit()], bpm=120)
        assert len(score.time_signatures) >= 1
        ts = score.time_signatures[0]
        assert ts.numerator == 4
        assert ts.denominator == 4


# ---------------------------------------------------------------------------
# MIDI note mapping
# ---------------------------------------------------------------------------

class TestMIDINoteMapping:
    @pytest.mark.parametrize("instrument,expected_pitch", [
        ("kick",         36),
        ("snare",        38),
        ("hihat_closed", 42),
        ("hihat_open",   46),
        ("ride",         51),
        ("crash",        49),
        ("tom_high",     50),
        ("tom_mid",      47),
        ("tom_low",      45),
    ])
    def test_instrument_maps_to_correct_midi_pitch(self, instrument, expected_pitch):
        score = build_sheet_music([_hit(0.0, instrument)], bpm=120)
        note = score.tracks[0].notes[0]
        assert note.pitch == expected_pitch

    def test_unknown_instrument_defaults_to_snare(self):
        """Instruments not in DRUM_MIDI_MAP fall back to snare (38)."""
        hit = {"time": 0.0, "instrument": "cowbell", "velocity": 0.5}
        score = build_sheet_music([hit], bpm=120)
        note = score.tracks[0].notes[0]
        assert note.pitch == 38

    def test_drum_midi_map_covers_all_valid_instruments(self):
        expected = {
            "kick", "snare", "hihat_closed", "hihat_open",
            "ride", "crash", "tom_high", "tom_mid", "tom_low",
        }
        assert set(DRUM_MIDI_MAP.keys()) == expected


# ---------------------------------------------------------------------------
# Velocity scaling
# ---------------------------------------------------------------------------

class TestVelocityScaling:
    def test_max_velocity_maps_to_127(self):
        score = build_sheet_music([_hit(velocity=1.0)], bpm=120)
        assert score.tracks[0].notes[0].velocity == 127

    def test_zero_velocity_maps_to_at_least_one(self):
        """MIDI velocity 0 is note-off — we clamp to 1."""
        score = build_sheet_music([_hit(velocity=0.0)], bpm=120)
        assert score.tracks[0].notes[0].velocity >= 1

    def test_midpoint_velocity_is_in_range(self):
        score = build_sheet_music([_hit(velocity=0.5)], bpm=120)
        v = score.tracks[0].notes[0].velocity
        assert 1 <= v <= 127


# ---------------------------------------------------------------------------
# Note ordering
# ---------------------------------------------------------------------------

class TestNoteOrdering:
    def test_notes_sorted_by_time(self):
        hits = [_hit(1.0, "kick"), _hit(0.0, "snare"), _hit(0.5, "crash")]
        score = build_sheet_music(hits, bpm=120)
        times = [n.time for n in score.tracks[0].notes]
        assert times == sorted(times)

    def test_multiple_hits_all_added(self):
        hits = [_hit(t * 0.5, "kick") for t in range(8)]
        score = build_sheet_music(hits, bpm=120)
        assert len(score.tracks[0].notes) == 8


# ---------------------------------------------------------------------------
# Pydantic DrumHit input type
# ---------------------------------------------------------------------------

class TestDrumHitPydanticInput:
    def test_accepts_pydantic_drum_hit_objects(self):
        from app.schemas.ml_contracts import DrumHit
        hits = [DrumHit(time=0.0, instrument="kick", velocity=0.9)]
        score = build_sheet_music(hits, bpm=120)
        assert len(score.tracks[0].notes) == 1
        assert score.tracks[0].notes[0].pitch == 36

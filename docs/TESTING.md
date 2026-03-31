# Testing Guide

DrumScribe has a layered test suite covering every stage of the pipeline — from
pure-Python guardrail logic up through API contracts and full pipeline regression
tests.  The default `make test` target runs fast, dependency-free unit tests only;
heavier tests are opt-in via explicit markers.

---

## Quick Start

```bash
# 1. Install test dependencies (one-time)
cd backend
pip install -r requirements-test.txt

# 2. Run unit tests from the project root
make test
```

---

## Test Targets

| Target | What it runs | Requires |
|---|---|---|
| `make test` | All unit tests (alias for `make test-unit`) | Python deps only |
| `make test-unit` | `tests/unit/` — no I/O, no services | Python deps only |
| `make test-integration` | `tests/integration/` + `tests/regression/` | PostgreSQL + Redis running |
| `make test-coverage` | Unit tests + HTML coverage report | Python deps only |
| `make test-frontend` | Frontend lint check | Node.js |

---

## Test Structure

```
backend/tests/
├── conftest.py                  # Shared fixtures (sample_audio, prediction_dict, tmp_storage)
├── unit/                        # Fast, no I/O
│   ├── test_guardrails.py       # ML guardrails (BPM, polyphony, velocity filter)
│   ├── test_ml_contracts.py     # Pydantic DrumHit + PredictionResult validation
│   ├── test_onset_detection.py  # PyTorch onset detection (impulse / silence)
│   ├── test_audio_ingestion.py  # Audio validation + YouTube download (mocked)
│   ├── test_transcription.py    # symusic score building, MIDI note mapping
│   ├── test_processors.py       # BPM detection output contract (mocked engine)
│   ├── test_config.py           # Settings defaults and environment overrides
│   └── test_validation.py       # JobCreate schema — URL + BPM field validation
├── integration/
│   └── test_api.py              # FastAPI endpoints via TestClient
└── regression/
    └── test_golden.py           # Full pipeline smoke test + storage backend
```

---

## Pytest Markers

Markers are defined in `backend/pyproject.toml`.  The default `addopts` excludes
`integration` and `slow` so `pytest` (or `make test`) is always fast.

| Marker | Description | Run with |
|---|---|---|
| `unit` | Pure unit tests — no I/O, no external services | default |
| `integration` | Requires live PostgreSQL and Redis | `make test-integration` |
| `slow` | Downloads ML model weights or runs real inference | `-m slow` |
| `e2e` | Full end-to-end browser tests via Playwright | `-m e2e` |

Run a specific marker subset directly:

```bash
cd backend
# Only slow tests (real model inference)
pytest -m slow -v

# Only integration tests
pytest -m integration -v

# Everything (unit + integration + slow — CI does NOT do this)
pytest -m "" -v
```

---

## Running Specific Test Files

```bash
cd backend

# One file
pytest tests/unit/test_guardrails.py -v

# One class
pytest tests/unit/test_ml_contracts.py::TestDrumHitValidation -v

# One test
pytest tests/unit/test_guardrails.py::TestBPMGuardrail::test_bpm_above_200_is_halved -v
```

---

## Coverage

```bash
make test-coverage
# Opens backend/htmlcov/index.html — visual per-line coverage

# Or in-terminal summary only
cd backend
pytest tests/unit/ --cov=app --cov-report=term-missing
```

Coverage is tracked for `app/` only.  The `alembic/` directory and
`app/core/telemetry.py` are excluded (see `pyproject.toml`).

---

## Unit Test Details

### `test_guardrails.py` — ML Guardrails

Three guardrail rules, each with boundary-condition tests:

1. **BPM Doubling** — BPM > 200 is halved (integer division); `bpm_unreliable`
   flag is set.  Boundary: 200 is unchanged, 201 is halved.
2. **Polyphony Limiter** — Max 4 simultaneous hits per 10 ms time bucket.
   Lowest-velocity hits are dropped.
3. **Confidence Filter** — Hits with velocity < 0.15 are dropped.

After all rules run, `hit_summary` and `confidence_score` are recalculated.

### `test_ml_contracts.py` — Pydantic Contracts

- **DrumHit**: time ≥ 0, velocity in [0, 1], instrument must match the enum,
  model is frozen (immutable after creation).
- **PredictionResult**: BPM in [40, 300], confidence in [0, 1], hits must be
  chronologically sorted, `hit_summary` counts must match the actual hits list.

### `test_onset_detection.py` — PyTorch Onset Detection

Uses synthetic tensors (no audio files, no model weights):
- Pure silence → no onsets
- Sharp impulse → at least one onset detected
- Lower sensitivity → more onsets; higher sensitivity → fewer

Requires `torch` and `torchaudio`.  Tests are automatically skipped if
not installed (`pytest.importorskip`).

### `test_audio_ingestion.py` — Audio Validation

- **Happy path** (uses `sample_audio` conftest fixture): returns sample rate
  and duration.
- **Error cases**: missing file, invalid data, silent audio, too-short audio.
- **YouTube download**: fully mocked via `unittest.mock.patch` — no network
  calls.  Covers success, yt-dlp failure, timeout, and missing output file.

Requires `soundfile` for the happy-path tests (auto-skipped if absent).

### `test_transcription.py` — symusic Score Building

- All 9 instruments map to the correct General MIDI percussion note numbers
  (kick=36, snare=38, etc.).
- BPM produces a matching tempo event.
- Velocity (0.0–1.0) scales to MIDI (1–127).
- Notes are sorted by time in the output track.
- Both raw `dict` and Pydantic `DrumHit` inputs are accepted.

Requires `symusic` (auto-skipped if absent).

### `test_processors.py` — BPM Detection Contract

Tests the shape of `run_prediction()` output using mocks:
- `detected_bpm` is an `int` in [40, 300]
- `bpm_unreliable` is a `bool`
- All required keys are present
- `user_bpm` override is reflected in output

### `test_validation.py` — JobCreate Schema

YouTube URL regex validation (watch, shorts, embed, youtu.be) and BPM range
validation (40–300).  Pure Pydantic — no network or DB.

---

## Integration Tests

`tests/integration/test_api.py` hits the FastAPI app via `TestClient`.  Most
tests work without a real database (they test request validation and OpenAPI
schemas).  Tests that need PostgreSQL are marked `@pytest.mark.integration` and
are excluded from the default run.

To run integration tests locally:

```bash
# Start the services first
make up MODE=mvp

# Then run integration tests
make test-integration
```

---

## Regression Tests

`tests/regression/test_golden.py` covers:
- `build_sheet_music` with empty and non-empty hit lists
- `export_musicxml` — produces a valid non-empty XML file
- `LocalStorageBackend` — save, read, list, delete roundtrips
- `validate_audio_signal` — returns correct metadata for synthetic audio

These tests do not require a running database or ML model weights.

---

## Continuous Integration

The CI pipeline (`.github/workflows/ci.yml`) runs on every push and PR:

| Job | What it does |
|---|---|
| `compose-validate` | `docker compose config` on both compose files |
| `backend-test` | Unit + regression tests with coverage upload |
| `frontend-test` | Lint + optional type check |
| `docker-build` | Build all four Docker images |
| `security-scan` | Trivy CVE scan on API and worker images |

Only `unit` and non-`slow` tests run in CI.  Integration and slow tests require
infrastructure not available in the standard CI runner.

---

## Adding New Tests

1. Place unit tests in `backend/tests/unit/test_<module>.py`.
2. Use the shared fixtures from `conftest.py` (`sample_audio`, `prediction_dict`,
   `tmp_storage`, `sample_hits`) where applicable.
3. Mark tests that need live services with `@pytest.mark.integration`.
4. Mark tests that download model weights with `@pytest.mark.slow`.
5. Use `pytest.importorskip("libraryname")` at the top of test files or fixtures
   that have optional heavy dependencies — this skips the test gracefully instead
   of failing with an ImportError.

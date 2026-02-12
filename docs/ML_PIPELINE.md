# ML Pipeline

> **Source:** [`backend/app/ml/`](../backend/app/ml/) and [`backend/app/services/transcription.py`](../backend/app/services/transcription.py)
>
> **Based on:** [AnNOTEator](https://github.com/cb-42/AnNOTEator) — adapted for production with singleton model loading, structured outputs, and async task execution.

---

## Pipeline Overview

```
Audio File / YouTube URL
        │
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 1: Drum Separation (Demucs htdemucs)                     │
│  Full mix → isolated drum track                                 │
│  Queue: heavy-compute │ ~2-4 GB RAM │ GPU optional              │
└───────────────────────────┬─────────────────────────────────────┘
                            │ drums.wav
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 2: Hit Prediction (Keras CNN)                            │
│  BPM detection → onset detection → mel-spectrogram → classify   │
│  6 classes: kick, snare, hihat, ride, tom, crash                │
│  Queue: heavy-compute │ ~500 MB RAM                             │
└───────────────────────────┬─────────────────────────────────────┘
                            │ hits.json
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 3: Transcription (music21)                               │
│  Quantize hits → build notation → export MusicXML + PDF         │
│  Queue: default │ lightweight                                   │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                  sheet_music.musicxml
                  sheet_music.pdf
```

Each stage runs as a separate **Celery task**, chained together:

```python
ingest_audio → separate_drums → predict_hits → transcribe_and_export
```

Stages 1-2 run on the `heavy-compute` queue (concurrency=1, 4 GB RAM limit). Stages 3 runs on the `default` queue (concurrency=4, lightweight).

---

## Stage 1: Drum Separation

**File:** [`engine.py → run_drum_separation()`](../backend/app/ml/engine.py)

### Model: Demucs `htdemucs`

| Property | Value |
|----------|-------|
| **Architecture** | Hybrid Transformer Demucs |
| **Author** | Meta Research (Facebook AI) |
| **Source** | [facebookresearch/demucs](https://github.com/facebookresearch/demucs) |
| **Package** | `demucs==4.0.1` via PyPI |
| **Weight download** | `torch.hub` → GitHub Releases (automatic on first call) |
| **Weight cache** | `~/.cache/torch/hub/` inside the container |
| **Output stems** | drums, bass, other, vocals (index 0 = drums) |
| **Peak RAM** | ~1.5 GB (1 min) to ~3.5 GB (5 min audio) |

### How it works

1. **Load audio** at the model's native sample rate using `demucs.audio.AudioFile`
2. **Normalize** the waveform (zero-mean, unit-std)
3. **Apply the model** with `shifts=1`, `split=True`, `overlap=0.25` — splits long audio into overlapping chunks to manage memory
4. **Extract drums** — stem index 0 in htdemucs output order
5. **Convert to mono** via `librosa.to_mono()`
6. **Save atomically** — writes to a temp file, then `os.replace()` to prevent corrupt artifacts if the worker crashes mid-write

### Demucs is NOT from Hugging Face

The `demucs` Python package is installed from **PyPI**. When `pretrained.get_model("htdemucs")` is called, it uses **`torch.hub`** to download weights from Meta's **GitHub Releases** — not the Hugging Face Hub. The weights are cached in `~/.cache/torch/hub/` and persist across container restarts via the Docker volume.

### Singleton pattern

The Demucs model is loaded once per worker process and cached in a module-level global (`_demucs_model`). This avoids reloading ~300 MB of weights on every job.

---

## Stage 2: Hit Prediction

**File:** [`engine.py → run_prediction()`](../backend/app/ml/engine.py)

This stage replicates AnNOTEator's `drum_to_frame()` + `predict_drumhit()` logic.

### 2a. BPM Detection

**File:** [`engine.py → _detect_bpm()`](../backend/app/ml/engine.py)

Uses a two-tier strategy with graceful fallback:

| Priority | Library | Method | Reliability |
|----------|---------|--------|-------------|
| 1st | **madmom** | `RNNBeatProcessor` → `TempoEstimationProcessor` | High (RNN-based, returns confidence) |
| 2nd | **librosa** | `librosa.beat.tempo()` | Medium (onset-based heuristic) |
| 3rd | Default | Hardcoded 120 BPM | Fallback only |

If madmom's confidence score is below 0.5, or if librosa fallback is used, the result is flagged as `bpm_unreliable: true` in the API response. Users can also supply BPM manually via the `bpm` parameter.

### 2b. Onset Detection

```
drum_track → librosa.onset.onset_strength() → librosa.onset.onset_detect()
```

- **Hop length** adapts to tempo: 512 samples for BPM > 110, 1024 otherwise (matching AnNOTEator's behavior)
- Onset times are converted to sample positions for clip extraction

### 2c. Frame Extraction

For each detected onset, a clip is extracted:

| Parameter | Value | Source |
|-----------|-------|--------|
| **Window size** | Based on 16th-note duration at detected BPM | AnNOTEator `resolution=16` |
| **Padding** | 32nd-note / 4 before onset | Captures attack transient |
| **Target length** | **8820 samples** (fixed) | AnNOTEator training config |

Clips shorter or longer than 8820 samples are resampled via `librosa.resample()` and padded/truncated to exactly 8820 samples. This is critical — the CNN was trained on this exact frame size.

### 2d. Mel-Spectrogram Feature Extraction

Each 8820-sample clip is converted to a mel-spectrogram:

| Parameter | Value | Matches AnNOTEator |
|-----------|-------|--------------------|
| `n_fft` | 2048 | Yes |
| `hop_length` | 512 | Yes |
| `n_mels` | 128 | Yes |
| `fmax` | 8000 Hz | Yes |
| `power` | 2.0 | Yes |

These parameters **must match the training configuration exactly** — changing any of them will degrade prediction accuracy.

The mel-spectrograms are stacked into a 4D tensor: `(num_onsets, 128, time_bins, 1)`.

### 2e. CNN Classification

| Property | Value |
|----------|-------|
| **Model** | `complete_network.h5` (Keras) |
| **Architecture** | CNN with 6 sigmoid outputs |
| **Classification** | Multi-label (multiple instruments per onset) |
| **Classes** | `snare`, `hihat_closed`, `kick`, `ride`, `tom_high`, `crash` |
| **Output** | 6 probabilities in [0, 1] per onset |

**Decision logic:**
1. Round each output to 0 or 1 (threshold = 0.5)
2. If **all 6 outputs round to 0** → pick the argmax (highest raw probability) as a single-label prediction
3. Otherwise, all instruments with output ≥ 0.5 are reported (multi-label)

This fallback matches the original AnNOTEator behavior and prevents silent frames from producing no output.

### 2f. Confidence Scoring

```python
confidence_score = mean(max(raw_prediction) for each onset)
```

The confidence score is the average of the highest raw sigmoid output per onset. Scores below `LOW_CONFIDENCE_THRESHOLD` (default: 0.5) trigger a `low_confidence` warning in the API response.

### Output format

```json
{
  "detected_bpm": 120,
  "bpm_unreliable": false,
  "duration_seconds": 180.5,
  "confidence_score": 0.8234,
  "hit_summary": {"kick": 45, "snare": 42, "hihat_closed": 120},
  "hits": [
    {"time": 0.5123, "instrument": "kick", "velocity": 0.9341},
    {"time": 0.5123, "instrument": "hihat_closed", "velocity": 0.7821},
    ...
  ]
}
```

---

## Stage 3: Transcription

**File:** [`transcription.py → build_sheet_music()`](../backend/app/services/transcription.py)

Converts the hit list into standard drum notation using **music21**.

### Instrument → Pitch Mapping

| Instrument | music21 Pitch | Staff Position | Notehead |
|------------|---------------|----------------|----------|
| Kick | F4 | Below staff | Normal |
| Snare | C5 | 3rd line | Normal |
| Hi-hat (closed) | G5 | Top line | **x** |
| Ride | G5 | Top line | **x** |
| Crash | A5 | Above staff | **x** |
| Tom (high) | E5 | 4th space | Normal |

### Quantization

- Hits are grouped by time — simultaneous hits become `PercussionChord` objects
- Time offsets are converted from seconds to quarter-note positions using the detected BPM
- Default note duration: eighth note (0.5 quarter-note lengths)

### Export

| Format | Method | Backend |
|--------|--------|---------|
| **MusicXML** | `music21.stream.write("musicxml")` | Built-in |
| **PDF** | MusicXML → LilyPond → PDF | `lilypond` CLI (configurable via `PDF_BACKEND`) |

PDF export supports three backends via the `PDF_BACKEND` env var:
- `"lilypond"` (default) — headless, no X11, recommended for containers
- `"musescore"` — requires xvfb for headless operation
- `"none"` — skip PDF, serve MusicXML only

---

## Model Management

**File:** [`registry.py → ModelResolver`](../backend/app/ml/registry.py)

### Resolution flow

```
1. Check cache: /data/models/complete_network/{MODEL_VERSION}/complete_network.h5
2. Cache hit  → return path
3. Cache miss → parse MODEL_URI scheme:
     http(s):// → streaming download via httpx
     s3://      → boto3 download_file
     file://    → shutil.copy2
4. Verify SHA256 integrity (if MODEL_SHA256 is set)
5. Load into Keras → singleton cached for process lifetime
```

### Lifecycle

| Event | What happens |
|-------|-------------|
| **Container start** | `entrypoint-worker.sh` runs `download_models.sh` — pre-caches both Demucs and CNN weights |
| **Worker init** | `preload_models()` loads the Keras model into memory (called via Celery `worker_init` signal) |
| **First job** | Models already warm — no cold-start delay |
| **Version bump** | Change `MODEL_VERSION` env var → triggers fresh download on next startup |

### Environment variables

| Variable | Example | Purpose |
|----------|---------|---------|
| `MODEL_URI` | `https://bucket.s3.amazonaws.com/models/v1.0.0/complete_network.h5` | Where to download the CNN model |
| `MODEL_VERSION` | `v1.0.0` | Cache key — change to force re-download |
| `MODEL_CACHE_DIR` | `/data/models` | Local cache directory (Docker volume) |
| `MODEL_SHA256` | `a1b2c3d4...` | Optional integrity check after download |

---

## Dependencies

### ML Stack (worker only)

| Package | Version | Purpose |
|---------|---------|---------|
| `demucs` | 4.0.1 | Drum separation (Hybrid Transformer Demucs) |
| `torch` | >=2.0.0 | PyTorch runtime for Demucs |
| `torchaudio` | >=2.0.0 | Audio I/O for Demucs |
| `tensorflow` | 2.16.2 | Keras CNN inference |
| `librosa` | 0.10.2 | Audio analysis, onset detection, mel-spectrograms |
| `madmom` | 0.16.1 | RNN-based BPM detection |
| `music21` | 9.3.0 | Sheet music generation and notation |
| `pedalboard` | 0.9.16 | Audio effects (compression) |
| `soundfile` | 0.13.1 | WAV file I/O |
| `numpy` | 1.26.4 | Numerical operations |
| `pandas` | 2.2.3 | Data manipulation |

### Why two requirement files?

- **`requirements-api.txt`** — FastAPI, SQLAlchemy, Redis, observability (~400 MB image)
- **`requirements-worker.txt`** — inherits API deps + full ML stack (~3 GB image)

The API server never runs ML inference — it only dispatches jobs and serves results. This split keeps the API image small and fast to deploy.

---

## Architecture Decisions

### Why Demucs before CNN?

The CNN was trained on **isolated drum tracks**, not full mixes. Running it on a full mix produces poor results because vocals, bass, and guitars create false onsets. Demucs separation is essential preprocessing.

### Why 8820 samples per frame?

This is the frame size used in AnNOTEator's training data. The CNN's input layer expects mel-spectrograms computed from exactly this many samples. Changing it would require retraining the model.

### Why multi-label classification?

A single onset can contain multiple simultaneous drum hits (e.g., kick + hi-hat). The 6 sigmoid outputs allow the model to predict any combination of instruments per onset, rather than forcing a single-class decision.

### Why madmom over librosa for BPM?

madmom uses a recurrent neural network trained specifically for beat tracking, which handles complex rhythms and tempo changes better than librosa's onset-based heuristic. However, madmom occasionally fails on edge cases, so librosa serves as a reliable fallback.

### Why singleton model loading?

Loading Demucs (~300 MB) and the Keras CNN (~15 MB) on every job would add 30-90 seconds of overhead. Both models are loaded once at worker startup and cached as module-level globals, so subsequent jobs start instantly.

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
│  Stage 0: Ingestion (yt-dlp / file upload)                      │
│  Download or validate uploaded audio                            │
│  Queue: io │ concurrency: 8 │ I/O-bound                        │
└───────────────────────────┬─────────────────────────────────────┘
                            │ audio file
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 1: Drum Separation (Demucs htdemucs)                     │
│  Full mix → isolated drum track                                 │
│  Queue: heavy-compute │ concurrency: 1 │ ~2–4 GB RAM            │
└───────────────────────────┬─────────────────────────────────────┘
                            │ drums.wav
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 2: Hit Prediction (Keras CNN)                            │
│  BPM detection → onset detection → mel-spectrogram → classify   │
│  6 classes: kick, snare, hihat, ride, tom, crash                │
│  Queue: heavy-compute │ concurrency: 1 │ ~500 MB RAM            │
└───────────────────────────┬─────────────────────────────────────┘
                            │ hits.json
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Stage 3: Transcription (music21)                               │
│  Quantize hits → build notation → export MusicXML + PDF         │
│  Queue: default │ concurrency: 4 │ lightweight                  │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                  sheet_music.musicxml
                  sheet_music.pdf
```

Each stage is a separate **Celery task** chained in `app/worker.py`:

```python
ingest_audio.s(job_id).set(queue="io")
  | separate_drums.s().set(queue="heavy-compute")
  | predict_hits.s().set(queue="heavy-compute")
  | transcribe_and_export.s().set(queue="default")
```

### Queue Assignment

| Task | Queue | Worker | Reason |
|------|-------|--------|--------|
| `ingest_audio` | `io` | `worker-io` (concurrency 8) | Network-bound; parallel downloads safe |
| `separate_drums` | `heavy-compute` | `worker-heavy` (concurrency 1) | Demucs requires up to 3.5 GB RAM alone |
| `predict_hits` | `heavy-compute` | `worker-heavy` (concurrency 1) | Shares process with loaded Demucs model |
| `transcribe_and_export` | `default` | `worker-default` (concurrency 4) | CPU-light; music21 + LilyPond only |
| `cleanup_old_artifacts` | `default` | `worker-default` | Periodic I/O task via `celery-beat` |
| `expire_stale_jobs` | `default` | `worker-default` | Periodic DB task via `celery-beat` (every 5 min) |

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
| **Weight download** | `demucs.pretrained.get_model("htdemucs")` → `torch.hub` → GitHub Releases (automatic on first call) |
| **Weight cache** | `TORCH_HOME=/app/inference/demucs` → host bind-mount `./inference/demucs/` |
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

The model lifecycle is split across two layers: **startup verification** (`app/core/model_manager.py`) and **runtime resolution** (`app/ml/registry.py`).

### Startup: `ModelManager` (entrypoint)

`entrypoint-worker.sh` calls `python -m app.core.model_manager` before Celery starts. `ModelManager.setup_all_models()` runs two steps:

**Step 1 — Demucs (critical):**
Calls `demucs.pretrained.get_model("htdemucs")`. This triggers `torch.hub` to download weights to `TORCH_HOME=/app/inference/demucs` (a host bind-mount) if they are not already cached. If this step fails, the entrypoint exits with code 1 and the container does not start.

**Step 2 — CNN verification (non-critical):**
`ModelManager.verify_cnn_model()` checks `MODEL_URI`:

| `MODEL_URI` type | Action | Container outcome |
|-----------------|--------|-------------------|
| Local path, file **exists** | Logs size, marks ready | ✓ starts |
| Local path, file **missing** | Logs `cnn_model_missing` warning | **✓ starts** (graceful) |
| `http://`, `https://`, `s3://` | Deferred — logs `cnn_model_remote` | ✓ starts |
| Not set (`""`) | Logs `cnn_model_not_configured` warning | ✓ starts |

Missing custom weights **never crash the container**. Workers start and are healthy; only `predict_hits` tasks will fail at runtime until weights are provided.

### Runtime: `ModelResolver`

**File:** [`app/ml/registry.py`](../backend/app/ml/registry.py)

Called by `get_keras_model()` on the first job that reaches `predict_hits`.

```
1. Check /data/models/complete_network/{MODEL_VERSION}/complete_network.h5
2. Cache hit  → return path
3. Cache miss → parse MODEL_URI scheme:
     http(s):// → httpx streaming download (timeout=300s)
     s3://      → boto3 download_file
     file://    → shutil.copy2
4. Verify SHA256 integrity (if MODEL_SHA256 is set, deletes corrupt file on mismatch)
5. Load into Keras → singleton cached in _keras_model for process lifetime
```

### Worker init signal

When `WORKER_MODE=true`, the Celery `worker_init` signal calls `preload_models()`, which calls `get_keras_model()` immediately at startup. This warms the model into memory before any task arrives — eliminating the 30–90 s cold-start on the first `predict_hits` job.

> `worker-io` sets `WORKER_MODE=false` (it never runs ML inference), so it skips model preloading entirely.

### Lifecycle Summary

| Event | What happens |
|-------|-------------|
| **Container start** | `entrypoint-worker.sh` → `python -m app.core.model_manager` → Demucs weights cached to `./inference/demucs/` (bind-mount); CNN path verified or warned |
| **Celery worker_init** | `preload_models()` → `ModelResolver.get_keras_model()` → CNN loaded into memory singleton |
| **First `predict_hits` job** | CNN model already warm; no download delay |
| **CNN file missing at startup** | Worker starts with warning; job fails at `predict_hits` with clear error |
| **`MODEL_VERSION` bumped** | `ModelResolver` detects cache miss → fresh download on next startup |

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `MODEL_URI` | `inference/pretrained_models/annoteators/complete_network.h5` | CNN weights source (local path, HTTP, or S3) |
| `MODEL_VERSION` | `v1.0.0` | Cache key in `/data/models/complete_network/{version}/` |
| `MODEL_CACHE_DIR` | `/data/models` | Named Docker volume mount point |
| `MODEL_SHA256` | `""` | Optional SHA256 for integrity check after download |
| `TORCH_HOME` | `/app/inference/demucs` | `torch.hub` cache dir — bind-mounted to `./inference/demucs/` on host |

---

## Dependencies

### Two Requirements Files

| File | Used By | Contents | Approx. Image Size |
|------|---------|----------|--------------------|
| `requirements-api.txt` | `Dockerfile.api` | FastAPI, SQLAlchemy, asyncpg, Redis, observability | ~400 MB |
| `requirements-worker.txt` | `Dockerfile.worker` | All of API deps + full ML stack below | ~3 GB |

The API never runs ML inference — it only dispatches jobs and serves results. This split keeps the API image lean and fast to build.

### ML Stack (`requirements-worker.txt`)

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
| `numpy` | 1.26.4 | Numerical operations (pinned — required by madmom at build time) |
| `pandas` | 2.2.3 | Data manipulation |

### `madmom` Build Isolation

`madmom==0.16.1` uses a legacy `setup.py` that imports `numpy` and `Cython` during pip's **metadata collection phase** — before the normal build-isolation sandbox can inject them. Installing it in a single `pip install -r requirements-worker.txt` call fails.

`Dockerfile.worker` resolves this with a four-tier install sequence (see [Docker Build Architecture](DEVOPS.md#4-docker-build-architecture)):

```
Tier 0: Upgrade pip/setuptools/wheel
Tier 1: Pre-seed numpy==1.26.4 + Cython>=3 into system site-packages
Tier 2: Install everything except madmom (full build isolation, clean dep tree)
Tier 3: Install madmom --no-build-isolation (sees Tier 1 numpy/Cython)
```

This keeps `celery[redis]` and its transitive dependencies (including `packaging`, required by `kombu`) resolved cleanly in Tier 2, while satisfying `madmom`'s unusual build requirements in Tier 3.

---

## Architecture Decisions

### Why three queues instead of two?

The original two-queue design (`default` + `heavy-compute`) mixed YouTube downloads with transcription tasks on `default`. Under burst traffic, long yt-dlp downloads would block available slots, starving MusicXML/PDF export jobs. The `io` queue dedicates high-concurrency (8) workers to network I/O, keeping `default` exclusively for CPU work and `heavy-compute` for ML inference. Each queue is independently scalable.

### Why Demucs before CNN?

The CNN was trained on **isolated drum tracks**, not full mixes. Running it on a full mix produces poor results because vocals, bass, and guitars create false onsets. Demucs separation is essential preprocessing.

### Why `./inference` as a bind-mount for Demucs weights?

Named Docker volumes are opaque — you can't inspect, pre-populate, or version-control their contents directly. Mounting `./inference` as a host directory means Demucs weights are:
- Visible and manageable on the host filesystem
- Preserved across `docker compose down -v`
- Shareable between worker replicas on the same host without duplication
- Easy to pre-populate by copying weights into `./inference/demucs/` before first run

### Why 8820 samples per frame?

This is the frame size used in AnNOTEator's training data. The CNN's input layer expects mel-spectrograms computed from exactly this many samples. Changing it would require retraining the model.

### Why multi-label classification?

A single onset can contain multiple simultaneous drum hits (e.g., kick + hi-hat). The 6 sigmoid outputs allow the model to predict any combination of instruments per onset, rather than forcing a single-class decision.

### Why madmom over librosa for BPM?

madmom uses a recurrent neural network trained specifically for beat tracking, which handles complex rhythms and tempo changes better than librosa's onset-based heuristic. However, madmom occasionally fails on edge cases, so librosa serves as a reliable fallback.

### Why singleton model loading?

Loading Demucs (~300 MB) and the Keras CNN (~15 MB) on every job would add 30–90 seconds of overhead. Both models are loaded once at worker startup and cached as module-level globals (`_demucs_model`, `_keras_model`), so subsequent jobs start instantly.

### Why does a missing CNN not crash the container?

During development, custom weights (`complete_network.h5`) may not be committed to the repository or may be stored externally. A hard failure on missing weights would prevent any worker from starting — blocking development of unrelated features (e.g., ingestion, transcription formatting). `ModelManager` separates Demucs (infrastructure-critical) from the CNN (feature-critical) so each can fail independently at the appropriate severity level.

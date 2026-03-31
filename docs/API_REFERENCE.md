# API Reference

Complete REST API documentation for DrumScribe's backend services.

**Base URL:** `https://api.drumscribe.ai` (production) or `http://localhost:8000` (development)

---

## Table of Contents

- [Authentication](#authentication)
- [Jobs API](#jobs-api)
- [Health & Monitoring](#health--monitoring)
- [Error Handling](#error-handling)
- [Rate Limiting](#rate-limiting)

---

## Authentication

Currently, the API is open for public use. Authentication will be added in future versions.

**Planned:**
- API Key authentication via `Authorization: Bearer <token>` header
- Rate limiting per API key
- User accounts and quotas

---

## Jobs API

### Create Job

Create a new drum transcription job.

**Endpoint:** `POST /api/jobs`

**Request:**

```http
POST /api/jobs HTTP/1.1
Host: api.drumscribe.ai
Content-Type: multipart/form-data

--boundary
Content-Disposition: form-data; name="audio"; filename="drums.mp3"
Content-Type: audio/mpeg

<binary audio data>
--boundary
Content-Disposition: form-data; name="user_bpm"

120
--boundary--
```

**Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `audio` | File | Yes | Audio file (mp3, wav, flac, ogg) |
| `user_bpm` | Integer | No | User-provided BPM (40-300) |
| `youtube_url` | String | No | YouTube URL (alternative to file upload) |

**Response:** `201 Created`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "progress": 0,
  "detected_bpm": null,
  "bpm_unreliable": null,
  "confidence_score": null,
  "user_bpm": 120,
  "created_at": "2026-03-26T12:00:00Z",
  "updated_at": "2026-03-26T12:00:00Z"
}
```

**cURL Example:**

```bash
curl -X POST https://api.drumscribe.ai/api/jobs \
  -F "audio=@drums.mp3" \
  -F "user_bpm=120"
```

**Python Example:**

```python
import requests

with open('drums.mp3', 'rb') as f:
    response = requests.post(
        'https://api.drumscribe.ai/api/jobs',
        files={'audio': f},
        data={'user_bpm': 120}
    )

job = response.json()
print(f"Job ID: {job['id']}")
```

**JavaScript Example:**

```javascript
const formData = new FormData()
formData.append('audio', audioFile)
formData.append('user_bpm', '120')

const response = await fetch('https://api.drumscribe.ai/api/jobs', {
  method: 'POST',
  body: formData,
})

const job = await response.json()
console.log(`Job ID: ${job.id}`)
```

---

### Get Job Status

Poll job status and progress.

**Endpoint:** `GET /api/jobs/{job_id}`

**Request:**

```http
GET /api/jobs/550e8400-e29b-41d4-a716-446655440000 HTTP/1.1
Host: api.drumscribe.ai
```

**Response:** `200 OK`

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "progress": 45,
  "detected_bpm": null,
  "bpm_unreliable": null,
  "confidence_score": null,
  "user_bpm": 120,
  "created_at": "2026-03-26T12:00:00Z",
  "updated_at": "2026-03-26T12:00:30Z"
}
```

**Status Values:**

| Status | Description | Progress |
|--------|-------------|----------|
| `pending` | Job queued, waiting to start | 0% |
| `processing` | ML pipeline running | 1-99% |
| `completed` | Successfully completed | 100% |
| `failed` | Error occurred | N/A |

**Progress Breakdown:**

- 0-5%: Audio ingestion
- 5-50%: Drum separation (BS-Roformer)
- 50-75%: Hit detection (ONNX Runtime)
- 75-100%: Transcription (symusic)

**Polling Recommendation:**
- Poll every 1 second while `status` is `processing`
- Stop polling when `status` is `completed` or `failed`

---

### Get Job Result

Get ML prediction results.

**Endpoint:** `GET /api/jobs/{job_id}/result`

**Request:**

```http
GET /api/jobs/550e8400-e29b-41d4-a716-446655440000/result HTTP/1.1
Host: api.drumscribe.ai
```

**Response:** `200 OK`

```json
{
  "schema_version": "1.0",
  "model_version": "MIT/ast-finetuned-audioset-10-10-0.4593",
  "detected_bpm": 128,
  "bpm_unreliable": false,
  "duration_seconds": 180.5,
  "confidence_score": 0.87,
  "hit_summary": {
    "kick": 245,
    "snare": 189,
    "hihat_closed": 512,
    "hihat_open": 34,
    "ride": 78,
    "crash": 12,
    "tom": 23
  },
  "hits": [
    {
      "time": 0.0,
      "instrument": "kick",
      "velocity": 0.92
    },
    {
      "time": 0.234,
      "instrument": "hihat_closed",
      "velocity": 0.78
    },
    {
      "time": 0.468,
      "instrument": "snare",
      "velocity": 0.85
    }
    // ... more hits
  ]
}
```

**Hit Object:**

| Field | Type | Description |
|-------|------|-------------|
| `time` | Float | Time in seconds from start |
| `instrument` | String | Drum class (kick, snare, hihat_closed, etc.) |
| `velocity` | Float | Confidence/velocity (0.0-1.0) |

**Instrument Values:**
- `kick` - Bass drum
- `snare` - Snare drum
- `hihat_closed` - Closed hi-hat
- `hihat_open` - Open hi-hat
- `ride` - Ride cymbal
- `crash` - Crash cymbal
- `tom` - Tom (high/mid/low)

---

### Download MusicXML

Download sheet music in MusicXML format.

**Endpoint:** `GET /api/jobs/{job_id}/download/musicxml`

**Request:**

```http
GET /api/jobs/550e8400-e29b-41d4-a716-446655440000/download/musicxml HTTP/1.1
Host: api.drumscribe.ai
```

**Response:** `200 OK`

```http
Content-Type: application/vnd.recordare.musicxml+xml
Content-Disposition: attachment; filename="drums.musicxml"

<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="3.1">
  <part-list>
    <score-part id="P1">
      <part-name>Drums</part-name>
    </score-part>
  </part-list>
  <!-- ... MusicXML content -->
</score-partwise>
```

**cURL Example:**

```bash
curl -O https://api.drumscribe.ai/api/jobs/{job_id}/download/musicxml
```

---

### Download PDF

Download sheet music in PDF format.

**Endpoint:** `GET /api/jobs/{job_id}/download/pdf`

**Request:**

```http
GET /api/jobs/550e8400-e29b-41d4-a716-446655440000/download/pdf HTTP/1.1
Host: api.drumscribe.ai
```

**Response:** `200 OK`

```http
Content-Type: application/pdf
Content-Disposition: attachment; filename="drums.pdf"

<binary PDF data>
```

---

### Delete Job

Cancel or delete a job.

**Endpoint:** `DELETE /api/jobs/{job_id}`

**Request:**

```http
DELETE /api/jobs/550e8400-e29b-41d4-a716-446655440000 HTTP/1.1
Host: api.drumscribe.ai
```

**Response:** `204 No Content`

**Notes:**
- Cancels job if still processing
- Deletes all associated artifacts (audio, results, sheet music)
- Cannot be undone

---

## Health & Monitoring

### Health Check

Check API health and dependencies.

**Endpoint:** `GET /api/health`

**Request:**

```http
GET /api/health HTTP/1.1
Host: api.drumscribe.ai
```

**Response:** `200 OK`

```json
{
  "status": "healthy",
  "timestamp": "2026-03-26T12:00:00Z",
  "checks": {
    "database": {
      "status": "healthy",
      "latency_ms": 5
    },
    "storage": {
      "status": "healthy",
      "latency_ms": 12
    },
    "modal": {
      "status": "healthy",
      "latency_ms": 150
    }
  }
}
```

**Status Values:**
- `healthy` - All systems operational
- `degraded` - Some systems experiencing issues
- `unhealthy` - Critical systems down

---

### Prometheus Metrics

Prometheus-compatible metrics endpoint.

**Endpoint:** `GET /metrics`

**Request:**

```http
GET /metrics HTTP/1.1
Host: api.drumscribe.ai
```

**Response:** `200 OK`

```
# HELP jobs_total Total number of jobs created
# TYPE jobs_total counter
jobs_total 12345

# HELP jobs_by_status Number of jobs by status
# TYPE jobs_by_status gauge
jobs_by_status{status="pending"} 5
jobs_by_status{status="processing"} 12
jobs_by_status{status="completed"} 12000
jobs_by_status{status="failed"} 328

# HELP inference_duration_seconds GPU inference duration
# TYPE inference_duration_seconds histogram
inference_duration_seconds_bucket{le="10"} 1234
inference_duration_seconds_bucket{le="30"} 5678
inference_duration_seconds_bucket{le="60"} 8901
inference_duration_seconds_sum 123456.78
inference_duration_seconds_count 9012
```

---

## Error Handling

### Error Response Format

All errors follow a consistent format:

```json
{
  "detail": "Error message",
  "error_code": "ERROR_CODE",
  "timestamp": "2026-03-26T12:00:00Z"
}
```

### HTTP Status Codes

| Code | Meaning | Description |
|------|---------|-------------|
| `200` | OK | Request successful |
| `201` | Created | Resource created successfully |
| `204` | No Content | Request successful, no response body |
| `400` | Bad Request | Invalid request parameters |
| `404` | Not Found | Resource not found |
| `413` | Payload Too Large | File exceeds size limit |
| `422` | Unprocessable Entity | Validation error |
| `429` | Too Many Requests | Rate limit exceeded |
| `500` | Internal Server Error | Server error |
| `503` | Service Unavailable | Service temporarily unavailable |

### Common Errors

**File Too Large:**

```json
{
  "detail": "File size exceeds maximum allowed size of 50MB",
  "error_code": "FILE_TOO_LARGE"
}
```

**Invalid Audio Format:**

```json
{
  "detail": "Unsupported audio format. Allowed: mp3, wav, flac, ogg",
  "error_code": "INVALID_AUDIO_FORMAT"
}
```

**Job Not Found:**

```json
{
  "detail": "Job not found",
  "error_code": "JOB_NOT_FOUND"
}
```

**Processing Failed:**

```json
{
  "detail": "ML pipeline failed: BPM detection error",
  "error_code": "PROCESSING_FAILED"
}
```

---

## Rate Limiting

**Current Limits:**
- 10 job creations per minute per IP
- 60 status polls per minute per IP
- 5 concurrent processing jobs per IP

**Rate Limit Headers:**

```http
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1648310400
```

**Rate Limit Exceeded Response:**

```http
HTTP/1.1 429 Too Many Requests
Retry-After: 60

{
  "detail": "Rate limit exceeded. Try again in 60 seconds.",
  "error_code": "RATE_LIMIT_EXCEEDED"
}
```

---

## Webhooks (Coming Soon)

**Planned Feature:**
- Register webhook URL for job completion notifications
- Receive POST request when job status changes
- Payload includes job ID and status

---

## Related Documentation

- **[System Architecture](ARCHITECTURE.md)** — Serverless design overview
- **[Backend Guide](../backend/README.md)** — Backend development
- **[Frontend Guide](../frontend/README.md)** — Frontend integration

---

**Last Updated:** March 2026

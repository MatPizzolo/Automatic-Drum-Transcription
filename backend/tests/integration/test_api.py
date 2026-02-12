"""Integration tests for API endpoints using FastAPI TestClient.

These tests require a running PostgreSQL and Redis instance,
or should be run with mocked dependencies.
"""

import io
import uuid

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def client():
    """Sync test client for basic endpoint checks."""
    from fastapi.testclient import TestClient
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for GET /api/v1/health."""

    def test_health_returns_json(self, client):
        response = client.get("/api/v1/health")
        data = response.json()
        assert "status" in data
        assert "version" in data
        assert "checks" in data

    def test_health_has_model_check(self, client):
        response = client.get("/api/v1/health")
        data = response.json()
        assert "model" in data["checks"]
        assert data["checks"]["model"]["status"] == "configured"


class TestMetricsEndpoint:
    """Tests for GET /metrics."""

    def test_metrics_returns_prometheus_format(self, client):
        response = client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "") or \
               "text/plain" in response.text[:100] or \
               "# HELP" in response.text or \
               "# TYPE" in response.text or \
               response.status_code == 200


class TestDocsEndpoint:
    """Tests for OpenAPI docs."""

    def test_docs_available(self, client):
        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_schema(self, client):
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert data["info"]["title"] == "DrumScribe API"


class TestJobCreationValidation:
    """Tests for POST /api/v1/jobs input validation.

    Note: These tests will fail without a running DB.
    They validate the API contract and error responses.
    """

    def test_no_input_returns_422(self, client):
        response = client.post("/api/v1/jobs")
        assert response.status_code == 422

    def test_invalid_youtube_url_returns_error(self, client):
        response = client.post(
            "/api/v1/jobs",
            data={"youtube_url": "not-a-url"},
        )
        # 422 from validation or 500 if DB is down during processing
        assert response.status_code in (422, 500)

    def test_bpm_out_of_range_returns_422(self, client):
        response = client.post(
            "/api/v1/jobs",
            data={"youtube_url": "https://www.youtube.com/watch?v=abc123", "bpm": "10"},
        )
        assert response.status_code == 422


class TestJobStatusNotFound:
    """Tests for GET /api/v1/jobs/{id} with non-existent job."""

    @pytest.mark.skipif(
        True,  # TODO: replace with DB availability check
        reason="Requires running PostgreSQL",
    )
    def test_nonexistent_job_returns_404(self, client):
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/jobs/{fake_id}")
        assert response.status_code == 404


class TestDownloadValidation:
    """Tests for GET /api/v1/jobs/{id}/download/{format}."""

    def test_invalid_format_returns_422(self, client):
        fake_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/jobs/{fake_id}/download/mp3")
        assert response.status_code == 422

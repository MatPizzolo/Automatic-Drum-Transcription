#!/usr/bin/env python3
"""
End-to-end ML pipeline test client.

Tests the complete transcription pipeline from audio upload/YouTube URL
through BS-Roformer drum separation, AST hit prediction, and MusicXML/PDF export.
"""

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
import structlog

# Configure structlog for CLI output
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)

logger = structlog.get_logger()


# Exit codes
EXIT_SUCCESS = 0
EXIT_API_ERROR = 1
EXIT_VALIDATION_ERROR = 2
EXIT_TIMEOUT = 3


@dataclass
class TestConfig:
    """Configuration for pipeline test."""

    api_url: str
    file_path: Optional[Path]
    youtube_url: Optional[str]
    title: Optional[str]
    bpm: Optional[int]
    poll_interval: int
    output_dir: Path
    verbose: bool
    max_wait_seconds: int = 600  # 10 minutes default


class PipelineTestClient:
    """Client for testing the drum transcription pipeline."""

    def __init__(self, config: TestConfig):
        self.config = config
        self.client = httpx.Client(timeout=30.0)
        self.logger = logger.bind(api_url=config.api_url)

        if config.verbose:
            structlog.configure(
                processors=[
                    structlog.processors.add_log_level,
                    structlog.processors.TimeStamper(fmt="iso"),
                    structlog.dev.ConsoleRenderer(),
                ],
                wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
                context_class=dict,
                logger_factory=structlog.PrintLoggerFactory(),
                cache_logger_on_first_use=False,
            )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()

    def check_health(self) -> bool:
        """Check API health status.

        Returns:
            True if API is healthy, False otherwise.
        """
        self.logger.info("checking_api_health")
        try:
            response = self.client.get(
                f"{self.config.api_url}/api/v1/health",
                timeout=5.0,
            )
            response.raise_for_status()
            health = response.json()

            self.logger.info(
                "health_check_complete",
                status=health.get("status"),
                checks=health.get("checks", {}),
            )

            if health.get("status") != "healthy":
                self.logger.error(
                    "api_unhealthy",
                    status=health.get("status"),
                    checks=health.get("checks", {}),
                )
                return False

            return True

        except httpx.HTTPError as e:
            self.logger.error("health_check_failed", error=str(e))
            return False

    def create_job(self) -> Optional[Dict[str, Any]]:
        """Create a transcription job via file upload or YouTube URL.

        Returns:
            Job creation response dict, or None on failure.
        """
        url = f"{self.config.api_url}/api/v1/jobs"

        try:
            if self.config.file_path:
                # File upload
                self.logger.info(
                    "uploading_file",
                    file=str(self.config.file_path),
                    size_mb=round(self.config.file_path.stat().st_size / 1024 / 1024, 2),
                )

                with open(self.config.file_path, "rb") as f:
                    files = {"file": (self.config.file_path.name, f)}
                    data = {}
                    if self.config.title:
                        data["title"] = self.config.title
                    if self.config.bpm:
                        data["bpm"] = str(self.config.bpm)

                    response = self._retry_request(
                        lambda: self.client.post(url, files=files, data=data)
                    )

            else:
                # YouTube URL
                self.logger.info("submitting_youtube_url", url=self.config.youtube_url)

                data = {
                    "youtube_url": self.config.youtube_url,
                    "title": self.config.title or "YouTube Transcription",
                }
                if self.config.bpm:
                    data["bpm"] = str(self.config.bpm)

                response = self._retry_request(
                    lambda: self.client.post(url, data=data)
                )

            if response is None:
                return None

            response.raise_for_status()
            job_data = response.json()

            self.logger.info(
                "job_created",
                job_id=job_data.get("id"),
                status=job_data.get("status"),
            )

            return job_data

        except httpx.HTTPStatusError as e:
            error_detail = "Unknown error"
            try:
                error_data = e.response.json()
                error_detail = error_data.get("detail", str(e))
            except Exception:
                error_detail = str(e)

            self.logger.error(
                "job_creation_failed",
                status_code=e.response.status_code,
                error=error_detail,
            )
            return None

        except Exception as e:
            self.logger.error("job_creation_error", error=str(e))
            return None

    def poll_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Poll job status until completion or failure.

        Args:
            job_id: Job UUID to poll.

        Returns:
            Final job status dict, or None on timeout/error.
        """
        url = f"{self.config.api_url}/api/v1/jobs/{job_id}"
        start_time = time.time()
        last_status = None
        last_progress = -1

        self.logger.info("polling_job_status", job_id=job_id)

        while True:
            elapsed = time.time() - start_time

            if elapsed > self.config.max_wait_seconds:
                self.logger.error(
                    "job_timeout",
                    job_id=job_id,
                    elapsed_seconds=int(elapsed),
                    max_wait_seconds=self.config.max_wait_seconds,
                )
                return None

            try:
                response = self.client.get(url, timeout=5.0)
                response.raise_for_status()
                status_data = response.json()

                current_status = status_data.get("status")
                current_progress = status_data.get("progress", 0)

                # Log status changes
                if current_status != last_status or current_progress != last_progress:
                    self.logger.info(
                        "job_status_update",
                        job_id=job_id,
                        status=current_status,
                        progress=current_progress,
                        elapsed_seconds=int(elapsed),
                    )
                    last_status = current_status
                    last_progress = current_progress

                # Check terminal states
                if current_status == "completed":
                    self.logger.info(
                        "job_completed",
                        job_id=job_id,
                        total_seconds=int(elapsed),
                        compute_time_ms=status_data.get("compute_time_ms"),
                    )
                    return status_data

                if current_status == "failed":
                    self.logger.error(
                        "job_failed",
                        job_id=job_id,
                        error=status_data.get("error_message"),
                        elapsed_seconds=int(elapsed),
                    )
                    return status_data

                # Wait before next poll
                time.sleep(self.config.poll_interval)

            except httpx.HTTPError as e:
                self.logger.warning(
                    "poll_request_failed",
                    job_id=job_id,
                    error=str(e),
                    retrying=True,
                )
                time.sleep(self.config.poll_interval)

    def get_job_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Fetch job result with hit data and download URLs.

        Args:
            job_id: Job UUID.

        Returns:
            Job result dict, or None on error.
        """
        url = f"{self.config.api_url}/api/v1/jobs/{job_id}/result"

        try:
            response = self.client.get(url, timeout=10.0)
            response.raise_for_status()
            result = response.json()

            self.logger.info(
                "job_result_retrieved",
                job_id=job_id,
                detected_bpm=result.get("detected_bpm"),
                total_hits=len(result.get("hits", [])),
                confidence_score=result.get("confidence_score"),
                warnings=result.get("warnings", []),
            )

            return result

        except httpx.HTTPError as e:
            self.logger.error("result_fetch_failed", job_id=job_id, error=str(e))
            return None

    def download_artifacts(self, job_id: str, download_urls: Dict[str, str]) -> bool:
        """Download MusicXML and PDF artifacts.

        Args:
            job_id: Job UUID.
            download_urls: Dict with 'musicxml' and/or 'pdf' URLs.

        Returns:
            True if at least one artifact downloaded successfully.
        """
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        success = False

        for format_type, relative_url in download_urls.items():
            url = f"{self.config.api_url}{relative_url}"
            output_file = self.config.output_dir / f"job_{job_id}.{format_type}"

            try:
                self.logger.info(
                    "downloading_artifact",
                    job_id=job_id,
                    format=format_type,
                    output=str(output_file),
                )

                response = self.client.get(url, timeout=30.0)
                response.raise_for_status()

                output_file.write_bytes(response.content)

                self.logger.info(
                    "artifact_downloaded",
                    job_id=job_id,
                    format=format_type,
                    size_kb=round(len(response.content) / 1024, 2),
                )
                success = True

            except httpx.HTTPError as e:
                self.logger.warning(
                    "artifact_download_failed",
                    job_id=job_id,
                    format=format_type,
                    error=str(e),
                )

        return success

    def save_metadata(self, job_id: str, status_data: Dict[str, Any], result_data: Optional[Dict[str, Any]]):
        """Save comprehensive job metadata to JSON file.

        Args:
            job_id: Job UUID.
            status_data: Final status response.
            result_data: Result response (if successful).
        """
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        metadata_file = self.config.output_dir / f"job_{job_id}_metadata.json"

        metadata = {
            "job_id": job_id,
            "test_timestamp": datetime.now(timezone.utc).isoformat(),
            "config": {
                "api_url": self.config.api_url,
                "file_path": str(self.config.file_path) if self.config.file_path else None,
                "youtube_url": self.config.youtube_url,
                "title": self.config.title,
                "bpm": self.config.bpm,
            },
            "status": status_data,
            "result": result_data,
        }

        metadata_file.write_text(json.dumps(metadata, indent=2))
        self.logger.info("metadata_saved", file=str(metadata_file))

    def _retry_request(self, request_func, max_retries: int = 3):
        """Retry HTTP request with exponential backoff.

        Args:
            request_func: Callable that returns httpx.Response.
            max_retries: Maximum number of retry attempts.

        Returns:
            Response object or None on failure.
        """
        for attempt in range(max_retries):
            try:
                return request_func()
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    self.logger.warning(
                        "request_retry",
                        attempt=attempt + 1,
                        max_retries=max_retries,
                        wait_seconds=wait_time,
                        error=str(e),
                    )
                    time.sleep(wait_time)
                else:
                    self.logger.error("request_failed_all_retries", error=str(e))
                    return None


def validate_inputs(config: TestConfig) -> bool:
    """Validate CLI inputs before making API calls.

    Args:
        config: Test configuration.

    Returns:
        True if valid, False otherwise.
    """
    # Mutually exclusive inputs
    if config.file_path and config.youtube_url:
        logger.error("validation_error", error="Cannot specify both --file and --youtube")
        return False

    if not config.file_path and not config.youtube_url:
        logger.error("validation_error", error="Must specify either --file or --youtube")
        return False

    # File validation
    if config.file_path:
        if not config.file_path.exists():
            logger.error("validation_error", error=f"File not found: {config.file_path}")
            return False

        if not config.file_path.is_file():
            logger.error("validation_error", error=f"Not a file: {config.file_path}")
            return False

        allowed_extensions = {".wav", ".mp3", ".flac", ".ogg"}
        if config.file_path.suffix.lower() not in allowed_extensions:
            logger.error(
                "validation_error",
                error=f"Invalid file extension: {config.file_path.suffix}",
                allowed=list(allowed_extensions),
            )
            return False

        # Check file size (50MB limit)
        size_mb = config.file_path.stat().st_size / 1024 / 1024
        if size_mb > 50:
            logger.error(
                "validation_error",
                error=f"File too large: {size_mb:.2f}MB (max 50MB)",
            )
            return False

    # YouTube URL validation
    if config.youtube_url:
        pattern = r"^(https?://)?(www\.)?(youtube\.com/(watch\?v=|embed/|v/|shorts/)|youtu\.be/)[\w\-]+"
        if not re.match(pattern, config.youtube_url):
            logger.error(
                "validation_error",
                error=f"Invalid YouTube URL format: {config.youtube_url}",
            )
            return False

    # BPM validation
    if config.bpm is not None:
        if config.bpm < 40 or config.bpm > 300:
            logger.error(
                "validation_error",
                error=f"BPM must be between 40 and 300, got {config.bpm}",
            )
            return False

    return True


def main() -> int:
    """Main entry point for pipeline test client.

    Returns:
        Exit code (0=success, 1=API error, 2=validation error, 3=timeout).
    """
    parser = argparse.ArgumentParser(
        description="End-to-end ML pipeline test client for drum transcription",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Input (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group()
    input_group.add_argument(
        "--file",
        type=Path,
        help="Path to audio file (.wav, .mp3, .flac, .ogg)",
    )
    input_group.add_argument(
        "--youtube",
        type=str,
        help="YouTube URL (e.g., https://www.youtube.com/watch?v=...)",
    )

    # Configuration
    parser.add_argument(
        "--api-url",
        type=str,
        default="http://localhost:8000",
        help="API base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--title",
        type=str,
        help="Job title (default: filename or 'YouTube Transcription')",
    )
    parser.add_argument(
        "--bpm",
        type=int,
        help="User-supplied BPM (40-300, optional)",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=3,
        help="Seconds between status checks (default: 3)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./test_results"),
        help="Directory to save artifacts (default: ./test_results)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed logging",
    )
    parser.add_argument(
        "--max-wait",
        type=int,
        default=600,
        help="Maximum wait time in seconds (default: 600)",
    )

    args = parser.parse_args()

    # Build config
    config = TestConfig(
        api_url=args.api_url.rstrip("/"),
        file_path=args.file,
        youtube_url=args.youtube,
        title=args.title,
        bpm=args.bpm,
        poll_interval=args.poll_interval,
        output_dir=args.output_dir,
        verbose=args.verbose,
        max_wait_seconds=args.max_wait,
    )

    # Validate inputs
    if not validate_inputs(config):
        return EXIT_VALIDATION_ERROR

    # Run test
    logger.info("pipeline_test_start", config=config.__dict__)

    with PipelineTestClient(config) as client:
        # 1. Health check
        if not client.check_health():
            logger.error("pipeline_test_failed", reason="API unhealthy")
            return EXIT_API_ERROR

        # 2. Create job
        job_data = client.create_job()
        if not job_data:
            logger.error("pipeline_test_failed", reason="Job creation failed")
            return EXIT_API_ERROR

        job_id = job_data["id"]

        # 3. Poll status
        status_data = client.poll_job_status(job_id)
        if not status_data:
            logger.error("pipeline_test_failed", reason="Job timeout")
            return EXIT_TIMEOUT

        # 4. Handle completion
        if status_data.get("status") == "failed":
            client.save_metadata(job_id, status_data, None)
            logger.error(
                "pipeline_test_failed",
                reason="Job failed",
                error=status_data.get("error_message"),
            )
            return EXIT_API_ERROR

        # 5. Get result
        result_data = client.get_job_result(job_id)
        if not result_data:
            logger.error("pipeline_test_failed", reason="Result fetch failed")
            return EXIT_API_ERROR

        # 6. Download artifacts
        download_urls = result_data.get("download_urls", {})
        if download_urls:
            artifacts_ok = client.download_artifacts(job_id, download_urls)
            if not artifacts_ok:
                logger.warning("no_artifacts_downloaded")
        else:
            logger.warning("no_download_urls_available")

        # 7. Save metadata
        client.save_metadata(job_id, status_data, result_data)

        logger.info(
            "pipeline_test_complete",
            job_id=job_id,
            status="success",
            output_dir=str(config.output_dir),
        )

    return EXIT_SUCCESS


if __name__ == "__main__":
    sys.exit(main())

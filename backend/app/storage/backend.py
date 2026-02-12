"""
Storage backends — abstract interface with local and S3 implementations.

All artifact I/O should go through `get_storage()` so the backend is swappable
via the `STORAGE_BACKEND` env var ("local" or "s3").
"""

import abc
import io
import os
import shutil
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class StorageBackend(abc.ABC):
    """Abstract storage interface — swap local for S3 via config."""

    @abc.abstractmethod
    def save_file(self, job_id: str, filename: str, data: bytes) -> str:
        """Save file data, return the stored path/key."""
        ...

    @abc.abstractmethod
    def read_file(self, path: str) -> bytes:
        """Read file from storage."""
        ...

    @abc.abstractmethod
    def file_exists(self, path: str) -> bool:
        """Check if file exists."""
        ...

    @abc.abstractmethod
    def delete_job_artifacts(self, job_id: str) -> int:
        """Delete all artifacts for a job. Returns count of files deleted."""
        ...

    @abc.abstractmethod
    def list_job_files(self, job_id: str) -> list[str]:
        """List all files for a job."""
        ...

    @abc.abstractmethod
    def get_job_dir(self, job_id: str) -> str:
        """Get the directory path for a job's artifacts."""
        ...

    @abc.abstractmethod
    def get_file_path(self, job_id: str, filename: str) -> str:
        """Get the full path/key for a specific file in a job's directory."""
        ...


# ---------------------------------------------------------------------------
# Local filesystem
# ---------------------------------------------------------------------------

class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend."""

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or settings.ARTIFACTS_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_job_dir(self, job_id: str) -> str:
        job_dir = self.base_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return str(job_dir)

    def get_file_path(self, job_id: str, filename: str) -> str:
        return str(Path(self.get_job_dir(job_id)) / filename)

    def save_file(self, job_id: str, filename: str, data: bytes) -> str:
        dest = Path(self.get_file_path(job_id, filename))
        dest.write_bytes(data)
        logger.info("file_saved", job_id=job_id, filename=filename, size=len(data))
        return str(dest)

    def read_file(self, path: str) -> bytes:
        return Path(path).read_bytes()

    def file_exists(self, path: str) -> bool:
        return Path(path).exists()

    def delete_job_artifacts(self, job_id: str) -> int:
        job_dir = self.base_dir / job_id
        if not job_dir.exists():
            return 0
        count = sum(1 for _ in job_dir.rglob("*") if _.is_file())
        shutil.rmtree(job_dir, ignore_errors=True)
        logger.info("artifacts_deleted", job_id=job_id, files_deleted=count)
        return count

    def list_job_files(self, job_id: str) -> list[str]:
        job_dir = self.base_dir / job_id
        if not job_dir.exists():
            return []
        return [str(f) for f in job_dir.rglob("*") if f.is_file()]


# ---------------------------------------------------------------------------
# S3 (requires boto3)
# ---------------------------------------------------------------------------

class S3StorageBackend(StorageBackend):
    """
    AWS S3 storage backend.

    Files are stored under s3://{bucket}/{prefix}/{job_id}/{filename}.
    For local operations (ML pipeline reads), files are downloaded to a
    local cache directory and the local path is returned.
    """

    def __init__(self):
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 is required for S3 storage. "
                "Install with: pip install boto3"
            )

        self.bucket = settings.S3_BUCKET
        self.prefix = settings.S3_PREFIX
        if not self.bucket:
            raise ValueError("S3_BUCKET must be set when using S3 storage backend")

        client_kwargs = {"region_name": settings.S3_REGION}
        if settings.S3_ENDPOINT_URL:
            client_kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL

        self._s3 = boto3.client("s3", **client_kwargs)

        # Local cache for files that need filesystem access (ML pipeline)
        self._local_cache = Path(settings.ARTIFACTS_DIR)
        self._local_cache.mkdir(parents=True, exist_ok=True)

    def _s3_key(self, job_id: str, filename: str) -> str:
        return f"{self.prefix}/{job_id}/{filename}"

    def get_job_dir(self, job_id: str) -> str:
        local_dir = self._local_cache / job_id
        local_dir.mkdir(parents=True, exist_ok=True)
        return str(local_dir)

    def get_file_path(self, job_id: str, filename: str) -> str:
        return str(Path(self.get_job_dir(job_id)) / filename)

    def save_file(self, job_id: str, filename: str, data: bytes) -> str:
        key = self._s3_key(job_id, filename)
        self._s3.upload_fileobj(io.BytesIO(data), self.bucket, key)
        logger.info("s3_file_saved", job_id=job_id, key=key, size=len(data))

        # Also write to local cache for ML pipeline access
        local_path = self.get_file_path(job_id, filename)
        Path(local_path).write_bytes(data)
        return local_path

    def read_file(self, path: str) -> bytes:
        # Try local cache first
        if Path(path).exists():
            return Path(path).read_bytes()

        # Parse S3 key from path and download
        logger.warning("s3_read_fallback_local", path=path)
        return Path(path).read_bytes()

    def file_exists(self, path: str) -> bool:
        # Check local cache first (fast path)
        if Path(path).exists():
            return True

        # Check S3 — extract key from path
        try:
            rel = Path(path).relative_to(self._local_cache)
            parts = rel.parts
            if len(parts) >= 2:
                key = f"{self.prefix}/{'/'.join(parts)}"
                self._s3.head_object(Bucket=self.bucket, Key=key)
                return True
        except Exception:
            pass
        return False

    def delete_job_artifacts(self, job_id: str) -> int:
        # Delete from S3
        prefix = f"{self.prefix}/{job_id}/"
        count = 0
        try:
            paginator = self._s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                objects = page.get("Contents", [])
                if objects:
                    delete_keys = [{"Key": obj["Key"]} for obj in objects]
                    self._s3.delete_objects(
                        Bucket=self.bucket,
                        Delete={"Objects": delete_keys},
                    )
                    count += len(delete_keys)
        except Exception as e:
            logger.warning("s3_delete_error", job_id=job_id, error=str(e))

        # Also clean local cache
        local_dir = self._local_cache / job_id
        if local_dir.exists():
            shutil.rmtree(local_dir, ignore_errors=True)

        logger.info("s3_artifacts_deleted", job_id=job_id, files_deleted=count)
        return count

    def list_job_files(self, job_id: str) -> list[str]:
        prefix = f"{self.prefix}/{job_id}/"
        files = []
        try:
            paginator = self._s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    files.append(obj["Key"])
        except Exception as e:
            logger.warning("s3_list_error", job_id=job_id, error=str(e))
        return files


# ---------------------------------------------------------------------------
# Singleton factory
# ---------------------------------------------------------------------------

_storage_instance: Optional[StorageBackend] = None


def get_storage() -> StorageBackend:
    """Get the singleton storage backend instance."""
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance

    if settings.STORAGE_BACKEND == "s3":
        _storage_instance = S3StorageBackend()
    elif settings.STORAGE_BACKEND == "local":
        _storage_instance = LocalStorageBackend()
    else:
        raise ValueError(f"Unknown storage backend: {settings.STORAGE_BACKEND}")

    logger.info("storage_backend_initialized", backend=settings.STORAGE_BACKEND)
    return _storage_instance

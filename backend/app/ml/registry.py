"""
ModelResolver — versioned model loading with caching and remote pull support.

Provides a singleton interface so models are loaded once at worker startup.
"""

import os
import hashlib
import shutil
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ModelResolver:
    """
    Resolves and caches ML models by name and version.

    - Checks local cache directory first.
    - If missing, pulls from configured URI (HTTP, S3, local path).
    - Supports versioning — resolved path includes version identifier.
    """

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        model_uri: Optional[str] = None,
        model_version: Optional[str] = None,
        model_sha256: Optional[str] = None,
    ):
        self.cache_dir = Path(cache_dir or settings.MODEL_CACHE_DIR)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.model_uri = model_uri or settings.MODEL_URI
        self.model_version = model_version or settings.MODEL_VERSION
        self.model_sha256 = model_sha256 or settings.MODEL_SHA256
        self._keras_model = None

    def get_model(self, name: str = "complete_network", version: str = "latest") -> str:
        """
        Resolve a model path. Returns the local filesystem path to the model file.

        If version is "latest", uses the configured MODEL_VERSION.
        """
        if version == "latest":
            version = self.model_version

        versioned_dir = self.cache_dir / name / version
        versioned_dir.mkdir(parents=True, exist_ok=True)

        # Determine expected filename from URI
        filename = Path(self.model_uri).name
        cached_path = versioned_dir / filename

        if cached_path.exists() and cached_path.stat().st_size > 0:
            logger.info(
                "model_cache_hit",
                name=name,
                version=version,
                path=str(cached_path),
            )
            return str(cached_path)

        # Pull from URI
        logger.info(
            "model_cache_miss",
            name=name,
            version=version,
            uri=self.model_uri,
        )
        self._pull_model(self.model_uri, str(cached_path))
        self._verify_integrity(str(cached_path))
        return str(cached_path)

    def _pull_model(self, uri: str, dest: str) -> None:
        """Download or copy model from URI to local cache."""
        parsed = urlparse(uri)

        if parsed.scheme in ("http", "https"):
            self._download_http(uri, dest)
        elif parsed.scheme == "s3":
            self._download_s3(uri, dest)
        elif parsed.scheme in ("", "file"):
            # Local path
            src = parsed.path if parsed.path else uri
            if not Path(src).exists():
                raise FileNotFoundError(f"Model file not found at local path: {src}")
            shutil.copy2(src, dest)
            logger.info("model_copied_local", src=src, dest=dest)
        else:
            raise ValueError(f"Unsupported model URI scheme: {parsed.scheme}")

    def _download_http(self, url: str, dest: str) -> None:
        """Download model from HTTP/HTTPS URL."""
        import httpx

        logger.info("model_downloading_http", url=url)
        with httpx.stream("GET", url, follow_redirects=True, timeout=300) as response:
            response.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=8192):
                    f.write(chunk)
        logger.info("model_downloaded", dest=dest, size=os.path.getsize(dest))

    def _verify_integrity(self, path: str) -> None:
        """Verify SHA256 checksum of downloaded model if MODEL_SHA256 is set."""
        if not self.model_sha256:
            logger.info("model_sha256_skip", reason="MODEL_SHA256 not configured")
            return

        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        actual = sha256.hexdigest()

        if actual != self.model_sha256:
            Path(path).unlink(missing_ok=True)
            raise ValueError(
                f"Model integrity check failed. "
                f"Expected SHA256: {self.model_sha256}, got: {actual}. "
                f"Deleted corrupt file: {path}"
            )
        logger.info("model_integrity_verified", sha256=actual[:16] + "...")

    def _download_s3(self, uri: str, dest: str) -> None:
        """Download model from S3 (requires boto3)."""
        try:
            import boto3
        except ImportError:
            raise ImportError("boto3 is required for S3 model downloads")

        parsed = urlparse(uri)
        bucket = parsed.netloc
        key = parsed.path.lstrip("/")

        logger.info("model_downloading_s3", bucket=bucket, key=key)
        s3 = boto3.client("s3")
        s3.download_file(bucket, key, dest)
        logger.info("model_downloaded", dest=dest, size=os.path.getsize(dest))

    def get_keras_model(self, name: str = "complete_network", version: str = "latest"):
        """Load and cache the Keras CNN model (singleton)."""
        if self._keras_model is not None:
            return self._keras_model

        model_path = self.get_model(name, version)

        from tensorflow import keras
        self._keras_model = keras.models.load_model(model_path)
        logger.info("keras_model_loaded", path=model_path)
        return self._keras_model

    @property
    def version(self) -> str:
        return self.model_version


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_resolver: Optional[ModelResolver] = None


def get_model_resolver() -> ModelResolver:
    """Get the singleton ModelResolver instance."""
    global _resolver
    if _resolver is None:
        _resolver = ModelResolver()
    return _resolver


def preload_models() -> None:
    """
    Preload models at worker startup.
    Called from worker_init signal handler.
    """
    resolver = get_model_resolver()
    try:
        resolver.get_keras_model()
        logger.info("models_preloaded")
    except Exception as e:
        logger.error("model_preload_failed", error=str(e))

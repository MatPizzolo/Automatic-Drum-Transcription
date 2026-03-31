"""
Modal Client — Wrapper for calling serverless GPU functions.

This module provides a clean interface for calling Modal serverless functions
from the backend API/workers. It handles:
- Function lookup and invocation
- Fallback to local inference if Modal is unavailable
- Error handling and retries
- Configuration management

Author: DrumScribe MLOps Team
"""

import os
from typing import Dict, Any, Optional

from app.core.config import settings
from app.utils.logging import get_logger

logger = get_logger(__name__)


class ModalClient:
    """
    Client for calling Modal serverless GPU functions.
    
    This client provides a unified interface for running ML inference either
    on Modal's serverless infrastructure or locally as a fallback.
    
    Usage:
        client = ModalClient()
        result = client.process_audio(audio_path="/path/to/audio.mp3", user_bpm=120)
    """
    
    def __init__(self):
        """Initialize Modal client with configuration."""
        self.use_modal = settings.USE_MODAL
        self.modal_app_name = settings.MODAL_APP_NAME
        self.modal_function_name = settings.MODAL_FUNCTION_NAME
        self._modal_function = None
        
        if self.use_modal:
            self._initialize_modal()
    
    def _initialize_modal(self) -> None:
        """Initialize Modal function lookup."""
        try:
            import modal
            
            logger.info(
                "modal_client_init",
                app_name=self.modal_app_name,
                function_name=self.modal_function_name,
            )
            
            # Lookup deployed Modal function
            self._modal_function = modal.Function.lookup(
                self.modal_app_name,
                self.modal_function_name,
            )
            
            logger.info("modal_client_ready", status="connected")
            
        except ImportError:
            logger.warning(
                "modal_sdk_not_installed",
                message="Modal SDK not found - falling back to local inference",
            )
            self.use_modal = False
            
        except Exception as e:
            logger.error(
                "modal_client_init_failed",
                error=str(e),
                message="Failed to connect to Modal - falling back to local inference",
            )
            self.use_modal = False
    
    def process_audio(
        self,
        audio_path: Optional[str] = None,
        audio_bytes: Optional[bytes] = None,
        user_bpm: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Process audio file through ML pipeline (Modal or local).
        
        Args:
            audio_path: Path to local audio file
            audio_bytes: Raw audio bytes (alternative to path)
            user_bpm: Optional user-provided BPM override
        
        Returns:
            Dictionary with PredictionResult schema
        
        Raises:
            RuntimeError: If both Modal and local inference fail
        """
        
        # If Modal is enabled, try serverless inference
        if self.use_modal and self._modal_function is not None:
            try:
                return self._process_audio_modal(audio_path, audio_bytes, user_bpm)
            except Exception as e:
                logger.error(
                    "modal_inference_failed",
                    error=str(e),
                    message="Modal inference failed - falling back to local",
                )
                # Fall through to local inference
        
        # Fallback to local inference
        return self._process_audio_local(audio_path, user_bpm)
    
    def _process_audio_modal(
        self,
        audio_path: Optional[str],
        audio_bytes: Optional[bytes],
        user_bpm: Optional[int],
    ) -> Dict[str, Any]:
        """
        Process audio using Modal serverless GPU.
        
        This method uploads the audio file to Modal and calls the serverless
        function. Modal handles all GPU provisioning, scaling, and teardown.
        """
        logger.info("modal_inference_start", audio_path=audio_path)
        
        # Read audio bytes if path provided
        if audio_path and not audio_bytes:
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()
        
        # Call Modal function
        result = self._modal_function.remote(
            audio_url=None,  # We're providing bytes directly
            audio_bytes=audio_bytes,
            user_bpm=user_bpm,
        )
        
        logger.info(
            "modal_inference_complete",
            total_hits=len(result.get("hits", [])),
            bpm=result.get("detected_bpm"),
        )
        
        return result
    
    def _process_audio_local(
        self,
        audio_path: Optional[str],
        user_bpm: Optional[int],
    ) -> Dict[str, Any]:
        """
        Process audio using local GPU/CPU (fallback).
        
        This method runs the entire ML pipeline locally using the existing
        engine.py functions. Used when Modal is unavailable or disabled.
        """
        logger.info("local_inference_start", audio_path=audio_path)
        
        from app.ml.engine import run_drum_separation, run_prediction
        from app.ml.guardrails import apply_ml_guardrails
        from app.schemas.ml_contracts import PredictionResult
        import tempfile
        from pathlib import Path
        
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            
            # Step 1: Drum separation
            drums_path = tmpdir_path / "drums.wav"
            run_drum_separation(audio_path, str(drums_path))
            
            # Step 2: Hit prediction
            result = run_prediction(str(drums_path), user_bpm=user_bpm)
            
            # Step 3: Apply guardrails
            result = apply_ml_guardrails(result)
            
            # Step 4: Validate with Pydantic
            validated = PredictionResult.model_validate(result)
            
            logger.info(
                "local_inference_complete",
                total_hits=len(validated.hits),
                bpm=validated.detected_bpm,
            )
            
            return validated.model_dump()


# ---------------------------------------------------------------------------
# Singleton Instance
# ---------------------------------------------------------------------------

_modal_client: Optional[ModalClient] = None


def get_modal_client() -> ModalClient:
    """Get the singleton ModalClient instance."""
    global _modal_client
    if _modal_client is None:
        _modal_client = ModalClient()
    return _modal_client

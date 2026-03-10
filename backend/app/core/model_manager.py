"""
Model Manager - Production-grade model initialization and verification.

This module handles the complete lifecycle of model setup for DrumScribe workers:
- Demucs source separation model (htdemucs) initialization
- Custom CNN hit classification model verification
- Graceful degradation for offline development
- Structured logging with OpenTelemetry integration

Author: DrumScribe DevOps Team
"""

import os
import sys
from pathlib import Path
from typing import Optional, Tuple

import structlog

logger = structlog.get_logger(__name__)


class ModelManager:
    """
    Manages model initialization and verification for DrumScribe workers.
    
    This class handles:
    - Demucs model pre-download and caching
    - CNN model file verification
    - Environment variable configuration
    - Graceful error handling for offline development
    """
    
    def __init__(self):
        """Initialize the model manager with environment configuration."""
        self.model_uri = os.getenv("MODEL_URI", "")
        self.model_cache_dir = os.getenv("MODEL_CACHE_DIR", "/data/models")
        self.torch_home = os.getenv("TORCH_HOME", "/app/inference/demucs")
        self.storage_backend = os.getenv("STORAGE_BACKEND", "local")
        
        # Ensure TORCH_HOME is set for torch.hub
        os.environ["TORCH_HOME"] = self.torch_home
        
        logger.info(
            "model_manager_initialized",
            model_uri=self.model_uri,
            model_cache_dir=self.model_cache_dir,
            torch_home=self.torch_home,
            storage_backend=self.storage_backend,
        )
    
    def setup_demucs(self) -> bool:
        """
        Initialize Demucs htdemucs model and trigger weight download.
        
        The Demucs pretrained.get_model() returns a BagOfModels object which
        does not have a .name attribute. We handle this gracefully by simply
        loading the model without accessing non-existent attributes.
        
        Returns:
            bool: True if successful, False otherwise
        """
        logger.info("demucs_setup_start", model_name="htdemucs")
        
        try:
            from demucs import pretrained
            
            # Load the model - this triggers weight download to TORCH_HOME
            # Note: BagOfModels doesn't have .name, so we don't access it
            model = pretrained.get_model(name="htdemucs")
            
            # Verify the model loaded successfully
            if model is None:
                logger.error("demucs_setup_failed", reason="Model returned None")
                return False
            
            # Get model type for logging (safe way without accessing .name)
            model_type = type(model).__name__
            
            logger.info(
                "demucs_setup_success",
                model_type=model_type,
                torch_home=self.torch_home,
                message="Demucs weights cached successfully"
            )
            return True
            
        except ImportError as e:
            logger.error(
                "demucs_import_error",
                error=str(e),
                message="Failed to import demucs. Ensure it's installed in requirements."
            )
            return False
            
        except Exception as e:
            logger.error(
                "demucs_setup_error",
                error=str(e),
                error_type=type(e).__name__,
                message="Unexpected error during Demucs initialization"
            )
            return False
    
    def verify_cnn_model(self) -> Tuple[bool, Optional[str]]:
        """
        Verify the custom CNN hit classification model exists.
        
        This method checks if the MODEL_URI points to a local .h5 file and
        verifies its existence. If the file is missing, it logs a warning
        but does NOT fail the container (allows offline development).
        
        Returns:
            Tuple[bool, Optional[str]]: (exists, path_or_message)
        """
        if not self.model_uri:
            logger.warning(
                "cnn_model_not_configured",
                message="MODEL_URI not set. CNN hit classification will be unavailable."
            )
            return False, "MODEL_URI environment variable not set"
        
        # Check if it's a local file path (not http:// or s3://)
        if self.model_uri.startswith(("http://", "https://", "s3://")):
            logger.info(
                "cnn_model_remote",
                model_uri=self.model_uri,
                message="CNN model is remote. Will be downloaded at runtime."
            )
            return True, self.model_uri
        
        # Local file path - verify existence
        model_path = Path(self.model_uri)
        
        if model_path.exists() and model_path.is_file():
            file_size_mb = model_path.stat().st_size / (1024 * 1024)
            logger.info(
                "cnn_model_verified",
                model_path=str(model_path),
                file_size_mb=round(file_size_mb, 2),
                message="CNN model file found and verified"
            )
            return True, str(model_path)
        else:
            logger.warning(
                "cnn_model_missing",
                model_path=str(model_path),
                message=(
                    "CNN model file not found. Hit classification will be unavailable. "
                    "To enable: place complete_network.h5 in ./inference/pretrained_models/annoteators/ "
                    "and restart workers."
                )
            )
            return False, f"File not found: {model_path}"
    
    def setup_all_models(self) -> bool:
        """
        Run complete model setup workflow.
        
        This is the main entry point called by the worker entrypoint.
        It orchestrates all model initialization steps and provides
        clear feedback on what succeeded and what failed.
        
        Returns:
            bool: True if critical models are ready, False if setup failed
        """
        logger.info("model_setup_start", message="Initializing all models...")
        
        success = True
        
        # Step 1: Setup Demucs (critical for source separation)
        logger.info("step_1_demucs", message="Setting up Demucs source separation model...")
        demucs_ok = self.setup_demucs()
        
        if not demucs_ok:
            logger.error(
                "demucs_setup_failed_critical",
                message="Demucs setup failed. This is critical for audio source separation."
            )
            success = False
        
        # Step 2: Verify CNN model (optional - graceful degradation)
        logger.info("step_2_cnn", message="Verifying CNN hit classification model...")
        cnn_exists, cnn_info = self.verify_cnn_model()
        
        if not cnn_exists:
            logger.warning(
                "cnn_model_unavailable",
                info=cnn_info,
                message="CNN model not available. Workers will start but hit classification will fail."
            )
            # Don't fail the container - allow workers to start for other tasks
        else:
            logger.info("cnn_model_ready", info=cnn_info)
        
        # Summary
        if success:
            logger.info(
                "model_setup_complete",
                demucs_ready=demucs_ok,
                cnn_ready=cnn_exists,
                message="Model setup completed successfully. Worker ready to start."
            )
        else:
            logger.error(
                "model_setup_failed",
                demucs_ready=demucs_ok,
                cnn_ready=cnn_exists,
                message="Model setup failed. Worker cannot start."
            )
        
        return success


def main() -> int:
    """
    Main entry point for model setup script.
    
    Called by worker entrypoint: python -m app.core.model_manager
    
    Returns:
        int: Exit code (0 = success, 1 = failure)
    """
    logger.info("model_manager_main_start", message="Starting model setup...")
    
    try:
        manager = ModelManager()
        success = manager.setup_all_models()
        
        if success:
            logger.info("model_manager_main_success", message="Model setup completed successfully")
            return 0
        else:
            logger.error("model_manager_main_failed", message="Model setup failed")
            return 1
            
    except Exception as e:
        logger.error(
            "model_manager_main_exception",
            error=str(e),
            error_type=type(e).__name__,
            message="Unexpected error in model manager"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())

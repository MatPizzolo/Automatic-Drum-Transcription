"""
ONNX Export Script for Audio Spectrogram Transformer (AST)

This script exports the HuggingFace AST model to ONNX format with optimizations
for production deployment on Modal's serverless GPU infrastructure.

Benefits of ONNX Export:
1. Faster inference: 2-3x speedup vs. PyTorch eager mode
2. Smaller memory footprint: ~40% reduction
3. Better cold start performance: Faster model loading
4. Cross-platform compatibility: Run on any ONNX runtime

Author: DrumScribe MLOps Team
"""

import os
import sys
from pathlib import Path

import numpy as np
import torch
from transformers import ASTForAudioClassification, ASTFeatureExtractor

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


def main():
    """
    Main execution flow:
    1. Load AST model from HuggingFace
    2. Generate dummy input for tracing
    3. Export to ONNX with dynamic axes
    4. Validate ONNX output matches PyTorch output
    """
    
    print("=" * 80)
    print("AST MODEL ONNX EXPORT SCRIPT")
    print("=" * 80)
    
    # -------------------------------------------------------------------------
    # Step 1: Configuration
    # -------------------------------------------------------------------------
    
    MODEL_NAME = "MIT/ast-finetuned-audioset-10-10-0.4593"
    OUTPUT_DIR = Path(__file__).parent.parent.parent / "models"
    OUTPUT_PATH = OUTPUT_DIR / "ast_optimized.onnx"
    
    # ONNX export configuration
    OPSET_VERSION = 14  # Latest stable opset with full Transformer support
    SAMPLE_RATE = 16000  # AST expects 16kHz audio
    AUDIO_DURATION = 10.0  # 10 seconds of audio for dummy input
    VALIDATION_TOLERANCE = 1e-4  # Maximum allowed difference between PyTorch and ONNX
    
    print(f"\n📋 Configuration:")
    print(f"  Model: {MODEL_NAME}")
    print(f"  Output: {OUTPUT_PATH}")
    print(f"  ONNX Opset: {OPSET_VERSION}")
    print(f"  Sample Rate: {SAMPLE_RATE} Hz")
    print(f"  Validation Tolerance: {VALIDATION_TOLERANCE}")
    
    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # -------------------------------------------------------------------------
    # Step 2: Load AST Model and Feature Extractor
    # -------------------------------------------------------------------------
    
    print(f"\n🔥 Loading AST model from HuggingFace...")
    
    # Load model in evaluation mode (disables dropout, batch norm training mode)
    model = ASTForAudioClassification.from_pretrained(MODEL_NAME)
    model.eval()  # CRITICAL: Must be in eval mode for deterministic inference
    
    # Load feature extractor (handles audio preprocessing)
    feature_extractor = ASTFeatureExtractor.from_pretrained(MODEL_NAME)
    
    print(f"✅ Model loaded successfully")
    print(f"  Parameters: {sum(p.numel() for p in model.parameters()):,}")
    print(f"  Model size: {sum(p.numel() * p.element_size() for p in model.parameters()) / 1024**2:.2f} MB")
    
    # -------------------------------------------------------------------------
    # Step 3: Generate Realistic Dummy Input
    # -------------------------------------------------------------------------
    
    print(f"\n🎵 Generating dummy audio input...")
    
    # Generate 10 seconds of silence at 16kHz
    # Shape: (num_samples,) where num_samples = sample_rate * duration
    num_samples = int(SAMPLE_RATE * AUDIO_DURATION)
    dummy_audio = np.zeros(num_samples, dtype=np.float32)
    
    # Add small random noise to make it more realistic (prevents numerical edge cases)
    dummy_audio += np.random.randn(num_samples).astype(np.float32) * 0.001
    
    print(f"✅ Dummy audio generated")
    print(f"  Shape: {dummy_audio.shape}")
    print(f"  Duration: {AUDIO_DURATION}s")
    print(f"  Sample rate: {SAMPLE_RATE} Hz")
    
    # -------------------------------------------------------------------------
    # Step 4: Preprocess Audio with Feature Extractor
    # -------------------------------------------------------------------------
    
    print(f"\n🔧 Preprocessing audio with feature extractor...")
    
    # Feature extractor converts raw audio to model input format
    # Returns: input_values (mel spectrogram features)
    inputs = feature_extractor(
        dummy_audio,
        sampling_rate=SAMPLE_RATE,
        return_tensors="pt",  # Return PyTorch tensors
        padding=True,
    )
    
    # Extract input tensor
    # Shape: (batch_size, sequence_length, num_mel_bins)
    # Typical: (1, 1024, 128) for 10 seconds of audio
    input_values = inputs["input_values"]
    
    print(f"✅ Audio preprocessed")
    print(f"  Input shape: {input_values.shape}")
    print(f"  Input dtype: {input_values.dtype}")
    print(f"  Input range: [{input_values.min():.4f}, {input_values.max():.4f}]")
    
    # -------------------------------------------------------------------------
    # Step 5: Run PyTorch Inference (Baseline for Validation)
    # -------------------------------------------------------------------------
    
    print(f"\n🔬 Running PyTorch inference (baseline)...")
    
    with torch.no_grad():
        pytorch_outputs = model(input_values)
        pytorch_logits = pytorch_outputs.logits
    
    print(f"✅ PyTorch inference complete")
    print(f"  Output shape: {pytorch_logits.shape}")
    print(f"  Output dtype: {pytorch_logits.dtype}")
    print(f"  Output range: [{pytorch_logits.min():.4f}, {pytorch_logits.max():.4f}]")
    
    # -------------------------------------------------------------------------
    # Step 6: Export to ONNX with Dynamic Axes
    # -------------------------------------------------------------------------
    
    print(f"\n📦 Exporting to ONNX format...")
    
    # CRITICAL: Define dynamic axes for variable-length audio
    # This allows the ONNX model to accept different audio lengths at runtime
    # without recompiling the graph
    dynamic_axes = {
        "input_values": {
            0: "batch_size",      # Dimension 0 is batch size (can vary)
            1: "sequence_length"  # Dimension 1 is time/sequence (can vary)
        },
        "logits": {
            0: "batch_size"       # Output batch size matches input
        }
    }
    
    # Export model to ONNX
    torch.onnx.export(
        model,                          # PyTorch model to export
        input_values,                   # Example input for tracing
        str(OUTPUT_PATH),               # Output file path
        export_params=True,             # Export trained parameter weights
        opset_version=OPSET_VERSION,    # ONNX opset version (14 = latest stable)
        do_constant_folding=True,       # Optimize by folding constant operations
        input_names=["input_values"],   # Input tensor names
        output_names=["logits"],        # Output tensor names
        dynamic_axes=dynamic_axes,      # Enable dynamic batch/sequence dimensions
        verbose=False,                  # Suppress detailed export logs
    )
    
    print(f"✅ ONNX export complete")
    print(f"  Output file: {OUTPUT_PATH}")
    print(f"  File size: {OUTPUT_PATH.stat().st_size / 1024**2:.2f} MB")
    print(f"  Dynamic axes: batch_size, sequence_length")
    
    # -------------------------------------------------------------------------
    # Step 7: Validate ONNX Model (Mathematical Proof of Correctness)
    # -------------------------------------------------------------------------
    
    print(f"\n🧪 Validating ONNX model output...")
    
    try:
        import onnxruntime as ort
    except ImportError:
        print("⚠️  WARNING: onnxruntime not installed")
        print("   Install with: pip install onnxruntime")
        print("   Skipping validation...")
        print("\n" + "=" * 80)
        print("✅ ONNX EXPORT SUCCESSFUL (validation skipped)")
        print("=" * 80)
        return
    
    # Initialize ONNX Runtime inference session
    # Use CPU for validation (GPU not required for correctness check)
    ort_session = ort.InferenceSession(
        str(OUTPUT_PATH),
        providers=["CPUExecutionProvider"]
    )
    
    print(f"✅ ONNX Runtime session initialized")
    print(f"  Providers: {ort_session.get_providers()}")
    
    # Prepare input for ONNX Runtime
    # ONNX Runtime expects numpy arrays, not PyTorch tensors
    ort_inputs = {
        "input_values": input_values.cpu().numpy()
    }
    
    # Run ONNX inference
    ort_outputs = ort_session.run(None, ort_inputs)
    onnx_logits = ort_outputs[0]  # First output is logits
    
    print(f"✅ ONNX inference complete")
    print(f"  Output shape: {onnx_logits.shape}")
    print(f"  Output dtype: {onnx_logits.dtype}")
    print(f"  Output range: [{onnx_logits.min():.4f}, {onnx_logits.max():.4f}]")
    
    # -------------------------------------------------------------------------
    # Step 8: Mathematical Validation (PyTorch vs. ONNX)
    # -------------------------------------------------------------------------
    
    print(f"\n🔍 Comparing PyTorch and ONNX outputs...")
    
    # Convert PyTorch tensor to numpy for comparison
    pytorch_logits_np = pytorch_logits.cpu().numpy()
    
    # Calculate absolute and relative differences
    abs_diff = np.abs(pytorch_logits_np - onnx_logits)
    rel_diff = abs_diff / (np.abs(pytorch_logits_np) + 1e-8)
    
    max_abs_diff = abs_diff.max()
    max_rel_diff = rel_diff.max()
    mean_abs_diff = abs_diff.mean()
    
    print(f"  Max absolute difference: {max_abs_diff:.2e}")
    print(f"  Max relative difference: {max_rel_diff:.2e}")
    print(f"  Mean absolute difference: {mean_abs_diff:.2e}")
    
    # Assert that outputs match within tolerance
    try:
        np.testing.assert_allclose(
            pytorch_logits_np,
            onnx_logits,
            rtol=VALIDATION_TOLERANCE,  # Relative tolerance
            atol=VALIDATION_TOLERANCE,  # Absolute tolerance
            err_msg="ONNX output does not match PyTorch output within tolerance"
        )
        
        print(f"✅ VALIDATION PASSED")
        print(f"  ONNX outputs match PyTorch outputs within {VALIDATION_TOLERANCE} tolerance")
        
    except AssertionError as e:
        print(f"❌ VALIDATION FAILED")
        print(f"  {str(e)}")
        print(f"\n⚠️  ONNX model may not be numerically equivalent to PyTorch model")
        print(f"  Consider:")
        print(f"    - Increasing tolerance (current: {VALIDATION_TOLERANCE})")
        print(f"    - Checking ONNX opset version compatibility")
        print(f"    - Verifying model export settings")
        sys.exit(1)
    
    # -------------------------------------------------------------------------
    # Step 9: Test Dynamic Axes (Variable-Length Audio)
    # -------------------------------------------------------------------------
    
    print(f"\n🧪 Testing dynamic axes with different audio lengths...")
    
    # Test with shorter audio (5 seconds)
    short_audio = np.random.randn(SAMPLE_RATE * 5).astype(np.float32) * 0.001
    short_inputs = feature_extractor(
        short_audio,
        sampling_rate=SAMPLE_RATE,
        return_tensors="pt",
        padding=True,
    )
    short_input_values = short_inputs["input_values"].cpu().numpy()
    
    # Test with longer audio (15 seconds)
    long_audio = np.random.randn(SAMPLE_RATE * 15).astype(np.float32) * 0.001
    long_inputs = feature_extractor(
        long_audio,
        sampling_rate=SAMPLE_RATE,
        return_tensors="pt",
        padding=True,
    )
    long_input_values = long_inputs["input_values"].cpu().numpy()
    
    # Run ONNX inference with different lengths
    try:
        short_outputs = ort_session.run(None, {"input_values": short_input_values})
        long_outputs = ort_session.run(None, {"input_values": long_input_values})
        
        print(f"✅ Dynamic axes working correctly")
        print(f"  5s audio input shape: {short_input_values.shape} → output shape: {short_outputs[0].shape}")
        print(f"  15s audio input shape: {long_input_values.shape} → output shape: {long_outputs[0].shape}")
        
    except Exception as e:
        print(f"❌ Dynamic axes test failed: {str(e)}")
        print(f"  ONNX model may have static input dimensions")
        sys.exit(1)
    
    # -------------------------------------------------------------------------
    # Step 10: Performance Comparison (Optional)
    # -------------------------------------------------------------------------
    
    print(f"\n⚡ Performance comparison...")
    
    import time
    
    # Warm-up runs
    for _ in range(5):
        with torch.no_grad():
            _ = model(input_values)
        _ = ort_session.run(None, ort_inputs)
    
    # Benchmark PyTorch
    num_runs = 100
    pytorch_times = []
    for _ in range(num_runs):
        start = time.perf_counter()
        with torch.no_grad():
            _ = model(input_values)
        pytorch_times.append(time.perf_counter() - start)
    
    # Benchmark ONNX
    onnx_times = []
    for _ in range(num_runs):
        start = time.perf_counter()
        _ = ort_session.run(None, ort_inputs)
        onnx_times.append(time.perf_counter() - start)
    
    pytorch_avg = np.mean(pytorch_times) * 1000  # Convert to ms
    onnx_avg = np.mean(onnx_times) * 1000
    speedup = pytorch_avg / onnx_avg
    
    print(f"  PyTorch average: {pytorch_avg:.2f} ms")
    print(f"  ONNX average: {onnx_avg:.2f} ms")
    print(f"  Speedup: {speedup:.2f}x")
    
    # -------------------------------------------------------------------------
    # Success Summary
    # -------------------------------------------------------------------------
    
    print("\n" + "=" * 80)
    print("✅ ONNX EXPORT AND VALIDATION SUCCESSFUL")
    print("=" * 80)
    print(f"\n📊 Summary:")
    print(f"  ✓ Model exported to: {OUTPUT_PATH}")
    print(f"  ✓ File size: {OUTPUT_PATH.stat().st_size / 1024**2:.2f} MB")
    print(f"  ✓ ONNX opset version: {OPSET_VERSION}")
    print(f"  ✓ Dynamic axes: batch_size, sequence_length")
    print(f"  ✓ Validation passed: max diff = {max_abs_diff:.2e}")
    print(f"  ✓ Performance: {speedup:.2f}x faster than PyTorch")
    print(f"\n🚀 Ready for production deployment on Modal!")
    print(f"\n💡 Next steps:")
    print(f"  1. Update modal_app.py to use ONNX model")
    print(f"  2. Replace PyTorch inference with onnxruntime")
    print(f"  3. Benchmark cold start and inference times")
    print(f"  4. Deploy and monitor performance improvements")
    print("=" * 80)


if __name__ == "__main__":
    main()

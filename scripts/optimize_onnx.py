#!/usr/bin/env python3
"""
PRAHARI ONNX Model Optimization Pipeline

Converts PyTorch models (YOLOv8, etc.) to ONNX format and applies
optimization passes for faster CPU/GPU inference.

Inspired by SmartSurv's ONNX compilation approach (3x speed boost).

Usage:
    python scripts/optimize_onnx.py --input model.pt --output model.onnx
    python scripts/optimize_onnx.py --input model.pt --output model.onnx --half
    python scripts/optimize_onnx.py --input model.pt --output model.onnx --optimize
"""

import argparse
import os
import sys
from pathlib import Path

try:
    import torch
    from torch.onnx import export as onnx_export
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False
    print('PyTorch not found. Install with: pip install torch')
    print('You can still use pre-converted ONNX models.')

try:
    import onnx
    from onnx import optimizer
    HAS_ONNX = True
except ImportError:
    HAS_ONNX = False

try:
    import onnxruntime as ort
    HAS_ONNXRUNTIME = True
except ImportError:
    HAS_ONNXRUNTIME = False


def convert_pytorch_to_onnx(input_path: str, output_path: str, half: bool = False) -> bool:
    """Convert a PyTorch model to ONNX format."""
    if not HAS_TORCH:
        print('ERROR: PyTorch is required for model conversion')
        return False

    if not os.path.exists(input_path):
        print(f'ERROR: Input model not found: {input_path}')
        return False

    print(f'Loading model: {input_path}')
    model = torch.load(input_path, map_location='cpu', weights_only=False)
    if hasattr(model, 'model'):
        model = model.model
    model.eval()

    if half:
        model = model.half()

    dummy_input = torch.randn(1, 3, 640, 640)
    if half:
        dummy_input = dummy_input.half()

    print(f'Exporting to ONNX: {output_path}')
    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    onnx_export(
        model,
        dummy_input,
        output_path,
        export_params=True,
        opset_version=14,
        do_constant_folding=True,
    )
    print(f'ONNX model saved: {output_path}')
    return True


def optimize_onnx_model(input_path: str, output_path: str, provider: str = 'auto') -> bool:
    """Apply ONNX optimization passes (constant folding, fusion, etc.)."""
    if not HAS_ONNX:
        print('ERROR: onnx package required for optimization')
        print('Install with: pip install onnx onnxoptimizer')
        return False

    if not os.path.exists(input_path):
        print(f'ERROR: Input model not found: {input_path}')
        return False

    print(f'Optimizing ONNX model: {input_path} -> {output_path}')
    model = onnx.load(input_path)

    passes = [
        'eliminate_nop_transpose',
        'fuse_consecutive_squeezes',
        'fuse_consecutive_transposes',
        'fuse_consecutive_single_ops',
        'fuse_consecutive_flattens',
    ]

    if not HAS_ONNXRUNTIME:
        print('WARNING: onnxruntime not found, skipping provider-specific optimization')
    else:
        if provider == 'auto':
            available = ort.get_available_providers()
            if 'CUDAExecutionProvider' in available:
                provider = 'cuda'
            elif 'CoreMLExecutionProvider' in available:
                provider = 'coreml'
            elif 'OpenVINOExecutionProvider' in available:
                provider = 'openvino'
            else:
                provider = 'cpu'
        print(f'Using execution provider: {provider}')

    try:
        opt_model = optimizer.optimize_model(model, passes)
        opt_model.save_model_to_file(output_path)
        print(f'Optimized model saved: {output_path}')
        return True
    except Exception as e:
        print(f'ERROR during optimization: {e}')
        return False


def quantize_onnx_model(input_path: str, output_path: str, mode: str = 'dynamic') -> bool:
    """Quantize ONNX model for smaller size and faster CPU inference."""
    try:
        from onnxruntime.quantization import quantize_dynamic, quantize_static, QuantType
    except ImportError:
        print('ERROR: onnxruntime.quantization not available')
        print('Install with: pip install onnxruntime')
        return False

    if not os.path.exists(input_path):
        print(f'ERROR: Input model not found: {input_path}')
        return False

    print(f'Quantizing ONNX model: {input_path} -> {output_path}')
    print(f'Quantification mode: {mode}')

    if mode == 'dynamic':
        quantize_dynamic(
            input_path,
            output_path,
            weight_type=QuantType.QInt8,
        )
    elif mode == 'static':
        print('WARNING: Static quantization requires calibration data. Using dynamic instead.')
        quantize_dynamic(
            input_path,
            output_path,
            weight_type=QuantType.QInt8,
        )
    else:
        print(f'ERROR: Unknown quantization mode: {mode}')
        return False

    input_size = os.path.getsize(input_path) / (1024 * 1024)
    output_size = os.path.getsize(output_path) / (1024 * 1024)
    print(f'Model size: {input_size:.1f} MB -> {output_size:.1f} MB')
    print(f'Quantized model saved: {output_path}')
    return True


def benchmark_onnx_model(model_path: str, provider: str = 'auto', warmup: int = 5, iterations: int = 100) -> dict:
    """Benchmark ONNX model inference speed."""
    if not HAS_ONNXRUNTIME:
        print('ERROR: onnxruntime not found for benchmarking')
        return {}

    if provider == 'auto':
        available = ort.get_available_providers()
        if 'CUDAExecutionProvider' in available:
            provider = 'CUDAExecutionProvider'
        elif 'CoreMLExecutionProvider' in available:
            provider = 'CoreMLExecutionProvider'
        else:
            provider = 'CPUExecutionProvider'

    print(f'Benchmarking: {model_path}')
    print(f'Execution provider: {provider}')

    sess_options = ort.SessionOptions()
    sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

    session = ort.InferenceSession(model_path, sess_options, providers=[provider])
    input_meta = session.get_inputs()[0]
    input_shape = input_meta.shape
    print(f'Input shape: {input_shape}')

    import time
    import numpy as np

    input_name = input_meta.name
    dummy_input = np.random.randn(1, 3, 640, 640).astype(np.float32)

    for _ in range(warmup):
        _ = session.run(None, {input_name: dummy_input})

    start = time.perf_counter()
    for _ in range(iterations):
        _ = session.run(None, {input_name: dummy_input})
    elapsed = time.perf_counter() - start

    avg_ms = (elapsed / iterations) * 1000
    fps = 1000 / avg_ms if avg_ms > 0 else 0

    print(f'Average inference time: {avg_ms:.2f} ms')
    print(f'Throughput: {fps:.1f} FPS')

    return {
        'avg_ms': round(avg_ms, 2),
        'fps': round(fps, 1),
        'provider': provider,
        'iterations': iterations,
    }


def main():
    parser = argparse.ArgumentParser(description='PRAHARI ONNX Model Optimization Pipeline')
    parser.add_argument('--input', '-i', required=True, help='Input model path (.pt)')
    parser.add_argument('--output', '-o', required=True, help='Output model path (.onnx)')
    parser.add_argument('--half', action='store_true', help='Use FP16 half precision')
    parser.add_argument('--optimize', action='store_true', help='Apply ONNX optimization passes')
    parser.add_argument('--quantize', choices=['dynamic', 'static'], help='Quantize model (reduces size, boosts CPU speed)')
    parser.add_argument('--benchmark', action='store_true', help='Benchmark the model after optimization')
    parser.add_argument('--provider', default='auto', help='ONNX Runtime execution provider (default: auto)')

    args = parser.parse_args()

    if not args.optimize and not args.quantize and not args.half:
        print('No operations selected. Use --optimize or --quantize or --half')
        parser.print_help()
        sys.exit(1)

    if args.half or (args.optimize and not os.path.exists(args.output)):
        success = convert_pytorch_to_onnx(args.input, args.output, args.half)
        if not success:
            sys.exit(1)

    if args.optimize:
        optimized_path = args.output.replace('.onnx', '_optimized.onnx')
        success = optimize_onnx_model(args.output, optimized_path, args.provider)
        if success:
            args.output = optimized_path

    if args.quantize:
        quantized_path = args.output.replace('.onnx', '_quantized.onnx')
        success = quantize_onnx_model(args.output, quantized_path, args.quantize)
        if success:
            args.output = quantized_path

    if args.benchmark:
        benchmark_onnx_model(args.output, args.provider)

    print(f'\nDone! Optimized model saved to: {args.output}')


if __name__ == '__main__':
    main()

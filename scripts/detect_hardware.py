#!/usr/bin/env python3
"""
PRAHARI Hardware Auto-Detection Utility

Detects available hardware acceleration (GPU, CUDA, TensorRT, CoreML, Coral TPU, etc.)
and recommends the optimal model format for each adapter.

Inspired by Locus Vision's hardware auto-detection pattern.

Usage:
    python scripts/detect_hardware.py
    python scripts/detect_hardware.py --json
    python scripts/detect_hardware.py --recommend
"""

import json
import os
import platform
import subprocess
import sys
from typing import Any

SYSTEM = platform.system()
MACHINE = platform.machine()


def detect_nvidia_gpu() -> dict[str, Any] | None:
    """Check for NVIDIA GPU with CUDA support."""
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=name,memory.total,driver_version', '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.strip().split(',')
            if len(parts) >= 3:
                return {
                    'vendor': 'nvidia',
                    'name': parts[0],
                    'memory_gb': float(parts[1]) / 1024,
                    'driver_version': parts[2],
                    'acceleration': ['cuda', 'tensorrt'],
                }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def detect_intel_gpu() -> dict[str, Any] | None:
    """Check for Intel integrated/discrete GPU."""
    try:
        if SYSTEM == 'Windows':
            result = subprocess.run(
                ['powershell', '-Command', 'Get-WmiObject -Class Win32_VideoController | Select-Object Name,AdapterRAM'],
                capture_output=True, text=True, timeout=5
            )
            if 'Intel' in result.stdout and 'HD Graphics' in result.stdout or 'Iris' in result.stdout:
                return {'vendor': 'intel_gpu', 'name': 'Intel Graphics', 'acceleration': ['openvino', 'cpu']}
        else:
            result = subprocess.run(['lspci'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and 'Intel' in result.stdout:
                gpu_lines = [l for l in result.stdout.split('\n') if 'VGA' in l or 'Display' in l]
                if gpu_lines:
                    return {
                        'vendor': 'intel_gpu',
                        'name': gpu_lines[0].strip(),
                        'acceleration': ['openvino', 'cpu'],
                    }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def detect_coraltpu() -> dict[str, Any] | None:
    """Check for Google Coral USB/M.2 TPU."""
    try:
        result = subprocess.run(['lsusb'], capture_output=True, text=True, timeout=5)
        if '1a6e:0805' in result.stdout or 'Google' in result.stdout:
            return {
                'vendor': 'google_coral',
                'name': 'Coral TPU',
                'acceleration': ['edgetpu', 'tflite'],
            }
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def detect_apple_silicon() -> dict[str, Any] | None:
    """Check for Apple Silicon (M1/M2/M3) with CoreML support."""
    if SYSTEM == 'Darwin' and MACHINE == 'arm64':
        return {
            'vendor': 'apple',
            'name': 'Apple Silicon',
            'acceleration': ['coreml', 'cpu'],
        }
    return None


def detect_cuda() -> dict[str, Any] | None:
    """Check for CUDA installation."""
    try:
        result = subprocess.run(['nvcc', '--version'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return {'vendor': 'nvidia', 'cuda_available': True}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def detect_tensorrt() -> dict[str, Any] | None:
    """Check for TensorRT."""
    try:
        trt_path = os.environ.get('TENSORRT_HOME', '/usr/src/tensorrt')
        if os.path.exists(trt_path):
            return {'vendor': 'nvidia', 'tensorrt_available': True}
    except Exception:
        pass
    return None


def detect_onnxruntime() -> dict[str, Any] | None:
    """Check if ONNX Runtime is installed."""
    try:
        import onnxruntime as ort
        providers = ort.get_available_providers()
        return {
            'vendor': 'onnxruntime',
            'available': True,
            'providers': providers,
        }
    except ImportError:
        return {'vendor': 'onnxruntime', 'available': False}


def detect_openvino() -> dict[str, Any] | None:
    """Check for OpenVINO."""
    try:
        result = subprocess.run(['which', 'benchmark_app'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return {'vendor': 'intel', 'openvino_available': True}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def detect_torch() -> dict[str, Any] | None:
    """Check for PyTorch and CUDA availability."""
    try:
        import torch
        return {
            'vendor': 'pytorch',
            'version': torch.__version__,
            'cuda_available': torch.cuda.is_available() if hasattr(torch, 'cuda') else False,
            'device_count': torch.cuda.device_count() if hasattr(torch, 'cuda') else 0,
            'device_name': torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        }
    except ImportError:
        return {'vendor': 'pytorch', 'available': False}


def detect_system_specs() -> dict[str, Any]:
    """Get basic system specifications."""
    import multiprocessing

    cpu_info = platform.processor() or 'Unknown'
    ram_gb = 0
    try:
        if SYSTEM == 'Linux':
            with open('/proc/meminfo') as f:
                for line in f:
                    if line.startswith('MemTotal'):
                        ram_gb = int(line.split()[1]) / (1024 * 1024)
                        break
        elif SYSTEM == 'Darwin':
            result = subprocess.run(['sysctl', '-n', 'hw.memsize'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                ram_gb = int(result.stdout.strip()) / (1024 ** 3)
        elif SYSTEM == 'Windows':
            import ctypes
            kernel32 = ctypes.windll.kernel32
            c_uint = ctypes.c_uint
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ('dwLength', c_uint),
                    ('dwMemoryLoad', c_uint),
                    ('ullTotalPhys', ctypes.c_ulonglong),
                    ('ullAvailPhys', ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                ram_gb = stat.ullTotalPhys / (1024 ** 3)
    except Exception:
        pass

    return {
        'os': f'{SYSTEM} {platform.release()}',
        'arch': MACHINE,
        'cpu': cpu_info,
        'cpu_cores': multiprocessing.cpu_count(),
        'ram_gb': round(ram_gb, 1),
        'python_version': platform.python_version(),
    }


def recommend_model_format(hardware: dict[str, Any]) -> str:
    """Recommend the optimal model format based on detected hardware."""
    accelerations: list[str] = hardware.get('accelerations', [])

    if 'cuda' in accelerations or 'tensorrt' in accelerations:
        return 'onnx_cuda'
    if 'coreml' in accelerations:
        return 'coreml'
    if 'edgetpu' in accelerations:
        return 'tflite_edgetpu'
    if 'openvino' in accelerations:
        return 'openvino_ir'
    if 'cuda' in accelerations:
        return 'onnx'

    return 'onnx_cpu'


def detect_all() -> dict[str, Any]:
    """Run all hardware detection checks."""
    system_specs = detect_system_specs()

    gpus: list[dict[str, Any]] = []
    nvidia = detect_nvidia_gpu()
    if nvidia:
        gpus.append(nvidia)

    intel_gpu = detect_intel_gpu()
    if intel_gpu:
        gpus.append(intel_gpu)

    apple = detect_apple_silicon()
    if apple:
        gpus.append(apple)

    accelerations: list[str] = []
    for gpu in gpus:
        accelerations.extend(gpu.get('acceleration', []))

    torch_info = detect_torch()
    onnx_info = detect_onnxruntime()
    cuda_info = detect_cuda()
    trt_info = detect_tensorrt()
    openvino_info = detect_openvino()
    coral = detect_coraltpu()

    if torch_info and torch_info.get('cuda_available'):
        accelerations.append('pytorch_cuda')
    if cuda_info:
        accelerations.append('cuda')
    if trt_info and trt_info.get('tensorrt_available'):
        accelerations.append('tensorrt')
    if onnx_info and onnx_info.get('available'):
        accelerations.extend([f'onnxruntime_{p}' for p in onnx_info.get('providers', [])])
    if openvino_info and openvino_info.get('openvino_available'):
        accelerations.append('openvino')
    if coral:
        accelerations.extend(coral.get('acceleration', []))

    all_hw = {
        'system': system_specs,
        'gpus': gpus,
        'torch': torch_info,
        'onnxruntime': onnx_info,
        'cuda': cuda_info,
        'tensorrt': trt_info,
        'openvino': openvino_info,
        'coral_tpu': coral,
    }

    all_hw['accelerations'] = list(set(accelerations))
    all_hw['recommended_model_format'] = recommend_model_format({'accelerations': accelerations})

    return all_hw


def print_report(hardware: dict[str, Any]) -> None:
    """Print a human-readable hardware report."""
    sys_info = hardware['system']

    print('=' * 56)
    print('  PRAHARI Hardware Detection Report')
    print('=' * 56)
    print()
    print(f'  System:       {sys_info["os"]}')
    print(f'  Architecture: {sys_info["arch"]}')
    print(f'  CPU:          {sys_info["cpu"]}')
    print(f'  CPU Cores:    {sys_info["cpu_cores"]}')
    print(f'  RAM:          {sys_info["ram_gb"]} GB')
    print(f'  Python:       {sys_info["python_version"]}')
    print()

    gpus = hardware.get('gpus', [])
    if gpus:
        print('GPUs:')
        for gpu in gpus:
            print(f'  - {gpu}')
    else:
        print('GPUs: None detected')
    print()

    accelerations = hardware.get('accelerations', [])
    if accelerations:
        print('Hardware Acceleration Support:')
        for acc in accelerations:
            print(f'  [+] {acc}')
    else:
        print('Hardware Acceleration: None')
    print()

    print(f'Recommended Model Format: {hardware["recommended_model_format"]}')
    print()

    format_descriptions = {
        'onnx_cuda': 'ONNX Runtime with CUDA — fastest for NVIDIA GPUs',
        'coreml': 'CoreML — optimized for Apple Silicon (M1/M2/M3)',
        'tflite_edgetpu': 'TensorFlow Lite with Edge TPU — for Google Coral devices',
        'openvino_ir': 'OpenVINO IR — optimized for Intel CPUs/iGPUs',
        'onnx': 'ONNX Runtime — broad compatibility',
        'onnx_cpu': 'ONNX Runtime (CPU only) — for systems without GPU',
    }
    print(f'Format Description: {format_descriptions.get(hardware["recommended_model_format"], "Unknown")}')
    print()
    print('=' * 56)


if __name__ == '__main__':
    hardware = detect_all()

    if '--json' in sys.argv:
        print(json.dumps(hardware, indent=2))
    elif '--recommend' in sys.argv:
        print(hardware['recommended_model_format'])
    else:
        print_report(hardware)

"""MLX Executor — ejecuta benchmarks de inferencia con MLX en el Mac Mini.

Sigue la misma interfaz que test_executor.py pero usa mlx-lm en lugar de llama-cli.
"""
import time
import json
from dataclasses import dataclass
from typing import Optional, List

from .test_executor import TestResult

MLX_MODELS_BASE = "/Users/admin/Documents/huggingface/models/mlx-community"

# Mapa de nombres de modelo (carpeta) a metadata
MLX_MODEL_CATALOG = {
    "gemma-3-1b-it-8bit": {"params_b": 1.0, "arch": "dense", "attn": "gqa", "context_max": 32768},
    "gemma-2-2b-it-4bit": {"params_b": 2.0, "arch": "dense", "attn": "gqa", "context_max": 8192},
    "granite-3.3-2b-instruct-4bit": {"params_b": 2.0, "arch": "dense", "attn": "gqa", "context_max": 32768},
    "Llama-3.2-1B-Instruct-4bit": {"params_b": 1.0, "arch": "dense", "attn": "gqa", "context_max": 131072},
    "Llama-3.2-3B-Instruct-4bit": {"params_b": 3.0, "arch": "dense", "attn": "gqa", "context_max": 131072},
    "Llama-3.2-11B-Vision-Instruct-4bit": {"params_b": 11.0, "arch": "dense", "attn": "gqa", "context_max": 131072},
    "gemma-3-4b-it-8bit": {"params_b": 4.0, "arch": "dense", "attn": "gqa", "context_max": 32768},
    "MiMo-7B-SFT-4bit": {"params_b": 7.0, "arch": "dense", "attn": "gqa", "context_max": 32768},
    "Mistral-7B-Instruct-v0.3-4bit": {"params_b": 7.0, "arch": "dense", "attn": "gqa", "context_max": 32768},
    "Mistral-Nemo-Instruct-2407-4bit": {"params_b": 12.0, "arch": "dense", "attn": "gqa", "context_max": 131072},
    "Qwen2.5-1.5B-Instruct-4bit": {"params_b": 1.5, "arch": "dense", "attn": "gqa", "context_max": 32768},
    "Qwen2.5-14B-Instruct-4bit": {"params_b": 14.0, "arch": "dense", "attn": "gqa", "context_max": 32768},
}


def run_mlx_test(model_name: str, max_tokens: int = 256, temp: float = 0.0) -> TestResult:
    """Ejecuta un test de generacion con MLX."""
    from mlx_lm import load, generate

    model_path = f"{MLX_MODELS_BASE}/{model_name}"
    meta = MLX_MODEL_CATALOG.get(model_name, {})

    start_time = time.time()
    
    # Carga
    load_start = time.time()
    model, tokenizer = load(model_path)
    load_time = time.time() - load_start

    # Generacion
    gen_start = time.time()
    prompt = "Hello, please generate a short response."
    result = generate(model, tokenizer, prompt, max_tokens=max_tokens, temp=temp, verbose=False)
    gen_time = time.time() - gen_start
    total_time = time.time() - start_time

    # Estimar tokens generados (rough)
    gen_tokens = len(result.split())

    result_obj = TestResult(
        config_id=model_name,
        status="ok",
        model_name=model_name,
        hardware="m1-mini-16gb",
        context_len=0,
        kv_format="mlx-4bit",
        flash_attn=True,
        quant="mlx-4bit",
        decode_speed=gen_tokens / gen_time if gen_time > 0 else 0,
        prefill_speed=None,
        prompt_tokens=0,
        generated_tokens=gen_tokens,
        load_time_ms=load_time * 1000,
        total_time_ms=total_time * 1000,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )
    return result_obj


def benchmark_mlx_model(model_name: str) -> TestResult:
    """Benchmark completo de un modelo MLX."""
    print(f"\n=== MLX Benchmark: {model_name} ===")
    result = run_mlx_test(model_name)
    print(f"  Speed: {result.decode_speed:.1f} tok/s")
    print(f"  Load: {result.load_time_ms/1000:.1f}s")
    print(f"  Total: {result.total_time_ms/1000:.1f}s")
    return result

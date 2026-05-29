"""Test Executor — ejecuta un test de inferencia controlado con llama-cli.

Filosofia:
- Timeouts separados por fase (carga, prefill, generacion)
- Parseo estricto de --show-timings
- Deteccion de OOM, crash, timeout
- Limpieza total entre tests
- Serie estricta: un test por invocacion
"""
import re
import os
import sys
import time
import json
import signal
import subprocess
from dataclasses import dataclass, field
from typing import Optional, List, Dict

from .model_registry import get_model, ModelSpec
from .test_matrix_generator import TestConfig
from .ram_budget import RAM_DISPONIBLE_GB

LLAMA_CLI_BIN = "/opt/homebrew/bin/llama-cli"

# Timeouts por fase (segundos)
TIMEOUT_LOAD = 60       # carga del modelo a RAM/GPU
TIMEOUT_PREFILL_BASE = 60  # base + 1s por cada 1000 tokens de prompt
TIMEOUT_GENERATE = 120  # 256 tokens a cualquier velocidad
TIMEOUT_TOTAL_WALL = 600  # hard limit absoluto


@dataclass
class TestResult:
    """Resultado completo de un test."""
    config_id: str
    status: str  # ok, oom, timeout, error, skipped
    model_name: str
    context_len: int
    kv_format: str
    flash_attn: bool
    quant: str
    hardware: str = "m1-mini-16gb"

    # Metricas extraidas
    decode_speed: Optional[float] = None      # tokens/s generacion
    prefill_speed: Optional[float] = None     # tokens/s prefill
    prompt_tokens: Optional[int] = None
    generated_tokens: Optional[int] = None
    load_time_ms: Optional[float] = None
    total_time_ms: Optional[float] = None

    # RAM observada
    ram_model_gb: Optional[float] = None
    ram_context_gb: Optional[float] = None
    ram_total_observed_gb: Optional[float] = None

    # RAM estimada (pre-test)
    ram_estimate_gb: Optional[float] = None

    # Errores
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    raw_output: str = ""

    # Timestamps
    timestamp: str = ""
    duration_s: float = 0.0

    @property
    def success(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict:
        return {
            "config_id": self.config_id,
            "status": self.status,
            "model_name": self.model_name,
            "hardware": self.hardware,
            "context_len": self.context_len,
            "kv_format": self.kv_format,
            "flash_attn": self.flash_attn,
            "quant": self.quant,
            "decode_speed_tok_s": round(self.decode_speed, 2) if self.decode_speed else None,
            "prefill_speed_tok_s": round(self.prefill_speed, 2) if self.prefill_speed else None,
            "prompt_tokens": self.prompt_tokens,
            "generated_tokens": self.generated_tokens,
            "load_time_ms": round(self.load_time_ms, 1) if self.load_time_ms else None,
            "total_time_ms": round(self.total_time_ms, 1) if self.total_time_ms else None,
            "ram_model_gb": round(self.ram_model_gb, 2) if self.ram_model_gb else None,
            "ram_context_gb": round(self.ram_context_gb, 2) if self.ram_context_gb else None,
            "ram_total_observed_gb": round(self.ram_total_observed_gb, 2) if self.ram_total_observed_gb else None,
            "ram_estimate_gb": round(self.ram_estimate_gb, 2) if self.ram_estimate_gb else None,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "timestamp": self.timestamp,
            "duration_s": round(self.duration_s, 1),
        }


def generate_prompt(n_tokens: int, model_name: str = "default") -> str:
    """Genera un prompt de exactamente n_tokens (aproximadamente).

    Usa repeticion de palabras comunes para minimizar variabilidad
    en la tokenizacion. El prompt simula una query de RAG larga.
    """
    word = "intelligence"
    repeat = max(1, n_tokens // 5)
    sentences = []
    for i in range(repeat):
        sentences.append(
            f"The concept of {word} in modern artificial {word} "
            f"systems requires deep understanding of {word} "
            f"processing and reasoning capabilities."
        )
    body = " ".join(sentences)
    return (
        f"<|im_start|>system\nYou are a precise assistant.\n<|im_end|>\n"
        f"<|im_start|>user\nAnalyze the following research passage:\n\n{body}\n\n"
        f"Provide a concise summary.\n<|im_end|>\n<|im_start|>assistant\n"
    )


def _parse_number_any(s: str) -> float:
    """Convierte un numero con coma o punto decimal a float."""
    s = s.strip().replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    return float(s)


def parse_timing_output(output: str) -> dict:
    """Extrae metricas del output de llama-cli con --show-timings.

    Soporta:
    - Formato localizado: [ Prompt: XX,X t/s | Generation: XX,X t/s ]
    - Formato llama_print_timings: estandar
    - Memory breakdown de Metal
    """
    metrics = {}

    # --- Formato localizado: [ Prompt: XX,X t/s | Generation: XX,X t/s ] ---
    m = re.search(r"\[\s*Prompt:\s*([\d,]+\.?\d*)\s*t/s\s*\|\s*Generation:\s*([\d,]+\.?\d*)\s*t/s\s*\]", output)
    if m:
        try:
            metrics["prompt_speed_tok_s"] = _parse_number_any(m.group(1))
            metrics["generate_speed_tok_s"] = _parse_number_any(m.group(2))
        except ValueError:
            pass

    # --- Formato llama_print_timings: (estandar, punto decimal) ---
    patterns = {
        "load_time_ms": r"llama_print_timings:\s+load time\s+=\s+(\d+\.?\d*)\s+ms",
        "prompt_eval_time_ms": r"llama_print_timings:\s+prompt eval time\s+=\s+(\d+\.?\d*)\s+ms",
        "eval_time_ms": r"llama_print_timings:\s+eval time\s+=\s+(\d+\.?\d*)\s+ms",
        "total_time_ms": r"llama_print_timings:\s+total time\s+=\s+(\d+\.?\d*)\s+ms",
        "prompt_tokens": r"llama_print_timings:\s+prompt eval time\s+=\s+[\d.]+\s+ms\s+/\s+(\d+)\s+tokens",
        "generated_tokens": r"llama_print_timings:\s+eval time\s+=\s+[\d.]+\s+ms\s+/\s+(\d+)\s+runs",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, output)
        if match:
            metrics[key] = float(match.group(1))

    # Recalcular speeds de llama_print_timings si no vienen del formato localizado
    if "generate_speed_tok_s" not in metrics and "eval_time_ms" in metrics and "generated_tokens" in metrics:
        gt = metrics["generated_tokens"]
        et_ms = metrics["eval_time_ms"]
        if et_ms > 0:
            metrics["generate_speed_tok_s"] = gt / (et_ms / 1000.0)

    if "prompt_speed_tok_s" not in metrics and "prompt_eval_time_ms" in metrics and "prompt_tokens" in metrics:
        pt = metrics["prompt_tokens"]
        pt_ms = metrics["prompt_eval_time_ms"]
        if pt_ms > 0:
            metrics["prompt_speed_tok_s"] = pt / (pt_ms / 1000.0)

    # --- Memory breakdown: common_memory_breakdown_print ---
    # Line: |   - MTL0 | 25559 = 20541 + (5016 =  4460 +     252 +     304) +           0 |
    mem_match = re.search(
        r"\|\s*-\s+MTL0.*?\|\s*\d+\s*=\s*\d+\s*\+\s*\(\s*\d+\s*=\s*(\d+)\s*\+\s*(\d+)\s*\+\s*(\d+)",
        output
    )
    if mem_match:
        metrics["vram_model_mb"] = float(mem_match.group(1))
        metrics["vram_context_mb"] = float(mem_match.group(2))
        metrics["vram_compute_mb"] = float(mem_match.group(3))

    # Host memory
    host_match = re.search(r"\|\s*-\s+Host\s*\|\s*\s*(\d+)", output)
    if host_match:
        metrics["vram_host_mb"] = float(host_match.group(1))

    # --- Detectar OOM ---
    oom_patterns = [
        r"failed to allocate", r"out of memory", r"cannot allocate",
        r"Killed", r"signal 9", r"std::bad_alloc", r"ggml_metal.*failed",
        r"error loading model", r"not enough memory",
    ]
    for pat in oom_patterns:
        if re.search(pat, output, re.IGNORECASE):
            metrics["oom_detected"] = True
            break

    return metrics


def run_single_test(
    test_cfg: TestConfig,
    model_spec: ModelSpec,
    prompt: Optional[str] = None,
    llama_bin: str = LLAMA_CLI_BIN,
    timeout_load: int = TIMEOUT_LOAD,
    timeout_generate: int = TIMEOUT_GENERATE,
    timeout_total: int = TIMEOUT_TOTAL_WALL,
) -> TestResult:
    """Ejecuta un test individual y retorna TestResult.

    1. Verifica que el modelo exista localmente
    2. Construye comando llama-cli
    3. Ejecuta con timeout por fase
    4. Parsea output
    5. Detecta errores
    """
    start_time = time.time()
    result = TestResult(
        config_id=test_cfg.id,
        status="error",
        model_name=test_cfg.model_name,
        context_len=test_cfg.context_len,
        kv_format=test_cfg.kv_format,
        flash_attn=test_cfg.flash_attn,
        quant=test_cfg.quant,
        ram_estimate_gb=test_cfg.ram_total_gb,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
    )

    # 1. Verificar modelo
    model_path = model_spec.effective_path()
    if not os.path.exists(model_path):
        result.status = "error"
        result.error_type = "model_not_found"
        result.error_message = f"Modelo no encontrado: {model_path}"
        result.duration_s = time.time() - start_time
        return result

    # 2. Construir prompt
    if prompt is None:
        # Prompt de tamano ~context_len/4 tokens para dejar espacio a generacion
        prompt_len = max(64, min(test_cfg.context_len - 256, test_cfg.context_len // 4 * 3))
        prompt = generate_prompt(prompt_len, test_cfg.model_name)

    # 3. Construir comando
    flags = test_cfg.llama_flags
    cmd = [llama_bin, "-m", model_path] + flags



    # Pipe prompt via stdin
    input_bytes = prompt.encode("utf-8")

    # 4. Ejecutar
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except FileNotFoundError:
        result.status = "error"
        result.error_type = "binary_not_found"
        result.error_message = f"llama-cli no encontrado en {llama_bin}"
        result.duration_s = time.time() - start_time
        return result
    except Exception as e:
        result.status = "error"
        result.error_type = "spawn_failed"
        result.error_message = str(e)
        result.duration_s = time.time() - start_time
        return result

    # 5. Timeout total
    try:
        stdout_bytes, _ = proc.communicate(input=input_bytes, timeout=timeout_total)
        return_code = proc.returncode
        raw_output = stdout_bytes.decode("utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
        result.status = "timeout"
        result.error_type = "total_timeout"
        result.error_message = f"Test excedio timeout total de {timeout_total}s"
        result.duration_s = time.time() - start_time
        return result

    result.raw_output = raw_output
    result.duration_s = time.time() - start_time

    # 6. Verificar codigo de retorno
    if return_code != 0 and return_code is not None:
        # Si hay timings igual se considera ok (crash post-generacion)
        if "llama_print_timings:" not in raw_output:
            if any(w in raw_output.lower() for w in ["oom", "out of memory", "killed", "signal 9"]):
                result.status = "oom"
                result.error_type = "oom"
            else:
                result.status = "error"
                result.error_type = "non_zero_exit"
            result.error_message = f"Exit code: {return_code}"
            return result

    # 7. Parsear timings
    timings = parse_timing_output(raw_output)

    if timings.get("oom_detected"):
        result.status = "oom"
        result.error_type = "oom"
        result.error_message = "OOM detectado en output"
        # Igual extraer metricas parciales si existen
    elif result.status == "error":
        result.status = "ok"

    result.decode_speed = timings.get("generate_speed_tok_s")
    result.prefill_speed = timings.get("prompt_speed_tok_s")
    result.prompt_tokens = int(timings.get("prompt_tokens", 0))
    result.generated_tokens = int(timings.get("generated_tokens", 0))
    result.load_time_ms = timings.get("load_time_ms")
    result.total_time_ms = timings.get("total_time_ms")

    # VRAM observada (memory breakdown)
    vram_keys = [k for k in timings if k.startswith("vram_") and k.endswith("_mb")]
    if vram_keys:
        total_vram = sum(timings[k] for k in vram_keys)
        result.ram_total_observed_gb = total_vram / 1024.0
        model_vram = timings.get("vram_model_mb")
        ctx_vram = timings.get("vram_context_mb")
        if model_vram:
            result.ram_model_gb = model_vram / 1024.0
        if ctx_vram:
            result.ram_context_gb = ctx_vram / 1024.0

    return result


def print_result(result: TestResult, verbose: bool = False) -> str:
    """Formatea TestResult como texto legible."""
    status_icon = {"ok": "OK", "oom": "OO", "timeout": "TO", "error": "ER", "skipped": "SK"}
    icon = status_icon.get(result.status, "??")

    lines = [
        f"[{icon}] {result.config_id} | {result.status.upper()}",
    ]

    if result.prefill_speed:
        lines.append(f"  Prefill: {result.prefill_speed:.1f} tok/s ({result.prompt_tokens} tokens)")
    if result.decode_speed:
        lines.append(f"  Generate: {result.decode_speed:.1f} tok/s ({result.generated_tokens} tokens)")
    if result.load_time_ms:
        lines.append(f"  Load: {result.load_time_ms:.0f} ms")
    if result.total_time_ms:
        lines.append(f"  Total: {result.total_time_ms:.0f} ms")
    if result.ram_total_observed_gb:
        lines.append(f"  RAM obs: {result.ram_total_observed_gb:.2f} GB (est: {result.ram_estimate_gb:.2f})")
    if result.error_message:
        lines.append(f"  Error: {result.error_message}")
    if verbose and result.raw_output:
        lines.append(f"  Raw (last 500 chars): {result.raw_output[-500:]}")

    return "\n".join(lines)


def run_test_series(
    configs: List[TestConfig],
    model_spec: ModelSpec,
    prompt: Optional[str] = None,
    cleanup_between: bool = True,
    stop_on_error: bool = False,
) -> List[TestResult]:
    """Ejecuta una serie de tests en serie (un modelo, muchas configs).

    Args:
        configs: Lista de TestConfig ordenada (la genera test_matrix_generator)
        model_spec: Spec del modelo
        prompt: Prompt opcional (si None, se genera auto)
        cleanup_between: Si True, intenta liberar RAM entre tests
        stop_on_error: Si True, detiene la serie al primer error

    Returns:
        Lista de TestResult en el mismo orden que configs
    """
    results = []
    total = len(configs)
    for i, cfg in enumerate(configs):
        print(f"\n--- Test {i+1}/{total}: {cfg.id} ---")

        if not cfg.fits:
            result = TestResult(
                config_id=cfg.id,
                status="skipped",
                model_name=cfg.model_name,
                context_len=cfg.context_len,
                kv_format=cfg.kv_format,
                flash_attn=cfg.flash_attn,
                quant=cfg.quant,
                error_type="budget_exceeded",
                error_message=f"RAM estimada: {cfg.ram_total_gb:.2f} >= {RAM_DISPONIBLE_GB:.1f} GB",
                timestamp=time.strftime("%Y-%m-%dT%H:%M:%S"),
            )
            results.append(result)
            print(print_result(result))
            continue

        result = run_single_test(cfg, model_spec, prompt=prompt)
        results.append(result)
        print(print_result(result))

        if cleanup_between:
            time.sleep(2)  # pausa para que Metal libere memoria

        if stop_on_error and result.status != "ok":
            print(f"\n--- Serie detenida por error en {cfg.id} ---")
            break

    return results


if __name__ == "__main__":
    from .model_registry import MODEL_REGISTRY
    from .test_matrix_generator import generate_matrix

    model = MODEL_REGISTRY["Qwen2.5-7B-1M"]
    configs = generate_matrix(model, context_steps=[16384, 32768])
    print(f"Ejecutando {len(configs)} tests para {model.name}")
    results = run_test_series(configs, model, stop_on_error=False)
    print(f"\nCompletados: {sum(1 for r in results if r.status == 'ok')}/{len(results)}")

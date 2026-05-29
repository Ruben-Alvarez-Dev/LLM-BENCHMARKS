# Models Status — Catalogo Completo de Modelos

> Proyecto: LLM-BENCHMARKS
> Hardware: Mac Mini M1 16GB (admin), MacBook Pro M1 Max 32GB (ruben)
> Actualizado: 2026-05-29

---

## Leyenda

| Icono | Significado |
|---|---|
| ✅ PROCESADO | Benchmarked, documentado, GGUF borrado de ambos |
| ⏳ PENDIENTE | En disco local, pendiente de procesar |
| ❌ ERROR | No se pudo procesar (tokenizador corrupto, etc) |
| 🗑️ ELIMINADO | Se borro intencionalmente (no aportaba vs alternativas) |

## Modelos Procesados (GGUF — llama.cpp)

| Modelo | tok/s | RAM | Contexto | Estado | Nota |
|---|---|---|---|---|---|
| Qwen2.5-7B-1M | 13.2 | 10 GB | 256K q4_0 | ✅ PROCESADO | Unico con 1M ctx. Borrado |
| Qwen3.5-4B | 60 | 6.8 GB | 256K q4_0 | ✅ PROCESADO | MVP del stack. Borrado |
| Gemma-3n-E2B | 71 | 6.3 GB | 128K f16 | ✅ PROCESADO | Worker 128K. Borrado |
| Qwen2.5-Coder-3B | 109 | 3.0 GB | 32K f16 | ✅ PROCESADO | Code. Borrado |
| Qwen3-1.7B | 156 | 3.4 GB | 32K f16 | ✅ PROCESADO | Worker rapido. Borrado |
| Qwen3.5-2B | 113 | 2.5 GB | 32K f16 | ✅ PROCESADO | Worker rapido. Borrado |
| DeepSeek-V2-Lite | 85 | 11.2 GB | 32K q4_0 | 🗑️ ELIMINADO | MLA no compensa en 16GB |
| Qwen3.5-9B | 38 | 9.4 GB | 256K q4_0 | 🗑️ ELIMINADO | Mas lento que 4B |
| Ministral-3-8B | 42 | 10.6 GB | 128K q4_0 | 🗑️ ELIMINADO | Similar a Qwen2.5-7B-1M |
| Gemma-4-E2B | — | — | — | 🗑️ ELIMINADO | Descarga incompleta |

## Modelos Procesados (MLX)

| Modelo | Bits | tok/s | RAM | Estado |
|---|---|---|---|---|
| Llama-3.2-1B | 4bit | 78.6 | 0.86 GB | ✅ PROCESADO |
| Qwen2.5-1.5B | 4bit | 61.9 | 1.07 GB | ✅ PROCESADO |
| Gemma-3-1B | 8bit | 50.9 | 1.50 GB | ✅ PROCESADO |
| Granite-3.3-2B | 4bit | 38.6 | 1.66 GB | ✅ PROCESADO |
| Gemma-2-2B | 4bit | 36.8 | 1.67 GB | ✅ PROCESADO |
| Llama-3.2-3B | 4bit | 31.7 | 2.11 GB | ✅ PROCESADO |
| MiMo-7B | 4bit | 15.1 | 4.55 GB | ✅ PROCESADO |
| Gemma-3-4B | 8bit | 14.4 | 5.03 GB | ✅ PROCESADO |
| Mistral-7B | 4bit | — | — | ❌ Tokenizador corrupto |

## Modelos Pendientes en /Users/local/

### GGUF (ejecutar con llama-cli)

Para procesar: `llama-cli -m <ruta> -ngl 99 -c N -st --temp 0.0 -n 256 --no-display-prompt --show-timings`

| # | Modelo | Ruta en /Users/local/ | Tamano | RAM est. |
|---|---|---|---|---|
| 1 | Gemma-4-26B-A4B | .lmstudio/models/lmstudio-community/gemma-4-26B-A4B-it-GGUF/gemma-4-26B-A4B-it-Q4_K_M.gguf | 16 GB | ~20 GB (MBP) |
| 2 | Mistral-Small-3.2-24B | .lmstudio/models/lmstudio-community/.../Mistral-Small-3.2-24B-Instruct-2506-Q4_K_M.gguf | 13 GB | ~17 GB (MBP) |
| 3 | Qwen3.6-27B | .lmstudio/models/Brian6145/.../Qwen3.6-27B-...-Q2_K.gguf | 10 GB | ~12 GB (MBP) |
| 4 | Ministral-3-14B | .lmstudio/models/lmstudio-community/.../Ministral-3-14B-Reasoning-2512-Q4_K_M.gguf | 7.7 GB | ~10 GB |
| 5 | Qwen3.5-9B | .lmstudio/models/lmstudio-community/.../Qwen3.5-9B-Q4_K_M.gguf | 5.2 GB | ~7 GB |
| 6 | Qwen2.5-7B (normal) | Jart-OS-local-server/.../models/qwen2.5-7b-instruct-Q4_K_M.gguf | 4.4 GB | ~6 GB |
| 7 | olmOCR-2-7B | .lmstudio/models/lmstudio-community/.../olmOCR-2-7B-1025-Q4_K_M.gguf | 4.4 GB | ~6 GB |
| 8 | Gemma-4-E2B | .lmstudio/models/majentik/.../gemma-4-E2B-it-RotorQuant-Q4_K_M.gguf | 3.2 GB | ~5 GB |
| 9 | Nemotron-3-Nano-4B | .lmstudio/models/lmstudio-community/.../NVIDIA-Nemotron-3-Nano-4B-Q4_K_M.gguf | 2.6 GB | ~4 GB |

### MLX (ejecutar con mlx_lm.benchmark)

| # | Modelo | Ruta | Tamano |
|---|---|---|---|
| 1 | GPT-OSS-20B | .lmstudio/models/mlx-community/gpt-oss-20b-MXFP4-Q8/ | 11 GB |
| 2 | Gemma-3n-E4B | .lmstudio/models/lmstudio-community/gemma-3n-E4B-it-MLX-6bit/ | 7 GB |
| 3 | Voxtral-4B-TTS | .lmstudio/models/majentik/Voxtral-4B-TTS-2603-RotorQuant-MLX-8bit/ | ~4 GB |
| 4 | Voxtral-Mini-3B | .lmstudio/models/majentik/Voxtral-Mini-3B-2507-RotorQuant-MLX-4bit/ | ~3 GB |
| 5 | Gemma-3-1B QAT | .lmstudio/models/mlx-community/gemma-3-1b-it-qat-4bit/ | 699 MB |

### Nota de Espacio

El Mac Mini tiene ~10 GB libres actualmente. Los modelos grandes (>7 GB)
NO entran en el MM y deben procesarse en el MBP (M1 Max 32GB) via SSH.

Los modelos de 2.6-7 GB SÍ entran en el MM (1 a la vez).

## Como Reanudar

```bash
# Conectarse al Mac Mini
ssh admin@mac-mini.local

# Ir al proyecto
cd /Users/admin/Code/LLM-BENCHMARKS

# Activar MLX
export PATH="$HOME/Library/Python/3.9/bin:$PATH"

# Benchmarkear modelo GGUF:
llama-cli -m /Users/local/.../model.gguf -ngl 99 -c 16384 -st --temp 0.0 -n 256 --no-display-prompt --show-timings

# Benchmarkear modelo MLX:
mlx_lm.benchmark --model /Users/local/.../model-dir/ --prompt-tokens 128 --generation-tokens 256

# Guardar resultado en BD:
PYTHONPATH=engines python3 -c "
from orchestrator.sqlite_writer import get_connection, save_result
from orchestrator.test_executor import TestResult
import time
conn = get_connection()
save_result(conn, TestResult(config_id='...', status='ok', model_name='...', hardware='m1-mini-16gb',
    context_len=N, kv_format='q4_0', flash_attn=True, quant='Q4_K_M',
    decode_speed=XX.X, prefill_speed=XXX.X, prompt_tokens=N, generated_tokens=256,
    timestamp=time.strftime('%Y-%m-%dT%H:%M:%S')))
conn.close()
"

# LLM-BENCHMARKS — Benchmark Suite for Local Inference

> Proyecto estructurado de investigacion y certificacion de modelos de lenguaje
> para inferencia local en Apple Silicon (Mac Mini M1 16GB, MacBook Pro M1 Max 32GB).
>
> Iniciado: 2026-05-24 | Ultima sesion: 2026-05-29

---

## Estructura del Proyecto

```
LLM-BENCHMARKS/
├── README.md                    # Este archivo — entry point
├── SESSION.md                   # Bitacora completa de toda la investigacion
├── docs/
│   ├── research/                # Papers, disenos, especificaciones
│   └── benchmarks/              # Reportes de benchmarks por modelo
├── engines/
│   ├── orchestrator/            # Pipeline de benchmarks (Python)
│   │   ├── __init__.py
│   │   ├── model_registry.py    # Catalogo de modelos con metadatos
│   │   ├── ram_budget.py        # Calculo de presupuesto RAM
│   │   ├── test_matrix_generator.py  # Matriz cartesiana de tests
│   │   ├── test_executor.py     # Ejecutor llama-cli con timeouts
│   │   ├── mlx_executor.py      # Ejecutor MLX (safetensors)
│   │   ├── sqlite_writer.py     # Persistencia SQLite + Markdown
│   │   └── main.py              # Pipeline CLI
│   └── requirements.txt
├── data/
│   └── benchmark_results.db     # BD SQLite con todos los resultados
├── models/
│   └── STATUS.md                # Estado de todos los modelos
└── scripts/
    └── run-benchmark.sh         # Script de ejecucion
```

## Hardware Objetivo

| Maquina | Chip | RAM | Hostname | Rol |
|---|---|---|---|---|
| Mac Mini | Apple M1 | 16 GB | mac-mini.local | Principal (benchmarks reales) |
| MacBook Pro | Apple M1 Max | 32 GB | MacBook-Pro-de-ruben.local | Workstation (modelos grandes, desarrollo) |

Ambas conectadas por red local (192.168.x.x) y Tailscale.

## Motores de Inferencia

| Engine | Formato | Instalacion | Estado |
|---|---|---|---|
| llama.cpp (llama-cli) | GGUF | Homebrew / copia binaria | ✅ v8880 en ambos |
| MLX (mlx-lm) | safetensors / MLX | pip install mlx-lm | ✅ v0.29.1 en MM |

## Uso Rapido

```bash
# Ver modelos disponibles en el registro
cd /Users/admin/Code/LLM-BENCHMARKS
PYTHONPATH=engines python3 -m orchestrator.main --list-models

# Ver resultados existentes
PYTHONPATH=engines python3 -m orchestrator.main --report

# Benchmark de un modelo GGUF
PYTHONPATH=engines python3 -m orchestrator.main Qwen2.5-7B-1M --contexts 16384 32768 --kv q4_0 --flash both

# Benchmark de un modelo MLX
mlx_lm.benchmark --model /ruta/al/modelo --prompt-tokens 128 --generation-tokens 256
```

## Estado Actual

**129 tests totales ejecutados, 129 OK, 0 errores.**

Completados (procesados, documentados, GGUFs borrados de ambos equipos):
- 10 modelos GGUF (llama.cpp)
- 9 modelos MLX

Pendientes (en `/Users/local/` del Mac Mini, no procesados):
- 9 modelos GGUF adicionales
- 5 modelos MLX adicionales

Ver `models/STATUS.md` para detalle completo.

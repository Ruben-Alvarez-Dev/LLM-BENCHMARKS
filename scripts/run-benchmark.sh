#!/bin/bash
# run-benchmark.sh — Ejecuta benchmark de un modelo y guarda resultado
#
# Uso:
#   ./scripts/run-benchmark.sh gguf <ruta-al-gguf> <nombre-modelo> <contexto> <kv>
#   ./scripts/run-benchmark.sh mlx <ruta-al-directorio> <nombre-modelo>
#
# Ejemplos:
#   ./scripts/run-benchmark.sh gguf /Users/local/.../model.gguf MiModelo 16384 q4_0
#   ./scripts/run-benchmark.sh mlx /Users/local/.../model-dir/ MiModelo-MLX

set -e
BASE_DIR="/Users/admin/Code/LLM-BENCHMARKS"
export PATH="$HOME/Library/Python/3.9/bin:$PATH"

ENGINE="$1"
MODEL_PATH="$2"
MODEL_NAME="$3"

if [ "$ENGINE" = "gguf" ]; then
    CONTEXT="${4:-16384}"
    KV="${5:-q4_0}"
    
    echo "[BENCHMARK] GGUF: $MODEL_NAME @ ${CONTEXT}K ${KV}"
    
    OUTPUT=$(llama-cli -m "$MODEL_PATH" -ngl 99 -c "$CONTEXT" \
        -ctk "$KV" -ctv "$KV" -st --temp 0.0 -n 256 \
        --no-display-prompt --show-timings 2>&1 <<< "test")
    
    echo "$OUTPUT" | grep -E "Prompt:|Generation:"
    
elif [ "$ENGINE" = "mlx" ]; then
    echo "[BENCHMARK] MLX: $MODEL_NAME"
    mlx_lm.benchmark --model "$MODEL_PATH" --prompt-tokens 128 --generation-tokens 256 2>&1 | grep "Averages"
else
    echo "Uso: $0 {gguf|mlx} <path> <name> [context] [kv]"
    exit 1
fi

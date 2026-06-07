# SPEC 05 — Batería multi-slot: certificación de serving concurrente en Mac mini M1 16GB

> **Fecha:** 2026-06-06 · **Origen:** INFERENCE-investigation/docs/research/2026-06-06-VERIFICACION-ADVERSARIAL-SOTA.md
> **Motivación:** los dos datos que deciden el stack de serving NO existen publicados en ningún
> sitio: (1) t/s real de los 7-9B híbridos 2026 en el mini, (2) estabilidad de llama-server
> multi-slot con estado recurrente (bugs #20222/#24055 abiertos). Los medimos aquí.

## Hipótesis a falsar

- **H1**: Granite-4.1-8B en llama-server aguanta 8 slots 1h sin crash ni degradación >20%.
- **H2**: Qwen3.5-9B en llama.cpp Metal rinde <50% que en MLX (kernel GDN sin fusionar).
- **H3**: El agregado con 8 streams es 2-3× el single-stream (no 8×).
- **H4**: planar3 K + f16 V iguala a q8_0/q8_0 en PPL con menos RAM.
- **H5**: ngram-mod mejora ≥15% el throughput en cargas de agente (output repetitivo).
- **H6**: per-stream bajo 8 slots ≥ 8 t/s (umbral de usabilidad para agentes).

## Matriz de tests

### Fase 1 — Velocidad base (llama-bench / mlx_lm.benchmark, single-stream)
| Modelo | Engine | Quant | Config |
|---|---|---|---|
| Granite-4.1-8B | llama.cpp mainline (pin ≥ fix #19559, < b9354) | Q4_K_M | fa on, kv q8/q8 |
| Qwen3.5-9B | llama.cpp mainline | Q4_K_M (unsloth) | fa on, kv q8/q8 |
| Qwen3.5-9B | MLX (mlx-lm ≥ últimas fixes GDN) | 4bit (DWQ si existe) | kv-bits 8 |
| Falcon-H1R-7B | llama.cpp | Q4_K_M oficial TII | fa on, kv q8/q8 |
| Qwen3.5-4B (control, ya certificado 60 t/s) | llama.cpp | q4_0 | régimen anterior |

Métricas: pp512, tg128, RAM pico (vm_stat), t/s sostenido a 8K de profundidad.

### Fase 2 — Concurrencia (la fase que importa)
Servidor: `llama-server -np {1,4,8} --kv-unified -c 32768 --cache-type-k q8_0 --cache-type-v q8_0 --flash-attn on` (+ variantes: `--spec-type ngram-mod` on/off; fork RotorQuant con planar3).
MLX: oMLX o vllm-mlx con batching, mismos modelos.

Cargas sintéticas (script nuevo `engines/orchestrator/concurrent_load.py`):
- **A. Chat agentes**: 8 streams, 256 in / 256 out, llegada Poisson 0,5 req/s — mide agregado, per-stream, TTFT p50/p95.
- **B. Multi-turno con prefijo compartido**: 8 conversaciones de 10 turnos, system prompt común de 1K — mide hit-rate de prefix cache y el % de reprefill (DETECTA #24055: si cada turno reprocesa todo, falla).
- **C. Asimétrica**: 1 stream de 16K + 7 idle — detecta la degradación por slots inactivos (#19523).
- **D. Soak 1h**: carga A sostenida — crashes ("Chunk not found" #20222), leaks (RSS), drift de latencia.
- **E. Calidad bajo concurrencia**: 20 prompts agénticos con tool-calling (JSON schema) por modelo bajo carga A — % de JSON válido y de llamadas correctas. Comparar con single-stream (descartar corrupción de estado recurrente entre slots).

### Fase 3 — KV / contexto
- q8/q8 vs q4/q4 vs planar3+f16 (fork): PPL wikitext-2 + RAM + t/s en Granite y Qwen3.5.
- Slot save/restore (`--slot-save-path`): latencia de save/restore de un slot de 16K vs reprefill.
- `--cache-ram` activado: TTFT tras churn de 16 conversaciones sobre 8 slots.

## Criterios de aceptación del stack ganador
1. 0 crashes en soak 1h con 8 slots.
2. per-stream ≥ 8 t/s bajo carga A; TTFT p95 ≤ 3 s con prefix cache caliente.
3. ≥ 95% JSON válido en tool-calling bajo concurrencia (E), sin degradar vs single-stream.
4. RAM pico total ≤ 12 GB (deja 4 GB a macOS + sidecars).
5. Reprefill por turno < 25% de los turnos en carga B.

## Logística
- GGUFs a descargar (≈16 GB total — liberar espacio antes, el mini tiene ~10 GB):
  granite-4.1-8b Q4_K_M (~4,9 GB) · unsloth/Qwen3.5-9B Q4_K_M (~5,6 GB) ·
  Falcon-H1R-7B Q4_K_M (~4,4 GB) · Qwen3.5-9B-MLX-4bit (~5,2 GB). Procesar de 1-2 en 1-2 y borrar, como en la campaña anterior.
- Builds: llama.cpp mainline pineada + fork RotorQuant recompilado; mlx-lm actualizado; oMLX.
- Resultados a `data/benchmark_results.db` + reporte `docs/benchmarks/2026-06-XX-MULTISLOT-REPORT.md`.
- Tiempo estimado: 1 día de máquina + 2-3 h de análisis.

## Cruce con inventario (FF_Files_and_Folders/_INVENTARIO_SISTEMA/llm_catalogo.csv, 2026-06)

Ya en disco o con comando de re-descarga en el catálogo (no hay que buscarlos):
- ✅ **Qwen3.5-9B-GLM5.1-Distill i1-Q4_K_S** (mradermacher, 5,0 GB) y **MLX-4bit** (Jackrong, 4,7 GB)
- ✅ **Qwen3.5-9B-DeepSeek-V4-Flash** GGUF (Jackrong Q4_K_S y mradermacher Q4_K_S+mmproj)
- ✅ **Qwen3.5-9B base q4** vía ollama (batiai) — extraer blob GGUF o re-bajar unsloth/Qwen3.5-9B-GGUF
- ✅ Controles ya certificados: Qwen3.5-4B (unsloth Q4_K_S), Qwen2.5-7B-1M, Qwen3-8B, DeepSeek-R1-0528-Qwen3-8B (GGUF+MLX)
- ✅ whisper-large-v3-turbo-mlx (para el stack de voz, no esta batería)
- ⚠️ **Qwen3.6-35B-A3B-RotorQuant** (Q2_K 12,1 GB / MLX-2bit 10,1 GB, majentik): MoE A3B muy interesante
  pero NO para el mini con 8 slots (no deja margen y Q2/2bit degrada) → candidato para el MBP 32GB.

A descargar (no aparecen en el catálogo):
- ⬇️ **Granite-4.1-8B Q4_K_M** (~4,9 GB) — el candidato robusto del informe
- ⬇️ **Falcon-H1R-7B Q4_K_M oficial TII** (~4,4 GB) — opcional, fase 1
- ⬇️ unsloth/Qwen3.5-9B-GGUF Q4_K_M (~5,6 GB) si no se extrae del blob de ollama

Nota distills: se benchmarkean como variantes del base (mismo coste), pero el informe de verificación
los descarta para producción de agentes hasta que pasen la fase E (tool-calling bajo concurrencia)
comparados contra el base — esa comparación ES parte de esta batería (E: base vs GLM5.1-Distill vs V4-Flash).

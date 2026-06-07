# 02-SPEC v2 — Especificación funcional

> Fase: Spec · Estado: Para aprobación · Fecha: 2026-06-06

## 1. Dimensiones del espacio de prueba

Una **campaña** = producto cartesiano (podado por el planner de RAM) de:

| Dimensión | Valores v2.0 | Notas |
|---|---|---|
| Máquina | mbp-m1max-32g, mini-m1-16g | extensible: cualquier runner registrado |
| Engine | llama.cpp(server/bench), llama.cpp-RotorQuant, MLX(mlx-lm), oMLX | declarados: vLLM-CUDA, TRT-LLM, vllm-metal |
| Modelo×Quant | del catálogo (llm_catalogo.csv importable) | GGUF y MLX |
| **Contexto** | **4096, 8192, 16384, 32768, 65536, 131072, 262144, 716800 (700K), 1048576 (1M)** | 700K/1M implican YaRN/rope-scaling donde aplique; el planner marca `extrapolated_rope=true` |
| **Profundidad** | 0%, 50%, 90% del contexto | la dimensión que v1 no tenía: decode CON la caché llena |
| **Concurrencia** | 1, 2, 4, 8 slots | `--kv-unified`; por perfil de carga |
| Perfil de carga | S (single), A (agentes Poisson), B (multi-turno prefijo común), C (asimétrica 1×largo+idle), D (soak 30-60min), E (calidad tool-calling) | de specs/05, absorbido |
| Técnicas | set declarativo por celda (KV q8/q4/planar3, flash-attn, ngram-mod, MTP, draft, iSWA...) | registro §03-DESIGN; las no soportadas en la plataforma se saltan con motivo registrado |

## 2. Presupuesto previo (planner)

Antes de encolar, cada celda pasa por el KvModel del engine+arquitectura:
- denso GQA: `2·layers·kv_heads·head_dim·bytes·ctx·slots_efectivos`
- híbrido (Qwen3.5/Granite/Falcon-H1): solo capas full-attention + estado recurrente fijo × slots
- SWA dual-cache (Gemma/gpt-oss): capas globales a ctx, capas SWA a window
- MLA: latente comprimido
Pesos por bits/weight reales del fichero (no tabla teórica: leer del GGUF/safetensors).
Límites por máquina: RAM total, wired limit Metal (consultado vía `sysctl iogpu.wired_limit_mb`),
reserva SO configurable. Si no cabe → celda `SKIPPED(budget)` con desglose, nunca OOM ciego.

## 3. Protocolo de medición (el corazón de v2)

Por celda:
1. **Pre-flight**: limpiar procesos del engine, `vm_stat` baseline, temperatura si disponible
   (`powermetrics --samplers smc` requiere sudo: opcional), versión+commit+flags del engine
   (`llama-server --version`, git describe del fork), hash del modelo.
2. **Carga**: medir load_time. Verificar `n_ctx` efectivo reportado por el engine == solicitado.
3. **Llenado a profundidad D**: prefill con **corpus real no repetitivo** (mezcla determinista
   seedeada de: código del propio repo, documentación técnica, prosa ES+EN — ratio 40/40/20,
   tokenizada y cortada a D). Medir `prefill_tps` y `ttft`.
4. **Decode-at-depth**: generar 128 tokens × **3 repeticiones** (+1 warmup descartado) en
   posición D. Reportar mediana, σ, min/max. Si σ/mediana > 10% → 2 repeticiones extra y flag.
5. **Concurrencia >1**: lanzar el perfil de carga (A-E) contra llama-server/oMLX con N slots.
   Métricas: agregado t/s, por-stream p50/p95, TTFT p50/p95, error rate, % reprefill
   (detectar regresión de checkpoints en híbridos), RSS pico muestreado a 1Hz.
6. **Calidad operativa** (gates automáticos sobre las generaciones):
   - JSON/tool-call válido (perfil E): % parseable + schema-conforme
   - Degeneración: detector de repetición (n-grama ≥8 repetido ≥4×) y de colapso (entropía)
   - A profundidad: needle-in-haystack ligero (3 needles insertados en el prefill; recall 0-3)
7. **Sostenido** (perfil D): t/s por minuto durante 30-60 min → pendiente de degradación térmica.
8. **Post-flight**: RSS final vs baseline (leak), exit limpio, logs crudos comprimidos y enlazados.

Todo crudo se guarda (stdout/stderr del engine, JSONL de requests); las métricas derivan
de los crudos por parsers versionados — recalculables si el parser mejora.

## 4. Veredictos (reglas versionadas, evaluadas por el Analyzer)

`VerdictRule v1`: para servir agentes —
- `apto_concurrencia(N, ctx)` si: 0 crashes en soak, per-stream p50 ≥ 8 t/s, TTFT p95 ≤ 3s
  (prefijo caliente), JSON válido ≥95% y sin degradación vs single-stream, RSS pico ≤ presupuesto.
- `apto_contexto(C)` si: decode@90% ≥ 60% del decode@0%, needle-recall ≥ 2/3, sin degeneración.
- `frontera(modelo, máquina)` = máx N y máx C que cumplen — lo que pediste: "este sirve hasta 4".
Reglas en YAML versionado; cada veredicto referencia regla+versión+celdas de evidencia.

## 5. Datos

SQLite WAL (se mantiene). Tablas nuevas/cambiadas: `machines`, `engines(version,commit,flags)`,
`models(file_hash,arch,kv_profile)`, `techniques`, `cells(dims...)`, `runs(n, raw_ref)`,
`measurements(metric,value,unit,run_id)`, `verdicts(rule,version,result,evidence)`,
`action_log` (WAL pattern de v1, se conserva tal cual).
Export: markdown (formato actual de docs/benchmarks), CSV, JSON.

## 6. API y frontend (resumen; detalle en 03-DESIGN)

- API REST FastAPI (se conserva el esqueleto backend/): máquinas, catálogo, campañas
  (crear=wizard, estado, abortar), celdas/runs/medidas, veredictos, exportes. WebSocket/SSE
  para progreso en vivo.
- SPA vanilla (se conserva frontend/): Dashboard (máquinas+último estado), Wizard de campaña
  (elige dims → ve nº de celdas y ETA → lanza), Monitor (cola, celda en curso, log tail, t/s
  en vivo), Comparador (matriz modelo×ctx×slots con semáforos de veredicto, curvas
  profundidad-vs-t/s), Detalle de celda (todas las medidas + crudos).
- La app corre en el MBP; el mini ejecuta vía runner-agent (03-DESIGN §4) por Tailscale/SSH.

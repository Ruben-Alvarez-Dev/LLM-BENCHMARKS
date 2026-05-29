# MLA Experiments — Diseno Experimental

> Fecha: 2026-05-29
> Proposito: Validar si las innovaciones de atencion de DeepSeek (MLA, CSA, atencion
> hibrida) pueden aplicarse al stack de inferencia local en Mac Mini M1 16GB.
> Hardware: Mac Mini M1 16GB + NVMe 4TB TB3
> Motores: llama.cpp (Metal), MLX (Apple)

---

## 1. Objetivos

### Objetivo General
Identificar e implementar al menos 3 tecnicas concretas derivadas de las innovaciones
de atencion de DeepSeek que mejoren la inferencia local en Mac Mini M1 16GB y que NO
esten cubiertas por la investigacion existente.

### Objetivos Especificos

| # | Objetivo | Tecnica DeepSeek relacionada |
|---|---|---|
| OE1 | Demostrar que MLA da contexto 2-4x mas largo que GQA con igual RAM | MLA (DeepSeek V2-V4) |
| OE2 | Implementar eviccion de KV cache por importancia atencional (no FIFO) | CSA Lightning Indexer (V4) |
| OE3 | Prefetch predictivo desde NVMe usando scores de atencion | CSA seleccion top-1024 (V4) |
| OE4 | Evaluar V4-Flash como API de respaldo para contexto extremo | DeepSeek V4 (precio estructural) |
| OE5 | Reemplazar sliding window fija por ventana dinamica por atencion | Principio atencion hibrida |

---

## 2. Metodologia

### Ciclo por Fase
Cada fase sigue: Diseno -> Implementacion -> Baseline -> Medicion -> Comparacion -> Conclusion

### Condiciones de Ejecucion

| Parametro | Valor |
|---|---|
| Hardware | Mac Mini M1 16GB, NVMe 4TB TB3 |
| llama.cpp | Fork turboquant, ultima version |
| MLX | Ultima version estable |
| Temperatura | 0.0 (greedy) para benchmarks |
| Repetibilidad | Cada medicion 3 veces, reportar mediana + std |

---

## 3. Metricas

### Rendimiento
- Tokens/segundo (tok/s) - llama.cpp --benchmark
- Prefill speed (tok/s) - llama_get_timings()
- Time to first token (ms) - llama_get_timings()
- RAM total del proceso (GB) - psutil
- KV cache real usado (GB) - llama.cpp metrics
- PPL - benchmark_vs_reference.py

### Atencion
- Score de atencion por token [0,1] - attention_callback (Fase 2)
- Top-K tokens por importancia - AttentionScoreTracker
- Hits relevantes preservados (%) - eviction_log

### Sistema
- Latencia page fault (ms)
- Tasa acierto prefetch (%)
- Latencia API V4-Flash (ms)
- Costo por consulta (USD)

---

## 4. Tecnicas vs Estado Actual

| Tecnica | Prioridad | Ya en stack? | Depende de | Esfuerzo |
|---|---|---|---|---|
| Benchmark MLA | Alta | No | Fase 1 descarga | Bajo |
| Eviccion por atencion | Alta | No | Fase 2 instr. | Medio |
| Prefetch predictivo | Media | No | Fase 2b eviccion | Medio |
| V4-Flash API fallback | Baja | No | API key | Bajo |
| Context windowing dinamico | Media | No | Fase 2 instr. | Alto |

**Decision:** A y B primero (alto impacto, bajo riesgo). C y E dependen de B.
D es independiente y paralelizable.

---

## 5. Criterios de Exito

### A: Benchmark MLA
- DeepSeek-V2-Lite cargado y cuantizado en M1
- Tabla comparativa MLA vs GQA con tok/s a 5 longitudes
- KV cache usado documentado
- Conclusion sobre ventaja de MLA en M1 16GB

### B: Eviccion por atencion
- Scores de atencion operativos
- Eviccion por score, no por edad
- Mejora en retencion de contexto vs FIFO
- Latencia eviccion < 50ms

### C: Prefetch predictivo
- Prefetch asincrono desde NVMe operativo
- Tasa acierto > 50%
- Reduccion latencia page fault > 40%

### D: V4-Flash API fallback
- Router delegando a V4-Flash
- Tabla decision documentada
- Costo promedio documentado

### E: Context windowing dinamico
- Ventana 8K reciente + historico importante
- Mejora needle-in-haystack vs sliding window
- Reduccion de tokens para misma cobertura

---

## 6. Archivos a Crear

```
docs/research/
  2026-05-29-MLA-EXPERIMENTS-DESIGN.md       <- ESTE
  2026-05-30-MLA-BENCHMARK-RESULTS.md         <- Fase 1b
  2026-05-31-ATTENTION-EVICTION-RESULTS.md    <- Fase 2b
  2026-06-01-PREFETCH-FALLBACK-RESULTS.md     <- Fases 3+4
  2026-06-02-CONTEXT-WINDOWING-RESULTS.md     <- Fase 5
  2026-06-03-MLA-CONCLUSIONS.md               <- Fase 6

src/infra/
  attention_tracker.py        <- Fase 2
  attention_eviction.py       <- Fase 2b
  prefetch_attention.py       <- Fase 3
  context_window_attention.py <- Fase 5

src/benchmark_scripts/
  benchmark_mla.py            <- Fase 1b
```

---

## 7. Riesgos

| Riesgo | Impacto | Probabilidad | Mitigacion |
|---|---|---|---|
| DS-V2-Lite no en GGUF | Alto | Media | Convertir manualmente |
| llama.cpp sin attention scores | Alto | Alta | MLX o heuristicas semanticas |
| V4-Flash no disponible | Medio | Baja | OpenRouter proxy |
| M1 no carga DS-V2-Lite | Alto | Media | Q3_K_M o modelo alternativo |
| Resultados no concluyentes | Bajo | Baja | Documentar y continuar |

# Summary Global — Campana de Certificación

> Fecha: 2026-05-29 | Hardware: Mac Mini M1 16GB | Motor: llama-cli v8880 Metal
> Tests totales: **105** | OK: **105** | OOM/Timeout/Error: **0**

---

## Ranking por Velocidad (16K q4_0, flash on)

| # | Modelo | tok/s | RAM (GB) | Contexto max | params |
|---|---|---|---|---|---|
| 🥇 | **Qwen3-1.7B** | **129.7** | 2.70 | 32K | 1.7B |
| 🥈 | **Qwen3.5-2B** | **108.1** | 2.15 | 32K | 2.0B |
| 🥉 | **Qwen2.5-Coder-3B** | **91.7** | 2.61 | 32K | 3.0B |
| 4 | **DeepSeek-V2-Lite** MLA | 84.6 | 11.19 | 32K | 16B |
| 5 | **Gemma-3n-E2B** | 62.2 | 5.10 | 128K | 2.0B |
| 6 | **Qwen3.5-4B** | 60.0 | 3.86 | **262K** | 4.0B |
| 7 | **Qwen2.5-7B-1M** | 29.5 | 5.51 | 256K | 7.0B |

## Ranking por Contexto Mantenido

| # | Modelo | Max ctx | tok/s @ max | RAM @ max |
|---|---|---|---|---|
| 🥇 | **Qwen3.5-4B** | **256K** | 60.1 | 6.75 GB |
| 🥈 | **Qwen2.5-7B-1M** | 256K | 44.6 | 9.86 GB |
| 🥉 | **Gemma-3n-E2B** | 128K | 62.0 | 5.57 GB |
| 4 | Resto | 32K | — | — |

## Ranking por Eficiencia (tok/s por GB)

| # | Modelo | tok/s/GB |
|---|---|---|
| 🥇 | **Qwen3.5-2B** q4_0 | **50.3** |
| 🥈 | **Qwen3-1.7B** q4_0 | **48.0** |
| 🥉 | **Qwen2.5-Coder-3B** q4_0 | **35.1** |
| 4 | **Qwen3.5-4B** q4_0 | 15.5 |
| 5 | **Gemma-3n-E2B** q4_0 | 12.2 |
| 6 | **Qwen2.5-7B-1M** q4_0 | 5.4 |
| 7 | **DeepSeek-V2-Lite** q4_0 | 7.6 |

## Recomendaciones para el Stack

| Rol | Modelo | Config | Performance |
|---|---|---|---|
| **Worker ultra-rapido** | Qwen3-1.7B | f16, no flash | **156 tok/s**, 3.4 GB |
| **Worker rapido** | Qwen2.5-Coder-3B | f16, flash | **109 tok/s**, 3.0 GB |
| **Worker balanceado** | Gemma-3n-E2B | f16, flash | **71 tok/s**, 5-6 GB, hasta 128K |
| **Contexto largo-reducido** | Qwen3.5-4B | q4_0, no flash | **60 tok/s**, 6.8 GB, hasta **256K** |
| **Contexto largo** | Qwen2.5-7B-1M | q4_0, flash | **45 tok/s**, 9.9 GB, hasta 256K |
| **MLS Experimental** | DeepSeek-V2-Lite | q4_0, no flash | **85 tok/s**, 11.2 GB (solo 16K) |

## Modelos en Disco — Estado

| Modelo | GGUF | Tamano | Tests | Decision |
|---|---|---|---|---|
| Qwen3-1.7B | local | 1.2 GB | 12/12 OK | ✅ Conservar — worker ultra-rapido |
| Qwen3.5-2B | local | 1.2 GB | 12/12 OK | ✅ Conservar — worker ultra-rapido |
| Qwen2.5-Coder-3B | local | 2.0 GB | 12/12 OK | ✅ Conservar — code specialist |
| Qwen3.5-4B | local | 2.7 GB | 24/24 OK | ⭐ **CONSERVAR** — mejor relacion ctx/velocidad/RAM |
| Gemma-3n-E2B | local | 2.8 GB | 24/24 OK | ✅ Conservar — worker 128K |
| Qwen2.5-7B-1M | local | 4.4 GB | 9/9 OK | ⏳ Conservar hasta tests MBP 32GB |
| DeepSeek-V2-Lite | local | **9.7 GB** | 12/12 OK | ❌ **Candidato a borrar** — no compensa en 16GB |
| bge-m3 | local | 417 MB | — | Embeddings, no aplica |

## Espacion en Disco

| Concepto | GB |
|---|---|
| Ocupado por GGUFs | 24.5 GB |
| Espacio libre actual | ~5.3 GB |
| **Si se borra DeepSeek** | **~15 GB libres** |
| DeepSeek-V2-Lite 9.7 GB ocupa ~65% del espacio de modelos y solo da 32K contexto. Su结论: no vale la pena en MM 16GB.

---

*Generado por Benchmark Orchestrator v1 — INFERENCE-investigation*

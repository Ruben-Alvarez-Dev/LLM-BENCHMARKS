# Reporte Comparativo: Qwen2.5-7B-1M vs DeepSeek-V2-Lite MLA

> Fecha: 2026-05-29 | Hardware: Mac Mini M1 16GB | Motor: llama-cli v8880 Metal

---

## Resumen Ejecutivo

| Modelo | Params | Atencion | Contexto max | Mejor tok/s | RAM pico | Veredicto |
|---|---|---|---|---|---|---|
| Qwen2.5-7B-1M | 7B | GQA | 1,000,000 | **47.1 t/s** (128K) | 9.86 GB (256K) | ⭐ Recomendado |
| DeepSeek-V2-Lite | 16B | **MLA** | 32,768 | **98.0 t/s** (16K) | 18.47 GB (32K) | ⚠ Solo viable <16K en 16GB |

## Qwen2.5-7B-1M — Resultados detallados

### q4_0 KV, flash on/off

| Contexto | Flash | Prefill (t/s) | Generate (t/s) | RAM obs (GB) | vs Estimado |
|---|---|---|---|---|---|
| 16K (f16, previo) | on | 339.1 | **57.0** | 6.0 | — |
| 32K | off | 240.2 | **26.2** | 5.51 | +0.63 |
| 32K | on  | 241.0 | **29.5** | 5.51 | +0.63 |
| 64K | off | 239.7 | **30.3** | 6.06 | +0.75 |
| 64K | on  | 160.1 | **46.0** | 6.06 | +0.75 |
| 128K | off | 240.5 | **46.8** | 7.26 | +1.07 |
| 128K | on  | 240.4 | **47.1** | 7.26 | +1.07 |
| 256K | off | 158.3 | **25.5** | 9.86 | +1.92 |
| 256K | on  | 238.6 | **44.6** | 9.86 | +1.92 |
| 512K | — | — | — | — | ❌ No entra |

### Observaciones Qwen

1. **Flash attention**: mejora generacion 10-50%, especialmente a 64K (30→46) y 256K (25→44)
2. **Limite practico**: 256K con q4_0 KV, flash on → 44.6 t/s sostenido a 9.86 GB
3. **Para 512K+**: requiere MacBook Pro 32GB
4. **RAM real vs estimada**: sistematicamente +0.6 a +1.9 GB (compute + host memory no contabilizados)

## DeepSeek-V2-Lite MLA — Resultados detallados

### 16B Q4_K_M, MLA, flash on/off

| Contexto | KV Format | Flash | Prefill (t/s) | Generate (t/s) | RAM obs (GB) |
|---|---|---|---|---|---|
| 16K | f16 | off | 110.4 | **97.5** | 14.22 |
| 16K | f16 | on  | 166.9 | **98.0** | 14.22 |
| 16K | q4_0 | off | 178.6 | **84.7** | 11.19 |
| 16K | q4_0 | on  | 178.5 | **84.6** | 11.19 |
| 16K | q8_0 | off | 179.7 | **86.8** | 12.25 |
| 16K | q8_0 | on  | 179.5 | **86.2** | 12.25 |
| 32K | f16 | off | 22.8 | **72.7** | 18.47 |
| 32K | f16 | on  | 183.1 | **83.2** | 18.47 |
| 32K | q4_0 | off | 178.5 | **84.2** | 12.41 |
| 32K | q4_0 | on  | 178.2 | **85.0** | 12.41 |
| 32K | q8_0 | off | 179.9 | **85.6** | 14.52 |
| 32K | q8_0 | on  | 181.2 | **86.6** | 14.52 |

### Observaciones DeepSeek MLA

1. **Flash en MLA**: impacto minimo (97.5→98.0, 84.7→84.6). MLA ya es eficiente intrinsecamente.
2. **RAM dominada por pesos**: 9.7 GB GGUF cargado completo (MoE entero, no 15% activo). El budget subestima por ~factor 3.
3. **Mejor config 16GB**: 16K q4_0 sin flash → 84.7 t/s, 11.19 GB. Mas alla se acerca a OOM.
4. **32K f16 sin flash**: catastrofico (22.8 t/s prefill) — MLA sin flash sufre con contexto largo.

## Comparacion Directa: MLA vs GQA

### A 32K contexto, q4_0 KV, flash on

| Metrica | Qwen GQA | DeepSeek MLA | Diferencia |
|---|---|---|---|
| Generate speed | 29.5 t/s | **85.0 t/s** | MLA 2.9x mas rapido |
| RAM total | **5.51 GB** | 12.41 GB | GQA 2.3x mas eficiente |
| Peso modelo | 4.4 GB | 9.7 GB | GQA 2.2x mas liviano |
| Contexto max real | 256K | 32K | GQA 8x mas contexto |
| Parametros totales | 7B | 16B | MLA 2.3x mas params |
| Tok/s por GB | 5.4 | 6.9 | MLA gana 28% eficiencia RAM |

### Conclusion MLA vs GQA

**MLA NO compensa en este hardware especifico** por tres razones:
1. El modelo es 16B vs 7B → ocupa 2.2x mas RAM solo en pesos
2. El contexto maximo es 32K vs 1M → factor 30x menos
3. Aunque MLA da 3x mas velocidad, el costo en RAM lo hace impractico para contexto largo

MLA brillaria en un escenario donde:
- El modelo fuera mas pequeno (~7B con MLA)
- El hardware tuviera 32GB+ de RAM unificada
- Se priorice velocidad sobre contexto

## Recomendaciones

| Caso de uso | Modelo | Config | Performance |
|---|---|---|---|
| Worker rapido (<16K) | DeepSeek-V2-Lite | q4_0, no flash | 85 t/s, 11.2 GB |
| Contexto medio (32K-128K) | Qwen2.5-7B-1M | q4_0, flash on | 46 t/s, 6-7 GB |
| Contexto largo (256K) | Qwen2.5-7B-1M | q4_0, flash on | 45 t/s, 9.9 GB |
| Contexto extremo (512K-1M) | Qwen2.5-7B-1M | — | Requiere MBP 32GB |

## Tests Pendientes

- [ ] Qwen2.5-7B-1M @ 512K-1M en MacBook Pro 32GB
- [ ] Qwen3.5-9B (descarga pendiente, sin token HF)
- [ ] Continuous batching multi-agente
- [ ] PlanarQuant K+f16 V (requiere fork de llama.cpp)
- [ ] Speculative decoding con Gemma 4 E2B/E4B

---

*Generado por Benchmark Orchestrator v1 — INFERENCE-investigation*

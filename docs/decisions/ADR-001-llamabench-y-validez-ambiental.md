# ADR-001 — llama-bench como instrumento de velocidad + validez ambiental obligatoria

> Fecha: 2026-06-06 · Estado: aceptada · Contexto: Fase 1 de FRONTIER BENCH (specs/v2)

## Incidente que la motiva

Primera ejecución real del protocolo F1 (QwenPaw-Flash-9B, ctx 16K, depths 0/50/90,
~14:37): el adapter usaba `llama-cli -st` y parseaba `--show-timings`. **El build
b8880 (Homebrew) ya no emite líneas de timings parseables en single-turn** — renderiza
una UI de chat (banner ASCII, "Loading model...", breakdown de memoria) y los timings
clásicos `llama_print_timings:`/`llama_perf_context_print:` no aparecen en el crudo.
El run d0 terminó sin métricas; el proceso se canceló a mitad de d50 para no quemar
20 min de CPU en un resultado vacío. Crudo de evidencia:
`data/runs/raw_QwenPaw-Flash-9B_ctx16384_d0.log`.

Lección de protocolo: parsear la salida humana de un binario que evoluciona
semanalmente es frágil POR DISEÑO. Hay que medir con instrumentos pensados para medir.

## Decisión 1 — separación de instrumentos

| Medición | Instrumento | Por qué |
|---|---|---|
| Velocidad (decode/prefill at depth) | **llama-bench** | `-d N` = profundidad NATIVA (decode con N tokens ya en caché — exactamente el fix del fallo A1), `-r N` repeticiones integradas, `-o json` estable sin regex |
| Calidad (needles, degeneración, JSON) | **llama-cli** | necesita el TEXTO generado real; sus timings dan igual aquí |
| Concurrencia (F3) | **llama-server** | API OpenAI + slots |

Adapter nuevo: `adapters/engines/llamabench.py` (parser tolerante: avg_ts/stddev_ts
o samples_ts, con o sin ruido de --progress). El de llama-cli queda para calidad.

## Decisión 2 — validez ambiental (requisito de Rubén, mismo día)

> "El sistema debe ver si hay o no hay más procesos, protegerse o al menos avisar,
> y no dar el test por bueno si algo interfiere o no ha tenido RAM suficiente."

Implementado en `domain/environment.py` (reglas puras) + `adapters/probes/macos_env.py`
(vm_stat/ps/sysctl, coste ~0):

- **Pre-flight**: RAM libre < requerido×1,10 → no válido; procesos ajenos >2 GiB RSS
  (con nombre y tamaño en el motivo) → no válido; load > cores×1,25 → no válido
  (load > cores → solo aviso). Sin `--force-env` la CLI ABORTA antes de cargar nada.
- **Post-flight**: swap creció >0,25 GiB durante el run → no válido; proceso pesado
  aparecido a mitad del run → no válido.
- **Consecuencia**: el run SE GUARDA SIEMPRE (histórico append-only) con `valid=0`
  e `interference_json` — pero `LiveRanking.ingest()` lo ignora y el VerdictEngine (F4)
  no lo usará como evidencia. Allowlist: los binarios del propio banco no cuentan
  como interferencia.

## Estado de la aceptación F1

**BLOQUEADA a petición del usuario** (RAM ocupada con otras cargas, 2026-06-06 ~15:00).
Comando listo para cuando se libere:

```bash
cd /Users/ruben/Code/LLM-BENCHMARKS
PYTHONPATH=src python3 -m frontier_bench.cli measure \
  --model-file "/Users/ruben/.lmstudio/models/mradermacher/QwenPaw-Flash-9B-i1-GGUF/QwenPaw-Flash-9B.i1-Q4_K_S.gguf" \
  --name QwenPaw-Flash-9B --machine mbp-m1max-32g \
  --ctx 16384 --depths 0,50,90 --reps 3 --needles \
  --corpus-root docs --corpus-root src
```

El pre-flight ambiental decidirá por sí mismo si puede correr — ese es el punto.

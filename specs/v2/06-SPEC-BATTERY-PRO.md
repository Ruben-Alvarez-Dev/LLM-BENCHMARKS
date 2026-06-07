# SPEC 06 — Baterías profesionales declarativas

> **Fecha:** 2026-06-07 · **Estado:** implementación inicial (dry) entregada
> **Origen:** SPEC 05 (batería multi-slot) + petición de profesionalización

## Qué cambia

La batería deja de ser código ad-hoc y pasa a ser DATA: `batteries.yaml`
declara baterías (modelos x servidor x np x variantes x perfiles A-E) e
hipótesis FALSABLES como bloques propios (`kind: hypothesis`) con métrica,
operador (gte/lte/between), umbral y scope (profile/model/np/variant).

Componentes entregados:

- `batteries.yaml` — presets `multislot_certification` (H1/H3/H5/H6 de la
  SPEC 05) y `smoke` (validación del instrumento en <10 min).
- `domain/battery_presets.py` — dominio puro: load_presets (validación
  estricta: batería sin hipótesis = inválida, hipótesis huérfana = inválida,
  scope con claves desconocidas = inválido), plan() cartesiano en seco con
  hipótesis adjuntas por celda, report() con semántica de la casa:
  **métrica no medida = fallo explícito "unmeasured"**, jamás aprobado por
  omisión.
- CLI `battery [preset] [--plan]` — lista, detalla hipótesis y muestra el
  plan EN SECO. No ejecuta modelos.
- 13 tests nuevos (96/96 en suite), incluyendo regresión anti-multilínea
  para yaml_lite (los arrays multilínea parsean como string — bug que ya
  nos mordió en techniques.yaml y quedó corregido en este mismo cambio).

## Integración con lo existente (NO se duplica nada)

1. **Adaptación a la máquina**: el plan declarativo es independiente del
   host; la resolución host-específica ocurre donde siempre — HostProfiler
   aporta los facts, TuningAdvisor ajusta flags del servidor citando
   evidencia, y KvModel/ram_budget podan np/ctx que no caben en ESA máquina
   (poda VISIBLE: skipped_budget con desglose).
2. **Registro al detalle**: la ejecución real consume las celdas vía el
   executor F3 (cola bench_run_request) → run_battery: preflight ambiental
   → serve → perfil → postflight → Run valid/invalid con interferencias →
   LIMPIEZA IMPOLUTA (try/finally). Cada fila lleva provenance (versión de
   engine por máquina — el skew b9290/b9430 que ya cazamos) y todo pasa por
   el action_log (visible en UI/SSE y MCP bench_action_log).
3. **Veredictos**: report() de la batería alimenta al VerdictEngine
   (verdict_rules.yaml) — las hipótesis de batería y los veredictos de
   aptitud comparten la misma regla de oro: nada se aprueba sin medición.

## Pendiente (siguientes incrementos)

- `battery <id> --enqueue`: volcar el plan a la cola de RunRequests
  (idempotente, mismo canal UI/MCP). Gated: requiere RAM libre y aceptación
  F1/F2 pendiente.
- Persistir battery_report en BD (tabla verdicts ya existe; añadir origen
  battery_id) y panel de batería en la UI junto al wizard.
- H2/H4 (cross-engine MLX y planar3 PPL) viven en celdas `measure`/quality,
  no en perfiles de carga; el reporte de batería los referencia como
  dependencias externas cuando existan.

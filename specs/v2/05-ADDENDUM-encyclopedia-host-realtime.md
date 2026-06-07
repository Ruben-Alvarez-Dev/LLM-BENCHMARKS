# 05-ADDENDUM v2 — Enciclopedia, selección granular, auto-adaptación al host, tiempo real

> Fecha: 2026-06-06 (mismo día, tras aprobar F0) · Amplía 02-SPEC y 03-DESIGN.
> Origen: requisitos de Rubén — "la aplicación como enciclopedia del banco de pruebas".

## 1. Selección granular y repetición (RunRequest)

El histórico es **append-only**: una celda nunca se "re-escribe"; cada ejecución añade un
`run` nuevo con timestamp y provenance. Sobre eso:

- `RunRequest = filtros + repeats + force + note`:
  - **filtros** por cualquier dimensión (máquina, modelo, engine, ctx, slots, perfil,
    técnica, protocolo, estado, "solo celdas sin runs", "solo las que fallaron"...)
  - **repeats N**: corre N veces la misma selección (p.ej. 10× el mismo test)
  - **force**: re-ejecuta aunque ya haya resultados (el run nuevo convive con los viejos)
  - **note**: por qué se repite (queda en action_log)
- Casos cubiertos explícitamente: "repetir TODO", "una sola celda concreta", "cambiar
  gradualmente qué pruebo" (wizard parte de cualquier selección previa y la edita).
- Comparación entre runs del mismo cell_key a lo largo del tiempo = detección de regresiones
  de engine/SO gratis (la dimensión temporal emerge sola del histórico).

## 2. Enciclopedia (la app te dice para qué sirve cada cosa)

Cada técnica, perfil de carga, métrica y regla de veredicto lleva metadatos obligatorios:

```yaml
purpose: "qué mide / qué optimiza"
not_for: "qué NO te dice este test (anti-malinterpretación)"
optimal_when: "condiciones en las que aporta"
evidence: [urls a papers/issues/informes propios]
```

- API `/api/encyclopedia` y panel en el frontend: navegable, buscable, con la evidencia
  enlazada (incl. nuestros informes de INFERENCE-investigation).
- El wizard muestra estos textos al seleccionar: eliges sabiendo qué significa cada celda.
- Los reportes insertan `not_for` como nota al pie automática (p.ej. "decode@depth0 no
  certifica rendimiento con caché llena" — el fallo A1 queda imposible de malinterpretar).

## 3. Auto-adaptación al host (HostProfiler + TuningAdvisor)

Primera acción al arrancar en CUALQUIER máquina (Mac, VPS Hetzner Xeon/Ryzen, caja NVIDIA):

1. **HostProfiler** detecta: SO, kernel, CPU (vendor, núcleos P/E, ISA: AVX2/AVX512/AMX/NEON/SVE),
   RAM y canales/bandwidth estimado, aceleradores (Metal, CUDA+CC, ROCm, ANE), NUMA,
   storage (NVMe/SATA), límites (wired limit, cgroups, ulimits), engines instalados+versión.
2. **TuningAdvisor** mapea el perfil a parámetros óptimos vía `tuning_rules.yaml`
   (reglas declarativas versionadas, derivadas del SOTA documentado — cada regla cita evidencia):
   - Metal → `-ngl 99`, fa on, KV q8/q8 simétrico (#21450), wired_limit sugerido
   - x86 server → `--threads = núcleos físicos P`, NUMA pinning, build AVX512/AMX si ISA
   - CUDA → paged attention, EAGLE-3/TurboQuant elegibles, `-ngl` según VRAM
   - genérico → ubatch/batch según RAM/bandwidth
3. El perfil del host se guarda como `machines.facts_json` (provenance) y el advisor
   **propone**, nunca impone: el usuario ve los parámetros sugeridos + la regla + la evidencia,
   y puede sobreescribirlos (la celda registra sugerido vs usado).

## 4. Tiempo real y ranking vivo

- **Canal-agnóstico**: el dominio emite `Event`s tipados a `NotifyPort`; los transportes son
  adaptadores (SSE por defecto, WebSocket opcional, lo-que-sea mañana). Mismo stream para
  frontend, CLI (`--follow`) y logs.
- Eventos: `host_profiled, campaign_planned, cell_started, rep_progress` (muestras 1Hz:
  tok/s instantáneo, RSS, tokens generados), `measurement, cell_done, cell_failed,
  ranking_updated, campaign_done`.
- **Ranking incremental**: el Analyzer mantiene leaderboards en caliente (por métrica y por
  veredicto: decode@depth, agregado@slots, TTFT p95, frontera) que se recalculan al aterrizar
  cada run y se publican como `ranking_updated` — la pantalla muestra la clasificación
  reordenándose mientras corre la campaña.

## 5. Cambios en tareas (04-TASKS)

- F0.5 (nuevo, hecho junto a esta adenda): `RunRequest` + `Scheduler` + `events.py` +
  `ranking.py` en dominio, `tuning_rules.yaml` esqueleto, enciclopedia en `techniques.yaml`.
- F2 amplía: HostProfiler real (macOS primero: sysctl/system_profiler; Linux: lscpu/cpuinfo,
  nvidia-smi; Windows: WMI futuro).
- F5 amplía: panel Enciclopedia, monitor con stream 1Hz y leaderboard vivo.

## 6. Adenda 2026-06-06e — mantenimiento (requisitos de Rubén)

- **Updates con aprobación**: antes de cada campaña, `check-updates` consulta brew/pip
  y PROPONE (componente, actual→nueva, comando exacto). Nada se ejecuta sin el sí
  explícito del usuario. Propuesto/aprobado/rechazado + versión antes/después al action_log.
  Motivado ademas por hecho real: Homebrew actualizó llama.cpp b8880→b9430 DURANTE la sesión.
- **Limpieza impoluta por batería**: CleanupManifest registra todo lo creado (prompts,
  temporales, caches); al cerrar la batería de cada modelo se borra todo y se verifica.
  Excepción: los crudos (evidencia) se conservan COMPRIMIDOS (.gz). Un modelo no empieza
  su batería hasta que la anterior queda impoluta.

# 03-DESIGN v2 — Arquitectura hexagonal

> Fase: Design · Estado: Para aprobación · Fecha: 2026-06-06
> Principios: clean/hexagonal, SOLID, DRY. El dominio no importa NADA de plataforma.

## 1. Capas

```
┌────────────────────────── adapters (impuro) ──────────────────────────┐
│ web/        FastAPI + SPA          storage/   SQLite, MD/CSV export   │
│ engines/    llamacpp, rotorquant,  runners/   LocalRunner,            │
│             mlx, omlx,             │          SshRunner (Tailscale)   │
│             [vllm_cuda]*, [trt]*   probes/    vmstat, psutil, rss1hz, │
│ corpus/     RealTextCorpus(seed)   │          [nvidia_smi]*           │
└──────────────────────────────┬────────────────────────────────────────┘
                       puertos │ (interfaces, dataclasses puras)
┌──────────────────────────────┴────────────────────────────────────────┐
│ domain/                                                                │
│   entities: Machine, Engine, Model(arch, KvProfile), Technique,        │
│             Campaign, Cell, Run, Measurement, Verdict                  │
│   services: Planner (poda por presupuesto), Scheduler (cola, retries,  │
│             afinidad máquina), MeasurementProtocol (§02-SPEC.3 como    │
│             máquina de estados), Analyzer (estadística), VerdictEngine │
│             (reglas YAML versionadas), KvModel (denso/híbrido/SWA/MLA) │
└────────────────────────────────────────────────────────────────────────┘
* = declarado, adapter pendiente (otra plataforma)
```

Regla de dependencia: adapters→puertos→dominio. Nunca al revés. Tests del dominio sin I/O.

## 2. Puertos (contratos)

- `EnginePort`: `capabilities() -> set[TechniqueId]`, `load(model,cfg)`, `bench_cell(cell) -> RawRun`,
  `serve(cfg) -> ServerHandle` (para concurrencia), `version_info() -> Provenance`.
- `RunnerPort`: `exec(cmd, env, timeout) -> Result`, `put/get(file)`, `probe() -> MachineFacts`
  (RAM, chip, sysctl wired limit, engines instalados+versión, espacio disco).
- `ProbePort`: `sample() -> {rss, ram_free, temp?}` a 1Hz durante runs.
- `CorpusPort`: `tokens(n, seed) -> texto real determinista` (40% código/40% docs/20% prosa).
- `LoadGenPort`: perfiles S/A/B/C/D/E contra un ServerHandle (OpenAI-compatible).
- `StoragePort`, `NotifyPort` (SSE/WebSocket al frontend).

## 3. Registro de técnicas (la abstracción clave)

`techniques.yaml` — declarativo, independiente de si HOY hay adapter:

```yaml
- id: kv_quant_q8
  dims: {cache_type_k: q8_0, cache_type_v: q8_0}
  supports: {llamacpp: native, mlx: native, vllm_cuda: native}
  constraints: [metal_requires_matching_kv_types]   # issue #21450
- id: kv_planar3
  supports: {rotorquant: native}                    # nuestro fork, Metal OK
- id: kv_turboquant_tbq4
  supports: {llamacpp: {cuda: fork-AmesianX}}       # declarada; sin adapter Mac aún
- id: spec_ngram_mod
  supports: {llamacpp: native}
- id: spec_mtp
  supports: {llamacpp: native}
  warnings: [metal_net_loss_issue_23752]            # se puede probar, queda avisado
- id: spec_eagle3
  supports: {vllm_cuda: native, llamacpp: pr-18039-open}
- id: paged_attention
  supports: {vllm_cuda: native, vllm_metal: v0.2-experimental}
...
```

El Planner consulta `Engine.capabilities() ∩ technique.supports[platform]`; lo no soportado
genera celda `SKIPPED(unsupported: motivo)` — queda en la matriz de resultados, visible,
para que al correr en NVIDIA esas columnas se llenen solas.

## 4. Runner remoto (mini por Tailscale)

v2.0: **SshRunner** sin agente instalado — ssh/scp (clave ya existente), comandos idempotentes,
`nohup` + polling de ficheros de estado JSON; sin dependencia en el mini más allá de
engines+python3. v2.1: agente HTTP ligero opcional (websocket de progreso fino).
La identidad de máquina (A4 de la auditoría) viaja en CADA fila desde `RunnerPort.probe()`.

## 5. Reutilización del código existente

| Origen | Destino |
|---|---|
| backend/{main,database,models}.py | adapters/web + adapters/storage (se conserva WAL action-log) |
| frontend/ (SPA vanilla esqueleto) | adapters/web/static (mismas rutas de specs v1 §3) |
| orchestrator/model_registry.py | domain/entities.Model + import de llm_catalogo.csv |
| orchestrator/ram_budget.py | domain/services.KvModel (generalizado por arquitectura y máquina) |
| orchestrator/test_executor.py | adapters/engines/llamacpp (parsers de timings se conservan, versionados) |
| orchestrator/mlx_executor.py | adapters/engines/mlx |
| orchestrator/sqlite_writer.py | adapters/storage (esquema migrado, datos viejos importables con flag `protocol=v1`) |
| specs/05 batería | domain: perfiles de carga A-E del LoadGenPort |

## 6. Decisiones y riesgos

- **Python 3.12 + FastAPI + SQLite** (continuidad con lo construido; cero infra).
- SPA vanilla JS (sin build step) — coherente con frontend/ existente y con MCP Lens.
- 700K/1M: solo modelos con rope extensible; el planner exige `--rope-scaling yarn` explícito
  y marca el resultado como extrapolación. En 16GB, 1M probablemente `SKIPPED(budget)` para
  todo lo que no sea híbrido/SWA — eso TAMBIÉN es un resultado.
- Riesgo: bugs vivos de llama-server con híbridos multi-slot (#20222/#24055) — el protocolo
  los detecta (error rate, % reprefill) en vez de sufrirlos en silencio; build del engine pineada
  por campaña.
- Riesgo térmico mini: perfil D obligatorio antes de cualquier veredicto de concurrencia.

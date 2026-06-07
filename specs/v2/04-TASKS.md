# 04-TASKS v2 — Plan de implementación

> Fase: Tasks · Estado: Para aprobación · Fecha: 2026-06-06
> Estimaciones en sesiones de trabajo (S ≈ medio día humano+agente).

## Fase 0 — Esqueleto hexagonal (2S)
- [ ] Estructura `src/frontier_bench/{domain,ports,adapters}` + pyproject; mover/adaptar backend existente
- [ ] Entidades + puertos como dataclasses/Protocols puros; tests de dominio sin I/O
- [ ] `techniques.yaml` inicial (todas las del informe 2026-06-06, soportadas o no)
- [ ] Migración de esquema SQLite + import de resultados v1 con flag `protocol=v1`
- ✓ Aceptación: `pytest domain/` verde sin tocar disco/red; BD migrada con los 129 tests viejos

## Fase 1 — Protocolo de medición correcto, single-stream, local (3S)
- [ ] CorpusPort con corpus real seedeado (código+docs+prosa, determinista)
- [ ] Adapter llama.cpp: load → fill-at-depth → decode×3+warmup → parse; provenance completo
- [ ] KvModel por arquitectura (denso/híbrido/SWA/MLA) + planner con presupuesto por máquina
- [ ] Probe RSS 1Hz + needle-recall + detector de degeneración
- ✓ Aceptación: re-correr Qwen3.5-4B en el MBP produce curva decode@{0,50,90}% con σ<10%
  y detecta el artefacto A1 (números v1 "planos" vs reales decrecientes)

## Fase 2 — Runner remoto + segunda máquina (2S)
- [ ] SshRunner (Tailscale): probe de máquina, push de configs, ejecución idempotente, recogida
- [ ] Registro de máquinas en BD desde probe (chip, RAM, wired limit, engines+versiones)
- ✓ Aceptación: misma celda corre en mini y MBP desde un solo comando; filas con machine_id correcto

## Fase 3 — Concurrencia (3S)
- [ ] EnginePort.serve + LoadGenPort con perfiles S/A/B/C/D/E (asyncio + httpx contra API OpenAI)
- [ ] Métricas agregado/por-stream/TTFT p50-p95/error-rate/% reprefill/RSS pico
- [ ] Adapter MLX/oMLX para servir (comparativa de stacks del informe)
- ✓ Aceptación: batería specs/05 ejecutable como campaña; detecta #20222/#24055 si ocurren

## Fase 4 — Analyzer + VerdictEngine (2S)
- [ ] Estadística (mediana/σ/IC, pendiente térmica) sobre crudos re-parseables
- [ ] Reglas YAML v1 (apto_concurrencia, apto_contexto, frontera) + evidencia enlazada
- [ ] Export markdown compatible con docs/benchmarks actuales + CSV/JSON
- ✓ Aceptación: la pregunta "¿este modelo sirve para 4 agentes a 32K en el mini?" se responde
  con un SELECT de verdicts, no con un humano mirando tablas

## Fase 5 — Frontend (3S)
- [ ] Dashboard máquinas/estado; Wizard de campaña (dims → nº celdas + ETA → lanzar)
- [ ] Monitor en vivo (SSE): cola, celda en curso, t/s instantáneo, log tail
- [ ] Comparador: matriz modelo×ctx×slots con semáforos de veredicto; curvas profundidad/t/s;
      vista de celda con crudos
- ✓ Aceptación: campaña completa lanzada y seguida sin tocar CLI

## Fase 6 — Campaña de re-certificación (la que importa) (2S de máquina)
- [ ] Modelos: Qwen3.5-9B base, GLM5.1-Distill, V4-Flash, Granite-4.1-8B, Falcon-H1R-7B,
      Qwen3.5-4B (control) — contextos 4K→1M, profundidades, slots 1/2/4/8, en ambas máquinas
- [ ] Informe: mapa de frontera por máquina + actualización de INFERENCE-investigation
- ✓ Aceptación: veredictos publicados; los fallos A1-A10 de v1 imposibles por construcción

## Orden y dependencias
F0→F1→F2→F3→F4→F5 (F5 puede solaparse desde F3); F6 al final.
Total estimado: ~15 sesiones. El MVP útil (F0-F4, sin UI) responde ya por CLI/SQL.

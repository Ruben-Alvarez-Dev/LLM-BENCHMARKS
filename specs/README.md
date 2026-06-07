# OpenSpec — LLM-BENCHMARKS Platform

Este directorio contiene las especificaciones formales (SDD/OpenSpec) para la
transformacion del proyecto LLM-BENCHMARKS de una CLI a una plataforma web
autocontenida con dashboard interactivo, orquestacion remota, y trazabilidad
atomica de todas las operaciones.

## Fases

| Fase | Archivo | Estado |
|---|---|---|
| Proposals | `01-PROPOSAL.md` | ✅ |
| Spec | `02-SPEC.md` | ⏳ |
| Design | `03-DESIGN.md` | ⏳ |
| Tasks | `04-TASKS.md` | ⏳ |
| Apply | `_apply/` | ⏳ |
| Verify | `_verify/` | ⏳ |

## Principios rectores

1. **Atomic logging**: toda accion se persiste antes de ejecutarse (Write-Ahead Log)
2. **Trazabilidad completa**: cada resultado tiene su sesion, timestamp, maquina, config, diff
3. **Sin ejecucion ciega**: cada paso se valida contra el estado anterior antes de continuar
4. **Multi-maquina nativo**: el backend orquesta via SSH, no asume un solo host

---

## ⚠️ v2 (2026-06-06)

La especificación vigente está en `specs/v2/` (FRONTIER BENCH): absorbe 01-04 y 05,
añade protocolo de medición corregido (decode-at-depth, n≥3, provenance), matriz de
contexto 4K→1M (incl. 700K), concurrencia 1-8 como dimensión, arquitectura hexagonal
multi-plataforma y veredictos automáticos. Ver `specs/v2/00-README.md`.

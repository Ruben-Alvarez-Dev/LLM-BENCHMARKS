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

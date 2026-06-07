# Specs v2 — FRONTIER BENCH (LLM-BENCHMARKS evolucionado)

> **Fecha:** 2026-06-06 · **Estado:** Spec aprobable
> **Relación con v1:** absorbe y sustituye specs/01-04 (la visión web/máquinas/atomic-log se mantiene)
> y specs/05-SPEC-MULTISLOT-BATTERY.md (pasa a ser un perfil de carga del sistema).
> **Base de evidencia:** docs/research/2026-06-06-VERIFICACION-ADVERSARIAL-SOTA.md (INFERENCE-investigation).

## Qué es

Aplicación de benchmark para **búsqueda de frontera** de inferencia LLM local:
qué modelo, con qué técnicas, en qué máquina, hasta qué contexto y hasta qué
concurrencia **sirve de verdad** — con evidencia reproducible y veredictos automáticos.

- Frontend web local sencillo (SPA) que controla N máquinas (hoy: MacBook Pro M1 Max 32GB
  y Mac mini M1 16GB vía red local/Tailscale).
- Núcleo agnóstico de plataforma (clean/hexagonal): los engines, técnicas y sondas son
  adaptadores. Las técnicas CUDA-only (EAGLE-3, TurboQuant KV, AWQ/GPTQ runtime, vLLM paged)
  quedan **declaradas en el registro** con adapter pendiente — la app debe correr mañana
  en una caja NVIDIA/Linux sin tocar el dominio.
- Matriz de contexto: **4K · 8K · 16K · 32K · 64K · 128K · 256K · 700K · 1M**.
- Concurrencia como dimensión de primera clase: **1 · 2 · 4 · 8 slots** × perfiles de carga.
- Veredictos automáticos: "apto hasta N slots @ ctx C en máquina M" con criterios explícitos.

## Documentos

| Doc | Contenido |
|---|---|
| 01-PROPOSAL | Visión, auditoría del pipeline v1 (fallos), objetivos y no-objetivos |
| 02-SPEC | Especificación funcional: dimensiones, protocolo de medición, veredictos, datos, API, UI |
| 03-DESIGN | Arquitectura hexagonal: dominio, puertos, adaptadores, registro de técnicas, runners |
| 04-TASKS | Plan de implementación por fases con criterios de aceptación |

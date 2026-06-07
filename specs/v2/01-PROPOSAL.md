# 01-PROPOSAL v2 — Visión y auditoría del pipeline actual

> Fase: Proposal · Estado: Para aprobación · Fecha: 2026-06-06

## 1. Visión

Una sola app, instalable con un comando, con frontend web local, que convierte la búsqueda
de frontera ("¿qué modelo+técnicas sirven en mi hardware para mi caso?") en un proceso
**sistemático, reproducible y comparable**, sobre cualquier máquina registrada (hoy 2 Macs
por Tailscale; mañana lo que sea). El resultado no son números sueltos: son **veredictos**
("apto para concurrencia ≤4 a 32K en mac-mini") con la evidencia enlazada.

## 2. Auditoría del pipeline v1 (por qué hay que profesionalizarlo)

Hallazgos sobre `engines/orchestrator/` y la campaña 2026-05-29 (105+24 tests):

| # | Fallo | Efecto | Severidad |
|---|---|---|---|
| A1 | **Decode medido a profundidad ~0**: el test "@256K" asigna 256K de KV pero genera en posición ~0-1K | Los "60 t/s @256K" certifican *asignación*, no rendimiento con caché llena. Qwen3.5-9B dio 37-38 t/s "planos" en todos los ctx — síntoma inequívoco | **Crítica** |
| A2 | **Prompt sintético repetitivo** (`frase × n`): texto altamente compresible, atención irreal | Prefill optimista; sesgo a favor de cualquier técnica de lookup/spec | Alta |
| A3 | **n=1 por celda**: sin repeticiones, sin σ ni IC | Indistinguible ruido de señal (±10% típico en Metal) | Alta |
| A4 | **Máquina no es dimensión dura**: tablas mezclan M1 Max y M1 sin columna obligatoria | Confusión real ya ocurrida: los 38 t/s del 9B se atribuyeron al mini siendo del MBP | **Crítica** |
| A5 | **Sin provenance**: versión/commit/flags de build del engine no quedan en cada fila | Resultados no reproducibles (llama.cpp cambia semanalmente; el fix de Qwen3.5 del 5-jun altera todo) | Alta |
| A6 | **RAM**: snapshot, no pico muestreado; presupuesto hardcodeado a 16GB y fórmula KV de transformer denso | Falla con híbridos (8/32 capas + estado recurrente), SWA dual-cache y MLA; inútil para el MBP | Alta |
| A7 | **Cero concurrencia**: todo single-stream | No responde la pregunta de servir 4-6 agentes | **Crítica** |
| A8 | **Cero calidad**: no se valida el output (JSON, repetición, degeneración) | Un modelo puede "rendir" 60 t/s generando basura, sobre todo a 700K/1M con YaRN | Alta |
| A9 | **Sin sostenido/térmico**: tests de 256 tokens | El mini (fanless-ish) throttlea; t/s del minuto 1 ≠ minuto 30 | Media |
| A10 | TTFT/prefill at depth no medido por separado | La latencia real de agente (prompt 16K) es invisible | Media |

Lo bueno de v1 que se conserva: registro de modelos con metadatos, presupuesto RAM previo
a la carga (idea), SQLite WAL + reportes markdown, atomic action log (specs v1), backend
FastAPI iniciado, disciplina de "descargar→probar→borrar".

## 3. Objetivos

1. **Protocolo de medición correcto** (02-SPEC §3): n≥3, decode-at-depth, prefill real,
   TTFT, pico de RAM muestreado, calidad gates, sostenido, provenance completo.
2. **Matriz completa**: contexto 4K→1M (incl. 700K), concurrencia 1→8, perfiles de carga.
3. **Multi-máquina**: agente runner por SSH/Tailscale; la app reparte y agrega.
4. **Abstracción total** (03-DESIGN): dominio puro + puertos; engines/técnicas/sondas como
   adaptadores; técnicas no-Mac declaradas y listas para adapter futuro (NVIDIA/Linux/Windows).
5. **Veredictos automáticos** con criterios versionados (no opinión: regla + evidencia).
6. Frontend web local sencillo: wizard de campaña, monitor en vivo, comparador, exportes.

## 4. No-objetivos (v2)

- No es un leaderboard público ni multi-tenant; es una herramienta personal/lab.
- No evalúa calidad "absoluta" del modelo (MMLU etc.) — solo calidad *operativa*
  (validez de output, degradación a profundidad, estabilidad bajo carga). Los benchmarks
  académicos se citan del exterior.
- No gestiona descargas de HF automáticamente en v2.0 (catálogo manual asistido; v2.1).
- Sin soporte Windows nativo en v2.0 — pero nada en el dominio puede impedirlo.

## 5. Éxito = 

Re-certificar la campaña de mayo en ≤1 día de máquina por modelo con: curvas t/s-vs-profundidad,
mapa de concurrencia (modelo × slots × ctx → veredicto), y cero ambigüedad de máquina/versión.

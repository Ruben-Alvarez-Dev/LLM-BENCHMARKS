# Censo de parámetros — llama-bench / llama-server (auditoría 2026-06-06)

> Fuente: `--help` reales de los binarios instalados (b9430, ggml 0.13.1 — segunda
> actualización silenciosa de Homebrew HOY: 0.10.0→0.13.1). Principio: nada por
> sentado — cada parámetro o se cubre, o se descarta con lógica escrita, o se marca
> "comprobar". Un descarte lógico documentado > un desastre por omisión.

## llama-bench (instrumento de velocidad)

| Parámetro | Decisión | Razonamiento |
|---|---|---|
| `-d` (n-depth) | **EJE central** — acepta listas/rangos: `-d 0,8192,...` o `4096-1048576*2` → escalera entera en UNA invocación, mismo proceso, menos varianza | el fix del fallo A1 |
| `-r` (repeticiones) | **EJE** (≥3) | σ integrada |
| `-p`/`-n`/`-pg` | cubiertos (512/128); `-pg` para combinado pp+tg | estándar |
| `-ctk/-ctv` | **EJE** (f16, q8_0, q4_0; planar3 en fork) | simétrico en Metal (#21450) |
| `-fa` | **EJE** (0/1) | |
| `-b`/`-ub` (batch) | **EJE exploratorio** (1 celda por modelo: 2048/512 vs 4096/1024) | afecta prefill; sin presupuesto para barrido completo: exploración primero |
| `--delay` | **USAR** (2-5s entre tests) | asentamiento térmico/RAM entre repeticiones |
| `--no-warmup` | **NO usar** | el warmup respeta los tiempos de carga (requisito de aislamiento) |
| `--prio` | **USAR** `--prio 2` en campañas | reduce interferencia del SO; anotar en provenance |
| `-t` (threads) | default en Metal (-ngl 99 → CPU casi irrelevante); **EJE en VPS CPU** | TuningAdvisor decide por plataforma |
| `-nkvo` (no-kv-offload) | **1 celda exploratoria** por modelo | KV en CPU libera wired limit a costa de velocidad: puede habilitar contextos imposibles en 16GB — comprobar, no suponer |
| `-mmp` (mmap 0/1) | **1 celda exploratoria** | mmap=0 cambia el perfil de carga/RSS; medir una vez y decidir |
| `-dio` (direct-io) | **1 celda exploratoria** en modelos >8GB | acelera carga; irrelevante para decode |
| `-ncmoe` | descarte lógico en Apple Silicon (memoria unificada, informe 06-06) | revisar solo en VPS |
| `--numa` | descarte en Mac (no NUMA); **EJE en VPS Xeon** | |
| `-sm/-mg/-ts/-dev/-ot/-nopo/--no-host` | descarte lógico: multi-GPU/offload exótico — N/A en M1/M1 Max single-GPU | reactivar en CUDA |
| `-fitt/-fitc` | NO usar en campañas | el presupuesto lo decide NUESTRO KvModel (verificable); fit automático ocultaría OOMs |
| `-hf*` | NO en campañas (descarga implícita rompe limpieza/aprobación) | catálogo gestiona descargas |
| `-embd` | fuera de alcance v2 (embeddings) | |
| `--prio`/`--poll`/`-C` (afinidad) | default Mac; censo VPS pendiente | |

**Hallazgo crítico**: llama-bench **NO tiene flags rope/YaRN** → no puede medir
velocidad a profundidad > contexto nativo. Más allá del nativo (512K/700K/1M en
modelos 256K) la velocidad-at-depth se mide vía **llama-server** (que sí los tiene)
con el cliente de loadgen. El planner debe enrutar esas celdas a llama-server.

## llama-server (concurrencia + YaRN)

| Parámetro | Decisión |
|---|---|
| `-c/-np/--kv-unified` | EJES (total ctx / slots / unified) |
| `--rope-scaling yarn --yarn-orig-ctx N` | **OBLIGATORIO** si ctx > nativo (implementado en adapter; nunca extrapolación silenciosa). `--rope-scale`, `--yarn-ext-factor/attn-factor/beta-*`: defaults; barrido = investigación específica, no campaña |
| `--cache-reuse / --slot-save-path / --cache-ram` | EJES de prefix-cache (perfil B los valida) |
| `--swa-full` | NO (anula el ahorro iSWA); 1 celda exploratoria si un modelo SWA da resultados raros |
| `-ctxcp/--checkpoint-*` | vigilar #24055; defaults + perfil B detecta |
| `--threads/-tb/-ub/-b` | TuningAdvisor por plataforma |

## Verificación de consistencia (sustituye suposiciones por medición)

1. **Metadatos GGUF leídos del fichero** (`gguf_reader.py`): arquitectura, capas,
   kv_heads (por capa en híbridos), head_dim, ctx nativo, rope/YaRN. Si un modelo
   ya viene extendido por YaRN (original_context_length < context_length), el aviso
   es automático y la consistencia >original es obligatoria.
2. **Contexto verificable** (`verifiable.py`): balizas sha256 cada 1024 tokens →
   cualquier posición comprobable al 100%; preguntas multi-baliza (inicio/25/50/75/90/fin);
   **bisección** del contexto efectivo (≤12 sondas) — caza fallos rápido, p.ej.
   "anuncia 256K pero pierde balizas desde ~93K".
3. **Aislamiento entre celdas** (`battery.wait_recovery`): baseline de RAM al inicio
   de batería; la celda N+1 no arranca hasta recuperar baseline±1,5GB (timeout →
   warning de leak registrado). Limpieza impoluta incondicional al cerrar cada modelo.
4. Escalera de contextos completa: 4K·8K·16K·32K·64K·128K·256K·**512K**·700K·1M.

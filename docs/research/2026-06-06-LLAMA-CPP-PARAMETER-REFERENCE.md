# llama.cpp Parameter Reference — Metal / Apple Silicon (v9430)

> **Fecha:** 2026-06-06
> **Hardware:** Mac Mini M1 16GB + MacBook Pro M1 Max 32GB
> **Motor:** llama.cpp v9430 (Homebrew), Metal backend, turbo3 kernels
> **Propósito:** Referencia exhaustiva de cada parámetro de `llama-server` relevante para
> inferencia en Apple Silicon. Qué hace, cuándo/debes/no-debes tocarlo, por qué, y con qué evidencia.
> **Fuentes:** `tuning_rules.yaml`, `techniques.yaml`, `2026-06-06-VERIFICACION-ADVERSARIAL-SOTA.md`,
> `2026-05-24-APPLE-SILICON-INFERENCE-STACK.md`, issues/PRs de llama.cpp verificados.

---

## Índice

1. [Línea base corregida](#1-línea-base-corregida)
2. [Parámetros OBLIGATORIOS](#2-parámetros-obligatorios)
3. [Parámetros RECOMENDADOS](#3-parámetros-recomendados)
4. [Parámetros SITUACIONALES](#4-parámetros-situacionales)
5. [Parámetros PROHIBIDOS en Metal](#5-parámetros-prohibidos-en-metal)
6. [YaRN — Extensión de contexto >262K](#6-yarn--extensión-de-contexto-262k)
7. [Tabla resumen alfabética](#7-tabla-resumen-alfabética)
8. [Referencias](#8-referencias)

---

## 1. Línea base corregida

Comando mínimo correcto para QwenPaw-Flash-9B en Apple Silicon:

```bash
llama-server --port N \
  -m <model.gguf> \
  -ngl 99 \                 # todas las capas en GPU
  -c 262144 \               # contexto nativo Qwen3.5
  --host 127.0.0.1 \
  --jinja \                 # chat template
  --reasoning off \         # suprimir thinking tokens
  -fa 1 \                   # flash attention
  -ctk q4_0 -ctv q4_0 \     # KV cache q4 simétrico (Metal-safe)
  --cache-ram 8192 \        # KV tier RAM 8 GiB
  -kvu \                    # KV buffer unificado
  --cache-reuse 256 \       # prefix cache reuse
  --spec-type ngram-mod     # speculative decoding (única EV+ en Metal)
```

---

## 2. Parámetros OBLIGATORIOS

Estos parámetros NO son opcionales en Metal. Quitarlos produce crash, degradación
severa, o mediciones inválidas.

### 2.1 `-fa 1` / `--flash-attn on`

| Propiedad | Valor |
|---|---|
| Qué hace | Reduce la complejidad de atención de O(n²) a O(n). Sin esto, cada token generado recorre TODOS los tokens previos del KV cache. |
| Por qué tocarlo | Sin Flash Attention en Metal, el decode a 256K contexto es impracticable. |
| Cuándo NO tocarlo | Nunca. Es obligatorio en Metal. |
| Evidencia | `tuning_rules.yaml:8` · `2026-05-24-APPLE-SILICON-INFERENCE-STACK.md §2.1` |

### 2.2 `-ctk q4_0 -ctv q4_0`

| Propiedad | Valor |
|---|---|
| Qué hace | Cuantiza la caché KV a 4-bit (0.5 bytes/valor), reduciendo 4× vs f16. |
| Por qué tocarlo | Sin esto, el KV cache a 256K ocuparía ~8 GB (f16) y no cabría en M1 16GB. Con q4_0 ocupa ~2 GB. |
| Por qué SIMÉTRICO | En Metal, mezclar tipos K y V (ej. `q8_0` + `q4_0`) crashea. Deben ser iguales. |
| Cuándo NO tocarlo | Solo si el modelo no cabe ni con q4_0 — entonces hay que bajar contexto. |
| Advertencia | V q4_0 tiene ~−1.4% PPL loss (K q4_0 solo −0.4%). Aceptable para producción. |
| Evidencia | `llama.cpp#21450` (Metal KV type mismatch crash) · `techniques.yaml:16-19` · `TechPlained KV cache quantization` |

### 2.3 `-ngl 99`

| Propiedad | Valor |
|---|---|
| Qué hace | Carga TODAS las capas del modelo en GPU (Metal). |
| Por qué tocarlo | En Apple Silicon la RAM es unificada — no hay copia CPU↔GPU. Poner capas en "CPU" es inútil: ocupan la misma RAM pero se ejecutan más lento. |
| Cuándo NO tocarlo | Solo si el modelo no cabe en RAM y hay que hacer offloading parcial (raro en 9B con 16GB). |
| Evidencia | `tuning_rules.yaml:7` · `2026-05-24-APPLE-SILICON-INFERENCE-STACK.md §1` |

### 2.4 `--jinja`

| Propiedad | Valor |
|---|---|
| Qué hace | Habilita el motor de templates Jinja2 para formatear el chat (system/user/assistant/tool). |
| Por qué tocarlo | QwenPaw usa un chat template complejo (multimodal + reasoning + tool calling). Sin `--jinja`, el formateo falla o se degrada. |
| Cuándo NO tocarlo | Solo si el modelo no tiene template (modelos base sin instruct). |
| Evidencia | Comportamiento observado: sin `--jinja`, QwenPaw no genera respuestas correctas. |

### 2.5 `--reasoning off`

| Propiedad | Valor |
|---|---|
| Qué hace | Suprime los tokens de pensamiento (`reasoning_content`). El modelo genera directamente la respuesta. |
| Por qué es OBLIGATORIO para benchmarks | QwenPaw gasta TODOS los tokens de generación en pensar (ej: 64 tok → 0 content). Medir velocidad con `reasoning on` mide velocidad de PENSAR, no de responder. Los t/s reales de generación son más altos. |
| Cuándo NO tocarlo | En producción, si querés que el modelo razone antes de responder (mejor calidad, más latencia). |
| Parámetros relacionados | `--reasoning-budget N` (limitar tokens de pensamiento), `--reasoning-format deepseek` (extraer reasoning al campo separado). |
| Evidencia | Verificado experimentalmente 2026-06-06 con QwenPaw-Flash-9B: 64 completion_tokens → 0 content_tokens con reasoning auto. |

---

## 3. Parámetros RECOMENDADOS

Mejoran rendimiento o estabilidad sin contrapartidas significativas. Activar siempre.

### 3.1 `--cache-ram N`

| Propiedad | Valor |
|---|---|
| Qué hace | Reserva N MiB de RAM de sistema como tier adicional para KV cache. Cuando el KV cache crece, en vez de crashear o throttlear, se pagina a esta RAM extra. |
| Por qué tocarlo | El subsistema Metal tiene un límite de memoria "wired" (~26 GB en M1 Max 32GB). Sin `--cache-ram`, el KV cache compite con los pesos del modelo por ese presupuesto wired. Con `--cache-ram`, el KV excedente va a RAM normal, liberando presión. |
| Valor recomendado | `8192` (8 GiB) para ambos M1 16GB y M1 Max 32GB. Default ya es 8192. |
| Cuándo NO tocarlo | Solo si tenés <8 GB de RAM libre (no es el caso en 16GB+ con un modelo 9B). |
| Evidencia | `tuning_rules.yaml:20-22` · `2026-06-06-VERIFICACION-ADVERSARIAL-SOTA.md §3.2` · `llama.cpp#20574 tutorial` |

### 3.2 `-kvu` / `--kv-unified`

| Propiedad | Valor |
|---|---|
| Qué hace | Usa un único buffer KV compartido entre todos los slots del servidor, en vez de particionar el contexto entre slots. |
| Por qué tocarlo | Sin unified KV, 8 slots × contexto/8 = cada slot ve poco contexto. Con unified KV, cualquier slot puede usar todo el buffer disponible. Fundamental para multi-slot serving. |
| Cuándo NO tocarlo | Single-slot (no cambia nada). |
| Advertencia | Slots inactivos pueden degradar throughput con `--kv-unified` activo (`llama.cpp#19523`). |
| Evidencia | `tuning_rules.yaml:11` · `techniques.yaml:69-71` · `2026-06-06-VERIFICACION-ADVERSARIAL-SOTA.md §3.2` |

### 3.3 `--cache-reuse N`

| Propiedad | Valor |
|---|---|
| Qué hace | Reutiliza fragmentos de KV cache entre requests cuando detecta prefijos compartidos (ej. mismo system prompt). Ahorra reprefill. |
| Por qué tocarlo | En cargas agénticas con system prompts fijos, reduce TTFT drásticamente (no reprefillea el system prompt en cada turno). |
| Valor recomendado | `256` (chunks mínimos de 256 tokens para considerar reuso). |
| Cuándo NO tocarlo | Si cada request tiene prompts completamente distintos (ej. benchmark con prompts aleatorios). |
| Evidencia | `techniques.yaml:64-66` · `2026-06-06-VERIFICACION-ADVERSARIAL-SOTA.md §3.2` |

### 3.4 `--spec-type ngram-mod`

| Propiedad | Valor |
|---|---|
| Qué hace | Speculative decoding basado en n-gramas. Un pool de ~16 MB compartido entre slots predice tokens futuros basándose en patrones vistos. |
| Por qué tocarlo | Es la ÚNICA técnica de speculative decoding con valor esperado positivo en Metal. No requiere draft model externo (0 RAM extra). |
| Speedup esperado | +15% throughput en cargas de agente (output repetitivo/tool calling). |
| Cuándo NO tocarlo | Si tu carga es puramente creativa/alta entropía (poco patrón repetible). |
| Comparación con MTP | `draft-mtp` es PÉRDIDA NETA en Metal (−11% a −14×). No usar. |
| Evidencia | `techniques.yaml:37-49` · `2026-06-06-VERIFICACION-ADVERSARIAL-SOTA.md §3.4` · `llama.cpp#23752` |

### 3.5 `--cont-batching`

| Propiedad | Valor |
|---|---|
| Qué hace | Permite procesar múltiples requests concurrentes en un mismo batch, intercalando prefill y decode. |
| Por qué no tocarlo | Ya viene activado por defecto. Desactivarlo (`-nocb`) mata el throughput multi-stream. |
| Speedup | 2-3× agregado a 4-8 streams (medido en MLX, `arXiv:2601.19139`). |
| Evidencia | `2026-06-06-VERIFICACION-ADVERSARIAL-SOTA.md §3.4` |

---

## 4. Parámetros SITUACIONALES

Usar solo cuando la situación lo amerite. No son defaults universales.

### 4.1 `--mlock`

| Propiedad | Valor |
|---|---|
| Qué hace | Bloquea el modelo en RAM física, impidiendo que macOS lo swappee o comprima. |
| Cuándo SÍ usarlo | Máquina dedicada 100% a inferencia (sin otras apps pesadas). Da estabilidad de latencia. |
| Cuándo NO usarlo | Máquina compartida con desarrollo/navegador/IDE. El resto del sistema se queda sin RAM. |
| Evidencia | `tuning_rules.yaml:22` · `2026-06-06-VERIFICACION-ADVERSARIAL-SOTA.md §3.4` |

### 4.2 `--threads N` / `--threads-batch N`

| Propiedad | Valor |
|---|---|
| Qué hace | Número de hilos CPU para generación (`--threads`) y procesamiento de prompt (`--threads-batch`). |
| Cuándo SÍ tocarlo | En modelos híbridos (Qwen3.5 GDN), las capas SSM pueden beneficiarse de más hilos CPU. Probar: `--threads 8 --threads-batch 8`. |
| Cuándo NO tocarlo | Default `-1` (auto) ya detecta los cores físicos. Solo cambiar si ves CPU ociosa durante generación. |
| Evidencia | Observación: las capas SSM (`ssm_conv1d`, `ssm_scan`) en Qwen3.5 usan CPU, no GPU. |

### 4.3 `-ub N` / `--ubatch-size N`

| Propiedad | Valor |
|---|---|
| Qué hace | Tamaño del micro-batch físico para procesamiento de prompt. Default: 512. |
| Cuándo SÍ tocarlo | Contextos grandes (256K+) pueden OOM durante el prefill. Reducir a 256 o 128 desbloquea el prefill a costa de velocidad. |
| Cuándo NO tocarlo | Si todo cabe sin OOM, déjalo en default. |
| Evidencia | `wiki.charleschen.ai`: "256k unblocked with smaller ubatch" para Qwen3-8B + YaRN + TurboQuant. |

### 4.4 `--prio 2`

| Propiedad | Valor |
|---|---|
| Qué hace | Prioridad del proceso: 0=normal, 1=medium, 2=high, 3=realtime. |
| Cuándo SÍ usarlo | Benchmarking (para reducir jitter del scheduler de macOS). |
| Cuándo NO usarlo | Producción normal (el sistema se puede volver irresponsivo). |
| Evidencia | Experiencia operativa. |

### 4.5 `--warmup`

| Propiedad | Valor |
|---|---|
| Qué hace | Ejecuta una pasada de warmup vacía antes de aceptar requests. Añade ~2s al startup. |
| Cuándo SÍ mantenerlo | Siempre en benchmarks (mediciones estables). Viene activado por defecto. |
| Cuándo NO desactivarlo | Solo si necesitás arranque más rápido y no te importa que el primer request sea más lento. |

### 4.6 `--reasoning-budget N`

| Propiedad | Valor |
|---|---|
| Qué hace | Limita los tokens de pensamiento a N. -1 = sin límite, 0 = pensar inmediatamente terminado. |
| Cuándo SÍ usarlo | En producción con agentes: `--reasoning-budget 512` permite pensar lo justo sin disparar costes. |
| Cuándo NO usarlo | Si necesitás máxima calidad de razonamiento (tareas complejas). |
| Parámetros relacionados | `--reasoning-format deepseek` para extraer reasoning a `message.reasoning_content`. |
| Evidencia | Help de llama-server v9430 · `--reasoning-budget-message` inyecta mensaje al agotar presupuesto. |

### 4.7 `--mmproj FILE`

| Propiedad | Valor |
|---|---|
| Qué hace | Carga el proyector multimodal para habilitar entrada de imágenes. |
| Cuándo SÍ usarlo | QwenPaw-Flash es multimodal (hereda de Qwen3.5). Con `--mmproj`, acepta imágenes. |
| Cuándo NO usarlo | Si solo necesitás texto (ahorra ~879 MB de RAM). |
| Archivos disponibles | `mmproj-QwenPaw-Flash-9B-heretic-BF16.gguf` (879 MB) para variantes heretic; `QwenPaw-Flash-9B.mmproj-f16.gguf` (876 MB) para base. |

### 4.8 `-np N` / `--parallel N`

| Propiedad | Valor |
|---|---|
| Qué hace | Número de slots del servidor (requests concurrentes). Default: auto. |
| Cuándo SÍ tocarlo | `-np 1` para benchmarks single-stream (evita overhead de sincronización). `-np 4` o `-np 8` para serving multi-agente. |
| Cuándo NO tocarlo | Default auto ya elige bien para el hardware. |
| Advertencia | Más slots = más RAM de KV cache. Con 8 slots y 32K c/u sin unified KV: 8 × 32K = 256K de contexto total → mismo RAM que 1 slot a 256K con unified KV. |
| Evidencia | `2026-06-06-VERIFICACION-ADVERSARIAL-SOTA.md §3.4` · `llama.cpp#19523` (idle slot degradation). |

### 4.9 `-b N` / `--batch-size N`

| Propiedad | Valor |
|---|---|
| Qué hace | Tamaño máximo de batch lógico para procesamiento de prompt. Default: 2048. |
| Cuándo SÍ tocarlo | Subir a 4096 o 8192 para prefill más rápido en contextos grandes (más paralelismo). |
| Cuándo NO tocarlo | Si subirlo causa OOM. |
| Evidencia | Documentación estándar de llama.cpp. |

---

## 5. Parámetros PROHIBIDOS en Metal

Estos parámetros están verificados como dañinos en Apple Silicon. NO usar.

### 5.1 `--spec-type draft-mtp`

| Propiedad | Valor |
|---|---|
| Qué hace | Speculative decoding usando las cabezas MTP (Multi-Token Prediction) nativas del modelo. |
| Por qué PROHIBIDO | **Pérdida neta medida en Metal**: −11% en modelos 9B densos, hasta −14× en MoE. Las cabezas MTP del modelo funcionan en CUDA pero el kernel Metal de llama.cpp no está optimizado. |
| Qué usar en su lugar | `--spec-type ngram-mod` (ver §3.4). |
| Evidencia | `llama.cpp#23752` · `techniques.yaml:42-49` · `2026-06-06-VERIFICACION-ADVERSARIAL-SOTA.md §3.4` |

### 3414 `--spec-type draft-eagle3`

| Propiedad | Valor |
|---|---|
| Qué hace | Speculative decoding con EAGLE-3 (draft tree). |
| Por qué PROHIBIDO | PR #18039 sigue ABIERTO. Solo stub en master. No funciona. |
| Evidencia | `llama.cpp#18039` · `techniques.yaml:52-53` |

### 5.3 `--defrag-thold N`

| Propiedad | Valor |
|---|---|
| Qué hace | Umbral de desfragmentación del KV cache. |
| Por qué PROHIBIDO | **Deprecado**. Ignorado por el motor. |
| Evidencia | Help de llama-server v9430: "DEPRECATED". |

### 5.4 `--no-mmap`

| Propiedad | Valor |
|---|---|
| Qué hace | Deshabilita memory-mapping del modelo (carga en RAM en vez de mmap). |
| Por qué NO usar | En Apple Silicon con RAM unificada, mmap es más rápido y no tiene contrapartida. Deshabilitarlo solo añade latencia de carga sin beneficio. |
| Cuándo SÍ podría usarse | Solo en sistemas con swap agresivo donde mmap causa pageouts — pero en ese caso `--mlock` es mejor solución. |

### 5.5 `-nkvo` / `--no-kv-offload`

| Propiedad | Valor |
|---|---|
| Qué hace | Mantiene el KV cache en CPU en vez de GPU. |
| Por qué NO usar | En memoria unificada (Apple Silicon), CPU y GPU comparten la misma RAM. "Mover" KV a CPU no ahorra memoria pero añade contención de acceso. |
| Cuándo SÍ podría usarse | Solo en GPU discreta (AMD/NVIDIA en Mac Pro). Irrelevante en M1/M2/M3/M4. |

### 5.6 `--spec-draft-model` / `-md`

| Propiedad | Valor |
|---|---|
| Qué hace | Carga un modelo draft externo para speculative decoding. |
| Por qué NO usar en M1 16GB | Un draft model típico (0.5B) consume ~0.5-1 GB extra + su propio KV cache. En 16GB con un modelo 9B, esto empuja al límite. Además, el batching de 8 slots ya satura la GPU. |
| Evidencia | `2026-06-06-VERIFICACION-ADVERSARIAL-SOTA.md §3.4` |

### 5.7 `--context-shift`

| Propiedad | Valor |
|---|---|
| Qué hace | StreamingLLM: desplaza el contexto cuando se llena, descartando tokens viejos. |
| Por qué NO usar en QwenPaw | Incompatible con modelos híbridos (SWA, GDN). El estado recurrente de las capas SSM no puede "shift-earse". |
| Evidencia | `2026-06-06-VERIFICACION-ADVERSARIAL-SOTA.md §3.2`: "Off por defecto; incompatible con SWA e híbridos". |

---

## 6. YaRN — Extensión de contexto >262K

QwenPaw-Flash-9B (basado en Qwen3.5-9B) tiene 262K tokens de contexto nativo.
Para extenderlo más allá se requiere YaRN.

### 6.1 Flags necesarios

```bash
--rope-scaling yarn \
--rope-scale 4 \
--yarn-orig-ctx 262144 \
--override-kv qwen35.context_length=int:1000000 \
-c 1048576
```

### 6.2 Qué hace cada flag

| Flag | Efecto |
|---|---|
| `--rope-scaling yarn` | Activa YaRN (Yet another RoPE extensioN). Interpola posiciones más allá del contexto de entrenamiento. |
| `--rope-scale 4` | Factor de escala: 4 × 262K = 1M. Para 512K: `--rope-scale 2`. |
| `--yarn-orig-ctx 262144` | Contexto original del modelo (sin extender). YaRN usa esto para calcular la interpolación. |
| `--override-kv qwen35.context_length=int:1000000` | **Crítico**: el modelo hardcodea `context_length=262144` en sus metadatos. Sin este override, `-c 1000000` es ignorado. |

### 6.3 Flags de tuning YaRN (defaults suelen bastar)

| Flag | Default | Cuándo tocar |
|---|---|---|
| `--yarn-ext-factor` | -1.00 | 0.0 = interpolación pura, 1.0 = extrapolación pura. Solo tocar si hay degradación visible a contexto extremo. |
| `--yarn-attn-factor` | -1.00 | Escala la magnitud de atención con √t. Ajustar si el modelo "olvida" el principio del contexto. |
| `--yarn-beta-slow` | -1.00 | Dimensión de corrección alta (α). Ajuste fino para PPL a contexto largo. |
| `--yarn-beta-fast` | -1.00 | Dimensión de corrección baja (β). Ajuste fino para PPL a contexto corto. |

### 6.4 Resultados conocidos

| Modelo | YaRN | Resultado | Fuente |
|---|---|---|---|
| Qwen3-8B (40K nativo) | 4× → 160K limpio, 512K OOM | `wiki.charleschen.ai` (abr 2026) |
| Qwen3.5-9B (262K nativo) | 4× → 1M (Google Cloud Medium confirma que es posible) | Medium abr 2026 |
| Reddit: Qwen3.5 >260K | Requiere `--override-kv qwen35.context_length=int:N` | `r/LocalLLaMA` abr 2026 |
| Qwen3-Next | `--rope-scale 4` confirmado funcional | `r/LocalLLaMA` nov 2025 |

### 6.5 Cuándo SÍ y cuándo NO usar YaRN

| Situación | Decisión |
|---|---|
| Necesitás 512K o 1M en un modelo 262K nativo | **Sí**, con YaRN |
| Solo necesitás ≤256K contexto | **No**, el nativo alcanza y es más rápido |
| Estás en M1 16GB | **No**: a 512K YaRN, KV cache q4_0 ≈ 4 GB → modelo 5.4 + KV 4 + overhead 2 = 11.4 GB. Justo pero sin margen |
| Estás en M1 Max 32GB | **Sí**: 11.4 GB de 27 GB disponibles, sobra |

---

## 7. Tabla resumen alfabética

| Flag | Categoría | ¿Tocar? | Nota |
|---|---|---|---|
| `-b N` | Situacional | A veces | Subir a 4096 para prefill más rápido |
| `--cache-ram N` | Recomendado | **Sí** | 8192 MiB default |
| `--cache-reuse N` | Recomendado | **Sí** | 256 para system prompts |
| `--cont-batching` | Recomendado | No tocar | Ya viene on |
| `--context-shift` | Prohibido | **NO** | Incompatible con híbridos |
| `-ctk q4_0 -ctv q4_0` | Obligatorio | **Sí** | Simétrico obligatorio |
| `--defrag-thold` | Prohibido | **NO** | Deprecado |
| `-fa 1` | Obligatorio | **Sí** | Flash Attention |
| `--jinja` | Obligatorio | **Sí** | Chat template |
| `-kvu` | Recomendado | **Sí** | Unified KV |
| `--mlock` | Situacional | A veces | Solo máquina dedicada |
| `--mmap` | Default | No tocar | Déjalo on |
| `--mmproj FILE` | Situacional | A veces | Solo si necesitás visión |
| `-ngl 99` | Obligatorio | **Sí** | Todas las capas GPU |
| `-nkvo` | Prohibido | **NO** | Irrelevante en RAM unificada |
| `--no-mmap` | Prohibido | **NO** | Más lento sin beneficio |
| `-np N` | Situacional | A veces | 1 para benchmark, N para serving |
| `--override-kv ...` | YaRN | Solo >262K | `qwen35.context_length=int:N` |
| `--prio 2` | Situacional | A veces | Solo para benchmarks |
| `--reasoning off` | Obligatorio (bench) | **Sí** | Mide generación real |
| `--reasoning-budget N` | Situacional | A veces | Limitar tokens de pensamiento |
| `--rope-scaling yarn` | YaRN | Solo >262K | Activar extensión |
| `--rope-scale N` | YaRN | Solo >262K | Factor de escala |
| `--spec-draft-model` | Prohibido | **NO** | Demasiada RAM en 16GB |
| `--spec-type draft-mtp` | Prohibido | **NO** | Pérdida neta en Metal |
| `--spec-type ngram-mod` | Recomendado | **Sí** | Único EV+ en Metal |
| `--threads N` | Situacional | A veces | Solo si CPU ociosa |
| `-ub N` | Situacional | A veces | Reducir si OOM en prefill |
| `--warmup` | Default | No tocar | Déjalo on |
| `--yarn-orig-ctx N` | YaRN | Solo >262K | Modelo original context |

---

## 8. Referencias

| Fuente | Tipo | Enlace / Path |
|---|---|---|
| `tuning_rules.yaml` | Reglas declarativas | `LLM-BENCHMARKS/tuning_rules.yaml` |
| `techniques.yaml` | Catálogo de técnicas | `LLM-BENCHMARKS/techniques.yaml` |
| VERIFICACION-ADVERSARIAL-SOTA | Doc investigación | `INFERENCE-investigation/docs/research/2026-06-06-VERIFICACION-ADVERSARIAL-SOTA.md` |
| APPLE-SILICON-INFERENCE-STACK | Doc investigación | `INFERENCE-investigation/docs/research/2026-05-24-APPLE-SILICON-INFERENCE-STACK.md` |
| llama.cpp#21450 | Issue | KV type mismatch crash en Metal |
| llama.cpp#23752 | Issue | MTP net loss en Metal medido |
| llama.cpp#19523 | Issue | Idle slots degradan throughput con unified KV |
| llama.cpp#22673 | PR | MTP draft mergeado (16-may) |
| llama.cpp#18039 | PR | EAGLE-3 (abierto, stub) |
| llama.cpp#20574 | Tutorial | `--cache-ram` usage |
| r/LocalLLaMA | Reddit | YaRN Qwen3.5 >260K flags correctos |
| wiki.charleschen.ai | Wiki | YaRN Qwen3-8B 128K/256K campaign |

---

*Documento generado 2026-06-06 a partir del análisis exhaustivo de parámetros de llama-server v9430
(Homebrew) para Apple Silicon con backend Metal. Cada afirmación cita su fuente; las no verificables
se marcan explícitamente. Complementa `tuning_rules.yaml` y `techniques.yaml` con el razonamiento
detallado de cada parámetro.*

# Jart-OS Architecture — Diseño del Sistema de Inferencia Distribuida

> **Fecha:** 2026-05-24 (v2)
> **Hardware objetivo:** Mac Mini M1 16GB + NVMe 4TB TB3 (LOCAL-SERVER)
> **Red:** REMOTE-SERVER (VPS) + WORKSTATION (M1 MAX 32GB)
> **Propósito:** Documento de arquitectura que consolida toda la investigación en un diseño coherente

---

## Índice

1. [Arquitectura General](#1-arquitectura-general)
2. [Jerarquía de Memoria](#2-jerarquía-de-memoria)
3. [Modelo de Concurrencia: 1 Modelo → N Agentes](#3-modelo-de-concurrencia-1-modelo--n-agentes)
4. [Superpool: Perfiles de Estrategia](#4-superpool-perfiles-de-estrategia)
5. [KV Cache: Pools, Páginas y Swap](#5-kv-cache-pools-páginas-y-swap)
6. [Paginación de Contexto con NVMe](#6-paginación-de-contexto-con-nvme)
7. [TORQ: Cuantización MXFP4 vía Rotación Dual](#7-torq-cuantización-mxfp4-vía-rotación-dual)
8. [OSCAR: Cuantización KV Cache 2-bit con Rotación Espectral](#8-oscar-cuantización-kv-cache-2-bit-con-rotación-espectral)
9. [Integración con MCP-agent-memory](#9-integración-con-mcp-agent-memory)
10. [Validación Experimental](#10-validación-experimental)
11. [Referencias](#11-referencias)

---

## 1. Arquitectura General

```
┌─────────────────────────────────────────────────────────────────┐
│                    REMOTE-SERVER  100.77.1.10                    │
│  VPS IONOS · SIN GPU                                             │
│  ▶ Self-hosted APPS                                              │
│  ▶ EMBEDDINGS (BGE-M3) para todo Jart-OS (fallback principal)   │
│  ▶ Fallback chain: REMOTE → LOCAL → cada dispositivo propio     │
│     ⚠️ NUNCA mezclar modelos de embeddings (BGE-M3 siempre)     │
└────────────────────────┬────────────────────────────────────────┘
                         │ LAN / Tailscale
┌────────────────────────┴────────────────────────────────────────┐
│              ★ LOCAL-SERVER  100.77.1.20 ★                       │
│  Mac Mini M1 · 16 GB RAM · 256GB SSD · 4TB NVMe (TB3)          │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   ORQUESTADOR CENTRAL                    │    │
│  │  L5_routing (MCP-agent-memory) + Continuous Batching    │    │
│  │  Router ANE (Qwen3.5-0.8B, 48 tok/s, <5ms, 0 GB GPU)   │    │
│  └──────────┬──────────┬──────────┬──────────┬────────────┘    │
│             │          │          │          │                  │
│     ┌───────▼──┐ ┌────▼───┐ ┌───▼────┐ ┌───▼──────┐           │
│     │Agente A  │ │Agente B│ │Agente C│ │Agente D  │           │
│     │Investig. │ │Program.│ │Tester  │ │Orquest.  │           │
│     │64-128K   │ │64-128K │ │64-128K │ │64-128K   │           │
│     └───────┬──┘ └────┬───┘ └───┬────┘ └───┬──────┘           │
│             │          │          │          │                  │
│     ┌───────┴──────────┴──────────┴──────────┴──────┐          │
│     │         MODELO COMPARTIDO (llama.cpp)         │          │
│     │  Qwen3.5-9B Q4_K_S · Flash Attn · Metal      │          │
│     │  KV Pool: 4 ranuras × 128K (planar3 sim)     │          │
│     │  Continuous batching: todos en 1 forward pass │          │
│     └───────────────────────────────────────────────┘          │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  NVMe 4TB TB3 (~2.75 GB/s) — CAPA WARM                  │    │
│  │  5 modelos completos (swap en <2s)                      │    │
│  │  KV pages históricas (swap en ~140ms)                    │    │
│  │  Qdrant persistente (vectores, chunks, sesiones)        │    │
│  └─────────────────────────────────────────────────────────┘    │
└────────────────────────┬────────────────────────────────────────┘
                         │ LAN / Tailscale
┌────────────────────────┴────────────────────────────────────────┐
│                    WORKSTATION  100.77.1.30                      │
│  MacBook PRO M1 MAX 32GB · 1TB                                  │
│  ▶ Estación de trabajo y documentos                             │
│  ▶ Se mantiene FRÍA (Mac Mini es el servidor real)              │
│  ▶ Solo carga modelos experimentalmente o si fallan los otros   │
│  ▶ Puede liberar M1 MAX 32GB cuando la estrategia lo requiere   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Jerarquía de Memoria

```
         CAPA         TECNOLOGÍA         VELOCIDAD     CAPACIDAD    PROPÓSITO
    ───────────── ─────────────────── ───────────── ───────────── ──────────────────
    HOT (L0)      RAM unificada M1      ~70 GB/s      16 GB       Modelo activo
                                                                   KV pool caliente
                                                                   Router ANE

    WARM (L1)     NVMe TB3 externo     ~2.75 GB/s      4 TB        Modelos inactivos
                                                                   KV pages frías
                                                                   Qdrant completo
                                                                   Sesiones históricas

    COLD (L2)     VPS remoto (RED)      ~50 MB/s     Ilimitado     Embeddings fallback
                                                                   Backup
```

### Mapa de Ocupación de RAM (4 agentes activos)

| Componente | RAM | Nota |
|---|---|---|
| Modelo (Qwen3.5-9B Q4_K_S) | 4.71 GB | Fijo, no crece con agentes |
| KV pool (4 × 128K, planar3 sim) | 1.55 GB | 512K total, 0.194 bytes/elemento |
| Qdrant hot index | 0.20 GB | Solo el índice, vectores en NVMe |
| Embeddings (BGE-M3, solo si VPS cae) | 0.60 GB | Opcional, solo en fallback |
| macOS + sistema | 2.00 GB | Estimación conservadora |
| **TOTAL** | **9.06 GB** | |
| **LIBRE** | **6.94 GB** | ✅ Margen para picos |

### Comparativa CON vs SIN NVMe

| Aspecto | Sin NVMe (solo 16GB RAM) | Con NVMe 4TB TB3 |
|---|---|---|
| Modelos disponibles | 1 (el que quepa) | 5+ (swap en <2s) |
| KV pool máximo | 256K total | 1M+ por agente (paginado) |
| Sesión por agente | Limitada a hot pool | Infinita (pages en NVMe) |
| Qdrant | En RAM (~200 MB) | En NVMe (4 TB, sin límite) |
| Backup/restore | No aplica | Sesión entera en <1s |

---

## 3. Modelo de Concurrencia: 1 Modelo → N Agentes

### Principio

**1 modelo físico, N slots de contexto, continuous batching.**
Los agentes NO son instancias separadas del modelo. Son ranuras de KV cache
con system prompts, tools e historial independientes, procesadas todas en el
mismo forward pass de la GPU.

### Continuous Batching en llama.cpp

El descubrimiento clave de la investigación es que **llama.cpp ya soporta
continuous batching** a través de su `llama_batch` API. Cada slot (agente)
aporta sus tokens y el modelo procesa todos simultáneamente.

```
Slot A: [sys_prompt_A | tools_A | history_A | query_A] → genera
Slot B: [sys_prompt_B | tools_B | history_B | query_B] → genera
Slot C: [sys_prompt_C | tools_C | history_C | query_C] → genera
Slot D: [sys_prompt_D | tools_D | history_D | query_D] → genera
                      ↓
         1 forward pass de Qwen3.5-9B
          procesa los 4 slots juntos
                      ↓
             4 respuestas diferentes
```

### Paged KV Cache en llama.cpp (PR #22569)

Actualmente en desarrollo (draft PR) — implementa:
- Pool de bloques fijos (16 tokens/bloque por defecto)
- Asignación bajo demanda (solo los bloques que cada secuencia necesita)
- Scheduler con admisión, evicción y swap in/out entre GPU y CPU
- Copy-on-Write para compartir prefijos entre slots

Resultados reportados en A10G con Llama-3 8B:
- **Sin paging**: OOM a 26 secuencias concurrentes
- **Con paging**: 247 secuencias concurrentes, 2.5× throughput agregado

### Context Checkpoints (PR #22929)

Para sesiones largas de agentes: checkpoints de contexto que permiten
reanudar sesiones sin reprocesar todo el historial. Extrae el inicio del
mensaje del usuario y crea un checkpoint en esa posición.

> Probado con Pi, GPT, Qwen3.6 27B y Gemma 4 31B.

### Eficiencia por Turno (vLLM x Mooncake)

Análisis de 610 trazas de Codex/SWE-bench Pro:
- **94.2%** de cache hit rate en prefijo compartido
- Ratio input/output: **131:1**
- Crecimiento promedio: **2,242 tokens por turno**
- Cada turno es mayormente prefijo ya visto → el cómputo real es ~5.8%

**Implicación directa para Jart-OS:** El hot pool de 128K no es un límite
de sesión. Es un cache de los últimos tokens. El 90%+ del contexto de cada
turno es prefijo reutilizable, no tokens nuevos.

---

## 4. Superpool: Perfiles de Estrategia

Definidos en `config/superpool-profiles.md`. Resumen:

| Perfil | Modelo | RAM | tok/s | Contexto | Uso |
|---|---|---|---|---|---|
| **test** | Gemma 4 E2B + MTPLX | ~3 GB | 81 | 2-4K | Respuestas rápidas, health checks |
| **low-consumption** | Falcon3-7B STQ1_0 | ~5 GB | 18-25 | 32-128K | Background, batería |
| **reasoner** | Qwen2.5-7B-1M + planar3 K+f16 V | ~10 GB | 25-35 | 128-256K | Razonamiento profundo |
| **tooling** | Ministral-3-8B + MCP | ~9 GB | 30-40 | 32-128K | Tools, agentes, automatización |
| **max-context** | Qwen2.5-7B-1M + planar3 sim | ~7-9 GB | 14-44 | 512K-1M | RAG largo, codebase |
| **max-power** | Qwen3.5-9B + TORQ opcional | ~10 GB | 34 | 256K | Máxima calidad |
| **workstation-offload** | M1 MAX 32GB remoto | N/A | — | — | Cuando no quepa en LOCAL |

**Transiciones:** L5_routing clasifica la tarea (ANE, <5ms) y elige el perfil.
Cada perfil puede cargarse desde NVMe en <2s.

---

## 5. KV Cache: Pools, Páginas y Swap

### Matemática del KV Cache

Para Qwen3.5-9B (8 capas full-attention, 4 KV heads, 256 dim):

```
Por token (f16): 8 × 4 × 256 × 2 bytes × 2 (K+V) = 32,768 bytes = 32 KB
Por token (planar3 sim, 10.3×): 32 KB / 10.3 ≈ 3.1 KB
Pool completo (4 × 128K, planar3): 512K × 3.1 KB = 1.55 GB
```

### Pool Compartido

Los 4 agentes comparten un pool de KV cache de 512K tokens total.
Cada agente tiene un límite de 128K pero pueden usar menos si la sesión
es corta. El espacio no usado por un agente está disponible para otros.

```
Pool total: 512K tokens (planar3 sim = 1.55 GB)
  ├── Slot A: 128K máximo (uso real: variable)
  ├── Slot B: 128K máximo
  ├── Slot C: 128K máximo
  └── Slot D: 128K máximo
```

### Páginas y Copy-on-Write

Cuando dos agentes comparten el mismo prefijo (ej: mismo system prompt base),
las páginas de KV cache se comparten vía Copy-on-Write. Si un agente modifica
su contexto, solo sus páginas divergen.

---

## 6. Paginación de Contexto con NVMe

### Estrategia

La NVMe de 4TB actúa como **capa de paginación** para el KV cache.
Cuando un agente supera su hot pool de 128K:

1. **L5_routing detecta ocupación >90%**
2. **Toma los 32K más antiguos** del slot del agente
3. **Los resume a chunk semántico** (vía el propio LLM o condensación)
4. **Guarda en Qdrant (NVMe)** como memoria warm (~1KB por chunk)
5. **Libera 32K del pool** — el agente sigue con 96K + tokens nuevos
6. **Si el agente necesita contexto antiguo:** RAG query a Qdrant (~50ms),
   carga el chunk relevante al pool, el agente ve el contexto completo

### Tiempos de Acceso

| Operación | Medio | Latencia |
|---|---|---|
| Hot pool hit | RAM (70 GB/s) | 0 ms |
| Page fault → carga de NVMe | NVMe (2.75 GB/s) | ~140 ms (128K page) |
| RAG query a Qdrant en NVMe | NVMe | ~50 ms |
| Load chunk Qdrant → KV pool | NVMe → RAM | ~2 ms |
| Swap de modelo completo | NVMe | ~0.5-2 s |
| Embedding remoto | VPS (50 MB/s) | ~200 ms |
| Embedding local (fallback) | RAM | ~5 ms |

### Validación Experimental: Flash-MoE

**Flash-MoE** (Starlog, 2026) corre un modelo de 397B parámetros en un
MacBook Pro 48GB **streaming expert weights desde SSD**. Resultados:
- 71% hit rate en page cache del SO
- 17.5 GB/s de lectura desde NVMe
- Confía en `mmap` + page cache del kernel — venció a LRU custom, malloc pools y LZ4 por 38%

### Validación Experimental: MoE-MADV

**MoE-MADV** (daystar7777, 2026) corre DeepSeek V4 284B en M1 Max 64GB
usando `MADV_WILLNEED` para prefetch de expertos:
- +25.4% decode throughput solo con hinting al OS
- 97.6% I/O-active en perfil inicial (sin optimizar)
- Usa `mmap` directamente sobre el GGUF

### Spike: Weight Block Pager

**Spike** (matthewworner, 2026) es un pager de bloques de peso para LLMs:
- Predictor Markov chain para prefetching
- 91% probabilidad de transición capa N → capa N+1
- 78% probabilidad cluster experto A → cluster experto B
- Diseñado para Apple Silicon + llama.cpp + MLX

### Implicación directa para Jart-OS

El NVMe no es "disco". Es el mismo mecanismo que Flash-MoE, MoE-MADV y
Spike usan: **paginación de pesos y contexto vía mmap + page cache del SO.**
El sistema operativo ya resuelve el problema mejor que cualquier cache custom.

---

## 7. TORQ: Cuantización MXFP4 vía Rotación Dual

**Referencia:** arXiv 2605.19561 — TORQ: Two-level Orthogonal Rotation for MXFP4 Quantization

### El Problema

MXFP4 (Microscaling FP4, formato nativo de Blackwell) sufre dos
desbalances estructurales:
1. **Inter-block Variance Imbalance:** Unos pocos bloques de alta varianza
   fuerzan el scaling factor hacia arriba, destruyendo la precisión de los
   valores pequeños.
2. **Intra-block Codebook Collapse:** El codebook geométrico de MXFP4
   no se alinea con la distribución real de activaciones (heavy-tailed).

### La Solución: Dos Niveles de Rotación

1. **Macro-Equilibrium Rotation (inter-block):** Basada en teorema de
   Schur-Horn. Givens rotations iterativas para ecualizar la varianza
   entre todos los bloques. O(B²) tiempo.
2. **Micro-Alignment Rotation (intra-block):** Maximiza entropía de
   ocupación del codebook. Alterna S-step (escala) + R-step (rotación).

### Resultados

| Modelo | RTN directo | TORQ | BF16 (full) |
|---|---|---|---|
| LLaMA3-8B (PPL WikiText) | >280 (fallo) | **8.57** | 8.11 |
| LLaMA3-8B (Avg Acc) | ~32% | **69.32%** | ~74% |
| Qwen3-32B (PPL) | — | **8.43** | 7.61 |
| Qwen3-32B (Avg Acc) | 38.40% | **73.63%** | 74.82% |

### Relevancia para Jart-OS

TORQ es la técnica "v-torque" (Vector TORQ) del superpool.
Añade una capa de cuantización de activaciones MXFP4 que:
- Se fusiona con los pesos de la capa lineal adyacente (overhead ~0 en inferencia)
- Solo necesita 128 muestras de calibración
- Es training-free (PTQ)
- Ideal para el perfil **max-power** cuando se busca máxima calidad

---

## 8. OSCAR: Cuantización KV Cache 2-bit con Rotación Espectral

**Referencia:** GitHub FutureMLS-Lab/OSCAR — Offline Spectral Covariance-Aware Rotation

### Qué es

OSCAR captura activaciones Q/K/V en un set de calibración pequeño, estima
**estructuras de covarianza K/V con conciencia de atención** offline, y
deriva rotaciones + thresholds de clipping por capa.

### Resultados

| Método | BPE | Qwen3-8B | Qwen3-32B | GLM-4.7 358B |
|---|---|---|---|---|
| BF16 | 16.00 | 70.84 | 74.19 | 77.89 |
| TurboQuant K3V3 | 3.25 | 56.88 | 71.99 | 78.15 |
| QuaRot-INT2 | 2.25 | 10.14 | 7.90 | 75.14 |
| **OSCAR (2.28 BPE)** | **2.28** | **69.42** | **74.17** | **78.16** |
| Gap vs BF16 | | **-1.42** | **-0.02** | **+0.27** |

**OSCAR a 2.28 BPE pierde solo 1.42 puntos en Qwen3-8B y 0.02 en Qwen3-32B.**
TurboQuant a 3.25 BPE pierde 13.96 y 2.20 respectivamente.

### Relevancia para Jart-OS

OSCAR permite comprimir el KV cache a **~2.3 bits por elemento** (vs los
0.194 de planar3 que son ~1.55 bits efectivos). La diferencia no es
tanto en compresión como en **calidad**: OSCAR está diseñado para preservar
la fidelidad de atención, no solo minimizar error de cuantización.

Podría ser un complemento a planar3 para el perfil **max-context** donde
cada bit de precisión importa.

---

## 9. Integración con MCP-agent-memory

### Mapeo L0-L5 → Sistema de Paginación

| Capa MCP | Función | Dónde vive | Correspondencia KV |
|---|---|---|---|
| L0 RAW | Event lake (JSONL) | NVMe | No aplica |
| L1 WORKING | Pasos, facts, hot dialogue | RAM (Qdrant hot) | Tokens activos en KV pool |
| L2 EPISODIC | Eventos agrupados, incidentes | NVMe (Qdrant full) | Chunks de contexto paginados |
| L3 SEMANTIC | Decisiones, entidades, patrones | NVMe (sistema archivos) | Contexto condensado |
| L4 CONSOLIDATED | Narrativas, resúmenes profundos | NVMe (Qdrant) | Resúmenes de sesión completa |
| L5 SELECTIVE | Routing de contexto y ensamblaje | RAM (proceso activo) | **Orquestador de paginación** |

### L5_routing como Gestor de Paginación

El módulo L5_routing de MCP-agent-memory se convierte en el **gestor de
paginación de KV cache**:

```
L5_routing_request_context(token_request, agente_id)
  ├── 1. ¿El contexto solicitado está en el hot pool (RAM)?
  │    ├── Sí → devuelve hit inmediato (0 ms)
  │    └── No →
  ├── 2. ¿Está en Qdrant (NVMe, warm)?
  │    ├── Sí → RAG query (~50 ms) → carga a KV pool → devuelve
  │    └── No →
  └── 3. Está en disco (JSONL, cold)
       → load a Qdrant → load a KV pool → devuelve (~500 ms)
```

### Ciclo de Vida de una Sesión Larga

```
1. Agente inicia → KV pool vacío (0 GB)
2. Cada interacción → ~500 tokens en su slot
3. Al llegar a 128K (~256 interacciones):
   → L5_routing detecta 90% ocupación
   → Saca los 32K más antiguos
   → Los condensa a chunk semántico
   → Chunk → Qdrant (NVMe, ~1KB)
   → Libera 32K del pool
4. Si el agente pregunta por contexto antiguo:
   → RAG query a Qdrant (~50ms)
   → Carga chunk relevante al KV pool
   → Respuesta normal
5. Sesión infinita, penalidad: ~500ms en page fault
```

---

## 10. Validación Experimental

### Proyectos Externos que Validan el Diseño

| Proyecto | Qué hace | Hardware | Valida para Jart-OS |
|---|---|---|---|
| **Flash-MoE** | 397B MoE desde NVMe, mmap, page cache del SO | MacBook 48GB | NVMe como capa warm, confiar en OS page cache |
| **MoE-MADV** | DeepSeek V4 284B con MADV_WILLNEED | M1 Max 64GB | Prefetch de contexto con hinting al kernel |
| **Spike** | Weight block pager con Markov predictor | Apple Silicon | Prefetch predictivo de pesos y KV pages |
| **llama.cpp PR#22569** | Paged KV cache + scheduler | Cualquier GPU | Páginas de KV, continuous batching, CoW |
| **llama.cpp PR#22929** | Context checkpoints para agentes | Cualquier GPU | Checkpoints de sesión para resume rápido |
| **vLLM Mooncake** | Prefix caching para agentic workloads | 60×GB200 | 94.2% cache hit, 131:1 ratio input/output |
| **OSCAR** | KV cache 2-bit con rotación espectral | Cualquier GPU | 2.28 BPE, pérdida <1.5 puntos |
| **TORQ** | MXFP4 dual rotation | Blackwell | Formato MXFP4 para activaciones |

### Confirmación de la Tesis Central

> **"El 90%+ del contexto de cada turno agentico es prefijo reutilizable."**

Los datos de vLLM x Mooncake (610 trazas, 33 turnos promedio) confirman:
- 94.2% cache hit rate
- 131 tokens de input por cada token de output
- 2,242 tokens nuevos por turno en promedio

Esto valida que **128K de hot pool por agente es suficiente para cubrir
~60 turnos de contexto activo antes de necesitar paginación.** Y cuando
se necesita, la página está en NVMe a 140ms de distancia.

---

## 11. Referencias

### Papers

| Paper | Venue | Link |
|---|---|---|
| TORQ: Two-Level Orthogonal Rotation for MXFP4 Quantization | arXiv May 2026 | arxiv.org/abs/2605.19561 |
| Block Rotation is All You Need for MXFP4 Quantization | ICML 2026 Poster | icml.cc/virtual/2026/poster/62818 |
| OSCAR: Offline Spectral Covariance-Aware Rotation for 2-bit KV Cache | arXiv May 2026 | arxiv.org/html/2605.17757 |

### Repositorios

| Proyecto | Link |
|---|---|
| FutureMLS-Lab/OSCAR | github.com/FutureMLS-Lab/OSCAR |
| matthewworner/spike | github.com/matthewworner/spike |
| daystar7777/MoE-MADV | github.com/daystar7777/MoE-MADV |
| Ruben-Alvarez-Dev/MCP-agent-memory | github.com/Ruben-Alvarez-Dev/MCP-agent-memory |
| Ruben-Alvarez-Dev/PROJECT-RAMIRO | github.com/Ruben-Alvarez-Dev/PROJECT-RAMIRO |

### PRs Activos (Mayo 2026)

| PR | Descripción |
|---|---|
| llama.cpp #22569 | Paged KV cache + scheduler (draft) |
| llama.cpp #22929 | Context checkpoints para agentes |
| vLLM #41685 | Pipeline parallelism optimizado para contexto largo |
| NVIDIA/Model-Optimizer #1372 | MXFP4 → NVFP4 weight cast |

### Guías

| Título | Fuente |
|---|---|
| KV Cache & PagedAttention Guide (2026) | localaimaster.com |
| Flash-MoE: 397B Model on 48GB RAM | starlog.is |
| How I Budget 64GB Unified Memory on M1 Max | dev.to/sleepyquant |
| Ollama vs llama.cpp vs vLLM (2026) | dev.to/thurmon_demich |
| DGX Spark + Mac Studio: Disaggregated Inference | allthings.how |
| llama.cpp Agent Architecture — Production Bottlenecks | markaicode.com |
| Saving GPU Memory with KV Cache Offloading | backend.ai |

---

*Documento generado el 2026-05-24 (v2). Consolidación de investigación web
(Brave, Kagi, Tavily, Serper, Jina, Exa, Linkup, Firecraw) + análisis de
repositorios locales (INFERENCE-investigation, CAAL, PROJECT-RAMIRO,
MCP-agent-memory) + verificación de código fuente (GitHub comunidad).*

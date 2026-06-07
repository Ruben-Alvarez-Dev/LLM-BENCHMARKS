# Apple Silicon Inference Stack — Pipeline Custom para Mac Mini M1 16GB

> **Fecha:** 2026-05-24 (v3, junio 2026 — ver addenda abajo)
> **Hardware:** Mac Mini M1 16GB + MacBook Pro M1 Max 32GB
> **Propósito:** Catálogo razonado de tecnologías, modelos, motores y estrategias para
> inferencia local de LLMs en Apple Silicon con recursos limitados.
> **Estado:** Activo. Actualizado con motor ROTORQUANT turbo3 compilado a medida.
>
> **ADDENDA JUNIO 2026 — Documentos complementarios (misma carpeta):**
> - `2026-06-06-VERIFICACION-ADVERSARIAL-SOTA.md` — Auditoría adversarial de afirmaciones SOTA
> - `2026-06-06-LLAMA-CPP-PARAMETER-REFERENCE.md` — Referencia exhaustiva de parámetros llama-server
> - `2026-06-06-BUILD-llama-cpp-rotorquant-turbo3-metal-arm64-johndpope-ssm-qwen35.md` — Build del motor ROTORQUANT turbo3 para Apple Silicon

---

## Índice

1. [Contexto Hardware](#1-contexto-hardware)
2. [Motores de Inferencia](#2-motores-de-inferencia)
3. [Cuantización de Pesos](#3-cuantización-de-pesos)
4. [Cuantización de KV Cache](#4-cuantización-de-kv-cache)
5. [Speculative Decoding](#5-speculative-decoding)
6. [Estrategias MoE para RAM Limitada](#6-estrategias-moe-para-ram-limitada)
7. [Motores TTS para Apple Silicon](#7-motores-tts-para-apple-silicon)
8. [Ecosistema MCP para Agentes Locales](#8-ecosistema-mcp-para-agentes-locales)
9. [Modelos Recomendados por Caso de Uso](#9-modelos-recomendados-por-caso-de-uso)
10. [Pipeline Recomendado para M1 16GB](#10-pipeline-recomendado-para-m1-16gb)
11. [VPS Research Stack — Herramientas de Investigación](#11-vps-research-stack--herramientas-de-investigación)
12. [MCP Ecosystem Local — Proyectos Propios y Afines](#12-mcp-ecosystem-local--proyectos-propios-y-afines)
13. [Nuevos Modelos y Benchmarks (Mayo 2026)](#13-nuevos-modelos-y-benchmarks-mayo-2026)
14. [Referencias y Fuentes](#14-referencias-y-fuentes)

---

## 1. Contexto Hardware

### Mac Mini M1 (2020)

| Especificación | Valor |
|---|---|
| SoC | Apple M1 |
| CPU | 4× Firestorm (rendimiento) + 4× Icestorm (eficiencia) |
| GPU | 8 núcleos — 2.6 TFLOPS FP32 |
| Neural Engine (ANE) | 16 núcleos — 11 TOPS |
| **RAM unificada** | **16 GB** (compartida CPU + GPU + ANE) |
| Ancho de banda memoria | ~70 GB/s (LPDDR4X) |
| RAM disponible para modelo | ~10-12 GB (tras sistema ~3-4 GB + overhead) |

### Implicaciones Arquitectónicas

1. **Memoria unificada:** No hay copia CPU↔GPU vía PCIe. Todo acceso es a la misma RAM física.
   Esto hace que el "offloading" CPU–GPU en Apple Silicon sea inherentemente más eficiente
   que en PC con GPU discreta.

2. **Cuello de botella real:** Ancho de banda de memoria (~70 GB/s). No es compute.
   Técnicas que reducen lecturas de memoria (cuantización, speculative decoding) impactan
   más que aumentar FLOPs.

3. **ANE separado:** El Neural Engine tiene su propia memoria (~2-4 GB) y no accede a la RAM
   unificada. Esto limita su contexto máximo a ~2K tokens pero lo hace ideal para tareas
   satélite (routing, STT, embeddings) que no tocan la GPU.

4. **Límite duro de 16 GB:** Un modelo Q4_K_M de 9B (~5 GB) + KV cache a 256K (~2-8 GB
   según cuantización) + overhead deja poco margen. Las técnicas de compresión agresiva
   (ternaria, 1-bit, MoE offloading) no son lujo — son necesidad.

---

## 2. Motores de Inferencia

### 2.1 llama.cpp (Metal) — Recomendado para carga principal

| Aspecto | Valor |
|---|---|
| Backend GPU | Metal (MPS) |
| Flash Attention | ✅ `--flash-attn 1` — O(n) en contexto largo |
| Cuantización | Q, IQ, TQ, SQ (ver sección 3) |
| KV Cache Quant | PlanarQuant, IsoQuant, TurboQuant+ |
| Formato modelo | GGUF |
| Tok/s (Qwen3.5-9B Q4_K_S, 512pp+128tg) | **34.6 tok/s** |
| Tok/s (Qwen2.5-7B Q4_K_M, misma carga) | **44.9 tok/s** |
| Prefill (Qwen3.5-9B, 1K prompt) | ~245 tok/s |
| Latencia primer token | ~1.2s |

**Fortalezas:**
- Único motor con Flash Attention real optimizado para Metal en Apple Silicon
- Ecosistema de cuantización más amplio: Q, IQ, TQ, STQ, SQ
- Soporta CPU+GPU híbrido para modelos que no caben en VRAM
- PlanarQuant/IsoQuant (10.3× KV cache) implementado en fork RotorQuant
- STQ1_0 (Sherry) 1.3125-bit recién integrado (PR #22836, mayo 2026)

**Debilidades:**
- Formato GGUF requiere conversión (no lee safetensors directamente)
- Sin speculative decoding nativo (requiere parches externos)
- Sin MTP heads nativas (a diferencia de MTPLX en MLX)

### 2.2 MLX (Apple) — Recomendado para contexto corto + agentes

| Aspecto | Valor |
|---|---|
| Backend GPU | Metal (nativo Apple) |
| Flash Attention | ❌ — usa `mx.fast.scaled_dot_product_attention` = O(n²) |
| Cuantización | 4-bit, 8-bit (safetensors nativos) |
| Speculative decoding | ✅ MTPLX, DFlash, DDTree (kernels Metal custom) |
| Formato modelo | Safetensors (nativo MLX) |
| Tok/s (Qwen3.5-9B, 84 tok) | **37.5 tok/s** |
| Tok/s (Qwen3.5-9B, 8K tok) | **1.9 tok/s** (degradación O(n²)) |

**Fortalezas:**
- MTPLX: speculative decoding 2.04-2.24× con MTP heads nativas
- Lightning MLX alcanza **70 tok/s** en Qwen3.6-27B y **226 tok/s** en Qwen3.6-35B MoE
- Lee safetensors directo — cero conversión
- Framework oficial de Apple — inversión directa de Apple

**Debilidades:**
- **CRÍTICO:** Sin Flash Attention real → degradación exponencial en contexto largo
- A 8K contexto: 1.9 tok/s vs llama.cpp 26+ tok/s (constante)
- Ecosistema de cuantización más limitado
- Solo Apple Silicon (no portable)

### 2.3 CoreML / ANE — Recomendado solo para tareas satélite

| Aspecto | Valor |
|---|---|
| Backend GPU/ANE | ANE (chip dedicado, ~2-4 GB propia) |
| Flash Attention | ❌ |
| KV Cache Quant | ❌ |
| Contexto máximo | **~2K tokens** (limitado por memoria ANE) |
| Velocidad (Qwen3.5-0.8B en ANE) | ~48 tok/s en iPhone / ~20 tok/s en M1 |
| Ecosistema | Muy nicho — ~10-180 descargas en HF por modelo |

**Casos de uso válidos en pipeline:**
- **Router ultrarrápido:** Qwen3.5-0.8B en ANE clasifica requests en <5ms sin tocar GPU
- **STT:** Whisper CoreML en ANE (transcripción sin ocupar RAM unificada)
- **Embeddings RAG:** EmbeddingGemma-300M en ANE (295 MB, búsqueda semántica)
- **Visión/OCR:** Apple Vision framework nativo en ANE

**NO sirve para:** LLM 256K+, tool calling complejo, generación de código.

---

## 3. Cuantización de Pesos

### 3.1 Formatos Clásicos (GGUF estándar)

| Formato | Bits/peso | Tamaño Qwen3.5-9B | Calidad relativa |
|---|---|---|---|
| FP16 | 16 | ~18 GB | baseline |
| Q8_0 | 8 | ~9 GB | ~0.1% PPL loss |
| Q6_K | 6.5 | ~7 GB | ~0.5% PPL loss |
| Q5_K_M | 5.5 | ~6 GB | ~1% PPL loss |
| **Q4_K_M** | 4.5 | ~5.0 GB | ~2% PPL loss |
| Q4_K_S | 4.5 | ~4.7 GB | ~3% PPL loss |
| Q3_K_M | 3.5 | ~4.0 GB | ~5% PPL loss |
| Q2_K | 2.5 | ~3.0 GB | ~10% PPL loss |

### 3.2 Formatos IQ (Importance-aware Quantization)

| Formato | Bits/peso | Tamaño teórico | Notas |
|---|---|---|---|
| IQ4_NL | 4.5 | ~5 GB | Mejor IQ para 4-bit |
| IQ3_S | 3.5 | ~4 GB | Bueno para 3-bit |
| IQ2_S | 2.5 | ~3 GB | Usable en tareas simples |
| IQ1_S | 1.5 | ~2 GB | Experimental |

### 3.3 Formatos Ternarios — NOVEDADES Mayo 2026

#### STQ1_0 / Sherry (PR #22836 — recién mergeado en llama.cpp)

| Propiedad | Valor |
|---|---|
| Bits/peso | **1.3125** |
| Estructura | 3:4 sparsity (3 pesos {-d,+d}, 1 zero por cada 4) |
| Decodificación | Lookup table 32-entry + `vqtbl2q` + `vdotq_s32` (ARM NEON) |
| Kernel Metal | ✅ (PR #23332 — CUDA; ARM NEON nativo) |
| Paper | Sherry — ACL 2026 (`arxiv.org/abs/2601.07892`) |

**Ventaja clave para M1 16GB:** Un modelo ternario STQ1_0 de 7B pesa ~1.3 GB.
Quedan ~11 GB para KV cache y sistema.

#### CAT-Q — ICML 2026 (Poster)

| Propiedad | Valor |
|---|---|
| Muestras calibración | Solo **512** |
| Training tokens equivalentes | 100B (BitNet) → 512 (CAT-Q) = **100,000× menos** |
| Modelos demostrados | 1.7B a 235B |
| Componentes | Learnable Modulation (LM) + Softened Ternarization (ST) |

**Implicación:** Podés ternarizar tu propio modelo (Qwen3.5-9B, Ministral-8B)
con CAT-Q sin entrenamiento costoso. 512 muestras de calibración bastan.

#### ATLAS-TQ1.0 — CPU Ternary Inference

| Modelo ternario | Tamaño TQ1 | RAM mínima |
|---|---|---|
| Falcon3-1B | 1.22 GB | 2 GB |
| Falcon3-3B | 1.96 GB | 4 GB |
| Falcon3-7B | **2.75 GB** | **6 GB** |
| Falcon3-10B | 3.28 GB | 8 GB |

### 3.4 Formato 1-bit — Q1_0_g128 / Bonsai

| Propiedad | Valor |
|---|---|
| Bits/peso | **1.0** (+ FP16 scale cada 128 pesos) |
| Tamaño Bonsai-8B | **1.15 GB** (vs ~16 GB FP16) |
| Motor | OxiBonsai (Rust puro) |
| SIMD | NEON (ARM), AVX2/AVX-512 (x86) |

**Para M1 16GB:** Bonsai-8B en 1.15 GB permite tener 3-4 modelos
cargados simultáneamente (ej: chat + código + RAG + tools).

### 3.5 TORQ — Two-level Orthogonal Rotation para MXFP4 (Mayo 2026)

**Referencia:** arXiv 2605.19561 — TORQ: Two-level Orthogonal Rotation for MXFP4 Quantization

| Propiedad | Valor |
|---|---|
| Formato objetivo | MXFP4 (e2m1) — Microscaling FP4, nativo en NVIDIA Blackwell |
| Bits/peso | 4 (floating-point block-shared exponent) |
| Enfoque | **Dos niveles de rotación ortogonal** sin reentrenamiento |
| Muestras calibración | Solo **128** segmentos de texto |
| Training | ❌ PTQ — post-training quantization |

**Los dos niveles de rotación:**

1. **Macro-Equilibrium Rotation** (inter-block): Basada en el teorema Schur-Horn.
   Redistribuye la energía de activación entre bloques para ecualizar varianzas.
   Previene que bloques de alta varianza dominen el error total.
   Implementada como rotaciones Givens iterativas (O(B²)).

2. **Micro-Alignment Rotation** (intra-block): Maximiza la entropía de ocupación
   del codebook MXFP4. Remodela la distribución local para que fluya
   uniformemente en cada intervalo de codificación FP4.
   Optimización alternante S-step (escala) + R-step (rotación).

**Resultados:**
| Modelo | Métrica | RTN directo | **TORQ** | BF16 (referencia) |
|---|---|---|---|---|
| LLaMA3-8B | WikiText PPL | >280 (fallo) | **8.57** | 8.11 |
| LLaMA3-8B | Avg Acc zero-shot | ~32% | **69.32%** | ~74% |
| Qwen3-32B | WikiText PPL | — | **8.43** | 7.61 |
| Qwen3-32B | Avg Acc | 38.40% | **73.63%** | 74.82% |

**Relevancia para Jart-OS:** TORQ es la única técnica diseñada específicamente
para MXFP4, el formato de cuantización de próxima generación soportado nativamente
en Blackwell. Se alinea con las técnicas de rotación del stack (Planar, Iso, Rotor)
pero opera a nivel de activación (no KV cache). Implementable como estrategia
"v-torque" en el perfil **max-power** o **max-context**.

### 3.6 Cuantización MLX nativa — mlx-onecomp

| Propiedad | Valor |
|---|---|
| Métodos | GPTQ, RTN, QEP portados a MLX |
| Memoria para shardear | 2-4 GB RAM |
| Preprocesamiento | Rotación Hadamard/Random para reducir outliers |
| AutoBit | Asignación óptima de bits por capa (ILP) |
| Post-cuantización | LoRA fine-tuning para recuperar calidad |

---

## 4. Cuantización de KV Cache

### 4.1 RotorQuant / PlanarQuant / IsoQuant — TU STACK

| Método | Grupo | Operaciones (d=128) | Parámetros | Calidad |
|---|---|---|---|---|
| TurboQuant (Google) | Denso d×d WHT | 16,384 | 16,384 | baseline |
| **IsoQuant** | **4D quaternion** | **512** | **128** | **mejor** |
| **PlanarQuant** | **2D Givens** | **256** | **128** | **mejor** |
| RotorQuant (Clifford) | Cl(3,0) sandwich | ~2,400 | 372 | research |

**Resultados en M1 Max (Qwen3.5-9B a 256K contexto):**

| K | V | Decode | RAM 256K | PPL loss |
|---|---|---|---|---|
| f16 | f16 | 34.5 | 14.5 GB | 0% |
| **planar3** | **f16** | **29.6** | **10.9 GB** | **0%** ✅ |
| q4_0 | q4_0 | 34.6 | 8.5 GB | ~2% |
| **planar3** | **planar3** | **25.8** | **7.2 GB** | **+4.2%** |
| **planar3** | **q8_0** | **22.4** | **8.8 GB** | **~1%** |

### 4.2 TurboQuant+ — Extensión con Metal TurboFlash

Añade sobre PlanarQuant/IsoQuant:
- **Metal TurboFlash** — fused kernel para Apple Silicon
- **V2.1 fused kernels** — dequant + attention en un solo paso
- **Attention-gated sparse dequantization** — solo decodifica canales relevantes
- **Layer-aware V compression** — políticas diferentes por capa

### 4.3 Cálculo de RAM para KV Cache en M1 16GB

**Qwen3.5-9B** (8 full-attn, 4 KV heads, 256 dim):

| KV Type | bytes | 128K | 200K | 256K |
|---|---|---|---|---|
| f16 | 2 | 4.00 GB | 6.00 GB | 8.00 GB |
| q8_0 | 1 | 2.00 GB | 3.00 GB | 4.00 GB |
| q4_0 | 0.5 | 1.00 GB | 1.50 GB | **2.00 GB** |
| planar3 K+f16 V | 1.04 | 2.08 GB | 3.12 GB | 4.16 GB |
| **planar3 simétrico** | **0.194** | **0.39 GB** | **0.58 GB** | **0.78 GB** |

**Qwen2.5-7B-1M** (28 capas, 4 KV heads, 128 dim) — a 1M contexto:

| KV Type | 256K | 512K | 1M |
|---|---|---|---|
| f16 | 7.00 GB | 14.0 GB | 28.0 GB |
| q4_0 | 1.75 GB | 3.50 GB | **7.00 GB** |
| planar3 | **0.68 GB** | **1.36 GB** | **2.72 GB** |

---

## 5. Speculative Decoding

### 5.1 MTPLX — Multi-Token Prediction nativo en Apple Silicon

**Referencia:** `github.com/youssofal/MTPLX` — 544★, Apache 2.0, mayo 2026

| Propiedad | Valor |
|---|---|
| Mecanismo | Cabezas MTP del propio modelo como drafter |
| Drafter externo | **No requiere** — cero memoria extra |
| Sampling | Rejection sampling exacto (funciona a temp>0) |
| Speedup | **2.04-2.24×** sobre autoregresivo sin MTP |
| Modelos compatibles | Qwen 3.6, Gemma 4 (MTP depth configurable 2-7+) |
| Runtime | MLX forkeado con kernels Metal custom |
| API | OpenAI + Anthropic compatibles |

**Benchmarks (Lightning MLX — fusión de Rapid-MLX + MTPLX):**

| Modelo | mlx-lm | oMLX | Rapid MLX | **Lightning MLX** |
|---|---|---|---|---|
| Qwen3.6-27B | 29.80 tok/s | 31.80 tok/s | 32.37 tok/s | **70.35 tok/s** |
| Qwen3.6-35B MoE | 110.37 | 114.59 | 106.00 | **226.01 tok/s** |

**⚠️ Limitación:** Corre sobre MLX → sin Flash Attention real.
A >4K contexto la velocidad se desploma. Ideal solo para prompts cortos (<2K).

### 5.2 DDTree — Árbol de Draft

**Referencia:** `github.com/jroth1111/ddtree-mlx` — primer port MLX con kernels Metal custom.

| Propiedad | Valor |
|---|---|
| Mecanismo | Árbol de draft (best-first heap) en vez de secuencia lineal |
| Speedup vs DFlash | **+10-15%** en código estructurado |
| Speedup vs AR | **~1.5×** |
| Paper | arXiv:2604.12989 — Ringel & Romano |

### 5.3 Gemma 4 MTP — 3× de speedup nativo

Google integró MTP heads nativas en Gemma 4. Benchmarks reales:

| Modelo | Sin MTP | Con MTP | Speedup |
|---|---|---|---|
| **Gemma 4 E2B** (2B) | ~27 tok/s | **~81 tok/s** | **3×** |
| **Gemma 4 E4B** (4B) | ~17 tok/s | **~52 tok/s** | **3×** |

Compatible con MLX (PR #1112) y vLLM (PR #41745).

---

## 6. Estrategias MoE para RAM Limitada

### 6.1 Expert Offloading con `--n-cpu-moe`

**Config para 16 GB:**
```bash
llama-server -m qwen3.6-35b-a3b-q4_k_m.gguf \
  --n-gpu-layers -1 \
  --n-cpu-moe 20 \   # 20 de 28 expertos en CPU
  --flash-attn 1      # Atención siempre en GPU
```

| Componente | GPU | CPU | Nota |
|---|---|---|---|
| Atención | ✅ siempre | ❌ | Crítico para latencia |
| Router | ✅ | ❌ | Define ruta por token |
| Expertos activos (2-4/28) | ✅ | ❌ | Se cargan según ruteo |
| Expertos fríos (24-26/28) | ❌ | ✅ | 75% del modelo en CPU |

**En M1 (memoria unificada):** No hay penalidad PCIe. CPU y GPU acceden
a la misma RAM. El overhead de "offloading" es mínimo comparado con GPU discreta.

### 6.2 CRAFT Lab — Cloud-Grade SLOs (OSDI 2026)

Paper de Tsinghua University presentado en USENIX OSDI 2026:
- Stream-Loading Prefill (SLP): 1,200 tok/s → 32K prompts en <30s
- Distributed SLP: 1,800 tok/s en dual RTX 5090
- AVX-512 FP8 GEMV: 4-5× menor latencia CPU
- CPU INT4 DeepSeek-V3: 28 tok/s en CPU sola

### 6.3 vLLM Feature Request: `--moe-gpu-prefetch` (#41447)

GPU expert slot mapping: N slots físicos en GPU, mapeo dinámico slot→expert_id,
evicción LRU/frequency-based. Hit → directo; Miss → load desde CPU.

---

## 7. Motores TTS para Apple Silicon

| # | Engine | Runtime | Aceleración | Streaming | Español | Puerto |
|---|---|---|---|---|---|---|
| **01** | **TTSKit (Argmax)** | Swift/CoreML | **ANE** | ✅ | ✅ | 5010 |
| **02** | **Qwen3-TTS MLX** | Python/MLX | **Metal GPU** | ✅ | ✅ | 5011 |
| **03** | **Py-Qwen3-TTS-CPP** | Python/C++ GGML | Metal | ❌ | ✅ | 5012 |
| **04** | **Orpheus-FastAPI** | Python/llama.cpp + SNAC | GGUF | ❌ | ✅ | 5013 |
| **05** | **Kokoro** | Python/ONNX | CPU | ❌ | ✅ | 5014 |
| **06** | **Voicebox** | TypeScript/MLX | Metal | ❌ | ? | 5015 |

### Recomendación para M1 16GB

| Prioridad | Engine | Razón |
|---|---|---|
| 🥇 | **TTSKit (Argmax)** | ANE → GPU libre para LLM, más rápido, streaming |
| 🥈 | **Qwen3-TTS MLX** | Mejor calidad, voice cloning (usa GPU) |
| 🥉 | **Kokoro** | Línea base probada, 82M params, liviano |

---

## 8. Ecosistema MCP para Agentes Locales

### 8.1 mcp-x-mac-seed — Auto-descubrimiento de 388 tools

**Referencia:** `github.com/reverendish/mcp-x-mac-seed` — Swift 6.3, MIT

388 tools auto-descubiertas en ~50 apps, ~2 segundos. 8 primitivas:
AppleScript, Accessibility, AppIntents, Screen Context, SQLite + Embeddings,
Semantic Search, Tool Table + Repair History, Execution Engine. Self-healing.

### 8.2 AppleMCP — Datos nativos de macOS

Acceso local seguro a: Mail, Calendar, Contacts, Notes, Reminders, Photos.
Sin cloud, sin sync, sin salida de datos.

### 8.3 Deckard — Proxy MCP con Seguridad

ACL default-deny, redacción outbound (API keys, tokens 2FA), injection tagging, audit log.

### 8.4 Ollama-MCP-Orchestrator

Orquestador Python que conecta Ollama con MCP servers. Auto-detecta tools instaladas.

### 8.5 Agent Orchestrator

Supervisa runs de Codex, Claude, Cursor, OpenCode desde un daemon local.

---

## 9. Modelos Recomendados por Caso de Uso

### Chat General / Tool Calling

| Modelo | Params | Contexto | RAM total | tok/s |
|---|---|---|---|---|
| **Qwen3.5-9B-GLM5.1-Distill** | 9B | 256K | ~8 GB | **34.6** |
| **Ministral-3-8B** | 8B | 128K | ~10 GB | **40.5** |
| **Qwen2.5-7B-1M-Thinking** | 7B | 1M | ~9 GB | **44.9** |

### Máxima Compresión (múltiples modelos simultáneos)

| Modelo | Formato | Tamaño | RAM | tok/s |
|---|---|---|---|---|
| **Falcon3-7B** | STQ1_0 (1.3125-bit) | **1.3 GB** | ~4 GB | 25-30 |
| **Bonsai-8B** | Q1_0_g128 (1-bit) | **1.15 GB** | ~3 GB | 18-22 |
| **Qwen3.5-9B** | planar3 simétrico | 5.0 GB + 0.78 GB KV | ~8 GB | 25.8 |

### MoE

| Modelo | Total | Activo | RAM | Nota |
|---|---|---|---|---|
| **Qwen3.6-35B-A3B** | 35B | 3B | ~14 GB | Justo en 16 GB con n-cpu-moe |

### RAG / Contexto Largo

| Modelo | Contexto | KV Quant | RAM KV |
|---|---|---|---|
| Qwen2.5-7B-1M | **1M** | q4_0 | 1.75 GB |
| Qwen3.5-9B | 256K | planar3 | 0.78 GB |

---

## 10. Pipeline Recomendado para M1 16GB

### Arquitectura en Capas

```
┌──────────────────────────────────────────────────────────┐
│                     APLICACIÓN                            │
│  ┌────────────────────────────────────────────────────┐  │
│  │              MCP Agent Orchestrator                 │  │
│  │  (Ollama-MCP-Orchestrator + mcp-x-mac-seed)        │  │
│  │  388 tools auto-descubiertas                        │  │
│  └────────────────────┬───────────────────────────────┘  │
│                        │                                  │
│  ┌─────────────────────┴──────────────────────────────┐  │
│  │            ROUTER (CoreML ANE)                      │  │
│  │  Qwen3.5-0.8B @ 48 tok/s — 1.2 GB ANE — <5ms      │  │
│  │  Clasifica: chat / código / RAG / tools / imagen    │  │
│  └──┬──────────┬──────────┬──────────┬───────────────┘  │
│     │          │          │          │                   │
│     ▼          ▼          ▼          ▼                   │
│  ┌──────┐ ┌────────┐ ┌────────┐ ┌──────────┐           │
│  │CHAT  │ │CÓDIGO  │ │  RAG   │ │  TOOLS   │           │
│  │llama │ │llama   │ │llama   │ │llama.cpp │           │
│  │.cpp  │ │.cpp    │ │.cpp    │ │          │           │
│  │9B    │ │7B-1M   │ │9B      │ │7B-1M     │           │
│  │Q4_K_S│ │Q4_K_M  │ │Q4_K_S  │ │Q4_K_M    │           │
│  │planar│ │planar3 │ │planar3 │ │planar3   │           │
│  └──┬───┘ └───┬────┘ └───┬────┘ └─────┬────┘           │
│     │         │          │            │                  │
│     └─────────┴──────────┴────────────┘                  │
│                        │                                  │
│  ┌─────────────────────┴──────────────────────────────┐  │
│  │            TTS (Apple ANE — GPU libre)              │  │
│  │  TTSKit Argmax — streaming, español, 0 GB GPU      │  │
│  └────────────────────────────────────────────────────┘  │
│                        │                                  │
│  ┌─────────────────────┴──────────────────────────────┐  │
│  │              MEMORIA PERSISTENTE                     │  │
│  │  Qdrant (vector DB, ~200 MB)                       │  │
│  │  Short-term memory (SQLite, ~50 MB)                │  │
│  │  Document Index (MCP-realtime-tech-docs)           │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### Asignación de RAM

| Componente | RAM | Ubicación |
|---|---|---|
| macOS + sistema | ~3 GB | RAM unificada |
| Router CoreML (Qwen3.5-0.8B) | 1.2 GB | **ANE** (no toca RAM) |
| LLM principal (Qwen3.5-9B Q4_K_S) | 5.0 GB | RAM unificada |
| KV cache (planar3 simétrico, 256K) | 0.78 GB | RAM unificada |
| Subagente ternario (Falcon3-3B STQ1_0) | 1.96 GB | RAM unificada |
| TTS (TTSKit CoreML) | 0 GB | **ANE** (no toca RAM) |
| Qdrant (vector DB) | 0.2 GB | RAM unificada |
| Ollama daemon + overhead | 0.5 GB | RAM unificada |
| **TOTAL** | **~12 GB** | ✅ Cabe en 16 GB |

---

## 11. VPS Research Stack — Herramientas de Investigación

> Stack de 4 herramientas auto-hospedadas en VPS para investigación local de LLMs.

### 11.1 Maestro — Orquestador de Investigación Multi-agente

**Referencia:** `github.com/murtaza-nasir/maestro`

| Propiedad | Valor |
|---|---|
| Propósito | Investigación compleja multi-agente con pipelines estructurados |
| RAM mínima | 16 GB (32+ GB recomendado) |
| GPU | NVIDIA 8GB+ VRAM recomendada |
| Disco | 30 GB+ |
| Despliegue | Docker + Docker Compose |
| LLMs | Ollama, OpenAI, Anthropic, HuggingFace |
| Interfaces | CLI, Web, Telegram, Slack |

**Arquitectura:** Agentes especializados colaboran mediante pipelines estructurados.
Memoria persistente, routing de tareas, herramientas integradas.
Soporta modelos locales hasta 15B Q4_K_M en 14-16 GB.

### 11.2 Perplexica — Búsqueda AI Auto-hospedada

**Referencia:** `github.com/ItzCrazyKns/Perplexica`

| Propiedad | Valor |
|---|---|
| Propósito | Alternativa local a Perplexity AI con citas verificables |
| RAM | 2 GB (básico) / 8 GB+ (con LLM local) |
| Backend búsqueda | SearXNG (meta-buscador) |
| LLM | Ollama, OpenAI, Anthropic |
| Característica clave | Resúmenes AI con citas, routing multimodal |

**Stack completo:** SearXNG (backend) → Perplexica (capa AI) → Ollama (LLM local).

### 11.3 GPT-Researcher — Agente de Investigación Autónomo

**Referencia:** `github.com/assafelovic/gpt-researcher`

| Propiedad | Valor |
|---|---|
| Propósito | Agente autónomo que genera informes con citas |
| RAM | 4-8 GB (depende del LLM) |
| LLMs | Ollama, OpenAI, Anthropic, Google, Azure |
| Formato salida | Informes estructurados con citas, web + docs locales |
| Despliegue | Docker, Python, Docker Compose |

### 11.4 SearXNG — Meta-buscador Privado

**Referencia:** `github.com/searxng/searxng`

| Propiedad | Valor |
|---|---|
| Propósito | Meta-búsqueda privada (agrega Google, Bing, DuckDuckGo, etc.) |
| RAM | ~2 GB |
| CPU | Bajo |

### 11.5 Integración del Stack VPS

| Componente | RAM | CPU |
|---|---|---|
| SearXNG | ~2 GB | Bajo |
| Perplexica | ~4 GB | Medio |
| GPT-Researcher | ~4 GB | Medio-Alto |
| Maestro + Ollama (7B) | ~7 GB | Alto (GPU si disponible) |
| **Total** | **~17 GB** | — |

---

## 12. MCP Ecosystem Local — Proyectos Propios y Afines

### 12.1 MCP-agent-memory (Ruben-Alvarez-Dev) — v2.0, 53 MCP Tools

**Referencia:** `github.com/Ruben-Alvarez-Dev/MCP-agent-memory`

**Arquitectura — 6 capas de memoria:**

```
L0 RAW          → Append-only event lake (JSONL)
L1 WORKING      → Steps, facts, hot dialogue (Qdrant)
L2 EPISODIC     → Grouped events, incidents (Qdrant + SQLite)
L3 SEMANTIC     → Decisions, entities, patterns (Qdrant + filesystem)
L4 CONSOLIDATED → Narratives, deep summaries (Qdrant)
L5 SELECTIVE    → Context routing and assembly
Lx REASONING    → Sequential thinking, plans, proposals
```

**53 MCP tools:**

| Módulo | Tools | Propósito |
|---|---|---|
| L0_capture | 4 | Ingesta en tiempo real |
| L0_to_L4_consolidation | 7 | Consolidación + dream cycle |
| L5_routing | 6 | Recuperación inteligente de contexto |
| L2_conversations | 5 | Persistencia de hilos |
| L3_facts | 5 | Memoria semántica CRUD |
| L3_decisions | 11 | Vault + integración Obsidian |
| Lx_reasoning | 10 | Razonamiento secuencial + planes |
| Health | 1 | Estado del sistema |

**Tecnologías y consumo:**

| Componente | Tecnología | RAM |
|---|---|---|
| Vector DB | Qdrant | ~200 MB |
| Embeddings | BGE-M3 (1024d) via llama.cpp | ~600 MB |
| LLM | qwen2.5-7b-instruct | ~4.5 GB |
| Almacenamiento | SQLite + FTS5 + Filesystem | ~50 MB |
| **Total** | | **~5.4 GB** |

**Características clave:** Backpack Orchestrator (auto-triggers), bilingual vault ES/EN,
dream cycle nocturno, HTTP sidecar (puerto 8890), zero-config.

### 12.2 Palantir (Ruben-Alvarez-Dev) — Gestor de Ecosistema MCP

**Referencia:** `github.com/Ruben-Alvarez-Dev/Palantir` — Go, zero dependencias

| Propiedad | Valor |
|---|---|
| Runtime | Go 1.25+ (binario único) |
| Propósito | Descubrir, instalar y gestionar servidores MCP |
| Editores | Cursor, Windsurf, VS Code, Claude Desktop, Zed, Trae, PearAI |
| Funcionalidades | Scan, list, install, service (launchd/systemd), status, logs |
| UI | TUI (bubbletea + lipgloss) + CLI |
| DB interna | SQLite |

### 12.3 MCP Memory Servers Relacionados

| Proyecto | Descripción | Almacenamiento |
|---|---|---|
| **agent-knowledge** (yucx-go) | Knowledge graph + BM25 + RRF | SQLite + YAML |
| **GraphMem MCP** (Sathvik-1007) | Grafos persistentes multi-hop | Graph + vector |
| **MnemonAI** (rondilley) | Memoria ACID tiered | LMDB + SQLite |
| **neuromcp** (AdelElo13) | Knowledge base Markdown + Git | Markdown + Git |
| **local-rag-mcp** (overlorde) | ChromaDB + llama.cpp | ChromaDB |
| **agent-memory-mcp** (ipiton) | Memoria persistente coding agents | SQLite + vector |

---

## 13. Nuevos Modelos y Benchmarks (Mayo 2026)

### 13.1 Gemma 4 con MTP Speculative Decoding

| Modelo | Params | Sin MTP | Con MTP | Speedup | RAM (4-bit) |
|---|---|---|---|---|---|
| **Gemma 4 E2B** | 2B | ~27 tok/s | **~81 tok/s** | **3×** | ~2 GB |
| **Gemma 4 E4B** | 4B | ~17 tok/s | **~52 tok/s** | **3×** | ~3 GB |
| Gemma 4 26B | 26B | — | ~85 tok/s (M5) | 2-3× | ~14 GB |

**Para M1 16GB:** Gemma 4 E2B (2B) en 4-bit cabe con ~2 GB y corre a 81 tok/s.
3× speedup real con MTP nativo — sin drafter externo.

### 13.2 Mistral Small 4 (119B MoE)

| Propiedad | Valor |
|---|---|
| Parámetros totales | 119B (MoE) |
| Activos por token | ~12B |
| Contexto | 256K |
| Cuantización mínima | Q4_K_M (~40 GB) |
| **¿Cabe en M1 16GB?** | **❌ No** — inviable incluso con offloading |

### 13.3 Tabla Comparativa de Modelos Recientes

| Modelo | Params | Contexto | RAM (4-bit) | tok/s (M1 Max) | ¿Cabe en 16GB? |
|---|---|---|---|---|---|
| **Gemma 4 E2B** | 2B | 32K | ~2 GB | **81** | ✅✅ Sobra |
| **Gemma 4 E4B** | 4B | 32K | ~3 GB | **52** | ✅✅ Sobra |
| **Qwen3.5-9B** | 9B | 256K | ~5 GB | **34.6** | ✅ |
| **Qwen2.5-7B-1M** | 7B | 1M | ~4.2 GB | **44.9** | ✅ |
| **Ministral-3-8B** | 8B | 128K | ~4.8 GB | **40.5** | ✅ |
| Mistral Small 4 | 119B | 256K | ~40 GB | — | ❌ |

### 13.4 Apple Silicon AI Calculator

**Referencia:** `localaimaster.com/tools/apple-silicon-ai-calculator`

Fórmula subyacente:
```
RAM_modelo = params × bits_per_weight / 8
RAM_KV_cache = n_layers × n_kv_heads × head_dim × 2 × tokens × bytes
RAM_total = RAM_modelo + RAM_KV_cache + overhead (~1.5 GB)
tok/s ≈ memory_bandwidth / (params × bytes_per_weight)
```

---

## 14. Referencias y Fuentes

### Papers

| Paper | Publicación | Enlace |
|---|---|---|
| Sherry: 1.25-Bit Ternary Quantization | ACL 2026 | `arxiv.org/abs/2601.07892` |
| CAT-Q: Cost-efficient Ternary Quantization | ICML 2026 | `icml.cc/virtual/2026/poster/65816` |
| Accelerating Speculative Decoding with DDTree | — | `arxiv.org/abs/2604.12989` |
| RotorQuant: Clifford Algebra KV Cache Compression | 2026 | `docs/research/sources/rotorquant.pdf` |
| Cloud-Grade SLOs for Local MoE Inference | OSDI 2026 | `craft.cs.tsinghua.edu.cn` |

### Repositorios — Investigación General

| Proyecto | Enlace |
|---|---|
| MTPLX — Native MTP Speculative Decoding | `github.com/youssofal/MTPLX` |
| Lightning MLX — Rapid-MLX + MTPLX | `github.com/samuelfaj/lightning-mlx` |
| DDTree-mlx — Tree speculative decoding | `github.com/jroth1111/ddtree-mlx` |
| ATLAS-TQ1.0 — CPU ternary inference | `github.com/xxxn3m3s1sxxx/ATLAS-TQ1_0` |
| OxiBonsai — Pure Rust 1-bit inference | `kitasanio.medium.com` |
| mlx-onecomp — GPTQ/RTN for MLX | `github.com/smalltomatowater-boop/mlx-onecomp` |
| TurboQuant+ — Metal TurboFlash | `github.com/fhnmor21/llama-cpp-turboquant` |
| mcp-x-mac-seed — 388 tools macOS | `github.com/reverendish/mcp-x-mac-seed` |
| AppleMCP — Native macOS MCP | `github.com/godmodeai2025/applemcp` |
| Deckard — Security MCP proxy | `github.com/lapidakis/Deckard` |
| Maestro — Multi-agent orchestrator | `github.com/murtaza-nasir/maestro` |
| Perplexica — Local AI search | `github.com/ItzCrazyKns/Perplexica` |
| GPT-Researcher — Autonomous research | `github.com/assafelovic/gpt-researcher` |

### Repositorios — Ruben-Alvarez-Dev

| Proyecto | Descripción | Tecnología |
|---|---|---|
| **MCP-agent-memory** | Memoria multi-capa (L0-L5+Lx), 53 tools, bilingual vault | Python, Qdrant, SQLite |
| **Palantir** | Gestor de ecosistema MCP — scan, install, service | Go (bubbletea) |
| **CLI-agent-memory** | CLI para memoria de agente | Python |
| **MCP-realtime-tech-docs** | Documentación técnica vía MCP | Python |
| **PROJECT-RAMIRO** | Plataforma multimodal con TIER system | TypeScript, Tauri |
| **Jart-OS** | Sistema operativo AI | Python |

### PRs (Mayo 2026)

| PR | Descripción | Estado |
|---|---|---|
| llama.cpp #22836 | STQ1_0 ternary + ARM NEON | ✅ Mergeado |
| llama.cpp #23332 | STQ1_0 CUDA dequant | ✅ Mergeado |
| vLLM #41745 | Gemma 4 MTP support | ✅ Mergeado |
| mlx-vlm #1112 | Gemma 4 MTP drafter | 🔄 Open |

### Guías y Artículos

| Título | Fuente |
|---|---|
| MLX vs llama.cpp on M1 Max — Honest Benchmark | `dev.to/sleepyquant` |
| MTPLX Is 2.04× Faster Than MLX | `xhinker.medium.com` |
| Qwen3.6 MoE on 16 GB: --n-cpu-moe Fixes OOM | `craftrigs.com` |
| Gemma 4 E2B vs E4B: 81 vs 52 tok/s | `ai-muninn.com` |
| Perplexica vs SearXNG: Self-Hosted AI Search | `zenvanriel.com` |
| Apple Silicon AI Calculator | `localaimaster.com` |
| Fine-Tuning Gemma 4 on Apple Silicon | `flowhunt.io` |

---

*Documento generado el 2026-05-24 (v2). Investigación basada en análisis de repositorios
locales (INFERENCE-investigation, CAAL, PROJECT-RAMIRO, QWEN-3-TTS-TESTING) + búsqueda web
(Brave, Kagi, Tavily, Serper, Jina, Exa) + verificación de código fuente
(GitHub — Ruben-Alvarez-Dev y comunidad). API keys registradas para uso futuro.*

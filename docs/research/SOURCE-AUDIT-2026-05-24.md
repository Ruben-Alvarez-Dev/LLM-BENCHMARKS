# Auditoría de Fuentes Externas — Investigación 2026-05-24

> **Propósito:** Trazabilidad completa de cada fuente externa (papers, arXiv,
> conferencias, repos comunitarios, guías técnicas) consultada durante la
> investigación. Sin fuentes locales.
>
> **Motores de búsqueda:** Brave Search, Kagi, Tavily, Serper, Jina, Exa,
> Linkup, Firecraw/Klavis
>
> **Total de queries:** ~40 en 5 tandas

---

## Tanda 1 — Stack de Inferencia (5 queries)

### 1.1 Búsqueda
**Query:** `latest LLM inference optimization Apple Silicon Metal 2026 beyond llama.cpp`
**Resultado:** MTPLX spec decoding. 544★. Qwen3.6-27B 2.24x.
**Fuente:** github.com/youssofal/MTPLX

### 1.2 Búsqueda
**Query:** `microscopic quantization 1.58 bit ternary BitNet bfloat16 KV cache 2026`
**Resultado:** CAT-Q ICML 2026 poster. Ternarización post-training con 512 muestras.
**Fuente:** icml.cc/virtual/2026/poster/65816

### 1.3 Búsqueda
**Query:** `speculative decoding small draft model Apple Silicon M1 16GB 2026`
**Resultado:** MTPLX + DFlash + DDTree benchmarks.
**Fuentes:** github.com/jroth1111/ddtree-mlx, github.com/samuelfaj/lightning-mlx

### 1.4 Búsqueda
**Query:** `mixture of experts on-device 16GB RAM efficient inference 2026`
**Resultado:** CRAFT Lab OSDI 2026. Tsinghua University.
**Fuente:** craft.cs.tsinghua.edu.cn

### 1.5 Búsqueda
**Query:** `hybrid SSM transformer Mamba2 GatedDeltaNet RWKV Apple Silicon benchmark 2026`
**Resultado:** Qwen3.5-9B arquitectura híbrida.
**Fuente:** — (resultado contextual)

---

## Tanda 2 — Profundización (5 queries)

### 2.1 Búsqueda
**Query:** `MTPLX native multi-token prediction speculative decoding Apple Silicon M1 2.24x faster 2026`
**Resultado:** 2.04-2.24x. Custom Metal: innovation-tape GDN, GraphBank.
**Fuentes:** github.com/youssofal/MTPLX, theneuralfeed.com, xhinker.medium.com

### 2.2 Búsqueda
**Query:** `CAT-Q ternary quantization ICML 2026 LLM cost-efficient 1.58 bit`
**Resultado:** Paper: 512 calibración, 100,000x menos tokens que BitNet. Authors: Shigeng Wang, Chao Li et al.
**Fuente:** icml.cc/virtual/2026/poster/65816

### 2.3 Búsqueda
**Query:** `CPU-GPU hybrid mixture of experts inference on-device CRAFT Lab 2026 16GB`
**Resultado:** Paper OSDI 2026. SLP 1,200 tok/s. AVX-512 FP8 GEMV.
**Fuente:** craft.cs.tsinghua.edu.cn/publication

### 2.4 Búsqueda
**Query:** `ddtree-mlx decision tree inference Apple Silicon MLX 2026`
**Resultado:** +10-15% sobre DFlash. +37.8% en vLLM. Paper: arXiv:2604.12989, Ringel & Romano.
**Fuente:** github.com/jroth1111/ddtree-mlx

### 2.5 Búsqueda
**Query:** `axolotl finetuning ternary LLMs HuggingFace 2026`
**Resultado:** Guía community. Axolotl team + Younes Belkada (FalconLLM).
**Fuente:** huggingface.co/blog/axolotl-ai-co

---

## Tanda 3 — Búsqueda de v-torque / TORQ (12 queries)

### 3.1-3.11 Búsquedas exploratorias
**Queries:** Variaciones de "v-torque", "vector torque", "V torque" en contexto de
cuantización, rotación, KV cache, transformers, LLM.
**Resultado progresivo:** TurboQuant → rotaciones → **TORQ encontrado** en query 3.9.
**Confirmación:** Query 3.11: ReSpinQuant, ConQuR, TORQ paper completo.

### 3.12 Fetch de paper completo
**URL:** `https://arxiv.org/html/2605.19561v1`
**Resultado:** Paper completo de TORQ. Autores: afiliación no especificada en el HTML.
- Dos niveles de rotación ortogonal
- Macro: Schur-Horn theorem, Givens rotations (O(B²))
- Micro: Maximum entropy codebook alignment
- Resultados: Qwen3-32B PPL 8.43, accuracy 38%→73.63%
- 128 muestras calibración, training-free
**Fuente:** arxiv.org/abs/2605.19561

---

## Tanda 4 — Expansión: Paging, NVMe, Concurrencia (4 queries)

### 4.1 Búsqueda
**Query:** `TORQ Two-level Orthogonal Rotation MXFP4 quantization implementation code GitHub open source 2026`
**Resultados adicionales encontrados:**
- **OSCAR** (FutureMLS-Lab, GitHub 8★, 2026-05-19): Offline Spectral Covariance-Aware Rotation para KV cache 2-bit
- **Block Rotation is All You Need for MXFP4** — ICML 2026 poster
- **DuQuant++** — arXiv:2604.17789, CASIA/NJU/THU/ZJU/Harvard/CityU
- Intel Auto-Round: QuaRot/SpinQuant rotation (PR #1797)
- NVIDIA Model-Optimizer: MXFP4→NVFP4 cast (PR #1372)
**Fuentes:** arxiv.org/html/2605.17757, github.com/FutureMLS-Lab/OSCAR, icml.cc/virtual/2026/poster/62818, arxiv.org/abs/2604.17789, github.com/intel/auto-round/pull/1797, github.com/NVIDIA/Model-Optimizer/commit/50706d1

### 4.2 Búsqueda
**Query:** `KV cache paging swap NVMe thunderbolt llama.cpp PagedAttention context infinite long session 2026`
**Resultados:**
- **PR #22569 llama.cpp**: Paged KV cache + scheduler + continuous batching (draft, +4029 líneas). NVIDIA A10G: 247 secuencias concurrentes, 2.5x throughput.
- **PR #22929 llama.cpp**: Context checkpoints para agentes. Extrae message_spans, crea checkpoint. Probado con Pi, GPT, Qwen3.6 27B, Gemma 4 31B.
- **vLLM x Mooncake**: Agentic workloads, 94.2% cache hit rate, 131:1 input/output ratio.
- **KV Cache & PagedAttention Guide 2026**: localaimaster.com
- **PagedAttention Internals**: sukruyusufkaya.com
- **KV Cache Offloading**: backend.ai
**Fuentes:** github.com/ggml-org/llama.cpp/pull/22569, github.com/ggml-org/llama.cpp/pull/22929, vllm.ai/blog/2026-05-06-mooncake-store, localaimaster.com/blog/kv-cache-paged-attention-guide, sukruyusufkaya.com, backend.ai/blog

### 4.3 Búsqueda
**Query:** `continuous batching multiple agents single model concurrent slots llama.cpp vLLM 2026`
**Resultados:**
- **llama.cpp Agent Architecture**: markaicode.com. Redis Streams, tiered cache, 500 agent steps/s en 4×T4.
- **vLLM PR #41685**: Pipeline parallelism optimizado para contexto largo.
- **Mooncake blog**: Agentic workloads, 3.8x throughput, 46x TTFT reduction.
- **Ollama vs llama.cpp vs vLLM 2026**: dev.to/thurmon_demich
**Fuentes:** markaicode.com, github.com/vllm-project/vllm/issues/41685, vllm.ai/blog, dev.to

### 4.4 Búsqueda
**Query:** `NVMe external Thunderbolt LLM inference cache swap context memory hierarchy Apple Silicon 2026`
**Resultados:**
- **Flash-MoE** (starlog.is): 397B en MacBook 48GB. mmap, page cache del SO, 71% hit rate, 17.5 GB/s NVMe.
  **Paper académico**: arXiv:2601.17063, "FlashMoE: Reducing SSD I/O Bottlenecks via ML-Based Cache Replacement".
  Autores: Byeongju Kim, Jungwan Lee, Donghyeon Han, Hoi-Jun Yoo, Sangyeob Kim (KAIST/affiliación coreana).
  ML-based cache replacement, 51% mejora cache hit, 2.6x speedup vs LRU.
- **MoE-MADV** (daystar7777, GitHub): DeepSeek V4 284B en M1 Max 64GB. +25.4% con MADV_WILLNEED. 97.6% I/O-active.
- **Spike** (matthewworner, GitHub): Weight block pager. Markov chain predictor. 91% prob capa N→N+1. Apple Silicon.
- **Budget Guide 64GB M1 Max**: dev.to/sleepyquant. Desglose RAM: sistema 18.6 GB, ML 38.7 GB, buffer 6.7 GB.
- **DGX Spark + Mac Studio**: allthings.how. Disaggregated prefill/decode con EXO. 2.8x speedup Llama-3.1 8B.
**Fuentes:** arxiv.org/abs/2601.17063, starlog.is, github.com/daystar7777/MoE-MADV, github.com/matthewworner/spike, dev.to/sleepyquant, allthings.how

---

## Tanda 5 — Papers Universitarios Adicionales (4 queries)

### 5.1 Búsqueda
**Query:** `arxiv.org SpecMoE speculative decoding mixture of experts memory bandwidth 2604.10152`
**Resultado:** "SpecMoE: A Fast and Efficient Mixture-of-Experts Inference via Self-Assisted Speculative Decoding".
Hasta 4.30x faster. Training-free. Self-assisted draft. Reduce expert loads y memory transfers.
**Fuente:** arxiv.org/abs/2604.10152

### 5.2 Búsqueda
**Query:** `arxiv.org DuQuant++ fine-grained rotation MXFP4 quantization 2604.17789`
**Resultado:** Autores: Haokun Lin, Xinle Jia, Haobo Xu, Bingchen Yao, Xianglong Guo, Yichen Wu, Zhichao Lu, Ying Wei, Qingfu Zhang, Zhenan Sun.
Afiliaciones: CASIA, NJU, THU, ZJU, Harvard, CityU.
**Fuente:** arxiv.org/abs/2604.17789, github.com/Hsu1023/DuQuant-v2

### 5.3 Búsqueda
**Query:** `arxiv.org FluxMoE expert paging virtualized tensor GPU offloading 2604.02715`
**Resultado:** "FluxMoE: Decoupling Expert Residency for High-Performance MoE Serving".
PagedTensor, tensor virtualization, budget-aware residency planner. 3.0x throughput vs vLLM.
Implementado sobre vLLM.
**Fuente:** arxiv.org/abs/2604.02715

### 5.4 Búsqueda
**Query:** `arxiv.org Sherry 1.25 bit ternary quantization ACL 2026 structured sparsity 2601.07892`
**Resultado:** "Sherry: Hardware-Efficient 1.25-Bit Ternary Quantization via Fine-grained Sparsification".
3:4 structured sparsity. 1.3125 bpw. Tencent/AngelSlim.
Aceptado en ACL 2026.
**Fuente:** arxiv.org/abs/2601.07892, github.com/Tencent/AngelSlim

### 5.5 Búsqueda
**Query:** `arxiv.org CRAFT Lab cloud-grade SLOs local MoE inference CPU-GPU hybrid OSDI 2026 Tsinghua`
**Resultado:** "Achieving Cloud-Grade SLOs for Local Mixture-of-Experts Inference through CPU–GPU Hybrid Design".
Tsinghua University, CRAFT Lab. OSDI 2026.
**Fuente:** craft.cs.tsinghua.edu.cn/publication

### 5.6 Búsqueda
**Query:** `arxiv.org TurboQuant ICLR 2026 Google KV cache polar quantization Walsh-Hadamard`
**Resultado:** "TurboQuant: Online Vector Quantization with Near-optimal Distortion Rate".
Autores: Amir Zandieh, Majid Daliri, Majid Hadian, Vahab Mirrokni (Google Research).
ICLR 2026.
**Fuente:** arxiv.org/abs/2504.19874, research.google/blog

### 5.7 Búsqueda
**Query:** `arxiv.org Mooncake distributed KV cache prefix sharing agentic workloads`
**Resultado:** "Mooncake: A KVCache-centric Disaggregated Architecture for LLM Serving". arXiv:2407.00079.
FAST '25 (USENIX). Integración con vLLM para agentic workloads.
**Fuente:** arxiv.org/abs/2407.00079, usenix.org, kvcache-ai.github.io/Mooncake

### 5.8 Búsqueda
**Query:** `arxiv.org FlashMoE ML-based cache replacement SSD I/O MoE edge devices 2601.17063`
**Resultado:** "FlashMoE: Reducing SSD I/O Bottlenecks via ML-Based Cache Replacement".
Autores: Byeongju Kim, Jungwan Lee, Donghyeon Han, Hoi-Jun Yoo, Sangyeob Kim (KAIST et al.).
51% cache hit mejora, 2.6x speedup.
**Fuente:** arxiv.org/abs/2601.17063

---

## Resumen de Papers Académicos Identificados

| ID | Paper | Venue | Autores/Afiliación |
|---|---|---|---|
| P1 | TORQ: Two-Level Orthogonal Rotation for MXFP4 | arXiv May 2026 | — |
| P2 | Block Rotation is All You Need for MXFP4 | ICML 2026 | — |
| P3 | CAT-Q: Cost-efficient Ternary Quantization | ICML 2026 | Shigeng Wang, Chao Li et al. |
| P4 | Sherry: 1.25-Bit Ternary Quantization | ACL 2026 | Tencent/AngelSlim |
| P5 | TurboQuant: Online Vector Quantization | ICLR 2026 | Zandieh, Daliri, Hadian, Mirrokni — Google Research |
| P6 | OSCAR: Offline Spectral Covariance Rotation | arXiv May 2026 | FutureMLS-Lab |
| P7 | DuQuant++: Fine-grained Rotation MXFP4 | arXiv Apr 2026 | CASIA, NJU, THU, ZJU, Harvard, CityU |
| P8 | FlashMoE: ML-Based Cache Replacement | arXiv Jan 2026 | Kim, Lee, Han, Yoo, Kim (KAIST et al.) |
| P9 | SpecMoE: Self-Assisted Speculative Decoding | arXiv Apr 2026 | — |
| P10 | FluxMoE: Decoupling Expert Residency | arXiv Apr 2026 | — |
| P11 | Cloud-Grade SLOs for Local MoE (CPU-GPU) | OSDI 2026 | Tsinghua CRAFT Lab |
| P12 | Mooncake: KVCache-centric Architecture | FAST '25 (USENIX) | — |
| P13 | Accelerating Speculative Decoding w/ DDTree | arXiv 2026 | Ringel & Romano |
| P14 | PagedAttention (vLLM) | SOSP '23 | Kwon et al. (Stanford) |

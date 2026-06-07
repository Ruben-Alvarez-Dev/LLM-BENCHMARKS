# ROTORQUANT Turbo Build — llama.cpp para Apple Silicon

> **Fecha:** 2026-06-06
> **Fuente:** johndpope/llama-cpp-turboquant (master, junio 2026)
> **Target:** Apple Silicon M1/M2/M3/M4 (ARM64, Metal 4)
> **Ubicación binario:** `engines/metal/llama-rotorquant`
> **Versión ggml:** 0.9.8 (commit 9c600bc)

## Por qué NO usar el binario Homebrew

El binario `llama.cpp` v9430 de Homebrew NO tiene los kernels turbo3/turbo4 de ROTORQUANT.
Sin estos kernels, la cuantización Q4_K_M y Q4_K_S usa LUTs estándar (2-mag), perdiendo
~15-20% de throughput en Metal.

El binario anterior (`llama-metal`, 12 MB, mayo 2026) fue compilado de una versión
pre-SSM del fork. No sabe cargar modelos Qwen3.5 (error: `missing tensor blk.32.ssm_conv1d.weight`).

## Fuente

```
Repo:   johndpope/llama-cpp-turboquant (GitHub)
Branch: master
URL:    https://github.com/johndpope/llama-cpp-turboquant
Clone:  git clone --depth 1 https://github.com/johndpope/llama-cpp-turboquant.git
```

Este fork incluye:
- Kernels **turbo3** (4-mag LUT) y **turbo4** (8-mag LUT) para cuantización
- Soporte completo para arquitectura **Qwen3.5** (GDN/SSM híbrido)
- Soporte **MoE** (Qwen3.5-MoE, etc.)
- K-quant cache types (q4_0, q8_0, q4_1, q5_0, q5_1, iq4_nl)
- Planar3 KV cache quantization (experimental)
- Asymmetric KV (K y V con tipos distintos)
- Flash Attention en Metal

## Comando de compilación

```bash
cmake .. \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_OSX_ARCHITECTURES=arm64 \
  -DCMAKE_OSX_DEPLOYMENT_TARGET=14.0 \
  \
  `# ── Metal backend (GPU) ──` \
  -DGGML_METAL=ON \
  -DGGML_METAL_EMBED_LIBRARY=ON \
  -DGGML_METAL_NDEBUG=ON \
  \
  `# ── CPU backend ──` \
  -DGGML_CPU=ON \
  -DGGML_CPU_REPACK=ON \
  -DGGML_CPU_ALL_VARIANTS=OFF \
  \
  `# ── Accelerate (Apple BLAS, reemplaza OpenBLAS) ──` \
  -DGGML_ACCELERATE=ON \
  -DGGML_BLAS=OFF \
  \
  `# ── Optimizaciones ──` \
  -DGGML_NATIVE=ON         `# -mcpu=native: detecta dotprod, NEON, etc` \
  -DGGML_LLAMAFILE=ON      `# Llamafile: ejecuta .cpp como scripts` \
  -DGGML_OPENMP=ON         `# Multi-threading via OpenMP` \
  -DGGML_LTO=ON            `# Link-Time Optimization` \
  -DGGML_CCACHE=OFF        `# ccache interfiere con LTO en ARM64` \
  \
  `# ── Backends deshabilitados (no aplican a Apple Silicon) ──` \
  -DGGML_CUDA=OFF -DGGML_HIP=OFF -DGGML_VULKAN=OFF \
  -DGGML_SYCL=OFF -DGGML_MUSA=OFF -DGGML_OPENCL=OFF \
  -DGGML_HEXAGON=OFF -DGGML_WEBGPU=OFF -DGGML_VIRTGPU=OFF \
  -DGGML_RPC=OFF -DGGML_OPENVINO=OFF \
  \
  `# ── No debug ──` \
  -DGGML_METAL_SHADER_DEBUG=OFF \
  -DGGML_SANITIZE_ADDRESS=OFF \
  -DGGML_SANITIZE_THREAD=OFF \
  -DGGML_SANITIZE_UNDEFINED=OFF \
  -DGGML_GPROF=OFF \
  \
  `# ── Solo server + CLI, sin tests ──` \
  -DGGML_BUILD_TESTS=OFF -DGGML_BUILD_EXAMPLES=OFF \
  -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF \
  -DLLAMA_BUILD_SERVER=ON \
  -DLLAMA_OPENSSL=ON

make -j$(sysctl -n hw.ncpu) llama-server llama-cli
```

## Justificación de cada flag

### Obligatorios (sin esto no compila o no funciona)

| Flag | Por qué |
|---|---|
| `GGML_METAL=ON` | Acelera todas las operaciones de matriz en GPU. Sin esto, todo corre en CPU (5-10× más lento). |
| `GGML_METAL_EMBED_LIBRARY=ON` | Empotra los shaders Metal en el binario. Sin esto, necesita archivos `.metal` externos. |
| `GGML_METAL_NDEBUG=ON` | Desactiva aserciones en shaders Metal. Shaders más rápidos (~5% de ganancia). |
| `GGML_CPU=ON` | Backend CPU para tokenización y operaciones que no van a GPU. |
| `GGML_ACCELERATE=ON` | Framework Accelerate de Apple para BLAS en CPU. Más rápido que implementación vanilla. |

### Rendimiento (medible)

| Flag | Por qué | Ganancia estimada |
|---|---|---|
| `GGML_NATIVE=ON` | `-mcpu=native` activa dotprod NEON en M1/M2/M3. | +5-10% en CPU ops |
| `GGML_CPU_REPACK=ON` | Convierte pesos Q4_0 a formato optimizado en runtime. | +10-15% en decode |
| `GGML_LLAMAFILE=ON` | Optimizaciones de llamafile (cosmopolitan) para mejor uso de memoria. | +3-5% |
| `GGML_OPENMP=ON` | Paraleliza el prefill con todos los cores. Sin esto, prefill es single-threaded. | 2-4× en prefill |
| `GGML_LTO=ON` | Link-Time Optimization: inlinea funciones entre unidades de compilación. | +5-10%, binario más chico |

### Deshabilitados (no aplican)

| Flag | Por qué OFF |
|---|---|
| `GGML_CUDA/HIP/VULKAN/SYCL/MUSA/OPENCL` | GPUs no-Apple. M1/M2/M3 usan Metal, no CUDA/Vulkan/etc. |
| `GGML_BLAS=OFF` | Reemplazado por `GGML_ACCELERATE=ON`. Accelerate es más rápido en Apple Silicon. |
| `GGML_HEXAGON/WEBGPU/VIRTGPU/RPC/OPENVINO` | Backends especializados que no aplican a inferencia local en macOS. |
| `GGML_CPU_ALL_VARIANTS=OFF` | Solo necesitamos la variante nativa del CPU. Compilar todas añade minutos sin beneficio. |
| `GGML_CCACHE=OFF` | Interfiere con `GGML_LTO=ON` en ARM64 (símbolos duplicados). |

### Debug deshabilitados

| Flag | Por qué OFF en producción |
|---|---|
| `GGML_METAL_SHADER_DEBUG=OFF` | `-fno-fast-math` en shaders Metal ralentiza ~20%. Solo para debug. |
| `GGML_SANITIZE_*` | Thread/address/undefined sanitizers añaden overhead de runtime. Solo para desarrollo. |
| `GGML_GPROF=OFF` | Profiling con gprof. No necesario en binario de producción. |

### Componentes

| Flag | Por qué |
|---|---|
| `LLAMA_BUILD_SERVER=ON` | Necesitamos `llama-server` para el API REST (llama-swap lo invoca). |
| `LLAMA_BUILD_EXAMPLES=OFF` | No necesitamos `llama-bench`, `llama-perplexity`, etc. en el binario de producción. |
| `LLAMA_BUILD_TESTS=OFF` | Tests unitarios. No se instalan. |
| `LLAMA_OPENSSL=ON` | HTTPS para el servidor. Por ahora usamos HTTP pero tenerlo no cuesta. |

## Resultado

| Métrica | Homebrew v9430 | ROTORQUANT turbo3 |
|---|---|---|
| Tamaño binario server | ~8 MB | **7.0 MB** |
| Tamaño binario CLI | ~6 MB | **5.3 MB** |
| Qwen3.5/SSM | OK | OK |
| Kernel cuantización | estándar (2-mag LUT) | **turbo3 (4-mag LUT)** |
| Gen t/s (QwenPaw heretic 9B Q4_K_M) | 68.4 | 67 (verificado) |

La diferencia de t/s es mínima (68 vs 67) porque el cuello es ancho de banda de RAM
unificada (400 GB/s), no el kernel de cuantización. El turbo3 brilla en modelos más
grandes donde el cómputo de matriz domina sobre la transferencia de pesos.

## ADVERTENCIA — No usar el binario viejo

El binario `engines/metal/llama-metal` (12 MB, 11 mayo 2026) **NO soporta Qwen3.5/SSM**.
Fue compilado de una versión anterior del fork ROTORQUANT sin el backend GDN.
Si intentás cargar cualquier modelo Qwen3.5 o QwenPaw con ese binario, falla con:

```
llama_model_load: error loading model: missing tensor 'blk.32.ssm_conv1d.weight'
```

**Usar siempre `llama-rotorquant` para modelos Qwen3.5+.**

---

*Build documentado por Ramiro, 2026-06-06. Parte del stack TIER-0-METAL/10999-inference-vllm2.*

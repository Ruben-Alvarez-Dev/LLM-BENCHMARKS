# Investigación 2026-06-12 — Inferencia en Ryzen 5 5600G 16GB (máquina de Manu)

> Máquina objetivo: `ryzen-5600g-16gb` (Mac-Pro-de-manu.local, Hackintosh macOS x86_64,
> Zen3 6c/12t, AVX2 sin AVX-512, Vega 7 iGPU, DDR4 dual-channel).
> Registrada en `data/frontier_bench_v2.db` vía `probe --ssh manu-macpro` (2026-06-12).
> Objetivo de Rubén: **≥20 tok/s decode sostenido, Q4, contexto ≥128K, máximo
> tooling + multimodalidad + razonamiento profundo.**
> Método: 5 agentes de búsqueda paralelos (MoE, densos, multimodal, cuantización,
> benchmarks reales) + verificación cruzada. Fuentes al final.

---

## 1. Física del problema (todo lo demás se deriva de aquí)

- Ancho de banda: DDR4-3200 dual = 47,7 GB/s teórico; AIDA64 en 5600G ≈ 50 GB/s
  lectura; **sostenido real para inferencia ≈ 38-42 GB/s** (usamos 40).
- Regla validada (llama.cpp #19480; carteakey.dev escala lineal con BW):
  **decode t/s ≈ 40 GB/s ÷ (GB activos leídos/token + lectura KV)**.
- Consecuencias con Q4 (~0,57 GB por B de parámetros activos):
  - Denso 7-8B → 8-10 t/s (verificado en 5600X/5600H/5700G). **Nunca llega a 20.**
  - Denso 4B → 12-17 t/s (borderline). Denso ≤2-3B → 20-35 t/s.
  - **MoE con ≤1,5B activos → 25-45 t/s. Es LA vía para cumplir el objetivo.**
- El requisito **128K de contexto** mata silenciosamente a los GQA densos clásicos:
  KV q8_0 de un GQA típico (8 kv-heads × hd128 × 36 capas) ≈ 74 KB/token →
  **9,7 GB solo de KV a 128K**. Solo sobreviven arquitecturas híbridas:
  - Atención lineal (Qwen3.5 GDN 3:1: solo ~¼ de capas con KV real → ~2 GB a 128K)
  - Mamba-2 (Granite-4.0-H: estado ~constante, cientos de MB a cualquier ctx)
  - SWA dual-cache (Gemma, GPT-OSS: KV moderado)

## 2. Aclaraciones de nomenclatura (petición de Rubén)

- **"Familia Next"**: Qwen3-Next-80B-A3B y Qwen3-Coder-Next (80B-A3B, 256K, Q4≈48 GB).
  Excelentes, pero **no caben ni de lejos en 16 GB**. No existe "Next N2"/"Next RL"
  como release pública — lo más cercano son las variantes Thinking/RL-tuned de la
  familia. Descartados por RAM, no por calidad.
- **Qwen3.5** (feb 2026): Small densos-híbridos 0.8B/2B/4B/9B multimodales 262K ✓;
  MoE 35B-A3B/122B-A10B (no caben). **Qwen3.6** (abr 2026): 35B-A3B y 27B denso
  (no caben en Q4; el 27B Q2 sí está en el Mini). **Qwen3.7** (may 2026):
  Max/Plus **solo API, sin pesos abiertos** a día de hoy (verificado HF 2026-05-23).
- **"Cuantización Rotor/iso/visión/VK"** → TurboQuant (Google, V-cache 2-3 bit),
  PlanarQuant/IsoQuant (K-cache), compresión KV: son **cuantización de KV-cache,
  no de pesos**; viven en forks (llama-cpp-turbo-planar-iso) sin CI macOS x86.
  Ganan RAM a contexto largo (~6x KV), apenas velocidad single-stream. Ver §5.

## 3. Escenario 1 — Solo RAM/CPU (el real hoy)

Presupuesto: 16 GB − ~3 GB (macOS+server) = **~12-13 GB para pesos+KV+buffers**.

| # | Modelo | Arq | Activos | Q4 pesos | KV@128K | t/s est. | Tool | Visión | Razonam. | Veredicto |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **Qwen3.5-2B** | híbrido GDN, 262K | 2B | 1,8 GB | ~1 GB | **22-30** | ✓✓ (fix mar-26) | ✓ nativa | toggle | **GANADOR: único que cumple TODO** |
| 2 | **Granite-4.0-H-Tiny 7B-A1B** | mamba2+MoE, 128K | ~1B | 4,2 GB | ~0,3 GB | **25-40** | ✓✓ (entrenado para ello) | ✗ | ✗ | El más rápido con calidad 7B; sin visión/razonamiento |
| 3 | **Qwen3.5-4B** | híbrido GDN, 262K | 4B | 2,8 GB | ~2 GB | 12-17 | ✓✓✓ (97,5% mejor de 13 en eval mar-26) | ✓ | toggle | El mejor agente; NO llega a 20 |
| 4 | Ling/Ring-mini-2.0 16B-A1.4B | MoE | 1,4B | 9,9 GB | ¿? | 18-28 (un report: 47-58 en DDR5) | ¿? | ✗ | Ring=reasoner | ctx 128K sin verificar; 0 benchmarks AVX2 |
| 5 | Nemotron-3-Nano-4B | mamba híbrido | 4,3B | 2,6 GB | ~0,4 GB | 12-16 | ✓✓✓ (95%, mejor multi-turno) | ✗ | ✓ control | Mejor agente secuencial; bajo el objetivo |
| 6 | Gemma-4-E2B QAT | MatFormer, 256K | ~2,3B | ~2 GB (Q4_0 QAT) | moderado | 15-21 | ✓ (flaky) | ✓ +audio | ✗ | Borderline; QAT = calidad extra a 4bit |
| — | GPT-OSS-20B MXFP4 | MoE SWA, 131K | 3,6B | 12,1 GB | ~1,6 GB | 15-20 | ✓✓ Harmony | ✗ | ✓✓ effort | **NO CABE a 128K en 16 GB** (14-15 GB + macOS) |
| — | LFM2.5-8B-A1B | conv híbrido | 1,5B | 5,2 GB | — | 25-35 | ✓ (parser bug) | ✗ | ✓ CoT | **EXCLUIDO: ctx 32K < 128K**. El más rápido si se relaja el requisito |
| — | Qwen3-30B-A3B / Qwen3.5-35B-A3B / Gemma-4-26B-A4B | MoE A3B/A4B | 3-4B | 13-22 GB | — | 8-16 | ✓✓✓ | ✓ (3.5/G4) | ✓✓ | No caben en Q4 (solo Q2 con pérdida) y no llegan a 20 |

**Multimodalidad dedicada** (si la visión es prioritaria sobre el chat):
MiniCPM-V-4.6 (1,3B, compresión 16x de tokens visuales) y LFM2.5-VL-1.6B
(~0,7 GB Q4) despachan visión a >20 t/s con encode de imagen en segundos;
Qwen3-VL-2B (256K, ggml-org GGUF) es el equilibrio visión+tools.
Encode de imagen en CPU: ~2-15 s/imagen según resolución (compute-bound).

## 4. Escenario 2 — Solo GPU (Sapphire RX 580 8GB Polaris) — corregido 2026-06-12

CORRECCIÓN: la GPU real no es la iGPU Vega 7 (deshabilitada/no inicializada en
macOS) sino una **Sapphire RX 580 8GB GDDR5 (Polaris 10, ~256 GB/s)**. macOS la
reporta erróneamente como "AMD Radeon RX 570" (device 0x67df es común a ambas;
identificación/spoof típico de Hackintosh), con **Metal 2 activo y dando
pantalla** (verificado por SSH con system_profiler 2026-06-12). Resuelve la duda V1 de
`MANU-DOCKER/rotorquant-analysis/ESTRATEGIA-RX580-macOS.md`: Polaris SÍ levanta
con aceleración en este Tahoe.

Lo que NO cambia (evidencia en ESTRATEGIA-RX580-macOS.md §1-2):

- **llama.cpp Metal en dGPU AMD = salida CORRUPTA silenciosa** (issues #19563,
  #15228: sin memoria unificada, sin simdgroup matmul, pre-Metal3). PROHIBIDO.
- Vía teórica correcta: **Vulkan vía MoltenVK** — sin probar en Polaris-macOS,
  posible tope de ~4 GB VRAM direccionable (V3), y Polaris sin DP4A →
  GEMM Q4/INT8 penalizadas.
- En bandwidth la dGPU es golosa (256 GB/s ≈ 6x la DDR4) → si MoltenVK
  funcionara con salida correcta, un 7-8B Q4 entero en VRAM podría dar
  ~20-40 t/s (techo Linux/Vulkan reportado: 8-25 t/s en 7B). **Es EL
  experimento de mayor valor/riesgo de la máquina** — celda exploratoria
  frontier_bench: comprobar, no suponer; validar (a) salida correcta
  (needles/balizas, no solo t/s), (b) VRAM real direccionable.
- ¿"Red neuronal"? **No hay NPU en ningún sitio**: Polaris no tiene núcleos
  neuronales, el 5600G no tiene XDNA (eso empieza en Ryzen 7040) y un
  Hackintosh no tiene ANE. CoreML aquí ejecuta en CPU + GPU vía MPS — y ese
  es justamente el **único uso seguro y nativo de la RX 580: Apple
  Vision/CoreML para OCR y embeddings de imagen** (confianza alta).

## 5. Escenario 3 — Combinado CPU+iGPU+técnicas (el techo de la máquina)

En macOS la combinación útil NO es CPU+GPU (ver §4), sino **CPU + pila de técnicas**:

1. **ik_llama.cpp** (fork ikawrakow): único backend soportado = CPU AVX2 → ideal
   aquí. AVX2 medido: decode ×1.5-2.4, prefill ×3-6.5 vs mainline con cuants
   IQ*_K. Build macOS x86 sin CI — **compilar y validar es parte del trabajo**
   ("vamos a compilar nosotros para la ocasión"). Trellis IQ_KT = calidad 2-4 bpw
   sin penalti CPU.
2. **Cuantización de pesos**: Q4_0 + repack AVX2 en runtime (sucesor de Q4_0_4_4)
   o IQ4_XS/IQ4_NL; QAT donde exista (Gemma). Evitar IQ2/IQ3 codebook en CPU.
3. **KV**: `-fa on` + `--cache-type-k/v q8_0` (mitad de KV, neutro-positivo en CPU).
   TurboQuant/Planar/Iso (forks) solo si hace falta exprimir contexto >128K.
4. **Especulativo**: draft externo NO (roba bandwidth en 6 cores); sí
   **ngram/prompt-lookup** (gratis en RAM) y **self-speculative/MTP de ik_llama**.
   Ganancia esperada ×1.1-1.4 en cargas repetitivas/agénticas.
5. La iGPU puede quedar para el **encode de visión** si algún día corre Linux
   (prefill ×2 vía Vulkan); bajo macOS, nada.

**Estimación combinada (Qwen3.5-2B + ik_llama IQ4_K + KV q8 + ngram): ~30-45 t/s
decode, prefill ×3-6. Con Granite-H-Tiny: ~35-50 t/s sin visión.**

## 6. Recomendación operativa

- **Recomendado para certificar primero: Qwen3.5-2B** (cumple 20 t/s + 128K +
  visión + tooling + thinking toggle) y **Granite-4.0-H-Tiny** (7B totales/1B
  activos — velocidad máxima con tooling sólido). Contraste: **Qwen3.5-4B**
  como "mejor agente aunque lento" (12-17 t/s).
- **Celda 7-9B (petición de Rubén): Qwen3.5-9B Q4** (5,2 GB ya en el MBP como
  QwenPaw-Flash-9B Q4_K_M, verificado con gguf_reader). Estimación conservadora
  5-8 t/s, PERO: es híbrido GDN con kernels CPU nativos recientes (PR #20334)
  y no existen números post-fix en DDR4 — el dato del M4 (~10 t/s a 120 GB/s)
  parece pre-fix. Hipótesis falsable: el GDN nativo lo acerca a 10-12 t/s en
  el Ryzen, batiendo la regla de bandwidth de los GQA densos. Medir, no suponer.
  Si pasa de 12 t/s, sube a candidato de agente de calidad.
- GGUFs concretos: `unsloth/Qwen3.5-2B-GGUF` (+mmproj-F16), `unsloth/Qwen3.5-4B-GGUF`,
  `ibm-granite/granite-4.0-h-tiny-GGUF` (Q4_K_M 4,23 GB), `ggml-org/Qwen3-VL-2B-Instruct-GGUF`,
  `LiquidAI/LFM2.5-VL-1.6B-GGUF` (visión rápida), `openbmb` MiniCPM-V-4.6 (repo GGUF oficial sin verificar).
- Server: `llama-server --jinja -fa on --cache-type-k q8_0 --cache-type-v q8_0 -t 6`
  (6 hilos físicos, NO 12; SMT perjudica decode bandwidth-bound).
- Todos los t/s de esta tabla son **estimaciones calculadas** ancladas en benchmarks
  de hardware análogo (5600X/5600H/5700G/3950X DDR4): **nadie ha publicado un
  benchmark del 5600G exacto → nuestra medición con FRONTIER BENCH será inédita.**

## 6a-bis. Batería ampliada Ryzen (petición de Rubén) — añadido 2026-06-12

Roster por CATEGORÍAS, 3-4 candidatos por categoría (regla de Rubén: se decide
con métricas y datos, no con prejuicio). Cada candidato ejercita además una
palanca concreta. Serie estricta: un modelo a la vez, pre/post-flight RAM,
borrado antes del siguiente.

**A. Workers ultrarrápidos (≤2,6B) — objetivo >25 t/s:**

| Modelo | GB Q4 | Palanca | Expectativa |
|---|---|---|---|
| Qwen3.5-2B | 1,8 | GDN + visión + thinking toggle | 22-30 t/s |
| BitNet b1.58 2B4T (bitnet.cpp) | 0,4 | ternaria + kernels ene-26 | 30-50 t/s |
| Gemma-4-E2B QAT | ~2 | QAT-Q4_0 + repack + visión/audio | 15-21 t/s |
| LFM2-2.6B | ~1,6 | conv-híbrido puro velocidad | 20-30 t/s |

**B. MoE de pocos activos (la apuesta principal) — objetivo ≥20 t/s con calidad 7-20B:**

| Modelo | GB | Palanca | Expectativa |
|---|---|---|---|
| Granite-4.0-H-Tiny 7B-A1B | 4,2 | mamba2-MoE, KV ~cte a 128K | 25-40 t/s |
| LFM2.5-8B-A1B | 5,2 | conv-MoE + CoT (ctx 32K, fuera de spec 128K: medir igual) | 25-35 t/s |
| Ling/Ring-mini-2.0 16B-A1.4B | 9,9 | MoE A1B grande, 0 benchs AVX2 | 18-28 t/s ¿? |
| GPT-OSS-20B MXFP4 | 12,1 | MXFP4 + effort razonamiento (solo ctx 8K, guardarraíl al límite) | 12-18 t/s |
| ERNIE-4.5-21B-A3B Q3_K_M | 10,3 | A3B que cabe en Q3 | 10-16 t/s |

**C. Agentes densos/híbridos 4B (tooling) — se aceptan 12-17 t/s si el tooling compensa:**

| Modelo | GB Q4 | Palanca | Expectativa |
|---|---|---|---|
| Qwen3.5-4B | 2,8 | mejor tool-calling 2026 (97,5%) | 12-17 t/s |
| Nemotron-3-Nano-4B | 2,6 | mamba denso, mejor multi-turno | 12-16 t/s |
| Jan-nano 4B | ~2,5 | fine-tune MCP/agentic de Qwen3-4B | 12-17 t/s |
| Ministral-3-3B | ~2 | denso clásico con visión 256K (control) | 15-20 t/s |

**D. Calidad 7-9B (techo de la máquina) — Rubén: medir, no descartar:**

| Modelo | GB Q4 | Palanca | Expectativa |
|---|---|---|---|
| Qwen3.5-9B (QwenPaw, ya en MBP) | 5,2 | GDN post-PR#20334 en DDR4 (dato inédito) | 5-12 t/s ¿? |
| Ministral-3-8B-Reasoning | ~5 | razonador denso + visión | 6-8 t/s |
| Falcon-H1R-7B | ~4,5 | reasoner mamba paralelo (batteries.yaml) | 6-9 t/s |
| Granite-4.1-8B | ~4,8 | denso mamba2 abr-26, "iguala al 32B-A9B" | 7-10 t/s |

**E. Visión dedicada — métrica extra: segundos/imagen de encode en CPU:**

| Modelo | GB | Palanca |
|---|---|---|
| Qwen3-VL-2B-Instruct | ~1,5+mmproj | visión+tools equilibrado |
| LFM2.5-VL-1.6B | 0,7 | encode nativo ≤512px (el más barato) |
| MiniCPM-V-4.6 1,3B | ~1 | compresión 16x de tokens visuales |
| Gemma-4-E2B (visión) | ~2 | visión+audio en un worker |

**F. Exploratorias (1 celda, hipótesis falsable):** DiffusionGemma-26B IQ3
(§6c) · MoltenVK sobre RX 580 con balizas · CoreML/Vision OCR en la RX 580.

Total ~22 candidatos, ~45 GB de descargas EN SERIE (caben en los 18 GB
libres yendo de uno en uno). Fase 1 = velocidad pura (llama-bench, descarte
rápido); fase 2 = los 3-4 mejores por categoría pasan a needles/tooling/
contexto; fase 3 = palancas transversales sobre los finalistas:
mainline vs **ik_llama.cpp** (IQ4_K/_R4), Q4_0-repack vs Q4_K_M vs IQ4_XS,
KV q8_0, ngram/self-spec/MTP, -t 6 vs 12, y en la RX 580: MoltenVK (con
balizas de verificación) + CoreML/Vision para encode de imagen.

## 6b. Nodo VPS (contabo-vps) y arquitectura distribuida — añadido 2026-06-12

Perfilada y registrada en BD: **AMD EPYC virtualizado, 6 vCPU, AVX2 (sin
AVX-512/AMX), 11,7 GB RAM, 85 GB libres, Docker+python3, Linux x86_64.**
Sin Tailscale instalado (instalarlo es prerrequisito del plan distribuido).

Cálculo del nodo: vCPUs compartidas → bandwidth efectivo DESCONOCIDO y variable
(típico VPS compartido: 10-25 GB/s; **hay que medirlo con llama-bench, no
suponerlo**). Presupuesto con guardarraíles (regla permanente): 11,7 − 2,5 GB
margen ≈ **9 GB para modelos**. Techo realista de chat: denso 4B Q4 (~5-12 t/s
según bandwidth real) o MoE A1B (~15-30 t/s). NO es nodo de chat principal:
es nodo de **servicios**.

**Reparto óptimo calculado (prioridad de Rubén: embeddings → VPS):**

| Servicio | Nodo | Por qué |
|---|---|---|
| Embeddings (BGE-M3 / nomic GGUF, ~0,6-1,2 GB) | **VPS** | Compute pequeño, sin estado, batcheable; RTT Tailscale ~25-45 ms ≪ tiempo de embedding; libera RAM del Ryzen |
| Reranker (bge-reranker-v2-m3) | **VPS** | Ídem |
| Router LiteLLM + UI + Postgres (repo LLM_ROUTER) | **VPS** | Ya tiene Docker; el Hackintosh no tiene ni python3 sano |
| Chat/agente principal (Qwen3.5-2B / Granite-H-Tiny) | **Ryzen** (CPU) | Único nodo que llega a ≥20 t/s |
| Tooling pesado lento (Qwen3.5-4B) | Ryzen, slot secundario | Un modelo a la vez (regla) |
| Visión/OCR | Ryzen (VLM 2B CPU + CoreML/Vision en RX 580) | La RX solo es segura vía CoreML/MPS |
| Worker batch nocturno | VPS | Trabajo asíncrono donde 5-10 t/s no duele |

Latencia de red medida (MBP→VPS por internet): ping ~40 ms, ssh OK. Falta medir
Ryzen→VPS vía Tailscale (DERP vs conexión directa: el ping previo a manu-macpro
fue relay `via 90.68.46.15` — vigilar que no degrade embeddings en lote).

**Benchmark pendiente en VPS (mismo protocolo frontier_bench, validez
ambiental incluida):** sysbench/STREAM para bandwidth real, llama-bench con
el mismo modelo testeado en el Ryzen (comparabilidad), y throughput de
embeddings (frases/s con BGE-M3 Q8) — todo con guardarraíles de RAM.

## 6c. DiffusionGemma (petición de Rubén) — añadido 2026-06-12

**google/diffusiongemma-26B-A4B-it** (10-jun-2026, Apache 2.0): primer modelo
de difusión de texto open-weight de Google — genera refinando bloques de 256
tokens en paralelo, no token a token. GGUF: `unsloth/diffusiongemma-26B-A4B-it-GGUF`.

Cálculo para nuestras máquinas:

- **RAM:** 26B-A4B Q4 ≈ 17 GB → **no cabe en 16 GB**; solo IQ3/Q2 (~10-11 GB)
  con guardarraíles al límite. En la VPS (9 GB útiles) no cabe de ninguna forma.
- **Soporte:** llama.cpp NO lo soporta en mainline — exige build custom con
  PR #24427 + sampler de difusión PR #24423 (entropy_bounded_denoising,
  temperatura linear_decay 0.8→0.4). Como vamos a compilar nosotros, es viable
  técnicamente, pero es código sin mergear (riesgo de bugs).
- **La física le juega EN CONTRA en CPU:** el "4x más rápido" de difusión viene
  de paralelizar el refinado del bloque — eso es throughput de CÓMPUTO (brilla
  en GPU). En un 6-core AVX2 bandwidth-bound el paralelismo extra no tiene de
  dónde salir; cada pasada de refinado relee los pesos. Hipótesis falsable:
  **en este Ryzen, DiffusionGemma IQ3 NO supera a Gemma-4-26B-A4B autoregresivo
  equivalente en t/s efectivos**. Celda exploratoria de bajo coste: 1 config,
  medir, documentar, borrar. Prioridad: tras los 3 candidatos principales.

Fuentes: huggingface.co/unsloth/diffusiongemma-26B-A4B-it-GGUF,
spheron.network/blog/deploy-diffusiongemma-gpu-cloud, diffusiongemma.dev,
ollama/ollama#16664, analyticsvidhya.com (jun-2026).

## 7. Hallazgos no verificados / vigilancia

- Ling-mini-2.0: contexto y calidad de tooling sin verificar; 0 benchs AVX2.
- Qwen3.5/3.6 MoE en CPU: kernels GDN nativos llegaron en PR #20334; números
  post-fix en DDR4 aún no publicados.
- ik_llama.cpp en macOS x86: build sin CI — verificar localmente.
- STQ1_0 (Tencent Sherry 1.25-bit, PR #22836): merge sin confirmar.
- "Phi-5" y "DeepSeek R2 distills": rumores sin release oficial en HF.
- North-Mini-Code (Cohere, 9-jun): requiere PR #24260, Q4 no cabe. Watch-list.

## 8. Fuentes principales

llama.cpp: issues #19480, #19894, #15228, #19431, #23838, #10757; PRs #20334,
#16063, #12332, #22836; discussions #15396, #15095, #20969, #5617;
docs multimodal.md / function-calling.md / speculative.md.
ik_llama.cpp: discussions #8, #164, #357; PRs 529, 1261, 1646.
Benchmarks: llamafile #450 (5600X), TechHara medium (5600H CPU vs iGPU),
openbenchmarking pts/llama-cpp (5600G), HN 45148237 (3950X DDR4),
reddit r/LocalLLaMA 1p90zzi (CPU-only t/s), ahelpme (EPYC 9554),
dev.to leaseweb (EPYC 9334), megaoneai (Pi 5).
Modelos: unsloth.ai/docs (qwen3.5, qwen3.6, gemma-4, ministral-3, granite-4.1),
liquid.ai/blog (LFM2.5), ibm.com (Granite 4.0/4.1), qwen.ai (3.6/3.7),
jdhodges.com eval tool-calling mar-2026, openai.com/open-models,
arXiv 2601.14277 (quant survey), 2504.12285 (BitNet), 2601.02346 (Falcon-H1R).
Qwen3.7 sin pesos: codersera.com, openrouter.ai/qwen/qwen3.7-max.

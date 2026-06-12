# Segunda pasada SOTA de técnicas — 2026-06-12 (pre-benchmark Ryzen)

> Verificación exhaustiva pedida por Rubén antes de tocar el primer modelo.
> 3 agentes (decode-acceleration / memoria-KV-contexto / serving-embeddings-GPU),
> contrastando PRs reales de GitHub, no blogs. b9605 = master de HOY (85f99dc).

## 1. LO QUE CAMBIA EL PLAN (alta prioridad)

### 1.1 `--spec-type`: especulación draft-free unificada — YA ESTÁ en b9605
- PR #18471 (ene-2026) + ampliaciones: `llama-server --spec-type
  ngram-mod|ngram-simple|ngram-map-k|ngram-map-k4v|draft-simple|draft-mtp`.
  `--spec-default` activa ngram-mod (pool rolling-hash ~16 MB, memoria cte).
- En CPU bandwidth-bound es el caso IDEAL (verificar n tokens ≈ 1 pasada de
  pesos): 40-150% reportado en cargas repetitivas/agénticas; ~1.0x en chat libre.
- ⚠️ CONTRAEVIDENCIA clave (benchmark thc1006, 19 configs): en MoE A3B la
  especulación NO gana a batch=1 — cada token draft activa expertos distintos
  y el verificador carga la UNIÓN (penalti de bandwidth). **Regla: especulación
  = palanca para DENSOS; en MoE medirla pero esperar ~1x y documentarlo.**
- Flags: `--spec-type ngram-mod --spec-ngram-mod-n-match 24 --spec-ngram-mod-n-min 48
  --spec-ngram-mod-n-max 64`; sweep de `--spec-draft-n-max` (en 6 cores, drafts
  >32 chocan con cómputo). El server imprime acceptance rate → anotarlo en BD.

### 1.2 MTP merged en mainline: Qwen3.6 (PR #22673, 16-may) y Gemma 4 (PR #23398
  7-jun + #24282 8-jun para E2B/E4B). b9605 está EN la frontera → verificar que
  acepta `--spec-type draft-mtp` con el GGUF MTP de Gemma-4-E2B (Unsloth los
  publica). Dense ~1.4-2.2x; en MoE batch=1 ~1x (misma razón que 1.1).
  ik_llama lo tiene desde mayo (PR #1744) con harness reproducible
  (karany97/llamacpp-gemma4-mtp, 2.6-3.0x lossless): correr sus 2 scripts.

### 1.3 KV asimétrico q5_0(K)/q4_0(V) — mejor que q4_1 a igual tamaño
- Estudio anbeeld (el que citan los maintainers): K=q5_0 + V=q4_0 da 91,4% de
  precisión de cola vs 88,8% de q4_1 al mismo tamaño; tras K=q5_0 el siguiente
  bit útil va a V. **Escalera de KV a medir: f16 → q8_0 → q5_0/q4_0.**
- TurboQuant TBQ: PR #21089 CERRADO SIN MERGE (2-jun-2026, JohannesGaessler:
  "no one has presented evidence"); turbo4 = más pequeño pero PEOR que q4_0 en
  precisión y 17% más lento en prefill. Forks vivos: TheTom, beellama (TCQ
  trellis, único modo viable <4 bits), qvac-fabric (K/V mixto + FA). Confirma
  nuestra decisión: KV q8_0 (o q5_0/q4_0) mainline, forks solo si falta RAM.
- Hadamard rotation (PR #21038 de ggerganov): sigue DRAFT; en CPU cuesta ~23%
  de throughput. No usar.

### 1.4 ¡La RX 580 vuelve al tablero!: Metal v3 backend en Intel-Mac AMD
- Discussion #19187 (2026): el backend Metal v3 de llama.cpp FUNCIONA en
  GPUs AMD de Mac Intel y es MÁS RÁPIDO que MoltenVK en prefill (decode
  comparable). Esto matiza el "Metal-AMD = corrupto" (#19563) de la doc de
  rotorquant-analysis — el v3 es posterior. MoltenVK en cambio acumula
  problemas nuevos (#19781 regresión pp, #20104 gibberish en Intel-Mac).
- **Celda exploratoria actualizada: probar Metal v3 ANTES que MoltenVK en la
  RX 580 — SIEMPRE con balizas sha256 (la lección del #19563 es que el t/s
  puede ser plausible y el texto basura; el needle-recall es el detector).**
- Vulkan/RADV (25 t/s en 4B Q4, 15 t/s en 9B en RX 580) sigue siendo solo-Linux.
  Tope ~4 GB por asignación única en RADV confirmado vigente (#15054).

### 1.5 llama-server ROUTER MODE (dic-2025) — cambia el diseño del router
- llama-server sin modelo = modo router: autodescubre GGUFs (`--models-dir`),
  carga bajo demanda según el campo `model`, LRU-evict con `--models-max`
  (¡default 4 → ponerlo a 1 en 16 GB!), multiproceso (crash aislado),
  `--sleep-idle-seconds` autodescarga, `--models-preset config.ini` (mmproj
  por modelo), endpoints GET /models, POST /models/load|unload.
- **Implementa NATIVAMENTE el protocolo de Rubén (un modelo a la vez) y la
  encuesta de Manu puede operar sobre /models/load|unload.** llama-swap solo
  haría falta si entran sd.cpp/whisper bajo el mismo endpoint.
- Bonus: llama-server ya habla la Anthropic Messages API (ene-2026).

## 2. HIGIENE DE BENCHMARK (obligatorio para validez)

- **Desactivar cachés en medición limpia**: `--cache-ram 0 -sps 0.0
  --cache-reuse 0 --no-cache-idle-slots` (el prompt-cache en RAM es default-ON
  desde oct-2025 y contamina el prefill del run N con el N-1).
- **Amortizar el prefill de 128K**: pagarlo UNA vez y `--slot-save-path` +
  POST /slots/{id}?action=save|restore (fichero ≈ tamaño KV; con q8_0 la mitad).
- **Bug #21133**: con `--mmproj` cargado se bloquean save/restore, checkpoints
  y cache-reuse incluso en peticiones de texto → NO cargar mmproj en celdas
  de texto; visión en celdas separadas.
- `-ctxcp/--ctx-checkpoints` (default 32) necesarios para reuse en SWA/híbridos.
- YaRN sigue siendo el techo (sin LongRoPE2/DCA en llama.cpp); runs con YaRN
  etiquetados aparte (calidad no comparable). Receta: `-c 131072 --rope-scaling
  yarn --rope-scale 4 --yarn-orig-ctx 32768` solo si ctx > nativo.
- macOS 16 GB: pesos mmap (file-backed, NO los comprime el compresor de macOS;
  evicción barata) pero KV/buffers son páginas anónimas → si rozan el techo
  entran al compresor (entropía alta = comprime mal = paga CPU y swapea igual).
  Síntoma: colapso de tg. **Regla cuantitativa: residente+KV+compute ≤ ~13 GB**
  — coincide con el guardarraíl de Rubén. `--no-mmap` NUNCA en macOS. `--mlock`
  solo si modelo+KV caben holgados.

## 3. DESCARTES VERIFICADOS (no perder tiempo)

- PowerInfer/TurboSparse: AVX2 sí pero macOS x86 NO soportado; zoo de modelos
  congelado en 2024-25. Fuera.
- Difusión en CPU: DiffusionGemma PR #24427 sigue sin merge; mecánicamente
  compute-bound (forward completo del bloque por paso de denoise) = el trade
  EQUIVOCADO para 6 cores bandwidth-bound; 0 números CPU publicados. La celda
  exploratoria queda en lo previsto (§6c del doc landscape): hipótesis de que
  pierde contra AR. Dream-7B/LLaDA-8B sí están en mainline (llama-diffusion-cli)
  como nota al pie.
- STQ1_0 (PR #22836): es cuantización de PESOS (no KV), kernel solo ARM NEON →
  en AVX2 caería al path genérico lento. Fuera.
- SuffixDecoding: solo vLLM; EAGLE-3.1: GPU+drafter entrenado. Fuera.
- vLLM-CPU/SGLang en 6 cores: llama.cpp los iguala o gana a paralelismo bajo.
  LiteLLM se queda como capa router pura (overhead ~ms, header
  x-litellm-overhead-duration-ms para medirlo).

## 4. STACK VPS ACTUALIZADO (embeddings/rerank)

- **EmbeddingGemma-300m** (308M, <200 MB cuantizado, mejor <500M multilingüe) o
  **Qwen3-Embedding-0.6B** (64,3 MTEB, 32K ctx) — medir ambos.
- Prefiltro casi gratis: **potion-base-32M** (model2vec estático, ~25k frases/s
  por core, 92% de MiniLM) → patrón 2 etapas: potion → denso.
- Reranker: **bge-reranker-v2-m3 ONNX int8** o **Qwen3-Reranker-0.6B GGUF**
  (llama.cpp /rerank). Servir con **TEI ≥1.8.2** (¡el backend MKL estuvo roto
  1.7.0→1.8.1!) o contenedor ONNX-cpu.
- Throughput estimado 6 vCPU (SIN benchmark publicado — medirlo): clase
  bge-small/EmbeddingGemma ~50-150 frases/s en batch; BGE-M3/Qwen3-0.6B ~5-20/s.
- Tailscale: VPS con IP pública → conexión directa casi garantizada (verificar
  `tailscale ping` = "direct"; el ping a manu-macpro salió via DERP → revisar).
  Jerarquía 2026: direct > peer-relay (12x DERP) > DERP.

## 5. Matriz de palancas FINAL para los finalistas

| Palanca | Flag | Esperado denso | Esperado MoE |
|---|---|---|---|
| ngram-mod | `--spec-type ngram-mod` | 1.2-2.5x (agéntico) | ~1x (documentar) |
| MTP | `--spec-type draft-mtp` + GGUF-MTP | 1.4-2.2x | ~1x |
| KV q8_0 | `-ctk q8_0 -ctv q8_0 -fa on` | RAM/2, t/s ~= | igual |
| KV q5_0/q4_0 | `-ctk q5_0 -ctv q4_0` | RAM/3, vigilar needles | igual |
| Q4_0-repack | GGUF Q4_0 (repack auto AVX2) | +pp, +tg leve | igual |
| ik_llama IQ4_K/_KT | fork (compilar) | decode x1.5-2.4 | fused MoE +
| hilos | `-t 6` (sweep 5/6/12) | decode óptimo 6 | prefill quizá 12 |
| Metal v3 RX580 | `-DGGML_METAL=ON` + balizas | ¿pp x2? VERIFICAR salida | ídem |

Fuentes primarias: PRs/issues llama.cpp #18471 #22673 #23398 #24282 #21089
(cerrado) #21038 (draft) #19726 (abierto) #21385 #21961 #21133 #24126 #15054;
discussions #19187 #19781 #20104 #20574 #20969 #15180; docs/speculative.md y
tools/server/README.md de master (b9605); anbeeld.com KV study; HF blog
model-management-in-llamacpp y anthropic-messages-api; unsloth.ai/docs (MTP,
diffusiongemma); github thc1006 / karany97 harnesses; tailscale.com peer-relay;
TEI releases; model2vec; Qwen3-Embedding/Reranker; EmbeddingGemma (arXiv
2509.20354).

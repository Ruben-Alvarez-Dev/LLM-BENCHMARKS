# Inference Techniques Landscape — 2026-06-07

> Researched via MCP-agent-research (13 providers; see audit at the bottom).
> Scope: what actually accelerates local inference on Apple Silicon (M1 16/32GB)
> as of June 2026, with evidence. Every claim carries a source.

## 1. Speculative decoding on Apple Silicon: engine-dependent, NOT a free win

### llama.cpp Metal: NET LOSS (measured)

- MTP (`--spec-type draft-mtp`) merged in mainline (PR #22673, 2026-05-16) but
  **degrades throughput on Metal at every configuration**. Issue #23752
  (M1 Max 32GB, Qwen3.5-9B-MTP Q4_K_M, b9330): baseline 25.3 tok/s vs 22.4
  (n_max=0, 100% acceptance) and 19.3 (n_max=6, 44% acceptance). Qwen3.6-35B-A3B
  MoE shows 5-14x regression. Draft evaluation overhead on Metal exceeds the
  speculative gain. Mirrored in HF Qwen3.5-9B discussion #56.
  https://github.com/ggml-org/llama.cpp/issues/23752

### MLX-native MTP: 2.24x (measured)

- **MTPLX** (Apache-2.0, 688 stars): runs the model's own MTP heads as drafter
  with exact probability-ratio acceptance + residual correction (distribution
  preserved at T>0). **~2.24x over no-MTP autoregressive at temp=0.6 on
  Qwen3.6-27B**; public record 63 tok/s on M5 Max. OpenAI/Anthropic-compatible
  server. Candidate engine adapter for FRONTIER BENCH.
  https://github.com/youssofal/MTPLX
- EAGLE-3 prototype for mlx-lm with Apple Silicon analysis:
  https://github.com/ml-explore/mlx-lm/discussions/890

### EAGLE-3 and DFlash status

- EAGLE-3 in llama.cpp: PR #18039 is still an OPEN DRAFT (22 commits, not
  merged as of 2026-06-07). Production EAGLE-3 lives in vLLM/SGLang:
  RedHatAI/gemma-4-31B-it-speculator.eagle3 (acceptance 2.07-3.93 tokens at
  k=3..5). https://github.com/ggml-org/llama.cpp/pull/18039
- DFlash (block-diffusion drafter; z-lab heads for Qwen3.5 4B/9B/27B/35B-A3B):
  2-5x on B200/SGLang at low concurrency, but the llama.cpp port (PR #22105)
  is a NET LOSS of -44.6% on RTX 3090 Q4. Engine + hardware dependent; no
  Apple Silicon datapoint yet. https://kaitchup.substack.com/p/dflash-for-qwen35-eagle-for-gemma

## 2. KV-cache quantization: TurboQuant is the headline

- TurboQuant (Google DeepMind, ICLR 2026): outlier-aware per-layer KV
  quantization, turbo3/turbo4 cache types. 4.6-5.2x KV compression
  near-lossless; mixed setups documented (`-ctk turbo3 -ctv turbo4` — Keys
  tolerate 3-bit better than Values). NOT in mainline: PR #21307 was closed
  ("AI policy violation"); lives in forks. turboquant_plus (6.9k stars) ships
  llama.cpp/Metal integration with prefill at ~q8_0 parity and ~4.6x
  compression — directly relevant to the 1M-token context ladder on the
  16GB Mac Mini, where KV is the wall.
  https://github.com/ggml-org/llama.cpp/discussions/20969
  https://github.com/ggml-org/llama.cpp/discussions/21243 (native Metal WIP)
  https://kevinkeller.org/posts/turboquant-kv-cache-local-llm-consumer-hardware/

## 3. Long context: YaRN limits and what's next

- YaRN degrades beyond scaling factor s~8 (YaRN paper, arXiv:2309.00071).
- Perplexity is NOT a sufficient indicator: Code Llama 13B shows rising ppl
  above 100K yet 99.4% passkey accuracy at 128K — validates our beacon-recall
  (sha256) methodology over ppl-based verdicts.
- LongRoPE2 (arXiv:2502.20082): near-lossless extension, candidate to watch.
- "60-70% rule": advertised vs effective context gap is universal (Llama 4
  Scout 10M analysis). Matches our decision to BISECT effective context.
- RTPurbo (Alibaba/Nanjing, May 2026 preprint): converts full-attention Qwen3
  to sparse attention in a few hundred steps — 9.36x prefill at 1M ctx.
  Research-stage; watch for GGUF-able artifacts.

## 4. Actions for FRONTIER BENCH

1. techniques.yaml — mtp: available in mainline, `not_for: metal` with
   evidence #23752; keep cells to CONFIRM on our M1s (measure, don't assume).
2. techniques.yaml — eagle3: correct status to "PR open, vLLM/forks only";
   not CUDA-only conceptually, but no mainline Metal path yet.
3. techniques.yaml — add dflash (engine-dependent; SGLang/vLLM datacenter
   yes, llama.cpp consumer no) and turboquant (fork-only; Metal via
   turboquant_plus).
4. New engine adapters to consider: MTPLX (MLX, native MTP) and mlx-lm —
   v1 had MLX coverage, v2 does not yet.
5. KV ladder: add turbo3/turbo4 cells (requires fork build) next to q4_0/q8_0.

## Appendix: MCP-agent-research audit (2026-06-07)

Tested during this research session:

| Tool | Result |
|---|---|
| search_status | OK — 13 providers reported healthy |
| search_deep | EXCELLENT — multi-provider fusion + extraction, fresh, relevant |
| search_web | EXCELLENT — freshness filter works, GitHub-aware results via exa |
| search_extract | OK — full content via Jina |
| search_auto | WORKS but output DUPLICATED (results 1-20 repeated as 21-45: fusion dedup bug) |
| perplexica_research | FAIL — HTTP 403 Forbidden |
| gpt_research | FAIL — HTTP 403 Forbidden |

Findings:
1. The two self-hosted research backends (Perplexica, GPT-Researcher) return
   403 — service-side auth/allowlist issue, not MCP code (clients in
   src/providers/self-hosted/ are correct).
2. search_status health check does NOT probe the research endpoints — it
   reported both as OK while they 403. Health check should hit /api/config
   (Perplexica) and the GPT-Researcher base URL.
3. search_auto has a result-duplication bug in its fusion/presentation layer.
4. Extraction target selection can pick tangential sources (chose a RoPE
   tutorial over the YaRN paper for extraction).
5. Repo has no README (entity catalog notes this; description recovered from
   package.json).

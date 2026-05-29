# Evolución de la Atención en LLMs (2025–2026)

> Fecha: 2026-05-29
> Propósito: Investigación complementaria sobre evolución de mecanismos de atención.

---

## Resumen

Entre oct 2025 y may 2026, industria china convergió hacia atención híbrida.
Tres implementaciones: DeepSeek V4 (CSA+HCA+MLA), Xiaomi MiMo (HySparse), MiniMax M3 (MSA).

---

## DeepSeek-OCR

Paper: arxiv 2510.18234 (oct 2025). Texto renderizado como imagen + VLM.
Compresión <10x: 97%. 20x: ~60%. 200k+ páginas/día A100-40G.

Crítica: arxiv 2601.03714 (ene 2026). Sin lenguaje: ~90% → ~20%.
Colapso en ~10k tokens.

OCR 2: arxiv 2601.20552. DeepEncoder V2 (Qwen2). Reordenamiento dinámico. 91.09%.

---

## Atención Híbrida

### DeepSeek V4 (abr 2026)
V4-Pro: 1.6T/49B activos. V4-Flash: 284B/13B. MIT. 1M ctx.
MLA + CSA (4x compresión) + HCA (128x compresión).
27% FLOPs, 10% KV cache (datos oficiales HF).
$0.435/M in, $0.87/M out (precio permanente).

Benchmarks vs Gemini 3.1 Pro (tabla HF):
- LiveCodeBench: 93.5 vs 91.7
- Codeforces: 3206 vs 3052
- SWE-bench: 80.6 vs 80.6
- GPQA Diamond: 90.1 vs 94.3

### Xiaomi HySparse (feb 2026)
arxiv 2602.03560. 49 layers, solo 5 full. KV cache ~10x.
MiMo-V2-Flash: 309B/15B 5:1. V2.5-Pro: 1.02T/42B 6:1.

### MiniMax M3 (may 2026)
MSA: block-level, sin comprimir. 9.7x prefill, 15.6x decode.

---

## Implicaciones

MLA + cuantización KV (PlanarQuant, IsoQuant) son ortogonales.
Potencial ~2% KV cache combinado.

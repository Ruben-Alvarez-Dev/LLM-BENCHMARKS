# LLM-BENCHMARKS — Benchmark Suite for Local Inference

> Research and certification of language models for local inference across a
> heterogeneous fleet (Apple Silicon, AMD x86 Hackintosh, Linux VPS).
> Started: 2026-05-24 · Last update: 2026-06-12

## Governance

This repo is governed by `CLAUDE.md` + `.atl/` (golden rules, machine-readable
rules, living memory in `learnings.md`, L0-L4 hook gates, Ralph Loop
`tasks.json`/`progress.txt`). Read `CLAUDE.md` before touching anything.
Iron rules: ONE model on disk at a time · memory guardrails always ·
sha256 beacons for correctness claims · external/strategic load first,
local as fallback · everything measured, nothing assumed.

## Project structure

```
LLM-BENCHMARKS/
├── CLAUDE.md                 # Per-iteration governance injection
├── .atl/                     # Golden rules, learnings, hooks, Ralph Loop state
├── SESSION.md                # Full research logbook (append-only)
├── src/frontier_bench/       # FRONTIER BENCH v2 — hexagonal benchmark engine
│   ├── domain/               # Pure domain: planner, kv_model, environment,
│   │                         #  verdicts, battery, scheduler, ranking, executor
│   └── adapters/             # llama-bench/cli/server, SSH/local runners,
│                             #  SQLite WAL store, probes, corpus (sha256 beacons),
│                             #  loadgen, web UI (:4400), MCP server
├── batteries.yaml            # Declarative batteries + falsifiable hypotheses
├── techniques.yaml           # Technique encyclopedia (purpose/not_for/evidence)
├── tuning_rules.yaml         # Host-adaptive tuning rules with evidence
├── verdict_rules.yaml        # APTO/FRONTERA verdict rules
├── data/frontier_bench_v2.db # All results (SQLite WAL, hardware-tracked)
├── docs/research/            # Dated research reports
├── docs/benchmarks/          # Per-model result reports
├── models/STATUS.md          # Model list + download/verify/delete protocol log
└── engines/orchestrator/     # v1 pipeline (legacy, migrated into v2 DB)
```

## Fleet (machines registered in DB)

| machine_id | Hardware | OS | Role |
|---|---|---|---|
| m1-mini-16gb | Mac Mini M1, 16 GB | macOS | Original benchmark node |
| m1-max-32gb | MacBook Pro M1 Max, 32 GB | macOS | Workstation / dev |
| ryzen-5600g-16gb | Ryzen 5 5600G, 16 GB, Sapphire RX 580 8GB | macOS x86 (Hackintosh) | **Active campaign** (CPU AVX2; GPU only via CoreML/Vision or beacon-verified Metal v3 cells) |
| contabo-vps | EPYC 6 vCPU, 11.7 GB | Linux | Services node: embeddings/rerank (TEI), router, batch |

## Active campaign (2026-06-12): ryzen-5600g-16gb

Goal: ≥20 t/s decode · Q4 · ≥128K context · max tooling/multimodal/reasoning.
22 candidates in 6 categories (workers ≤2.6B · small-active MoE · 4B agents ·
7-9B quality · vision · exploratory) — see
`docs/research/2026-06-12-RYZEN-5600G-INFERENCE-LANDSCAPE.md` and the SOTA
techniques pass in `docs/research/2026-06-12-TECHNIQUES-SOTA-V2.md`.

First verified results (llama.cpp b9605, 6 threads, defaults — no fa/KVq8 yet):

| Model | Cell | t/s |
|---|---|---|
| Qwen3.5-2B Q4_K_M | pp512 | 151.7 ± 0.9 |
| Qwen3.5-2B Q4_K_M | tg128 | **25.1 ± 0.4** ✓ target met |
| Qwen3.5-2B Q4_K_M | tg128 @32K depth | 8.4 ± 0.1 (lever cells queued) |

Distributed architecture (router LiteLLM + web UI + LiveKit voice on VPS,
llama-server router-mode on Ryzen): see `~/Code/LLM_ROUTER/ARQUITECTURA-DISTRIBUIDA-MANU.md`.

## Historic results (v1, Mac Mini M1 16GB)

129 tests, 10 GGUF + 9 MLX models processed and documented; migrated into the
v2 DB with `protocol=v1`. Highlights: Qwen3.5-4B 60 t/s (MVP), Qwen3-1.7B
156 t/s, Gemma-3n-E2B 71 t/s @128K. Full tables in `SESSION.md` §4.

## Quick usage

```bash
# Profile and register a machine (local or remote)
PYTHONPATH=src python3 -m frontier_bench.cli probe --machine-id <id> [--ssh <host>]

# Plan a declarative battery (dry)
PYTHONPATH=src python3 -m frontier_bench.cli battery multislot_certification --plan

# Measure decode-at-depth with environmental validity
PYTHONPATH=src python3 -m frontier_bench.cli measure --help

# Live dashboard
PYTHONPATH=src python3 -m frontier_bench.cli ui   # http://localhost:4400
```

## Tests

83/83 green (pure-domain unittest, no I/O). TDD gate: nothing is "done"
without an explicit passing proof.

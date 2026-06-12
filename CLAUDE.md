# CLAUDE.md — LLM-BENCHMARKS Governance (loaded every iteration)

> Full rules: `.atl/golden-rules.md` · Machine-readable: `.atl/golden-rules.json`
> Living memory: `.atl/learnings.md` · Hooks: `.atl/hooks/`

## Identity & language
- Spanish with Rubén. English for EVERYTHING else (code, docs, commits, specs, configs).
- SOLID + DRY + Clean/Hexagonal + BEM. Industry-standard docs (ADR, conventional commits).

## Non-negotiables (blacklist)
- NO improvising — spec first, plan first, then execute exactly that.
- NO mockups / demos / fake data — 100% real, production.
- NO touching anything outside the approved scope (surgical cuts only).
- NO claims without a second source. NO lazy questions — search/investigate first.
- NO "seems to work" — explicit passing test (TDD gate) or it is NOT done.
- NO hiding errors. NO delegating to Rubén what the AI can do itself.
- NO context rot — Ralph Loop: fresh context, memory in filesystem + Git.

## Pre-action protocol
SAY what you intend → LIST the exact actions → WAIT for Rubén's OK → EXECUTE only that.

## Post-action protocol
Verify → show evidence to Rubén → capture learning in `.atl/learnings.md` →
granular conventional commit (2-4 sentences, English) → push if remote exists.
Keep the repo CURRENT as work happens: README, docs, experiments, expansions —
the repo must always describe today's reality, not last week's (Rubén 2026-06-12).

## Project-specific iron rules (benchmarks)
- ONE model on disk at a time: download → note in list → verify sha256 → bench →
  DELETE → only then next. Never batch downloads.
- Memory guardrails ALWAYS: resident+KV+compute ≤ ~13 GB on 16 GB nodes;
  abort/cut load when approaching limits (RAM ≥2-3 GB free, VRAM ≥1-1.5 GB).
- Environmental validity: pre/post-flight (domain/environment.py); interference ⇒ valid=0.
- Beacons (sha256 balizas) for any correctness claim — t/s alone proves nothing
  (Metal-AMD silent corruption precedent).
- Every result → SQLite DB + docs/benchmarks/ + SESSION.md. Estimates labeled as such.
- External/strategic load preferred (APIs, VPS); local node is fallback.

## Filesystem convention
- Any project created/loaded/generated lives under the user's `~/Code/` folder
  on EVERY machine (e.g. /Users/ruben/Code, /Users/manu/Code, VPS user's ~/Code).

## Workflow (7 layers)
L0 SPEC → L0.5 PLAN (options, trade-offs, consult learnings) → L1 INJECT (this file)
→ L2 VALIDATE (approval? scope? double source? no mock?) → L3 EXECUTE (plan only)
→ L3.5 TDD GATE (green or not done) → L4 RECALC (evidence/suspicion ⇒ stop;
learning ⇒ save; verified ⇒ show; commit ⇒ granular+push; next ⇒ L0).

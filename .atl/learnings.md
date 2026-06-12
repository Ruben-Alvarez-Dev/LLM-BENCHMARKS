# learnings.md — living memory (append-only)

Format: `LL-XXX · date · what happened · learning · rule reinforced`

- **LL-001** · 2026-06-12 · Assumed the 5600G's iGPU (Vega 7) was the GPU; the
  real card is a Sapphire RX 580 8GB (macOS misreports it as "RX 570", device
  0x67df common to both). The team's own docs (rotorquant-analysis/) had it all.
  · **Read the project's existing documentation BEFORE forming hardware
  assumptions.** · GR03, GR09
- **LL-002** · 2026-06-12 · Noted the wrong sha256 in STATUS.md (copied Q4_1's
  LFS oid instead of Q4_K_M's from the HF API listing). Caught at verify step.
  · **The verify-download step works; never skip it. Double-check field↔file
  alignment when reading API listings.** · GR08, PR01
- **LL-003** · 2026-06-12 · llama-bench runs WITHOUT flash attention and with
  f16 KV by default: tg128 fell 22.2→8.4 t/s from depth 0→32K on Qwen3.5-2B.
  · **Never report depth cells without stating fa/KV flags; always run the
  fa+KVq8 comparison cell.** · GR10, PR03
- **LL-004** · 2026-06-12 · Tailscale ping to manu-macpro went via DERP relay
  (90.68.46.15) — direct path not established. · **Check `tailscale ping` =
  direct before any latency-sensitive distributed work; peer-relay/port pinning
  is the fix.** · GR09
- **LL-005** · 2026-06-12 · Mainline rejected TurboQuant KV (PR #21089, Jun 2)
  on evidence (worse than q4_0 at quality, slower prefill); asymmetric
  q5_0(K)/q4_0(V) beats q4_1 at equal size (anbeeld study).
  · **Verify merge status of any "hot" technique against the actual PR, not
  blog coverage; two blogs were factually wrong (fake b8607 merge, fake 5600G
  numbers).** · GR08
- **LL-006** · 2026-06-12 · Installed frontier-bench into ~/frontier-bench on
  manu's machine before Rubén's ~/Code rule arrived. · **Projects live under
  ~/Code of each machine's user; migrate ~/frontier-bench →
  /Users/manu/Code/frontier-bench at next safe window (no bench running).**
  · PR05
- **LL-007** · 2026-06-12 · Voice channel decision: WebRTC/LiveKit ONLY for
  realtime audio; HTTP/SSE over Tailscale for all inference. LiveKit Agents +
  Silero VAD also kills the fetch+decodeAudioData/autoplay bug class that bit
  jart-voice. · GR15

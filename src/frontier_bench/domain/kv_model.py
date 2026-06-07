"""KvModel — coste de memoria por arquitectura (corrige el fallo A6 de v1).

v1 asumía transformer denso para todo. Aquí cada ArchKind tiene su fórmula:
  DENSE_GQA : 2 · layers · kv_heads · head_dim · bytes · tokens
  HYBRID    : igual pero SOLO capas full-attention + estado recurrente fijo × slots
  SWA       : capas globales a ctx, capas SWA a min(ctx, window)
  MLA       : latente comprimido · layers · tokens
  RECURRENT : solo estado fijo × slots

Puro: sin I/O. Los bytes/elemento de la caché incluyen overhead de bloque GGUF.
"""
from __future__ import annotations

from dataclasses import dataclass

from .entities import ArchKind, KvProfile, MachineFacts, ModelSpec

# bytes por elemento de caché (aprox. con overhead de bloque)
CACHE_BYTES = {
    "f16": 2.0,
    "bf16": 2.0,
    "q8_0": 1.0625,   # 8.5 bits/el efectivos
    "q4_0": 0.5625,   # 4.5 bits/el efectivos
    "planar3_f16": 1.30,  # K planar3 (~0.6) + V f16 (2.0) → media; fork RotorQuant
}

GiB = 1024 ** 3


def _per_token_full_attn(p: KvProfile, layers: int, cache_bytes: float) -> float:
    return 2.0 * layers * p.kv_heads * p.head_dim * cache_bytes


def kv_bytes(p: KvProfile, ctx_tokens: int, slots: int, cache_type: str = "f16") -> float:
    """Bytes totales de memoria de estado para `ctx_tokens` TOTALES (presupuesto kv-unified)
    repartidos entre `slots`. Para arquitecturas con estado fijo, el estado va POR SLOT."""
    cb = CACHE_BYTES.get(cache_type, 2.0)
    if p.arch is ArchKind.DENSE_GQA:
        return _per_token_full_attn(p, p.n_layers, cb) * ctx_tokens
    if p.arch is ArchKind.HYBRID_LINEAR:
        full = p.full_attn_layers or 0
        kv = _per_token_full_attn(p, full, cb) * ctx_tokens
        state = p.recurrent_state_mb * 1024 ** 2 * slots
        return kv + state
    if p.arch is ArchKind.SWA:
        global_l = p.swa_global_layers
        swa_l = p.n_layers - global_l
        # con slots, cada secuencia llena su propia ventana SWA
        per_slot_ctx = max(1, ctx_tokens // max(1, slots))
        swa_tokens = min(per_slot_ctx, p.swa_window) * slots
        return (_per_token_full_attn(p, global_l, cb) * ctx_tokens
                + _per_token_full_attn(p, swa_l, cb) * swa_tokens)
    if p.arch is ArchKind.MLA:
        return p.n_layers * p.mla_latent_dim * cb * ctx_tokens
    if p.arch is ArchKind.RECURRENT:
        return p.recurrent_state_mb * 1024 ** 2 * slots
    raise ValueError(f"ArchKind no soportado: {p.arch}")


@dataclass(frozen=True)
class BudgetResult:
    fits: bool
    weights_gb: float
    kv_gb: float
    compute_overhead_gb: float
    total_gb: float
    budget_gb: float
    reason: str = ""


# overhead de buffers de compute (empírico; se recalibra con sondas reales en F1)
COMPUTE_OVERHEAD_GB = 1.2
SAFETY_MARGIN_GB = 0.5


def budget(machine: MachineFacts, model: ModelSpec, ctx_tokens: int, slots: int,
           cache_type: str = "f16") -> BudgetResult:
    """¿Cabe esta celda en esta máquina? Pesos por tamaño REAL de fichero."""
    weights_gb = model.file_bytes / GiB
    kv_gb = kv_bytes(model.kv, ctx_tokens, slots, cache_type) / GiB
    total = weights_gb + kv_gb + COMPUTE_OVERHEAD_GB + SAFETY_MARGIN_GB
    cap = machine.gpu_budget_gb
    fits = total <= cap
    reason = "" if fits else (
        f"total {total:.2f} GiB > presupuesto {cap:.2f} GiB "
        f"(pesos {weights_gb:.2f} + kv {kv_gb:.2f} + overhead {COMPUTE_OVERHEAD_GB + SAFETY_MARGIN_GB:.2f})"
    )
    return BudgetResult(fits, round(weights_gb, 3), round(kv_gb, 3),
                        COMPUTE_OVERHEAD_GB, round(total, 3), round(cap, 3), reason)

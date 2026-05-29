"""RAM Budget Calculator - calcula si una configuracion entra en RAM antes de cargar."""
from dataclasses import dataclass
from typing import Optional

# Constantes de hardware
RAM_TOTAL_GB = 16.0
RAM_SISTEMA_GB = 3.5      # macOS + servicios base
RAM_OVERHEAD_LLAMA_GB = 0.5  # llama.cpp runtime
RAM_MARGEN_GB = 1.0        # margen de seguridad
RAM_COMPUTE_OVERHEAD_GB = 1.5  # compute GPU + host memory (observado empiricamente)
RAM_DISPONIBLE_GB = RAM_TOTAL_GB - RAM_SISTEMA_GB - RAM_OVERHEAD_LLAMA_GB - RAM_MARGEN_GB  # ~11 GB

@dataclass
class BudgetResult:
    fits: bool
    ram_weights_gb: float
    ram_kv_gb: float
    ram_total_gb: float
    ram_available_gb: float
    breakdown: str

def bits_per_weight(quant: str) -> float:
    """Bits por peso segun formato de cuantizacion."""
    table = {
        "Q4_K_M": 4.5, "Q4_K_S": 4.25, "Q3_K_M": 3.5, "Q3_K_S": 3.3,
        "Q2_K": 2.5, "STQ1_0": 1.3125, "Q1_0_g128": 1.0,
        "Q8_0": 8.0, "Q6_K": 6.5, "Q5_K_M": 5.5, "F16": 16.0,
    }
    return table.get(quant, 4.5)

MLA_LATENT_DIM = 512  # DeepSeek-V2-Lite kv_lora_rank (latent KV dimension)


def kv_cache_bytes_per_token(n_layers: int, n_kv_heads: int, head_dim: int,
                               kv_format: str, attn_type: str = "gqa",
                               latent_dim: int = MLA_LATENT_DIM) -> float:
    """Bytes de KV cache por token (K+V).

    Para GQA: 2 * n_layers * n_kv_heads * head_dim * bytes_por_valor
    Para MLA: 2 * n_layers * latent_dim * 2  (latent f16, siempre f16 porque
              la compresion es en el espacio latente, no por cuantizacion)
    """
    if attn_type == "mla":
        # MLA: KV comprimido a espacio latente de dimension latent_dim
        # Siempre f16 porque la compresion es arquitectural, no por cuantizacion KV
        return 2 * n_layers * latent_dim * 2

    # GQA standard
    bytes_per_val = {"f16": 2, "q4_0": 0.5, "planar3-kf16": 1.04,
                     "planar3-sim": 0.194, "q8_0": 1.0}.get(kv_format, 2)
    return 2 * n_layers * n_kv_heads * head_dim * bytes_per_val

def calculate(model_name: str, n_layers: int, n_kv_heads: int, head_dim: int,
              params_b: float, quant: str, kv_format: str, context_len: int,
              attn_type: str = "gqa", n_gpu_layers: int = 99,
              moe_active_ratio: float = 1.0) -> BudgetResult:
    """Calcula si una configuracion entra en RAM."""
    # Pesos
    ram_weights_gb = params_b * bits_per_weight(quant) / 8.0 * moe_active_ratio

    # KV cache
    bytes_per = kv_cache_bytes_per_token(n_layers, n_kv_heads, head_dim, kv_format, attn_type, latent_dim=MLA_LATENT_DIM)
    ram_kv_gb = (bytes_per * context_len) / (1024**3)

    # Offloading: si n_gpu_layers < 99, parte de los pesos van a CPU
    # (en M1 es memoria unificada, no hay diferencia real)
    ram_total = ram_weights_gb + ram_kv_gb + RAM_OVERHEAD_LLAMA_GB + RAM_COMPUTE_OVERHEAD_GB

    fits = ram_total <= RAM_DISPONIBLE_GB

    breakdown = (
        f"  Pesos: {ram_weights_gb:.2f} GB ({quant}, {params_b}B params)\n"
        f"  KV cache: {ram_kv_gb:.3f} GB ({kv_format}, {context_len} ctx, {attn_type})\n"
        f"  Llama overhead: {RAM_OVERHEAD_LLAMA_GB:.1f} GB\n"  f"  Compute+host: {RAM_COMPUTE_OVERHEAD_GB:.1f} GB\n"
        f"  Total: {ram_total:.2f} GB / {RAM_DISPONIBLE_GB:.1f} GB disponible"
    )

    return BudgetResult(
        fits=fits,
        ram_weights_gb=ram_weights_gb,
        ram_kv_gb=ram_kv_gb,
        ram_total_gb=ram_total,
        ram_available_gb=RAM_DISPONIBLE_GB,
        breakdown=breakdown,
    )

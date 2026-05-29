"""Model Registry - catalogo de modelos con metadatos tecnicos."""
import os
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class ModelSpec:
    name: str
    params_b: float
    arch: str  # dense, moe
    attn: str  # gqa, mla
    context_max: int
    n_layers: int
    n_kv_heads: int
    head_dim: int
    gguf_source: str
    local_path: Optional[str] = None
    quant_available: list = None
    techniques: list = None
    notes: str = ""

    def effective_path(self, quant: str = "Q4_K_M") -> str:
        """Retorna ruta local si existe, o source HF como referencia."""
        if self.local_path and os.path.exists(self.local_path):
            return self.local_path
        return self.gguf_source

    @property
    def has_local(self) -> bool:
        return bool(self.local_path) and os.path.exists(self.local_path)

MODEL_REGISTRY = {
    "Qwen3.5-9B": ModelSpec(
        name="Qwen3.5-9B",
        params_b=9.0, arch="dense", attn="gqa",
        context_max=262144, n_layers=28, n_kv_heads=4, head_dim=128,
        gguf_source="lmstudio-community/Qwen3.5-9B-GGUF",
        local_path="/Users/admin/Code/-Code/INFERENCE-investigation/external/models/Qwen3.5-9B-Q4_K_M.gguf",
        quant_available=["Q4_K_M","Q6_K","Q8_0"],
        techniques=["flash-attn","planar3-kf16","planar3-sim","IsoQuant"],
        notes="Modelo principal del stack. 5.5 GB Q4_K_M. Descargado 2026-05-29."
    ),
    "Qwen2.5-7B-1M": ModelSpec(
        name="Qwen2.5-7B-1M",
        params_b=7.0, arch="dense", attn="gqa",
        context_max=1_000_000, n_layers=28, n_kv_heads=4, head_dim=128,
        gguf_source="Qwen/Qwen2.5-7B-1M-GGUF",
        local_path="/Users/admin/Code/-Code/INFERENCE-investigation/external/vLLM-Jart-OS/models/Qwen2.5-7B-Instruct-1M-Thinking-Claude-Gemini-GPT5.2-DISTILL-PaperWitch-heresy.Q4_K_M.gguf",
        quant_available=["Q4_K_M","Q4_K_S"],
        techniques=["flash-attn","planar3-kf16","planar3-sim"],
        notes="Probar limite real de contexto mantenido en M1 16GB. Distill thinking, Q4_K_M."
    ),
    "Ministral-3-8B": ModelSpec(
        name="Ministral-3-8B",
        params_b=8.0, arch="dense", attn="gqa",
        context_max=131072, n_layers=24, n_kv_heads=4, head_dim=128,
        gguf_source="mistralai/Ministral-3-8B-Instruct-2512-GGUF",
        local_path="/Users/admin/Code/-Code/INFERENCE-investigation/external/models/Ministral-3-8B-Instruct-Q4_K_M.gguf",
        quant_available=["Q4_K_M"],
        techniques=["flash-attn","planar3-kf16"],
        notes="Competidor directo de Qwen3.5. Instruct 2512. Descargado 2026-05-29."
    ),
    "DeepSeek-V2-Lite": ModelSpec(
        name="DeepSeek-V2-Lite",
        params_b=16.0, arch="moe", attn="mla",
        context_max=32768, n_layers=27, n_kv_heads=0, head_dim=128,
        gguf_source="deepseek-ai/DeepSeek-V2-Lite-Chat-GGUF",
        local_path="/Users/admin/Code/-Code/INFERENCE-investigation/external/models/DeepSeek-V2-Lite-Chat-Q4_K_M.gguf",
        quant_available=["Q4_K_M"],
        techniques=["flash-attn"],
        notes="MLA. 16B total, ~2.4B activos. Ver si compensa peso extra."
    ),
    "Gemma-4-E2B": ModelSpec(
        name="Gemma-4-E2B",
        params_b=2.0, arch="dense", attn="gqa",
        context_max=32768, n_layers=16, n_kv_heads=2, head_dim=128,
        gguf_source="lmstudio-community/gemma-4-E2B-it-GGUF",
        local_path="/Users/admin/Code/-Code/INFERENCE-investigation/external/models/Gemma-4-E2B-Q4_K_M.gguf",
        quant_available=["Q4_K_M"],
        techniques=["flash-attn","mtp-spec"],
        notes="Worker veloz. 81 tok/s con MTP nativo. Target 96+ tok/s. Descargado 2026-05-29."
    ),
    "Gemma-4-E4B": ModelSpec(
        name="Gemma-4-E4B",
        params_b=4.0, arch="dense", attn="gqa",
        context_max=32768, n_layers=20, n_kv_heads=4, head_dim=128,
        gguf_source="google/gemma-4-4b-GGUF",
        quant_available=["Q4_K_M"],
        techniques=["flash-attn","mtp-spec"],
        notes="Worker. 52 tok/s con MTP."
    ),
    "Falcon3-7B-STQ1_0": ModelSpec(
        name="Falcon3-7B-STQ1_0",
        params_b=7.0, arch="dense", attn="gqa",
        context_max=65536, n_layers=24, n_kv_heads=4, head_dim=128,
        gguf_source="falcon/falcon3-7b-stq1_0-GGUF",
        quant_available=["STQ1_0"],
        techniques=["planar3-kf16"],
        notes="Ternario 1.3 GB. Worker ligero para tareas atomicas."
    ),

    "Gemma-3n-E2B": ModelSpec(
        name="Gemma-3n-E2B",
        params_b=2.0, arch="dense", attn="gqa",
        context_max=131072, n_layers=16, n_kv_heads=2, head_dim=128,
        gguf_source="google/gemma-3n-2b-it-GGUF",
        local_path="/Users/admin/Jart-OS-workstation/infra/TIERS/TIER-0-METAL/10999-inference-vllm2/models/gemma-3n-E2B-it-Q4_K_M.gguf",
        quant_available=["Q4_K_M"],
        techniques=["flash-attn"],
        notes="Gemma 3N E2B. Worker ligero. 2.8 GB."
    ),
    "Qwen3.5-4B": ModelSpec(
        name="Qwen3.5-4B",
        params_b=4.0, arch="dense", attn="gqa",
        context_max=262144, n_layers=28, n_kv_heads=4, head_dim=128,
        gguf_source="Qwen/Qwen3.5-4B-GGUF",
        local_path="/Users/admin/Jart-OS-workstation/infra/TIERS/TIER-0-METAL/10999-inference-vllm2/models/Qwen_Qwen3.5-4B-Q4_K_M.gguf",
        quant_available=["Q4_K_M"],
        techniques=["flash-attn"],
        notes="Qwen3.5-4B. Modelo principal reducido. 2.7 GB. Contexto 262K."
    ),
    "Qwen2.5-Coder-3B": ModelSpec(
        name="Qwen2.5-Coder-3B",
        params_b=3.0, arch="dense", attn="gqa",
        context_max=32768, n_layers=24, n_kv_heads=4, head_dim=128,
        gguf_source="Qwen/Qwen2.5-Coder-3B-GGUF",
        local_path="/Users/admin/Jart-OS-workstation/infra/TIERS/TIER-0-METAL/10999-inference-vllm2/models/Qwen2.5-Coder-3B-Instruct-Q4_K_M.gguf",
        quant_available=["Q4_K_M"],
        techniques=["flash-attn"],
        notes="Code specialist. 2.0 GB."
    ),
    "Qwen3-1.7B": ModelSpec(
        name="Qwen3-1.7B",
        params_b=1.7, arch="dense", attn="gqa",
        context_max=32768, n_layers=16, n_kv_heads=2, head_dim=128,
        gguf_source="Qwen/Qwen3-1.7B-GGUF",
        local_path="/Users/admin/Jart-OS-workstation/infra/TIERS/TIER-0-METAL/10999-inference-vllm2/models/Qwen3-1.7B-Q4_K_M.gguf",
        quant_available=["Q4_K_M"],
        techniques=["flash-attn"],
        notes="Ultra-ligero. 1.2 GB."
    ),
    "Qwen3.5-2B": ModelSpec(
        name="Qwen3.5-2B",
        params_b=2.0, arch="dense", attn="gqa",
        context_max=32768, n_layers=16, n_kv_heads=2, head_dim=128,
        gguf_source="Qwen/Qwen3.5-2B-GGUF",
        local_path="/Users/admin/Jart-OS-workstation/infra/TIERS/TIER-0-METAL/10999-inference-vllm2/models/Qwen3.5-2B-Q4_K_M.gguf",
        quant_available=["Q4_K_M"],
        techniques=["flash-attn"],
        notes="Ultra-ligero. 1.2 GB."
    ),

        "Bonsai-8B": ModelSpec(
        name="Bonsai-8B",
        params_b=8.0, arch="dense", attn="gqa",
        context_max=32768, n_layers=24, n_kv_heads=4, head_dim=128,
        gguf_source="bonsai/bonsai-8b-q1_0_g128-GGUF",
        quant_available=["Q1_0_g128"],
        techniques=[],
        notes="1-bit experimental. 1.15 GB. Muy limitado pero muy chico."
    ),
}

def get_model(name: str) -> Optional[ModelSpec]:
    return MODEL_REGISTRY.get(name)

def list_models() -> list:
    return list(MODEL_REGISTRY.keys())

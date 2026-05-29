"""Test Matrix Generator — genera matriz cartesiana de tests y filtra por presupuesto RAM.

Para cada modelo, produce una lista ordenada de configuraciones (context x kv_format x flash_attn)
que pasan el filtro de RAM disponible. Se ejecutan en serie, de menor a mayor contexto.
"""
from dataclasses import dataclass
from typing import List, Optional

from .model_registry import ModelSpec
from .ram_budget import calculate as calc_ram, RAM_DISPONIBLE_GB

CONTEXT_STEPS = [16_384, 32_768, 65_536, 131_072, 262_144, 524_288, 768_000, 1_000_000]
KV_FORMATS = ["f16", "q4_0", "q8_0"]
KV_FORMATS_EXPERIMENTAL = ["planar3-kf16", "planar3-sim"]
FLASH_OPTIONS = [True, False]
GENERATION_TOKENS = 256
TEMPERATURE = 0.0
GPU_LAYERS = 99


@dataclass
class TestConfig:
    """Una configuracion atomica de test."""
    model_name: str
    context_len: int
    kv_format: str
    flash_attn: bool
    quant: str
    generation_tokens: int = GENERATION_TOKENS
    temperature: float = TEMPERATURE
    n_gpu_layers: int = GPU_LAYERS
    ram_weights_gb: float = 0.0
    ram_kv_gb: float = 0.0
    ram_total_gb: float = 0.0
    ram_available_gb: float = RAM_DISPONIBLE_GB
    fits: bool = False
    notes: str = ""

    @property
    def id(self) -> str:
        flash_str = "fa" if self.flash_attn else "nofa"
        return f"{self.model_name}_{self.context_len // 1024}K_{self.kv_format}_{flash_str}"

    @property
    def llama_flags(self) -> List[str]:
        flags = [
            "-ngl", str(self.n_gpu_layers),
            "-c", str(self.context_len),
            "-ctk", self.kv_format,
            "-ctv", self.kv_format,
            "--temp", str(self.temperature),
            "-n", str(self.generation_tokens),
            "-st",
            "--no-display-prompt",
            "--show-timings",
        ]
        if self.flash_attn:
            flags.extend(["-fa", "1"])
        return flags

    def __repr__(self) -> str:
        status = "OK" if self.fits else "NO"
        return (
            f"[{status}] {self.id} | "
            f"RAM {self.ram_total_gb:.2f}/{self.ram_available_gb:.1f} GB | "
            f"pesos={self.ram_weights_gb:.2f} kv={self.ram_kv_gb:.3f}"
        )


def generate_matrix(
    model: ModelSpec,
    context_steps: Optional[List[int]] = None,
    kv_formats: Optional[List[str]] = None,
    flash_options: Optional[List[bool]] = None,
    quant: Optional[str] = None,
    include_experimental_kv: bool = False,
) -> List[TestConfig]:
    if context_steps is None:
        context_steps = CONTEXT_STEPS
    if kv_formats is None:
        kv_formats = KV_FORMATS
    if flash_options is None:
        flash_options = FLASH_OPTIONS
    if quant is None:
        quant = model.quant_available[0] if model.quant_available else "Q4_K_M"
    if include_experimental_kv:
        kv_formats = list(dict.fromkeys(kv_formats + KV_FORMATS_EXPERIMENTAL))

    if quant not in (model.quant_available or []):
        return []

    raw_configs = []
    for ctx in context_steps:
        if ctx > model.context_max:
            continue
        for kv in kv_formats:
            for flash in flash_options:
                cfg = TestConfig(
                    model_name=model.name,
                    context_len=ctx,
                    kv_format=kv,
                    flash_attn=flash,
                    quant=quant,
                )
                raw_configs.append(cfg)

    attn_type = model.attn
    moe_ratio = 0.15 if model.arch == "moe" else 1.0

    validated = []
    for cfg in raw_configs:
        budget = calc_ram(
            model_name=model.name,
            n_layers=model.n_layers,
            n_kv_heads=model.n_kv_heads,
            head_dim=model.head_dim,
            params_b=model.params_b,
            quant=cfg.quant,
            kv_format=cfg.kv_format,
            context_len=cfg.context_len,
            attn_type=attn_type,
            n_gpu_layers=cfg.n_gpu_layers,
            moe_active_ratio=moe_ratio,
        )
        cfg.fits = budget.fits
        cfg.ram_weights_gb = budget.ram_weights_gb
        cfg.ram_kv_gb = budget.ram_kv_gb
        cfg.ram_total_gb = budget.ram_total_gb
        cfg.ram_available_gb = budget.ram_available_gb
        if not cfg.fits:
            cfg.notes = (
                f"No entra en RAM: necesita {budget.ram_total_gb:.2f} GB, "
                f"disponible {RAM_DISPONIBLE_GB:.1f} GB"
            )
        validated.append(cfg)

    validated.sort(key=lambda c: (c.context_len, c.kv_format, c.flash_attn))
    return validated


def generate_matrix_for_models(
    model_names: Optional[List[str]] = None, **kwargs,
) -> dict:
    from .model_registry import MODEL_REGISTRY, list_models
    if model_names is None:
        model_names = list_models()
    result = {}
    for name in model_names:
        model = MODEL_REGISTRY.get(name)
        if model is None:
            continue
        result[name] = generate_matrix(model, **kwargs)
    return result


def summary_report(matrices: dict) -> str:
    lines = ["# Matriz de Tests - Resumen", ""]
    total = 0
    passed = 0
    for model_name, configs in matrices.items():
        lines.append(f"## {model_name}")
        lines.append(f"  Total configs: {len(configs)}")
        fits = [c for c in configs if c.fits]
        no_fit = [c for c in configs if not c.fits]
        lines.append(f"  OK Entran: {len(fits)}")
        lines.append(f"  NO Entran: {len(no_fit)}")
        if no_fit:
            lines.append("  Detalle:")
            for c in no_fit:
                lines.append(f"    - {c}")
        if fits:
            lines.append("  Orden ejecucion:")
            for c in fits:
                lines.append(f"    {c}")
        lines.append("")
        total += len(configs)
        passed += len(fits)
    lines.append(f"---\nTotal: {total} configuraciones, {passed} ejecutables.")
    return "\n".join(lines)


if __name__ == "__main__":
    from .model_registry import MODEL_REGISTRY
    model = MODEL_REGISTRY["Qwen2.5-7B-1M"]
    matrix = generate_matrix(model)
    print(summary_report({"Qwen2.5-7B-1M": matrix}))

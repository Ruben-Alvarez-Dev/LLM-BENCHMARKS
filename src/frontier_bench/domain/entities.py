"""Entidades del dominio — puras, sin I/O, sin dependencias de plataforma.

Regla: este módulo solo importa stdlib (dataclasses, enum, typing).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ───────────────────────── enums ─────────────────────────

class ArchKind(str, Enum):
    """Clase de arquitectura de atención — determina el modelo de memoria KV."""
    DENSE_GQA = "dense_gqa"        # transformer clásico (Llama, Qwen2.5, Mistral)
    HYBRID_LINEAR = "hybrid"       # lineal+full intercalado (Qwen3.5 GDN, Granite-H, Falcon-H1)
    SWA = "swa"                    # sliding-window intercalado (Gemma 3, gpt-oss)
    MLA = "mla"                    # latente comprimido (DeepSeek V2/V3)
    RECURRENT = "recurrent"        # puro sin KV (RWKV, Mamba puro)


class Platform(str, Enum):
    METAL = "metal"
    CUDA = "cuda"
    CPU = "cpu"
    ROCM = "rocm"


class CellStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    OK = "ok"
    FAILED = "failed"
    SKIPPED_BUDGET = "skipped_budget"
    SKIPPED_UNSUPPORTED = "skipped_unsupported"


class LoadProfile(str, Enum):
    """Perfiles de carga (specs/05 absorbida)."""
    S = "single"          # single-stream clásico
    A = "agents_poisson"  # 8 streams cortos, llegada Poisson
    B = "multiturn"       # multi-turno con prefijo compartido (detecta reprefill)
    C = "asymmetric"      # 1 stream largo + resto idle (detecta bug kvu)
    D = "soak"            # sostenido 30-60 min (térmico, leaks, crashes)
    E = "quality"         # tool-calling JSON bajo carga


# ───────────────────────── hardware ─────────────────────────

@dataclass(frozen=True)
class MachineFacts:
    """Identidad y límites de una máquina. SIEMPRE viaja con cada resultado (fallo A4 de v1)."""
    machine_id: str                # p.ej. "mini-m1-16g"
    hostname: str
    chip: str
    ram_gb: float
    platform: Platform
    wired_limit_gb: Optional[float] = None   # límite Metal (sysctl); None => ~2/3 RAM
    bandwidth_gbs: Optional[float] = None    # informativo (M1: 68, M1 Max: 400)
    os_reserve_gb: float = 3.0

    @property
    def gpu_budget_gb(self) -> float:
        """RAM utilizable por el engine (pesos+KV+buffers)."""
        wired = self.wired_limit_gb if self.wired_limit_gb else self.ram_gb * (2 / 3)
        return min(wired, self.ram_gb - self.os_reserve_gb)


# ───────────────────────── modelo ─────────────────────────

@dataclass(frozen=True)
class KvProfile:
    """Parámetros que determinan el coste de memoria por arquitectura.

    Para HYBRID: n_layers = total, full_attn_layers = capas con KV real,
    recurrent_state_mb = estado fijo por slot (todas las capas lineales).
    Para SWA: swa_window y global_layers (las demás usan ventana).
    Para MLA: mla_latent_dim sustituye a kv_heads*head_dim.
    """
    arch: ArchKind
    n_layers: int
    kv_heads: int = 0
    head_dim: int = 0
    full_attn_layers: Optional[int] = None
    recurrent_state_mb: float = 0.0
    swa_window: int = 0
    swa_global_layers: int = 0
    mla_latent_dim: int = 0


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    name: str
    params_b: float
    quant: str
    file_bytes: int                 # tamaño REAL del fichero (fallo A6: nada de tablas teóricas)
    kv: KvProfile
    context_native: int             # ctx máximo sin rope-scaling
    context_max: int                # con YaRN/rope si el modelo lo declara
    file_path: Optional[str] = None
    file_hash: Optional[str] = None

    def rope_extrapolated(self, ctx: int) -> bool:
        return ctx > self.context_native


# ───────────────────────── engine y técnicas ─────────────────────────

@dataclass(frozen=True)
class EngineInfo:
    """Provenance completo (fallo A5 de v1): sin esto la fila no es reproducible."""
    engine_id: str                  # "llamacpp" | "rotorquant" | "mlx" | "omlx" | "vllm_cuda"...
    version: str
    commit: Optional[str] = None
    build_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Technique:
    """Técnica declarada — exista o no adapter en esta plataforma (abstracción multi-plataforma)."""
    technique_id: str
    dims: dict = field(default_factory=dict)         # parámetros que inyecta en el engine
    supports: dict = field(default_factory=dict)     # engine_id -> platforms | "native" | nota
    constraints: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    def supported_on(self, engine_id: str, platform: Platform) -> bool:
        entry = self.supports.get(engine_id)
        if entry is None:
            return False
        if entry == "native":
            return True
        if isinstance(entry, (list, tuple, set)):
            return platform.value in entry
        if isinstance(entry, dict):
            val = entry.get(platform.value)
            return bool(val) and val == "native"
        return False


# ───────────────────────── celdas y runs ─────────────────────────

CONTEXT_LADDER = (4_096, 8_192, 16_384, 32_768, 65_536, 131_072, 262_144,
                  524_288, 716_800, 1_048_576)   # 512K añadido 2026-06-06 (auditoría)
DEPTH_PCTS = (0, 50, 90)
SLOT_LADDER = (1, 2, 4, 8)


@dataclass
class CellSpec:
    """Una celda = un punto del espacio de prueba."""
    machine_id: str
    engine_id: str
    model_id: str
    ctx: int
    depth_pct: int
    slots: int
    profile: LoadProfile
    techniques: tuple[str, ...] = ()
    protocol: str = "v2"
    status: CellStatus = CellStatus.PENDING
    skip_reason: str = ""

    @property
    def depth_tokens(self) -> int:
        return int(self.ctx * self.depth_pct / 100)


@dataclass(frozen=True)
class Measurement:
    metric: str        # "decode_tps" | "prefill_tps" | "ttft_ms" | "rss_peak_gb" | ...
    value: float
    unit: str
    run_index: int = 0


@dataclass
class Run:
    """Una ejecución de una celda (n repeticiones dentro).

    valid/interference: validez ambiental (domain.environment) — un run con RAM
    insuficiente o procesos interfiriendo SE GUARDA pero no puntúa en rankings
    ni veredictos. Requisito de Rubén 2026-06-06.
    """
    cell_key: str
    n_reps: int
    measurements: list[Measurement] = field(default_factory=list)
    raw_ref: Optional[str] = None   # ruta al crudo comprimido
    error: Optional[str] = None
    valid: bool = True
    interference: tuple[str, ...] = ()

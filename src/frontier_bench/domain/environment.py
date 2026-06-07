"""Validez ambiental — un resultado solo cuenta si el entorno no interfirió.

Requisito (Rubén, 2026-06-06): "el sistema debe ver si hay o no hay más procesos,
protegerse o al menos avisar, y no dar el test por bueno si algo interfiere o no
ha tenido RAM suficiente".

Reglas puras: reciben snapshots del entorno (antes/después) y emiten un
ValidityReport. Los runs inválidos SE GUARDAN (histórico append-only) pero
marcados valid=0 con motivos — excluidos de rankings y veredictos por defecto.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProcessInfo:
    name: str
    rss_gb: float


@dataclass(frozen=True)
class EnvSnapshot:
    free_ram_gb: float            # libre + inactiva (recuperable)
    total_ram_gb: float
    swap_used_gb: float
    load_avg_1m: float
    n_cores: int
    heavy_processes: tuple[ProcessInfo, ...] = ()   # ajenos al benchmark, RSS > umbral


@dataclass(frozen=True)
class ValidityReport:
    valid: bool
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


# Umbrales (versionados con el protocolo; ajustables por config)
HEAVY_PROC_GB = 2.0          # proceso ajeno con más de esto => interferencia
SWAP_DELTA_GB = 0.25         # si el run provoca swap, la medición no es fiable
LOAD_FACTOR = 1.25           # load medio > cores*factor => contención de CPU
RAM_HEADROOM = 1.10          # se exige requerido × 10% de colchón


def assess(before: EnvSnapshot, after: EnvSnapshot | None,
           required_gb: float) -> ValidityReport:
    reasons: list[str] = []
    warnings: list[str] = []

    if before.free_ram_gb < required_gb * RAM_HEADROOM:
        reasons.append(
            f"ram_insuficiente: libres {before.free_ram_gb:.1f} GiB < "
            f"requeridos {required_gb:.1f} GiB (+10% colchón)")

    if before.heavy_processes:
        listing = ", ".join(f"{p.name}({p.rss_gb:.1f}G)" for p in before.heavy_processes[:5])
        reasons.append(f"procesos_pesados_activos: {listing}")

    if before.load_avg_1m > before.n_cores * LOAD_FACTOR:
        reasons.append(
            f"contencion_cpu: load {before.load_avg_1m:.1f} > {before.n_cores} cores")
    elif before.load_avg_1m > before.n_cores:
        warnings.append(f"load_alto: {before.load_avg_1m:.1f}")

    if after is not None:
        swap_delta = after.swap_used_gb - before.swap_used_gb
        if swap_delta > SWAP_DELTA_GB:
            reasons.append(f"swap_durante_run: +{swap_delta:.2f} GiB")
        new_heavy = {p.name for p in after.heavy_processes} - \
                    {p.name for p in before.heavy_processes}
        if new_heavy:
            reasons.append(f"procesos_aparecidos_durante_run: {', '.join(sorted(new_heavy))}")

    return ValidityReport(valid=not reasons, reasons=tuple(reasons),
                          warnings=tuple(warnings))

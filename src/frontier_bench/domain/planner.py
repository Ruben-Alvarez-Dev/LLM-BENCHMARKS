"""Planner — expande los ejes de una campaña en celdas y las poda con motivo registrado.

Nada se descarta en silencio (fallos A1/A7 de v1): cada combinación imposible queda como
celda SKIPPED_* con su razón, visible en la matriz de resultados. Así, al correr la misma
campaña en otra plataforma (p.ej. CUDA), las columnas se llenan solas.

Puro: recibe máquinas, modelos, engines y técnicas como datos; no toca disco ni red.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import Iterable, Mapping

from .entities import (CellSpec, CellStatus, EngineInfo, LoadProfile, MachineFacts,
                       ModelSpec, Platform, Technique)
from .kv_model import budget


@dataclass(frozen=True)
class CampaignAxes:
    machines: tuple[str, ...]
    engines: tuple[str, ...]
    models: tuple[str, ...]
    contexts: tuple[int, ...]
    depth_pcts: tuple[int, ...] = (0, 50, 90)
    slot_ladder: tuple[int, ...] = (1, 2, 4, 8)
    profiles: tuple[LoadProfile, ...] = (LoadProfile.S,)
    technique_sets: tuple[tuple[str, ...], ...] = ((),)
    cache_type: str = "q8_0"


@dataclass
class PlanResult:
    cells: list[CellSpec] = field(default_factory=list)

    @property
    def pending(self) -> list[CellSpec]:
        return [c for c in self.cells if c.status is CellStatus.PENDING]

    def skipped(self, status: CellStatus) -> list[CellSpec]:
        return [c for c in self.cells if c.status is status]

    def summary(self) -> dict:
        out: dict[str, int] = {}
        for c in self.cells:
            out[c.status.value] = out.get(c.status.value, 0) + 1
        return out


def _techniques_ok(tech_ids: tuple[str, ...], registry: Mapping[str, Technique],
                   engine_id: str, platform: Platform) -> tuple[bool, str]:
    for tid in tech_ids:
        tech = registry.get(tid)
        if tech is None:
            return False, f"técnica desconocida: {tid}"
        if not tech.supported_on(engine_id, platform):
            return False, f"{tid} no soportada en {engine_id}/{platform.value}"
    return True, ""


def plan(axes: CampaignAxes,
         machines: Mapping[str, MachineFacts],
         models: Mapping[str, ModelSpec],
         engines: Mapping[str, EngineInfo],
         techniques: Mapping[str, Technique],
         engines_caps: Mapping[str, frozenset] | None = None) -> PlanResult:
    """Producto cartesiano podado. Reglas de poda, en orden:
    1) técnica no soportada en engine/plataforma → SKIPPED_UNSUPPORTED
    2) profundidad/slots incoherentes con el perfil → se omite la combinación (no es celda)
    3) presupuesto de RAM → SKIPPED_BUDGET con desglose
    """
    result = PlanResult()
    for m_id, e_id, mod_id, ctx, depth, slots, profile, techs in product(
            axes.machines, axes.engines, axes.models, axes.contexts,
            axes.depth_pcts, axes.slot_ladder, axes.profiles, axes.technique_sets):

        machine, model = machines[m_id], models[mod_id]

        # coherencia: perfiles de concurrencia no aplican a slots=1 y viceversa
        if profile is LoadProfile.S and slots != 1:
            continue
        if profile is not LoadProfile.S and slots == 1:
            continue
        # profundidad solo se barre en single-stream; en concurrencia la fija el perfil
        if profile is not LoadProfile.S and depth != 0:
            continue

        cell = CellSpec(machine_id=m_id, engine_id=e_id, model_id=mod_id, ctx=ctx,
                        depth_pct=depth, slots=slots, profile=profile, techniques=techs)

        ok, why = _techniques_ok(techs, techniques, e_id, machine.platform)
        if not ok:
            cell.status, cell.skip_reason = CellStatus.SKIPPED_UNSUPPORTED, why
            result.cells.append(cell)
            continue

        # routing del censo 2026-06-06: ctx > nativo exige rope_yarn en el engine
        # (llama-bench NO lo tiene → esas celdas van a llama-server)
        if engines_caps is not None and model.rope_extrapolated(ctx):
            caps = engines_caps.get(e_id, frozenset())
            if "rope_yarn" not in caps:
                cell.status = CellStatus.SKIPPED_UNSUPPORTED
                cell.skip_reason = (f"ctx {ctx} > nativo {model.context_native}: "
                                    f"requiere rope_yarn y {e_id} no lo soporta "
                                    f"(enrutar a llama-server)")
                result.cells.append(cell)
                continue

        b = budget(machine, model, ctx, slots, axes.cache_type)
        if not b.fits:
            cell.status, cell.skip_reason = CellStatus.SKIPPED_BUDGET, b.reason
            result.cells.append(cell)
            continue

        if model.rope_extrapolated(ctx):
            cell.skip_reason = "rope_extrapolated"  # no salta: se marca (700K/1M con YaRN)

        result.cells.append(cell)
    return result

"""Scheduler — selección granular y repetición sobre histórico append-only.

Principio "enciclopedia": nada se pisa. Cada ejecución es un run nuevo; repetir 10 veces
el mismo test, re-correr una sola celda concreta, o re-lanzar todo, son el MISMO mecanismo:
un RunRequest = filtros + repeats + force.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Optional

from .entities import CellSpec, CellStatus, LoadProfile


@dataclass(frozen=True)
class CellFilter:
    """Filtros por cualquier dimensión. None = no filtra. Composición = AND."""
    machine_ids: Optional[frozenset[str]] = None
    engine_ids: Optional[frozenset[str]] = None
    model_ids: Optional[frozenset[str]] = None
    ctxs: Optional[frozenset[int]] = None
    slots: Optional[frozenset[int]] = None
    profiles: Optional[frozenset[LoadProfile]] = None
    techniques_any: Optional[frozenset[str]] = None   # celda que use ALGUNA de estas
    protocols: Optional[frozenset[str]] = None
    statuses: Optional[frozenset[CellStatus]] = None
    only_without_runs: bool = False
    only_failed: bool = False

    def matches(self, cell: CellSpec, run_count: int = 0) -> bool:
        checks = (
            (self.machine_ids, cell.machine_id),
            (self.engine_ids, cell.engine_id),
            (self.model_ids, cell.model_id),
            (self.ctxs, cell.ctx),
            (self.slots, cell.slots),
            (self.profiles, cell.profile),
            (self.protocols, cell.protocol),
            (self.statuses, cell.status),
        )
        for allowed, value in checks:
            if allowed is not None and value not in allowed:
                return False
        if self.techniques_any is not None and not (set(cell.techniques) & self.techniques_any):
            return False
        if self.only_without_runs and run_count > 0:
            return False
        if self.only_failed and cell.status is not CellStatus.FAILED:
            return False
        return True


@dataclass(frozen=True)
class RunRequest:
    filters: CellFilter = field(default_factory=CellFilter)
    repeats: int = 1          # 10 => corre la selección 10 veces
    force: bool = False       # True => re-ejecuta aunque ya existan runs
    note: str = ""            # por qué (queda en action_log)


@dataclass(frozen=True)
class WorkItem:
    cell: CellSpec
    rep_index: int            # 0..repeats-1
    requested_by: str = ""


def build_work(cells: Iterable[CellSpec],
               run_counts: Mapping[str, int],
               request: RunRequest,
               cell_key_fn: Callable[[CellSpec], str]) -> list[WorkItem]:
    """Convierte un RunRequest en cola de trabajo determinista.

    - Las celdas SKIPPED_* nunca generan trabajo (su motivo ya es el resultado).
    - Sin force: solo celdas que el filtro acepte Y que necesiten runs (only_without_runs
      o cualquier celda si repeats>0 — la semántica de "ya probado" la decide el filtro).
    - Con force: el histórico es irrelevante para la selección.
    """
    out: list[WorkItem] = []
    for cell in cells:
        if cell.status in (CellStatus.SKIPPED_BUDGET, CellStatus.SKIPPED_UNSUPPORTED):
            continue
        count = run_counts.get(cell_key_fn(cell), 0)
        if not request.filters.matches(cell, run_count=count):
            continue
        if not request.force and count > 0 and request.filters.only_without_runs:
            continue
        for rep in range(max(1, request.repeats)):
            out.append(WorkItem(cell=cell, rep_index=rep, requested_by=request.note))
    return out

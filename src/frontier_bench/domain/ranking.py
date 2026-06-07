"""Ranking incremental — leaderboards en caliente mientras corre la campaña.

Cada vez que aterriza un run, el ranking de cada métrica se recalcula y se publica
como evento RANKING_UPDATED. La pantalla ve la clasificación reordenarse en vivo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Optional

from .entities import Run
from .events import Event, EventBus, EventKind

# métrica -> mayor es mejor?
METRIC_DIRECTION = {
    "decode_tps": True,
    "prefill_tps": True,
    "aggregate_tps": True,
    "per_stream_tps_p50": True,
    "ttft_ms_p95": False,
    "rss_peak_gb": False,
    "json_valid_pct": True,
    "needle_recall": True,
}


@dataclass
class RankingEntry:
    subject: str               # p.ej. "Qwen3.5-9B @ mini-m1-16g | ctx32K d50 s1"
    value: float
    n_runs: int


@dataclass
class Leaderboard:
    metric: str
    entries: list[RankingEntry] = field(default_factory=list)

    def top(self, n: int = 10) -> list[RankingEntry]:
        return self.entries[:n]


class LiveRanking:
    """Acumula medianas por (métrica, sujeto) y mantiene leaderboards ordenados."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._values: dict[str, dict[str, list[float]]] = {}   # metric -> subject -> samples
        self._bus = bus

    @staticmethod
    def subject_of(run: Run) -> str:
        # cell_key ya codifica todas las dimensiones; legible tal cual
        return run.cell_key

    def ingest(self, run: Run) -> list[Leaderboard]:
        # los runs inválidos (interferencia ambiental) NO puntúan jamás
        if not run.valid:
            return []
        changed: set[str] = set()
        subject = self.subject_of(run)
        for m in run.measurements:
            if m.metric not in METRIC_DIRECTION:
                continue
            self._values.setdefault(m.metric, {}).setdefault(subject, []).append(m.value)
            changed.add(m.metric)

        boards = [self.leaderboard(metric) for metric in sorted(changed)]
        if self._bus:
            for b in boards:
                self._bus.publish(Event(EventKind.RANKING_UPDATED, {
                    "metric": b.metric,
                    "top": [{"subject": e.subject, "value": e.value, "n": e.n_runs}
                            for e in b.top(10)],
                }))
        return boards

    def leaderboard(self, metric: str) -> Leaderboard:
        higher_better = METRIC_DIRECTION.get(metric, True)
        entries = [RankingEntry(subject=s, value=median(vals), n_runs=len(vals))
                   for s, vals in self._values.get(metric, {}).items()]
        entries.sort(key=lambda e: e.value, reverse=higher_better)
        return Leaderboard(metric=metric, entries=entries)

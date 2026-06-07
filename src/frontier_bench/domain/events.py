"""Eventos del dominio — el stream de tiempo real es canal-agnóstico.

El dominio publica Events tipados; QUÉ transporte los lleva (SSE, WebSocket, stdout,
lo que sea mañana) es problema de un adapter de NotifyPort. Mismo stream para
frontend, CLI --follow y logging.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable


class EventKind(str, Enum):
    HOST_PROFILED = "host_profiled"
    CAMPAIGN_PLANNED = "campaign_planned"
    CELL_STARTED = "cell_started"
    REP_PROGRESS = "rep_progress"        # muestras 1Hz: tok/s instantáneo, RSS, tokens
    MEASUREMENT = "measurement"
    CELL_DONE = "cell_done"
    CELL_FAILED = "cell_failed"
    RANKING_UPDATED = "ranking_updated"
    CAMPAIGN_DONE = "campaign_done"


@dataclass(frozen=True)
class Event:
    kind: EventKind
    payload: dict = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


@runtime_checkable
class EventSink(Protocol):
    def publish(self, event: Event) -> None: ...


class EventBus:
    """Bus mínimo síncrono: el dominio publica, los adapters se suscriben."""

    def __init__(self) -> None:
        self._sinks: list[EventSink] = []

    def subscribe(self, sink: EventSink) -> None:
        self._sinks.append(sink)

    def publish(self, event: Event) -> None:
        for sink in self._sinks:
            sink.publish(event)

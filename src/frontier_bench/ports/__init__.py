"""Puertos — contratos entre el dominio y los adaptadores.

Solo Protocols y dataclasses puras. Los adaptadores (engines, runners, sondas,
storage, web) implementan estos contratos; el dominio no conoce ninguna implementación.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Protocol, runtime_checkable

from ..domain.entities import (CellSpec, EngineInfo, MachineFacts, Measurement,
                               ModelSpec, Run)


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float


@runtime_checkable
class RunnerPort(Protocol):
    """Ejecuta comandos en una máquina (local o remota vía SSH/Tailscale)."""
    def probe(self) -> MachineFacts: ...
    def exec(self, cmd: list[str], timeout_s: float, env: Optional[dict] = None) -> ExecResult: ...
    def put_file(self, local_path: str, remote_path: str) -> None: ...
    def get_file(self, remote_path: str, local_path: str) -> None: ...


@runtime_checkable
class EnginePort(Protocol):
    """Un motor de inferencia en una máquina concreta."""
    def info(self) -> EngineInfo: ...
    def capabilities(self) -> set[str]: ...
    def run_cell(self, cell: CellSpec, model: ModelSpec) -> Run: ...


@dataclass(frozen=True)
class ServerHandle:
    base_url: str
    pid: int


@runtime_checkable
class ServingEnginePort(EnginePort, Protocol):
    """Engine capaz de servir API OpenAI-compatible para perfiles de concurrencia."""
    def serve(self, cell: CellSpec, model: ModelSpec) -> ServerHandle: ...
    def stop(self, handle: ServerHandle) -> None: ...


@runtime_checkable
class CorpusPort(Protocol):
    """Texto real determinista (corrige el fallo A2: nada de relleno repetido)."""
    def text_tokens(self, n_tokens: int, seed: int) -> str: ...


@runtime_checkable
class ProbePort(Protocol):
    """Muestreo 1Hz de RSS/RAM/temperatura durante un run."""
    def start(self) -> None: ...
    def stop(self) -> list[Measurement]: ...


@runtime_checkable
class LoadGenPort(Protocol):
    """Genera los perfiles de carga A-E contra un ServerHandle."""
    def run_profile(self, handle: ServerHandle, cell: CellSpec) -> list[Measurement]: ...


@runtime_checkable
class StoragePort(Protocol):
    def save_run(self, run: Run) -> None: ...
    def save_cells(self, cells: Iterable[CellSpec]) -> None: ...
    def log_action(self, actor: str, action: str, payload: dict) -> None: ...

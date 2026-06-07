"""Battery runner — orquesta la batería de UN modelo de principio a fin.

Por cada celda de concurrencia: pre-flight ambiental → serve → perfil de carga →
post-flight → métricas → Run (válido o no). Al CERRAR la batería del modelo:
limpieza impoluta (CleanupManifest) ANTES de pasar al siguiente — política de
Rubén 2026-06-06. Todo via puertos: testeable 100% en seco con fakes.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .entities import CellSpec, CellStatus, Measurement, ModelSpec, Run
from .environment import EnvSnapshot, assess
from .events import Event, EventBus, EventKind
from .loadmetrics import compute
from .maintenance import CleanupManifest, CleanupReport


@dataclass
class BatteryResult:
    model_id: str
    runs: list[Run] = field(default_factory=list)
    cleanup: Optional[CleanupReport] = None

    @property
    def pristine(self) -> bool:
        return self.cleanup is not None and self.cleanup.pristine


def wait_recovery(env_probe: Callable[[], EnvSnapshot], baseline_free_gb: float,
                  tolerance_gb: float = 1.5, timeout_s: float = 120.0,
                  sleep_fn: Callable[[float], None] = time.sleep) -> float:
    """Aislamiento entre celdas: espera a que la RAM libre vuelva ~al baseline
    antes de la siguiente prueba (el engine anterior debe haber soltado todo).
    Devuelve los segundos esperados; si agota el timeout, el caller lo registra."""
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        if env_probe().free_ram_gb >= baseline_free_gb - tolerance_gb:
            return time.time() - t0
        sleep_fn(2.0)
    return time.time() - t0


def run_battery(model: ModelSpec,
                cells: list[CellSpec],
                serving_engine,                       # ServingEnginePort
                load_runner: Callable,                # (base_url, cell) -> (results, wall_s, texts)
                env_probe: Callable[[], EnvSnapshot],
                required_gb: float,
                bus: Optional[EventBus] = None,
                manifest: Optional[CleanupManifest] = None,
                force_env: bool = False,
                settle_tolerance_gb: float = 1.5,
                settle_timeout_s: float = 120.0,
                sleep_fn: Callable[[float], None] = time.sleep) -> BatteryResult:
    """Batería completa de un modelo. El manifest registra TODO lo creado;
    la limpieza es incondicional al final (try/finally)."""
    manifest = manifest or CleanupManifest(battery_id=f"battery-{model.model_id}")
    out = BatteryResult(model_id=model.model_id)
    emit = (lambda k, p: bus.publish(Event(k, p))) if bus else (lambda k, p: None)

    baseline = env_probe()          # estado limpio de referencia de TODA la batería
    first = True
    try:
        for cell in cells:
            # aislamiento: la celda anterior debe haber devuelto la RAM
            if not first:
                settled_s = wait_recovery(env_probe, baseline.free_ram_gb,
                                          settle_tolerance_gb, settle_timeout_s,
                                          sleep_fn)
                if env_probe().free_ram_gb < baseline.free_ram_gb - settle_tolerance_gb:
                    emit(EventKind.CELL_FAILED,
                         {"warn": f"RAM no recuperada tras {settled_s:.0f}s — "
                                  f"posible leak del engine anterior"})
            first = False
            emit(EventKind.CELL_STARTED, {"cell": f"{model.model_id} s{cell.slots} "
                                                  f"{cell.profile.value}"})
            env_before = env_probe()
            pre = assess(env_before, None, required_gb)
            if not pre.valid and not force_env:
                run = Run(cell_key="", n_reps=0, valid=False,
                          interference=pre.reasons,
                          error="preflight: entorno no válido")
                out.runs.append(run)
                emit(EventKind.CELL_FAILED, {"reasons": list(pre.reasons)})
                continue

            handle = None
            t0 = time.time()
            try:
                handle = serving_engine.serve(cell, model)
                results, wall_s, texts = load_runner(handle.base_url, cell)
            except Exception as e:  # noqa: BLE001
                run = Run(cell_key="", n_reps=0, error=f"serve/load: {e}")
                cell.status = CellStatus.FAILED
                out.runs.append(run)
                emit(EventKind.CELL_FAILED, {"error": str(e)[:200]})
                continue
            finally:
                if handle is not None:
                    serving_engine.stop(handle)

            env_after = env_probe()
            report = assess(env_before, env_after, required_gb)
            metrics = compute(results, wall_s,
                              expect_cached_prefix=(cell.profile.value == "multiturn"))
            run = Run(cell_key="", n_reps=len(results),
                      measurements=metrics.measurements,
                      valid=report.valid, interference=report.reasons)
            run.measurements.append(Measurement("wall_s", round(wall_s, 2), "s"))
            cell.status = CellStatus.OK
            out.runs.append(run)
            emit(EventKind.CELL_DONE, {"valid": run.valid,
                                       "n_requests": len(results)})
    finally:
        out.cleanup = manifest.cleanup()
        emit(EventKind.CAMPAIGN_DONE, {
            "model": model.model_id,
            "pristine": out.cleanup.pristine,
            "deleted": len(out.cleanup.deleted),
            "evidence_kept": len(out.cleanup.kept_evidence)})
    return out

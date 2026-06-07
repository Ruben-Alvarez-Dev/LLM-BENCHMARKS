"""Executor — consume la cola de RunRequests (UI/MCP/CLI) y la convierte en plan.

Modo `dry` (el único permitido mientras Rubén tenga la RAM ocupada): lee la cola,
construye el plan de trabajo (scheduler), lo registra y lo devuelve — SIN ejecutar.
Modo real (cuando se desbloquee): mismo plan → battery runner con pre-flight,
aprobación de updates pendiente y limpieza impoluta. La cola es idempotente:
cada request se marca consumida con referencia a su plan.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .scheduler import CellFilter, RunRequest, build_work


@dataclass
class ExecutorReport:
    consumed_ids: list[int] = field(default_factory=list)
    planned_items: int = 0
    plans: list[dict] = field(default_factory=list)
    mode: str = "dry"


def _filters_from_payload(p: dict) -> CellFilter:
    f = p.get("filters", {}) or {}
    return CellFilter(
        model_ids=frozenset([f["model"]]) if f.get("model") else None,
        machine_ids=frozenset([f["machine"]]) if f.get("machine") else None,
        ctxs=frozenset([int(f["ctx"])]) if f.get("ctx") else None,
        only_failed=bool(f.get("only_failed", False)),
    )


def pending_requests(store) -> list[tuple[int, dict]]:
    """Cola = run_request_queued sin run_request_consumed posterior que lo refiera."""
    queued = store.query(
        "SELECT id, payload_json FROM action_log WHERE action='run_request_queued' "
        "ORDER BY id")
    consumed = {json.loads(r[1]).get("queued_id")
                for r in store.query(
                    "SELECT id, payload_json FROM action_log "
                    "WHERE action='run_request_consumed'")}
    return [(rid, json.loads(pj)) for rid, pj in queued if rid not in consumed]


def execute_once(store, cells, cell_key_fn, run_counts=None, dry: bool = True,
                 battery_fn=None) -> ExecutorReport:
    """Una pasada por la cola. dry=True: solo planifica y registra (modo actual).
    dry=False: requiere battery_fn (inyectado) y ejecuta de verdad."""
    report = ExecutorReport(mode="dry" if dry else "real")
    run_counts = run_counts or {}
    for rid, payload in pending_requests(store):
        request = RunRequest(filters=_filters_from_payload(payload),
                             repeats=int(payload.get("repeats", 1)),
                             force=bool(payload.get("force", False)),
                             note=payload.get("note", ""))
        work = build_work(cells, run_counts, request, cell_key_fn)
        plan = {"queued_id": rid, "items": len(work),
                "cells": sorted({cell_key_fn(w.cell) for w in work})[:50],
                "repeats": request.repeats, "note": request.note}
        report.plans.append(plan)
        report.planned_items += len(work)
        if not dry and battery_fn is not None and work:
            battery_fn(work)        # gated: pre-flight ambiental dentro de battery
        store.log_action("executor", "run_request_consumed", plan)
        report.consumed_ids.append(rid)
    return report

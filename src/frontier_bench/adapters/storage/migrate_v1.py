"""Migración v1 → v2: importa data/benchmark_results.db al esquema nuevo.

Los resultados v1 se conservan como celdas/runs con protocol='v1' y depth_pct=0
(la campaña v1 medía decode con caché vacía — fallo A1 — así que ESO es lo que
esas filas certifican; el flag lo deja explícito para siempre).

Uso:
    python -m frontier_bench.adapters.storage.migrate_v1 <v1.db> <v2.db>
"""
from __future__ import annotations

import json
import sqlite3
import sys

from ...domain.entities import CellSpec, CellStatus, LoadProfile, Measurement, Run
from .sqlite_store import SqliteStore, cell_key

V1_HW_TO_MACHINE = {
    "m1-mini-16gb": "mini-m1-16g",
    "m1-max-32gb": "mbp-m1max-32g",
    "macbook-pro-m1-max": "mbp-m1max-32g",
}


def migrate(v1_path: str, v2_path: str) -> dict:
    src = sqlite3.connect(v1_path)
    src.row_factory = sqlite3.Row
    store = SqliteStore(v2_path)
    stats = {"models": 0, "cells": 0, "runs": 0, "measurements": 0}

    models = {r["id"]: dict(r) for r in src.execute("SELECT * FROM models")}
    for m in models.values():
        store._conn.execute(
            """INSERT OR IGNORE INTO models
               (model_id,name,params_b,quant,file_bytes,arch,kv_profile_json,
                context_native,context_max)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (m["name"], m["name"], m["params_b"] or 0.0, m["quant"] or "?",
             0, m["architecture"] or "unknown",
             json.dumps({"v1_attention": m["attention"]}),
             m["context_max"] or 0, m["context_max"] or 0))
        stats["models"] += 1

    for r in src.execute("SELECT * FROM test_runs"):
        m = models.get(r["model_id"], {"name": f"unknown-{r['model_id']}"})
        machine = V1_HW_TO_MACHINE.get(r["hardware"] or "", r["hardware"] or "unknown")
        techs = []
        if r["flash_attn"]:
            techs.append("flash_attn")
        kv_fmt = (r["kv_format"] or "f16").lower()
        if kv_fmt in ("q8_0", "q4_0"):
            techs.append("kv_q8" if kv_fmt == "q8_0" else "kv_q4")

        cell = CellSpec(machine_id=machine, engine_id="llamacpp@v1-unknown",
                        model_id=m["name"], ctx=r["context_len"] or 0, depth_pct=0,
                        slots=1, profile=LoadProfile.S, techniques=tuple(techs),
                        protocol="v1",
                        status=CellStatus.OK if r["status"] == "ok" else CellStatus.FAILED,
                        skip_reason="")
        store.save_cells([cell], campaign_id="v1-import")
        stats["cells"] += 1

        meas = []
        for metric, col, unit in (("decode_tps", "decode_speed", "tok/s"),
                                  ("prefill_tps", "prefill_speed", "tok/s"),
                                  ("load_time_s", "load_time_s", "s"),
                                  ("ram_observed_gb", "ram_total_observed_gb", "GiB"),
                                  ("ram_estimated_gb", "ram_estimate_gb", "GiB")):
            val = r[col]
            if val is not None:
                meas.append(Measurement(metric=metric, value=float(val), unit=unit))
        run = Run(cell_key=cell_key(cell), n_reps=1, measurements=meas,
                  raw_ref=None, error=r["error"])
        store.save_run(run)
        stats["runs"] += 1
        stats["measurements"] += len(meas)

    store.log_action("migrate_v1", "import", {"source": v1_path, **stats})
    store.close()
    src.close()
    return stats


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    print(json.dumps(migrate(sys.argv[1], sys.argv[2]), indent=2))

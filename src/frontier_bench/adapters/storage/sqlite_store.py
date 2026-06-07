"""Adapter de almacenamiento — SQLite WAL. Implementa StoragePort.

Conserva el patrón de atomic action log de specs v1. Las medidas derivan de crudos
re-parseables (raw_ref), nunca se sobreescriben: parser nuevo => filas nuevas con versión.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Iterable

from ...domain.entities import CellSpec, Measurement, Run

SCHEMA = """
CREATE TABLE IF NOT EXISTS machines (
  machine_id TEXT PRIMARY KEY, hostname TEXT, chip TEXT, ram_gb REAL,
  platform TEXT, wired_limit_gb REAL, bandwidth_gbs REAL, facts_json TEXT
);
CREATE TABLE IF NOT EXISTS engines (
  engine_key TEXT PRIMARY KEY,            -- engine_id@version+commit
  engine_id TEXT, version TEXT, commit_sha TEXT, build_flags TEXT
);
CREATE TABLE IF NOT EXISTS models (
  model_id TEXT PRIMARY KEY, name TEXT, params_b REAL, quant TEXT,
  file_bytes INTEGER, file_hash TEXT, arch TEXT, kv_profile_json TEXT,
  context_native INTEGER, context_max INTEGER, file_path TEXT
);
CREATE TABLE IF NOT EXISTS campaigns (
  campaign_id TEXT PRIMARY KEY, name TEXT, created_at TEXT, axes_json TEXT, status TEXT
);
CREATE TABLE IF NOT EXISTS cells (
  cell_key TEXT PRIMARY KEY, campaign_id TEXT,
  machine_id TEXT, engine_key TEXT, model_id TEXT,
  ctx INTEGER, depth_pct INTEGER, slots INTEGER, profile TEXT,
  techniques_json TEXT, protocol TEXT DEFAULT 'v2',
  status TEXT, skip_reason TEXT,
  FOREIGN KEY(campaign_id) REFERENCES campaigns(campaign_id)
);
CREATE TABLE IF NOT EXISTS runs (
  run_id INTEGER PRIMARY KEY AUTOINCREMENT,
  cell_key TEXT, n_reps INTEGER, raw_ref TEXT, error TEXT, created_at TEXT,
  valid INTEGER DEFAULT 1, interference_json TEXT DEFAULT '[]',
  FOREIGN KEY(cell_key) REFERENCES cells(cell_key)
);
CREATE TABLE IF NOT EXISTS measurements (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER, metric TEXT, value REAL, unit TEXT, run_index INTEGER,
  parser_version TEXT DEFAULT 'v2.0',
  FOREIGN KEY(run_id) REFERENCES runs(run_id)
);
CREATE TABLE IF NOT EXISTS verdicts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  rule TEXT, rule_version TEXT, subject_json TEXT, result TEXT,
  evidence_json TEXT, created_at TEXT
);
CREATE TABLE IF NOT EXISTS action_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT, actor TEXT, action TEXT, payload_json TEXT, state TEXT DEFAULT 'committed'
);
CREATE INDEX IF NOT EXISTS idx_cells_campaign ON cells(campaign_id);
CREATE INDEX IF NOT EXISTS idx_cells_status ON cells(status);
CREATE INDEX IF NOT EXISTS idx_meas_run ON measurements(run_id);
"""


def cell_key(c: CellSpec) -> str:
    techs = ",".join(c.techniques) or "none"
    return (f"{c.machine_id}|{c.engine_id}|{c.model_id}|ctx{c.ctx}|d{c.depth_pct}"
            f"|s{c.slots}|{c.profile.value}|{techs}|{c.protocol}")


class SqliteStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        # migración suave para BDs creadas antes de la validez ambiental
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(runs)")}
        if "valid" not in cols:
            self._conn.execute("ALTER TABLE runs ADD COLUMN valid INTEGER DEFAULT 1")
            self._conn.execute("ALTER TABLE runs ADD COLUMN interference_json TEXT DEFAULT '[]'")
        self._conn.commit()

    # ── StoragePort ──
    def save_cells(self, cells: Iterable[CellSpec], campaign_id: str = "adhoc") -> None:
        rows = [(cell_key(c), campaign_id, c.machine_id, c.engine_id, c.model_id,
                 c.ctx, c.depth_pct, c.slots, c.profile.value,
                 json.dumps(list(c.techniques)), c.protocol, c.status.value, c.skip_reason)
                for c in cells]
        self._conn.executemany(
            """INSERT OR REPLACE INTO cells
               (cell_key,campaign_id,machine_id,engine_key,model_id,ctx,depth_pct,slots,
                profile,techniques_json,protocol,status,skip_reason)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
        self._conn.commit()

    def save_run(self, run: Run) -> int:
        cur = self._conn.execute(
            "INSERT INTO runs (cell_key,n_reps,raw_ref,error,created_at,valid,interference_json)"
            " VALUES (?,?,?,?,?,?,?)",
            (run.cell_key, run.n_reps, run.raw_ref, run.error,
             time.strftime("%Y-%m-%dT%H:%M:%S"),
             int(run.valid), json.dumps(list(run.interference))))
        run_id = cur.lastrowid
        self._conn.executemany(
            "INSERT INTO measurements (run_id,metric,value,unit,run_index) VALUES (?,?,?,?,?)",
            [(run_id, m.metric, m.value, m.unit, m.run_index) for m in run.measurements])
        self._conn.commit()
        return int(run_id)

    def save_machine(self, facts, facts_json: dict | None = None) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO machines
               (machine_id,hostname,chip,ram_gb,platform,wired_limit_gb,bandwidth_gbs,facts_json)
               VALUES (?,?,?,?,?,?,?,?)""",
            (facts.machine_id, facts.hostname, facts.chip, facts.ram_gb,
             facts.platform.value, facts.wired_limit_gb, facts.bandwidth_gbs,
             json.dumps(facts_json or {})))
        self._conn.commit()

    def log_action(self, actor: str, action: str, payload: dict) -> None:
        self._conn.execute(
            "INSERT INTO action_log (ts,actor,action,payload_json) VALUES (?,?,?,?)",
            (time.strftime("%Y-%m-%dT%H:%M:%S"), actor, action, json.dumps(payload)))
        self._conn.commit()

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        return self._conn.execute(sql, params).fetchall()

    def close(self) -> None:
        self._conn.close()

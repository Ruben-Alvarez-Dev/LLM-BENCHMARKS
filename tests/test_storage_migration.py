"""Tests de storage y migración v1→v2 — usa BDs temporales (único test con I/O, en /tmp)."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from frontier_bench.adapters.storage.migrate_v1 import migrate
from frontier_bench.adapters.storage.sqlite_store import SqliteStore, cell_key
from frontier_bench.domain.entities import (CellSpec, CellStatus, LoadProfile,
                                            Measurement, Run)


def make_v1_db(path: str) -> None:
    conn = sqlite3.connect(path)
    conn.executescript("""
      CREATE TABLE models (id INTEGER PRIMARY KEY, name TEXT UNIQUE, params_b REAL,
        architecture TEXT, attention TEXT, context_max INTEGER, quant TEXT,
        hardware TEXT DEFAULT "m1-mini-16gb");
      CREATE TABLE test_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, model_id INTEGER,
        hardware TEXT DEFAULT "m1-mini-16gb", context_len INTEGER, kv_format TEXT,
        flash_attn INTEGER, status TEXT, load_time_s REAL, decode_speed REAL,
        prefill_speed REAL, total_time_ms REAL, prompt_tokens INTEGER,
        generated_tokens INTEGER, ram_estimate_gb REAL, ram_model_gb REAL,
        ram_context_gb REAL, ram_total_observed_gb REAL, error TEXT, timestamp TEXT);
    """)
    conn.execute("INSERT INTO models (id,name,params_b,architecture,attention,context_max,quant)"
                 " VALUES (1,'Qwen3.5-9B',9.0,'hybrid','gdn',262144,'Q4_K_M')")
    conn.execute("INSERT INTO test_runs (model_id,hardware,context_len,kv_format,flash_attn,"
                 "status,load_time_s,decode_speed,prefill_speed,ram_total_observed_gb)"
                 " VALUES (1,'m1-mini-16gb',16384,'q4_0',1,'ok',2.2,37.9,88.2,6.48)")
    conn.commit()
    conn.close()


class TestSqliteStore(unittest.TestCase):
    def test_roundtrip_cell_and_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = SqliteStore(Path(tmp) / "v2.db")
            cell = CellSpec(machine_id="mini-m1-16g", engine_id="llamacpp@b9309",
                            model_id="qwen35-9b", ctx=32768, depth_pct=50, slots=1,
                            profile=LoadProfile.S, techniques=("kv_q8", "flash_attn"))
            store.save_cells([cell], campaign_id="test")
            run = Run(cell_key=cell_key(cell), n_reps=3, measurements=[
                Measurement("decode_tps", 21.4, "tok/s", 0),
                Measurement("decode_tps", 21.9, "tok/s", 1),
                Measurement("decode_tps", 21.1, "tok/s", 2),
            ])
            run_id = store.save_run(run)
            rows = store.query("SELECT metric, value FROM measurements WHERE run_id=?", (run_id,))
            self.assertEqual(len(rows), 3)
            cells = store.query("SELECT status, depth_pct FROM cells")
            self.assertEqual(cells, [("pending", 50)])
            store.close()

    def test_cell_key_is_unique_per_dimension(self):
        a = CellSpec("m", "e", "mod", 4096, 0, 1, LoadProfile.S)
        b = CellSpec("m", "e", "mod", 4096, 50, 1, LoadProfile.S)
        self.assertNotEqual(cell_key(a), cell_key(b))


class TestMigrateV1(unittest.TestCase):
    def test_v1_rows_imported_with_protocol_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            v1 = str(Path(tmp) / "v1.db")
            v2 = str(Path(tmp) / "v2.db")
            make_v1_db(v1)
            stats = migrate(v1, v2)
            self.assertEqual(stats["models"], 1)
            self.assertEqual(stats["runs"], 1)
            conn = sqlite3.connect(v2)
            proto, machine, status = conn.execute(
                "SELECT protocol, machine_id, status FROM cells").fetchone()
            self.assertEqual(proto, "v1")               # marcado para siempre
            self.assertEqual(machine, "mini-m1-16g")    # mapeo de hardware v1
            self.assertEqual(status, "ok")
            metrics = dict(conn.execute(
                "SELECT metric, value FROM measurements").fetchall())
            self.assertAlmostEqual(metrics["decode_tps"], 37.9)
            self.assertAlmostEqual(metrics["ram_observed_gb"], 6.48)
            # el action_log registra la importación (patrón WAL de v1 conservado)
            n_log = conn.execute("SELECT COUNT(*) FROM action_log").fetchone()[0]
            self.assertEqual(n_log, 1)
            conn.close()


if __name__ == "__main__":
    unittest.main()

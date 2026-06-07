"""Tests: validez ambiental (puro) + parser de llama-bench JSON (fixtures)."""
import unittest

from frontier_bench.adapters.engines.llamabench import parse_bench_json, rows_to_measurements
from frontier_bench.adapters.storage.sqlite_store import cell_key
from frontier_bench.domain.entities import CellSpec, LoadProfile, Measurement, Run
from frontier_bench.domain.environment import (EnvSnapshot, ProcessInfo, assess)
from frontier_bench.domain.ranking import LiveRanking


def snap(free=20.0, swap=0.0, load=2.0, heavy=(), cores=10) -> EnvSnapshot:
    return EnvSnapshot(free_ram_gb=free, total_ram_gb=32.0, swap_used_gb=swap,
                       load_avg_1m=load, n_cores=cores, heavy_processes=heavy)


class TestEnvironmentValidity(unittest.TestCase):
    def test_clean_environment_is_valid(self):
        report = assess(snap(), snap(), required_gb=8.0)
        self.assertTrue(report.valid)
        self.assertEqual(report.reasons, ())

    def test_insufficient_ram_invalidates(self):
        report = assess(snap(free=6.0), None, required_gb=8.0)
        self.assertFalse(report.valid)
        self.assertTrue(any("ram_insuficiente" in r for r in report.reasons))

    def test_heavy_process_invalidates_with_name(self):
        heavy = (ProcessInfo("LM Studio Helper", 4.2),)
        report = assess(snap(heavy=heavy), None, required_gb=4.0)
        self.assertFalse(report.valid)
        self.assertTrue(any("LM Studio Helper" in r for r in report.reasons))

    def test_swap_during_run_invalidates(self):
        report = assess(snap(swap=0.1), snap(swap=0.9), required_gb=4.0)
        self.assertFalse(report.valid)
        self.assertTrue(any("swap_durante_run" in r for r in report.reasons))

    def test_process_appearing_mid_run_invalidates(self):
        after = snap(heavy=(ProcessInfo("Xcode", 5.0),))
        report = assess(snap(), after, required_gb=4.0)
        self.assertFalse(report.valid)
        self.assertTrue(any("Xcode" in r for r in report.reasons))

    def test_high_load_is_warning_extreme_is_invalid(self):
        warn = assess(snap(load=11.0), None, required_gb=4.0)   # > cores, < cores*1.25
        self.assertTrue(warn.valid)
        self.assertTrue(warn.warnings)
        bad = assess(snap(load=14.0), None, required_gb=4.0)    # > cores*1.25
        self.assertFalse(bad.valid)

    def test_invalid_run_never_ranks(self):
        ranking = LiveRanking()
        cell = CellSpec("m", "e", "model", 4096, 0, 1, LoadProfile.S)
        bad = Run(cell_key=cell_key(cell), n_reps=1, valid=False,
                  interference=("ram_insuficiente",),
                  measurements=[Measurement("decode_tps", 999.0, "tok/s")])
        self.assertEqual(ranking.ingest(bad), [])
        self.assertEqual(ranking.leaderboard("decode_tps").entries, [])


BENCH_JSON = """
[
  {"n_prompt": 512, "n_gen": 0, "n_depth": 8192, "avg_ts": 412.3, "stddev_ts": 8.1},
  {"n_prompt": 0, "n_gen": 128, "n_depth": 8192, "samples_ts": [21.4, 21.9, 21.1]}
]
"""

BENCH_WITH_PROGRESS = "llama-bench: benchmark 1/2 ...\n" + BENCH_JSON


class TestLlamaBenchParser(unittest.TestCase):
    def test_parses_clean_json(self):
        rows = parse_bench_json(BENCH_JSON)
        self.assertEqual(len(rows), 2)
        meas = rows_to_measurements(rows)
        decode = [m for m in meas if m.metric == "decode_tps"]
        self.assertEqual(len(decode), 3)               # samples_ts => 3 muestras
        self.assertAlmostEqual(decode[1].value, 21.9)
        prefill = [m for m in meas if m.metric == "prefill_tps"]
        self.assertAlmostEqual(prefill[0].value, 412.3)

    def test_tolerates_progress_noise(self):
        rows = parse_bench_json(BENCH_WITH_PROGRESS)
        self.assertEqual(len(rows), 2)

    def test_garbage_returns_empty(self):
        self.assertEqual(parse_bench_json("sin json"), [])


if __name__ == "__main__":
    unittest.main()

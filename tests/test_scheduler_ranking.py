"""Tests de Scheduler (selección granular/repetición) y LiveRanking (sin I/O)."""
import unittest

from frontier_bench.adapters.storage.sqlite_store import cell_key
from frontier_bench.domain.entities import (CellSpec, CellStatus, LoadProfile,
                                            Measurement, Run)
from frontier_bench.domain.events import Event, EventBus, EventKind
from frontier_bench.domain.ranking import LiveRanking
from frontier_bench.domain.scheduler import CellFilter, RunRequest, build_work


def cells_fixture() -> list[CellSpec]:
    mk = lambda model, ctx, status=CellStatus.PENDING: CellSpec(
        machine_id="mini-m1-16g", engine_id="llamacpp", model_id=model, ctx=ctx,
        depth_pct=0, slots=1, profile=LoadProfile.S, status=status)
    return [
        mk("qwen35-9b", 4096),
        mk("qwen35-9b", 32768),
        mk("granite41-8b", 4096),
        mk("granite41-8b", 32768, status=CellStatus.FAILED),
        CellSpec("mini-m1-16g", "llamacpp", "qwen35-9b", 65536, 0, 1, LoadProfile.S,
                 status=CellStatus.SKIPPED_BUDGET, skip_reason="no cabe"),
    ]


class TestScheduler(unittest.TestCase):
    def test_repeat_same_test_10_times(self):
        cells = cells_fixture()
        req = RunRequest(filters=CellFilter(model_ids=frozenset({"qwen35-9b"}),
                                            ctxs=frozenset({4096})),
                         repeats=10, force=True, note="estabilidad")
        work = build_work(cells, run_counts={}, request=req, cell_key_fn=cell_key)
        self.assertEqual(len(work), 10)
        self.assertTrue(all(w.cell.model_id == "qwen35-9b" and w.cell.ctx == 4096
                            for w in work))
        self.assertEqual([w.rep_index for w in work], list(range(10)))

    def test_single_concrete_cell_even_if_already_run(self):
        cells = cells_fixture()
        counts = {cell_key(c): 5 for c in cells}   # todo ya probado 5 veces
        req = RunRequest(filters=CellFilter(model_ids=frozenset({"granite41-8b"}),
                                            ctxs=frozenset({4096})),
                         repeats=1, force=True)
        work = build_work(cells, counts, req, cell_key)
        self.assertEqual(len(work), 1)

    def test_only_without_runs_skips_done(self):
        cells = cells_fixture()
        done = cell_key(cells[0])
        req = RunRequest(filters=CellFilter(only_without_runs=True))
        work = build_work(cells, {done: 1}, req, cell_key)
        keys = {cell_key(w.cell) for w in work}
        self.assertNotIn(done, keys)
        self.assertEqual(len(work), 3)   # 4 elegibles - 1 con runs (skipped no cuenta)

    def test_only_failed(self):
        cells = cells_fixture()
        req = RunRequest(filters=CellFilter(only_failed=True))
        work = build_work(cells, {}, req, cell_key)
        self.assertEqual(len(work), 1)
        self.assertEqual(work[0].cell.model_id, "granite41-8b")
        self.assertEqual(work[0].cell.ctx, 32768)

    def test_skipped_cells_never_generate_work(self):
        cells = cells_fixture()
        req = RunRequest(filters=CellFilter(), repeats=3, force=True)
        work = build_work(cells, {}, req, cell_key)
        self.assertTrue(all(w.cell.status is not CellStatus.SKIPPED_BUDGET for w in work))


class _Capture:
    def __init__(self):
        self.events: list[Event] = []

    def publish(self, event: Event) -> None:
        self.events.append(event)


class TestLiveRanking(unittest.TestCase):
    def test_leaderboard_reorders_and_publishes(self):
        bus = EventBus()
        cap = _Capture()
        bus.subscribe(cap)
        ranking = LiveRanking(bus)

        a = CellSpec("mini", "llamacpp", "granite41-8b", 32768, 0, 1, LoadProfile.S)
        b = CellSpec("mini", "llamacpp", "qwen35-9b", 32768, 0, 1, LoadProfile.S)
        ranking.ingest(Run(cell_key=cell_key(a), n_reps=1,
                           measurements=[Measurement("decode_tps", 30.0, "tok/s")]))
        boards = ranking.ingest(Run(cell_key=cell_key(b), n_reps=1,
                                    measurements=[Measurement("decode_tps", 38.0, "tok/s")]))
        lb = boards[0]
        self.assertEqual(lb.metric, "decode_tps")
        self.assertIn("qwen35-9b", lb.entries[0].subject)     # 38 > 30 → arriba
        kinds = {e.kind for e in cap.events}
        self.assertIn(EventKind.RANKING_UPDATED, kinds)

    def test_lower_is_better_metrics(self):
        ranking = LiveRanking()
        a = CellSpec("mini", "llamacpp", "modelA", 4096, 0, 1, LoadProfile.S)
        b = CellSpec("mini", "llamacpp", "modelB", 4096, 0, 1, LoadProfile.S)
        ranking.ingest(Run(cell_key=cell_key(a), n_reps=1,
                           measurements=[Measurement("ttft_ms_p95", 900.0, "ms")]))
        ranking.ingest(Run(cell_key=cell_key(b), n_reps=1,
                           measurements=[Measurement("ttft_ms_p95", 2400.0, "ms")]))
        lb = ranking.leaderboard("ttft_ms_p95")
        self.assertIn("modelA", lb.entries[0].subject)        # menor TTFT gana

    def test_median_over_repeats(self):
        ranking = LiveRanking()
        c = CellSpec("mini", "llamacpp", "modelA", 4096, 0, 1, LoadProfile.S)
        for v in (20.0, 22.0, 40.0):   # outlier no domina
            ranking.ingest(Run(cell_key=cell_key(c), n_reps=1,
                               measurements=[Measurement("decode_tps", v, "tok/s")]))
        lb = ranking.leaderboard("decode_tps")
        self.assertAlmostEqual(lb.entries[0].value, 22.0)
        self.assertEqual(lb.entries[0].n_runs, 3)


if __name__ == "__main__":
    unittest.main()

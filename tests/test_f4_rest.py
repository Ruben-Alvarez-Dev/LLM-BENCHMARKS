"""Tests F4+resto: veredictos, frontera, tuning, executor, routing, catálogo."""
import tempfile
import unittest
from pathlib import Path

from frontier_bench.adapters.storage.import_catalog import parse_catalog
from frontier_bench.adapters.storage.sqlite_store import SqliteStore, cell_key
from frontier_bench.adapters.web.yaml_lite import load_blocks
from frontier_bench.domain.entities import (ArchKind, CellSpec, CellStatus, EngineInfo,
                                            KvProfile, LoadProfile, MachineFacts,
                                            ModelSpec, Platform)
from frontier_bench.domain.executor import execute_once, pending_requests
from frontier_bench.domain.kv_model import GiB
from frontier_bench.domain.planner import CampaignAxes, plan
from frontier_bench.domain.tuning import advise
from frontier_bench.domain.verdicts import (Verdict, check_requirements,
                                            derive_context_metrics, evaluate, frontera)

RULES = load_blocks(
    (Path(__file__).parent.parent / "verdict_rules.yaml").read_text())


class TestVerdicts(unittest.TestCase):
    def test_apto_concurrencia_passes_and_fails(self):
        good = {"error_rate_pct": 0.0, "per_stream_tps_p50": 11.2,
                "ttft_ms_p95": 1800.0, "reprefill_pct": 5.0, "json_valid_pct": 98.0}
        vs = evaluate(RULES, {"model": "m", "machine": "mini", "ctx": 32768,
                              "slots": 4}, good, ["cell-1"])
        conc = next(v for v in vs if v.rule == "apto_concurrencia")
        self.assertTrue(conc.passed, conc.failures)
        self.assertEqual(conc.evidence, ("cell-1",))

        slow = dict(good, per_stream_tps_p50=5.1)
        vs = evaluate(RULES, {}, slow, [])
        conc = next(v for v in vs if v.rule == "apto_concurrencia")
        self.assertFalse(conc.passed)
        self.assertTrue(any("per_stream" in f for f in conc.failures))

    def test_missing_required_metric_never_passes_by_omission(self):
        ok, fails = check_requirements({"reprefill_pct": {"max": 25}}, {})
        self.assertFalse(ok)
        self.assertIn("SIN MEDIR", fails[0])

    def test_optional_metric_ignored_if_absent_but_checked_if_present(self):
        base = {"error_rate_pct": 0, "per_stream_tps_p50": 10,
                "ttft_ms_p95": 1000, "reprefill_pct": 0}
        vs = evaluate(RULES, {}, base, [])           # sin json_valid_pct: pasa
        self.assertTrue(next(v for v in vs if v.rule == "apto_concurrencia").passed)
        vs = evaluate(RULES, {}, dict(base, json_valid_pct=80.0), [])
        self.assertFalse(next(v for v in vs if v.rule == "apto_concurrencia").passed)

    def test_frontera_answers_the_original_question(self):
        def v(model, ctx, slots, passed):
            return Verdict("apto_concurrencia", "v1",
                           {"model": model, "machine": "mini", "ctx": ctx,
                            "slots": slots}, passed, (), ())
        conc = [v("granite", 32768, 2, True), v("granite", 32768, 4, True),
                v("granite", 32768, 8, False), v("qwen", 32768, 2, True),
                v("qwen", 32768, 4, False)]
        ctxv = [Verdict("apto_contexto", "v1",
                        {"model": "granite", "machine": "mini", "ctx": 131072},
                        True, (), ())]
        table = {e.model_id: e for e in frontera(conc, ctxv)}
        self.assertEqual(table["granite"].max_slots_por_ctx[32768], 4)   # "hasta 4"
        self.assertEqual(table["qwen"].max_slots_por_ctx[32768], 2)      # "este no"
        self.assertEqual(table["granite"].max_ctx_consistente, 131072)

    def test_derived_context_metrics(self):
        m = derive_context_metrics(30.0, 21.0, beacons_ok=5, beacons_asked=6,
                                   degenerate_runs=0, total_runs=3)
        self.assertAlmostEqual(m["decode_retention_pct"], 70.0)
        self.assertAlmostEqual(m["beacon_recall_pct"], 83.33, places=1)


class TestTuning(unittest.TestCase):
    RULES = load_blocks((Path(__file__).parent.parent / "tuning_rules.yaml").read_text())

    def test_metal_16gb_gets_q8_and_wired_hint(self):
        merged, sugg = advise(self.RULES, {"platform": "metal", "ram_gb": 16.0,
                                           "cpu_vendor": "apple", "isa": ["neon"]})
        self.assertEqual(merged["cache_type_k"], "q8_0")
        self.assertEqual(merged["wired_limit_mb_hint"], 12288)
        self.assertTrue(all(s.evidence for s in sugg))    # toda sugerencia cita evidencia

    def test_xeon_avx512_gets_build_flags_not_metal_params(self):
        merged, _ = advise(self.RULES, {"platform": "cpu", "ram_gb": 64.0,
                                        "cpu_vendor": "intel", "isa": ["avx512"]})
        self.assertIn("-DGGML_AVX512=ON", merged.get("build_flags", []))
        self.assertNotIn("cache_type_k", merged)          # regla metal no matchea


class TestExecutor(unittest.TestCase):
    def _store(self):
        tmp = tempfile.mkdtemp()
        return SqliteStore(Path(tmp) / "x.db")

    def _cells(self):
        return [CellSpec("mini", "e", "granite", 32768, 0, 1, LoadProfile.S),
                CellSpec("mini", "e", "qwen", 32768, 0, 1, LoadProfile.S)]

    def test_queue_consume_idempotent_dry(self):
        store = self._store()
        store.log_action("ui", "run_request_queued",
                         {"filters": {"model": "granite"}, "repeats": 3})
        self.assertEqual(len(pending_requests(store)), 1)
        report = execute_once(store, self._cells(), cell_key, dry=True)
        self.assertEqual(report.planned_items, 3)         # 1 celda × 3 repeats
        self.assertEqual(len(report.plans[0]["cells"]), 1)
        # idempotencia: segunda pasada no re-consume
        self.assertEqual(len(pending_requests(store)), 0)
        report2 = execute_once(store, self._cells(), cell_key, dry=True)
        self.assertEqual(report2.planned_items, 0)
        store.close()


class TestPlannerRouting(unittest.TestCase):
    def test_beyond_native_requires_rope_yarn_capability(self):
        machines = {"mini": MachineFacts("mini", "h", "Apple M1", 16.0,
                                         Platform.METAL, 10.7)}
        kv = KvProfile(ArchKind.HYBRID_LINEAR, 32, 4, 256, 8, 25.0)
        models = {"m": ModelSpec("m", "M", 9.0, "Q4", int(5 * GiB), kv,
                                 262144, 1048576)}
        engines = {"llamabench": EngineInfo("llamabench", "1"),
                   "llamaserver": EngineInfo("llamaserver", "1")}
        caps = {"llamabench": frozenset({"kv_q8"}),
                "llamaserver": frozenset({"kv_q8", "rope_yarn"})}
        axes = CampaignAxes(machines=("mini",), engines=("llamabench", "llamaserver"),
                            models=("m",), contexts=(524288,), depth_pcts=(0,),
                            slot_ladder=(1,), technique_sets=((),), cache_type="q4_0")
        result = plan(axes, machines, models, engines, {}, engines_caps=caps)
        by_engine = {c.engine_id: c for c in result.cells}
        self.assertIs(by_engine["llamabench"].status, CellStatus.SKIPPED_UNSUPPORTED)
        self.assertIn("rope_yarn", by_engine["llamabench"].skip_reason)
        # el server puede o no caber por presupuesto, pero NO se descarta por rope
        self.assertNotIn("rope_yarn", by_engine["llamaserver"].skip_reason)


CSV_SAMPLE = """categoria,engine,author,model,tag_quant,format,size,size_bytes,path,download_page,redownload,flag,notes
lmstudio,LM Studio,unsloth,Qwen3.5-4B-GGUF,Q4_K_S,GGUF,3.7GB,3924505440,/no/existe.gguf,https://x,cmd,,
ollama,Ollama,library,gemma3,12b,GGUF(ollama),8.1 GB,,/tampoco,https://y,cmd2,,
"""


class TestCatalogImport(unittest.TestCase):
    def test_parse_best_effort(self):
        rows = parse_catalog(CSV_SAMPLE)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["model_id"], "unsloth/Qwen3.5-4B-GGUF")
        self.assertEqual(rows[0]["file_bytes"], 3924505440)
        self.assertFalse(rows[0]["on_disk"])
        self.assertAlmostEqual(rows[1]["file_bytes"] / GiB, 8.1, places=1)


if __name__ == "__main__":
    unittest.main()

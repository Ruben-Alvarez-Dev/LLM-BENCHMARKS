"""Tests del Planner — expansión y poda con motivo (sin I/O)."""
import unittest

from frontier_bench.domain.entities import (ArchKind, CellStatus, EngineInfo, KvProfile,
                                            LoadProfile, MachineFacts, ModelSpec, Platform,
                                            Technique)
from frontier_bench.domain.kv_model import GiB
from frontier_bench.domain.planner import CampaignAxes, plan


def fixtures():
    machines = {
        "mini-m1-16g": MachineFacts("mini-m1-16g", "mac-mini.local", "Apple M1", 16.0,
                                    Platform.METAL, wired_limit_gb=10.7),
        "mbp-m1max-32g": MachineFacts("mbp-m1max-32g", "MacBook-Pro.local", "Apple M1 Max",
                                      32.0, Platform.METAL, wired_limit_gb=24.0),
    }
    kv = KvProfile(arch=ArchKind.HYBRID_LINEAR, n_layers=32, full_attn_layers=8,
                   kv_heads=4, head_dim=256, recurrent_state_mb=25.0)
    models = {
        "qwen35-9b": ModelSpec("qwen35-9b", "Qwen3.5-9B", 9.65, "Q4_K_M",
                               int(5.6 * GiB), kv, 262_144, 1_048_576),
    }
    engines = {"llamacpp": EngineInfo("llamacpp", "b9309")}
    techniques = {
        "kv_q8": Technique("kv_q8", supports={"llamacpp": "native"}),
        "spec_eagle3": Technique("spec_eagle3", supports={"vllm_cuda": "native"}),
    }
    return machines, models, engines, techniques


class TestPlanner(unittest.TestCase):
    def test_unsupported_technique_is_visible_not_silent(self):
        machines, models, engines, techniques = fixtures()
        axes = CampaignAxes(machines=("mini-m1-16g",), engines=("llamacpp",),
                            models=("qwen35-9b",), contexts=(4096,), depth_pcts=(0,),
                            slot_ladder=(1,), profiles=(LoadProfile.S,),
                            technique_sets=(("spec_eagle3",),))
        result = plan(axes, machines, models, engines, techniques)
        self.assertEqual(len(result.cells), 1)
        cell = result.cells[0]
        self.assertIs(cell.status, CellStatus.SKIPPED_UNSUPPORTED)
        self.assertIn("spec_eagle3", cell.skip_reason)

    def test_budget_prunes_realistically_per_machine(self):
        machines, models, engines, techniques = fixtures()
        axes = CampaignAxes(machines=("mini-m1-16g", "mbp-m1max-32g"), engines=("llamacpp",),
                            models=("qwen35-9b",),
                            contexts=(262_144, 716_800, 1_048_576), depth_pcts=(0,),
                            slot_ladder=(1,), technique_sets=((),), cache_type="q4_0")
        result = plan(axes, machines, models, engines, techniques)
        by_key = {(c.machine_id, c.ctx): c for c in result.cells}
        # mini: 256K q4 cabe (coincide con la campaña real: 9.39GB observados);
        # 700K/1M ya no — y queda VISIBLE con desglose, no silencioso
        self.assertIs(by_key[("mini-m1-16g", 262_144)].status, CellStatus.PENDING)
        self.assertIs(by_key[("mini-m1-16g", 716_800)].status, CellStatus.SKIPPED_BUDGET)
        self.assertIn("GiB", by_key[("mini-m1-16g", 716_800)].skip_reason)
        # MBP 32GB: 700K cabe y queda marcado como extrapolación rope (>256K nativo)
        cell_700k = by_key[("mbp-m1max-32g", 716_800)]
        self.assertIs(cell_700k.status, CellStatus.PENDING)
        self.assertEqual(cell_700k.skip_reason, "rope_extrapolated")

    def test_concurrency_axes_coherence(self):
        machines, models, engines, techniques = fixtures()
        axes = CampaignAxes(machines=("mini-m1-16g",), engines=("llamacpp",),
                            models=("qwen35-9b",), contexts=(32_768,), depth_pcts=(0, 50),
                            slot_ladder=(1, 4), profiles=(LoadProfile.S, LoadProfile.A),
                            technique_sets=((),))
        result = plan(axes, machines, models, engines, techniques)
        combos = {(c.profile, c.slots, c.depth_pct) for c in result.cells}
        # S solo con slots=1 (profundidades 0 y 50); A solo con slots=4 y depth=0
        self.assertIn((LoadProfile.S, 1, 0), combos)
        self.assertIn((LoadProfile.S, 1, 50), combos)
        self.assertIn((LoadProfile.A, 4, 0), combos)
        self.assertNotIn((LoadProfile.A, 1, 0), combos)
        self.assertNotIn((LoadProfile.S, 4, 0), combos)
        self.assertNotIn((LoadProfile.A, 4, 50), combos)

    def test_summary_counts(self):
        machines, models, engines, techniques = fixtures()
        axes = CampaignAxes(machines=("mini-m1-16g", "mbp-m1max-32g"), engines=("llamacpp",),
                            models=("qwen35-9b",), contexts=(4096, 32_768), depth_pcts=(0,),
                            slot_ladder=(1,), technique_sets=((), ("kv_q8",)))
        result = plan(axes, machines, models, engines, techniques)
        s = result.summary()
        self.assertEqual(sum(s.values()), len(result.cells))
        self.assertEqual(s.get("pending"), len(result.pending))


if __name__ == "__main__":
    unittest.main()

"""Tests del KvModel — matemática de memoria por arquitectura (sin I/O)."""
import unittest

from frontier_bench.domain.entities import ArchKind, KvProfile, MachineFacts, ModelSpec, Platform
from frontier_bench.domain.kv_model import GiB, budget, kv_bytes


def dense_8b() -> KvProfile:
    # Llama-3.1-8B-style: 32 capas, 8 kv_heads, head_dim 128
    return KvProfile(arch=ArchKind.DENSE_GQA, n_layers=32, kv_heads=8, head_dim=128)


def hybrid_qwen35_9b() -> KvProfile:
    # Qwen3.5-9B: 32 capas, 8 full-attention, GQA 4 kv_heads, head_dim 256, estado GDN ~25MB/slot
    return KvProfile(arch=ArchKind.HYBRID_LINEAR, n_layers=32, full_attn_layers=8,
                     kv_heads=4, head_dim=256, recurrent_state_mb=25.0)


def swa_gemma() -> KvProfile:
    # Gemma-3-style: 32 capas, 1 de cada 6 global, ventana 1024
    return KvProfile(arch=ArchKind.SWA, n_layers=30, kv_heads=8, head_dim=128,
                     swa_global_layers=5, swa_window=1024)


class TestKvBytes(unittest.TestCase):
    def test_dense_per_token(self):
        # 2*32*8*128*2 bytes = 131072 B/token f16
        total = kv_bytes(dense_8b(), ctx_tokens=1, slots=1, cache_type="f16")
        self.assertAlmostEqual(total, 131072.0)

    def test_hybrid_much_smaller_than_dense(self):
        ctx = 131_072  # 128K
        dense = kv_bytes(dense_8b(), ctx, slots=1, cache_type="f16")
        hybrid = kv_bytes(hybrid_qwen35_9b(), ctx, slots=1, cache_type="f16")
        # hybrid: solo 8/32 capas tienen KV (aunque head_dim doble) → ~2x menos como mínimo
        self.assertLess(hybrid, dense / 2)

    def test_hybrid_recurrent_state_scales_with_slots(self):
        one = kv_bytes(hybrid_qwen35_9b(), 4096, slots=1)
        eight = kv_bytes(hybrid_qwen35_9b(), 4096, slots=8)
        delta_mb = (eight - one) / 1024 ** 2
        self.assertAlmostEqual(delta_mb, 25.0 * 7, delta=0.1)

    def test_swa_caps_at_window(self):
        small = kv_bytes(swa_gemma(), 2_048, slots=1)
        big = kv_bytes(swa_gemma(), 262_144, slots=1)
        # las capas SWA no crecen más allá de la ventana: big crece ~37x, no 128x (denso)
        ratio = big / small
        self.assertLess(ratio, 45)
        self.assertGreater(ratio, 20)

    def test_q8_halves_f16(self):
        f16 = kv_bytes(dense_8b(), 8192, 1, "f16")
        q8 = kv_bytes(dense_8b(), 8192, 1, "q8_0")
        self.assertAlmostEqual(q8 / f16, 1.0625 / 2, places=3)


class TestBudget(unittest.TestCase):
    def setUp(self):
        self.mini = MachineFacts(machine_id="mini-m1-16g", hostname="mac-mini.local",
                                 chip="Apple M1", ram_gb=16.0, platform=Platform.METAL,
                                 wired_limit_gb=10.7, bandwidth_gbs=68.0)
        self.qwen = ModelSpec(model_id="qwen35-9b-q4", name="Qwen3.5-9B", params_b=9.65,
                              quant="Q4_K_M", file_bytes=int(5.6 * GiB),
                              kv=hybrid_qwen35_9b(), context_native=262_144,
                              context_max=1_048_576)
        self.dense = ModelSpec(model_id="llama31-8b-q4", name="Llama-3.1-8B", params_b=8.0,
                               quant="Q4_K_M", file_bytes=int(4.7 * GiB),
                               kv=dense_8b(), context_native=131_072, context_max=131_072)

    def test_hybrid_8slots_32k_fits_mini(self):
        b = budget(self.mini, self.qwen, ctx_tokens=32_768, slots=8, cache_type="q8_0")
        self.assertTrue(b.fits, b.reason)

    def test_dense_1m_does_not_fit_mini(self):
        b = budget(self.mini, self.dense, ctx_tokens=1_048_576, slots=1, cache_type="q8_0")
        self.assertFalse(b.fits)
        self.assertIn("presupuesto", b.reason)

    def test_rope_flag(self):
        self.assertTrue(self.qwen.rope_extrapolated(716_800))
        self.assertFalse(self.qwen.rope_extrapolated(262_144))


if __name__ == "__main__":
    unittest.main()

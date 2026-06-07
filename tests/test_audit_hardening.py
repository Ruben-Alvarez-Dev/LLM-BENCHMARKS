"""Tests de la auditoría 2026-06-06: 512K, GGUF reader, contexto verificable,
bisección, aislamiento entre celdas y YaRN obligatorio."""
import io
import struct
import tempfile
import unittest
from pathlib import Path

from frontier_bench.adapters.corpus.verifiable import (beacon_code, build_verifiable,
                                                       check_answer, find_effective_context,
                                                       probe_positions, question_for)
from frontier_bench.adapters.engines.llamaserver import LlamaServer
from frontier_bench.adapters.models.gguf_reader import (GGUFError, facts_from_metadata,
                                                        read_metadata)
from frontier_bench.domain.battery import wait_recovery
from frontier_bench.domain.entities import (CONTEXT_LADDER, ArchKind, CellSpec,
                                            KvProfile, LoadProfile, ModelSpec)
from frontier_bench.domain.environment import EnvSnapshot


class TestContextLadder(unittest.TestCase):
    def test_full_ladder_including_512k(self):
        self.assertEqual(CONTEXT_LADDER,
                         (4096, 8192, 16384, 32768, 65536, 131072,
                          262144, 524288, 716800, 1048576))


# ───────── GGUF sintético ─────────

def _s(txt: bytes) -> bytes:
    return struct.pack("<Q", len(txt)) + txt


def _kv_str(key: bytes, val: bytes) -> bytes:
    return _s(key) + struct.pack("<I", 8) + _s(val)


def _kv_u32(key: bytes, val: int) -> bytes:
    return _s(key) + struct.pack("<I", 4) + struct.pack("<I", val)


def _kv_f32(key: bytes, val: float) -> bytes:
    return _s(key) + struct.pack("<I", 6) + struct.pack("<f", val)


def _kv_arr_u32(key: bytes, vals: list[int]) -> bytes:
    body = struct.pack("<I", 4) + struct.pack("<Q", len(vals))
    body += b"".join(struct.pack("<I", v) for v in vals)
    return _s(key) + struct.pack("<I", 9) + body


def synthetic_gguf(kvs: list[bytes]) -> bytes:
    return b"GGUF" + struct.pack("<I", 3) + struct.pack("<Q", 0) + \
           struct.pack("<Q", len(kvs)) + b"".join(kvs)


class TestGgufReader(unittest.TestCase):
    def _write(self, kvs) -> str:
        f = tempfile.NamedTemporaryFile(suffix=".gguf", delete=False)
        f.write(synthetic_gguf(kvs))
        f.close()
        return f.name

    def test_hybrid_with_per_layer_kv_heads_and_yarn(self):
        # híbrido tipo Qwen3.5: 8 de 32 capas con KV; YA extendido por YaRN
        kv_per_layer = [4 if i % 4 == 3 else 0 for i in range(32)]
        path = self._write([
            _kv_str(b"general.architecture", b"qwen35"),
            _kv_u32(b"qwen35.block_count", 32),
            _kv_arr_u32(b"qwen35.attention.head_count_kv", kv_per_layer),
            _kv_u32(b"qwen35.attention.key_length", 256),
            _kv_u32(b"qwen35.context_length", 262144),
            _kv_str(b"qwen35.rope.scaling.type", b"yarn"),
            _kv_u32(b"qwen35.rope.scaling.original_context_length", 32768),
            _kv_f32(b"qwen35.rope.freq_base", 10000000.0),
        ])
        facts = facts_from_metadata(read_metadata(path))
        self.assertEqual(facts.arch, "qwen35")
        self.assertEqual(facts.n_layers, 32)
        self.assertEqual(facts.kv_heads, 4)
        self.assertEqual(facts.head_dim, 256)
        self.assertEqual(facts.context_native, 262144)
        self.assertEqual(facts.raw_keys["_derived.full_attn_layers"], 8)
        self.assertEqual(facts.rope_scaling_type, "yarn")
        # AVISO crítico: ya viene extendido → consistencia obligatoria >32K
        self.assertTrue(any("YaRN" in w and "32768" in w for w in facts.warnings))

    def test_not_gguf_raises(self):
        f = tempfile.NamedTemporaryFile(suffix=".bin", delete=False)
        f.write(b"NOPE" + b"\x00" * 64)
        f.close()
        with self.assertRaises(GGUFError):
            read_metadata(f.name)


class TestVerifiableContext(unittest.TestCase):
    BASE = ("palabra única %d distinta " * 4000) % tuple(range(4000)) \
        if False else " ".join(f"w{i}" for i in range(40000))

    def test_beacons_at_known_positions_and_checkable(self):
        text, beacons = build_verifiable(self.BASE, n_tokens=8192, seed=7,
                                         interval_tokens=1024)
        self.assertGreaterEqual(len(beacons), 7)
        # determinista
        _, b2 = build_verifiable(self.BASE, 8192, seed=7, interval_tokens=1024)
        self.assertEqual([b.code for b in beacons], [b.code for b in b2])
        # otro seed => otros códigos (no memorizable por el modelo)
        _, b3 = build_verifiable(self.BASE, 8192, seed=8, interval_tokens=1024)
        self.assertNotEqual(beacons[0].code, b3[0].code)
        # cada baliza está físicamente en el texto
        for b in beacons[:3]:
            self.assertIn(b.code, text)

    def test_answer_checking_exact(self):
        _, beacons = build_verifiable(self.BASE, 4096, seed=1)
        idxs = probe_positions(beacons)
        q = question_for(beacons, idxs)
        self.assertIn(str(idxs[-1]), q)
        good = ", ".join(beacon_code(1, i) for i in idxs)
        self.assertTrue(all(check_answer(good, beacons, idxs).values()))
        partial = beacon_code(1, idxs[0])     # solo la primera
        res = check_answer(partial, beacons, idxs)
        self.assertTrue(res[idxs[0]])
        self.assertFalse(res[idxs[-1]])

    def test_bisection_finds_effective_limit(self):
        true_limit = 93_000     # el modelo "real" recuerda hasta aquí
        calls = []

        def recalls(depth):
            calls.append(depth)
            return depth <= true_limit

        found = find_effective_context(recalls, 4096, 262144, resolution=2048)
        self.assertLessEqual(abs(found - true_limit), 2048)
        self.assertLessEqual(len(calls), 14)   # coste acotado: pocas sondas

    def test_bisection_edges(self):
        self.assertEqual(find_effective_context(lambda d: False, 4096, 262144), 0)
        self.assertEqual(find_effective_context(lambda d: True, 4096, 262144), 262144)


class TestMasterContext(unittest.TestCase):
    BASE = "\n\n".join(
        " ".join(f"tok{i}_{j}" for j in range(60)) for i in range(3000))

    def test_prefixes_are_exact_nested_slices(self):
        from frontier_bench.adapters.corpus.verifiable import MasterContext
        master = MasterContext(self.BASE, max_tokens=65536, seed=42)
        t512, b512 = master.prefix(32768)
        t256, b256 = master.prefix(16384)
        # 16K es PREFIJO LITERAL de 32K — diferencias atribuibles solo a longitud
        self.assertTrue(t512.startswith(t256))
        # y ambos son prefijos del maestro
        self.assertTrue(master.text.startswith(t512))
        # balizas: las del prefijo corto son subconjunto exacto de las del largo
        codes256 = [b.code for b in b256]
        self.assertEqual(codes256, [b.code for b in b512][:len(codes256)])

    def test_salting_makes_filler_globally_unique(self):
        from frontier_bench.adapters.corpus.verifiable import MasterContext
        m1 = MasterContext(self.BASE, 8192, seed=1)
        m2 = MasterContext(self.BASE, 8192, seed=2)
        # mismo corpus base, seeds distintos => textos distintos (sal + balizas)
        self.assertNotEqual(m1.text[:2000], m2.text[:2000])
        self.assertIn("(frag:", m1.text)                 # sal presente
        self.assertNotEqual(m1.fingerprint(), m2.fingerprint())
        # determinismo: mismo seed => bit a bit idéntico
        m1b = MasterContext(self.BASE, 8192, seed=1)
        self.assertEqual(m1.fingerprint(), m1b.fingerprint())


class TestIsolation(unittest.TestCase):
    def test_wait_recovery_returns_when_ram_back(self):
        seq = [EnvSnapshot(5.0, 32, 0, 1, 10), EnvSnapshot(9.0, 32, 0, 1, 10),
               EnvSnapshot(19.5, 32, 0, 1, 10)]
        it = iter(seq)
        last = seq[-1]
        probe = lambda: next(it, last)
        waited = wait_recovery(probe, baseline_free_gb=20.0, tolerance_gb=1.5,
                               timeout_s=60, sleep_fn=lambda s: None)
        self.assertGreaterEqual(waited, 0.0)   # terminó (3ª muestra ya recupera)

    def test_wait_recovery_times_out_on_leak(self):
        probe = lambda: EnvSnapshot(5.0, 32, 0, 1, 10)   # nunca recupera
        waited = wait_recovery(probe, 20.0, 1.5, timeout_s=0.05,
                               sleep_fn=lambda s: None)
        self.assertGreaterEqual(waited, 0.05)


class TestYarnEnforcement(unittest.TestCase):
    def test_server_adds_yarn_flags_beyond_native(self):
        model = ModelSpec("m", "M", 9.0, "Q4", 5 << 30,
                          KvProfile(ArchKind.HYBRID_LINEAR, 32, 4, 256, 8, 25.0),
                          context_native=262144, context_max=1048576,
                          file_path="/x.gguf")
        srv = LlamaServer()
        within = srv.build_cmd(CellSpec("m", "e", "m", 262144, 0, 1, LoadProfile.S), model)
        beyond = srv.build_cmd(CellSpec("m", "e", "m", 524288, 0, 1, LoadProfile.S), model)
        self.assertNotIn("--rope-scaling", " ".join(within))
        s = " ".join(beyond)
        self.assertIn("--rope-scaling yarn", s)
        self.assertIn("--yarn-orig-ctx 262144", s)


if __name__ == "__main__":
    unittest.main()

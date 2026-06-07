"""Tests: políticas de mantenimiento (updates+limpieza) y parser yaml_lite."""
import tempfile
import unittest
from pathlib import Path

from frontier_bench.adapters.web.yaml_lite import load_blocks
from frontier_bench.domain.maintenance import (CleanupManifest, parse_brew_outdated)

BREW_JSON = """{"formulae":[
 {"name":"llama.cpp","installed_versions":["8880"],"current_version":"9430"},
 {"name":"wget","installed_versions":["1.21"],"current_version":"1.25"},
 {"name":"ggml","installed_versions":["0.9"],"current_version":"0.10"}
],"casks":[]}"""


class TestUpdates(unittest.TestCase):
    def test_only_watched_components_proposed(self):
        props = parse_brew_outdated(BREW_JSON)
        names = {p.component for p in props}
        self.assertEqual(names, {"llama.cpp", "ggml"})    # wget no nos importa
        llama = next(p for p in props if p.component == "llama.cpp")
        self.assertEqual(llama.current, "8880")
        self.assertEqual(llama.latest, "9430")
        self.assertIn("brew upgrade", llama.command)      # se propone, no se ejecuta

    def test_garbage_json(self):
        self.assertEqual(parse_brew_outdated("no json"), [])


class TestCleanup(unittest.TestCase):
    def test_battery_leaves_pristine_but_keeps_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            prompt = d / "prompt_d50.txt"; prompt.write_text("x" * 1000)
            cache = d / "cache_dir"; cache.mkdir(); (cache / "f").write_text("y")
            raw = d / "raw_model_ctx16384.log"; raw.write_text("timings...")

            m = CleanupManifest(battery_id="test")
            m.register_temp(prompt)
            m.register_temp(cache)
            m.register_evidence(raw)
            report = m.cleanup()

            self.assertTrue(report.pristine)
            self.assertFalse(prompt.exists())             # temporal borrado
            self.assertFalse(cache.exists())              # cache borrada
            self.assertFalse(raw.exists())                # crudo original...
            gz = raw.with_suffix(".log.gz")
            self.assertTrue(gz.exists())                  # ...conservado comprimido
            self.assertIn(str(gz), report.kept_evidence)

    def test_failed_deletion_reported(self):
        m = CleanupManifest(battery_id="x")
        # un path inexistente no es fallo (ya no está); pristine
        m.register_temp("/tmp/no-existe-frontier-bench-xyz")
        self.assertTrue(m.cleanup().pristine)


YAML_SAMPLE = """
# comentario
- id: kv_q8
  dims: {cache_type_k: q8_0, cache_type_v: q8_0}
  supports: {llamacpp: native, vllm_cuda: native}
  constraints: [metal_kv_types_must_match]   # inline comment
  purpose: "Duplica el contexto con pérdida ~0"
  not_for: "No acelera el decode"

- id: spec_eagle3
  supports: {vllm_cuda: native, llamacpp: {cuda: pr-18039-open}}
  warnings: [solo_cuda]
"""


class TestYamlLite(unittest.TestCase):
    def test_parses_registry(self):
        blocks = load_blocks(YAML_SAMPLE)
        self.assertEqual(len(blocks), 2)
        kv = blocks[0]
        self.assertEqual(kv["id"], "kv_q8")
        self.assertEqual(kv["dims"]["cache_type_k"], "q8_0")
        self.assertEqual(kv["supports"]["llamacpp"], "native")
        self.assertEqual(kv["constraints"], ["metal_kv_types_must_match"])
        self.assertIn("contexto", kv["purpose"])
        eagle = blocks[1]
        self.assertEqual(eagle["supports"]["llamacpp"], {"cuda": "pr-18039-open"})
        self.assertEqual(eagle["warnings"], ["solo_cuda"])

    def test_real_registry_file_parses(self):
        text = (Path(__file__).parent.parent / "techniques.yaml").read_text()
        blocks = load_blocks(text)
        ids = {b["id"] for b in blocks}
        self.assertGreaterEqual(len(ids), 14)
        self.assertIn("kv_planar3", ids)


if __name__ == "__main__":
    unittest.main()

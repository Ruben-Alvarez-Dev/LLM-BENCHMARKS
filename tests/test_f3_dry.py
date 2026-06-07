"""F3 en seco: FakeOpenAIServer (stdlib) + perfiles + métricas + battery runner.

Cero modelos: el fake simula streaming token a token, timings de llama-server,
errores inyectados y reprefill configurable.
"""
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from frontier_bench.adapters.engines.llamaserver import LlamaServer
from frontier_bench.adapters.loadgen.profiles import (ProfileParams, json_tool_validity,
                                                      profile_A, profile_B)
from frontier_bench.domain.battery import run_battery
from frontier_bench.domain.entities import (ArchKind, CellSpec, KvProfile, LoadProfile,
                                            ModelSpec)
from frontier_bench.domain.environment import EnvSnapshot, ProcessInfo
from frontier_bench.domain.loadmetrics import RequestResult, compute, percentile
from frontier_bench.ports import ServerHandle


# ───────── fake OpenAI server ─────────

class FakeConfig:
    n_tokens = 8
    token_delay_s = 0.005
    fail_every = 0           # 0 = sin errores; N = falla 1 de cada N
    reprefill = False        # True => timings.prompt_n = total del prompt
    counter = 0


def make_fake_handler(cfg: FakeConfig):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            cfg.counter += 1
            if cfg.fail_every and cfg.counter % cfg.fail_every == 0:
                self.send_response(500)
                self.end_headers()
                return
            prompt = body["messages"][-1]["content"]
            n_prompt = len(prompt.split())
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            reply = '{"tool": "buscar", "args": {"query": "x", "limit": 3}}'
            words = (reply if "JSON" in prompt else "palabra " * cfg.n_tokens).split()
            for i, w in enumerate(words[:max(cfg.n_tokens, len(words))]):
                time.sleep(cfg.token_delay_s)
                chunk = {"choices": [{"delta": {"content": w + " "}}]}
                if i == len(words) - 1:
                    chunk["timings"] = {
                        "prompt_n": n_prompt if cfg.reprefill else min(8, n_prompt)}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")

    return H


class FakeServerMixin:
    def start_fake(self, cfg: FakeConfig) -> str:
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_fake_handler(cfg))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{self.httpd.server_port}"

    def tearDown(self):
        if hasattr(self, "httpd"):
            self.httpd.shutdown()


class TestLoadgenDry(FakeServerMixin, unittest.TestCase):
    def test_profile_A_metrics(self):
        cfg = FakeConfig()
        url = self.start_fake(cfg)
        p = ProfileParams(n_streams=4, requests_per_stream=2, max_tokens=8,
                          arrival_rate_per_s=50.0)
        results, wall, _ = profile_A(url, ["hola mundo", "qué tal"], p)
        m = {x.metric: x.value for x in compute(results, wall).measurements}
        self.assertEqual(m["requests_total"], 8)
        self.assertEqual(m["error_rate_pct"], 0.0)
        self.assertGreater(m["aggregate_tps"], 0)
        self.assertGreater(m["ttft_ms_p95"], 0)

    def test_profile_A_detects_errors(self):
        cfg = FakeConfig()
        cfg.fail_every = 2
        url = self.start_fake(cfg)
        p = ProfileParams(n_streams=2, requests_per_stream=3, arrival_rate_per_s=50.0)
        results, wall, _ = profile_A(url, ["x"], p)
        m = {x.metric: x.value for x in compute(results, wall).measurements}
        self.assertGreater(m["error_rate_pct"], 20.0)

    def test_profile_B_detects_reprefill_regression(self):
        cfg = FakeConfig()
        cfg.reprefill = True       # simula #24055: reprocesa TODO el prompt cada turno
        url = self.start_fake(cfg)
        p = ProfileParams(n_streams=2, turns=3,
                          shared_prefix="prefijo " * 60)
        results, wall, _ = profile_B(url, p)
        m = {x.metric: x.value for x in
             compute(results, wall, expect_cached_prefix=True).measurements}
        self.assertGreater(m["reprefill_pct"], 90.0)

        cfg2 = FakeConfig()        # cache sano: prompt_n pequeño
        url2 = self.start_fake(cfg2)
        results2, wall2, _ = profile_B(url2, p)
        m2 = {x.metric: x.value for x in
              compute(results2, wall2, expect_cached_prefix=True).measurements}
        self.assertLess(m2["reprefill_pct"], 10.0)

    def test_profile_E_json_validity(self):
        cfg = FakeConfig()
        url = self.start_fake(cfg)
        from frontier_bench.adapters.loadgen.profiles import profile_E
        p = ProfileParams(n_streams=2, requests_per_stream=2, arrival_rate_per_s=50.0)
        _, _, texts = profile_E(url, p)
        self.assertEqual(json_tool_validity(texts), 100.0)


class TestLlamaServerCmd(unittest.TestCase):
    def test_command_respects_techniques(self):
        model = ModelSpec("m", "M", 9.0, "Q4", 5 * 1024**3,
                          KvProfile(ArchKind.HYBRID_LINEAR, 32, 4, 256, 8, 25.0),
                          262144, 262144, file_path="/x/m.gguf")
        cell = CellSpec("mini", "llamaserver", "m", 32768, 0, 8, LoadProfile.A,
                        techniques=("flash_attn", "kv_q8", "kv_unified",
                                    "spec_ngram_mod", "prefix_cache_reuse"))
        cmd = LlamaServer(port=8123).build_cmd(cell, model)
        s = " ".join(cmd)
        self.assertIn("-np 8", s)
        self.assertIn("--kv-unified", s)
        self.assertIn("--cache-type-k q8_0 --cache-type-v q8_0", s)
        self.assertIn("--spec-type ngram-mod", s)
        self.assertIn("--cache-reuse 256", s)
        self.assertIn("--no-webui", s)


class FakeServingEngine:
    """ServingEnginePort falso que apunta al FakeOpenAIServer ya levantado."""
    def __init__(self, base_url):
        self.base_url = base_url
        self.stopped = 0

    def serve(self, cell, model):
        return ServerHandle(base_url=self.base_url, pid=0)

    def stop(self, handle):
        self.stopped += 1


def clean_env():
    return EnvSnapshot(free_ram_gb=20, total_ram_gb=32, swap_used_gb=0,
                       load_avg_1m=2, n_cores=10)


def dirty_env():
    return EnvSnapshot(free_ram_gb=2, total_ram_gb=32, swap_used_gb=0,
                       load_avg_1m=2, n_cores=10,
                       heavy_processes=(ProcessInfo("OtraApp", 8.0),))


class TestBatteryRunner(FakeServerMixin, unittest.TestCase):
    def _cells(self):
        return [CellSpec("mini", "fake", "m", 16384, 0, 4, LoadProfile.A),
                CellSpec("mini", "fake", "m", 16384, 0, 8, LoadProfile.A)]

    def _model(self):
        return ModelSpec("m", "M", 9.0, "Q4", 5 * 1024**3,
                         KvProfile(ArchKind.HYBRID_LINEAR, 32, 4, 256, 8, 25.0),
                         262144, 262144, file_path="/x.gguf")

    def test_battery_runs_and_cleans(self):
        url = self.start_fake(FakeConfig())
        engine = FakeServingEngine(url)
        p = ProfileParams(n_streams=2, requests_per_stream=2, arrival_rate_per_s=50.0)

        def loader(base_url, cell):
            return profile_A(base_url, ["hola"], p)

        result = run_battery(self._model(), self._cells(), engine, loader,
                             env_probe=clean_env, required_gb=7.0)
        self.assertEqual(len(result.runs), 2)
        self.assertTrue(all(r.valid for r in result.runs))
        self.assertEqual(engine.stopped, 2)          # server parado tras cada celda
        self.assertTrue(result.pristine)             # limpieza ejecutada y verificada

    def test_dirty_environment_blocks_without_force(self):
        url = self.start_fake(FakeConfig())
        engine = FakeServingEngine(url)

        def loader(base_url, cell):
            raise AssertionError("no debe llegar a cargar nada")

        result = run_battery(self._model(), self._cells()[:1], engine, loader,
                             env_probe=dirty_env, required_gb=7.0)
        self.assertFalse(result.runs[0].valid)
        self.assertIn("preflight", result.runs[0].error)
        self.assertEqual(engine.stopped, 0)          # ni se arrancó el server


class TestPercentile(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(percentile([1, 2, 3, 4], 50), 2.5)
        self.assertEqual(percentile([10], 95), 10)
        self.assertEqual(percentile([], 95), 0.0)


if __name__ == "__main__":
    unittest.main()

"""Adapter llama-server — ServingEnginePort para perfiles de concurrencia (A-E).

Construye el comando según la celda + técnicas (ngram-mod, kv-unified, q8/q8...),
arranca, espera /health, y para limpio. La ejecución real con modelo queda gated
por el pre-flight ambiental (domain.environment) en el battery runner.
"""
from __future__ import annotations

import re
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from ...domain.entities import CellSpec, EngineInfo, ModelSpec
from ...ports import ServerHandle


@dataclass
class LlamaServer:
    binary: str = "llama-server"
    host: str = "127.0.0.1"
    port: int = 8099
    startup_timeout_s: float = 300.0
    _proc: subprocess.Popen | None = field(default=None, repr=False)
    _info: EngineInfo | None = field(default=None, repr=False)

    def info(self) -> EngineInfo:
        if self._info is None:
            out = subprocess.run([self.binary, "--version"], capture_output=True,
                                 text=True, timeout=60)
            blob = out.stdout + out.stderr
            ver = re.search(r"version:\s+(\d+)\s+\(([0-9a-f]+)\)", blob)
            self._info = EngineInfo("llamacpp-server",
                                    ver.group(1) if ver else "unknown",
                                    ver.group(2) if ver else None)
        return self._info

    def capabilities(self) -> set[str]:
        return {"kv_q8", "kv_q4", "flash_attn", "spec_ngram_mod", "kv_unified",
                "prefix_cache_reuse", "rope_yarn"}

    def build_cmd(self, cell: CellSpec, model: ModelSpec) -> list[str]:
        cmd = [self.binary, "-m", str(model.file_path),
               "--host", self.host, "--port", str(self.port),
               "-c", str(cell.ctx), "-np", str(cell.slots),
               "-ngl", "99", "--no-webui"]
        t = cell.techniques
        if "flash_attn" in t:
            cmd += ["--flash-attn", "on"]
        if "kv_q8" in t:
            cmd += ["--cache-type-k", "q8_0", "--cache-type-v", "q8_0"]
        elif "kv_q4" in t:
            cmd += ["--cache-type-k", "q4_0", "--cache-type-v", "q4_0"]
        if "kv_unified" in t:
            cmd += ["--kv-unified"]
        if "spec_ngram_mod" in t:
            cmd += ["--spec-type", "ngram-mod"]
        if "prefix_cache_reuse" in t:
            cmd += ["--cache-reuse", "256"]
        # YaRN OBLIGATORIO si el contexto pedido supera el nativo del modelo:
        # nunca extrapolar en silencio; el run queda además sujeto a balizas de
        # consistencia (adapters/corpus/verifiable.py) — auditoría 2026-06-06
        if cell.ctx > model.context_native > 0:
            cmd += ["--rope-scaling", "yarn",
                    "--yarn-orig-ctx", str(model.context_native)]
        return cmd

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def serve(self, cell: CellSpec, model: ModelSpec,
              log_path: str | Path | None = None) -> ServerHandle:
        log = open(log_path, "w") if log_path else subprocess.DEVNULL
        self._proc = subprocess.Popen(self.build_cmd(cell, model),
                                      stdout=log, stderr=subprocess.STDOUT)
        t0 = time.time()
        while time.time() - t0 < self.startup_timeout_s:
            if self._proc.poll() is not None:
                raise RuntimeError(f"llama-server murió al arrancar (exit {self._proc.returncode})")
            try:
                with urllib.request.urlopen(self.base_url + "/health", timeout=3) as r:
                    if r.status == 200:
                        return ServerHandle(base_url=self.base_url, pid=self._proc.pid)
            except OSError:
                time.sleep(1.0)
        self.stop(None)
        raise RuntimeError("llama-server no respondió /health a tiempo")

    def stop(self, handle: ServerHandle | None) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None

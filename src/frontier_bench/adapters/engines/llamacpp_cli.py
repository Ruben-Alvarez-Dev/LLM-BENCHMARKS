"""Adapter llama.cpp (llama-cli) — protocolo de medición F1 para perfil S.

Por celda y profundidad D:
  warmup (descartado) + N reps de: prefill(corpus real de D tokens) → decode 128 tokens.
  Cada rep paga su prefill completo (sin --prompt-cache en builds modernos) — eso da
  N muestras también de prefill. RSS muestreado a 1Hz desde un hilo.
  + 1 run de needles (recall a profundidad) con la pregunta al final.

Provenance: versión+commit de llama-cli, flags, modelo (ruta+bytes), fingerprint del corpus.
"""
from __future__ import annotations

import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from ...domain.entities import CellSpec, EngineInfo, Measurement, ModelSpec, Run
from ...domain.quality import (degeneration, insert_needles, make_needles,
                               needle_question, needle_recall)

GiB = 1024 ** 3

# ── parsers de timings: soporta llama_print_timings (viejo) y llama_perf_* (moderno) ──
_PATTERNS = {
    "prompt_ms": [
        r"llama_print_timings:\s+prompt eval time\s+=\s+([\d.]+)\s+ms",
        r"llama_perf_context_print:\s+prompt eval time\s+=\s+([\d.]+)\s+ms",
    ],
    "prompt_tokens": [
        r"prompt eval time\s+=\s+[\d.]+\s+ms\s+/\s+(\d+)\s+tokens",
    ],
    "eval_ms": [
        r"llama_print_timings:\s+eval time\s+=\s+([\d.]+)\s+ms",
        r"llama_perf_context_print:\s+eval time\s+=\s+([\d.]+)\s+ms",
    ],
    "eval_tokens": [
        # anclado a ':' para NO capturar la línea "prompt eval time"
        r"(?:llama_print_timings|llama_perf_context_print):\s+eval time\s+=\s+[\d.]+\s+ms\s+/\s+(\d+)\s+(?:runs|tokens)",
    ],
    "load_ms": [
        r"load time\s+=\s+([\d.]+)\s+ms",
    ],
}


def parse_timings(raw: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, pats in _PATTERNS.items():
        for pat in pats:
            m = re.search(pat, raw)
            if m:
                out[key] = float(m.group(1))
                break
    if "prompt_ms" in out and "prompt_tokens" in out and out["prompt_ms"] > 0:
        out["prefill_tps"] = out["prompt_tokens"] / (out["prompt_ms"] / 1000)
    if "eval_ms" in out and "eval_tokens" in out and out["eval_ms"] > 0:
        out["decode_tps"] = out["eval_tokens"] / (out["eval_ms"] / 1000)
    if "load_ms" in out and "prompt_ms" in out:
        out["ttft_ms"] = out["load_ms"] + out["prompt_ms"]
    return out


class _RssSampler(threading.Thread):
    """Muestrea RSS del proceso a 1Hz (ps -o rss=). Pico en .peak_gb."""

    def __init__(self, pid: int):
        super().__init__(daemon=True)
        self.pid = pid
        self.samples: list[float] = []
        self._stop = threading.Event()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                out = subprocess.run(["ps", "-o", "rss=", "-p", str(self.pid)],
                                     capture_output=True, text=True, timeout=5)
                kb = float(out.stdout.strip() or 0)
                if kb > 0:
                    self.samples.append(kb * 1024 / GiB)
            except Exception:
                pass
            self._stop.wait(1.0)

    def stop(self) -> float:
        self._stop.set()
        return max(self.samples) if self.samples else 0.0


@dataclass
class LlamaCppCli:
    """Implementa EnginePort para perfil S (single-stream, decode-at-depth)."""
    binary: str = "llama-cli"
    extra_args: tuple[str, ...] = ()
    timeout_s: float = 1800.0
    _info: EngineInfo | None = field(default=None, repr=False)

    def info(self) -> EngineInfo:
        if self._info is None:
            out = subprocess.run([self.binary, "--version"], capture_output=True,
                                 text=True, timeout=60)
            blob = out.stdout + out.stderr
            ver = re.search(r"version:\s+(\d+)\s+\(([0-9a-f]+)\)", blob)
            self._info = EngineInfo(
                engine_id="llamacpp",
                version=ver.group(1) if ver else "unknown",
                commit=ver.group(2) if ver else None)
        return self._info

    def capabilities(self) -> set[str]:
        return {"kv_q8", "kv_q4", "flash_attn", "spec_ngram_mod", "kv_unified",
                "rope_yarn", "prefix_cache_reuse"}

    # ── ejecución ──
    def _cmd(self, model: ModelSpec, cell: CellSpec, prompt_file: Path, n_gen: int) -> list[str]:
        cmd = [self.binary, "-m", str(model.file_path), "-c", str(cell.ctx),
               "-n", str(n_gen), "--temp", "0.0", "-ngl", "99", "-st",
               "--no-display-prompt", "--seed", "42"]
        dims: dict[str, str] = {}
        if "flash_attn" in cell.techniques:
            cmd += ["-fa", "on"]
        if "kv_q8" in cell.techniques:
            cmd += ["-ctk", "q8_0", "-ctv", "q8_0"]
        elif "kv_q4" in cell.techniques:
            cmd += ["-ctk", "q4_0", "-ctv", "q4_0"]
        if prompt_file is not None:
            cmd += ["-f", str(prompt_file)]
        cmd += list(self.extra_args)
        return cmd

    def _exec(self, cmd: list[str]) -> tuple[str, str, float]:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True)
        sampler = _RssSampler(proc.pid)
        sampler.start()
        try:
            stdout, stderr = proc.communicate(timeout=self.timeout_s)
        finally:
            peak = sampler.stop()
        return stdout, stderr, peak

    def run_cell(self, cell: CellSpec, model: ModelSpec, corpus, workdir: str | Path,
                 reps: int = 3, warmup: int = 1, n_gen: int = 128,
                 corpus_seed: int = 1234) -> Run:
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        run = Run(cell_key="", n_reps=reps)

        # prompt a profundidad D (corpus real); D=0 => prompt mínimo
        depth = cell.depth_tokens
        base_text = corpus.text_tokens(depth, corpus_seed) if depth > 0 else "Hola."
        prompt_file = workdir / f"prompt_d{cell.depth_pct}_{cell.ctx}.txt"
        prompt_file.write_text(base_text)

        raws: list[str] = []
        for i in range(warmup + reps):
            stdout, stderr, peak_gb = self._exec(self._cmd(model, cell, prompt_file, n_gen))
            raw = stdout + "\n" + stderr
            raws.append(f"### rep {i} {'(warmup)' if i < warmup else ''}\n{raw}")
            if i < warmup:
                continue
            rep = i - warmup
            t = parse_timings(raw)
            if "decode_tps" not in t:
                run.error = f"rep {rep}: sin timings parseables"
                continue
            for metric, unit in (("decode_tps", "tok/s"), ("prefill_tps", "tok/s"),
                                 ("ttft_ms", "ms"), ("prompt_tokens", "tok")):
                if metric in t:
                    run.measurements.append(Measurement(metric, t[metric], unit, rep))
            run.measurements.append(Measurement("rss_peak_gb", peak_gb, "GiB", rep))
            deg = degeneration(stdout)
            run.measurements.append(Measurement("degenerate", float(deg.degenerate), "bool", rep))

        # needles (1 vez por celda, solo con profundidad real)
        if depth > 0:
            needles = make_needles(seed=corpus_seed)
            ntext = insert_needles(base_text, needles) + needle_question(needles)
            nfile = workdir / f"needle_d{cell.depth_pct}_{cell.ctx}.txt"
            nfile.write_text(ntext)
            stdout, stderr, _ = self._exec(self._cmd(model, cell, nfile, 64))
            run.measurements.append(Measurement(
                "needle_recall", float(needle_recall(stdout, needles)), "n/3", 0))
            raws.append(f"### needles\n{stdout[-2000:]}")

        raw_path = workdir / f"raw_{cell.model_id}_ctx{cell.ctx}_d{cell.depth_pct}.log"
        raw_path.write_text("\n\n".join(raws))
        run.raw_ref = str(raw_path)
        return run

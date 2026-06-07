"""Adapter llama-bench — medición de velocidad con PROFUNDIDAD NATIVA (-d).

Decisión 2026-06-06 (ver SESSION.md): llama-cli b8880 dejó de emitir timings
parseables en single-turn (UI de chat). llama-bench es el instrumento correcto:
  -d N  : decode con N tokens YA en caché (decode-at-depth de serie)
  -r N  : repeticiones integradas con media y σ
  -o json: salida estable, sin regex frágiles
Reparto de responsabilidades: velocidad => llama-bench; calidad/needles (texto
generado real) => llama-cli (sus timings dan igual ahí).
"""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from ...domain.entities import CellSpec, EngineInfo, Measurement, ModelSpec, Run


def parse_bench_json(raw: str) -> list[dict]:
    """llama-bench -o json => lista de resultados. Tolerante a campos según build:
    avg_ts/stddev_ts (clásico) o samples_ts (lista de muestras)."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # algunos builds imprimen líneas de progreso antes del JSON
        m = re.search(r"\[\s*{.*}\s*\]", raw, re.DOTALL)
        if not m:
            return []
        data = json.loads(m.group(0))
    return data if isinstance(data, list) else [data]


def rows_to_measurements(rows: list[dict]) -> list[Measurement]:
    out: list[Measurement] = []
    for row in rows:
        n_gen = int(row.get("n_gen", 0))
        n_prompt = int(row.get("n_prompt", 0))
        metric = "decode_tps" if n_gen > 0 else "prefill_tps"
        samples = row.get("samples_ts") or []
        if samples:
            for i, v in enumerate(samples):
                out.append(Measurement(metric, float(v), "tok/s", i))
        elif row.get("avg_ts") is not None:
            out.append(Measurement(metric, float(row["avg_ts"]), "tok/s", 0))
            if row.get("stddev_ts") is not None:
                out.append(Measurement(f"{metric}_stddev", float(row["stddev_ts"]), "tok/s", 0))
        depth = row.get("n_depth", row.get("depth"))
        if depth is not None:
            out.append(Measurement(f"{metric}_at_depth", float(depth), "tok", 0))
    return out


@dataclass
class LlamaBench:
    binary: str = "llama-bench"
    timeout_s: float = 3600.0
    _info: EngineInfo | None = field(default=None, repr=False)

    def info(self) -> EngineInfo:
        if self._info is None:
            out = subprocess.run([self.binary, "--version"], capture_output=True,
                                 text=True, timeout=60)
            blob = out.stdout + out.stderr
            ver = re.search(r"version:\s+(\d+)\s+\(([0-9a-f]+)\)", blob)
            self._info = EngineInfo("llamacpp-bench",
                                    ver.group(1) if ver else "unknown",
                                    ver.group(2) if ver else None)
        return self._info

    def capabilities(self) -> set[str]:
        return {"kv_q8", "kv_q4", "flash_attn"}

    def build_cmd(self, model: ModelSpec, cell: CellSpec, reps: int,
                  n_gen: int = 128, n_prompt: int = 512,
                  depths: list[int] | None = None,
                  delay_s: int = 2) -> list[str]:
        # multi-depth nativo (censo 2026-06-06): toda la escalera de profundidades
        # en UNA invocación — mismo proceso, menos varianza; --delay asienta entre tests
        d_arg = ",".join(str(d) for d in depths) if depths else str(cell.depth_tokens)
        cmd = [self.binary, "-m", str(model.file_path),
               "-p", str(n_prompt), "-n", str(n_gen),
               "-d", d_arg, "-r", str(reps),
               "--delay", str(delay_s),
               "-ngl", "99", "-o", "json", "--progress"]
        if "flash_attn" in cell.techniques:
            cmd += ["-fa", "1"]
        if "kv_q8" in cell.techniques:
            cmd += ["-ctk", "q8_0", "-ctv", "q8_0"]
        elif "kv_q4" in cell.techniques:
            cmd += ["-ctk", "q4_0", "-ctv", "q4_0"]
        return cmd

    def run_cell(self, cell: CellSpec, model: ModelSpec, workdir: str | Path,
                 reps: int = 3) -> Run:
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        cmd = self.build_cmd(model, cell, reps)
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=self.timeout_s)
        raw_path = workdir / f"bench_{cell.model_id}_ctx{cell.ctx}_d{cell.depth_pct}.json"
        raw_path.write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr)

        run = Run(cell_key="", n_reps=reps, raw_ref=str(raw_path))
        rows = parse_bench_json(proc.stdout)
        if not rows:
            run.error = f"llama-bench sin JSON parseable (exit {proc.returncode})"
            return run
        run.measurements = rows_to_measurements(rows)
        return run

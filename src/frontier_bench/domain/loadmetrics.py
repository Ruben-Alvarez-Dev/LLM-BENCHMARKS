"""Métricas de carga concurrente — funciones puras sobre resultados de requests.

Convierte la lista de RequestResult (lo que devuelve el LoadGen) en las métricas
que deciden veredictos: agregado, por-stream, TTFT p50/p95, error rate y
%reprefill (detector de la regresión de checkpoints en híbridos: #20225/#24055).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from .entities import Measurement


@dataclass(frozen=True)
class RequestResult:
    stream_id: int
    t_start: float            # epoch s
    ttft_ms: float            # primer token
    total_ms: float
    tokens_out: int
    prompt_tokens: int = 0    # tokens de prompt PROCESADOS según el server (timings)
    prompt_total: int = 0     # tokens de prompt ENVIADOS (estimado cliente)
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    @property
    def decode_tps(self) -> float:
        gen_ms = self.total_ms - self.ttft_ms
        return self.tokens_out / (gen_ms / 1000) if gen_ms > 0 and self.tokens_out else 0.0

    @property
    def reprefilled(self) -> bool:
        """True si el server re-procesó la mayoría del prompt pese a prefijo cacheado."""
        if self.prompt_total <= 0 or self.prompt_tokens <= 0:
            return False
        return self.prompt_tokens > 0.5 * self.prompt_total


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    vs = sorted(values)
    k = (len(vs) - 1) * pct / 100
    lo, hi = int(k), min(int(k) + 1, len(vs) - 1)
    return vs[lo] + (vs[hi] - vs[lo]) * (k - lo)


@dataclass
class LoadMetrics:
    measurements: list[Measurement] = field(default_factory=list)


def compute(results: list[RequestResult], wall_s: float,
            expect_cached_prefix: bool = False) -> LoadMetrics:
    out = LoadMetrics()
    ok = [r for r in results if r.ok]
    add = out.measurements.append

    add(Measurement("requests_total", float(len(results)), "req"))
    add(Measurement("error_rate_pct",
                    100.0 * (len(results) - len(ok)) / len(results) if results else 0.0, "%"))
    if ok:
        total_tokens = sum(r.tokens_out for r in ok)
        add(Measurement("aggregate_tps", total_tokens / wall_s if wall_s > 0 else 0.0, "tok/s"))
        per_stream = [r.decode_tps for r in ok if r.decode_tps > 0]
        if per_stream:
            add(Measurement("per_stream_tps_p50", median(per_stream), "tok/s"))
            add(Measurement("per_stream_tps_min", min(per_stream), "tok/s"))
        ttfts = [r.ttft_ms for r in ok]
        add(Measurement("ttft_ms_p50", percentile(ttfts, 50), "ms"))
        add(Measurement("ttft_ms_p95", percentile(ttfts, 95), "ms"))
        if expect_cached_prefix:
            # solo cuentan los requests POSTERIORES al primero de cada stream
            later = [r for r in ok if r.prompt_total > 0]
            if later:
                rep = sum(1 for r in later if r.reprefilled)
                add(Measurement("reprefill_pct", 100.0 * rep / len(later), "%"))
    return out

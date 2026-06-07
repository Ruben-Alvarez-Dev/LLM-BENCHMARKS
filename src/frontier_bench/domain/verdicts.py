"""VerdictEngine — convierte medidas en respuestas, con regla+versión+evidencia.

La pregunta original de Rubén: "que el benchmark diga directamente: este modelo
sirve para concurrencias de hasta 4, y este no". Eso es `frontera()`.

Puro: recibe métricas agregadas (medianas de runs VÁLIDOS) y reglas declarativas.
Un veredicto sin evidencia enlazada no existe.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional


@dataclass(frozen=True)
class Verdict:
    rule: str
    rule_version: str
    subject: dict                 # {model, machine, ctx, slots...}
    passed: bool
    failures: tuple[str, ...]     # qué umbral falló y por cuánto
    evidence: tuple[str, ...]     # cell_keys / run_ids que sustentan


def check_requirements(requires: Mapping[str, dict],
                       metrics: Mapping[str, float],
                       optional: Mapping[str, dict] | None = None
                       ) -> tuple[bool, list[str]]:
    """Evalúa umbrales {metric: {min|max: x}} contra métricas medidas.
    Métrica REQUERIDA ausente => fallo explícito (nada se aprueba por omisión).
    Métrica OPCIONAL ausente => se ignora (el perfil no corrió)."""
    failures: list[str] = []
    for metric, bound in requires.items():
        v = metrics.get(metric)
        if v is None:
            failures.append(f"{metric}: SIN MEDIR (requerida)")
            continue
        if "min" in bound and v < float(bound["min"]):
            failures.append(f"{metric}: {v:.1f} < min {bound['min']}")
        if "max" in bound and v > float(bound["max"]):
            failures.append(f"{metric}: {v:.1f} > max {bound['max']}")
    for metric, bound in (optional or {}).items():
        v = metrics.get(metric)
        if v is None:
            continue
        if "min" in bound and v < float(bound["min"]):
            failures.append(f"{metric}: {v:.1f} < min {bound['min']} (opcional medida)")
        if "max" in bound and v > float(bound["max"]):
            failures.append(f"{metric}: {v:.1f} > max {bound['max']} (opcional medida)")
    return (not failures), failures


def evaluate(rule_blocks: list[dict], subject: dict,
             metrics: Mapping[str, float],
             evidence: list[str]) -> list[Verdict]:
    """Aplica todas las reglas con `requires` al sujeto. Solo métricas de runs válidos."""
    out: list[Verdict] = []
    for rule in rule_blocks:
        requires = rule.get("requires")
        if not requires:
            continue
        passed, failures = check_requirements(requires, metrics, rule.get("optional"))
        out.append(Verdict(rule=rule["id"], rule_version=str(rule.get("version", "?")),
                           subject=dict(subject), passed=passed,
                           failures=tuple(failures), evidence=tuple(evidence)))
    return out


@dataclass
class FronteraEntry:
    model_id: str
    machine_id: str
    max_slots_por_ctx: dict[int, int] = field(default_factory=dict)
    max_ctx_consistente: int = 0


def frontera(concurrency_verdicts: list[Verdict],
             context_verdicts: list[Verdict]) -> list[FronteraEntry]:
    """LA respuesta: por (modelo, máquina), máximo N de slots aprobado por ctx
    y máximo ctx con consistencia aprobada."""
    table: dict[tuple[str, str], FronteraEntry] = {}

    def entry(s: dict) -> FronteraEntry:
        key = (s.get("model", "?"), s.get("machine", "?"))
        if key not in table:
            table[key] = FronteraEntry(model_id=key[0], machine_id=key[1])
        return table[key]

    for v in concurrency_verdicts:
        if v.rule != "apto_concurrencia" or not v.passed:
            continue
        e = entry(v.subject)
        ctx, slots = int(v.subject.get("ctx", 0)), int(v.subject.get("slots", 0))
        e.max_slots_por_ctx[ctx] = max(e.max_slots_por_ctx.get(ctx, 0), slots)

    for v in context_verdicts:
        if v.rule != "apto_contexto" or not v.passed:
            continue
        e = entry(v.subject)
        e.max_ctx_consistente = max(e.max_ctx_consistente,
                                    int(v.subject.get("ctx", 0)))
    return sorted(table.values(), key=lambda e: (e.model_id, e.machine_id))


def derive_context_metrics(decode_at_depth0: Optional[float],
                           decode_at_depth90: Optional[float],
                           beacons_ok: int, beacons_asked: int,
                           degenerate_runs: int, total_runs: int) -> dict[str, float]:
    """Métricas derivadas para apto_contexto a partir de medidas crudas."""
    out: dict[str, float] = {}
    if decode_at_depth0 and decode_at_depth90 is not None:
        out["decode_retention_pct"] = 100.0 * decode_at_depth90 / decode_at_depth0
    if beacons_asked:
        out["beacon_recall_pct"] = 100.0 * beacons_ok / beacons_asked
    if total_runs:
        out["degenerate_rate_pct"] = 100.0 * degenerate_runs / total_runs
    return out

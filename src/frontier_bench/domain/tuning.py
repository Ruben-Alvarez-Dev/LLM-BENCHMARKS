"""TuningAdvisor — aplica tuning_rules.yaml al perfil del host y PROPONE parámetros.

Propone, no impone: cada sugerencia lleva la regla que la originó y su evidencia;
la celda registra sugerido-vs-usado. Auto-adaptación de specs/v2/05 §3.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Suggestion:
    params: dict
    rule_index: int
    evidence: tuple[str, ...] = ()


def _match(when: dict, facts: dict) -> bool:
    """facts esperados: platform, ram_gb, cpu_vendor, isa (lista), os..."""
    for key, cond in (when or {}).items():
        if key == "has_isa":
            isa = set(facts.get("isa", []))
            if not set(cond if isinstance(cond, list) else [cond]) <= isa:
                return False
        elif isinstance(cond, dict):
            v = facts.get(key)
            if v is None:
                return False
            if "lte" in cond and not v <= cond["lte"]:
                return False
            if "gte" in cond and not v >= cond["gte"]:
                return False
        else:
            if str(facts.get(key, "")).lower() != str(cond).lower():
                return False
    return True


def advise(rule_blocks: list[dict], facts: dict) -> tuple[dict, list[Suggestion]]:
    """Devuelve (parámetros fusionados en orden de reglas, sugerencias con origen)."""
    merged: dict = {}
    suggestions: list[Suggestion] = []
    for i, rule in enumerate(rule_blocks):
        if not _match(rule.get("when", {}), facts):
            continue
        params = rule.get("suggest", {}) or {}
        merged.update(params)
        suggestions.append(Suggestion(params=dict(params), rule_index=i,
                                      evidence=tuple(rule.get("evidence", []) or [])))
    return merged, suggestions


def facts_from_host_profile(profile) -> dict:
    """Adapta HostProfile (adapters/probes) al dict que esperan las reglas."""
    f = profile.facts
    chip = (f.chip or "").lower()
    vendor = ("apple" if "apple" in chip else
              "intel" if "intel" in chip or "xeon" in chip else
              "amd" if "amd" in chip or "ryzen" in chip or "epyc" in chip else "?")
    isa = []
    if profile.arch == "arm64":
        isa.append("neon")
    return {"platform": f.platform.value, "ram_gb": f.ram_gb,
            "cpu_vendor": vendor, "isa": isa, "os": profile.os_name}

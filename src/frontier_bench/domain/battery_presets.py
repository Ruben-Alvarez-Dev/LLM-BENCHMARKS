"""Battery presets — professional declarative batteries (SPEC 06).

Pure domain. Consumes parsed blocks (list[dict]) — yaml_lite stays at the
boundary, same pattern as tuning.advise(). No I/O here.

Semantics mirror the house rules:
- The plan is generated DRY; execution belongs to the F3 executor.
- A hypothesis whose metric was never measured is an EXPLICIT FAIL
  ("unmeasured"), never a silent pass.
"""
from __future__ import annotations

from dataclasses import dataclass, field

VALID_PROFILES = {"A", "B", "C", "D", "E"}
VALID_OPS = {"gte", "lte", "between"}
SCOPE_KEYS = {"profile", "model", "np", "variant"}


@dataclass(frozen=True)
class Hypothesis:
    id: str
    battery: str
    statement: str
    metric: str
    op: str
    value: float | None = None
    low: float | None = None
    high: float | None = None
    scope: dict = field(default_factory=dict)

    def matches(self, *, profile: str, model: str, np: int, variant: str) -> bool:
        cell = {"profile": profile, "model": model, "np": np, "variant": variant}
        return all(cell.get(k) == v for k, v in self.scope.items())

    def check(self, measured: float) -> bool:
        if self.op == "gte":
            return measured >= float(self.value)
        if self.op == "lte":
            return measured <= float(self.value)
        return float(self.low) <= measured <= float(self.high)


@dataclass(frozen=True)
class BatteryPreset:
    id: str
    description: str
    models: tuple
    server: dict
    np: tuple
    variants: tuple
    profiles: tuple
    hypotheses: tuple  # of Hypothesis
    spec: str = ""


@dataclass(frozen=True)
class PlannedBatteryCell:
    battery_id: str
    model: str
    np: int
    variant: str
    profile: str
    hypothesis_ids: tuple


def _err(msg: str) -> ValueError:
    return ValueError(f"batteries: {msg}")


def load_presets(blocks: list[dict]) -> list[BatteryPreset]:
    batteries: dict[str, dict] = {}
    hypos: list[dict] = []
    for b in blocks:
        kind = b.get("kind")
        if kind == "battery":
            if not b.get("id"):
                raise _err("battery block without id")
            if b["id"] in batteries:
                raise _err(f"duplicate battery id '{b['id']}'")
            batteries[b["id"]] = b
        elif kind == "hypothesis":
            hypos.append(b)
        else:
            raise _err(f"block '{b.get('id')}' has unknown kind '{kind}'")

    parsed_hypos: dict[str, list[Hypothesis]] = {bid: [] for bid in batteries}
    seen_h: set[str] = set()
    for h in hypos:
        hid = h.get("id") or ""
        if not hid or hid in seen_h:
            raise _err(f"hypothesis with missing or duplicate id '{hid}'")
        seen_h.add(hid)
        bid = h.get("battery") or ""
        if bid not in batteries:
            raise _err(f"hypothesis '{hid}' references unknown battery '{bid}'")
        op = h.get("op") or ""
        if op not in VALID_OPS:
            raise _err(f"hypothesis '{hid}' has invalid op '{op}'")
        if op == "between" and (h.get("low") is None or h.get("high") is None):
            raise _err(f"hypothesis '{hid}' op=between requires low and high")
        if op in ("gte", "lte") and h.get("value") is None:
            raise _err(f"hypothesis '{hid}' op={op} requires value")
        scope = h.get("scope") or {}
        unknown = set(scope) - SCOPE_KEYS
        if unknown:
            raise _err(f"hypothesis '{hid}' has unknown scope keys {sorted(unknown)}")
        if not h.get("metric"):
            raise _err(f"hypothesis '{hid}' lacks a metric")
        parsed_hypos[bid].append(Hypothesis(
            id=hid, battery=bid, statement=h.get("statement", ""),
            metric=h["metric"], op=op, value=h.get("value"),
            low=h.get("low"), high=h.get("high"), scope=scope,
        ))

    presets: list[BatteryPreset] = []
    for bid, b in batteries.items():
        models = b.get("models") or []
        profiles = b.get("profiles") or []
        if not models:
            raise _err(f"battery '{bid}' has no models")
        bad = set(profiles) - VALID_PROFILES
        if bad:
            raise _err(f"battery '{bid}' has unknown profiles {sorted(bad)}")
        if not parsed_hypos[bid]:
            raise _err(f"battery '{bid}' has no hypotheses — a battery without "
                       "falsifiable hypotheses is not a battery")
        presets.append(BatteryPreset(
            id=bid, description=b.get("description", ""),
            models=tuple(models), server=b.get("server") or {},
            np=tuple(b.get("np") or [1]), variants=tuple(b.get("variants") or ["baseline"]),
            profiles=tuple(profiles), hypotheses=tuple(parsed_hypos[bid]),
            spec=b.get("spec", ""),
        ))
    return presets


def plan(preset: BatteryPreset) -> list[PlannedBatteryCell]:
    """Cartesian dry plan; each cell lists the hypotheses it can serve."""
    cells: list[PlannedBatteryCell] = []
    for model in preset.models:
        for n in preset.np:
            for variant in preset.variants:
                for profile in preset.profiles:
                    hids = tuple(h.id for h in preset.hypotheses
                                 if h.matches(profile=profile, model=model,
                                              np=n, variant=variant))
                    cells.append(PlannedBatteryCell(
                        battery_id=preset.id, model=model, np=n,
                        variant=variant, profile=profile, hypothesis_ids=hids,
                    ))
    return cells


def report(preset: BatteryPreset, measurements: dict[str, float]) -> dict:
    """Verdict per hypothesis. Missing metric => explicit 'unmeasured' fail."""
    verdicts = {}
    for h in preset.hypotheses:
        if h.metric not in measurements:
            verdicts[h.id] = {"status": "unmeasured", "passed": False,
                              "reason": f"metric '{h.metric}' was never measured"}
        else:
            ok = h.check(measurements[h.metric])
            verdicts[h.id] = {"status": "measured", "passed": ok,
                              "measured": measurements[h.metric]}
    passed = all(v["passed"] for v in verdicts.values())
    return {"battery": preset.id, "passed": passed, "hypotheses": verdicts}

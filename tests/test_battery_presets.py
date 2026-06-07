"""Tests: battery presets (SPEC 06) — parser real, validacion, plan y report."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from frontier_bench.adapters.web.yaml_lite import load_blocks
from frontier_bench.domain.battery_presets import (
    load_presets, plan, report, Hypothesis,
)

ROOT = os.path.join(os.path.dirname(__file__), "..")


def real_blocks():
    with open(os.path.join(ROOT, "batteries.yaml")) as f:
        return load_blocks(f.read())


class TestRealFile(unittest.TestCase):
    def test_real_file_parses_and_validates(self):
        presets = load_presets(real_blocks())
        ids = {p.id for p in presets}
        self.assertEqual(ids, {"multislot_certification", "smoke"})

    def test_no_multiline_arrays_regression(self):
        """yaml_lite no soporta arrays multilinea: si un campo lista llega
        como str, el fichero esta mal escrito (regresion conocida)."""
        for b in real_blocks():
            for key in ("models", "np", "variants", "profiles"):
                if key in b:
                    self.assertIsInstance(b[key], list,
                                          f"{b.get('id')}.{key} parsed as non-list")

    def test_multislot_plan_cardinality(self):
        presets = {p.id: p for p in load_presets(real_blocks())}
        cells = plan(presets["multislot_certification"])
        # 4 modelos x 3 np x 2 variantes x 5 perfiles
        self.assertEqual(len(cells), 4 * 3 * 2 * 5)

    def test_hypotheses_attach_to_matching_cells_only(self):
        presets = {p.id: p for p in load_presets(real_blocks())}
        cells = plan(presets["multislot_certification"])
        h6_cells = [c for c in cells if "H6" in c.hypothesis_ids]
        self.assertTrue(h6_cells)
        for c in h6_cells:
            self.assertEqual((c.profile, c.np), ("A", 8))
        h1_cells = [c for c in cells if "H1" in c.hypothesis_ids]
        for c in h1_cells:
            self.assertEqual(c.model, "Granite-4.1-8B")
            self.assertEqual(c.profile, "D")


class TestValidation(unittest.TestCase):
    def _battery(self, **over):
        b = {"id": "b1", "kind": "battery", "models": ["m"],
             "profiles": ["A"], "np": [1], "variants": ["baseline"]}
        b.update(over)
        return b

    def _hypo(self, **over):
        h = {"id": "h1", "kind": "hypothesis", "battery": "b1",
             "metric": "x", "op": "gte", "value": 1}
        h.update(over)
        return h

    def test_battery_without_hypotheses_rejected(self):
        with self.assertRaises(ValueError):
            load_presets([self._battery()])

    def test_orphan_hypothesis_rejected(self):
        with self.assertRaises(ValueError):
            load_presets([self._battery(), self._hypo(battery="nope")])

    def test_invalid_op_rejected(self):
        with self.assertRaises(ValueError):
            load_presets([self._battery(), self._hypo(op="eq")])

    def test_between_requires_bounds(self):
        with self.assertRaises(ValueError):
            load_presets([self._battery(),
                          self._hypo(op="between", value=None)])

    def test_unknown_profile_rejected(self):
        with self.assertRaises(ValueError):
            load_presets([self._battery(profiles=["Z"]), self._hypo()])

    def test_unknown_scope_key_rejected(self):
        with self.assertRaises(ValueError):
            load_presets([self._battery(),
                          self._hypo(scope={"machine": "x"})])


class TestReport(unittest.TestCase):
    def setUp(self):
        self.presets = {p.id: p for p in load_presets([
            {"id": "b1", "kind": "battery", "models": ["m"], "profiles": ["A"],
             "np": [1], "variants": ["baseline"]},
            {"id": "h1", "kind": "hypothesis", "battery": "b1",
             "metric": "tps", "op": "gte", "value": 8.0},
            {"id": "h2", "kind": "hypothesis", "battery": "b1",
             "metric": "err", "op": "lte", "value": 0.0},
        ])}

    def test_unmeasured_is_explicit_fail(self):
        r = report(self.presets["b1"], {"tps": 9.0})
        self.assertFalse(r["passed"])
        self.assertEqual(r["hypotheses"]["h2"]["status"], "unmeasured")

    def test_all_measured_and_passing(self):
        r = report(self.presets["b1"], {"tps": 9.0, "err": 0.0})
        self.assertTrue(r["passed"])

    def test_between_check(self):
        h = Hypothesis(id="x", battery="b", statement="", metric="m",
                       op="between", low=2.0, high=3.0)
        self.assertTrue(h.check(2.5))
        self.assertFalse(h.check(3.5))


if __name__ == "__main__":
    unittest.main()

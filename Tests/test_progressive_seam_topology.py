# -*- coding: utf-8 -*-
"""Focused V4.73 bounded local-topology search regressions."""

from __future__ import annotations

import unittest
from types import SimpleNamespace

try:
    import Part
    from FreeCAD import Vector
except ImportError:  # pragma: no cover
    Part = Vector = None

from Commands.SplitPanelCommand import _progressive_four_part_split
from Core.SinuousSeamPath import SinuousSeamPathFinder


@unittest.skipIf(Part is None, "FreeCAD Part module is unavailable")
class ProgressiveSeamTopologyTests(unittest.TestCase):
    @staticmethod
    def _case():
        source = Part.makeBox(300.0, 300.0, 8.0)
        for x_value, y_value in (
            (152.0, 50.0), (152.0, 250.0),
            (50.0, 148.0), (250.0, 148.0),
        ):
            source = source.cut(
                Part.makeCylinder(8.0, 8.0, Vector(x_value, y_value, 0.0))
            )
        finder = SinuousSeamPathFinder()
        candidates = finder.topology_shortlist(
            finder.generate(source), (0.0, 300.0, 0.0, 300.0)
        )
        return finder, candidates

    @staticmethod
    def _center_for(plan, detour_id):
        for path in (plan.vertical, plan.horizontal):
            if detour_id in path.detour_ids:
                index = path.detour_ids.index(detour_id)
                feature_id = path.detour_feature_ids[index]
                feature = next(
                    item for item in plan.features
                    if item.feature_id == feature_id
                )
                xmin, ymin, xmax, ymax = feature.bounds_mm
                return SimpleNamespace(
                    x=0.5 * (xmin + xmax), y=0.5 * (ymin + ymax)
                )
        raise AssertionError(detour_id)

    @staticmethod
    def _invalid(plan, detour_id):
        center = ProgressiveSeamTopologyTests._center_for(plan, detour_id)
        solids = [SimpleNamespace(Volume=1.0, CenterOfMass=center)]
        solids.extend(
            SimpleNamespace(
                Volume=1000.0 + index,
                CenterOfMass=SimpleNamespace(x=150.0, y=150.0),
            )
            for index in range(4)
        )
        return SimpleNamespace(
            solid_count=5,
            shape=SimpleNamespace(Solids=tuple(solids)),
            seam_plan=plan,
        )

    def test_two_problem_detours_are_reduced_progressively_to_four_parts(self):
        finder, candidates = self._case()

        def validate(plan):
            if finder.detour_level(plan, "VDET_001") == 3:
                return self._invalid(plan, "VDET_001")
            if finder.detour_level(plan, "HDET_001") == 3:
                return self._invalid(plan, "HDET_001")
            return SimpleNamespace(solid_count=4, seam_plan=plan)

        result = _progressive_four_part_split(
            finder, candidates, (0.0, 300.0, 0.0, 300.0), validate
        )
        accepted, validations, _rejected, _success, diagnostics, _elapsed = result
        self.assertIsNotNone(accepted)
        self.assertEqual(validations, 3)
        self.assertEqual(accepted.seam_plan.vertical.detour_levels, (2, 3))
        self.assertEqual(accepted.seam_plan.horizontal.detour_levels, (2, 3))
        self.assertIn("VDET_001", diagnostics[0])
        self.assertIn("HDET_001", diagnostics[1])
        self.assertIn("accepted", diagnostics[2])
        self.assertEqual(accepted.seam_plan.intersection_count, 1)

    def test_validation_limit_retains_bounded_failure(self):
        finder, candidates = self._case()

        def invalid(plan):
            return self._invalid(plan, "VDET_001")

        accepted, validations, *_rest = _progressive_four_part_split(
            finder, candidates, (0.0, 300.0, 0.0, 300.0), invalid,
            maximum_validations=2,
        )
        self.assertIsNone(accepted)
        self.assertEqual(validations, 2)

    def test_planning_budget_stops_before_another_exact_validation(self):
        finder, candidates = self._case()
        values = iter((0.0, 0.0, 0.0, 31.0, 31.0, 31.0))

        def clock():
            return next(values)

        accepted, validations, *_rest = _progressive_four_part_split(
            finder,
            candidates,
            (0.0, 300.0, 0.0, 300.0),
            lambda plan: self._invalid(plan, "VDET_001"),
            time_budget_s=30.0,
            clock=clock,
        )
        self.assertIsNone(accepted)
        self.assertEqual(validations, 1)

    def test_highest_quality_valid_candidate_is_retained_immediately(self):
        finder, candidates = self._case()

        def valid(plan):
            return SimpleNamespace(solid_count=4, seam_plan=plan)

        accepted, validations, *_rest = _progressive_four_part_split(
            finder, candidates, (0.0, 300.0, 0.0, 300.0), valid
        )
        self.assertEqual(validations, 1)
        self.assertEqual(accepted.seam_plan, candidates[0])


if __name__ == "__main__":
    unittest.main()

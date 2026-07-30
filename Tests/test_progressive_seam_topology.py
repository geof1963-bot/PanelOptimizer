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
from Core.ConnectivityRepair import (
    ComponentConnectivityObservation,
    RegionConnectivityDiagnosis,
)
from Core.Exceptions import RegionConnectivityError
from Core.Settings import Settings
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

    @classmethod
    def _diagnosis(cls, plan, detours, *, slivers=0, region_index=2):
        """Build classified multi-island evidence in priority order."""
        def observation(rank, volume, detour_id, classification):
            center = cls._center_for(plan, detour_id)
            axis = "vertical" if detour_id.startswith("V") else "horizontal"
            return ComponentConnectivityObservation(
                rank=rank,
                volume_mm3=volume,
                bounds_mm=(center.x - 1.0, center.y - 1.0, 0.0,
                           center.x + 1.0, center.y + 1.0, 8.0),
                centroid_mm=(center.x, center.y, 4.0),
                nearest_seam=axis,
                nearest_segment_index=0,
                nearest_segment_id=("VSEG_001" if axis == "vertical"
                                    else "HSEG_001"),
                nearest_detour_id=detour_id,
                seam_distance_mm=float(rank),
                opening_distance_mm=1.0,
                footprint_mm2=4.0,
                thickness_mm=8.0,
                volume_ratio=volume / 100000.0,
                touches_panel_exterior=False,
                spans_substantial_thickness=True,
                classification=classification,
            )

        primary = detours[0]
        components = [observation(1, 100000.0, primary, "STRUCTURAL")]
        components.extend(
            observation(rank, volume, detour_id, "STRUCTURAL")
            for rank, (volume, detour_id) in enumerate(
                zip(
                    range(5000, 5000 - len(detours) * 500, -500),
                    detours,
                ),
                start=2,
            )
        )
        components.extend(
            observation(
                len(components) + 1,
                10.0 - index,
                primary,
                "NON_STRUCTURAL_SLIVER",
            )
            for index in range(slivers)
        )
        return RegionConnectivityDiagnosis(region_index, tuple(components))

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
        self.assertGreater(
            accepted.seam_plan.vertical.maximum_deviation_mm, 0.5
        )
        self.assertGreater(
            accepted.seam_plan.horizontal.maximum_deviation_mm, 0.5
        )
        self.assertTrue(all(
            report.original_profile_preserved
            for path in (
                accepted.seam_plan.vertical,
                accepted.seam_plan.horizontal,
            )
            for report in path.hole_offset_reports
        ))
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

    def test_multi_island_repairs_progress_across_multiple_detours(self):
        finder, candidates = self._case()

        def validate(plan):
            if finder.detour_level(plan, "VDET_001") == 3:
                raise RegionConnectivityError(self._diagnosis(
                    plan,
                    ("VDET_001", "HDET_001", "VDET_002", "HDET_002"),
                    slivers=2,
                ))
            if finder.detour_level(plan, "HDET_001") == 3:
                raise RegionConnectivityError(self._diagnosis(
                    plan, ("HDET_001", "VDET_002")
                ))
            return SimpleNamespace(solid_count=4, seam_plan=plan)

        accepted, validations, _rejected, _success, diagnostics, _elapsed = (
            _progressive_four_part_split(
                finder,
                candidates,
                (0.0, 300.0, 0.0, 300.0),
                validate,
            )
        )
        self.assertIsNotNone(accepted)
        self.assertEqual(validations, 3)
        self.assertEqual(accepted.seam_plan.vertical.detour_levels, (2, 3))
        self.assertEqual(accepted.seam_plan.horizontal.detour_levels, (2, 3))
        history = "\n".join(diagnostics)
        self.assertIn("7 raw, 2 slivers, 5 structural", history)
        self.assertIn("VDET_001 L3->L2: 5->3", history)
        self.assertIn("HDET_001 L3->L2: 3->1", history)

    def test_multi_island_search_limits_match_v474d_bounds(self):
        self.assertEqual(Settings.Split.MAX_MULTI_ISLAND_REPAIR_STEPS, 12)
        self.assertEqual(Settings.Split.MAX_CONNECTIVITY_EXACT_VALIDATIONS, 12)
        self.assertEqual(Settings.Split.MAX_CONNECTIVITY_REPAIR_TIME_S, 30.0)

    def test_worse_child_is_not_expanded_and_best_state_is_retained(self):
        finder, candidates = self._case()

        def validate(plan):
            vertical = finder.detour_level(plan, "VDET_001")
            horizontal = finder.detour_level(plan, "HDET_001")
            if vertical == 2:
                raise RegionConnectivityError(self._diagnosis(
                    plan,
                    ("VDET_001", "HDET_001", "VDET_002", "HDET_002",
                     "VDET_001"),
                ))
            if horizontal == 3:
                raise RegionConnectivityError(self._diagnosis(
                    plan,
                    ("VDET_001", "HDET_001", "VDET_002", "HDET_002"),
                ))
            return SimpleNamespace(solid_count=4, seam_plan=plan)

        accepted, validations, _r, _s, diagnostics, _e = (
            _progressive_four_part_split(
                finder,
                candidates,
                (0.0, 300.0, 0.0, 300.0),
                validate,
            )
        )
        self.assertIsNotNone(accepted)
        self.assertLessEqual(validations, 3)
        self.assertTrue(any(
            "restoring the best state" in item for item in diagnostics
        ))

    def test_repair_that_breaks_adjacent_region_is_rejected(self):
        finder, candidates = self._case()

        def validate(plan):
            vertical = finder.detour_level(plan, "VDET_001")
            horizontal = finder.detour_level(plan, "HDET_001")
            if vertical == 2:
                raise RegionConnectivityError(self._diagnosis(
                    plan, ("VDET_001",), region_index=4
                ))
            if horizontal == 3:
                raise RegionConnectivityError(self._diagnosis(
                    plan, ("VDET_001", "HDET_001", "VDET_002", "HDET_002")
                ))
            return SimpleNamespace(solid_count=4, seam_plan=plan)

        accepted, _v, _r, _s, diagnostics, _e = (
            _progressive_four_part_split(
                finder,
                candidates,
                (0.0, 300.0, 0.0, 300.0),
                validate,
            )
        )
        self.assertIsNotNone(accepted)
        self.assertTrue(any(
            "Region_4 became disconnected" in item for item in diagnostics
        ))


if __name__ == "__main__":
    unittest.main()

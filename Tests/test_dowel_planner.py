# -*- coding: utf-8 -*-
"""Focused FreeCAD regressions for V4.40 dowel planning and drilling."""

from __future__ import annotations

import math
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

try:
    import FreeCAD
    import Part
    from FreeCAD import Vector
except ImportError:  # pragma: no cover
    FreeCAD = Part = Vector = None

from Core.DowelPlanner import DowelParameters, DowelPlanner, _candidate_distances
from Core.Exceptions import DowelPlanningError
from Core.MacroSplitCore import MacroSplitCore
from Core.MeshPatchRebuilder import build_macro_mesh_parts
from Core.Settings import Settings
from Core.SinuousSeamPath import SinuousSeamPathFinder
from Core.SinuousSeamPath import Point2D, SeamPath2D, SinuousSeamPlan


@unittest.skipIf(Part is None, "FreeCAD Part module is unavailable")
class DowelPlannerTests(unittest.TestCase):
    """Verify compact placement, exact mating-pair cuts, and mesh integrity."""

    @staticmethod
    def _macro(source, vertical_offset=0.0, horizontal_offset=0.0):
        finder = SinuousSeamPathFinder()
        proposed = finder.generate(source, vertical_offset, horizontal_offset)
        box = source.BoundBox
        bounds = (float(box.XMin), float(box.XMax), float(box.YMin), float(box.YMax))
        for candidate in finder.candidate_plans(proposed, bounds):
            result = MacroSplitCore().cut(
                source, vertical_offset, horizontal_offset, seam_plan=candidate
            )
            if result.solid_count == 4:
                return result
        raise AssertionError("fixture did not yield four macro parts")

    def test_settings_are_exact_v440_defaults(self):
        settings = Settings.Joinery
        self.assertEqual(settings.DOWEL_DIAMETER_MM, 4.0)
        self.assertEqual(settings.DOWEL_HOLE_DIAMETER_MM, 4.3)
        self.assertEqual(settings.DOWEL_LENGTH_MM, 30.0)
        self.assertEqual(settings.DOWEL_AXIS_HEIGHT_MM, 2.5)
        self.assertEqual(settings.DOWEL_EDGE_MARGIN_MM, 15.0)
        self.assertEqual(settings.DOWEL_MIN_MATERIAL_MARGIN_MM, 2.0)
        self.assertEqual(settings.DOWEL_CENTER_EXCLUSION_MM, 20.0)
        self.assertEqual(settings.DOWEL_MIN_SPACING_MM, 60.0)
        self.assertEqual(settings.DOWEL_MAX_UNSUPPORTED_SPAN_MM, 110.0)
        self.assertEqual(settings.DOWELS_TARGET_PER_BRANCH, 3)
        self.assertEqual(settings.DOWELS_MIN_PER_BRANCH, 2)
        self.assertEqual(settings.DOWELS_MAX_PER_BRANCH, 4)

    def test_unsupported_third_dowel_uses_well_spaced_pair(self):
        source = Part.makeBox(300.0, 300.0, 8.0)
        macro = self._macro(source)
        first = DowelPlanner().plan(macro)
        second = DowelPlanner().plan(macro)
        self.assertEqual(first, second)
        self.assertEqual(len(first.dowels), 8)
        self.assertEqual(
            tuple(len(branch.accepted_dowel_ids) for branch in first.branches),
            (2, 2, 2, 2),
        )
        self.assertTrue(all(branch.used_two_dowel_fallback for branch in first.branches))
        self.assertTrue(all(min(branch.spacing_mm) >= 60.0 for branch in first.branches))
        with self.assertRaises(FrozenInstanceError):
            first.dowels[0].status = "changed"

    def test_long_branches_use_balanced_coverage_without_clustering(self):
        plan = DowelPlanner().plan(self._macro(Part.makeBox(594.0, 594.0, 8.0)))
        self.assertEqual(len(plan.dowels), 12)
        for branch in plan.branches:
            self.assertEqual(branch.target_fractions, (0.25, 0.50, 0.75))
            self.assertFalse(branch.used_two_dowel_fallback)
            self.assertEqual(len(branch.accepted_dowel_ids), 3)
            self.assertTrue(all(value >= 60.0 for value in branch.spacing_mm))
            self.assertGreater(branch.safe_candidate_count, 3)
            self.assertEqual(branch.sampled_point_count, branch.safe_candidate_count)
            self.assertEqual(branch.cheap_candidate_count, branch.sampled_point_count)
            self.assertLessEqual(branch.exact_validation_count, 3)
            self.assertLessEqual(branch.largest_unsupported_span_mm, 110.0)
            self.assertTrue(branch.coverage_target_achieved)
            self.assertFalse(branch.spacing_exception)

    def test_four_dowels_are_used_only_when_three_cannot_cover_branch(self):
        long_plan = DowelPlanner().plan(
            self._macro(Part.makeBox(1000.0, 1000.0, 8.0))
        )
        self.assertTrue(
            all(len(branch.accepted_dowel_ids) == 4 for branch in long_plan.branches)
        )
        self.assertTrue(
            all(branch.largest_unsupported_span_mm <= 110.0 for branch in long_plan.branches)
        )
        ordinary = DowelPlanner().plan(
            self._macro(Part.makeBox(594.0, 594.0, 8.0))
        )
        self.assertTrue(
            all(len(branch.accepted_dowel_ids) == 3 for branch in ordinary.branches)
        )

    def test_safe_pool_is_independent_of_selected_spacing(self):
        plan = DowelPlanner().plan(self._macro(Part.makeBox(300.0, 300.0, 8.0)))
        for branch in plan.branches:
            self.assertGreater(
                branch.safe_candidate_count, len(branch.accepted_dowel_ids)
            )
            self.assertEqual(len(branch.accepted_dowel_ids), 2)
            self.assertGreaterEqual(branch.spacing_mm[0], 60.0)

    def test_v440_real_branch_evidence_window_is_scanned(self):
        planner = DowelPlanner()
        macro = self._macro(Part.makeBox(594.0, 594.0, 8.0))
        solids, bounds = planner._ordered_solids_and_bounds(macro)
        branch = planner._branches(macro)[0]
        interval = planner._usable_interval(branch, bounds, (297.0, 297.0))
        original = planner._cheap_candidate_reason

        def evidence_window(result, parts, panel_bounds, current, center, tangent, occupied):
            if 30.0 <= center[1] <= 56.0:
                return original(
                    result, parts, panel_bounds, current, center, tangent, occupied
                )
            return "fixture exclusion outside V4.40 evidence window"

        with patch.object(
            planner, "_cheap_candidate_reason", side_effect=evidence_window
        ):
            candidates, _rejections, sampled, spacing = (
                planner._safe_candidate_pool(
                    interval, branch, macro, solids, bounds, 2.5, ()
                )
            )
        self.assertGreaterEqual(len(candidates), 2)
        self.assertGreater(sampled, len(candidates))
        self.assertIn(spacing, (5.0, 2.5))
        selected, _targets = planner._select_safe_subset(candidates, interval)
        self.assertEqual(len(selected), 2)

    def test_exact_brep_validation_runs_only_on_selected_shortlist(self):
        planner = DowelPlanner()
        macro = self._macro(Part.makeBox(594.0, 594.0, 8.0))
        original = planner._exact_candidate_reason
        calls = []

        def counted(*args, **kwargs):
            calls.append(args[3])
            return original(*args, **kwargs)

        with patch.object(planner, "_exact_candidate_reason", side_effect=counted):
            plan = planner.plan(macro)
        self.assertEqual(len(calls), 12)
        self.assertEqual(
            len(calls), sum(branch.exact_validation_count for branch in plan.branches)
        )
        self.assertLess(len(calls), sum(branch.sampled_point_count for branch in plan.branches))

    def test_cheap_prefilter_has_no_false_negative_against_exact_logic(self):
        planner = DowelPlanner()
        macro = self._macro(Part.makeBox(100.0, 100.0, 8.0))
        solids, bounds = planner._ordered_solids_and_bounds(macro)
        branch = planner._branches(macro)[0]
        interval = planner._usable_interval(branch, bounds, (50.0, 50.0))
        for distance in (interval[0], sum(interval) / 2.0, interval[1]):
            from Core.DowelPlanner import _point_and_tangent
            point, tangent = _point_and_tangent(branch.points, distance)
            center = (point[0], point[1], 2.5)
            exact = planner._candidate_reason(
                macro, solids, bounds, branch, center, tangent, ()
            )
            cheap = planner._cheap_candidate_reason(
                macro, solids, bounds, branch, center, tangent, ()
            )
            if exact is None:
                self.assertIsNone(cheap)

    def test_fixture_dowel_coordinates_are_unchanged(self):
        plan = DowelPlanner().plan(self._macro(Part.makeBox(594.0, 594.0, 8.0)))
        self.assertEqual(
            tuple((round(item.center_xyz_mm[0], 6), round(item.center_xyz_mm[1], 6)) for item in plan.dowels),
            (
                (297.0, 80.0), (297.0, 145.0), (297.0, 210.0),
                (297.0, 382.0), (297.0, 447.0), (297.0, 512.0),
                (80.0, 297.0), (145.0, 297.0), (210.0, 297.0),
                (382.0, 297.0), (447.0, 297.0), (512.0, 297.0),
            ),
        )

    def test_relocation_order_is_symmetric_around_target(self):
        self.assertEqual(
            _candidate_distances(50.0, 0.0, 100.0, search_limit=15.0)[:7],
            (50.0, 55.0, 45.0, 60.0, 40.0, 65.0, 35.0),
        )

    def test_constrained_branches_accept_minimum_two(self):
        plan = DowelPlanner().plan(self._macro(Part.makeBox(100.0, 100.0, 8.0)))
        self.assertEqual(len(plan.dowels), 8)
        self.assertTrue(all(len(branch.accepted_dowel_ids) == 2 for branch in plan.branches))
        self.assertTrue(all(branch.safe_candidate_count >= 2 for branch in plan.branches))
        self.assertTrue(
            all(not branch.minimum_spacing_achievable for branch in plan.branches)
        )

    def test_axes_are_horizontal_and_normal_to_local_tangent(self):
        plan = DowelPlanner().plan(self._macro(Part.makeBox(300.0, 300.0, 8.0)))
        for dowel in plan.dowels:
            dot = sum(a * b for a, b in zip(dowel.tangent_xy, dowel.axis_xy))
            self.assertAlmostEqual(dot, 0.0, places=12)
            self.assertAlmostEqual(math.hypot(*dowel.axis_xy), 1.0, places=12)
            self.assertAlmostEqual(dowel.center_xyz_mm[2], 2.5, places=12)
        vertical = tuple(item for item in plan.dowels if item.seam_branch.startswith("vertical"))
        horizontal = tuple(item for item in plan.dowels if item.seam_branch.startswith("horizontal"))
        self.assertTrue(all(abs(item.axis_xy[0]) == 1.0 for item in vertical))
        self.assertTrue(all(abs(item.axis_xy[1]) == 1.0 for item in horizontal))

    def test_sinuous_segment_uses_its_local_xy_normal(self):
        vertical = SeamPath2D(
            "vertical", 150.0,
            (Point2D(150.0, 0.0), Point2D(150.0, 300.0)),
            (), (), 300.0, 0.0,
        )
        points = (
            Point2D(0.0, 150.0), Point2D(100.0, 150.0),
            Point2D(140.0, 170.0), Point2D(180.0, 150.0),
            Point2D(300.0, 150.0),
        )
        length = sum(
            math.hypot(second.x_mm - first.x_mm, second.y_mm - first.y_mm)
            for first, second in zip(points, points[1:])
        )
        horizontal = SeamPath2D(
            "horizontal", 150.0, points, (), (), length, 20.0,
        )
        seam = SinuousSeamPlan(vertical, horizontal, (), 1)
        macro = MacroSplitCore().cut(Part.makeBox(300.0, 300.0, 8.0), seam_plan=seam)
        plan = DowelPlanner().plan(macro)
        curved = tuple(
            item for item in plan.dowels
            if abs(item.tangent_xy[1]) > 0.1
        )
        self.assertTrue(curved)
        for item in curved:
            self.assertAlmostEqual(
                item.tangent_xy[0] * item.axis_xy[0]
                + item.tangent_xy[1] * item.axis_xy[1],
                0.0,
                places=12,
            )

    def test_center_and_outer_edge_exclusions_are_respected(self):
        macro = self._macro(Part.makeBox(300.0, 300.0, 8.0))
        plan = DowelPlanner().plan(macro)
        for item in plan.dowels:
            x_value, y_value, _ = item.center_xyz_mm
            self.assertGreaterEqual(math.hypot(x_value - 150.0, y_value - 150.0), 20.0)
            self.assertGreaterEqual(min(x_value, 300.0 - x_value, y_value, 300.0 - y_value), 15.0)

    def test_nearby_artistic_hole_causes_relocation_or_rejection(self):
        source = Part.makeBox(300.0, 300.0, 8.0).cut(
            Part.makeCylinder(10.0, 8.0, Vector(150.0, 37.5, 0.0))
        )
        macro = self._macro(source)
        plan = DowelPlanner().plan(macro)
        reasons = tuple(
            rejection.reason
            for branch in plan.branches
            for rejection in branch.rejected_candidates
        )
        self.assertTrue(any(reason.startswith("opening margin") for reason in reasons))
        self.assertGreaterEqual(
            len(plan.branches[0].accepted_dowel_ids),
            Settings.Joinery.DOWELS_MIN_PER_BRANCH,
        )

    def test_apply_drills_only_matching_part_pairs_and_preserves_source(self):
        source = Part.makeBox(300.0, 300.0, 8.0)
        source_before = source.exportBrepToString()
        macro = self._macro(source)
        application = DowelPlanner().apply(macro)
        self.assertEqual(source.exportBrepToString(), source_before)
        self.assertEqual(application.macro_result.solid_count, 4)
        self.assertEqual(len(application.cutters), len(application.plan.dowels))
        expected_cutter_volume = math.pi * (4.3 / 2.0) ** 2 * 30.0
        for cutter in application.cutters:
            self.assertAlmostEqual(float(cutter.Volume), expected_cutter_volume, places=6)
        solids = {}
        for solid in macro.shape.Solids:
            center = solid.CenterOfMass
            key = (float(center.x) >= macro.cut_x_mm, float(center.y) >= macro.cut_y_mm)
            solids[key] = solid
        ordered = tuple(solids[key] for key in (
            (False, False), (True, False), (False, True), (True, True)
        ))
        for dowel, cutter in zip(application.plan.dowels, application.cutters):
            intended = {int(name[-1]) - 1 for name in dowel.intended_part_names}
            removed = tuple(
                float(solid.Volume) - float(solid.cut(cutter).Volume)
                for solid in ordered
            )
            self.assertTrue(all(removed[index] > 0.0 for index in intended))
            self.assertTrue(all(
                abs(value) < 1.0e-6
                for index, value in enumerate(removed)
                if index not in intended
            ))
        self.assertGreater(application.removed_volume_mm3, 0.0)

    def test_apply_reuses_exactly_validated_cutters(self):
        planner = DowelPlanner()
        macro = self._macro(Part.makeBox(100.0, 100.0, 8.0))
        original = planner._cutter
        calls = []

        def counted(*args, **kwargs):
            calls.append(args)
            return original(*args, **kwargs)

        with patch.object(planner, "_cutter", side_effect=counted):
            plan = planner.plan(macro)
            after_plan = len(calls)
            application = planner.apply(macro, plan)
        self.assertEqual(len(application.cutters), len(plan.dowels))
        self.assertEqual(len(calls), after_plan)

    def test_drilled_parts_remain_watertight_and_dowel_cavities_are_not_capped(self):
        source = Part.makeBox(200.0, 200.0, 8.0)
        application = DowelPlanner().apply(self._macro(source))
        mesh_parts = build_macro_mesh_parts(application.macro_result)
        self.assertEqual(len(mesh_parts), 4)
        self.assertTrue(all(part.after.open_edge_count == 0 for part in mesh_parts))
        self.assertTrue(all(part.after.non_manifold_edge_count == 0 for part in mesh_parts))
        self.assertTrue(all(part.after.connected_component_count == 1 for part in mesh_parts))
        self.assertTrue(all(part.after.is_solid for part in mesh_parts))
        self.assertTrue(all(part.is_printable for part in mesh_parts))

    def test_offsets_recompute_plan_and_preserve_determinism(self):
        source = Part.makeBox(300.0, 300.0, 8.0)
        centered = DowelPlanner().plan(self._macro(source))
        offset_macro = self._macro(source, -2.0, 10.0)
        first = DowelPlanner().plan(offset_macro)
        second = DowelPlanner().plan(offset_macro)
        self.assertEqual(first, second)
        self.assertNotEqual(
            tuple(item.center_xyz_mm for item in centered.dowels),
            tuple(item.center_xyz_mm for item in first.dowels),
        )

    def test_invalid_diameter_or_branch_count_is_rejected(self):
        with self.assertRaises(DowelPlanningError):
            DowelPlanner(DowelParameters(dowel_diameter_mm=5.0, hole_diameter_mm=4.3))
        with self.assertRaises(DowelPlanningError):
            DowelPlanner(DowelParameters(minimum_per_branch=1))


if __name__ == "__main__":
    unittest.main()

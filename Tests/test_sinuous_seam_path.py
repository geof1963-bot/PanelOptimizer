# -*- coding: utf-8 -*-
"""Focused FreeCAD regressions for the practical V4.30 seam paths."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

try:
    import Part
    from FreeCAD import Vector
except ImportError:  # pragma: no cover
    Part = Vector = None

from Core.MacroSplitCore import MacroSplitCore
from Core.MeshPatchRebuilder import build_macro_mesh_parts
from Core.Settings import Settings
from Core.SinuousSeamPath import (
    Point2D,
    SinuousSeamParameters,
    SinuousSeamPathFinder,
    _clean_open_path,
    _material_side_cutter_envelope_mm,
    _point_closed_polyline_distance,
    _self_intersects,
)


@unittest.skipIf(Part is None, "FreeCAD Part module is unavailable")
class SinuousSeamPathTests(unittest.TestCase):
    """Verify deterministic local detours without AnalyzerEngine."""

    @staticmethod
    def _perforated(*holes):
        shape = Part.makeBox(100.0, 100.0, 8.0)
        for x_value, y_value, radius in holes:
            shape = shape.cut(
                Part.makeCylinder(radius, 8.0, Vector(x_value, y_value, 0.0))
            )
        return shape

    def test_no_nearby_hole_produces_straight_paths(self):
        plan = SinuousSeamPathFinder().generate(Part.makeBox(100, 100, 8))
        self.assertEqual(plan.vertical.points, (Point2D(50, 0), Point2D(50, 100)))
        self.assertEqual(plan.horizontal.points, (Point2D(0, 50), Point2D(100, 50)))
        self.assertEqual(plan.vertical.followed_feature_ids, ())
        self.assertEqual(plan.horizontal.followed_feature_ids, ())
        self.assertEqual(plan.intersection_count, 1)

    def test_v471_settings_are_bounded_mission_values(self):
        self.assertEqual(Settings.Split.SEAM_SEARCH_CORRIDOR_MM, 75.0)
        self.assertEqual(Settings.Split.MAX_FOLLOWED_FEATURES_PER_SEAM, 8)
        self.assertEqual(Settings.Split.MAX_SEAM_VARIANTS_PER_AXIS, 12)
        self.assertEqual(Settings.Split.SEAM_MIN_FOLLOW_LENGTH_MM, 15.0)
        self.assertEqual(Settings.Split.SEAM_BEAM_WIDTH, 6)
        self.assertEqual(Settings.Split.SEAM_COVERAGE_EPSILON_MM, 1.0)
        self.assertEqual(Settings.Split.MAX_EXACT_TOPOLOGY_VALIDATIONS, 8)
        self.assertEqual(Settings.Split.SEAM_PLANNING_TIME_BUDGET_S, 30.0)

    def test_collinear_and_tiny_segments_are_removed(self):
        points = (
            Point2D(0.0, 0.0),
            Point2D(0.0, 0.01),
            Point2D(0.0, 5.0),
            Point2D(0.0, 10.0),
        )
        self.assertEqual(
            _clean_open_path(points, 0.5, 30.0),
            (Point2D(0.0, 0.0), Point2D(0.0, 10.0)),
        )

    def test_contour_entry_and_exit_are_smoothed_deterministically(self):
        plan = SinuousSeamPathFinder().generate(
            self._perforated((52.0, 20.0, 8.0))
        )
        path = plan.vertical
        self.assertEqual(path.smoothing_transition_count, 2)
        self.assertGreater(path.maximum_artificial_turn_before_deg, 30.0)
        self.assertLessEqual(path.maximum_artificial_turn_after_deg, 30.0)
        self.assertLess(
            path.maximum_artificial_turn_after_deg,
            path.maximum_artificial_turn_before_deg,
        )
        self.assertGreater(path.segment_count_after_cleanup, 1)

    def test_near_hole_is_followed_and_outside_corridor_is_ignored(self):
        near = SinuousSeamPathFinder().generate(
            self._perforated((52.0, 20.0, 8.0))
        )
        self.assertEqual(len(near.vertical.followed_feature_ids), 1)
        self.assertGreater(near.vertical.maximum_deviation_mm, 0.0)
        self.assertGreater(near.vertical.path_length_mm, 100.0)
        far = SinuousSeamPathFinder().generate(
            self._perforated((10.0, 20.0, 5.0))
        )
        self.assertEqual(far.vertical.followed_feature_ids, ())

    def test_circular_hole_chain_is_offset_by_visible_envelope_and_clearance(self):
        plan = SinuousSeamPathFinder().generate(
            self._perforated((52.0, 20.0, 8.0))
        )
        report = plan.vertical.hole_offset_reports[0]
        self.assertEqual(report.feature_id, plan.vertical.followed_feature_ids[0])
        self.assertAlmostEqual(report.cutter_envelope_mm, 1.1, places=9)
        self.assertAlmostEqual(report.clearance_mm, 0.10, places=9)
        self.assertAlmostEqual(report.final_offset_mm, 1.20, places=9)
        self.assertGreaterEqual(report.minimum_material_side_clearance_mm, 0.10 - 1e-6)
        self.assertIn("cutter normal", report.interior_side)

    def test_irregular_opening_uses_local_interior_normals(self):
        vertices = tuple(
            Vector(*point, 0.0)
            for point in (
                (45.0, 10.0), (58.0, 12.0), (61.0, 21.0),
                (55.0, 29.0), (44.0, 26.0), (42.0, 17.0), (45.0, 10.0),
            )
        )
        opening = Part.Face(Part.makePolygon(vertices)).extrude(Vector(0, 0, 8))
        source = Part.makeBox(100.0, 100.0, 8.0).cut(opening)
        plan = SinuousSeamPathFinder().generate(source)
        self.assertEqual(len(plan.vertical.hole_offset_reports), 1)
        report = plan.vertical.hole_offset_reports[0]
        self.assertGreaterEqual(report.minimum_material_side_clearance_mm, 0.10 - 1e-6)
        feature = next(
            item for item in plan.features if item.feature_id == report.feature_id
        )
        followed_points = tuple(
            point for point in plan.vertical.points
            if _point_closed_polyline_distance(point, feature.points) >= 1.1
        )
        self.assertTrue(followed_points)

    def test_asymmetric_profile_selects_actual_material_side_envelope(self):
        profile = SimpleNamespace(top_width_mm=2.2, bottom_width_mm=2.0)
        canonical = (1.0, 0.0)
        self.assertAlmostEqual(
            _material_side_cutter_envelope_mm((1.0, 0.0), canonical, profile),
            1.1,
        )
        self.assertAlmostEqual(
            _material_side_cutter_envelope_mm((-1.0, 0.0), canonical, profile),
            3.0,
        )

    def test_multiple_holes_are_bounded_and_deterministic(self):
        source = self._perforated(
            (52.0, 18.0, 7.0),
            (48.0, 82.0, 6.0),
            (18.0, 52.0, 7.0),
        )
        finder = SinuousSeamPathFinder()
        first = finder.generate(source, 2.0, -3.0)
        second = finder.generate(source, 2.0, -3.0)
        self.assertEqual(first, second)
        self.assertLessEqual(len(first.vertical.followed_feature_ids), 3)
        self.assertLessEqual(len(first.horizontal.followed_feature_ids), 3)
        self.assertEqual(first.vertical.points[0].y_mm, 0.0)
        self.assertEqual(first.vertical.points[-1].y_mm, 100.0)
        self.assertEqual(first.horizontal.points[0].x_mm, 0.0)
        self.assertEqual(first.horizontal.points[-1].x_mm, 100.0)
        self.assertEqual(first.intersection_count, 1)

    def test_vertical_route_follows_two_holes_without_backtracking(self):
        source = Part.makeBox(300.0, 300.0, 8.0)
        for y_value in (50.0, 250.0):
            source = source.cut(
                Part.makeCylinder(8.0, 8.0, Vector(152.0, y_value, 0.0))
            )
        plan = SinuousSeamPathFinder().generate(source)
        self.assertEqual(len(plan.vertical.followed_feature_ids), 2)
        self.assertEqual(len(plan.vertical.hole_offset_reports), 2)
        self.assertTrue(all(
            first.y_mm < second.y_mm
            for first, second in zip(plan.vertical.points, plan.vertical.points[1:])
        ))
        self.assertFalse(_self_intersects(plan.vertical.points))
        self.assertEqual(plan.intersection_count, 1)

    def test_three_hole_route_improves_contour_following_ratio_and_splits_four(self):
        def panel(y_values):
            shape = Part.makeBox(300.0, 300.0, 8.0)
            for y_value in y_values:
                shape = shape.cut(
                    Part.makeCylinder(8.0, 8.0, Vector(152.0, y_value, 0.0))
                )
            return shape

        single = SinuousSeamPathFinder().generate(panel((45.0,)))
        source = panel((45.0, 95.0, 245.0))
        finder = SinuousSeamPathFinder()
        multiple = finder.generate(source)
        self.assertEqual(len(multiple.vertical.followed_feature_ids), 3)
        self.assertGreater(
            multiple.vertical.contour_following_length_mm,
            single.vertical.contour_following_length_mm,
        )
        self.assertGreater(
            multiple.vertical.contour_following_ratio,
            single.vertical.contour_following_ratio,
        )
        self.assertLessEqual(
            multiple.vertical.maximum_artificial_turn_after_deg,
            30.0,
        )
        valid = tuple(
            MacroSplitCore().cut(source, seam_plan=candidate)
            for candidate in finder.candidate_plans(
                multiple, (0.0, 300.0, 0.0, 300.0)
            )
            if MacroSplitCore().cut(source, seam_plan=candidate).solid_count == 4
        )
        self.assertTrue(valid)
        self.assertEqual(valid[0].seam_plan.vertical.followed_feature_ids,
                         multiple.vertical.followed_feature_ids)

    def test_v471_follows_four_holes_and_connects_without_center_return(self):
        source = Part.makeBox(400.0, 400.0, 8.0)
        for y_value in (45.0, 115.0, 285.0, 355.0):
            source = source.cut(
                Part.makeCylinder(10.0, 8.0, Vector(202.0, y_value, 0.0))
            )
        before = source.exportBrepToString()
        finder = SinuousSeamPathFinder()
        plan = finder.generate(source)
        path = plan.vertical
        self.assertEqual(len(path.followed_feature_ids), 4)
        self.assertGreater(path.contour_following_length_mm, 100.0)
        self.assertGreater(path.contour_following_ratio, 0.20)
        first, second = path.followed_feature_bounds_mm[:2]
        bridge_points = tuple(
            point for point in path.points
            if first[3] < point.y_mm < second[1]
        )
        self.assertTrue(bridge_points)
        self.assertTrue(all(
            abs(point.x_mm - path.nominal_coordinate_mm) > 0.10
            for point in bridge_points
        ))
        self.assertFalse(_self_intersects(path.points))
        self.assertTrue(all(
            first_point.y_mm < second_point.y_mm
            for first_point, second_point in zip(path.points, path.points[1:])
        ))
        candidates = finder.candidate_plans(plan, (0.0, 400.0, 0.0, 400.0))
        result = next(
            result for candidate in candidates
            for result in (MacroSplitCore().cut(source, seam_plan=candidate),)
            if result.solid_count == 4
        )
        self.assertEqual(result.seam_plan.vertical.followed_feature_ids,
                         path.followed_feature_ids)
        self.assertEqual(source.exportBrepToString(), before)

    def test_combination_variants_recover_both_full_sinuous_axes(self):
        source = Part.makeBox(300.0, 300.0, 8.0)
        for x_value, y_value in (
            (152.0, 50.0), (152.0, 250.0),
            (50.0, 148.0), (250.0, 148.0),
        ):
            source = source.cut(
                Part.makeCylinder(8.0, 8.0, Vector(x_value, y_value, 0.0))
            )
        finder = SinuousSeamPathFinder()
        proposed = finder.generate(source)
        candidates = finder.candidate_plans(
            proposed, (0.0, 300.0, 0.0, 300.0)
        )
        self.assertEqual(len(candidates[0].vertical.followed_feature_ids), 2)
        self.assertEqual(len(candidates[0].horizontal.followed_feature_ids), 2)
        self.assertEqual(candidates[0].intersection_count, 1)
        shortlist = finder.topology_shortlist(
            proposed, (0.0, 300.0, 0.0, 300.0)
        )
        self.assertLessEqual(len(shortlist), 5)
        self.assertEqual(shortlist[0], candidates[0])
        diagnostics = finder.search_diagnostics
        self.assertGreater(diagnostics["route_candidates_pruned"], 0)
        self.assertGreater(diagnostics["detour_cache_hits"], 0)
        self.assertGreater(diagnostics["transition_cache_hits"], 0)
        self.assertTrue(all(
            candidate.vertical.followed_feature_ids
            and candidate.horizontal.followed_feature_ids
            for candidate in shortlist
        ))
        result = MacroSplitCore().cut(source, seam_plan=shortlist[0])
        self.assertEqual(result.solid_count, 4)
        self.assertLess(shortlist[0].vertical.longest_straight_segment_mm, 100.0)
        self.assertLess(shortlist[0].horizontal.longest_straight_segment_mm, 100.0)

    def test_local_detour_levels_reduce_only_the_requested_unit(self):
        source = Part.makeBox(300.0, 300.0, 8.0)
        for x_value, y_value in (
            (152.0, 50.0), (152.0, 250.0),
            (50.0, 148.0), (250.0, 148.0),
        ):
            source = source.cut(
                Part.makeCylinder(8.0, 8.0, Vector(x_value, y_value, 0.0))
            )
        finder = SinuousSeamPathFinder()
        plan = finder.topology_shortlist(
            finder.generate(source), (0.0, 300.0, 0.0, 300.0)
        )[0]
        self.assertEqual(plan.vertical.detour_ids, ("VDET_001", "VDET_002"))
        self.assertEqual(plan.vertical.detour_levels, (3, 3))
        self.assertEqual(plan.horizontal.detour_ids, ("HDET_001", "HDET_002"))
        reduced = finder.simplify_detour(
            plan, "VDET_001", (0.0, 300.0, 0.0, 300.0)
        )
        self.assertIsNotNone(reduced)
        self.assertEqual(reduced.vertical.detour_levels, (2, 3))
        self.assertEqual(reduced.horizontal, plan.horizontal)
        self.assertLess(
            reduced.vertical.contour_following_length_mm,
            plan.vertical.contour_following_length_mm,
        )
        self.assertEqual(reduced.intersection_count, 1)
        self.assertTrue(all(
            report.original_profile_preserved
            for report in reduced.vertical.hole_offset_reports
        ))

    def test_progressive_level_zero_bypass_keeps_other_detours_sinuous(self):
        source = Part.makeBox(400.0, 400.0, 8.0)
        for y_value in (45.0, 115.0, 285.0, 355.0):
            source = source.cut(
                Part.makeCylinder(10.0, 8.0, Vector(202.0, y_value, 0.0))
            )
        for x_value in (55.0, 345.0):
            source = source.cut(
                Part.makeCylinder(10.0, 8.0, Vector(x_value, 198.0, 0.0))
            )
        finder = SinuousSeamPathFinder()
        plan = finder.topology_shortlist(
            finder.generate(source), (0.0, 400.0, 0.0, 400.0)
        )[0]
        original_other_levels = plan.vertical.detour_levels[1:]
        for expected in (2, 1, 0):
            plan = finder.simplify_detour(
                plan, "VDET_001", (0.0, 400.0, 0.0, 400.0)
            )
            self.assertIsNotNone(plan)
            self.assertEqual(plan.vertical.detour_levels[0], expected)
        self.assertEqual(plan.vertical.detour_levels[1:], original_other_levels)
        self.assertEqual(plan.intersection_count, 1)
        self.assertGreater(len(plan.vertical.followed_feature_ids), 1)
        self.assertLess(plan.vertical.longest_straight_segment_mm, 100.0)
        self.assertFalse(_self_intersects(plan.vertical.points))

    def test_unexpected_solid_is_mapped_to_nearest_detour(self):
        source = Part.makeBox(300.0, 300.0, 8.0)
        for y_value in (50.0, 250.0):
            source = source.cut(
                Part.makeCylinder(8.0, 8.0, Vector(152.0, y_value, 0.0))
            )
        finder = SinuousSeamPathFinder()
        plan = finder.generate(source)
        first_bounds = plan.vertical.followed_feature_bounds_mm[0]
        center = SimpleNamespace(
            x=0.5 * (first_bounds[0] + first_bounds[2]),
            y=0.5 * (first_bounds[1] + first_bounds[3]),
        )
        solids = [
            SimpleNamespace(Volume=1.0, CenterOfMass=center),
            *(
                SimpleNamespace(
                    Volume=1000.0 + index,
                    CenterOfMass=SimpleNamespace(x=150.0, y=150.0),
                )
                for index in range(4)
            ),
        ]
        result = SimpleNamespace(shape=SimpleNamespace(Solids=solids))
        self.assertEqual(
            finder.likely_problem_detours(plan, result)[0], "VDET_001"
        )

    def test_longer_monotone_contour_direction_is_preferred(self):
        points = tuple(Point2D(*point) for point in (
            (0.0, 0.0), (0.0, 10.0), (0.0, 20.0), (10.0, 20.0),
            (6.0, 15.0), (10.0, 10.0), (6.0, 5.0),
        ))
        chain = SinuousSeamPathFinder()._nearest_monotone_chain(
            points, "vertical", 5.0, -20.0, 20.0
        )
        self.assertTrue(any(point.x_mm == 10.0 for point in chain))
        self.assertGreater(
            sum(
                ((second.x_mm-first.x_mm) ** 2
                 + (second.y_mm-first.y_mm) ** 2) ** 0.5
                for first, second in zip(chain, chain[1:])
            ),
            25.0,
        )

    def test_boundary_sampling_refines_curves_and_compacts_straights(self):
        class AdaptiveWire:
            def __init__(self):
                self.deflections = []

            def discretize(self, Deflection=None, Number=None):
                self.deflections.append(Deflection)
                values = (
                    ((0, 0), (5, 0), (10, 0), (10, 10), (0, 10), (0, 0))
                    if Deflection == 2.0
                    else (
                        (0, 0), (2.5, 0), (5, 0), (7.5, 0), (10, 0),
                        (10, 2), (9, 5), (7, 8), (4, 10), (0, 10), (0, 0),
                    )
                )
                return tuple(SimpleNamespace(x=x, y=y) for x, y in values)

        wire = AdaptiveWire()
        points = SinuousSeamPathFinder()._sample_wire(wire)
        self.assertEqual(wire.deflections, [2.0, 1.0])
        self.assertIn(Point2D(9.0, 5.0), points)
        self.assertNotIn(Point2D(5.0, 0.0), points)

    def test_followed_hole_reports_preserved_original_profile(self):
        source = self._perforated((52.0, 20.0, 8.0))
        finder = SinuousSeamPathFinder()
        plan = finder.generate(source)
        report = plan.vertical.hole_offset_reports[0]
        self.assertTrue(report.original_profile_preserved)
        self.assertGreaterEqual(
            report.minimum_material_side_clearance_mm,
            report.clearance_mm - 1.0e-6,
        )
        result = MacroSplitCore().cut(source, seam_plan=plan)
        material_probe = Part.makeCylinder(
            0.03, 8.0, Vector(43.95, 20.0, 0.0)
        )
        expected = source.common(material_probe).Volume
        self.assertGreater(expected, 0.0)
        self.assertAlmostEqual(
            result.shape.common(material_probe).Volume, expected, places=7
        )

    def test_overlapping_feature_intervals_are_not_forced_into_invalid_chain(self):
        source = Part.makeBox(300.0, 300.0, 8.0)
        for y_value in (50.0, 60.0, 70.0):
            source = source.cut(
                Part.makeCylinder(7.0, 8.0, Vector(152.0, y_value, 0.0))
            )
        plan = SinuousSeamPathFinder().generate(source)
        self.assertLess(len(plan.vertical.followed_feature_ids), 3)
        self.assertFalse(_self_intersects(plan.vertical.points))

    def test_paths_are_immutable_and_continuous_monotone(self):
        plan = SinuousSeamPathFinder().generate(
            self._perforated((52.0, 20.0, 8.0))
        )
        with self.assertRaises(FrozenInstanceError):
            plan.vertical.maximum_deviation_mm = 2.0
        self.assertTrue(all(
            first.y_mm < second.y_mm
            for first, second in zip(plan.vertical.points, plan.vertical.points[1:])
        ))
        self.assertTrue(all(
            first.x_mm < second.x_mm
            for first, second in zip(plan.horizontal.points, plan.horizontal.points[1:])
        ))

    def test_segmented_cut_preserves_hole_and_v426_mesh_pipeline(self):
        source = self._perforated((52.0, 20.0, 8.0))
        before = source.exportBrepToString()
        finder = SinuousSeamPathFinder(
            SinuousSeamParameters(maximum_features_per_seam=1)
        )
        plan = finder.generate(source)
        result = MacroSplitCore().cut(source, seam_plan=plan)
        self.assertEqual(result.solid_count, 4)
        self.assertEqual(result.seam_plan, plan)
        self.assertEqual(source.exportBrepToString(), before)
        hole = Part.makeCylinder(7.5, 8.0, Vector(52.0, 20.0, 0.0))
        self.assertAlmostEqual(float(result.shape.common(hole).Volume), 0.0, places=6)
        meshes = build_macro_mesh_parts(result)
        self.assertEqual(len(meshes), 4)
        self.assertTrue(all(part.after.open_edge_count == 0 for part in meshes))
        self.assertTrue(all(part.after.is_solid for part in meshes))
        self.assertTrue(all(part.is_printable for part in meshes))


if __name__ == "__main__":
    unittest.main()

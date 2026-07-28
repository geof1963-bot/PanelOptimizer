# -*- coding: utf-8 -*-
"""Focused FreeCAD regressions for the practical V4.30 seam paths."""

from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError

try:
    import Part
    from FreeCAD import Vector
except ImportError:  # pragma: no cover
    Part = Vector = None

from Core.MacroSplitCore import MacroSplitCore
from Core.MeshPatchRebuilder import build_macro_mesh_parts
from Core.SinuousSeamPath import (
    Point2D,
    SinuousSeamParameters,
    SinuousSeamPathFinder,
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
        self.assertLessEqual(len(first.vertical.followed_feature_ids), 2)
        self.assertLessEqual(len(first.horizontal.followed_feature_ids), 2)
        self.assertEqual(first.vertical.points[0].y_mm, 0.0)
        self.assertEqual(first.vertical.points[-1].y_mm, 100.0)
        self.assertEqual(first.horizontal.points[0].x_mm, 0.0)
        self.assertEqual(first.horizontal.points[-1].x_mm, 100.0)
        self.assertEqual(first.intersection_count, 1)

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

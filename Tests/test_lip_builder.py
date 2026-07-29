# -*- coding: utf-8 -*-
"""Focused FreeCAD regressions for V4.50 top-surface mastic lips."""

from __future__ import annotations

import math
import tempfile
import unittest

try:
    import Part
    from FreeCAD import Vector
except ImportError:  # pragma: no cover
    Part = Vector = None

from Core.DowelPlanner import DowelPlanner
from Core.LipBuilder import LipBuilder, LipParameters
from Core.MacroSplitCore import MacroSplitCore
from Core.MeshPatchRebuilder import build_macro_mesh_parts, export_mesh_parts
from Core.Settings import Settings
from Core.SinuousSeamPath import SinuousSeamPathFinder


@unittest.skipIf(Part is None, "FreeCAD Part module is unavailable")
class LipBuilderTests(unittest.TestCase):
    """Verify placement, local clipping, joinery, mesh, and export contracts."""

    @staticmethod
    def _macro(source, vertical_offset=0.0, horizontal_offset=0.0):
        finder = SinuousSeamPathFinder()
        proposed = finder.generate(source, vertical_offset, horizontal_offset)
        bounds = source.BoundBox
        panel_bounds = (
            float(bounds.XMin), float(bounds.XMax),
            float(bounds.YMin), float(bounds.YMax),
        )
        for candidate in finder.candidate_plans(proposed, panel_bounds):
            result = MacroSplitCore().cut(
                source,
                vertical_offset,
                horizontal_offset,
                seam_plan=candidate,
            )
            if result.solid_count == 4:
                return result
        raise AssertionError("fixture did not yield four macro parts")

    @classmethod
    def _application(cls, source, vertical_offset=0.0, horizontal_offset=0.0):
        drilled = DowelPlanner().apply(
            cls._macro(source, vertical_offset, horizontal_offset)
        )
        lips = LipBuilder().apply(
            drilled.macro_result,
            dowel_cutters=drilled.cutters,
        )
        return drilled, lips

    def test_settings_and_rectangular_profile_are_exact(self):
        self.assertEqual(Settings.Lips.LIP_HEIGHT_MM, 0.30)
        self.assertEqual(Settings.Lips.LIP_WIDTH_MM, 0.80)
        self.assertEqual(LipParameters().height_mm, 0.30)
        self.assertEqual(LipParameters().width_mm, 0.80)

    def test_straight_seams_add_separate_top_only_lips_and_preserve_source(self):
        source = Part.makeBox(100.0, 100.0, 8.0)
        source_before = source.exportBrepToString()
        drilled, application = self._application(source)
        self.assertEqual(source.exportBrepToString(), source_before)
        self.assertEqual(application.macro_result.solid_count, 4)
        self.assertEqual(len(application.reports), 4)
        self.assertTrue(application.dowel_holes_preserved)
        self.assertAlmostEqual(
            float(application.macro_result.shape.BoundBox.ZMax), 8.30, places=6
        )
        self.assertAlmostEqual(
            float(application.macro_result.shape.BoundBox.ZMin), 0.0, places=6
        )
        self.assertTrue(all(report.volume_added_mm3 > 0.0 for report in application.reports))
        self.assertTrue(all(report.total_length_mm > 0.0 for report in application.reports))
        self.assertTrue(all(report.is_printable for report in application.reports))
        self.assertEqual(len(tuple(application.macro_result.shape.Solids)), 4)
        for cutter in drilled.cutters:
            self.assertAlmostEqual(
                float(application.macro_result.shape.common(cutter).Volume),
                0.0,
                places=6,
            )

    def test_sinuous_lips_follow_path_and_do_not_fill_artistic_opening(self):
        source = Part.makeBox(300.0, 300.0, 8.0).cut(
            Part.makeCylinder(8.0, 8.0, Vector(60.0, 152.0, 0.0))
        )
        drilled, application = self._application(source)
        plan = drilled.macro_result.seam_plan
        self.assertEqual(plan.vertical.maximum_deviation_mm, 0.0)
        self.assertGreater(plan.horizontal.maximum_deviation_mm, 0.0)
        opening = Part.makeCylinder(7.5, 8.3, Vector(60.0, 152.0, 0.0))
        self.assertAlmostEqual(
            float(application.macro_result.shape.common(opening).Volume),
            0.0,
            places=5,
        )
        self.assertTrue(any(report.trimmed_segment_count for report in application.reports))

    def test_external_edges_and_intersection_are_cleanly_trimmed(self):
        _drilled, application = self._application(Part.makeBox(100.0, 100.0, 8.0))
        bounds = application.macro_result.shape.BoundBox
        self.assertAlmostEqual(float(bounds.XMin), 0.0, places=7)
        self.assertAlmostEqual(float(bounds.XMax), 100.0, places=7)
        self.assertAlmostEqual(float(bounds.YMin), 0.0, places=7)
        self.assertAlmostEqual(float(bounds.YMax), 100.0, places=7)
        exclusion = Part.makeBox(3.7, 3.7, 0.31, Vector(48.15, 48.15, 8.0))
        self.assertAlmostEqual(
            float(application.preview_shape.common(exclusion).Volume), 0.0, places=6
        )
        self.assertTrue(any(report.trimmed_segment_count for report in application.reports))

    def test_offset_regression_recomputes_actual_lips(self):
        source = Part.makeBox(300.0, 300.0, 8.0)
        _centered_drilled, centered = self._application(source)
        offset_drilled, offset = self._application(source, -2.0, 10.0)
        self.assertEqual(offset_drilled.macro_result.cut_x_mm, 148.0)
        self.assertEqual(offset_drilled.macro_result.cut_y_mm, 160.0)
        self.assertNotEqual(
            tuple(round(report.total_length_mm, 6) for report in centered.reports),
            tuple(round(report.total_length_mm, 6) for report in offset.reports),
        )

    def test_meshes_are_watertight_and_four_stls_reopen(self):
        _drilled, application = self._application(Part.makeBox(100.0, 100.0, 8.0))
        meshes = build_macro_mesh_parts(application.macro_result)
        self.assertEqual(len(meshes), 4)
        self.assertTrue(all(item.after.open_edge_count == 0 for item in meshes))
        self.assertTrue(all(item.after.non_manifold_edge_count == 0 for item in meshes))
        self.assertTrue(all(item.after.connected_component_count == 1 for item in meshes))
        self.assertTrue(all(item.after.is_solid for item in meshes))
        self.assertTrue(all(item.is_printable for item in meshes))
        with tempfile.TemporaryDirectory() as directory:
            artifacts = export_mesh_parts(meshes, directory)
            self.assertEqual(
                tuple(item.name for item in artifacts),
                ("Part_1", "Part_2", "Part_3", "Part_4"),
            )
            self.assertTrue(all(item.reopened.is_solid for item in artifacts))


if __name__ == "__main__":
    unittest.main()

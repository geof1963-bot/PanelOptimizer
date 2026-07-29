# -*- coding: utf-8 -*-
"""FreeCAD regressions against the two proven groove macros."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

try:
    import Part
    from FreeCAD import Vector
except ImportError:  # pragma: no cover - exercised outside FreeCAD
    Part = None
    Vector = None

from Core.MacroSplitCore import MacroGrooveParameters, MacroSplitCore


@unittest.skipIf(Part is None, "FreeCAD Part module is unavailable")
class MacroSplitCoreTests(unittest.TestCase):
    """Require exact agreement with macro cutter construction and sequence."""

    @staticmethod
    def _macro_reference(shape, vertical_offset=0.0, horizontal_offset=0.0):
        """Execute the attached offset macro's geometry without document I/O."""
        groove_depth = 1.2
        top_width = 2.2
        bottom_width = 0.5
        overlap = 20.0
        panel_shape = shape.copy()
        bb = panel_shape.BoundBox
        xmin, xmax = bb.XMin, bb.XMax
        ymin, ymax = bb.YMin, bb.YMax
        zmax = bb.ZMax
        width, height = xmax - xmin, ymax - ymin
        real_center_x = (xmin + xmax) / 2.0
        real_center_y = (ymin + ymax) / 2.0
        center_x = real_center_x + vertical_offset
        center_y = real_center_y + horizontal_offset
        half_top = top_width / 2.0
        half_bottom = bottom_width / 2.0
        z_bottom = zmax - groove_depth

        vertical_points = [
            Vector(center_x - half_top, ymin - overlap, zmax),
            Vector(center_x + half_top, ymin - overlap, zmax),
            Vector(center_x + half_top, ymin - overlap, z_bottom),
            Vector(center_x + half_bottom, ymin - overlap, z_bottom),
        ]
        vertical_poly = Part.makePolygon(vertical_points + [vertical_points[0]])
        vertical_cutter = Part.Face(Part.Wire(vertical_poly.Edges)).extrude(
            Vector(0, height + overlap * 2, 0)
        )
        horizontal_points = [
            Vector(xmin - overlap, center_y - half_top, zmax),
            Vector(xmin - overlap, center_y + half_top, zmax),
            Vector(xmin - overlap, center_y + half_top, z_bottom),
            Vector(xmin - overlap, center_y + half_bottom, z_bottom),
        ]
        horizontal_poly = Part.makePolygon(
            horizontal_points + [horizontal_points[0]]
        )
        horizontal_cutter = Part.Face(
            Part.Wire(horizontal_poly.Edges)
        ).extrude(Vector(width + overlap * 2, 0, 0))
        result = panel_shape.cut(vertical_cutter)
        result = result.cut(horizontal_cutter)
        try:
            result = result.removeSplitter()
        except Exception:
            pass
        return result

    @staticmethod
    def _metrics(shape):
        bounds = shape.BoundBox
        return (
            shape.ShapeType,
            len(shape.Solids),
            len(shape.Faces),
            float(shape.Volume),
            float(bounds.XMin),
            float(bounds.YMin),
            float(bounds.ZMin),
            float(bounds.XMax),
            float(bounds.YMax),
            float(bounds.ZMax),
        )

    def _assert_matches_macro(self, shape, x_offset=0.0, y_offset=0.0):
        expected = self._macro_reference(shape, x_offset, y_offset)
        actual = MacroSplitCore().cut(shape, x_offset, y_offset)
        self.assertAlmostEqual(
            actual.surface_groove_result_volume_mm3,
            expected.Volume,
            places=7,
        )
        self.assertEqual(actual.solid_count, 4)
        self.assertTrue(all(solid.isValid() for solid in actual.shape.Solids))
        self.assertTrue(all(solid.isClosed() for solid in actual.shape.Solids))
        self.assertLess(actual.result_volume_mm3, expected.Volume)
        self.assertEqual(actual.separation_width_mm, 0.5)
        return actual

    def test_centered_cut_matches_macro(self):
        """Zero offsets reproduce the centered macro exactly."""
        result = self._assert_matches_macro(Part.makeBox(100, 80, 8))
        self.assertEqual(result.real_center_x_mm, 50.0)
        self.assertEqual(result.real_center_y_mm, 40.0)
        self.assertEqual(result.cut_x_mm, 50.0)
        self.assertEqual(result.cut_y_mm, 40.0)

    def test_vertical_positive_offset(self):
        result = self._assert_matches_macro(Part.makeBox(100, 80, 8), 12.5, 0)
        self.assertEqual(result.cut_x_mm, 62.5)

    def test_vertical_negative_offset(self):
        result = self._assert_matches_macro(Part.makeBox(100, 80, 8), -7.0, 0)
        self.assertEqual(result.cut_x_mm, 43.0)

    def test_horizontal_positive_offset(self):
        result = self._assert_matches_macro(Part.makeBox(100, 80, 8), 0, 9.0)
        self.assertEqual(result.cut_y_mm, 49.0)

    def test_horizontal_negative_offset(self):
        result = self._assert_matches_macro(Part.makeBox(100, 80, 8), 0, -11.0)
        self.assertEqual(result.cut_y_mm, 29.0)

    def test_simultaneous_offsets_and_offset_coordinates(self):
        source = Part.makeBox(100, 80, 8, Vector(20, -30, 4))
        result = self._assert_matches_macro(source, -2.0, 10.0)
        self.assertEqual(result.real_center_x_mm, 70.0)
        self.assertEqual(result.real_center_y_mm, 10.0)
        self.assertEqual(result.cut_x_mm, 68.0)
        self.assertEqual(result.cut_y_mm, 20.0)

    def test_perforated_panel_matches_macro(self):
        source = Part.makeBox(120, 100, 8).cut(
            Part.makeCylinder(8, 8, Vector(60, 50, 0))
        ).cut(Part.makeCylinder(5, 8, Vector(25, 30, 0)))
        result = self._assert_matches_macro(source, -2.0, 10.0)
        self.assertGreaterEqual(result.solid_count, 1)

    def test_source_remains_byte_identical(self):
        source = Part.makeBox(120, 100, 8).cut(
            Part.makeCylinder(6, 8, Vector(40, 45, 0))
        )
        before = source.exportBrepToString()
        MacroSplitCore().cut(source, 3.0, -4.0)
        self.assertEqual(source.exportBrepToString(), before)

    def test_repeated_results_are_deterministic(self):
        source = Part.makeBox(120, 100, 8).cut(
            Part.makeCylinder(6, 8, Vector(40, 45, 0))
        )
        first = MacroSplitCore().cut(source, -2.0, 10.0)
        second = MacroSplitCore().cut(source, -2.0, 10.0)
        self.assertEqual(first.cut_x_mm, second.cut_x_mm)
        self.assertEqual(first.cut_y_mm, second.cut_y_mm)
        self.assertEqual(self._metrics(first.shape), self._metrics(second.shape))
        self.assertEqual(
            first.shape.exportBrepToString(),
            second.shape.exportBrepToString(),
        )

    def test_profile_defaults_are_exact_macro_values(self):
        self.assertEqual(
            MacroGrooveParameters(),
            MacroGrooveParameters(1.2, 2.2, 0.5, 20.0),
        )

    def test_workbench_command_creates_four_parts_without_analysis(self):
        """Command writes four lipped parts and all lightweight previews."""
        import FreeCAD
        from Commands.SplitPanelCommand import PanelOptimizerSplitPanelCommand

        document = FreeCAD.newDocument("PanelOptimizerMacroSplitCommand")
        try:
            source_object = document.addObject("Part::Feature", "FINAL_PANEL")
            source_object.Shape = Part.makeBox(300, 280, 8)
            before = self._metrics(source_object.Shape)
            with patch(
                "Commands.SplitPanelCommand.FreeCADGui.Selection",
                SimpleNamespace(getSelection=lambda: (source_object,)),
                create=True,
            ), patch.object(
                PanelOptimizerSplitPanelCommand,
                "_select_output_directory",
                return_value="",
            ):
                PanelOptimizerSplitPanelCommand().Activated()

            group = document.getObject("PanelOptimizer_Result")
            self.assertIsNotNone(group)
            self.assertEqual(
                tuple(item.Name for item in group.Group),
                ("Part_1", "Part_2", "Part_3", "Part_4"),
            )
            self.assertIsNotNone(
                document.getObject("PanelOptimizer_VerticalSeam")
            )
            self.assertIsNotNone(
                document.getObject("PanelOptimizer_HorizontalSeam")
            )
            self.assertIsNotNone(document.getObject("PanelOptimizer_Dowels"))
            lips = document.getObject("PanelOptimizer_Lips")
            self.assertIsNotNone(lips)
            self.assertEqual(
                lips.PanelOptimizerRole,
                "PanelOptimizer.LipPreview.v4",
            )
            self.assertGreater(float(lips.Shape.Volume), 0.0)
            self.assertEqual(self._metrics(source_object.Shape), before)
        finally:
            FreeCAD.closeDocument(document.Name)


if __name__ == "__main__":
    unittest.main()

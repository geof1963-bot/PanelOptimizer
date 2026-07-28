# -*- coding: utf-8 -*-
"""FreeCAD integration tests for V4.21 direct-solid extraction."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

try:
    import FreeCAD
    import Part
    from FreeCAD import Vector
except ImportError:  # pragma: no cover
    FreeCAD = None
    Part = None
    Vector = None

from Core.Exceptions import PrintableLimitViolation, STLExportError
from Core.ExportEngine import ExportEngine
from Core.MacroPartExtractor import MacroPartExtractor
from Core.MacroSplitCore import MacroSplitCore
from Core.SplitWorkflow import SplitDocumentWriter
from Core.SplittingUtilities import volume_tolerance_mm3


@unittest.skipIf(Part is None, "FreeCAD Part module is unavailable")
class MacroPartExtractionTests(unittest.TestCase):
    """Extract and validate four solids from already macro-cut geometry."""

    @staticmethod
    def _extract(shape, x_offset=0.0, y_offset=0.0, settings=None):
        macro = MacroSplitCore().cut(shape, x_offset, y_offset)
        extractor = (
            MacroPartExtractor(settings)
            if settings is not None
            else MacroPartExtractor()
        )
        return macro, extractor.extract(macro, "macro-panel")

    def test_plain_594_panel_produces_four_centered_solids(self):
        source = Part.makeBox(594, 594, 8)
        macro, extraction = self._extract(source)
        execution = extraction.execution
        self.assertEqual(len(execution.shapes), 4)
        self.assertEqual(
            tuple(part.quadrant for part in execution.result.parts),
            ("lower_left", "lower_right", "upper_left", "upper_right"),
        )
        self.assertTrue(all(shape.ShapeType == "Solid" for shape in execution.shapes))
        self.assertTrue(all(shape.isValid() for shape in execution.shapes))
        self.assertTrue(all(shape.isClosed() for shape in execution.shapes))
        self.assertEqual(execution.result.cut_x_mm, 297.0)
        self.assertEqual(execution.result.cut_y_mm, 297.0)
        self.assertEqual(macro.solid_count, 4)
        self.assertGreater(
            macro.source_volume_mm3,
            macro.surface_groove_result_volume_mm3,
        )
        self.assertGreater(
            macro.surface_groove_result_volume_mm3,
            macro.result_volume_mm3,
        )
        self.assertAlmostEqual(
            macro.surface_groove_removed_volume_mm3
            + macro.additional_separation_removed_volume_mm3,
            macro.source_volume_mm3 - macro.result_volume_mm3,
            places=7,
        )
        self.assertEqual(macro.separation_width_mm, 0.5)
        self.assertLessEqual(
            extraction.extraction_delta_mm3,
            volume_tolerance_mm3(macro.result_volume_mm3),
        )

    def test_extraction_runs_no_post_cut_partition_operation(self):
        """V4.21 reads direct solids and contains no slice/general-fuse path."""
        source = (
            Path(__file__).resolve().parents[1]
            / "Core"
            / "MacroPartExtractor.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("from BOPTools", source)
        self.assertNotIn("SplitAPI.slice(", source)
        self.assertNotIn(".generalFuse(", source)
        self.assertNotIn("common(tool", source)

    def test_offsets_drive_quadrant_bounds_and_order(self):
        source = Part.makeBox(594, 594, 8)
        _, extraction = self._extract(source, -2.0, 10.0)
        result = extraction.execution.result
        self.assertEqual(result.cut_x_mm, 295.0)
        self.assertEqual(result.cut_y_mm, 307.0)
        self.assertEqual(
            tuple((part.size_x_mm, part.size_y_mm) for part in result.parts),
            (
                (295.25, 307.25),
                (298.25, 307.25),
                (295.25, 286.25),
                (298.25, 286.25),
            ),
        )

    def test_perforations_and_cut_intersections_are_preserved(self):
        source = Part.makeBox(200, 180, 8)
        holes = (
            Part.makeCylinder(7, 8, Vector(35, 35, 0)),
            Part.makeCylinder(6, 8, Vector(97, 60, 0)),
            Part.makeCylinder(8, 8, Vector(100, 90, 0)),
            Part.makeCylinder(5, 8, Vector(150, 135, 0)),
        )
        for hole in holes:
            source = source.cut(hole)
        macro, extraction = self._extract(source)
        self.assertEqual(len(extraction.execution.shapes), 4)
        self.assertTrue(all(shape.isValid() for shape in extraction.execution.shapes))
        self.assertAlmostEqual(
            sum(shape.Volume for shape in extraction.execution.shapes),
            macro.result_volume_mm3,
            delta=volume_tolerance_mm3(macro.result_volume_mm3),
        )
        self.assertTrue(
            any(
                "Cylinder" in type(face.Surface).__name__
                for shape in extraction.execution.shapes
                for face in shape.Faces
            )
        )

    def test_parts_have_zero_pairwise_material_overlap(self):
        _, extraction = self._extract(Part.makeBox(120, 100, 8))
        tolerance = volume_tolerance_mm3(extraction.macro_result_volume_mm3)
        shapes = extraction.execution.shapes
        for index, first in enumerate(shapes):
            for second in shapes[index + 1 :]:
                self.assertLessEqual(first.common(second).Volume, tolerance)

    def test_printable_limits_pass_fail_and_equality(self):
        source = Part.makeBox(100, 80, 8)
        equal = SimpleNamespace(MAX_PART_WIDTH=50.25, MAX_PART_HEIGHT=40.25)
        failing = SimpleNamespace(MAX_PART_WIDTH=49.0, MAX_PART_HEIGHT=39.0)
        _, equal_result = self._extract(source, settings=equal)
        _, failed_result = self._extract(source, settings=failing)
        self.assertTrue(equal_result.execution.result.all_parts_printable)
        self.assertFalse(failed_result.execution.result.all_parts_printable)
        self.assertTrue(
            all(not part.is_printable for part in failed_result.execution.result.parts)
        )

    def test_source_is_unchanged_and_repeated_results_are_deterministic(self):
        source = Part.makeBox(120, 100, 8).cut(
            Part.makeCylinder(5, 8, Vector(30, 30, 0))
        )
        before = source.exportBrepToString()
        _, first = self._extract(source, 3.0, -4.0)
        _, second = self._extract(source, 3.0, -4.0)
        self.assertEqual(source.exportBrepToString(), before)
        self.assertEqual(first.execution.result, second.execution.result)
        self.assertEqual(
            tuple(shape.exportBrepToString() for shape in first.execution.shapes),
            tuple(shape.exportBrepToString() for shape in second.execution.shapes),
        )

    def test_document_lifecycle_keeps_exact_owned_four_part_set(self):
        document = FreeCAD.newDocument("PanelOptimizerMacroParts")
        try:
            source = document.addObject("Part::Feature", "SourcePanel")
            source.Shape = Part.makeBox(100, 80, 8)
            before = source.Shape.Volume
            _, extraction = self._extract(source.Shape)
            writer = SplitDocumentWriter()
            writer.write(document, extraction.execution)
            writer.write(document, extraction.execution)
            group = document.getObject("PanelOptimizer_Result")
            self.assertEqual(
                tuple(item.Name for item in group.Group),
                ("Part_1", "Part_2", "Part_3", "Part_4"),
            )
            self.assertEqual(source.Shape.Volume, before)
        finally:
            FreeCAD.closeDocument(document.Name)

    def test_transactional_four_stl_export_and_limit_block(self):
        _, extraction = self._extract(Part.makeBox(100, 80, 8))
        execution = extraction.execution
        with tempfile.TemporaryDirectory() as directory:
            report = ExportEngine(execution.resolve_shape).export_parts(
                execution.result.parts,
                directory,
            )
            files = tuple(sorted(Path(directory).iterdir()))
            self.assertEqual(
                tuple(path.name for path in files),
                ("Part_1.stl", "Part_2.stl", "Part_3.stl", "Part_4.stl"),
            )
            self.assertTrue(all(path.stat().st_size > 0 for path in files))
            self.assertEqual(len(report.artifacts), 4)

        limits = SimpleNamespace(MAX_PART_WIDTH=10.0, MAX_PART_HEIGHT=10.0)
        _, blocked = self._extract(Part.makeBox(100, 80, 8), settings=limits)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(PrintableLimitViolation):
                ExportEngine(blocked.execution.resolve_shape).export_parts(
                    blocked.execution.result.parts,
                    directory,
                )
            self.assertEqual(tuple(Path(directory).iterdir()), ())

    def test_export_failure_removes_partial_files(self):
        _, extraction = self._extract(Part.makeBox(100, 80, 8))
        execution = extraction.execution
        calls = 0

        def failing(reference):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError("injected export failure")
            return execution.resolve_shape(reference)

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(STLExportError):
                ExportEngine(failing).export_parts(execution.result.parts, directory)
            self.assertEqual(tuple(Path(directory).iterdir()), ())


if __name__ == "__main__":
    unittest.main()

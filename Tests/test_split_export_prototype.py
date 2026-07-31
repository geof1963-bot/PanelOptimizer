# -*- coding: utf-8 -*-
"""FreeCAD integration tests for the legacy four-part split prototype."""

from __future__ import annotations

import ast
import os
import tempfile
import unittest
from dataclasses import fields, is_dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    import FreeCAD
    import Mesh
    import Part
    from FreeCAD import Vector
except ImportError:  # pragma: no cover - exercised outside FreeCAD
    FreeCAD = None
    Mesh = None
    Part = None
    Vector = None

from Core.Exceptions import (
    InvalidSelectionError,
    PrintableLimitViolation,
    SplitOperationError,
    SplitSourceError,
    STLExportError,
)
from Core.ExportEngine import ExportEngine
from Core.Models import SplitResult
from Core.SplitterEngine import SplitExecution, SplitterEngine
from Core.SplitWorkflow import SplitDocumentWriter, validate_single_selection
from Core.SplittingUtilities import volume_tolerance_mm3


@unittest.skipIf(Part is None, "FreeCAD Part module is unavailable")
class SplitExportPrototypeTests(unittest.TestCase):
    """Verify deterministic B-rep splitting, validation, output, and export."""

    @staticmethod
    def _split(shape, source_id="prototype-panel", settings=None):
        """Split one source with default or injected effective limits."""
        engine = SplitterEngine(settings) if settings is not None else SplitterEngine()
        return engine.split_four_quadrants(shape, source_id)

    def _assert_model_value_is_freecad_independent(self, value):
        """Recursively allow only immutable model values and scalar leaves."""
        if is_dataclass(value):
            self.assertTrue(value.__class__.__module__.startswith("Core.Models"))
            self.assertTrue(value.__class__.__dataclass_params__.frozen)
            for model_field in fields(value):
                self._assert_model_value_is_freecad_independent(
                    getattr(value, model_field.name)
                )
            return
        if isinstance(value, tuple):
            for item in value:
                self._assert_model_value_is_freecad_independent(item)
            return
        self.assertIsInstance(value, (str, int, float, bool, type(None)))

    def test_594_plate_produces_four_297_by_297_solids(self):
        """The default center cuts produce four printable quadrants."""
        execution = self._split(Part.makeBox(594, 594, 8), "large-panel")

        self.assertEqual(len(execution.shapes), 4)
        self.assertEqual(len(execution.result.parts), 4)
        self.assertEqual(execution.result.cut_x_mm, 297.0)
        self.assertEqual(execution.result.cut_y_mm, 297.0)
        self.assertTrue(execution.result.all_parts_printable)
        self.assertEqual(
            execution.partition_method,
            "Part.TopoShape.generalFuse(two planar tools)",
        )
        self.assertEqual(execution.initial_partition_solid_count, 4)
        self.assertEqual(execution.solids_per_quadrant, (1, 1, 1, 1))
        self.assertEqual(
            execution.result.strategy,
            "bounding_box_center_quadrants",
        )
        for part, shape in zip(execution.result.parts, execution.shapes):
            self.assertEqual(shape.ShapeType, "Solid")
            self.assertEqual(len(shape.Solids), 1)
            self.assertTrue(shape.isValid())
            self.assertAlmostEqual(part.size_x_mm, 297.0)
            self.assertAlmostEqual(part.size_y_mm, 297.0)
            self.assertAlmostEqual(part.size_z_mm, 8.0)
            self.assertTrue(part.within_x_limit)
            self.assertTrue(part.within_y_limit)

    def test_volume_is_preserved_and_result_solids_do_not_overlap(self):
        """Quadrants reconstruct source volume without shared interior."""
        source = Part.makeBox(594, 594, 8)
        execution = self._split(source, "volume-panel")
        tolerance = volume_tolerance_mm3(source.Volume)

        self.assertLessEqual(execution.result.volume_difference_mm3, tolerance)
        self.assertAlmostEqual(
            sum(shape.Volume for shape in execution.shapes),
            source.Volume,
            delta=tolerance,
        )
        for first_index, first in enumerate(execution.shapes):
            for second in execution.shapes[first_index + 1 :]:
                self.assertLessEqual(first.common(second).Volume, tolerance)

    def test_quadrant_order_is_model_coordinate_deterministic(self):
        """Names map to lower-left, lower-right, upper-left, upper-right."""
        source = Part.makeBox(100, 80, 5, Vector(10, 20, 3))
        execution = self._split(source, "offset-panel")

        self.assertEqual(
            tuple(part.name for part in execution.result.parts),
            ("Part_1", "Part_2", "Part_3", "Part_4"),
        )
        self.assertEqual(
            tuple(part.quadrant for part in execution.result.parts),
            (
                "lower_left",
                "lower_right",
                "upper_left",
                "upper_right",
            ),
        )
        self.assertEqual(
            tuple(
                (
                    part.bounding_box.minimum.x_mm,
                    part.bounding_box.minimum.y_mm,
                )
                for part in execution.result.parts
            ),
            ((10.0, 20.0), (60.0, 20.0), (10.0, 60.0), (60.0, 60.0)),
        )

    def test_perforations_are_preserved_by_boolean_intersection(self):
        """A center-crossing cylindrical hole remains absent from all parts."""
        plain_volume = 100.0 * 100.0 * 8.0
        source = Part.makeBox(100, 100, 8).cut(
            Part.makeCylinder(10, 8, Vector(50, 50, 0))
        )
        execution = self._split(source, "perforated-panel")

        self.assertEqual(len(execution.shapes), 4)
        self.assertTrue(all(shape.isValid() for shape in execution.shapes))
        self.assertLess(sum(shape.Volume for shape in execution.shapes), plain_volume)
        self.assertAlmostEqual(
            sum(shape.Volume for shape in execution.shapes),
            source.Volume,
            delta=volume_tolerance_mm3(source.Volume),
        )
        self.assertTrue(
            all(
                any(
                    "Cylinder" in type(face.Surface).__name__
                    for face in shape.Faces
                )
                for shape in execution.shapes
            )
        )

    def test_representative_multi_hole_panel_preserves_every_void(self):
        """Inside, X-crossing, Y-crossing, and center-near holes survive."""
        depth = 8.0
        holes = (
            (40.0, 40.0, 8.0),
            (100.0, 50.0, 7.0),
            (50.0, 100.0, 7.0),
            (104.0, 104.0, 6.0),
        )
        tools = tuple(
            Part.makeCylinder(radius, depth, Vector(x, y, 0))
            for x, y, radius in holes
        )
        source = Part.makeBox(200, 200, depth).cut(
            tools[0].fuse(tools[1]).fuse(tools[2]).fuse(tools[3])
        )
        execution = self._split(source, "representative-perforated-panel")
        expected_volume = 200.0 * 200.0 * depth - sum(
            3.141592653589793 * radius * radius * depth
            for _, _, radius in holes
        )

        self.assertEqual(len(execution.shapes), 4)
        self.assertTrue(all(shape.ShapeType == "Solid" for shape in execution.shapes))
        self.assertTrue(all(shape.isValid() for shape in execution.shapes))
        self.assertAlmostEqual(
            source.Volume,
            expected_volume,
            delta=volume_tolerance_mm3(source.Volume),
        )
        self.assertAlmostEqual(
            sum(shape.Volume for shape in execution.shapes),
            source.Volume,
            delta=volume_tolerance_mm3(source.Volume),
        )
        self.assertTrue(
            all(
                any(
                    "Cylinder" in type(face.Surface).__name__
                    for face in shape.Faces
                )
                for shape in execution.shapes
            )
        )

    def test_complex_perforated_brep_uses_one_coherent_partition(self):
        """Many cut features are partitioned by one two-plane slice call."""
        source = Part.makeBox(180, 140, 8, Vector(-30, 15, 2))
        holes = tuple(
            Part.makeCylinder(
                3.0 + (index % 3),
                8,
                Vector(-15 + (index % 6) * 28, 28 + (index // 6) * 32, 2),
            )
            for index in range(18)
        )
        cutting_tool = holes[0]
        for hole in holes[1:]:
            cutting_tool = cutting_tool.fuse(hole)
        source = source.cut(cutting_tool)
        before = source.exportBrepToString()

        real_partition = SplitterEngine._partition_source
        with patch.object(
            SplitterEngine,
            "_partition_source",
            wraps=real_partition,
        ) as partition_call:
            execution = self._split(source, "complex-partition")

        self.assertEqual(partition_call.call_count, 1)
        self.assertEqual(execution.initial_partition_solid_count, 4)
        self.assertEqual(execution.solids_per_quadrant, (1, 1, 1, 1))
        self.assertTrue(all(shape.isValid() for shape in execution.shapes))
        self.assertTrue(all(shape.isClosed() for shape in execution.shapes))
        self.assertAlmostEqual(
            sum(shape.Volume for shape in execution.shapes),
            source.Volume,
            delta=volume_tolerance_mm3(source.Volume),
        )
        self.assertEqual(source.exportBrepToString(), before)

    def test_split_command_has_no_analyzer_prerequisite(self):
        """The basic split command remains independent of deep analysis."""
        command_source = (
            Path(__file__).resolve().parents[1]
            / "Commands"
            / "SplitPanelCommand.py"
        ).read_text(encoding="utf-8")
        splitter_source = (
            Path(__file__).resolve().parents[1]
            / "Core"
            / "SplitterEngine.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("AnalyzerEngine", command_source)
        self.assertNotIn("AnalyzerEngine", splitter_source)

    def test_source_under_effective_limits_is_still_split(self):
        """Prototype semantics always create four parts for a valid source."""
        execution = self._split(Part.makeBox(100, 80, 5), "small-panel")

        self.assertEqual(len(execution.result.parts), 4)
        self.assertTrue(execution.result.all_parts_printable)

    def test_oversized_parts_are_recorded_and_export_is_blocked(self):
        """Limit violations preserve split geometry but never export silently."""
        settings = SimpleNamespace(
            MAX_PART_WIDTH=200.0,
            MAX_PART_HEIGHT=200.0,
        )
        execution = self._split(
            Part.makeBox(594, 594, 8),
            "oversized-results",
            settings,
        )

        self.assertFalse(execution.result.all_parts_printable)
        self.assertTrue(all(not part.is_printable for part in execution.result.parts))
        self.assertTrue(
            all(
                not part.within_x_limit and not part.within_y_limit
                for part in execution.result.parts
            )
        )
        with tempfile.TemporaryDirectory() as output_directory:
            with self.assertRaises(PrintableLimitViolation):
                ExportEngine(execution.resolve_shape).export_parts(
                    execution.result.parts,
                    output_directory,
                )
            self.assertEqual(tuple(Path(output_directory).iterdir()), ())

    def test_printable_limit_equality_passes_and_any_excess_fails(self):
        """Limit comparison is exact <= with no legacy or hard-coded value."""
        source = Part.makeBox(594, 594, 8)
        equal_settings = SimpleNamespace(
            MAX_PART_WIDTH=297.0,
            MAX_PART_HEIGHT=297.0,
            MAX_PART_SIZE=1.0,
        )
        below_settings = SimpleNamespace(
            MAX_PART_WIDTH=296.999,
            MAX_PART_HEIGHT=296.999,
            MAX_PART_SIZE=1000.0,
        )

        equal = self._split(source, "limit-equality", equal_settings)
        excessive = self._split(source, "limit-excess", below_settings)

        self.assertTrue(equal.result.all_parts_printable)
        self.assertTrue(all(part.is_printable for part in equal.result.parts))
        self.assertFalse(excessive.result.all_parts_printable)
        self.assertTrue(
            all(not part.is_printable for part in excessive.result.parts)
        )
        production_source = (
            Path(__file__).resolve().parents[1]
            / "Core"
            / "SplitterEngine.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("MAX_PART_SIZE", production_source)
        self.assertNotIn("330", production_source)

    def test_original_source_shape_remains_unchanged(self):
        """Boolean construction never mutates or replaces the caller's source."""
        source = Part.makeBox(120, 90, 6).cut(
            Part.makeCylinder(5, 6, Vector(30, 30, 0))
        )
        before = (
            source.Volume,
            source.Area,
            source.BoundBox.XMin,
            source.BoundBox.XMax,
            source.BoundBox.YMin,
            source.BoundBox.YMax,
            len(source.Faces),
            len(source.Solids),
        )

        self._split(source, "unchanged-source")

        after = (
            source.Volume,
            source.Area,
            source.BoundBox.XMin,
            source.BoundBox.XMax,
            source.BoundBox.YMin,
            source.BoundBox.YMax,
            len(source.Faces),
            len(source.Solids),
        )
        self.assertEqual(after, before)
        self.assertTrue(source.isValid())

    def test_document_writer_creates_exact_group_and_four_visible_objects(self):
        """FreeCAD output has deterministic names without hiding the source."""
        document_name = "PanelOptimizerPrototypeOutput"
        document = FreeCAD.newDocument(document_name)
        try:
            source_object = document.addObject("Part::Feature", "SourcePanel")
            source_object.Shape = Part.makeBox(100, 80, 5)
            source_volume = source_object.Shape.Volume
            execution = self._split(source_object.Shape, source_object.Name)

            outputs = SplitDocumentWriter().write(document, execution)

            group = document.getObject("PanelOptimizer_Result")
            self.assertIsNotNone(group)
            self.assertEqual(
                tuple(item.Name for item in group.Group),
                ("Part_1", "Part_2", "Part_3", "Part_4"),
            )
            self.assertEqual(tuple(item.Name for item in outputs), tuple(
                f"Part_{index}" for index in range(1, 5)
            ))
            self.assertTrue(all(item.Shape.isValid() for item in outputs))
            self.assertTrue(
                all(
                    item.ViewObject is None or item.ViewObject.Visibility
                    for item in outputs
                )
            )
            self.assertEqual(source_object.Shape.Volume, source_volume)
            self.assertTrue(
                source_object.ViewObject is None
                or source_object.ViewObject.Visibility
            )
        finally:
            FreeCAD.closeDocument(document_name)

    def test_stl_export_writes_exactly_four_nonempty_files(self):
        """Export uses deterministic filenames and immutable artifact records."""
        execution = self._split(Part.makeBox(100, 80, 5), "export-panel")

        with tempfile.TemporaryDirectory() as output_directory:
            report = ExportEngine(execution.resolve_shape).export_parts(
                execution.result.parts,
                output_directory,
            )
            paths = tuple(sorted(Path(output_directory).iterdir()))

            self.assertEqual(
                tuple(path.name for path in paths),
                ("Part_1.stl", "Part_2.stl", "Part_3.stl", "Part_4.stl"),
            )
            self.assertTrue(all(path.stat().st_size > 0 for path in paths))
            self.assertEqual(len(report.artifacts), 4)
            self.assertEqual(report.split_result_id, execution.result.result_id)
            self.assertTrue(all(item.byte_count > 0 for item in report.artifacts))

    def test_each_stl_contains_its_corresponding_asymmetric_part(self):
        """Part_N filenames resolve only the matching quadrant B-rep."""
        base = Part.makeBox(100, 100, 1)
        bosses = (
            Part.makeBox(10, 10, 1, Vector(10, 10, 1)),
            Part.makeBox(10, 10, 2, Vector(70, 10, 1)),
            Part.makeBox(10, 10, 3, Vector(10, 70, 1)),
            Part.makeBox(10, 10, 4, Vector(70, 70, 1)),
        )
        source = base.fuse(bosses[0]).fuse(bosses[1]).fuse(
            bosses[2]
        ).fuse(bosses[3])
        execution = self._split(source, "asymmetric-export")

        with tempfile.TemporaryDirectory() as output_directory:
            ExportEngine(execution.resolve_shape).export_parts(
                execution.result.parts,
                output_directory,
            )
            mesh_volumes = tuple(
                abs(float(Mesh.Mesh(
                    str(Path(output_directory) / f"Part_{index}.stl")
                ).Volume))
                for index in range(1, 5)
            )

        brep_volumes = tuple(part.volume_mm3 for part in execution.result.parts)
        self.assertEqual(tuple(sorted(mesh_volumes)), mesh_volumes)
        for mesh_volume, brep_volume in zip(mesh_volumes, brep_volumes):
            self.assertAlmostEqual(mesh_volume, brep_volume, delta=0.01)

    def test_stl_failure_removes_every_partial_file(self):
        """A hard serialization failure leaves no half-created export set."""
        execution = self._split(Part.makeBox(100, 80, 5), "failed-export")
        calls = 0

        def failing_resolver(reference):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("Injected exporter failure")
            return execution.resolve_shape(reference)

        with tempfile.TemporaryDirectory() as output_directory:
            with self.assertRaises(STLExportError):
                ExportEngine(failing_resolver).export_parts(
                    execution.result.parts,
                    output_directory,
                )
            self.assertEqual(tuple(Path(output_directory).iterdir()), ())

    def test_stl_failure_preserves_previous_valid_final_files(self):
        """Pre-existing final STLs remain byte-identical before commit."""
        execution = self._split(Part.makeBox(100, 80, 5), "preserved-export")
        calls = 0

        def failing_resolver(reference):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise RuntimeError("Injected exporter failure")
            return execution.resolve_shape(reference)

        with tempfile.TemporaryDirectory() as output_directory:
            expected = {}
            for index in range(1, 5):
                path = Path(output_directory) / f"Part_{index}.stl"
                content = f"previous-{index}".encode("ascii")
                path.write_bytes(content)
                expected[path.name] = content

            with self.assertRaises(STLExportError):
                ExportEngine(failing_resolver).export_parts(
                    execution.result.parts,
                    output_directory,
                )

            self.assertEqual(
                {
                    path.name: path.read_bytes()
                    for path in Path(output_directory).iterdir()
                },
                expected,
            )

    def test_stl_commit_failure_restores_previous_four_file_set(self):
        """A finalization error rolls every destination back atomically."""
        execution = self._split(Part.makeBox(100, 80, 5), "commit-failure")

        with tempfile.TemporaryDirectory() as output_directory:
            expected = {}
            for index in range(1, 5):
                path = Path(output_directory) / f"Part_{index}.stl"
                content = f"stable-{index}".encode("ascii")
                path.write_bytes(content)
                expected[path.name] = content

            real_replace = os.replace
            replace_calls = 0

            def fail_second_commit(source, destination):
                nonlocal replace_calls
                replace_calls += 1
                if replace_calls == 6:
                    raise OSError("Injected atomic-replace failure")
                return real_replace(source, destination)

            with patch(
                "Core.ExportEngine.os.replace",
                side_effect=fail_second_commit,
            ):
                with self.assertRaises(STLExportError):
                    ExportEngine(execution.resolve_shape).export_parts(
                        execution.result.parts,
                        output_directory,
                    )

            self.assertEqual(
                {
                    path.name: path.read_bytes()
                    for path in Path(output_directory).iterdir()
                },
                expected,
            )

    def test_repeated_splits_have_equivalent_models_and_geometry(self):
        """Unchanged source and settings give stable records and B-rep metrics."""
        source = Part.makeBox(100, 80, 5).cut(
            Part.makeCylinder(4, 5, Vector(25, 20, 0))
        )

        first = self._split(source, "deterministic-split")
        second = self._split(source, "deterministic-split")

        self.assertEqual(first.result, second.result)
        self.assertEqual(
            tuple(
                (
                    shape.ShapeType,
                    shape.Volume,
                    shape.Area,
                    len(shape.Faces),
                    shape.BoundBox.XMin,
                    shape.BoundBox.YMin,
                    shape.BoundBox.XMax,
                    shape.BoundBox.YMax,
                )
                for shape in first.shapes
            ),
            tuple(
                (
                    shape.ShapeType,
                    shape.Volume,
                    shape.Area,
                    len(shape.Faces),
                    shape.BoundBox.XMin,
                    shape.BoundBox.YMin,
                    shape.BoundBox.XMax,
                    shape.BoundBox.YMax,
                )
                for shape in second.shapes
            ),
        )

    def test_invalid_selection_and_non_solid_shape_fail_cleanly(self):
        """Selection and source validation use explicit project exceptions."""
        with self.assertRaises(InvalidSelectionError):
            validate_single_selection(())
        with self.assertRaises(InvalidSelectionError):
            validate_single_selection((object(), object()))
        with self.assertRaises(InvalidSelectionError):
            validate_single_selection((object(),))
        with self.assertRaises(SplitSourceError):
            self._split(Part.makePlane(10, 10), "face-only")
        with self.assertRaises(SplitSourceError):
            self._split(Part.Shape(), "null-shape")

    def test_models_remain_freecad_independent(self):
        """No runtime B-rep crosses into SplitResult or model imports."""
        execution = self._split(Part.makeBox(20, 20, 2), "model-boundary")
        self.assertIsInstance(execution.result, SplitResult)
        self._assert_model_value_is_freecad_independent(execution.result)

        module_path = (
            Path(__file__).resolve().parents[1] / "Core" / "Models" / "Split.py"
        )
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        imported = {
            alias.name.split(".", maxsplit=1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module.split(".", maxsplit=1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertTrue(
            {"FreeCAD", "FreeCADGui", "Part", "Gui"}.isdisjoint(imported)
        )

    def test_existing_reserved_document_name_causes_no_partial_output(self):
        """Writer detects conflicts before adding any result object."""
        document_name = "PanelOptimizerPrototypeConflict"
        document = FreeCAD.newDocument(document_name)
        try:
            document.addObject("App::FeaturePython", "Part_1")
            execution = self._split(Part.makeBox(20, 20, 2), "conflict-panel")

            with self.assertRaises(SplitOperationError):
                SplitDocumentWriter().write(document, execution)

            self.assertIsNone(document.getObject("PanelOptimizer_Result"))
            self.assertIsNone(document.getObject("Part_2"))
            self.assertIsNone(document.getObject("Part_3"))
            self.assertIsNone(document.getObject("Part_4"))
        finally:
            FreeCAD.closeDocument(document_name)

    def test_initial_document_write_failure_leaves_no_partial_group(self):
        """A failed first write removes only its incomplete owned objects."""
        document_name = "PanelOptimizerPrototypeInitialRollback"
        document = FreeCAD.newDocument(document_name)
        try:
            source_object = document.addObject("Part::Feature", "SourcePanel")
            source_object.Shape = Part.makeBox(100, 80, 5)
            execution = self._split(source_object.Shape, source_object.Name)

            class CopyFailure:
                @staticmethod
                def copy():
                    raise RuntimeError("Injected initial write failure")

            failing = SplitExecution(
                result=execution.result,
                shapes=(
                    execution.shapes[0],
                    execution.shapes[1],
                    CopyFailure(),
                    execution.shapes[3],
                ),
            )
            with self.assertRaises(SplitOperationError):
                SplitDocumentWriter().write(document, failing)

            self.assertIsNone(document.getObject("PanelOptimizer_Result"))
            self.assertTrue(
                all(
                    document.getObject(name) is None
                    for name in SplitDocumentWriter.PART_NAMES
                )
            )
            self.assertIs(document.getObject("SourcePanel"), source_object)
        finally:
            FreeCAD.closeDocument(document_name)

    def test_repeated_document_write_replaces_only_owned_results(self):
        """Repeated writes update one complete owned result set in place."""
        document_name = "PanelOptimizerPrototypeRepeatedOutput"
        document = FreeCAD.newDocument(document_name)
        try:
            source_object = document.addObject("Part::Feature", "SourcePanel")
            source_object.Shape = Part.makeBox(100, 80, 5)
            source_volume = source_object.Shape.Volume
            execution = self._split(source_object.Shape, source_object.Name)
            writer = SplitDocumentWriter()

            first = writer.write(document, execution)
            second = writer.write(document, execution)

            group = document.getObject("PanelOptimizer_Result")
            self.assertEqual(
                group.PanelOptimizerRole,
                SplitDocumentWriter.GROUP_ROLE,
            )
            self.assertEqual(
                tuple(item.Name for item in group.Group),
                SplitDocumentWriter.PART_NAMES,
            )
            self.assertEqual(tuple(item.Name for item in second), writer.PART_NAMES)
            self.assertTrue(
                all(
                    item.PanelOptimizerRole == SplitDocumentWriter.PART_ROLE
                    for item in second
                )
            )
            self.assertEqual(source_object.Shape.Volume, source_volume)
            self.assertIs(document.getObject("SourcePanel"), source_object)
            self.assertEqual(
                {item.Name for item in document.Objects},
                {
                    "SourcePanel",
                    "PanelOptimizer_Result",
                    "Part_1",
                    "Part_2",
                    "Part_3",
                    "Part_4",
                },
            )
            self.assertEqual(len(first), 4)
        finally:
            FreeCAD.closeDocument(document_name)

    def test_failed_replacement_restores_previous_owned_result(self):
        """Explicit backups restore a valid result after replacement fails."""
        document_name = "PanelOptimizerPrototypeRollback"
        document = FreeCAD.newDocument(document_name)
        try:
            source_object = document.addObject("Part::Feature", "SourcePanel")
            source_object.Shape = Part.makeBox(100, 80, 5)
            execution = self._split(source_object.Shape, source_object.Name)
            writer = SplitDocumentWriter()
            writer.write(document, execution)
            previous_volumes = tuple(
                document.getObject(name).Shape.Volume
                for name in writer.PART_NAMES
            )

            class CopyFailure:
                @staticmethod
                def copy():
                    raise RuntimeError("Injected document write failure")

            failing = SplitExecution(
                result=execution.result,
                shapes=(
                    execution.shapes[0],
                    execution.shapes[1],
                    CopyFailure(),
                    execution.shapes[3],
                ),
            )
            with self.assertRaises(SplitOperationError):
                writer.write(document, failing)

            restored_group = document.getObject("PanelOptimizer_Result")
            self.assertIsNotNone(restored_group)
            self.assertEqual(
                tuple(item.Name for item in restored_group.Group),
                writer.PART_NAMES,
            )
            self.assertEqual(
                tuple(
                    document.getObject(name).Shape.Volume
                    for name in writer.PART_NAMES
                ),
                previous_volumes,
            )
            self.assertIs(document.getObject("SourcePanel"), source_object)
        finally:
            FreeCAD.closeDocument(document_name)

    def test_split_command_module_uses_local_workbench_imports(self):
        """The UI command is importable without a conflicting package name."""
        from Commands.SplitPanelCommand import PanelOptimizerSplitPanelCommand

        resources = PanelOptimizerSplitPanelCommand().GetResources()
        self.assertEqual(resources["MenuText"], "Split Panel")


if __name__ == "__main__":
    unittest.main()

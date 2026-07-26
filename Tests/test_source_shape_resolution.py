# -*- coding: utf-8 -*-
"""FreeCAD regressions for conservative source-solid resolution."""

from __future__ import annotations

import unittest
from dataclasses import fields, is_dataclass
from types import SimpleNamespace
from unittest.mock import patch

try:
    import Part
    from FreeCAD import Vector
except ImportError:  # pragma: no cover - exercised outside FreeCAD
    Part = None
    Vector = None

from Core.AnalyzerEngine import AnalyzerEngine
from Core.Exceptions import InvalidShapeError, SplitSourceError
from Core.GeometryEngine import GeometryEngine
from Core.SourceShapeResolver import (
    diagnose_source_shape,
    resolve_source_shape,
)
from Core.SplitterEngine import SplitterEngine
from Core.SplitWorkflow import resolve_selected_shape


class _Container:
    """Minimal read-only proxy for a FreeCAD container-shape boundary."""

    ShapeType = "Compound"
    Shells = ()
    CompSolids = ()

    def __init__(self, solids, *, valid=False, null=False):
        self.Solids = tuple(solids)
        self._valid = valid
        self._null = null

    def isNull(self):
        return self._null

    def isValid(self):
        return self._valid

    def isClosed(self):
        return False

    def check(self):
        if not self._valid:
            raise RuntimeError("Invalid top-level container")

    def __getattr__(self, name):
        if len(self.Solids) == 1:
            return getattr(self.Solids[0], name)
        raise AttributeError(name)


class _InvalidSolid:
    """Contained-solid validity proxy used before geometry is accessed."""

    ShapeType = "Solid"

    @staticmethod
    def isNull():
        return False

    @staticmethod
    def isValid():
        return False


@unittest.skipIf(Part is None, "FreeCAD Part module is unavailable")
class SourceShapeResolutionTests(unittest.TestCase):
    """Apply the same source policy to measurement and splitting."""

    @staticmethod
    def _assert_model_has_no_freecad_values(value):
        if is_dataclass(value):
            if value.__class__.__module__.startswith("Core.Models"):
                for model_field in fields(value):
                    SourceShapeResolutionTests._assert_model_has_no_freecad_values(
                        getattr(value, model_field.name)
                    )
                return
        if isinstance(value, tuple):
            for item in value:
                SourceShapeResolutionTests._assert_model_has_no_freecad_values(item)
            return
        if value.__class__.__module__.startswith("Core.Models"):
            return
        if not isinstance(value, (str, int, float, bool, type(None))):
            raise AssertionError(type(value).__name__)

    def test_valid_top_level_solid_is_accepted_directly(self):
        solid = Part.makeBox(20, 20, 5)

        resolution = resolve_source_shape(solid)

        self.assertIs(resolution.shape, solid)
        self.assertFalse(resolution.used_contained_solid)
        self.assertEqual(resolution.messages, ())

    def test_invalid_container_with_one_valid_solid_is_accepted(self):
        solid = Part.makeBox(20, 20, 5)
        wrapper = _Container((solid,))

        resolution = resolve_source_shape(wrapper)
        snapshot = GeometryEngine().create_snapshot(wrapper, "wrapped", "Wrapped")
        split = SplitterEngine().split_four_quadrants(wrapper, "wrapped")

        self.assertIs(resolution.shape, solid)
        self.assertTrue(resolution.used_contained_solid)
        self.assertEqual(
            resolution.messages,
            ("Top-level shape invalid; using one valid contained solid.",),
        )
        self.assertEqual(snapshot.shape_type, "Solid")
        self.assertEqual(snapshot.solid_count, 1)
        self.assertEqual(snapshot.validation_messages, resolution.messages)
        self.assertEqual(len(split.shapes), 4)

    def test_invalid_container_with_no_solid_is_rejected(self):
        with self.assertRaisesRegex(InvalidShapeError, "no valid solid"):
            resolve_source_shape(_Container(()))

    def test_container_with_multiple_valid_solids_is_rejected(self):
        wrapper = _Container(
            (
                Part.makeBox(5, 5, 5),
                Part.makeBox(5, 5, 5, Vector(10, 0, 0)),
            )
        )

        with self.assertRaisesRegex(InvalidShapeError, "multiple valid solids"):
            resolve_source_shape(wrapper)
        with self.assertRaisesRegex(SplitSourceError, "multiple valid solids"):
            SplitterEngine().split_four_quadrants(wrapper, "multiple")

    def test_invalid_contained_solid_is_rejected(self):
        wrapper = _Container((_InvalidSolid(),))

        with self.assertRaisesRegex(InvalidShapeError, "invalid solid"):
            resolve_source_shape(wrapper)

    def test_analyze_and_split_resolve_the_identical_solid(self):
        solid = Part.makeBox(20, 20, 5)
        wrapper = _Container((solid,))
        selected = SimpleNamespace(Shape=wrapper)

        analyze_resolution = resolve_source_shape(wrapper)
        split_resolution = resolve_selected_shape(selected)
        snapshot = GeometryEngine().create_snapshot(
            analyze_resolution.shape,
            "same-policy",
            "Same policy",
            validation_messages=analyze_resolution.messages,
        )
        report = AnalyzerEngine(
            lambda source_id: analyze_resolution.shape
        ).analyze(snapshot)

        self.assertIs(analyze_resolution.shape, split_resolution.shape)
        self.assertEqual(analyze_resolution.messages, split_resolution.messages)
        self.assertEqual(report.geometry.validation_messages, analyze_resolution.messages)

    def test_resolution_and_analysis_leave_source_unchanged(self):
        solid = Part.makeBox(20, 20, 5).cut(Part.makeCylinder(2, 5, Vector(10, 10, 0)))
        wrapper = _Container((solid,))
        before = (
            solid.Volume,
            solid.Area,
            len(solid.Faces),
            len(solid.Edges),
            solid.BoundBox.XMin,
            solid.BoundBox.XMax,
        )

        resolution = resolve_source_shape(wrapper)
        snapshot = GeometryEngine().create_snapshot(wrapper, "unchanged", "Unchanged")
        report = AnalyzerEngine(lambda source_id: resolution.shape).analyze(snapshot)

        after = (
            solid.Volume,
            solid.Area,
            len(solid.Faces),
            len(solid.Edges),
            solid.BoundBox.XMin,
            solid.BoundBox.XMax,
        )
        self.assertEqual(after, before)
        self.assertIs(wrapper.Solids[0], solid)
        self._assert_model_has_no_freecad_values(report)

    def test_diagnostic_reports_container_and_solid_validity(self):
        solid = Part.makeBox(2, 3, 4)
        wrapper = _Container((solid,))

        diagnostic = diagnose_source_shape(wrapper)

        self.assertEqual(diagnostic.shape_type, "Compound")
        self.assertEqual(diagnostic.solid_count, 1)
        self.assertEqual(diagnostic.shell_count, 0)
        self.assertEqual(diagnostic.compsolid_count, 0)
        self.assertFalse(diagnostic.is_null)
        self.assertFalse(diagnostic.is_valid)
        self.assertFalse(diagnostic.is_closed)
        self.assertEqual(diagnostic.check_status, "failed")
        self.assertIn("Invalid top-level container", diagnostic.check_message)
        self.assertEqual(diagnostic.solids[0].shape_type, "Solid")
        self.assertFalse(diagnostic.solids[0].is_null)
        self.assertTrue(diagnostic.solids[0].is_valid)

    def test_analyze_command_reports_contained_solid_extraction(self):
        import Commands.AnalyzeCommand as analyze_module

        solid = Part.makeBox(20, 20, 5)
        wrapper = _Container((solid,))
        selected = SimpleNamespace(
            Name="WrappedPanel",
            Label="Wrapped panel",
            Shape=wrapper,
        )
        messages = []
        warnings = []
        freecad_stub = SimpleNamespace(
            ActiveDocument=object(),
            Console=SimpleNamespace(
                PrintMessage=messages.append,
                PrintWarning=warnings.append,
                PrintError=warnings.append,
            ),
        )
        freecad_gui_stub = SimpleNamespace(
            Selection=SimpleNamespace(getSelection=lambda: (selected,)),
        )

        with patch.object(analyze_module, "FreeCAD", freecad_stub), patch.object(
            analyze_module,
            "FreeCADGui",
            freecad_gui_stub,
        ):
            analyze_module.PanelOptimizerAnalyzeCommand().Activated()

        self.assertEqual(warnings, [])
        self.assertIn(
            "PanelOptimizer: Top-level shape invalid; using one valid "
            "contained solid.\n",
            messages,
        )


if __name__ == "__main__":
    unittest.main()

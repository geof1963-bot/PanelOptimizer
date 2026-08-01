# -*- coding: utf-8 -*-
"""FreeCAD regressions for conservative source-solid resolution."""

from __future__ import annotations

import unittest
from dataclasses import fields, is_dataclass
from types import SimpleNamespace
from unittest.mock import patch

try:
    import FreeCAD
    import Part
    from FreeCAD import Vector
except ImportError:  # pragma: no cover - exercised outside FreeCAD
    FreeCAD = None
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


class _RepairTrapSolid:
    """Invalid solid proxy that records every forbidden repair operation."""

    ShapeType = "Solid"

    def __init__(self, shape):
        self._shape = shape
        self.Solids = (self,)
        self.calls = {
            "copy": 0,
            "fix": 0,
            "fixTolerance": 0,
            "removeSplitter": 0,
            "check": 0,
        }

    def isNull(self):
        return False

    def isValid(self):
        return False

    def isClosed(self):
        return bool(self._shape.isClosed())

    def copy(self):
        self.calls["copy"] += 1
        raise AssertionError("copy must not be called for automatic repair")

    def fix(self, *args):
        self.calls["fix"] += 1
        raise AssertionError("fix must not be called")

    def fixTolerance(self, *args):
        self.calls["fixTolerance"] += 1
        raise AssertionError("fixTolerance must not be called")

    def removeSplitter(self):
        self.calls["removeSplitter"] += 1
        raise AssertionError("removeSplitter must not be called")

    def check(self, *args):
        self.calls["check"] += 1
        raise AssertionError("check must not be called on invalid geometry")

    def __getattr__(self, name):
        return getattr(self._shape, name)


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

    @staticmethod
    def _invalid_inner_shell(radius):
        """Create a closed invalid solid with a misoriented inner shell."""
        outer = Part.makeBox(100, 100, 8)
        inner = Part.makeSphere(radius, Vector(50, 50, 4))
        return Part.makeSolid(
            Part.makeCompound(
                (outer.OuterShell.copy(), inner.OuterShell.copy())
            )
        )

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

        with self.assertRaisesRegex(InvalidShapeError, r"2 solids \(2 valid\)"):
            resolve_source_shape(wrapper)
        with self.assertRaisesRegex(SplitSourceError, r"2 solids \(2 valid\)"):
            SplitterEngine().split_four_quadrants(wrapper, "multiple")

    def test_invalid_contained_solid_is_rejected(self):
        wrapper = _Container((_InvalidSolid(),))

        with self.assertRaisesRegex(
            InvalidShapeError,
            "Automatic repair is disabled for safety",
        ):
            resolve_source_shape(wrapper)

    def test_invalid_solid_never_invokes_repair_or_detailed_check(self):
        trapped = _RepairTrapSolid(self._invalid_inner_shell(0.02))

        with self.assertRaisesRegex(
            InvalidShapeError,
            "Source solid is invalid",
        ) as context:
            resolve_source_shape(_Container((trapped,)))

        self.assertEqual(
            trapped.calls,
            {
                "copy": 0,
                "fix": 0,
                "fixTolerance": 0,
                "removeSplitter": 0,
                "check": 0,
            },
        )
        message = str(context.exception)
        self.assertIn("shape type=Solid", message)
        self.assertIn("valid=False", message)
        self.assertIn("closed=True", message)
        self.assertIn("solid count=1", message)
        self.assertIn("shell count=2", message)
        self.assertIn("volume=", message)
        self.assertIn("bounding box=", message)
        self.assertIn("B-rep check=skipped_for_safety", message)

    def test_real_invalid_solid_fails_without_source_change(self):
        invalid = self._invalid_inner_shell(0.02)
        before_brep = invalid.exportBrepToString()

        with self.assertRaisesRegex(
            InvalidShapeError,
            "Automatic repair is disabled for safety",
        ):
            resolve_source_shape(_Container((invalid,)))

        self.assertFalse(invalid.isValid())
        self.assertEqual(invalid.exportBrepToString(), before_brep)

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
        self.assertEqual(diagnostic.check_status, "skipped_for_safety")
        self.assertIn("disabled", diagnostic.check_message)
        self.assertEqual(diagnostic.solids[0].shape_type, "Solid")
        self.assertFalse(diagnostic.solids[0].is_null)
        self.assertTrue(diagnostic.solids[0].is_valid)
        self.assertTrue(diagnostic.solids[0].is_closed)
        self.assertEqual(diagnostic.solids[0].shell_count, 1)
        self.assertIsNone(diagnostic.solids[0].problematic_subshape_count)
        self.assertAlmostEqual(diagnostic.solids[0].volume_mm3, solid.Volume)
        self.assertIsNone(diagnostic.solids[0].area_mm2)
        self.assertIsNotNone(diagnostic.solids[0].bounding_box_mm)
        self.assertIsNone(diagnostic.solids[0].center_of_mass_mm)

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

    def test_analyze_command_fails_cleanly_without_automatic_repair(self):
        import Commands.AnalyzeCommand as analyze_module

        invalid = self._invalid_inner_shell(0.02)
        before_brep = invalid.exportBrepToString()
        selected = SimpleNamespace(
            Name="RepairablePanel",
            Label="Repairable panel",
            Shape=_Container((invalid,)),
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

        self.assertEqual(messages[-1], "\n")
        self.assertTrue(
            any("PanelOptimizer: Source solid is invalid." in item for item in warnings)
        )
        self.assertTrue(
            any("Automatic repair is disabled for safety." in item for item in warnings)
        )
        self.assertEqual(invalid.exportBrepToString(), before_brep)

    def test_macro_split_command_bypasses_deep_validation_without_source_mutation(self):
        import Commands.SplitPanelCommand as split_module

        document_name = "PanelOptimizerTransientRepairSplit"
        document = FreeCAD.newDocument(document_name)
        try:
            source = document.addObject("Part::Feature", "RepairableSource")
            source.Label = "Repairable source"
            source.Shape = self._invalid_inner_shell(0.02)
            original_shape = source.Shape
            before_brep = original_shape.exportBrepToString()
            before_geometry = (
                original_shape.isNull(),
                original_shape.isValid(),
                original_shape.isClosed(),
                len(original_shape.Solids),
                len(original_shape.Shells),
                len(original_shape.Faces),
                len(original_shape.Edges),
                len(original_shape.Vertexes),
                original_shape.Volume,
                original_shape.Area,
                original_shape.BoundBox.XMin,
                original_shape.BoundBox.YMin,
                original_shape.BoundBox.ZMin,
                original_shape.BoundBox.XMax,
                original_shape.BoundBox.YMax,
                original_shape.BoundBox.ZMax,
                original_shape.CenterOfMass.x,
                original_shape.CenterOfMass.y,
                original_shape.CenterOfMass.z,
            )
            before_label = source.Label
            before_properties = tuple(source.PropertiesList)
            messages = []
            warnings = []
            errors = []
            freecad_stub = SimpleNamespace(
                ActiveDocument=document,
                Console=SimpleNamespace(
                    PrintMessage=messages.append,
                    PrintWarning=warnings.append,
                    PrintError=errors.append,
                ),
            )
            freecad_gui_stub = SimpleNamespace(
                Selection=SimpleNamespace(getSelection=lambda: (source,)),
            )

            with patch.object(split_module, "FreeCAD", freecad_stub), patch.object(
                split_module,
                "FreeCADGui",
                freecad_gui_stub,
            ):
                split_module.PanelOptimizerSplitPanelCommand().Activated()

            self.assertTrue(errors)
            self.assertFalse(
                any("Automatic repair is disabled" in item for item in errors)
            )
            self.assertEqual(
                messages, ["PanelOptimizer Split Pipeline V7.10\n"]
            )
            self.assertEqual(warnings, [])
            after_shape = source.Shape
            after_geometry = (
                after_shape.isNull(),
                after_shape.isValid(),
                after_shape.isClosed(),
                len(after_shape.Solids),
                len(after_shape.Shells),
                len(after_shape.Faces),
                len(after_shape.Edges),
                len(after_shape.Vertexes),
                after_shape.Volume,
                after_shape.Area,
                after_shape.BoundBox.XMin,
                after_shape.BoundBox.YMin,
                after_shape.BoundBox.ZMin,
                after_shape.BoundBox.XMax,
                after_shape.BoundBox.YMax,
                after_shape.BoundBox.ZMax,
                after_shape.CenterOfMass.x,
                after_shape.CenterOfMass.y,
                after_shape.CenterOfMass.z,
            )
            self.assertEqual(after_geometry, before_geometry)
            self.assertEqual(original_shape.exportBrepToString(), before_brep)
            self.assertFalse(after_shape.isValid())
            self.assertEqual(source.Label, before_label)
            self.assertEqual(tuple(source.PropertiesList), before_properties)
            self.assertIsNone(document.getObject("PanelOptimizer_Result"))
        finally:
            FreeCAD.closeDocument(document_name)


if __name__ == "__main__":
    unittest.main()

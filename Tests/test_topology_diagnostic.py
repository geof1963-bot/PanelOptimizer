# -*- coding: utf-8 -*-
"""FreeCAD tests for explicit crash-conscious topology diagnostics."""

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

from Core.TopologyDiagnostic import (
    format_topology_diagnostic,
    inspect_topology,
)


class _RepairTrap:
    """Delegate scalar topology while trapping every forbidden operation."""

    def __init__(self, shape):
        self._shape = shape
        self.calls = {
            "fix": 0,
            "fixTolerance": 0,
            "removeSplitter": 0,
            "check": 0,
        }

    def fix(self, *args):
        self.calls["fix"] += 1
        raise AssertionError("fix must not run")

    def fixTolerance(self, *args):
        self.calls["fixTolerance"] += 1
        raise AssertionError("fixTolerance must not run")

    def removeSplitter(self):
        self.calls["removeSplitter"] += 1
        raise AssertionError("removeSplitter must not run")

    def check(self, *args):
        self.calls["check"] += 1
        raise AssertionError("full-shape check must not run")

    def __getattr__(self, name):
        return getattr(self._shape, name)


@unittest.skipIf(Part is None, "FreeCAD Part module is unavailable")
class TopologyDiagnosticTests(unittest.TestCase):
    """Localize suspicious subshapes without changing source geometry."""

    @staticmethod
    def _open_solid():
        box = Part.makeBox(10, 10, 5)
        return Part.makeSolid(
            Part.makeShell(tuple(face.copy() for face in box.Faces[:-1]))
        )

    def test_valid_solid_has_no_invalid_or_suspicious_subshapes(self):
        report = inspect_topology(Part.makeBox(10, 10, 5))

        self.assertTrue(report.is_valid)
        self.assertTrue(report.is_closed)
        self.assertEqual(report.invalid_faces, 0)
        self.assertEqual(report.invalid_edges, 0)
        self.assertEqual(report.degenerate_edges, 0)
        self.assertEqual(report.invalid_vertices, 0)
        self.assertEqual(report.suspicious_total, 0)
        self.assertEqual(report.suspicious_elements, ())
        self.assertEqual(report.bopcheck_status, "disabled_for_safety")

    def test_malformed_open_solid_localizes_boundary_edges(self):
        shape = self._open_solid()

        report = inspect_topology(shape)

        self.assertFalse(report.is_valid)
        self.assertFalse(report.is_closed)
        self.assertGreater(report.suspicious_total, 0)
        boundary_edges = tuple(
            item
            for item in report.suspicious_elements
            if "face_incidence_1" in item.reasons
        )
        self.assertTrue(boundary_edges)
        self.assertTrue(all(item.element_id.startswith("Edge") for item in boundary_edges))
        self.assertTrue(all(item.related_element_ids for item in boundary_edges))

    def test_diagnostic_is_deterministic_and_limits_default_output(self):
        shape = self._open_solid()

        first = inspect_topology(shape, suspicious_limit=2)
        second = inspect_topology(shape, suspicious_limit=2)

        self.assertEqual(first, second)
        self.assertEqual(len(first.suspicious_elements), 2)
        self.assertGreater(first.suspicious_total, 2)
        self.assertEqual(
            tuple(item.element_id for item in first.suspicious_elements),
            tuple(sorted(
                (item.element_id for item in first.suspicious_elements),
                key=lambda value: (value.rstrip("0123456789"), int(value.lstrip("EdgeFaceVertex"))),
            )),
        )

    def test_source_remains_unchanged_and_no_unsafe_api_runs(self):
        shape = self._open_solid()
        before = shape.exportBrepToString()
        trapped = _RepairTrap(shape)

        report = inspect_topology(trapped)

        self.assertFalse(report.is_valid)
        self.assertEqual(shape.exportBrepToString(), before)
        self.assertEqual(
            trapped.calls,
            {
                "fix": 0,
                "fixTolerance": 0,
                "removeSplitter": 0,
                "check": 0,
            },
        )

    def test_console_format_is_bounded_and_contains_required_totals(self):
        report = inspect_topology(self._open_solid(), suspicious_limit=2)

        output = format_topology_diagnostic(report)

        self.assertIn("PanelOptimizer Geometry Diagnostic", output)
        self.assertIn("Solid valid: False", output)
        self.assertIn("Closed: False", output)
        self.assertIn("Invalid faces:", output)
        self.assertIn("Invalid edges:", output)
        self.assertIn("Degenerate edges:", output)
        self.assertIn("Suspicious regions:", output)
        self.assertIn("BOPCheck: disabled_for_safety", output)
        self.assertEqual(output.count("\n- "), 2)

    def test_diagnostic_command_prints_one_bounded_report(self):
        import Commands.GeometryDiagnosticCommand as command_module

        selected = SimpleNamespace(Shape=self._open_solid())
        messages = []
        errors = []
        freecad_stub = SimpleNamespace(
            ActiveDocument=object(),
            Console=SimpleNamespace(
                PrintMessage=messages.append,
                PrintError=errors.append,
            ),
        )
        gui_stub = SimpleNamespace(
            Selection=SimpleNamespace(getSelection=lambda: (selected,)),
        )

        with patch.object(command_module, "FreeCAD", freecad_stub), patch.object(
            command_module,
            "FreeCADGui",
            gui_stub,
        ):
            command_module.PanelOptimizerGeometryDiagnosticCommand().Activated()

        self.assertEqual(errors, [])
        self.assertEqual(len(messages), 1)
        self.assertIn("PanelOptimizer Geometry Diagnostic", messages[0])
        self.assertLessEqual(messages[0].count("\n- "), 20)

    def test_diagnostic_command_appends_invalid_planar_face_detail(self):
        import Commands.GeometryDiagnosticCommand as command_module

        points = (
            (0, 0, 1.4),
            (10, 10, 1.4),
            (0, 10, 1.4),
            (10, 0, 1.4),
            (0, 0, 1.4),
        )
        wire = Part.makePolygon([Vector(*point) for point in points])
        selected = SimpleNamespace(Shape=Part.makeCompound((Part.Face(wire),)))
        messages = []
        freecad_stub = SimpleNamespace(
            ActiveDocument=object(),
            Console=SimpleNamespace(
                PrintMessage=messages.append,
                PrintError=lambda message: self.fail(message),
            ),
        )
        gui_stub = SimpleNamespace(
            Selection=SimpleNamespace(getSelection=lambda: (selected,)),
        )

        with patch.object(command_module, "FreeCAD", freecad_stub), patch.object(
            command_module, "FreeCADGui", gui_stub
        ):
            command_module.PanelOptimizerGeometryDiagnosticCommand().Activated()

        self.assertEqual(len(messages), 1)
        self.assertIn("Invalid planar-face detail: 1 total; showing 1.", messages[0])
        self.assertIn("self_intersecting_wire", messages[0])


if __name__ == "__main__":
    unittest.main()

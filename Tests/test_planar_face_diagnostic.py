# -*- coding: utf-8 -*-
"""FreeCAD regressions for focused invalid planar-face diagnostics."""

from __future__ import annotations

import unittest

try:
    import Part
    from FreeCAD import Vector
except ImportError:  # pragma: no cover - exercised outside FreeCAD
    Part = None
    Vector = None

from Core.PlanarFaceDiagnostic import (
    format_invalid_planar_face_diagnostic,
    inspect_invalid_planar_faces,
)


class _RepairTrap:
    """Delegate read-only topology and fail on every prohibited operation."""

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
class PlanarFaceDiagnosticTests(unittest.TestCase):
    """Inspect invalid planar topology using scalar read-only evidence."""

    @staticmethod
    def _wire(points):
        return Part.makePolygon([Vector(*point) for point in points])

    @classmethod
    def _self_crossing_face(cls, x_offset=0.0):
        wire = cls._wire(
            (
                (x_offset + 0, 0, 1.4),
                (x_offset + 10, 10, 1.4),
                (x_offset + 0, 10, 1.4),
                (x_offset + 10, 0, 1.4),
                (x_offset + 0, 0, 1.4),
            )
        )
        return Part.Face(wire)

    @classmethod
    def _touching_inner_loop_face(cls):
        outer = cls._wire(
            ((0, 0, 1.4), (10, 0, 1.4), (10, 10, 1.4),
             (0, 10, 1.4), (0, 0, 1.4))
        )
        inner = cls._wire(
            ((0, 4, 1.4), (4, 4, 1.4), (4, 6, 1.4),
             (0, 6, 1.4), (0, 4, 1.4))
        )
        return Part.Face([outer, inner])

    def test_self_crossing_planar_wire_is_localized_exactly(self):
        face = self._self_crossing_face()
        self.assertFalse(face.isValid())

        report = inspect_invalid_planar_faces(Part.makeCompound((face,)))

        self.assertEqual(report.invalid_face_total, 1)
        self.assertEqual(report.inspected_face_ids, ("Face1",))
        detail = report.faces[0]
        self.assertEqual(detail.surface_type, "Plane")
        self.assertAlmostEqual(detail.plane_origin_mm[2], 1.4)
        self.assertEqual(detail.wire_count, 1)
        self.assertEqual(detail.outer_wire_edge_count, 4)
        self.assertEqual(detail.inner_wire_count, 0)
        self.assertEqual(detail.edge_count, 4)
        self.assertEqual(detail.vertex_count, 4)
        self.assertTrue(detail.wires[0].is_closed)
        self.assertTrue(detail.wires[0].is_valid)
        issue_types = tuple(
            item.issue_type for item in detail.wires[0].planar_issues
        )
        self.assertIn("self_intersecting_wire", issue_types)
        self.assertIn("near_zero_area_loop", issue_types)
        crossing = next(
            item
            for item in detail.wires[0].planar_issues
            if item.issue_type == "self_intersecting_wire"
        )
        self.assertEqual(crossing.point_xy_mm, (5.0, 5.0))

    def test_touching_inner_loop_is_face_level_defect(self):
        face = self._touching_inner_loop_face()
        self.assertFalse(face.isValid())

        detail = inspect_invalid_planar_faces(
            Part.makeCompound((face,))
        ).faces[0]

        self.assertEqual(detail.wire_count, 2)
        self.assertEqual(detail.inner_wire_count, 1)
        self.assertTrue(all(wire.is_valid for wire in detail.wires))
        issue_types = tuple(item.issue_type for item in detail.planar_issues)
        self.assertIn("inner_wire_touches_outer_wire", issue_types)
        self.assertIn("nested_loop_has_contradictory_orientation", issue_types)
        touching = next(
            item
            for item in detail.planar_issues
            if item.issue_type == "inner_wire_touches_outer_wire"
        )
        self.assertEqual(touching.point_xy_mm, (0.0, 4.0))

    def test_edge_geometry_leaving_explicit_face_plane_is_reported(self):
        wire = self._wire(
            ((0, 0, 1.4), (10, 0, 1.41), (10, 10, 1.4),
             (0, 10, 1.4), (0, 0, 1.4))
        )
        face = Part.Face(Part.Plane(Vector(0, 0, 1.4), Vector(0, 0, 1)), wire)
        self.assertFalse(face.isValid())

        detail = inspect_invalid_planar_faces(
            Part.makeCompound((face,))
        ).faces[0]

        issues = tuple(
            issue
            for wire_detail in detail.wires
            for issue in wire_detail.continuity_issues
            if issue.issue_type == "edge_geometry_leaves_face_plane"
        )
        self.assertTrue(issues)
        self.assertAlmostEqual(max(issue.distance_mm for issue in issues), 0.01)
        self.assertIn("edge_geometry_leaves_face_plane", detail.findings)

    def test_valid_planar_face_produces_no_invalid_detail(self):
        wire = self._wire(
            ((0, 0, 1.4), (10, 0, 1.4), (10, 10, 1.4),
             (0, 10, 1.4), (0, 0, 1.4))
        )
        face = Part.Face(wire)
        self.assertTrue(face.isValid())

        report = inspect_invalid_planar_faces(Part.makeCompound((face,)))

        self.assertEqual(report.invalid_face_total, 0)
        self.assertEqual(report.inspected_face_ids, ())
        self.assertEqual(report.faces, ())

    def test_default_output_is_limited_to_seven_faces(self):
        faces = tuple(self._self_crossing_face(index * 20.0) for index in range(8))

        report = inspect_invalid_planar_faces(Part.makeCompound(faces))

        self.assertEqual(report.invalid_face_total, 8)
        self.assertEqual(len(report.faces), 7)
        self.assertEqual(
            report.inspected_face_ids,
            tuple(f"Face{index}" for index in range(1, 8)),
        )

    def test_diagnostic_is_deterministic_and_formatted_with_wire_evidence(self):
        shape = Part.makeCompound(
            (self._self_crossing_face(), self._touching_inner_loop_face())
        )

        first = inspect_invalid_planar_faces(shape)
        second = inspect_invalid_planar_faces(shape)

        self.assertEqual(first, second)
        output = format_invalid_planar_face_diagnostic(first)
        self.assertIn("Invalid planar-face detail: 2 total; showing 2.", output)
        self.assertIn("Wire1:", output)
        self.assertIn("self_intersecting_wire", output)
        self.assertIn("inner_wire_touches_outer_wire", output)

    def test_source_is_unchanged_and_no_repair_or_full_check_runs(self):
        shape = Part.makeCompound((self._self_crossing_face(),))
        before = shape.exportBrepToString()
        trapped = _RepairTrap(shape)

        report = inspect_invalid_planar_faces(trapped)

        self.assertEqual(report.invalid_face_total, 1)
        self.assertEqual(shape.exportBrepToString(), before)
        self.assertEqual(
            trapped.calls,
            {"fix": 0, "fixTolerance": 0, "removeSplitter": 0, "check": 0},
        )


if __name__ == "__main__":
    unittest.main()

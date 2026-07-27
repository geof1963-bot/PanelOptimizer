# -*- coding: utf-8 -*-
"""FreeCAD tests for the one supported transient reconstruction family."""

from __future__ import annotations

import unittest

try:
    import Part
    from FreeCAD import Vector
except ImportError:  # pragma: no cover - exercised outside FreeCAD
    Part = None
    Vector = None

from Core.AnalyzerEngine import AnalyzerEngine
from Core.GeometryEngine import GeometryEngine
from Core.SourceShapeResolver import resolve_source_shape
from Core.SplitterEngine import SplitterEngine
from Core.TargetedPlanarReconstruction import (
    attempt_targeted_planar_reconstruction,
)


class _InvalidSolidProxy:
    """One closed invalid solid boundary assembled from real Part topology."""

    ShapeType = "Solid"

    def __init__(self, faces, edges, vertices, equivalent_shape):
        self.Faces = tuple(faces)
        self.Edges = tuple(edges)
        self.Vertexes = tuple(vertices)
        self.Shells = (object(),)
        self.Solids = (self,)
        self.BoundBox = equivalent_shape.BoundBox
        self.CenterOfMass = equivalent_shape.CenterOfMass
        self.Volume = equivalent_shape.Volume
        self._equivalent_shape = equivalent_shape
        self._invalid_face_index = next(
            index for index, face in enumerate(self.Faces) if not face.isValid()
        )
        self._brep = equivalent_shape.exportBrepToString()
        self.calls = {
            "copy": 0,
            "fix": 0,
            "fixTolerance": 0,
            "removeSplitter": 0,
            "check": 0,
        }

    @staticmethod
    def isNull():
        return False

    @staticmethod
    def isValid():
        return False

    @staticmethod
    def isClosed():
        return True

    def exportBrepToString(self):
        return self._brep

    def copy(self):
        self.calls["copy"] += 1
        equivalent = self._equivalent_shape.copy()
        faces = list(equivalent.Faces)
        faces[self._invalid_face_index] = _InvalidFaceProxy(
            faces[self._invalid_face_index]
        )
        return _InvalidSolidProxy(
            faces,
            equivalent.Edges,
            equivalent.Vertexes,
            equivalent,
        )

    def fix(self, *args):
        self.calls["fix"] += 1
        raise AssertionError("fix must not run")

    def fixTolerance(self, *args):
        self.calls["fixTolerance"] += 1
        raise AssertionError("fixTolerance must not run")

    def removeSplitter(self):
        self.calls["removeSplitter"] += 1
        raise AssertionError("removeSplitter must not run during reconstruction")

    def check(self, *args):
        self.calls["check"] += 1
        raise AssertionError("full-shape check must not run")


class _InvalidFaceProxy:
    """Expose one real planar face as the known invalid-face defect."""

    ShapeType = "Face"

    def __init__(self, face):
        self._face = face

    @staticmethod
    def isValid():
        return False

    def __getattr__(self, name):
        return getattr(self._face, name)


@unittest.skipIf(Part is None, "FreeCAD Part module is unavailable")
class TargetedPlanarReconstructionTests(unittest.TestCase):
    """Reconstruct only valid closed wires departing from one fixed plane."""

    @staticmethod
    def _unique(items):
        result = []
        for item in items:
            if not any(item.isSame(existing) for existing in result):
                result.append(item)
        return tuple(result)

    @classmethod
    def _supported_source(cls):
        height = 80.0
        bottom_points = (
            Vector(0, 0, 0),
            Vector(20, 0, 0),
            Vector(20, 20, 0),
            Vector(0, 20, 0),
        )
        top_points = (
            Vector(0, 0, height),
            Vector(20, 0, height + 0.00000011),
            Vector(20, 20, height),
            Vector(0, 20, height - 0.00000011),
        )
        bottom_edges = tuple(
            Part.makeLine(bottom_points[index], bottom_points[(index + 1) % 4])
            for index in range(4)
        )
        top_edges = tuple(
            Part.makeLine(top_points[index], top_points[(index + 1) % 4])
            for index in range(4)
        )
        vertical_edges = tuple(
            Part.makeLine(bottom_points[index], top_points[index])
            for index in range(4)
        )
        bottom_face = Part.Face(Part.Wire(bottom_edges))
        side_faces = tuple(
            Part.Face(
                Part.Wire(
                    (
                        bottom_edges[index],
                        vertical_edges[(index + 1) % 4],
                        top_edges[index],
                        vertical_edges[index],
                    )
                )
            )
            for index in range(4)
        )
        invalid_top = Part.Face(
            Part.Plane(Vector(0, 0, height), Vector(0, 0, 1)),
            Part.Wire(top_edges),
        )
        equivalent = Part.makeSolid(
            Part.makeShell((bottom_face, *side_faces, invalid_top))
        )
        if not equivalent.isValid():
            raise AssertionError("synthetic contextual solid must be valid")
        target = max(
            enumerate(equivalent.Faces),
            key=lambda item: item[1].CenterOfMass.z,
        )[0]
        contextual_faces = list(equivalent.Faces)
        contextual_faces[target] = _InvalidFaceProxy(contextual_faces[target])
        return _InvalidSolidProxy(
            contextual_faces,
            equivalent.Edges,
            equivalent.Vertexes,
            equivalent,
        )

    @staticmethod
    def _geometry(shape):
        box = shape.BoundBox
        center = shape.CenterOfMass
        return (
            shape.Volume,
            box.XMin,
            box.YMin,
            box.ZMin,
            box.XMax,
            box.YMax,
            box.ZMax,
            center.x,
            center.y,
            center.z,
        )

    def test_off_plane_planar_boundary_is_reconstructed(self):
        source = self._supported_source()

        outcome = attempt_targeted_planar_reconstruction(source)

        self.assertTrue(outcome.succeeded, outcome.reason)
        self.assertTrue(outcome.shape.isValid())
        self.assertTrue(outcome.shape.isClosed())
        self.assertEqual(len(outcome.shape.Solids), 1)
        self.assertEqual(sum(not face.isValid() for face in outcome.shape.Faces), 0)
        self.assertEqual(sum(not edge.isValid() for edge in outcome.shape.Edges), 0)
        self.assertEqual(
            sum(not vertex.isValid() for vertex in outcome.shape.Vertexes), 0
        )
        self.assertEqual(outcome.provenance.rebuilt_face_ids, ("Face6",))
        self.assertEqual(outcome.provenance.rebuilt_face_count, 1)
        self.assertAlmostEqual(
            outcome.provenance.maximum_geometric_displacement_mm,
            1.1e-7,
        )

    def test_valid_solid_is_returned_untouched(self):
        source = Part.makeBox(20, 20, 8)

        outcome = attempt_targeted_planar_reconstruction(source)

        self.assertEqual(outcome.status, "not_required")
        self.assertIs(outcome.shape, source)
        self.assertIsNone(outcome.provenance)

    def test_unrelated_invalid_closed_solid_is_refused(self):
        outer = Part.makeBox(20, 20, 8)
        inner = Part.makeSphere(0.02, Vector(10, 10, 4))
        source = Part.makeSolid(
            Part.makeCompound((outer.OuterShell, inner.OuterShell))
        )
        self.assertFalse(source.isValid())
        self.assertTrue(source.isClosed())

        outcome = attempt_targeted_planar_reconstruction(source)

        self.assertEqual(outcome.status, "ineligible")
        self.assertIsNone(outcome.shape)
        self.assertIsNotNone(outcome.reason)

    def test_bounds_center_volume_and_source_are_preserved(self):
        source = self._supported_source()
        before_brep = source.exportBrepToString()
        before = self._geometry(source)

        outcome = attempt_targeted_planar_reconstruction(source)

        self.assertTrue(outcome.succeeded, outcome.reason)
        after = self._geometry(outcome.shape)
        for original, reconstructed in zip(before, after):
            self.assertAlmostEqual(original, reconstructed, places=7)
        self.assertEqual(source.exportBrepToString(), before_brep)
        self.assertEqual(
            source.calls,
            {"copy": 1, "fix": 0, "fixTolerance": 0,
             "removeSplitter": 0, "check": 0},
        )

    def test_resolver_and_analyzer_use_transient_reconstruction(self):
        source = self._supported_source()

        resolution = resolve_source_shape(source)
        snapshot = GeometryEngine().create_snapshot(
            resolution.shape,
            "supported",
            "Supported",
            validation_messages=resolution.messages,
        )
        report = AnalyzerEngine(
            lambda source_id: resolution.shape
        ).analyze(snapshot)

        self.assertEqual(
            resolution.source_resolution,
            "targeted_planar_reconstruction",
        )
        self.assertEqual(
            resolution.messages,
            (
                "Source solid is invalid.",
                "Detected supported planar-boundary defect on 1 faces.",
                "Targeted transient reconstruction succeeded.",
                "Original source remains unchanged.",
            ),
        )
        self.assertTrue(report.geometry.is_valid)
        self.assertEqual(report.geometry.validation_messages, resolution.messages)

    def test_splitter_uses_transient_reconstruction_unchanged(self):
        source = self._supported_source()

        execution = SplitterEngine().split_four_quadrants(source, "supported")

        self.assertEqual(len(execution.shapes), 4)
        self.assertTrue(all(shape.isValid() for shape in execution.shapes))
        self.assertTrue(all(shape.isClosed() for shape in execution.shapes))

    def test_repeated_reconstruction_is_deterministic(self):
        source = self._supported_source()

        first = attempt_targeted_planar_reconstruction(source)
        second = attempt_targeted_planar_reconstruction(source)

        self.assertTrue(first.succeeded, first.reason)
        self.assertEqual(first.provenance, second.provenance)
        self.assertEqual(self._geometry(first.shape), self._geometry(second.shape))
        self.assertEqual(
            first.shape.exportBrepToString(),
            second.shape.exportBrepToString(),
        )


if __name__ == "__main__":
    unittest.main()

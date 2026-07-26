# -*- coding: utf-8 -*-
"""Topology-stage tests using real FreeCAD boundary representations."""

from __future__ import annotations

import unittest
from dataclasses import fields, is_dataclass

try:
    import Part
    from FreeCAD import Vector
except ImportError:  # pragma: no cover - exercised outside FreeCAD
    Part = None
    Vector = None

from Core.AnalyzerEngine import AnalyzerEngine
from Core.Exceptions import ShapeResolutionError, TopologyAnalysisError
from Core.GeometryEngine import GeometryEngine
from Core.Models import (
    ManufacturingAnalysis,
    SeamAnalysis,
)
from Core.Topology import HoleDetector


@unittest.skipIf(Part is None, "FreeCAD Part module is unavailable")
class AnalyzerEngineTopologyTests(unittest.TestCase):
    """Verify topology descriptions without creating a FreeCAD document."""

    @staticmethod
    def _snapshot(shape, source_id="panel"):
        return GeometryEngine().create_snapshot(
            shape,
            source_id,
            "Test panel",
        )

    def _assert_model_value_is_freecad_independent(self, value):
        """Recursively reject mutable collections and non-model objects."""
        if is_dataclass(value):
            self.assertTrue(
                value.__class__.__module__.startswith("Core.Models"),
                value.__class__.__module__,
            )
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
        self.assertIsInstance(
            value,
            (str, int, float, bool, type(None)),
            type(value).__name__,
        )

    def test_detects_through_and_blind_cylindrical_holes(self):
        """Cylindrical openings are described without evaluating them."""
        panel = Part.makeBox(30, 20, 5)
        through_tool = Part.makeCylinder(2, 5, Vector(8, 10, 0))
        blind_tool = Part.makeCylinder(3, 3, Vector(22, 10, 2))
        shape = panel.cut(through_tool.fuse(blind_tool))
        snapshot = self._snapshot(shape)

        report = AnalyzerEngine(lambda source_id: shape).analyze(snapshot)

        self.assertEqual(len(report.topology.holes), 2)
        self.assertEqual(
            {hole.is_through_hole for hole in report.topology.holes},
            {True, False},
        )
        self.assertEqual(len(report.topology.dead_ends), 1)
        self.assertTrue(report.geometric.material_ligaments)
        self.assertEqual(report.manufacturing.warnings, ())
        self.assertEqual(report.seam.safe_zones, ())

    def test_detects_enclosed_cavity_from_inner_shell(self):
        """A closed inner shell is emitted as a cavity with exact volume."""
        cavity_tool = Part.makeSphere(1, Vector(10, 10, 2.5))
        shape = Part.makeBox(20, 20, 5).cut(cavity_tool)
        snapshot = self._snapshot(shape)

        report = AnalyzerEngine(lambda source_id: shape).analyze(snapshot)

        self.assertEqual(len(report.topology.cavities), 1)
        self.assertAlmostEqual(
            report.topology.cavities[0].volume_mm3,
            4.0 * 3.141592653589793 / 3.0,
        )
        self.assertEqual(
            report.topology.cavities[0].opening_feature_ids,
            (),
        )

    def test_enclosed_cylinder_is_a_cavity_not_a_hole(self):
        """A cylindrical void without an opening is not called a hole."""
        cavity_tool = Part.makeCylinder(1, 2, Vector(10, 10, 1.5))
        shape = Part.makeBox(20, 20, 5).cut(cavity_tool)
        snapshot = self._snapshot(shape)

        report = AnalyzerEngine(lambda source_id: shape).analyze(snapshot)

        self.assertEqual(report.topology.holes, ())
        self.assertEqual(len(report.topology.cavities), 1)
        self.assertAlmostEqual(
            report.topology.cavities[0].volume_mm3,
            2.0 * 3.141592653589793,
        )

    def test_reports_every_disconnected_component_as_an_island(self):
        """Disconnected solids are all described without choosing a main one."""
        first = Part.makeBox(5, 5, 5)
        second = Part.makeBox(5, 5, 5, Vector(10, 0, 0))
        shape = Part.makeCompound((first, second))
        snapshot = self._snapshot(shape)

        report = AnalyzerEngine(lambda source_id: shape).analyze(snapshot)

        self.assertEqual(len(report.topology.islands), 2)
        graph = report.topology.connectivity_graph
        self.assertIsNotNone(graph)
        self.assertEqual(len(graph.nodes), 2)
        self.assertEqual(graph.edges, ())
        self.assertEqual(graph.connected_component_count, 2)

    def test_exterior_cylindrical_shell_is_not_a_hole(self):
        """An exterior cylinder remains exterior even when shell is reversed."""
        cylinder = Part.makeCylinder(5, 8)
        outer_face = next(
            face
            for face in cylinder.Faces
            if type(face.Surface).__name__ == "Cylinder"
        )
        shape = Part.makeShell((outer_face,))
        shape.reverse()
        snapshot = self._snapshot(shape)

        report = AnalyzerEngine(lambda source_id: shape).analyze(snapshot)

        self.assertEqual(report.topology.holes, ())
        self.assertEqual(report.topology.cavities, ())
        self.assertEqual(
            report.topology.connectivity_graph.nodes[0].node_type,
            "shell",
        )

    def test_reversing_hollow_solid_does_not_swap_hole_and_exterior(self):
        """Relative orientation identifies the same bore after solid reversal."""
        shape = Part.makeCylinder(5, 8).cut(Part.makeCylinder(2, 8))
        shape.reverse()
        snapshot = self._snapshot(shape)

        report = AnalyzerEngine(lambda source_id: shape).analyze(snapshot)

        self.assertEqual(len(report.topology.holes), 1)
        self.assertEqual(report.topology.holes[0].diameter_mm, 4.0)
        self.assertTrue(report.topology.holes[0].is_through_hole)

    def test_cylinder_opening_into_cavity_is_not_through_or_dead_end(self):
        """A cavity connection is neither a through segment nor a blind cap."""
        panel = Part.makeBox(30, 30, 8)
        cavity = Part.makeSphere(4, Vector(15, 15, 4))
        access = Part.makeCylinder(1, 4, Vector(15, 15, 4))
        shape = panel.cut(cavity.fuse(access))
        snapshot = self._snapshot(shape)

        report = AnalyzerEngine(lambda source_id: shape).analyze(snapshot)

        self.assertEqual(len(report.topology.holes), 1)
        self.assertFalse(report.topology.holes[0].is_through_hole)
        self.assertEqual(report.topology.dead_ends, ())

    def test_counterbore_and_stepped_holes_are_described_as_segments(self):
        """Each distinct coaxial cylinder is retained in topology order."""
        panel = Part.makeBox(30, 30, 8)
        cases = {
            "counterbore": (
                Part.makeCylinder(2, 8, Vector(15, 15, 0)).fuse(
                    Part.makeCylinder(4, 3, Vector(15, 15, 5))
                ),
                [(4.0, 5.0), (8.0, 3.0)],
            ),
            "stepped": (
                Part.makeCylinder(2, 3, Vector(15, 15, 0))
                .fuse(Part.makeCylinder(3, 2, Vector(15, 15, 3)))
                .fuse(Part.makeCylinder(1, 3, Vector(15, 15, 5))),
                [(2.0, 3.0), (4.0, 3.0), (6.0, 2.0)],
            ),
        }

        for source_id, (tool, expected_segments) in cases.items():
            with self.subTest(source_id=source_id):
                shape = panel.cut(tool)
                snapshot = self._snapshot(shape, source_id)
                analyzer = AnalyzerEngine(lambda resolved_id: shape)

                first_report = analyzer.analyze(snapshot)
                second_report = analyzer.analyze(snapshot)

                segments = sorted(
                    (hole.diameter_mm, hole.depth_mm)
                    for hole in first_report.topology.holes
                )
                self.assertEqual(segments, expected_segments)
                self.assertTrue(
                    all(
                        hole.is_through_hole
                        for hole in first_report.topology.holes
                    )
                )
                self.assertEqual(
                    first_report.topology,
                    second_report.topology,
                )

    def test_blind_counterbore_marks_every_connected_segment_non_through(self):
        """A cap makes the complete connected counterbore non-through."""
        panel = Part.makeBox(30, 30, 8)
        tool = Part.makeCylinder(2, 5, Vector(15, 15, 3)).fuse(
            Part.makeCylinder(4, 2, Vector(15, 15, 6))
        )
        shape = panel.cut(tool)
        snapshot = self._snapshot(shape)

        report = AnalyzerEngine(lambda source_id: shape).analyze(snapshot)

        self.assertEqual(len(report.topology.holes), 2)
        self.assertTrue(
            all(
                not hole.is_through_hole
                for hole in report.topology.holes
            )
        )
        self.assertEqual(len(report.topology.dead_ends), 1)

    def test_duplicate_circular_edges_and_seam_edge_do_not_add_endpoints(self):
        """Duplicate circles collapse by center and cylinder seams are ignored."""
        cylinder = Part.makeCylinder(2, 5)
        cylinder_face = next(
            face
            for face in cylinder.Faces
            if type(face.Surface).__name__ == "Cylinder"
        )
        circle_edges = tuple(
            edge
            for edge in cylinder_face.Edges
            if type(edge.Curve).__name__ == "Circle"
        )
        seam_edges = tuple(
            edge
            for edge in cylinder_face.Edges
            if type(edge.Curve).__name__ != "Circle"
        )
        detector = HoleDetector()

        centers = detector._distinct_circle_centers(
            circle_edges + circle_edges
        )

        self.assertEqual(len(centers), 2)
        self.assertTrue(seam_edges)
        self.assertTrue(
            all(
                not detector._is_closed_circle(edge)
                for edge in seam_edges
            )
        )

    def test_report_contains_only_immutable_model_values(self):
        """No resolved FreeCAD object crosses into the immutable report."""
        shape = Part.makeBox(20, 20, 5).cut(
            Part.makeCylinder(2, 5, Vector(10, 10, 0))
        )
        snapshot = self._snapshot(shape)

        report = AnalyzerEngine(lambda source_id: shape).analyze(snapshot)

        self._assert_model_value_is_freecad_independent(report)

    def test_partial_report_uses_exact_later_stage_defaults(self):
        """Implemented geometry is present while later stages stay default."""
        shape = Part.makeBox(5, 5, 5)
        snapshot = self._snapshot(shape)

        report = AnalyzerEngine(lambda source_id: shape).analyze(snapshot)

        self.assertTrue(report.geometric.thickness_observations)
        self.assertEqual(report.geometric.clearance_observations, ())
        self.assertEqual(report.geometric.material_ligaments, ())
        self.assertTrue(report.geometric.edge_observations)
        self.assertTrue(report.geometric.corner_observations)
        self.assertTrue(report.geometric.curvature_observations)
        self.assertTrue(report.geometric.flat_regions)
        self.assertEqual(report.geometric.symmetries, ())
        self.assertEqual(report.geometric.feature_proximities, ())
        self.assertEqual(report.geometric.complexity_indicators, ())
        self.assertEqual(report.manufacturing, ManufacturingAnalysis())
        self.assertEqual(report.seam, SeamAnalysis())

    def test_invalid_resolved_shell_raises_topology_error(self):
        """An invalid shell is rejected before topology inspection."""
        shape = Part.makeBox(5, 5, 5)
        snapshot = self._snapshot(shape)

        class InvalidShell:
            ShapeType = "Shell"

            @staticmethod
            def isNull():
                return False

            @staticmethod
            def isValid():
                return False

        with self.assertRaises(TopologyAnalysisError):
            AnalyzerEngine(lambda source_id: InvalidShell()).analyze(snapshot)

    def test_requires_a_shape_resolver(self):
        """Analysis fails explicitly when its read-only dependency is absent."""
        shape = Part.makeBox(5, 5, 5)
        snapshot = self._snapshot(shape)

        with self.assertRaises(ShapeResolutionError):
            AnalyzerEngine().analyze(snapshot)


if __name__ == "__main__":
    unittest.main()

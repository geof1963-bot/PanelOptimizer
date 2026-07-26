# -*- coding: utf-8 -*-
"""FreeCAD integration tests for exact symmetry and complexity counts."""

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
from Core.Models import ManufacturingAnalysis, SeamAnalysis
from Core.Topology import TopologyAnalyzer


@unittest.skipIf(Part is None, "FreeCAD Part module is unavailable")
class SymmetryAndComplexityIntegrationTests(unittest.TestCase):
    """Verify conservative symmetry evidence and unweighted counts."""

    @staticmethod
    def _analyze(shape, source_id="final-geometry"):
        snapshot = GeometryEngine().create_snapshot(
            shape,
            source_id,
            "Symmetry and complexity source",
        )
        return AnalyzerEngine(lambda resolved_id: shape).analyze(snapshot)

    @staticmethod
    def _centered_plate():
        return Part.makeBox(20, 16, 4, Vector(-10, -8, -2))

    @staticmethod
    def _directions(report):
        return tuple(
            (item.direction.x, item.direction.y, item.direction.z)
            for item in report.geometric.symmetries
        )

    def test_centered_rectangular_plate_has_three_exact_reflections(self):
        """The three center principal planes are proven in axis order."""
        report = self._analyze(self._centered_plate(), "centered-plate")

        self.assertEqual(
            self._directions(report),
            ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        )
        self.assertTrue(
            all(
                item.symmetry_type == "reflection"
                and item.rotational_order is None
                and item.maximum_deviation_mm == 0.0
                and item.origin == report.geometry.center
                for item in report.geometric.symmetries
            )
        )
        self.assertEqual(
            tuple(item.observation_id for item in report.geometric.symmetries),
            (
                "centered-plate:geometry:symmetry:0001",
                "centered-plate:geometry:symmetry:0002",
                "centered-plate:geometry:symmetry:0003",
            ),
        )

    def test_one_off_center_hole_removes_only_affected_reflection(self):
        """A single displaced hole cannot pass the X-plane B-rep proof."""
        shape = self._centered_plate().cut(
            Part.makeCylinder(1, 4, Vector(3, 0, -2))
        )
        report = self._analyze(shape, "off-center-hole")

        self.assertEqual(
            self._directions(report),
            ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        )

    def test_symmetric_hole_pair_preserves_principal_reflections(self):
        """Mirrored through holes preserve all three supported planes."""
        holes = Part.makeCylinder(1, 4, Vector(-3, 0, -2)).fuse(
            Part.makeCylinder(1, 4, Vector(3, 0, -2))
        )
        report = self._analyze(
            self._centered_plate().cut(holes),
            "symmetric-hole-pair",
        )

        self.assertEqual(
            self._directions(report),
            ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
        )

    def test_centered_cylinder_reports_only_supported_reflections(self):
        """A finite cylinder has principal reflections but no rotation record."""
        report = self._analyze(
            Part.makeCylinder(3, 6, Vector(0, 0, -3)),
            "centered-cylinder",
        )

        self.assertEqual(len(report.geometric.symmetries), 3)
        self.assertTrue(
            all(
                item.symmetry_type == "reflection"
                and item.rotational_order is None
                for item in report.geometric.symmetries
            )
        )

    def test_reversed_orientation_preserves_symmetry_and_complexity(self):
        """Whole-solid orientation is irrelevant to both observations."""
        forward = self._centered_plate()
        reversed_shape = forward.copy()
        reversed_shape.reverse()

        first = self._analyze(forward, "final-orientation")
        second = self._analyze(reversed_shape, "final-orientation")

        self.assertEqual(
            first.geometric.symmetries,
            second.geometric.symmetries,
        )
        self.assertEqual(
            first.geometric.complexity_indicators,
            second.geometric.complexity_indicators,
        )

    def test_slight_asymmetry_is_not_absorbed_by_a_threshold(self):
        """Even a small asymmetric cut removes affected exact symmetries."""
        shape = self._centered_plate().cut(
            Part.makeCylinder(0.001, 4, Vector(3, 1, -2))
        )
        report = self._analyze(shape, "slight-asymmetry")

        self.assertEqual(
            self._directions(report),
            ((0.0, 0.0, 1.0),),
        )

    def test_box_complexity_contains_only_exact_descriptive_counts(self):
        """A box has analytic elements, twelve creases, and no mixed family."""
        report = self._analyze(self._centered_plate(), "box-complexity")

        self.assertEqual(len(report.geometric.complexity_indicators), 1)
        observation = report.geometric.complexity_indicators[0]
        self.assertEqual(
            (
                observation.non_analytic_surface_count,
                observation.non_analytic_curve_count,
                observation.curvature_discontinuity_count,
                observation.mixed_surface_junction_count,
            ),
            (0, 0, 12, 0),
        )
        self.assertFalse(hasattr(observation, "complexity_score"))

    def test_hole_and_cavity_complexity_remain_category_counts(self):
        """Analytic holes and planar cavities add structure, not a score."""
        hole_shape = self._centered_plate().cut(
            Part.makeCylinder(1, 4, Vector(3, 0, -2))
        )
        cavity_shape = self._centered_plate().cut(
            Part.makeBox(4, 4, 2, Vector(-2, -2, -1))
        )

        hole_report = self._analyze(hole_shape, "hole-complexity")
        cavity_report = self._analyze(cavity_shape, "cavity-complexity")
        hole = hole_report.geometric.complexity_indicators[0]
        cavity = cavity_report.geometric.complexity_indicators[0]

        self.assertEqual(hole.non_analytic_surface_count, 0)
        self.assertEqual(hole.non_analytic_curve_count, 0)
        self.assertEqual(hole.curvature_discontinuity_count, 14)
        self.assertEqual(hole.mixed_surface_junction_count, 2)
        self.assertEqual(len(cavity_report.topology.cavities), 1)
        self.assertEqual(cavity.non_analytic_surface_count, 0)
        self.assertEqual(cavity.non_analytic_curve_count, 0)
        self.assertGreater(cavity.curvature_discontinuity_count, 12)
        self.assertEqual(cavity.mixed_surface_junction_count, 0)

    def test_bspline_extrusion_counts_non_analytic_surface_and_curves(self):
        """Unsupported exact B-spline families are counted, not evaluated."""
        curve = Part.BSplineCurve()
        curve.interpolate(
            (
                Vector(0, 0, 0),
                Vector(5, -2, 0),
                Vector(10, 0, 0),
            )
        )
        wire = Part.Wire(
            (
                curve.toShape(),
                Part.makeLine(Vector(10, 0, 0), Vector(10, 10, 0)),
                Part.makeLine(Vector(10, 10, 0), Vector(0, 10, 0)),
                Part.makeLine(Vector(0, 10, 0), Vector(0, 0, 0)),
            )
        )
        shape = Part.Face(wire).extrude(Vector(0, 0, 4))

        report = self._analyze(shape, "bspline-complexity")
        observation = report.geometric.complexity_indicators[0]

        self.assertEqual(observation.non_analytic_surface_count, 1)
        self.assertEqual(observation.non_analytic_curve_count, 2)

    def test_complete_pipeline_is_deterministic_and_downstream_is_default(self):
        """All approved geometry is populated without activating later stages."""
        holes = Part.makeCylinder(1, 4, Vector(-3, 0, -2)).fuse(
            Part.makeCylinder(1, 4, Vector(3, 0, -2))
        )
        shape = self._centered_plate().cut(holes)
        snapshot = GeometryEngine().create_snapshot(
            shape,
            "complete-geometric-pipeline",
            "Complete geometric source",
        )
        topology_before = TopologyAnalyzer().analyze(snapshot, shape)

        first = AnalyzerEngine(lambda resolved_id: shape).analyze(snapshot)
        second = AnalyzerEngine(lambda resolved_id: shape).analyze(snapshot)

        self.assertEqual(first, second)
        self.assertEqual(first.topology, topology_before)
        geometric = first.geometric
        self.assertTrue(geometric.thickness_observations)
        self.assertTrue(geometric.clearance_observations)
        self.assertTrue(geometric.material_ligaments)
        self.assertTrue(geometric.edge_observations)
        self.assertTrue(geometric.corner_observations)
        self.assertTrue(geometric.curvature_observations)
        self.assertTrue(geometric.flat_regions)
        self.assertTrue(geometric.symmetries)
        self.assertTrue(geometric.feature_proximities)
        self.assertTrue(geometric.complexity_indicators)
        self.assertEqual(first.manufacturing, ManufacturingAnalysis())
        self.assertEqual(first.seam, SeamAnalysis())


if __name__ == "__main__":
    unittest.main()

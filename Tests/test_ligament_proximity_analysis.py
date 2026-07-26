# -*- coding: utf-8 -*-
"""FreeCAD integration tests for ligaments and feature proximity."""

from __future__ import annotations

import math
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


@unittest.skipIf(Part is None, "FreeCAD Part module is unavailable")
class LigamentAndProximityIntegrationTests(unittest.TestCase):
    """Verify only implemented ligament and proximity observations."""

    @staticmethod
    def _analyze(shape, source_id="panel"):
        snapshot = GeometryEngine().create_snapshot(
            shape,
            source_id,
            "Ligament and proximity panel",
        )
        return AnalyzerEngine(lambda resolved_id: shape).analyze(snapshot)

    @staticmethod
    def _two_hole_shape():
        holes = Part.makeCylinder(2, 8, Vector(8, 10, 0)).fuse(
            Part.makeCylinder(2, 8, Vector(20, 10, 0))
        )
        return Part.makeBox(30, 20, 8).cut(holes)

    def test_hole_pair_reuses_one_exact_clearance_for_ligament_and_proximity(
        self,
    ):
        """One canonical pair shares identical exact separation evidence."""
        report = self._analyze(self._two_hole_shape(), "hole-pair")

        clearance = next(
            item
            for item in report.geometric.clearance_observations
            if len(item.related_feature_ids) == 2
        )
        ligaments = tuple(
            item
            for item in report.geometric.material_ligaments
            if len(item.related_feature_ids) == 2
        )
        proximities = tuple(
            item
            for item in report.geometric.feature_proximities
            if {
                item.first_feature_id,
                item.second_feature_id,
            } == set(clearance.related_feature_ids)
        )

        self.assertEqual(len(ligaments), 1)
        self.assertEqual(len(proximities), 1)
        ligament = ligaments[0]
        proximity = proximities[0]
        self.assertEqual(ligament.start, clearance.first_boundary_point)
        self.assertEqual(ligament.end, clearance.second_boundary_point)
        self.assertEqual(ligament.width_mm, clearance.clearance_mm)
        self.assertEqual(
            (ligament.first_boundary_id, ligament.second_boundary_id),
            clearance.related_feature_ids,
        )
        self.assertEqual(proximity.distance_mm, clearance.clearance_mm)
        self.assertEqual(
            math.dist(
                (
                    ligament.start.x_mm,
                    ligament.start.y_mm,
                    ligament.start.z_mm,
                ),
                (
                    ligament.end.x_mm,
                    ligament.end.y_mm,
                    ligament.end.z_mm,
                ),
            ),
            ligament.width_mm,
        )

    def test_hole_to_exterior_ligament_reuses_clearance_boundaries(self):
        """A proven material segment retains hole and source-face identity."""
        shape = Part.makeBox(20, 20, 8).cut(
            Part.makeCylinder(2, 8, Vector(4, 10, 0))
        )

        report = self._analyze(shape, "edge-ligament")

        clearance = next(
            item
            for item in report.geometric.clearance_observations
            if math.isclose(item.clearance_mm, 2.0)
        )
        ligament = next(
            item
            for item in report.geometric.material_ligaments
            if math.isclose(item.width_mm, 2.0)
        )
        self.assertEqual(ligament.start, clearance.first_boundary_point)
        self.assertEqual(ligament.end, clearance.second_boundary_point)
        self.assertEqual(
            ligament.related_feature_ids,
            clearance.related_feature_ids,
        )
        self.assertEqual(
            ligament.source_element_ids,
            clearance.source_element_ids,
        )
        self.assertEqual(
            ligament.first_boundary_id,
            clearance.related_feature_ids[0],
        )
        self.assertEqual(
            ligament.second_boundary_id,
            clearance.source_element_ids[0],
        )

    def test_counterbore_segments_do_not_duplicate_physical_ligament(self):
        """Coaxial segments collapse to one exact physical boundary pair."""
        counterbore = Part.makeCylinder(4, 3, Vector(8, 10, 5)).fuse(
            Part.makeCylinder(2, 5, Vector(8, 10, 0))
        )
        other_hole = Part.makeCylinder(2, 8, Vector(22, 10, 0))
        shape = Part.makeBox(30, 20, 8).cut(counterbore.fuse(other_hole))

        report = self._analyze(shape, "counterbore-ligament")

        pair_clearances = tuple(
            item
            for item in report.geometric.clearance_observations
            if len(item.related_feature_ids) == 2
        )
        pair_ligaments = tuple(
            item
            for item in report.geometric.material_ligaments
            if len(item.related_feature_ids) == 2
        )
        self.assertEqual(len(pair_clearances), 2)
        self.assertEqual(len(pair_ligaments), 1)
        self.assertEqual(
            pair_ligaments[0].width_mm,
            min(item.clearance_mm for item in pair_clearances),
        )

    def test_hole_to_enclosed_cavity_uses_exact_brep_distance(self):
        """Hole and inner shell produce one positive nearest-point relation."""
        voids = Part.makeCylinder(2, 8, Vector(8, 15, 0)).fuse(
            Part.makeBox(4, 6, 4, Vector(20, 12, 2))
        )
        shape = Part.makeBox(50, 30, 8).cut(voids)

        report = self._analyze(shape, "hole-cavity-proximity")

        self.assertEqual(len(report.topology.holes), 1)
        self.assertEqual(len(report.topology.cavities), 1)
        proximity = next(
            item
            for item in report.geometric.feature_proximities
            if "hole" in item.first_feature_id + item.second_feature_id
            and "cavity" in item.first_feature_id + item.second_feature_id
        )
        self.assertAlmostEqual(proximity.distance_mm, 10.0)
        self.assertAlmostEqual(
            math.dist(
                (
                    proximity.first_point.x_mm,
                    proximity.first_point.y_mm,
                    proximity.first_point.z_mm,
                ),
                (
                    proximity.second_point.x_mm,
                    proximity.second_point.y_mm,
                    proximity.second_point.z_mm,
                ),
            ),
            proximity.distance_mm,
        )

    def test_two_enclosed_cavities_use_exact_shell_distance(self):
        """Canonical cavity pair records its exact boundary separation."""
        cavities = Part.makeBox(4, 4, 4, Vector(8, 8, 2)).fuse(
            Part.makeBox(4, 4, 4, Vector(20, 8, 2))
        )
        shape = Part.makeBox(40, 25, 8).cut(cavities)

        report = self._analyze(shape, "cavity-pair")

        self.assertEqual(len(report.topology.cavities), 2)
        self.assertEqual(len(report.geometric.feature_proximities), 1)
        proximity = report.geometric.feature_proximities[0]
        self.assertAlmostEqual(proximity.distance_mm, 8.0)
        self.assertLess(proximity.first_feature_id, proximity.second_feature_id)

    def test_disconnected_islands_do_not_create_cross_island_ligament(self):
        """Hole evidence remains scoped to its owning material region."""
        first = Part.makeBox(20, 20, 8).cut(
            Part.makeCylinder(2, 8, Vector(5, 10, 0))
        )
        second = Part.makeBox(20, 20, 8, Vector(30, 0, 0)).cut(
            Part.makeCylinder(2, 8, Vector(35, 10, 0))
        )
        report = self._analyze(first.fuse(second), "island-ligament")

        self.assertFalse(
            any(
                len(item.related_feature_ids) == 2
                for item in report.geometric.material_ligaments
            )
        )

    def test_touching_holes_have_no_ligament_or_proximity_pair(self):
        """Undefined contact semantics are conservatively omitted."""
        holes = Part.makeCylinder(2, 8, Vector(8, 10, 0)).fuse(
            Part.makeCylinder(2, 8, Vector(12, 10, 0))
        )
        report = self._analyze(
            Part.makeBox(30, 20, 8).cut(holes),
            "touching-features",
        )

        self.assertFalse(
            any(
                len(item.related_feature_ids) == 2
                for item in report.geometric.material_ligaments
            )
        )
        self.assertFalse(report.geometric.feature_proximities)

    def test_reversed_orientation_preserves_ligament_and_proximity_values(self):
        """Whole-solid reversal retains supported descriptive evidence."""
        forward = self._two_hole_shape()
        reversed_shape = forward.copy()
        reversed_shape.reverse()

        first = self._analyze(forward, "orientation")
        second = self._analyze(reversed_shape, "orientation")

        self.assertEqual(
            first.geometric.material_ligaments,
            second.geometric.material_ligaments,
        )
        self.assertEqual(
            first.geometric.feature_proximities,
            second.geometric.feature_proximities,
        )

    def test_repeated_analysis_has_identical_complete_report(self):
        """Ordering, identifiers, measurements, and report equality are stable."""
        shape = self._two_hole_shape()

        first = self._analyze(shape, "ligament-determinism")
        second = self._analyze(shape, "ligament-determinism")

        self.assertEqual(first, second)

    def test_pipeline_populates_only_implemented_collections(self):
        """Later geometric and downstream stages retain exact defaults."""
        report = self._analyze(self._two_hole_shape(), "ligament-pipeline")

        self.assertTrue(report.topology.holes)
        self.assertTrue(report.geometric.thickness_observations)
        self.assertTrue(report.geometric.clearance_observations)
        self.assertTrue(report.geometric.material_ligaments)
        self.assertTrue(report.geometric.feature_proximities)
        self.assertTrue(report.geometric.edge_observations)
        self.assertTrue(report.geometric.corner_observations)
        self.assertTrue(report.geometric.curvature_observations)
        self.assertTrue(report.geometric.flat_regions)
        self.assertTrue(report.geometric.symmetries)
        self.assertTrue(report.geometric.complexity_indicators)
        self.assertEqual(report.manufacturing, ManufacturingAnalysis())
        self.assertEqual(report.seam, SeamAnalysis())


if __name__ == "__main__":
    unittest.main()

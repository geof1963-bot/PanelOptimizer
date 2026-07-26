# -*- coding: utf-8 -*-
"""FreeCAD integration tests for thickness and clearance analysis."""

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
from Core.GeometryAnalysis._Utilities import (
    LINEAR_COMPARISON_TOLERANCE_MM,
)
from Core.GeometryEngine import GeometryEngine
from Core.Models import ManufacturingAnalysis, SeamAnalysis
from Core.Topology import TopologyAnalyzer


@unittest.skipIf(Part is None, "FreeCAD Part module is unavailable")
class GeometricAnalysisIntegrationTests(unittest.TestCase):
    """Verify implemented geometric observations and pipeline defaults."""

    @staticmethod
    def _analyze(shape, source_id="panel"):
        snapshot = GeometryEngine().create_snapshot(
            shape,
            source_id,
            "Geometric test panel",
        )
        return AnalyzerEngine(lambda resolved_id: shape).analyze(snapshot)

    def test_uniform_plate_has_local_planar_thickness(self):
        """Opposing panel faces produce their exact local separation."""
        report = self._analyze(Part.makeBox(40, 30, 8))

        observations = report.geometric.thickness_observations
        self.assertEqual(len(observations), 1)
        self.assertAlmostEqual(observations[0].thickness_mm, 8.0)
        self.assertEqual(observations[0].direction.z, 1.0)
        self.assertAlmostEqual(
            observations[0].second_boundary_point.z_mm
            - observations[0].first_boundary_point.z_mm,
            8.0,
        )

    def test_through_hole_does_not_become_material_thickness(self):
        """A perforation preserves plate thickness and not its diameter."""
        shape = Part.makeBox(40, 30, 8).cut(
            Part.makeCylinder(2, 8, Vector(10, 10, 0))
        )

        report = self._analyze(shape)

        thicknesses = {
            observation.thickness_mm
            for observation in report.geometric.thickness_observations
        }
        self.assertEqual(thicknesses, {8.0})
        self.assertNotIn(4.0, thicknesses)
        self.assertEqual(len(report.topology.holes), 1)

    def test_two_holes_report_boundary_not_center_clearance(self):
        """Canonical hole pair uses circular boundary-to-boundary distance."""
        holes = Part.makeCylinder(2, 8, Vector(8, 10, 0)).fuse(
            Part.makeCylinder(2, 8, Vector(20, 10, 0))
        )
        shape = Part.makeBox(30, 20, 8).cut(holes)

        report = self._analyze(shape)

        topology_ids = tuple(
            hole.feature_id for hole in report.topology.holes
        )
        pair_observations = tuple(
            observation
            for observation in report.geometric.clearance_observations
            if observation.related_feature_ids == topology_ids
        )
        self.assertEqual(len(pair_observations), 1)
        observation = pair_observations[0]
        self.assertAlmostEqual(observation.clearance_mm, 8.0)
        center_distance = math.dist(
            (
                report.topology.holes[0].center.x_mm,
                report.topology.holes[0].center.y_mm,
            ),
            (
                report.topology.holes[1].center.x_mm,
                report.topology.holes[1].center.y_mm,
            ),
        )
        self.assertAlmostEqual(center_distance, 12.0)
        self.assertNotEqual(observation.clearance_mm, center_distance)
        self.assertAlmostEqual(
            math.dist(
                (
                    observation.first_boundary_point.x_mm,
                    observation.first_boundary_point.y_mm,
                    observation.first_boundary_point.z_mm,
                ),
                (
                    observation.second_boundary_point.x_mm,
                    observation.second_boundary_point.y_mm,
                    observation.second_boundary_point.z_mm,
                ),
            ),
            observation.clearance_mm,
        )

    def test_hole_near_external_boundary_reports_direct_spacing(self):
        """A hole boundary and panel side face produce their exact gap."""
        shape = Part.makeBox(20, 20, 8).cut(
            Part.makeCylinder(2, 8, Vector(4, 10, 0))
        )

        report = self._analyze(shape)

        hole_id = report.topology.holes[0].feature_id
        boundary_observations = tuple(
            observation
            for observation in report.geometric.clearance_observations
            if observation.related_feature_ids == (hole_id,)
        )
        self.assertTrue(boundary_observations)
        self.assertIn(
            2.0,
            {
                observation.clearance_mm
                for observation in boundary_observations
            },
        )
        self.assertEqual(
            {
                (
                    observation.second_boundary_point.x_mm,
                    observation.second_boundary_point.y_mm,
                )
                for observation in boundary_observations
            },
            {(0.0, 10.0), (4.0, 0.0), (4.0, 20.0), (20.0, 10.0)},
        )

    def test_inner_cavity_wall_is_not_an_exterior_clearance_boundary(self):
        """A nearby inner-shell plane is excluded from exterior clearances."""
        plate = Part.makeBox(30, 20, 8)
        hole = Part.makeCylinder(2, 8, Vector(5, 10, 0))
        cavity = Part.makeBox(4, 8, 4, Vector(12, 6, 2))
        shape = plate.cut(hole.fuse(cavity))

        report = self._analyze(shape, "cavity-clearance")

        outer_faces = tuple(shape.Solids[0].OuterShell.Faces)
        outer_face_ids = {
            f"cavity-clearance:face:{index:04d}"
            for index, face in enumerate(shape.Faces, start=1)
            if any(face.isSame(outer_face) for outer_face in outer_faces)
        }
        hole_clearances = tuple(
            observation
            for observation in report.geometric.clearance_observations
            if len(observation.related_feature_ids) == 1
        )
        self.assertTrue(hole_clearances)
        self.assertTrue(
            all(
                set(observation.source_element_ids) <= outer_face_ids
                for observation in hole_clearances
            )
        )
        self.assertNotIn(
            (12.0, 10.0),
            {
                (
                    observation.second_boundary_point.x_mm,
                    observation.second_boundary_point.y_mm,
                )
                for observation in hole_clearances
            },
        )

    def test_stepped_plate_preserves_distinct_local_thicknesses(self):
        """Separate planar regions retain their different exact thicknesses."""
        shape = Part.makeBox(20, 20, 5).fuse(
            Part.makeBox(10, 20, 3, Vector(0, 0, 5))
        )

        report = self._analyze(shape)

        self.assertEqual(
            tuple(
                observation.thickness_mm
                for observation in report.geometric.thickness_observations
            ),
            (5.0, 8.0),
        )
        by_thickness = {
            observation.thickness_mm: observation
            for observation in report.geometric.thickness_observations
        }
        self.assertLess(
            by_thickness[8.0].first_boundary_point.x_mm,
            10.0,
        )
        self.assertGreater(
            by_thickness[5.0].first_boundary_point.x_mm,
            10.0,
        )

    def test_blind_hole_and_cavity_never_interrupt_thickness_segments(self):
        """Accepted thickness lines remain wholly inside continuous material."""
        plate = Part.makeBox(40, 30, 8)
        blind_hole = Part.makeCylinder(3, 5, Vector(10, 10, 3))
        cavity = Part.makeBox(8, 8, 4, Vector(24, 11, 2))
        shape = plate.cut(blind_hole.fuse(cavity))

        report = self._analyze(shape, "void-thickness")

        self.assertEqual(
            {
                observation.thickness_mm
                for observation in report.geometric.thickness_observations
            },
            {2.0, 3.0, 8.0},
        )
        for observation in report.geometric.thickness_observations:
            first = Vector(
                observation.first_boundary_point.x_mm,
                observation.first_boundary_point.y_mm,
                observation.first_boundary_point.z_mm,
            )
            second = Vector(
                observation.second_boundary_point.x_mm,
                observation.second_boundary_point.y_mm,
                observation.second_boundary_point.z_mm,
            )
            midpoint = (first + second) / 2.0
            self.assertTrue(
                shape.Solids[0].isInside(
                    midpoint,
                    LINEAR_COMPARISON_TOLERANCE_MM,
                    False,
                )
            )
            self.assertAlmostEqual(
                shape.Solids[0].common(Part.makeLine(first, second)).Length,
                observation.thickness_mm,
            )

    def test_disconnected_solids_do_not_measure_across_voids_or_islands(self):
        """Separate solids retain local thickness and no cross-island gap."""
        first = Part.makeBox(20, 20, 3).cut(
            Part.makeCylinder(2, 3, Vector(5, 10, 0))
        )
        second = Part.makeBox(20, 20, 3, Vector(30, 0, 5)).cut(
            Part.makeCylinder(2, 3, Vector(35, 10, 5))
        )
        shape = first.fuse(second)

        report = self._analyze(shape, "disconnected")

        self.assertEqual(len(report.geometric.thickness_observations), 2)
        for observation in report.geometric.thickness_observations:
            self.assertAlmostEqual(observation.thickness_mm, 3.0)
        self.assertFalse(
            any(
                len(observation.related_feature_ids) == 2
                for observation in report.geometric.clearance_observations
            )
        )

    def test_open_shell_has_no_material_thickness_or_clearance(self):
        """A shell without a closed material solid is conservatively omitted."""
        box = Part.makeBox(20, 20, 8)
        shape = Part.makeShell(tuple(box.Faces[:-1]))

        report = self._analyze(shape, "open-shell")

        self.assertEqual(report.geometric.thickness_observations, ())
        self.assertEqual(report.geometric.clearance_observations, ())

    def test_overlapping_and_tangent_holes_have_no_pair_clearance(self):
        """Non-positive circular boundary gaps are never observations."""
        for source_id, center_distance in (
            ("overlapping-holes", 3.0),
            ("tangent-holes", 4.0),
        ):
            with self.subTest(center_distance=center_distance):
                holes = Part.makeCylinder(2, 8, Vector(8, 10, 0)).fuse(
                    Part.makeCylinder(
                        2,
                        8,
                        Vector(8 + center_distance, 10, 0),
                    )
                )
                shape = Part.makeBox(30, 20, 8).cut(holes)

                report = self._analyze(shape, source_id)

                self.assertFalse(
                    any(
                        len(observation.related_feature_ids) == 2
                        for observation
                        in report.geometric.clearance_observations
                    )
                )

    def test_coaxial_counterbore_segments_do_not_form_a_clearance_pair(self):
        """Segments of one stepped coaxial opening are not separated holes."""
        counterbore = Part.makeCylinder(4, 3, Vector(10, 10, 5)).fuse(
            Part.makeCylinder(2, 5, Vector(10, 10, 0))
        )
        shape = Part.makeBox(30, 20, 8).cut(counterbore)

        report = self._analyze(shape, "counterbore-clearance")

        self.assertEqual(len(report.topology.holes), 2)
        self.assertFalse(
            any(
                len(observation.related_feature_ids) == 2
                for observation in report.geometric.clearance_observations
            )
        )

    def test_non_z_aligned_plate_is_conservatively_omitted(self):
        """Unsupported non-Z thickness does not produce a guessed value."""
        shape = Part.makeBox(20, 20, 8)
        shape.rotate(Vector(0, 0, 0), Vector(1, 0, 0), 30)

        report = self._analyze(shape, "rotated-plate")

        self.assertEqual(report.geometric.thickness_observations, ())

    def test_reversed_solid_orientation_preserves_supported_observations(self):
        """Whole-solid reversal does not erase exact material measurements."""
        shape = Part.makeBox(30, 20, 8).cut(
            Part.makeCylinder(2, 8, Vector(5, 10, 0))
        )
        shape.reverse()

        report = self._analyze(shape, "reversed-solid")

        self.assertEqual(
            tuple(
                observation.thickness_mm
                for observation in report.geometric.thickness_observations
            ),
            (8.0,),
        )
        self.assertEqual(
            {
                observation.clearance_mm
                for observation in report.geometric.clearance_observations
            },
            {3.0, 8.0, 23.0},
        )

    def test_repeated_analysis_is_deterministic(self):
        """An unchanged B-rep produces equal observations and stable IDs."""
        holes = Part.makeCylinder(2, 8, Vector(8, 10, 0)).fuse(
            Part.makeCylinder(2, 8, Vector(20, 10, 0))
        )
        shape = Part.makeBox(30, 20, 8).cut(holes)

        first = self._analyze(shape, "deterministic")
        second = self._analyze(shape, "deterministic")

        self.assertEqual(first, second)
        self.assertEqual(
            tuple(
                item.observation_id
                for item in first.geometric.thickness_observations
            ),
            tuple(
                item.observation_id
                for item in second.geometric.thickness_observations
            ),
        )
        self.assertEqual(
            tuple(
                item.observation_id
                for item in first.geometric.clearance_observations
            ),
            tuple(
                item.observation_id
                for item in second.geometric.clearance_observations
            ),
        )

    def test_partial_pipeline_populates_only_implemented_geometry(self):
        """Topology and eight geometry collections precede later defaults."""
        holes = Part.makeCylinder(2, 8, Vector(8, 10, 0)).fuse(
            Part.makeCylinder(2, 8, Vector(20, 10, 0))
        )
        shape = Part.makeBox(30, 20, 8).cut(holes)

        snapshot = GeometryEngine().create_snapshot(
            shape,
            "pipeline",
            "Geometric test panel",
        )
        topology_before = TopologyAnalyzer().analyze(snapshot, shape)
        report = AnalyzerEngine(lambda source_id: shape).analyze(snapshot)

        self.assertEqual(len(report.topology.holes), 2)
        self.assertEqual(report.topology, topology_before)
        self.assertTrue(report.geometric.thickness_observations)
        self.assertTrue(report.geometric.clearance_observations)
        self.assertTrue(report.geometric.material_ligaments)
        self.assertTrue(report.geometric.edge_observations)
        self.assertTrue(report.geometric.corner_observations)
        self.assertTrue(report.geometric.curvature_observations)
        self.assertTrue(report.geometric.flat_regions)
        self.assertTrue(report.geometric.symmetries)
        self.assertTrue(report.geometric.feature_proximities)
        self.assertTrue(report.geometric.complexity_indicators)
        self.assertEqual(report.manufacturing.overall_status, "pass")
        self.assertTrue(report.manufacturing.constraint_evaluations)
        self.assertEqual(report.seam, SeamAnalysis())


if __name__ == "__main__":
    unittest.main()

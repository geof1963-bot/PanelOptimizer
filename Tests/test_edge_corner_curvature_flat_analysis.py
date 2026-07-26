# -*- coding: utf-8 -*-
"""FreeCAD integration tests for local B-rep surface observations."""

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
from Core.GeometryAnalysis.CornerAnalyzer import CornerAnalyzer
from Core.GeometryAnalysis.CurvatureAnalyzer import CurvatureAnalyzer
from Core.GeometryAnalysis._Utilities import (
    LINEAR_COMPARISON_TOLERANCE_MM,
)
from Core.GeometryEngine import GeometryEngine
from Core.Models import (
    ManufacturingAnalysis,
    SeamAnalysis,
    TopologyAnalysis,
)


@unittest.skipIf(Part is None, "FreeCAD Part module is unavailable")
class EdgeCornerCurvatureFlatIntegrationTests(unittest.TestCase):
    """Verify descriptive edge, corner, curvature, and planar regions."""

    @staticmethod
    def _analyze(shape, source_id="surface-panel"):
        snapshot = GeometryEngine().create_snapshot(
            shape,
            source_id,
            "Surface observation panel",
        )
        return AnalyzerEngine(lambda resolved_id: shape).analyze(snapshot)

    def test_box_has_lines_right_angles_zero_curvature_and_flat_faces(self):
        """A rectangular solid exposes its exact elementary B-rep facts."""
        report = self._analyze(Part.makeBox(10, 8, 4), "box-surface")

        self.assertEqual(len(report.geometric.edge_observations), 12)
        self.assertTrue(
            all(
                edge.curve_type == "line" and not edge.is_closed
                for edge in report.geometric.edge_observations
            )
        )
        self.assertEqual(len(report.geometric.corner_observations), 24)
        self.assertTrue(
            all(
                round(corner.angle_degrees, 12) == 90.0
                for corner in report.geometric.corner_observations
            )
        )
        self.assertEqual(len(report.geometric.curvature_observations), 6)
        self.assertTrue(
            all(
                observation.first_principal_curvature_per_mm == 0.0
                and observation.second_principal_curvature_per_mm == 0.0
                for observation in report.geometric.curvature_observations
            )
        )
        self.assertEqual(len(report.geometric.flat_regions), 6)

    def test_cylinder_has_circular_edges_and_exact_cylindrical_curvature(self):
        """Cylinder observations retain analytic circle and 1/r curvature."""
        report = self._analyze(Part.makeCylinder(2, 5), "cylinder-surface")

        self.assertEqual(
            sum(
                edge.curve_type == "circle"
                for edge in report.geometric.edge_observations
            ),
            2,
        )
        curved = tuple(
            item
            for item in report.geometric.curvature_observations
            if item.first_principal_curvature_per_mm != 0.0
            or item.second_principal_curvature_per_mm != 0.0
        )
        self.assertEqual(len(curved), 1)
        self.assertEqual(
            {
                abs(curved[0].first_principal_curvature_per_mm),
                abs(curved[0].second_principal_curvature_per_mm),
            },
            {0.0, 0.5},
        )

    def test_sphere_has_exact_equal_principal_curvatures(self):
        """A sphere contributes one analytic observation with curvature 1/r."""
        report = self._analyze(Part.makeSphere(3), "sphere-surface")

        self.assertEqual(len(report.geometric.curvature_observations), 1)
        observation = report.geometric.curvature_observations[0]
        self.assertAlmostEqual(
            abs(observation.first_principal_curvature_per_mm),
            1.0 / 3.0,
        )
        self.assertAlmostEqual(
            abs(observation.second_principal_curvature_per_mm),
            1.0 / 3.0,
        )

    def test_degenerate_sphere_pole_edges_are_omitted(self):
        """Collapsed pole edges never become misleading edge observations."""
        report = self._analyze(Part.makeSphere(3), "sphere-edges")

        self.assertEqual(len(report.geometric.edge_observations), 1)
        edge = report.geometric.edge_observations[0]
        self.assertEqual(edge.source_edge_id, "sphere-edges:edge:0002")
        self.assertGreater(
            edge.length_mm,
            LINEAR_COMPARISON_TOLERANCE_MM,
        )

    def test_curvature_sign_follows_the_canonical_reported_normal(self):
        """Canonical normal reversal also reverses signed curvatures."""
        cylinder = Part.makeCylinder(2, 5)
        cylindrical_face = next(
            face
            for face in cylinder.Faces
            if "cylinder" in type(face.Surface).__name__.lower()
        )
        _, _, v_min, v_max = cylindrical_face.ParameterRange

        values = CurvatureAnalyzer._surface_values(
            cylindrical_face,
            math.pi,
            (v_min + v_max) / 2.0,
        )

        self.assertIsNotNone(values)
        _, normal, _, _, first, second = values
        self.assertAlmostEqual(normal.x, 1.0)
        self.assertEqual({round(first, 12), round(second, 12)}, {0.0, 0.5})

    def test_unsupported_analytic_surface_is_omitted(self):
        """A torus receives no approximated curvature observation."""
        report = self._analyze(Part.makeTorus(5, 2), "torus-curvature")

        self.assertEqual(report.geometric.curvature_observations, ())

    def test_through_hole_surface_is_distinct_from_planar_regions(self):
        """The hole cylinder has curvature and never joins a flat region."""
        shape = Part.makeBox(20, 20, 5).cut(
            Part.makeCylinder(2, 5, Vector(10, 10, 0))
        )
        report = self._analyze(shape, "perforated-surface")

        cylindrical_face_ids = {
            f"perforated-surface:face:{index:04d}"
            for index, face in enumerate(shape.Faces, start=1)
            if "cylinder" in type(face.Surface).__name__.lower()
        }
        self.assertEqual(len(report.topology.holes), 1)
        self.assertTrue(
            any(
                item.source_face_id in cylindrical_face_ids
                and (
                    item.first_principal_curvature_per_mm != 0.0
                    or item.second_principal_curvature_per_mm != 0.0
                )
                for item in report.geometric.curvature_observations
            )
        )
        self.assertTrue(
            all(
                cylindrical_face_ids.isdisjoint(region.source_face_ids)
                for region in report.geometric.flat_regions
            )
        )
        for observation in report.geometric.curvature_observations:
            face_index = int(observation.source_face_id.rsplit(":", 1)[1]) - 1
            self.assertTrue(
                shape.Faces[face_index].isInside(
                    Vector(
                        observation.location.x_mm,
                        observation.location.y_mm,
                        observation.location.z_mm,
                    ),
                    LINEAR_COMPARISON_TOLERANCE_MM,
                    True,
                )
            )

    def test_connected_coplanar_faces_merge_by_shared_edge(self):
        """Unrefined adjacent planar faces form deterministic flat regions."""
        shape = Part.makeBox(10, 10, 5).fuse(
            Part.makeBox(10, 10, 5, Vector(10, 0, 0))
        )
        report = self._analyze(shape, "connected-flat")

        merged = tuple(
            region
            for region in report.geometric.flat_regions
            if len(region.source_face_ids) == 2
            and round(region.area_mm2, 9) == 200.0
        )
        self.assertEqual(len(merged), 2)
        self.assertEqual(
            {region.center.z_mm for region in merged},
            {0.0, 5.0},
        )
        self.assertTrue(
            all(
                region.center.x_mm == 10.0
                and region.center.y_mm == 5.0
                and region.bounding_box.minimum.x_mm == 0.0
                and region.bounding_box.maximum.x_mm == 20.0
                and len(region.boundary_edge_ids) == 6
                for region in merged
            )
        )

    def test_disconnected_coplanar_faces_remain_separate(self):
        """A recessed slot separates top faces without splitting the solid."""
        shape = Part.makeBox(30, 10, 5).cut(
            Part.makeBox(4, 10, 2, Vector(13, 0, 3))
        )
        report = self._analyze(shape, "disconnected-flat")

        top_regions = tuple(
            region
            for region in report.geometric.flat_regions
            if round(region.center.z_mm, 9) == 5.0
            and abs(region.normal.z) == 1.0
        )
        self.assertEqual(len(top_regions), 2)
        self.assertTrue(
            all(len(region.source_face_ids) == 1 for region in top_regions)
        )

    def test_parallel_offset_faces_remain_separate(self):
        """Parallel top and bottom planes do not merge without coplanarity."""
        report = self._analyze(Part.makeBox(10, 8, 4), "parallel-flat")

        horizontal = tuple(
            region
            for region in report.geometric.flat_regions
            if abs(region.normal.z) == 1.0
        )
        self.assertEqual(len(horizontal), 2)
        self.assertEqual(
            {region.center.z_mm for region in horizontal},
            {0.0, 4.0},
        )

    def test_cavity_planes_never_merge_with_outer_shell_planes(self):
        """Inner-shell and outer-shell planar regions retain separate IDs."""
        shape = Part.makeBox(30, 20, 8).cut(
            Part.makeBox(4, 8, 4, Vector(12, 6, 2))
        )
        report = self._analyze(shape, "cavity-flat")

        outer_faces = tuple(shape.Solids[0].OuterShell.Faces)
        outer_ids = {
            f"cavity-flat:face:{index:04d}"
            for index, face in enumerate(shape.Faces, start=1)
            if any(face.isSame(outer) for outer in outer_faces)
        }
        inner_ids = {
            f"cavity-flat:face:{index:04d}"
            for index, face in enumerate(shape.Faces, start=1)
            if not any(face.isSame(outer) for outer in outer_faces)
        }
        self.assertTrue(inner_ids)
        self.assertTrue(
            all(
                not (
                    outer_ids.intersection(region.source_face_ids)
                    and inner_ids.intersection(region.source_face_ids)
                )
                for region in report.geometric.flat_regions
            )
        )

    def test_coincident_faces_from_different_solids_never_merge(self):
        """Solid ownership separates even exactly coincident planar faces."""
        first = Part.makeBox(10, 10, 5)
        shape = Part.makeCompound((first, first.copy()))
        report = self._analyze(shape, "coincident-solids")

        self.assertEqual(len(shape.Solids), 2)
        self.assertEqual(len(report.geometric.flat_regions), 12)
        self.assertTrue(
            all(
                len(region.source_face_ids) == 1
                for region in report.geometric.flat_regions
            )
        )

    def test_two_edge_vertex_uses_outward_included_angle(self):
        """A vertex with exactly two valid lines yields one angle."""
        wire = Part.makePolygon(
            (
                Vector(0, 0, 0),
                Vector(10, 0, 0),
                Vector(10, 10, 0),
            )
        )
        snapshot = GeometryEngine().create_snapshot(
            Part.makeBox(1, 1, 1),
            "two-edge-vertex",
            "Corner fixture",
        )

        observations = CornerAnalyzer().analyze(
            snapshot,
            TopologyAnalysis(),
            wire,
        )

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].angle_degrees, 90.0)

    def test_collinear_opposite_edges_report_180_degrees(self):
        """Opposite outward directions preserve the exact straight angle."""
        shape = Part.makePolygon(
            (
                Vector(-10, 0, 0),
                Vector(0, 0, 0),
                Vector(10, 0, 0),
            )
        )
        snapshot = GeometryEngine().create_snapshot(
            Part.makeBox(1, 1, 1),
            "straight-corner",
            "Corner fixture",
        )

        observations = CornerAnalyzer().analyze(
            snapshot,
            TopologyAnalysis(),
            shape,
        )

        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0].angle_degrees, 180.0)

    def test_multi_edge_vertex_uses_unique_canonical_pairs(self):
        """Every box vertex yields three unambiguous pairwise angles."""
        report = self._analyze(Part.makeBox(10, 8, 4), "vertex-pairs")

        grouped: dict[str, list[tuple[str, ...]]] = {}
        for corner in report.geometric.corner_observations:
            grouped.setdefault(corner.source_vertex_id, []).append(
                corner.incident_edge_ids
            )
        self.assertEqual(len(grouped), 8)
        self.assertTrue(all(len(pairs) == 3 for pairs in grouped.values()))
        self.assertTrue(
            all(
                len(pairs) == len(set(pairs))
                for pairs in grouped.values()
            )
        )

    def test_reversed_orientation_preserves_supported_observations(self):
        """Source orientation reversal leaves descriptive values unchanged."""
        forward = Part.makeBox(10, 8, 4)
        reversed_shape = forward.copy()
        reversed_shape.reverse()

        first = self._analyze(forward, "surface-orientation")
        second = self._analyze(reversed_shape, "surface-orientation")

        self.assertEqual(
            first.geometric.edge_observations,
            second.geometric.edge_observations,
        )
        self.assertEqual(
            first.geometric.corner_observations,
            second.geometric.corner_observations,
        )
        self.assertEqual(
            first.geometric.curvature_observations,
            second.geometric.curvature_observations,
        )
        self.assertEqual(
            first.geometric.flat_regions,
            second.geometric.flat_regions,
        )

    def test_reversed_cylinder_preserves_closed_edges_and_curvature(self):
        """Reversal preserves circular seam data and nonzero curvature."""
        forward = Part.makeCylinder(2, 5)
        reversed_shape = forward.copy()
        reversed_shape.reverse()

        first = self._analyze(forward, "curved-orientation")
        second = self._analyze(reversed_shape, "curved-orientation")

        self.assertEqual(
            first.geometric.edge_observations,
            second.geometric.edge_observations,
        )
        self.assertEqual(
            first.geometric.curvature_observations,
            second.geometric.curvature_observations,
        )

    def test_repeated_analysis_has_identical_complete_report(self):
        """Every new collection is deterministic in values, order, and IDs."""
        shape = Part.makeBox(20, 20, 5).cut(
            Part.makeCylinder(2, 5, Vector(10, 10, 0))
        )

        first = self._analyze(shape, "surface-determinism")
        second = self._analyze(shape, "surface-determinism")

        self.assertEqual(first, second)

    def test_pipeline_populates_only_active_geometric_components(self):
        """Symmetry, complexity, manufacturing, and seam remain defaults."""
        shape = Part.makeBox(30, 20, 8).cut(
            Part.makeCylinder(2, 8, Vector(5, 10, 0)).fuse(
                Part.makeCylinder(2, 8, Vector(20, 10, 0))
            )
        )
        report = self._analyze(shape, "surface-pipeline")

        self.assertTrue(report.topology.holes)
        self.assertTrue(report.geometric.thickness_observations)
        self.assertTrue(report.geometric.clearance_observations)
        self.assertTrue(report.geometric.material_ligaments)
        self.assertTrue(report.geometric.edge_observations)
        self.assertTrue(report.geometric.corner_observations)
        self.assertTrue(report.geometric.curvature_observations)
        self.assertTrue(report.geometric.flat_regions)
        self.assertTrue(report.geometric.feature_proximities)
        self.assertTrue(report.geometric.symmetries)
        self.assertTrue(report.geometric.complexity_indicators)
        self.assertEqual(report.manufacturing, ManufacturingAnalysis())
        self.assertEqual(report.seam, SeamAnalysis())


if __name__ == "__main__":
    unittest.main()

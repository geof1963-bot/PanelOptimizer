# -*- coding: utf-8 -*-
"""Contract tests for the future GeometricAnalysis stage."""

from __future__ import annotations

import ast
import unittest
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

from Core.Models import (
    BoundingBox,
    ClearanceObservation,
    CornerObservation,
    CurvatureObservation,
    Direction3D,
    EdgeObservation,
    FeatureProximityObservation,
    FlatRegionObservation,
    GeometricAnalysis,
    GeometricComplexityObservation,
    MaterialLigamentObservation,
    Point3D,
    SymmetryObservation,
    ThicknessObservation,
)


class GeometricAnalysisContractTests(unittest.TestCase):
    """Verify contracts without invoking a geometry detector."""

    def setUp(self):
        """Create reusable immutable coordinate values."""
        self.first = Point3D(1.0, 2.0, 3.0)
        self.second = Point3D(4.0, 6.0, 3.0)
        self.direction = Direction3D(0.6, 0.8, 0.0)
        self.bounds = BoundingBox(self.first, self.second)

    def _populated_analysis(self):
        """Create one deterministic instance of every observation contract."""
        thickness = ThicknessObservation(
            observation_id="panel:geometry:thickness:0001",
            first_boundary_point=self.first,
            second_boundary_point=self.second,
            direction=self.direction,
            thickness_mm=5.0,
            source_element_ids=("panel:face:0001", "panel:face:0002"),
            related_feature_ids=("panel:hole:0001",),
        )
        clearance = ClearanceObservation(
            observation_id="panel:geometry:clearance:0001",
            first_boundary_point=self.first,
            second_boundary_point=self.second,
            clearance_mm=5.0,
            source_element_ids=("panel:edge:0001", "panel:edge:0002"),
        )
        ligament = MaterialLigamentObservation(
            observation_id="panel:geometry:ligament:0001",
            start=self.first,
            end=self.second,
            width_mm=5.0,
            first_boundary_id="panel:hole:0001",
            second_boundary_id="panel:face:0003",
            related_feature_ids=("panel:hole:0001",),
            source_element_ids=("panel:face:0003",),
        )
        edge = EdgeObservation(
            observation_id="panel:geometry:edge:0001",
            source_edge_id="panel:edge:0001",
            start_point=self.first,
            end_point=self.second,
            length_mm=5.0,
            curve_type="line",
            is_closed=False,
        )
        corner = CornerObservation(
            observation_id="panel:geometry:corner:0001",
            source_vertex_id="panel:vertex:0001",
            position=self.first,
            angle_degrees=90.0,
            incident_edge_ids=("panel:edge:0001", "panel:edge:0002"),
        )
        curvature = CurvatureObservation(
            observation_id="panel:geometry:curvature:0001",
            source_face_id="panel:face:0001",
            location=self.first,
            normal=Direction3D(0.0, 0.0, 1.0),
            first_principal_direction=Direction3D(1.0, 0.0, 0.0),
            second_principal_direction=Direction3D(0.0, 1.0, 0.0),
            first_principal_curvature_per_mm=0.1,
            second_principal_curvature_per_mm=0.2,
        )
        flat_region = FlatRegionObservation(
            observation_id="panel:geometry:flat-region:0001",
            center=self.first,
            normal=Direction3D(0.0, 0.0, 1.0),
            bounding_box=self.bounds,
            area_mm2=12.0,
            source_face_ids=("panel:face:0004",),
            boundary_edge_ids=("panel:edge:0003",),
        )
        symmetry = SymmetryObservation(
            observation_id="panel:geometry:symmetry:0001",
            symmetry_type="reflection",
            origin=self.first,
            direction=Direction3D(1.0, 0.0, 0.0),
            rotational_order=None,
            maximum_deviation_mm=0.01,
            related_feature_ids=("panel:hole:0001", "panel:hole:0002"),
        )
        proximity = FeatureProximityObservation(
            observation_id="panel:geometry:proximity:0001",
            first_feature_id="panel:hole:0001",
            second_feature_id="panel:cavity:0001",
            first_point=self.first,
            second_point=self.second,
            distance_mm=5.0,
        )
        complexity = GeometricComplexityObservation(
            observation_id="panel:geometry:complexity:0001",
            non_analytic_surface_count=2,
            non_analytic_curve_count=3,
            curvature_discontinuity_count=4,
            mixed_surface_junction_count=5,
        )
        return GeometricAnalysis(
            thickness_observations=(thickness,),
            clearance_observations=(clearance,),
            material_ligaments=(ligament,),
            edge_observations=(edge,),
            corner_observations=(corner,),
            curvature_observations=(curvature,),
            flat_regions=(flat_region,),
            symmetries=(symmetry,),
            feature_proximities=(proximity,),
            complexity_indicators=(complexity,),
        )

    def test_default_report_contains_only_empty_tuples(self):
        """Every future observation collection has an exact empty default."""
        analysis = GeometricAnalysis()

        self.assertTrue(fields(analysis))
        for model_field in fields(analysis):
            value = getattr(analysis, model_field.name)
            self.assertIsInstance(value, tuple)
            self.assertEqual(value, ())

    def test_contracts_are_frozen_and_tuple_based(self):
        """Populated contracts reject mutation and mutable collections."""
        analysis = self._populated_analysis()

        with self.assertRaises(FrozenInstanceError):
            analysis.material_ligaments = ()

        for model_field in fields(analysis):
            collection = getattr(analysis, model_field.name)
            self.assertIsInstance(collection, tuple)
            for observation in collection:
                for observation_field in fields(observation):
                    value = getattr(observation, observation_field.name)
                    self.assertNotIsInstance(value, (list, dict, set))

    def test_equal_inputs_produce_deterministically_equal_contracts(self):
        """Value equality is stable for identical deterministic identifiers."""
        first = self._populated_analysis()
        second = self._populated_analysis()

        self.assertEqual(first, second)
        self.assertEqual(hash(first), hash(second))

    def test_obsolete_draft_contracts_are_not_exported(self):
        """Misleading import-only aliases are absent after clean migration."""
        import Core.Models as models
        import Core.Models.Analysis as analysis_models

        self.assertFalse(hasattr(models, "CorridorFeature"))
        self.assertFalse(hasattr(models, "SymmetryFeature"))
        self.assertFalse(hasattr(models, "ThinBridgeFeature"))
        self.assertFalse(hasattr(analysis_models, "CorridorFeature"))
        self.assertFalse(hasattr(analysis_models, "SymmetryFeature"))
        self.assertFalse(hasattr(analysis_models, "ThinBridgeFeature"))
        analysis_field_names = {
            model_field.name for model_field in fields(GeometricAnalysis)
        }
        self.assertIn("material_ligaments", analysis_field_names)
        self.assertNotIn("thin_bridges", analysis_field_names)
        symmetry_fields = {
            model_field.name for model_field in fields(SymmetryObservation)
        }
        self.assertNotIn("confidence", symmetry_fields)

    def test_model_modules_do_not_import_freecad(self):
        """Core model modules contain no FreeCAD or Part dependency."""
        models_directory = (
            Path(__file__).resolve().parents[1] / "Core" / "Models"
        )
        forbidden_roots = {"FreeCAD", "FreeCADGui", "Part"}

        for module_path in models_directory.glob("*.py"):
            tree = ast.parse(
                module_path.read_text(encoding="utf-8"),
                filename=str(module_path),
            )
            imported_roots = {
                alias.name.split(".", maxsplit=1)[0]
                for node in ast.walk(tree)
                if isinstance(node, ast.Import)
                for alias in node.names
            }
            imported_roots.update(
                node.module.split(".", maxsplit=1)[0]
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module
            )
            self.assertTrue(
                forbidden_roots.isdisjoint(imported_roots),
                f"{module_path.name}: {forbidden_roots & imported_roots}",
            )


if __name__ == "__main__":
    unittest.main()

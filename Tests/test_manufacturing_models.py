# -*- coding: utf-8 -*-
"""Contract tests for the future ManufacturingAnalysis stage."""

from __future__ import annotations

import ast
import unittest
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

from Core.Models import (
    BuildEnvelope,
    ConstraintEvaluation,
    ManufacturingAnalysis,
    ManufacturingConstraint,
    ManufacturingProfile,
    ManufacturingWarning,
)
from Core.Settings import Settings


class ManufacturingContractTests(unittest.TestCase):
    """Verify manufacturing architecture without running an analyzer."""

    @staticmethod
    def _contracts():
        """Create deterministic profile, evaluation, warning, and report."""
        envelope = BuildEnvelope(
            constraint_id="profile:build-envelope",
            physical_x_mm=400.0,
            physical_y_mm=410.0,
            physical_z_mm=420.0,
            safety_margin_x_mm=10.0,
            safety_margin_y_mm=12.0,
            safety_margin_z_mm=14.0,
            effective_x_mm=390.0,
            effective_y_mm=398.0,
            effective_z_mm=406.0,
        )
        constraint = ManufacturingConstraint(
            constraint_id="profile:minimum-thickness",
            constraint_type="minimum_thickness",
            level="hard",
            comparison="greater_than_or_equal",
            limit_value=1.2,
            unit="mm",
            severity="error",
            description="Configured minimum local material thickness.",
        )
        profile = ManufacturingProfile(
            profile_id="generic-fdm",
            profile_version="2.1",
            settings_version="settings-7",
            display_name="Generic FDM profile",
            process_type="fdm",
            build_envelope=envelope,
            constraints=(constraint,),
            notes=("Contract fixture",),
        )
        evaluation = ConstraintEvaluation(
            evaluation_id=(
                "panel:manufacturing:evaluation:0001"
            ),
            constraint_id=constraint.constraint_id,
            constraint_type=constraint.constraint_type,
            constraint_level=constraint.level,
            status="fail",
            measured_value=1.0,
            required_value=constraint.limit_value,
            unit=constraint.unit,
            comparison=constraint.comparison,
            severity="error",
            rationale="Measured thickness is below the configured minimum.",
            related_geometric_observation_ids=(
                "panel:geometry:thickness:0001",
            ),
            source_element_ids=(
                "panel:face:0001",
                "panel:face:0002",
            ),
        )
        warning = ManufacturingWarning(
            warning_id="panel:manufacturing:warning:0001",
            warning_type="local_thickness_risk",
            severity="warning",
            message="A local thickness requires review.",
            rationale="The configured warning rule was triggered.",
            evaluation_ids=(evaluation.evaluation_id,),
            related_geometric_observation_ids=(
                "panel:geometry:thickness:0001",
            ),
        )
        analysis = ManufacturingAnalysis(
            profile_id=profile.profile_id,
            profile_version=profile.profile_version,
            settings_version=profile.settings_version,
            overall_status="fail",
            constraint_evaluations=(evaluation,),
            warnings=(warning,),
        )
        return envelope, constraint, profile, evaluation, warning, analysis

    def test_inactive_analysis_has_exact_model_defaults(self):
        """AnalyzerEngine's untouched stage has an auditable inactive state."""
        analysis = ManufacturingAnalysis()

        self.assertIsNone(analysis.profile_id)
        self.assertIsNone(analysis.profile_version)
        self.assertIsNone(analysis.settings_version)
        self.assertEqual(analysis.overall_status, "not_evaluated")
        self.assertEqual(analysis.constraint_evaluations, ())
        self.assertEqual(analysis.warnings, ())

    def test_profile_and_results_are_frozen_and_tuple_based(self):
        """No profile or report collection exposes mutable state."""
        contracts = self._contracts()
        envelope, constraint, profile, evaluation, warning, analysis = (
            contracts
        )

        for instance, field_name, value in (
            (envelope, "effective_x_mm", 1.0),
            (constraint, "limit_value", 2.0),
            (profile, "constraints", ()),
            (evaluation, "status", "pass"),
            (warning, "message", "changed"),
            (analysis, "overall_status", "pass"),
        ):
            with self.subTest(type=type(instance).__name__):
                with self.assertRaises(FrozenInstanceError):
                    setattr(instance, field_name, value)

        for instance in (profile, evaluation, warning, analysis):
            for model_field in fields(instance):
                value = getattr(instance, model_field.name)
                self.assertNotIsInstance(value, (list, dict, set))

    def test_equal_inputs_have_deterministic_value_equality(self):
        """Profile provenance and results compare entirely by value."""
        first = self._contracts()
        second = self._contracts()

        self.assertEqual(first, second)
        self.assertEqual(
            tuple(hash(item) for item in first),
            tuple(hash(item) for item in second),
        )

    def test_units_and_physical_effective_extents_are_explicit(self):
        """Scalar rules and envelope dimensions expose unambiguous units."""
        envelope, constraint, _, evaluation, _, _ = self._contracts()

        envelope_fields = {item.name for item in fields(envelope)}
        self.assertTrue(
            {
                "physical_x_mm",
                "physical_y_mm",
                "physical_z_mm",
                "safety_margin_x_mm",
                "safety_margin_y_mm",
                "safety_margin_z_mm",
                "effective_x_mm",
                "effective_y_mm",
                "effective_z_mm",
            }.issubset(envelope_fields)
        )
        self.assertEqual(constraint.unit, "mm")
        self.assertEqual(evaluation.unit, constraint.unit)
        self.assertEqual(evaluation.measured_value, 1.0)
        self.assertEqual(evaluation.required_value, 1.2)

    def test_hard_failures_and_nonfatal_warnings_are_distinct(self):
        """A failed hard constraint is not represented as a warning score."""
        _, constraint, _, evaluation, warning, analysis = self._contracts()

        self.assertEqual(constraint.level, "hard")
        self.assertEqual(evaluation.status, "fail")
        self.assertEqual(evaluation.severity, "error")
        self.assertEqual(warning.severity, "warning")
        self.assertEqual(analysis.overall_status, "fail")
        self.assertFalse(hasattr(analysis, "score"))

    def test_warning_clean_migration_uses_evidence_ids_only(self):
        """The obsolete geometry-copying warning fields are not retained."""
        warning_fields = {
            model_field.name for model_field in fields(ManufacturingWarning)
        }

        self.assertIn("evaluation_ids", warning_fields)
        self.assertIn("related_geometric_observation_ids", warning_fields)
        self.assertNotIn("location", warning_fields)
        self.assertNotIn("bounding_box", warning_fields)
        self.assertNotIn("category", warning_fields)
        self.assertNotIn("related_feature_ids", warning_fields)

    def test_centralized_settings_and_profile_are_immutable(self):
        """Configured values can be snapshotted without mutable global input."""
        _, _, profile, _, _, _ = self._contracts()

        with self.assertRaises(FrozenInstanceError):
            Settings.Printer.BED_SIZE_X = 1.0
        with self.assertRaises(FrozenInstanceError):
            profile.profile_version = "changed"

    def test_manufacturing_model_has_no_freecad_or_gui_dependency(self):
        """The focused contract module remains runtime-geometry independent."""
        module_path = (
            Path(__file__).resolve().parents[1]
            / "Core"
            / "Models"
            / "Manufacturing.py"
        )
        tree = ast.parse(
            module_path.read_text(encoding="utf-8"),
            filename=str(module_path),
        )
        forbidden = {"FreeCAD", "FreeCADGui", "Part", "Gui"}
        imported = {
            alias.name.split(".", maxsplit=1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module.split(".", maxsplit=1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        )
        self.assertTrue(forbidden.isdisjoint(imported))


if __name__ == "__main__":
    unittest.main()

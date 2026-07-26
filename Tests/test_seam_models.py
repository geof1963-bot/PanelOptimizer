# -*- coding: utf-8 -*-
"""Contract tests for the architecture-only SeamAnalysis stage."""

from __future__ import annotations

import ast
import unittest
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

try:
    import Part
except ImportError:  # pragma: no cover - exercised outside FreeCAD
    Part = None

from Core.AnalyzerEngine import AnalyzerEngine
from Core.GeometryEngine import GeometryEngine
from Core.Models import (
    SeamAnalysis,
    SeamConstraint,
    SeamEvidence,
    SeamProfile,
    SeamWarning,
    SeamZone,
)


class SeamContractTests(unittest.TestCase):
    """Verify focused immutable seam contracts without running seam rules."""

    @staticmethod
    def _contracts():
        """Create one deterministic populated instance of every contract."""
        constraint = SeamConstraint(
            constraint_id="seam-policy:constraint:cavity-avoidance",
            constraint_type="cavity_avoidance",
            level="hard",
            category="forbidden",
            description="Forbid traversal through a proven cavity region.",
        )
        profile = SeamProfile(
            profile_id="seam-policy",
            profile_version="1",
            settings_version="settings-1",
            display_name="Default seam policy",
            constraints=(constraint,),
            notes=("No scoring weights.",),
        )
        evidence = SeamEvidence(
            evidence_id="panel:seam:evidence:0001",
            evidence_type="cavity_presence",
            rationale="Topology identifies an enclosed cavity.",
            related_topology_feature_ids=("panel:cavity:0001",),
            related_manufacturing_evaluation_ids=(
                "panel:manufacturing:evaluation:0001",
            ),
            source_element_ids=("panel:face:0004",),
        )
        zone = SeamZone(
            zone_id="panel:seam:zone:0001",
            constraint_id=constraint.constraint_id,
            category="forbidden",
            rationale="The referenced cavity region forbids traversal.",
            evidence_ids=(evidence.evidence_id,),
            region_reference_ids=("panel:cavity:0001",),
        )
        warning = SeamWarning(
            warning_id="panel:seam:warning:0001",
            warning_type="incomplete_region_evidence",
            severity="warning",
            message="Seam region evidence is incomplete.",
            rationale="A configured seam rule lacks exact source evidence.",
            constraint_ids=(constraint.constraint_id,),
            evidence_ids=(evidence.evidence_id,),
            zone_ids=(zone.zone_id,),
        )
        analysis = SeamAnalysis(
            profile_id=profile.profile_id,
            profile_version=profile.profile_version,
            settings_version=profile.settings_version,
            evidence=(evidence,),
            zones=(zone,),
            warnings=(warning,),
        )
        return constraint, profile, evidence, zone, warning, analysis

    def test_inactive_analysis_has_exact_defaults(self):
        """The architecture remains inactive until a seam analyzer exists."""
        analysis = SeamAnalysis()

        self.assertIsNone(analysis.profile_id)
        self.assertIsNone(analysis.profile_version)
        self.assertIsNone(analysis.settings_version)
        self.assertEqual(analysis.evidence, ())
        self.assertEqual(analysis.zones, ())
        self.assertEqual(analysis.warnings, ())

    def test_contracts_are_frozen_slotted_and_tuple_based(self):
        """Seam contracts expose no mutable collection or writable state."""
        contracts = self._contracts()

        for instance in contracts:
            self.assertTrue(instance.__class__.__dataclass_params__.frozen)
            self.assertTrue(hasattr(instance.__class__, "__slots__"))
            for model_field in fields(instance):
                value = getattr(instance, model_field.name)
                self.assertNotIsInstance(value, (list, dict, set))

        with self.assertRaises(FrozenInstanceError):
            contracts[-1].zones = ()

    def test_equal_inputs_have_deterministic_value_equality(self):
        """Profiles and reports compare entirely by immutable values."""
        first = self._contracts()
        second = self._contracts()

        self.assertEqual(first, second)
        self.assertEqual(
            tuple(hash(item) for item in first),
            tuple(hash(item) for item in second),
        )

    def test_contracts_contain_no_scoring_or_path_generation_fields(self):
        """Seam evidence cannot conceal ranking or generated route geometry."""
        forbidden_names = {
            "score",
            "weight",
            "cost",
            "rank",
            "path",
            "route",
            "polyline",
            "spline",
            "segments",
            "boundary_points",
        }

        for model_type in (
            SeamConstraint,
            SeamProfile,
            SeamEvidence,
            SeamZone,
            SeamWarning,
            SeamAnalysis,
        ):
            names = {model_field.name for model_field in fields(model_type)}
            self.assertFalse(
                any(
                    forbidden in field_name
                    for field_name in names
                    for forbidden in forbidden_names
                ),
                model_type,
            )

    def test_candidate_zone_was_cleanly_replaced(self):
        """The ambiguous path-like draft contract has no compatibility alias."""
        import Core.Models as models
        import Core.Models.Analysis as analysis_models

        self.assertFalse(hasattr(models, "CandidateZone"))
        self.assertFalse(hasattr(analysis_models, "CandidateZone"))
        self.assertFalse(hasattr(SeamAnalysis(), "safe_zones"))
        self.assertFalse(hasattr(SeamAnalysis(), "forbidden_zones"))

    def test_seam_model_has_no_freecad_or_gui_dependency(self):
        """The focused model module remains runtime-geometry independent."""
        module_path = (
            Path(__file__).resolve().parents[1]
            / "Core"
            / "Models"
            / "Seam.py"
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


@unittest.skipIf(Part is None, "FreeCAD Part module is unavailable")
class SeamPipelineContractTests(unittest.TestCase):
    """Verify architecture changes do not activate the seam stage."""

    def test_analyzer_engine_still_returns_default_seam_analysis(self):
        """Implemented upstream stages run while seam stays exactly inactive."""
        shape = Part.makeBox(20, 10, 2)
        snapshot = GeometryEngine().create_snapshot(
            shape,
            "seam-default",
            "Panel",
        )

        report = AnalyzerEngine(lambda source_id: shape).analyze(snapshot)

        self.assertTrue(report.topology.connectivity_graph)
        self.assertTrue(report.geometric.thickness_observations)
        self.assertEqual(report.manufacturing.overall_status, "pass")
        self.assertEqual(report.seam, SeamAnalysis())


if __name__ == "__main__":
    unittest.main()

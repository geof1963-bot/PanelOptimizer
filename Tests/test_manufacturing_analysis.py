# -*- coding: utf-8 -*-
"""Core and FreeCAD integration tests for manufacturing evaluation."""

from __future__ import annotations

import unittest
from dataclasses import replace
from types import SimpleNamespace

try:
    import Part
    from FreeCAD import Vector
except ImportError:  # pragma: no cover - exercised outside FreeCAD
    Part = None
    Vector = None

from Core.AnalyzerEngine import AnalyzerEngine
from Core.Exceptions import (
    ConstraintEvaluationError,
    ManufacturingProfileError,
)
from Core.GeometryAnalysis import GeometricAnalyzer
from Core.GeometryEngine import GeometryEngine
from Core.ManufacturingAnalysis import (
    ConstraintEvaluator,
    ManufacturingAnalyzer,
    ProfileComposer,
)
from Core.Models import (
    BoundingBox,
    BuildEnvelope,
    CavityFeature,
    ClearanceObservation,
    Direction3D,
    GeometricAnalysis,
    HoleFeature,
    ManufacturingConstraint,
    ManufacturingProfile,
    ManufacturingWarning,
    MaterialLigamentObservation,
    Point3D,
    SeamAnalysis,
    ThicknessObservation,
    TopologyAnalysis,
)
from Core.Settings import Settings
from Core.Topology import TopologyAnalyzer


@unittest.skipIf(Part is None, "FreeCAD Part module is unavailable")
class ManufacturingAnalysisIntegrationTests(unittest.TestCase):
    """Verify only the implemented deterministic fabrication constraints."""

    @staticmethod
    def _snapshot(shape, source_id):
        return GeometryEngine().create_snapshot(
            shape,
            source_id,
            "Manufacturing source",
        )

    @classmethod
    def _analyze(cls, shape, source_id, profile=None):
        snapshot = cls._snapshot(shape, source_id)
        return AnalyzerEngine(
            lambda resolved_id: shape,
            manufacturing_profile=profile,
        ).analyze(snapshot)

    @staticmethod
    def _constraint(
        constraint_type,
        limit,
        level="hard",
        enabled=True,
        unit="mm",
    ):
        return ManufacturingConstraint(
            constraint_id=f"test-profile:constraint:{constraint_type}",
            constraint_type=constraint_type,
            level=level,
            comparison="greater_than_or_equal",
            limit_value=limit,
            unit=unit,
            severity="error" if level == "hard" else "warning",
            description=f"Test {constraint_type} rule.",
            is_enabled=enabled,
        )

    @staticmethod
    def _profile(*constraints, envelope=None):
        return ManufacturingProfile(
            profile_id="test-profile",
            profile_version="1",
            settings_version="test-settings-1",
            display_name="Test profile",
            process_type="fdm",
            build_envelope=envelope,
            constraints=tuple(constraints),
        )

    def test_profile_composition_owns_effective_limits_in_split_settings(self):
        """Physical, effective, and total-margin values have one source each."""
        profile = ProfileComposer().compose()
        envelope = profile.build_envelope

        self.assertIsNotNone(envelope)
        self.assertEqual(envelope.physical_x_mm, Settings.Printer.BED_SIZE_X)
        self.assertEqual(envelope.physical_y_mm, Settings.Printer.BED_SIZE_Y)
        self.assertEqual(envelope.effective_x_mm, Settings.Split.MAX_PART_WIDTH)
        self.assertEqual(envelope.effective_y_mm, Settings.Split.MAX_PART_HEIGHT)
        self.assertEqual(
            envelope.safety_margin_x_mm,
            Settings.Printer.BED_SIZE_X - Settings.Split.MAX_PART_WIDTH,
        )
        self.assertIsNone(envelope.physical_z_mm)
        self.assertIsNone(envelope.effective_z_mm)
        self.assertEqual(profile.constraints, ())

    def test_legacy_scalar_printer_limit_is_not_a_profile_source(self):
        """Changing the legacy overlap cannot change effective axis limits."""
        settings = SimpleNamespace(
            Printer=replace(Settings.Printer, MAX_PART_SIZE=1.0),
            Split=Settings.Split,
            Manufacturing=Settings.Manufacturing,
        )

        profile = ProfileComposer(settings).compose()

        self.assertEqual(
            profile.build_envelope.effective_x_mm,
            Settings.Split.MAX_PART_WIDTH,
        )
        self.assertEqual(
            profile.build_envelope.effective_y_mm,
            Settings.Split.MAX_PART_HEIGHT,
        )
        report = self._analyze(
            Part.makeBox(2, 2, 2),
            "legacy-limit-runtime",
            profile,
        )
        self.assertEqual(report.manufacturing.overall_status, "pass")

    def test_profile_composition_rejects_impossible_envelopes(self):
        """Non-positive, oversized, and partial axis settings are errors."""
        cases = (
            (
                "effective-over-physical",
                replace(Settings.Printer, BED_SIZE_X=100.0),
                replace(Settings.Split, MAX_PART_WIDTH=101.0),
            ),
            (
                "zero-physical",
                replace(Settings.Printer, BED_SIZE_X=0.0),
                Settings.Split,
            ),
            (
                "zero-effective",
                Settings.Printer,
                replace(Settings.Split, MAX_PART_WIDTH=0.0),
            ),
            (
                "negative-physical",
                replace(Settings.Printer, BED_SIZE_Y=-1.0),
                Settings.Split,
            ),
            (
                "physical-z-only",
                replace(Settings.Printer, BED_SIZE_Z=100.0),
                Settings.Split,
            ),
            (
                "effective-z-only",
                Settings.Printer,
                replace(Settings.Split, MAX_PART_DEPTH=90.0),
            ),
        )
        for name, printer, split in cases:
            with self.subTest(name=name):
                settings = SimpleNamespace(
                    Printer=printer,
                    Split=split,
                    Manufacturing=Settings.Manufacturing,
                )
                with self.assertRaises(ManufacturingProfileError):
                    ProfileComposer(settings).compose()

    def test_zero_total_safety_margin_is_valid_and_unambiguous(self):
        """Margin is the total axis difference and may validly equal zero."""
        settings = SimpleNamespace(
            Printer=replace(Settings.Printer, BED_SIZE_X=330.0),
            Split=replace(Settings.Split, MAX_PART_WIDTH=330.0),
            Manufacturing=Settings.Manufacturing,
        )

        envelope = ProfileComposer(settings).compose().build_envelope

        self.assertEqual(envelope.safety_margin_x_mm, 0.0)
        self.assertEqual(
            envelope.safety_margin_x_mm,
            envelope.physical_x_mm - envelope.effective_x_mm,
        )

    def test_injected_incoherent_envelope_is_a_profile_error(self):
        """Bypassing composition cannot silently introduce invalid margins."""
        invalid = BuildEnvelope(
            constraint_id="invalid:envelope",
            physical_x_mm=100.0,
            physical_y_mm=100.0,
            physical_z_mm=None,
            safety_margin_x_mm=-1.0,
            safety_margin_y_mm=10.0,
            safety_margin_z_mm=None,
            effective_x_mm=90.0,
            effective_y_mm=90.0,
            effective_z_mm=None,
        )

        with self.assertRaises(ManufacturingProfileError):
            self._analyze(
                Part.makeBox(20, 20, 5),
                "invalid-injected-envelope",
                self._profile(envelope=invalid),
            )

    def test_injected_decimal_envelope_accepts_representation_roundoff(self):
        """Configuration coherence tolerates only floating representation."""
        envelope = BuildEnvelope(
            constraint_id="decimal:envelope",
            physical_x_mm=0.3,
            physical_y_mm=0.3,
            physical_z_mm=None,
            safety_margin_x_mm=0.1,
            safety_margin_y_mm=0.1,
            safety_margin_z_mm=None,
            effective_x_mm=0.2,
            effective_y_mm=0.2,
            effective_z_mm=None,
        )

        report = self._analyze(
            Part.makeBox(0.2, 0.2, 0.1),
            "decimal-envelope",
            self._profile(envelope=envelope),
        )

        self.assertEqual(report.manufacturing.overall_status, "pass")

    def test_profile_composes_configured_constraints_in_fixed_order(self):
        """Identical configured rules produce an ordered immutable tuple."""
        configured = replace(
            Settings.Manufacturing,
            MINIMUM_THICKNESS_MM=2.0,
            ENABLE_MINIMUM_THICKNESS=True,
            MINIMUM_LIGAMENT_WIDTH_MM=1.0,
            ENABLE_MINIMUM_LIGAMENT=False,
        )
        settings = SimpleNamespace(
            Printer=Settings.Printer,
            Split=Settings.Split,
            Manufacturing=configured,
        )

        first = ProfileComposer(settings).compose()
        second = ProfileComposer(settings).compose()

        self.assertEqual(first, second)
        self.assertEqual(
            tuple(item.constraint_type for item in first.constraints),
            ("minimum_thickness", "minimum_ligament_width"),
        )
        self.assertTrue(first.constraints[0].is_enabled)
        self.assertFalse(first.constraints[1].is_enabled)

    def test_inside_build_envelope_passes_each_configured_axis(self):
        """A small source produces independent passing X/Y evaluations."""
        report = self._analyze(Part.makeBox(100, 80, 5), "inside-envelope")

        evaluations = report.manufacturing.constraint_evaluations
        self.assertEqual(report.manufacturing.overall_status, "pass")
        self.assertEqual(
            tuple(item.constraint_type for item in evaluations),
            ("build_envelope_x", "build_envelope_y"),
        )
        self.assertTrue(all(item.status == "pass" for item in evaluations))

    def test_exact_build_envelope_boundary_passes_without_tolerance(self):
        """The defined <= comparison accepts exact equality and nothing more."""
        profile = ProfileComposer().compose()
        shape = Part.makeBox(
            profile.build_envelope.effective_x_mm,
            profile.build_envelope.effective_y_mm,
            5,
        )

        report = self._analyze(shape, "envelope-equality", profile)

        self.assertEqual(report.manufacturing.overall_status, "pass")
        self.assertTrue(
            all(
                item.measured_value == item.required_value
                and item.comparison == "less_than_or_equal"
                and item.status == "pass"
                for item in report.manufacturing.constraint_evaluations
            )
        )

    def test_configured_z_axis_is_evaluated_independently(self):
        """Z remains absent by default but becomes active when fully configured."""
        settings = SimpleNamespace(
            Printer=replace(Settings.Printer, BED_SIZE_Z=100.0),
            Split=replace(Settings.Split, MAX_PART_DEPTH=90.0),
            Manufacturing=Settings.Manufacturing,
        )
        profile = ProfileComposer(settings).compose()

        report = self._analyze(
            Part.makeBox(20, 20, 91),
            "configured-z",
            profile,
        )
        by_type = {
            item.constraint_type: item
            for item in report.manufacturing.constraint_evaluations
        }

        self.assertEqual(by_type["build_envelope_x"].status, "pass")
        self.assertEqual(by_type["build_envelope_y"].status, "pass")
        self.assertEqual(by_type["build_envelope_z"].status, "fail")
        self.assertEqual(report.manufacturing.overall_status, "fail")

    def test_exceeding_x_is_a_hard_result_not_an_exception(self):
        """An oversized X extent produces a valid failed analysis."""
        width = Settings.Split.MAX_PART_WIDTH + 1.0
        report = self._analyze(
            Part.makeBox(width, 20, 5),
            "oversized-x",
        )

        by_type = {
            item.constraint_type: item
            for item in report.manufacturing.constraint_evaluations
        }
        self.assertEqual(report.manufacturing.overall_status, "fail")
        self.assertEqual(by_type["build_envelope_x"].status, "fail")
        self.assertEqual(by_type["build_envelope_y"].status, "pass")

    def test_x_and_y_fail_independently_in_deterministic_order(self):
        """Two oversized axes retain independent X-then-Y evidence."""
        shape = Part.makeBox(
            Settings.Split.MAX_PART_WIDTH + 1.0,
            Settings.Split.MAX_PART_HEIGHT + 2.0,
            5,
        )
        report = self._analyze(shape, "oversized-xy")

        evaluations = report.manufacturing.constraint_evaluations
        self.assertEqual(
            tuple(item.evaluation_id for item in evaluations),
            (
                "oversized-xy:manufacturing:build-envelope:x",
                "oversized-xy:manufacturing:build-envelope:y",
            ),
        )
        self.assertTrue(all(item.status == "fail" for item in evaluations))

    def test_large_source_panel_fails_envelope_without_harming_analysis(self):
        """An unsplit source can fail one-part limits with valid upstream data."""
        shape = Part.makeBox(594, 594, 8)
        snapshot = self._snapshot(shape, "large-source-panel")
        topology_before = TopologyAnalyzer().analyze(snapshot, shape)
        geometric_before = GeometricAnalyzer().analyze(
            snapshot,
            topology_before,
            shape,
        )
        report = AnalyzerEngine(lambda resolved_id: shape).analyze(snapshot)

        self.assertEqual(report.manufacturing.overall_status, "fail")
        self.assertTrue(report.topology.connectivity_graph)
        self.assertTrue(report.geometric.thickness_observations)
        self.assertEqual(report.topology, topology_before)
        self.assertEqual(report.geometric, geometric_before)
        self.assertEqual(report.seam, SeamAnalysis())

    def test_thickness_above_and_below_hard_minimum(self):
        """Every local thickness is compared with the configured minimum."""
        constraint = self._constraint("minimum_thickness", 2.0)
        profile = self._profile(constraint)

        above = self._analyze(
            Part.makeBox(20, 20, 3),
            "thickness-pass",
            profile,
        )
        below = self._analyze(
            Part.makeBox(20, 20, 1),
            "thickness-fail",
            profile,
        )

        self.assertEqual(above.manufacturing.overall_status, "pass")
        self.assertEqual(below.manufacturing.overall_status, "fail")
        evaluation = below.manufacturing.constraint_evaluations[0]
        self.assertEqual(evaluation.measured_value, 1.0)
        self.assertEqual(evaluation.required_value, 2.0)
        self.assertEqual(
            evaluation.related_geometric_observation_ids,
            ("thickness-fail:geometry:thickness:0001",),
        )

    def test_ligament_minimum_produces_pass_and_fail_results(self):
        """Ligament width is interpreted without new structural analysis."""
        shape = Part.makeBox(30, 20, 8).cut(
            Part.makeCylinder(2, 8, Vector(8, 10, 0)).fuse(
                Part.makeCylinder(2, 8, Vector(20, 10, 0))
            )
        )
        passing = self._analyze(
            shape,
            "ligament-pass",
            self._profile(self._constraint("minimum_ligament_width", 1.0)),
        )
        failing = self._analyze(
            shape,
            "ligament-fail",
            self._profile(self._constraint("minimum_ligament_width", 9.0)),
        )

        self.assertEqual(passing.manufacturing.overall_status, "pass")
        self.assertEqual(failing.manufacturing.overall_status, "fail")
        self.assertTrue(
            any(
                item.status == "fail"
                and item.related_geometric_observation_ids[0].startswith(
                    "ligament-fail:geometry:ligament:"
                )
                for item in failing.manufacturing.constraint_evaluations
            )
        )

    def test_only_typed_hole_to_hole_clearance_is_evaluated(self):
        """The hole-pair rule never consumes hole-to-exterior clearances."""
        holes = Part.makeCylinder(2, 8, Vector(8, 10, 0)).fuse(
            Part.makeCylinder(2, 8, Vector(20, 10, 0))
        )
        shape = Part.makeBox(30, 20, 8).cut(holes)
        profile = self._profile(
            self._constraint("minimum_hole_to_hole_clearance", 9.0)
        )

        report = self._analyze(shape, "hole-pair-clearance", profile)
        evaluations = report.manufacturing.constraint_evaluations

        self.assertEqual(len(evaluations), 1)
        self.assertEqual(evaluations[0].status, "fail")
        self.assertEqual(
            len(evaluations[0].related_topology_feature_ids),
            2,
        )
        self.assertEqual(evaluations[0].source_element_ids, ())

    def test_only_typed_hole_to_exterior_clearances_are_evaluated(self):
        """The exterior rule requires one hole ID and measured source faces."""
        shape = Part.makeBox(20, 20, 8).cut(
            Part.makeCylinder(2, 8, Vector(4, 10, 0))
        )
        profile = self._profile(
            self._constraint("minimum_hole_to_exterior_clearance", 3.0)
        )

        report = self._analyze(shape, "exterior-clearance", profile)
        evaluations = report.manufacturing.constraint_evaluations

        self.assertTrue(evaluations)
        self.assertEqual(report.manufacturing.overall_status, "fail")
        self.assertTrue(
            all(
                len(item.related_topology_feature_ids) == 1
                and item.source_element_ids
                for item in evaluations
            )
        )

    def test_generic_clearance_rule_is_omitted_as_semantically_ambiguous(self):
        """No global rule is applied across unrelated clearance meanings."""
        shape = Part.makeBox(20, 20, 8).cut(
            Part.makeCylinder(2, 8, Vector(4, 10, 0))
        )
        profile = self._profile(
            self._constraint("minimum_feature_clearance", 3.0)
        )

        report = self._analyze(shape, "generic-clearance", profile)

        self.assertEqual(report.manufacturing.constraint_evaluations, ())
        self.assertEqual(report.manufacturing.overall_status, "not_evaluated")

    def test_malformed_clearance_evidence_is_omitted_conservatively(self):
        """Typed rules require explicit semantics and corroborating IDs."""
        snapshot = self._snapshot(Part.makeBox(20, 20, 5), "clearance-evidence")
        first_hole = HoleFeature(
            "hole-1", Point3D(4, 4, 0), Direction3D(0, 0, 1), 2, 5, True
        )
        second_hole = HoleFeature(
            "hole-2", Point3D(12, 4, 0), Direction3D(0, 0, 1), 2, 5, True
        )
        cavity = CavityFeature(
            "cavity-1",
            Point3D(10, 10, 2),
            BoundingBox(Point3D(9, 9, 1), Point3D(11, 11, 3)),
            8,
            (),
        )
        topology = TopologyAnalysis(
            holes=(first_hole, second_hole),
            cavities=(cavity,),
        )
        point_a = Point3D(5, 4, 2)
        point_b = Point3D(11, 4, 2)
        observations = (
            ClearanceObservation(
                "unspecified-pair", point_a, point_b, 6, (),
                ("hole-1", "hole-2"),
            ),
            ClearanceObservation(
                "pair-with-source", point_a, point_b, 6,
                ("clearance-evidence:face:0001",),
                ("hole-1", "hole-2"), "hole_to_hole",
            ),
            ClearanceObservation(
                "cavity-pair", point_a, point_b, 6, (),
                ("hole-1", "cavity-1"), "hole_to_hole",
            ),
            ClearanceObservation(
                "exterior-without-source", point_a, point_b, 6, (),
                ("hole-1",), "hole_to_exterior",
            ),
            ClearanceObservation(
                "exterior-with-edge", point_a, point_b, 6,
                ("clearance-evidence:edge:0001",),
                ("hole-1",), "hole_to_exterior",
            ),
            ClearanceObservation(
                "valid-exterior", point_a, point_b, 6,
                (
                    "clearance-evidence:face:0001",
                    "clearance-evidence:face:0002",
                ),
                ("hole-1",), "hole_to_exterior",
            ),
        )
        profile = self._profile(
            self._constraint("minimum_hole_to_hole_clearance", 5),
            self._constraint("minimum_hole_to_exterior_clearance", 5),
        )

        evaluations = ConstraintEvaluator().evaluate(
            snapshot,
            topology,
            GeometricAnalysis(clearance_observations=observations),
            profile,
        )

        self.assertEqual(len(evaluations), 1)
        self.assertEqual(
            evaluations[0].related_geometric_observation_ids,
            ("valid-exterior",),
        )
        self.assertEqual(
            evaluations[0].source_element_ids,
            (
                "clearance-evidence:face:0001",
                "clearance-evidence:face:0002",
            ),
        )

    def test_counterbore_clearances_remain_explicit_local_evidence(self):
        """Stepped segments are evaluated only as detector-typed exact gaps."""
        counterbore = Part.makeCylinder(4, 3, Vector(8, 10, 5)).fuse(
            Part.makeCylinder(2, 5, Vector(8, 10, 0))
        )
        other_hole = Part.makeCylinder(2, 8, Vector(22, 10, 0))
        shape = Part.makeBox(30, 20, 8).cut(counterbore.fuse(other_hole))
        profile = self._profile(
            self._constraint("minimum_hole_to_hole_clearance", 1)
        )

        report = self._analyze(shape, "counterbore-manufacturing", profile)
        typed = tuple(
            item
            for item in report.geometric.clearance_observations
            if item.relationship_type == "hole_to_hole"
        )

        self.assertEqual(len(typed), 2)
        self.assertEqual(
            tuple(
                item.related_geometric_observation_ids[0]
                for item in report.manufacturing.constraint_evaluations
            ),
            tuple(item.observation_id for item in typed),
        )
        self.assertTrue(
            all(not item.source_element_ids for item in typed)
        )

    def test_disabled_constraint_produces_no_evaluation(self):
        """A configured but disabled scalar constraint remains inactive."""
        profile = self._profile(
            self._constraint("minimum_thickness", 10.0, enabled=False)
        )

        report = self._analyze(
            Part.makeBox(20, 20, 1),
            "disabled-thickness",
            profile,
        )

        self.assertEqual(report.manufacturing.constraint_evaluations, ())
        self.assertEqual(report.manufacturing.overall_status, "not_evaluated")

    def test_warning_only_violation_derives_warning_status(self):
        """A warning rule cannot become a hard manufacturing failure."""
        profile = self._profile(
            self._constraint("minimum_thickness", 2.0, level="warning")
        )

        report = self._analyze(
            Part.makeBox(20, 20, 1),
            "warning-thickness",
            profile,
        )

        self.assertEqual(report.manufacturing.overall_status, "warning")
        self.assertEqual(
            report.manufacturing.constraint_evaluations[0].status,
            "warning",
        )
        self.assertEqual(report.manufacturing.warnings, ())

    def test_mixed_hard_and_warning_results_follow_precedence(self):
        """Hard failure wins; otherwise only a warning violation warns."""
        shape = Part.makeBox(20, 20, 2)
        hard_pass = self._constraint("minimum_thickness", 1.0)
        warning_pass = replace(
            self._constraint("minimum_thickness", 1.0, level="warning"),
            constraint_id="test-profile:constraint:warning-pass",
        )
        warning_fail = replace(
            self._constraint("minimum_thickness", 3.0, level="warning"),
            constraint_id="test-profile:constraint:warning-fail",
        )
        hard_fail = replace(
            self._constraint("minimum_thickness", 3.0),
            constraint_id="test-profile:constraint:hard-fail",
        )

        passing = self._analyze(
            shape, "mixed-pass", self._profile(hard_pass, warning_pass)
        )
        warning = self._analyze(
            shape, "mixed-warning", self._profile(hard_pass, warning_fail)
        )
        failing = self._analyze(
            shape, "mixed-fail", self._profile(hard_fail, warning_fail)
        )

        self.assertEqual(passing.manufacturing.overall_status, "pass")
        self.assertEqual(warning.manufacturing.overall_status, "warning")
        self.assertEqual(failing.manufacturing.overall_status, "fail")
        self.assertEqual(
            ManufacturingAnalyzer._overall_status(
                (),
                (
                    ManufacturingWarning(
                        "warning-1",
                        "test-warning",
                        "warning",
                        "Test warning.",
                        "Explicit warning evidence.",
                    ),
                ),
            ),
            "warning",
        )

    def test_minimum_comparison_direction_and_exact_equality(self):
        """Minimum rules use >=; an incompatible direction is rejected."""
        exact = self._analyze(
            Part.makeBox(20, 20, 2),
            "minimum-equality",
            self._profile(self._constraint("minimum_thickness", 2.0)),
        )
        self.assertTrue(
            all(
                item.measured_value == item.required_value
                and item.comparison == "greater_than_or_equal"
                and item.status == "pass"
                for item in exact.manufacturing.constraint_evaluations
            )
        )

        reversed_constraint = replace(
            self._constraint("minimum_thickness", 2.0),
            comparison="less_than_or_equal",
        )
        with self.assertRaises(ConstraintEvaluationError):
            self._analyze(
                Part.makeBox(20, 20, 2),
                "reversed-minimum",
                self._profile(reversed_constraint),
            )

    def test_equivalent_ids_deduplicate_but_distinct_equal_values_remain(self):
        """Observation identity, not numeric equality, controls traceability."""
        snapshot = self._snapshot(Part.makeBox(10, 10, 2), "observation-ids")
        direction = Direction3D(0, 0, 1)
        first = Point3D(1, 1, 0)
        second = Point3D(1, 1, 2)
        thickness_a = ThicknessObservation(
            "thickness-a", first, second, direction, 2, ("face-a", "face-b")
        )
        thickness_b = replace(thickness_a, observation_id="thickness-b")
        ligament_a = MaterialLigamentObservation(
            "ligament-a", first, second, 2, "boundary-a", "boundary-b"
        )
        ligament_b = replace(ligament_a, observation_id="ligament-b")
        geometric = GeometricAnalysis(
            thickness_observations=(thickness_a, thickness_a, thickness_b),
            material_ligaments=(ligament_a, ligament_a, ligament_b),
        )
        profile = self._profile(
            self._constraint("minimum_thickness", 1),
            self._constraint("minimum_ligament_width", 1),
        )

        evaluations = ConstraintEvaluator().evaluate(
            snapshot, TopologyAnalysis(), geometric, profile
        )

        self.assertEqual(len(evaluations), 4)
        self.assertEqual(
            tuple(item.related_geometric_observation_ids[0] for item in evaluations),
            ("thickness-a", "thickness-b", "ligament-a", "ligament-b"),
        )

        conflicting = replace(thickness_a, thickness_mm=3)
        with self.assertRaises(ConstraintEvaluationError):
            ConstraintEvaluator().evaluate(
                snapshot,
                TopologyAnalysis(),
                GeometricAnalysis(
                    thickness_observations=(thickness_a, conflicting)
                ),
                self._profile(self._constraint("minimum_thickness", 1)),
            )

    def test_no_active_constraints_is_not_evaluated(self):
        """A profile without envelope or enabled rules has no implied pass."""
        report = self._analyze(
            Part.makeBox(20, 20, 1),
            "no-constraints",
            self._profile(),
        )

        self.assertEqual(report.manufacturing.constraint_evaluations, ())
        self.assertEqual(report.manufacturing.overall_status, "not_evaluated")

    def test_incompatible_units_raise_evaluation_error(self):
        """Unexpected units are never silently converted or compared."""
        profile = self._profile(
            self._constraint("minimum_thickness", 2.0, unit="inch")
        )

        with self.assertRaises(ConstraintEvaluationError):
            self._analyze(
                Part.makeBox(20, 20, 1),
                "invalid-units",
                profile,
            )

    def test_repeated_complete_analysis_is_deterministically_equal(self):
        """Profile, evaluations, rationale, and full report remain identical."""
        shape = Part.makeBox(30, 20, 8).cut(
            Part.makeCylinder(2, 8, Vector(8, 10, 0)).fuse(
                Part.makeCylinder(2, 8, Vector(20, 10, 0))
            )
        )
        profile = ProfileComposer().compose()
        snapshot = self._snapshot(shape, "manufacturing-determinism")
        analyzer = AnalyzerEngine(
            lambda resolved_id: shape,
            manufacturing_profile=profile,
        )

        first = analyzer.analyze(snapshot)
        second = analyzer.analyze(snapshot)

        self.assertEqual(ProfileComposer().compose(), profile)
        self.assertEqual(first.manufacturing, second.manufacturing)
        self.assertEqual(first, second)

    def test_profile_composition_does_not_mutate_or_cache_settings(self):
        """Composition snapshots current values without changing its source."""
        originals = (
            Settings.Printer,
            Settings.Split,
            Settings.Manufacturing,
        )
        settings = SimpleNamespace(
            Printer=Settings.Printer,
            Split=Settings.Split,
            Manufacturing=Settings.Manufacturing,
        )
        composer = ProfileComposer(settings)

        first = composer.compose()
        second = composer.compose()
        settings.Split = replace(
            settings.Split,
            MAX_PART_WIDTH=settings.Split.MAX_PART_WIDTH - 1.0,
        )
        changed = composer.compose()

        self.assertEqual(first, second)
        self.assertNotEqual(
            first.build_envelope.effective_x_mm,
            changed.build_envelope.effective_x_mm,
        )
        self.assertEqual(
            (Settings.Printer, Settings.Split, Settings.Manufacturing),
            originals,
        )

    def test_pipeline_activates_manufacturing_and_leaves_seam_default(self):
        """Topology and geometry precede manufacturing; seam stays inactive."""
        shape = Part.makeBox(30, 20, 8).cut(
            Part.makeCylinder(2, 8, Vector(8, 10, 0))
        )
        report = self._analyze(shape, "manufacturing-pipeline")

        self.assertTrue(report.topology.holes)
        self.assertTrue(report.geometric.thickness_observations)
        self.assertEqual(report.manufacturing.overall_status, "pass")
        self.assertTrue(report.manufacturing.constraint_evaluations)
        self.assertEqual(report.seam, SeamAnalysis())


if __name__ == "__main__":
    unittest.main()

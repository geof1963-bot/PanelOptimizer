# -*- coding: utf-8 -*-
"""Explainable evaluation of implemented manufacturing constraints."""

from __future__ import annotations

from collections.abc import Callable

from ..Exceptions import ConstraintEvaluationError
from ..Exceptions import ManufacturingProfileError
from ..Models import (
    ClearanceObservation,
    ConstraintEvaluation,
    GeometricAnalysis,
    GeometrySnapshot,
    ManufacturingConstraint,
    ManufacturingProfile,
    TopologyAnalysis,
)
from ._Utilities import (
    comparison_result,
    configuration_values_equal,
    finite_number,
    format_value,
    result_state,
)

__all__ = ["ConstraintEvaluator"]


class ConstraintEvaluator:
    """Evaluate only envelope, thickness, ligament, and typed clearance rules."""

    def evaluate(
        self,
        geometry: GeometrySnapshot,
        topology: TopologyAnalysis,
        geometric: GeometricAnalysis,
        profile: ManufacturingProfile,
    ) -> tuple[ConstraintEvaluation, ...]:
        """Return canonical independent evaluations for supported constraints.

        Envelope axes are emitted first in X/Y/Z order. Enabled scalar
        constraints follow profile tuple order, and their evidence follows the
        immutable upstream observation order. Unsupported constraint types and
        disabled constraints are omitted rather than given guessed semantics.
        """
        evaluations: list[ConstraintEvaluation] = []
        envelope = profile.build_envelope
        if envelope is not None:
            self._validate_envelope(envelope)
        if envelope is not None and envelope.is_enabled:
            for axis, measured, allowed in (
                ("x", geometry.width_mm, envelope.effective_x_mm),
                ("y", geometry.height_mm, envelope.effective_y_mm),
                ("z", geometry.thickness_mm, envelope.effective_z_mm),
            ):
                if allowed is None:
                    continue
                evaluations.append(
                    self._build_envelope_evaluation(
                        geometry.source_id,
                        envelope.constraint_id,
                        axis,
                        measured,
                        allowed,
                    )
                )

        hole_ids = {item.feature_id for item in topology.holes}
        for constraint_index, constraint in enumerate(
            profile.constraints,
            start=1,
        ):
            if not constraint.is_enabled:
                continue
            if constraint.constraint_type == "minimum_thickness":
                evaluations.extend(
                    self._observation_evaluations(
                        geometry.source_id,
                        "thickness",
                        constraint_index,
                        constraint,
                        geometric.thickness_observations,
                        lambda item: item.thickness_mm,
                        lambda item: item.related_feature_ids,
                        lambda item: item.source_element_ids,
                    )
                )
            elif constraint.constraint_type == "minimum_ligament_width":
                evaluations.extend(
                    self._observation_evaluations(
                        geometry.source_id,
                        "ligament",
                        constraint_index,
                        constraint,
                        geometric.material_ligaments,
                        lambda item: item.width_mm,
                        lambda item: item.related_feature_ids,
                        lambda item: item.source_element_ids,
                    )
                )
            elif constraint.constraint_type in {
                "minimum_hole_to_hole_clearance",
                "minimum_hole_to_exterior_clearance",
            }:
                matching = tuple(
                    item
                    for item in geometric.clearance_observations
                    if self._clearance_matches(
                        constraint.constraint_type,
                        item,
                        hole_ids,
                    )
                )
                evaluations.extend(
                    self._observation_evaluations(
                        geometry.source_id,
                        "clearance",
                        constraint_index,
                        constraint,
                        matching,
                        lambda item: item.clearance_mm,
                        lambda item: item.related_feature_ids,
                        lambda item: item.source_element_ids,
                    )
                )
        return tuple(evaluations)

    @staticmethod
    def _build_envelope_evaluation(
        source_id: str,
        constraint_id: str,
        axis: str,
        measured_value: object,
        allowed_value: object,
    ) -> ConstraintEvaluation:
        """Compare one snapshot extent with one configured effective extent."""
        measured = finite_number(
            measured_value,
            f"Measured {axis.upper()} extent",
        )
        allowed = finite_number(
            allowed_value,
            f"Allowed {axis.upper()} extent",
        )
        passed = comparison_result(measured, allowed, "less_than_or_equal")
        status, severity = result_state(passed, "hard", "error")
        relation = "within" if passed else "exceeds"
        return ConstraintEvaluation(
            evaluation_id=(
                f"{source_id}:manufacturing:build-envelope:{axis}"
            ),
            constraint_id=f"{constraint_id}:{axis}",
            constraint_type=f"build_envelope_{axis}",
            constraint_level="hard",
            status=status,
            measured_value=measured,
            required_value=allowed,
            unit="mm",
            comparison="less_than_or_equal",
            severity=severity,
            rationale=(
                f"Measured {axis.upper()} extent {format_value(measured)} mm "
                f"{relation} effective allowed extent "
                f"{format_value(allowed)} mm."
            ),
        )

    @staticmethod
    def _observation_evaluations(
        source_id: str,
        observation_kind: str,
        constraint_index: int,
        constraint: ManufacturingConstraint,
        observations: tuple[object, ...],
        measured_value: Callable[[object], object],
        related_feature_ids: Callable[[object], tuple[str, ...]],
        source_element_ids: Callable[[object], tuple[str, ...]],
    ) -> tuple[ConstraintEvaluation, ...]:
        """Evaluate one enabled minimum rule for every applicable observation."""
        if constraint.unit != "mm":
            raise ConstraintEvaluationError(
                f"Constraint '{constraint.constraint_id}' must use unit 'mm'."
            )
        if constraint.comparison != "greater_than_or_equal":
            raise ConstraintEvaluationError(
                f"Constraint '{constraint.constraint_id}' must use a "
                "minimum comparison."
            )
        required = finite_number(
            constraint.limit_value,
            f"Constraint '{constraint.constraint_id}' limit",
        )
        result: list[ConstraintEvaluation] = []
        seen: dict[str, object] = {}
        for observation in observations:
            observation_id = str(observation.observation_id)
            previous = seen.get(observation_id)
            if previous is not None:
                if observation != previous:
                    raise ConstraintEvaluationError(
                        f"Observation ID '{observation_id}' has conflicting values."
                    )
                continue
            seen[observation_id] = observation
            observation_index = len(result) + 1
            measured = finite_number(
                measured_value(observation),
                f"Observation '{observation.observation_id}' measurement",
            )
            passed = comparison_result(
                measured,
                required,
                constraint.comparison,
            )
            status, severity = result_state(
                passed,
                constraint.level,
                constraint.severity,
            )
            relation = "satisfies" if passed else "violates"
            result.append(
                ConstraintEvaluation(
                    evaluation_id=(
                        f"{source_id}:manufacturing:{observation_kind}:"
                        f"{constraint_index:04d}:{observation_index:04d}"
                    ),
                    constraint_id=constraint.constraint_id,
                    constraint_type=constraint.constraint_type,
                    constraint_level=constraint.level,
                    status=status,
                    measured_value=measured,
                    required_value=required,
                    unit="mm",
                    comparison=constraint.comparison,
                    severity=severity,
                    rationale=(
                        f"Measured {observation_kind} "
                        f"{format_value(measured)} mm {relation} configured "
                        f"minimum {format_value(required)} mm."
                    ),
                    related_topology_feature_ids=tuple(
                        related_feature_ids(observation)
                    ),
                    related_geometric_observation_ids=(
                        observation.observation_id,
                    ),
                    source_element_ids=tuple(source_element_ids(observation)),
                )
            )
        return tuple(result)

    @staticmethod
    def _clearance_matches(
        constraint_type: str,
        observation: ClearanceObservation,
        hole_ids: set[str],
    ) -> bool:
        """Match only the two exact clearance relationships currently encoded."""
        related = observation.related_feature_ids
        sources = observation.source_element_ids
        if constraint_type == "minimum_hole_to_hole_clearance":
            return (
                observation.relationship_type == "hole_to_hole"
                and
                len(related) == 2
                and not sources
                and all(item in hole_ids for item in related)
            )
        if constraint_type == "minimum_hole_to_exterior_clearance":
            return (
                observation.relationship_type == "hole_to_exterior"
                and
                len(related) == 1
                and related[0] in hole_ids
                and bool(sources)
                and all(":face:" in item for item in sources)
            )
        return False

    @staticmethod
    def _validate_envelope(envelope: object) -> None:
        """Reject incoherent injected envelopes before any evaluation."""
        axes = (
            (
                "X",
                envelope.physical_x_mm,
                envelope.safety_margin_x_mm,
                envelope.effective_x_mm,
            ),
            (
                "Y",
                envelope.physical_y_mm,
                envelope.safety_margin_y_mm,
                envelope.effective_y_mm,
            ),
            (
                "Z",
                envelope.physical_z_mm,
                envelope.safety_margin_z_mm,
                envelope.effective_z_mm,
            ),
        )
        for axis, physical_value, margin_value, effective_value in axes:
            configured = tuple(
                value is not None
                for value in (
                    physical_value,
                    margin_value,
                    effective_value,
                )
            )
            if not any(configured):
                continue
            if not all(configured):
                raise ManufacturingProfileError(
                    f"Build-envelope {axis} settings are only partially configured."
                )
            try:
                physical = finite_number(
                    physical_value,
                    f"Physical {axis} extent",
                )
                margin = finite_number(
                    margin_value,
                    f"{axis} safety margin",
                )
                effective = finite_number(
                    effective_value,
                    f"Effective {axis} extent",
                )
            except ConstraintEvaluationError as error:
                raise ManufacturingProfileError(str(error)) from error
            if physical <= 0.0 or effective <= 0.0 or margin < 0.0:
                raise ManufacturingProfileError(
                    f"Build-envelope {axis} extents must be positive and its "
                    "total safety margin must be non-negative."
                )
            if effective > physical:
                raise ManufacturingProfileError(
                    f"Effective {axis} extent cannot exceed its physical extent."
                )
            if not configuration_values_equal(
                margin,
                physical - effective,
            ):
                raise ManufacturingProfileError(
                    f"Build-envelope {axis} safety margin must equal physical "
                    "extent minus effective extent."
                )

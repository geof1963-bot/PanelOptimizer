# -*- coding: utf-8 -*-
"""Immutable manufacturing-profile and evaluation contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ConstraintLevel = Literal["hard", "warning"]
ConstraintComparison = Literal[
    "less_than_or_equal",
    "greater_than_or_equal",
    "equal",
    "not_applicable",
]
EvaluationStatus = Literal["pass", "warning", "fail", "not_evaluated"]
EvaluationSeverity = Literal["none", "advisory", "warning", "error"]


@dataclass(frozen=True, slots=True)
class BuildEnvelope:
    """Configured physical and effective build extents for one machine.

    Attributes:
        constraint_id: Stable profile-local identifier for build-envelope
            evaluations.
        physical_x_mm: Physical machine travel or bed extent along model X,
            in millimetres.
        physical_y_mm: Physical machine travel or bed extent along model Y,
            in millimetres.
        physical_z_mm: Physical machine travel or bed extent along model Z,
            in millimetres.
        safety_margin_x_mm: Total reserved X span, in millimetres, used when
            configuring the effective limit; it is not a per-side distance.
        safety_margin_y_mm: Total reserved Y span, in millimetres.
        safety_margin_z_mm: Total reserved Z span, in millimetres.
        effective_x_mm: Configured maximum allowed part extent along X after
            margins and any machine-specific restrictions, in millimetres.
        effective_y_mm: Configured maximum allowed part extent along Y after
            margins and restrictions, in millimetres.
        effective_z_mm: Configured maximum allowed part extent along Z after
            margins and restrictions, in millimetres.
        is_enabled: Whether a future analyzer evaluates this hard constraint.

    Physical size, reserved margin, and effective allowed size are retained as
    separate auditable configuration facts.  This model does not calculate or
    validate one from another.
    """

    constraint_id: str
    physical_x_mm: float
    physical_y_mm: float
    physical_z_mm: float
    safety_margin_x_mm: float
    safety_margin_y_mm: float
    safety_margin_z_mm: float
    effective_x_mm: float
    effective_y_mm: float
    effective_z_mm: float
    is_enabled: bool = True


@dataclass(frozen=True, slots=True)
class ManufacturingConstraint:
    """One scalar fabrication rule configured by a manufacturing profile.

    Attributes:
        constraint_id: Stable identifier unique within the profile.
        constraint_type: Extensible machine-readable type such as
            ``minimum_thickness``, ``minimum_ligament_width``, or
            ``minimum_feature_clearance``.
        level: ``hard`` when violation makes the source incompatible with the
            profile, or ``warning`` when violation describes fabrication risk.
        comparison: Required comparison between evidence and ``limit_value``.
        limit_value: Configured required or allowed scalar value.
        unit: Explicit unit for the limit and future measured value, such as
            ``mm``, ``degrees``, ``1/mm``, ``count``, or ``dimensionless``.
        severity: Severity assigned by a future analyzer when the constraint
            is violated. Hard constraints normally use ``error``.
        description: Human-readable explanation of the configured rule.
        is_enabled: Whether a future analyzer evaluates this constraint.

    Constraint types remain extensible for different fabrication processes.
    No project or printer limit is embedded in this contract.
    """

    constraint_id: str
    constraint_type: str
    level: ConstraintLevel
    comparison: ConstraintComparison
    limit_value: float
    unit: str
    severity: Literal["advisory", "warning", "error"]
    description: str
    is_enabled: bool = True


@dataclass(frozen=True, slots=True)
class ManufacturingProfile:
    """Versioned immutable input for future manufacturing interpretation.

    Attributes:
        profile_id: Stable identifier for the machine/process configuration.
        profile_version: Version of the profile's fabrication rules.
        settings_version: Version or revision of the centralized configured
            settings from which this immutable profile snapshot was built.
        display_name: Human-readable profile name.
        process_type: Process identifier such as ``fdm``; it is descriptive
            configuration, not a hard-coded analyzer branch.
        build_envelope: Optional focused physical/effective envelope contract.
        constraints: Ordered scalar hard constraints and warning rules.
        notes: Ordered profile documentation strings.

    The centralized Settings system remains the configured-value source.  A
    future composition layer will snapshot those values into this contract and
    inject it into manufacturing analysis; the model itself reads no globals.
    """

    profile_id: str
    profile_version: str
    settings_version: str
    display_name: str
    process_type: str
    build_envelope: BuildEnvelope | None = None
    constraints: tuple[ManufacturingConstraint, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ConstraintEvaluation:
    """One explainable comparison of geometric evidence with a constraint.

    Attributes:
        evaluation_id: Deterministic identifier using
            ``{source_id}:manufacturing:evaluation:{index:04d}`` in canonical
            constraint and evidence order.
        constraint_id: ID of the profile constraint being evaluated.
        constraint_type: Snapshotted machine-readable constraint type.
        constraint_level: ``hard`` or ``warning`` from the profile.
        status: Explicit ``pass``, ``warning``, ``fail``, or
            ``not_evaluated`` result. This is not a score.
        measured_value: Consumed geometric measurement, or ``None`` when the
            rule has no reliable evidence.
        required_value: Configured required or allowed value, or ``None`` for
            a non-scalar descriptive risk evaluation.
        unit: Unit shared by measured and required values.
        comparison: Comparison rule captured for standalone explainability.
        severity: Result severity. Passing results normally use ``none``;
            hard failures normally use ``error``.
        rationale: Human-readable explanation of evidence and result.
        related_topology_feature_ids: Referenced TopologyAnalysis feature IDs.
        related_geometric_observation_ids: Referenced GeometricAnalysis
            observation IDs, including thickness, ligament, and clearance.
        source_element_ids: Stable source face, edge, or vertex IDs when an
            upstream observation reference is insufficient.

    Geometry is referenced by stable IDs rather than duplicated coordinates or
    FreeCAD objects.
    """

    evaluation_id: str
    constraint_id: str
    constraint_type: str
    constraint_level: ConstraintLevel
    status: EvaluationStatus
    measured_value: float | None
    required_value: float | None
    unit: str
    comparison: ConstraintComparison
    severity: EvaluationSeverity
    rationale: str
    related_topology_feature_ids: tuple[str, ...] = ()
    related_geometric_observation_ids: tuple[str, ...] = ()
    source_element_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ManufacturingWarning:
    """One non-fatal fabrication concern backed by explicit evidence.

    Attributes:
        warning_id: Deterministic identifier using
            ``{source_id}:manufacturing:warning:{index:04d}``.
        warning_type: Stable machine-readable warning category.
        severity: Non-fatal ``advisory`` or ``warning`` severity.
        message: Concise human-readable concern.
        rationale: Explainable reason the concern was emitted.
        evaluation_ids: Constraint evaluations supporting the warning.
        related_topology_feature_ids: Referenced topology feature IDs.
        related_geometric_observation_ids: Referenced geometric evidence IDs.
        source_element_ids: Stable source topology element references.

    Hard failures belong in ``ConstraintEvaluation`` with ``status="fail"``;
    they are not disguised as warnings. Geometry is not duplicated here.
    """

    warning_id: str
    warning_type: str
    severity: Literal["advisory", "warning"]
    message: str
    rationale: str
    evaluation_ids: tuple[str, ...] = ()
    related_topology_feature_ids: tuple[str, ...] = ()
    related_geometric_observation_ids: tuple[str, ...] = ()
    source_element_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ManufacturingAnalysis:
    """Immutable interpretation against one versioned fabrication profile.

    Attributes:
        profile_id: Profile identifier used for the evaluations, or ``None``
            when the stage has not run.
        profile_version: Evaluated fabrication-rule version, or ``None``.
        settings_version: Evaluated centralized-settings revision, or
            ``None``.
        overall_status: Derived ``pass``, ``warning``, or ``fail`` result;
            ``not_evaluated`` is the exact inactive-stage default.
        constraint_evaluations: Ordered explainable hard/warning evaluations.
        warnings: Ordered non-fatal fabrication concerns.

    ``overall_status`` will be derived solely from explicit evaluations when
    the stage is implemented; it is never a score.
    """

    profile_id: str | None = None
    profile_version: str | None = None
    settings_version: str | None = None
    overall_status: EvaluationStatus = "not_evaluated"
    constraint_evaluations: tuple[ConstraintEvaluation, ...] = ()
    warnings: tuple[ManufacturingWarning, ...] = ()

# -*- coding: utf-8 -*-
"""Immutable seam-policy and seam-placement evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


SeamConstraintLevel = Literal["hard", "advisory"]
SeamZoneCategory = Literal[
    "allowed",
    "preferred",
    "discouraged",
    "forbidden",
]
SeamWarningSeverity = Literal["advisory", "warning"]


@dataclass(frozen=True, slots=True)
class SeamConstraint:
    """One non-scoring rule declaration in an immutable seam profile.

    Attributes:
        constraint_id: Stable identifier unique within the profile.
        constraint_type: Extensible rule-family name, such as
            ``hole_avoidance`` or ``boundary_following``.
        level: ``hard`` for a traversal prohibition or ``advisory`` for
            descriptive guidance.
        category: Zone category emitted when future analysis proves the rule.
            Hard constraints use ``forbidden``. Advisory constraints use
            ``allowed``, ``preferred``, or ``discouraged``.
        description: Human-readable meaning of the rule.
        is_enabled: Whether future seam analysis applies the rule.

    The contract intentionally contains no threshold, weight, score, path
    cost, or printer setting. A future profile composer or analyzer must reject
    inconsistent ``level`` and ``category`` combinations.
    """

    constraint_id: str
    constraint_type: str
    level: SeamConstraintLevel
    category: SeamZoneCategory
    description: str
    is_enabled: bool = True


@dataclass(frozen=True, slots=True)
class SeamProfile:
    """Versioned immutable policy input for future seam interpretation.

    Attributes:
        profile_id: Stable identity of the seam policy.
        profile_version: Version of the policy's rule definitions.
        settings_version: Revision of centralized settings from which the
            profile was composed.
        display_name: Human-readable policy name.
        constraints: Deterministically ordered seam constraints.
        notes: Ordered policy documentation strings.

    This profile enables rule families only. Manufacturing thresholds remain
    in ``ManufacturingProfile`` and scoring weights remain in scoring models.
    """

    profile_id: str
    profile_version: str
    settings_version: str
    display_name: str
    constraints: tuple[SeamConstraint, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SeamEvidence:
    """One seam-specific interpretation backed by immutable upstream IDs.

    Attributes:
        evidence_id: Deterministic ID using
            ``{source_id}:seam:evidence:{index:04d}`` in canonical profile-rule
            and upstream-evidence order.
        evidence_type: Descriptive evidence family, such as
            ``cavity_presence``, ``manufacturing_failure``, or
            ``boundary_alignment``.
        rationale: Explainable statement of the seam relevance established by
            a future rule, without ranking or selecting a route.
        related_topology_feature_ids: Referenced ``TopologyAnalysis`` feature
            or region IDs.
        related_geometric_observation_ids: Referenced ``GeometricAnalysis``
            observation IDs.
        related_manufacturing_evaluation_ids: Referenced
            ``ManufacturingAnalysis`` evaluation IDs. Manufacturing facts are
            not copied or recalculated.
        source_element_ids: Stable source face, edge, or vertex IDs.

    Evidence describes why a source region matters to seam placement. It does
    not itself permit, prohibit, score, or geometrically route a seam.
    """

    evidence_id: str
    evidence_type: str
    rationale: str
    related_topology_feature_ids: tuple[str, ...] = ()
    related_geometric_observation_ids: tuple[str, ...] = ()
    related_manufacturing_evaluation_ids: tuple[str, ...] = ()
    source_element_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SeamZone:
    """A categorized source region or relationship relevant to seam placement.

    Attributes:
        zone_id: Deterministic ID using
            ``{source_id}:seam:zone:{index:04d}`` in canonical constraint and
            evidence order.
        constraint_id: Profile constraint responsible for the category.
        category: ``allowed`` for an explicitly evaluated permissible region,
            ``preferred`` or ``discouraged`` for advisory guidance, or
            ``forbidden`` for a hard traversal prohibition. Absence of a zone
            never implies that a region is allowed.
        rationale: Explainable seam-specific interpretation.
        evidence_ids: Ordered ``SeamEvidence`` IDs supporting the zone.
        region_reference_ids: Stable upstream feature, observation, or source
            element IDs that locate the relevant region or relationship.

    Exact upstream identities are retained instead of copied boundary points
    or generic freeform geometry. This is a static classified region, not a
    candidate route, path segment, or ranked alternative.
    """

    zone_id: str
    constraint_id: str
    category: SeamZoneCategory
    rationale: str
    evidence_ids: tuple[str, ...]
    region_reference_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SeamWarning:
    """One non-fatal problem or ambiguity in seam-specific interpretation.

    Attributes:
        warning_id: Deterministic ID using
            ``{source_id}:seam:warning:{index:04d}``.
        warning_type: Stable seam-warning family.
        severity: Non-fatal ``advisory`` or ``warning`` severity.
        message: Concise human-readable warning.
        rationale: Explainable reason the warning was emitted.
        constraint_ids: Seam-profile constraints associated with the warning.
        evidence_ids: Seam evidence associated with the warning.
        zone_ids: Seam zones associated with the warning.

    This contract does not duplicate ``ManufacturingWarning``. It is reserved
    for seam-analysis ambiguity or unavailable seam-specific evidence.
    """

    warning_id: str
    warning_type: str
    severity: SeamWarningSeverity
    message: str
    rationale: str
    constraint_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    zone_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SeamAnalysis:
    """Immutable non-scoring seam-placement guidance for one profile.

    Attributes:
        profile_id: Seam-profile ID used by analysis, or ``None`` while the
            stage is inactive.
        profile_version: Evaluated seam-policy version, or ``None``.
        settings_version: Evaluated centralized-settings revision, or
            ``None``.
        evidence: Ordered seam-specific interpretations of upstream facts.
        zones: Ordered allowed, preferred, discouraged, or forbidden regions.
        warnings: Ordered non-fatal seam-analysis warnings.

    The exact inactive-stage default contains ``None`` provenance and empty
    tuples. This report contains no generated path, score, ranking, split plan,
    joinery, or export state.
    """

    profile_id: str | None = None
    profile_version: str | None = None
    settings_version: str | None = None
    evidence: tuple[SeamEvidence, ...] = ()
    zones: tuple[SeamZone, ...] = ()
    warnings: tuple[SeamWarning, ...] = ()

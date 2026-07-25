# -*- coding: utf-8 -*-
"""Immutable local clearance and feature-proximity observations."""

from __future__ import annotations

from dataclasses import dataclass

from .Common import Point3D


@dataclass(frozen=True, slots=True)
class ClearanceObservation:
    """One local separation between two distinct source boundaries.

    Attributes:
        observation_id: Deterministic ID using
            ``{source_id}:geometry:clearance:{index:04d}`` in canonical
            source-boundary order.
        first_boundary_point: Closest point on the first boundary, in model
            coordinates and mm.
        second_boundary_point: Closest point on the second boundary, in model
            coordinates and mm.
        clearance_mm: Direct boundary-to-boundary separation, in mm.  The
            intervening region may be material or empty space; this record does
            not classify it.
        source_element_ids: Deterministic IDs of directly measured source faces
            or edges.  The tuple may be empty when both boundaries are already
            represented by ``related_feature_ids``.
        related_feature_ids: Topology feature IDs intersecting or bounded by
            the measured clearance.

    This is a local geometric gap.  It is not center-to-center distance, a
    manufacturing allowance, or a statement that the clearance is sufficient.
    """

    observation_id: str
    first_boundary_point: Point3D
    second_boundary_point: Point3D
    clearance_mm: float
    source_element_ids: tuple[str, ...]
    related_feature_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FeatureProximityObservation:
    """The nearest known relationship between two topology features.

    Attributes:
        observation_id: Deterministic ID using
            ``{source_id}:geometry:proximity:{index:04d}``, ordered by the
            canonical pair of feature IDs.
        first_feature_id: First referenced TopologyAnalysis feature ID.
        second_feature_id: Second referenced TopologyAnalysis feature ID.
        first_point: Nearest point on the first feature, in model coordinates
            and mm.
        second_point: Nearest point on the second feature, in model coordinates
            and mm.
        distance_mm: Euclidean separation of the two nearest points, in mm.

    Unlike ``ClearanceObservation``, this record relates semantic topology
    features rather than arbitrary material boundaries.  It is a pair-local
    relationship even when the two features are far apart in the source.
    """

    observation_id: str
    first_feature_id: str
    second_feature_id: str
    first_point: Point3D
    second_point: Point3D
    distance_mm: float

# -*- coding: utf-8 -*-
"""Immutable local material-thickness observations."""

from __future__ import annotations

from dataclasses import dataclass

from .Common import Direction3D, Point3D


@dataclass(frozen=True, slots=True)
class ThicknessObservation:
    """One local separation between opposite material boundaries.

    Attributes:
        observation_id: Deterministic ID using
            ``{source_id}:geometry:thickness:{index:04d}``, where the index
            follows canonical source-topology order.
        first_boundary_point: First model-coordinate boundary point, in mm.
        second_boundary_point: Opposite model-coordinate boundary point, in mm.
        direction: Unit direction from the first point to the second.
        thickness_mm: Local boundary-to-boundary distance, in mm.
        source_element_ids: Deterministic IDs of the measured source faces or
            edges, in endpoint order.
        related_feature_ids: Topology feature IDs associated with the local
            observation, or an empty tuple.

    This is a local observation.  It does not repeat the global panel thickness
    stored by :class:`GeometrySnapshot`.
    """

    observation_id: str
    first_boundary_point: Point3D
    second_boundary_point: Point3D
    direction: Direction3D
    thickness_mm: float
    source_element_ids: tuple[str, ...]
    related_feature_ids: tuple[str, ...] = ()

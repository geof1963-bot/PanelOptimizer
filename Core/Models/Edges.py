# -*- coding: utf-8 -*-
"""Immutable local edge and corner observations."""

from __future__ import annotations

from dataclasses import dataclass

from .Common import Point3D


@dataclass(frozen=True, slots=True)
class EdgeObservation:
    """Measured characteristics of one source edge.

    Attributes:
        observation_id: Deterministic ID using
            ``{source_id}:geometry:edge:{index:04d}``, matching canonical
            source-edge order.
        source_edge_id: Stable source-topology edge identifier.
        start_point: Edge start in model coordinates and mm.  For a closed
            edge, this equals the deterministic seam point.
        end_point: Edge end in model coordinates and mm.  For a closed edge,
            this equals ``start_point``.
        length_mm: Total edge length, in mm.
        curve_type: Descriptive curve family such as ``line``, ``circle``,
            ``ellipse``, or ``spline``; it is not a quality classification.
        is_closed: Whether the edge forms a closed loop.
        related_feature_ids: Topology feature IDs using this edge.

    This is a local observation of an existing edge, not a seam candidate.
    """

    observation_id: str
    source_edge_id: str
    start_point: Point3D
    end_point: Point3D
    length_mm: float
    curve_type: str
    is_closed: bool
    related_feature_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CornerObservation:
    """Measured angular relationship at one source vertex.

    Attributes:
        observation_id: Deterministic ID using
            ``{source_id}:geometry:corner:{index:04d}``, matching canonical
            source-vertex order.
        source_vertex_id: Stable source-topology vertex identifier.
        position: Vertex position in model coordinates and mm.
        angle_degrees: Observed local included angle between directions away
            from the vertex, in the inclusive range 0 through 180 degrees.
        incident_edge_ids: Stable source edge IDs participating in the angle.
        related_feature_ids: Topology feature IDs containing the corner.

    Canonical edge ordering affects only identifier order, not the outward
    directions or angle.  This local angle carries no sharpness threshold or
    manufacturing verdict.
    """

    observation_id: str
    source_vertex_id: str
    position: Point3D
    angle_degrees: float
    incident_edge_ids: tuple[str, ...]
    related_feature_ids: tuple[str, ...] = ()

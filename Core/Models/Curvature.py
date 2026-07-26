# -*- coding: utf-8 -*-
"""Immutable curvature and flat-region observations."""

from __future__ import annotations

from dataclasses import dataclass

from .Common import BoundingBox, Direction3D, Point3D


@dataclass(frozen=True, slots=True)
class CurvatureObservation:
    """Principal surface curvatures at one local source-face position.

    Attributes:
        observation_id: Deterministic ID using
            ``{source_id}:geometry:curvature:{index:04d}`` in canonical
            source-face and sample order.
        source_face_id: Stable source-topology face identifier.
        location: Sample position in model coordinates and mm.
        normal: Unit surface normal in model coordinates, canonicalized so
            its first non-zero component is positive.
        first_principal_direction: Unit direction of the first principal
            curvature in model coordinates.
        second_principal_direction: Unit direction of the second principal
            curvature in model coordinates.
        first_principal_curvature_per_mm: Signed first principal curvature,
            in inverse millimetres and relative to ``normal``.
        second_principal_curvature_per_mm: Signed second principal curvature,
            in inverse millimetres and relative to ``normal``.
        related_feature_ids: Topology feature IDs containing the sample.

    This is a local differential observation.  It contains no curvature score
    or acceptable-radius decision.
    """

    observation_id: str
    source_face_id: str
    location: Point3D
    normal: Direction3D
    first_principal_direction: Direction3D
    second_principal_direction: Direction3D
    first_principal_curvature_per_mm: float
    second_principal_curvature_per_mm: float
    related_feature_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FlatRegionObservation:
    """One locally planar, connected source-face region.

    Attributes:
        observation_id: Deterministic ID using
            ``{source_id}:geometry:flat-region:{index:04d}`` in canonical
            source-face order.
        center: Area centroid in model coordinates and mm.
        normal: Unit region normal in model coordinates.
        bounding_box: Axis-aligned model-coordinate region bounds.
        area_mm2: Region surface area, in square millimetres.
        source_face_ids: Stable IDs of the planar source faces in the region.
        boundary_edge_ids: Stable IDs of edges bounding the region.
        related_feature_ids: Topology feature IDs overlapping the region.

    Flatness is a measured surface characteristic, not a declaration that the
    region is printable or suitable for a seam.
    """

    observation_id: str
    center: Point3D
    normal: Direction3D
    bounding_box: BoundingBox
    area_mm2: float
    source_face_ids: tuple[str, ...]
    boundary_edge_ids: tuple[str, ...]
    related_feature_ids: tuple[str, ...] = ()

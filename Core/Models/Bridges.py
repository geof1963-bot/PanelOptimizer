# -*- coding: utf-8 -*-
"""Immutable narrow-material-bridge observations."""

from __future__ import annotations

from dataclasses import dataclass

from .Common import BoundingBox, Point3D


@dataclass(frozen=True, slots=True)
class ThinBridgeFeature:
    """One locally narrow material connection between larger regions.

    Attributes:
        feature_id: Deterministic ID using
            ``{source_id}:geometry:bridge:{index:04d}`` in canonical
            source-region order.
        start: First endpoint of the bridge centerline, in model coordinates
            and mm.
        end: Second endpoint of the bridge centerline, in model coordinates
            and mm.
        bounding_box: Axis-aligned model-coordinate bounds of the bridge.
        length_mm: Centerline endpoint distance, in mm.
        minimum_width_mm: Smallest observed in-plane material width, in mm.
        minimum_thickness_mm: Smallest observed through-material thickness,
            in mm.
        source_element_ids: Deterministic IDs of contributing source faces,
            edges, or vertices.
        related_feature_ids: Topology feature IDs adjacent to the bridge.

    The word ``thin`` names the observed narrow region; it does not express a
    manufacturing failure or threshold comparison.
    """

    feature_id: str
    start: Point3D
    end: Point3D
    bounding_box: BoundingBox
    length_mm: float
    minimum_width_mm: float
    minimum_thickness_mm: float
    source_element_ids: tuple[str, ...] = ()
    related_feature_ids: tuple[str, ...] = ()

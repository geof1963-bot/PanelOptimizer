# -*- coding: utf-8 -*-
"""Geometry data contracts exchanged by future PanelOptimizer engines."""

from __future__ import annotations

from dataclasses import dataclass

from .Common import BoundingBox, Point3D


@dataclass(frozen=True, slots=True)
class GeometrySnapshot:
    """A validated, FreeCAD-independent description of a source geometry."""

    source_id: str
    source_label: str
    bounding_box: BoundingBox
    center: Point3D
    width_mm: float
    height_mm: float
    thickness_mm: float
    area_mm2: float
    volume_mm3: float
    solid_count: int
    face_count: int
    edge_count: int
    vertex_count: int
    validation_messages: tuple[str, ...] = ()

# -*- coding: utf-8 -*-
"""Analysis data contracts exchanged by future PanelOptimizer engines."""

from __future__ import annotations

from dataclasses import dataclass

from .Common import BoundingBox, Direction3D, Point3D
from .Geometry import GeometrySnapshot


@dataclass(frozen=True, slots=True)
class HoleFeature:
    """A detected circular opening or recess in the source geometry."""

    feature_id: str
    center: Point3D
    axis: Direction3D
    diameter_mm: float
    depth_mm: float
    is_through_hole: bool


@dataclass(frozen=True, slots=True)
class IslandFeature:
    """A detected isolated geometric region."""

    feature_id: str
    bounding_box: BoundingBox
    center: Point3D
    area_mm2: float


@dataclass(frozen=True, slots=True)
class CorridorFeature:
    """A detected narrow region that may inform a seam-path decision."""

    feature_id: str
    start: Point3D
    end: Point3D
    length_mm: float
    minimum_width_mm: float


@dataclass(frozen=True, slots=True)
class AnalysisReport:
    """The immutable result of analyzing one geometry snapshot."""

    geometry: GeometrySnapshot
    holes: tuple[HoleFeature, ...] = ()
    islands: tuple[IslandFeature, ...] = ()
    corridors: tuple[CorridorFeature, ...] = ()
    printability_issues: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

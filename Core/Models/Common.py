# -*- coding: utf-8 -*-
"""Shared immutable value objects for PanelOptimizer data models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Point3D:
    """A point in model coordinates, expressed in millimetres."""

    x_mm: float
    y_mm: float
    z_mm: float


@dataclass(frozen=True, slots=True)
class Direction3D:
    """A direction expressed as three dimensionless vector components."""

    x: float
    y: float
    z: float


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """The minimum and maximum corners of an axis-aligned bounding box."""

    minimum: Point3D
    maximum: Point3D

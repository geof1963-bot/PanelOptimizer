# -*- coding: utf-8 -*-
"""Shared conversion helpers for read-only topology components."""

from __future__ import annotations

import math

from ..Exceptions import TopologyAnalysisError
from ..Models import BoundingBox, Point3D


def bounding_box(shape: object) -> BoundingBox:
    """Convert a FreeCAD-like bound box into immutable value objects."""
    try:
        bounds = shape.BoundBox
        values = (
            finite_float(bounds.XMin, "bounding-box X minimum"),
            finite_float(bounds.YMin, "bounding-box Y minimum"),
            finite_float(bounds.ZMin, "bounding-box Z minimum"),
            finite_float(bounds.XMax, "bounding-box X maximum"),
            finite_float(bounds.YMax, "bounding-box Y maximum"),
            finite_float(bounds.ZMax, "bounding-box Z maximum"),
        )
    except AttributeError as error:
        raise TopologyAnalysisError(
            "Topology bounding box is unavailable."
        ) from error
    return BoundingBox(
        minimum=Point3D(*values[:3]),
        maximum=Point3D(*values[3:]),
    )


def finite_float(value: object, label: str) -> float:
    """Convert a topological measurement and reject non-finite values."""
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise TopologyAnalysisError(
            f"Topology {label} is not numeric."
        ) from error
    if not math.isfinite(result):
        raise TopologyAnalysisError(
            f"Topology {label} is not finite."
        )
    return result


def identifier(source_id: str, kind: str, index: int) -> str:
    """Create a deterministic identifier from source topology order."""
    return f"{source_id}:{kind}:{index:04d}"


def point(vector: object, label: str) -> Point3D:
    """Convert a vector-like value into an immutable finite point."""
    try:
        values = float(vector.x), float(vector.y), float(vector.z)
    except (AttributeError, TypeError, ValueError) as error:
        raise TopologyAnalysisError(
            f"Topology contains an unreadable {label}."
        ) from error
    if not all(math.isfinite(value) for value in values):
        raise TopologyAnalysisError(
            f"Topology contains a non-finite {label}."
        )
    return Point3D(*values)


def same_shape(first: object, second: object) -> bool:
    """Compare topology identity without retaining either object."""
    if first is second:
        return True
    if first is None or second is None:
        return False
    is_same = getattr(first, "isSame", None)
    if callable(is_same):
        try:
            return bool(is_same(second))
        except (TypeError, RuntimeError):
            return False
    return False

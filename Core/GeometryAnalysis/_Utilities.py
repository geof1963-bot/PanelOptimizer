# -*- coding: utf-8 -*-
"""Shared read-only B-rep utilities for local geometric measurements."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..Models import Direction3D, Point3D

# OpenCASCADE-scale comparison tolerance used only for coincident lengths and
# point-on-boundary classification.  It is not a manufacturing tolerance.
LINEAR_COMPARISON_TOLERANCE_MM = 1.0e-7

# Dimensionless tolerance used only when comparing normalized directions.
# It is unrelated to printer, material, or process requirements.
DIRECTION_COMPARISON_TOLERANCE = 1.0e-9

# Deterministic UV-domain locations used to find a valid point on a trimmed
# planar face.  They select a measurement location; they do not approximate the
# resulting boundary-to-boundary distance.
PLANAR_SAMPLE_FRACTIONS = (0.5, 0.25, 0.75)


@dataclass(frozen=True, slots=True)
class PlanarFace:
    """Internal read-only description of one source planar face."""

    face: object
    source_face_id: str
    source_index: int
    owner_solid_index: int
    is_outer_boundary: bool
    normal: Direction3D
    plane_point: Point3D


def collect_planar_faces(source_id: str, shape: object) -> tuple[PlanarFace, ...]:
    """Return source-ordered planar faces with stable IDs and solid ownership."""
    solids = tuple(getattr(shape, "Solids", ()))
    collected: list[PlanarFace] = []
    for source_index, face in enumerate(
        getattr(shape, "Faces", ()),
        start=1,
    ):
        if "plane" not in type(getattr(face, "Surface", None)).__name__.lower():
            continue
        owner_index = owner_solid_index(face, solids)
        if owner_index is None:
            continue
        outer_shell = getattr(solids[owner_index], "OuterShell", None)
        outer_faces = tuple(getattr(outer_shell, "Faces", ()))
        normal = face_normal(face)
        collected.append(
            PlanarFace(
                face=face,
                source_face_id=(
                    f"{source_id}:face:{source_index:04d}"
                ),
                source_index=source_index,
                owner_solid_index=owner_index,
                is_outer_boundary=any(
                    same_shape(face, outer_face)
                    for outer_face in outer_faces
                ),
                normal=normal,
                plane_point=to_point(face.CenterOfMass),
            )
        )
    return tuple(collected)


def face_normal(face: object) -> Direction3D:
    """Read a normalized, orientation-aware face normal."""
    parameter_range = tuple(face.ParameterRange)
    u_value = (float(parameter_range[0]) + float(parameter_range[1])) / 2.0
    v_value = (float(parameter_range[2]) + float(parameter_range[3])) / 2.0
    vector = face.normalAt(u_value, v_value)
    magnitude = float(vector.Length)
    if magnitude <= DIRECTION_COMPARISON_TOLERANCE:
        return Direction3D(0.0, 0.0, 0.0)
    return Direction3D(
        float(vector.x) / magnitude,
        float(vector.y) / magnitude,
        float(vector.z) / magnitude,
    )


def face_sample_points(face: object) -> tuple[object, ...]:
    """Return deterministic exact points lying inside a trimmed planar face.

    The face center of mass is considered first, followed by a fixed 3-by-3
    sequence of UV-domain fractions in nested tuple order.  Candidates are
    retained only when the B-rep face accepts them and duplicate coordinates
    are removed without reordering.  These points locate an exact measurement;
    they never approximate its distance.  If none is valid, an empty tuple
    causes the calling analyzer to omit that face pair.
    """
    candidates: list[object] = [face.CenterOfMass]
    u_min, u_max, v_min, v_max = (
        float(value) for value in face.ParameterRange
    )
    for u_fraction in PLANAR_SAMPLE_FRACTIONS:
        for v_fraction in PLANAR_SAMPLE_FRACTIONS:
            candidates.append(
                face.valueAt(
                    u_min + (u_max - u_min) * u_fraction,
                    v_min + (v_max - v_min) * v_fraction,
                )
            )

    accepted: list[object] = []
    for candidate in candidates:
        if not face.isInside(
            candidate,
            LINEAR_COMPARISON_TOLERANCE_MM,
            True,
        ):
            continue
        if any(
            points_close(to_point(candidate), to_point(known))
            for known in accepted
        ):
            continue
        accepted.append(candidate)
    return tuple(accepted)


def vector_like(reference: object, point: Point3D) -> object:
    """Create a transient vector of the same runtime type as a shape vector."""
    return type(reference)(point.x_mm, point.y_mm, point.z_mm)


def to_point(vector: object) -> Point3D:
    """Convert a transient FreeCAD-like vector into an immutable model point."""
    return Point3D(
        x_mm=float(vector.x),
        y_mm=float(vector.y),
        z_mm=float(vector.z),
    )


def distance(first: Point3D, second: Point3D) -> float:
    """Return Euclidean model-space distance in millimetres."""
    return math.sqrt(
        (second.x_mm - first.x_mm) ** 2
        + (second.y_mm - first.y_mm) ** 2
        + (second.z_mm - first.z_mm) ** 2
    )


def points_close(first: Point3D, second: Point3D) -> bool:
    """Compare model points using the centralized kernel tolerance."""
    return (
        math.isclose(
            first.x_mm,
            second.x_mm,
            rel_tol=0.0,
            abs_tol=LINEAR_COMPARISON_TOLERANCE_MM,
        )
        and math.isclose(
            first.y_mm,
            second.y_mm,
            rel_tol=0.0,
            abs_tol=LINEAR_COMPARISON_TOLERANCE_MM,
        )
        and math.isclose(
            first.z_mm,
            second.z_mm,
            rel_tol=0.0,
            abs_tol=LINEAR_COMPARISON_TOLERANCE_MM,
        )
    )


def direction_is_vertical(direction: Direction3D) -> bool:
    """Return whether a normalized direction is parallel to model Z."""
    return (
        math.isclose(
            direction.x,
            0.0,
            rel_tol=0.0,
            abs_tol=DIRECTION_COMPARISON_TOLERANCE,
        )
        and math.isclose(
            direction.y,
            0.0,
            rel_tol=0.0,
            abs_tol=DIRECTION_COMPARISON_TOLERANCE,
        )
        and math.isclose(
            abs(direction.z),
            1.0,
            rel_tol=0.0,
            abs_tol=DIRECTION_COMPARISON_TOLERANCE,
        )
    )


def direction_is_axis_aligned_horizontal(direction: Direction3D) -> bool:
    """Return whether a normalized direction is parallel to model X or Y."""
    x_aligned = math.isclose(
        abs(direction.x),
        1.0,
        rel_tol=0.0,
        abs_tol=DIRECTION_COMPARISON_TOLERANCE,
    ) and math.isclose(
        direction.y,
        0.0,
        rel_tol=0.0,
        abs_tol=DIRECTION_COMPARISON_TOLERANCE,
    )
    y_aligned = math.isclose(
        abs(direction.y),
        1.0,
        rel_tol=0.0,
        abs_tol=DIRECTION_COMPARISON_TOLERANCE,
    ) and math.isclose(
        direction.x,
        0.0,
        rel_tol=0.0,
        abs_tol=DIRECTION_COMPARISON_TOLERANCE,
    )
    return (
        math.isclose(
            direction.z,
            0.0,
            rel_tol=0.0,
            abs_tol=DIRECTION_COMPARISON_TOLERANCE,
        )
        and (x_aligned or y_aligned)
    )


def material_segment_is_complete(
    solids: tuple[object, ...],
    first_vector: object,
    second_vector: object,
    expected_length_mm: float,
    owner_solid_index: int | None = None,
) -> bool:
    """Verify that one exact boundary segment is wholly contained in material.

    A transient line is intersected with a forward-oriented copy of the
    resolved solid.  Equality of the resulting length, plus strict inclusion
    of the segment midpoint, proves that no hole, cavity, inter-solid void, or
    coincident boundary substitutes for continuous material.
    """
    try:
        import Part
    except ImportError:
        return False

    line = Part.makeLine(first_vector, second_vector)
    candidate_solids = (
        (solids[owner_solid_index],)
        if owner_solid_index is not None
        else solids
    )
    midpoint = type(first_vector)(
        (float(first_vector.x) + float(second_vector.x)) / 2.0,
        (float(first_vector.y) + float(second_vector.y)) / 2.0,
        (float(first_vector.z) + float(second_vector.z)) / 2.0,
    )
    for source_solid in candidate_solids:
        solid = source_solid
        if str(getattr(source_solid, "Orientation", "")) == "Reversed":
            solid = source_solid.copy()
            solid.reverse()
        if not solid.isInside(
            midpoint,
            LINEAR_COMPARISON_TOLERANCE_MM,
            False,
        ):
            continue
        if math.isclose(
            float(solid.common(line).Length),
            expected_length_mm,
            rel_tol=0.0,
            abs_tol=LINEAR_COMPARISON_TOLERANCE_MM,
        ):
            return True
    return False


def owner_solid_index(
    face: object,
    solids: tuple[object, ...],
) -> int | None:
    """Return source-order owner index for a face, when one exists."""
    for owner_index, solid in enumerate(solids):
        if any(same_shape(face, candidate) for candidate in solid.Faces):
            return owner_index
    return None


def same_shape(first: object, second: object) -> bool:
    """Compare B-rep topology identity without storing it in a model."""
    if first is second:
        return True
    is_same = getattr(first, "isSame", None)
    if callable(is_same):
        try:
            return bool(is_same(second))
        except (RuntimeError, TypeError):
            return False
    return False

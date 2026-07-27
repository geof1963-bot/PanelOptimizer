# -*- coding: utf-8 -*-
"""Narrow transient reconstruction for proven off-plane planar boundaries.

This module supports exactly one defect family: an otherwise closed one-shell
solid whose invalid faces are horizontal planes on one common plane and whose
valid closed wires contain valid edges departing slightly from that plane.
Only departing edges are projected exactly onto the plane.  No generic repair,
healing, tolerance mutation, refinement, meshing, or boolean is used.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .GeometryAnalysis._Utilities import (
    DIRECTION_COMPARISON_TOLERANCE,
    LINEAR_COMPARISON_TOLERANCE_MM,
)
from .SplittingUtilities import volume_tolerance_mm3

# The supported defect observed in FINAL_PANEL departs by at most about
# 0.0120032 mm.  This geometry-only ceiling prevents the targeted operation
# from becoming an unrestricted projection repair.
MAX_SUPPORTED_BOUNDARY_DEPARTURE_MM = 0.0121
TARGETED_EQUIVALENCE_TOLERANCE_MM = LINEAR_COMPARISON_TOLERANCE_MM
PROJECTION_TARGET_SCALE = 3.0

__all__ = [
    "MAX_SUPPORTED_BOUNDARY_DEPARTURE_MM",
    "TARGETED_EQUIVALENCE_TOLERANCE_MM",
    "TargetedReconstructionOutcome",
    "TargetedReconstructionProvenance",
    "attempt_targeted_planar_reconstruction",
]


@dataclass(frozen=True, slots=True)
class TargetedReconstructionProvenance:
    """Immutable scalar provenance for one accepted transient result."""

    rebuilt_face_ids: tuple[str, ...]
    rebuilt_face_count: int
    maximum_original_boundary_departure_mm: float
    maximum_geometric_displacement_mm: float
    original_volume_mm3: float
    reconstructed_volume_mm3: float
    volume_delta_mm3: float


@dataclass(frozen=True, slots=True)
class TargetedReconstructionOutcome:
    """Runtime result; the transient FreeCAD shape remains outside Models."""

    shape: object | None
    status: str
    reason: str
    provenance: TargetedReconstructionProvenance | None = None

    @property
    def succeeded(self) -> bool:
        """Return whether strict reconstruction and equivalence checks passed."""
        return self.status == "succeeded" and self.shape is not None


@dataclass(frozen=True, slots=True)
class _Metrics:
    bounds_mm: tuple[float, float, float, float, float, float]
    center_mm: tuple[float, float, float]
    volume_mm3: float


@dataclass(frozen=True, slots=True)
class _EligibleFace:
    source_index: int
    face: object
    plane_z_mm: float
    departure_mm: float


def attempt_targeted_planar_reconstruction(
    solid: object,
) -> TargetedReconstructionOutcome:
    """Reconstruct only an exactly eligible invalid planar-boundary solid.

    Eligibility is completed before any geometry is produced.  On success,
    the returned solid is newly assembled from the original unaffected faces
    and newly constructed planar faces.  The caller-owned source is never
    copied, assigned, mutated, or saved.
    """
    if solid is None:
        return _outcome("ineligible", "source solid is missing")
    if _boolean(solid, "isNull") is not False:
        return _outcome("ineligible", "source solid is null or unreadable")
    if _boolean(solid, "isValid") is True:
        return TargetedReconstructionOutcome(
            shape=solid,
            status="not_required",
            reason="source solid is already valid",
        )

    try:
        eligible, reason = _eligible_faces(solid)
    except Exception as error:
        return _outcome("ineligible", f"eligibility inspection failed: {error}")
    if not eligible:
        return _outcome("ineligible", reason)

    try:
        original_metrics = _metrics(solid)
        transient = solid.copy()
        transient_faces = _items(transient, "Faces")
        if len(transient_faces) != len(_items(solid, "Faces")):
            raise ValueError("transient copy changed the source face count")
        transient_eligible = tuple(
            _EligibleFace(
                item.source_index,
                transient_faces[item.source_index - 1],
                item.plane_z_mm,
                item.departure_mm,
            )
            for item in eligible
        )
        replacements = {
            item.source_index: _rebuild_face(item)
            for item in transient_eligible
        }
        source_faces = transient_faces
        shell_faces = tuple(
            replacements.get(index, face)
            for index, face in enumerate(source_faces, start=1)
        )
        candidate = _make_solid(shell_faces)
        rejection = _validate_candidate(
            candidate,
            original_metrics,
            expected_face_count=len(source_faces),
        )
        if rejection:
            return _outcome("failed", rejection)
        result_metrics = _metrics(candidate)
    except Exception as error:
        return _outcome("failed", f"targeted construction failed: {error}")

    maximum_departure = max(item.departure_mm for item in eligible)
    provenance = TargetedReconstructionProvenance(
        rebuilt_face_ids=tuple(
            f"Face{item.source_index}" for item in eligible
        ),
        rebuilt_face_count=len(eligible),
        maximum_original_boundary_departure_mm=maximum_departure,
        maximum_geometric_displacement_mm=maximum_departure,
        original_volume_mm3=original_metrics.volume_mm3,
        reconstructed_volume_mm3=result_metrics.volume_mm3,
        volume_delta_mm3=(
            result_metrics.volume_mm3 - original_metrics.volume_mm3
        ),
    )
    return TargetedReconstructionOutcome(
        shape=candidate,
        status="succeeded",
        reason="targeted planar-boundary reconstruction accepted",
        provenance=provenance,
    )


def _eligible_faces(
    solid: object,
) -> tuple[tuple[_EligibleFace, ...], str]:
    """Return all invalid faces only when every eligibility rule is met."""
    if str(getattr(solid, "ShapeType", "")) != "Solid":
        return (), "source topology is not a Solid"
    if _boolean(solid, "isClosed") is not True:
        return (), "source solid is not closed"
    if len(_items(solid, "Solids")) != 1:
        return (), "source does not contain exactly one solid"
    if len(_items(solid, "Shells")) != 1:
        return (), "source solid does not contain exactly one shell"

    faces = _items(solid, "Faces")
    edges = _items(solid, "Edges")
    vertices = _items(solid, "Vertexes")
    if any(_boolean(edge, "isValid") is not True for edge in edges):
        return (), "source contains an invalid or unreadable edge"
    if any(_boolean(vertex, "isValid") is not True for vertex in vertices):
        return (), "source contains an invalid or unreadable vertex"

    invalid = tuple(
        (index, face)
        for index, face in enumerate(faces, start=1)
        if _boolean(face, "isValid") is False
    )
    if not invalid:
        return (), "source has no invalid planar faces"
    if any(_boolean(face, "isValid") is None for face in faces):
        return (), "one or more face validity states are unavailable"

    edge_index = _TopologyIndex(edges)
    face_edges = tuple(
        tuple(
            index
            for edge in _items(face, "Edges")
            if (index := edge_index.find(edge)) is not None
        )
        for face in faces
    )
    incidence: list[list[int]] = [[] for _ in edges]
    for face_index, indices in enumerate(face_edges, start=1):
        for edge_id in dict.fromkeys(indices):
            incidence[edge_id - 1].append(face_index)

    result = []
    reference_z = None
    for face_index, face in invalid:
        surface = getattr(face, "Surface", None)
        if type(surface).__name__ != "Plane":
            return (), f"Face{face_index} is not an exact planar face"
        origin = _vector(getattr(surface, "Position", None))
        axis = _vector(getattr(surface, "Axis", None))
        if origin is None or axis is None:
            return (), f"Face{face_index} cannot expose its plane"
        if (
            abs(axis[0]) > DIRECTION_COMPARISON_TOLERANCE
            or abs(axis[1]) > DIRECTION_COMPARISON_TOLERANCE
            or abs(abs(axis[2]) - 1.0) > DIRECTION_COMPARISON_TOLERANCE
        ):
            return (), f"Face{face_index} is not on the supported XY plane"
        if reference_z is None:
            reference_z = origin[2]
        elif abs(origin[2] - reference_z) > LINEAR_COMPARISON_TOLERANCE_MM:
            return (), "invalid faces do not share one fixed plane"

        wires = _items(face, "Wires")
        outer = getattr(face, "OuterWire", None)
        if not wires or outer is None:
            return (), f"Face{face_index} has no readable outer wire"
        if sum(_is_same(wire, outer) for wire in wires) != 1:
            return (), f"Face{face_index} outer-wire identity is ambiguous"
        for wire in wires:
            if _boolean(wire, "isClosed") is not True:
                return (), f"Face{face_index} contains an open wire"
            if _boolean(wire, "isValid") is not True:
                return (), f"Face{face_index} contains an invalid wire"
            wire_edges = _items(wire, "Edges")
            if not wire_edges:
                return (), f"Face{face_index} contains an empty wire"
            if any(
                _boolean(edge, "isValid") is not True for edge in wire_edges
            ):
                return (), f"Face{face_index} contains an invalid edge"

        own_edge_ids = tuple(dict.fromkeys(face_edges[face_index - 1]))
        if len(own_edge_ids) != len(_items(face, "Edges")):
            return (), f"Face{face_index} edge identity is incomplete or duplicated"
        for edge_id in own_edge_ids:
            adjacent = tuple(
                item for item in incidence[edge_id - 1] if item != face_index
            )
            if len(adjacent) != 1:
                return (), f"Face{face_index} lacks one exact adjacent face per edge"
            if _boolean(faces[adjacent[0] - 1], "isValid") is not True:
                return (), f"Face{face_index} has an invalid adjacent face"

        departures = tuple(
            _horizontal_departure(edge, origin[2])
            for edge in _items(face, "Edges")
        )
        maximum = max(departures, default=0.0)
        if maximum <= LINEAR_COMPARISON_TOLERANCE_MM:
            return (), f"Face{face_index} has no off-plane boundary geometry"
        if maximum > MAX_SUPPORTED_BOUNDARY_DEPARTURE_MM:
            return (), f"Face{face_index} exceeds the supported departure envelope"
        result.append(_EligibleFace(face_index, face, origin[2], maximum))
    return tuple(result), ""


def _rebuild_face(item: _EligibleFace) -> object:
    """Project only departing edges and construct one planar replacement."""
    import Part
    from FreeCAD import Vector

    source_face = item.face
    bounds = source_face.BoundBox
    extent = max(float(bounds.XLength), float(bounds.YLength))
    if not math.isfinite(extent) or extent <= 0.0:
        raise ValueError(f"Face{item.source_index} has unusable planar bounds")
    target_size = extent * PROJECTION_TARGET_SCALE
    margin = (target_size - extent) / 2.0
    target = Part.makePlane(
        target_size,
        target_size,
        Vector(
            float(bounds.XMin) - margin,
            float(bounds.YMin) - margin,
            item.plane_z_mm,
        ),
        Vector(0.0, 0.0, 1.0),
    )

    source_wires = _items(source_face, "Wires")
    source_outer = source_face.OuterWire
    ordered_sources = (
        source_outer,
        *(wire for wire in source_wires if not _is_same(wire, source_outer)),
    )
    rebuilt_wires = []
    for wire_index, source_wire in enumerate(ordered_sources):
        rebuilt_edges = []
        for source_edge in _ordered_edges(source_wire):
            departure = _horizontal_departure(source_edge, item.plane_z_mm)
            if departure <= LINEAR_COMPARISON_TOLERANCE_MM:
                rebuilt_edges.append(source_edge)
                continue
            projected = target.makeParallelProjection(
                source_edge,
                Vector(0.0, 0.0, 1.0),
            )
            projected_edges = _items(projected, "Edges")
            if len(projected_edges) != 1:
                raise ValueError(
                    f"Face{item.source_index} edge projection produced "
                    f"{len(projected_edges)} edges"
                )
            projected_edge = projected_edges[0]
            if _boolean(projected_edge, "isValid") is not True:
                raise ValueError(
                    f"Face{item.source_index} produced an invalid projected edge"
                )
            _orient_projected_edge(
                projected_edge,
                source_edge,
                item.plane_z_mm,
            )
            if (
                _horizontal_departure(projected_edge, item.plane_z_mm)
                > LINEAR_COMPARISON_TOLERANCE_MM
            ):
                raise ValueError(
                    f"Face{item.source_index} projection did not reach its plane"
                )
            rebuilt_edges.append(projected_edge)

        rebuilt_wire = Part.Wire(rebuilt_edges)
        winding = _xy_winding(rebuilt_wire)
        if abs(winding) <= LINEAR_COMPARISON_TOLERANCE_MM:
            raise ValueError(
                f"Face{item.source_index} wire orientation is indeterminate"
            )
        if (wire_index == 0 and winding < 0.0) or (
            wire_index > 0 and winding > 0.0
        ):
            rebuilt_wire.reverse()
        rebuilt_wires.append(rebuilt_wire)

    replacement = Part.Face(source_face.Surface, rebuilt_wires)
    if str(replacement.Orientation) != str(source_face.Orientation):
        replacement.reverse()
    return replacement


def _make_solid(faces: tuple[object, ...]) -> object:
    """Use direct topology construction without sewing or shape healing."""
    import Part

    shell = Part.makeShell(faces)
    if bool(shell.isNull()) or not bool(shell.isClosed()):
        raise ValueError("reconstructed shell is null or open")
    return Part.makeSolid(shell)


def _validate_candidate(
    candidate: object,
    original: _Metrics,
    *,
    expected_face_count: int,
) -> str:
    """Return the first strict structural or geometric rejection reason."""
    if _boolean(candidate, "isNull") is not False:
        return "reconstructed result is null or unreadable"
    if _boolean(candidate, "isValid") is not True:
        return "reconstructed result is invalid"
    if _boolean(candidate, "isClosed") is not True:
        return "reconstructed result is not closed"
    if len(_items(candidate, "Solids")) != 1:
        return "reconstructed result does not contain exactly one solid"
    faces = _items(candidate, "Faces")
    edges = _items(candidate, "Edges")
    vertices = _items(candidate, "Vertexes")
    if len(faces) != expected_face_count:
        return "reconstructed result changed the source face count"
    if any(_boolean(face, "isValid") is not True for face in faces):
        return "reconstructed result contains an invalid face"
    if any(
        _boolean(wire, "isValid") is not True
        or _boolean(wire, "isClosed") is not True
        for face in faces
        for wire in _items(face, "Wires")
    ):
        return "reconstructed result contains an invalid or open wire"
    if any(_boolean(edge, "isValid") is not True for edge in edges):
        return "reconstructed result contains an invalid edge"
    if any(_boolean(vertex, "isValid") is not True for vertex in vertices):
        return "reconstructed result contains an invalid vertex"

    result = _metrics(candidate)
    if result.volume_mm3 <= 0.0:
        return "reconstructed result does not have positive volume"
    if any(
        abs(before - after) > TARGETED_EQUIVALENCE_TOLERANCE_MM
        for before, after in zip(original.bounds_mm, result.bounds_mm)
    ):
        return "reconstructed bounding box changed beyond geometry tolerance"
    if any(
        abs(before - after) > TARGETED_EQUIVALENCE_TOLERANCE_MM
        for before, after in zip(original.center_mm, result.center_mm)
    ):
        return "reconstructed center of mass changed beyond geometry tolerance"
    if (
        abs(original.volume_mm3 - result.volume_mm3)
        > volume_tolerance_mm3(original.volume_mm3)
    ):
        return "reconstructed volume changed beyond geometry tolerance"
    return ""


def _metrics(shape: object) -> _Metrics:
    bounds = shape.BoundBox
    center = shape.CenterOfMass
    values = (
        float(bounds.XMin),
        float(bounds.YMin),
        float(bounds.ZMin),
        float(bounds.XMax),
        float(bounds.YMax),
        float(bounds.ZMax),
        float(center.x),
        float(center.y),
        float(center.z),
        float(shape.Volume),
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("source contains a non-finite geometry measurement")
    return _Metrics(values[:6], values[6:9], values[9])


def _orient_projected_edge(
    projected: object,
    source: object,
    plane_z_mm: float,
) -> None:
    """Match one projected edge to the source edge's local traversal."""
    source_points = _oriented_endpoints(source)
    projected_points = _oriented_endpoints(projected)
    if source_points is None or projected_points is None:
        raise ValueError("projected edge endpoints are unavailable")
    intended = (source_points[0][0], source_points[0][1], plane_z_mm)
    if _distance(projected_points[0], intended) > _distance(
        projected_points[1], intended
    ):
        projected.reverse()
        projected_points = _oriented_endpoints(projected)
        if projected_points is None:
            raise ValueError("projected edge orientation is unavailable")
    if _distance(projected_points[0], intended) > LINEAR_COMPARISON_TOLERANCE_MM:
        raise ValueError("projected edge changed its intended XY endpoint")


def _xy_winding(wire: object) -> float:
    vertices = _items(wire, "OrderedVertexes")
    points = tuple(_vector(vertex.Point) for vertex in vertices)
    if len(points) < 3 or any(point is None for point in points):
        return 0.0
    xy = tuple((point[0], point[1]) for point in points if point is not None)
    return 0.5 * sum(
        xy[index][0] * xy[(index + 1) % len(xy)][1]
        - xy[(index + 1) % len(xy)][0] * xy[index][1]
        for index in range(len(xy))
    )


def _horizontal_departure(edge: object, plane_z_mm: float) -> float:
    bounds = edge.BoundBox
    values = (float(bounds.ZMin), float(bounds.ZMax), plane_z_mm)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("edge has non-finite boundary coordinates")
    return max(abs(values[0] - plane_z_mm), abs(values[1] - plane_z_mm))


def _oriented_endpoints(
    edge: object,
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    vertices = _items(edge, "Vertexes")
    if len(vertices) != 2:
        return None
    points = (_vector(vertices[0].Point), _vector(vertices[1].Point))
    if points[0] is None or points[1] is None:
        return None
    result = (points[0], points[1])
    if str(getattr(edge, "Orientation", "Forward")) == "Reversed":
        result = (result[1], result[0])
    return result


def _ordered_edges(wire: object) -> tuple[object, ...]:
    edges = _items(wire, "OrderedEdges")
    if not edges or len(edges) != len(_items(wire, "Edges")):
        raise ValueError("wire cannot expose one deterministic ordered edge set")
    return edges


def _distance(first: tuple[float, ...], second: tuple[float, ...]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second)))


def _vector(value: object) -> tuple[float, float, float] | None:
    try:
        result = (float(value.x), float(value.y), float(value.z))
        return result if all(math.isfinite(item) for item in result) else None
    except (AttributeError, TypeError, ValueError):
        return None


def _boolean(value: object, name: str) -> bool | None:
    member = getattr(value, name, None)
    if member is None:
        return None
    try:
        return bool(member() if callable(member) else member)
    except Exception:
        return None


def _items(value: object, name: str) -> tuple[object, ...]:
    try:
        return tuple(getattr(value, name, ()))
    except Exception as error:
        raise ValueError(f"source cannot expose {name.lower()}") from error


class _TopologyIndex:
    def __init__(self, items: tuple[object, ...]) -> None:
        self._items = items
        self._buckets: dict[int | None, list[int]] = {}
        for index, item in enumerate(items, start=1):
            self._buckets.setdefault(_hash_code(item), []).append(index)

    def find(self, candidate: object) -> int | None:
        key = _hash_code(candidate)
        for index in self._buckets.get(key, ()):
            if _is_same(candidate, self._items[index - 1]):
                return index
        if key is None:
            for index, item in enumerate(self._items, start=1):
                if _is_same(candidate, item):
                    return index
        return None


def _hash_code(shape: object) -> int | None:
    method = getattr(shape, "hashCode", None)
    if not callable(method):
        return None
    try:
        return int(method())
    except Exception:
        return None


def _is_same(first: object, second: object) -> bool:
    if first is second:
        return True
    method = getattr(first, "isSame", None)
    if not callable(method):
        return False
    try:
        return bool(method(second))
    except Exception:
        return False


def _outcome(status: str, reason: str) -> TargetedReconstructionOutcome:
    return TargetedReconstructionOutcome(None, status, reason)

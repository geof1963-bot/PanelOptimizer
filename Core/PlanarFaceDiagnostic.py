# -*- coding: utf-8 -*-
"""Focused read-only diagnostics for invalid planar source faces.

The inspector in this module is intentionally diagnostic-only.  It reads
individual faces, wires, edges, and vertices and converts every result to
immutable scalar data.  It does not call a whole-shape checker, BOPCheck,
repair, refinement, meshing, reconstruction, or a boolean operation.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .Exceptions import InvalidShapeError, NullShapeError

# Geometry-only comparison tolerances.  They locate topology defects and are
# unrelated to manufacturing capability or acceptance criteria.
PLANAR_DIAGNOSTIC_TOLERANCE_MM = 1.0e-7
NEAR_ZERO_LOOP_AREA_MM2 = 1.0e-12
DEFAULT_INVALID_PLANAR_FACE_LIMIT = 7

Point3 = tuple[float, float, float]
Bounds = tuple[float, float, float, float, float, float]

__all__ = [
    "DEFAULT_INVALID_PLANAR_FACE_LIMIT",
    "NEAR_ZERO_LOOP_AREA_MM2",
    "PLANAR_DIAGNOSTIC_TOLERANCE_MM",
    "AdjacentFaceDiagnostic",
    "EdgeContinuityIssue",
    "InvalidPlanarFaceDiagnostic",
    "InvalidPlanarFaceReport",
    "PlanarSegment",
    "PlanarTopologyIssue",
    "WireDiagnostic",
    "format_invalid_planar_face_diagnostic",
    "inspect_invalid_planar_faces",
]


@dataclass(frozen=True, slots=True)
class EdgeContinuityIssue:
    """Scalar evidence about one edge or consecutive edge pair."""

    issue_type: str
    wire_index: int
    edge_ids: tuple[str, ...]
    distance_mm: float | None = None


@dataclass(frozen=True, slots=True)
class PlanarTopologyIssue:
    """Scalar evidence found by deterministic XY segment inspection."""

    issue_type: str
    wire_indices: tuple[int, ...]
    edge_ids: tuple[str, ...]
    point_xy_mm: tuple[float, float] | None = None
    overlap_length_mm: float | None = None


@dataclass(frozen=True, slots=True)
class PlanarSegment:
    """One exact linear edge represented by scalar XY endpoints."""

    edge_id: str
    start_xy_mm: tuple[float, float]
    end_xy_mm: tuple[float, float]


@dataclass(frozen=True, slots=True)
class WireDiagnostic:
    """Read-only scalar description of one wire belonging to a face."""

    wire_index: int
    is_outer: bool
    is_closed: bool | None
    is_valid: bool | None
    edge_count: int
    total_length_mm: float | None
    orientation: str
    bounding_box_mm: Bounds | None
    signed_area_xy_mm2: float | None
    edge_ids: tuple[str, ...]
    edge_curve_types: tuple[tuple[str, str], ...]
    projected_segments: tuple[PlanarSegment, ...]
    continuity_issues: tuple[EdgeContinuityIssue, ...]
    planar_issues: tuple[PlanarTopologyIssue, ...]


@dataclass(frozen=True, slots=True)
class AdjacentFaceDiagnostic:
    """One directly edge-adjacent source face, without recursive traversal."""

    face_id: str
    surface_type: str
    shared_edge_count: int
    is_valid: bool | None


@dataclass(frozen=True, slots=True)
class InvalidPlanarFaceDiagnostic:
    """Complete scalar evidence for one invalid planar source face."""

    face_id: str
    surface_type: str
    plane_origin_mm: Point3 | None
    plane_normal: Point3 | None
    orientation: str
    area_mm2: float | None
    bounding_box_mm: Bounds | None
    wire_count: int
    outer_wire_edge_count: int | None
    inner_wire_count: int | None
    edge_count: int
    vertex_count: int
    wires: tuple[WireDiagnostic, ...]
    planar_issues: tuple[PlanarTopologyIssue, ...]
    adjacent_faces: tuple[AdjacentFaceDiagnostic, ...]
    findings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InvalidPlanarFaceReport:
    """Bounded deterministic report for invalid planar faces only."""

    invalid_face_total: int
    inspected_face_ids: tuple[str, ...]
    faces: tuple[InvalidPlanarFaceDiagnostic, ...]
    output_limit: int
    common_patterns: tuple[str, ...]


def inspect_invalid_planar_faces(
    shape: object,
    *,
    face_limit: int = DEFAULT_INVALID_PLANAR_FACE_LIMIT,
) -> InvalidPlanarFaceReport:
    """Inspect at most ``face_limit`` invalid planar faces in source order.

    Candidate faces are selected solely by per-face ``isValid()``.  Plane,
    wire, curve, point, measure, and adjacency properties are then read from
    those faces.  The source shape is never copied or modified.
    """
    if shape is None:
        raise NullShapeError("Planar-face diagnostic source shape is missing.")
    if _safe_boolean(shape, "isNull") is not False:
        raise NullShapeError("Planar-face diagnostic source is null or unreadable.")
    if not isinstance(face_limit, int) or face_limit < 0:
        raise InvalidShapeError(
            "Invalid planar-face diagnostic limit must be a non-negative integer."
        )

    faces = _items(shape, "Faces")
    source_edges = _items(shape, "Edges")
    edge_index = _TopologyIndex(source_edges)
    face_edge_ids = tuple(
        tuple(
            edge_id
            for edge in _items(face, "Edges")
            if (edge_id := edge_index.find(edge)) is not None
        )
        for face in faces
    )
    invalid_numbers = tuple(
        index
        for index, face in enumerate(faces, start=1)
        if _safe_boolean(face, "isValid") is False
    )

    diagnostics = []
    for face_number in invalid_numbers[:face_limit]:
        diagnostics.append(
            _inspect_face(
                faces,
                face_edge_ids,
                edge_index,
                face_number,
            )
        )
    result = tuple(diagnostics)
    return InvalidPlanarFaceReport(
        invalid_face_total=len(invalid_numbers),
        inspected_face_ids=tuple(item.face_id for item in result),
        faces=result,
        output_limit=face_limit,
        common_patterns=_common_patterns(result),
    )


def format_invalid_planar_face_diagnostic(
    report: InvalidPlanarFaceReport,
) -> str:
    """Format the bounded face/wire evidence for the console."""
    if not report.faces:
        return "Invalid planar-face detail: none.\n"
    lines = [
        "Invalid planar-face detail: "
        f"{report.invalid_face_total} total; showing {len(report.faces)}.",
    ]
    for face in report.faces:
        lines.extend(
            (
                "",
                f"{face.face_id}: surface={face.surface_type}; "
                f"origin={_point(face.plane_origin_mm)} mm; "
                f"normal={_point(face.plane_normal)}; "
                f"orientation={face.orientation}",
                f"  area={_number(face.area_mm2)} mm^2; "
                f"bounds={_bounds_text(face.bounding_box_mm)}; "
                f"wires={face.wire_count}; outer_edges="
                f"{_value(face.outer_wire_edge_count)}; inner_wires="
                f"{_value(face.inner_wire_count)}; edges={face.edge_count}; "
                f"vertices={face.vertex_count}",
            )
        )
        for wire in face.wires:
            lines.append(
                f"  Wire{wire.wire_index}: outer={wire.is_outer}; "
                f"closed={wire.is_closed}; valid={wire.is_valid}; "
                f"edges={wire.edge_count}; length="
                f"{_number(wire.total_length_mm)} mm; "
                f"orientation={wire.orientation}; "
                f"bounds={_bounds_text(wire.bounding_box_mm)}; "
                f"signed_xy_area={_number(wire.signed_area_xy_mm2)} mm^2; "
                f"curves={_curve_summary(wire.edge_curve_types)}"
            )
            for issue in wire.continuity_issues:
                suffix = (
                    ""
                    if issue.distance_mm is None
                    else f"; distance={_number(issue.distance_mm)} mm"
                )
                lines.append(
                    f"    edge: {issue.issue_type}; "
                    f"edges={','.join(issue.edge_ids) or 'unavailable'}{suffix}"
                )
            for issue in wire.planar_issues:
                lines.append("    planar: " + _planar_issue_text(issue))
        for issue in face.planar_issues:
            lines.append("  planar: " + _planar_issue_text(issue))
        if face.adjacent_faces:
            lines.append(
                "  adjacent: "
                + ", ".join(
                    f"{item.face_id}({item.surface_type},shared="
                    f"{item.shared_edge_count},valid={item.is_valid})"
                    for item in face.adjacent_faces
                )
            )
        else:
            lines.append("  adjacent: none by exact shared-edge identity")
        lines.append(
            "  findings: " + (", ".join(face.findings) or "no scalar cause isolated")
        )
    if report.common_patterns:
        lines.extend(("", "Shared pattern evidence:"))
        lines.extend(f"- {item}" for item in report.common_patterns)
    return "\n".join(lines) + "\n"


def _inspect_face(
    faces: tuple[object, ...],
    face_edge_ids: tuple[tuple[int, ...], ...],
    edge_index: "_TopologyIndex",
    face_number: int,
) -> InvalidPlanarFaceDiagnostic:
    face = faces[face_number - 1]
    wires = _items(face, "Wires")
    outer = getattr(face, "OuterWire", None)
    surface = getattr(face, "Surface", None)
    surface_type = type(surface).__name__ if surface is not None else "Unavailable"
    origin = _vector(getattr(surface, "Position", None))
    normal = _vector(getattr(surface, "Axis", None))
    xy_plane = normal is not None and (
        abs(normal[0]) <= PLANAR_DIAGNOSTIC_TOLERANCE_MM
        and abs(normal[1]) <= PLANAR_DIAGNOSTIC_TOLERANCE_MM
        and abs(abs(normal[2]) - 1.0) <= PLANAR_DIAGNOSTIC_TOLERANCE_MM
    )

    wire_data = tuple(
        _inspect_wire(
            wire,
            index,
            _is_same(wire, outer),
            edge_index,
            xy_plane,
            None if origin is None or not xy_plane else origin[2],
        )
        for index, wire in enumerate(wires, start=1)
    )
    cross_wire_issues = _cross_wire_planar_issues(wire_data)
    own_edges = set(face_edge_ids[face_number - 1])
    adjacent = []
    for index, other in enumerate(faces, start=1):
        if index == face_number:
            continue
        shared = own_edges.intersection(face_edge_ids[index - 1])
        if shared:
            adjacent.append(
                AdjacentFaceDiagnostic(
                    face_id=f"Face{index}",
                    surface_type=_surface_type(other),
                    shared_edge_count=len(shared),
                    is_valid=_safe_boolean(other, "isValid"),
                )
            )

    outer_data = next((item for item in wire_data if item.is_outer), None)
    findings = []
    if surface_type != "Plane":
        findings.append("invalid face is not an exact plane")
    if not xy_plane:
        findings.append("XY projection unavailable for non-horizontal plane")
    if any(item.is_valid is False for item in wire_data):
        findings.append("one or more constituent wires are invalid")
    if any(item.is_closed is False for item in wire_data):
        findings.append("one or more constituent wires are open")
    continuity_types = {
        issue.issue_type
        for wire in wire_data
        for issue in wire.continuity_issues
    }
    findings.extend(sorted(continuity_types))
    planar_types = {
        issue.issue_type
        for wire in wire_data
        for issue in wire.planar_issues
    } | {issue.issue_type for issue in cross_wire_issues}
    findings.extend(sorted(planar_types))
    if not findings:
        findings.append("no scalar cause isolated")

    return InvalidPlanarFaceDiagnostic(
        face_id=f"Face{face_number}",
        surface_type=surface_type,
        plane_origin_mm=origin,
        plane_normal=normal,
        orientation=str(getattr(face, "Orientation", "Unknown")),
        area_mm2=_safe_float(face, "Area"),
        bounding_box_mm=_bounds(face),
        wire_count=len(wires),
        outer_wire_edge_count=(None if outer_data is None else outer_data.edge_count),
        inner_wire_count=(None if outer_data is None else len(wires) - 1),
        edge_count=len(_items(face, "Edges")),
        vertex_count=len(_items(face, "Vertexes")),
        wires=wire_data,
        planar_issues=cross_wire_issues,
        adjacent_faces=tuple(adjacent),
        findings=tuple(dict.fromkeys(findings)),
    )


def _inspect_wire(
    wire: object,
    wire_index: int,
    is_outer: bool,
    edge_index: "_TopologyIndex",
    xy_plane: bool,
    plane_z_mm: float | None,
) -> WireDiagnostic:
    raw_edges = _items(wire, "Edges")
    ordered_edges = _optional_items(wire, "OrderedEdges") or raw_edges
    edge_ids = tuple(
        f"Edge{index}"
        for edge in ordered_edges
        if (index := edge_index.find(edge)) is not None
    )
    continuity = []
    curve_types = tuple(
        (
            _edge_id(edge_index, edge, position),
            type(getattr(edge, "Curve", None)).__name__,
        )
        for position, edge in enumerate(ordered_edges)
    )
    if len(ordered_edges) != len(raw_edges):
        continuity.append(
            EdgeContinuityIssue(
                "ordered_edge_count_mismatch", wire_index, edge_ids
            )
        )
    seen: list[tuple[int, object]] = []
    for position, edge in enumerate(ordered_edges):
        edge_id = _edge_id(edge_index, edge, position)
        length = _safe_float(edge, "Length")
        endpoints = _oriented_endpoints(edge)
        edge_bounds = _bounds(edge)
        if plane_z_mm is not None and edge_bounds is not None:
            deviation = max(
                abs(edge_bounds[2] - plane_z_mm),
                abs(edge_bounds[5] - plane_z_mm),
            )
            if deviation > PLANAR_DIAGNOSTIC_TOLERANCE_MM:
                continuity.append(
                    EdgeContinuityIssue(
                        "edge_geometry_leaves_face_plane",
                        wire_index,
                        (edge_id,),
                        deviation,
                    )
                )
        if length is None:
            continuity.append(
                EdgeContinuityIssue("length_unavailable", wire_index, (edge_id,))
            )
        elif length <= 0.0:
            continuity.append(
                EdgeContinuityIssue("zero_length_edge", wire_index, (edge_id,), length)
            )
        elif length <= PLANAR_DIAGNOSTIC_TOLERANCE_MM:
            continuity.append(
                EdgeContinuityIssue("tiny_edge", wire_index, (edge_id,), length)
            )
        if endpoints is not None and _distance(*endpoints) <= PLANAR_DIAGNOSTIC_TOLERANCE_MM:
            continuity.append(
                EdgeContinuityIssue(
                    "self_returning_edge", wire_index, (edge_id,), _distance(*endpoints)
                )
            )
        for previous_position, previous in seen:
            if _is_same(edge, previous):
                continuity.append(
                    EdgeContinuityIssue(
                        "duplicated_topology_edge",
                        wire_index,
                        (_edge_id(edge_index, previous, previous_position), edge_id),
                    )
                )
        seen.append((position, edge))

    closed = _safe_boolean(wire, "isClosed")
    pair_count = len(ordered_edges) if closed is True else max(0, len(ordered_edges) - 1)
    for position in range(pair_count):
        first = ordered_edges[position]
        second = ordered_edges[(position + 1) % len(ordered_edges)]
        first_points = _oriented_endpoints(first)
        second_points = _oriented_endpoints(second)
        if first_points is None or second_points is None:
            continue
        expected_gap = _distance(first_points[1], second_points[0])
        ids = (
            _edge_id(edge_index, first, position),
            _edge_id(edge_index, second, (position + 1) % len(ordered_edges)),
        )
        if expected_gap <= PLANAR_DIAGNOSTIC_TOLERANCE_MM:
            continue
        minimum_gap = min(
            _distance(a, b) for a in first_points for b in second_points
        )
        issue = (
            "reversed_local_continuity"
            if minimum_gap <= PLANAR_DIAGNOSTIC_TOLERANCE_MM
            else "disconnected_consecutive_edges"
        )
        continuity.append(EdgeContinuityIssue(issue, wire_index, ids, expected_gap))

    planar, signed_area, segments = _within_wire_planar_issues(
        wire_index, ordered_edges, edge_index, closed, xy_plane
    )
    return WireDiagnostic(
        wire_index=wire_index,
        is_outer=is_outer,
        is_closed=closed,
        is_valid=_safe_boolean(wire, "isValid"),
        edge_count=len(raw_edges),
        total_length_mm=_safe_float(wire, "Length"),
        orientation=str(getattr(wire, "Orientation", "Unknown")),
        bounding_box_mm=_bounds(wire),
        signed_area_xy_mm2=signed_area,
        edge_ids=edge_ids,
        edge_curve_types=curve_types,
        projected_segments=segments,
        continuity_issues=tuple(continuity),
        planar_issues=planar,
    )


def _within_wire_planar_issues(
    wire_index: int,
    edges: tuple[object, ...],
    edge_index: "_TopologyIndex",
    closed: bool | None,
    xy_plane: bool,
) -> tuple[
    tuple[PlanarTopologyIssue, ...],
    float | None,
    tuple[PlanarSegment, ...],
]:
    if not xy_plane:
        return (), None, ()
    segments = _linear_segments(edges, edge_index)
    if len(segments) != len(edges):
        linear_ids = {item.edge_id for item in segments}
        return (
            (
                PlanarTopologyIssue(
                    "nonlinear_edges_not_projected",
                    (wire_index,),
                    tuple(
                        _edge_id(edge_index, edge, position)
                        for position, edge in enumerate(edges)
                        if _edge_id(edge_index, edge, position) not in linear_ids
                    ),
                ),
            ),
            None,
            segments,
        )
    issues = []
    count = len(segments)
    for first in range(count):
        for second in range(first + 1, count):
            if second == first + 1 or (
                closed is True and first == 0 and second == count - 1
            ):
                continue
            if (
                math.dist(
                    segments[first].start_xy_mm,
                    segments[second].start_xy_mm,
                )
                <= PLANAR_DIAGNOSTIC_TOLERANCE_MM
            ):
                issues.append(
                    PlanarTopologyIssue(
                        "repeated_nonconsecutive_vertex",
                        (wire_index,),
                        (segments[first].edge_id, segments[second].edge_id),
                        segments[first].start_xy_mm,
                    )
                )
    for first in range(count):
        for second in range(first + 1, count):
            if second == first + 1 or (
                closed is True and first == 0 and second == count - 1
            ):
                continue
            relation = _segment_relation(segments[first], segments[second])
            if relation is None:
                continue
            kind, point, overlap = relation
            issues.append(
                PlanarTopologyIssue(
                    "overlapping_collinear_segments"
                    if kind == "overlap"
                    else "self_intersecting_wire",
                    (wire_index,),
                    (segments[first].edge_id, segments[second].edge_id),
                    point,
                    overlap,
                )
            )
    area = _signed_area(segments) if closed is True else None
    if area is not None and abs(area) <= NEAR_ZERO_LOOP_AREA_MM2:
        issues.append(
            PlanarTopologyIssue(
                "near_zero_area_loop",
                (wire_index,),
                tuple(item.edge_id for item in segments),
            )
        )
    return tuple(issues), area, segments


def _cross_wire_planar_issues(
    wires: tuple[WireDiagnostic, ...],
) -> tuple[PlanarTopologyIssue, ...]:
    issues = []
    for first in range(len(wires)):
        for second in range(first + 1, len(wires)):
            a = wires[first].projected_segments
            b = wires[second].projected_segments
            if not a or not b:
                continue
            if _canonical_loop(a) == _canonical_loop(b):
                issues.append(
                    PlanarTopologyIssue(
                        "duplicated_loops",
                        (wires[first].wire_index, wires[second].wire_index),
                        tuple(item.edge_id for item in a + b),
                    )
                )
            relation = _first_loop_relation(a, b)
            if relation is not None:
                kind, ids, point, overlap = relation
                role = (
                    "inner_wire_touches_outer_wire"
                    if wires[first].is_outer or wires[second].is_outer
                    else "inner_wires_touch"
                )
                if kind == "overlap":
                    role += "_with_collinear_overlap"
                issues.append(
                    PlanarTopologyIssue(
                        role,
                        (wires[first].wire_index, wires[second].wire_index),
                        ids,
                        point,
                        overlap,
                    )
                )
            if wires[first].is_outer != wires[second].is_outer:
                outer = wires[first] if wires[first].is_outer else wires[second]
                inner = wires[second] if wires[first].is_outer else wires[first]
                containment = _point_in_loop(
                    inner.projected_segments[0].start_xy_mm,
                    outer.projected_segments,
                )
                if containment == 0:
                    issues.append(
                        PlanarTopologyIssue(
                            "inner_loop_outside_outer_loop",
                            (outer.wire_index, inner.wire_index),
                            (),
                        )
                    )
                elif (
                    outer.signed_area_xy_mm2 is not None
                    and inner.signed_area_xy_mm2 is not None
                    and outer.signed_area_xy_mm2 * inner.signed_area_xy_mm2 > 0.0
                ):
                    issues.append(
                        PlanarTopologyIssue(
                            "nested_loop_has_contradictory_orientation",
                            (outer.wire_index, inner.wire_index),
                            (),
                        )
                    )
    return tuple(issues)


def _linear_segments(
    edges: tuple[object, ...], edge_index: "_TopologyIndex"
) -> tuple[PlanarSegment, ...]:
    result = []
    for position, edge in enumerate(edges):
        curve = getattr(edge, "Curve", None)
        if type(curve).__name__ != "Line":
            continue
        endpoints = _oriented_endpoints(edge)
        if endpoints is None:
            continue
        result.append(
            PlanarSegment(
                edge_id=_edge_id(edge_index, edge, position),
                start_xy_mm=(endpoints[0][0], endpoints[0][1]),
                end_xy_mm=(endpoints[1][0], endpoints[1][1]),
            )
        )
    return tuple(result)


def _first_loop_relation(
    first: tuple[PlanarSegment, ...], second: tuple[PlanarSegment, ...]
):
    for a in first:
        for b in second:
            relation = _segment_relation(a, b)
            if relation is not None:
                kind, point, overlap = relation
                return kind, (a.edge_id, b.edge_id), point, overlap
    return None


def _segment_relation(first: PlanarSegment, second: PlanarSegment):
    a, b = first.start_xy_mm, first.end_xy_mm
    c, d = second.start_xy_mm, second.end_xy_mm
    ab = (b[0] - a[0], b[1] - a[1])
    cd = (d[0] - c[0], d[1] - c[1])
    cross = _cross(ab, cd)
    ac = (c[0] - a[0], c[1] - a[1])
    if abs(cross) <= PLANAR_DIAGNOSTIC_TOLERANCE_MM:
        if abs(_cross(ab, ac)) > PLANAR_DIAGNOSTIC_TOLERANCE_MM:
            return None
        axis = 0 if abs(ab[0]) >= abs(ab[1]) else 1
        first_range = sorted((a[axis], b[axis]))
        second_range = sorted((c[axis], d[axis]))
        low = max(first_range[0], second_range[0])
        high = min(first_range[1], second_range[1])
        if high < low - PLANAR_DIAGNOSTIC_TOLERANCE_MM:
            return None
        if high - low > PLANAR_DIAGNOSTIC_TOLERANCE_MM:
            return "overlap", None, high - low
        point = _shared_endpoint(a, b, c, d)
        return "touch", point, None
    t = _cross(ac, cd) / cross
    u = _cross(ac, ab) / cross
    tolerance = PLANAR_DIAGNOSTIC_TOLERANCE_MM
    if -tolerance <= t <= 1.0 + tolerance and -tolerance <= u <= 1.0 + tolerance:
        return "intersect", (a[0] + t * ab[0], a[1] + t * ab[1]), None
    return None


def _point_in_loop(
    point: tuple[float, float],
    segments: tuple[PlanarSegment, ...],
) -> int:
    """Return 1 inside, -1 on boundary, or 0 outside a linear XY loop."""
    crossings = 0
    px, py = point
    for segment in segments:
        a, b = segment.start_xy_mm, segment.end_xy_mm
        if _point_on_segment(point, a, b):
            return -1
        if (a[1] > py) == (b[1] > py):
            continue
        crossing_x = a[0] + (py - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
        if crossing_x > px:
            crossings += 1
    return 1 if crossings % 2 else 0


def _point_on_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> bool:
    direction = (end[0] - start[0], end[1] - start[1])
    offset = (point[0] - start[0], point[1] - start[1])
    if abs(_cross(direction, offset)) > PLANAR_DIAGNOSTIC_TOLERANCE_MM:
        return False
    return (
        min(start[0], end[0]) - PLANAR_DIAGNOSTIC_TOLERANCE_MM
        <= point[0]
        <= max(start[0], end[0]) + PLANAR_DIAGNOSTIC_TOLERANCE_MM
        and min(start[1], end[1]) - PLANAR_DIAGNOSTIC_TOLERANCE_MM
        <= point[1]
        <= max(start[1], end[1]) + PLANAR_DIAGNOSTIC_TOLERANCE_MM
    )


def _signed_area(segments: tuple[PlanarSegment, ...]) -> float:
    return 0.5 * sum(
        start[0] * end[1] - end[0] * start[1]
        for start, end in (
            (segment.start_xy_mm, segment.end_xy_mm) for segment in segments
        )
    )


def _canonical_loop(
    segments: tuple[PlanarSegment, ...]
) -> tuple[tuple[int, int], ...]:
    points = tuple(_quantized(item.start_xy_mm) for item in segments)
    if not points:
        return ()
    rotations = tuple(points[index:] + points[:index] for index in range(len(points)))
    reverse = tuple(reversed(points))
    reverse_rotations = tuple(
        reverse[index:] + reverse[:index] for index in range(len(reverse))
    )
    return min(rotations + reverse_rotations)


def _common_patterns(
    faces: tuple[InvalidPlanarFaceDiagnostic, ...]
) -> tuple[str, ...]:
    if not faces:
        return ()
    patterns = []
    origins = [face.plane_origin_mm for face in faces]
    if all(item is not None for item in origins):
        z_values = [item[2] for item in origins if item is not None]
        if max(z_values) - min(z_values) <= PLANAR_DIAGNOSTIC_TOLERANCE_MM:
            patterns.append(f"all inspected faces lie on Z={_number(z_values[0])} mm")
    signatures = {
        (
            face.surface_type,
            face.wire_count,
            face.inner_wire_count,
            face.outer_wire_edge_count,
            tuple(wire.edge_count for wire in face.wires),
            face.findings,
        )
        for face in faces
    }
    if len(signatures) == 1:
        patterns.append("all inspected faces share the same wire/edge defect signature")
    else:
        common = set(faces[0].findings)
        for face in faces[1:]:
            common.intersection_update(face.findings)
        if common:
            patterns.append("common findings: " + ", ".join(sorted(common)))
    patterns.append(
        "modeling-operation provenance is not inferable from scalar topology alone"
    )
    return tuple(patterns)


class _TopologyIndex:
    """Resolve stable one-based source indices by exact topology identity."""

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


def _surface_type(face: object) -> str:
    surface = getattr(face, "Surface", None)
    return type(surface).__name__ if surface is not None else "Unavailable"


def _oriented_endpoints(edge: object) -> tuple[Point3, Point3] | None:
    vertices = _items(edge, "Vertexes")
    if len(vertices) != 2:
        return None
    points = (_vertex_point(vertices[0]), _vertex_point(vertices[1]))
    if None in points:
        return None
    result = (points[0], points[1])
    if str(getattr(edge, "Orientation", "Forward")) == "Reversed":
        result = (result[1], result[0])
    return result  # type: ignore[return-value]


def _vertex_point(vertex: object) -> Point3 | None:
    return _vector(getattr(vertex, "Point", None))


def _vector(value: object) -> Point3 | None:
    try:
        result = (float(value.x), float(value.y), float(value.z))
        return result if all(math.isfinite(item) for item in result) else None
    except (AttributeError, TypeError, ValueError):
        return None


def _distance(first: Point3, second: Point3) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(first, second)))


def _cross(first: tuple[float, float], second: tuple[float, float]) -> float:
    return first[0] * second[1] - first[1] * second[0]


def _shared_endpoint(a, b, c, d) -> tuple[float, float] | None:
    for first in (a, b):
        for second in (c, d):
            if math.dist(first, second) <= PLANAR_DIAGNOSTIC_TOLERANCE_MM:
                return first
    return None


def _quantized(point: tuple[float, float]) -> tuple[int, int]:
    return tuple(
        int(round(value / PLANAR_DIAGNOSTIC_TOLERANCE_MM)) for value in point
    )  # type: ignore[return-value]


def _edge_id(index: _TopologyIndex, edge: object, fallback: int) -> str:
    source_index = index.find(edge)
    return f"Edge{source_index}" if source_index is not None else f"WireEdge{fallback + 1}"


def _safe_boolean(value: object, name: str) -> bool | None:
    member = getattr(value, name, None)
    if member is None:
        return None
    try:
        return bool(member() if callable(member) else member)
    except Exception:
        return None


def _safe_float(value: object, name: str) -> float | None:
    try:
        result = float(getattr(value, name))
        return result if math.isfinite(result) else None
    except (AttributeError, TypeError, ValueError):
        return None


def _bounds(shape: object) -> Bounds | None:
    try:
        box = shape.BoundBox
        result = (
            float(box.XMin),
            float(box.YMin),
            float(box.ZMin),
            float(box.XMax),
            float(box.YMax),
            float(box.ZMax),
        )
        return result if all(math.isfinite(item) for item in result) else None
    except (AttributeError, TypeError, ValueError):
        return None


def _items(shape: object, name: str) -> tuple[object, ...]:
    try:
        return tuple(getattr(shape, name, ()))
    except Exception as error:
        raise InvalidShapeError(
            f"Planar-face diagnostic source cannot expose {name.lower()}."
        ) from error


def _optional_items(shape: object, name: str) -> tuple[object, ...]:
    try:
        return tuple(getattr(shape, name, ()))
    except Exception:
        return ()


def _hash_code(shape: object) -> int | None:
    method = getattr(shape, "hashCode", None)
    if not callable(method):
        return None
    try:
        return int(method())
    except Exception:
        return None


def _is_same(first: object, second: object) -> bool:
    if first is None or second is None:
        return False
    if first is second:
        return True
    method = getattr(first, "isSame", None)
    if not callable(method):
        return False
    try:
        return bool(method(second))
    except Exception:
        return False


def _planar_issue_text(issue: PlanarTopologyIssue) -> str:
    details = [issue.issue_type]
    details.append("wires=" + ",".join(str(item) for item in issue.wire_indices))
    if issue.edge_ids:
        details.append("edges=" + ",".join(issue.edge_ids))
    if issue.point_xy_mm is not None:
        details.append("xy=" + _point2(issue.point_xy_mm) + " mm")
    if issue.overlap_length_mm is not None:
        details.append(f"overlap={_number(issue.overlap_length_mm)} mm")
    return "; ".join(details)


def _curve_summary(values: tuple[tuple[str, str], ...]) -> str:
    counts: dict[str, int] = {}
    for _, curve_type in values:
        counts[curve_type] = counts.get(curve_type, 0) + 1
    return ",".join(
        f"{curve_type}:{count}" for curve_type, count in sorted(counts.items())
    ) or "unavailable"


def _number(value: float | None) -> str:
    return "unavailable" if value is None else format(value, ".12g")


def _value(value: object | None) -> str:
    return "unavailable" if value is None else str(value)


def _point(value: Point3 | None) -> str:
    if value is None:
        return "unavailable"
    return "(" + ", ".join(_number(item) for item in value) + ")"


def _point2(value: tuple[float, float]) -> str:
    return "(" + ", ".join(_number(item) for item in value) + ")"


def _bounds_text(value: Bounds | None) -> str:
    if value is None:
        return "unavailable"
    return "(" + ", ".join(_number(item) for item in value) + ") mm"

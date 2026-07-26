# -*- coding: utf-8 -*-
"""Explicit read-only localization diagnostics for invalid source topology."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .Exceptions import InvalidShapeError, NullShapeError

# Geometry-only coordinate comparison used solely to label boundary proximity.
DIAGNOSTIC_BOUNDARY_TOLERANCE_MM = 1.0e-7
DEFAULT_SUSPICIOUS_ELEMENT_LIMIT = 20

__all__ = [
    "DEFAULT_SUSPICIOUS_ELEMENT_LIMIT",
    "DIAGNOSTIC_BOUNDARY_TOLERANCE_MM",
    "SuspiciousTopologyElement",
    "TopologyDiagnosticReport",
    "format_topology_diagnostic",
    "inspect_topology",
]


@dataclass(frozen=True, slots=True)
class SuspiciousTopologyElement:
    """Immutable scalar description of one suspicious source subshape."""

    element_id: str
    element_type: str
    source_index: int
    reasons: tuple[str, ...]
    bounding_box_mm: tuple[float, float, float, float, float, float] | None
    measure_value: float | None
    measure_unit: str
    adjacency_count: int | None
    is_degenerate: bool | None
    orientation: str
    related_element_ids: tuple[str, ...]
    boundary_regions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TopologyDiagnosticReport:
    """Crash-conscious scalar report produced only on explicit invocation."""

    shape_type: str
    is_valid: bool | None
    is_closed: bool | None
    solid_count: int
    shell_count: int
    bounding_box_mm: tuple[float, float, float, float, float, float] | None
    volume_mm3: float | None
    total_faces: int
    invalid_faces: int
    total_edges: int
    invalid_edges: int
    degenerate_edges: int
    total_vertices: int
    invalid_vertices: int
    suspicious_total: int
    suspicious_elements: tuple[SuspiciousTopologyElement, ...]
    output_limit: int
    bopcheck_status: str = "disabled_for_safety"


def inspect_topology(
    shape: object,
    *,
    suspicious_limit: int = DEFAULT_SUSPICIOUS_ELEMENT_LIMIT,
) -> TopologyDiagnosticReport:
    """Inspect subshapes read-only in deterministic FreeCAD topology order.

    This explicit diagnostic calls ``isValid()`` only on individual faces,
    edges, and vertices. It never calls full-shape ``check()``, BOPCheck,
    repair, refinement, copying, or a geometry-producing operation. Python
    exceptions from scalar reads are recorded as unavailable/suspicious facts.
    """
    if shape is None:
        raise NullShapeError("Diagnostic source shape is missing.")
    if _safe_boolean(shape, "isNull") is not False:
        raise NullShapeError("Diagnostic source shape is null or unreadable.")
    if not isinstance(suspicious_limit, int) or suspicious_limit < 0:
        raise InvalidShapeError(
            "Diagnostic suspicious-element limit must be a non-negative integer."
        )

    faces = _items(shape, "Faces")
    edges = _items(shape, "Edges")
    vertices = _items(shape, "Vertexes")
    solids = _items(shape, "Solids")
    shells = _items(shape, "Shells")
    shape_bounds = _bounds(shape)

    edge_index = _TopologyIndex(edges)
    vertex_index = _TopologyIndex(vertices)
    face_edges: list[tuple[int, ...]] = []
    edge_face_incidence: list[list[int]] = [[] for _ in edges]
    for face_number, face in enumerate(faces, start=1):
        indices: list[int] = []
        for edge in _items(face, "Edges"):
            index = edge_index.find(edge)
            if index is not None:
                indices.append(index)
                edge_face_incidence[index - 1].append(face_number)
        face_edges.append(tuple(indices))

    edge_vertices: list[tuple[int, ...]] = []
    vertex_edge_incidence: list[list[int]] = [[] for _ in vertices]
    for edge_number, edge in enumerate(edges, start=1):
        indices = []
        for vertex in _items(edge, "Vertexes"):
            index = vertex_index.find(vertex)
            if index is not None:
                indices.append(index)
                vertex_edge_incidence[index - 1].append(edge_number)
        edge_vertices.append(tuple(indices))

    suspicious: list[SuspiciousTopologyElement] = []
    invalid_faces = 0
    for index, face in enumerate(faces, start=1):
        validity = _safe_boolean(face, "isValid")
        area = _safe_float(face, "Area")
        reasons = []
        if validity is False:
            invalid_faces += 1
            reasons.append("invalid")
        elif validity is None:
            reasons.append("validity_unavailable")
        if area is None:
            reasons.append("area_unavailable")
        elif area <= 0.0:
            reasons.append("non_positive_area")
        if reasons:
            suspicious.append(
                _element(
                    "Face",
                    index,
                    tuple(reasons),
                    face,
                    area,
                    "mm^2",
                    len(face_edges[index - 1]),
                    None,
                    tuple(f"Edge{item}" for item in face_edges[index - 1]),
                    shape_bounds,
                )
            )

    invalid_edges = 0
    degenerate_edges = 0
    for index, edge in enumerate(edges, start=1):
        validity = _safe_boolean(edge, "isValid")
        degenerate = _safe_boolean(edge, "isDegenerate")
        length = _safe_float(edge, "Length")
        adjacency = len(edge_face_incidence[index - 1])
        reasons = []
        if validity is False:
            invalid_edges += 1
            reasons.append("invalid")
        elif validity is None:
            reasons.append("validity_unavailable")
        if degenerate is True:
            degenerate_edges += 1
            reasons.append("degenerate")
        if length is None:
            reasons.append("length_unavailable")
        elif length <= 0.0:
            reasons.append("non_positive_length")
        if adjacency != 2:
            reasons.append(f"face_incidence_{adjacency}")
        if reasons:
            related_faces = tuple(
                f"Face{item}"
                for item in _unique_ordered(edge_face_incidence[index - 1])
            )
            related_vertices = tuple(
                f"Vertex{item}" for item in edge_vertices[index - 1]
            )
            suspicious.append(
                _element(
                    "Edge",
                    index,
                    tuple(reasons),
                    edge,
                    length,
                    "mm",
                    adjacency,
                    degenerate,
                    related_faces + related_vertices,
                    shape_bounds,
                )
            )

    invalid_vertices = 0
    for index, vertex in enumerate(vertices, start=1):
        validity = _safe_boolean(vertex, "isValid")
        reasons = []
        if validity is False:
            invalid_vertices += 1
            reasons.append("invalid")
        elif validity is None:
            reasons.append("validity_unavailable")
        if reasons:
            related = tuple(
                f"Edge{item}" for item in vertex_edge_incidence[index - 1]
            )
            suspicious.append(
                _element(
                    "Vertex",
                    index,
                    tuple(reasons),
                    vertex,
                    None,
                    "",
                    len(related),
                    None,
                    related,
                    shape_bounds,
                )
            )

    suspicious.sort(key=_suspicious_sort_key)
    return TopologyDiagnosticReport(
        shape_type=str(getattr(shape, "ShapeType", "Unknown")),
        is_valid=_safe_boolean(shape, "isValid"),
        is_closed=_safe_boolean(shape, "isClosed"),
        solid_count=len(solids),
        shell_count=len(shells),
        bounding_box_mm=shape_bounds,
        volume_mm3=_safe_float(shape, "Volume"),
        total_faces=len(faces),
        invalid_faces=invalid_faces,
        total_edges=len(edges),
        invalid_edges=invalid_edges,
        degenerate_edges=degenerate_edges,
        total_vertices=len(vertices),
        invalid_vertices=invalid_vertices,
        suspicious_total=len(suspicious),
        suspicious_elements=tuple(suspicious[:suspicious_limit]),
        output_limit=suspicious_limit,
    )


def format_topology_diagnostic(report: TopologyDiagnosticReport) -> str:
    """Format one concise console report with an already-limited element list."""
    lines = [
        "PanelOptimizer Geometry Diagnostic",
        "",
        f"Shape type: {report.shape_type}",
        f"Solid valid: {report.is_valid}",
        f"Closed: {report.is_closed}",
        f"Solids: {report.solid_count}",
        f"Shells: {report.shell_count}",
        f"Volume: {_number(report.volume_mm3)} mm^3",
        f"Bounding box: {_format_bounds(report.bounding_box_mm)}",
        f"Invalid faces: {report.invalid_faces} / {report.total_faces}",
        f"Invalid edges: {report.invalid_edges} / {report.total_edges}",
        f"Degenerate edges: {report.degenerate_edges}",
        f"Invalid vertices: {report.invalid_vertices} / {report.total_vertices}",
        f"BOPCheck: {report.bopcheck_status}",
        "",
    ]
    if not report.suspicious_elements:
        lines.append("Suspicious regions: none detected by safe local checks.")
    else:
        lines.append(
            "Suspicious regions: "
            f"{report.suspicious_total} total; showing first "
            f"{len(report.suspicious_elements)}."
        )
        for item in report.suspicious_elements:
            details = [
                f"reasons={','.join(item.reasons)}",
                f"bounds={_format_bounds(item.bounding_box_mm)}",
            ]
            if item.measure_value is not None:
                details.append(
                    f"measure={_number(item.measure_value)} {item.measure_unit}"
                )
            if item.adjacency_count is not None:
                details.append(f"adjacency={item.adjacency_count}")
            if item.is_degenerate is not None:
                details.append(f"degenerate={item.is_degenerate}")
            details.append(f"orientation={item.orientation}")
            if item.related_element_ids:
                details.append("related=" + ",".join(item.related_element_ids))
            if item.boundary_regions:
                details.append("regions=" + ",".join(item.boundary_regions))
            lines.append(f"- {item.element_id}: " + "; ".join(details))
    return "\n".join(lines) + "\n"


class _TopologyIndex:
    """Resolve subshape identity using hash buckets plus exact ``isSame``."""

    def __init__(self, items: tuple[object, ...]) -> None:
        self._items = items
        self._buckets: dict[int | None, list[int]] = {}
        for index, item in enumerate(items, start=1):
            self._buckets.setdefault(_hash_code(item), []).append(index)

    def find(self, candidate: object) -> int | None:
        """Return the stable one-based source index for one topology item."""
        key = _hash_code(candidate)
        indices = self._buckets.get(key, ())
        for index in indices:
            if _is_same(candidate, self._items[index - 1]):
                return index
        if key is None:
            for index, item in enumerate(self._items, start=1):
                if _is_same(candidate, item):
                    return index
        return None


def _element(
    kind: str,
    index: int,
    reasons: tuple[str, ...],
    shape: object,
    measure: float | None,
    unit: str,
    adjacency: int | None,
    degenerate: bool | None,
    related: tuple[str, ...],
    source_bounds: tuple[float, float, float, float, float, float] | None,
) -> SuspiciousTopologyElement:
    """Create one immutable suspicious-element record."""
    bounds = _bounds(shape)
    return SuspiciousTopologyElement(
        element_id=f"{kind}{index}",
        element_type=str(getattr(shape, "ShapeType", kind)),
        source_index=index,
        reasons=reasons,
        bounding_box_mm=bounds,
        measure_value=measure,
        measure_unit=unit,
        adjacency_count=adjacency,
        is_degenerate=degenerate,
        orientation=str(getattr(shape, "Orientation", "Unknown")),
        related_element_ids=related,
        boundary_regions=_boundary_regions(bounds, source_bounds),
    )


def _boundary_regions(
    bounds: tuple[float, float, float, float, float, float] | None,
    source: tuple[float, float, float, float, float, float] | None,
) -> tuple[str, ...]:
    """Label only evidenced proximity to global top, bottom, or outer border."""
    if bounds is None or source is None:
        return ()
    labels = []
    if abs(bounds[2] - source[2]) <= DIAGNOSTIC_BOUNDARY_TOLERANCE_MM:
        labels.append("bottom_z")
    if abs(bounds[5] - source[5]) <= DIAGNOSTIC_BOUNDARY_TOLERANCE_MM:
        labels.append("top_z")
    if any(
        abs(bounds[index] - source[index])
        <= DIAGNOSTIC_BOUNDARY_TOLERANCE_MM
        for index in (0, 1, 3, 4)
    ):
        labels.append("outer_xy_border")
    return tuple(labels)


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


def _bounds(
    shape: object,
) -> tuple[float, float, float, float, float, float] | None:
    try:
        bounds = shape.BoundBox
        values = tuple(
            float(item)
            for item in (
                bounds.XMin,
                bounds.YMin,
                bounds.ZMin,
                bounds.XMax,
                bounds.YMax,
                bounds.ZMax,
            )
        )
        return values if all(math.isfinite(item) for item in values) else None
    except (AttributeError, TypeError, ValueError):
        return None


def _items(shape: object, name: str) -> tuple[object, ...]:
    try:
        return tuple(getattr(shape, name, ()))
    except Exception as error:
        raise InvalidShapeError(
            f"Diagnostic source cannot expose {name.lower()}."
        ) from error


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


def _unique_ordered(values: list[int]) -> tuple[int, ...]:
    return tuple(dict.fromkeys(values))


def _suspicious_sort_key(item: SuspiciousTopologyElement) -> tuple[int, int]:
    order = {"Face": 0, "Edge": 1, "Vertex": 2}
    prefix = item.element_id.rstrip("0123456789")
    return order.get(prefix, 3), item.source_index


def _number(value: float | None) -> str:
    return "unavailable" if value is None else format(value, ".12g")


def _format_bounds(
    values: tuple[float, float, float, float, float, float] | None,
) -> str:
    if values is None:
        return "unavailable"
    return "(" + ", ".join(format(value, ".12g") for value in values) + ") mm"

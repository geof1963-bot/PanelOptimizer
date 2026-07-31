# -*- coding: utf-8 -*-
"""Focused local patch reconstruction and transactional mesh export.

This module operates only on transient meshes made from the four closed V4.21
parts.  It neither repairs B-reps nor changes split geometry.  Open mesh
boundaries are accepted only when their vertices lie on one exact neighboring
facet plane within the mesh movement ceiling.  The existing boundary polygon
is triangulated and added with the orientation required by adjacent facets.
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass
from pathlib import Path

from .Exceptions import ExportError, SplitOperationError, STLExportError
from .MacroSplitCore import MacroSplitResult
from .Settings import Settings
from .SplittingUtilities import finite_positive

LINEAR_DEFLECTION_MM = 0.1
ANGULAR_DEFLECTION_DEGREES = 15.0
RELATIVE_DEFLECTION = False
MAXIMUM_VERTEX_MOVEMENT_MM = 0.02
MESH_POINT_MATCH_TOLERANCE_MM = 1.0e-6
MESH_BOUNDS_TOLERANCE_MM = LINEAR_DEFLECTION_MM
MESH_VOLUME_RELATIVE_TOLERANCE = 0.005
MAX_RESIDUAL_OPEN_EDGES = 8
MAX_RESIDUAL_LOOP_PERIMETER_MM = 20.0
MAX_RESIDUAL_LOOP_AREA_MM2 = 25.0
MAX_RESIDUAL_PLANARITY_DEVIATION_MM = 0.02

PART_NAMES = ("Part_1", "Part_2", "Part_3", "Part_4")
QUADRANTS = ("lower_left", "lower_right", "upper_left", "upper_right")

__all__ = [
    "ANGULAR_DEFLECTION_DEGREES",
    "LINEAR_DEFLECTION_MM",
    "MAXIMUM_VERTEX_MOVEMENT_MM",
    "MeshExportArtifact",
    "MeshMetrics",
    "MeshPartResult",
    "MeshPatchObservation",
    "MeshPatchRebuilder",
    "build_macro_mesh_parts",
    "export_mesh_parts",
]


@dataclass(frozen=True, slots=True)
class MeshMetrics:
    """Scalar topology and geometry facts for one transient mesh."""

    triangle_count: int
    vertex_count: int
    connected_component_count: int
    open_edge_count: int
    non_manifold_edge_count: int
    degenerate_facet_count: int
    is_solid: bool
    volume_mm3: float
    bounds_mm: tuple[float, float, float, float, float, float]
    size_mm: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class MeshPatchObservation:
    """Descriptive evidence for one reconstructed missing surface patch."""

    patch_index: int
    patch_type: str
    boundary_vertex_count: int
    boundary_edge_count: int
    inner_boundary_count: int
    boundary_perimeter_mm: float
    bounds_mm: tuple[float, float, float, float, float, float]
    average_z_mm: float
    normal: tuple[float, float, float]
    planarity_deviation_mm: float
    triangle_count: int
    area_mm2: float
    boundary_endpoints_mm: tuple[tuple[float, float, float], ...] = ()
    boundary_edge_lengths_mm: tuple[float, ...] = ()
    nearest_local_surface: str = "adjacent mesh facets"


@dataclass(frozen=True, slots=True)
class MeshPartResult:
    """Runtime mesh plus immutable validation facts for one V4.21 quadrant."""

    name: str
    quadrant: str
    mesh: object
    source_brep_valid: bool
    source_brep_closed: bool
    source_brep_volume_mm3: float
    before: MeshMetrics
    after: MeshMetrics
    patches: tuple[MeshPatchObservation, ...]
    triangles_added: int
    vertices_added: int
    maximum_vertex_movement_mm: float
    within_x_limit: bool
    within_y_limit: bool
    is_printable: bool


@dataclass(frozen=True, slots=True)
class MeshExportArtifact:
    """One committed STL and its mandatory reopened-mesh validation."""

    name: str
    file_path: str
    byte_count: int
    reopened: MeshMetrics


def _clean_mesh(mesh: object) -> None:
    """Apply only the conservative cleanup approved for V4.24/V4.26."""
    mesh.removeDuplicatedPoints()
    mesh.removeDuplicatedFacets()
    mesh.fixDegenerations()
    mesh.removeInvalidPoints()
    mesh.harmonizeNormals()


def _vector(point: object) -> tuple[float, float, float]:
    return (float(point.x), float(point.y), float(point.z))


def _subtract(first, second):
    return tuple(first[index] - second[index] for index in range(3))


def _dot(first, second) -> float:
    return sum(first[index] * second[index] for index in range(3))


def _length(value) -> float:
    return math.sqrt(_dot(value, value))


def _normalize(value) -> tuple[float, float, float]:
    magnitude = _length(value)
    if not math.isfinite(magnitude) or magnitude <= 1.0e-15:
        raise SplitOperationError("Mesh patch normal is unavailable.")
    return tuple(item / magnitude for item in value)


def _mesh_topology(mesh: object):
    points_raw, facets_raw = mesh.Topology
    points = tuple(_vector(point) for point in points_raw)
    facets = tuple(tuple(map(int, facet)) for facet in facets_raw)
    incidence: dict[tuple[int, int], list[int]] = {}
    for facet_index, facet in enumerate(facets):
        for first, second in (
            (facet[0], facet[1]),
            (facet[1], facet[2]),
            (facet[2], facet[0]),
        ):
            incidence.setdefault(tuple(sorted((first, second))), []).append(
                facet_index
            )
    boundary = tuple(
        sorted(edge for edge, owners in incidence.items() if len(owners) == 1)
    )
    return points, facets, incidence, boundary


def _boundary_cycles(boundary: tuple[tuple[int, int], ...]):
    """Return deterministic edge-disjoint cycles, including figure-eights."""
    adjacency: dict[int, set[int]] = {}
    for first, second in boundary:
        adjacency.setdefault(first, set()).add(second)
        adjacency.setdefault(second, set()).add(first)
    cycles: set[tuple[int, ...]] = set()
    for start in sorted(adjacency):
        def visit(current, path, visited):
            for neighbor in sorted(adjacency[current]):
                if neighbor == start and len(path) >= 3:
                    cycle = tuple(path)
                    variants = []
                    for oriented in (cycle, tuple(reversed(cycle))):
                        for offset in range(len(oriented)):
                            variants.append(oriented[offset:] + oriented[:offset])
                    cycles.add(min(variants))
                elif neighbor not in visited and neighbor >= start:
                    visit(neighbor, path + (neighbor,), visited | {neighbor})
        visit(start, (start,), {start})
    unused = set(boundary)
    selected = []
    for cycle in sorted(cycles, key=lambda item: (len(item), item)):
        edges = {
            tuple(sorted((cycle[index], cycle[(index + 1) % len(cycle)])))
            for index in range(len(cycle))
        }
        if edges and edges <= unused:
            selected.append(cycle)
            unused -= edges
    if unused:
        raise SplitOperationError(
            f"Mesh boundary contains {len(unused)} ambiguous non-cycle edges."
        )
    return tuple(selected)


def _directed_edge(facet, first: int, second: int) -> bool:
    return any(
        facet[index] == first and facet[(index + 1) % 3] == second
        for index in range(3)
    )


def _triangle_area(first, second, third) -> float:
    one = _subtract(second, first)
    two = _subtract(third, first)
    cross = (
        one[1] * two[2] - one[2] * two[1],
        one[2] * two[0] - one[0] * two[2],
        one[0] * two[1] - one[1] * two[0],
    )
    return _length(cross) / 2.0


def mesh_metrics(mesh: object) -> MeshMetrics:
    """Measure exact mesh topology without inventing unavailable checks."""
    points, facets, incidence, boundary = _mesh_topology(mesh)
    bounds = mesh.BoundBox
    non_manifold = sum(len(owners) > 2 for owners in incidence.values())
    degenerate = sum(bool(facet.isDegenerated()) for facet in mesh.Facets)
    return MeshMetrics(
        triangle_count=int(mesh.CountFacets),
        vertex_count=int(mesh.CountPoints),
        connected_component_count=int(mesh.countComponents()),
        open_edge_count=len(boundary),
        non_manifold_edge_count=non_manifold,
        degenerate_facet_count=degenerate,
        is_solid=bool(mesh.isSolid()),
        volume_mm3=float(mesh.Volume),
        bounds_mm=(
            float(bounds.XMin), float(bounds.YMin), float(bounds.ZMin),
            float(bounds.XMax), float(bounds.YMax), float(bounds.ZMax),
        ),
        size_mm=(
            float(bounds.XLength), float(bounds.YLength), float(bounds.ZLength)
        ),
    )


class MeshPatchRebuilder:
    """Tessellate one closed part and reconstruct only planar mesh gaps."""

    def rebuild(self, source_shape: object, timings: dict | None = None) -> tuple[object, MeshMetrics, MeshMetrics, tuple[MeshPatchObservation, ...], int, int, float]:
        """Return one validated watertight mesh without changing the B-rep."""
        try:
            if (
                source_shape is None
                or not source_shape.isClosed()
                or len(source_shape.Solids) != 1
                or float(source_shape.Volume) <= 0.0
            ):
                raise SplitOperationError(
                    "Mesh patching requires one closed positive-volume part."
                )
            source_bounds = source_shape.BoundBox
            import MeshPart

            started = time.perf_counter()
            mesh = MeshPart.meshFromShape(
                Shape=source_shape,
                LinearDeflection=LINEAR_DEFLECTION_MM,
                AngularDeflection=math.radians(ANGULAR_DEFLECTION_DEGREES),
                Relative=RELATIVE_DEFLECTION,
            )
            _clean_mesh(mesh)
            if timings is not None:
                timings["mesh"] = timings.get("mesh", 0.0) + time.perf_counter() - started
        except SplitOperationError:
            raise
        except Exception as error:
            raise SplitOperationError("Unable to tessellate the V4.21 part.") from error
        started = time.perf_counter()
        result = self.rebuild_mesh(mesh, source_shape)
        if timings is not None:
            timings["mesh_repair"] = (
                timings.get("mesh_repair", 0.0) + time.perf_counter() - started
            )
        return result

    def rebuild_mesh(self, mesh: object, source_shape: object):
        """Reconstruct supported local patches in an existing transient mesh.

        This entry point exists so focused tests and diagnostic tools can use
        the same repair logic without changing the fixed V4.24 tessellation.
        The source shape is read only for bounds and volume validation.
        """
        try:
            import Mesh

            working = mesh.copy()
            _clean_mesh(working)
            source_bounds = source_shape.BoundBox
            source_volume = float(source_shape.Volume)
        except Exception as error:
            raise SplitOperationError("Unable to inspect transient mesh input.") from error
        before = mesh_metrics(working)
        if before.triangle_count <= 0 or before.connected_component_count != 1:
            raise SplitOperationError(
                "Tessellated part is empty or has multiple components."
            )
        points, facets, incidence, boundary = _mesh_topology(working)
        cycles = _boundary_cycles(boundary)
        groups = self._group_coplanar_cycles(cycles, points, facets, incidence, working.Facets)
        mutable_points = list(points)
        added: list[tuple[int, int, int]] = []
        observations = []
        for patch_index, (outer, holes) in enumerate(groups, start=1):
            triangles, new_points, observation = self._patch_group(
                patch_index, outer, holes, points, facets, incidence,
                working.Facets, mutable_points,
            )
            added.extend(triangles)
            mutable_points.extend(new_points)
            observations.append(observation)
        try:
            import FreeCAD
            repaired = Mesh.Mesh(
                (
                    [FreeCAD.Vector(*point) for point in mutable_points],
                    list(facets + tuple(added)),
                )
            )
            repaired.harmonizeNormals()
        except Exception as error:
            raise SplitOperationError("Unable to assemble local mesh patches.") from error
        after = mesh_metrics(repaired)
        residual_observations = ()
        residual_triangles = 0
        if (
            0 < after.open_edge_count <= MAX_RESIDUAL_OPEN_EDGES
            and after.non_manifold_edge_count == 0
            and after.connected_component_count == 1
        ):
            repaired, residual_observations, residual_triangles = (
                self._close_residual_boundaries(repaired, len(observations))
            )
            observations.extend(residual_observations)
            after = mesh_metrics(repaired)
        self._validate_repaired(
            before,
            after,
            source_volume,
            source_bounds,
        )
        return (
            repaired,
            before,
            after,
            tuple(observations),
            len(added) + residual_triangles,
            len(mutable_points) - len(points),
            0.0,
        )

    def _close_residual_boundaries(self, mesh, patch_index_offset=0):
        """Close only tiny residual cycles using their existing vertices."""
        try:
            import FreeCAD
            import Mesh

            points, facets, incidence, boundary = _mesh_topology(mesh)
            cycles = _boundary_cycles(boundary)
        except SplitOperationError:
            raise
        except Exception as error:
            raise SplitOperationError(
                "Unable to inspect residual mesh boundaries."
            ) from error
        if not cycles:
            return mesh, (), 0

        added = []
        observations = []
        for offset, cycle in enumerate(cycles, start=1):
            centroid, normal, deviation = self._cycle_plane(
                cycle, points, facets, incidence, mesh.Facets
            )
            oriented = self._oriented_cycle(cycle, facets, incidence)
            perimeter = sum(
                _length(_subtract(
                    points[cycle[(index + 1) % len(cycle)]],
                    points[cycle[index]],
                ))
                for index in range(len(cycle))
            )
            basis = self._plane_basis(normal)
            polygon = tuple(
                self._project(points[index], centroid, basis)
                for index in cycle
            )
            area = abs(self._signed_area(polygon))
            if (
                len(cycle) > MAX_RESIDUAL_OPEN_EDGES
                or perimeter > MAX_RESIDUAL_LOOP_PERIMETER_MM
                or area > MAX_RESIDUAL_LOOP_AREA_MM2
                or deviation > MAX_RESIDUAL_PLANARITY_DEVIATION_MM
            ):
                endpoints = tuple(points[index] for index in cycle)
                lengths = tuple(
                    _length(_subtract(
                        points[cycle[(index + 1) % len(cycle)]],
                        points[cycle[index]],
                    ))
                    for index in range(len(cycle))
                )
                raise SplitOperationError(
                    "Residual mesh boundary is not a safe tiny patch: "
                    f"edges={len(cycle)}, endpoints={endpoints}, "
                    f"lengths={lengths}, perimeter={perimeter:.6f} mm, "
                    f"area={area:.6f} mm^2, planarity="
                    f"{deviation:.6f} mm."
                )
            triangles = self._minimal_cycle_triangles(oriented, points)
            added.extend(triangles)
            bounds = tuple(
                min(points[index][axis] for index in cycle)
                for axis in range(3)
            ) + tuple(
                max(points[index][axis] for index in cycle)
                for axis in range(3)
            )
            observations.append(MeshPatchObservation(
                patch_index=patch_index_offset + offset,
                patch_type="tiny_residual_loop",
                boundary_vertex_count=len(cycle),
                boundary_edge_count=len(cycle),
                inner_boundary_count=0,
                boundary_perimeter_mm=perimeter,
                bounds_mm=bounds,
                average_z_mm=centroid[2],
                normal=normal,
                planarity_deviation_mm=deviation,
                triangle_count=len(triangles),
                area_mm2=sum(
                    _triangle_area(points[a], points[b], points[c])
                    for a, b, c in triangles
                ),
                boundary_endpoints_mm=tuple(points[index] for index in cycle),
                boundary_edge_lengths_mm=tuple(
                    _length(_subtract(
                        points[cycle[(index + 1) % len(cycle)]],
                        points[cycle[index]],
                    ))
                    for index in range(len(cycle))
                ),
                nearest_local_surface=(
                    "adjacent mesh facets; normal "
                    f"({normal[0]:.6f}, {normal[1]:.6f}, {normal[2]:.6f})"
                ),
            ))
        repaired = Mesh.Mesh((
            [FreeCAD.Vector(*point) for point in points],
            list(facets + tuple(added)),
        ))
        repaired.harmonizeNormals()
        return repaired, tuple(observations), len(added)

    @staticmethod
    def _minimal_cycle_triangles(cycle, points):
        """Triangulate a tiny cycle without adding or moving vertices."""
        if len(cycle) == 3:
            return (tuple(cycle),)
        if len(cycle) == 4:
            first = _length(_subtract(points[cycle[0]], points[cycle[2]]))
            second = _length(_subtract(points[cycle[1]], points[cycle[3]]))
            if first <= second:
                return (
                    (cycle[0], cycle[1], cycle[2]),
                    (cycle[0], cycle[2], cycle[3]),
                )
            return (
                (cycle[1], cycle[2], cycle[3]),
                (cycle[1], cycle[3], cycle[0]),
            )
        return tuple(
            (cycle[0], cycle[index], cycle[index + 1])
            for index in range(1, len(cycle) - 1)
        )

    @staticmethod
    def _cycle_plane(cycle, points, facets, incidence, mesh_facets):
        normals = []
        for index in range(len(cycle)):
            edge = tuple(sorted((cycle[index], cycle[(index + 1) % len(cycle)])))
            normals.append(_vector(mesh_facets[incidence[edge][0]].Normal))
        # A whole missing face has only transverse neighboring facets, so its
        # own boundary-derived Newell normal is also an exact plane candidate.
        newell = [0.0, 0.0, 0.0]
        for index, current_index in enumerate(cycle):
            current = points[current_index]
            following = points[cycle[(index + 1) % len(cycle)]]
            newell[0] += (current[1] - following[1]) * (current[2] + following[2])
            newell[1] += (current[2] - following[2]) * (current[0] + following[0])
            newell[2] += (current[0] - following[0]) * (current[1] + following[1])
        normals.append(tuple(newell))
        centroid = tuple(
            sum(points[index][axis] for index in cycle) / len(cycle)
            for axis in range(3)
        )
        candidates = []
        for value in normals:
            try:
                normal = _normalize(value)
            except SplitOperationError:
                continue
            deviation = max(
                abs(_dot(_subtract(points[index], centroid), normal))
                for index in cycle
            )
            candidates.append(
                (deviation, tuple(round(item, 12) for item in normal), normal)
            )
        if not candidates:
            raise SplitOperationError(
                "Mesh boundary has no valid neighboring plane."
            )
        deviation, _, normal = min(candidates)
        if deviation > MAXIMUM_VERTEX_MOVEMENT_MM:
            raise SplitOperationError(
                "Mesh boundary is non-planar or ambiguous: "
                f"deviation {deviation:g} mm exceeds "
                f"{MAXIMUM_VERTEX_MOVEMENT_MM:g} mm."
            )
        return centroid, normal, deviation

    @staticmethod
    def _plane_basis(normal):
        reference = (1.0, 0.0, 0.0) if abs(normal[0]) < 0.8 else (0.0, 1.0, 0.0)
        first = _normalize((
            normal[1] * reference[2] - normal[2] * reference[1],
            normal[2] * reference[0] - normal[0] * reference[2],
            normal[0] * reference[1] - normal[1] * reference[0],
        ))
        second = (
            normal[1] * first[2] - normal[2] * first[1],
            normal[2] * first[0] - normal[0] * first[2],
            normal[0] * first[1] - normal[1] * first[0],
        )
        return first, second

    @staticmethod
    def _project(point, origin, basis):
        offset = _subtract(point, origin)
        return (_dot(offset, basis[0]), _dot(offset, basis[1]))

    @staticmethod
    def _signed_area(polygon):
        return sum(
            polygon[index][0] * polygon[(index + 1) % len(polygon)][1]
            - polygon[(index + 1) % len(polygon)][0] * polygon[index][1]
            for index in range(len(polygon))
        ) / 2.0

    @staticmethod
    def _contains(polygon, point):
        inside = False
        x_value, y_value = point
        for index, first in enumerate(polygon):
            second = polygon[(index + 1) % len(polygon)]
            if ((first[1] > y_value) != (second[1] > y_value)):
                crossing = (
                    (second[0] - first[0]) * (y_value - first[1])
                    / (second[1] - first[1]) + first[0]
                )
                if x_value < crossing:
                    inside = not inside
        return inside

    def _group_coplanar_cycles(self, cycles, points, facets, incidence, mesh_facets):
        """Group nested coplanar boundaries as outer polygon plus holes."""
        records = []
        for cycle in cycles:
            centroid, normal, deviation = self._cycle_plane(
                cycle, points, facets, incidence, mesh_facets
            )
            basis = self._plane_basis(normal)
            polygon = tuple(self._project(points[index], centroid, basis) for index in cycle)
            records.append((cycle, centroid, normal, deviation, basis, abs(self._signed_area(polygon))))
        parents = [None] * len(records)
        for child_index, child in enumerate(records):
            candidates = []
            child_point = points[child[0][0]]
            for outer_index, outer in enumerate(records):
                if outer_index == child_index or outer[5] <= child[5]:
                    continue
                if abs(_dot(child[2], outer[2])) < 1.0 - 1.0e-8:
                    continue
                if abs(_dot(_subtract(child_point, outer[1]), outer[2])) > MAXIMUM_VERTEX_MOVEMENT_MM:
                    continue
                outer_polygon = tuple(
                    self._project(points[index], outer[1], outer[4]) for index in outer[0]
                )
                if self._contains(outer_polygon, self._project(child_point, outer[1], outer[4])):
                    candidates.append((outer[5], outer_index))
            if candidates:
                parents[child_index] = min(candidates)[1]
        depths = []
        for index in range(len(records)):
            depth, current, seen = 0, index, set()
            while parents[current] is not None:
                if current in seen:
                    raise SplitOperationError("Nested mesh boundaries are cyclic.")
                seen.add(current)
                current = parents[current]
                depth += 1
            depths.append(depth)
        groups = []
        for index, record in enumerate(records):
            if depths[index] % 2:
                continue
            holes = tuple(
                records[child][0]
                for child in range(len(records))
                if parents[child] == index and depths[child] == depths[index] + 1
            )
            groups.append((record[0], holes))
        return tuple(groups)

    @staticmethod
    def _oriented_cycle(cycle, facets, incidence):
        first, second = cycle[0], cycle[1]
        owner = incidence[tuple(sorted((first, second)))][0]
        return (
            tuple(reversed(cycle))
            if _directed_edge(facets[owner], first, second)
            else cycle
        )

    def _patch_group(
        self, patch_index, outer, holes, points, facets, incidence,
        mesh_facets, mutable_points,
    ):
        """Triangulate one planar polygon while preserving nested holes."""
        centroid, normal, deviation = self._cycle_plane(
            outer, points, facets, incidence, mesh_facets
        )
        oriented_outer = self._oriented_cycle(outer, facets, incidence)
        if not holes:
            # The real defects are often near-collinear strips which OCC does
            # not accept as standalone Face wires. Their existing ordered
            # boundary still defines the exact missing triangle fan.
            triangles = tuple(
                (oriented_outer[0], oriented_outer[index], oriented_outer[index + 1])
                for index in range(1, len(oriented_outer) - 1)
            )
            new_points = []
        else:
            triangles, new_points = self._triangulate_with_holes(
                patch_index, oriented_outer, holes, points, centroid, normal,
                mutable_points,
            )
        if not triangles:
            raise SplitOperationError(
                f"Mesh patch {patch_index} has no positive-area triangles."
            )
        if any(len(set(triangle)) != 3 for triangle in triangles):
            raise SplitOperationError(
                f"Mesh patch {patch_index} triangulation is degenerate."
            )
        patch_area = sum(
            _triangle_area((mutable_points + new_points)[a], (mutable_points + new_points)[b], (mutable_points + new_points)[c])
            for a, b, c in triangles
        )
        bounds = tuple(
            min(points[index][axis] for cycle in (outer,) + holes for index in cycle) for axis in range(3)
        ) + tuple(
            max(points[index][axis] for cycle in (outer,) + holes for index in cycle) for axis in range(3)
        )
        perimeter = sum(
            _length(
                _subtract(
                    points[cycle[(index + 1) % len(cycle)]],
                    points[cycle[index]],
                )
            )
            for cycle in (outer,) + holes
            for index in range(len(cycle))
        )
        patch_type = (
            "planar_horizontal"
            if abs(normal[2]) >= 0.999
            else "planar_vertical"
            if abs(normal[2]) <= 0.001
            else "narrow_planar_strip"
        )
        return triangles, new_points, MeshPatchObservation(
            patch_index=patch_index,
            patch_type=patch_type,
            boundary_vertex_count=sum(len(cycle) for cycle in (outer,) + holes),
            boundary_edge_count=sum(len(cycle) for cycle in (outer,) + holes),
            inner_boundary_count=len(holes),
            boundary_perimeter_mm=perimeter,
            bounds_mm=bounds,
            average_z_mm=centroid[2],
            normal=normal,
            planarity_deviation_mm=deviation,
            triangle_count=len(triangles),
            area_mm2=patch_area,
        )

    def _triangulate_with_holes(
        self, patch_index, oriented_outer, holes, points, centroid, normal,
        mutable_points,
    ):
        """Triangulate one valid planar face while retaining its inner wires."""
        try:
            import FreeCAD
            import MeshPart
            import Part

            def make_wire(cycle):
                vertices = [FreeCAD.Vector(*points[index]) for index in cycle]
                vertices.append(vertices[0])
                return Part.Wire(Part.makePolygon(vertices).Edges)

            outer_wire = make_wire(oriented_outer)
            inner_wires = []
            basis = self._plane_basis(normal)
            outer_polygon = tuple(
                self._project(points[index], centroid, basis)
                for index in oriented_outer
            )
            outer_sign = self._signed_area(outer_polygon)
            for hole in holes:
                wire = make_wire(hole)
                # OCC requires inner wires to oppose the outer wire.
                hole_polygon = tuple(
                    self._project(points[index], centroid, basis)
                    for index in hole
                )
                if self._signed_area(hole_polygon) * outer_sign > 0.0:
                    wire.reverse()
                inner_wires.append(wire)
            face = Part.Face([outer_wire] + inner_wires)
            if face.isNull() or not face.isValid() or float(face.Area) <= 0.0:
                raise SplitOperationError(f"Mesh patch {patch_index} polygon is invalid.")
            patch_mesh = MeshPart.meshFromShape(
                Shape=face,
                LinearDeflection=LINEAR_DEFLECTION_MM,
                AngularDeflection=math.radians(ANGULAR_DEFLECTION_DEGREES),
                Relative=RELATIVE_DEFLECTION,
            )
            patch_points_raw, patch_facets_raw = patch_mesh.Topology
        except SplitOperationError:
            raise
        except Exception as error:
            raise SplitOperationError(
                f"Unable to triangulate mesh patch {patch_index}."
            ) from error

        new_points = []
        mapped = []
        for raw in patch_points_raw:
            point = _vector(raw)
            candidates = [
                (_length(_subtract(point, existing)), index)
                for index, existing in enumerate(mutable_points + new_points)
            ]
            distance, index = min(candidates)
            if distance <= MESH_POINT_MATCH_TOLERANCE_MM:
                mapped.append(index)
            else:
                mapped.append(len(mutable_points) + len(new_points))
                new_points.append(point)
        triangles = tuple(tuple(mapped[int(index)] for index in facet) for facet in patch_facets_raw)
        if triangles:
            boundary_first, boundary_second = oriented_outer[:2]
            patch_directed = any(
                _directed_edge(triangle, boundary_first, boundary_second)
                for triangle in triangles
            )
            patch_reversed = any(
                _directed_edge(triangle, boundary_second, boundary_first)
                for triangle in triangles
            )
            if not patch_directed and not patch_reversed:
                raise SplitOperationError(
                    f"Mesh patch {patch_index} lost its source boundary identity."
                )
            if patch_reversed:
                triangles = tuple((a, c, b) for a, b, c in triangles)
        return triangles, new_points

    @staticmethod
    def _validate_repaired(before, after, source_volume, source_bounds):
        if (
            after.open_edge_count != 0
            or after.non_manifold_edge_count != 0
            or after.connected_component_count != 1
            or not after.is_solid
        ):
            raise SplitOperationError(
                "Local mesh patches did not produce one watertight manifold: "
                f"open={after.open_edge_count}, "
                f"non-manifold={after.non_manifold_edge_count}, "
                f"components={after.connected_component_count}, "
                f"solid={after.is_solid}."
            )
        if any(
            abs(first - second) > MESH_BOUNDS_TOLERANCE_MM
            for first, second in zip(before.bounds_mm, after.bounds_mm)
        ):
            raise SplitOperationError("Local mesh patches changed part bounds.")
        if abs(after.volume_mm3 - source_volume) > max(
            1.0e-6, abs(source_volume) * MESH_VOLUME_RELATIVE_TOLERANCE
        ):
            raise SplitOperationError("Repaired mesh volume is incoherent with its V4.21 part.")
        expected = (
            float(source_bounds.XMin), float(source_bounds.YMin), float(source_bounds.ZMin),
            float(source_bounds.XMax), float(source_bounds.YMax), float(source_bounds.ZMax),
        )
        if any(
            actual < lower - MESH_BOUNDS_TOLERANCE_MM
            or actual > upper + MESH_BOUNDS_TOLERANCE_MM
            for actual, lower, upper in zip(
                after.bounds_mm,
                expected,
                expected,
            )
        ):
            raise SplitOperationError("Repaired mesh extends outside source bounds.")


def build_macro_mesh_parts(
    macro_result: MacroSplitResult,
    split_settings: object = Settings.Split,
    timings: dict | None = None,
) -> tuple[MeshPartResult, ...]:
    """Classify and rebuild the four closed solids produced by V4.21."""
    if not isinstance(macro_result, MacroSplitResult):
        raise SplitOperationError("Mesh workflow requires a MacroSplitResult.")
    try:
        solids = tuple(macro_result.shape.Solids)
    except Exception as error:
        raise SplitOperationError("Unable to read V4.21 result solids.") from error
    if len(solids) != 4:
        raise SplitOperationError(
            f"V4.21 mesh workflow requires four solids; found {len(solids)}."
        )
    quadrants: dict[tuple[bool, bool], list[object]] = {}
    for solid in solids:
        center = solid.CenterOfMass
        key = (
            float(center.x) >= macro_result.cut_x_mm,
            float(center.y) >= macro_result.cut_y_mm,
        )
        quadrants.setdefault(key, []).append(solid)
    keys = ((False, False), (True, False), (False, True), (True, True))
    if tuple(len(quadrants.get(key, ())) for key in keys) != (1, 1, 1, 1):
        raise SplitOperationError(
            "V4.21 solids do not map one-to-one to the four quadrants."
        )
    ordered = tuple(quadrants[key][0] for key in keys)
    maximum_width = finite_positive(
        split_settings.MAX_PART_WIDTH, "Settings.Split.MAX_PART_WIDTH"
    )
    maximum_height = finite_positive(
        split_settings.MAX_PART_HEIGHT, "Settings.Split.MAX_PART_HEIGHT"
    )
    rebuilder = MeshPatchRebuilder()
    results = []
    for name, quadrant, solid in zip(PART_NAMES, QUADRANTS, ordered):
        rebuilt = rebuilder.rebuild(solid, timings=timings)
        mesh, before, after, patches, triangles, vertices, movement = rebuilt
        within_x = after.size_mm[0] <= maximum_width
        within_y = after.size_mm[1] <= maximum_height
        results.append(
            MeshPartResult(
                name=name,
                quadrant=quadrant,
                mesh=mesh,
                source_brep_valid=bool(solid.isValid()),
                source_brep_closed=bool(solid.isClosed()),
                source_brep_volume_mm3=float(solid.Volume),
                before=before,
                after=after,
                patches=patches,
                triangles_added=triangles,
                vertices_added=vertices,
                maximum_vertex_movement_mm=movement,
                within_x_limit=within_x,
                within_y_limit=within_y,
                is_printable=within_x and within_y,
            )
        )
    return tuple(results)


def export_mesh_parts(
    parts: tuple[MeshPartResult, ...],
    output_directory: str,
    timings: dict | None = None,
    full_reopen_validation: bool = Settings.Performance.FULL_STL_REOPEN_VALIDATION,
) -> tuple[MeshExportArtifact, ...]:
    """Transactionally export and reopen exactly four validated mesh parts."""
    ordered = tuple(parts)
    if tuple(item.name for item in ordered) != PART_NAMES:
        raise ExportError("Mesh parts are not in deterministic quadrant order.")
    if not all(item.is_printable for item in ordered):
        raise ExportError("Mesh STL export is blocked by configured X/Y limits.")
    try:
        destination = Path(output_directory).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ExportError("Selected mesh export path is unavailable.") from error
    if not destination.is_dir():
        raise ExportError("Selected mesh export path is not a directory.")
    finals = tuple(destination / f"{name}.stl" for name in PART_NAMES)
    temporaries = tuple(
        destination / f".{name}.paneloptimizer.partial.stl" for name in PART_NAMES
    )
    backups = tuple(
        destination / f".{name}.paneloptimizer.backup.stl" for name in PART_NAMES
    )
    if any(path.exists() for path in backups):
        raise STLExportError(
            "Export directory contains a previous PanelOptimizer backup."
        )
    reopened_metrics = []
    try:
        import Mesh

        for path in temporaries:
            if path.exists():
                path.unlink()
        for part, path in zip(ordered, temporaries):
            started = time.perf_counter()
            part.mesh.write(str(path))
            if not path.is_file() or path.stat().st_size <= 0:
                raise STLExportError(f"STL export produced no data for {part.name}.")
            if timings is not None:
                timings["stl_export"] = (
                    timings.get("stl_export", 0.0) + time.perf_counter() - started
                )
            if not full_reopen_validation:
                reopened_metrics.append(part.after)
                continue
            started = time.perf_counter()
            reopened = Mesh.Mesh(str(path))
            _clean_mesh(reopened)
            metrics = mesh_metrics(reopened)
            if (
                metrics.open_edge_count != 0
                or metrics.non_manifold_edge_count != 0
                or metrics.connected_component_count != 1
                or not metrics.is_solid
            ):
                raise STLExportError(
                    f"Reopened STL validation failed for {part.name}."
                )
            if any(
                abs(first - second) > MESH_BOUNDS_TOLERANCE_MM
                for first, second in zip(metrics.bounds_mm, part.after.bounds_mm)
            ):
                raise STLExportError(
                    f"Reopened STL bounds changed for {part.name}."
                )
            reopened_metrics.append(metrics)
            if timings is not None:
                timings["stl_verify"] = (
                    timings.get("stl_verify", 0.0) + time.perf_counter() - started
                )
    except Exception as error:
        _remove_files(temporaries)
        if isinstance(error, (ExportError, STLExportError)):
            raise
        raise STLExportError("Unable to serialize and reopen all four mesh STLs.") from error

    backed_up = []
    committed = []
    try:
        for final, backup in zip(finals, backups):
            if final.exists():
                os.replace(final, backup)
                backed_up.append((final, backup))
        for temporary, final in zip(temporaries, finals):
            os.replace(temporary, final)
            committed.append(final)
    except Exception as error:
        _remove_files(tuple(committed) + temporaries)
        for final, backup in reversed(backed_up):
            if backup.exists():
                os.replace(backup, final)
        raise STLExportError(
            "Unable to commit all four mesh STLs; previous files were restored."
        ) from error
    _remove_files(backups)
    return tuple(
        MeshExportArtifact(
            name=part.name,
            file_path=str(path),
            byte_count=path.stat().st_size,
            reopened=metrics,
        )
        for part, path, metrics in zip(ordered, finals, reopened_metrics)
    )


def _remove_files(paths) -> None:
    for path in paths:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass

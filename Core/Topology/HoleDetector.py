# -*- coding: utf-8 -*-
"""Read-only detection of cylindrical holes and recesses."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from ..Exceptions import TopologyAnalysisError
from ..Models import (
    BoundingBox,
    Direction3D,
    GeometrySnapshot,
    HoleFeature,
    Point3D,
)
from .ConnectivityBuilder import MaterialRegion
from ._Utilities import bounding_box, finite_float, identifier, point, same_shape

__all__ = ["HoleDetector"]


@dataclass(frozen=True, slots=True)
class DetectedHole:
    """Associate an immutable hole feature with its material region."""

    feature: HoleFeature
    owner_index: int
    bounding_box: BoundingBox
    entry_point: Point3D | None
    terminal_point: Point3D | None
    endpoints: tuple[Point3D, Point3D]


class HoleDetector:
    """Detect cylindrical openings without evaluating their usefulness."""

    def detect(
        self,
        geometry: GeometrySnapshot,
        shape: object,
        regions: tuple[MaterialRegion, ...],
    ) -> tuple[DetectedHole, ...]:
        """Detect inward cylindrical faces with two circular endpoints.

        Only cylinders owned by a solid are considered because an open shell
        does not identify which side contains material.  A candidate face must
        oppose its owning solid's orientation; comparing relative orientation
        prevents reversal of an entire solid from turning its exterior wall
        into a false hole.

        Two planar endpoint neighbours and no terminal cap prove a through
        segment.  One single-edge planar cap proves a blind recess.  A segment
        opening into non-planar void geometry remains a non-through hole but
        is not called a dead end.  Fully capped cylinders are enclosed voids
        and are excluded from hole findings.
        """
        faces = tuple(getattr(shape, "Faces", ()))
        detected: list[DetectedHole] = []

        for face in faces:
            surface = getattr(face, "Surface", None)
            if not self._is_cylinder(surface):
                continue

            owner_index = self._owner_index(face, regions)
            if regions[owner_index].node_type != "solid":
                continue
            if not self._is_inward_face(face, regions[owner_index].shape):
                continue

            circular_edges = tuple(
                edge
                for edge in getattr(face, "Edges", ())
                if self._is_closed_circle(edge)
            )
            endpoint_points = self._distinct_circle_centers(circular_edges)
            if len(endpoint_points) != 2:
                continue

            radius = finite_float(
                self._required_attribute(surface, "Radius"),
                "cylinder radius",
            )
            if radius <= 0.0:
                raise TopologyAnalysisError(
                    "A cylindrical hole has a non-positive radius."
                )

            axis = self._normalized_direction(
                self._required_attribute(surface, "Axis")
            )
            endpoints = self._ordered_along_axis(endpoint_points, axis)
            depth = self._distance(endpoints[0], endpoints[1])
            if depth <= 0.0:
                raise TopologyAnalysisError(
                    "A cylindrical hole has zero axial depth."
                )

            capped = tuple(
                self._endpoint_has_terminal_cap(
                    circular_edges,
                    endpoint,
                    face,
                    faces,
                )
                for endpoint in endpoints
            )
            if all(capped):
                continue

            planar_neighbours = tuple(
                self._endpoint_has_planar_neighbour(
                    circular_edges,
                    endpoint,
                    face,
                    faces,
                )
                for endpoint in endpoints
            )
            is_through = not any(capped) and all(planar_neighbours)
            entry_point: Point3D | None = None
            terminal_point: Point3D | None = None
            if capped.count(True) == 1:
                terminal_index = capped.index(True)
                terminal_point = endpoints[terminal_index]
                entry_point = endpoints[1 - terminal_index]

            feature_index = len(detected) + 1
            detected.append(
                DetectedHole(
                    feature=HoleFeature(
                        feature_id=identifier(
                            geometry.source_id,
                            "hole",
                            feature_index,
                        ),
                        center=self._midpoint(*endpoints),
                        axis=axis,
                        diameter_mm=2.0 * radius,
                        depth_mm=depth,
                        is_through_hole=is_through,
                    ),
                    owner_index=owner_index,
                    bounding_box=bounding_box(face),
                    entry_point=entry_point,
                    terminal_point=terminal_point,
                    endpoints=endpoints,
                )
            )

        return self._propagate_non_through_connections(tuple(detected))

    def _propagate_non_through_connections(
        self,
        holes: tuple[DetectedHole, ...],
    ) -> tuple[DetectedHole, ...]:
        """Propagate a capped or cavity-connected state across hole segments.

        Counterbores and stepped holes produce one feature per cylindrical
        segment because ``HoleFeature`` has one diameter.  Segments sharing an
        axial endpoint form one continuous void.  If any segment is not
        through, the connected segments cannot independently be through.
        """
        parents = list(range(len(holes)))

        def find(index: int) -> int:
            while parents[index] != index:
                parents[index] = parents[parents[index]]
                index = parents[index]
            return index

        def union(first: int, second: int) -> None:
            first_root = find(first)
            second_root = find(second)
            if first_root != second_root:
                parents[second_root] = first_root

        for first in range(len(holes)):
            for second in range(first + 1, len(holes)):
                shares_endpoint = any(
                    self._points_equal(first_point, second_point)
                    for first_point in holes[first].endpoints
                    for second_point in holes[second].endpoints
                )
                if shares_endpoint and self._axes_parallel(
                    holes[first].feature.axis,
                    holes[second].feature.axis,
                ):
                    union(first, second)

        non_through_roots = {
            find(index)
            for index, hole in enumerate(holes)
            if not hole.feature.is_through_hole
        }
        return tuple(
            replace(
                hole,
                feature=replace(
                    hole.feature,
                    is_through_hole=False,
                ),
            )
            if find(index) in non_through_roots
            else hole
            for index, hole in enumerate(holes)
        )

    @staticmethod
    def _axes_parallel(
        first: Direction3D,
        second: Direction3D,
    ) -> bool:
        """Return whether two normalized axes are parallel in either direction."""
        dot_product = (
            first.x * second.x
            + first.y * second.y
            + first.z * second.z
        )
        return math.isclose(abs(dot_product), 1.0)

    @staticmethod
    def _is_inward_face(face: object, solid: object) -> bool:
        """Return whether face orientation opposes its owning solid.

        FreeCAD composes face orientation with the solid orientation.  Relative
        comparison therefore remains valid when the complete solid is reversed.
        If a resolver omits solid orientation, the conventional FreeCAD inward
        value is used conservatively.
        """
        face_orientation = str(getattr(face, "Orientation", ""))
        solid_orientation = getattr(solid, "Orientation", None)
        if solid_orientation is None:
            return face_orientation == "Reversed"
        return face_orientation != str(solid_orientation)

    def _owner_index(
        self,
        face: object,
        regions: tuple[MaterialRegion, ...],
    ) -> int:
        """Return the source-order solid or shell containing a face."""
        for index, region in enumerate(regions):
            if any(
                same_shape(face, candidate)
                for candidate in getattr(region.shape, "Faces", ())
            ):
                return index
        raise TopologyAnalysisError(
            "A detected feature cannot be associated with a material region."
        )

    def _endpoint_has_terminal_cap(
        self,
        circular_edges: tuple[object, ...],
        endpoint: Point3D,
        cylinder_face: object,
        all_faces: tuple[object, ...],
    ) -> bool:
        """Return whether an endpoint has a single-edge planar closure."""
        return any(
            len(tuple(getattr(adjacent, "Edges", ()))) == 1
            for adjacent in self._adjacent_endpoint_faces(
                circular_edges,
                endpoint,
                cylinder_face,
                all_faces,
            )
            if self._is_plane(getattr(adjacent, "Surface", None))
        )

    def _endpoint_has_planar_neighbour(
        self,
        circular_edges: tuple[object, ...],
        endpoint: Point3D,
        cylinder_face: object,
        all_faces: tuple[object, ...],
    ) -> bool:
        """Return whether an endpoint meets any planar boundary face."""
        return any(
            self._is_plane(getattr(adjacent, "Surface", None))
            for adjacent in self._adjacent_endpoint_faces(
                circular_edges,
                endpoint,
                cylinder_face,
                all_faces,
            )
        )

    def _adjacent_endpoint_faces(
        self,
        circular_edges: tuple[object, ...],
        endpoint: Point3D,
        cylinder_face: object,
        all_faces: tuple[object, ...],
    ) -> tuple[object, ...]:
        """Return faces sharing circular edges at one cylinder endpoint."""
        endpoint_edges = tuple(
            edge
            for edge in circular_edges
            if self._points_equal(self._circle_center(edge), endpoint)
        )
        adjacent_faces: list[object] = []
        for edge in endpoint_edges:
            for candidate in all_faces:
                if same_shape(candidate, cylinder_face):
                    continue
                if any(
                    same_shape(edge, candidate_edge)
                    for candidate_edge in getattr(candidate, "Edges", ())
                ):
                    if not any(
                        same_shape(candidate, known)
                        for known in adjacent_faces
                    ):
                        adjacent_faces.append(candidate)
        return tuple(adjacent_faces)

    @staticmethod
    def _is_cylinder(surface: object) -> bool:
        """Identify a cylindrical surface without importing FreeCAD."""
        return (
            surface is not None
            and "cylinder" in type(surface).__name__.lower()
            and hasattr(surface, "Radius")
            and hasattr(surface, "Axis")
        )

    @staticmethod
    def _is_plane(surface: object) -> bool:
        """Identify a planar surface without importing FreeCAD."""
        return surface is not None and "plane" in type(surface).__name__.lower()

    @staticmethod
    def _is_closed_circle(edge: object) -> bool:
        """Accept full circular edges and reject arcs and seam lines."""
        curve = getattr(edge, "Curve", None)
        if curve is None or "circle" not in type(curve).__name__.lower():
            return False
        if not hasattr(curve, "Center") or not hasattr(curve, "Radius"):
            return False
        is_closed = getattr(edge, "isClosed", None)
        return bool(is_closed()) if callable(is_closed) else True

    def _distinct_circle_centers(
        self,
        edges: tuple[object, ...],
    ) -> tuple[Point3D, ...]:
        """Collapse duplicate endpoint edges by their geometric centre."""
        centers: list[Point3D] = []
        for edge in edges:
            center = self._circle_center(edge)
            if not any(self._points_equal(center, known) for known in centers):
                centers.append(center)
        return tuple(centers)

    def _circle_center(self, edge: object) -> Point3D:
        """Read one circular edge centre into an immutable point."""
        curve = self._required_attribute(edge, "Curve")
        return point(
            self._required_attribute(curve, "Center"),
            "circle center",
        )

    @staticmethod
    def _ordered_along_axis(
        points: tuple[Point3D, Point3D],
        axis: Direction3D,
    ) -> tuple[Point3D, Point3D]:
        """Order endpoints by projection on their cylinder axis."""
        ordered = sorted(
            points,
            key=lambda point: (
                point.x_mm * axis.x
                + point.y_mm * axis.y
                + point.z_mm * axis.z
            ),
        )
        return ordered[0], ordered[1]

    @staticmethod
    def _normalized_direction(vector: object) -> Direction3D:
        """Convert a vector-like object to a finite unit direction."""
        x_value, y_value, z_value = HoleDetector._coordinates(vector)
        magnitude = math.sqrt(
            x_value * x_value + y_value * y_value + z_value * z_value
        )
        if not math.isfinite(magnitude) or magnitude <= 0.0:
            raise TopologyAnalysisError(
                "A topological direction is missing or zero-length."
            )
        return Direction3D(
            x=x_value / magnitude,
            y=y_value / magnitude,
            z=z_value / magnitude,
        )

    @staticmethod
    def _coordinates(vector: object) -> tuple[float, float, float]:
        """Read lower- or upper-case Cartesian vector attributes."""
        try:
            lower = (
                getattr(vector, "x", None),
                getattr(vector, "y", None),
                getattr(vector, "z", None),
            )
            upper = (
                getattr(vector, "X", None),
                getattr(vector, "Y", None),
                getattr(vector, "Z", None),
            )
            values = tuple(
                float(low if low is not None else high)
                for low, high in zip(lower, upper)
            )
            return values[0], values[1], values[2]
        except (TypeError, ValueError) as error:
            raise TopologyAnalysisError(
                "Topology contains an unreadable Cartesian vector."
            ) from error

    @staticmethod
    def _midpoint(first: Point3D, second: Point3D) -> Point3D:
        """Return the immutable midpoint of two endpoints."""
        return Point3D(
            x_mm=(first.x_mm + second.x_mm) / 2.0,
            y_mm=(first.y_mm + second.y_mm) / 2.0,
            z_mm=(first.z_mm + second.z_mm) / 2.0,
        )

    @staticmethod
    def _distance(first: Point3D, second: Point3D) -> float:
        """Return Euclidean endpoint distance."""
        return math.sqrt(
            (second.x_mm - first.x_mm) ** 2
            + (second.y_mm - first.y_mm) ** 2
            + (second.z_mm - first.z_mm) ** 2
        )

    @staticmethod
    def _points_equal(first: Point3D, second: Point3D) -> bool:
        """Compare endpoint centers using numeric closeness."""
        return (
            math.isclose(first.x_mm, second.x_mm)
            and math.isclose(first.y_mm, second.y_mm)
            and math.isclose(first.z_mm, second.z_mm)
        )

    @staticmethod
    def _required_attribute(value: object, name: str) -> object:
        """Read a required topology attribute with a project exception."""
        try:
            return getattr(value, name)
        except AttributeError as error:
            raise TopologyAnalysisError(
                f"Topology attribute '{name}' is unavailable."
            ) from error

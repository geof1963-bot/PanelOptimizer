# -*- coding: utf-8 -*-
"""Connected coplanar region observations for source planar faces."""

from __future__ import annotations

import math

from ..Models import (
    BoundingBox,
    Direction3D,
    FlatRegionObservation,
    GeometrySnapshot,
    Point3D,
    TopologyAnalysis,
)
from ._Utilities import (
    DIRECTION_COMPARISON_TOLERANCE,
    LINEAR_COMPARISON_TOLERANCE_MM,
    PlanarFace,
    collect_planar_faces,
    same_shape,
    to_point,
)

__all__ = ["FlatRegionAnalyzer"]


class FlatRegionAnalyzer:
    """Group only connected, coplanar faces within one material solid."""

    def analyze(
        self,
        geometry: GeometrySnapshot,
        topology: TopologyAnalysis,
        shape: object,
    ) -> tuple[FlatRegionObservation, ...]:
        """Return deterministic connected components of planar source faces.

        Faces are unioned only when they have the same solid owner, lie on the
        same plane within centralized kernel tolerances, and share an exact
        source B-rep edge. Parallel offset faces, disconnected coplanar faces,
        and cavity/exterior faces without topological contact remain separate.
        """
        del topology
        faces = tuple(
            face
            for face in collect_planar_faces(geometry.source_id, shape)
            if self._canonical_normal(face.face) is not None
        )
        if not faces:
            return ()
        parents = list(range(len(faces)))

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

        for first_index, first in enumerate(faces):
            for second_index in range(first_index + 1, len(faces)):
                second = faces[second_index]
                if self._may_merge(first, second):
                    union(first_index, second_index)

        grouped: dict[int, list[PlanarFace]] = {}
        for index, face in enumerate(faces):
            grouped.setdefault(find(index), []).append(face)
        regions = tuple(
            tuple(grouped[root])
            for root in sorted(
                grouped,
                key=lambda item: grouped[item][0].source_index,
            )
        )
        return tuple(
            self._observation(
                geometry.source_id,
                observation_index,
                region,
                shape,
            )
            for observation_index, region in enumerate(regions, start=1)
        )

    @staticmethod
    def _may_merge(first: PlanarFace, second: PlanarFace) -> bool:
        """Require same owner, exact coplanarity, and a shared B-rep edge."""
        if first.owner_solid_index != second.owner_solid_index:
            return False
        first_normal = FlatRegionAnalyzer._canonical_normal(first.face)
        second_normal = FlatRegionAnalyzer._canonical_normal(second.face)
        if first_normal is None or second_normal is None:
            return False
        dot_product = (
            first_normal.x * second_normal.x
            + first_normal.y * second_normal.y
            + first_normal.z * second_normal.z
        )
        if not math.isclose(
            abs(dot_product),
            1.0,
            rel_tol=0.0,
            abs_tol=DIRECTION_COMPARISON_TOLERANCE,
        ):
            return False
        offset = (
            (second.plane_point.x_mm - first.plane_point.x_mm)
            * first_normal.x
            + (second.plane_point.y_mm - first.plane_point.y_mm)
            * first_normal.y
            + (second.plane_point.z_mm - first.plane_point.z_mm)
            * first_normal.z
        )
        if abs(offset) > LINEAR_COMPARISON_TOLERANCE_MM:
            return False
        return any(
            same_shape(first_edge, second_edge)
            for first_edge in getattr(first.face, "Edges", ())
            for second_edge in getattr(second.face, "Edges", ())
        )

    @staticmethod
    def _observation(
        source_id: str,
        index: int,
        region: tuple[PlanarFace, ...],
        shape: object,
    ) -> FlatRegionObservation:
        """Aggregate exact area, centroid, bounds, and boundary edge IDs."""
        areas = tuple(float(item.face.Area) for item in region)
        total_area = sum(areas)
        if total_area > 0.0:
            center = Point3D(
                sum(
                    float(item.face.CenterOfMass.x) * area
                    for item, area in zip(region, areas)
                )
                / total_area,
                sum(
                    float(item.face.CenterOfMass.y) * area
                    for item, area in zip(region, areas)
                )
                / total_area,
                sum(
                    float(item.face.CenterOfMass.z) * area
                    for item, area in zip(region, areas)
                )
                / total_area,
            )
        else:
            center = to_point(region[0].face.CenterOfMass)
        bounds = tuple(item.face.BoundBox for item in region)
        bounding_box = BoundingBox(
            minimum=Point3D(
                min(float(item.XMin) for item in bounds),
                min(float(item.YMin) for item in bounds),
                min(float(item.ZMin) for item in bounds),
            ),
            maximum=Point3D(
                max(float(item.XMax) for item in bounds),
                max(float(item.YMax) for item in bounds),
                max(float(item.ZMax) for item in bounds),
            ),
        )
        normal = FlatRegionAnalyzer._canonical_normal(region[0].face)
        if normal is None:  # Guarded when the region is collected.
            raise ValueError("Planar region normal is unavailable.")
        return FlatRegionObservation(
            observation_id=(
                f"{source_id}:geometry:flat-region:{index:04d}"
            ),
            center=center,
            normal=normal,
            bounding_box=bounding_box,
            area_mm2=total_area,
            source_face_ids=tuple(item.source_face_id for item in region),
            boundary_edge_ids=FlatRegionAnalyzer._boundary_edge_ids(
                source_id,
                region,
                shape,
            ),
            related_feature_ids=(),
        )

    @staticmethod
    def _boundary_edge_ids(
        source_id: str,
        region: tuple[PlanarFace, ...],
        shape: object,
    ) -> tuple[str, ...]:
        """Return source-ordered edges referenced by exactly one region face."""
        result: list[str] = []
        for edge_index, source_edge in enumerate(
            getattr(shape, "Edges", ()),
            start=1,
        ):
            incidence = sum(
                1
                for item in region
                if any(
                    same_shape(source_edge, face_edge)
                    for face_edge in getattr(item.face, "Edges", ())
                )
            )
            if incidence == 1:
                result.append(f"{source_id}:edge:{edge_index:04d}")
        return tuple(result)

    @staticmethod
    def _canonical_normal(face: object) -> Direction3D | None:
        """Return a normalized underlying-plane normal with stable sign."""
        try:
            u_min, u_max, v_min, v_max = (
                float(value) for value in face.ParameterRange
            )
            vector = face.Surface.normal(
                (u_min + u_max) / 2.0,
                (v_min + v_max) / 2.0,
            )
            components = float(vector.x), float(vector.y), float(vector.z)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return None
        magnitude = math.sqrt(sum(value**2 for value in components))
        if magnitude <= DIRECTION_COMPARISON_TOLERANCE:
            return None
        normalized = tuple(value / magnitude for value in components)
        for value in normalized:
            if abs(value) <= DIRECTION_COMPARISON_TOLERANCE:
                continue
            if value < 0.0:
                normalized = tuple(-component for component in normalized)
            break
        return Direction3D(*normalized)

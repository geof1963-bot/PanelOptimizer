# -*- coding: utf-8 -*-
"""Conservative clearance analysis driven by topology hole features."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..Models import (
    ClearanceObservation,
    GeometrySnapshot,
    HoleFeature,
    Point3D,
    TopologyAnalysis,
)
from ._Utilities import (
    LINEAR_COMPARISON_TOLERANCE_MM,
    PlanarFace,
    collect_planar_faces,
    direction_is_axis_aligned_horizontal,
    direction_is_vertical,
    distance,
    material_segment_is_complete,
    to_point,
    vector_like,
)

__all__ = ["ClearanceAnalyzer"]


@dataclass(frozen=True, slots=True)
class _ClearanceMeasurement:
    """Internal immutable values awaiting deterministic observation IDs."""

    first_point: Point3D
    second_point: Point3D
    clearance_mm: float
    source_element_ids: tuple[str, ...]
    related_feature_ids: tuple[str, ...]


class ClearanceAnalyzer:
    """Measure supported direct separations without evaluating adequacy."""

    def analyze(
        self,
        geometry: GeometrySnapshot,
        topology: TopologyAnalysis,
        shape: object,
    ) -> tuple[ClearanceObservation, ...]:
        """Measure topology-driven cylindrical-hole clearances.

        Supported observations are:

        - boundary-to-boundary spacing between two model-Z cylindrical holes
          whose axial ranges overlap; and
        - spacing from a model-Z cylindrical hole to an axis-aligned vertical
          planar source boundary.

        Hole geometry and IDs come from ``TopologyAnalysis``.  The resolved
        shape is used only to verify that the direct boundary segment is
        uninterrupted material and that a projected endpoint lies on the
        source face.  Center distance is never substituted for circular
        boundary spacing.  Each unordered hole pair is visited once.

        Cavities, non-cylindrical openings, non-vertical holes, curved exterior
        boundaries, and pairs without a provable direct segment are omitted.
        """
        solids = tuple(getattr(shape, "Solids", ()))
        if not solids:
            return ()

        holes = tuple(
            sorted(
                (
                    hole
                    for hole in topology.holes
                    if direction_is_vertical(hole.axis)
                ),
                key=lambda hole: hole.feature_id,
            )
        )
        planar_faces = tuple(
            face
            for face in collect_planar_faces(geometry.source_id, shape)
            if (
                face.is_outer_boundary
                and direction_is_axis_aligned_horizontal(face.normal)
            )
        )
        feature_owner_indices = self._feature_owner_indices(topology)
        measurements: list[_ClearanceMeasurement] = []

        for first_index, first_hole in enumerate(holes):
            for second_hole in holes[first_index + 1:]:
                measurement = self._between_holes(
                    first_hole,
                    second_hole,
                    shape,
                    solids,
                    feature_owner_indices,
                )
                if measurement is not None:
                    measurements.append(measurement)

        for hole in holes:
            for planar_face in planar_faces:
                measurement = self._between_hole_and_plane(
                    hole,
                    planar_face,
                    shape,
                    solids,
                    feature_owner_indices,
                )
                if measurement is not None:
                    measurements.append(measurement)

        return tuple(
            ClearanceObservation(
                observation_id=(
                    f"{geometry.source_id}:geometry:clearance:"
                    f"{index:04d}"
                ),
                first_boundary_point=measurement.first_point,
                second_boundary_point=measurement.second_point,
                clearance_mm=measurement.clearance_mm,
                source_element_ids=measurement.source_element_ids,
                related_feature_ids=measurement.related_feature_ids,
            )
            for index, measurement in enumerate(measurements, start=1)
        )

    def _between_holes(
        self,
        first: HoleFeature,
        second: HoleFeature,
        shape: object,
        solids: tuple[object, ...],
        feature_owner_indices: dict[str, int],
    ) -> _ClearanceMeasurement | None:
        """Return exact spacing for a valid same-region circular-hole pair."""
        first_owner = feature_owner_indices.get(first.feature_id)
        second_owner = feature_owner_indices.get(second.feature_id)
        if (
            first_owner is None
            or second_owner is None
            or first_owner != second_owner
        ):
            return None

        first_interval = self._axial_interval(first)
        second_interval = self._axial_interval(second)
        overlap_minimum = max(first_interval[0], second_interval[0])
        overlap_maximum = min(first_interval[1], second_interval[1])
        if (
            overlap_maximum - overlap_minimum
            <= LINEAR_COMPARISON_TOLERANCE_MM
        ):
            return None

        x_delta = second.center.x_mm - first.center.x_mm
        y_delta = second.center.y_mm - first.center.y_mm
        center_distance = math.hypot(x_delta, y_delta)
        if center_distance <= LINEAR_COMPARISON_TOLERANCE_MM:
            return None

        first_radius = first.diameter_mm / 2.0
        second_radius = second.diameter_mm / 2.0
        clearance = center_distance - first_radius - second_radius
        if clearance <= LINEAR_COMPARISON_TOLERANCE_MM:
            return None

        x_direction = x_delta / center_distance
        y_direction = y_delta / center_distance
        z_coordinate = (overlap_minimum + overlap_maximum) / 2.0
        first_point = Point3D(
            first.center.x_mm + x_direction * first_radius,
            first.center.y_mm + y_direction * first_radius,
            z_coordinate,
        )
        second_point = Point3D(
            second.center.x_mm - x_direction * second_radius,
            second.center.y_mm - y_direction * second_radius,
            z_coordinate,
        )
        first_vector = vector_like(shape.CenterOfGravity, first_point)
        second_vector = vector_like(shape.CenterOfGravity, second_point)
        if not material_segment_is_complete(
            solids,
            first_vector,
            second_vector,
            clearance,
            owner_solid_index=first_owner,
        ):
            return None

        return _ClearanceMeasurement(
            first_point=first_point,
            second_point=second_point,
            clearance_mm=clearance,
            source_element_ids=(),
            related_feature_ids=(
                first.feature_id,
                second.feature_id,
            ),
        )

    def _between_hole_and_plane(
        self,
        hole: HoleFeature,
        planar_face: PlanarFace,
        shape: object,
        solids: tuple[object, ...],
        feature_owner_indices: dict[str, int],
    ) -> _ClearanceMeasurement | None:
        """Return direct spacing from one hole to its own outer-shell plane."""
        hole_owner = feature_owner_indices.get(hole.feature_id)
        if (
            hole_owner is None
            or hole_owner != planar_face.owner_solid_index
        ):
            return None

        center = hole.center
        normal = planar_face.normal
        center_to_plane = (
            (planar_face.plane_point.x_mm - center.x_mm) * normal.x
            + (planar_face.plane_point.y_mm - center.y_mm) * normal.y
            + (planar_face.plane_point.z_mm - center.z_mm) * normal.z
        )
        plane_distance = abs(center_to_plane)
        radius = hole.diameter_mm / 2.0
        clearance = plane_distance - radius
        if clearance <= LINEAR_COMPARISON_TOLERANCE_MM:
            return None

        sign = 1.0 if center_to_plane >= 0.0 else -1.0
        x_direction = normal.x * sign
        y_direction = normal.y * sign
        z_direction = normal.z * sign
        first_point = Point3D(
            center.x_mm + x_direction * radius,
            center.y_mm + y_direction * radius,
            center.z_mm + z_direction * radius,
        )
        second_point = Point3D(
            center.x_mm + normal.x * center_to_plane,
            center.y_mm + normal.y * center_to_plane,
            center.z_mm + normal.z * center_to_plane,
        )
        first_vector = vector_like(shape.CenterOfGravity, first_point)
        second_vector = vector_like(shape.CenterOfGravity, second_point)
        if not planar_face.face.isInside(
            second_vector,
            LINEAR_COMPARISON_TOLERANCE_MM,
            True,
        ):
            return None
        if not math.isclose(
            distance(first_point, second_point),
            clearance,
            rel_tol=0.0,
            abs_tol=LINEAR_COMPARISON_TOLERANCE_MM,
        ):
            return None
        if not material_segment_is_complete(
            solids,
            first_vector,
            second_vector,
            clearance,
            owner_solid_index=planar_face.owner_solid_index,
        ):
            return None

        return _ClearanceMeasurement(
            first_point=first_point,
            second_point=to_point(second_vector),
            clearance_mm=clearance,
            source_element_ids=(planar_face.source_face_id,),
            related_feature_ids=(hole.feature_id,),
        )

    @staticmethod
    def _axial_interval(hole: HoleFeature) -> tuple[float, float]:
        """Return model-Z extent for an already vertical cylindrical hole."""
        half_depth = hole.depth_mm / 2.0
        return (
            hole.center.z_mm - half_depth,
            hole.center.z_mm + half_depth,
        )

    @staticmethod
    def _feature_owner_indices(
        topology: TopologyAnalysis,
    ) -> dict[str, int]:
        """Map topology feature IDs to deterministic material-region indices."""
        graph = topology.connectivity_graph
        if graph is None:
            return {}
        owners: dict[str, int] = {}
        for owner_index, node in enumerate(graph.nodes):
            for feature_id in node.related_feature_ids:
                owners[feature_id] = owner_index
        return owners

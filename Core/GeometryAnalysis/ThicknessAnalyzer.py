# -*- coding: utf-8 -*-
"""Conservative local thickness analysis for planar panel regions."""

from __future__ import annotations

import math

from ..Models import (
    Direction3D,
    GeometrySnapshot,
    Point3D,
    ThicknessObservation,
    TopologyAnalysis,
)
from ._Utilities import (
    DIRECTION_COMPARISON_TOLERANCE,
    LINEAR_COMPARISON_TOLERANCE_MM,
    PlanarFace,
    collect_planar_faces,
    direction_is_vertical,
    distance,
    face_sample_points,
    material_segment_is_complete,
    to_point,
    vector_like,
)

__all__ = ["ThicknessAnalyzer"]


class ThicknessAnalyzer:
    """Measure exact local thickness between supported planar boundaries."""

    def analyze(
        self,
        geometry: GeometrySnapshot,
        topology: TopologyAnalysis,
        shape: object,
    ) -> tuple[ThicknessObservation, ...]:
        """Return source-ordered local model-Z thickness observations.

        The implemented method pairs opposing planar faces belonging to the
        same solid when both face normals are parallel to model Z.  It projects
        a deterministic point per face pair along Z and accepts the measurement
        only when the complete exact segment lies in material.  The reported
        distance is the perpendicular plane separation, never the snapshot's
        global Z extent.

        Perforations do not become thickness because a segment interrupted by
        a void is rejected.  Non-planar boundaries, non-Z thickness directions,
        and face pairs without a reliable shared material segment are omitted.
        ``topology`` is accepted as the preceding pipeline contract; this
        detector does not alter or rediscover its feature classifications.
        """
        del topology
        solids = tuple(getattr(shape, "Solids", ()))
        if not solids:
            return ()

        planar_faces = collect_planar_faces(geometry.source_id, shape)
        measurements: list[
            tuple[PlanarFace, PlanarFace, object, object, float]
        ] = []

        for first_index, first in enumerate(planar_faces):
            for second in planar_faces[first_index + 1:]:
                if first.owner_solid_index != second.owner_solid_index:
                    continue
                if not (
                    direction_is_vertical(first.normal)
                    and direction_is_vertical(second.normal)
                    and self._directions_opposed(first, second)
                ):
                    continue

                lower, upper = self._ordered_by_height(first, second)
                separation = (
                    upper.plane_point.z_mm - lower.plane_point.z_mm
                )
                if separation <= LINEAR_COMPARISON_TOLERANCE_MM:
                    continue

                material_points = self._material_points(
                    lower,
                    upper,
                    solids,
                    separation,
                )
                if material_points is None:
                    continue
                lower_vector, upper_vector = material_points
                measurements.append(
                    (
                        lower,
                        upper,
                        lower_vector,
                        upper_vector,
                        separation,
                    )
                )

        return tuple(
            ThicknessObservation(
                observation_id=(
                    f"{geometry.source_id}:geometry:thickness:"
                    f"{index:04d}"
                ),
                first_boundary_point=to_point(lower_vector),
                second_boundary_point=to_point(upper_vector),
                direction=Direction3D(0.0, 0.0, 1.0),
                thickness_mm=separation,
                source_element_ids=(
                    lower.source_face_id,
                    upper.source_face_id,
                ),
                related_feature_ids=(),
            )
            for index, (
                lower,
                upper,
                lower_vector,
                upper_vector,
                separation,
            ) in enumerate(measurements, start=1)
        )

    @staticmethod
    def _directions_opposed(first: PlanarFace, second: PlanarFace) -> bool:
        """Return whether two normalized face normals point oppositely."""
        dot_product = (
            first.normal.x * second.normal.x
            + first.normal.y * second.normal.y
            + first.normal.z * second.normal.z
        )
        return math.isclose(
            dot_product,
            -1.0,
            rel_tol=0.0,
            abs_tol=DIRECTION_COMPARISON_TOLERANCE,
        )

    @staticmethod
    def _ordered_by_height(
        first: PlanarFace,
        second: PlanarFace,
    ) -> tuple[PlanarFace, PlanarFace]:
        """Return lower then upper face without changing source pair ordering."""
        if first.plane_point.z_mm <= second.plane_point.z_mm:
            return first, second
        return second, first

    def _material_points(
        self,
        lower: PlanarFace,
        upper: PlanarFace,
        solids: tuple[object, ...],
        separation: float,
    ) -> tuple[object, object] | None:
        """Find one exact vertical material segment shared by two faces."""
        for upper_sample in face_sample_points(upper.face):
            lower_point = to_point(upper_sample)
            lower_point = Point3D(
                lower_point.x_mm,
                lower_point.y_mm,
                lower.plane_point.z_mm,
            )
            lower_vector = vector_like(upper_sample, lower_point)
            if self._valid_material_segment(
                lower,
                upper,
                lower_vector,
                upper_sample,
                solids,
                separation,
            ):
                return lower_vector, upper_sample

        for lower_sample in face_sample_points(lower.face):
            upper_point = to_point(lower_sample)
            upper_point = Point3D(
                upper_point.x_mm,
                upper_point.y_mm,
                upper.plane_point.z_mm,
            )
            upper_vector = vector_like(lower_sample, upper_point)
            if self._valid_material_segment(
                lower,
                upper,
                lower_sample,
                upper_vector,
                solids,
                separation,
            ):
                return lower_sample, upper_vector
        return None

    @staticmethod
    def _valid_material_segment(
        lower: PlanarFace,
        upper: PlanarFace,
        lower_vector: object,
        upper_vector: object,
        solids: tuple[object, ...],
        separation: float,
    ) -> bool:
        """Require both face membership and an uninterrupted material segment."""
        if not lower.face.isInside(
            lower_vector,
            LINEAR_COMPARISON_TOLERANCE_MM,
            True,
        ):
            return False
        if not upper.face.isInside(
            upper_vector,
            LINEAR_COMPARISON_TOLERANCE_MM,
            True,
        ):
            return False
        actual_distance = distance(
            to_point(lower_vector),
            to_point(upper_vector),
        )
        if not math.isclose(
            actual_distance,
            separation,
            rel_tol=0.0,
            abs_tol=LINEAR_COMPARISON_TOLERANCE_MM,
        ):
            return False
        return material_segment_is_complete(
            solids,
            lower_vector,
            upper_vector,
            separation,
            owner_solid_index=lower.owner_solid_index,
        )

# -*- coding: utf-8 -*-
"""Exact local curvature observations for supported analytic surfaces."""

from __future__ import annotations

import math

from ..Models import (
    CurvatureObservation,
    Direction3D,
    GeometrySnapshot,
    TopologyAnalysis,
)
from ._Utilities import (
    DIRECTION_COMPARISON_TOLERANCE,
    LINEAR_COMPARISON_TOLERANCE_MM,
    PLANAR_SAMPLE_FRACTIONS,
    to_point,
)

__all__ = ["CurvatureAnalyzer"]


class CurvatureAnalyzer:
    """Describe exact analytic principal curvature at one point per face."""

    def analyze(
        self,
        geometry: GeometrySnapshot,
        topology: TopologyAnalysis,
        shape: object,
    ) -> tuple[CurvatureObservation, ...]:
        """Return source-ordered plane, cylinder, and sphere observations.

        One deterministic valid parameter is selected for each supported face.
        OpenCASCADE supplies the exact analytic principal curvatures, while the
        underlying analytic surface supplies orientation-independent normal
        and tangent directions. Unsupported surfaces or faces without a valid
        deterministic point are omitted; no dense or approximate sampling is
        performed.
        """
        del topology
        observations: list[CurvatureObservation] = []
        for source_index, face in enumerate(
            getattr(shape, "Faces", ()),
            start=1,
        ):
            if self._surface_family(face) is None:
                continue
            parameters = self._sample_parameters(face)
            if parameters is None:
                continue
            values = self._surface_values(face, *parameters)
            if values is None:
                continue
            (
                location,
                normal,
                first_direction,
                second_direction,
                first_curvature,
                second_curvature,
            ) = values
            observation_index = len(observations) + 1
            observations.append(
                CurvatureObservation(
                    observation_id=(
                        f"{geometry.source_id}:geometry:curvature:"
                        f"{observation_index:04d}"
                    ),
                    source_face_id=(
                        f"{geometry.source_id}:face:{source_index:04d}"
                    ),
                    location=location,
                    normal=normal,
                    first_principal_direction=first_direction,
                    second_principal_direction=second_direction,
                    first_principal_curvature_per_mm=first_curvature,
                    second_principal_curvature_per_mm=second_curvature,
                    related_feature_ids=(),
                )
            )
        return tuple(observations)

    @staticmethod
    def _surface_family(face: object) -> str | None:
        """Return the supported exact analytic surface family."""
        name = type(getattr(face, "Surface", None)).__name__.lower()
        for family in ("plane", "cylinder", "sphere"):
            if family in name:
                return family
        return None

    @staticmethod
    def _sample_parameters(face: object) -> tuple[float, float] | None:
        """Return the first deterministic parameter lying on the trimmed face."""
        try:
            u_min, u_max, v_min, v_max = (
                float(value) for value in face.ParameterRange
            )
        except (AttributeError, TypeError, ValueError):
            return None

        candidates: list[tuple[float, float]] = []
        try:
            candidates.append(
                tuple(
                    float(value)
                    for value in face.Surface.parameter(face.CenterOfMass)
                )
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass
        for u_fraction in PLANAR_SAMPLE_FRACTIONS:
            for v_fraction in PLANAR_SAMPLE_FRACTIONS:
                candidates.append(
                    (
                        u_min + (u_max - u_min) * u_fraction,
                        v_min + (v_max - v_min) * v_fraction,
                    )
                )

        for u_value, v_value in candidates:
            try:
                point = face.valueAt(u_value, v_value)
                if face.isInside(
                    point,
                    LINEAR_COMPARISON_TOLERANCE_MM,
                    True,
                ):
                    return u_value, v_value
            except (AttributeError, RuntimeError, TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _surface_values(
        face: object,
        u_value: float,
        v_value: float,
    ) -> tuple[
        object,
        Direction3D,
        Direction3D,
        Direction3D,
        float,
        float,
    ] | None:
        """Read exact analytic values and convert all vectors to models."""
        try:
            surface = face.Surface
            location = to_point(surface.value(u_value, v_value))
            normal_result = CurvatureAnalyzer._canonical_direction_with_sign(
                surface.normal(u_value, v_value)
            )
            tangents = surface.tangent(u_value, v_value)
            first_direction = CurvatureAnalyzer._canonical_direction(
                tangents[0]
            )
            second_direction = CurvatureAnalyzer._canonical_direction(
                tangents[1]
            )
            curvatures = tuple(
                float(value) for value in face.curvatureAt(u_value, v_value)
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return None
        if (
            normal_result is None
            or first_direction is None
            or second_direction is None
            or len(curvatures) != 2
            or not all(math.isfinite(value) for value in curvatures)
        ):
            return None
        normal, normal_sign = normal_result
        return (
            location,
            normal,
            first_direction,
            second_direction,
            curvatures[0] * normal_sign,
            curvatures[1] * normal_sign,
        )

    @staticmethod
    def _canonical_direction(vector: object) -> Direction3D | None:
        """Normalize a direction and choose an orientation-stable sign."""
        result = CurvatureAnalyzer._canonical_direction_with_sign(vector)
        return None if result is None else result[0]

    @staticmethod
    def _canonical_direction_with_sign(
        vector: object,
    ) -> tuple[Direction3D, float] | None:
        """Return a canonical direction and its sign relative to the input.

        Principal curvature is signed relative to the surface normal.  The
        returned sign lets callers reverse both together when canonicalizing
        the normal, preserving that exact geometric relationship.
        """
        try:
            components = float(vector.x), float(vector.y), float(vector.z)
        except (AttributeError, TypeError, ValueError):
            return None
        magnitude = math.sqrt(sum(value**2 for value in components))
        if magnitude <= DIRECTION_COMPARISON_TOLERANCE:
            return None
        normalized = tuple(value / magnitude for value in components)
        sign = 1.0
        for value in normalized:
            if abs(value) <= DIRECTION_COMPARISON_TOLERANCE:
                continue
            if value < 0.0:
                normalized = tuple(-component for component in normalized)
                sign = -1.0
            break
        return Direction3D(*normalized), sign

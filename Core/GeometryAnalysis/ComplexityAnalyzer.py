# -*- coding: utf-8 -*-
"""Descriptive source-wide geometric-complexity counts."""

from __future__ import annotations

import math

from ..Models import (
    EdgeObservation,
    GeometricComplexityObservation,
    GeometrySnapshot,
    TopologyAnalysis,
)
from ._Utilities import DIRECTION_COMPARISON_TOLERANCE, same_shape

__all__ = ["ComplexityAnalyzer"]


class ComplexityAnalyzer:
    """Count focused structural facts without weighting or evaluation."""

    _ANALYTIC_SURFACE_FAMILIES = (
        "plane",
        "cylinder",
        "cone",
        "sphere",
        "torus",
    )
    _ANALYTIC_CURVE_FAMILIES = {
        "line",
        "circle",
        "ellipse",
        "hyperbola",
        "parabola",
    }

    def analyze(
        self,
        geometry: GeometrySnapshot,
        topology: TopologyAnalysis,
        shape: object,
        edge_observations: tuple[EdgeObservation, ...],
    ) -> tuple[GeometricComplexityObservation, ...]:
        """Return one deterministic source-wide group of exact counts.

        Non-analytic curve counts reuse readable, deduplicated
        ``EdgeObservation`` evidence.  Surface categories, adjacent-face
        boundaries, and vertex-to-face incidence require the transient source
        B-rep.  ``curvature_discontinuity_count`` is deliberately conservative:
        it counts only two-face boundaries whose exact surface normals prove a
        tangent discontinuity.  Tangent boundaries with a possible higher-
        order curvature jump are omitted rather than approximated.

        No raw GeometrySnapshot total, topology-feature count, weighting,
        normalization, or qualitative label is produced.
        """
        del topology
        return (
            GeometricComplexityObservation(
                observation_id=(
                    f"{geometry.source_id}:geometry:complexity:0001"
                ),
                non_analytic_surface_count=self._non_analytic_surface_count(
                    shape
                ),
                non_analytic_curve_count=sum(
                    item.curve_type not in self._ANALYTIC_CURVE_FAMILIES
                    for item in edge_observations
                ),
                curvature_discontinuity_count=(
                    self._curvature_discontinuity_count(shape)
                ),
                mixed_surface_junction_count=(
                    self._mixed_surface_junction_count(shape)
                ),
            ),
        )

    @classmethod
    def _non_analytic_surface_count(cls, shape: object) -> int:
        """Count faces outside the approved exact analytic families."""
        return sum(
            not any(
                family in cls._surface_name(face)
                for family in cls._ANALYTIC_SURFACE_FAMILIES
            )
            for face in getattr(shape, "Faces", ())
        )

    @classmethod
    def _mixed_surface_junction_count(cls, shape: object) -> int:
        """Count vertices incident to more than one surface family."""
        faces = tuple(getattr(shape, "Faces", ()))
        return sum(
            len(
                {
                    cls._surface_family(face)
                    for face in faces
                    if any(
                        same_shape(vertex, face_vertex)
                        for face_vertex in getattr(face, "Vertexes", ())
                    )
                }
            )
            > 1
            for vertex in getattr(shape, "Vertexes", ())
        )

    @classmethod
    def _curvature_discontinuity_count(cls, shape: object) -> int:
        """Count boundaries with a proven discontinuity of surface tangent."""
        faces = tuple(getattr(shape, "Faces", ()))
        seen_edges: list[object] = []
        count = 0
        for edge in getattr(shape, "Edges", ()):
            if any(same_shape(edge, known) for known in seen_edges):
                continue
            seen_edges.append(edge)
            incident = tuple(
                face
                for face in faces
                if any(
                    same_shape(edge, face_edge)
                    for face_edge in getattr(face, "Edges", ())
                )
            )
            if len(incident) != 2:
                continue
            normals = cls._boundary_normals(edge, incident)
            if normals is None:
                continue
            dot_product = abs(
                normals[0][0] * normals[1][0]
                + normals[0][1] * normals[1][1]
                + normals[0][2] * normals[1][2]
            )
            if not math.isclose(
                dot_product,
                1.0,
                rel_tol=0.0,
                abs_tol=DIRECTION_COMPARISON_TOLERANCE,
            ):
                count += 1
        return count

    @staticmethod
    def _boundary_normals(
        edge: object,
        faces: tuple[object, object],
    ) -> tuple[
        tuple[float, float, float],
        tuple[float, float, float],
    ] | None:
        """Return exact underlying-surface normals at the edge midpoint."""
        try:
            parameter = (
                float(edge.FirstParameter) + float(edge.LastParameter)
            ) / 2.0
            point = edge.valueAt(parameter)
            result: list[tuple[float, float, float]] = []
            for face in faces:
                u_value, v_value = face.Surface.parameter(point)
                vector = face.Surface.normal(u_value, v_value)
                components = (
                    float(vector.x),
                    float(vector.y),
                    float(vector.z),
                )
                magnitude = math.sqrt(
                    sum(value**2 for value in components)
                )
                if magnitude <= DIRECTION_COMPARISON_TOLERANCE:
                    return None
                result.append(
                    tuple(value / magnitude for value in components)
                )
            return result[0], result[1]
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return None

    @classmethod
    def _surface_family(cls, face: object) -> str:
        """Return one stable exact surface family or ``non_analytic``."""
        name = cls._surface_name(face)
        for family in cls._ANALYTIC_SURFACE_FAMILIES:
            if family in name:
                return family
        return "non_analytic"

    @staticmethod
    def _surface_name(face: object) -> str:
        """Return the normalized runtime name of one exact B-rep surface."""
        try:
            return type(face.Surface).__name__.lower()
        except (AttributeError, RuntimeError, TypeError):
            return ""

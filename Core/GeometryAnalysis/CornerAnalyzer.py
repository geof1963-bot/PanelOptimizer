# -*- coding: utf-8 -*-
"""Deterministic angular observations between incident linear edges."""

from __future__ import annotations

import math

from ..Models import CornerObservation, GeometrySnapshot, TopologyAnalysis
from ._Utilities import DIRECTION_COMPARISON_TOLERANCE, same_shape, to_point

__all__ = ["CornerAnalyzer"]


class CornerAnalyzer:
    """Describe unambiguous pairwise linear-edge angles at source vertices."""

    def analyze(
        self,
        geometry: GeometrySnapshot,
        topology: TopologyAnalysis,
        shape: object,
    ) -> tuple[CornerObservation, ...]:
        """Return canonical angles for every incident pair of linear edges.

        Vertices and edges retain source B-rep order. At vertices incident to
        more than two linear edges, each unordered pair is independently
        unambiguous and emitted once. Nonlinear, closed, degenerate, or
        unreadable edges are omitted rather than assigned an approximate
        tangent angle.
        """
        del topology
        edges: list[tuple[int, object]] = []
        for edge_index, edge in enumerate(
            getattr(shape, "Edges", ()),
            start=1,
        ):
            if any(same_shape(edge, known) for _, known in edges):
                continue
            edges.append((edge_index, edge))
        observations: list[CornerObservation] = []
        for vertex_index, vertex in enumerate(
            getattr(shape, "Vertexes", ()),
            start=1,
        ):
            incident = tuple(
                (edge_index, edge)
                for edge_index, edge in edges
                if self._is_linear(edge)
                and self._contains_vertex(edge, vertex)
            )
            for first_index, first in enumerate(incident):
                for second in incident[first_index + 1:]:
                    angle = self._included_angle(vertex, first[1], second[1])
                    if angle is None:
                        continue
                    observation_index = len(observations) + 1
                    edge_ids = tuple(
                        sorted(
                            (
                                f"{geometry.source_id}:edge:{first[0]:04d}",
                                f"{geometry.source_id}:edge:{second[0]:04d}",
                            )
                        )
                    )
                    observations.append(
                        CornerObservation(
                            observation_id=(
                                f"{geometry.source_id}:geometry:corner:"
                                f"{observation_index:04d}"
                            ),
                            source_vertex_id=(
                                f"{geometry.source_id}:vertex:"
                                f"{vertex_index:04d}"
                            ),
                            position=to_point(vertex.Point),
                            angle_degrees=angle,
                            incident_edge_ids=edge_ids,
                            related_feature_ids=(),
                        )
                    )
        return tuple(observations)

    @staticmethod
    def _is_linear(edge: object) -> bool:
        """Return whether the exact B-rep curve is a straight line."""
        try:
            return type(edge.Curve).__name__.lower() in {
                "line",
                "linesegment",
            }
        except (AttributeError, RuntimeError, TypeError):
            return False

    @staticmethod
    def _contains_vertex(edge: object, vertex: object) -> bool:
        """Return whether an edge references the source vertex."""
        return any(
            same_shape(candidate, vertex)
            for candidate in getattr(edge, "Vertexes", ())
        )

    @staticmethod
    def _included_angle(
        vertex: object,
        first_edge: object,
        second_edge: object,
    ) -> float | None:
        """Return the exact included angle between two outward edge vectors."""
        first = CornerAnalyzer._outward_direction(vertex, first_edge)
        second = CornerAnalyzer._outward_direction(vertex, second_edge)
        if first is None or second is None:
            return None
        dot_product = max(
            -1.0,
            min(
                1.0,
                first[0] * second[0]
                + first[1] * second[1]
                + first[2] * second[2],
            ),
        )
        return math.degrees(math.acos(dot_product))

    @staticmethod
    def _outward_direction(
        vertex: object,
        edge: object,
    ) -> tuple[float, float, float] | None:
        """Return a normalized linear-edge direction away from one vertex."""
        try:
            origin = vertex.Point
            other = next(
                candidate.Point
                for candidate in edge.Vertexes
                if not same_shape(candidate, vertex)
            )
            components = (
                float(other.x - origin.x),
                float(other.y - origin.y),
                float(other.z - origin.z),
            )
        except (AttributeError, RuntimeError, StopIteration, TypeError):
            return None
        magnitude = math.sqrt(sum(value**2 for value in components))
        if magnitude <= DIRECTION_COMPARISON_TOLERANCE:
            return None
        return tuple(value / magnitude for value in components)

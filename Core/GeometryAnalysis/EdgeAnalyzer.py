# -*- coding: utf-8 -*-
"""Deterministic descriptive observations of source B-rep edges."""

from __future__ import annotations

import math

from ..Models import EdgeObservation, GeometrySnapshot, TopologyAnalysis
from ._Utilities import (
    LINEAR_COMPARISON_TOLERANCE_MM,
    points_close,
    same_shape,
    to_point,
)

__all__ = ["EdgeAnalyzer"]


class EdgeAnalyzer:
    """Describe unique source edges without evaluating their importance."""

    def analyze(
        self,
        geometry: GeometrySnapshot,
        topology: TopologyAnalysis,
        shape: object,
    ) -> tuple[EdgeObservation, ...]:
        """Return one source-ordered observation per unique readable edge.

        Curve families are read from the exact B-rep curve type. Open-edge
        endpoints are canonicalized lexicographically so whole-shape reversal
        cannot change them. Closed edges use their deterministic parameter-seam
        point for both endpoints. Unsupported curves remain descriptive
        ``generic`` edges rather than being evaluated or approximated.
        """
        del topology
        observations: list[EdgeObservation] = []
        seen: list[object] = []
        for source_index, edge in enumerate(
            getattr(shape, "Edges", ()),
            start=1,
        ):
            if any(same_shape(edge, known) for known in seen):
                continue
            seen.append(edge)
            endpoints = self._endpoints(edge)
            if endpoints is None:
                continue
            start_point, end_point, is_closed = endpoints
            try:
                length = float(edge.Length)
            except (AttributeError, TypeError, ValueError):
                continue
            # OpenCASCADE may expose collapsed pole edges with a tiny but
            # non-zero computed length.  They do not define a readable
            # one-dimensional geometric edge, so omit them conservatively.
            if (
                not math.isfinite(length)
                or length <= LINEAR_COMPARISON_TOLERANCE_MM
            ):
                continue
            observation_index = len(observations) + 1
            observations.append(
                EdgeObservation(
                    observation_id=(
                        f"{geometry.source_id}:geometry:edge:"
                        f"{observation_index:04d}"
                    ),
                    source_edge_id=(
                        f"{geometry.source_id}:edge:{source_index:04d}"
                    ),
                    start_point=start_point,
                    end_point=end_point,
                    length_mm=length,
                    curve_type=self._curve_family(edge),
                    is_closed=is_closed,
                    related_feature_ids=(),
                )
            )
        return tuple(observations)

    @staticmethod
    def _endpoints(
        edge: object,
    ) -> tuple[object, object, bool] | None:
        """Return canonical immutable endpoints and exact closure state."""
        try:
            closed_method = getattr(edge, "isClosed", None)
            is_closed = (
                bool(closed_method())
                if callable(closed_method)
                else False
            )
            vertices = tuple(getattr(edge, "Vertexes", ()))
            if is_closed:
                seam = to_point(edge.valueAt(edge.FirstParameter))
                return seam, seam, True
            if len(vertices) < 2:
                return None
            endpoints = sorted(
                (to_point(vertices[0].Point), to_point(vertices[-1].Point)),
                key=lambda point: (point.x_mm, point.y_mm, point.z_mm),
            )
            inferred_closed = points_close(endpoints[0], endpoints[1])
            return endpoints[0], endpoints[1], inferred_closed
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return None

    @staticmethod
    def _curve_family(edge: object) -> str:
        """Return a stable neutral family name for an exact B-rep curve."""
        try:
            curve_name = type(edge.Curve).__name__.lower()
        except (AttributeError, RuntimeError, TypeError):
            return "generic"
        if "bspline" in curve_name:
            return "spline"
        if "bezier" in curve_name:
            return "bezier"
        if "circle" in curve_name:
            return "circle"
        if "ellipse" in curve_name:
            return "ellipse"
        if "parabola" in curve_name:
            return "parabola"
        if "hyperbola" in curve_name:
            return "hyperbola"
        if curve_name in {"line", "linesegment"}:
            return "line"
        return "generic"

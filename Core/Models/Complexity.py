# -*- coding: utf-8 -*-
"""Immutable global geometric-complexity indicators."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GeometricComplexityObservation:
    """Global descriptive counts not present in ``GeometrySnapshot``.

    Attributes:
        observation_id: Deterministic ID
            ``{source_id}:geometry:complexity:0001`` for the source-wide
            observation.
        non_analytic_surface_count: Number of faces not represented by an
            analytic plane, cylinder, cone, sphere, or torus.
        non_analytic_curve_count: Number of edges not represented by an
            analytic line, circle, ellipse, hyperbola, or parabola.
        curvature_discontinuity_count: Number of adjacent surface boundaries
            whose curvature continuity is discontinuous.
        mixed_surface_junction_count: Number of vertices joining more than one
            descriptive surface family.

    All fields are dimensionless counts.  This is the only global observation
    in GeometricAnalysis.  It does not repeat GeometrySnapshot face, edge, or
    vertex totals and does not combine the counts into a score.
    """

    observation_id: str
    non_analytic_surface_count: int
    non_analytic_curve_count: int
    curvature_discontinuity_count: int
    mixed_surface_junction_count: int

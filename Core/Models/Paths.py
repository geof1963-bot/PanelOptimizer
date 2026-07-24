# -*- coding: utf-8 -*-
"""Path-planning data contracts for future PanelOptimizer engines."""

from __future__ import annotations

from dataclasses import dataclass

from .Common import Point3D


@dataclass(frozen=True, slots=True)
class PathMetrics:
    """Scores and measurements assigned to one candidate seam path."""

    length_mm: float
    visibility_cost: float
    structural_cost: float
    manufacturing_cost: float
    total_cost: float


@dataclass(frozen=True, slots=True)
class CandidatePath:
    """One ranked, geometry-neutral candidate seam path."""

    candidate_id: str
    geometry_id: str
    rank: int
    points: tuple[Point3D, ...]
    followed_feature_ids: tuple[str, ...]
    metrics: PathMetrics
    notes: tuple[str, ...] = ()

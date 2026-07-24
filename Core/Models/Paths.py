# -*- coding: utf-8 -*-
"""Path-planning data contracts for future PanelOptimizer engines."""

from __future__ import annotations

from dataclasses import dataclass

from .Common import Point3D


@dataclass(frozen=True, slots=True)
class CandidatePath:
    """One unranked, geometry-neutral candidate seam path."""

    candidate_id: str
    geometry_id: str
    points: tuple[Point3D, ...]
    followed_feature_ids: tuple[str, ...]
    notes: tuple[str, ...] = ()

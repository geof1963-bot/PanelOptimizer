# -*- coding: utf-8 -*-
"""Read-only detection of cylindrical dead-end regions."""

from __future__ import annotations

from ..Models import DeadEndRegion, GeometrySnapshot
from .HoleDetector import DetectedHole
from ._Utilities import identifier

__all__ = ["DeadEndDetector"]


class DeadEndDetector:
    """Describe blind cylindrical recesses without applying thresholds."""

    def detect(
        self,
        geometry: GeometrySnapshot,
        holes: tuple[DetectedHole, ...],
    ) -> tuple[DeadEndRegion, ...]:
        """Create dead ends only from one-entry, one-cap hole topology.

        Through segments and segments opening into other void geometry have no
        unambiguous terminal point and are therefore omitted.
        """
        dead_ends: list[DeadEndRegion] = []
        for hole in holes:
            if hole.entry_point is None or hole.terminal_point is None:
                continue
            dead_ends.append(
                DeadEndRegion(
                    region_id=identifier(
                        geometry.source_id,
                        "dead-end",
                        len(dead_ends) + 1,
                    ),
                    entry_point=hole.entry_point,
                    terminal_point=hole.terminal_point,
                    bounding_box=hole.bounding_box,
                    depth_mm=hole.feature.depth_mm,
                    minimum_width_mm=hole.feature.diameter_mm,
                )
            )
        return tuple(dead_ends)

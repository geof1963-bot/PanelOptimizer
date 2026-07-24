# -*- coding: utf-8 -*-
"""Public interface for the PanelOptimizer splitting engine."""

from __future__ import annotations

from collections.abc import Callable

from .Models import GeometrySnapshot, JoineryPlan, PrintablePart, SplitPlan

__all__ = ["SplitterEngine"]


class SplitterEngine:
    """Define the creation of printable parts from immutable plans."""

    def create_printable_parts(
        self,
        geometry: GeometrySnapshot,
        split_plan: SplitPlan,
        joinery_plan: JoineryPlan,
        shape_resolver: Callable[[str], object],
    ) -> tuple[PrintablePart, ...]:
        """Create new printable parts for one geometry and its plans.

        Args:
            geometry: The immutable snapshot of the source geometry.
            split_plan: The selected seam-path plan for the geometry.
            joinery_plan: The joinery specification for the split plan.
            shape_resolver: An injected callable that resolves a source ID to
                the caller-owned source shape.

        Returns:
            Newly created PrintablePart records for the supplied plans.

        Raises:
            NotImplementedError: Always, until the splitting engine exists.
            SplitterError: In a future implementation, if the plans cannot be
                applied to produce valid printable parts.
        """
        raise NotImplementedError("SplitterEngine.create_printable_parts")

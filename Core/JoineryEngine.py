# -*- coding: utf-8 -*-
"""Public interface for the PanelOptimizer joinery engine."""

from __future__ import annotations

from .Models import JoineryPlan, SplitPlan

__all__ = ["JoineryEngine"]


class JoineryEngine:
    """Define the joinery plan generated for an immutable split plan."""

    def create_joinery_plan(self, split_plan: SplitPlan) -> JoineryPlan:
        """Create a new joinery plan for one selected split plan.

        Args:
            split_plan: The immutable plan containing selected seam paths.

        Returns:
            A newly created JoineryPlan associated with the split plan.

        Raises:
            NotImplementedError: Always, until the joinery engine exists.
            JoineryError: In a future implementation, if compatible joinery
                cannot be specified for the split plan.
        """
        raise NotImplementedError("JoineryEngine.create_joinery_plan")

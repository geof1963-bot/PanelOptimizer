# -*- coding: utf-8 -*-
"""Public interface for the PanelOptimizer path-finding engine."""

from __future__ import annotations

from .Models import AnalysisReport, SplitPlan

__all__ = ["PathFinderEngine"]


class PathFinderEngine:
    """Define the planning of seam paths from immutable analysis data."""

    def create_split_plan(self, analysis: AnalysisReport) -> SplitPlan:
        """Create a new split plan from one analysis report.

        Args:
            analysis: The report containing the geometry and detected features.

        Returns:
            A newly created SplitPlan containing selected candidate paths.

        Raises:
            NotImplementedError: Always, until the path-finding engine exists.
            PathFinderError: In a future implementation, if no valid split plan
                can be produced.
        """
        raise NotImplementedError("PathFinderEngine.create_split_plan")

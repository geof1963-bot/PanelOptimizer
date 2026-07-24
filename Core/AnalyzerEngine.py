# -*- coding: utf-8 -*-
"""Public interface for the PanelOptimizer analysis engine."""

from __future__ import annotations

from .Models import AnalysisReport, GeometrySnapshot

__all__ = ["AnalyzerEngine"]


class AnalyzerEngine:
    """Define the analysis of a geometry snapshot without altering it."""

    def analyze(self, geometry: GeometrySnapshot) -> AnalysisReport:
        """Create a new analysis report for one geometry snapshot.

        Args:
            geometry: The immutable geometry snapshot to inspect.

        Returns:
            A newly created AnalysisReport for the supplied geometry.

        Raises:
            NotImplementedError: Always, until the analyzer engine exists.
            AnalyzerError: In a future implementation, if analysis cannot be
                completed for the supplied geometry.
        """
        raise NotImplementedError("AnalyzerEngine.analyze")

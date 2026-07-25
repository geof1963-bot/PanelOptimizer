# -*- coding: utf-8 -*-
"""Orchestration of implemented read-only geometric observations."""

from __future__ import annotations

from ..Exceptions import GeometricAnalysisError
from ..Models import GeometricAnalysis, GeometrySnapshot, TopologyAnalysis
from .ClearanceAnalyzer import ClearanceAnalyzer
from .ThicknessAnalyzer import ThicknessAnalyzer

__all__ = ["GeometricAnalyzer"]


class GeometricAnalyzer:
    """Coordinate only the currently implemented geometric analyzers."""

    def analyze(
        self,
        geometry: GeometrySnapshot,
        topology: TopologyAnalysis,
        shape: object,
    ) -> GeometricAnalysis:
        """Return thickness and clearance observations for one source shape.

        All other GeometricAnalysis collections retain their exact model
        defaults until their dedicated components are implemented.

        Raises:
            GeometricAnalysisError: If an unexpected failure prevents the
                implemented geometric observations from being completed.
        """
        try:
            return GeometricAnalysis(
                thickness_observations=ThicknessAnalyzer().analyze(
                    geometry,
                    topology,
                    shape,
                ),
                clearance_observations=ClearanceAnalyzer().analyze(
                    geometry,
                    topology,
                    shape,
                ),
            )
        except GeometricAnalysisError:
            raise
        except Exception as error:
            raise GeometricAnalysisError(
                "Unable to derive geometric observations from the source shape."
            ) from error

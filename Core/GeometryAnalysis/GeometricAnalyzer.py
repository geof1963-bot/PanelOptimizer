# -*- coding: utf-8 -*-
"""Orchestration of implemented read-only geometric observations."""

from __future__ import annotations

from ..Exceptions import GeometricAnalysisError
from ..Models import GeometricAnalysis, GeometrySnapshot, TopologyAnalysis
from .ClearanceAnalyzer import ClearanceAnalyzer
from .ComplexityAnalyzer import ComplexityAnalyzer
from .CornerAnalyzer import CornerAnalyzer
from .CurvatureAnalyzer import CurvatureAnalyzer
from .EdgeAnalyzer import EdgeAnalyzer
from .FlatRegionAnalyzer import FlatRegionAnalyzer
from .LigamentAnalyzer import LigamentAnalyzer
from .ProximityAnalyzer import ProximityAnalyzer
from .SymmetryAnalyzer import SymmetryAnalyzer
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
        """Return all currently implemented observations for one source shape.

        Manufacturing and seam stages remain outside this orchestrator.

        Raises:
            GeometricAnalysisError: If an unexpected failure prevents the
                implemented geometric observations from being completed.
        """
        try:
            thickness_observations = ThicknessAnalyzer().analyze(
                geometry,
                topology,
                shape,
            )
            clearance_observations = ClearanceAnalyzer().analyze(
                geometry,
                topology,
                shape,
            )
            edge_observations = EdgeAnalyzer().analyze(
                geometry,
                topology,
                shape,
            )
            return GeometricAnalysis(
                thickness_observations=thickness_observations,
                clearance_observations=clearance_observations,
                material_ligaments=LigamentAnalyzer().analyze(
                    geometry,
                    topology,
                    clearance_observations,
                ),
                edge_observations=edge_observations,
                corner_observations=CornerAnalyzer().analyze(
                    geometry,
                    topology,
                    shape,
                ),
                curvature_observations=CurvatureAnalyzer().analyze(
                    geometry,
                    topology,
                    shape,
                ),
                flat_regions=FlatRegionAnalyzer().analyze(
                    geometry,
                    topology,
                    shape,
                ),
                symmetries=SymmetryAnalyzer().analyze(
                    geometry,
                    topology,
                    shape,
                ),
                feature_proximities=ProximityAnalyzer().analyze(
                    geometry,
                    topology,
                    shape,
                    clearance_observations,
                ),
                complexity_indicators=ComplexityAnalyzer().analyze(
                    geometry,
                    topology,
                    shape,
                    edge_observations,
                ),
            )
        except GeometricAnalysisError:
            raise
        except Exception as error:
            raise GeometricAnalysisError(
                "Unable to derive geometric observations from the source shape."
            ) from error

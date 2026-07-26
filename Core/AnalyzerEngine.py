# -*- coding: utf-8 -*-
"""Public interface for the staged PanelOptimizer analysis engine."""

from __future__ import annotations

import logging
from collections.abc import Callable

from .Exceptions import AnalyzerError, ShapeResolutionError
from .GeometryAnalysis import GeometricAnalyzer
from .Models import AnalysisReport, GeometrySnapshot
from .Topology import TopologyAnalyzer

__all__ = ["AnalyzerEngine"]


class AnalyzerEngine:
    """Orchestrate read-only analysis stages for one geometry snapshot.

    The source shape is obtained through an injected resolver instead of a
    FreeCAD document.  This keeps the engine independent of GUI and document
    state and gives the caller ownership of the resolved shape.
    """

    def __init__(
        self,
        shape_resolver: Callable[[str], object] | None = None,
    ) -> None:
        """Create an analyzer with an optional read-only shape resolver.

        Args:
            shape_resolver: A callable mapping a snapshot source ID to the
                caller-owned source shape.  It may instead be supplied to
                :meth:`analyze` for compatibility with engine call sites that
                inject dependencies per operation.
        """
        self._shape_resolver = shape_resolver

    def analyze(
        self,
        geometry: GeometrySnapshot,
        shape_resolver: Callable[[str], object] | None = None,
    ) -> AnalysisReport:
        """Describe the implemented analysis stages for one snapshot.

        Args:
            geometry: The immutable geometry snapshot to inspect.
            shape_resolver: An optional operation-scoped resolver.  When
                present it takes precedence over the constructor dependency.

        Returns:
            A new partial report containing topology plus the complete
            approved GeometricAnalysis observations. Manufacturing and seam
            stages retain their immutable empty defaults.

        Raises:
            ShapeResolutionError: If no callable resolver is available or the
                source shape cannot be resolved.
            AnalyzerError: If an implemented analysis stage cannot be
                completed.
        """
        logger = logging.getLogger(self.__class__.__name__)
        resolver = (
            shape_resolver
            if shape_resolver is not None
            else self._shape_resolver
        )

        if resolver is None or not callable(resolver):
            raise ShapeResolutionError(
                "AnalyzerEngine requires a callable read-only shape resolver."
            )

        try:
            shape = resolver(geometry.source_id)
        except AnalyzerError:
            raise
        except Exception as error:
            logger.error(
                "Unable to resolve analysis source '%s'.",
                geometry.source_id,
            )
            raise ShapeResolutionError(
                f"Unable to resolve source shape '{geometry.source_id}'."
            ) from error

        if shape is None:
            raise ShapeResolutionError(
                f"Resolver returned no shape for '{geometry.source_id}'."
            )

        try:
            topology = TopologyAnalyzer().analyze(geometry, shape)
            geometric = GeometricAnalyzer().analyze(
                geometry,
                topology,
                shape,
            )
            return AnalysisReport(
                geometry=geometry,
                topology=topology,
                geometric=geometric,
            )
        except AnalyzerError:
            logger.error(
                "Unable to analyze source '%s'.",
                geometry.source_id,
            )
            raise
        except Exception as error:
            logger.error(
                "Unexpected analysis failure for '%s'.",
                geometry.source_id,
            )
            raise AnalyzerError(
                f"Analysis failed for '{geometry.source_id}'."
            ) from error

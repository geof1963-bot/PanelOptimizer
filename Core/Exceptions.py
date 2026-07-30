# -*- coding: utf-8 -*-
"""
***************************************************************************
*   PanelOptimizer - FreeCAD Workbench                                    *
*                                                                         *
*   Exceptions.py                                                         *
*                                                                         *
*   Custom exceptions used throughout the project.                        *
*                                                                         *
***************************************************************************
"""


class PanelOptimizerError(Exception):
    """Base exception for PanelOptimizer."""
    pass


class GeometryError(PanelOptimizerError):
    """Geometry related error."""
    pass


class NullShapeError(GeometryError):
    """Raised when a supplied shape is null or missing."""
    pass


class InvalidShapeError(GeometryError):
    """Raised when a supplied shape fails geometric validation."""
    pass


class EmptyShapeError(GeometryError):
    """Raised when a supplied shape contains no measurable topology."""
    pass


class GeometryMeasurementError(GeometryError):
    """Raised when a shape property required for measurement is unavailable."""
    pass


class AnalyzerError(PanelOptimizerError):
    """Analyzer related error."""
    pass


class ShapeResolutionError(AnalyzerError):
    """Raised when an analyzer cannot resolve its snapshot's source shape."""
    pass


class TopologyAnalysisError(AnalyzerError):
    """Raised when source topology cannot be described reliably."""
    pass


class GeometricAnalysisError(AnalyzerError):
    """Raised when implemented local geometry cannot be measured reliably."""
    pass


class ManufacturingAnalysisError(AnalyzerError):
    """Raised when manufacturing evidence cannot be evaluated reliably."""
    pass


class ManufacturingProfileError(ManufacturingAnalysisError):
    """Raised when configured settings cannot form a valid profile."""
    pass


class ConstraintEvaluationError(ManufacturingAnalysisError):
    """Raised when a configured constraint cannot be applied safely."""
    pass


class PathFinderError(PanelOptimizerError):
    """PathFinder related error."""
    pass


class SplitterError(PanelOptimizerError):
    """Splitter related error."""
    pass


class InvalidSelectionError(SplitterError):
    """Raised when the split command does not receive exactly one source."""
    pass


class SplitSourceError(SplitterError):
    """Raised when selected geometry cannot be used as one solid source."""
    pass


class SplitOperationError(SplitterError):
    """Raised when the requested boolean split cannot complete reliably."""
    pass


class RegionConnectivityError(SplitOperationError):
    """Raised with structured evidence for a disconnected ownership region."""

    def __init__(self, diagnosis):
        self.diagnosis = diagnosis
        super().__init__(diagnosis.failure_message())


class UnexpectedPartCountError(SplitOperationError):
    """Raised when a split does not produce exactly four quadrant parts."""
    pass


class InvalidResultingSolidError(SplitOperationError):
    """Raised when a produced quadrant is empty, invalid, or not one solid."""
    pass


class PrintableLimitViolation(SplitterError):
    """Raised when a workflow attempts to export an oversized result part."""
    pass


class JoineryError(PanelOptimizerError):
    """Joinery related error."""
    pass


class DowelPlanningError(JoineryError):
    """Raised when a safe deterministic dowel plan cannot be produced."""
    pass


class LipBuildError(JoineryError):
    """Raised when V4.50 lip geometry cannot be built safely."""
    pass


class ExportError(PanelOptimizerError):
    """Export related error."""
    pass


class STLExportError(ExportError):
    """Raised when transactional STL export cannot complete."""
    pass


class SettingsError(PanelOptimizerError):
    """Settings related error."""
    pass

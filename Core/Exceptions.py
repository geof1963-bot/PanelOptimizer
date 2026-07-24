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


class PathFinderError(PanelOptimizerError):
    """PathFinder related error."""
    pass


class SplitterError(PanelOptimizerError):
    """Splitter related error."""
    pass


class JoineryError(PanelOptimizerError):
    """Joinery related error."""
    pass


class ExportError(PanelOptimizerError):
    """Export related error."""
    pass


class SettingsError(PanelOptimizerError):
    """Settings related error."""
    pass

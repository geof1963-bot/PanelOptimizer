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
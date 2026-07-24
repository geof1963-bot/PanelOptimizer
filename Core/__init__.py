# -*- coding: utf-8 -*-
"""
PanelOptimizer.Core
===================

Core engine package for the PanelOptimizer FreeCAD Workbench.

This package contains all non-GUI logic of the project.

Modules
-------
BaseObject : Shared engine-object functionality.
Exceptions : Custom project exceptions.
GeometryEngine : Geometry-engine public interface.
AnalyzerEngine  : Analysis-engine public interface.
PathFinderEngine: Path-finding public interface.
JoineryEngine   : Joinery-engine public interface.
SplitterEngine  : Splitting-engine public interface.
ExportEngine    : Export-engine public interface.
Models     : Immutable data contracts shared by engine modules.
Settings   : Global project parameters.
"""

__title__ = "PanelOptimizer.Core"
__author__ = "Geoffroy"
__license__ = "GPL-3.0-or-later"

__all__ = [
    "BaseObject",
    "Exceptions",
    "GeometryEngine",
    "AnalyzerEngine",
    "PathFinderEngine",
    "JoineryEngine",
    "SplitterEngine",
    "ExportEngine",
    "Models",
    "Settings",
]

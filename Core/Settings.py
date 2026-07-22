# -*- coding: utf-8 -*-
"""
PanelOptimizer Workbench
Core/Settings.py

Global settings and design constraints.

All project constants must be defined here.
No module should hardcode numerical values.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PrinterSettings:
    """3D printer characteristics."""

    NAME: str = "Creality K2 Plus"

    BED_SIZE_X: float = 350.0
    BED_SIZE_Y: float = 350.0

    # Safety margin
    MAX_PART_SIZE: float = 330.0


@dataclass(frozen=True)
class PanelSettings:
    """Default panel characteristics."""

    DEFAULT_WIDTH: float = 594.0
    DEFAULT_HEIGHT: float = 594.0
    DEFAULT_THICKNESS: float = 8.0


@dataclass(frozen=True)
class JoinerySettings:
    """Invisible assembly parameters."""

    DOWEL_DIAMETER: float = 4.0
    HOLE_DIAMETER: float = 4.3

    DOWEL_MAX_LENGTH: float = 30.0

    HOLE_DEPTH: float = 20.0

    ENTRANCE_CHAMFER: float = 0.40

    MIN_DISTANCE_FROM_EDGE: float = 10.0

    MIN_DISTANCE_FROM_DECORATION: float = 8.0

    MIN_DOWEL_SPACING: float = 80.0
    MAX_DOWEL_SPACING: float = 120.0


@dataclass(frozen=True)
class SplitSettings:
    """Split engine constraints."""

    NUMBER_OF_PARTS: int = 4

    MAX_PART_WIDTH: float = 330.0
    MAX_PART_HEIGHT: float = 330.0

    ENABLE_SMART_PATH: bool = True

    GENERATE_MULTIPLE_SOLUTIONS: bool = True

    NUMBER_OF_SOLUTIONS: int = 5


@dataclass(frozen=True)
class AnalyzerSettings:
    """Geometry analyzer parameters."""

    DETECT_HOLES: bool = True

    DETECT_ISLANDS: bool = True

    DETECT_CORRIDORS: bool = True

    COMPUTE_BOUNDING_BOX: bool = True

    COMPUTE_VOLUME: bool = True

    COMPUTE_AREA: bool = True

    COMPUTE_PERIMETER: bool = True


class Settings:
    """
    Global settings container.
    """

    Printer = PrinterSettings()

    Panel = PanelSettings()

    Joinery = JoinerySettings()

    Split = SplitSettings()

    Analyzer = AnalyzerSettings()
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
    BED_SIZE_Z: float | None = None

    # Legacy compatibility value. ProfileComposer intentionally ignores this;
    # Settings.Split owns effective axis-specific printable-part limits.
    MAX_PART_SIZE: float = 330.0


@dataclass(frozen=True)
class PanelSettings:
    """Default panel characteristics."""

    DEFAULT_WIDTH: float = 594.0
    DEFAULT_HEIGHT: float = 594.0
    DEFAULT_THICKNESS: float = 8.0


@dataclass(frozen=True)
class JoinerySettings:
    """Simple V4.60 wooden-dowel planning parameters, in millimetres."""

    DOWEL_DIAMETER_MM: float = 4.0
    DOWEL_HOLE_DIAMETER_MM: float = 4.3
    DOWEL_LENGTH_MM: float = 30.0
    DOWEL_AXIS_HEIGHT_MM: float = 2.5
    DOWEL_EDGE_MARGIN_MM: float = 15.0
    DOWEL_MIN_MATERIAL_MARGIN_MM: float = 2.0
    DOWEL_CENTER_EXCLUSION_MM: float = 20.0
    DOWEL_MIN_SPACING_MM: float = 60.0
    DOWEL_MAX_UNSUPPORTED_SPAN_MM: float = 110.0
    DOWELS_TARGET_PER_BRANCH: int = 4
    DOWELS_MIN_PER_BRANCH: int = 3
    DOWELS_MAX_PER_BRANCH: int = 4
    DOWEL_MIN_USEFUL_DEPTH_PER_SIDE_MM: float = 6.0


@dataclass(frozen=True)
class LipSettings:
    """V4.50 top-surface mastic-lip dimensions, in millimetres."""

    LIP_HEIGHT_MM: float = 0.30
    LIP_WIDTH_MM: float = 0.80


@dataclass(frozen=True)
class PerformanceSettings:
    """Interactive performance switches; safety validation stays enabled."""

    FULL_STL_REOPEN_VALIDATION: bool = True


@dataclass(frozen=True)
class SplitSettings:
    """Split engine constraints."""

    NUMBER_OF_PARTS: int = 4

    MAX_PART_WIDTH: float = 330.0
    MAX_PART_HEIGHT: float = 330.0
    MAX_PART_DEPTH: float | None = None

    ENABLE_SMART_PATH: bool = True

    GENERATE_MULTIPLE_SOLUTIONS: bool = True

    NUMBER_OF_SOLUTIONS: int = 5

    # V4.30 lightweight top-view seam-path geometry.
    SEAM_SEARCH_CORRIDOR_MM: float = 75.0
    SEAM_CENTER_EXCLUSION_MM: float = 12.0
    SEAM_MIN_FEATURE_SIZE_MM: float = 8.0
    SEAM_BOUNDARY_DEFLECTION_MM: float = 2.0
    SEAM_SIMPLIFICATION_MM: float = 1.0
    SEAM_SIMPLIFY_TOLERANCE_MM: float = 0.50
    SEAM_MAX_ARTIFICIAL_TURN_DEG: float = 30.0
    SEAM_APPROACH_LENGTH_MM: float = 5.0
    SEAM_HOLE_CLEARANCE_MM: float = 0.10
    MAX_FOLLOWED_FEATURES_PER_SEAM: int = 8
    MAX_SEAM_VARIANTS_PER_AXIS: int = 12
    SEAM_MIN_FOLLOW_LENGTH_MM: float = 15.0
    SEAM_BEAM_WIDTH: int = 6
    SEAM_COVERAGE_EPSILON_MM: float = 1.0
    MAX_EXACT_TOPOLOGY_VALIDATIONS: int = 8
    SEAM_PLANNING_TIME_BUDGET_S: float = 30.0
    MAX_CONNECTIVITY_REPAIR_ATTEMPTS: int = 8
    MAX_CONNECTIVITY_REPAIR_TIME_S: float = 20.0
    CONNECTIVITY_REPAIR_WINDOW_MM: float = 40.0

    # V4.74C conservative ownership-fragment classification.  Every scalar
    # limit must pass together; none of these values is sufficient alone.
    MAX_SLIVER_VOLUME_MM3: float = 50.0
    MAX_SLIVER_VOLUME_RATIO: float = 0.0002
    MAX_SLIVER_THICKNESS_RATIO: float = 0.30
    # This is a bounding-box footprint, not occupied area. Thin curved B-rep
    # fragments can therefore have sparse boxes much larger than volume/Z.
    MAX_SLIVER_FOOTPRINT_MM2: float = 300.0
    MAX_SLIVER_BOUNDARY_DISTANCE_MM: float = 2.5
    PANEL_EXTERIOR_TOLERANCE_MM: float = 0.05


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


@dataclass(frozen=True)
class ManufacturingSettings:
    """Versioned fabrication constraints used to compose a profile.

    ``None`` means that no scalar value is configured.  Enabled flags are
    retained separately so a configured rule can be disabled without losing
    its value.  No minimum is invented by the manufacturing implementation.
    """

    PROFILE_ID: str = "creality-k2-plus-fdm"
    PROFILE_VERSION: str = "1"
    SETTINGS_VERSION: str = "3.12"
    PROCESS_TYPE: str = "fdm"

    ENABLE_BUILD_ENVELOPE: bool = True

    MINIMUM_THICKNESS_MM: float | None = None
    MINIMUM_THICKNESS_LEVEL: str = "hard"
    ENABLE_MINIMUM_THICKNESS: bool = False

    MINIMUM_LIGAMENT_WIDTH_MM: float | None = None
    MINIMUM_LIGAMENT_LEVEL: str = "hard"
    ENABLE_MINIMUM_LIGAMENT: bool = False

    MINIMUM_HOLE_TO_HOLE_CLEARANCE_MM: float | None = None
    MINIMUM_HOLE_TO_HOLE_CLEARANCE_LEVEL: str = "hard"
    ENABLE_MINIMUM_HOLE_TO_HOLE_CLEARANCE: bool = False

    MINIMUM_HOLE_TO_EXTERIOR_CLEARANCE_MM: float | None = None
    MINIMUM_HOLE_TO_EXTERIOR_CLEARANCE_LEVEL: str = "hard"
    ENABLE_MINIMUM_HOLE_TO_EXTERIOR_CLEARANCE: bool = False


class Settings:
    """
    Global settings container.
    """

    Printer = PrinterSettings()

    Panel = PanelSettings()

    Joinery = JoinerySettings()

    Lips = LipSettings()

    Performance = PerformanceSettings()

    Split = SplitSettings()

    Analyzer = AnalyzerSettings()

    Manufacturing = ManufacturingSettings()

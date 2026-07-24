# -*- coding: utf-8 -*-
"""Immutable data contracts shared by PanelOptimizer engine modules."""

from .Analysis import (
    AnalysisReport,
    CorridorFeature,
    HoleFeature,
    IslandFeature,
)
from .Common import BoundingBox, Direction3D, Point3D
from .Export import ExportArtifact, ExportReport
from .Geometry import GeometrySnapshot
from .Paths import CandidatePath, PathMetrics
from .Split import (
    DowelPlacement,
    JoineryPlan,
    JointSpecification,
    PrintablePart,
    SplitPlan,
)

__all__ = [
    "AnalysisReport",
    "BoundingBox",
    "CandidatePath",
    "CorridorFeature",
    "Direction3D",
    "DowelPlacement",
    "ExportArtifact",
    "ExportReport",
    "GeometrySnapshot",
    "HoleFeature",
    "IslandFeature",
    "JoineryPlan",
    "JointSpecification",
    "PathMetrics",
    "Point3D",
    "PrintablePart",
    "SplitPlan",
]

# -*- coding: utf-8 -*-
"""Immutable data contracts shared by PanelOptimizer engine modules."""

from .Analysis import (
    AnalysisReport,
    CorridorFeature,
    CandidateZone,
    CavityFeature,
    ConnectivityEdge,
    ConnectivityGraph,
    ConnectivityNode,
    DeadEndRegion,
    GeometricAnalysis,
    HoleFeature,
    IslandFeature,
    ManufacturingAnalysis,
    ManufacturingWarning,
    SeamAnalysis,
    SymmetryFeature,
    ThinBridgeFeature,
    TopologyAnalysis,
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
    "CandidateZone",
    "CandidatePath",
    "CavityFeature",
    "ConnectivityEdge",
    "ConnectivityGraph",
    "ConnectivityNode",
    "CorridorFeature",
    "DeadEndRegion",
    "Direction3D",
    "DowelPlacement",
    "ExportArtifact",
    "ExportReport",
    "GeometricAnalysis",
    "GeometrySnapshot",
    "HoleFeature",
    "IslandFeature",
    "JoineryPlan",
    "JointSpecification",
    "ManufacturingAnalysis",
    "ManufacturingWarning",
    "PathMetrics",
    "Point3D",
    "PrintablePart",
    "SeamAnalysis",
    "SplitPlan",
    "SymmetryFeature",
    "ThinBridgeFeature",
    "TopologyAnalysis",
]

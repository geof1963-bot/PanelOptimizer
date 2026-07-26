# -*- coding: utf-8 -*-
"""Immutable data contracts shared by PanelOptimizer engine modules."""

from .Analysis import (
    AnalysisReport,
    CandidateZone,
    CavityFeature,
    ConnectivityEdge,
    ConnectivityGraph,
    ConnectivityNode,
    DeadEndRegion,
    GeometricAnalysis,
    HoleFeature,
    IslandFeature,
    SeamAnalysis,
    TopologyAnalysis,
)
from .Clearance import (
    ClearanceObservation,
    FeatureProximityObservation,
)
from .Common import BoundingBox, Direction3D, Point3D
from .Complexity import GeometricComplexityObservation
from .Curvature import CurvatureObservation, FlatRegionObservation
from .Edges import CornerObservation, EdgeObservation
from .Export import ExportArtifact, ExportReport
from .Geometry import GeometrySnapshot
from .Ligaments import MaterialLigamentObservation
from .Manufacturing import (
    BuildEnvelope,
    ConstraintEvaluation,
    ManufacturingAnalysis,
    ManufacturingConstraint,
    ManufacturingProfile,
    ManufacturingWarning,
)
from .Paths import CandidatePath
from .Scoring import (
    CandidateScore,
    PathRanking,
    ScoreBreakdown,
    ScoringCriterion,
)
from .Symmetry import SymmetryObservation
from .Thickness import ThicknessObservation
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
    "BuildEnvelope",
    "CandidateScore",
    "CandidateZone",
    "CandidatePath",
    "CavityFeature",
    "ClearanceObservation",
    "ConnectivityEdge",
    "ConnectivityGraph",
    "ConnectivityNode",
    "ConstraintEvaluation",
    "CornerObservation",
    "CurvatureObservation",
    "DeadEndRegion",
    "Direction3D",
    "DowelPlacement",
    "EdgeObservation",
    "ExportArtifact",
    "ExportReport",
    "FeatureProximityObservation",
    "FlatRegionObservation",
    "GeometricAnalysis",
    "GeometricComplexityObservation",
    "GeometrySnapshot",
    "HoleFeature",
    "IslandFeature",
    "JoineryPlan",
    "JointSpecification",
    "ManufacturingAnalysis",
    "ManufacturingConstraint",
    "ManufacturingProfile",
    "ManufacturingWarning",
    "MaterialLigamentObservation",
    "PathRanking",
    "Point3D",
    "PrintablePart",
    "ScoreBreakdown",
    "ScoringCriterion",
    "SeamAnalysis",
    "SplitPlan",
    "SymmetryObservation",
    "ThicknessObservation",
    "TopologyAnalysis",
]

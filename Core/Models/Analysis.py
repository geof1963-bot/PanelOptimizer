# -*- coding: utf-8 -*-
"""Analysis data contracts exchanged by future PanelOptimizer engines."""

from __future__ import annotations

from dataclasses import dataclass, field

from .Clearance import (
    ClearanceObservation,
    FeatureProximityObservation,
)
from .Common import BoundingBox, Direction3D, Point3D
from .Complexity import GeometricComplexityObservation
from .Curvature import CurvatureObservation, FlatRegionObservation
from .Edges import CornerObservation, EdgeObservation
from .Geometry import GeometrySnapshot
from .Ligaments import MaterialLigamentObservation
from .Manufacturing import ManufacturingAnalysis
from .Seam import SeamAnalysis
from .Symmetry import SymmetryObservation
from .Thickness import ThicknessObservation


@dataclass(frozen=True, slots=True)
class HoleFeature:
    """A detected circular opening or recess in the source geometry."""

    feature_id: str
    center: Point3D
    axis: Direction3D
    diameter_mm: float
    depth_mm: float
    is_through_hole: bool


@dataclass(frozen=True, slots=True)
class IslandFeature:
    """A detected isolated geometric region."""

    feature_id: str
    bounding_box: BoundingBox
    center: Point3D
    area_mm2: float


@dataclass(frozen=True, slots=True)
class CavityFeature:
    """A detected internal void and its known opening relationships."""

    feature_id: str
    center: Point3D
    bounding_box: BoundingBox
    volume_mm3: float
    opening_feature_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DeadEndRegion:
    """A region with one known entry and no onward connection."""

    region_id: str
    entry_point: Point3D
    terminal_point: Point3D
    bounding_box: BoundingBox
    depth_mm: float
    minimum_width_mm: float


@dataclass(frozen=True, slots=True)
class ConnectivityNode:
    """One region or feature represented as a graph node."""

    node_id: str
    node_type: str
    position: Point3D
    related_feature_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ConnectivityEdge:
    """One traversable relationship between two connectivity nodes."""

    edge_id: str
    start_node_id: str
    end_node_id: str
    length_mm: float
    minimum_clearance_mm: float


@dataclass(frozen=True, slots=True)
class ConnectivityGraph:
    """A graph describing connectivity between analyzed regions."""

    nodes: tuple[ConnectivityNode, ...]
    edges: tuple[ConnectivityEdge, ...]
    connected_component_count: int


@dataclass(frozen=True, slots=True)
class TopologyAnalysis:
    """Immutable findings about holes, regions, cavities, and connectivity."""

    holes: tuple[HoleFeature, ...] = ()
    islands: tuple[IslandFeature, ...] = ()
    cavities: tuple[CavityFeature, ...] = ()
    dead_ends: tuple[DeadEndRegion, ...] = ()
    connectivity_graph: ConnectivityGraph | None = None


@dataclass(frozen=True, slots=True)
class GeometricAnalysis:
    """Focused local observations and source-wide complexity counts.

    Global bounds, dimensions, area, volume, and raw topology counts remain in
    ``GeometrySnapshot``.  Holes, islands, cavities, dead ends, and material
    connectivity remain in ``TopologyAnalysis``.  These empty tuple defaults
    allow AnalyzerEngine to return reports while later stages remain inactive.
    """

    thickness_observations: tuple[ThicknessObservation, ...] = ()
    clearance_observations: tuple[ClearanceObservation, ...] = ()
    material_ligaments: tuple[MaterialLigamentObservation, ...] = ()
    edge_observations: tuple[EdgeObservation, ...] = ()
    corner_observations: tuple[CornerObservation, ...] = ()
    curvature_observations: tuple[CurvatureObservation, ...] = ()
    flat_regions: tuple[FlatRegionObservation, ...] = ()
    symmetries: tuple[SymmetryObservation, ...] = ()
    feature_proximities: tuple[FeatureProximityObservation, ...] = ()
    complexity_indicators: tuple[GeometricComplexityObservation, ...] = ()


@dataclass(frozen=True, slots=True)
class AnalysisReport:
    """The immutable, staged result of analyzing one geometry snapshot."""

    geometry: GeometrySnapshot
    topology: TopologyAnalysis = field(default_factory=TopologyAnalysis)
    geometric: GeometricAnalysis = field(default_factory=GeometricAnalysis)
    manufacturing: ManufacturingAnalysis = field(
        default_factory=ManufacturingAnalysis
    )
    seam: SeamAnalysis = field(default_factory=SeamAnalysis)

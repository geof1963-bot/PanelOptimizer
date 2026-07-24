# -*- coding: utf-8 -*-
"""Analysis data contracts exchanged by future PanelOptimizer engines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .Common import BoundingBox, Direction3D, Point3D
from .Geometry import GeometrySnapshot


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
class CorridorFeature:
    """A detected narrow region that may inform a seam-path decision."""

    feature_id: str
    start: Point3D
    end: Point3D
    length_mm: float
    minimum_width_mm: float


@dataclass(frozen=True, slots=True)
class ThinBridgeFeature:
    """A detected narrow connection between larger geometric regions."""

    feature_id: str
    start: Point3D
    end: Point3D
    bounding_box: BoundingBox
    length_mm: float
    minimum_width_mm: float
    minimum_thickness_mm: float


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
class SymmetryFeature:
    """A detected reflective or rotational symmetry relationship."""

    feature_id: str
    symmetry_type: str
    origin: Point3D
    direction: Direction3D
    confidence: float


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
class CandidateZone:
    """A region classified as safe or forbidden for future seam planning."""

    zone_id: str
    classification: Literal["safe", "forbidden"]
    anchor: Point3D
    bounding_box: BoundingBox
    boundary_points: tuple[Point3D, ...]
    reason: str
    related_feature_ids: tuple[str, ...]
    normal: Direction3D | None = None


@dataclass(frozen=True, slots=True)
class ManufacturingWarning:
    """A structured manufacturing concern found during analysis."""

    warning_id: str
    category: str
    severity: str
    message: str
    related_feature_ids: tuple[str, ...]
    location: Point3D | None = None
    bounding_box: BoundingBox | None = None


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
    """Immutable findings about dimensions, passages, and symmetry."""

    thin_bridges: tuple[ThinBridgeFeature, ...] = ()
    corridors: tuple[CorridorFeature, ...] = ()
    symmetries: tuple[SymmetryFeature, ...] = ()


@dataclass(frozen=True, slots=True)
class ManufacturingAnalysis:
    """Immutable manufacturing concerns without making split decisions."""

    warnings: tuple[ManufacturingWarning, ...] = ()


@dataclass(frozen=True, slots=True)
class SeamAnalysis:
    """Immutable seam-planning evidence without generating seam paths."""

    safe_zones: tuple[CandidateZone, ...] = ()
    forbidden_zones: tuple[CandidateZone, ...] = ()


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

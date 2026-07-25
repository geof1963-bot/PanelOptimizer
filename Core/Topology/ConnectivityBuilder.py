# -*- coding: utf-8 -*-
"""Material-region decomposition and connectivity graph construction."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..Exceptions import TopologyAnalysisError
from ..Models import (
    BoundingBox,
    ConnectivityEdge,
    ConnectivityGraph,
    ConnectivityNode,
    DeadEndRegion,
    GeometrySnapshot,
    Point3D,
)

if TYPE_CHECKING:
    from .CavityDetector import DetectedCavity
    from .HoleDetector import DetectedHole

from ._Utilities import bounding_box, finite_float, identifier, point, same_shape

__all__ = ["ConnectivityBuilder"]


@dataclass(frozen=True, slots=True)
class MaterialRegion:
    """Internal read-only view of a resolved solid or shell region."""

    shape: object
    node_id: str
    node_type: str
    center: Point3D
    bounding_box: BoundingBox
    area_mm2: float
    volume_mm3: float


class ConnectivityBuilder:
    """Decompose material and describe shared-face connectivity."""

    def material_regions(
        self,
        geometry: GeometrySnapshot,
        shape: object,
    ) -> tuple[MaterialRegion, ...]:
        """Create internal regions from solids, shells, or a face-bearing shape.

        Source topology order is retained.  Region size never changes inclusion
        or ordering.
        """
        solids = tuple(getattr(shape, "Solids", ()))
        shells = tuple(getattr(shape, "Shells", ()))
        raw_regions = solids or shells
        if not raw_regions and tuple(getattr(shape, "Faces", ())):
            raw_regions = (shape,)
        if not raw_regions:
            raise TopologyAnalysisError(
                "Resolved source shape contains no material regions."
            )

        return tuple(
            MaterialRegion(
                shape=region_shape,
                node_id=identifier(
                    geometry.source_id,
                    "region",
                    index,
                ),
                node_type=self._region_type(region_shape),
                center=point(region_shape.CenterOfGravity, "region center"),
                bounding_box=bounding_box(region_shape),
                area_mm2=finite_float(
                    region_shape.Area,
                    "region area",
                ),
                volume_mm3=finite_float(
                    getattr(region_shape, "Volume", 0.0),
                    "region volume",
                ),
            )
            for index, region_shape in enumerate(raw_regions, start=1)
        )

    def connected_components(
        self,
        regions: tuple[MaterialRegion, ...],
    ) -> tuple[tuple[tuple[int, ...], ...], tuple[tuple[int, int], ...]]:
        """Group regions connected by identical shared boundary faces.

        Edge-only and vertex-only contact is not material continuity.  Both
        components and contact pairs remain in source topology order.
        """
        parents = list(range(len(regions)))
        contacts: list[tuple[int, int]] = []

        def find(index: int) -> int:
            while parents[index] != index:
                parents[index] = parents[parents[index]]
                index = parents[index]
            return index

        def union(first: int, second: int) -> None:
            first_root = find(first)
            second_root = find(second)
            if first_root != second_root:
                parents[second_root] = first_root

        for first in range(len(regions)):
            for second in range(first + 1, len(regions)):
                if self._share_face(
                    regions[first].shape,
                    regions[second].shape,
                ):
                    contacts.append((first, second))
                    union(first, second)

        grouped: dict[int, list[int]] = {}
        for index in range(len(regions)):
            grouped.setdefault(find(index), []).append(index)
        return (
            tuple(tuple(indices) for indices in grouped.values()),
            tuple(contacts),
        )

    def build(
        self,
        geometry: GeometrySnapshot,
        regions: tuple[MaterialRegion, ...],
        holes: tuple[DetectedHole, ...],
        cavities: tuple[DetectedCavity, ...],
        dead_ends: tuple[DeadEndRegion, ...],
        components: tuple[tuple[int, ...], ...],
        contact_pairs: tuple[tuple[int, int], ...],
    ) -> ConnectivityGraph:
        """Build immutable region nodes and direct-contact edges.

        Related topology identifiers annotate their owning node.  Every shared
        face produces one undirected relationship represented once.
        """
        related: list[list[str]] = [[] for _ in regions]
        for hole in holes:
            related[hole.owner_index].append(hole.feature.feature_id)
        for cavity in cavities:
            related[cavity.owner_index].append(cavity.feature.feature_id)
        blind_holes = tuple(
            hole for hole in holes if hole.terminal_point is not None
        )
        for dead_end, hole in zip(dead_ends, blind_holes):
            related[hole.owner_index].append(dead_end.region_id)

        nodes = tuple(
            ConnectivityNode(
                node_id=region.node_id,
                node_type=region.node_type,
                position=region.center,
                related_feature_ids=tuple(related[index]),
            )
            for index, region in enumerate(regions)
        )
        edges = tuple(
            ConnectivityEdge(
                edge_id=identifier(
                    geometry.source_id,
                    "connection",
                    index,
                ),
                start_node_id=regions[first].node_id,
                end_node_id=regions[second].node_id,
                length_mm=self._distance(
                    regions[first].center,
                    regions[second].center,
                ),
                minimum_clearance_mm=0.0,
            )
            for index, (first, second) in enumerate(
                contact_pairs,
                start=1,
            )
        )
        return ConnectivityGraph(
            nodes=nodes,
            edges=edges,
            connected_component_count=len(components),
        )

    @staticmethod
    def _distance(first: Point3D, second: Point3D) -> float:
        """Return Euclidean distance between region centers."""
        return math.sqrt(
            (second.x_mm - first.x_mm) ** 2
            + (second.y_mm - first.y_mm) ** 2
            + (second.z_mm - first.z_mm) ** 2
        )

    @staticmethod
    def _share_face(first: object, second: object) -> bool:
        """Return whether two regions reference a common face."""
        return any(
            same_shape(first_face, second_face)
            for first_face in getattr(first, "Faces", ())
            for second_face in getattr(second, "Faces", ())
        )

    @staticmethod
    def _region_type(shape: object) -> str:
        """Return a normalized descriptive region type."""
        shape_type = str(getattr(shape, "ShapeType", "region")).lower()
        return shape_type or "region"

# -*- coding: utf-8 -*-
"""Orchestration of read-only topology detectors."""

from __future__ import annotations

from ..Exceptions import TopologyAnalysisError
from ..Models import GeometrySnapshot, TopologyAnalysis
from .CavityDetector import CavityDetector
from .ConnectivityBuilder import ConnectivityBuilder
from .DeadEndDetector import DeadEndDetector
from .HoleDetector import HoleDetector
from .IslandDetector import IslandDetector

__all__ = ["TopologyAnalyzer"]


class TopologyAnalyzer:
    """Coordinate focused detectors and return immutable topology findings."""

    def analyze(
        self,
        geometry: GeometrySnapshot,
        shape: object,
    ) -> TopologyAnalysis:
        """Build one topology stage without retaining or changing the shape."""
        self._validate_shape(shape)

        connectivity_builder = ConnectivityBuilder()
        regions = connectivity_builder.material_regions(geometry, shape)
        holes = HoleDetector().detect(geometry, shape, regions)
        cavities = CavityDetector().detect(geometry, regions)
        dead_ends = DeadEndDetector().detect(geometry, holes)
        components, contacts = connectivity_builder.connected_components(
            regions
        )
        islands = IslandDetector().detect(geometry, regions, components)
        graph = connectivity_builder.build(
            geometry,
            regions,
            holes,
            cavities,
            dead_ends,
            components,
            contacts,
        )

        return TopologyAnalysis(
            holes=tuple(item.feature for item in holes),
            islands=islands,
            cavities=tuple(item.feature for item in cavities),
            dead_ends=dead_ends,
            connectivity_graph=graph,
        )

    @staticmethod
    def _validate_shape(shape: object) -> None:
        """Reject null or invalid resolved shapes without changing them."""
        is_null = getattr(shape, "isNull", None)
        if callable(is_null) and bool(is_null()):
            raise TopologyAnalysisError("Resolved source shape is null.")

        is_valid = getattr(shape, "isValid", None)
        if callable(is_valid) and not bool(is_valid()):
            raise TopologyAnalysisError("Resolved source shape is invalid.")

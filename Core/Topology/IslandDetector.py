# -*- coding: utf-8 -*-
"""Read-only detection of disconnected material islands."""

from __future__ import annotations

from ..Models import BoundingBox, GeometrySnapshot, IslandFeature, Point3D
from .ConnectivityBuilder import MaterialRegion
from ._Utilities import identifier

__all__ = ["IslandDetector"]


class IslandDetector:
    """Describe all disconnected components without selecting a main one."""

    def detect(
        self,
        geometry: GeometrySnapshot,
        regions: tuple[MaterialRegion, ...],
        components: tuple[tuple[int, ...], ...],
    ) -> tuple[IslandFeature, ...]:
        """Return every component as an island when more than one exists.

        Bounds, summed area, and volume-weighted center are descriptive only.
        Source component order determines identifiers.
        """
        if len(components) <= 1:
            return ()

        return tuple(
            IslandFeature(
                feature_id=identifier(
                    geometry.source_id,
                    "island",
                    feature_index,
                ),
                bounding_box=self._combined_bounds(component_regions),
                center=self._combined_center(component_regions),
                area_mm2=sum(
                    region.area_mm2 for region in component_regions
                ),
            )
            for feature_index, component in enumerate(components, start=1)
            for component_regions in (
                tuple(regions[index] for index in component),
            )
        )

    @staticmethod
    def _combined_bounds(
        regions: tuple[MaterialRegion, ...],
    ) -> BoundingBox:
        """Return union bounds for one non-empty component."""
        return BoundingBox(
            minimum=Point3D(
                min(region.bounding_box.minimum.x_mm for region in regions),
                min(region.bounding_box.minimum.y_mm for region in regions),
                min(region.bounding_box.minimum.z_mm for region in regions),
            ),
            maximum=Point3D(
                max(region.bounding_box.maximum.x_mm for region in regions),
                max(region.bounding_box.maximum.y_mm for region in regions),
                max(region.bounding_box.maximum.z_mm for region in regions),
            ),
        )

    @staticmethod
    def _combined_center(
        regions: tuple[MaterialRegion, ...],
    ) -> Point3D:
        """Return volume-weighted center, or arithmetic mean for shells."""
        weights = tuple(abs(region.volume_mm3) for region in regions)
        total_weight = sum(weights)
        if total_weight <= 0.0:
            weights = tuple(1.0 for _ in regions)
            total_weight = float(len(regions))
        return Point3D(
            x_mm=sum(
                region.center.x_mm * weight
                for region, weight in zip(regions, weights)
            )
            / total_weight,
            y_mm=sum(
                region.center.y_mm * weight
                for region, weight in zip(regions, weights)
            )
            / total_weight,
            z_mm=sum(
                region.center.z_mm * weight
                for region, weight in zip(regions, weights)
            )
            / total_weight,
        )

# -*- coding: utf-8 -*-
"""V4.74A connectivity diagnosis for explicit XY ownership regions.

This module is deliberately read-only.  It describes the exact solids returned
by an ownership ``common()`` and maps secondary material to the closest local
seam section.  Route mutation remains owned by ``SinuousSeamPathFinder``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

__all__ = [
    "ComponentConnectivityObservation",
    "RegionConnectivityDiagnosis",
    "diagnose_region_connectivity",
]


@dataclass(frozen=True, slots=True)
class ComponentConnectivityObservation:
    """Scalar evidence for one physically disconnected ownership component."""

    rank: int
    volume_mm3: float
    bounds_mm: tuple[float, float, float, float, float, float]
    centroid_mm: tuple[float, float, float]
    nearest_seam: str
    nearest_segment_index: int
    nearest_segment_id: str
    nearest_detour_id: str | None
    seam_distance_mm: float
    opening_distance_mm: float


@dataclass(frozen=True, slots=True)
class RegionConnectivityDiagnosis:
    """Exact disconnected-region evidence passed to the bounded repair loop."""

    region_index: int
    components: tuple[ComponentConnectivityObservation, ...]
    repair_attempts: int = 0
    rejection_reason: str = "no local connected alternative was accepted"

    @property
    def secondary(self) -> ComponentConnectivityObservation:
        """Return the largest component other than the main body."""
        return self.components[1]

    def with_failure(self, attempts: int, reason: str):
        """Return the same immutable evidence with terminal search details."""
        return replace(
            self,
            repair_attempts=int(attempts),
            rejection_reason=str(reason),
        )

    def failure_message(self) -> str:
        """Render the detailed V4.74A user-facing failure report."""
        secondary = self.secondary
        detour = secondary.nearest_detour_id or secondary.nearest_segment_id
        component_lines = []
        for component in self.components:
            component_lines.append(
                f"Component {component.rank}: volume {component.volume_mm3:.6f} "
                f"mm^3; bounds {component.bounds_mm}; centroid "
                f"{component.centroid_mm}; nearest seam "
                f"{component.nearest_seam}/{component.nearest_segment_id}; "
                f"nearest detour "
                f"{component.nearest_detour_id or 'none'}; opening distance "
                f"{component.opening_distance_mm:.6f} mm"
            )
        return (
            f"Region_{self.region_index} disconnected\n"
            f"Components: {len(self.components)}\n"
            + "\n".join(component_lines)
            + "\n"
            f"Secondary volume: {secondary.volume_mm3:.6f} mm^3\n"
            f"Centroid: ({secondary.centroid_mm[0]:.6f}, "
            f"{secondary.centroid_mm[1]:.6f}, {secondary.centroid_mm[2]:.6f}) mm\n"
            f"Nearest seam: {secondary.nearest_seam}\n"
            f"Nearest detour: {detour}\n"
            f"Repair attempts: {self.repair_attempts}\n"
            "Reason no connected alternative was accepted: "
            f"{self.rejection_reason}"
        )


def diagnose_region_connectivity(region_index, solids, seam_plan):
    """Describe disconnected solids and map each to the nearest seam section."""
    ordered = tuple(sorted(solids, key=lambda item: float(item.Volume), reverse=True))
    if len(ordered) < 2:
        raise ValueError("Connectivity diagnosis requires multiple solids.")
    features = {feature.feature_id: feature for feature in seam_plan.features}
    observations = []
    for rank, solid in enumerate(ordered, start=1):
        center = solid.CenterOfMass
        centroid = (float(center.x), float(center.y), float(center.z))
        bounds = solid.BoundBox
        bounds_mm = (
            float(bounds.XMin), float(bounds.YMin), float(bounds.ZMin),
            float(bounds.XMax), float(bounds.YMax), float(bounds.ZMax),
        )
        seam, segment_index, seam_distance = _nearest_seam_segment(
            centroid[:2], seam_plan
        )
        detour_id = _nearest_detour(centroid[:2], seam, features)
        opening_distance = min(
            (_closed_polyline_distance(centroid[:2], feature.points)
             for feature in seam_plan.features),
            default=math.inf,
        )
        prefix = "VSEG" if seam.axis == "vertical" else "HSEG"
        observations.append(ComponentConnectivityObservation(
            rank=rank,
            volume_mm3=float(solid.Volume),
            bounds_mm=bounds_mm,
            centroid_mm=centroid,
            nearest_seam=seam.axis,
            nearest_segment_index=segment_index,
            nearest_segment_id=f"{prefix}_{segment_index + 1:03d}",
            nearest_detour_id=detour_id,
            seam_distance_mm=seam_distance,
            opening_distance_mm=opening_distance,
        ))
    return RegionConnectivityDiagnosis(int(region_index), tuple(observations))


def _nearest_seam_segment(point, seam_plan):
    ranked = []
    for path in (seam_plan.vertical, seam_plan.horizontal):
        for index, (first, second) in enumerate(zip(path.points, path.points[1:])):
            distance = _point_segment_distance(
                point, (first.x_mm, first.y_mm), (second.x_mm, second.y_mm)
            )
            ranked.append((distance, path.axis, index, path))
    distance, _axis, index, path = min(ranked)
    return path, index, distance


def _nearest_detour(point, path, features):
    ranked = []
    for detour_id, feature_id, level in zip(
        path.detour_ids, path.detour_feature_ids, path.detour_levels
    ):
        feature = features.get(feature_id)
        if feature is not None and level > 0:
            ranked.append((_closed_polyline_distance(point, feature.points), detour_id))
    return min(ranked)[1] if ranked else None


def _point_segment_distance(point, first, second):
    dx, dy = second[0] - first[0], second[1] - first[1]
    denominator = dx * dx + dy * dy
    if denominator <= 1.0e-18:
        return math.hypot(point[0] - first[0], point[1] - first[1])
    ratio = max(0.0, min(1.0, (
        (point[0] - first[0]) * dx + (point[1] - first[1]) * dy
    ) / denominator))
    return math.hypot(
        point[0] - (first[0] + ratio * dx),
        point[1] - (first[1] + ratio * dy),
    )


def _closed_polyline_distance(point, points):
    values = tuple((float(item.x_mm), float(item.y_mm)) for item in points)
    if len(values) < 2:
        return math.inf
    return min(
        _point_segment_distance(point, first, second)
        for first, second in zip(values, values[1:] + values[:1])
    )

# -*- coding: utf-8 -*-
"""V4.74A connectivity diagnosis for explicit XY ownership regions.

This module is deliberately read-only.  It describes the exact solids returned
by an ownership ``common()`` and maps secondary material to the closest local
seam section.  Route mutation remains owned by ``SinuousSeamPathFinder``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .Settings import Settings

__all__ = [
    "ComponentConnectivityObservation",
    "RegionConnectivityDiagnosis",
    "classify_region_components",
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
    footprint_mm2: float
    thickness_mm: float
    volume_ratio: float
    touches_panel_exterior: bool
    spans_substantial_thickness: bool
    classification: str
    volume_ok: bool = False
    volume_ratio_ok: bool = False
    thickness_ok: bool = False
    footprint_ok: bool = False
    opening_proximity_ok: bool = False
    silhouette_risk: bool = False
    full_thickness: bool = False

    @property
    def is_structural(self) -> bool:
        """Return whether this component must remain printable material."""
        return self.classification == "STRUCTURAL"


@dataclass(frozen=True, slots=True)
class RegionConnectivityDiagnosis:
    """Exact disconnected-region evidence passed to the bounded repair loop."""

    region_index: int
    components: tuple[ComponentConnectivityObservation, ...]
    repair_attempts: int = 0
    rejection_reason: str = "no local connected alternative was accepted"

    @property
    def structural_components(self):
        """Return components which still require physical connectivity."""
        return tuple(item for item in self.components if item.is_structural)

    @property
    def ignored_slivers(self):
        """Return independently confirmed non-structural fragments."""
        return tuple(item for item in self.components if not item.is_structural)

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
                f"{component.opening_distance_mm:.6f} mm; footprint "
                f"{component.footprint_mm2:.6f} mm^2; thickness "
                f"{component.thickness_mm:.6f} mm; volume ratio "
                f"{component.volume_ratio:.8f}; volume_ok "
                f"{component.volume_ok}; ratio_ok "
                f"{component.volume_ratio_ok}; thickness_ok "
                f"{component.thickness_ok}; footprint_ok "
                f"{component.footprint_ok}; original exterior contact "
                f"{component.touches_panel_exterior}; silhouette risk "
                f"{component.silhouette_risk}; full thickness "
                f"{component.full_thickness}; classification "
                f"{component.classification}"
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


def diagnose_region_connectivity(
    region_index,
    solids,
    seam_plan,
    panel_bounds=None,
    panel_thickness_mm=None,
    original_exterior=None,
):
    """Describe disconnected solids and map each to the nearest seam section."""
    ordered = tuple(sorted(solids, key=lambda item: float(item.Volume), reverse=True))
    if len(ordered) < 2:
        raise ValueError("Connectivity diagnosis requires multiple solids.")
    features = {feature.feature_id: feature for feature in seam_plan.features}
    observations = []
    main_volume = float(ordered[0].Volume)
    if panel_bounds is None:
        panel_bounds = _combined_bounds(ordered)
    if panel_thickness_mm is None:
        panel_thickness_mm = panel_bounds[5] - panel_bounds[2]
    for rank, solid in enumerate(ordered, start=1):
        center = solid.CenterOfMass
        centroid = (float(center.x), float(center.y), float(center.z))
        bounds = solid.BoundBox
        bounds_mm = (
            float(bounds.XMin), float(bounds.YMin), float(bounds.ZMin),
            float(bounds.XMax), float(bounds.YMax), float(bounds.ZMax),
        )
        footprint = max(0.0, bounds_mm[3] - bounds_mm[0]) * max(
            0.0, bounds_mm[4] - bounds_mm[1]
        )
        thickness = max(0.0, bounds_mm[5] - bounds_mm[2])
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
            footprint_mm2=footprint,
            thickness_mm=thickness,
            volume_ratio=float(solid.Volume) / main_volume,
            touches_panel_exterior=_touches_original_exterior(
                solid, bounds_mm, panel_bounds, original_exterior
            ),
            spans_substantial_thickness=(
                thickness / max(panel_thickness_mm, 1.0e-12)
                > Settings.Split.MAX_SLIVER_THICKNESS_RATIO
            ),
            classification="STRUCTURAL",
        ))
    return classify_region_components(
        RegionConnectivityDiagnosis(int(region_index), tuple(observations)),
        panel_thickness_mm,
    )


def classify_region_components(diagnosis, panel_thickness_mm):
    """Classify secondary solids using combined conservative evidence.

    A fragment is ignored only when it is small in absolute and relative
    volume, shallow, small in XY, and does not touch the original panel's
    outer silhouette. Seam, artistic-opening, and region-tool proximity are
    diagnostic context only. The main component is always structural.
    """
    classified = []
    for component in diagnosis.components:
        thickness_ratio = component.thickness_mm / max(
            float(panel_thickness_mm), 1.0e-12
        )
        volume_ok = (
            component.volume_mm3 <= Settings.Split.MAX_SLIVER_VOLUME_MM3
        )
        ratio_ok = (
            component.volume_ratio <= Settings.Split.MAX_SLIVER_VOLUME_RATIO
        )
        thickness_ok = (
            thickness_ratio <= Settings.Split.MAX_SLIVER_THICKNESS_RATIO
        )
        footprint_ok = (
            component.footprint_mm2 <= Settings.Split.MAX_SLIVER_FOOTPRINT_MM2
        )
        opening_proximity_ok = (
            component.opening_distance_mm
            <= Settings.Split.MAX_SLIVER_BOUNDARY_DISTANCE_MM
        )
        full_thickness = thickness_ratio >= 0.95
        silhouette_risk = component.touches_panel_exterior
        is_sliver = (
            component.rank > 1
            and volume_ok
            and ratio_ok
            and thickness_ok
            and footprint_ok
            and not silhouette_risk
        )
        classified.append(replace(
            component,
            spans_substantial_thickness=(
                thickness_ratio > Settings.Split.MAX_SLIVER_THICKNESS_RATIO
            ),
            classification=(
                "NON_STRUCTURAL_SLIVER" if is_sliver else "STRUCTURAL"
            ),
            volume_ok=volume_ok,
            volume_ratio_ok=ratio_ok,
            thickness_ok=thickness_ok,
            footprint_ok=footprint_ok,
            opening_proximity_ok=opening_proximity_ok,
            silhouette_risk=silhouette_risk,
            full_thickness=full_thickness,
        ))
    return replace(diagnosis, components=tuple(classified))


def _combined_bounds(solids):
    return (
        min(float(item.BoundBox.XMin) for item in solids),
        min(float(item.BoundBox.YMin) for item in solids),
        min(float(item.BoundBox.ZMin) for item in solids),
        max(float(item.BoundBox.XMax) for item in solids),
        max(float(item.BoundBox.YMax) for item in solids),
        max(float(item.BoundBox.ZMax) for item in solids),
    )


def _touches_original_exterior(solid, bounds, panel_bounds, exterior_shape):
    """Check only the original panel's outer XY silhouette.

    The real split pipeline supplies a surface extruded from the original top
    face's ``OuterWire``. Hole wires, seams, and region tools are absent from
    that shape. Bounds are a conservative fallback for isolated classifier
    callers which do not have source topology.
    """
    tolerance = Settings.Split.PANEL_EXTERIOR_TOLERANCE_MM
    if exterior_shape is not None:
        try:
            distance, _points, _info = solid.distToShape(exterior_shape)
            return float(distance) <= tolerance
        except Exception:
            pass
    return any(
        abs(value - exterior) <= tolerance
        for value, exterior in (
            (bounds[0], panel_bounds[0]),
            (bounds[1], panel_bounds[1]),
            (bounds[3], panel_bounds[3]),
            (bounds[4], panel_bounds[4]),
        )
    )


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

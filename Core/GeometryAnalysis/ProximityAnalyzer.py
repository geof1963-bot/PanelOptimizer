# -*- coding: utf-8 -*-
"""Exact B-rep proximity observations between topology features."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..Models import (
    CavityFeature,
    ClearanceObservation,
    FeatureProximityObservation,
    GeometrySnapshot,
    HoleFeature,
    Point3D,
    TopologyAnalysis,
)
from ._Utilities import (
    LINEAR_COMPARISON_TOLERANCE_MM,
    distance,
    same_shape,
    to_point,
)

__all__ = ["ProximityAnalyzer"]


@dataclass(frozen=True, slots=True)
class _ResolvedFeature:
    """Internal association of an immutable feature with transient B-rep."""

    feature_id: str
    owner_index: int
    shape: object


@dataclass(frozen=True, slots=True)
class _ProximityMeasurement:
    """Internal exact feature-pair measurement before ID assignment."""

    first_feature_id: str
    second_feature_id: str
    first_point: Point3D
    second_point: Point3D
    distance_mm: float


class ProximityAnalyzer:
    """Measure conservative exact proximity between topology features."""

    def analyze(
        self,
        geometry: GeometrySnapshot,
        topology: TopologyAnalysis,
        shape: object,
        clearances: tuple[ClearanceObservation, ...],
    ) -> tuple[FeatureProximityObservation, ...]:
        """Return exact hole-hole, hole-cavity, and cavity-cavity proximity.

        Hole pairs already measured by clearance reuse those exact endpoints
        and distances; this preserves the broader semantic feature relation
        without a second potentially conflicting calculation.  Hole-cavity
        and cavity-cavity distances use OpenCASCADE ``distToShape`` between
        exact transient feature B-reps resolved from topology source order.

        Only pairs owned by the same material region are considered.  Contact,
        intersection, missing B-rep mappings, open shells, and non-positive
        distances are omitted because the contract does not define contact
        semantics.
        """
        owners = self._feature_owner_indices(topology)
        measurements: dict[tuple[str, str], _ProximityMeasurement] = {}

        for clearance in clearances:
            measurement = self._from_hole_clearance(clearance, owners)
            if measurement is not None:
                measurements[self._pair_key(measurement)] = measurement

        holes = self._resolve_holes(topology.holes, owners)
        cavities = self._resolve_cavities(topology.cavities, owners, shape)
        for hole in holes:
            for cavity in cavities:
                measurement = self._measure_pair(hole, cavity)
                if measurement is not None:
                    measurements[self._pair_key(measurement)] = measurement

        for first_index, first in enumerate(cavities):
            for second in cavities[first_index + 1:]:
                measurement = self._measure_pair(first, second)
                if measurement is not None:
                    measurements[self._pair_key(measurement)] = measurement

        ordered = tuple(measurements[key] for key in sorted(measurements))
        return tuple(
            FeatureProximityObservation(
                observation_id=(
                    f"{geometry.source_id}:geometry:proximity:{index:04d}"
                ),
                first_feature_id=item.first_feature_id,
                second_feature_id=item.second_feature_id,
                first_point=item.first_point,
                second_point=item.second_point,
                distance_mm=item.distance_mm,
            )
            for index, item in enumerate(ordered, start=1)
        )

    @staticmethod
    def _from_hole_clearance(
        clearance: ClearanceObservation,
        owners: dict[str, int],
    ) -> _ProximityMeasurement | None:
        """Reuse exact clearance evidence for one same-region hole pair."""
        if (
            len(clearance.related_feature_ids) != 2
            or clearance.source_element_ids
            or clearance.clearance_mm <= LINEAR_COMPARISON_TOLERANCE_MM
            or not math.isclose(
                distance(
                    clearance.first_boundary_point,
                    clearance.second_boundary_point,
                ),
                clearance.clearance_mm,
                rel_tol=0.0,
                abs_tol=LINEAR_COMPARISON_TOLERANCE_MM,
            )
        ):
            return None
        first_id, second_id = clearance.related_feature_ids
        first_owner = owners.get(first_id)
        second_owner = owners.get(second_id)
        if (
            first_owner is None
            or second_owner is None
            or first_owner != second_owner
        ):
            return None
        return ProximityAnalyzer._canonical_measurement(
            first_id,
            second_id,
            clearance.first_boundary_point,
            clearance.second_boundary_point,
            clearance.clearance_mm,
        )

    @staticmethod
    def _resolve_holes(
        holes: tuple[HoleFeature, ...],
        owners: dict[str, int],
    ) -> tuple[_ResolvedFeature, ...]:
        """Build exact transient cylinders from immutable hole dimensions."""
        try:
            import Part
            from FreeCAD import Vector
        except ImportError:
            return ()

        resolved: list[_ResolvedFeature] = []
        for hole in sorted(holes, key=lambda item: item.feature_id):
            owner_index = owners.get(hole.feature_id)
            if owner_index is None:
                continue
            half_depth = hole.depth_mm / 2.0
            base = Point3D(
                hole.center.x_mm - hole.axis.x * half_depth,
                hole.center.y_mm - hole.axis.y * half_depth,
                hole.center.z_mm - hole.axis.z * half_depth,
            )
            base_vector = Vector(base.x_mm, base.y_mm, base.z_mm)
            axis_vector = Vector(hole.axis.x, hole.axis.y, hole.axis.z)
            try:
                cylinder = Part.makeCylinder(
                    hole.diameter_mm / 2.0,
                    hole.depth_mm,
                    base_vector,
                    axis_vector,
                )
            except (RuntimeError, TypeError, ValueError):
                continue
            resolved.append(
                _ResolvedFeature(
                    feature_id=hole.feature_id,
                    owner_index=owner_index,
                    shape=cylinder,
                )
            )
        return tuple(resolved)

    @staticmethod
    def _resolve_cavities(
        cavities: tuple[CavityFeature, ...],
        owners: dict[str, int],
        shape: object,
    ) -> tuple[_ResolvedFeature, ...]:
        """Map cavity IDs to closed inner shells in detector source order."""
        source_shells: list[tuple[int, object]] = []
        for owner_index, solid in enumerate(getattr(shape, "Solids", ())):
            outer_shell = getattr(solid, "OuterShell", None)
            for shell_index, shell in enumerate(getattr(solid, "Shells", ())):
                is_outer = (
                    same_shape(shell, outer_shell)
                    if outer_shell is not None
                    else shell_index == 0
                )
                if is_outer:
                    continue
                is_closed = getattr(shell, "isClosed", None)
                if callable(is_closed) and not bool(is_closed()):
                    continue
                source_shells.append((owner_index, shell))

        resolved: list[_ResolvedFeature] = []
        for cavity, (owner_index, shell) in zip(cavities, source_shells):
            if owners.get(cavity.feature_id) != owner_index:
                continue
            resolved.append(
                _ResolvedFeature(cavity.feature_id, owner_index, shell)
            )
        return tuple(resolved)

    @staticmethod
    def _measure_pair(
        first: _ResolvedFeature,
        second: _ResolvedFeature,
    ) -> _ProximityMeasurement | None:
        """Return the canonical positive exact B-rep distance for one pair."""
        if first.owner_index != second.owner_index:
            return None
        try:
            result = first.shape.distToShape(second.shape)
            measured_distance = float(result[0])
            point_pairs = tuple(result[1])
        except (AttributeError, IndexError, RuntimeError, TypeError, ValueError):
            return None
        if (
            not math.isfinite(measured_distance)
            or measured_distance <= LINEAR_COMPARISON_TOLERANCE_MM
            or not point_pairs
        ):
            return None

        points = tuple(
            sorted(
                (
                    (to_point(pair[0]), to_point(pair[1]))
                    for pair in point_pairs
                ),
                key=lambda pair: (
                    pair[0].x_mm,
                    pair[0].y_mm,
                    pair[0].z_mm,
                    pair[1].x_mm,
                    pair[1].y_mm,
                    pair[1].z_mm,
                ),
            )
        )
        return ProximityAnalyzer._canonical_measurement(
            first.feature_id,
            second.feature_id,
            points[0][0],
            points[0][1],
            measured_distance,
        )

    @staticmethod
    def _canonical_measurement(
        first_id: str,
        second_id: str,
        first_point: Point3D,
        second_point: Point3D,
        measured_distance: float,
    ) -> _ProximityMeasurement:
        """Order one feature pair and its corresponding points by stable ID."""
        if first_id <= second_id:
            return _ProximityMeasurement(
                first_id,
                second_id,
                first_point,
                second_point,
                measured_distance,
            )
        return _ProximityMeasurement(
            second_id,
            first_id,
            second_point,
            first_point,
            measured_distance,
        )

    @staticmethod
    def _pair_key(measurement: _ProximityMeasurement) -> tuple[str, str]:
        """Return the already-canonical unique feature-pair key."""
        return measurement.first_feature_id, measurement.second_feature_id

    @staticmethod
    def _feature_owner_indices(
        topology: TopologyAnalysis,
    ) -> dict[str, int]:
        """Map topology feature IDs to deterministic material-region indices."""
        graph = topology.connectivity_graph
        if graph is None:
            return {}
        owners: dict[str, int] = {}
        for owner_index, node in enumerate(graph.nodes):
            for feature_id in node.related_feature_ids:
                owners[feature_id] = owner_index
        return owners

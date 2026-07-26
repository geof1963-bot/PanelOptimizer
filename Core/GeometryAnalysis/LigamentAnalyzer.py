# -*- coding: utf-8 -*-
"""Clearance-backed observations of exact continuous-material ligaments."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..Models import (
    ClearanceObservation,
    GeometrySnapshot,
    HoleFeature,
    MaterialLigamentObservation,
    TopologyAnalysis,
)
from ._Utilities import (
    DIRECTION_COMPARISON_TOLERANCE,
    LINEAR_COMPARISON_TOLERANCE_MM,
    distance,
)

__all__ = ["LigamentAnalyzer"]


@dataclass(frozen=True, slots=True)
class _LigamentCandidate:
    """One clearance-derived candidate keyed by its physical boundaries."""

    physical_key: tuple[str, ...]
    clearance: ClearanceObservation


class LigamentAnalyzer:
    """Translate proven material clearances into ligament observations."""

    def analyze(
        self,
        geometry: GeometrySnapshot,
        topology: TopologyAnalysis,
        clearances: tuple[ClearanceObservation, ...],
    ) -> tuple[MaterialLigamentObservation, ...]:
        """Return canonical ligaments without remeasuring source geometry.

        Only clearance patterns produced by the implemented clearance stage
        are accepted: hole-to-hole and hole-to-exterior.  Those clearances
        already prove that their exact endpoint segment is continuous material
        inside one material region.  Endpoint distance is checked again to
        protect this semantic boundary, but no B-rep distance is recomputed.

        Coaxial hole segments whose axial intervals touch are grouped as one
        physical opening solely for duplicate suppression.  If multiple
        clearances describe the same physical boundary pair, the smallest
        exact transverse segment is retained, with clearance ID as a stable
        tie-breaker.  Failure to match a supported evidence pattern causes
        conservative omission.
        """
        hole_groups = self._hole_group_ids(topology.holes)
        candidates: list[_LigamentCandidate] = []
        for clearance in clearances:
            if not math.isclose(
                distance(
                    clearance.first_boundary_point,
                    clearance.second_boundary_point,
                ),
                clearance.clearance_mm,
                rel_tol=0.0,
                abs_tol=LINEAR_COMPARISON_TOLERANCE_MM,
            ):
                continue

            physical_key = self._physical_key(clearance, hole_groups)
            if physical_key is None:
                continue
            candidates.append(
                _LigamentCandidate(
                    physical_key=physical_key,
                    clearance=clearance,
                )
            )

        selected: dict[tuple[str, ...], _LigamentCandidate] = {}
        for candidate in candidates:
            previous = selected.get(candidate.physical_key)
            if previous is None or self._selection_key(candidate) < (
                self._selection_key(previous)
            ):
                selected[candidate.physical_key] = candidate

        ordered = tuple(selected[key] for key in sorted(selected))
        return tuple(
            self._observation(geometry.source_id, index, item.clearance)
            for index, item in enumerate(ordered, start=1)
        )

    @staticmethod
    def _selection_key(candidate: _LigamentCandidate) -> tuple[float, str]:
        """Return deterministic minimum-width and evidence-ID ordering."""
        return (
            candidate.clearance.clearance_mm,
            candidate.clearance.observation_id,
        )

    @staticmethod
    def _physical_key(
        clearance: ClearanceObservation,
        hole_groups: dict[str, str],
    ) -> tuple[str, ...] | None:
        """Return a canonical physical-boundary key for supported evidence."""
        related = clearance.related_feature_ids
        source = clearance.source_element_ids
        if len(related) == 2 and not source:
            first_group = hole_groups.get(related[0])
            second_group = hole_groups.get(related[1])
            if (
                first_group is None
                or second_group is None
                or first_group == second_group
            ):
                return None
            first_group, second_group = sorted((first_group, second_group))
            return "hole-hole", first_group, second_group
        if len(related) == 1 and len(source) == 1:
            group = hole_groups.get(related[0])
            if group is None:
                return None
            return "hole-exterior", group, source[0]
        return None

    @staticmethod
    def _observation(
        source_id: str,
        index: int,
        clearance: ClearanceObservation,
    ) -> MaterialLigamentObservation:
        """Create one immutable ligament from its exact clearance evidence."""
        if len(clearance.related_feature_ids) == 2:
            first_boundary_id, second_boundary_id = (
                clearance.related_feature_ids
            )
        else:
            first_boundary_id = clearance.related_feature_ids[0]
            second_boundary_id = clearance.source_element_ids[0]
        return MaterialLigamentObservation(
            observation_id=(
                f"{source_id}:geometry:ligament:{index:04d}"
            ),
            start=clearance.first_boundary_point,
            end=clearance.second_boundary_point,
            width_mm=clearance.clearance_mm,
            first_boundary_id=first_boundary_id,
            second_boundary_id=second_boundary_id,
            related_feature_ids=clearance.related_feature_ids,
            source_element_ids=clearance.source_element_ids,
        )

    def _hole_group_ids(
        self,
        holes: tuple[HoleFeature, ...],
    ) -> dict[str, str]:
        """Map touching coaxial segments to one canonical opening ID."""
        ordered = tuple(sorted(holes, key=lambda hole: hole.feature_id))
        parents = list(range(len(ordered)))

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

        for first_index, first in enumerate(ordered):
            for second_index in range(first_index + 1, len(ordered)):
                second = ordered[second_index]
                if self._segments_are_connected_coaxial(first, second):
                    union(first_index, second_index)

        groups: dict[int, list[str]] = {}
        for index, hole in enumerate(ordered):
            groups.setdefault(find(index), []).append(hole.feature_id)
        canonical = {
            root: min(feature_ids)
            for root, feature_ids in groups.items()
        }
        return {
            hole.feature_id: canonical[find(index)]
            for index, hole in enumerate(ordered)
        }

    @staticmethod
    def _segments_are_connected_coaxial(
        first: HoleFeature,
        second: HoleFeature,
    ) -> bool:
        """Return whether two hole segments form one coaxial opening."""
        cross_x = first.axis.y * second.axis.z - first.axis.z * second.axis.y
        cross_y = first.axis.z * second.axis.x - first.axis.x * second.axis.z
        cross_z = first.axis.x * second.axis.y - first.axis.y * second.axis.x
        if math.sqrt(cross_x**2 + cross_y**2 + cross_z**2) > (
            DIRECTION_COMPARISON_TOLERANCE
        ):
            return False

        delta_x = second.center.x_mm - first.center.x_mm
        delta_y = second.center.y_mm - first.center.y_mm
        delta_z = second.center.z_mm - first.center.z_mm
        offset_cross_x = delta_y * first.axis.z - delta_z * first.axis.y
        offset_cross_y = delta_z * first.axis.x - delta_x * first.axis.z
        offset_cross_z = delta_x * first.axis.y - delta_y * first.axis.x
        if math.sqrt(
            offset_cross_x**2 + offset_cross_y**2 + offset_cross_z**2
        ) > LINEAR_COMPARISON_TOLERANCE_MM:
            return False

        axial_delta = abs(
            delta_x * first.axis.x
            + delta_y * first.axis.y
            + delta_z * first.axis.z
        )
        endpoint_separation = (
            axial_delta - (first.depth_mm + second.depth_mm) / 2.0
        )
        return endpoint_separation <= LINEAR_COMPARISON_TOLERANCE_MM

# -*- coding: utf-8 -*-
"""Robust V4.60A full-branch dowel planning and transient drilling.

The planner consumes the already accepted V4.30 four-solid result.  It splits
the two immutable seam polylines at their sole intersection, samples each of
the four branches by arc length, and validates a horizontal cylindrical hole
against the four transient solids.  Only the two expected mating solids may
lose material.  No FreeCAD object is stored in the immutable plan records.
"""

from __future__ import annotations

import math
import time
from bisect import bisect_left
from itertools import combinations
from dataclasses import dataclass, replace

from .Exceptions import DowelPlanningError
from .MacroSplitCore import MacroSplitResult
from .Settings import Settings
from .ProductionDiagnostics import log_event, operation
from .SplittingUtilities import volume_tolerance_mm3

__all__ = [
    "DowelApplication",
    "DowelParameters",
    "DowelPlan",
    "DowelPlanner",
    "DowelPosition",
    "DowelRejection",
    "SeamBranchPlan",
]

_COORDINATE_TOLERANCE_MM = 1.0e-7
_TARGET_FRACTIONS = (0.20, 0.50, 0.80)
_FALLBACK_FRACTIONS = (0.30, 0.70)
_RELOCATION_INCREMENT_MM = 5.0


@dataclass(frozen=True, slots=True)
class DowelParameters:
    """Validated V4.60A configuration; scalar geometry is in millimetres."""

    dowel_diameter_mm: float = Settings.Joinery.DOWEL_DIAMETER_MM
    hole_diameter_mm: float = Settings.Joinery.DOWEL_HOLE_DIAMETER_MM
    length_mm: float = Settings.Joinery.DOWEL_LENGTH_MM
    axis_height_mm: float = Settings.Joinery.DOWEL_AXIS_HEIGHT_MM
    edge_margin_mm: float = Settings.Joinery.DOWEL_EDGE_MARGIN_MM
    material_margin_mm: float = Settings.Joinery.DOWEL_MIN_MATERIAL_MARGIN_MM
    center_exclusion_mm: float = Settings.Joinery.DOWEL_CENTER_EXCLUSION_MM
    minimum_spacing_mm: float = Settings.Joinery.DOWEL_MIN_SPACING_MM
    maximum_unsupported_span_mm: float = Settings.Joinery.DOWEL_MAX_UNSUPPORTED_SPAN_MM
    target_per_branch: int = Settings.Joinery.DOWELS_TARGET_PER_BRANCH
    minimum_per_branch: int = Settings.Joinery.DOWELS_MIN_PER_BRANCH
    maximum_per_branch: int = Settings.Joinery.DOWELS_MAX_PER_BRANCH
    minimum_useful_depth_per_side_mm: float = (
        Settings.Joinery.DOWEL_MIN_USEFUL_DEPTH_PER_SIDE_MM
    )


@dataclass(frozen=True, slots=True)
class DowelPosition:
    """One accepted coaxial hole pair in model coordinates, in millimetres."""

    dowel_id: str
    seam_branch: str
    center_xyz_mm: tuple[float, float, float]
    tangent_xy: tuple[float, float]
    axis_xy: tuple[float, float]
    intended_part_names: tuple[str, str]
    hole_diameter_mm: float
    total_hole_length_mm: float
    status: str = "accepted"
    branch_distance_mm: float = 0.0
    target_fraction: float = 0.0
    useful_depth_part_a_mm: float = 0.0
    useful_depth_part_b_mm: float = 0.0
    bore_exits_artistic_opening: bool = False
    nearest_artistic_hole_clearance_mm: float = math.inf


@dataclass(frozen=True, slots=True)
class DowelRejection:
    """One rejected deterministic candidate and its concise geometry reason."""

    seam_branch: str
    target_fraction: float
    center_xyz_mm: tuple[float, float, float]
    reason: str
    branch_distance_mm: float = 0.0


@dataclass(frozen=True, slots=True)
class SeamBranchPlan:
    """Planning result for one of the four mating seam branches."""

    branch_id: str
    length_mm: float
    requested_count: int
    accepted_dowel_ids: tuple[str, ...]
    rejected_candidates: tuple[DowelRejection, ...]
    usable_interval_mm: tuple[float, float] = (0.0, 0.0)
    usable_length_mm: float = 0.0
    target_fractions: tuple[float, ...] = ()
    requested_target_fractions: tuple[float, ...] = ()
    accepted_distances_mm: tuple[float, ...] = ()
    spacing_mm: tuple[float, ...] = ()
    used_two_dowel_fallback: bool = False
    minimum_spacing_achievable: bool = True
    sampled_point_count: int = 0
    safe_candidate_count: int = 0
    rejected_geometry_counts: tuple[tuple[str, int], ...] = ()
    sampling_interval_mm: float = 5.0
    cheap_candidate_count: int = 0
    shortlisted_candidate_count: int = 0
    exact_validation_count: int = 0
    safe_interval_count: int = 0
    unsupported_spans_mm: tuple[float, ...] = ()
    largest_unsupported_span_mm: float = 0.0
    coverage_target_achieved: bool = False
    spacing_exception: bool = False
    degraded_two_dowel: bool = False


@dataclass(frozen=True, slots=True)
class DowelPlan:
    """Immutable scalar-only plan for all four mating branches."""

    dowels: tuple[DowelPosition, ...]
    branches: tuple[SeamBranchPlan, ...]


@dataclass(frozen=True, slots=True)
class DowelApplication:
    """Transient drilled macro result plus its immutable plan and metadata."""

    macro_result: MacroSplitResult
    plan: DowelPlan
    cutters: tuple[object, ...]
    removed_volume_mm3: float


@dataclass(frozen=True, slots=True)
class _Branch:
    branch_id: str
    points: tuple[tuple[float, float], ...]
    intended_indices: tuple[int, int]
    intended_names: tuple[str, str]


@dataclass(frozen=True, slots=True)
class _Candidate:
    distance_mm: float
    center_xyz_mm: tuple[float, float, float]
    tangent_xy: tuple[float, float]
    target_fraction: float
    target_distance_mm: float
    nearest_opening_clearance_mm: float = math.inf
    surrounding_material_mm: float = 0.0
    local_material_score: float = 1.0


class DowelPlanner:
    """Plan and subtract simple coaxial dowel holes from V4.30 parts only."""

    def __init__(self, parameters: DowelParameters = DowelParameters()) -> None:
        self._parameters = self._validate_parameters(parameters)
        self._validated_cutters = {}
        self._inside_cache = {}
        self._exact_candidate_cache = {}
        self._feature_polygon_cache = {}
        self._branch_frame_cache = {}
        self._active_intersection = None
        self._solid_bounds = ()
        self._solid_centers = ()

    def plan(self, macro_result: MacroSplitResult) -> DowelPlan:
        """Return a safe deterministic plan without modifying any input shape."""
        self._validated_cutters = {}
        self._inside_cache = {}
        self._exact_candidate_cache = {}
        self._feature_polygon_cache = {}
        self._branch_frame_cache = {}
        self._active_intersection = _seam_intersection(macro_result.seam_plan)
        solids, bounds = self._ordered_solids_and_bounds(macro_result)
        solid_bounds = []
        solid_centers = []
        for solid in solids:
            box = solid.BoundBox
            center = solid.CenterOfMass
            solid_bounds.append((
                float(box.XMin), float(box.XMax),
                float(box.YMin), float(box.YMax),
                float(box.ZMin), float(box.ZMax),
            ))
            solid_centers.append((float(center.x), float(center.y)))
        self._solid_bounds = tuple(solid_bounds)
        self._solid_centers = tuple(solid_centers)
        branches = self._branches(macro_result)
        z_value = bounds[4] + self._parameters.axis_height_mm
        radius = self._parameters.hole_diameter_mm / 2.0
        if z_value - radius < bounds[4] or z_value + radius > bounds[5]:
            raise DowelPlanningError(
                "Configured dowel hole does not fit inside panel thickness."
            )
        accepted = []
        branch_results = []
        occupied: list[tuple[float, float]] = []
        for branch in branches:
            branch_started = time.perf_counter()
            length = _polyline_length(branch.points)
            usable_interval = self._usable_interval(
                branch, bounds, self._active_intersection
            )
            usable_length = usable_interval[1] - usable_interval[0]
            requested_targets = _even_fractions(
                self._parameters.target_per_branch
            )
            pool_started = time.perf_counter()
            candidates, rejections, sampled_count, sampling_interval = (
                self._safe_candidate_pool(
                    usable_interval,
                    branch,
                    macro_result,
                    solids,
                    bounds,
                    z_value,
                    occupied,
                )
            )
            pool_seconds = time.perf_counter() - pool_started
            cheap_candidate_count = len(candidates)
            selection_started = time.perf_counter()
            shortlisted = self._candidate_shortlist(
                candidates, usable_interval, limit=32
            )
            (
                chosen_candidates,
                actual_targets,
                exact_results,
                exact_rejections,
            ) = self._validated_safe_subset(
                shortlisted,
                usable_interval,
                branch,
                macro_result,
                solids,
            )
            selection_seconds = time.perf_counter() - selection_started
            if (
                len(chosen_candidates) < self._parameters.target_per_branch
                and len(candidates) > len(shortlisted)
            ):
                recovery = self._full_branch_recovery_shortlist(
                    candidates, usable_interval, limit=32
                )
                recovery_by_distance = {
                    round(candidate.distance_mm, 9): candidate
                    for candidate in (
                        tuple(chosen_candidates) + tuple(recovery)
                    )
                }
                recovery = tuple(sorted(
                    recovery_by_distance.values(),
                    key=lambda candidate: candidate.distance_mm,
                ))
                recovered = self._validated_safe_subset(
                    recovery, usable_interval, branch, macro_result, solids
                )
                recovery_results = recovered[2]
                recovery_rejections = recovered[3]
                exact_results.update(recovery_results)
                exact_rejections = (
                    tuple(exact_rejections) + tuple(recovery_rejections)
                )
                if len(recovered[0]) > len(chosen_candidates):
                    chosen_candidates, actual_targets = recovered[:2]
            rejections = tuple(rejections) + tuple(exact_rejections)
            used_fallback = (
                self._parameters.target_per_branch >= 3
                and len(chosen_candidates) == 2
            )
            branch_dowels = []
            for candidate in sorted(
                chosen_candidates, key=lambda item: item.distance_mm
            ):
                center = candidate.center_xyz_mm
                tangent = candidate.tangent_xy
                axis = _canonical_normal(tangent, branch.branch_id)
                dowel_id = (
                    f"dowel:{branch.branch_id}:{len(branch_dowels) + 1:02d}"
                )
                exact_reason, cutter, useful_depths, opening_breakout = exact_results[
                    round(candidate.distance_mm, 9)
                ]
                if exact_reason is not None:
                    raise DowelPlanningError(
                        f"Selected candidate for {dowel_id} was not exact-safe."
                    )
                record = DowelPosition(
                    dowel_id=dowel_id,
                    seam_branch=branch.branch_id,
                    center_xyz_mm=center,
                    tangent_xy=tangent,
                    axis_xy=axis,
                    intended_part_names=branch.intended_names,
                    hole_diameter_mm=self._parameters.hole_diameter_mm,
                    total_hole_length_mm=self._parameters.length_mm,
                    branch_distance_mm=candidate.distance_mm,
                    target_fraction=candidate.target_fraction,
                    useful_depth_part_a_mm=useful_depths[0],
                    useful_depth_part_b_mm=useful_depths[1],
                    bore_exits_artistic_opening=opening_breakout,
                    nearest_artistic_hole_clearance_mm=(
                        candidate.nearest_opening_clearance_mm
                    ),
                )
                branch_dowels.append(record)
                accepted.append(record)
                occupied.append(center[:2])
                self._validated_cutters[
                    self._cutter_cache_key(center, axis)
                ] = cutter
            if len(branch_dowels) < 2:
                reasons = sorted({item.reason for item in rejections})
                raise DowelPlanningError(
                    f"Branch '{branch.branch_id}' has {len(candidates)} safe "
                    f"candidates and only {len(branch_dowels)} selected dowels; "
                    f"minimum is {self._parameters.minimum_per_branch}. "
                    f"Rejected reasons: {', '.join(reasons)}."
                )
            branch_results.append(
                SeamBranchPlan(
                    branch_id=branch.branch_id,
                    length_mm=length,
                    requested_count=self._parameters.target_per_branch,
                    accepted_dowel_ids=tuple(item.dowel_id for item in branch_dowels),
                    rejected_candidates=tuple(rejections),
                    usable_interval_mm=usable_interval,
                    usable_length_mm=usable_length,
                    target_fractions=tuple(actual_targets),
                    requested_target_fractions=tuple(requested_targets),
                    accepted_distances_mm=tuple(
                        item.branch_distance_mm for item in branch_dowels
                    ),
                    spacing_mm=_adjacent_center_spacings(branch_dowels),
                    used_two_dowel_fallback=used_fallback,
                    minimum_spacing_achievable=(
                        len(branch_dowels) >= 2
                        and min(_adjacent_center_spacings(branch_dowels), default=0.0)
                        >= self._parameters.minimum_spacing_mm
                        - _COORDINATE_TOLERANCE_MM
                    ),
                    sampled_point_count=sampled_count,
                    # Cheap filtering is conservative; subtract any false
                    # positives discovered while exact-checking the shortlist.
                    safe_candidate_count=cheap_candidate_count - sum(
                        reason is not None
                        for reason, _cutter, _depths, _breakout
                        in exact_results.values()
                    ),
                    rejected_geometry_counts=_rejection_counts(rejections),
                    sampling_interval_mm=sampling_interval,
                    cheap_candidate_count=cheap_candidate_count,
                    shortlisted_candidate_count=len(shortlisted),
                    exact_validation_count=len(exact_results),
                    safe_interval_count=_safe_interval_count(
                        candidates, sampling_interval
                    ),
                    unsupported_spans_mm=_unsupported_spans(
                        branch_dowels, usable_interval
                    ),
                    largest_unsupported_span_mm=max(
                        _unsupported_spans(branch_dowels, usable_interval),
                        default=usable_length,
                    ),
                    coverage_target_achieved=max(
                        _unsupported_spans(branch_dowels, usable_interval),
                        default=usable_length,
                    ) <= self._parameters.maximum_unsupported_span_mm
                    + _COORDINATE_TOLERANCE_MM,
                    spacing_exception=(
                        min(_adjacent_center_spacings(branch_dowels), default=math.inf)
                        < self._parameters.minimum_spacing_mm
                        - _COORDINATE_TOLERANCE_MM
                    ),
                    degraded_two_dowel=len(branch_dowels) == 2,
                )
            )
            log_event(
                "[6] Dowels",
                branch.branch_id,
                f"SUMMARY sampled={sampled_count} cheap={cheap_candidate_count} "
                f"exact={len(exact_results)} selected={len(branch_dowels)} "
                f"pool_seconds={pool_seconds:.6f} "
                f"selection_seconds={selection_seconds:.6f} "
                f"seconds={time.perf_counter() - branch_started:.6f} "
                f"positions={tuple(item.center_xyz_mm for item in branch_dowels)} "
                f"depths={tuple((item.useful_depth_part_a_mm, item.useful_depth_part_b_mm) for item in branch_dowels)}",
            )
        return DowelPlan(tuple(accepted), tuple(branch_results))

    def _candidate_shortlist(self, candidates, interval, limit):
        """Keep a small deterministic pool around the four target positions."""
        if len(candidates) <= limit:
            return tuple(candidates)
        start, end = interval
        quality_floor = (
            self._parameters.hole_diameter_mm / 2.0
            + self._parameters.material_margin_mm
        )
        selected = {}
        ideals = tuple(
            start + (end - start) * fraction
            for fraction in _even_fractions(self._parameters.target_per_branch)
        )
        per_target = max(1, limit // len(ideals))
        for ideal in ideals:
            ranked = sorted(
                candidates,
                key=lambda candidate: (
                    abs(candidate.distance_mm - ideal)
                    + 10.0 * max(
                        0.0,
                        quality_floor - candidate.nearest_opening_clearance_mm,
                    ),
                    -candidate.nearest_opening_clearance_mm,
                    candidate.distance_mm,
                ),
            )
            for candidate in ranked[:per_target]:
                selected[round(candidate.distance_mm, 9)] = candidate
        return tuple(sorted(
            selected.values(), key=lambda candidate: candidate.distance_mm
        ))[:limit]

    def _full_branch_recovery_shortlist(self, candidates, interval, limit):
        """Bound one underfilled recovery scan across the complete branch."""
        if len(candidates) <= limit:
            return tuple(candidates)
        start, end = interval
        bin_count = 8
        width = max((end - start) / bin_count, _COORDINATE_TOLERANCE_MM)
        buckets = [[] for _ in range(bin_count)]
        for candidate in candidates:
            index = min(
                bin_count - 1,
                max(0, int((candidate.distance_mm - start) / width)),
            )
            buckets[index].append(candidate)
        selected = []
        per_bin = max(1, limit // bin_count)
        for bucket in buckets:
            selected.extend(sorted(
                bucket,
                key=lambda candidate: (
                    -candidate.nearest_opening_clearance_mm,
                    -candidate.surrounding_material_mm,
                    candidate.distance_mm,
                ),
            )[:per_bin])
        return tuple(sorted(
            selected, key=lambda candidate: candidate.distance_mm
        ))[:limit]

    def _usable_interval(self, branch, bounds, intersection):
        """Measure the contiguous branch interval outside edge/center margins."""
        length = _polyline_length(branch.points)
        sample_count = max(1, int(math.ceil(length)))
        distances = tuple(length * index / sample_count for index in range(sample_count + 1))

        def eligible(distance):
            point, _ = self._branch_point_and_tangent(branch, distance)
            edge_clearance = min(
                point[0] - bounds[0], bounds[1] - point[0],
                point[1] - bounds[2], bounds[3] - point[1],
            )
            center_clearance = math.hypot(
                point[0] - intersection[0], point[1] - intersection[1]
            )
            return (
                edge_clearance >= self._parameters.edge_margin_mm
                - _COORDINATE_TOLERANCE_MM
                and center_clearance >= self._parameters.center_exclusion_mm
                - _COORDINATE_TOLERANCE_MM
            )

        usable = tuple(distance for distance in distances if eligible(distance))
        if len(usable) < 2:
            raise DowelPlanningError(
                f"Branch '{branch.branch_id}' has no usable dowel interval."
            )
        return float(min(usable)), float(max(usable))

    def _safe_candidate_pool(
        self,
        interval,
        branch,
        macro_result,
        solids,
        bounds,
        z_value,
        occupied,
    ):
        """Scan the complete interval using only conservative cheap checks."""
        start, end = interval
        sampled = list(_sample_distances(start, end, 5.0))
        candidates = []
        rejections = []

        def evaluate(distance):
            point, tangent = self._branch_point_and_tangent(branch, distance)
            center = (point[0], point[1], z_value)
            reason = self._cheap_candidate_reason(
                macro_result,
                solids,
                bounds,
                branch,
                center,
                tangent,
                occupied,
            )
            fraction = (
                (distance - start) / (end - start)
                if end - start > _COORDINATE_TOLERANCE_MM
                else 0.5
            )
            if reason is not None:
                rejections.append(
                    DowelRejection(
                        branch.branch_id,
                        fraction,
                        center,
                        reason,
                        branch_distance_mm=distance,
                    )
                )
                return
            axis = _canonical_normal(tangent, branch.branch_id)
            half = self._parameters.length_mm / 2.0
            first = (
                center[0] - axis[0] * half,
                center[1] - axis[1] * half,
            )
            second = (
                center[0] + axis[0] * half,
                center[1] + axis[1] * half,
            )
            opening_clearance = self._nearest_opening_clearance(
                first, second, macro_result.seam_plan.features
            )
            surrounding = min(
                center[0] - bounds[0], bounds[1] - center[0],
                center[1] - bounds[2], bounds[3] - center[1],
            )
            candidates.append(_Candidate(
                distance, center, tangent, fraction, distance,
                opening_clearance, surrounding,
            ))
        for distance in sampled:
            evaluate(distance)
        sampling_interval = 5.0
        if len(candidates) < self._parameters.target_per_branch:
            refined = tuple(
                distance
                for distance in _sample_distances(start, end, 2.5)
                if all(
                    abs(distance - prior) > _COORDINATE_TOLERANCE_MM
                    for prior in sampled
                )
            )
            sampled.extend(refined)
            for distance in refined:
                evaluate(distance)
            sampling_interval = 2.5
        return (
            tuple(sorted(candidates, key=lambda item: item.distance_mm)),
            tuple(rejections),
            len(sampled),
            sampling_interval,
        )

    def _branch_point_and_tangent(self, branch, distance):
        """Locate one arc-length frame in O(log n) on a cached polyline."""
        frames = self._branch_frame_cache.get(branch.branch_id)
        if frames is None:
            built = []
            consumed = 0.0
            for first, second in zip(branch.points, branch.points[1:]):
                length = math.hypot(
                    second[0] - first[0], second[1] - first[1]
                )
                if length <= _COORDINATE_TOLERANCE_MM:
                    continue
                built.append((consumed + length, consumed, first, second, length))
                consumed += length
            if not built:
                raise DowelPlanningError(
                    f"Branch '{branch.branch_id}' has no measurable segment."
                )
            frames = (tuple(item[0] for item in built), tuple(built), consumed)
            self._branch_frame_cache[branch.branch_id] = frames
        ends, segments, total = frames
        target = min(max(float(distance), 0.0), total)
        index = min(
            bisect_left(ends, target - _COORDINATE_TOLERANCE_MM),
            len(segments) - 1,
        )
        _end, consumed, first, second, length = segments[index]
        ratio = min(max((target - consumed) / length, 0.0), 1.0)
        tangent = (
            (second[0] - first[0]) / length,
            (second[1] - first[1]) / length,
        )
        point = (
            first[0] + ratio * (second[0] - first[0]),
            first[1] + ratio * (second[1] - first[1]),
        )
        return point, tangent

    def _validated_safe_subset(
        self, candidates, interval, branch, macro_result, solids
    ):
        """Lazily exact-check only candidates that can win subset selection.

        The cheap phase has no intentional false negatives.  Consequently, if
        the best subset in the current superset passes exact validation, no
        unvalidated subset can outrank it.  Failed candidates are removed and
        the deterministic selection is repeated.
        """
        remaining = list(candidates)
        exact_results = {}
        rejections = []
        while len(remaining) >= 2:
            selected, targets = self._select_safe_subset(tuple(remaining), interval)
            if not selected:
                break
            # Expensive classifiers are restricted to the current winning
            # layout. Low cylindrical occupancy is pruned only while a full
            # four-candidate recovery remains possible.
            low_material = []
            for candidate in selected:
                material_score = self._xy_material_score(
                    macro_result,
                    candidate.center_xyz_mm,
                    _canonical_normal(
                        candidate.tangent_xy, branch.branch_id
                    ),
                )
                if material_score < 1.0 - _COORDINATE_TOLERANCE_MM:
                    low_material.append((candidate, material_score))
                    continue
                if candidate.nearest_opening_clearance_mm >= (
                    self._parameters.hole_diameter_mm / 2.0
                    + self._parameters.material_margin_mm
                ):
                    continue
                score = self._local_material_score(
                    solids,
                    branch,
                    candidate.center_xyz_mm,
                    _canonical_normal(candidate.tangent_xy, branch.branch_id),
                )
                if score < 1.0 - _COORDINATE_TOLERANCE_MM:
                    low_material.append((candidate, score))
            removable = [
                candidate for candidate, _score in low_material
                if len(remaining) - len(low_material) >= self._parameters.target_per_branch
            ]
            if removable:
                removed_keys = {
                    round(candidate.distance_mm, 9) for candidate in removable
                }
                remaining = [
                    candidate for candidate in remaining
                    if round(candidate.distance_mm, 9) not in removed_keys
                ]
                for candidate, score in low_material:
                    if round(candidate.distance_mm, 9) in removed_keys:
                        rejections.append(DowelRejection(
                            branch.branch_id,
                            candidate.target_fraction,
                            candidate.center_xyz_mm,
                            f"low cylindrical material score {score:.3f}",
                            branch_distance_mm=candidate.distance_mm,
                        ))
                continue
            failed_distances = set()
            for candidate in selected:
                key = round(candidate.distance_mm, 9)
                if key not in exact_results:
                    cache_key = (branch.branch_id, key)
                    if cache_key not in self._exact_candidate_cache:
                        self._exact_candidate_cache[cache_key] = (
                            self._exact_candidate_reason(
                                macro_result,
                                solids,
                                branch,
                                candidate.center_xyz_mm,
                                candidate.tangent_xy,
                            )
                        )
                    exact_results[key] = self._exact_candidate_cache[cache_key]
                reason, _cutter, _depths, _breakout = exact_results[key]
                log_event(
                    "[6] Dowels",
                    branch.branch_id,
                    f"candidate_distance={candidate.distance_mm:.6f} "
                    f"result={reason or 'SAFE'}",
                )
                if reason is not None:
                    failed_distances.add(key)
                    rejections.append(
                        DowelRejection(
                            branch.branch_id,
                            candidate.target_fraction,
                            candidate.center_xyz_mm,
                            reason,
                            branch_distance_mm=candidate.distance_mm,
                        )
                    )
            if not failed_distances:
                return selected, targets, exact_results, tuple(rejections)
            remaining = [
                candidate
                for candidate in remaining
                if round(candidate.distance_mm, 9) not in failed_distances
            ]
        return (), (), exact_results, tuple(rejections)

    def _select_safe_subset(self, candidates, interval):
        """Choose the smallest useful 2-4 layout by unsupported branch span."""
        if len(candidates) < 2:
            return (), ()
        if len(candidates) >= 4:
            four = self._best_coverage_subset(
                candidates, 4, self._parameters.minimum_spacing_mm, interval
            )
            if four:
                return four, _even_fractions(4)
            four_relaxed = self._best_coverage_subset(
                candidates,
                4,
                self._parameters.minimum_spacing_mm * 0.75,
                interval,
            )
            if four_relaxed:
                return four_relaxed, _even_fractions(4)
        if len(candidates) >= 3:
            three = self._best_coverage_subset(
                candidates, 3, self._parameters.minimum_spacing_mm, interval
            )
            if three:
                return three, _even_fractions(3)
            three_relaxed = self._best_coverage_subset(
                candidates, 3, 0.0, interval
            )
            if three_relaxed:
                return three_relaxed, _even_fractions(3)
        fallback = self._best_coverage_subset(candidates, 2, 0.0, interval)
        return fallback, _even_fractions(2)

    def _best_relaxed_coverage(self, candidates, interval):
        layouts = []
        for count in range(3, min(self._parameters.maximum_per_branch, len(candidates)) + 1):
            selected = self._best_coverage_subset(candidates, count, 0.0, interval)
            if selected:
                layouts.append(selected)
                if _largest_candidate_gap(selected, interval) <= (
                    self._parameters.maximum_unsupported_span_mm
                    + _COORDINATE_TOLERANCE_MM
                ):
                    return selected
        return min(
            layouts,
            key=lambda selected: (
                _largest_candidate_gap(selected, interval), len(selected)
            ),
            default=(),
        )

    def _best_coverage_subset(self, candidates, count, minimum_spacing, interval):
        """Dynamic Pareto search over all cheap candidates, bounded by O(k*n^2)."""
        ordered = tuple(sorted(candidates, key=lambda item: item.distance_mm))
        if len(ordered) <= 40 and count <= 4:
            return self._exhaustive_coverage_subset(
                ordered, count, minimum_spacing, interval
            )
        ideals = tuple(
            interval[0] + (interval[1] - interval[0]) * fraction
            for fraction in _even_fractions(count)
        )
        states = {}
        for index, candidate in enumerate(ordered):
            states[(1, index)] = [(
                (index,),
                candidate.distance_mm - interval[0],
                math.inf,
                abs(candidate.distance_mm - ideals[0]),
                min(
                    candidate.nearest_opening_clearance_mm,
                    min(candidate.surrounding_material_mm,
                        self._parameters.edge_margin_mm),
                ),
                candidate.local_material_score,
            )]
        for used in range(2, count + 1):
            for index, candidate in enumerate(ordered):
                options = []
                for previous in range(index):
                    spacing = math.dist(
                        ordered[previous].center_xyz_mm[:2],
                        candidate.center_xyz_mm[:2],
                    )
                    if spacing < minimum_spacing - _COORDINATE_TOLERANCE_MM:
                        continue
                    for indices, largest, smallest, deviation, quality, material_score in states.get(
                        (used - 1, previous), ()
                    ):
                        options.append((
                            indices + (index,),
                            max(largest, candidate.distance_mm - ordered[previous].distance_mm),
                            min(smallest, spacing),
                            deviation + abs(candidate.distance_mm - ideals[used - 1]),
                            min(
                                quality,
                                candidate.nearest_opening_clearance_mm,
                                min(candidate.surrounding_material_mm,
                                    self._parameters.edge_margin_mm),
                            ),
                            min(material_score, candidate.local_material_score),
                        ))
                states[(used, index)] = _pareto_layouts(options)
        finalists = []
        for index in range(len(ordered)):
            for state in states.get((count, index), ()):
                (
                    indices, largest, smallest, deviation,
                    minimum_local_quality, minimum_material_score,
                ) = state
                final_largest = max(largest, interval[1] - ordered[index].distance_mm)
                quality_floor = (
                    self._parameters.hole_diameter_mm / 2.0
                    + self._parameters.material_margin_mm
                )
                quality_penalty = max(
                    0.0, quality_floor - minimum_local_quality
                )
                material_penalty = 200.0 * max(
                    0.0, 1.0 - minimum_material_score
                )
                signature = tuple(round(ordered[item].distance_mm, 9) for item in indices)
                finalists.append((
                    (
                        final_largest + quality_penalty + material_penalty,
                        -minimum_local_quality,
                        -smallest,
                        deviation,
                        signature,
                    ),
                    tuple(ordered[item] for item in indices),
                ))
        return min(finalists, key=lambda item: item[0])[1] if finalists else ()

    def _xy_material_score(self, macro_result, center, axis):
        """Score useful-depth probes against vectorized opening polygons."""

        depth = self._parameters.minimum_useful_depth_per_side_mm
        radius = self._parameters.hole_diameter_mm / 2.0
        tangent = (-axis[1], axis[0])
        scores = []
        for sign in (-1.0, 1.0):
            base = (
                center[0] + sign * axis[0] * depth,
                center[1] + sign * axis[1] * depth,
            )
            probes = (
                base,
                (base[0] + tangent[0] * radius, base[1] + tangent[1] * radius),
                (base[0] - tangent[0] * radius, base[1] - tangent[1] * radius),
            )
            material = 0
            for probe in probes:
                inside_opening = any(
                    feature.bounds_mm[0] <= probe[0] <= feature.bounds_mm[2]
                    and feature.bounds_mm[1] <= probe[1] <= feature.bounds_mm[3]
                    and self._point_in_feature(probe, feature)
                    for feature in macro_result.seam_plan.features
                )
                material += not inside_opening
            scores.append(material / len(probes))
        return min(scores, default=0.0)

    def _point_in_feature(self, probe, feature):
        """Run the odd-even polygon rule with cached NumPy coordinate arrays."""
        try:
            import numpy
        except ImportError:
            from .SinuousSeamPath import Point2D, _point_in_polygon
            return _point_in_polygon(Point2D(*probe), feature.points)
        key = feature.feature_id
        arrays = self._feature_polygon_cache.get(key)
        if arrays is None:
            x_values = numpy.asarray(
                tuple(point.x_mm for point in feature.points), dtype=float
            )
            y_values = numpy.asarray(
                tuple(point.y_mm for point in feature.points), dtype=float
            )
            arrays = (
                x_values, y_values,
                numpy.roll(x_values, 1), numpy.roll(y_values, 1),
            )
            self._feature_polygon_cache[key] = arrays
        x_values, y_values, previous_x, previous_y = arrays
        crosses = ((previous_y > probe[1]) != (y_values > probe[1]))
        crossing_x = previous_x + (
            (probe[1] - previous_y)
            * (x_values - previous_x)
            / numpy.where(y_values != previous_y, y_values - previous_y, 1.0)
        )
        return bool(numpy.count_nonzero(crosses & (probe[0] < crossing_x)) % 2)

    def _nearest_opening_clearance(self, first, second, features):
        """Return the cheap nearest 2D opening-box clearance for ranking."""
        radius = self._parameters.hole_diameter_mm / 2.0
        segment_bounds = (
            min(first[0], second[0]), min(first[1], second[1]),
            max(first[0], second[0]), max(first[1], second[1]),
        )
        return min(
            (
                _xy_bounds_distance(segment_bounds, feature.bounds_mm) - radius
                for feature in features
            ),
            default=math.inf,
        )

    def _exhaustive_coverage_subset(
        self, ordered, count, minimum_spacing, interval
    ):
        """Score a bounded shortlist with the exact policy and cached scalars."""
        ideals = tuple(
            interval[0] + (interval[1] - interval[0]) * fraction
            for fraction in _even_fractions(count)
        )
        quality_floor = (
            self._parameters.hole_diameter_mm / 2.0
            + self._parameters.material_margin_mm
        )
        size = len(ordered)
        adjacent_spacing = {}
        for first in range(size):
            first_center = ordered[first].center_xyz_mm
            for second in range(first + 1, size):
                second_center = ordered[second].center_xyz_mm
                adjacent_spacing[first, second] = math.hypot(
                    second_center[0] - first_center[0],
                    second_center[1] - first_center[1],
                )
        qualities = tuple(
            min(
                candidate.nearest_opening_clearance_mm,
                candidate.surrounding_material_mm,
                self._parameters.edge_margin_mm,
            )
            for candidate in ordered
        )
        material_scores = tuple(
            candidate.local_material_score for candidate in ordered
        )
        deviations = tuple(
            tuple(
                abs(candidate.distance_mm - ideals[position])
                for position in range(count)
            )
            for candidate in ordered
        )
        try:
            import numpy
            index_rows = numpy.asarray(
                tuple(combinations(range(size), count)), dtype=int
            )
            if index_rows.size:
                centers = numpy.asarray(tuple(
                    item.center_xyz_mm[:2] for item in ordered
                ))
                center_deltas = (
                    centers[index_rows[:, 1:]]
                    - centers[index_rows[:, :-1]]
                )
                spacing_rows = numpy.hypot(
                    center_deltas[:, :, 0], center_deltas[:, :, 1]
                )
                smallest_rows = spacing_rows.min(axis=1)
                valid = smallest_rows >= (
                    minimum_spacing - _COORDINATE_TOLERANCE_MM
                )
                index_rows = index_rows[valid]
                smallest_rows = smallest_rows[valid]
                if len(index_rows):
                    candidate_distances = numpy.asarray(tuple(
                        item.distance_mm for item in ordered
                    ))
                    distance_rows = candidate_distances[index_rows]
                    gap_rows = numpy.concatenate((
                        (distance_rows[:, :1] - interval[0]),
                        numpy.diff(distance_rows, axis=1),
                        (interval[1] - distance_rows[:, -1:]),
                    ), axis=1)
                    minimum_quality_rows = numpy.asarray(qualities)[
                        index_rows
                    ].min(axis=1)
                    minimum_material_rows = numpy.asarray(material_scores)[
                        index_rows
                    ].min(axis=1)
                    primary = (
                        gap_rows.max(axis=1)
                        + numpy.maximum(0.0, quality_floor - minimum_quality_rows)
                        + 200.0 * numpy.maximum(
                            0.0, 1.0 - minimum_material_rows
                        )
                    )
                    deviation_rows = numpy.asarray(deviations)[index_rows]
                    deviation_rows = numpy.diagonal(
                        deviation_rows, axis1=1, axis2=2
                    ).sum(axis=1)
                    signature = numpy.round(distance_rows, 9)
                    keys = [
                        signature[:, column]
                        for column in range(count - 1, -1, -1)
                    ] + [
                        deviation_rows,
                        -smallest_rows,
                        -minimum_quality_rows,
                        primary,
                    ]
                    best = index_rows[numpy.lexsort(tuple(keys))[0]]
                    return tuple(ordered[int(index)] for index in best)
        except ImportError:
            pass
        best_score = None
        best_indices = None
        for indices in combinations(range(size), count):
            smallest = min(
                adjacent_spacing[first, second]
                for first, second in zip(indices, indices[1:])
            )
            if smallest < minimum_spacing - _COORDINATE_TOLERANCE_MM:
                continue
            largest_gap = max(
                ordered[indices[0]].distance_mm - interval[0],
                interval[1] - ordered[indices[-1]].distance_mm,
                *(
                    ordered[second].distance_mm
                    - ordered[first].distance_mm
                    for first, second in zip(indices, indices[1:])
                ),
            )
            minimum_quality = min(qualities[index] for index in indices)
            quality_penalty = max(0.0, quality_floor - minimum_quality)
            minimum_material = min(material_scores[index] for index in indices)
            material_penalty = 200.0 * max(0.0, 1.0 - minimum_material)
            deviation = sum(
                deviations[index][position]
                for position, index in enumerate(indices)
            )
            signature = tuple(
                round(ordered[index].distance_mm, 9) for index in indices
            )
            score = (
                largest_gap + quality_penalty + material_penalty,
                -minimum_quality,
                -smallest,
                deviation,
                signature,
            )
            if best_score is None or score < best_score:
                best_score = score
                best_indices = indices
        return (
            tuple(ordered[index] for index in best_indices)
            if best_indices is not None else ()
        )

    def _local_material_score(self, solids, branch, center, axis):
        """Return a cached 0..1 cylindrical engagement score at useful depth."""
        try:
            from FreeCAD import Vector
        except Exception:
            return 0.0
        depth = self._parameters.minimum_useful_depth_per_side_mm
        scores = []
        for index in branch.intended_indices:
            if len(self._solid_centers) == len(solids):
                part_center = self._solid_centers[index]
            else:
                part_center = (
                    float(solids[index].CenterOfMass.x),
                    float(solids[index].CenterOfMass.y),
                )
            projection = (
                (part_center[0] - center[0]) * axis[0]
                + (part_center[1] - center[1]) * axis[1]
            )
            sign = 1.0 if projection >= 0.0 else -1.0
            probe = Vector(
                center[0] + sign * axis[0] * depth,
                center[1] + sign * axis[1] * depth,
                center[2],
            )
            scores.append(float(self._is_inside(solids[index], index, probe)))
        return min(scores, default=0.0)

    def _is_inside(self, solid, index, probe):
        key = (
            index,
            round(float(probe.x), 6),
            round(float(probe.y), 6),
            round(float(probe.z), 6),
        )
        if key not in self._inside_cache:
            self._inside_cache[key] = bool(
                solid.isInside(probe, _COORDINATE_TOLERANCE_MM, True)
            )
        return self._inside_cache[key]

    @staticmethod
    def _best_subset(candidates, count, minimum_spacing, interval, ideals):
        ranked = []
        ideal_distances = tuple(
            interval[0] + (interval[1] - interval[0]) * fraction
            for fraction in ideals
        )
        for candidate_set in combinations(candidates, count):
            centers = tuple(item.center_xyz_mm for item in candidate_set)
            pairwise = tuple(
                math.dist(centers[first][:2], centers[second][:2])
                for first in range(len(centers))
                for second in range(first + 1, len(centers))
            )
            smallest = min(pairwise, default=math.inf)
            if smallest < minimum_spacing - _COORDINATE_TOLERANCE_MM:
                continue
            ordered = tuple(sorted(item.distance_mm for item in candidate_set))
            coverage = ordered[-1] - ordered[0] if len(ordered) > 1 else 0.0
            deviation = sum(
                abs(item.distance_mm - ideal)
                for item, ideal in zip(candidate_set, ideal_distances)
            )
            signature = tuple(-round(value, 9) for value in ordered)
            score = (smallest, coverage, -deviation, signature)
            ranked.append((score, candidate_set))
        return max(ranked, key=lambda item: item[0])[1] if ranked else ()

    def apply(self, macro_result: MacroSplitResult, plan: DowelPlan | None = None) -> DowelApplication:
        """Batch-subtract validated cutters once from each mating part copy."""
        import Part

        chosen = plan if plan is not None else self.plan(macro_result)
        solids, _ = self._ordered_solids_and_bounds(macro_result)
        drilled = [solid.copy() for solid in solids]
        name_to_index = {f"Part_{index + 1}": index for index in range(4)}
        cutters = []
        cutters_by_part = [[] for _ in range(4)]
        before = sum(float(solid.Volume) for solid in drilled)
        for dowel in chosen.dowels:
            cutter = self._validated_cutters.get(
                self._cutter_cache_key(dowel.center_xyz_mm, dowel.axis_xy)
            )
            if cutter is None:
                cutter = self._cutter(dowel.center_xyz_mm, dowel.axis_xy)
            cutters.append(cutter)
            for name in dowel.intended_part_names:
                index = name_to_index[name]
                cutters_by_part[index].append(cutter)
        for index, part_cutters in enumerate(cutters_by_part):
            name = f"Part_{index + 1}"
            try:
                tool = Part.makeCompound(tuple(part_cutters))
                with operation(
                    "[6] Dowels",
                    name,
                    f"batch cut {len(part_cutters)} validated dowels",
                    drilled[index],
                ):
                    drilled[index] = drilled[index].cut(tool)
            except Exception as error:
                raise DowelPlanningError(
                    f"Boolean batch drilling failed in {name}."
                ) from error
            if not tuple(drilled[index].Solids) or float(drilled[index].Volume) <= 0.0:
                raise DowelPlanningError(
                    f"Batch drilling produced unusable geometry in {name}."
                )
        result_shape = Part.makeCompound(tuple(drilled))
        after = sum(float(solid.Volume) for solid in drilled)
        drilled_result = replace(
            macro_result,
            shape=result_shape,
            result_volume_mm3=after,
            solid_count=len(tuple(result_shape.Solids)),
        )
        if drilled_result.solid_count != 4 or before - after <= 0.0:
            raise DowelPlanningError("Dowel drilling did not preserve four positive parts.")
        return DowelApplication(
            macro_result=drilled_result,
            plan=chosen,
            cutters=tuple(cutters),
            removed_volume_mm3=before - after,
        )

    def _candidate_reason(
        self, macro_result, solids, bounds, branch, center, tangent, occupied
    ) -> str | None:
        """Compatibility helper performing both planning validation phases."""
        reason = self._cheap_candidate_reason(
            macro_result, solids, bounds, branch, center, tangent, occupied
        )
        if reason is not None:
            return reason
        reason, _cutter, _depths, _breakout = self._exact_candidate_reason(
            macro_result, solids, branch, center, tangent
        )
        return reason

    def _cheap_candidate_reason(
        self, macro_result, solids, bounds, branch, center, tangent, occupied
    ) -> str | None:
        """Reject obvious failures without constructing or cutting a BRep."""
        x_value, y_value, _ = center
        xmin, xmax, ymin, ymax, _, _ = bounds
        if min(x_value - xmin, xmax - x_value, y_value - ymin, ymax - y_value) < self._parameters.edge_margin_mm:
            return "outer-edge exclusion"
        intersection = (
            self._active_intersection
            if self._active_intersection is not None
            else _seam_intersection(macro_result.seam_plan)
        )
        if math.hypot(x_value - intersection[0], y_value - intersection[1]) < self._parameters.center_exclusion_mm:
            return "central-intersection exclusion"
        minimum_spacing = (
            self._parameters.hole_diameter_mm
            + 2.0 * self._parameters.material_margin_mm
        )
        if any(
            math.hypot(x_value - prior[0], y_value - prior[1]) < minimum_spacing
            for prior in occupied
        ):
            return "dowel clustering"
        axis = _canonical_normal(tangent, branch.branch_id)
        half = self._parameters.length_mm / 2.0
        first = (x_value - axis[0] * half, y_value - axis[1] * half)
        second = (x_value + axis[0] * half, y_value + axis[1] * half)
        # Artistic-opening breakout is allowed after both mating parts provide
        # the configured useful engagement. Exact validation records it.

        # A bounding-box miss proves insufficient local material and is safe to
        # reject.  Overlap is deliberately inconclusive and left to exact BRep
        # validation, avoiding false negatives around irregular panel forms.
        radius = self._parameters.hole_diameter_mm / 2.0
        segment_bounds = (
            min(first[0], second[0]) - radius,
            max(first[0], second[0]) + radius,
            min(first[1], second[1]) - radius,
            max(first[1], second[1]) + radius,
            center[2] - radius,
            center[2] + radius,
        )
        for index in branch.intended_indices:
            if len(self._solid_bounds) == len(solids):
                solid_bounds = self._solid_bounds[index]
            else:
                box = solids[index].BoundBox
                solid_bounds = (
                    float(box.XMin), float(box.XMax),
                    float(box.YMin), float(box.YMax),
                    float(box.ZMin), float(box.ZMax),
                )
            if not _bounds_overlap(
                segment_bounds,
                solid_bounds,
            ):
                return f"insufficient approximate material in Part_{index + 1}"
        return None

    def _exact_candidate_reason(
        self, macro_result, solids, branch, center, tangent
    ):
        """Run the authoritative four-solid BRep checks once for a shortlist item."""
        axis = _canonical_normal(tangent, branch.branch_id)
        cutter = self._cutter(center, axis)
        expected = set(branch.intended_indices)
        section_area = math.pi * (self._parameters.hole_diameter_mm / 2.0) ** 2
        useful_depths = {}
        cutter_box = cutter.BoundBox
        cutter_bounds = (
            float(cutter_box.XMin), float(cutter_box.XMax),
            float(cutter_box.YMin), float(cutter_box.YMax),
            float(cutter_box.ZMin), float(cutter_box.ZMax),
        )
        for index, solid in enumerate(solids):
            if index not in expected:
                box = solid.BoundBox
                solid_bounds = (
                    float(box.XMin), float(box.XMax),
                    float(box.YMin), float(box.YMax),
                    float(box.ZMin), float(box.ZMax),
                )
                if not _bounds_overlap(cutter_bounds, solid_bounds):
                    continue
            try:
                label = (
                    f"candidate=({center[0]:.3f},{center[1]:.3f},"
                    f"{center[2]:.3f}) Part_{index + 1}"
                )
                with operation(
                    "[6] Dowels", label, "validation common"
                ):
                    intersection = solid.common(cutter)
                    removed = float(intersection.Volume)
            except Exception:
                return "local boolean validation failed", cutter, (0.0, 0.0), False
            tolerance = volume_tolerance_mm3(float(solid.Volume))
            if index in expected:
                useful_depths[index] = max(0.0, removed / section_area)
                if useful_depths[index] < (
                    self._parameters.minimum_useful_depth_per_side_mm
                    - _COORDINATE_TOLERANCE_MM
                ):
                    return (
                        f"insufficient useful depth in Part_{index + 1}",
                        cutter,
                        tuple(
                            useful_depths.get(item, 0.0)
                            for item in branch.intended_indices
                        ),
                        True,
                    )
            if index not in expected and removed > tolerance:
                return (
                    f"would drill Part_{index + 1}", cutter, (0.0, 0.0), False
                )
        ordered_depths = tuple(
            useful_depths.get(item, 0.0) for item in branch.intended_indices
        )
        expected_total_depth = (
            self._parameters.length_mm - macro_result.separation_width_mm
        )
        breakout = sum(ordered_depths) < expected_total_depth - 0.05
        return None, cutter, ordered_depths, breakout

    @staticmethod
    def _cutter_cache_key(center, axis):
        return tuple(round(float(value), 9) for value in (*center, *axis))

    def _cutter(self, center, axis):
        import Part
        from FreeCAD import Vector

        half = self._parameters.length_mm / 2.0
        base = Vector(center[0] - axis[0] * half, center[1] - axis[1] * half, center[2])
        return Part.makeCylinder(
            self._parameters.hole_diameter_mm / 2.0,
            self._parameters.length_mm,
            base,
            Vector(axis[0], axis[1], 0.0),
        )

    @staticmethod
    def _ordered_solids_and_bounds(macro_result):
        if not isinstance(macro_result, MacroSplitResult) or macro_result.seam_plan is None:
            raise DowelPlanningError("Dowel planning requires a V4.30 seam result.")
        solids = tuple(macro_result.shape.Solids)
        if len(solids) != 4:
            raise DowelPlanningError("Dowel planning requires exactly four solids.")
        mapped = {}
        for solid in solids:
            center = solid.CenterOfMass
            key = (float(center.x) >= macro_result.cut_x_mm, float(center.y) >= macro_result.cut_y_mm)
            mapped.setdefault(key, []).append(solid)
        keys = ((False, False), (True, False), (False, True), (True, True))
        if any(len(mapped.get(key, ())) != 1 for key in keys):
            raise DowelPlanningError("Dowel parts do not map to four quadrants.")
        box = macro_result.shape.BoundBox
        bounds = (float(box.XMin), float(box.XMax), float(box.YMin), float(box.YMax), float(box.ZMin), float(box.ZMax))
        return tuple(mapped[key][0] for key in keys), bounds

    def _branches(self, macro_result):
        point = (
            self._active_intersection
            if self._active_intersection is not None
            else _seam_intersection(macro_result.seam_plan)
        )
        vertical_low, vertical_high = _split_polyline(macro_result.seam_plan.vertical.points, point)
        horizontal_low, horizontal_high = _split_polyline(macro_result.seam_plan.horizontal.points, point)
        return (
            _Branch("vertical_below", vertical_low, (0, 1), ("Part_1", "Part_2")),
            _Branch("vertical_above", vertical_high, (2, 3), ("Part_3", "Part_4")),
            _Branch("horizontal_left", horizontal_low, (0, 2), ("Part_1", "Part_3")),
            _Branch("horizontal_right", horizontal_high, (1, 3), ("Part_2", "Part_4")),
        )

    @staticmethod
    def _validate_parameters(parameters):
        values = (
            parameters.dowel_diameter_mm, parameters.hole_diameter_mm,
            parameters.length_mm, parameters.axis_height_mm,
            parameters.edge_margin_mm, parameters.material_margin_mm,
            parameters.center_exclusion_mm, parameters.minimum_spacing_mm,
            parameters.maximum_unsupported_span_mm,
            parameters.minimum_useful_depth_per_side_mm,
        )
        if not all(math.isfinite(float(value)) and float(value) > 0.0 for value in values):
            raise DowelPlanningError("Dowel geometry settings must be finite and positive.")
        if parameters.hole_diameter_mm < parameters.dowel_diameter_mm:
            raise DowelPlanningError("Dowel hole diameter cannot be smaller than dowel diameter.")
        if not (
            2 <= int(parameters.minimum_per_branch)
            <= int(parameters.target_per_branch)
            <= int(parameters.maximum_per_branch)
            <= 4
        ):
            raise DowelPlanningError(
                "Dowel branch counts must satisfy 2 <= minimum <= target <= maximum <= 4."
            )
        return parameters


def _polyline_length(points):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))


def _sample_distances(start, end, interval):
    """Return deterministic full-interval samples including both endpoints."""
    lower, upper, step = float(start), float(end), float(interval)
    values = [lower]
    index = 1
    while lower + index * step < upper - _COORDINATE_TOLERANCE_MM:
        values.append(lower + index * step)
        index += 1
    if upper - values[-1] > _COORDINATE_TOLERANCE_MM:
        values.append(upper)
    return tuple(values)


def _even_fractions(count):
    return tuple(index / (count + 1.0) for index in range(1, count + 1))


def _largest_candidate_gap(candidates, interval):
    ordered = tuple(sorted(item.distance_mm for item in candidates))
    if not ordered:
        return interval[1] - interval[0]
    return max(
        (ordered[0] - interval[0],)
        + tuple(second - first for first, second in zip(ordered, ordered[1:]))
        + (interval[1] - ordered[-1],)
    )


def _unsupported_spans(dowels, interval):
    ordered = tuple(sorted(item.branch_distance_mm for item in dowels))
    if not ordered:
        return (interval[1] - interval[0],)
    return (
        (ordered[0] - interval[0],)
        + tuple(second - first for first, second in zip(ordered, ordered[1:]))
        + (interval[1] - ordered[-1],)
    )


def _safe_interval_count(candidates, sampling_interval):
    ordered = tuple(sorted(item.distance_mm for item in candidates))
    if not ordered:
        return 0
    threshold = float(sampling_interval) * 1.5 + _COORDINATE_TOLERANCE_MM
    return 1 + sum(
        second - first > threshold
        for first, second in zip(ordered, ordered[1:])
    )


def _pareto_layouts(options):
    """Retain deterministic non-dominated partial coverage layouts."""
    result = []
    for candidate in sorted(
        options,
        key=lambda item: (
            item[1], -item[2], item[3], -item[5], -item[4], item[0]
        ),
    ):
        _indices, largest, smallest, deviation, quality, material = candidate
        if any(
            prior[1] <= largest + _COORDINATE_TOLERANCE_MM
            and prior[2] >= smallest - _COORDINATE_TOLERANCE_MM
            and prior[3] <= deviation + _COORDINATE_TOLERANCE_MM
            and prior[4] >= quality - _COORDINATE_TOLERANCE_MM
            and prior[5] >= material - _COORDINATE_TOLERANCE_MM
            for prior in result
        ):
            continue
        result = [
            prior
            for prior in result
            if not (
                largest <= prior[1] + _COORDINATE_TOLERANCE_MM
                and smallest >= prior[2] - _COORDINATE_TOLERANCE_MM
                and deviation <= prior[3] + _COORDINATE_TOLERANCE_MM
                and quality >= prior[4] - _COORDINATE_TOLERANCE_MM
                and material >= prior[5] - _COORDINATE_TOLERANCE_MM
            )
        ]
        result.append(candidate)
    return result


def _rejection_counts(rejections):
    counts = {}
    for rejection in rejections:
        counts[rejection.reason] = counts.get(rejection.reason, 0) + 1
    return tuple(sorted(counts.items()))


def _bounds_overlap(first, second):
    """Return whether two XYZ axis-aligned boxes overlap or touch."""
    return not (
        first[1] < second[0] - _COORDINATE_TOLERANCE_MM
        or second[1] < first[0] - _COORDINATE_TOLERANCE_MM
        or first[3] < second[2] - _COORDINATE_TOLERANCE_MM
        or second[3] < first[2] - _COORDINATE_TOLERANCE_MM
        or first[5] < second[4] - _COORDINATE_TOLERANCE_MM
        or second[5] < first[4] - _COORDINATE_TOLERANCE_MM
    )


def _xy_bounds_distance(first, second):
    """Return the Euclidean gap between two XY axis-aligned boxes."""
    dx = max(float(second[0]) - float(first[2]), float(first[0]) - float(second[2]), 0.0)
    dy = max(float(second[1]) - float(first[3]), float(first[1]) - float(second[3]), 0.0)
    return math.hypot(dx, dy)


def _candidate_distances(target, start, end, *, search_limit=None):
    """Scan 0,+5,-5 relocations within one usable interval."""
    lower, upper = float(start), float(end)
    values = [min(max(float(target), lower), upper)]
    span = upper - lower
    limit = span if search_limit is None else min(span, float(search_limit))
    maximum_steps = int(math.ceil(limit / _RELOCATION_INCREMENT_MM))
    for step in range(1, maximum_steps + 1):
        delta = step * _RELOCATION_INCREMENT_MM
        for candidate in (target + delta, target - delta):
            if lower <= candidate <= upper:
                values.append(float(candidate))
    for endpoint in (lower, upper):
        if (search_limit is None or limit >= span - _COORDINATE_TOLERANCE_MM) and all(
            abs(endpoint - value) > _COORDINATE_TOLERANCE_MM for value in values
        ):
            values.append(endpoint)
    return tuple(values)


def _adjacent_center_spacings(dowels):
    ordered = tuple(sorted(dowels, key=lambda item: item.branch_distance_mm))
    return tuple(
        math.dist(first.center_xyz_mm[:2], second.center_xyz_mm[:2])
        for first, second in zip(ordered, ordered[1:])
    )


def _point_and_tangent(points, distance):
    length = _polyline_length(points)
    target = min(max(float(distance), 0.0), length)
    consumed = 0.0
    for first, second in zip(points, points[1:]):
        segment = math.hypot(second[0] - first[0], second[1] - first[1])
        if segment <= _COORDINATE_TOLERANCE_MM:
            continue
        if consumed + segment >= target - _COORDINATE_TOLERANCE_MM:
            ratio = min(max((target - consumed) / segment, 0.0), 1.0)
            tangent = ((second[0] - first[0]) / segment, (second[1] - first[1]) / segment)
            return (first[0] + ratio * (second[0] - first[0]), first[1] + ratio * (second[1] - first[1])), tangent
        consumed += segment
    first, second = points[-2], points[-1]
    segment = math.hypot(second[0] - first[0], second[1] - first[1])
    return second, ((second[0] - first[0]) / segment, (second[1] - first[1]) / segment)


def _canonical_normal(tangent, branch_id):
    tx, ty = tangent
    if branch_id.startswith("vertical"):
        normal = (ty, -tx)
        if normal[0] < 0.0:
            normal = (-normal[0], -normal[1])
    else:
        normal = (-ty, tx)
        if normal[1] < 0.0:
            normal = (-normal[0], -normal[1])
    return normal


def _seam_intersection(plan):
    found = []
    for a, b in zip(plan.vertical.points, plan.vertical.points[1:]):
        for c, d in zip(plan.horizontal.points, plan.horizontal.points[1:]):
            point = _segment_intersection((a.x_mm, a.y_mm), (b.x_mm, b.y_mm), (c.x_mm, c.y_mm), (d.x_mm, d.y_mm))
            if point is not None and not any(math.hypot(point[0] - prior[0], point[1] - prior[1]) <= _COORDINATE_TOLERANCE_MM for prior in found):
                found.append(point)
    if len(found) != 1:
        raise DowelPlanningError("Dowel planning requires one seam intersection.")
    return found[0]


def _segment_intersection(a, b, c, d):
    rx, ry = b[0] - a[0], b[1] - a[1]
    sx, sy = d[0] - c[0], d[1] - c[1]
    denominator = rx * sy - ry * sx
    if abs(denominator) <= _COORDINATE_TOLERANCE_MM:
        return None
    qx, qy = c[0] - a[0], c[1] - a[1]
    t = (qx * sy - qy * sx) / denominator
    u = (qx * ry - qy * rx) / denominator
    if -_COORDINATE_TOLERANCE_MM <= t <= 1.0 + _COORDINATE_TOLERANCE_MM and -_COORDINATE_TOLERANCE_MM <= u <= 1.0 + _COORDINATE_TOLERANCE_MM:
        return a[0] + t * rx, a[1] + t * ry
    return None


def _split_polyline(points, intersection):
    scalar = tuple((float(point.x_mm), float(point.y_mm)) for point in points)
    for index, (first, second) in enumerate(zip(scalar, scalar[1:])):
        if _point_segment_distance(intersection, first, second) <= _COORDINATE_TOLERANCE_MM:
            low = scalar[: index + 1]
            high = scalar[index + 1 :]
            if not low or math.hypot(low[-1][0] - intersection[0], low[-1][1] - intersection[1]) > _COORDINATE_TOLERANCE_MM:
                low += (intersection,)
            if not high or math.hypot(high[0][0] - intersection[0], high[0][1] - intersection[1]) > _COORDINATE_TOLERANCE_MM:
                high = (intersection,) + high
            return low, high
    raise DowelPlanningError("Seam intersection is not on both polylines.")


def _point_segment_distance(point, first, second):
    dx, dy = second[0] - first[0], second[1] - first[1]
    squared = dx * dx + dy * dy
    if squared <= _COORDINATE_TOLERANCE_MM ** 2:
        return math.hypot(point[0] - first[0], point[1] - first[1])
    ratio = min(max(((point[0] - first[0]) * dx + (point[1] - first[1]) * dy) / squared, 0.0), 1.0)
    return math.hypot(point[0] - (first[0] + ratio * dx), point[1] - (first[1] + ratio * dy))


def _segment_polyline_distance(first, second, points):
    if len(points) < 2:
        return math.inf
    return min(_segment_distance(first, second, a, b) for a, b in zip(points, points[1:] + points[:1]))


def _segment_distance(a, b, c, d):
    if _segment_intersection(a, b, c, d) is not None:
        return 0.0
    return min(
        _point_segment_distance(a, c, d), _point_segment_distance(b, c, d),
        _point_segment_distance(c, a, b), _point_segment_distance(d, a, b),
    )

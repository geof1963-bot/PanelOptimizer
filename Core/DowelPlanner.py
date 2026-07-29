# -*- coding: utf-8 -*-
"""Deterministic V4.60-distributed dowel planning and transient drilling.

The planner consumes the already accepted V4.30 four-solid result.  It splits
the two immutable seam polylines at their sole intersection, samples each of
the four branches by arc length, and validates a horizontal cylindrical hole
against the four transient solids.  Only the two expected mating solids may
lose material.  No FreeCAD object is stored in the immutable plan records.
"""

from __future__ import annotations

import math
from itertools import product
from dataclasses import dataclass, replace

from .Exceptions import DowelPlanningError
from .MacroSplitCore import MacroSplitResult
from .Settings import Settings
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
    """Validated V4.40 configuration; scalar geometry is in millimetres."""

    dowel_diameter_mm: float = Settings.Joinery.DOWEL_DIAMETER_MM
    hole_diameter_mm: float = Settings.Joinery.DOWEL_HOLE_DIAMETER_MM
    length_mm: float = Settings.Joinery.DOWEL_LENGTH_MM
    axis_height_mm: float = Settings.Joinery.DOWEL_AXIS_HEIGHT_MM
    edge_margin_mm: float = Settings.Joinery.DOWEL_EDGE_MARGIN_MM
    material_margin_mm: float = Settings.Joinery.DOWEL_MIN_MATERIAL_MARGIN_MM
    center_exclusion_mm: float = Settings.Joinery.DOWEL_CENTER_EXCLUSION_MM
    minimum_spacing_mm: float = Settings.Joinery.DOWEL_MIN_SPACING_MM
    target_per_branch: int = Settings.Joinery.DOWELS_TARGET_PER_BRANCH
    minimum_per_branch: int = Settings.Joinery.DOWELS_MIN_PER_BRANCH


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


class DowelPlanner:
    """Plan and subtract simple coaxial dowel holes from V4.30 parts only."""

    def __init__(self, parameters: DowelParameters = DowelParameters()) -> None:
        self._parameters = self._validate_parameters(parameters)

    def plan(self, macro_result: MacroSplitResult) -> DowelPlan:
        """Return a safe deterministic plan without modifying any input shape."""
        solids, bounds = self._ordered_solids_and_bounds(macro_result)
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
            length = _polyline_length(branch.points)
            usable_interval = self._usable_interval(
                branch, bounds, _seam_intersection(macro_result.seam_plan)
            )
            usable_length = usable_interval[1] - usable_interval[0]
            rejections = []
            cache = {}
            chosen_candidates = ()
            actual_targets = ()
            used_fallback = False
            requested_targets = _TARGET_FRACTIONS[: self._parameters.target_per_branch]
            three_dowel_failure_reason = None
            if (
                self._parameters.target_per_branch >= 3
                and usable_length >= 2.0 * self._parameters.minimum_spacing_mm
            ):
                pools = tuple(
                    self._candidate_pool(
                        fraction,
                        usable_interval,
                        branch,
                        macro_result,
                        solids,
                        bounds,
                        z_value,
                        occupied,
                        cache,
                        rejections,
                        search_limit=0.0,
                        maximum_safe_candidates=1,
                    )
                    for fraction in requested_targets
                )
                chosen_candidates = self._select_distribution(
                    pools,
                    self._parameters.minimum_spacing_mm,
                    prefer_targets=True,
                )
                if not chosen_candidates:
                    pools = tuple(
                        self._candidate_pool(
                            fraction,
                            usable_interval,
                            branch,
                            macro_result,
                            solids,
                            bounds,
                            z_value,
                            occupied,
                            cache,
                            rejections,
                            search_limit=self._parameters.minimum_spacing_mm / 2.0,
                            maximum_safe_candidates=5,
                        )
                        for fraction in requested_targets
                    )
                    chosen_candidates = self._select_distribution(
                        pools,
                        self._parameters.minimum_spacing_mm,
                        prefer_targets=True,
                    )
                if chosen_candidates:
                    actual_targets = requested_targets
                else:
                    three_dowel_failure_reason = (
                        "no safe 20/50/80 set meets minimum spacing"
                    )
            elif self._parameters.target_per_branch >= 3:
                three_dowel_failure_reason = (
                    "usable interval cannot support three minimum-spaced dowels"
                )
            if not chosen_candidates:
                if three_dowel_failure_reason is not None:
                    midpoint = (usable_interval[0] + usable_interval[1]) / 2.0
                    point, _ = _point_and_tangent(branch.points, midpoint)
                    rejections.append(
                        DowelRejection(
                            branch.branch_id,
                            0.50,
                            (point[0], point[1], z_value),
                            three_dowel_failure_reason,
                            branch_distance_mm=midpoint,
                        )
                    )
                used_fallback = self._parameters.target_per_branch >= 3
                actual_targets = _FALLBACK_FRACTIONS
                pools = tuple(
                    self._candidate_pool(
                        fraction,
                        usable_interval,
                        branch,
                        macro_result,
                        solids,
                        bounds,
                        z_value,
                        occupied,
                        cache,
                        rejections,
                        search_limit=0.0,
                        maximum_safe_candidates=1,
                    )
                    for fraction in actual_targets
                )
                required_spacing = min(
                    self._parameters.minimum_spacing_mm, usable_length
                )
                chosen_candidates = self._select_distribution(
                    pools, required_spacing, prefer_targets=False
                )
                if not chosen_candidates:
                    pools = tuple(
                        self._candidate_pool(
                            fraction,
                            usable_interval,
                            branch,
                            macro_result,
                            solids,
                            bounds,
                            z_value,
                            occupied,
                            cache,
                            rejections,
                            search_limit=min(
                                self._parameters.minimum_spacing_mm / 2.0,
                                usable_length,
                            ),
                            maximum_safe_candidates=7,
                        )
                        for fraction in actual_targets
                    )
                    chosen_candidates = self._select_distribution(
                        pools, required_spacing, prefer_targets=False
                    )
                if not chosen_candidates:
                    chosen_candidates = self._select_distribution(
                        pools, 0.0, prefer_targets=False
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
                )
                branch_dowels.append(record)
                accepted.append(record)
                occupied.append(center[:2])
            if len(branch_dowels) < self._parameters.minimum_per_branch:
                reasons = sorted({item.reason for item in rejections})
                raise DowelPlanningError(
                    f"Branch '{branch.branch_id}' has only {len(branch_dowels)} "
                    f"safe dowels; minimum is {self._parameters.minimum_per_branch}. "
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
                )
            )
        return DowelPlan(tuple(accepted), tuple(branch_results))

    def _usable_interval(self, branch, bounds, intersection):
        """Measure the contiguous branch interval outside edge/center margins."""
        length = _polyline_length(branch.points)
        sample_count = max(1, int(math.ceil(length)))
        distances = tuple(length * index / sample_count for index in range(sample_count + 1))

        def eligible(distance):
            point, _ = _point_and_tangent(branch.points, distance)
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

    def _candidate_pool(
        self,
        fraction,
        interval,
        branch,
        macro_result,
        solids,
        bounds,
        z_value,
        occupied,
        cache,
        rejections,
        *,
        search_limit,
        maximum_safe_candidates,
    ):
        """Evaluate symmetric nearest-first relocations around one target."""
        start, end = interval
        target = start + (end - start) * fraction
        candidates = []
        for distance in _candidate_distances(
            target, start, end, search_limit=search_limit
        ):
            key = round(distance, 9)
            if key not in cache:
                point, tangent = _point_and_tangent(branch.points, distance)
                center = (point[0], point[1], z_value)
                reason = self._candidate_reason(
                    macro_result,
                    solids,
                    bounds,
                    branch,
                    center,
                    tangent,
                    occupied,
                )
                cache[key] = (center, tangent, reason)
            center, tangent, reason = cache[key]
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
                continue
            candidates.append(
                _Candidate(distance, center, tangent, fraction, target)
            )
            if len(candidates) >= maximum_safe_candidates:
                break
        return tuple(candidates)

    @staticmethod
    def _select_distribution(pools, minimum_spacing, *, prefer_targets):
        """Choose one candidate per target as a deterministic complete set."""
        if not pools or any(not pool for pool in pools):
            return ()
        ranked = []
        for candidate_set in product(*pools):
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
                abs(item.distance_mm - item.target_distance_mm)
                for item in candidate_set
            )
            signature = tuple(-round(value, 9) for value in ordered)
            score = (
                (-deviation, smallest, coverage, signature)
                if prefer_targets
                else (smallest, coverage, -deviation, signature)
            )
            ranked.append((score, candidate_set))
        return max(ranked, key=lambda item: item[0])[1] if ranked else ()

    def apply(self, macro_result: MacroSplitResult, plan: DowelPlan | None = None) -> DowelApplication:
        """Subtract each planned cutter from exactly its two mating part copies."""
        import Part

        chosen = plan if plan is not None else self.plan(macro_result)
        solids, _ = self._ordered_solids_and_bounds(macro_result)
        drilled = [solid.copy() for solid in solids]
        name_to_index = {f"Part_{index + 1}": index for index in range(4)}
        cutters = []
        before = sum(float(solid.Volume) for solid in drilled)
        for dowel in chosen.dowels:
            cutter = self._cutter(dowel.center_xyz_mm, dowel.axis_xy)
            cutters.append(cutter)
            for name in dowel.intended_part_names:
                index = name_to_index[name]
                try:
                    drilled[index] = drilled[index].cut(cutter)
                except Exception as error:
                    raise DowelPlanningError(
                        f"Boolean drilling failed for {dowel.dowel_id} in {name}."
                    ) from error
                if not tuple(drilled[index].Solids) or float(drilled[index].Volume) <= 0.0:
                    raise DowelPlanningError(
                        f"{dowel.dowel_id} produced unusable geometry in {name}."
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
        x_value, y_value, _ = center
        xmin, xmax, ymin, ymax, _, _ = bounds
        if min(x_value - xmin, xmax - x_value, y_value - ymin, ymax - y_value) < self._parameters.edge_margin_mm:
            return "outer-edge exclusion"
        intersection = _seam_intersection(macro_result.seam_plan)
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
        clearance = self._parameters.hole_diameter_mm / 2.0 + self._parameters.material_margin_mm
        for feature in macro_result.seam_plan.features:
            points = tuple((point.x_mm, point.y_mm) for point in feature.points)
            if _segment_polyline_distance(first, second, points) < clearance:
                return f"opening margin ({feature.feature_id})"
        cutter = self._cutter(center, axis)
        expected = set(branch.intended_indices)
        half_volume = math.pi * (self._parameters.hole_diameter_mm / 2.0) ** 2 * (self._parameters.length_mm / 2.0)
        total_removed = 0.0
        for index, solid in enumerate(solids):
            try:
                cut_shape = solid.cut(cutter)
                removed = float(solid.Volume) - float(cut_shape.Volume)
            except Exception:
                return "local boolean validation failed"
            tolerance = volume_tolerance_mm3(float(solid.Volume))
            total_removed += max(0.0, removed)
            if index in expected and removed < half_volume * 0.55:
                return f"insufficient material in Part_{index + 1}"
            if index not in expected and removed > tolerance:
                return f"would drill Part_{index + 1}"
        expected_material = (
            math.pi
            * (self._parameters.hole_diameter_mm / 2.0) ** 2
            * (self._parameters.length_mm - macro_result.separation_width_mm)
        )
        material_tolerance = max(
            volume_tolerance_mm3(expected_material),
            expected_material * 1.0e-4,
        )
        if total_removed < expected_material - material_tolerance:
            return "cutter intersects existing void"
        return None

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

    @staticmethod
    def _branches(macro_result):
        point = _seam_intersection(macro_result.seam_plan)
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
        )
        if not all(math.isfinite(float(value)) and float(value) > 0.0 for value in values):
            raise DowelPlanningError("Dowel geometry settings must be finite and positive.")
        if parameters.hole_diameter_mm < parameters.dowel_diameter_mm:
            raise DowelPlanningError("Dowel hole diameter cannot be smaller than dowel diameter.")
        if not (2 <= int(parameters.minimum_per_branch) <= int(parameters.target_per_branch) <= 3):
            raise DowelPlanningError("Dowel branch counts must satisfy 2 <= minimum <= target <= 3.")
        return parameters


def _polyline_length(points):
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))


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

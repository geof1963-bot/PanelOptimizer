# -*- coding: utf-8 -*-
"""Deterministic lightweight XY seam paths following top-view openings.

This module deliberately does not use AnalyzerEngine.  It reads the largest
top planar face, treats its inner wires as visible opening boundaries, and
builds monotone vertical/horizontal polylines.  A selected detour approaches
one boundary, follows its nearest monotone side, and returns to the nominal
line.  Unsupported or ambiguous boundaries are simply ignored.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, replace

from .Exceptions import SplitOperationError
from .Settings import Settings

_COORDINATE_TOLERANCE_MM = 1.0e-6

__all__ = [
    "BoundaryFeature2D",
    "HoleOffsetReport",
    "Point2D",
    "SeamPath2D",
    "SinuousSeamParameters",
    "SinuousSeamPathFinder",
    "SinuousSeamPlan",
]


@dataclass(frozen=True, slots=True, order=True)
class Point2D:
    """One immutable model-coordinate XY point, in millimetres."""

    x_mm: float
    y_mm: float


@dataclass(frozen=True, slots=True)
class BoundaryFeature2D:
    """One sampled top-view opening boundary without FreeCAD objects."""

    feature_id: str
    source_wire_index: int
    points: tuple[Point2D, ...]
    bounds_mm: tuple[float, float, float, float]
    perimeter_mm: float


@dataclass(frozen=True, slots=True)
class HoleOffsetReport:
    """Scalar evidence that a followed cutter path remains inside an opening."""

    feature_id: str
    boundary_bounds_mm: tuple[float, float, float, float]
    interior_side: str
    cutter_envelope_mm: float
    clearance_mm: float
    final_offset_mm: float
    minimum_material_side_clearance_mm: float
    followed_contour_length_mm: float = 0.0
    direction_used: str = "unknown"
    minimum_offset_mm: float = 0.0
    maximum_offset_mm: float = 0.0
    average_offset_mm: float = 0.0
    original_profile_preserved: bool = False


@dataclass(frozen=True, slots=True)
class SeamPath2D:
    """One continuous monotone edge-to-edge seam polyline."""

    axis: str
    nominal_coordinate_mm: float
    points: tuple[Point2D, ...]
    followed_feature_ids: tuple[str, ...]
    followed_feature_bounds_mm: tuple[tuple[float, float, float, float], ...]
    path_length_mm: float
    maximum_deviation_mm: float
    segment_count_before_cleanup: int = 0
    segment_count_after_cleanup: int = 0
    smoothing_transition_count: int = 0
    maximum_artificial_turn_before_deg: float = 0.0
    maximum_artificial_turn_after_deg: float = 0.0
    hole_offset_reports: tuple[HoleOffsetReport, ...] = ()
    contour_following_length_mm: float = 0.0
    contour_following_ratio: float = 0.0
    longest_straight_segment_mm: float = 0.0
    detour_ids: tuple[str, ...] = ()
    detour_feature_ids: tuple[str, ...] = ()
    detour_levels: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class SinuousSeamPlan:
    """The two deterministic paths and extracted feature evidence."""

    vertical: SeamPath2D
    horizontal: SeamPath2D
    features: tuple[BoundaryFeature2D, ...]
    intersection_count: int


@dataclass(frozen=True, slots=True)
class SinuousSeamParameters:
    """Minimal geometry-only configuration for the practical V4.30 finder."""

    search_corridor_mm: float = Settings.Split.SEAM_SEARCH_CORRIDOR_MM
    center_exclusion_mm: float = Settings.Split.SEAM_CENTER_EXCLUSION_MM
    minimum_feature_size_mm: float = Settings.Split.SEAM_MIN_FEATURE_SIZE_MM
    boundary_deflection_mm: float = Settings.Split.SEAM_BOUNDARY_DEFLECTION_MM
    boundary_simplification_mm: float = Settings.Split.SEAM_SIMPLIFICATION_MM
    path_simplify_tolerance_mm: float = Settings.Split.SEAM_SIMPLIFY_TOLERANCE_MM
    maximum_artificial_turn_deg: float = Settings.Split.SEAM_MAX_ARTIFICIAL_TURN_DEG
    approach_length_mm: float = Settings.Split.SEAM_APPROACH_LENGTH_MM
    hole_clearance_mm: float = Settings.Split.SEAM_HOLE_CLEARANCE_MM
    minimum_follow_length_mm: float = Settings.Split.SEAM_MIN_FOLLOW_LENGTH_MM
    maximum_features_per_seam: int = Settings.Split.MAX_FOLLOWED_FEATURES_PER_SEAM
    maximum_variants_per_axis: int = Settings.Split.MAX_SEAM_VARIANTS_PER_AXIS
    beam_width: int = Settings.Split.SEAM_BEAM_WIDTH
    coverage_epsilon_mm: float = Settings.Split.SEAM_COVERAGE_EPSILON_MM


class SinuousSeamPathFinder:
    """Extract useful opening wires and generate two simple seam paths."""

    def __init__(
        self,
        parameters: SinuousSeamParameters = SinuousSeamParameters(),
        split_settings: object = Settings.Split,
    ) -> None:
        self._parameters = self._validated_parameters(parameters)
        self._split_settings = split_settings
        self._detour_cache = {}
        self._transition_cache = {}
        self._diagnostics = {}

    def generate(
        self,
        source_shape: object,
        vertical_offset: float = 0.0,
        horizontal_offset: float = 0.0,
    ) -> SinuousSeamPlan:
        """Generate deterministic paths directly from the source top view."""
        self._detour_cache = {}
        self._transition_cache = {}
        self._diagnostics = {
            "route_candidates_generated": 0,
            "route_candidates_pruned": 0,
            "detour_cache_hits": 0,
            "transition_cache_hits": 0,
        }
        try:
            bounds = source_shape.BoundBox
            xmin, xmax = float(bounds.XMin), float(bounds.XMax)
            ymin, ymax = float(bounds.YMin), float(bounds.YMax)
            zmax = float(bounds.ZMax)
        except Exception as error:
            raise SplitOperationError("Sinuous seam source is unavailable.") from error
        nominal_x = (xmin + xmax) / 2.0 + self._finite(vertical_offset)
        nominal_y = (ymin + ymax) / 2.0 + self._finite(horizontal_offset)
        started = time.perf_counter()
        features = self._extract_features(source_shape, zmax)
        self._diagnostics["contour_prep_seconds"] = time.perf_counter() - started
        started = time.perf_counter()
        vertical = self._build_path(
            "vertical", nominal_x, nominal_y, (xmin, xmax, ymin, ymax), features
        )
        horizontal = self._build_path(
            "horizontal", nominal_y, nominal_x, (xmin, xmax, ymin, ymax), features
        )
        intersections = _intersection_count(vertical.points, horizontal.points)
        self._diagnostics["initial_intersection_count"] = intersections
        self._diagnostics["initial_vertical_features"] = len(
            vertical.followed_feature_ids
        )
        self._diagnostics["initial_horizontal_features"] = len(
            horizontal.followed_feature_ids
        )
        if intersections != 1:
            # Keep the already-proven vertical detour and conservatively make
            # the second seam straight. A monotone vertical path kept straight
            # in the center exclusion zone then intersects it exactly once.
            horizontal = self._straight_path(
                "horizontal", nominal_y, (xmin, xmax, ymin, ymax)
            )
            intersections = _intersection_count(vertical.points, horizontal.points)
        if intersections != 1:
            vertical = self._straight_path(
                "vertical", nominal_x, (xmin, xmax, ymin, ymax)
            )
            intersections = _intersection_count(vertical.points, horizontal.points)
        if intersections != 1:
            raise SplitOperationError("Seam paths do not intersect exactly once.")
        self._diagnostics["initial_route_seconds"] = time.perf_counter() - started
        return SinuousSeamPlan(vertical, horizontal, features, intersections)

    @property
    def search_diagnostics(self) -> dict[str, float | int]:
        """Return a copy of bounded per-run seam-search evidence."""
        return dict(self._diagnostics)

    def candidate_plans(
        self,
        plan: SinuousSeamPlan,
        panel_bounds: tuple[float, float, float, float],
    ) -> tuple[SinuousSeamPlan, ...]:
        """Return bounded route combinations ordered by hidden contour length."""
        started = time.perf_counter()
        verticals = self._path_variants(
            plan.vertical,
            plan.horizontal.nominal_coordinate_mm,
            panel_bounds,
            plan.features,
        )
        horizontals = self._path_variants(
            plan.horizontal,
            plan.vertical.nominal_coordinate_mm,
            panel_bounds,
            plan.features,
        )
        candidates = []
        for vertical in verticals:
            for horizontal in horizontals:
                intersections = _intersection_count(vertical.points, horizontal.points)
                if intersections == 1:
                    candidates.append(
                        SinuousSeamPlan(
                            vertical, horizontal, plan.features, intersections
                        )
                    )
        candidates.sort(
            key=lambda candidate: (
                -candidate.vertical.contour_following_length_mm
                - candidate.horizontal.contour_following_length_mm,
                candidate.vertical.maximum_deviation_mm
                + candidate.horizontal.maximum_deviation_mm,
                candidate.vertical.points,
                candidate.horizontal.points,
            )
        )
        unique = []
        signatures = set()
        for candidate in candidates:
            signature = (candidate.vertical.points, candidate.horizontal.points)
            if signature not in signatures:
                signatures.add(signature)
                unique.append(candidate)
        self._diagnostics["route_candidates_generated"] = len(unique)
        self._diagnostics["route_search_seconds"] = time.perf_counter() - started
        return tuple(unique)

    def topology_shortlist(
        self,
        plan: SinuousSeamPlan,
        panel_bounds: tuple[float, float, float, float],
    ) -> tuple[SinuousSeamPlan, ...]:
        """Return at most five quality-ranked plans for expensive B-rep checks."""
        candidates = self.candidate_plans(plan, panel_bounds)
        if not candidates:
            return ()
        fully_sinuous = tuple(
            candidate for candidate in candidates
            if _meaningfully_sinuous(candidate.vertical)
            and _meaningfully_sinuous(candidate.horizontal)
        )
        if fully_sinuous:
            best = fully_sinuous[0]
            best_vertical = len(best.vertical.followed_feature_ids)
            best_horizontal = len(best.horizontal.followed_feature_ids)
            selected = [best]
            categories = (
                lambda item: (
                    len(item.vertical.followed_feature_ids) < best_vertical
                    and len(item.horizontal.followed_feature_ids) == best_horizontal
                ),
                lambda item: (
                    len(item.vertical.followed_feature_ids) == best_vertical
                    and len(item.horizontal.followed_feature_ids) < best_horizontal
                ),
                lambda item: (
                    len(item.vertical.followed_feature_ids) < best_vertical
                    and len(item.horizontal.followed_feature_ids) < best_horizontal
                ),
            )
            for predicate in categories:
                match = next(
                    (item for item in fully_sinuous if predicate(item)), None
                )
                if match is not None and match not in selected:
                    selected.append(match)
            for candidate in fully_sinuous:
                if candidate not in selected:
                    selected.append(candidate)
                if len(selected) >= 5:
                    break
            shortlist = tuple(selected[:5])
            self._diagnostics["route_candidates_pruned"] = max(
                0, len(candidates) - len(shortlist)
            )
            self._diagnostics["topology_shortlist_count"] = len(shortlist)
            self._diagnostics["straight_fallback_excluded"] = 1
            return shortlist
        best = candidates[0]
        selected = [best]
        categories = (
            lambda item: not item.vertical.followed_feature_ids,
            lambda item: not item.horizontal.followed_feature_ids,
            lambda item: (
                not item.vertical.followed_feature_ids
                and not item.horizontal.followed_feature_ids
            ),
        )
        for predicate in categories:
            match = next((item for item in candidates if predicate(item)), None)
            if match is not None and match not in selected:
                selected.append(match)
        best_coverage = (
            best.vertical.contour_following_length_mm
            + best.horizontal.contour_following_length_mm
        )
        for candidate in candidates[1:]:
            coverage = (
                candidate.vertical.contour_following_length_mm
                + candidate.horizontal.contour_following_length_mm
            )
            if (
                best_coverage - coverage <= self._parameters.coverage_epsilon_mm
                and candidate not in selected
            ):
                selected.append(candidate)
            if len(selected) >= 5:
                break
        shortlist = tuple(selected[:5])
        self._diagnostics["route_candidates_pruned"] = max(
            0, len(candidates) - len(shortlist)
        )
        self._diagnostics["topology_shortlist_count"] = len(shortlist)
        return shortlist

    @staticmethod
    def topology_quality_key(plan: SinuousSeamPlan):
        """Rank locally simplified plans without another exact boolean."""
        return (
            -(
                plan.vertical.contour_following_length_mm
                + plan.horizontal.contour_following_length_mm
            ),
            -(len(plan.vertical.followed_feature_ids)
              + len(plan.horizontal.followed_feature_ids)),
            plan.vertical.longest_straight_segment_mm
            + plan.horizontal.longest_straight_segment_mm,
            plan.vertical.points,
            plan.horizontal.points,
        )

    @staticmethod
    def detour_level(plan: SinuousSeamPlan, detour_id: str) -> int | None:
        for path in (plan.vertical, plan.horizontal):
            for identifier, level in zip(path.detour_ids, path.detour_levels):
                if identifier == detour_id:
                    return level
        return None

    def simplify_detour(
        self,
        plan: SinuousSeamPlan,
        detour_id: str,
        panel_bounds: tuple[float, float, float, float],
    ) -> SinuousSeamPlan | None:
        """Reduce exactly one local detour by one level and reuse the other axis."""
        target = None
        for path in (plan.vertical, plan.horizontal):
            if detour_id in path.detour_ids:
                target = path
                break
        if target is None:
            return None
        levels = dict(zip(target.detour_feature_ids, target.detour_levels))
        index = target.detour_ids.index(detour_id)
        feature_id = target.detour_feature_ids[index]
        current = levels[feature_id]
        if current <= 0:
            return None
        levels[feature_id] = current - 1
        if target.axis == "vertical":
            vertical = self._build_path(
                "vertical", target.nominal_coordinate_mm,
                plan.horizontal.nominal_coordinate_mm,
                panel_bounds, plan.features, levels,
            )
            horizontal = plan.horizontal
        else:
            vertical = plan.vertical
            horizontal = self._build_path(
                "horizontal", target.nominal_coordinate_mm,
                plan.vertical.nominal_coordinate_mm,
                panel_bounds, plan.features, levels,
            )
        intersections = _intersection_count(vertical.points, horizontal.points)
        candidate = SinuousSeamPlan(
            vertical, horizontal, plan.features, intersections
        )
        if (
            intersections != 1
            or not _meaningfully_sinuous(vertical)
            or not _meaningfully_sinuous(horizontal)
        ):
            return None
        return candidate

    def connectivity_repair_candidates(
        self,
        plan: SinuousSeamPlan,
        diagnosis: object,
        panel_bounds: tuple[float, float, float, float],
    ) -> tuple[SinuousSeamPlan, ...]:
        """Return curved one-step reductions for prioritized islands.

        V4.74D deliberately does not restart the global route search. The
        largest structural island is considered first, then nearer islands.
        At most one child per responsible detour is emitted so exact feedback
        drives progressive multi-detour repair without combinatorial search.
        """
        try:
            islands = diagnosis.structural_islands
        except AttributeError:
            return ()
        candidates = []
        handled = set()
        for island in islands:
            detour_id = island.nearest_detour_id
            if not detour_id or detour_id in handled:
                continue
            handled.add(detour_id)
            child = self.simplify_detour(plan, detour_id, panel_bounds)
            if child is None:
                continue
            island_diagnosis = replace(
                diagnosis, components=(diagnosis.main, island)
            )
            if self._connectivity_repair_precheck(
                plan, child, island_diagnosis
            ):
                candidates.append(child)
            if len(candidates) >= self._split_settings.SEAM_BEAM_WIDTH:
                break
        return tuple(candidates)

    def _connectivity_repair_precheck(self, original, candidate, diagnosis):
        """Cheap 2D gate before any OCC ownership ``common()`` operation."""
        secondary = diagnosis.secondary
        target_axis = secondary.nearest_seam
        target_original = getattr(original, target_axis)
        target_candidate = getattr(candidate, target_axis)
        other_axis = "horizontal" if target_axis == "vertical" else "vertical"
        if getattr(original, other_axis) != getattr(candidate, other_axis):
            return False
        if candidate.intersection_count != 1:
            return False
        if target_original.points == target_candidate.points:
            return False
        if not (
            _meaningfully_sinuous(candidate.vertical)
            and _meaningfully_sinuous(candidate.horizontal)
        ):
            return False
        if not all(
            report.original_profile_preserved
            for path in (candidate.vertical, candidate.horizontal)
            for report in path.hole_offset_reports
        ):
            return False
        detour_id = secondary.nearest_detour_id
        if detour_id not in target_candidate.detour_ids:
            return False
        index = target_candidate.detour_ids.index(detour_id)
        feature_id = target_candidate.detour_feature_ids[index]
        feature = next(
            (item for item in candidate.features if item.feature_id == feature_id),
            None,
        )
        if feature is None:
            return False
        xmin, ymin, xmax, ymax = feature.bounds_mm
        travel_center = (
            secondary.centroid_mm[1]
            if target_axis == "vertical"
            else secondary.centroid_mm[0]
        )
        feature_min, feature_max = (
            (ymin, ymax) if target_axis == "vertical" else (xmin, xmax)
        )
        window = float(self._split_settings.CONNECTIVITY_REPAIR_WINDOW_MM)
        return feature_min - window <= travel_center <= feature_max + window

    @staticmethod
    def likely_problem_detours(
        plan: SinuousSeamPlan, macro_result: object
    ) -> tuple[str, ...]:
        """Map the smallest unexpected solids to nearby deterministic detours."""
        feature_bounds = {
            feature.feature_id: feature.bounds_mm for feature in plan.features
        }
        units = []
        for path in (plan.vertical, plan.horizontal):
            units.extend(zip(
                path.detour_ids, path.detour_feature_ids, path.detour_levels
            ))
        active = tuple(item for item in units if item[2] > 0)
        if not active:
            return ()
        try:
            solids = tuple(sorted(
                macro_result.shape.Solids,
                key=lambda solid: float(solid.Volume),
            ))
            unexpected_count = max(1, len(solids) - 4)
            centers = tuple(
                (float(solid.CenterOfMass.x), float(solid.CenterOfMass.y))
                for solid in solids[:unexpected_count]
            )
        except Exception:
            centers = ()

        def rectangle_distance(center, bounds):
            x, y = center
            xmin, ymin, xmax, ymax = bounds
            return math.hypot(
                max(xmin - x, 0.0, x - xmax),
                max(ymin - y, 0.0, y - ymax),
            )

        ranked = []
        for detour_id, feature_id, level in active:
            bounds = feature_bounds.get(feature_id)
            proximity = min(
                (rectangle_distance(center, bounds) for center in centers),
                default=math.inf,
            ) if bounds is not None else math.inf
            ranked.append((proximity, -level, detour_id))
        return tuple(item[2] for item in sorted(ranked))

    def _path_variants(self, primary, center_other, panel_bounds, features):
        """Build a bounded set of cached-feature routes from complex to straight."""
        axis = primary.axis
        full = self._build_path(
            axis,
            primary.nominal_coordinate_mm,
            center_other,
            panel_bounds,
            features,
        )
        variants = [full, primary]
        followed = set(full.followed_feature_ids)
        for feature_id in sorted(followed):
            subset = tuple(
                feature for feature in features if feature.feature_id != feature_id
            )
            variants.append(
                self._build_path(
                    axis,
                    full.nominal_coordinate_mm,
                    center_other,
                    panel_bounds,
                    subset,
                )
            )
        if followed:
            remaining = tuple(
                feature for feature in features if feature.feature_id not in followed
            )
            if remaining:
                variants.append(
                    self._build_path(
                        axis,
                        full.nominal_coordinate_mm,
                        center_other,
                        panel_bounds,
                        remaining,
                    )
                )
        variants.append(
            self._straight_path(axis, primary.nominal_coordinate_mm, panel_bounds)
        )
        unique = {}
        for path in variants:
            unique.setdefault(path.points, path)
        return tuple(sorted(
            unique.values(),
            key=lambda path: (
                -path.contour_following_length_mm,
                path.maximum_deviation_mm,
                path.points,
            ),
        )[: min(
            self._parameters.maximum_variants_per_axis,
            self._parameters.beam_width,
        )])

    def _extract_features(
        self, source_shape: object, zmax: float
    ) -> tuple[BoundaryFeature2D, ...]:
        """Sample inner wires of the largest horizontal top planar face."""
        candidates = []
        try:
            for face_index, face in enumerate(source_shape.Faces, start=1):
                box = face.BoundBox
                if (
                    abs(float(box.ZMin) - zmax) > _COORDINATE_TOLERANCE_MM
                    or abs(float(box.ZMax) - zmax) > _COORDINATE_TOLERANCE_MM
                    or type(face.Surface).__name__ != "Plane"
                    or len(face.Wires) <= 1
                ):
                    continue
                candidates.append((float(face.Area), face_index, face))
        except Exception as error:
            raise SplitOperationError("Unable to inspect top-view opening wires.") from error
        if not candidates:
            return ()
        _, _, top_face = max(candidates, key=lambda item: (item[0], -item[1]))
        wires = tuple(top_face.Wires)
        outer_index = max(
            range(len(wires)), key=lambda index: (float(wires[index].Length), -index)
        )
        raw = []
        for wire_index, wire in enumerate(wires, start=1):
            if wire_index - 1 == outer_index:
                continue
            try:
                box = wire.BoundBox
                size_x = float(box.XLength)
                size_y = float(box.YLength)
                perimeter = float(wire.Length)
                if max(size_x, size_y) < self._parameters.minimum_feature_size_mm:
                    continue
                points = self._sample_wire(wire)
                if len(points) < 3:
                    continue
                signature = (
                    round(float(box.XMin), 6), round(float(box.YMin), 6),
                    round(float(box.XMax), 6), round(float(box.YMax), 6),
                    round(perimeter, 6), wire_index,
                )
                raw.append((signature, wire_index, points, perimeter))
            except Exception:
                continue
        features = []
        for index, (signature, wire_index, points, perimeter) in enumerate(
            sorted(raw, key=lambda item: item[0]), start=1
        ):
            features.append(
                BoundaryFeature2D(
                    feature_id=f"boundary:wire:{index:04d}",
                    source_wire_index=wire_index,
                    points=points,
                    bounds_mm=(signature[0], signature[1], signature[2], signature[3]),
                    perimeter_mm=perimeter,
                )
            )
        return tuple(features)

    def _sample_wire(self, wire: object) -> tuple[Point2D, ...]:
        """Adaptively sample curved regions and compact nearly straight runs."""
        try:
            values = wire.discretize(
                Deflection=self._parameters.boundary_deflection_mm
            )
        except Exception:
            values = wire.discretize(Number=48)
        points = []
        for value in values:
            point = Point2D(float(value.x), float(value.y))
            if not points or _distance(points[-1], point) > _COORDINATE_TOLERANCE_MM:
                points.append(point)
        if len(points) > 1 and _distance(points[0], points[-1]) <= _COORDINATE_TOLERANCE_MM:
            points.pop()
        if len(points) < 3:
            return ()
        canonical = _canonical_cycle(tuple(points))
        if _maximum_cycle_turn_deg(canonical) >= 8.0:
            try:
                finer = wire.discretize(
                    Deflection=self._parameters.boundary_deflection_mm / 2.0
                )
                dense = _deduplicate(tuple(
                    Point2D(float(value.x), float(value.y)) for value in finer
                ))
                if len(dense) > 1 and _distance(dense[0], dense[-1]) <= _COORDINATE_TOLERANCE_MM:
                    dense = dense[:-1]
                if len(dense) >= 3:
                    canonical = _canonical_cycle(dense)
            except Exception:
                pass
        return _adaptive_simplify_closed(
            canonical, self._parameters.boundary_simplification_mm
        )

    def _build_path(
        self,
        axis: str,
        nominal: float,
        center_other: float,
        panel_bounds: tuple[float, float, float, float],
        features: tuple[BoundaryFeature2D, ...],
        detour_levels_by_feature: dict[str, int] | None = None,
    ) -> SeamPath2D:
        """Choose a few non-overlapping deterministic boundary detours."""
        xmin, xmax, ymin, ymax = panel_bounds
        travel_min, travel_max = (ymin, ymax) if axis == "vertical" else (xmin, xmax)
        cross_min, cross_max = (xmin, xmax) if axis == "vertical" else (ymin, ymax)
        configured_limit = float(
            self._split_settings.MAX_PART_WIDTH
            if axis == "vertical"
            else self._split_settings.MAX_PART_HEIGHT
        )
        allowed_min = cross_max - configured_limit
        allowed_max = cross_min + configured_limit
        ranked = []
        for feature in features:
            cache_key = (
                feature.feature_id, axis, round(nominal, 9),
                round(center_other, 9), round(allowed_min, 9),
                round(allowed_max, 9),
            )
            if cache_key in self._detour_cache:
                detour = self._detour_cache[cache_key]
                self._diagnostics["detour_cache_hits"] = (
                    self._diagnostics.get("detour_cache_hits", 0) + 1
                )
            else:
                detour = self._feature_detour(
                    feature, axis, nominal, center_other, allowed_min, allowed_max
                )
                self._detour_cache[cache_key] = detour
            if detour is not None:
                boundary_distance, travel_span, interval, chain, report = detour
                ranked.append(
                    (
                        -report.followed_contour_length_mm,
                        boundary_distance,
                        feature.feature_id,
                        interval,
                        chain,
                        feature,
                        report,
                    )
                )
        selected = []
        for item in sorted(ranked):
            chain = item[4]
            chain_interval = (
                chain[0].y_mm if axis == "vertical" else chain[0].x_mm,
                chain[-1].y_mm if axis == "vertical" else chain[-1].x_mm,
            )
            if any(
                not (
                    chain_interval[1]
                    < (chosen[4][0].y_mm if axis == "vertical" else chosen[4][0].x_mm)
                    or chain_interval[0]
                    > (chosen[4][-1].y_mm if axis == "vertical" else chosen[4][-1].x_mm)
                )
                for chosen in selected
            ):
                continue
            selected.append(item)
            if len(selected) >= self._parameters.maximum_features_per_seam:
                break
        selected.sort(key=lambda item: item[3][0])
        prefix = "VDET" if axis == "vertical" else "HDET"
        detour_units = tuple(
            (
                f"{prefix}_{index:03d}",
                item[5].feature_id,
                max(0, min(3, int(
                    (detour_levels_by_feature or {}).get(item[5].feature_id, 3)
                ))),
            )
            for index, item in enumerate(selected, start=1)
        )
        level_by_feature = {
            feature_id: level for _detour_id, feature_id, level in detour_units
        }
        adjusted = []
        for item in selected:
            level = level_by_feature[item[5].feature_id]
            if level == 0:
                continue
            if level < 3:
                fraction = 0.70 if level == 2 else 0.35
                shortened = _central_polyline_portion(item[4], fraction, axis)
                if len(shortened) < 2:
                    continue
                report = replace(
                    item[6],
                    followed_contour_length_mm=_polyline_length(shortened),
                )
                item = item[:4] + (shortened, item[5], report)
            adjusted.append(item)
        assembled = self._assemble_feature_route(
            adjusted, axis, nominal, center_other, travel_min, travel_max
        )
        if assembled is None:
            key = f"{axis}_assembly_fallbacks"
            self._diagnostics[key] = self._diagnostics.get(key, 0) + 1
            return self._straight_path(axis, nominal, panel_bounds)
        (
            raw_points, smoothed_points, followed, followed_bounds,
            offset_reports, contour_following_length, transition_count,
            artificial_before, artificial_after,
        ) = assembled
        raw_compact = _deduplicate(tuple(raw_points))
        compact = _clean_open_path(
            tuple(smoothed_points),
            min(self._parameters.path_simplify_tolerance_mm, 0.20),
            self._parameters.maximum_artificial_turn_deg,
        )
        if not _strictly_monotone(compact, axis) or _self_intersects(compact):
            key = f"{axis}_geometry_fallbacks"
            self._diagnostics[key] = self._diagnostics.get(key, 0) + 1
            return self._straight_path(axis, nominal, panel_bounds)
        path_length = _polyline_length(compact)
        return SeamPath2D(
            axis=axis,
            nominal_coordinate_mm=nominal,
            points=compact,
            followed_feature_ids=tuple(followed),
            followed_feature_bounds_mm=tuple(followed_bounds),
            path_length_mm=path_length,
            maximum_deviation_mm=max(
                abs((point.x_mm if axis == "vertical" else point.y_mm) - nominal)
                for point in compact
            ),
            segment_count_before_cleanup=max(0, len(raw_compact) - 1),
            segment_count_after_cleanup=max(0, len(compact) - 1),
            smoothing_transition_count=transition_count,
            maximum_artificial_turn_before_deg=max(artificial_before, default=0.0),
            maximum_artificial_turn_after_deg=max(artificial_after, default=0.0),
            hole_offset_reports=tuple(offset_reports),
            contour_following_length_mm=contour_following_length,
            contour_following_ratio=(
                contour_following_length / path_length if path_length > 0.0 else 0.0
            ),
            longest_straight_segment_mm=max(
                (_distance(first, second)
                 for first, second in zip(compact, compact[1:])),
                default=0.0,
            ),
            detour_ids=tuple(item[0] for item in detour_units),
            detour_feature_ids=tuple(item[1] for item in detour_units),
            detour_levels=tuple(item[2] for item in detour_units),
        )

    def _assemble_feature_route(
        self, selected, axis, nominal, center_other, travel_min, travel_max
    ):
        """Join successive contours directly, using the nominal line only as fallback."""
        start = self._point(axis, nominal, travel_min)
        raw = [start]
        smoothed = [start]
        accepted = []
        artificial_before = []
        artificial_after = []
        transition_count = 0
        axis_tangent = self._axis_tangent(axis)
        previous_chain = None
        for item in selected:
            interval, chain = item[3], item[4]
            entry_tangent = _unit_direction(chain[0], chain[1])
            if previous_chain is None:
                entry = self._point(
                    axis, nominal, max(travel_min, interval[0])
                )
                curve = self._smooth_transition(
                    entry, chain[0], axis_tangent, entry_tangent, axis
                )
                if curve is None and _distance(entry, start) > _COORDINATE_TOLERANCE_MM:
                    # A feature close to the panel edge can leave too little
                    # run for its steep contour tangent.  Use the available
                    # edge-to-feature distance as the deterministic curved
                    # approach instead of discarding the whole sinuous axis.
                    entry = start
                    curve = self._smooth_transition(
                        entry, chain[0], axis_tangent, entry_tangent, axis
                    )
                if curve is None:
                    continue
                smoothed.append(entry)
                smoothed.extend(curve)
                raw.extend((entry, chain[0]))
                artificial_before.extend((
                    _turn_angle_deg(axis_tangent, _unit_direction(entry, chain[0])),
                    _turn_angle_deg(_unit_direction(entry, chain[0]), entry_tangent),
                ))
                artificial_after.extend(
                    _transition_curve_angles((entry,) + curve, axis_tangent, entry_tangent)
                )
                transition_count += 1
            else:
                exit_tangent = _unit_direction(previous_chain[-2], previous_chain[-1])
                bridge = self._hole_to_hole_bridge(
                    accepted[-1], item, axis, nominal, center_other
                )
                if bridge is not None:
                    bridge_points, bridge_raw, bridge_turns = bridge
                    smoothed.extend(bridge_points)
                    raw.extend(bridge_raw)
                    artificial_after.extend(bridge_turns)
                    transition_count += 2
                else:
                    curve = self._smooth_transition(
                        previous_chain[-1], chain[0], exit_tangent,
                        entry_tangent, axis,
                    )
                    if curve is None:
                        continue
                    smoothed.extend(curve)
                    raw.append(chain[0])
                    artificial_before.extend((
                        _turn_angle_deg(
                            exit_tangent,
                            _unit_direction(previous_chain[-1], chain[0]),
                        ),
                        _turn_angle_deg(
                            _unit_direction(previous_chain[-1], chain[0]),
                            entry_tangent,
                        ),
                    ))
                    artificial_after.extend(
                        _transition_curve_angles(
                            (previous_chain[-1],) + curve,
                            exit_tangent,
                            entry_tangent,
                        )
                    )
                    transition_count += 1
            smoothed.extend(chain[1:])
            raw.extend(chain[1:])
            accepted.append(item)
            previous_chain = chain
        if not accepted:
            final = self._point(axis, nominal, travel_max)
            return (
                [start, final], [start, final], [], [], [], 0.0, 0, [], []
            )
        interval, chain = accepted[-1][3], accepted[-1][4]
        exit_point = self._point(axis, nominal, min(travel_max, interval[1]))
        exit_tangent = _unit_direction(chain[-2], chain[-1])
        exit_curve = self._smooth_transition(
            chain[-1], exit_point, exit_tangent, axis_tangent, axis
        )
        if exit_curve is None:
            travel = lambda point: point.y_mm if axis == "vertical" else point.x_mm
            cross = lambda point: point.x_mm if axis == "vertical" else point.y_mm
            remaining = travel_max - travel(chain[-1])
            run = min(
                self._parameters.approach_length_mm
                + 3.0 * accepted[-1][6].maximum_offset_mm,
                remaining / 3.0,
            )
            guide = 0.5 * (cross(chain[-1]) + nominal)
            first_anchor = self._point(
                axis, guide, travel(chain[-1]) + run
            )
            second_anchor = self._point(
                axis, nominal, travel(chain[-1]) + 2.0 * run
            )
            first_curve = self._smooth_transition(
                chain[-1], first_anchor, exit_tangent, axis_tangent, axis
            )
            second_curve = self._smooth_transition(
                first_anchor, second_anchor, axis_tangent, axis_tangent, axis
            )
            if first_curve is None or second_curve is None:
                return None
            smoothed.extend(first_curve)
            smoothed.extend(second_curve)
            exit_curve = first_curve + second_curve
            raw.extend((first_anchor, second_anchor))
            transition_count += 2
        else:
            smoothed.extend(exit_curve)
            raw.append(exit_point)
            transition_count += 1
        final = self._point(axis, nominal, travel_max)
        smoothed.append(final)
        raw.append(final)
        artificial_before.extend((
            _turn_angle_deg(exit_tangent, _unit_direction(chain[-1], exit_point)),
            _turn_angle_deg(_unit_direction(chain[-1], exit_point), axis_tangent),
        ))
        artificial_after.extend(
            _transition_curve_angles(
                (chain[-1],) + exit_curve, exit_tangent, axis_tangent
            )
        )
        return (
            raw,
            smoothed,
            [item[5].feature_id for item in accepted],
            [item[5].bounds_mm for item in accepted],
            [item[6] for item in accepted],
            sum(_polyline_length(item[4]) for item in accepted),
            transition_count,
            artificial_before,
            artificial_after,
        )

    def _hole_to_hole_bridge(
        self, previous_item, item, axis, nominal, center_other
    ):
        """Join contours through a displaced guide, without returning to nominal."""
        previous_chain, chain = previous_item[4], item[4]
        travel = lambda point: point.y_mm if axis == "vertical" else point.x_mm
        cross = lambda point: point.x_mm if axis == "vertical" else point.y_mm
        gap = travel(chain[0]) - travel(previous_chain[-1])
        if gap <= _COORDINATE_TOLERANCE_MM:
            return None
        if (
            travel(previous_chain[-1]) < center_other
            < travel(chain[0])
        ):
            # Opposite branch features must meet the other seam at one shared,
            # deterministic nominal point.  Two Hermite curves keep this long
            # central connection flowing while preventing the independently
            # bowed axis bridges from producing extra intersections.
            center = self._point(axis, nominal, center_other)
            exit_tangent = _unit_direction(
                previous_chain[-2], previous_chain[-1]
            )
            entry_tangent = _unit_direction(chain[0], chain[1])
            first_curve = self._smooth_transition(
                previous_chain[-1], center, exit_tangent,
                self._axis_tangent(axis), axis,
            )
            second_curve = self._smooth_transition(
                center, chain[0], self._axis_tangent(axis),
                entry_tangent, axis,
            )
            if first_curve is None or second_curve is None:
                return None
            turns = (
                _transition_curve_angles(
                    (previous_chain[-1],) + first_curve,
                    exit_tangent, self._axis_tangent(axis),
                )
                + _transition_curve_angles(
                    (center,) + second_curve,
                    self._axis_tangent(axis), entry_tangent,
                )
            )
            return (
                first_curve + second_curve,
                (center, chain[0]),
                turns,
            )
        maximum_offset = max(
            previous_item[6].maximum_offset_mm,
            item[6].maximum_offset_mm,
        )
        run = min(
            self._parameters.approach_length_mm + 3.0 * maximum_offset,
            gap / 3.0,
        )
        guide = 0.5 * (cross(previous_chain[-1]) + cross(chain[0]))
        # Equal endpoints can occasionally put the guide back on nominal. A small,
        # deterministic bias keeps the route attached to the followed-hole side.
        if abs(guide - nominal) <= _COORDINATE_TOLERANCE_MM:
            deviations = (
                cross(previous_chain[-1]) - nominal,
                cross(chain[0]) - nominal,
            )
            guide = nominal + max(deviations, key=lambda value: (abs(value), value))
        first_anchor = self._point(axis, guide, travel(previous_chain[-1]) + run)
        second_anchor = self._point(axis, guide, travel(chain[0]) - run)
        exit_tangent = _unit_direction(previous_chain[-2], previous_chain[-1])
        entry_tangent = _unit_direction(chain[0], chain[1])
        first_curve = self._smooth_transition(
            previous_chain[-1], first_anchor, exit_tangent,
            self._axis_tangent(axis), axis,
        )
        second_curve = self._smooth_transition(
            second_anchor, chain[0], self._axis_tangent(axis),
            entry_tangent, axis,
        )
        midpoint_travel = 0.5 * (
            travel(first_anchor) + travel(second_anchor)
        )
        sign = 1.0 if guide >= nominal else -1.0
        outward_room = max(
            0.0,
            self._parameters.search_corridor_mm - abs(guide - nominal),
        )
        bow = min(28.0, gap * 0.12, outward_room)
        if bow <= _COORDINATE_TOLERANCE_MM:
            sign = -sign
            bow = min(28.0, gap * 0.12, abs(guide - nominal))
        midpoint = self._point(axis, guide + sign * bow, midpoint_travel)
        middle_first = self._smooth_transition(
            first_anchor, midpoint, self._axis_tangent(axis),
            self._axis_tangent(axis), axis,
        )
        middle_second = self._smooth_transition(
            midpoint, second_anchor, self._axis_tangent(axis),
            self._axis_tangent(axis), axis,
        )
        if (
            first_curve is None or second_curve is None
            or middle_first is None or middle_second is None
        ):
            return None
        points = first_curve + middle_first + middle_second + second_curve
        turns = (
            _transition_curve_angles(
                (previous_chain[-1],) + first_curve,
                exit_tangent,
                self._axis_tangent(axis),
            )
            + _transition_curve_angles(
                (second_anchor,) + second_curve,
                self._axis_tangent(axis),
                entry_tangent,
            )
        )
        return points, (first_anchor, midpoint, second_anchor, chain[0]), turns

    def _smooth_transition(
        self, first, last, first_tangent, last_tangent, axis
    ) -> tuple[Point2D, ...]:
        """Return a monotone sampled cubic transition excluding its first point."""
        cache_key = (first, last, first_tangent, last_tangent, axis)
        if cache_key in self._transition_cache:
            self._diagnostics["transition_cache_hits"] = (
                self._diagnostics.get("transition_cache_hits", 0) + 1
            )
            return self._transition_cache[cache_key]
        chord = _distance(first, last)
        if chord <= _COORDINATE_TOLERANCE_MM:
            self._transition_cache[cache_key] = (last,)
            return (last,)
        for tangent_factor in (0.5, 0.35, 0.2, 0.1):
            derivative_scale = chord * tangent_factor
            minimum_subdivisions = max(4, int(math.ceil(chord / 20.0)))
            for subdivisions in tuple(sorted({
                minimum_subdivisions,
                max(8, minimum_subdivisions),
                max(16, minimum_subdivisions),
                max(32, minimum_subdivisions),
            })):
                points = [first]
                for index in range(1, subdivisions + 1):
                    value = index / subdivisions
                    h00 = 2.0 * value ** 3 - 3.0 * value ** 2 + 1.0
                    h10 = value ** 3 - 2.0 * value ** 2 + value
                    h01 = -2.0 * value ** 3 + 3.0 * value ** 2
                    h11 = value ** 3 - value ** 2
                    points.append(
                        Point2D(
                            h00 * first.x_mm
                            + h10 * derivative_scale * first_tangent[0]
                            + h01 * last.x_mm
                            + h11 * derivative_scale * last_tangent[0],
                            h00 * first.y_mm
                            + h10 * derivative_scale * first_tangent[1]
                            + h01 * last.y_mm
                            + h11 * derivative_scale * last_tangent[1],
                        )
                    )
                candidate = tuple(points)
                directions = tuple(
                    _unit_direction(one, two)
                    for one, two in zip(candidate, candidate[1:])
                )
                turn_angles = (
                    (_turn_angle_deg(first_tangent, directions[0]),)
                    + tuple(
                        _turn_angle_deg(one, two)
                        for one, two in zip(directions, directions[1:])
                    )
                    + (_turn_angle_deg(directions[-1], last_tangent),)
                )
                if _strictly_monotone(candidate, axis) and max(turn_angles) <= (
                    self._parameters.maximum_artificial_turn_deg
                ):
                    self._transition_cache[cache_key] = candidate[1:]
                    return candidate[1:]
        self._transition_cache[cache_key] = None
        return None

    @staticmethod
    def _axis_tangent(axis):
        return (0.0, 1.0) if axis == "vertical" else (1.0, 0.0)

    @staticmethod
    def _transition_turns(curve, following, preceding):
        points = tuple(curve)
        directions = [preceding]
        if len(points) >= 2:
            directions.extend(
                _unit_direction(first, second)
                for first, second in zip(points, points[1:])
            )
        if following is not None and points:
            directions.append(_unit_direction(points[-1], following))
        return tuple(
            _turn_angle_deg(first, second)
            for first, second in zip(directions, directions[1:])
        )

    def _feature_detour(
        self, feature, axis, nominal, center_other, allowed_min, allowed_max
    ):
        xmin, ymin, xmax, ymax = feature.bounds_mm
        cross_bounds = (xmin, xmax) if axis == "vertical" else (ymin, ymax)
        travel_bounds = (ymin, ymax) if axis == "vertical" else (xmin, xmax)
        boundary_distance = max(
            cross_bounds[0] - nominal, 0.0, nominal - cross_bounds[1]
        )
        feature_travel_span = travel_bounds[1] - travel_bounds[0]
        if (
            boundary_distance > self._parameters.search_corridor_mm
            or feature_travel_span < self._parameters.minimum_feature_size_mm
        ):
            return None
        chain = self._nearest_monotone_chain(
            feature.points, axis, nominal, allowed_min, allowed_max
        )
        if not chain:
            return None
        offset_result = self._offset_chain_into_opening(chain, feature, axis)
        if offset_result is None:
            offset_result = self._longest_safe_offset_portion(
                chain, feature, axis
            )
        if offset_result is None:
            return None
        chain, offset_report = offset_result
        if (
            offset_report.followed_contour_length_mm
            < self._parameters.minimum_follow_length_mm
            - _COORDINATE_TOLERANCE_MM
        ):
            return None
        chain_travel = tuple(
            point.y_mm if axis == "vertical" else point.x_mm for point in chain
        )
        travel_span = chain_travel[-1] - chain_travel[0]
        if (
            travel_span < self._parameters.minimum_feature_size_mm
            or not (
                chain_travel[-1] < center_other - self._parameters.center_exclusion_mm
                or chain_travel[0] > center_other + self._parameters.center_exclusion_mm
            )
        ):
            return None
        cross_values = tuple(
            point.x_mm if axis == "vertical" else point.y_mm for point in chain
        )
        if (
            max(abs(value - nominal) for value in cross_values)
            > self._parameters.search_corridor_mm
            or min(cross_values) < allowed_min
            or max(cross_values) > allowed_max
        ):
            return None
        # The offset contour needs enough run for its tangent transition to
        # cross the opening edge cleanly without isolating a microscopic wedge.
        transition_run = (
            self._parameters.approach_length_mm
            + 3.0 * offset_report.final_offset_mm
        )
        interval = (
            chain_travel[0] - transition_run,
            chain_travel[-1] + transition_run,
        )
        return boundary_distance, travel_span, interval, chain, offset_report

    def _longest_safe_offset_portion(self, chain, feature, axis):
        """Keep the longest safe contiguous portion when a tight end collapses."""
        candidates = []
        for first in range(len(chain) - 1):
            for last in range(first + 2, len(chain) + 1):
                portion = tuple(chain[first:last])
                length = _polyline_length(portion)
                if length + _COORDINATE_TOLERANCE_MM < (
                    self._parameters.minimum_follow_length_mm
                ):
                    continue
                candidates.append((
                    -length,
                    first,
                    -last,
                    portion,
                ))
        for _, _, _, portion in sorted(candidates):
            result = self._offset_chain_into_opening(portion, feature, axis)
            if result is not None:
                return result
        return None

    def _offset_chain_into_opening(self, chain, feature, axis):
        """Move only a followed contour chain beyond the visible cutter envelope."""
        from .MacroSplitCore import MacroGrooveParameters

        profile = MacroGrooveParameters()
        interiors = []
        envelopes = []
        sides = []
        for first, second in zip(chain, chain[1:]):
            tangent = _unit_direction(first, second)
            normals = ((-tangent[1], tangent[0]), (tangent[1], -tangent[0]))
            point = Point2D(
                (first.x_mm + second.x_mm) / 2.0,
                (first.y_mm + second.y_mm) / 2.0,
            )
            interior = next(
                (
                    normal
                    for probe in (0.05, 0.25, 0.5, 1.0)
                    for normal in normals
                    if _point_in_polygon(
                        Point2D(
                            point.x_mm + normal[0] * probe,
                            point.y_mm + normal[1] * probe,
                        ),
                        feature.points,
                    )
                ),
                None,
            )
            if interior is None:
                return None
            canonical = (
                (tangent[1], -tangent[0])
                if axis == "vertical"
                else (-tangent[1], tangent[0])
            )
            envelope = _material_side_cutter_envelope_mm(
                interior, canonical, profile
            )
            interiors.append(interior)
            envelopes.append(envelope)
            sides.append(1 if _dot(interior, canonical) >= 0.0 else -1)

        theoretical = max(envelopes)
        required = theoretical + self._parameters.hole_clearance_mm
        for step in range(41):
            final_offset = required + step * 0.05
            shifted = _offset_feature_chain(chain, feature.points, final_offset)
            samples = _polyline_samples(shifted, 4)
            if all(_point_in_polygon(point, feature.points) for point in samples):
                clearances = tuple(
                    _point_closed_polyline_distance(point, feature.points)
                    - theoretical
                    for point in samples
                )
                if min(clearances, default=-math.inf) >= (
                    self._parameters.hole_clearance_mm
                    - _COORDINATE_TOLERANCE_MM
                ):
                    side = (
                        "positive cutter normal"
                        if all(value > 0 for value in sides)
                        else "negative cutter normal"
                        if all(value < 0 for value in sides)
                        else "locally varying cutter normal"
                    )
                    return shifted, HoleOffsetReport(
                        feature.feature_id,
                        feature.bounds_mm,
                        side,
                        theoretical,
                        self._parameters.hole_clearance_mm,
                        final_offset,
                        min(clearances),
                        followed_contour_length_mm=_polyline_length(shifted),
                        direction_used=_chain_direction(chain, feature.points),
                        minimum_offset_mm=final_offset,
                        maximum_offset_mm=final_offset,
                        average_offset_mm=final_offset,
                        original_profile_preserved=(
                            min(clearances)
                            >= self._parameters.hole_clearance_mm
                            - _COORDINATE_TOLERANCE_MM
                        ),
                    )
        return None

    def _nearest_monotone_chain(
        self, points: tuple[Point2D, ...], axis: str, nominal: float,
        allowed_min: float = -math.inf, allowed_max: float = math.inf,
    ) -> tuple[Point2D, ...]:
        """Return the useful monotone boundary run nearest the nominal seam."""
        travel = lambda point: point.y_mm if axis == "vertical" else point.x_mm
        cross = lambda point: point.x_mm if axis == "vertical" else point.y_mm
        valid = []
        for oriented in (points, tuple(reversed(points))):
            doubled = oriented + oriented
            for start in range(len(oriented)):
                chain = [doubled[start]]
                if not allowed_min <= cross(chain[0]) <= allowed_max:
                    continue
                for index in range(start + 1, start + len(oriented)):
                    point = doubled[index]
                    if (
                        travel(point) <= travel(chain[-1]) + _COORDINATE_TOLERANCE_MM
                        or not allowed_min <= cross(point) <= allowed_max
                        or abs(cross(point) - nominal) > self._parameters.search_corridor_mm
                    ):
                        break
                    chain.append(point)
                if len(chain) < 2:
                    continue
                simplified = _adaptive_simplify_open(
                    tuple(chain), self._parameters.boundary_simplification_mm
                )
                span = travel(simplified[-1]) - travel(simplified[0])
                if span < self._parameters.minimum_feature_size_mm:
                    continue
                valid.append(
                    (
                        -_polyline_length(simplified),
                        -span,
                        max(abs(cross(point) - nominal) for point in simplified),
                        tuple((round(point.x_mm, 9), round(point.y_mm, 9)) for point in simplified),
                        simplified,
                    )
                )
        return min(valid)[4] if valid else ()

    @staticmethod
    def _point(axis: str, cross: float, travel: float) -> Point2D:
        return Point2D(cross, travel) if axis == "vertical" else Point2D(travel, cross)

    @staticmethod
    def _straight_path(axis, nominal, panel_bounds):
        xmin, xmax, ymin, ymax = panel_bounds
        points = (
            (Point2D(nominal, ymin), Point2D(nominal, ymax))
            if axis == "vertical"
            else (Point2D(xmin, nominal), Point2D(xmax, nominal))
        )
        return SeamPath2D(
            axis,
            nominal,
            points,
            (),
            (),
            _polyline_length(points),
            0.0,
            segment_count_before_cleanup=1,
            segment_count_after_cleanup=1,
            longest_straight_segment_mm=_polyline_length(points),
        )

    @staticmethod
    def _finite(value: object) -> float:
        try:
            result = float(value)
        except (TypeError, ValueError) as error:
            raise SplitOperationError("Seam offset must be finite.") from error
        if not math.isfinite(result):
            raise SplitOperationError("Seam offset must be finite.")
        return result

    @staticmethod
    def _validated_parameters(parameters):
        if not isinstance(parameters, SinuousSeamParameters):
            raise SplitOperationError("Invalid sinuous seam parameters.")
        numeric = (
            parameters.search_corridor_mm,
            parameters.center_exclusion_mm,
            parameters.minimum_feature_size_mm,
            parameters.boundary_deflection_mm,
            parameters.boundary_simplification_mm,
            parameters.path_simplify_tolerance_mm,
            parameters.maximum_artificial_turn_deg,
            parameters.approach_length_mm,
            parameters.hole_clearance_mm,
            parameters.minimum_follow_length_mm,
            parameters.coverage_epsilon_mm,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in numeric):
            raise SplitOperationError("Sinuous seam parameters must be positive.")
        if parameters.maximum_features_per_seam < 1:
            raise SplitOperationError("At least one seam feature must be allowed.")
        if parameters.maximum_variants_per_axis < 1:
            raise SplitOperationError("At least one seam route variant is required.")
        if parameters.beam_width < 1:
            raise SplitOperationError("Seam beam width must be positive.")
        return parameters


def _distance(first: Point2D, second: Point2D) -> float:
    return math.hypot(first.x_mm - second.x_mm, first.y_mm - second.y_mm)


def _meaningfully_sinuous(path: SeamPath2D) -> bool:
    """Require a followed feature, lateral deviation, and multiple turns."""
    if not path.followed_feature_ids or path.maximum_deviation_mm <= 0.5:
        return False
    directions = tuple(
        _unit_direction(first, second)
        for first, second in zip(path.points, path.points[1:])
    )
    changes = sum(
        _turn_angle_deg(first, second) > 1.0
        for first, second in zip(directions, directions[1:])
    )
    return changes > 1


def _unit_direction(first: Point2D, second: Point2D) -> tuple[float, float]:
    length = _distance(first, second)
    if length <= _COORDINATE_TOLERANCE_MM:
        return (0.0, 0.0)
    return (
        (second.x_mm - first.x_mm) / length,
        (second.y_mm - first.y_mm) / length,
    )


def _turn_angle_deg(first, second) -> float:
    first_length = math.hypot(*first)
    second_length = math.hypot(*second)
    if first_length <= _COORDINATE_TOLERANCE_MM or second_length <= _COORDINATE_TOLERANCE_MM:
        return 0.0
    cosine = max(
        -1.0,
        min(
            1.0,
            (first[0] * second[0] + first[1] * second[1])
            / (first_length * second_length),
        ),
    )
    return math.degrees(math.acos(cosine))


def _maximum_turn_deg(points: tuple[Point2D, ...]) -> float:
    return max(
        (
            _turn_angle_deg(
                _unit_direction(points[index - 1], points[index]),
                _unit_direction(points[index], points[index + 1]),
            )
            for index in range(1, len(points) - 1)
        ),
        default=0.0,
    )


def _transition_curve_angles(points, first_tangent, last_tangent):
    directions = tuple(
        _unit_direction(first, second)
        for first, second in zip(points, points[1:])
    )
    if not directions:
        return (_turn_angle_deg(first_tangent, last_tangent),)
    return (
        (_turn_angle_deg(first_tangent, directions[0]),)
        + tuple(
            _turn_angle_deg(first, second)
            for first, second in zip(directions, directions[1:])
        )
        + (_turn_angle_deg(directions[-1], last_tangent),)
    )


def _polyline_length(points: tuple[Point2D, ...]) -> float:
    return sum(_distance(points[index], points[index + 1]) for index in range(len(points) - 1))


def _central_polyline_portion(points, fraction, axis):
    """Return a deterministic central arc-length portion of one detour."""
    if len(points) < 2:
        return tuple(points)
    total = _polyline_length(points)
    if total <= _COORDINATE_TOLERANCE_MM:
        return tuple(points)
    fraction = max(0.05, min(1.0, float(fraction)))
    start_distance = 0.5 * total * (1.0 - fraction)
    end_distance = total - start_distance

    def point_at(distance):
        traversed = 0.0
        for first, second in zip(points, points[1:]):
            length = _distance(first, second)
            if traversed + length >= distance - _COORDINATE_TOLERANCE_MM:
                ratio = 0.0 if length <= 0.0 else (distance - traversed) / length
                ratio = max(0.0, min(1.0, ratio))
                return Point2D(
                    first.x_mm + ratio * (second.x_mm - first.x_mm),
                    first.y_mm + ratio * (second.y_mm - first.y_mm),
                )
            traversed += length
        return points[-1]

    result = [point_at(start_distance)]
    traversed = 0.0
    for first, second in zip(points, points[1:]):
        traversed += _distance(first, second)
        if start_distance < traversed < end_distance:
            result.append(second)
    result.append(point_at(end_distance))
    compact = _deduplicate(tuple(result))
    if not _strictly_monotone(compact, axis):
        return ()
    return compact


def _canonical_cycle(points: tuple[Point2D, ...]) -> tuple[Point2D, ...]:
    variants = []
    for oriented in (points, tuple(reversed(points))):
        for offset in range(len(oriented)):
            rotated = oriented[offset:] + oriented[:offset]
            signature = tuple((round(p.x_mm, 9), round(p.y_mm, 9)) for p in rotated)
            variants.append((signature, rotated))
    return min(variants, key=lambda item: item[0])[1]


def _point_segment_distance(point, first, second):
    dx, dy = second.x_mm - first.x_mm, second.y_mm - first.y_mm
    denominator = dx * dx + dy * dy
    if denominator <= 0.0:
        return _distance(point, first)
    factor = max(0.0, min(1.0, ((point.x_mm-first.x_mm)*dx + (point.y_mm-first.y_mm)*dy) / denominator))
    projection = Point2D(first.x_mm + factor * dx, first.y_mm + factor * dy)
    return _distance(point, projection)


def _dot(first, second):
    return first[0] * second[0] + first[1] * second[1]


def _point_in_polygon(point, polygon):
    """Deterministic odd-even test for one sampled opening boundary."""
    inside = False
    for first, second in zip(polygon, polygon[1:] + polygon[:1]):
        if ((first.y_mm > point.y_mm) != (second.y_mm > point.y_mm)):
            crossing_x = first.x_mm + (
                (point.y_mm - first.y_mm)
                * (second.x_mm - first.x_mm)
                / (second.y_mm - first.y_mm)
            )
            if point.x_mm < crossing_x:
                inside = not inside
    return inside


def _point_closed_polyline_distance(point, polygon):
    return min(
        _point_segment_distance(point, first, second)
        for first, second in zip(polygon, polygon[1:] + polygon[:1])
    )


def _polyline_samples(points, subdivisions):
    samples = [points[0]]
    for first, second in zip(points, points[1:]):
        for index in range(1, subdivisions + 1):
            ratio = index / subdivisions
            samples.append(
                Point2D(
                    first.x_mm + ratio * (second.x_mm - first.x_mm),
                    first.y_mm + ratio * (second.y_mm - first.y_mm),
                )
            )
    return tuple(samples)


def _offset_open_polyline(points, segment_normals, offset):
    """Offset segment lines and join adjacent lines at their intersection."""
    shifted = [
        Point2D(
            points[0].x_mm + segment_normals[0][0] * offset,
            points[0].y_mm + segment_normals[0][1] * offset,
        )
    ]
    for index in range(1, len(points) - 1):
        point = points[index]
        previous_base = Point2D(
            point.x_mm + segment_normals[index - 1][0] * offset,
            point.y_mm + segment_normals[index - 1][1] * offset,
        )
        following_base = Point2D(
            point.x_mm + segment_normals[index][0] * offset,
            point.y_mm + segment_normals[index][1] * offset,
        )
        previous_direction = _unit_direction(points[index - 1], point)
        following_direction = _unit_direction(point, points[index + 1])
        denominator = (
            previous_direction[0] * following_direction[1]
            - previous_direction[1] * following_direction[0]
        )
        if abs(denominator) <= _COORDINATE_TOLERANCE_MM:
            shifted.append(
                Point2D(
                    (previous_base.x_mm + following_base.x_mm) / 2.0,
                    (previous_base.y_mm + following_base.y_mm) / 2.0,
                )
            )
            continue
        delta_x = following_base.x_mm - previous_base.x_mm
        delta_y = following_base.y_mm - previous_base.y_mm
        factor = (
            delta_x * following_direction[1]
            - delta_y * following_direction[0]
        ) / denominator
        shifted.append(
            Point2D(
                previous_base.x_mm + previous_direction[0] * factor,
                previous_base.y_mm + previous_direction[1] * factor,
            )
        )
    shifted.append(
        Point2D(
            points[-1].x_mm + segment_normals[-1][0] * offset,
            points[-1].y_mm + segment_normals[-1][1] * offset,
        )
    )
    return tuple(shifted)


def _offset_feature_chain(chain, polygon, offset):
    """Return chain vertices from the inward offset of the complete boundary."""
    shifted = []
    for point in chain:
        try:
            index = polygon.index(point)
        except ValueError:
            return ()
        previous = polygon[index - 1]
        following = polygon[(index + 1) % len(polygon)]
        incoming = _unit_direction(previous, point)
        outgoing = _unit_direction(point, following)
        incoming_normal = _inward_segment_normal(previous, point, polygon)
        outgoing_normal = _inward_segment_normal(point, following, polygon)
        incoming_base = Point2D(
            point.x_mm + incoming_normal[0] * offset,
            point.y_mm + incoming_normal[1] * offset,
        )
        outgoing_base = Point2D(
            point.x_mm + outgoing_normal[0] * offset,
            point.y_mm + outgoing_normal[1] * offset,
        )
        denominator = incoming[0] * outgoing[1] - incoming[1] * outgoing[0]
        if abs(denominator) <= _COORDINATE_TOLERANCE_MM:
            shifted.append(
                Point2D(
                    (incoming_base.x_mm + outgoing_base.x_mm) / 2.0,
                    (incoming_base.y_mm + outgoing_base.y_mm) / 2.0,
                )
            )
            continue
        delta_x = outgoing_base.x_mm - incoming_base.x_mm
        delta_y = outgoing_base.y_mm - incoming_base.y_mm
        factor = (
            delta_x * outgoing[1] - delta_y * outgoing[0]
        ) / denominator
        shifted.append(
            Point2D(
                incoming_base.x_mm + incoming[0] * factor,
                incoming_base.y_mm + incoming[1] * factor,
            )
        )
    return tuple(shifted)


def _chain_direction(chain, polygon):
    if len(chain) < 2:
        return "unknown"
    try:
        first = polygon.index(chain[0])
        second = polygon.index(chain[1])
    except ValueError:
        return "unknown"
    if second == (first + 1) % len(polygon):
        return "forward"
    if second == (first - 1) % len(polygon):
        return "reverse"
    return "sampled"


def _inward_segment_normal(first, second, polygon):
    tangent = _unit_direction(first, second)
    midpoint = Point2D(
        (first.x_mm + second.x_mm) / 2.0,
        (first.y_mm + second.y_mm) / 2.0,
    )
    normals = ((-tangent[1], tangent[0]), (tangent[1], -tangent[0]))
    for probe in (0.05, 0.25, 0.5, 1.0):
        for normal in normals:
            if _point_in_polygon(
                Point2D(
                    midpoint.x_mm + normal[0] * probe,
                    midpoint.y_mm + normal[1] * probe,
                ),
                polygon,
            ):
                return normal
    return normals[0]


def _material_side_cutter_envelope_mm(interior, canonical_normal, profile):
    """Return the actual asymmetric profile reach toward visible material."""
    negative_extent = float(profile.top_width_mm) / 2.0
    positive_extent = max(
        float(profile.top_width_mm) / 2.0,
        float(profile.bottom_width_mm) / 2.0 + float(profile.bottom_width_mm),
    )
    # If the opening is on +normal, material is on the negative side, and
    # conversely.  Keeping both values explicit preserves asymmetric profiles.
    return (
        negative_extent
        if _dot(interior, canonical_normal) >= 0.0
        else positive_extent
    )


def _simplify_open(points: tuple[Point2D, ...], tolerance: float) -> tuple[Point2D, ...]:
    if len(points) <= 2:
        return points
    first, last = points[0], points[-1]
    distances = tuple(_point_segment_distance(point, first, last) for point in points[1:-1])
    maximum = max(distances, default=0.0)
    if maximum <= tolerance:
        return (first, last)
    split = distances.index(maximum) + 1
    left = _simplify_open(points[:split + 1], tolerance)
    right = _simplify_open(points[split:], tolerance)
    return left[:-1] + right


def _adaptive_simplify_open(
    points: tuple[Point2D, ...], tolerance: float
) -> tuple[Point2D, ...]:
    """Preserve visible curvature while removing redundant straight samples."""
    compact = list(_deduplicate(points))
    changed = True
    while changed and len(compact) > 2:
        changed = False
        for index in range(1, len(compact) - 1):
            previous, current, following = (
                compact[index - 1], compact[index], compact[index + 1]
            )
            turn = _turn_angle_deg(
                _unit_direction(previous, current),
                _unit_direction(current, following),
            )
            if (
                turn < 5.0
                and _point_segment_distance(current, previous, following)
                <= tolerance
            ):
                del compact[index]
                changed = True
                break
    return tuple(compact)


def _simplify_closed(points: tuple[Point2D, ...], tolerance: float) -> tuple[Point2D, ...]:
    # Preserve the canonical anchor and the farthest point, simplifying the two
    # ordered halves independently so loop topology remains deterministic.
    anchor = points[0]
    split = max(range(1, len(points)), key=lambda index: (_distance(anchor, points[index]), -index))
    first = _simplify_open(points[:split + 1], tolerance)
    second = _simplify_open(points[split:] + (anchor,), tolerance)
    return first[:-1] + second[:-1]


def _maximum_cycle_turn_deg(points: tuple[Point2D, ...]) -> float:
    """Return the largest local boundary turn in one closed sample cycle."""
    return max((
        _turn_angle_deg(
            _unit_direction(points[index - 1], points[index]),
            _unit_direction(points[index], points[(index + 1) % len(points)]),
        )
        for index in range(len(points))
    ), default=0.0)


def _adaptive_simplify_closed(
    points: tuple[Point2D, ...], tolerance: float
) -> tuple[Point2D, ...]:
    """Keep curved samples while collapsing low-curvature, near-linear points."""
    compact = list(points)
    changed = True
    while changed and len(compact) > 3:
        changed = False
        for index in range(len(compact)):
            previous = compact[index - 1]
            current = compact[index]
            following = compact[(index + 1) % len(compact)]
            turn = _turn_angle_deg(
                _unit_direction(previous, current),
                _unit_direction(current, following),
            )
            if (
                turn < 5.0
                and _point_segment_distance(current, previous, following)
                <= tolerance
            ):
                del compact[index]
                changed = True
                break
    return _canonical_cycle(tuple(compact))


def _deduplicate(points: tuple[Point2D, ...]) -> tuple[Point2D, ...]:
    result = []
    for point in points:
        if not result or _distance(result[-1], point) > _COORDINATE_TOLERANCE_MM:
            result.append(point)
    return tuple(result)


def _clean_open_path(
    points: tuple[Point2D, ...],
    tolerance: float,
    maximum_turn_deg: float | None = None,
) -> tuple[Point2D, ...]:
    """Remove duplicates, tiny steps, and near-collinear interior points."""
    compact = list(_deduplicate(points))
    changed = True
    while changed and len(compact) > 2:
        changed = False
        for index in range(1, len(compact) - 1):
            previous, current, following = (
                compact[index - 1], compact[index], compact[index + 1]
            )
            first_length = _distance(previous, current)
            second_length = _distance(current, following)
            first_direction = _unit_direction(previous, current)
            second_direction = _unit_direction(current, following)
            forward = (
                first_direction[0] * second_direction[0]
                + first_direction[1] * second_direction[1]
            ) > 0.0
            if (
                min(first_length, second_length) <= tolerance
                or (
                    forward
                    and _point_segment_distance(current, previous, following)
                    <= tolerance
                )
            ):
                trial = compact[:index] + compact[index + 1:]
                new_window = tuple(trial[max(0, index - 2): index + 2])
                allowed_turn = (
                    math.inf
                    if maximum_turn_deg is None
                    else maximum_turn_deg
                )
                if _maximum_turn_deg(new_window) <= allowed_turn + 1.0e-9:
                    compact.pop(index)
                    changed = True
                    break
    return tuple(compact)


def _strictly_monotone(points: tuple[Point2D, ...], axis: str) -> bool:
    values = tuple(point.y_mm if axis == "vertical" else point.x_mm for point in points)
    return all(values[index + 1] > values[index] + _COORDINATE_TOLERANCE_MM for index in range(len(values) - 1))


def _orientation(first, second, third):
    return (second.x_mm-first.x_mm)*(third.y_mm-first.y_mm) - (second.y_mm-first.y_mm)*(third.x_mm-first.x_mm)


def _segments_intersect(first, second, third, fourth) -> bool:
    if (
        max(first.x_mm, second.x_mm) + _COORDINATE_TOLERANCE_MM
        < min(third.x_mm, fourth.x_mm)
        or max(third.x_mm, fourth.x_mm) + _COORDINATE_TOLERANCE_MM
        < min(first.x_mm, second.x_mm)
        or max(first.y_mm, second.y_mm) + _COORDINATE_TOLERANCE_MM
        < min(third.y_mm, fourth.y_mm)
        or max(third.y_mm, fourth.y_mm) + _COORDINATE_TOLERANCE_MM
        < min(first.y_mm, second.y_mm)
    ):
        return False
    one = _orientation(first, second, third)
    two = _orientation(first, second, fourth)
    three = _orientation(third, fourth, first)
    four = _orientation(third, fourth, second)
    return (
        (one <= _COORDINATE_TOLERANCE_MM and two >= -_COORDINATE_TOLERANCE_MM or one >= -_COORDINATE_TOLERANCE_MM and two <= _COORDINATE_TOLERANCE_MM)
        and (three <= _COORDINATE_TOLERANCE_MM and four >= -_COORDINATE_TOLERANCE_MM or three >= -_COORDINATE_TOLERANCE_MM and four <= _COORDINATE_TOLERANCE_MM)
    )


def _self_intersects(points: tuple[Point2D, ...]) -> bool:
    for first in range(len(points) - 1):
        for second in range(first + 2, len(points) - 1):
            if _segments_intersect(points[first], points[first + 1], points[second], points[second + 1]):
                return True
    return False


def _intersection_count(vertical, horizontal) -> int:
    intersections = []
    for first in range(len(vertical) - 1):
        for second in range(len(horizontal) - 1):
            point = _segment_intersection_point(
                vertical[first], vertical[first + 1],
                horizontal[second], horizontal[second + 1],
            )
            if point is not None and not any(
                _distance(point, existing) <= _COORDINATE_TOLERANCE_MM
                for existing in intersections
            ):
                intersections.append(point)
    return len(intersections)


def _segment_intersection_point(first, second, third, fourth):
    """Return one XY intersection, coalescing a shared polyline vertex."""
    if not _segments_intersect(first, second, third, fourth):
        return None
    rx = second.x_mm - first.x_mm
    ry = second.y_mm - first.y_mm
    sx = fourth.x_mm - third.x_mm
    sy = fourth.y_mm - third.y_mm
    denominator = rx * sy - ry * sx
    if abs(denominator) > _COORDINATE_TOLERANCE_MM:
        qpx = third.x_mm - first.x_mm
        qpy = third.y_mm - first.y_mm
        ratio = (qpx * sy - qpy * sx) / denominator
        return Point2D(first.x_mm + ratio * rx, first.y_mm + ratio * ry)
    for one in (first, second):
        for two in (third, fourth):
            if _distance(one, two) <= _COORDINATE_TOLERANCE_MM:
                return one
    return Point2D(
        0.5 * (max(min(first.x_mm, second.x_mm), min(third.x_mm, fourth.x_mm))
               + min(max(first.x_mm, second.x_mm), max(third.x_mm, fourth.x_mm))),
        0.5 * (max(min(first.y_mm, second.y_mm), min(third.y_mm, fourth.y_mm))
               + min(max(first.y_mm, second.y_mm), max(third.y_mm, fourth.y_mm))),
    )

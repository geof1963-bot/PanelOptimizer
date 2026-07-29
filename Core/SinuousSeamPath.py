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
from dataclasses import dataclass

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
    maximum_features_per_seam: int = Settings.Split.SEAM_MAX_FEATURES


class SinuousSeamPathFinder:
    """Extract useful opening wires and generate two simple seam paths."""

    def __init__(
        self,
        parameters: SinuousSeamParameters = SinuousSeamParameters(),
        split_settings: object = Settings.Split,
    ) -> None:
        self._parameters = self._validated_parameters(parameters)
        self._split_settings = split_settings

    def generate(
        self,
        source_shape: object,
        vertical_offset: float = 0.0,
        horizontal_offset: float = 0.0,
    ) -> SinuousSeamPlan:
        """Generate deterministic paths directly from the source top view."""
        try:
            bounds = source_shape.BoundBox
            xmin, xmax = float(bounds.XMin), float(bounds.XMax)
            ymin, ymax = float(bounds.YMin), float(bounds.YMax)
            zmax = float(bounds.ZMax)
        except Exception as error:
            raise SplitOperationError("Sinuous seam source is unavailable.") from error
        nominal_x = (xmin + xmax) / 2.0 + self._finite(vertical_offset)
        nominal_y = (ymin + ymax) / 2.0 + self._finite(horizontal_offset)
        features = self._extract_features(source_shape, zmax)
        vertical = self._build_path(
            "vertical", nominal_x, nominal_y, (xmin, xmax, ymin, ymax), features
        )
        horizontal = self._build_path(
            "horizontal", nominal_y, nominal_x, (xmin, xmax, ymin, ymax), features
        )
        intersections = _intersection_count(vertical.points, horizontal.points)
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
        return SinuousSeamPlan(vertical, horizontal, features, intersections)

    def candidate_plans(
        self,
        plan: SinuousSeamPlan,
        panel_bounds: tuple[float, float, float, float],
    ) -> tuple[SinuousSeamPlan, ...]:
        """Return bounded route combinations ordered by hidden contour length."""
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
        return tuple(unique)

    def _path_variants(self, primary, center_other, panel_bounds, features):
        """Build at most five cached-feature routes from complex to straight."""
        axis = primary.axis
        variants = [primary]
        followed = set(primary.followed_feature_ids)
        for feature_id in sorted(followed):
            subset = tuple(
                feature for feature in features if feature.feature_id != feature_id
            )
            variants.append(
                self._build_path(
                    axis,
                    primary.nominal_coordinate_mm,
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
                        primary.nominal_coordinate_mm,
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
        )[:5])

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
        """Discretize one exact wire deterministically, then simplify it."""
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
        return _simplify_closed(canonical, self._parameters.boundary_simplification_mm)

    def _build_path(
        self,
        axis: str,
        nominal: float,
        center_other: float,
        panel_bounds: tuple[float, float, float, float],
        features: tuple[BoundaryFeature2D, ...],
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
            detour = self._feature_detour(
                feature, axis, nominal, center_other, allowed_min, allowed_max
            )
            if detour is not None:
                boundary_distance, travel_span, interval, chain, report = detour
                ranked.append(
                    (
                        -travel_span,
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
            interval = item[3]
            if any(
                not (interval[1] < chosen[3][0] or interval[0] > chosen[3][1])
                for chosen in selected
            ):
                continue
            selected.append(item)
            if len(selected) >= self._parameters.maximum_features_per_seam:
                break
        selected.sort(key=lambda item: item[3][0])
        raw_points = [self._point(axis, nominal, travel_min)]
        smoothed_points = [self._point(axis, nominal, travel_min)]
        followed = []
        followed_bounds = []
        offset_reports = []
        contour_following_length = 0.0
        transition_count = 0
        artificial_before = []
        artificial_after = []
        for item in selected:
            interval, chain, feature, offset_report = (
                item[3], item[4], item[5], item[6]
            )
            entry = self._point(axis, nominal, interval[0])
            exit_point = self._point(axis, nominal, interval[1])
            entry_curve = self._smooth_transition(
                entry,
                chain[0],
                self._axis_tangent(axis),
                _unit_direction(chain[0], chain[1]),
                axis,
            )
            exit_curve = self._smooth_transition(
                chain[-1],
                exit_point,
                _unit_direction(chain[-2], chain[-1]),
                self._axis_tangent(axis),
                axis,
            )
            if entry_curve is None or exit_curve is None:
                continue
            entry_after = _transition_curve_angles(
                (entry,) + entry_curve,
                self._axis_tangent(axis),
                _unit_direction(chain[0], chain[1]),
            )
            exit_after = _transition_curve_angles(
                (chain[-1],) + exit_curve,
                _unit_direction(chain[-2], chain[-1]),
                self._axis_tangent(axis),
            )
            if max(entry_after + exit_after, default=0.0) > (
                self._parameters.maximum_artificial_turn_deg
                + _COORDINATE_TOLERANCE_MM
            ):
                continue
            raw_points.append(entry)
            raw_points.extend(chain)
            raw_points.append(exit_point)
            smoothed_points.append(entry)
            smoothed_points.extend(entry_curve)
            smoothed_points.extend(chain[1:-1])
            smoothed_points.append(chain[-1])
            smoothed_points.extend(exit_curve)
            transition_count += 2
            artificial_before.extend(
                (
                    _turn_angle_deg(
                        self._axis_tangent(axis),
                        _unit_direction(entry, chain[0]),
                    ),
                    _turn_angle_deg(
                        _unit_direction(entry, chain[0]),
                        _unit_direction(chain[0], chain[1]),
                    ),
                    _turn_angle_deg(
                        _unit_direction(chain[-2], chain[-1]),
                        _unit_direction(chain[-1], exit_point),
                    ),
                    _turn_angle_deg(
                        _unit_direction(chain[-1], exit_point),
                        self._axis_tangent(axis),
                    ),
                )
            )
            artificial_after.extend(entry_after)
            artificial_after.extend(exit_after)
            followed.append(feature.feature_id)
            followed_bounds.append(feature.bounds_mm)
            offset_reports.append(offset_report)
            contour_following_length += _polyline_length(chain)
        final_point = self._point(axis, nominal, travel_max)
        raw_points.append(final_point)
        smoothed_points.append(final_point)
        raw_compact = _deduplicate(tuple(raw_points))
        compact = _clean_open_path(
            tuple(smoothed_points),
            self._parameters.path_simplify_tolerance_mm,
            self._parameters.maximum_artificial_turn_deg,
        )
        if not _strictly_monotone(compact, axis) or _self_intersects(compact):
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
        )

    def _smooth_transition(
        self, first, last, first_tangent, last_tangent, axis
    ) -> tuple[Point2D, ...]:
        """Return a monotone sampled cubic transition excluding its first point."""
        chord = _distance(first, last)
        if chord <= _COORDINATE_TOLERANCE_MM:
            return (last,)
        derivative_scale = chord * 0.5
        for subdivisions in (4, 8, 16, 32):
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
                return candidate[1:]
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
            return None
        chain, offset_report = offset_result
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
                simplified = _simplify_open(
                    tuple(chain), self._parameters.boundary_simplification_mm
                )
                span = travel(simplified[-1]) - travel(simplified[0])
                if span < self._parameters.minimum_feature_size_mm:
                    continue
                valid.append(
                    (
                        -span,
                        max(abs(cross(point) - nominal) for point in simplified),
                        _polyline_length(simplified),
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
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in numeric):
            raise SplitOperationError("Sinuous seam parameters must be positive.")
        if parameters.maximum_features_per_seam < 1:
            raise SplitOperationError("At least one seam feature must be allowed.")
        return parameters


def _distance(first: Point2D, second: Point2D) -> float:
    return math.hypot(first.x_mm - second.x_mm, first.y_mm - second.y_mm)


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


def _simplify_closed(points: tuple[Point2D, ...], tolerance: float) -> tuple[Point2D, ...]:
    # Preserve the canonical anchor and the farthest point, simplifying the two
    # ordered halves independently so loop topology remains deterministic.
    anchor = points[0]
    split = max(range(1, len(points)), key=lambda index: (_distance(anchor, points[index]), -index))
    first = _simplify_open(points[:split + 1], tolerance)
    second = _simplify_open(points[split:] + (anchor,), tolerance)
    return first[:-1] + second[:-1]


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
    intersections = 0
    for first in range(len(vertical) - 1):
        for second in range(len(horizontal) - 1):
            if _segments_intersect(vertical[first], vertical[first + 1], horizontal[second], horizontal[second + 1]):
                intersections += 1
    return intersections

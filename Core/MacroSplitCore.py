# -*- coding: utf-8 -*-
"""Pragmatic V4.10 groove cutting faithfully extracted from proven macros."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .Exceptions import SplitOperationError, SplitSourceError

__all__ = [
    "MacroGrooveParameters",
    "MacroSplitCore",
    "MacroSplitResult",
]


@dataclass(frozen=True, slots=True)
class MacroGrooveParameters:
    """Exact scalar groove parameters shared by both reference macros.

    All values are model-coordinate millimetres. The visible V4.10 profile is
    unchanged. V4.21 also uses ``bottom_width_mm`` as the full-depth slot width,
    starting at the existing profile's bottom-left coordinate. ``overlap_mm``
    extends cutters beyond transverse and bottom panel boundaries.
    """

    groove_depth_mm: float = 1.2
    top_width_mm: float = 2.2
    bottom_width_mm: float = 0.5
    overlap_mm: float = 20.0


@dataclass(frozen=True, slots=True)
class MacroSplitResult:
    """Runtime result and scalar metadata for one macro-equivalent cut.

    ``shape`` is transient FreeCAD geometry and deliberately does not enter
    ``Core.Models`` or an immutable analysis report.
    """

    shape: object
    real_center_x_mm: float
    real_center_y_mm: float
    cut_x_mm: float
    cut_y_mm: float
    vertical_offset_mm: float
    horizontal_offset_mm: float
    source_volume_mm3: float
    surface_groove_result_volume_mm3: float
    surface_groove_removed_volume_mm3: float
    additional_separation_removed_volume_mm3: float
    result_volume_mm3: float
    solid_count: int
    separation_width_mm: float
    cleanup_applied: bool
    seam_plan: object | None


class MacroSplitCore:
    """Apply the two proven full-length asymmetric groove cutters."""

    def cut(
        self,
        source_shape: object,
        vertical_offset: float = 0.0,
        horizontal_offset: float = 0.0,
        parameters: MacroGrooveParameters = MacroGrooveParameters(),
        seam_plan: object | None = None,
    ) -> MacroSplitResult:
        """Return a transient macro-equivalent result without source mutation.

        Positive ``vertical_offset`` moves the X-directed cut position right;
        positive ``horizontal_offset`` moves the Y-directed cut position up.
        This naming and sign convention exactly follows
        ``chanfreins_avec_Offsets.FCMacro``.

        The boolean sequence is intentionally fixed: copy source, cut the
        Y-extruded vertical cutter, cut the X-extruded horizontal cutter, then
        attempt ``removeSplitter``. Invalid-but-usable source geometry is not
        rejected before these macro operations.
        """
        if source_shape is None or not hasattr(source_shape, "BoundBox"):
            raise SplitSourceError("Macro split requires a shape-like source.")
        offset_x = self._finite(vertical_offset, "vertical offset")
        offset_y = self._finite(horizontal_offset, "horizontal offset")
        profile = self._validated_parameters(parameters)

        try:
            panel_shape = source_shape.copy()
            bounds = panel_shape.BoundBox
            xmin = float(bounds.XMin)
            xmax = float(bounds.XMax)
            ymin = float(bounds.YMin)
            ymax = float(bounds.YMax)
            zmax = float(bounds.ZMax)
            zmin = float(bounds.ZMin)
            width = xmax - xmin
            height = ymax - ymin
            source_volume = float(panel_shape.Volume)
        except Exception as error:
            raise SplitSourceError(
                "Unable to copy or measure the macro split source."
            ) from error
        if not all(
            math.isfinite(value)
            for value in (xmin, xmax, ymin, ymax, zmin, zmax, source_volume)
        ) or width <= 0.0 or height <= 0.0:
            raise SplitSourceError(
                "Macro split source must have finite positive X/Y extents."
            )

        real_center_x = (xmin + xmax) / 2.0
        real_center_y = (ymin + ymax) / 2.0
        cut_x = real_center_x + offset_x
        cut_y = real_center_y + offset_y
        half_top = profile.top_width_mm / 2.0
        half_bottom = profile.bottom_width_mm / 2.0
        z_bottom = zmax - profile.groove_depth_mm
        slot_left_x = cut_x + half_bottom
        slot_right_x = slot_left_x + profile.bottom_width_mm
        slot_lower_y = cut_y + half_bottom
        slot_upper_y = slot_lower_y + profile.bottom_width_mm
        below_panel = zmin - profile.overlap_mm

        try:
            import Part
            from FreeCAD import Vector

            if seam_plan is None:
                surface_vertical_cutter = self._extruded_profile(
                    (
                        (cut_x - half_top, ymin - profile.overlap_mm, zmax),
                        (cut_x + half_top, ymin - profile.overlap_mm, zmax),
                        (cut_x + half_top, ymin - profile.overlap_mm, z_bottom),
                        (cut_x + half_bottom, ymin - profile.overlap_mm, z_bottom),
                    ),
                    Vector(0.0, height + profile.overlap_mm * 2.0, 0.0),
                    Part,
                    Vector,
                )
                surface_horizontal_cutter = self._extruded_profile(
                    (
                        (xmin - profile.overlap_mm, cut_y - half_top, zmax),
                        (xmin - profile.overlap_mm, cut_y + half_top, zmax),
                        (xmin - profile.overlap_mm, cut_y + half_top, z_bottom),
                        (xmin - profile.overlap_mm, cut_y + half_bottom, z_bottom),
                    ),
                    Vector(width + profile.overlap_mm * 2.0, 0.0, 0.0),
                    Part,
                    Vector,
                )
                vertical_cutter = self._extruded_profile(
                    (
                        (cut_x - half_top, ymin - profile.overlap_mm, zmax),
                        (cut_x + half_top, ymin - profile.overlap_mm, zmax),
                        (cut_x + half_top, ymin - profile.overlap_mm, z_bottom),
                        (slot_right_x, ymin - profile.overlap_mm, z_bottom),
                        (slot_right_x, ymin - profile.overlap_mm, below_panel),
                        (slot_left_x, ymin - profile.overlap_mm, below_panel),
                        (slot_left_x, ymin - profile.overlap_mm, z_bottom),
                    ),
                    Vector(0.0, height + profile.overlap_mm * 2.0, 0.0),
                    Part,
                    Vector,
                )
                horizontal_cutter = self._extruded_profile(
                    (
                        (xmin - profile.overlap_mm, cut_y - half_top, zmax),
                        (xmin - profile.overlap_mm, cut_y + half_top, zmax),
                        (xmin - profile.overlap_mm, cut_y + half_top, z_bottom),
                        (xmin - profile.overlap_mm, slot_upper_y, z_bottom),
                        (xmin - profile.overlap_mm, slot_upper_y, below_panel),
                        (xmin - profile.overlap_mm, slot_lower_y, below_panel),
                        (xmin - profile.overlap_mm, slot_lower_y, z_bottom),
                    ),
                    Vector(width + profile.overlap_mm * 2.0, 0.0, 0.0),
                    Part,
                    Vector,
                )
            else:
                self._validate_seam_plan(seam_plan, cut_x, cut_y)
                surface_vertical_cutter = self._segmented_path_cutter(
                    seam_plan.vertical, profile, zmax, z_bottom, below_panel,
                    False, Part, Vector,
                )
                surface_horizontal_cutter = self._segmented_path_cutter(
                    seam_plan.horizontal, profile, zmax, z_bottom, below_panel,
                    False, Part, Vector,
                )
                vertical_cutter = self._segmented_path_cutter(
                    seam_plan.vertical, profile, zmax, z_bottom, below_panel,
                    True, Part, Vector,
                )
                horizontal_cutter = self._segmented_path_cutter(
                    seam_plan.horizontal, profile, zmax, z_bottom, below_panel,
                    True, Part, Vector,
                )
            surface_result = panel_shape.cut(surface_vertical_cutter)
            surface_result = surface_result.cut(surface_horizontal_cutter)
            result = panel_shape.cut(vertical_cutter)
            result = result.cut(horizontal_cutter)
        except Exception as error:
            raise SplitOperationError(
                "Macro-based vertical/horizontal groove cut failed."
            ) from error

        cleanup_applied = False
        try:
            result = result.removeSplitter()
            cleanup_applied = True
        except Exception:
            # Both reference macros explicitly keep the boolean result when
            # optional splitter cleanup is unavailable.
            pass

        try:
            if result.isNull():
                raise SplitOperationError("Macro-based cut returned null geometry.")
            result_volume = float(result.Volume)
            surface_result_volume = float(surface_result.Volume)
            solid_count = len(result.Solids)
        except SplitOperationError:
            raise
        except Exception as error:
            raise SplitOperationError(
                "Unable to inspect macro-based cut result."
            ) from error
        return MacroSplitResult(
            shape=result,
            real_center_x_mm=real_center_x,
            real_center_y_mm=real_center_y,
            cut_x_mm=cut_x,
            cut_y_mm=cut_y,
            vertical_offset_mm=offset_x,
            horizontal_offset_mm=offset_y,
            source_volume_mm3=source_volume,
            surface_groove_result_volume_mm3=surface_result_volume,
            surface_groove_removed_volume_mm3=(
                source_volume - surface_result_volume
            ),
            additional_separation_removed_volume_mm3=(
                surface_result_volume - result_volume
            ),
            result_volume_mm3=result_volume,
            solid_count=solid_count,
            separation_width_mm=profile.bottom_width_mm,
            cleanup_applied=cleanup_applied,
            seam_plan=seam_plan,
        )

    @classmethod
    def _segmented_path_cutter(
        cls, path, profile, zmax, z_bottom, below_panel, full_depth, Part, Vector
    ):
        """Build overlapping straight profile segments along one XY path."""
        pieces = []
        points = tuple(path.points)
        for index, (first, second) in enumerate(zip(points, points[1:])):
            dx = float(second.x_mm - first.x_mm)
            dy = float(second.y_mm - first.y_mm)
            length = math.hypot(dx, dy)
            if length <= 0.0:
                raise SplitOperationError("Seam path contains a zero-length segment.")
            tx, ty = dx / length, dy / length
            if path.axis == "vertical":
                nx, ny = ty, -tx
            elif path.axis == "horizontal":
                nx, ny = -ty, tx
            else:
                raise SplitOperationError("Unsupported seam path axis.")
            start_extension = (
                profile.overlap_mm if index == 0 else profile.top_width_mm
            )
            end_extension = (
                profile.overlap_mm
                if index == len(points) - 2
                else profile.top_width_mm
            )
            start_x = first.x_mm - tx * start_extension
            start_y = first.y_mm - ty * start_extension
            segment_length = length + start_extension + end_extension
            half_top = profile.top_width_mm / 2.0
            half_bottom = profile.bottom_width_mm / 2.0

            def location(offset, z_value):
                return (
                    start_x + nx * offset,
                    start_y + ny * offset,
                    z_value,
                )

            cross_section = [
                location(-half_top, zmax),
                location(half_top, zmax),
                location(half_top, z_bottom),
            ]
            if full_depth:
                slot_left = half_bottom
                slot_right = half_bottom + profile.bottom_width_mm
                cross_section.extend(
                    (
                        location(slot_right, z_bottom),
                        location(slot_right, below_panel),
                        location(slot_left, below_panel),
                        location(slot_left, z_bottom),
                    )
                )
            else:
                cross_section.append(location(half_bottom, z_bottom))
            pieces.append(
                cls._extruded_profile(
                    tuple(cross_section),
                    Vector(tx * segment_length, ty * segment_length, 0.0),
                    Part,
                    Vector,
                )
            )
        if not pieces:
            raise SplitOperationError("Seam path contains no cutter segments.")
        try:
            cutter = pieces[0].multiFuse(pieces[1:]) if len(pieces) > 1 else pieces[0]
            try:
                cutter = cutter.removeSplitter()
            except Exception:
                pass
            return cutter
        except Exception as error:
            raise SplitOperationError("Unable to unite segmented seam cutter.") from error

    @staticmethod
    def _validate_seam_plan(seam_plan, cut_x, cut_y):
        """Require the focused immutable plan and unchanged nominal offsets."""
        try:
            valid = (
                seam_plan.intersection_count == 1
                and seam_plan.vertical.axis == "vertical"
                and seam_plan.horizontal.axis == "horizontal"
                and abs(seam_plan.vertical.nominal_coordinate_mm - cut_x) <= 1.0e-7
                and abs(seam_plan.horizontal.nominal_coordinate_mm - cut_y) <= 1.0e-7
            )
        except Exception as error:
            raise SplitOperationError("Sinuous seam plan is unavailable.") from error
        if not valid:
            raise SplitOperationError("Sinuous seam plan is inconsistent with cut offsets.")

    @staticmethod
    def _extruded_profile(points, extrusion, Part, Vector):
        """Build and extrude the macros' ordered four-point profile."""
        vectors = [Vector(*point) for point in points]
        polygon = Part.makePolygon((*vectors, vectors[0]))
        wire = Part.Wire(polygon.Edges)
        return Part.Face(wire).extrude(extrusion)

    @staticmethod
    def _finite(value: object, label: str) -> float:
        """Return one finite scalar offset without imposing policy limits."""
        try:
            result = float(value)
        except (TypeError, ValueError) as error:
            raise SplitOperationError(f"Macro split {label} must be finite.") from error
        if not math.isfinite(result):
            raise SplitOperationError(f"Macro split {label} must be finite.")
        return result

    @classmethod
    def _validated_parameters(
        cls,
        parameters: MacroGrooveParameters,
    ) -> MacroGrooveParameters:
        """Validate geometric profile scalars without redesigning the profile."""
        if not isinstance(parameters, MacroGrooveParameters):
            raise SplitOperationError(
                "Macro split parameters must be MacroGrooveParameters."
            )
        values = (
            cls._finite(parameters.groove_depth_mm, "groove depth"),
            cls._finite(parameters.top_width_mm, "top width"),
            cls._finite(parameters.bottom_width_mm, "bottom width"),
            cls._finite(parameters.overlap_mm, "overlap"),
        )
        if any(value <= 0.0 for value in values):
            raise SplitOperationError(
                "Macro groove dimensions and overlap must be positive."
            )
        if (
            parameters.bottom_width_mm
            > (parameters.top_width_mm - parameters.bottom_width_mm) / 2.0
        ):
            raise SplitOperationError(
                "Macro separation width must fit inside the existing flat "
                "bottom segment."
            )
        return parameters

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

    All values are model-coordinate millimetres. The profile has a
    ``top_width_mm`` opening at the source maximum-Z face, a flat
    ``bottom_width_mm`` at ``groove_depth_mm`` below that face, one sloped
    negative-axis wall, and one vertical positive-axis wall. ``overlap_mm``
    extends each extrusion beyond both transverse panel boundaries.
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
    result_volume_mm3: float
    solid_count: int
    cleanup_applied: bool


class MacroSplitCore:
    """Apply the two proven full-length asymmetric groove cutters."""

    def cut(
        self,
        source_shape: object,
        vertical_offset: float = 0.0,
        horizontal_offset: float = 0.0,
        parameters: MacroGrooveParameters = MacroGrooveParameters(),
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
            width = xmax - xmin
            height = ymax - ymin
            source_volume = float(panel_shape.Volume)
        except Exception as error:
            raise SplitSourceError(
                "Unable to copy or measure the macro split source."
            ) from error
        if not all(
            math.isfinite(value)
            for value in (xmin, xmax, ymin, ymax, zmax, source_volume)
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

        try:
            import Part
            from FreeCAD import Vector

            vertical_cutter = self._extruded_profile(
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
            horizontal_cutter = self._extruded_profile(
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
            result_volume_mm3=result_volume,
            solid_count=solid_count,
            cleanup_applied=cleanup_applied,
        )

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
        return parameters

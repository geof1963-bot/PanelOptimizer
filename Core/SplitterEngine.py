# -*- coding: utf-8 -*-
"""Deterministic four-quadrant solid splitting for the V4.00 prototype."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .Exceptions import (
    InvalidResultingSolidError,
    SplitOperationError,
    SplitSourceError,
    UnexpectedPartCountError,
)
from .Models import BoundingBox, Point3D, PrintablePart, SplitResult
from .Settings import Settings
from .SourceShapeResolver import resolve_source_shape
from .SplittingUtilities import (
    finite_positive,
    format_mm,
    volume_tolerance_mm3,
)

__all__ = ["SplitExecution", "SplitterEngine"]


@dataclass(slots=True)
class SplitExecution:
    """Runtime pairing of an immutable result with caller-owned B-rep shapes.

    ``shapes`` contains FreeCAD geometry and therefore deliberately lives
    outside ``Core.Models``. Its order exactly matches ``result.parts``.
    """

    result: SplitResult
    shapes: tuple[object, ...]

    def resolve_shape(self, geometry_reference: str) -> object:
        """Resolve one immutable part reference to its runtime shape."""
        for part, shape in zip(self.result.parts, self.shapes):
            if part.geometry_reference == geometry_reference:
                return shape
        raise SplitOperationError(
            f"Unknown split geometry reference '{geometry_reference}'."
        )


class SplitterEngine:
    """Split one valid solid at its bounding-box X/Y centre planes."""

    def __init__(self, split_settings: object = Settings.Split) -> None:
        """Store a read-only source for authoritative effective limits."""
        self._split_settings = split_settings

    def split_four_quadrants(
        self,
        shape: object,
        source_id: str,
    ) -> SplitExecution:
        """Return four validated solids and an immutable split result.

        The source is intersected with four axis-aligned clipping prisms whose
        shared boundaries are the bounding-box centre X and Y planes. Prisms
        span the exact full source Z range. Quadrants are produced in lower-left,
        lower-right, upper-left, upper-right model-coordinate order.

        Printable-limit violations remain recorded workflow results; they do
        not invalidate otherwise sound split geometry.

        Raises:
            SplitSourceError: If the input is not exactly one valid solid.
            SplitOperationError: If configuration or boolean operations fail.
            UnexpectedPartCountError: If exactly four parts are not produced.
            InvalidResultingSolidError: If any quadrant is empty, invalid, or
                contains other than one solid.
        """
        source_solid = self._validated_source_solid(shape)
        stable_source_id = str(source_id)
        if not stable_source_id:
            raise SplitSourceError("Split source ID cannot be empty.")

        maximum_width = finite_positive(
            self._split_settings.MAX_PART_WIDTH,
            "Settings.Split.MAX_PART_WIDTH",
        )
        maximum_height = finite_positive(
            self._split_settings.MAX_PART_HEIGHT,
            "Settings.Split.MAX_PART_HEIGHT",
        )
        bounds = source_solid.BoundBox
        dimensions = tuple(
            float(value)
            for value in (
                bounds.XLength,
                bounds.YLength,
                bounds.ZLength,
            )
        )
        if not all(math.isfinite(value) and value > 0.0 for value in dimensions):
            raise SplitSourceError(
                "Source solid must have finite positive X, Y, and Z extents."
            )

        cut_x = (float(bounds.XMin) + float(bounds.XMax)) / 2.0
        cut_y = (float(bounds.YMin) + float(bounds.YMax)) / 2.0
        source_volume = float(source_solid.Volume)
        if not math.isfinite(source_volume) or source_volume <= 0.0:
            raise SplitSourceError("Source solid must have positive finite volume.")

        specifications = (
            ("Part_1", "lower_left", bounds.XMin, bounds.YMin, cut_x, cut_y),
            ("Part_2", "lower_right", cut_x, bounds.YMin, bounds.XMax, cut_y),
            ("Part_3", "upper_left", bounds.XMin, cut_y, cut_x, bounds.YMax),
            ("Part_4", "upper_right", cut_x, cut_y, bounds.XMax, bounds.YMax),
        )
        shapes: list[object] = []
        parts: list[PrintablePart] = []
        result_id = f"{stable_source_id}:split:result:0001"

        for index, specification in enumerate(specifications, start=1):
            name, quadrant, x_min, y_min, x_max, y_max = specification
            result_shape = self._intersect_quadrant(
                source_solid,
                float(x_min),
                float(y_min),
                float(x_max),
                float(y_max),
                float(bounds.ZMin),
                float(bounds.ZMax),
                name,
            )
            part_id = f"{stable_source_id}:split:part:{index:04d}"
            printable_part = self._part_record(
                result_shape,
                part_id,
                result_id,
                stable_source_id,
                name,
                quadrant,
                maximum_width,
                maximum_height,
            )
            shapes.append(result_shape)
            parts.append(printable_part)

        if len(shapes) != 4 or len(parts) != 4:
            raise UnexpectedPartCountError(
                f"Expected four quadrant parts, received {len(shapes)}."
            )

        tolerance = volume_tolerance_mm3(source_volume)
        self._validate_non_overlapping(tuple(shapes), tolerance)
        result_volume = sum(float(item.Volume) for item in shapes)
        volume_difference = abs(source_volume - result_volume)
        if volume_difference > tolerance:
            raise SplitOperationError(
                "Split volume is not preserved: source "
                f"{format_mm(source_volume)} mm^3, results "
                f"{format_mm(result_volume)} mm^3, difference "
                f"{format_mm(volume_difference)} mm^3 exceeds geometry "
                f"tolerance {format_mm(tolerance)} mm^3."
            )

        all_printable = all(item.is_printable for item in parts)
        messages = tuple(
            f"{item.name}: {message}"
            for item in parts
            for message in item.validation_messages
        )
        result = SplitResult(
            result_id=result_id,
            source_id=stable_source_id,
            strategy="bounding_box_center_quadrants",
            cut_x_mm=cut_x,
            cut_y_mm=cut_y,
            maximum_width_mm=maximum_width,
            maximum_height_mm=maximum_height,
            parts=tuple(parts),
            source_volume_mm3=source_volume,
            result_volume_mm3=result_volume,
            volume_difference_mm3=volume_difference,
            all_parts_printable=all_printable,
            validation_messages=messages,
        )
        return SplitExecution(result=result, shapes=tuple(shapes))

    @staticmethod
    def _validated_source_solid(shape: object) -> object:
        """Return the one caller-owned source solid after conservative checks."""
        try:
            return resolve_source_shape(shape).shape
        except Exception as error:
            raise SplitSourceError(str(error)) from error

    @staticmethod
    def _intersect_quadrant(
        source_solid: object,
        x_min: float,
        y_min: float,
        x_max: float,
        y_max: float,
        z_min: float,
        z_max: float,
        name: str,
    ) -> object:
        """Intersect one exact X/Y quadrant prism with the source solid."""
        try:
            import Part
            from FreeCAD import Vector

            tool = Part.makeBox(
                x_max - x_min,
                y_max - y_min,
                z_max - z_min,
                Vector(x_min, y_min, z_min),
            )
            intersection = source_solid.common(tool)
        except Exception as error:
            raise SplitOperationError(
                f"Boolean intersection failed for {name}."
            ) from error

        try:
            solids = tuple(intersection.Solids)
            if intersection.isNull() or not intersection.isValid():
                raise InvalidResultingSolidError(
                    f"{name} is null or invalid after splitting."
                )
            if len(solids) != 1:
                raise InvalidResultingSolidError(
                    f"{name} must contain exactly one solid; found {len(solids)}."
                )
            result = solids[0].removeSplitter()
            if (
                result.isNull()
                or not result.isValid()
                or len(result.Solids) != 1
                or float(result.Volume) <= 0.0
            ):
                raise InvalidResultingSolidError(
                    f"{name} is not one non-empty valid solid."
                )
            return result
        except InvalidResultingSolidError:
            raise
        except Exception as error:
            raise InvalidResultingSolidError(
                f"Unable to validate resulting solid {name}."
            ) from error

    @staticmethod
    def _part_record(
        shape: object,
        part_id: str,
        result_id: str,
        source_id: str,
        name: str,
        quadrant: str,
        maximum_width: float,
        maximum_height: float,
    ) -> PrintablePart:
        """Create one FreeCAD-independent part record and limit result."""
        bounds = shape.BoundBox
        size_x = float(bounds.XLength)
        size_y = float(bounds.YLength)
        size_z = float(bounds.ZLength)
        within_x = size_x <= maximum_width
        within_y = size_y <= maximum_height
        messages: list[str] = []
        if not within_x:
            messages.append(
                f"X size {format_mm(size_x)} mm exceeds effective maximum "
                f"{format_mm(maximum_width)} mm."
            )
        if not within_y:
            messages.append(
                f"Y size {format_mm(size_y)} mm exceeds effective maximum "
                f"{format_mm(maximum_height)} mm."
            )
        return PrintablePart(
            part_id=part_id,
            split_result_id=result_id,
            source_id=source_id,
            name=name,
            quadrant=quadrant,
            geometry_reference=part_id,
            bounding_box=BoundingBox(
                minimum=Point3D(bounds.XMin, bounds.YMin, bounds.ZMin),
                maximum=Point3D(bounds.XMax, bounds.YMax, bounds.ZMax),
            ),
            size_x_mm=size_x,
            size_y_mm=size_y,
            size_z_mm=size_z,
            volume_mm3=float(shape.Volume),
            within_x_limit=within_x,
            within_y_limit=within_y,
            is_printable=within_x and within_y,
            validation_messages=tuple(messages),
        )

    @staticmethod
    def _validate_non_overlapping(
        shapes: tuple[object, ...],
        volume_tolerance: float,
    ) -> None:
        """Reject any pair whose interiors overlap above kernel tolerance."""
        for first_index, first in enumerate(shapes):
            for second_index, second in enumerate(
                shapes[first_index + 1 :],
                start=first_index + 1,
            ):
                try:
                    overlap_volume = float(first.common(second).Volume)
                except Exception as error:
                    raise SplitOperationError(
                        "Unable to verify quadrant overlap."
                    ) from error
                if overlap_volume > volume_tolerance:
                    raise SplitOperationError(
                        f"Part_{first_index + 1} and Part_{second_index + 1} "
                        "overlap by "
                        f"{format_mm(overlap_volume)} mm^3."
                    )

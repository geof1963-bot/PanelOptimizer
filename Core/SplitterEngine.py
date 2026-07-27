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
    PARTITION_CLASSIFICATION_TOLERANCE_MM,
    PARTITION_FUZZY_TOLERANCE_MM,
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
    partition_method: str = "Part.TopoShape.generalFuse(two planar tools)"
    initial_partition_solid_count: int = 4
    solids_per_quadrant: tuple[int, int, int, int] = (1, 1, 1, 1)

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

        One OpenCASCADE general-fuse partition slices the source with two
        planar faces spanning its full Z depth. Resulting source fragments are
        then classified in lower-left, lower-right, upper-left, upper-right
        model-coordinate order.

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

        partition_solids = self._partition_source(source_solid, cut_x, cut_y)
        classified = self._classify_partition_solids(
            partition_solids,
            cut_x,
            cut_y,
        )
        specifications = (
            ("Part_1", "lower_left"),
            ("Part_2", "lower_right"),
            ("Part_3", "upper_left"),
            ("Part_4", "upper_right"),
        )
        shapes: list[object] = []
        parts: list[PrintablePart] = []
        result_id = f"{stable_source_id}:split:result:0001"

        for index, specification in enumerate(specifications, start=1):
            name, quadrant = specification
            candidates = classified[index - 1]
            if len(candidates) != 1:
                raise InvalidResultingSolidError(
                    f"{name} contains {len(candidates)} disconnected material "
                    "components after center-plane partition; V4.00 requires "
                    "one printable solid per quadrant."
                )
            result_shape = self._validated_partition_solid(candidates[0], name)
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
        return SplitExecution(
            result=result,
            shapes=tuple(shapes),
            initial_partition_solid_count=len(partition_solids),
            solids_per_quadrant=tuple(len(items) for items in classified),
        )

    @staticmethod
    def _validated_source_solid(shape: object) -> object:
        """Return the one caller-owned source solid after conservative checks."""
        try:
            return resolve_source_shape(shape).shape
        except Exception as error:
            raise SplitSourceError(str(error)) from error

    @staticmethod
    def _partition_source(
        source_solid: object,
        cut_x: float,
        cut_y: float,
    ) -> tuple[object, ...]:
        """Partition the source once with two exact center-plane faces.

        OpenCASCADE ``generalFuse`` partitions the source and both zero-volume
        planar tools coherently. Because the tools are faces, every resulting
        solid necessarily originates from the source; no history-map filtering
        is needed. This avoids a FreeCAD SplitAPI history omission observed on
        the real panel. No healing, refining, or source mutation is performed.
        """
        try:
            import Part
            from FreeCAD import Vector

            bounds = source_solid.BoundBox
            # Extend the bounded faces beyond every source extent so their
            # outer edges cannot coincide with complex source boundaries.
            # This changes neither infinite-plane location nor cut geometry.
            margin = max(
                float(bounds.XLength),
                float(bounds.YLength),
                float(bounds.ZLength),
            )
            x_plane = SplitterEngine._plane_face(
                (
                    (cut_x, bounds.YMin - margin, bounds.ZMin - margin),
                    (cut_x, bounds.YMax + margin, bounds.ZMin - margin),
                    (cut_x, bounds.YMax + margin, bounds.ZMax + margin),
                    (cut_x, bounds.YMin - margin, bounds.ZMax + margin),
                ),
                Part,
                Vector,
            )
            y_plane = SplitterEngine._plane_face(
                (
                    (bounds.XMin - margin, cut_y, bounds.ZMin - margin),
                    (bounds.XMax + margin, cut_y, bounds.ZMin - margin),
                    (bounds.XMax + margin, cut_y, bounds.ZMax + margin),
                    (bounds.XMin - margin, cut_y, bounds.ZMax + margin),
                ),
                Part,
                Vector,
            )
            fuzzy_tolerance = max(
                PARTITION_FUZZY_TOLERANCE_MM,
                float(source_solid.getTolerance(1)),
            )
            partition, _history = source_solid.generalFuse(
                (
                    Part.makeCompound((x_plane,)),
                    Part.makeCompound((y_plane,)),
                ),
                fuzzy_tolerance,
            )
        except Exception as error:
            raise SplitOperationError(
                "Center-plane partition failed during OpenCASCADE general fuse."
            ) from error

        try:
            if partition.isNull() or not partition.isValid():
                raise SplitOperationError(
                    "Center-plane partition returned null or invalid geometry."
                )
            solids = tuple(partition.Solids)
            if not solids:
                raise UnexpectedPartCountError(
                    "Center-plane partition returned no material solids."
                )
            return tuple(sorted(solids, key=SplitterEngine._solid_sort_key))
        except SplitOperationError:
            raise
        except Exception as error:
            raise SplitOperationError(
                "Unable to inspect center-plane partition result."
            ) from error

    @staticmethod
    def _plane_face(points: tuple[tuple[float, float, float], ...], Part, Vector):
        """Build one bounded planar cutting face from four scalar corners."""
        vertices = [Vector(*point) for point in points]
        return Part.Face(Part.makePolygon((*vertices, vertices[0])))

    @staticmethod
    def _solid_sort_key(solid: object) -> tuple[float, ...]:
        """Return a deterministic scalar ordering key for partition solids."""
        bounds = solid.BoundBox
        center = solid.CenterOfMass
        return (
            float(bounds.XMin), float(bounds.YMin), float(bounds.ZMin),
            float(bounds.XMax), float(bounds.YMax), float(bounds.ZMax),
            float(center.x), float(center.y), float(center.z),
            float(solid.Volume),
        )

    @staticmethod
    def _classify_partition_solids(
        solids: tuple[object, ...],
        cut_x: float,
        cut_y: float,
    ) -> tuple[tuple[object, ...], ...]:
        """Classify each partition solid by its unambiguous half-space bounds.

        A result that still crosses either cutting plane is rejected instead
        of being assigned from a potentially misleading centre of mass.
        """
        quadrants: list[list[object]] = [[], [], [], []]
        tolerance = PARTITION_CLASSIFICATION_TOLERANCE_MM
        for solid in solids:
            bounds = solid.BoundBox
            left = float(bounds.XMax) <= cut_x + tolerance
            right = float(bounds.XMin) >= cut_x - tolerance
            lower = float(bounds.YMax) <= cut_y + tolerance
            upper = float(bounds.YMin) >= cut_y - tolerance
            if left == right or lower == upper:
                raise SplitOperationError(
                    "Center-plane partition left a material solid crossing or "
                    "ambiguously touching a cut plane."
                )
            quadrant_index = (
                0 if left and lower else
                1 if right and lower else
                2 if left and upper else
                3
            )
            quadrants[quadrant_index].append(solid)
        return tuple(
            tuple(sorted(items, key=SplitterEngine._solid_sort_key))
            for items in quadrants
        )

    @staticmethod
    def _validated_partition_solid(shape: object, name: str) -> object:
        """Return one non-empty valid partition solid without refinement."""
        try:
            if (
                shape.isNull()
                or not shape.isValid()
                or not shape.isClosed()
                or shape.ShapeType != "Solid"
                or len(shape.Solids) != 1
                or float(shape.Volume) <= 0.0
            ):
                raise InvalidResultingSolidError(
                    f"{name} is not one non-empty valid closed solid."
                )
            return shape
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

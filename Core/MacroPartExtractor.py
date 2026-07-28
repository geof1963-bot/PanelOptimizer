# -*- coding: utf-8 -*-
"""Extract four printable quadrants from one V4.10 macro-cut result."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .Exceptions import (
    InvalidResultingSolidError,
    SplitOperationError,
    UnexpectedPartCountError,
)
from .MacroSplitCore import MacroSplitResult
from .Models import BoundingBox, Point3D, PrintablePart, SplitResult
from .Settings import Settings
from .SplitterEngine import SplitExecution
from .SplittingUtilities import (
    PARTITION_CLASSIFICATION_TOLERANCE_MM,
    finite_positive,
    format_mm,
    volume_tolerance_mm3,
)

__all__ = ["MacroPartExtraction", "MacroPartExtractor"]


@dataclass(frozen=True, slots=True)
class MacroPartExtraction:
    """Four-part runtime result plus macro material-accounting metadata."""

    execution: SplitExecution
    original_source_volume_mm3: float
    macro_result_volume_mm3: float
    surface_groove_removed_volume_mm3: float
    additional_separation_removed_volume_mm3: float
    total_removed_volume_mm3: float
    final_volume_mm3: float
    extraction_delta_mm3: float
    extraction_method: str = "MacroSplitCore.result.Solids"


class MacroPartExtractor:
    """Validate and classify four solids created directly by MacroSplitCore."""

    def __init__(self, split_settings: object = Settings.Split) -> None:
        self._split_settings = split_settings

    def extract(
        self,
        macro_result: MacroSplitResult,
        source_id: str,
        *,
        accept_closed_invalid: bool = False,
        verify_overlap: bool = True,
    ) -> MacroPartExtraction:
        """Return four valid, non-overlapping, volume-conserving quadrants.

        V4.21 full-depth cutters already separated the panel. This method runs
        no boolean or slicing operation; it only reads ``result.Solids``.
        """
        if not isinstance(macro_result, MacroSplitResult):
            raise SplitOperationError(
                "Macro part extraction requires a MacroSplitResult."
            )
        stable_source_id = str(source_id)
        if not stable_source_id:
            raise SplitOperationError("Macro extraction source ID cannot be empty.")
        maximum_width = finite_positive(
            self._split_settings.MAX_PART_WIDTH,
            "Settings.Split.MAX_PART_WIDTH",
        )
        maximum_height = finite_positive(
            self._split_settings.MAX_PART_HEIGHT,
            "Settings.Split.MAX_PART_HEIGHT",
        )
        try:
            solids = tuple(macro_result.shape.Solids)
        except Exception as error:
            raise SplitOperationError(
                "Unable to read solids from the full-depth macro result."
            ) from error
        if len(solids) != 4:
            raise UnexpectedPartCountError(
                "Macro-result separation must produce exactly four solids; "
                f"found {len(solids)}."
            )
        ordered = self._classify(
            solids,
            macro_result.cut_x_mm,
            macro_result.cut_y_mm,
            require_valid=not accept_closed_invalid,
        )

        result_id = f"{stable_source_id}:split:result:0001"
        quadrant_names = (
            ("Part_1", "lower_left"),
            ("Part_2", "lower_right"),
            ("Part_3", "upper_left"),
            ("Part_4", "upper_right"),
        )
        parts = tuple(
            self._part_record(
                shape,
                f"{stable_source_id}:split:part:{index:04d}",
                result_id,
                stable_source_id,
                name,
                quadrant,
                maximum_width,
                maximum_height,
            )
            for index, (shape, (name, quadrant)) in enumerate(
                zip(ordered, quadrant_names),
                start=1,
            )
        )
        macro_volume = float(macro_result.result_volume_mm3)
        final_volume = sum(float(shape.Volume) for shape in ordered)
        delta = abs(macro_volume - final_volume)
        tolerance = volume_tolerance_mm3(macro_volume)
        if delta > tolerance:
            raise SplitOperationError(
                "Macro extraction volume is not preserved: macro result "
                f"{format_mm(macro_volume)} mm^3, final solids "
                f"{format_mm(final_volume)} mm^3, difference "
                f"{format_mm(delta)} mm^3 exceeds geometry tolerance "
                f"{format_mm(tolerance)} mm^3."
            )
        if verify_overlap:
            self._validate_non_overlapping(ordered, tolerance)

        messages = tuple(
            f"{part.name}: {message}"
            for part in parts
            for message in part.validation_messages
        )
        immutable_result = SplitResult(
            result_id=result_id,
            source_id=stable_source_id,
            strategy="macro_full_depth_cut",
            cut_x_mm=macro_result.cut_x_mm,
            cut_y_mm=macro_result.cut_y_mm,
            maximum_width_mm=maximum_width,
            maximum_height_mm=maximum_height,
            parts=parts,
            source_volume_mm3=macro_volume,
            result_volume_mm3=final_volume,
            volume_difference_mm3=delta,
            all_parts_printable=all(part.is_printable for part in parts),
            validation_messages=messages,
        )
        execution = SplitExecution(
            result=immutable_result,
            shapes=ordered,
            partition_method="MacroSplitCore.result.Solids",
            initial_partition_solid_count=4,
            solids_per_quadrant=(1, 1, 1, 1),
        )
        return MacroPartExtraction(
            execution=execution,
            original_source_volume_mm3=macro_result.source_volume_mm3,
            macro_result_volume_mm3=macro_volume,
            surface_groove_removed_volume_mm3=(
                macro_result.surface_groove_removed_volume_mm3
            ),
            additional_separation_removed_volume_mm3=(
                macro_result.additional_separation_removed_volume_mm3
            ),
            total_removed_volume_mm3=(
                macro_result.source_volume_mm3 - macro_volume
            ),
            final_volume_mm3=final_volume,
            extraction_delta_mm3=delta,
        )

    @staticmethod
    def _classify(
        solids: tuple[object, ...],
        cut_x: float,
        cut_y: float,
        require_valid: bool = True,
    ) -> tuple[object, object, object, object]:
        """Classify by material center with canonical per-quadrant identity."""
        quadrants: dict[tuple[bool, bool], list[object]] = {}
        for solid in solids:
            try:
                center = solid.CenterOfMass
                key = (float(center.x) >= cut_x, float(center.y) >= cut_y)
            except Exception as error:
                raise SplitOperationError(
                    "Unable to classify a macro extraction solid."
                ) from error
            quadrants.setdefault(key, []).append(solid)
        keys = ((False, False), (True, False), (False, True), (True, True))
        counts = tuple(len(quadrants.get(key, ())) for key in keys)
        if counts != (1, 1, 1, 1):
            raise UnexpectedPartCountError(
                "Macro extraction quadrant component counts are "
                f"{counts}; expected (1, 1, 1, 1)."
            )
        ordered = tuple(quadrants[key][0] for key in keys)
        for index, solid in enumerate(ordered, start=1):
            try:
                valid = (
                    solid.ShapeType == "Solid"
                    and not solid.isNull()
                    and solid.isClosed()
                    and (not require_valid or solid.isValid())
                    and len(solid.Solids) == 1
                    and float(solid.Volume) > 0.0
                )
            except Exception as error:
                raise InvalidResultingSolidError(
                    f"Unable to validate Part_{index}."
                ) from error
            if not valid:
                raise InvalidResultingSolidError(
                    f"Part_{index} is not one supported non-empty closed solid."
                )
        return ordered  # type: ignore[return-value]

    @staticmethod
    def _part_record(
        shape, part_id, result_id, source_id, name, quadrant,
        maximum_width, maximum_height,
    ) -> PrintablePart:
        """Create one immutable part record using only configured X/Y limits."""
        bounds = shape.BoundBox
        size_x = float(bounds.XLength)
        size_y = float(bounds.YLength)
        size_z = float(bounds.ZLength)
        # Neutralize only kernel-coordinate noise so mathematical equality
        # passes; this geometry tolerance is not a printable allowance.
        within_x = (
            size_x <= maximum_width + PARTITION_CLASSIFICATION_TOLERANCE_MM
        )
        within_y = (
            size_y <= maximum_height + PARTITION_CLASSIFICATION_TOLERANCE_MM
        )
        messages = []
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
        shapes: tuple[object, object, object, object],
        tolerance: float,
    ) -> None:
        """Reject positive pairwise common volume above kernel tolerance."""
        for first_index, first in enumerate(shapes):
            for second_index, second in enumerate(shapes[first_index + 1 :], first_index + 1):
                try:
                    overlap = float(first.common(second).Volume)
                except Exception as error:
                    raise SplitOperationError(
                        "Unable to verify extracted-part overlap."
                    ) from error
                if not math.isfinite(overlap) or overlap > tolerance:
                    raise SplitOperationError(
                        f"Part_{first_index + 1} and Part_{second_index + 1} "
                        f"overlap by {format_mm(overlap)} mm^3."
                    )

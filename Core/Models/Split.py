# -*- coding: utf-8 -*-
"""Split, joinery, and printable-part data contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .Common import BoundingBox, Direction3D, Point3D
from .Paths import CandidatePath


@dataclass(frozen=True, slots=True)
class SplitPlan:
    """A selected set of seam paths for producing printable parts."""

    plan_id: str
    geometry_id: str
    target_part_count: int
    cut_paths: tuple[CandidatePath, ...]
    total_cost: float
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DowelPlacement:
    """The parameters for one alignment dowel and its mating holes."""

    dowel_id: str
    position: Point3D
    axis: Direction3D
    dowel_diameter_mm: float
    hole_diameter_mm: float
    hole_depth_mm: float


@dataclass(frozen=True, slots=True)
class JointSpecification:
    """A joinery definition associated with one candidate seam path."""

    joint_id: str
    candidate_path_id: str
    profile_name: str
    dowels: tuple[DowelPlacement, ...]
    glue_clearance_mm: float
    chamfer_mm: float
    filler_groove_depth_mm: float


@dataclass(frozen=True, slots=True)
class JoineryPlan:
    """The joinery to apply to one selected split plan."""

    split_plan_id: str
    joints: tuple[JointSpecification, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PrintablePart:
    """One validated split part with an opaque runtime-geometry reference.

    All dimensions use model-coordinate millimetres. ``geometry_reference``
    is a stable lookup key owned by the caller; it is never a FreeCAD object.
    Printable validity records independent X/Y comparisons against the
    configured effective limits.
    """

    part_id: str
    split_result_id: str
    source_id: str
    name: str
    quadrant: Literal[
        "lower_left",
        "lower_right",
        "upper_left",
        "upper_right",
    ]
    geometry_reference: str
    bounding_box: BoundingBox
    size_x_mm: float
    size_y_mm: float
    size_z_mm: float
    volume_mm3: float
    within_x_limit: bool
    within_y_limit: bool
    is_printable: bool
    joint_ids: tuple[str, ...] = ()
    validation_messages: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SplitResult:
    """Deterministic result of one non-path-based split operation.

    Attributes:
        result_id: Stable operation ID derived from ``source_id``.
        source_id: Immutable identity of the source geometry.
        strategy: Exact implemented split strategy.
        cut_x_mm: Model X coordinate of the vertical cutting plane.
        cut_y_mm: Model Y coordinate of the horizontal cutting plane.
        maximum_width_mm: Configured effective X limit used for validation.
        maximum_height_mm: Configured effective Y limit used for validation.
        parts: Exactly four parts in lower-left, lower-right, upper-left,
            upper-right order for the current prototype.
        source_volume_mm3: Source solid volume before splitting.
        result_volume_mm3: Sum of the four result volumes.
        volume_difference_mm3: Absolute source/result volume difference.
        all_parts_printable: Whether every part satisfies both configured
            effective X/Y limits.
        validation_messages: Ordered workflow-level validation messages.

    This is not a path plan and contains no route, score, joinery, document
    object, or FreeCAD shape.
    """

    result_id: str
    source_id: str
    strategy: Literal[
        "bounding_box_center_quadrants",
        "macro_full_depth_cut",
    ]
    cut_x_mm: float
    cut_y_mm: float
    maximum_width_mm: float
    maximum_height_mm: float
    parts: tuple[PrintablePart, ...]
    source_volume_mm3: float
    result_volume_mm3: float
    volume_difference_mm3: float
    all_parts_printable: bool
    validation_messages: tuple[str, ...] = ()

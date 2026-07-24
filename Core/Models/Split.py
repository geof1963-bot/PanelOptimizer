# -*- coding: utf-8 -*-
"""Split, joinery, and printable-part data contracts."""

from __future__ import annotations

from dataclasses import dataclass

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
    """A split result and its opaque reference to the produced geometry."""

    part_id: str
    split_plan_id: str
    geometry_reference: str
    bounding_box: BoundingBox
    volume_mm3: float
    joint_ids: tuple[str, ...]
    is_printable: bool
    validation_messages: tuple[str, ...] = ()

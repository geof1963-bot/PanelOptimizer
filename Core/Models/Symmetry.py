# -*- coding: utf-8 -*-
"""Immutable geometric symmetry observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .Common import Direction3D, Point3D


@dataclass(frozen=True, slots=True)
class SymmetryObservation:
    """One measured reflection or rotational symmetry relationship.

    Attributes:
        observation_id: Deterministic ID using
            ``{source_id}:geometry:symmetry:{index:04d}`` after canonical
            ordering by type, origin, and direction.
        symmetry_type: ``reflection`` or ``rotation``.
        origin: A point on the reflection plane or rotation axis, in model
            coordinates and mm.
        direction: Unit reflection-plane normal or rotation-axis direction in
            model coordinates.
        rotational_order: Repetitions per full revolution for rotational
            symmetry; ``None`` for reflection.
        maximum_deviation_mm: Largest measured correspondence deviation, in mm.
            This is evidence, not a normalized rating or threshold.
        related_feature_ids: Topology feature IDs participating in the
            relationship.

    This is a source-level relationship observation, not a local surface
    sample or a global dimension.
    """

    observation_id: str
    symmetry_type: Literal["reflection", "rotation"]
    origin: Point3D
    direction: Direction3D
    rotational_order: int | None
    maximum_deviation_mm: float
    related_feature_ids: tuple[str, ...] = ()

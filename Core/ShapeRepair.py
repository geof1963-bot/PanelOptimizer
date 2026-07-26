# -*- coding: utf-8 -*-
"""Conservative transient B-rep repair and geometry-equivalence checks."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .SplittingUtilities import (
    KERNEL_VOLUME_ABSOLUTE_TOLERANCE_MM3,
    KERNEL_VOLUME_RELATIVE_TOLERANCE,
)

# OpenCASCADE repair precision in millimetres. These values govern shape-fix
# mechanics only; they are unrelated to manufacturing or printer limits.
REPAIR_WORKING_PRECISION_MM = 1.0e-7
REPAIR_MINIMUM_PRECISION_MM = 1.0e-7
REPAIR_MAXIMUM_PRECISION_MM = 1.0e-3
REPAIR_FIXED_TOLERANCE_MM = 1.0e-7

# Strict geometry-equivalence tolerances. Bounds and centre coordinates use an
# absolute model-space tolerance. Volume uses a kernel-scale absolute/relative
# comparison and never represents a manufacturing allowance.
REPAIR_LINEAR_EQUIVALENCE_TOLERANCE_MM = 1.0e-7
REPAIR_VOLUME_ABSOLUTE_TOLERANCE_MM3 = (
    KERNEL_VOLUME_ABSOLUTE_TOLERANCE_MM3
)
REPAIR_VOLUME_RELATIVE_TOLERANCE = KERNEL_VOLUME_RELATIVE_TOLERANCE

__all__ = [
    "REPAIR_FIXED_TOLERANCE_MM",
    "REPAIR_LINEAR_EQUIVALENCE_TOLERANCE_MM",
    "REPAIR_MAXIMUM_PRECISION_MM",
    "REPAIR_MINIMUM_PRECISION_MM",
    "REPAIR_VOLUME_ABSOLUTE_TOLERANCE_MM3",
    "REPAIR_VOLUME_RELATIVE_TOLERANCE",
    "REPAIR_WORKING_PRECISION_MM",
    "RepairAttempt",
    "RepairOutcome",
    "attempt_transient_repair",
]


@dataclass(frozen=True, slots=True)
class _GeometryMetrics:
    """Finite geometry values used only for repair equivalence validation."""

    bounds_mm: tuple[float, float, float, float, float, float]
    center_mm: tuple[float, float, float]
    volume_mm3: float


@dataclass(frozen=True, slots=True)
class RepairAttempt:
    """Immutable scalar result of one deterministic transient strategy."""

    strategy: str
    accepted: bool
    result: str


@dataclass(frozen=True, slots=True)
class RepairOutcome:
    """Transient repair result; ``shape`` stays outside Core.Models."""

    shape: object | None
    strategy: str
    attempts: tuple[RepairAttempt, ...]


def attempt_transient_repair(shape: object) -> RepairOutcome:
    """Try minimal deterministic repair strategies on independent copies.

    Strategies are ordered from the smallest intervention to increasingly
    broader tolerance/refinement operations. Every strategy starts from a new
    deep geometry copy. A result is accepted only after structural validation
    and strict comparison with the original measurable geometry.
    """
    try:
        original_metrics = _metrics(shape)
    except Exception as error:
        return RepairOutcome(
            shape=None,
            strategy="",
            attempts=(
                RepairAttempt(
                    strategy="preflight",
                    accepted=False,
                    result=f"original metrics unavailable: {error}",
                ),
            ),
        )
    if original_metrics.volume_mm3 <= 0.0:
        return RepairOutcome(
            shape=None,
            strategy="",
            attempts=(
                RepairAttempt(
                    strategy="preflight",
                    accepted=False,
                    result="original volume is not positive",
                ),
            ),
        )

    strategies = (
        ("shape_fix", _shape_fix),
        ("fixed_tolerance_then_shape_fix", _fixed_tolerance_then_shape_fix),
        ("remove_splitter_then_shape_fix", _remove_splitter_then_shape_fix),
    )
    attempts: list[RepairAttempt] = []
    for name, strategy in strategies:
        try:
            candidate = strategy(shape)
            accepted_shape, rejection = _validated_equivalent_shape(
                candidate,
                original_metrics,
            )
            if accepted_shape is not None:
                attempts.append(RepairAttempt(name, True, "accepted"))
                return RepairOutcome(
                    shape=accepted_shape,
                    strategy=name,
                    attempts=tuple(attempts),
                )
            attempts.append(RepairAttempt(name, False, rejection))
        except Exception as error:
            attempts.append(
                RepairAttempt(name, False, f"operation failed: {error}")
            )
    return RepairOutcome(shape=None, strategy="", attempts=tuple(attempts))


def _shape_fix(shape: object) -> object:
    """Apply standard ShapeFix to a transient deep geometry copy."""
    candidate = shape.copy()
    if not bool(
        candidate.fix(
            REPAIR_WORKING_PRECISION_MM,
            REPAIR_MINIMUM_PRECISION_MM,
            REPAIR_MAXIMUM_PRECISION_MM,
        )
    ):
        raise RuntimeError("shape fix reported failure")
    return candidate


def _fixed_tolerance_then_shape_fix(shape: object) -> object:
    """Normalize transient tolerances before the same standard shape fix."""
    candidate = shape.copy()
    candidate.fixTolerance(REPAIR_FIXED_TOLERANCE_MM)
    if not bool(
        candidate.fix(
            REPAIR_WORKING_PRECISION_MM,
            REPAIR_MINIMUM_PRECISION_MM,
            REPAIR_MAXIMUM_PRECISION_MM,
        )
    ):
        raise RuntimeError("shape fix reported failure")
    return candidate


def _remove_splitter_then_shape_fix(shape: object) -> object:
    """Refine only a transient copy, then apply the standard shape fix."""
    candidate = shape.copy().removeSplitter()
    if not bool(
        candidate.fix(
            REPAIR_WORKING_PRECISION_MM,
            REPAIR_MINIMUM_PRECISION_MM,
            REPAIR_MAXIMUM_PRECISION_MM,
        )
    ):
        raise RuntimeError("shape fix reported failure")
    return candidate


def _validated_equivalent_shape(
    candidate: object,
    original_metrics: _GeometryMetrics,
) -> tuple[object | None, str]:
    """Return one valid closed solid only when geometry remains equivalent."""
    try:
        if bool(candidate.isNull()):
            return None, "result is null"
        if not bool(candidate.isValid()):
            return None, "result remains invalid"
        solids = tuple(candidate.Solids)
        if len(solids) != 1:
            return None, f"result contains {len(solids)} solids"
        solid = solids[0]
        if bool(solid.isNull()) or not bool(solid.isValid()):
            return None, "result solid is null or invalid"
        if not _closed(solid):
            return None, "result solid is not closed"
        candidate_metrics = _metrics(solid)
        if candidate_metrics.volume_mm3 <= 0.0:
            return None, "result volume is not positive"
        mismatch = _equivalence_mismatch(original_metrics, candidate_metrics)
        if mismatch:
            return None, mismatch
        return solid, ""
    except Exception as error:
        return None, f"post-validation failed: {error}"


def _metrics(shape: object) -> _GeometryMetrics:
    """Read finite bounds, centre of mass, and volume from one shape."""
    bounds = shape.BoundBox
    center = shape.CenterOfMass
    values = (
        float(bounds.XMin),
        float(bounds.YMin),
        float(bounds.ZMin),
        float(bounds.XMax),
        float(bounds.YMax),
        float(bounds.ZMax),
        float(center.x),
        float(center.y),
        float(center.z),
        float(shape.Volume),
    )
    if not all(math.isfinite(value) for value in values):
        raise ValueError("non-finite geometry measurement")
    return _GeometryMetrics(
        bounds_mm=values[:6],
        center_mm=values[6:9],
        volume_mm3=values[9],
    )


def _equivalence_mismatch(
    original: _GeometryMetrics,
    repaired: _GeometryMetrics,
) -> str:
    """Describe the first strict bounds, centre, or volume mismatch."""
    if any(
        abs(before - after) > REPAIR_LINEAR_EQUIVALENCE_TOLERANCE_MM
        for before, after in zip(original.bounds_mm, repaired.bounds_mm)
    ):
        return "bounding box changed beyond geometry tolerance"
    if any(
        abs(before - after) > REPAIR_LINEAR_EQUIVALENCE_TOLERANCE_MM
        for before, after in zip(original.center_mm, repaired.center_mm)
    ):
        return "center of mass changed beyond geometry tolerance"
    volume_tolerance = max(
        REPAIR_VOLUME_ABSOLUTE_TOLERANCE_MM3,
        abs(original.volume_mm3) * REPAIR_VOLUME_RELATIVE_TOLERANCE,
    )
    if abs(original.volume_mm3 - repaired.volume_mm3) > volume_tolerance:
        return "volume changed beyond geometry tolerance"
    return ""


def _closed(shape: object) -> bool:
    """Read a shape's closed state without changing it."""
    member = getattr(shape, "isClosed", None)
    return bool(member() if callable(member) else member)

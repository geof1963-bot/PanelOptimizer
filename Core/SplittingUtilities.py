# -*- coding: utf-8 -*-
"""Low-level geometry-only validation helpers for deterministic splitting."""

from __future__ import annotations

import math

from .Exceptions import SplitOperationError


# OpenCASCADE result-validation tolerances. These validate boolean geometry;
# they are unrelated to printer limits or manufacturing acceptance.
KERNEL_VOLUME_ABSOLUTE_TOLERANCE_MM3 = 1.0e-6
KERNEL_VOLUME_RELATIVE_TOLERANCE = 1.0e-9


def finite_positive(value: object, label: str) -> float:
    """Return one finite positive split configuration value."""
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise SplitOperationError(
            f"{label} must be a finite positive number."
        ) from error
    if not math.isfinite(result) or result <= 0.0:
        raise SplitOperationError(
            f"{label} must be a finite positive number."
        )
    return result


def volume_tolerance_mm3(source_volume_mm3: float) -> float:
    """Return geometry-only volume tolerance scaled to the source solid."""
    return max(
        KERNEL_VOLUME_ABSOLUTE_TOLERANCE_MM3,
        abs(source_volume_mm3) * KERNEL_VOLUME_RELATIVE_TOLERANCE,
    )


def format_mm(value: float) -> str:
    """Format a deterministic millimetre value for validation messages."""
    return format(value, ".12g")

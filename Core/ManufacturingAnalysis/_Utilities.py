# -*- coding: utf-8 -*-
"""Low-level deterministic helpers for manufacturing evaluation."""

from __future__ import annotations

import math

from ..Exceptions import ConstraintEvaluationError
from ..Models.Manufacturing import EvaluationSeverity, EvaluationStatus


# Floating-point representation tolerance used only to validate the arithmetic
# identity of composed configuration values. It is never applied to a part
# measurement or manufacturing pass/fail comparison.
CONFIGURATION_COHERENCE_TOLERANCE_MM = 1.0e-12


def finite_number(value: object, label: str) -> float:
    """Return one finite configured or measured scalar value."""
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ConstraintEvaluationError(
            f"{label} must be a finite numeric value."
        ) from error
    if not math.isfinite(result):
        raise ConstraintEvaluationError(
            f"{label} must be a finite numeric value."
        )
    return result


def format_value(value: float) -> str:
    """Format one finite scalar deterministically for rationale text."""
    return format(value, ".12g")


def comparison_result(
    measured: float,
    required: float,
    comparison: str,
) -> bool:
    """Apply one supported scalar comparison without tolerance or scoring."""
    if comparison == "less_than_or_equal":
        return measured <= required
    if comparison == "greater_than_or_equal":
        return measured >= required
    if comparison == "equal":
        return measured == required
    raise ConstraintEvaluationError(
        f"Unsupported scalar comparison '{comparison}'."
    )


def configuration_values_equal(first: float, second: float) -> bool:
    """Compare two configuration-derived millimetre values for coherence."""
    return math.isclose(
        first,
        second,
        rel_tol=0.0,
        abs_tol=CONFIGURATION_COHERENCE_TOLERANCE_MM,
    )


def result_state(
    passed: bool,
    level: str,
    configured_severity: str,
) -> tuple[EvaluationStatus, EvaluationSeverity]:
    """Return the explicit result state for one scalar comparison."""
    if passed:
        return "pass", "none"
    if level == "hard":
        return "fail", "error"
    if level == "warning" and configured_severity in {
        "advisory",
        "warning",
    }:
        return "warning", configured_severity
    raise ConstraintEvaluationError(
        "Constraint level and severity do not define a supported result."
    )

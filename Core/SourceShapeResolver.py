# -*- coding: utf-8 -*-
"""Read-only diagnosis and conservative transient source-solid resolution."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .Exceptions import InvalidShapeError, NullShapeError
from .ShapeRepair import RepairAttempt, attempt_transient_repair

__all__ = [
    "ResolvedSourceShape",
    "ShapeDiagnostic",
    "SolidDiagnostic",
    "diagnose_source_shape",
    "resolve_source_shape",
]


@dataclass(frozen=True, slots=True)
class SolidDiagnostic:
    """Scalar geometry and validity facts for one contained solid."""

    index: int
    shape_type: str
    is_null: bool | None
    is_valid: bool | None
    is_closed: bool | None
    shell_count: int
    check_status: str
    check_message: str
    problematic_subshape_count: int | None
    volume_mm3: float | None
    area_mm2: float | None
    bounding_box_mm: tuple[float, float, float, float, float, float] | None
    center_of_mass_mm: tuple[float, float, float] | None


@dataclass(frozen=True, slots=True)
class ShapeDiagnostic:
    """FreeCAD-independent facts read from one source B-rep container.

    ``check_status`` is ``completed`` when the available read-only ``check()``
    call returns, ``failed`` when it raises, and ``unavailable`` when the shape
    exposes no such call. Completion is not treated as validity. The optional
    message is exception text only; no FreeCAD or OpenCASCADE object is
    retained.
    """

    shape_type: str
    solid_count: int
    shell_count: int
    compsolid_count: int
    is_null: bool | None
    is_valid: bool | None
    is_closed: bool | None
    check_status: str
    check_message: str
    solids: tuple[SolidDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class ResolvedSourceShape:
    """Runtime source resolution; deliberately outside immutable Core.Models.

    ``shape`` is either caller-owned valid geometry used read-only or a repaired
    transient copy. ``diagnostic`` and ``messages`` contain only immutable
    descriptive values.
    """

    shape: object
    diagnostic: ShapeDiagnostic
    used_contained_solid: bool
    source_resolution: str
    repair_strategy: str = ""
    repair_attempts: tuple[RepairAttempt, ...] = ()
    messages: tuple[str, ...] = ()


def diagnose_source_shape(
    shape: object,
    *,
    run_shape_check: bool = True,
) -> ShapeDiagnostic:
    """Describe source/container validity without modifying its geometry.

    The optional OpenCASCADE-backed ``shape.check()`` call is diagnostic only.
    It is never used to heal, rebuild, copy, or accept geometry, and its return
    value is not interpreted as a replacement for ``isValid()``.
    """
    if shape is None:
        raise NullShapeError("Selected shape is missing.")

    is_null = _optional_boolean(shape, "isNull")
    is_valid = _optional_boolean(shape, "isValid")
    is_closed = _optional_boolean(shape, "isClosed")
    solids = _topology_items(shape, "Solids")
    shells = _topology_items(shape, "Shells")
    compsolids = _topology_items(shape, "CompSolids")
    solid_diagnostics = tuple(
        _solid_diagnostic(solid, index, run_shape_check)
        for index, solid in enumerate(solids, start=1)
    )

    check_status = "unavailable"
    check_message = ""
    check_method = getattr(shape, "check", None)
    if run_shape_check and callable(check_method):
        try:
            check_method()
            check_status = "completed"
        except Exception as error:
            check_status = "failed"
            check_message = str(error)

    return ShapeDiagnostic(
        shape_type=str(getattr(shape, "ShapeType", "Unknown")),
        solid_count=len(solids),
        shell_count=len(shells),
        compsolid_count=len(compsolids),
        is_null=is_null,
        is_valid=is_valid,
        is_closed=is_closed,
        check_status=check_status,
        check_message=check_message,
        solids=solid_diagnostics,
    )


def resolve_source_shape(shape: object) -> ResolvedSourceShape:
    """Return exactly one valid or safely repaired source solid.

    A valid top-level ``Solid`` is accepted directly. Any other top-level
    container is accepted only when it exposes exactly one contained solid.
    An invalid sole solid receives conservative repair attempts on transient
    deep copies. Invalid, absent, or multiple results are rejected explicitly.
    """
    diagnostic = diagnose_source_shape(shape, run_shape_check=False)
    if diagnostic.is_null is None:
        raise NullShapeError("Selected shape cannot report whether it is null.")
    if diagnostic.is_null:
        raise NullShapeError("Selected shape is null.")

    if diagnostic.shape_type == "Solid":
        if diagnostic.is_valid is True:
            return ResolvedSourceShape(
                shape=shape,
                diagnostic=diagnostic,
                used_contained_solid=False,
                source_resolution="direct",
            )
        return _repair_or_reject(
            source_shape=shape,
            invalid_solid=shape,
            used_contained_solid=False,
            source_resolution="repaired_source_solid",
        )

    solids = _topology_items(shape, "Solids")
    if not solids:
        raise InvalidShapeError("Selected shape contains no valid solid.")
    if len(solids) > 1:
        valid_count = sum(
            item.is_null is False and item.is_valid is True
            for item in diagnostic.solids
        )
        raise InvalidShapeError(
            f"Selected shape contains {len(solids)} solids ({valid_count} "
            "valid); V4.00 requires exactly one."
        )

    contained = diagnostic.solids[0]
    if contained.is_null is not False:
        raise InvalidShapeError("Selected shape contains a null solid.")
    if contained.is_valid is not True:
        return _repair_or_reject(
            source_shape=shape,
            invalid_solid=solids[0],
            used_contained_solid=True,
            source_resolution="repaired_contained_solid",
        )

    messages = (
        (
            "Top-level shape invalid; using one valid contained solid."
            if diagnostic.is_valid is not True
            else "Using one valid contained solid from the source container."
        ),
    )
    return ResolvedSourceShape(
        shape=solids[0],
        diagnostic=diagnostic,
        used_contained_solid=True,
        source_resolution="contained_solid",
        messages=messages,
    )


def _repair_or_reject(
    source_shape: object,
    invalid_solid: object,
    used_contained_solid: bool,
    source_resolution: str,
) -> ResolvedSourceShape:
    """Repair one invalid solid transiently or raise a diagnostic failure."""
    diagnostic = diagnose_source_shape(source_shape, run_shape_check=True)
    solid_diagnostic = (
        diagnostic.solids[0]
        if diagnostic.solids
        else _solid_diagnostic(invalid_solid, 1, True)
    )
    outcome = attempt_transient_repair(invalid_solid)
    if outcome.shape is None:
        result = outcome.attempts[-1].result if outcome.attempts else "not run"
        raise InvalidShapeError(
            "Selected solid is invalid and could not be repaired safely "
            f"(contained solids={diagnostic.solid_count}, "
            f"valid={solid_diagnostic.is_valid}, "
            f"closed={solid_diagnostic.is_closed}, repair attempted=yes, "
            f"result={result})."
        )
    return ResolvedSourceShape(
        shape=outcome.shape,
        diagnostic=diagnostic,
        used_contained_solid=used_contained_solid,
        source_resolution=source_resolution,
        repair_strategy=outcome.strategy,
        repair_attempts=outcome.attempts,
        messages=(
            "Selected solid is invalid.",
            "Transient B-rep repair succeeded "
            f"(strategy: {outcome.strategy}).",
            "Original source remains unchanged.",
        ),
    )


def _optional_boolean(value: object, name: str) -> bool | None:
    """Read one optional boolean property or zero-argument method."""
    member = getattr(value, name, None)
    if member is None:
        return None
    try:
        return bool(member() if callable(member) else member)
    except Exception:
        return None


def _solid_diagnostic(
    solid: object,
    index: int,
    run_shape_check: bool,
) -> SolidDiagnostic:
    """Collect immutable pre-repair facts for one contained solid."""
    check_status, check_message = _shape_check(solid, run_shape_check)
    return SolidDiagnostic(
        index=index,
        shape_type=str(getattr(solid, "ShapeType", "Unknown")),
        is_null=_optional_boolean(solid, "isNull"),
        is_valid=_optional_boolean(solid, "isValid"),
        is_closed=_optional_boolean(solid, "isClosed"),
        shell_count=len(_topology_items(solid, "Shells")),
        check_status=check_status,
        check_message=check_message,
        problematic_subshape_count=(
            _problematic_subshape_count(solid) if run_shape_check else None
        ),
        volume_mm3=_optional_float(solid, "Volume"),
        area_mm2=_optional_float(solid, "Area"),
        bounding_box_mm=_optional_bounds(solid),
        center_of_mass_mm=_optional_point(solid, "CenterOfMass"),
    )


def _shape_check(shape: object, enabled: bool) -> tuple[str, str]:
    """Run the optional detailed B-rep check and retain scalar output only."""
    method = getattr(shape, "check", None)
    if not enabled or not callable(method):
        return "unavailable", ""
    try:
        method(True)
        return "completed", ""
    except TypeError:
        try:
            method()
            return "completed", ""
        except Exception as error:
            return "failed", str(error)
    except Exception as error:
        return "failed", str(error)


def _problematic_subshape_count(shape: object) -> int:
    """Count exposed invalid subshapes; overlapping levels count separately."""
    count = 0
    for name in ("Shells", "Faces", "Wires", "Edges", "Vertexes"):
        for item in _topology_items(shape, name):
            if _optional_boolean(item, "isValid") is not True:
                count += 1
    return count


def _optional_float(value: object, name: str) -> float | None:
    """Read one finite scalar measurement when available."""
    try:
        result = float(getattr(value, name))
        return result if math.isfinite(result) else None
    except (AttributeError, TypeError, ValueError):
        return None


def _optional_bounds(
    shape: object,
) -> tuple[float, float, float, float, float, float] | None:
    """Read six finite bounding-box coordinates when available."""
    try:
        bounds = shape.BoundBox
        values = tuple(
            float(value)
            for value in (
                bounds.XMin,
                bounds.YMin,
                bounds.ZMin,
                bounds.XMax,
                bounds.YMax,
                bounds.ZMax,
            )
        )
        return values if all(math.isfinite(value) for value in values) else None
    except (AttributeError, TypeError, ValueError):
        return None


def _optional_point(
    shape: object,
    name: str,
) -> tuple[float, float, float] | None:
    """Read one finite point-like measurement when available."""
    try:
        point = getattr(shape, name)
        values = float(point.x), float(point.y), float(point.z)
        return values if all(math.isfinite(value) for value in values) else None
    except (AttributeError, TypeError, ValueError):
        return None


def _topology_items(value: object, name: str) -> tuple[object, ...]:
    """Read one topology collection in the stable order supplied by FreeCAD."""
    try:
        return tuple(getattr(value, name, ()))
    except Exception as error:
        raise InvalidShapeError(
            f"Selected shape cannot expose its {name.lower()}."
        ) from error

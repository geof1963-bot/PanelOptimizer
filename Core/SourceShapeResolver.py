# -*- coding: utf-8 -*-
"""Read-only diagnosis and conservative transient source-solid resolution."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .Exceptions import InvalidShapeError, NullShapeError

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

    Detailed OpenCASCADE ``check()`` calls are deliberately skipped because
    malformed native geometry can crash the FreeCAD process. ``check_status``
    therefore records ``skipped_for_safety`` without calling that API.
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

    ``shape`` is caller-owned valid geometry used read-only downstream.
    ``diagnostic`` and ``messages`` contain only immutable descriptive values.
    """

    shape: object
    diagnostic: ShapeDiagnostic
    used_contained_solid: bool
    source_resolution: str
    messages: tuple[str, ...] = ()


def diagnose_source_shape(
    shape: object,
    *,
    run_shape_check: bool = False,
) -> ShapeDiagnostic:
    """Describe source/container validity without modifying its geometry.

    ``run_shape_check`` is retained for call compatibility but intentionally
    ignored. Detailed OpenCASCADE checks and per-subshape validity scans are
    unsafe on malformed B-reps and are never invoked here.
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
        _solid_diagnostic(solid, index)
        for index, solid in enumerate(solids, start=1)
    )

    check_status = "skipped_for_safety"
    check_message = "Detailed B-rep check disabled for invalid-shape safety."

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
    """Return exactly one valid source solid without attempting repair.

    A valid top-level ``Solid`` is accepted directly. Any other top-level
    container is accepted only when it exposes exactly one contained solid.
    Invalid solids are rejected with crash-safe scalar diagnostics. Automatic
    repair is disabled and no geometry-producing operation is called.
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
        raise _invalid_solid_error(diagnostic, shape)

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
        raise _invalid_solid_error(diagnostic, solids[0])

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


def _invalid_solid_error(
    diagnostic: ShapeDiagnostic,
    invalid_solid: object,
) -> InvalidShapeError:
    """Build one concise crash-safe invalid-source exception."""
    solid_diagnostic = (
        diagnostic.solids[0]
        if diagnostic.solids
        else _solid_diagnostic(invalid_solid, 1)
    )
    bounds = _format_bounds(solid_diagnostic.bounding_box_mm)
    volume = _format_scalar(solid_diagnostic.volume_mm3)
    return InvalidShapeError(
        "Source solid is invalid.\n"
        "Automatic repair is disabled for safety.\n"
        "Diagnostics: "
        f"shape type={solid_diagnostic.shape_type}; "
        f"valid={solid_diagnostic.is_valid}; "
        f"closed={solid_diagnostic.is_closed}; "
        f"solid count={diagnostic.solid_count}; "
        f"shell count={solid_diagnostic.shell_count}; "
        f"volume={volume} mm^3; bounding box={bounds}; "
        f"B-rep check={solid_diagnostic.check_status}."
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
) -> SolidDiagnostic:
    """Collect conservative scalar facts without detailed native checks."""
    return SolidDiagnostic(
        index=index,
        shape_type=str(getattr(solid, "ShapeType", "Unknown")),
        is_null=_optional_boolean(solid, "isNull"),
        is_valid=_optional_boolean(solid, "isValid"),
        is_closed=_optional_boolean(solid, "isClosed"),
        shell_count=len(_topology_items(solid, "Shells")),
        check_status="skipped_for_safety",
        check_message="Detailed B-rep check disabled for invalid-shape safety.",
        problematic_subshape_count=None,
        volume_mm3=_optional_float(solid, "Volume"),
        area_mm2=None,
        bounding_box_mm=_optional_bounds(solid),
        center_of_mass_mm=None,
    )


def _format_scalar(value: float | None) -> str:
    """Format an optional diagnostic scalar deterministically."""
    return "unavailable" if value is None else format(value, ".12g")


def _format_bounds(
    values: tuple[float, float, float, float, float, float] | None,
) -> str:
    """Format optional bounds without evaluating additional geometry."""
    if values is None:
        return "unavailable"
    return "(" + ", ".join(format(value, ".12g") for value in values) + ") mm"


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


def _topology_items(value: object, name: str) -> tuple[object, ...]:
    """Read one topology collection in the stable order supplied by FreeCAD."""
    try:
        return tuple(getattr(value, name, ()))
    except Exception as error:
        raise InvalidShapeError(
            f"Selected shape cannot expose its {name.lower()}."
        ) from error

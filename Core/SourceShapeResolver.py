# -*- coding: utf-8 -*-
"""Read-only diagnosis and conservative source-solid resolution."""

from __future__ import annotations

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
    """Scalar validity facts for one contained solid in source order."""

    index: int
    shape_type: str
    is_null: bool | None
    is_valid: bool | None


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

    ``shape`` is caller-owned FreeCAD geometry used read-only downstream.
    ``diagnostic`` and ``messages`` contain only immutable descriptive values.
    """

    shape: object
    diagnostic: ShapeDiagnostic
    used_contained_solid: bool
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
        SolidDiagnostic(
            index=index,
            shape_type=str(getattr(solid, "ShapeType", "Unknown")),
            is_null=_optional_boolean(solid, "isNull"),
            is_valid=_optional_boolean(solid, "isValid"),
        )
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
    """Return exactly one valid source solid using the V4.00 policy.

    A valid top-level ``Solid`` is accepted directly. Any other top-level
    container is accepted only when it exposes exactly one contained solid and
    that solid is non-null and valid. Invalid, absent, or multiple contained
    solids are rejected explicitly. No repair or geometry-producing operation
    is called.
    """
    diagnostic = diagnose_source_shape(shape, run_shape_check=False)
    if diagnostic.is_null is None:
        raise NullShapeError("Selected shape cannot report whether it is null.")
    if diagnostic.is_null:
        raise NullShapeError("Selected shape is null.")

    if diagnostic.shape_type == "Solid":
        if diagnostic.is_valid is not True:
            raise InvalidShapeError("Selected contained solid is invalid.")
        return ResolvedSourceShape(
            shape=shape,
            diagnostic=diagnostic,
            used_contained_solid=False,
        )

    solids = _topology_items(shape, "Solids")
    if not solids:
        raise InvalidShapeError("Selected shape contains no valid solid.")
    invalid_solids = tuple(
        item
        for item in diagnostic.solids
        if item.is_null is not False or item.is_valid is not True
    )
    if invalid_solids:
        raise InvalidShapeError("Selected shape contains an invalid solid.")
    if len(solids) > 1:
        raise InvalidShapeError(
            "Selected shape contains multiple valid solids; V4.00 requires "
            "exactly one."
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
        messages=messages,
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


def _topology_items(value: object, name: str) -> tuple[object, ...]:
    """Read one topology collection in the stable order supplied by FreeCAD."""
    try:
        return tuple(getattr(value, name, ()))
    except Exception as error:
        raise InvalidShapeError(
            f"Selected shape cannot expose its {name.lower()}."
        ) from error

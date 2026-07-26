# -*- coding: utf-8 -*-
"""Composition of immutable manufacturing profiles from central settings."""

from __future__ import annotations

import math

from ..Exceptions import ManufacturingProfileError
from ..Models import (
    BuildEnvelope,
    ManufacturingConstraint,
    ManufacturingProfile,
)
from ..Settings import Settings

__all__ = ["ProfileComposer"]


class ProfileComposer:
    """Create reproducible profiles without reading GUI or document state."""

    def __init__(self, settings: object = Settings) -> None:
        """Store one read-only centralized settings container."""
        self._settings = settings

    def compose(self) -> ManufacturingProfile:
        """Return the deterministic profile represented by current settings.

        Effective X and Y part limits are owned by ``Settings.Split``;
        physical machine extents are owned by ``Settings.Printer``.  The
        overlapping legacy ``Printer.MAX_PART_SIZE`` value is intentionally
        not read, so it cannot become a competing source of truth.  Z is
        included only when both its physical and effective settings exist.

        Raises:
            ManufacturingProfileError: If configured values are incomplete,
                non-finite, non-positive where an extent is required, or
                internally impossible.
        """
        try:
            printer = self._settings.Printer
            split = self._settings.Split
            manufacturing = self._settings.Manufacturing
            profile_id = str(manufacturing.PROFILE_ID)
            profile_version = str(manufacturing.PROFILE_VERSION)
            settings_version = str(manufacturing.SETTINGS_VERSION)
            process_type = str(manufacturing.PROCESS_TYPE)
            display_name = str(printer.NAME)
        except AttributeError as error:
            raise ManufacturingProfileError(
                "Centralized manufacturing settings are incomplete."
            ) from error
        if not all(
            value
            for value in (
                profile_id,
                profile_version,
                settings_version,
                process_type,
                display_name,
            )
        ):
            raise ManufacturingProfileError(
                "Manufacturing profile identity settings cannot be empty."
            )

        envelope = self._build_envelope(printer, split, manufacturing)
        constraints = tuple(
            item
            for item in (
                self._constraint(
                    profile_id,
                    "minimum-thickness",
                    "minimum_thickness",
                    manufacturing.MINIMUM_THICKNESS_MM,
                    manufacturing.MINIMUM_THICKNESS_LEVEL,
                    manufacturing.ENABLE_MINIMUM_THICKNESS,
                    "Configured minimum local material thickness.",
                ),
                self._constraint(
                    profile_id,
                    "minimum-ligament",
                    "minimum_ligament_width",
                    manufacturing.MINIMUM_LIGAMENT_WIDTH_MM,
                    manufacturing.MINIMUM_LIGAMENT_LEVEL,
                    manufacturing.ENABLE_MINIMUM_LIGAMENT,
                    "Configured minimum continuous-material ligament width.",
                ),
                self._constraint(
                    profile_id,
                    "minimum-hole-to-hole-clearance",
                    "minimum_hole_to_hole_clearance",
                    manufacturing.MINIMUM_HOLE_TO_HOLE_CLEARANCE_MM,
                    manufacturing.MINIMUM_HOLE_TO_HOLE_CLEARANCE_LEVEL,
                    manufacturing.ENABLE_MINIMUM_HOLE_TO_HOLE_CLEARANCE,
                    "Configured minimum hole-to-hole boundary clearance.",
                ),
                self._constraint(
                    profile_id,
                    "minimum-hole-to-exterior-clearance",
                    "minimum_hole_to_exterior_clearance",
                    manufacturing.MINIMUM_HOLE_TO_EXTERIOR_CLEARANCE_MM,
                    manufacturing.MINIMUM_HOLE_TO_EXTERIOR_CLEARANCE_LEVEL,
                    manufacturing.ENABLE_MINIMUM_HOLE_TO_EXTERIOR_CLEARANCE,
                    "Configured minimum hole-to-exterior boundary clearance.",
                ),
            )
            if item is not None
        )
        return ManufacturingProfile(
            profile_id=profile_id,
            profile_version=profile_version,
            settings_version=settings_version,
            display_name=display_name,
            process_type=process_type,
            build_envelope=envelope,
            constraints=constraints,
            notes=(
                "Effective X/Y limits are owned by Settings.Split.",
                "Printer.MAX_PART_SIZE is a legacy value and is not composed.",
            ),
        )

    @staticmethod
    def _build_envelope(
        printer: object,
        split: object,
        manufacturing: object,
    ) -> BuildEnvelope:
        """Compose physical, margin, and effective axis settings."""
        physical_x = ProfileComposer._positive(
            printer.BED_SIZE_X,
            "Printer.BED_SIZE_X",
        )
        physical_y = ProfileComposer._positive(
            printer.BED_SIZE_Y,
            "Printer.BED_SIZE_Y",
        )
        effective_x = ProfileComposer._positive(
            split.MAX_PART_WIDTH,
            "Split.MAX_PART_WIDTH",
        )
        effective_y = ProfileComposer._positive(
            split.MAX_PART_HEIGHT,
            "Split.MAX_PART_HEIGHT",
        )
        if effective_x > physical_x or effective_y > physical_y:
            raise ManufacturingProfileError(
                "Effective X/Y part limits cannot exceed physical extents."
            )

        physical_z = ProfileComposer._optional_positive(
            getattr(printer, "BED_SIZE_Z", None),
            "Printer.BED_SIZE_Z",
        )
        effective_z = ProfileComposer._optional_positive(
            getattr(split, "MAX_PART_DEPTH", None),
            "Split.MAX_PART_DEPTH",
        )
        if (physical_z is None) != (effective_z is None):
            raise ManufacturingProfileError(
                "Physical and effective Z settings must be configured together."
            )
        if (
            physical_z is not None
            and effective_z is not None
            and effective_z > physical_z
        ):
            raise ManufacturingProfileError(
                "Effective Z part limit cannot exceed the physical extent."
            )
        return BuildEnvelope(
            constraint_id=(
                f"{manufacturing.PROFILE_ID}:constraint:build-envelope"
            ),
            physical_x_mm=physical_x,
            physical_y_mm=physical_y,
            physical_z_mm=physical_z,
            safety_margin_x_mm=physical_x - effective_x,
            safety_margin_y_mm=physical_y - effective_y,
            safety_margin_z_mm=(
                None
                if physical_z is None or effective_z is None
                else physical_z - effective_z
            ),
            effective_x_mm=effective_x,
            effective_y_mm=effective_y,
            effective_z_mm=effective_z,
            is_enabled=bool(manufacturing.ENABLE_BUILD_ENVELOPE),
        )

    @staticmethod
    def _constraint(
        profile_id: str,
        suffix: str,
        constraint_type: str,
        configured_value: object,
        configured_level: object,
        is_enabled: object,
        description: str,
    ) -> ManufacturingConstraint | None:
        """Compose one optional scalar constraint in declared source order."""
        if configured_value is None:
            if bool(is_enabled):
                raise ManufacturingProfileError(
                    f"Enabled constraint '{constraint_type}' has no value."
                )
            return None
        limit = ProfileComposer._non_negative(
            configured_value,
            constraint_type,
        )
        level = str(configured_level)
        if level not in {"hard", "warning"}:
            raise ManufacturingProfileError(
                f"Constraint '{constraint_type}' has invalid level '{level}'."
            )
        return ManufacturingConstraint(
            constraint_id=f"{profile_id}:constraint:{suffix}",
            constraint_type=constraint_type,
            level=level,
            comparison="greater_than_or_equal",
            limit_value=limit,
            unit="mm",
            severity="error" if level == "hard" else "warning",
            description=description,
            is_enabled=bool(is_enabled),
        )

    @staticmethod
    def _non_negative(value: object, label: str) -> float:
        """Return a finite non-negative configured scalar."""
        try:
            result = float(value)
        except (TypeError, ValueError) as error:
            raise ManufacturingProfileError(
                f"{label} must be a finite non-negative number."
            ) from error
        if not math.isfinite(result) or result < 0.0:
            raise ManufacturingProfileError(
                f"{label} must be a finite non-negative number."
            )
        return result

    @staticmethod
    def _positive(value: object, label: str) -> float:
        """Return a finite strictly positive configured extent."""
        result = ProfileComposer._non_negative(value, label)
        if result == 0.0:
            raise ManufacturingProfileError(
                f"{label} must be a finite positive number."
            )
        return result

    @staticmethod
    def _optional_positive(value: object, label: str) -> float | None:
        """Return an optional finite strictly positive configured extent."""
        if value is None:
            return None
        return ProfileComposer._positive(value, label)

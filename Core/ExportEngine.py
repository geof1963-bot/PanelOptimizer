# -*- coding: utf-8 -*-
"""Transactional STL export for validated printable-part records."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from .Exceptions import (
    ExportError,
    PrintableLimitViolation,
    STLExportError,
)
from .Models import ExportArtifact, ExportReport, PrintablePart

__all__ = ["ExportEngine"]


class ExportEngine:
    """Export exactly four caller-resolved split shapes as deterministic STLs."""

    PART_NAMES = ("Part_1", "Part_2", "Part_3", "Part_4")

    def __init__(
        self,
        shape_resolver: Callable[[str], object] | None = None,
    ) -> None:
        """Store an optional opaque-reference-to-shape resolver."""
        self._shape_resolver = shape_resolver

    def export_parts(
        self,
        parts: tuple[PrintablePart, ...],
        output_directory: str,
        file_format: str = "STL",
        shape_resolver: Callable[[str], object] | None = None,
    ) -> ExportReport:
        """Export four printable parts without leaving partial output files.

        All shapes are first exported to deterministic partial filenames and
        checked for non-empty content. Final files are replaced only after all
        four temporary exports succeed. Existing final files are backed up and
        restored if finalization fails.

        Raises:
            PrintableLimitViolation: If any part failed configured X/Y limits.
            ExportError: If input, directory, or resolver configuration is
                invalid.
            STLExportError: If shape serialization or transactional commit
                fails.
        """
        ordered_parts = tuple(parts)
        if len(ordered_parts) != 4:
            raise ExportError(
                f"V4.00 STL export requires exactly four parts; received "
                f"{len(ordered_parts)}."
            )
        if str(file_format).upper() != "STL":
            raise ExportError("V4.00 supports STL export only.")
        split_result_ids = {item.split_result_id for item in ordered_parts}
        if len(split_result_ids) != 1:
            raise ExportError("All exported parts must belong to one split result.")
        for expected_name, part in zip(self.PART_NAMES, ordered_parts):
            if part.name != expected_name:
                raise ExportError(
                    "Printable parts are not in deterministic quadrant order."
                )
        invalid_parts = tuple(item for item in ordered_parts if not item.is_printable)
        if invalid_parts:
            details = "; ".join(
                f"{item.name}: {', '.join(item.validation_messages)}"
                for item in invalid_parts
            )
            raise PrintableLimitViolation(
                "STL export blocked because split parts exceed configured "
                f"effective limits. {details}"
            )

        resolver = shape_resolver or self._shape_resolver
        if resolver is None or not callable(resolver):
            raise ExportError("STL export requires a callable shape resolver.")
        destination = self._validated_directory(output_directory)
        final_paths = tuple(
            destination / f"{name}.stl" for name in self.PART_NAMES
        )
        temporary_paths = tuple(
            destination / f".{name}.paneloptimizer.partial.stl"
            for name in self.PART_NAMES
        )
        backup_paths = tuple(
            destination / f".{name}.paneloptimizer.backup.stl"
            for name in self.PART_NAMES
        )
        if any(path.exists() for path in backup_paths):
            raise STLExportError(
                "Export directory contains a previous PanelOptimizer backup; "
                "remove or recover it before exporting."
            )

        try:
            for temporary in temporary_paths:
                if temporary.exists():
                    temporary.unlink()
            for part, temporary in zip(ordered_parts, temporary_paths):
                shape = resolver(part.geometry_reference)
                self._validate_shape(shape, part.name)
                shape.exportStl(str(temporary))
                if not temporary.is_file() or temporary.stat().st_size <= 0:
                    raise STLExportError(
                        f"STL serialization produced no data for {part.name}."
                    )
        except (ExportError, PrintableLimitViolation):
            self._remove_files(temporary_paths)
            raise
        except Exception as error:
            self._remove_files(temporary_paths)
            raise STLExportError("Unable to serialize all four STL files.") from error

        backed_up: list[tuple[Path, Path]] = []
        committed: list[Path] = []
        try:
            for final, backup in zip(final_paths, backup_paths):
                if final.exists():
                    os.replace(final, backup)
                    backed_up.append((final, backup))
            for temporary, final in zip(temporary_paths, final_paths):
                os.replace(temporary, final)
                committed.append(final)
        except Exception as error:
            self._remove_files(tuple(committed) + temporary_paths)
            for final, backup in reversed(backed_up):
                if backup.exists():
                    os.replace(backup, final)
            raise STLExportError(
                "Unable to finalize all four STL files; previous files were "
                "restored where present."
            ) from error

        self._remove_files(backup_paths)
        artifacts = tuple(
            ExportArtifact(
                part_id=part.part_id,
                file_path=str(path),
                file_format="STL",
                byte_count=path.stat().st_size,
            )
            for part, path in zip(ordered_parts, final_paths)
        )
        return ExportReport(
            split_result_id=ordered_parts[0].split_result_id,
            output_directory=str(destination),
            artifacts=artifacts,
        )

    @staticmethod
    def _validated_directory(output_directory: str) -> Path:
        """Return one existing caller-selected output directory."""
        if not str(output_directory):
            raise ExportError("An output directory must be selected.")
        try:
            destination = Path(output_directory).expanduser().resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise ExportError("Selected output directory does not exist.") from error
        if not destination.is_dir():
            raise ExportError("Selected output path is not a directory.")
        return destination

    @staticmethod
    def _validate_shape(shape: object, name: str) -> None:
        """Reject missing, invalid, empty, or non-solid export geometry."""
        try:
            valid = (
                shape is not None
                and not shape.isNull()
                and shape.isValid()
                and len(shape.Solids) == 1
                and float(shape.Volume) > 0.0
            )
        except Exception as error:
            raise STLExportError(
                f"Unable to inspect export geometry for {name}."
            ) from error
        if not valid:
            raise STLExportError(f"Export geometry for {name} is invalid.")

    @staticmethod
    def _remove_files(paths: tuple[Path, ...]) -> None:
        """Remove only known transaction files when they exist."""
        for path in paths:
            try:
                if path.exists():
                    path.unlink()
            except OSError:
                pass

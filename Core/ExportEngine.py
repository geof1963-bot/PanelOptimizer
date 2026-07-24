# -*- coding: utf-8 -*-
"""Public interface for the PanelOptimizer export engine."""

from __future__ import annotations

from .Models import ExportReport, PrintablePart

__all__ = ["ExportEngine"]


class ExportEngine:
    """Define the export of printable-part records to external files."""

    def export_parts(
        self,
        parts: tuple[PrintablePart, ...],
        output_directory: str,
        file_format: str,
    ) -> ExportReport:
        """Export printable parts and return a new export report.

        Args:
            parts: The immutable printable-part records to export.
            output_directory: The caller-selected destination directory.
            file_format: The requested export format, such as ``"STL"``.

        Returns:
            A newly created ExportReport for the requested export operation.

        Raises:
            NotImplementedError: Always, until the export engine exists.
            ExportError: In a future implementation, if an export operation
                cannot complete.
        """
        raise NotImplementedError("ExportEngine.export_parts")

# -*- coding: utf-8 -*-
"""Export data contracts for future PanelOptimizer engines."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExportArtifact:
    """A single file emitted for one printable part."""

    part_id: str
    file_path: str
    file_format: str
    byte_count: int


@dataclass(frozen=True, slots=True)
class ExportReport:
    """The immutable outcome of exporting the parts from one split plan."""

    split_plan_id: str
    output_directory: str
    artifacts: tuple[ExportArtifact, ...]
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

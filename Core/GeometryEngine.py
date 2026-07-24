# -*- coding: utf-8 -*-
"""Public interface for the PanelOptimizer geometry engine."""

from __future__ import annotations

from .Models import GeometrySnapshot

__all__ = ["GeometryEngine"]


class GeometryEngine:
    """Define the conversion from an opaque source shape to model data."""

    def create_snapshot(
        self,
        shape: object,
        source_id: str,
        source_label: str,
    ) -> GeometrySnapshot:
        """Create a new immutable snapshot for one source shape.

        Args:
            shape: The opaque source shape supplied by the caller.
            source_id: A stable identifier for the source shape.
            source_label: A human-readable label for the source shape.

        Returns:
            A newly created GeometrySnapshot describing the source shape.

        Raises:
            NotImplementedError: Always, until the geometry engine exists.
            GeometryError: In a future implementation, if the source shape
                cannot be validated or described.
        """
        raise NotImplementedError("GeometryEngine.create_snapshot")

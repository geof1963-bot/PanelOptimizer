# -*- coding: utf-8 -*-
"""Measurement and validation engine for PanelOptimizer source shapes."""

from __future__ import annotations

import logging
import math

from .Exceptions import (
    EmptyShapeError,
    GeometryError,
    GeometryMeasurementError,
    InvalidShapeError,
    NullShapeError,
)
from .Models import BoundingBox, GeometrySnapshot, Point3D

__all__ = ["GeometryEngine"]


class GeometryEngine:
    """Measure one FreeCAD shape without modifying it or interpreting it."""

    def create_snapshot(
        self,
        shape: object,
        source_id: str,
        source_label: str,
    ) -> GeometrySnapshot:
        """Measure a FreeCAD shape and return a new immutable snapshot.

        Args:
            shape: The caller-owned FreeCAD shape to measure.
            source_id: A stable identifier for the source shape.
            source_label: A human-readable label for the source shape.

        Returns:
            A newly created GeometrySnapshot containing topology, bounds,
            centre of gravity, area, volume, and shape-state information.

        Raises:
            NullShapeError: If the shape is missing or reports itself as null.
            InvalidShapeError: If the shape is invalid or has unsupported
                topology for this engine.
            EmptyShapeError: If the shape contains no measurable topology.
            GeometryMeasurementError: If a required property cannot be read
                or contains a non-finite measurement.
        """
        logger = logging.getLogger(self.__class__.__name__)

        try:
            self._validate_shape(shape)

            face_count = len(shape.Faces)
            edge_count = len(shape.Edges)
            vertex_count = len(shape.Vertexes)

            if face_count == 0 and edge_count == 0 and vertex_count == 0:
                raise EmptyShapeError("Shape contains no measurable topology.")

            bounding_box = shape.BoundBox
            center = shape.CenterOfGravity
            volume_mm3 = float(shape.Volume)
            area_mm2 = float(shape.Area)

            dimensions = (
                float(bounding_box.XLength),
                float(bounding_box.YLength),
                float(bounding_box.ZLength),
            )
            bounds = (
                float(bounding_box.XMin),
                float(bounding_box.YMin),
                float(bounding_box.ZMin),
                float(bounding_box.XMax),
                float(bounding_box.YMax),
                float(bounding_box.ZMax),
            )
            center_coordinates = (
                float(center.x),
                float(center.y),
                float(center.z),
            )

            self._validate_measurements(
                dimensions + bounds + center_coordinates + (volume_mm3, area_mm2)
            )

            return GeometrySnapshot(
                source_id=source_id,
                source_label=source_label,
                bounding_box=BoundingBox(
                    minimum=Point3D(*bounds[:3]),
                    maximum=Point3D(*bounds[3:]),
                ),
                center=Point3D(*center_coordinates),
                width_mm=dimensions[0],
                height_mm=dimensions[1],
                thickness_mm=dimensions[2],
                area_mm2=area_mm2,
                volume_mm3=volume_mm3,
                solid_count=len(shape.Solids),
                face_count=face_count,
                edge_count=edge_count,
                vertex_count=vertex_count,
                shape_type=self._shape_type(shape),
                is_closed=self._closed_state(shape),
                is_valid=True,
            )
        except GeometryError:
            logger.error("Unable to measure geometry '%s'.", source_id)
            raise
        except Exception as error:
            logger.error("Unable to measure geometry '%s'.", source_id)
            raise GeometryMeasurementError(
                "Shape cannot provide the measurements required for a "
                "GeometrySnapshot."
            ) from error

    @staticmethod
    def _validate_shape(shape: object) -> None:
        """Validate null state, validity, and supported topological type."""
        if shape is None:
            raise NullShapeError("Shape is missing.")

        if bool(shape.isNull()):
            raise NullShapeError("Shape is null.")

        if not bool(shape.isValid()):
            raise InvalidShapeError("Shape is invalid.")

        shape_type = GeometryEngine._shape_type(shape)
        supported_types = {"Solid", "CompSolid", "Shell", "Compound"}

        if shape_type not in supported_types:
            raise InvalidShapeError(
                f"Unsupported shape type for measurement: {shape_type}."
            )

    @staticmethod
    def _shape_type(shape: object) -> str:
        """Return the FreeCAD topological type required by the snapshot."""
        shape_type = str(shape.ShapeType)

        if not shape_type:
            raise GeometryMeasurementError("Shape type is unavailable.")

        return shape_type

    @staticmethod
    def _closed_state(shape: object) -> bool | None:
        """Return closed state when FreeCAD exposes it for the shape."""
        closed_state = getattr(shape, "isClosed", None)

        if closed_state is None:
            return None

        if callable(closed_state):
            return bool(closed_state())

        return bool(closed_state)

    @staticmethod
    def _validate_measurements(measurements: tuple[float, ...]) -> None:
        """Reject non-finite values that cannot form a reliable snapshot."""
        if not all(math.isfinite(value) for value in measurements):
            raise GeometryMeasurementError(
                "Shape contains a non-finite geometric measurement."
            )

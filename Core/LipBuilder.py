# -*- coding: utf-8 -*-
"""Focused V4.50 top-surface mastic lips for accepted final seams."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .Exceptions import LipBuildError
from .MacroSplitCore import MacroGrooveParameters, MacroSplitResult
from .Settings import Settings
from .ProductionDiagnostics import log_event, operation
from .SplittingUtilities import (
    PARTITION_CLASSIFICATION_TOLERANCE_MM,
    volume_tolerance_mm3,
)

__all__ = ["LipApplication", "LipBuilder", "LipParameters", "LipPartReport"]

_EPSILON_MM = 1.0e-7
_FUSION_OVERLAP_MM = 0.01
_PART_NAMES = ("Part_1", "Part_2", "Part_3", "Part_4")
_QUADRANT_KEYS = ((False, False), (True, False), (False, True), (True, True))


@dataclass(frozen=True, slots=True)
class LipParameters:
    """Small rectangular rib dimensions and the referenced groove opening."""

    height_mm: float = Settings.Lips.LIP_HEIGHT_MM
    width_mm: float = Settings.Lips.LIP_WIDTH_MM
    groove_top_width_mm: float = MacroGrooveParameters().top_width_mm


@dataclass(frozen=True, slots=True)
class LipPartReport:
    """Measured per-part outcome of local clipping and fusion."""

    name: str
    dimensions_before_mm: tuple[float, float, float]
    dimensions_after_mm: tuple[float, float, float]
    volume_added_mm3: float
    total_length_mm: float
    segment_count: int
    trimmed_segment_count: int
    rejected_segment_count: int
    within_x_limit: bool
    within_y_limit: bool

    @property
    def is_printable(self) -> bool:
        return self.within_x_limit and self.within_y_limit


@dataclass(frozen=True, slots=True)
class LipApplication:
    """Transient four-part result, preview compound, and validation evidence."""

    macro_result: MacroSplitResult
    preview_shape: object
    reports: tuple[LipPartReport, ...]
    dowel_holes_preserved: bool


class LipBuilder:
    """Build two seam-offset ribs and retain only each part's material side."""

    def __init__(
        self,
        parameters: LipParameters = LipParameters(),
        split_settings: object = Settings.Split,
    ) -> None:
        self._parameters = self._validate_parameters(parameters)
        self._split_settings = split_settings

    def apply(
        self,
        macro_result: MacroSplitResult,
        *,
        dowel_cutters: tuple[object, ...] = (),
    ) -> LipApplication:
        """Add top-only lips to four drilled parts without mutating the input."""
        import Part
        from FreeCAD import Vector

        if not isinstance(macro_result, MacroSplitResult):
            raise LipBuildError("Lip construction requires a MacroSplitResult.")
        if macro_result.seam_plan is None:
            raise LipBuildError("Lip construction requires accepted final seam paths.")
        solids = self._ordered_solids(macro_result)
        try:
            zmax = max(float(solid.BoundBox.ZMax) for solid in solids)
            candidates = self._segment_candidates(
                macro_result.seam_plan, zmax, Part, Vector
            )
            exclusion = self._central_exclusion(
                macro_result.seam_plan, zmax, Part, Vector
            )
        except LipBuildError:
            raise
        except Exception as error:
            raise LipBuildError("Unable to construct seam-offset lip solids.") from error

        # The exclusion box is shared by all four part masks. Cut it from
        # each batched rib once, then reuse those exact transient shapes for
        # the four material-side commons below.
        prepared_candidates = []
        for candidate, ideal_volume in candidates:
            try:
                with operation(
                    "[7] Lips", "shared", "prepare clipped candidate", candidate
                ):
                    prepared = candidate.cut(exclusion)
            except Exception as error:
                raise LipBuildError("Shared lip candidate preparation failed.") from error
            prepared_candidates.append((prepared, ideal_volume))
        prepared_candidates = tuple(prepared_candidates)

        fused_parts = []
        preview_pieces = []
        reports = []
        cross_section = self._parameters.width_mm * self._parameters.height_mm
        for name, solid in zip(_PART_NAMES, solids):
            before_box = solid.BoundBox
            before_volume = float(solid.Volume)
            mask = self._top_material_mask(solid, zmax, Part, Vector)
            pieces = []
            trimmed = rejected = 0
            for candidate, ideal_volume in prepared_candidates:
                if not self._bbox_overlaps_xy(candidate.BoundBox, before_box):
                    rejected += 1
                    continue
                try:
                    with operation(
                        "[7] Lips", name, "clip candidate", candidate
                    ):
                        clipped = candidate.common(mask)
                    actual_volume = float(clipped.Volume)
                except Exception as error:
                    raise LipBuildError(f"Local lip clipping failed for {name}.") from error
                tolerance = max(1.0e-8, ideal_volume * 1.0e-7)
                if actual_volume <= tolerance:
                    rejected += 1
                    continue
                if actual_volume < ideal_volume - tolerance:
                    trimmed += 1
                pieces.append(clipped)
            if not pieces:
                raise LipBuildError(f"No lip material survived clipping for {name}.")
            try:
                with operation("[7] Lips", name, "fuse lip pieces", solid):
                    lip_shape = (
                        pieces[0].multiFuse(pieces[1:])
                        if len(pieces) > 1 else pieces[0]
                    )
                    fused = solid.fuse(lip_shape)
                try:
                    fused = fused.removeSplitter()
                except Exception as error:
                    log_event(
                        "[7] Lips", name,
                        "WARNING removeSplitter failed: "
                        f"{type(error).__name__}: {error}",
                    )
            except Exception as error:
                raise LipBuildError(f"Lip fusion failed for {name}.") from error
            if len(tuple(fused.Solids)) != 1 or float(fused.Volume) <= before_volume:
                raise LipBuildError(f"Lip fusion did not preserve one positive {name} solid.")
            after_box = fused.BoundBox
            added = float(fused.Volume) - before_volume
            within_x = float(after_box.XLength) <= (
                float(self._split_settings.MAX_PART_WIDTH)
                + PARTITION_CLASSIFICATION_TOLERANCE_MM
            )
            within_y = float(after_box.YLength) <= (
                float(self._split_settings.MAX_PART_HEIGHT)
                + PARTITION_CLASSIFICATION_TOLERANCE_MM
            )
            if not (within_x and within_y):
                raise LipBuildError(
                    f"{name} exceeds configured printable bounds after local "
                    f"lip clipping: {self._dimensions(after_box)} mm."
                )
            fused_parts.append(fused)
            preview_pieces.append(lip_shape)
            reports.append(
                LipPartReport(
                    name=name,
                    dimensions_before_mm=self._dimensions(before_box),
                    dimensions_after_mm=self._dimensions(after_box),
                    volume_added_mm3=added,
                    total_length_mm=added / cross_section,
                    segment_count=len(pieces),
                    trimmed_segment_count=trimmed,
                    rejected_segment_count=rejected,
                    within_x_limit=within_x,
                    within_y_limit=within_y,
                )
            )

        result_shape = Part.makeCompound(tuple(fused_parts))
        result_volume = sum(float(solid.Volume) for solid in fused_parts)
        updated = replace(
            macro_result,
            shape=result_shape,
            result_volume_mm3=result_volume,
            solid_count=len(tuple(result_shape.Solids)),
        )
        if updated.solid_count != 4:
            raise LipBuildError("Lip operations did not preserve four separate parts.")
        dowels_preserved = self._dowel_holes_are_open(result_shape, dowel_cutters)
        if not dowels_preserved:
            raise LipBuildError("Lip operations damaged or closed a dowel cavity.")
        return LipApplication(
            macro_result=updated,
            preview_shape=Part.makeCompound(tuple(preview_pieces)),
            reports=tuple(reports),
            dowel_holes_preserved=True,
        )

    def _segment_candidates(self, seam_plan, zmax, Part, Vector):
        """Return deterministic rectangular ribs on both sides of every segment."""
        offset = (
            self._parameters.groove_top_width_mm / 2.0
            + self._parameters.width_mm / 2.0
        )
        pieces = []
        for path in (seam_plan.vertical, seam_plan.horizontal):
            for first, second in zip(path.points, path.points[1:]):
                dx = float(second.x_mm - first.x_mm)
                dy = float(second.y_mm - first.y_mm)
                length = math.hypot(dx, dy)
                if length <= _EPSILON_MM:
                    raise LipBuildError("Seam path contains a zero-length segment.")
                tx, ty = dx / length, dy / length
                nx, ny = -ty, tx
                half = self._parameters.width_mm / 2.0
                for side in (-1.0, 1.0):
                    cx1 = float(first.x_mm) + nx * offset * side
                    cy1 = float(first.y_mm) + ny * offset * side
                    cx2 = float(second.x_mm) + nx * offset * side
                    cy2 = float(second.y_mm) + ny * offset * side
                    base_z = zmax - _FUSION_OVERLAP_MM
                    corners = (
                        Vector(cx1 - nx * half, cy1 - ny * half, base_z),
                        Vector(cx1 + nx * half, cy1 + ny * half, base_z),
                        Vector(cx2 + nx * half, cy2 + ny * half, base_z),
                        Vector(cx2 - nx * half, cy2 - ny * half, base_z),
                    )
                    wire = Part.makePolygon((*corners, corners[0]))
                    rib = Part.Face(Part.Wire(wire.Edges)).extrude(
                        Vector(
                            0.0,
                            0.0,
                            self._parameters.height_mm + _FUSION_OVERLAP_MM,
                        )
                    )
                    pieces.append((rib, float(rib.Volume)))
        if not pieces:
            raise LipBuildError("Accepted seam plan contains no lip segments.")
        # Union small deterministic batches before per-part mask clipping.
        # This preserves the exact rib union while avoiding one expensive
        # common/cut boolean for every sampled curve segment and every part.
        batched = []
        batch_size = 64
        for start in range(0, len(pieces), batch_size):
            shapes = tuple(item[0] for item in pieces[start:start + batch_size])
            try:
                shape = (
                    shapes[0].multiFuse(shapes[1:])
                    if len(shapes) > 1 else shapes[0]
                )
                try:
                    shape = shape.removeSplitter()
                except Exception:
                    pass
            except Exception as error:
                raise LipBuildError("Unable to batch curved lip segments.") from error
            batched.append((shape, float(shape.Volume)))
        return tuple(batched)

    @staticmethod
    def _bbox_overlaps_xy(first, second):
        """Cheap material-footprint gate before an OCC clip operation."""
        return not (
            float(first.XMax) <= float(second.XMin) + _EPSILON_MM
            or float(first.XMin) >= float(second.XMax) - _EPSILON_MM
            or float(first.YMax) <= float(second.YMin) + _EPSILON_MM
            or float(first.YMin) >= float(second.YMax) - _EPSILON_MM
        )

    def _top_material_mask(self, solid, zmax, Part, Vector):
        """Extrude only coplanar ZMax faces, preserving openings and panel edges."""
        top_faces = []
        for face in solid.Faces:
            vertices = tuple(face.Vertexes)
            if vertices and all(
                abs(float(vertex.Point.z) - zmax) <= _EPSILON_MM
                for vertex in vertices
            ):
                top_face = face.copy()
                top_face.translate(Vector(0.0, 0.0, -_FUSION_OVERLAP_MM))
                top_faces.append(
                    top_face.extrude(
                        Vector(
                            0.0,
                            0.0,
                            self._parameters.height_mm + _FUSION_OVERLAP_MM,
                        )
                    )
                )
        if not top_faces:
            raise LipBuildError("A split part has no measurable top material face.")
        return (
            top_faces[0].multiFuse(top_faces[1:])
            if len(top_faces) > 1
            else top_faces[0]
        )

    def _central_exclusion(self, seam_plan, zmax, Part, Vector):
        point = self._intersection_point(seam_plan)
        # Keep orthogonal rib ends separated instead of letting them meet at
        # one exclusion-box edge, which creates a non-manifold tessellation.
        half = (
            self._parameters.groove_top_width_mm / 2.0
            + self._parameters.width_mm * 1.25
        )
        return Part.makeBox(
            half * 2.0,
            half * 2.0,
            self._parameters.height_mm + _FUSION_OVERLAP_MM + _EPSILON_MM,
            Vector(
                point[0] - half,
                point[1] - half,
                zmax - _FUSION_OVERLAP_MM,
            ),
        )

    @staticmethod
    def _intersection_point(seam_plan):
        for a, b in zip(seam_plan.vertical.points, seam_plan.vertical.points[1:]):
            for c, d in zip(seam_plan.horizontal.points, seam_plan.horizontal.points[1:]):
                denominator = ((a.x_mm - b.x_mm) * (c.y_mm - d.y_mm)
                               - (a.y_mm - b.y_mm) * (c.x_mm - d.x_mm))
                if abs(denominator) <= _EPSILON_MM:
                    continue
                determinant_ab = a.x_mm * b.y_mm - a.y_mm * b.x_mm
                determinant_cd = c.x_mm * d.y_mm - c.y_mm * d.x_mm
                x_value = (determinant_ab * (c.x_mm - d.x_mm)
                           - (a.x_mm - b.x_mm) * determinant_cd) / denominator
                y_value = (determinant_ab * (c.y_mm - d.y_mm)
                           - (a.y_mm - b.y_mm) * determinant_cd) / denominator
                if (
                    min(a.x_mm, b.x_mm) - _EPSILON_MM <= x_value <= max(a.x_mm, b.x_mm) + _EPSILON_MM
                    and min(a.y_mm, b.y_mm) - _EPSILON_MM <= y_value <= max(a.y_mm, b.y_mm) + _EPSILON_MM
                    and min(c.x_mm, d.x_mm) - _EPSILON_MM <= x_value <= max(c.x_mm, d.x_mm) + _EPSILON_MM
                    and min(c.y_mm, d.y_mm) - _EPSILON_MM <= y_value <= max(c.y_mm, d.y_mm) + _EPSILON_MM
                ):
                    return float(x_value), float(y_value)
        raise LipBuildError("Unable to locate the accepted seam intersection.")

    @staticmethod
    def _ordered_solids(macro_result):
        try:
            solids = tuple(macro_result.shape.Solids)
        except Exception as error:
            raise LipBuildError("Unable to read the four drilled parts.") from error
        quadrants = {}
        for solid in solids:
            center = solid.CenterOfMass
            key = (
                float(center.x) >= macro_result.cut_x_mm,
                float(center.y) >= macro_result.cut_y_mm,
            )
            quadrants.setdefault(key, []).append(solid)
        if tuple(len(quadrants.get(key, ())) for key in _QUADRANT_KEYS) != (1, 1, 1, 1):
            raise LipBuildError("Drilled parts do not map one-to-one to four quadrants.")
        return tuple(quadrants[key][0] for key in _QUADRANT_KEYS)

    @staticmethod
    def _dowel_holes_are_open(result_shape, cutters):
        cutters = tuple(cutters)
        if not cutters:
            return True
        try:
            import Part
            tool = Part.makeCompound(cutters)
            overlap = float(result_shape.common(tool).Volume)
            tolerance = volume_tolerance_mm3(float(tool.Volume))
        except Exception as error:
            raise LipBuildError("Unable to verify dowel cavities.") from error
        return overlap <= tolerance

    @staticmethod
    def _dimensions(box):
        return float(box.XLength), float(box.YLength), float(box.ZLength)

    @staticmethod
    def _validate_parameters(parameters):
        if not isinstance(parameters, LipParameters):
            raise LipBuildError("Lip parameters must be LipParameters.")
        values = (parameters.height_mm, parameters.width_mm, parameters.groove_top_width_mm)
        try:
            valid = all(math.isfinite(float(value)) and float(value) > 0.0 for value in values)
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise LipBuildError("Lip and groove dimensions must be finite and positive.")
        return parameters

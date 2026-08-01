# -*- coding: utf-8 -*-
"""Pragmatic V4.10 groove cutting faithfully extracted from proven macros."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .ConnectivityRepair import diagnose_region_connectivity
from .ProductionDiagnostics import log_event, operation
from .Exceptions import (
    RegionConnectivityError,
    SplitOperationError,
    SplitSourceError,
)

__all__ = [
    "MacroGrooveParameters",
    "MacroSplitCore",
    "MacroSplitResult",
]


@dataclass(frozen=True, slots=True)
class MacroGrooveParameters:
    """Exact scalar groove parameters shared by both reference macros.

    All values are model-coordinate millimetres. The visible V4.10 profile is
    unchanged. V4.21 also uses ``bottom_width_mm`` as the full-depth slot width,
    starting at the existing profile's bottom-left coordinate. ``overlap_mm``
    extends cutters beyond transverse and bottom panel boundaries.
    """

    groove_depth_mm: float = 1.2
    top_width_mm: float = 2.2
    bottom_width_mm: float = 0.5
    overlap_mm: float = 20.0


@dataclass(frozen=True, slots=True)
class MacroSplitResult:
    """Runtime result and scalar metadata for one macro-equivalent cut.

    ``shape`` is transient FreeCAD geometry and deliberately does not enter
    ``Core.Models`` or an immutable analysis report.
    """

    shape: object
    real_center_x_mm: float
    real_center_y_mm: float
    cut_x_mm: float
    cut_y_mm: float
    vertical_offset_mm: float
    horizontal_offset_mm: float
    source_volume_mm3: float
    surface_groove_result_volume_mm3: float
    surface_groove_removed_volume_mm3: float
    additional_separation_removed_volume_mm3: float
    result_volume_mm3: float
    solid_count: int
    separation_width_mm: float
    cleanup_applied: bool
    seam_plan: object | None
    partition_method: str = "global_double_cut"
    region_areas_mm2: tuple[float, ...] = ()
    region_raw_solid_counts: tuple[int, ...] = ()
    region_solid_counts: tuple[int, ...] = ()
    region_discarded_sliver_counts: tuple[int, ...] = ()
    connectivity_repair_attempts: int = 0
    connectivity_diagnostics: tuple[object, ...] = ()
    connectivity_repair_history: tuple[str, ...] = ()
    region_component_diagnostics: tuple[object, ...] = ()


class MacroSplitCore:
    """Apply the two proven full-length asymmetric groove cutters."""

    def cut(
        self,
        source_shape: object,
        vertical_offset: float = 0.0,
        horizontal_offset: float = 0.0,
        parameters: MacroGrooveParameters = MacroGrooveParameters(),
        seam_plan: object | None = None,
    ) -> MacroSplitResult:
        """Return a transient macro-equivalent result without source mutation.

        Positive ``vertical_offset`` moves the X-directed cut position right;
        positive ``horizontal_offset`` moves the Y-directed cut position up.
        This naming and sign convention exactly follows
        ``chanfreins_avec_Offsets.FCMacro``.

        The boolean sequence is intentionally fixed: copy source, cut the
        Y-extruded vertical cutter, cut the X-extruded horizontal cutter, then
        attempt ``removeSplitter``. Invalid-but-usable source geometry is not
        rejected before these macro operations.
        """
        if source_shape is None or not hasattr(source_shape, "BoundBox"):
            raise SplitSourceError("Macro split requires a shape-like source.")
        offset_x = self._finite(vertical_offset, "vertical offset")
        offset_y = self._finite(horizontal_offset, "horizontal offset")
        profile = self._validated_parameters(parameters)

        try:
            panel_shape = source_shape.copy()
            bounds = panel_shape.BoundBox
            xmin = float(bounds.XMin)
            xmax = float(bounds.XMax)
            ymin = float(bounds.YMin)
            ymax = float(bounds.YMax)
            zmax = float(bounds.ZMax)
            zmin = float(bounds.ZMin)
            width = xmax - xmin
            height = ymax - ymin
            source_volume = float(panel_shape.Volume)
        except Exception as error:
            raise SplitSourceError(
                "Unable to copy or measure the macro split source."
            ) from error
        if not all(
            math.isfinite(value)
            for value in (xmin, xmax, ymin, ymax, zmin, zmax, source_volume)
        ) or width <= 0.0 or height <= 0.0:
            raise SplitSourceError(
                "Macro split source must have finite positive X/Y extents."
            )

        real_center_x = (xmin + xmax) / 2.0
        real_center_y = (ymin + ymax) / 2.0
        cut_x = real_center_x + offset_x
        cut_y = real_center_y + offset_y
        half_top = profile.top_width_mm / 2.0
        half_bottom = profile.bottom_width_mm / 2.0
        z_bottom = zmax - profile.groove_depth_mm
        slot_left_x = cut_x + half_bottom
        slot_right_x = slot_left_x + profile.bottom_width_mm
        slot_lower_y = cut_y + half_bottom
        slot_upper_y = slot_lower_y + profile.bottom_width_mm
        below_panel = zmin - profile.overlap_mm

        try:
            import Part
            from FreeCAD import Vector

            if seam_plan is None:
                surface_vertical_cutter = self._extruded_profile(
                    (
                        (cut_x - half_top, ymin - profile.overlap_mm, zmax),
                        (cut_x + half_top, ymin - profile.overlap_mm, zmax),
                        (cut_x + half_top, ymin - profile.overlap_mm, z_bottom),
                        (cut_x + half_bottom, ymin - profile.overlap_mm, z_bottom),
                    ),
                    Vector(0.0, height + profile.overlap_mm * 2.0, 0.0),
                    Part,
                    Vector,
                )
                surface_horizontal_cutter = self._extruded_profile(
                    (
                        (xmin - profile.overlap_mm, cut_y - half_top, zmax),
                        (xmin - profile.overlap_mm, cut_y + half_top, zmax),
                        (xmin - profile.overlap_mm, cut_y + half_top, z_bottom),
                        (xmin - profile.overlap_mm, cut_y + half_bottom, z_bottom),
                    ),
                    Vector(width + profile.overlap_mm * 2.0, 0.0, 0.0),
                    Part,
                    Vector,
                )
                vertical_cutter = self._extruded_profile(
                    (
                        (cut_x - half_top, ymin - profile.overlap_mm, zmax),
                        (cut_x + half_top, ymin - profile.overlap_mm, zmax),
                        (cut_x + half_top, ymin - profile.overlap_mm, z_bottom),
                        (slot_right_x, ymin - profile.overlap_mm, z_bottom),
                        (slot_right_x, ymin - profile.overlap_mm, below_panel),
                        (slot_left_x, ymin - profile.overlap_mm, below_panel),
                        (slot_left_x, ymin - profile.overlap_mm, z_bottom),
                    ),
                    Vector(0.0, height + profile.overlap_mm * 2.0, 0.0),
                    Part,
                    Vector,
                )
                horizontal_cutter = self._extruded_profile(
                    (
                        (xmin - profile.overlap_mm, cut_y - half_top, zmax),
                        (xmin - profile.overlap_mm, cut_y + half_top, zmax),
                        (xmin - profile.overlap_mm, cut_y + half_top, z_bottom),
                        (xmin - profile.overlap_mm, slot_upper_y, z_bottom),
                        (xmin - profile.overlap_mm, slot_upper_y, below_panel),
                        (xmin - profile.overlap_mm, slot_lower_y, below_panel),
                        (xmin - profile.overlap_mm, slot_lower_y, z_bottom),
                    ),
                    Vector(width + profile.overlap_mm * 2.0, 0.0, 0.0),
                    Part,
                    Vector,
                )
            else:
                self._validate_seam_plan(seam_plan, cut_x, cut_y)
                surface_vertical_cutter = self._continuous_path_cutter(
                    seam_plan.vertical, profile, zmax, z_bottom, below_panel,
                    False, Part, Vector,
                )
                surface_horizontal_cutter = self._continuous_path_cutter(
                    seam_plan.horizontal, profile, zmax, z_bottom, below_panel,
                    False, Part, Vector,
                )
                vertical_cutter = self._continuous_path_cutter(
                    seam_plan.vertical, profile, zmax, z_bottom, below_panel,
                    True, Part, Vector,
                )
                horizontal_cutter = self._continuous_path_cutter(
                    seam_plan.horizontal, profile, zmax, z_bottom, below_panel,
                    True, Part, Vector,
                )
            surface_tool = self._clean_crossing_tool(
                surface_vertical_cutter, surface_horizontal_cutter
            )
            full_tool = self._clean_crossing_tool(
                vertical_cutter, horizontal_cutter
            )
            surface_result = panel_shape.cut(surface_tool)
            result = panel_shape.cut(full_tool)
        except Exception as error:
            raise SplitOperationError(
                "Macro-based vertical/horizontal groove cut failed."
            ) from error

        cleanup_applied = False
        try:
            result = result.removeSplitter()
            cleanup_applied = True
        except Exception:
            # Both reference macros explicitly keep the boolean result when
            # optional splitter cleanup is unavailable.
            pass

        # Curved segmented cutters can leave detached intersection crumbs.
        # Exclude only unprintable slivers when four substantial quadrant
        # solids remain unambiguously; their count depends on how the two
        # segmented seam envelopes meet at the shared center point.
        try:
            solids = tuple(sorted(
                result.Solids, key=lambda solid: float(solid.Volume)
            ))
            sliver_limit = (
                profile.bottom_width_mm
                * profile.top_width_mm
                * max(zmax - zmin, 1.0)
            )
            slivers = tuple(
                solid for solid in solids
                if float(solid.Volume) <= sliver_limit
            )
            quadrants = tuple(
                solid for solid in solids
                if float(solid.Volume) > sliver_limit * 1000.0
            )
            if (
                panel_shape.isValid()
                and len(quadrants) == 4
                and len(slivers) == len(solids) - 4
            ):
                result = Part.makeCompound(quadrants)
                cleanup_applied = True
        except Exception:
            pass

        try:
            if result.isNull():
                raise SplitOperationError("Macro-based cut returned null geometry.")
            result_volume = float(result.Volume)
            surface_result_volume = float(surface_result.Volume)
            solid_count = len(result.Solids)
        except SplitOperationError:
            raise
        except Exception as error:
            raise SplitOperationError(
                "Unable to inspect macro-based cut result."
            ) from error
        return MacroSplitResult(
            shape=result,
            real_center_x_mm=real_center_x,
            real_center_y_mm=real_center_y,
            cut_x_mm=cut_x,
            cut_y_mm=cut_y,
            vertical_offset_mm=offset_x,
            horizontal_offset_mm=offset_y,
            source_volume_mm3=source_volume,
            surface_groove_result_volume_mm3=surface_result_volume,
            surface_groove_removed_volume_mm3=(
                source_volume - surface_result_volume
            ),
            additional_separation_removed_volume_mm3=(
                surface_result_volume - result_volume
            ),
            result_volume_mm3=result_volume,
            solid_count=solid_count,
            separation_width_mm=profile.bottom_width_mm,
            cleanup_applied=cleanup_applied,
            seam_plan=seam_plan,
        )

    def cut_regions(
        self,
        source_shape: object,
        vertical_offset: float = 0.0,
        horizontal_offset: float = 0.0,
        parameters: MacroGrooveParameters = MacroGrooveParameters(),
        seam_plan: object | None = None,
    ) -> MacroSplitResult:
        """Extract four seam-owned regions, then apply the unchanged cutters."""
        if source_shape is None or not hasattr(source_shape, "BoundBox"):
            raise SplitSourceError("Region split requires a shape-like source.")
        if seam_plan is None:
            raise SplitOperationError("Region split requires sinuous seam guides.")
        offset_x = self._finite(vertical_offset, "vertical offset")
        offset_y = self._finite(horizontal_offset, "horizontal offset")
        profile = self._validated_parameters(parameters)
        try:
            import Part
            from FreeCAD import Vector

            panel_shape = source_shape.copy()
            bounds = panel_shape.BoundBox
            xmin, xmax = float(bounds.XMin), float(bounds.XMax)
            ymin, ymax = float(bounds.YMin), float(bounds.YMax)
            zmin, zmax = float(bounds.ZMin), float(bounds.ZMax)
            source_volume = float(panel_shape.Volume)
        except Exception as error:
            raise SplitSourceError("Unable to copy or measure region source.") from error
        real_center_x = 0.5 * (xmin + xmax)
        real_center_y = 0.5 * (ymin + ymax)
        cut_x = real_center_x + offset_x
        cut_y = real_center_y + offset_y
        self._validate_seam_plan(seam_plan, cut_x, cut_y)
        z_bottom = zmax - profile.groove_depth_mm
        below_panel = zmin - profile.overlap_mm
        try:
            # Ownership boundaries meet at the middle of the asymmetric
            # full-depth slot.  The subsequent unchanged cutter removes that
            # overlap boundary, reproducing the original 0.5 mm separation.
            ownership_offset = profile.bottom_width_mm
            region_tools, region_areas = self._region_tools(
                seam_plan,
                (xmin, xmax, ymin, ymax),
                zmin,
                zmax,
                profile.overlap_mm,
                ownership_offset,
                Part,
                Vector,
            )
            surface_vertical = self._continuous_path_cutter(
                seam_plan.vertical, profile, zmax, z_bottom, below_panel,
                False, Part, Vector,
            )
            surface_horizontal = self._continuous_path_cutter(
                seam_plan.horizontal, profile, zmax, z_bottom, below_panel,
                False, Part, Vector,
            )
            full_vertical = self._continuous_path_cutter(
                seam_plan.vertical, profile, zmax, z_bottom, below_panel,
                True, Part, Vector,
            )
            full_horizontal = self._continuous_path_cutter(
                seam_plan.horizontal, profile, zmax, z_bottom, below_panel,
                True, Part, Vector,
            )
            # Surface-groove geometry is reporting metadata only. Build the
            # exact source-level result once instead of repeating the same two
            # surface cuts for every ownership region. The production parts
            # below still use the unchanged region ownership and full-depth
            # cutters.
            surface_tool = self._clean_crossing_tool(
                surface_vertical, surface_horizontal
            )
            full_tool = self._clean_crossing_tool(full_vertical, full_horizontal)
            with operation(
                "[4] Extract structural parts",
                "surface result",
                "surface vertical groove cut",
                panel_shape,
            ):
                surface_result = panel_shape.cut(surface_tool)
            final_parts = []
            region_solid_counts = []
            region_raw_solid_counts = []
            discarded_sliver_counts = []
            component_diagnostics = []
            original_exterior = self._original_exterior_surface(
                panel_shape, zmin, zmax, Part, Vector
            )
            for index, tool in enumerate(region_tools, start=1):
                with operation(
                    "[3] Build ownership regions",
                    f"Region_{index}",
                    "panel.common(region_tool)",
                    panel_shape,
                ):
                    owned = panel_shape.common(tool)
                owned_solids = tuple(owned.Solids)
                ownership_discarded = 0
                if len(owned_solids) != 1:
                    diagnosis = diagnose_region_connectivity(
                        index,
                        owned_solids,
                        seam_plan,
                        (xmin, ymin, zmin, xmax, ymax, zmax),
                        zmax - zmin,
                        original_exterior,
                    )
                    component_diagnostics.append(diagnosis)
                    structural = diagnosis.structural_components
                    if len(structural) != 1:
                        raise RegionConnectivityError(diagnosis)
                    owned = sorted(
                        owned_solids,
                        key=lambda item: float(item.Volume),
                        reverse=True,
                    )[structural[0].rank - 1]
                    ownership_discarded = len(diagnosis.ignored_slivers)
                with operation(
                    "[4] Extract structural parts",
                    f"Region_{index}",
                    "full-depth seam cuts",
                    owned,
                ):
                    final_part = owned.cut(full_tool)
                try:
                    final_part = final_part.removeSplitter()
                except Exception as error:
                    log_event(
                        "[4] Extract structural parts",
                        f"Region_{index}",
                        "WARNING removeSplitter failed: "
                        f"{type(error).__name__}: {error}",
                    )
                raw_solids = tuple(final_part.Solids)
                if len(raw_solids) == 1:
                    final_solid = raw_solids[0]
                    discarded = 0
                else:
                    diagnosis = diagnose_region_connectivity(
                        index,
                        raw_solids,
                        seam_plan,
                        (xmin, ymin, zmin, xmax, ymax, zmax),
                        zmax - zmin,
                        original_exterior,
                    )
                    component_diagnostics.append(diagnosis)
                    structural = diagnosis.structural_components
                    if len(structural) != 1:
                        raise RegionConnectivityError(diagnosis)
                    ordered_final = tuple(sorted(
                        raw_solids,
                        key=lambda item: float(item.Volume),
                        reverse=True,
                    ))
                    final_solid = ordered_final[structural[0].rank - 1]
                    discarded = diagnosis.sliver_count
                region_solid_counts.append(1)
                region_raw_solid_counts.append(
                    len(raw_solids) + ownership_discarded
                )
                discarded_sliver_counts.append(discarded + ownership_discarded)
                final_parts.append(final_solid)
            result = Part.makeCompound(tuple(final_parts))
        except SplitOperationError:
            raise
        except Exception as error:
            raise SplitOperationError("Region-based seam extraction failed.") from error
        result_volume = float(result.Volume)
        surface_volume = float(surface_result.Volume)
        return MacroSplitResult(
            shape=result,
            real_center_x_mm=real_center_x,
            real_center_y_mm=real_center_y,
            cut_x_mm=cut_x,
            cut_y_mm=cut_y,
            vertical_offset_mm=offset_x,
            horizontal_offset_mm=offset_y,
            source_volume_mm3=source_volume,
            surface_groove_result_volume_mm3=surface_volume,
            surface_groove_removed_volume_mm3=source_volume - surface_volume,
            additional_separation_removed_volume_mm3=surface_volume - result_volume,
            result_volume_mm3=result_volume,
            solid_count=len(tuple(result.Solids)),
            separation_width_mm=profile.bottom_width_mm,
            cleanup_applied=True,
            seam_plan=seam_plan,
            partition_method="sinuous_xy_regions",
            region_areas_mm2=tuple(region_areas),
            region_raw_solid_counts=tuple(region_raw_solid_counts),
            region_solid_counts=tuple(region_solid_counts),
            region_discarded_sliver_counts=tuple(discarded_sliver_counts),
            region_component_diagnostics=tuple(component_diagnostics),
        )

    @staticmethod
    def _original_exterior_surface(panel_shape, zmin, zmax, Part, Vector):
        """Extrude the original top face's outer wire through panel Z."""
        candidates = []
        for face in panel_shape.Faces:
            bounds = face.BoundBox
            if abs(float(bounds.ZMax) - zmax) > 1.0e-6:
                continue
            if abs(float(bounds.ZMin) - zmax) > 1.0e-6:
                continue
            try:
                wire = face.OuterWire
                footprint = (
                    float(wire.BoundBox.XLength)
                    * float(wire.BoundBox.YLength)
                )
                candidates.append((footprint, wire))
            except Exception:
                continue
        if not candidates:
            return None
        outer_wire = max(candidates, key=lambda item: item[0])[1]
        try:
            return outer_wire.extrude(Vector(0.0, 0.0, zmin - zmax))
        except Exception:
            return Part.makeCompound(tuple(outer_wire.Edges))

    @classmethod
    def _region_tools(
        cls, seam_plan, bounds, zmin, zmax, overlap, ownership_offset,
        Part, Vector,
    ):
        """Validate four explicit XY ownership polygons and extrude them."""
        xmin, xmax, ymin, ymax = bounds
        vertical = cls._offset_ownership_path(
            seam_plan.vertical, ownership_offset
        )
        horizontal = cls._offset_ownership_path(
            seam_plan.horizontal, ownership_offset
        )
        vertical = (
            (vertical[0][0], ymin),
            *vertical[1:-1],
            (vertical[-1][0], ymax),
        )
        horizontal = (
            (xmin, horizontal[0][1]),
            *horizontal[1:-1],
            (xmax, horizontal[-1][1]),
        )
        vertical_low, vertical_high, horizontal_left, horizontal_right = (
            cls._split_region_paths(vertical, horizontal)
        )
        polygons = (
            vertical_low
            + tuple(reversed(horizontal_left[:-1]))
            + ((xmin, ymin),),
            (vertical_low[0], (xmax, ymin), horizontal_right[-1])
            + tuple(reversed(horizontal_right[:-1]))
            + tuple(reversed(vertical_low[:-1])),
            (horizontal_left[0], (xmin, ymax), vertical_high[-1])
            + tuple(reversed(vertical_high[:-1]))
            + tuple(reversed(horizontal_left[:-1])),
            vertical_high
            + ((xmax, ymax), horizontal_right[-1])
            + tuple(reversed(horizontal_right[:-1])),
        )
        base_z = zmin - overlap
        faces = []
        for index, polygon in enumerate(polygons, start=1):
            compact = cls._compact_xy_polygon(polygon)
            if len(compact) < 3 or cls._xy_self_intersects(compact):
                raise SplitOperationError(
                    f"Region_{index} 2D boundary is malformed."
                )
            vectors = tuple(Vector(x, y, base_z) for x, y in compact)
            face = Part.Face(Part.makePolygon(vectors + (vectors[0],)))
            if face.isNull() or not face.isValid() or float(face.Area) <= 1.0e-7:
                raise SplitOperationError(
                    f"Region_{index} 2D boundary has no valid positive area."
                )
            faces.append(face)
        rectangle = Part.Face(Part.makePolygon((
            Vector(xmin, ymin, base_z), Vector(xmax, ymin, base_z),
            Vector(xmax, ymax, base_z), Vector(xmin, ymax, base_z),
            Vector(xmin, ymin, base_z),
        )))
        area_tolerance = max(1.0e-5, float(rectangle.Area) * 1.0e-8)
        for first in range(4):
            outside = float(faces[first].cut(rectangle).Area)
            if outside > area_tolerance:
                raise SplitOperationError(
                    f"Region_{first + 1} extends outside the panel domain."
                )
            for second in range(first + 1, 4):
                if float(faces[first].common(faces[second]).Area) > area_tolerance:
                    raise SplitOperationError(
                        f"Regions {first + 1} and {second + 1} overlap."
                    )
        areas = tuple(float(face.Area) for face in faces)
        if abs(sum(areas) - float(rectangle.Area)) > area_tolerance:
            raise SplitOperationError("Four XY regions do not cover the panel domain.")
        height = (zmax - zmin) + 2.0 * overlap
        tools = tuple(face.extrude(Vector(0.0, 0.0, height)) for face in faces)
        return tools, areas

    @classmethod
    def _offset_ownership_path(cls, path, distance):
        points = tuple((float(p.x_mm), float(p.y_mm)) for p in path.points)
        normals = []
        for first, second in zip(points, points[1:]):
            dx, dy = second[0] - first[0], second[1] - first[1]
            length = math.hypot(dx, dy)
            if length <= 1.0e-9:
                raise SplitOperationError("Region seam contains a zero-length segment.")
            tx, ty = dx / length, dy / length
            normals.append(
                (ty, -tx) if path.axis == "vertical" else (-ty, tx)
            )
        shifted = []
        for index, point in enumerate(points):
            if index == 0:
                nx, ny = normals[0]
                scale = distance
            elif index == len(points) - 1:
                nx, ny = normals[-1]
                scale = distance
            else:
                nx = normals[index - 1][0] + normals[index][0]
                ny = normals[index - 1][1] + normals[index][1]
                length = math.hypot(nx, ny)
                if length <= 1.0e-9:
                    nx, ny = normals[index]
                    scale = distance
                else:
                    nx, ny = nx / length, ny / length
                    projection = nx * normals[index][0] + ny * normals[index][1]
                    scale = distance / max(projection, 0.5)
            shifted.append((point[0] + nx * scale, point[1] + ny * scale))
        return cls._remove_xy_loops(tuple(shifted))

    @classmethod
    def _remove_xy_loops(cls, points):
        """Collapse only tiny loops introduced by ownership-line offsetting."""
        result = list(cls._compact_xy_path(points))
        while True:
            crossing = None
            for first in range(len(result) - 1):
                for second in range(first + 2, len(result) - 1):
                    point = cls._xy_segment_intersection(
                        result[first], result[first + 1],
                        result[second], result[second + 1],
                    )
                    if point is not None:
                        crossing = (first, second, point)
                        break
                if crossing is not None:
                    break
            if crossing is None:
                return tuple(result)
            first, second, point = crossing
            result = result[:first + 1] + [point] + result[second + 1:]

    @classmethod
    def _split_region_paths(cls, vertical, horizontal):
        matches = []
        for vertical_index, (a, b) in enumerate(zip(vertical, vertical[1:])):
            for horizontal_index, (c, d) in enumerate(zip(horizontal, horizontal[1:])):
                point = cls._xy_segment_intersection(a, b, c, d)
                if point is not None and not any(
                    math.hypot(point[0] - old[0], point[1] - old[1]) <= 1.0e-7
                    for old, _i, _j in matches
                ):
                    matches.append((point, vertical_index, horizontal_index))
        if len(matches) != 1:
            raise SplitOperationError(
                f"Region seams must intersect once; found {len(matches)}."
            )
        point, vertical_index, horizontal_index = matches[0]
        vertical_low = vertical[:vertical_index + 1] + (point,)
        vertical_high = (point,) + vertical[vertical_index + 1:]
        horizontal_left = horizontal[:horizontal_index + 1] + (point,)
        horizontal_right = (point,) + horizontal[horizontal_index + 1:]
        return tuple(map(cls._compact_xy_path, (
            vertical_low, vertical_high, horizontal_left, horizontal_right
        )))

    @staticmethod
    def _xy_segment_intersection(a, b, c, d):
        rx, ry = b[0] - a[0], b[1] - a[1]
        sx, sy = d[0] - c[0], d[1] - c[1]
        denominator = rx * sy - ry * sx
        if abs(denominator) <= 1.0e-9:
            return None
        qx, qy = c[0] - a[0], c[1] - a[1]
        t = (qx * sy - qy * sx) / denominator
        u = (qx * ry - qy * rx) / denominator
        if -1.0e-9 <= t <= 1.0 + 1.0e-9 and -1.0e-9 <= u <= 1.0 + 1.0e-9:
            return (a[0] + t * rx, a[1] + t * ry)
        return None

    @staticmethod
    def _compact_xy_path(points):
        result = []
        for point in points:
            value = (float(point[0]), float(point[1]))
            if not result or math.hypot(
                value[0] - result[-1][0], value[1] - result[-1][1]
            ) > 1.0e-7:
                result.append(value)
        return tuple(result)

    @classmethod
    def _compact_xy_polygon(cls, points):
        compact = cls._compact_xy_path(points)
        if len(compact) > 1 and math.hypot(
            compact[0][0] - compact[-1][0],
            compact[0][1] - compact[-1][1],
        ) <= 1.0e-7:
            compact = compact[:-1]
        return compact

    @classmethod
    def _xy_self_intersects(cls, points):
        edges = tuple(zip(points, points[1:] + points[:1]))
        for first, edge_a in enumerate(edges):
            for second in range(first + 1, len(edges)):
                if second in (first, first + 1) or (
                    first == 0 and second == len(edges) - 1
                ):
                    continue
                if cls._xy_segment_intersection(
                    edge_a[0], edge_a[1], edges[second][0], edges[second][1]
                ) is not None:
                    return True
        return False

    @classmethod
    def _continuous_path_cutter(
        cls, path, profile, zmax, z_bottom, below_panel, full_depth, Part, Vector
    ):
        """Build one validated continuous ribbon and extrude it once."""
        # Accepted routes already terminate on the panel boundary or at the
        # intended artistic opening.  Extending them by the old 20 mm macro
        # overlap created oversized offset loops on tight repair candidates.
        points = cls._clean_master_points(path, 0.0)
        half_top = profile.top_width_mm / 2.0
        half_bottom = profile.bottom_width_mm / 2.0
        top_wire = cls._ribbon_wire(
            points, -half_top, profile.top_width_mm, zmax, path.axis, Part, Vector
        )
        bottom_wire = cls._ribbon_wire(
            points, half_bottom, profile.bottom_width_mm,
            z_bottom, path.axis, Part, Vector
        )
        try:
            try:
                cutter = Part.makeLoft([top_wire, bottom_wire], True)
            except Exception:
                # A very tight artistic turn can defeat OCC's ruled loft even
                # when the validated ribbon is sound.  Keep one continuous
                # ribbon and use a constant-width wall for that candidate;
                # never fall back to segment-wise prisms.
                cutter = Part.Face(top_wire).extrude(
                    Vector(0.0, 0.0, z_bottom - zmax)
                )
            if full_depth:
                slot_face = Part.Face(bottom_wire)
                slot = slot_face.extrude(
                    Vector(0.0, 0.0, below_panel - z_bottom)
                )
                cutter = cutter.fuse(slot)
            try:
                cutter = cutter.removeSplitter()
            except Exception:
                pass
            return cutter
        except Exception as error:
            raise SplitOperationError(
                "Unable to build continuous seam ribbon cutter."
            ) from error

    @classmethod
    def _segmented_path_cutter(
        cls, path, profile, zmax, z_bottom, below_panel, full_depth, Part, Vector
    ):
        """Backward-compatible name for the V7.10 continuous implementation."""
        return cls._continuous_path_cutter(
            path, profile, zmax, z_bottom, below_panel, full_depth, Part, Vector
        )

    @staticmethod
    def _clean_master_points(path, extension):
        """Extend, deduplicate, and simplify the accepted seam master curve."""
        raw = tuple((float(point.x_mm), float(point.y_mm)) for point in path.points)
        points = []
        for point in raw:
            if not points or math.dist(point, points[-1]) > 1.0e-6:
                points.append(point)
        if len(points) < 2:
            raise SplitOperationError("Continuous seam requires two points.")
        simplified = [points[0]]
        for index, point in enumerate(points[1:-1], start=1):
            previous = simplified[-1]
            following = points[index + 1]
            first = (point[0] - previous[0], point[1] - previous[1])
            second = (following[0] - point[0], following[1] - point[1])
            cross = abs(first[0] * second[1] - first[1] * second[0])
            if cross > 1.0e-5:
                simplified.append(point)
        simplified.append(points[-1])
        first, second = simplified[0], simplified[1]
        last, before_last = simplified[-1], simplified[-2]
        first_length = math.dist(first, second)
        last_length = math.dist(last, before_last)
        if first_length <= 1.0e-6 or last_length <= 1.0e-6:
            raise SplitOperationError("Continuous seam has a zero-length end.")
        extended = list(simplified)
        extended[0] = (
            first[0] - (second[0] - first[0]) * extension / first_length,
            first[1] - (second[1] - first[1]) * extension / first_length,
        )
        extended[-1] = (
            last[0] + (last[0] - before_last[0]) * extension / last_length,
            last[1] + (last[1] - before_last[1]) * extension / last_length,
        )
        return tuple(extended)

    @staticmethod
    def _ribbon_wire(points, offset, width, z, axis, Part, Vector):
        """Create one closed offset ribbon wire with no segment overlap."""
        normals = []
        for first, second in zip(points, points[1:]):
            dx, dy = second[0] - first[0], second[1] - first[1]
            length = math.hypot(dx, dy)
            if length <= 1.0e-6:
                raise SplitOperationError("Continuous seam contains a zero edge.")
            if axis == "vertical":
                normals.append((dy / length, -dx / length))
            elif axis == "horizontal":
                normals.append((-dy / length, dx / length))
            else:
                raise SplitOperationError("Unsupported seam path axis.")

        def offset_points(distance):
            result = []
            for index, point in enumerate(points):
                if index == 0:
                    normal = normals[0]
                elif index == len(points) - 1:
                    normal = normals[-1]
                else:
                    nx = normals[index - 1][0] + normals[index][0]
                    ny = normals[index - 1][1] + normals[index][1]
                    length = math.hypot(nx, ny)
                    normal = normals[index] if length <= 1.0e-6 else (nx / length, ny / length)
                result.append((point[0] + normal[0] * distance, point[1] + normal[1] * distance))
            return result

        left = offset_points(offset)
        right = offset_points(offset + width)
        polygon = MacroSplitCore._remove_xy_loops(
            tuple(left + list(reversed(right)))
        )
        if len(polygon) < 4 or MacroSplitCore._xy_self_intersects(polygon):
            raise SplitOperationError("Continuous seam ribbon self-intersects.")
        vectors = tuple(Vector(x, y, z) for x, y in polygon)
        wire = Part.makePolygon(vectors + (vectors[0],))
        if len(tuple(wire.Edges)) != len(polygon):
            raise SplitOperationError("Continuous seam ribbon has duplicate edges.")
        return Part.Wire(wire.Edges)

    @staticmethod
    def _clean_crossing_tool(first, second):
        """Fuse both canonical seam tools once and remove internal splitters."""
        try:
            tool = first.fuse(second)
            try:
                tool = tool.removeSplitter()
            except Exception:
                pass
            return tool
        except Exception as error:
            raise SplitOperationError("Canonical seam crossing tool failed.") from error

    @staticmethod
    def _validate_seam_plan(seam_plan, cut_x, cut_y):
        """Require the focused immutable plan and unchanged nominal offsets."""
        try:
            valid = (
                seam_plan.intersection_count == 1
                and seam_plan.vertical.axis == "vertical"
                and seam_plan.horizontal.axis == "horizontal"
                and abs(seam_plan.vertical.nominal_coordinate_mm - cut_x) <= 1.0e-7
                and abs(seam_plan.horizontal.nominal_coordinate_mm - cut_y) <= 1.0e-7
            )
        except Exception as error:
            raise SplitOperationError("Sinuous seam plan is unavailable.") from error
        if not valid:
            raise SplitOperationError("Sinuous seam plan is inconsistent with cut offsets.")

    @staticmethod
    def _extruded_profile(points, extrusion, Part, Vector):
        """Build and extrude the macros' ordered four-point profile."""
        vectors = [Vector(*point) for point in points]
        polygon = Part.makePolygon((*vectors, vectors[0]))
        wire = Part.Wire(polygon.Edges)
        return Part.Face(wire).extrude(extrusion)

    @staticmethod
    def _finite(value: object, label: str) -> float:
        """Return one finite scalar offset without imposing policy limits."""
        try:
            result = float(value)
        except (TypeError, ValueError) as error:
            raise SplitOperationError(f"Macro split {label} must be finite.") from error
        if not math.isfinite(result):
            raise SplitOperationError(f"Macro split {label} must be finite.")
        return result

    @classmethod
    def _validated_parameters(
        cls,
        parameters: MacroGrooveParameters,
    ) -> MacroGrooveParameters:
        """Validate geometric profile scalars without redesigning the profile."""
        if not isinstance(parameters, MacroGrooveParameters):
            raise SplitOperationError(
                "Macro split parameters must be MacroGrooveParameters."
            )
        values = (
            cls._finite(parameters.groove_depth_mm, "groove depth"),
            cls._finite(parameters.top_width_mm, "top width"),
            cls._finite(parameters.bottom_width_mm, "bottom width"),
            cls._finite(parameters.overlap_mm, "overlap"),
        )
        if any(value <= 0.0 for value in values):
            raise SplitOperationError(
                "Macro groove dimensions and overlap must be positive."
            )
        if (
            parameters.bottom_width_mm
            > (parameters.top_width_mm - parameters.bottom_width_mm) / 2.0
        ):
            raise SplitOperationError(
                "Macro separation width must fit inside the existing flat "
                "bottom segment."
            )
        return parameters

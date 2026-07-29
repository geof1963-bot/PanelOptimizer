# -*- coding: utf-8 -*-
"""FreeCAD GUI command for the V4.50 lipped, dowelled four-STL workflow."""

from __future__ import annotations

import os
import time

import FreeCAD
import FreeCADGui

from Core.Exceptions import PanelOptimizerError
from Core.DowelPlanner import DowelPlanner
from Core.LipBuilder import LipBuilder, LipParameters
from Core.MacroPartExtractor import MacroPartExtractor
from Core.MacroSplitCore import MacroGrooveParameters, MacroSplitCore
from Core.MeshPatchRebuilder import build_macro_mesh_parts, export_mesh_parts
from Core.SinuousSeamPath import SinuousSeamPathFinder
from Core.SplitWorkflow import SplitDocumentWriter, validate_single_selection


class PanelOptimizerSplitPanelCommand:
    """Create, validate, and export four parts from macro-cut geometry."""

    def __init__(
        self,
        vertical_offset: float = 0.0,
        horizontal_offset: float = 0.0,
        parameters: MacroGrooveParameters = MacroGrooveParameters(),
    ) -> None:
        """Store explicit macro inputs; registered command defaults to center."""
        self._vertical_offset = vertical_offset
        self._horizontal_offset = horizontal_offset
        self._parameters = parameters

    def GetResources(self):
        """Return command label, tooltip, and optional icon path."""
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "Gui",
            "Resources",
            "icons",
            "SplitPanel.svg",
        )
        return {
            "Pixmap": icon_path,
            "MenuText": "Split Panel",
            "ToolTip": "Create four grooved, dowelled, lipped parts and export STL",
        }

    def IsActive(self):
        """Enable the command whenever a FreeCAD document is active."""
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        """Run V4.30 seams, V4.40 dowels, V4.50 lips, and four-STL export."""
        document = FreeCAD.ActiveDocument
        if document is None:
            self._error("PanelOptimizer: no active document.")
            return

        timings = {}
        total_started = time.perf_counter()
        interactive_wait = 0.0
        try:
            source_object = validate_single_selection(
                FreeCADGui.Selection.getSelection()
            )
            self._validate_seam_preview_names(document)
            path_finder = SinuousSeamPathFinder()
            started = time.perf_counter()
            proposed_plan = path_finder.generate(
                source_object.Shape,
                self._vertical_offset,
                self._horizontal_offset,
            )
            bounds = source_object.Shape.BoundBox
            panel_bounds = (
                float(bounds.XMin), float(bounds.XMax),
                float(bounds.YMin), float(bounds.YMax),
            )
            candidate_plans = tuple(
                path_finder.candidate_plans(proposed_plan, panel_bounds)
            )
            timings["seams"] = time.perf_counter() - started
            macro_result = None
            started = time.perf_counter()
            for candidate in candidate_plans:
                attempt = MacroSplitCore().cut(
                    source_object.Shape,
                    self._vertical_offset,
                    self._horizontal_offset,
                    self._parameters,
                    seam_plan=candidate,
                )
                if attempt.solid_count == 4:
                    macro_result = attempt
                    break
            timings["split"] = time.perf_counter() - started
            if macro_result is None:
                raise PanelOptimizerError(
                    "No seam candidate produced exactly four parts."
                )
            planner = DowelPlanner()
            started = time.perf_counter()
            dowel_plan = planner.plan(macro_result)
            timings["dowel_plan"] = time.perf_counter() - started
            started = time.perf_counter()
            dowel_application = planner.apply(macro_result, dowel_plan)
            timings["dowel_cut"] = time.perf_counter() - started
            started = time.perf_counter()
            lip_application = LipBuilder(
                LipParameters(
                    groove_top_width_mm=self._parameters.top_width_mm,
                )
            ).apply(
                dowel_application.macro_result,
                dowel_cutters=dowel_application.cutters,
            )
            timings["lips"] = time.perf_counter() - started
            macro_result = lip_application.macro_result
            mesh_parts = build_macro_mesh_parts(macro_result, timings=timings)
            extraction = MacroPartExtractor().extract(
                macro_result,
                str(source_object.Name),
                accept_closed_invalid=True,
                verify_overlap=False,
            )
            output_objects = SplitDocumentWriter().write(
                document,
                extraction.execution,
            )
            self._write_seam_previews(
                document,
                macro_result.seam_plan,
                float(bounds.ZMax) + 0.1,
                recompute=False,
            )
            self._write_dowel_preview(
                document,
                dowel_application.cutters,
                recompute=False,
            )
            self._write_lip_preview(
                document, lip_application.preview_shape, recompute=False
            )
            document.recompute()
            FreeCAD.Console.PrintMessage(
                "PanelOptimizer\n"
                f"Source: {source_object.Name}\n"
                f"Cuts: X = {macro_result.cut_x_mm:g}, "
                f"Y = {macro_result.cut_y_mm:g}\n"
            )
            for path in (
                macro_result.seam_plan.vertical,
                macro_result.seam_plan.horizontal,
            ):
                FreeCAD.Console.PrintMessage(
                    f"{path.axis.title()} seam: {path.path_length_mm:.3f} mm, "
                    f"max deviation {path.maximum_deviation_mm:.3f} mm, "
                    f"features {len(path.followed_feature_ids)}, segments "
                    f"{path.segment_count_before_cleanup} -> "
                    f"{path.segment_count_after_cleanup}, transitions "
                    f"{path.smoothing_transition_count}, artificial turn "
                    f"{path.maximum_artificial_turn_before_deg:.2f} -> "
                    f"{path.maximum_artificial_turn_after_deg:.2f} deg, contour "
                    f"{path.contour_following_length_mm:.3f} mm "
                    f"({path.contour_following_ratio:.1%})\n"
                )
                for report in path.hole_offset_reports:
                    FreeCAD.Console.PrintMessage(
                        f"  {report.feature_id}: bounds "
                        f"{report.boundary_bounds_mm}, interior "
                        f"{report.interior_side}, envelope "
                        f"{report.cutter_envelope_mm:.3f} mm + clearance "
                        f"{report.clearance_mm:.3f} mm -> offset "
                        f"{report.final_offset_mm:.3f} mm, remaining "
                        f"{report.minimum_material_side_clearance_mm:.3f} mm\n"
                    )
            for branch in dowel_application.plan.branches:
                positions = tuple(
                    dowel.center_xyz_mm
                    for dowel in dowel_application.plan.dowels
                    if dowel.seam_branch == branch.branch_id
                )
                rejection_reasons = tuple(sorted({
                    item.reason for item in branch.rejected_candidates
                }))
                FreeCAD.Console.PrintMessage(
                    f"{branch.branch_id}: "
                    f"usable {branch.usable_length_mm:.3f} mm, targets "
                    f"{branch.target_fractions}, positions {positions}, "
                    f"spacing {branch.spacing_mm}, fallback "
                    f"{branch.used_two_dowel_fallback}, sampled "
                    f"{branch.sampled_point_count}, safe "
                    f"{branch.safe_candidate_count}, selected "
                    f"{len(branch.accepted_dowel_ids)}, rejected geometry "
                    f"{branch.rejected_geometry_counts or rejection_reasons}, "
                    f"cheap {branch.cheap_candidate_count}, shortlist "
                    f"{branch.shortlisted_candidate_count}, exact "
                    f"{branch.exact_validation_count}, safe intervals "
                    f"{branch.safe_interval_count}, unsupported "
                    f"{branch.unsupported_spans_mm}, largest "
                    f"{branch.largest_unsupported_span_mm:.3f} mm, "
                    f"coverage {branch.coverage_target_achieved}, spacing "
                    f"exception {branch.spacing_exception}, degraded two-dowel "
                    f"{branch.degraded_two_dowel}\n"
                )
            for report in lip_application.reports:
                FreeCAD.Console.PrintMessage(
                    f"{report.name} lips: {report.total_length_mm:.3f} mm, "
                    f"+{report.volume_added_mm3:.3f} mm^3, "
                    f"segments {report.segment_count}, trimmed "
                    f"{report.trimmed_segment_count}, rejected "
                    f"{report.rejected_segment_count}, dimensions "
                    f"{report.dimensions_before_mm} -> "
                    f"{report.dimensions_after_mm}\n"
                )
            for part in mesh_parts:
                status = "watertight - OK" if part.is_printable else "EXCEEDS LIMIT"
                FreeCAD.Console.PrintMessage(
                    f"{part.name}: {status}\n"
                )
            FreeCAD.Console.PrintMessage(
                f"{len(output_objects)} parts created.\n"
            )
            if not all(part.is_printable for part in mesh_parts):
                self._error(
                    "PanelOptimizer: STL export blocked by printable limits:\n"
                    + "\n".join(
                        f"{part.name}: "
                        + ", ".join(
                            dimension
                            for dimension, within in (
                                ("X", part.within_x_limit),
                                ("Y", part.within_y_limit),
                            )
                            if not within
                        )
                        + " exceeds configured limit"
                        for part in mesh_parts
                        if not part.is_printable
                    )
                )
                return
            wait_started = time.perf_counter()
            output_directory = self._select_output_directory()
            interactive_wait += time.perf_counter() - wait_started
            if not output_directory:
                FreeCAD.Console.PrintWarning(
                    "PanelOptimizer: STL export cancelled; four result solids "
                    "remain in PanelOptimizer_Result.\n"
                )
                timings["total"] = time.perf_counter() - total_started - interactive_wait
                self._print_performance(timings)
                return
            artifacts = export_mesh_parts(
                mesh_parts, output_directory, timings=timings
            )
            timings["total"] = time.perf_counter() - total_started - interactive_wait
            FreeCAD.Console.PrintMessage(
                f"{len(artifacts)} STL files exported.\n"
            )
            self._print_performance(timings)
        except PanelOptimizerError as error:
            self._error(f"PanelOptimizer: {error}")
        except Exception as error:
            self._error(
                "PanelOptimizer: unexpected macro split failure: "
                f"{error}"
            )

    @staticmethod
    def _validate_seam_preview_names(document) -> None:
        """Reject unowned reserved preview names before document mutation."""
        for name in (
            "PanelOptimizer_VerticalSeam",
            "PanelOptimizer_HorizontalSeam",
        ):
            output = document.getObject(name)
            if output is not None and (
                "PanelOptimizerRole" not in tuple(output.PropertiesList)
                or output.PanelOptimizerRole != "PanelOptimizer.SeamPreview.v4"
            ):
                raise PanelOptimizerError(
                    f"Existing object '{name}' is not an owned seam preview."
                )
        lips = document.getObject("PanelOptimizer_Lips")
        if lips is not None and (
            "PanelOptimizerRole" not in tuple(lips.PropertiesList)
            or lips.PanelOptimizerRole != "PanelOptimizer.LipPreview.v4"
        ):
            raise PanelOptimizerError(
                "Existing object 'PanelOptimizer_Lips' is not an owned lip preview."
            )
        dowels = document.getObject("PanelOptimizer_Dowels")
        if dowels is not None and (
            "PanelOptimizerRole" not in tuple(dowels.PropertiesList)
            or dowels.PanelOptimizerRole != "PanelOptimizer.DowelPreview.v4"
        ):
            raise PanelOptimizerError(
                "Existing object 'PanelOptimizer_Dowels' is not an owned "
                "dowel preview."
            )

    @staticmethod
    def _write_seam_previews(
        document, seam_plan, z_value, recompute=True
    ) -> tuple[object, object]:
        """Create or update two owned lightweight Part polyline previews."""
        import Part

        definitions = (
            ("PanelOptimizer_VerticalSeam", seam_plan.vertical),
            ("PanelOptimizer_HorizontalSeam", seam_plan.horizontal),
        )
        previews = []
        for name, path in definitions:
            output = document.getObject(name)
            if output is None:
                output = document.addObject("Part::Feature", name)
                output.addProperty(
                    "App::PropertyString",
                    "PanelOptimizerRole",
                    "PanelOptimizer",
                )
                output.PanelOptimizerRole = "PanelOptimizer.SeamPreview.v4"
                output.setEditorMode("PanelOptimizerRole", 1)
            elif (
                "PanelOptimizerRole" not in tuple(output.PropertiesList)
                or output.PanelOptimizerRole != "PanelOptimizer.SeamPreview.v4"
            ):
                raise PanelOptimizerError(
                    f"Existing object '{name}' is not an owned seam preview."
                )
            vectors = tuple(
                FreeCAD.Vector(point.x_mm, point.y_mm, z_value)
                for point in path.points
            )
            output.Shape = Part.makePolygon(vectors)
            output.Label = name
            previews.append(output)
        if recompute:
            document.recompute()
        return tuple(previews)

    @staticmethod
    def _write_dowel_preview(document, cutters, recompute=True) -> object:
        """Create or update one owned lightweight compound of planned holes."""
        import Part

        name = "PanelOptimizer_Dowels"
        output = document.getObject(name)
        if output is None:
            output = document.addObject("Part::Feature", name)
            output.addProperty(
                "App::PropertyString",
                "PanelOptimizerRole",
                "PanelOptimizer",
            )
            output.PanelOptimizerRole = "PanelOptimizer.DowelPreview.v4"
            output.setEditorMode("PanelOptimizerRole", 1)
        elif (
            "PanelOptimizerRole" not in tuple(output.PropertiesList)
            or output.PanelOptimizerRole != "PanelOptimizer.DowelPreview.v4"
        ):
            raise PanelOptimizerError(
                f"Existing object '{name}' is not an owned dowel preview."
            )
        output.Shape = Part.makeCompound(tuple(cutter.copy() for cutter in cutters))
        output.Label = name
        view = getattr(output, "ViewObject", None)
        if view is not None:
            view.ShapeColor = (0.95, 0.65, 0.10)
            view.Transparency = 65
        if recompute:
            document.recompute()
        return output

    @staticmethod
    def _write_lip_preview(document, preview_shape, recompute=True) -> object:
        """Create or update the owned lightweight V4.50 lip compound."""
        name = "PanelOptimizer_Lips"
        output = document.getObject(name)
        if output is None:
            output = document.addObject("Part::Feature", name)
            output.addProperty(
                "App::PropertyString",
                "PanelOptimizerRole",
                "PanelOptimizer",
            )
            output.PanelOptimizerRole = "PanelOptimizer.LipPreview.v4"
            output.setEditorMode("PanelOptimizerRole", 1)
        elif (
            "PanelOptimizerRole" not in tuple(output.PropertiesList)
            or output.PanelOptimizerRole != "PanelOptimizer.LipPreview.v4"
        ):
            raise PanelOptimizerError(
                f"Existing object '{name}' is not an owned lip preview."
            )
        output.Shape = preview_shape.copy()
        output.Label = name
        view = getattr(output, "ViewObject", None)
        if view is not None:
            view.ShapeColor = (0.20, 0.75, 0.95)
            view.Transparency = 25
        if recompute:
            document.recompute()
        return output

    @staticmethod
    def _print_performance(timings) -> None:
        """Print one concise V4.61 stage report in seconds."""
        FreeCAD.Console.PrintMessage(
            "PanelOptimizer Performance\n"
            f"Seams: {timings.get('seams', 0.0):.3f} s\n"
            f"Split: {timings.get('split', 0.0):.3f} s\n"
            f"Dowels plan: {timings.get('dowel_plan', 0.0):.3f} s\n"
            f"Dowels cut: {timings.get('dowel_cut', 0.0):.3f} s\n"
            f"Lips: {timings.get('lips', 0.0):.3f} s\n"
            f"Mesh: {timings.get('mesh', 0.0):.3f} s\n"
            f"Mesh repair: {timings.get('mesh_repair', 0.0):.3f} s\n"
            f"STL export: {timings.get('stl_export', 0.0):.3f} s\n"
            f"STL verify: {timings.get('stl_verify', 0.0):.3f} s\n"
            f"Total: {timings.get('total', 0.0):.3f} s\n"
        )

    @staticmethod
    def _select_output_directory() -> str:
        """Ask for the existing directory used by transactional export."""
        from PySide import QtGui

        return str(
            QtGui.QFileDialog.getExistingDirectory(
                None,
                "Select PanelOptimizer STL output directory",
                "",
                QtGui.QFileDialog.ShowDirsOnly,
            )
        )

    @staticmethod
    def _error(message: str) -> None:
        """Emit one concise command failure without changing the source."""
        FreeCAD.Console.PrintError(message.rstrip() + "\n")


if hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand(
        "PanelOptimizer_SplitPanel",
        PanelOptimizerSplitPanelCommand(),
    )

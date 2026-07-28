# -*- coding: utf-8 -*-
"""FreeCAD GUI command for the V4.40 dowelled four-STL workflow."""

from __future__ import annotations

import os

import FreeCAD
import FreeCADGui

from Core.Exceptions import PanelOptimizerError
from Core.DowelPlanner import DowelPlanner
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
            "ToolTip": "Apply macro grooves, create four parts, and export STL",
        }

    def IsActive(self):
        """Enable the command whenever a FreeCAD document is active."""
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        """Run V4.30 seams, V4.40 dowels, V4.26 mesh, and four-STL export."""
        document = FreeCAD.ActiveDocument
        if document is None:
            self._error("PanelOptimizer: no active document.")
            return

        try:
            source_object = validate_single_selection(
                FreeCADGui.Selection.getSelection()
            )
            self._validate_seam_preview_names(document)
            path_finder = SinuousSeamPathFinder()
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
            macro_result = None
            for candidate in path_finder.candidate_plans(
                proposed_plan, panel_bounds
            ):
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
            if macro_result is None:
                raise PanelOptimizerError(
                    "No seam candidate produced exactly four parts."
                )
            dowel_application = DowelPlanner().apply(macro_result)
            macro_result = dowel_application.macro_result
            mesh_parts = build_macro_mesh_parts(macro_result)
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
            )
            self._write_dowel_preview(
                document,
                dowel_application.cutters,
            )
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
                    f"features {len(path.followed_feature_ids)}\n"
                )
            for branch in dowel_application.plan.branches:
                FreeCAD.Console.PrintMessage(
                    f"{branch.branch_id}: "
                    f"{len(branch.accepted_dowel_ids)} dowels\n"
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
            output_directory = self._select_output_directory()
            if not output_directory:
                FreeCAD.Console.PrintWarning(
                    "PanelOptimizer: STL export cancelled; four result solids "
                    "remain in PanelOptimizer_Result.\n"
                )
                return
            artifacts = export_mesh_parts(mesh_parts, output_directory)
            FreeCAD.Console.PrintMessage(
                f"{len(artifacts)} STL files exported.\n"
            )
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
    def _write_seam_previews(document, seam_plan, z_value) -> tuple[object, object]:
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
        document.recompute()
        return tuple(previews)

    @staticmethod
    def _write_dowel_preview(document, cutters) -> object:
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
        document.recompute()
        return output

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

# -*- coding: utf-8 -*-
"""FreeCAD GUI command for the V4.26 watertight mesh workflow."""

from __future__ import annotations

import os

import FreeCAD
import FreeCADGui

from Core.Exceptions import PanelOptimizerError
from Core.MacroPartExtractor import MacroPartExtractor
from Core.MacroSplitCore import MacroGrooveParameters, MacroSplitCore
from Core.MeshPatchRebuilder import build_macro_mesh_parts, export_mesh_parts
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
        """Run V4.21 cutting, local mesh patching, and four-STL export."""
        document = FreeCAD.ActiveDocument
        if document is None:
            self._error("PanelOptimizer: no active document.")
            return

        try:
            source_object = validate_single_selection(
                FreeCADGui.Selection.getSelection()
            )
            macro_result = MacroSplitCore().cut(
                source_object.Shape,
                self._vertical_offset,
                self._horizontal_offset,
                self._parameters,
            )
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
            FreeCAD.Console.PrintMessage(
                "PanelOptimizer\n"
                f"Source: {source_object.Name}\n"
                f"Cuts: X = {macro_result.cut_x_mm:g}, "
                f"Y = {macro_result.cut_y_mm:g}\n"
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

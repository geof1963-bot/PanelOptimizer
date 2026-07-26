# -*- coding: utf-8 -*-
"""FreeCAD GUI command for the deterministic V4.00 split/export prototype."""

from __future__ import annotations

import os

import FreeCAD
import FreeCADGui

from Core.Exceptions import PanelOptimizerError
from Core.ExportEngine import ExportEngine
from Core.SplitterEngine import SplitterEngine
from Core.SplitWorkflow import (
    SplitDocumentWriter,
    validate_single_selection,
)


class PanelOptimizerSplitPanelCommand:
    """Split one selected solid into four quadrants and export four STLs."""

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
            "MenuText": "Split and Export Panel",
            "ToolTip": "Split the selected panel into four solids and export STL",
        }

    def IsActive(self):
        """Enable the command whenever a FreeCAD document is active."""
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        """Execute selection, split, document output, validation, and export."""
        document = FreeCAD.ActiveDocument
        if document is None:
            self._error("PanelOptimizer: no active document.")
            return

        try:
            source_object = validate_single_selection(
                FreeCADGui.Selection.getSelection()
            )
            source_id = str(source_object.Name)
            execution = SplitterEngine().split_four_quadrants(
                source_object.Shape,
                source_id,
            )
            output_objects = SplitDocumentWriter().write(document, execution)

            if not execution.result.all_parts_printable:
                details = "\n".join(execution.result.validation_messages)
                self._error(
                    "PanelOptimizer created four inspection parts, but STL "
                    "export was blocked by effective printable limits:\n"
                    + details
                )
                return

            output_directory = self._select_output_directory()
            if not output_directory:
                FreeCAD.Console.PrintWarning(
                    "PanelOptimizer: STL export cancelled; four result solids "
                    "remain in PanelOptimizer_Result.\n"
                )
                return

            report = ExportEngine(execution.resolve_shape).export_parts(
                execution.result.parts,
                output_directory,
                "STL",
            )
            FreeCAD.Console.PrintMessage(
                "PanelOptimizer: split complete. Created "
                f"{len(output_objects)} solids and exported "
                f"{len(report.artifacts)} STL files to "
                f"{report.output_directory}.\n"
            )
        except PanelOptimizerError as error:
            self._error(f"PanelOptimizer: {error}")
        except Exception as error:
            self._error(
                "PanelOptimizer: unexpected split/export failure: "
                f"{error}"
            )

    @staticmethod
    def _select_output_directory() -> str:
        """Ask the user for an explicit existing STL destination directory."""
        from PySide import QtGui

        selected = QtGui.QFileDialog.getExistingDirectory(
            None,
            "Select PanelOptimizer STL output directory",
            "",
            QtGui.QFileDialog.ShowDirsOnly,
        )
        return str(selected)

    @staticmethod
    def _error(message: str) -> None:
        """Emit one concise command failure without changing the source."""
        FreeCAD.Console.PrintError(message.rstrip() + "\n")


if hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand(
        "PanelOptimizer_SplitPanel",
        PanelOptimizerSplitPanelCommand(),
    )

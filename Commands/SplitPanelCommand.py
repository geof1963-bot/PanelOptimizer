# -*- coding: utf-8 -*-
"""FreeCAD GUI command for the pragmatic V4.10 macro-equivalent cut."""

from __future__ import annotations

import os

import FreeCAD
import FreeCADGui

from Core.Exceptions import PanelOptimizerError
from Core.MacroSplitCore import MacroGrooveParameters, MacroSplitCore
from Core.SplitWorkflow import validate_single_selection


class PanelOptimizerSplitPanelCommand:
    """Create one macro-equivalent crossed-groove result object."""

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
            "MenuText": "Macro Split Panel",
            "ToolTip": "Apply the proven centered macro groove geometry",
        }

    def IsActive(self):
        """Enable the command whenever a FreeCAD document is active."""
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        """Apply the centered V4.10 macro cut without deep analysis."""
        document = FreeCAD.ActiveDocument
        if document is None:
            self._error("PanelOptimizer: no active document.")
            return

        try:
            source_object = validate_single_selection(
                FreeCADGui.Selection.getSelection()
            )
            result = MacroSplitCore().cut(
                source_object.Shape,
                self._vertical_offset,
                self._horizontal_offset,
                self._parameters,
            )
            output_object = document.addObject(
                "Part::Feature",
                "FINAL_PANEL_BEVELED",
            )
            output_object.Shape = result.shape
            document.recompute()
            bounds = source_object.Shape.BoundBox
            FreeCAD.Console.PrintMessage(
                "PanelOptimizer V4.10 - Macro Split\n"
                f"Source: {source_object.Name}\n"
                f"Panel: {bounds.XLength:g} x {bounds.YLength:g} x "
                f"{bounds.ZLength:g} mm\n"
                f"Real center X/Y: {result.real_center_x_mm:g}, "
                f"{result.real_center_y_mm:g}\n"
                f"Vertical cut X: {result.cut_x_mm:g}\n"
                f"Horizontal cut Y: {result.cut_y_mm:g}\n"
                f"Offsets: X={result.vertical_offset_mm:g}, "
                f"Y={result.horizontal_offset_mm:g}\n"
                "Macro-based cut completed.\n"
            )
        except PanelOptimizerError as error:
            self._error(f"PanelOptimizer: {error}")
        except Exception as error:
            self._error(
                "PanelOptimizer: unexpected macro split failure: "
                f"{error}"
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

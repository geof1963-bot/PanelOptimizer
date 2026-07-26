# -*- coding: utf-8 -*-
"""Explicit console diagnostic command for selected invalid topology."""

from __future__ import annotations

import os

import FreeCAD
import FreeCADGui

from Core.TopologyDiagnostic import (
    format_topology_diagnostic,
    inspect_topology,
)


class PanelOptimizerGeometryDiagnosticCommand:
    """Print a bounded read-only topology diagnostic for one selected shape."""

    def GetResources(self):
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "Gui",
            "Resources",
            "icons",
            "Analyze.svg",
        )
        return {
            "Pixmap": icon_path,
            "MenuText": "Diagnose Geometry",
            "ToolTip": "Locate suspicious topology without modifying geometry",
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):
        try:
            selection = tuple(FreeCADGui.Selection.getSelection())
            if len(selection) != 1 or not hasattr(selection[0], "Shape"):
                raise ValueError("Select exactly one object with a Shape.")
            report = inspect_topology(selection[0].Shape)
            FreeCAD.Console.PrintMessage(
                "\n" + format_topology_diagnostic(report)
            )
        except Exception as error:
            FreeCAD.Console.PrintError(
                f"PanelOptimizer geometry diagnostic failed: {error}\n"
            )


if hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand(
        "PanelOptimizer_DiagnoseGeometry",
        PanelOptimizerGeometryDiagnosticCommand(),
    )

# -*- coding: utf-8 -*-
"""
PanelOptimizer Workbench

AnalyzeCommand.py

FreeCAD 1.1.x
"""

import os

import FreeCAD
import FreeCADGui


class PanelOptimizerAnalyzeCommand:
    """
    Analyze the currently selected panel.
    """

    def GetResources(self):
        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "Gui",
            "Resources",
            "icons",
            "Analyze.svg"
        )

        return {
            "Pixmap": icon_path,
            "MenuText": "Analyze",
            "ToolTip": "Analyze the selected panel geometry"
        }

    def IsActive(self):
        """
        The command is active only if a document is open.
        """
        return FreeCAD.ActiveDocument is not None

    def Activated(self):

        doc = FreeCAD.ActiveDocument

        if doc is None:
            FreeCAD.Console.PrintError(
                "\nPanelOptimizer : no active document.\n"
            )
            return

        selection = FreeCADGui.Selection.getSelection()

        if len(selection) == 0:
            FreeCAD.Console.PrintError(
                "\nPanelOptimizer : no object selected.\n"
            )
            return

        obj = selection[0]

        if not hasattr(obj, "Shape"):
            FreeCAD.Console.PrintError(
                "\nPanelOptimizer : selected object has no Shape.\n"
            )
            return

        shape = obj.Shape

        if shape.isNull():
            FreeCAD.Console.PrintError(
                "\nPanelOptimizer : invalid shape.\n"
            )
            return

        FreeCAD.Console.PrintMessage("\n")
        FreeCAD.Console.PrintMessage("=====================================\n")
        FreeCAD.Console.PrintMessage(" PanelOptimizer - Analyze\n")
        FreeCAD.Console.PrintMessage("=====================================\n\n")

        FreeCAD.Console.PrintMessage(
            f"Object : {obj.Label}\n"
        )

        FreeCAD.Console.PrintMessage(
            f"Faces : {len(shape.Faces)}\n"
        )

        FreeCAD.Console.PrintMessage(
            f"Edges : {len(shape.Edges)}\n"
        )

        FreeCAD.Console.PrintMessage(
            f"Vertices : {len(shape.Vertexes)}\n"
        )

        bbox = shape.BoundBox

        FreeCAD.Console.PrintMessage("\nBounding Box\n")
        FreeCAD.Console.PrintMessage("-----------------------------\n")

        FreeCAD.Console.PrintMessage(
            f"X : {bbox.XLength:.3f} mm\n"
        )

        FreeCAD.Console.PrintMessage(
            f"Y : {bbox.YLength:.3f} mm\n"
        )

        FreeCAD.Console.PrintMessage(
            f"Z : {bbox.ZLength:.3f} mm\n"
        )

        FreeCAD.Console.PrintMessage("\nVolume\n")
        FreeCAD.Console.PrintMessage("-----------------------------\n")

        FreeCAD.Console.PrintMessage(
            f"{shape.Volume:.3f} mm³\n"
        )

        FreeCAD.Console.PrintMessage("\nArea\n")
        FreeCAD.Console.PrintMessage("-----------------------------\n")

        FreeCAD.Console.PrintMessage(
            f"{shape.Area:.3f} mm²\n"
        )

        FreeCAD.Console.PrintMessage("\n")

        try:
            from PanelOptimizer.Core.Analyzer import Analyzer

            analyzer = Analyzer()

            analyzer.analyze(obj)

        except Exception as err:

            FreeCAD.Console.PrintWarning(
                "\nAnalyzer module not available.\n"
            )

            FreeCAD.Console.PrintWarning(
                str(err) + "\n"
            )


FreeCADGui.addCommand(
    "PanelOptimizer_Analyze",
    PanelOptimizerAnalyzeCommand()
)
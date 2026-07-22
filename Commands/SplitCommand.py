# -*- coding: utf-8 -*-
"""
PanelOptimizer Workbench

SplitPanelCommand.py

FreeCAD 1.1.x
"""

import os

import FreeCAD
import FreeCADGui


class PanelOptimizerSplitPanelCommand:
    """
    Split the selected panel.
    """

    def GetResources(self):

        icon_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "Gui",
            "Resources",
            "icons",
            "SplitPanel.svg"
        )

        return {
            "Pixmap": icon_path,
            "MenuText": "Split Panel",
            "ToolTip": "Prepare the selected panel for splitting"
        }

    def IsActive(self):
        return FreeCAD.ActiveDocument is not None

    def Activated(self):

        doc = FreeCAD.ActiveDocument

        if doc is None:
            FreeCAD.Console.PrintError(
                "\nPanelOptimizer : no active document.\n"
            )
            return

        selection = FreeCADGui.Selection.getSelection()

        if len(selection) != 1:
            FreeCAD.Console.PrintError(
                "\nSelect exactly one solid.\n"
            )
            return

        obj = selection[0]

        if not hasattr(obj, "Shape"):
            FreeCAD.Console.PrintError(
                "\nSelected object has no Shape.\n"
            )
            return

        shape = obj.Shape

        if shape.isNull():
            FreeCAD.Console.PrintError(
                "\nInvalid shape.\n"
            )
            return

        bbox = shape.BoundBox

        FreeCAD.Console.PrintMessage("\n")
        FreeCAD.Console.PrintMessage("=========================================\n")
        FreeCAD.Console.PrintMessage(" PanelOptimizer - Split Panel\n")
        FreeCAD.Console.PrintMessage("=========================================\n\n")

        FreeCAD.Console.PrintMessage(
            f"Selected object : {obj.Label}\n"
        )

        FreeCAD.Console.PrintMessage(
            f"Bounding Box : "
            f"{bbox.XLength:.2f} × "
            f"{bbox.YLength:.2f} × "
            f"{bbox.ZLength:.2f} mm\n\n"
        )

        if bbox.XLength <= 330 and bbox.YLength <= 330:

            FreeCAD.Console.PrintMessage(
                "Panel already printable.\n"
            )

            return

        FreeCAD.Console.PrintMessage(
            "Panel exceeds printable size.\n"
        )

        FreeCAD.Console.PrintMessage(
            "Preparing split engine...\n"
        )

        try:

            from PanelOptimizer.Core.Splitter import Splitter

            splitter = Splitter()

            splitter.prepare(obj)

        except Exception as err:

            FreeCAD.Console.PrintWarning(
                "\nSplitter module unavailable.\n"
            )

            FreeCAD.Console.PrintWarning(
                str(err) + "\n"
            )


FreeCADGui.addCommand(
    "PanelOptimizer_SplitPanel",
    PanelOptimizerSplitPanelCommand()
)
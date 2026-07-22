# -*- coding: utf-8 -*-
"""
PanelOptimizer Workbench
InitGui.py

Compatible FreeCAD 1.1.x
"""

import os
import FreeCAD
import FreeCADGui


class PanelOptimizerWorkbench(Workbench):
    """
    PanelOptimizer FreeCAD Workbench
    """

    MenuText = "PanelOptimizer"
    ToolTip = "Optimize artistic panels for large format 3D printing"
    Icon = os.path.join(
        os.path.dirname(__file__),
        "Gui",
        "Resources",
        "icons",
        "PanelOptimizer.svg"
    )

    def GetClassName(self):
        return "Gui::PythonWorkbench"

    def Initialize(self):
        """
        Called once when the workbench is loaded.
        """

        import PanelOptimizer.Commands.AnalyzeCommand
        import PanelOptimizer.Commands.SplitPanelCommand

        self.command_list = [
            "PanelOptimizer_Analyze",
            "PanelOptimizer_SplitPanel",
        ]

        self.appendToolbar(
            "PanelOptimizer",
            self.command_list
        )

        self.appendMenu(
            "PanelOptimizer",
            self.command_list
        )

        FreeCAD.Console.PrintMessage(
            "\n"
            "=========================================\n"
            " PanelOptimizer Workbench V3.01 loaded\n"
            "=========================================\n"
        )

    def Activated(self):
        FreeCAD.Console.PrintMessage(
            "PanelOptimizer activated.\n"
        )

    def Deactivated(self):
        FreeCAD.Console.PrintMessage(
            "PanelOptimizer deactivated.\n"
        )

    def ContextMenu(self, recipient):
        self.appendContextMenu(
            "PanelOptimizer",
            self.command_list
        )


FreeCADGui.addWorkbench(PanelOptimizerWorkbench())
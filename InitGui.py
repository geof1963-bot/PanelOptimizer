# -*- coding: utf-8 -*-
"""
PanelOptimizer Workbench
InitGui.py

Compatible FreeCAD 1.1.x
"""

import os
import FreeCAD
import FreeCADGui


MODULE_DIRECTORY = os.path.abspath(
    os.path.join(
        FreeCAD.getUserAppDataDir(),
        "Mod",
        "PanelOptimizer",
    )
)
ICON_DIRECTORY = os.path.join(
    MODULE_DIRECTORY,
    "Gui",
    "Resources",
    "icons",
)
WORKBENCH_ICON = os.path.join(ICON_DIRECTORY, "PanelOptimizer.svg")


class PanelOptimizerWorkbench(Workbench):
    """
    PanelOptimizer FreeCAD Workbench
    """

    MenuText = "PanelOptimizer"
    ToolTip = "Optimize artistic panels for large format 3D printing"

    def GetClassName(self):
        return "Gui::PythonWorkbench"

    def Initialize(self):
        """
        Called once when the workbench is loaded.
        """

        import Commands.AnalyzeCommand
        import Commands.GeometryDiagnosticCommand
        import Commands.SplitPanelCommand

        self.command_list = [
            "PanelOptimizer_Analyze",
            "PanelOptimizer_DiagnoseGeometry",
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
            " PanelOptimizer Workbench V4.00 loaded\n"
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


PanelOptimizerWorkbench.Icon = WORKBENCH_ICON
FreeCADGui.addWorkbench(PanelOptimizerWorkbench())

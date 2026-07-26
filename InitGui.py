# -*- coding: utf-8 -*-
"""
PanelOptimizer Workbench
InitGui.py

Compatible FreeCAD 1.1.x
"""

import os
import FreeCAD
import FreeCADGui


def _module_directory():
    """Return this user-installed workbench directory without ``__file__``.

    FreeCAD may execute ``InitGui.py`` as an initialization script rather than
    import it as a normal Python module.  In that execution mode ``__file__``
    is not guaranteed to exist.  The user application directory is a stable
    FreeCAD API boundary and locates the current ``Mod/PanelOptimizer``
    installation without embedding an operating-system user path.
    """
    return os.path.abspath(
        os.path.join(
            FreeCAD.getUserAppDataDir(),
            "Mod",
            "PanelOptimizer",
        )
    )


MODULE_DIRECTORY = _module_directory()


class PanelOptimizerWorkbench(Workbench):
    """
    PanelOptimizer FreeCAD Workbench
    """

    MenuText = "PanelOptimizer"
    ToolTip = "Optimize artistic panels for large format 3D printing"
    Icon = os.path.join(
        MODULE_DIRECTORY,
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

        import Commands.AnalyzeCommand
        import Commands.SplitPanelCommand

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


FreeCADGui.addWorkbench(PanelOptimizerWorkbench())

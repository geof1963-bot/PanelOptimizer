# ***************************************************************************
# *                                                                         *
# *  PanelOptimizer Workbench                                               *
# *  Version : V0.40B                                                       *
# *                                                                         *
# *  FreeCAD 1.1                                                            *
# *                                                                         *
# ***************************************************************************

import FreeCAD
import FreeCADGui


class PanelOptimizerWorkbench(FreeCADGui.Workbench):

    MenuText = "Panel Optimizer"

    ToolTip = (
        "Optimize artistic panels for invisible assembly "
        "and 3D printing."
    )

    Icon = ""

    ########################################################################
    # Initialize
    ########################################################################

    def Initialize(self):

        # ---------------------------------------------------------------
        # Import commands
        # ---------------------------------------------------------------

        from Commands.AnalyzeCommand import AnalyzeCommand

        FreeCADGui.addCommand(
            "PanelOptimizer_Analyze",
            AnalyzeCommand()
        )

        # ---------------------------------------------------------------
        # Toolbars
        # ---------------------------------------------------------------

        self.appendToolbar(
            "Panel Optimizer",
            [
                "PanelOptimizer_Analyze",
            ]
        )

        # ---------------------------------------------------------------
        # Menus
        # ---------------------------------------------------------------

        self.appendMenu(
            "Panel Optimizer",
            [
                "PanelOptimizer_Analyze",
            ]
        )

        FreeCAD.Console.PrintMessage(
            "\n"
            "=========================================\n"
            " PanelOptimizer Workbench V0.40B\n"
            " FreeCAD 1.1\n"
            "=========================================\n"
        )

    ########################################################################
    # Activated
    ########################################################################

    def Activated(self):

        FreeCAD.Console.PrintMessage(
            "PanelOptimizer activated.\n"
        )

    ########################################################################
    # Deactivated
    ########################################################################

    def Deactivated(self):

        FreeCAD.Console.PrintMessage(
            "PanelOptimizer deactivated.\n"
        )

    ########################################################################
    # Context Menu
    ########################################################################

    def ContextMenu(self, recipient):

        self.appendContextMenu(
            "Panel Optimizer",
            [
                "PanelOptimizer_Analyze",
            ]
        )

    ########################################################################
    # Class Name
    ########################################################################

    def GetClassName(self):

        return "Gui::PythonWorkbench"


FreeCADGui.addWorkbench(PanelOptimizerWorkbench())
import FreeCADGui as Gui

import Commands.AnalyzeCommand


class PanelOptimizerWorkbench(Gui.Workbench):

    MenuText = "PanelOptimizer"
    ToolTip = "3D Panel Optimization for FDM Printing"

    Icon = ""

    def Initialize(self):

        self.appendToolbar(
            "PanelOptimizer",
            ["PanelOptimizer_Analyze"]
        )

        self.appendMenu(
            "PanelOptimizer",
            ["PanelOptimizer_Analyze"]
        )

        print("PanelOptimizer initialized")

    def Activated(self):
        pass

    def Deactivated(self):
        pass


Gui.addWorkbench(PanelOptimizerWorkbench())
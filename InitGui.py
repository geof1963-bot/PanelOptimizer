import FreeCADGui as Gui

import Commands.AnalyzeCommand


class PanelOptimizerWorkbench(Gui.Workbench):

    MenuText = "PanelOptimizer"
    ToolTip = "Prepare large artistic panels for FDM printing"

    Icon = ""

    Toolbox = [
        "PanelOptimizer_Analyze",
    ]

    MenuItems = [
        "PanelOptimizer_Analyze",
    ]

    def Initialize(self):

        self.appendToolbar(
            "PanelOptimizer",
            self.Toolbox
        )

        self.appendMenu(
            "PanelOptimizer",
            self.MenuItems
        )

        Gui.addLanguagePath("")

        print("PanelOptimizer Workbench initialized")

    def Activated(self):
        print("PanelOptimizer activated")

    def Deactivated(self):
        print("PanelOptimizer deactivated")


Gui.addWorkbench(PanelOptimizerWorkbench())
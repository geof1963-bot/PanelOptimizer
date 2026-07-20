# ***************************************************************************
# *                                                                         *
# *  PanelOptimizer                                                         *
# *                                                                         *
# *  AnalyzeCommand.py                                                      *
# *                                                                         *
# *  Version : V0.40B                                                       *
# *                                                                         *
# ***************************************************************************

import FreeCAD
import FreeCADGui

from Analyzer.PanelAnalyzer import PanelAnalyzer


class AnalyzeCommand:

    def GetResources(self):

        return {
            "Pixmap": "",
            "MenuText": "Analyze Panel",
            "ToolTip": (
                "Analyze the selected panel and build the complete "
                "geometrical analysis."
            )
        }

    # ------------------------------------------------------------------

    def IsActive(self):

        if FreeCAD.ActiveDocument is None:
            return False

        if len(FreeCADGui.Selection.getSelection()) != 1:
            return False

        return True

    # ------------------------------------------------------------------

    def Activated(self):

        FreeCAD.Console.PrintMessage("\n")
        FreeCAD.Console.PrintMessage(
            "=============================================\n"
        )
        FreeCAD.Console.PrintMessage(
            " PANEL OPTIMIZER - ANALYZE\n"
        )
        FreeCAD.Console.PrintMessage(
            "=============================================\n"
        )

        selection = FreeCADGui.Selection.getSelection()

        if len(selection) != 1:

            FreeCAD.Console.PrintError(
                "Please select one solid.\n"
            )
            return

        obj = selection[0]

        if not hasattr(obj, "Shape"):

            FreeCAD.Console.PrintError(
                "Selected object has no Shape.\n"
            )
            return

        shape = obj.Shape

        if shape.isNull():

            FreeCAD.Console.PrintError(
                "Shape is empty.\n"
            )
            return

        FreeCAD.Console.PrintMessage(
            f"Object : {obj.Label}\n"
        )

        bbox = shape.BoundBox

        FreeCAD.Console.PrintMessage(
            f"Bounding Box : "
            f"{bbox.XLength:.2f} x "
            f"{bbox.YLength:.2f} x "
            f"{bbox.ZLength:.2f} mm\n"
        )

        if bbox.XLength > 330.0 or bbox.YLength > 330.0:

            FreeCAD.Console.PrintWarning(
                "\n"
                "WARNING :\n"
                "This object cannot be printed in one piece.\n"
                "Optimization will search a valid split.\n\n"
            )

        analyzer = PanelAnalyzer(shape)

        result = analyzer.run()

        FreeCAD.Console.PrintMessage("\n")
        FreeCAD.Console.PrintMessage(
            "Analysis completed.\n"
        )

        if result is not None:

            if hasattr(result, "printSummary"):
                result.printSummary()

        FreeCAD.Console.PrintMessage(
            "=============================================\n"
        )

    # ------------------------------------------------------------------

    def GetClassName(self):

        return "Gui::PythonCommand"
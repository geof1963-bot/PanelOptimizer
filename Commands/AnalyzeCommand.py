import FreeCAD as App
import FreeCADGui as Gui
from Core.Analyzer import Analyzer

class AnalyzeCommand:
    def GetResources(self):
        return {"Pixmap":"","MenuText":"Analyze","ToolTip":"Analyze selected object"}

    def Activated(self):
        selection = Gui.Selection.getSelection()
        if not selection:
            App.Console.PrintError("No object selected.\n")
            return
        result = Analyzer().analyze(selection[0])
        bb = result.bounding_box

        App.Console.PrintMessage("\n=====================================\n")
        App.Console.PrintMessage(" PANEL OPTIMIZER V0.07\n")
        App.Console.PrintMessage("=====================================\n")
        App.Console.PrintMessage(f"Object   : {result.object_name}\n")
        App.Console.PrintMessage(f"Faces    : {result.face_count}\n")
        App.Console.PrintMessage(f"Edges    : {result.edge_count}\n")
        App.Console.PrintMessage(f"Vertices : {result.vertex_count}\n")
        App.Console.PrintMessage(f"BBox     : {bb.XLength:.2f} x {bb.YLength:.2f} x {bb.ZLength:.2f} mm\n")
        App.Console.PrintMessage(f"Volume   : {result.volume:.2f} mm³\n")
        App.Console.PrintMessage(f"Surface  : {result.area:.2f} mm²\n\n")
        App.Console.PrintMessage("Faces\n--------------------------\n")
        for face in result.faces:
            App.Console.PrintMessage(
                f"Face {face.index:4d} : {face.type:12s} "
                f"A={face.area:10.2f} "
                f"N=({face.normal_x:5.2f},{face.normal_y:5.2f},{face.normal_z:5.2f})\n")

    def IsActive(self):
        return App.ActiveDocument is not None

Gui.addCommand("PanelOptimizer_Analyze", AnalyzeCommand())

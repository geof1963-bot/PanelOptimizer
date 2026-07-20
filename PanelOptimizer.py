# ***************************************************************************
# *                                                                         *
# *  PanelOptimizer                                                         *
# *                                                                         *
# *  FreeCAD Workbench                                                      *
# *                                                                         *
# *  Version : V0.40B                                                       *
# *                                                                         *
# ***************************************************************************

"""
PanelOptimizer

Workbench FreeCAD destiné à préparer automatiquement
des panneaux artistiques pour l'impression 3D FDM.

Le Workbench ne cherche pas uniquement à découper un panneau.

Il optimise le panneau terminé afin de produire
quatre pièces imprimables dont les joints deviendront
quasi invisibles après :

    - collage
    - mastiquage
    - ponçage
    - peinture

Architecture :

Analyzer
Geometry
CutPlanner
Splitter
Joinery
Exporter
Settings
Utils
"""

import FreeCAD

# -------------------------------------------------------------------------
# Informations générales
# -------------------------------------------------------------------------

WORKBENCH_NAME = "PanelOptimizer"

VERSION_MAJOR = 0
VERSION_MINOR = 40
VERSION_PATCH = "B"

VERSION = f"{VERSION_MAJOR}.{VERSION_MINOR:02d}{VERSION_PATCH}"

AUTHOR = "Geoffroy / OpenAI"

DESCRIPTION = (
    "Invisible panel optimizer for FreeCAD."
)

# -------------------------------------------------------------------------
# Contraintes physiques
# -------------------------------------------------------------------------

FINAL_PANEL_WIDTH = 594.0
FINAL_PANEL_HEIGHT = 594.0
FINAL_PANEL_THICKNESS = 8.0

MAX_PRINT_WIDTH = 330.0
MAX_PRINT_HEIGHT = 330.0

DOWEL_DIAMETER = 4.0
DOWEL_HOLE_DIAMETER = 4.3
MAX_DOWEL_LENGTH = 30.0

# -------------------------------------------------------------------------
# Console
# -------------------------------------------------------------------------

def print_banner():

    FreeCAD.Console.PrintMessage("\n")
    FreeCAD.Console.PrintMessage("=========================================\n")
    FreeCAD.Console.PrintMessage("        PANEL OPTIMIZER\n")
    FreeCAD.Console.PrintMessage("=========================================\n")
    FreeCAD.Console.PrintMessage(f"Version : {VERSION}\n")
    FreeCAD.Console.PrintMessage("FreeCAD Workbench\n")
    FreeCAD.Console.PrintMessage("=========================================\n")
    FreeCAD.Console.PrintMessage("\n")


def print_project_constraints():

    FreeCAD.Console.PrintMessage(
        "Final panel : "
        f"{FINAL_PANEL_WIDTH:.0f} x "
        f"{FINAL_PANEL_HEIGHT:.0f} x "
        f"{FINAL_PANEL_THICKNESS:.0f} mm\n"
    )

    FreeCAD.Console.PrintMessage(
        "Maximum printable part : "
        f"{MAX_PRINT_WIDTH:.0f} x "
        f"{MAX_PRINT_HEIGHT:.0f} mm\n"
    )

    FreeCAD.Console.PrintMessage(
        f"Dowel diameter : {DOWEL_DIAMETER:.1f} mm\n"
    )

    FreeCAD.Console.PrintMessage(
        f"Hole diameter : {DOWEL_HOLE_DIAMETER:.1f} mm\n"
    )

    FreeCAD.Console.PrintMessage(
        f"Maximum dowel length : {MAX_DOWEL_LENGTH:.0f} mm\n"
    )

    FreeCAD.Console.PrintMessage("\n")


# -------------------------------------------------------------------------
# Vérification FreeCAD
# -------------------------------------------------------------------------

def check_environment():

    try:
        version = FreeCAD.Version()

        major = version[0]
        minor = version[1]

        FreeCAD.Console.PrintMessage(
            f"Running on FreeCAD {major}.{minor}\n"
        )

        return True

    except Exception:

        FreeCAD.Console.PrintWarning(
            "Unable to determine FreeCAD version.\n"
        )

        return False


# -------------------------------------------------------------------------
# Initialisation
# -------------------------------------------------------------------------

def initialize():

    print_banner()

    check_environment()

    print_project_constraints()


# -------------------------------------------------------------------------
# Lancement
# -------------------------------------------------------------------------

initialize()
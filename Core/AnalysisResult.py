# -*- coding: utf-8 -*-

class AnalysisResult:

    def __init__(self):

        # ==========================================================
        # General
        # ==========================================================

        self.object_name = ""

        # ==========================================================
        # Geometry
        # ==========================================================

        self.face_count = 0
        self.edge_count = 0
        self.vertex_count = 0

        self.area = 0.0
        self.volume = 0.0

        # ==========================================================
        # Bounding Box
        # ==========================================================

        self.bounding_box = None

        self.size_x = 0.0
        self.size_y = 0.0
        self.size_z = 0.0

        self.x_min = 0.0
        self.x_max = 0.0

        self.y_min = 0.0
        self.y_max = 0.0

        self.z_min = 0.0
        self.z_max = 0.0

        # ==========================================================
        # Printing constraints
        # ==========================================================

        self.max_print_size = 330.0

        self.printable = False

        # ==========================================================
        # Face collections
        # ==========================================================

        self.faces = []

        self.planar_faces = []
        self.cylindrical_faces = []
        self.bspline_faces = []

        # ==========================================================
        # Statistics
        # ==========================================================

        self.planar_face_count = 0
        self.cylindrical_face_count = 0
        self.bspline_face_count = 0

        # ==========================================================
        # Future modules
        # ==========================================================

        self.holes = []

        self.open_contours = []

        self.islands = []

        self.corridors = []

        self.thin_areas = []

        self.cost_map = None

        self.candidate_paths = []

        self.best_paths = []

    # ==============================================================
    # Console summary
    # ==============================================================

    def printSummary(self):

        print("")
        print("========================================")
        print(" PANEL ANALYSIS")
        print("========================================")

        print(f"Object               : {self.object_name}")

        print("")

        print("Dimensions")
        print("----------------------------------------")
        print(f"X                    : {self.size_x:.2f} mm")
        print(f"Y                    : {self.size_y:.2f} mm")
        print(f"Z                    : {self.size_z:.2f} mm")

        print("")

        print("Geometry")
        print("----------------------------------------")
        print(f"Faces                : {self.face_count}")
        print(f"Edges                : {self.edge_count}")
        print(f"Vertices             : {self.vertex_count}")

        print("")

        print("Surface              : %.2f mm²" % self.area)
        print("Volume               : %.2f mm³" % self.volume)

        print("")

        print("Classification")
        print("----------------------------------------")
        print(f"Planar               : {self.planar_face_count}")
        print(f"Cylindrical          : {self.cylindrical_face_count}")
        print(f"BSpline              : {self.bspline_face_count}")

        print("")

        print("Printing")
        print("----------------------------------------")

        if self.printable:
            print("Status               : Printable")
        else:
            print("Status               : Split required")

        print("Maximum size         : %.0f mm" % self.max_print_size)

        print("========================================")
        print("")
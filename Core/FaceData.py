# -*- coding: utf-8 -*-

class FaceData:

    def __init__(self):

        # Identification
        self.index = -1
        self.type = ""

        # Geometry
        self.surface = None
        self.area = 0.0
        self.center = None
        self.normal = None

        self.normal_x = 0.0
        self.normal_y = 0.0
        self.normal_z = 0.0

        self.bounding_box = None

        # Topology
        self.edges = []
        self.vertices = []
        self.neighbours = []

        # Classification
        self.is_planar = False
        self.is_cylindrical = False
        self.is_conical = False
        self.is_spherical = False
        self.is_bspline = False

        self.is_horizontal = False
        self.is_vertical = False

        self.is_outer = False
        self.is_inner = False

        self.is_hole = False
        self.is_island = False

        self.is_printable = True
        self.is_cut_candidate = False

        # Future optimisation
        self.group = -1
        self.tag = ""
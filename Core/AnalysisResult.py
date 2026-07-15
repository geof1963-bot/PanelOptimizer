# -*- coding: utf-8 -*-

class AnalysisResult:

    def __init__(self):

        # Object information
        self.object_name = ""

        # Global statistics
        self.face_count = 0
        self.edge_count = 0
        self.vertex_count = 0

        self.volume = 0.0
        self.area = 0.0

        self.bounding_box = None

        # Geometry
        self.faces = []

        # Future topology
        self.outer_faces = []
        self.inner_faces = []

        self.planar_faces = []
        self.cylindrical_faces = []
        self.bspline_faces = []

        self.holes = []
        self.islands = []

        # Split planning
        self.cut_candidates = []
        self.cut_paths = []

        # Output
        self.blocks = []
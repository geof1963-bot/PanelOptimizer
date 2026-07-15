# -*- coding: utf-8 -*-

class AnalysisResult:
    def __init__(self):
        self.object_name = ""
        self.face_count = 0
        self.edge_count = 0
        self.vertex_count = 0
        self.volume = 0.0
        self.area = 0.0
        self.bounding_box = None
        self.faces = []

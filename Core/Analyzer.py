# -*- coding: utf-8 -*-

from Core.AnalysisResult import AnalysisResult
from Core.FaceData import FaceData

class Analyzer:
    def analyze(self, obj):
        shape = obj.Shape
        result = AnalysisResult()
        result.object_name = obj.Label
        result.face_count = len(shape.Faces)
        result.edge_count = len(shape.Edges)
        result.vertex_count = len(shape.Vertexes)
        result.volume = shape.Volume
        result.area = shape.Area
        result.bounding_box = shape.BoundBox

        for index, face in enumerate(shape.Faces):
            fd = FaceData()
            fd.index = index
            fd.type = face.Surface.__class__.__name__
            fd.area = face.Area
            fd.surface = face.Surface
            try:
                u0,u1,v0,v1 = face.ParameterRange
                u=(u0+u1)/2
                v=(v0+v1)/2
                fd.center = face.valueAt(u,v)
                fd.normal = face.normalAt(u,v)
                fd.normal_x = fd.normal.x
                fd.normal_y = fd.normal.y
                fd.normal_z = fd.normal.z
            except Exception:
                pass
            result.faces.append(fd)
        return result

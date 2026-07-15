# -*- coding: utf-8 -*-

from Core.AnalysisResult import AnalysisResult
from Core.FaceData import FaceData
from Core.GeometryClassifier import GeometryClassifier


class Analyzer:

    def __init__(self):

        self.classifier = GeometryClassifier()

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
            fd.area = face.Area
            fd.surface = face.Surface

            try:

                u0, u1, v0, v1 = face.ParameterRange

                u = (u0 + u1) / 2
                v = (v0 + v1) / 2

                fd.center = face.valueAt(u, v)
                fd.normal = face.normalAt(u, v)

                fd.normal_x = fd.normal.x
                fd.normal_y = fd.normal.y
                fd.normal_z = fd.normal.z

            except Exception:
                pass

            # Classification géométrique
            self.classifier.classify(face, fd)

            result.faces.append(fd)

            if fd.is_planar:
                result.planar_faces.append(fd)

            if fd.is_cylindrical:
                result.cylindrical_faces.append(fd)

            if fd.is_bspline:
                result.bspline_faces.append(fd)

        return result
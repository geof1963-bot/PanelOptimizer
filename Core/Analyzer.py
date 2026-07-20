# -*- coding: utf-8 -*-

from Core.AnalysisResult import AnalysisResult
from Core.FaceData import FaceData
from Core.GeometryClassifier import GeometryClassifier


class Analyzer:

    def __init__(self):

        self.classifier = GeometryClassifier()

    # ------------------------------------------------------------------
    # Main analysis
    # ------------------------------------------------------------------

    def analyze(self, obj):

        shape = obj.Shape
        bbox = shape.BoundBox

        result = AnalysisResult()

        # --------------------------------------------------------------
        # General object information
        # --------------------------------------------------------------

        result.object_name = obj.Label

        result.face_count = len(shape.Faces)
        result.edge_count = len(shape.Edges)
        result.vertex_count = len(shape.Vertexes)

        result.volume = shape.Volume
        result.area = shape.Area

        result.bounding_box = bbox

        # --------------------------------------------------------------
        # Bounding box dimensions
        # --------------------------------------------------------------

        result.size_x = bbox.XLength
        result.size_y = bbox.YLength
        result.size_z = bbox.ZLength

        result.x_min = bbox.XMin
        result.x_max = bbox.XMax

        result.y_min = bbox.YMin
        result.y_max = bbox.YMax

        result.z_min = bbox.ZMin
        result.z_max = bbox.ZMax

        # --------------------------------------------------------------
        # Printing constraints
        # --------------------------------------------------------------

        result.max_print_size = 330.0

        result.printable = (
            result.size_x <= result.max_print_size
            and
            result.size_y <= result.max_print_size
        )

        # --------------------------------------------------------------
        # Faces
        # --------------------------------------------------------------

        for index, face in enumerate(shape.Faces):

            fd = FaceData()

            fd.index = index
            fd.area = face.Area
            fd.surface = face.Surface

            try:

                u0, u1, v0, v1 = face.ParameterRange

                u = (u0 + u1) / 2.0
                v = (v0 + v1) / 2.0

                fd.center = face.valueAt(u, v)
                fd.normal = face.normalAt(u, v)

                fd.normal_x = fd.normal.x
                fd.normal_y = fd.normal.y
                fd.normal_z = fd.normal.z

            except Exception:
                pass

            self.classifier.classify(face, fd)

            result.faces.append(fd)

            if fd.is_planar:
                result.planar_faces.append(fd)

            if fd.is_cylindrical:
                result.cylindrical_faces.append(fd)

            if fd.is_bspline:
                result.bspline_faces.append(fd)

        # --------------------------------------------------------------
        # Statistics
        # --------------------------------------------------------------

        result.planar_face_count = len(result.planar_faces)
        result.cylindrical_face_count = len(result.cylindrical_faces)
        result.bspline_face_count = len(result.bspline_faces)

        return result
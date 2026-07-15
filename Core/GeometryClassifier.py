# -*- coding: utf-8 -*-

class GeometryClassifier:
    """
    Analyse une face FreeCAD et complète les propriétés
    géométriques de FaceData.
    """

    def classify(self, face, face_data):

        surface_name = face.Surface.__class__.__name__

        face_data.type = surface_name

        # -------------------------------------------------
        # Surface type
        # -------------------------------------------------

        face_data.is_planar = (surface_name == "Plane")
        face_data.is_cylindrical = (surface_name == "Cylinder")
        face_data.is_conical = (surface_name == "Cone")
        face_data.is_spherical = (surface_name == "Sphere")
        face_data.is_bspline = ("BSpline" in surface_name)

        # -------------------------------------------------
        # Bounding box
        # -------------------------------------------------

        face_data.bounding_box = face.BoundBox

        # -------------------------------------------------
        # Orientation
        # -------------------------------------------------

        try:

            nx = abs(face_data.normal_x)
            ny = abs(face_data.normal_y)
            nz = abs(face_data.normal_z)

            tolerance = 0.90

            face_data.is_horizontal = (nz > tolerance)

            face_data.is_vertical = (
                nx > tolerance or
                ny > tolerance
            )

        except Exception:

            pass

        return face_data
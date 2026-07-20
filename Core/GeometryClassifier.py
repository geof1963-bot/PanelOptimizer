# -*- coding: utf-8 -*-

class GeometryClassifier:
    """
    Analyse une face FreeCAD et complète les propriétés
    géométriques de FaceData.
    """

    def classify(self, face, face_data):

        surface = face.Surface
        surface_name = surface.__class__.__name__

        face_data.type = surface_name

        # -------------------------------------------------
        # Surface type
        # -------------------------------------------------

        face_data.is_planar = (surface_name == "Plane")
        face_data.is_cylindrical = (surface_name == "Cylinder")
        face_data.is_conical = (surface_name == "Cone")
        face_data.is_spherical = (surface_name == "Sphere")
        face_data.is_toroidal = (surface_name == "Toroid")
        face_data.is_revolution = ("SurfaceOfRevolution" in surface_name)
        face_data.is_offset = ("Offset" in surface_name)
        face_data.is_bspline = ("BSpline" in surface_name)

        # -------------------------------------------------
        # Bounding Box
        # -------------------------------------------------

        face_data.bounding_box = face.BoundBox

        # -------------------------------------------------
        # Surface properties
        # -------------------------------------------------

        try:
            face_data.area = face.Area
        except Exception:
            face_data.area = 0.0

        try:
            face_data.center = face.CenterOfMass
        except Exception:
            face_data.center = None

        # -------------------------------------------------
        # Orientation
        # -------------------------------------------------

        face_data.is_horizontal = False
        face_data.is_vertical = False
        face_data.is_inclined = False

        try:

            nx = abs(face_data.normal_x)
            ny = abs(face_data.normal_y)
            nz = abs(face_data.normal_z)

            tolerance = 0.90

            if nz >= tolerance:
                face_data.is_horizontal = True

            elif nx >= tolerance or ny >= tolerance:
                face_data.is_vertical = True

            else:
                face_data.is_inclined = True

        except Exception:
            pass

        # -------------------------------------------------
        # Circular edges
        # -------------------------------------------------

        face_data.circular_edge_count = 0

        try:

            for edge in face.Edges:

                curve_name = edge.Curve.__class__.__name__

                if curve_name in ("Circle", "ArcOfCircle"):
                    face_data.circular_edge_count += 1

        except Exception:
            pass

        # -------------------------------------------------
        # Simple complexity indicator
        # -------------------------------------------------

        try:

            edge_count = len(face.Edges)

            if edge_count <= 4:
                face_data.complexity = "LOW"

            elif edge_count <= 12:
                face_data.complexity = "MEDIUM"

            else:
                face_data.complexity = "HIGH"

        except Exception:

            face_data.complexity = "UNKNOWN"

        return face_data
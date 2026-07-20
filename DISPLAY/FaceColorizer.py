# -*- coding: utf-8 -*-

import FreeCADGui as Gui


class FaceColorizer:

    COLORS = {
        "Plane":      (0.0, 1.0, 0.0),
        "Cylinder":   (0.0, 0.4, 1.0),
        "Cone":       (1.0, 0.0, 0.0),
        "Sphere":     (1.0, 0.0, 1.0),
        "BSpline":    (1.0, 1.0, 0.0)
    }

    DEFAULT = (0.75, 0.75, 0.75)

    def colorize(self, obj, result):

        view = obj.ViewObject

        colors = []

        for face in result.faces:

            colors.append(
                self.COLORS.get(face.type, self.DEFAULT)
            )

        view.DiffuseColor = colors
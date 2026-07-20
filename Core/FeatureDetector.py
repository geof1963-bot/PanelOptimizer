# -*- coding: utf-8 -*-

class FeatureDetector:
    """
    Détecte les éléments géométriques remarquables
    du panneau.

    Ce module ne prend aucune décision.

    Il construit uniquement une description
    géométrique du panneau qui sera exploitée
    ensuite par CostMap et Optimizer.
    """

    def __init__(self):

        pass

    # ---------------------------------------------------------

    def detect(self, panel):

        self.detectBorders(panel)
        self.detectLargeFaces(panel)
        self.detectCircularFeatures(panel)

        return panel

    # ---------------------------------------------------------

    def detectBorders(self, panel):

        panel.borders = []

        bbox = panel.bounding_box

        panel.borders.append(("LEFT", bbox.XMin))
        panel.borders.append(("RIGHT", bbox.XMax))
        panel.borders.append(("BOTTOM", bbox.YMin))
        panel.borders.append(("TOP", bbox.YMax))

    # ---------------------------------------------------------

    def detectLargeFaces(self, panel):

        panel.large_faces = []

        for face in panel.faces:

            if face.area > 5000:

                panel.large_faces.append(face)

    # ---------------------------------------------------------

    def detectCircularFeatures(self, panel):

        panel.circular_features = []

        for face in panel.faces:

            if getattr(face, "circular_edge_count", 0) > 0:

                panel.circular_features.append(face)
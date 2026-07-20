# -*- coding: utf-8 -*-

class PanelData:
    """
    Représentation complète d'un panneau artistique.

    Cette classe constitue le modèle central utilisé par
    tous les modules du Workbench.

    Elle ne dépend pas directement des algorithmes
    d'analyse ou de découpe.
    """

    def __init__(self):

        # =====================================================
        # Source
        # =====================================================

        self.object = None
        self.shape = None
        self.label = ""

        # =====================================================
        # Bounding Box
        # =====================================================

        self.bounding_box = None

        self.width = 0.0
        self.height = 0.0
        self.thickness = 0.0

        # =====================================================
        # Geometry
        # =====================================================

        self.faces = []
        self.edges = []
        self.vertices = []

        # =====================================================
        # Detected objects
        # =====================================================

        self.holes = []
        self.open_contours = []

        self.islands = []
        self.corridors = []

        self.thin_areas = []

        # =====================================================
        # Printing constraints
        # =====================================================

        self.max_part_size = 330.0

        self.printable = False

        # =====================================================
        # Optimization
        # =====================================================

        self.cost_map = None

        self.candidate_paths = []

        self.best_solution = None

        # =====================================================
        # Splitter
        # =====================================================

        self.parts = []

        # =====================================================
        # Joinery
        # =====================================================

        self.joints = []

        self.dowels = []

        self.grooves = []

        self.chamfers = []

        self.lips = []

        # =====================================================
        # Export
        # =====================================================

        self.exported_files = []

    # =========================================================

    def setShape(self, obj):

        self.object = obj
        self.shape = obj.Shape
        self.label = obj.Label

        bbox = self.shape.BoundBox

        self.bounding_box = bbox

        self.width = bbox.XLength
        self.height = bbox.YLength
        self.thickness = bbox.ZLength

        self.printable = (
            self.width <= self.max_part_size
            and
            self.height <= self.max_part_size
        )
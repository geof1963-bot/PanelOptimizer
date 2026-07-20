# -*- coding: utf-8 -*-

class CostMap:
    """
    CostMap

    Représente une carte de coût géométrique du panneau.

    Chaque cellule reçoit un coût qui sera utilisé
    ultérieurement par le moteur d'optimisation afin de
    rechercher les trajectoires de découpe les plus
    discrètes.
    """

    def __init__(self):

        self.width = 0
        self.height = 0

        self.cell_size = 5.0  # mm

        self.grid = []

    # ---------------------------------------------------------

    def initialize(self, panel):

        self.width = int(panel.width / self.cell_size) + 1
        self.height = int(panel.height / self.cell_size) + 1

        self.grid = [
            [1.0 for x in range(self.width)]
            for y in range(self.height)
        ]

    # ---------------------------------------------------------

    def addPenaltyCircle(self, x, y, radius, value):

        radius2 = radius * radius

        for j in range(self.height):

            py = j * self.cell_size

            for i in range(self.width):

                px = i * self.cell_size

                dx = px - x
                dy = py - y

                if dx * dx + dy * dy <= radius2:

                    self.grid[j][i] += value

    # ---------------------------------------------------------

    def addBonusCircle(self, x, y, radius, value):

        radius2 = radius * radius

        for j in range(self.height):

            py = j * self.cell_size

            for i in range(self.width):

                px = i * self.cell_size

                dx = px - x
                dy = py - y

                if dx * dx + dy * dy <= radius2:

                    self.grid[j][i] -= value

                    if self.grid[j][i] < 0.0:
                        self.grid[j][i] = 0.0

    # ---------------------------------------------------------

    def getCost(self, x, y):

        ix = int(x / self.cell_size)
        iy = int(y / self.cell_size)

        if (
            ix < 0
            or iy < 0
            or ix >= self.width
            or iy >= self.height
        ):
            return 999999.0

        return self.grid[iy][ix]
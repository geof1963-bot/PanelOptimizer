# -*- coding: utf-8 -*-

from dataclasses import dataclass, field
from math import sqrt


# ==========================================================
# NODE
# ==========================================================

@dataclass
class GraphNode:

    id: int

    x: float

    y: float

    z: float = 0.0

    kind: str = "UNKNOWN"

    weight: float = 1.0

    data: dict = field(default_factory=dict)


# ==========================================================
# EDGE
# ==========================================================

@dataclass
class GraphEdge:

    start: int

    end: int

    distance: float

    cost: float

    data: dict = field(default_factory=dict)


# ==========================================================
# GRAPH BUILDER
# ==========================================================

class GraphBuilder:

    """
    Construction du graphe géométrique.

    Aucune optimisation n'est effectuée ici.

    Le rôle est uniquement de transformer
    le panneau en réseau de noeuds.
    """

    def __init__(self):

        self.nodes = []

        self.edges = []

    # -----------------------------------------------------

    def build(self, panel):

        self.nodes.clear()
        self.edges.clear()

        self._addBorderNodes(panel)

        self._addHoleNodes(panel)

        self._connectNearestNodes()

        return self

    # -----------------------------------------------------

    def _addBorderNodes(self, panel):

        bbox = panel.bounding_box

        self.addNode(
            bbox.XMin,
            (bbox.YMin + bbox.YMax) / 2,
            "LEFT_BORDER"
        )

        self.addNode(
            bbox.XMax,
            (bbox.YMin + bbox.YMax) / 2,
            "RIGHT_BORDER"
        )

        self.addNode(
            (bbox.XMin + bbox.XMax) / 2,
            bbox.YMin,
            "BOTTOM_BORDER"
        )

        self.addNode(
            (bbox.XMin + bbox.XMax) / 2,
            bbox.YMax,
            "TOP_BORDER"
        )

    # -----------------------------------------------------

    def _addHoleNodes(self, panel):

        for hole in getattr(panel, "holes", []):

            self.addNode(

                hole.center.x,

                hole.center.y,

                "HOLE"

            )

    # -----------------------------------------------------

    def addNode(self, x, y, kind):

        node = GraphNode(

            id=len(self.nodes),

            x=x,

            y=y,

            kind=kind

        )

        self.nodes.append(node)

    # -----------------------------------------------------

    def _connectNearestNodes(self):

        count = len(self.nodes)

        for i in range(count):

            nodeA = self.nodes[i]

            distances = []

            for j in range(count):

                if i == j:
                    continue

                nodeB = self.nodes[j]

                d = sqrt(

                    (nodeA.x - nodeB.x) ** 2 +

                    (nodeA.y - nodeB.y) ** 2

                )

                distances.append(

                    (d, j)

                )

            distances.sort()

            for d, j in distances[:4]:

                self.edges.append(

                    GraphEdge(

                        start=i,

                        end=j,

                        distance=d,

                        cost=d

                    )

                )
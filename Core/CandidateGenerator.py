# -*- coding: utf-8 -*-


# TODO V0.60
# CandidateGenerator utilisera les chemins produits
# par PathFinder pour construire les solutions candidates.

from dataclasses import dataclass


@dataclass
class CandidateCut:

    id: int = 0

    vertical_x: float = 0.0
    horizontal_y: float = 0.0

    part_width_left: float = 0.0
    part_width_right: float = 0.0

    part_height_bottom: float = 0.0
    part_height_top: float = 0.0

    printable: bool = False

    score: float = 0.0

    penalties: dict = None

    metadata: dict = None

    def __post_init__(self):

        if self.penalties is None:
            self.penalties = {}

        if self.metadata is None:
            self.metadata = {}


# ================================================================


class CandidateGenerator:

    """
    Génère des centaines de candidats.

    Aucune optimisation n'est réalisée ici.

    Le rôle est uniquement de produire des solutions
    géométriquement valides.
    """

    def __init__(self):

        self.maximum_part_size = 330.0

        self.step = 5.0

    # ------------------------------------------------------------

    def generate(self, panel):

        candidates = []

        width = panel.width
        height = panel.height

        index = 0

        x = self.maximum_part_size

        while x <= width:

            y = self.maximum_part_size

            while y <= height:

                candidate = CandidateCut()

                candidate.id = index

                candidate.vertical_x = x
                candidate.horizontal_y = y

                candidate.part_width_left = x
                candidate.part_width_right = width - x

                candidate.part_height_bottom = y
                candidate.part_height_top = height - y

                candidate.printable = (

                    candidate.part_width_left <= self.maximum_part_size and
                    candidate.part_width_right <= self.maximum_part_size and
                    candidate.part_height_bottom <= self.maximum_part_size and
                    candidate.part_height_top <= self.maximum_part_size

                )

                if candidate.printable:

                    candidates.append(candidate)

                    index += 1

                y += self.step

            x += self.step

        return candidates
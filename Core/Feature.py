# -*- coding: utf-8 -*-

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ==========================================================
# FEATURE TYPES
# ==========================================================

class FeatureType(Enum):

    UNKNOWN = "UNKNOWN"

    HOLE = "HOLE"

    CHANNEL = "CHANNEL"

    HOLE_WITH_CHANNEL = "HOLE_WITH_CHANNEL"

    ISLAND = "ISLAND"

    BORDER = "BORDER"

    NARROW_ZONE = "NARROW_ZONE"

    THIN_BRIDGE = "THIN_BRIDGE"

    CURVATURE_ZONE = "CURVATURE_ZONE"

    EDGE = "EDGE"

    VERTEX = "VERTEX"


# ==========================================================
# FEATURE
# ==========================================================

@dataclass
class Feature:

    id: int = -1

    type: FeatureType = FeatureType.UNKNOWN

    shape: Any = None

    center: Any = None

    bbox: Any = None

    area: float = 0.0

    perimeter: float = 0.0

    orientation: float = 0.0

    priority: float = 1.0

    cost: float = 1.0

    attributes: dict = field(default_factory=dict)

    neighbours: list = field(default_factory=list)

    metadata: dict = field(default_factory=dict)

    # -----------------------------------------------------

    def addNeighbour(self, feature_id):

        if feature_id not in self.neighbours:

            self.neighbours.append(feature_id)

    # -----------------------------------------------------

    def setAttribute(self, key, value):

        self.attributes[key] = value

    # -----------------------------------------------------

    def getAttribute(self, key, default=None):

        return self.attributes.get(key, default)

    # -----------------------------------------------------

    def isHole(self):

        return self.type in (
            FeatureType.HOLE,
            FeatureType.HOLE_WITH_CHANNEL,
        )

    # -----------------------------------------------------

    def isChannel(self):

        return self.type == FeatureType.CHANNEL

    # -----------------------------------------------------

    def __repr__(self):

        return (
            f"<Feature "
            f"id={self.id} "
            f"type={self.type.value}>"
        )
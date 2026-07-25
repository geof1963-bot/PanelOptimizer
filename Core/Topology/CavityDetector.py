# -*- coding: utf-8 -*-
"""Read-only detection of enclosed cavities."""

from __future__ import annotations

from dataclasses import dataclass

from ..Models import CavityFeature, GeometrySnapshot
from .ConnectivityBuilder import MaterialRegion
from ._Utilities import bounding_box, finite_float, identifier, point, same_shape

__all__ = ["CavityDetector"]


@dataclass(frozen=True, slots=True)
class DetectedCavity:
    """Associate an immutable cavity with its owning material region."""

    feature: CavityFeature
    owner_index: int


class CavityDetector:
    """Detect closed inner shells without interpreting their suitability."""

    def detect(
        self,
        geometry: GeometrySnapshot,
        regions: tuple[MaterialRegion, ...],
    ) -> tuple[DetectedCavity, ...]:
        """Describe every closed, non-outer shell of every solid.

        Open shells are ignored because they do not bound an enclosed volume.
        Signed shell volume is converted to its absolute descriptive value.
        """
        detected: list[DetectedCavity] = []
        for owner_index, region in enumerate(regions):
            if region.node_type != "solid":
                continue

            shells = tuple(getattr(region.shape, "Shells", ()))
            outer_shell = getattr(region.shape, "OuterShell", None)
            for shell_index, shell in enumerate(shells):
                is_outer = (
                    same_shape(shell, outer_shell)
                    if outer_shell is not None
                    else shell_index == 0
                )
                if is_outer:
                    continue

                is_closed = getattr(shell, "isClosed", None)
                if callable(is_closed) and not bool(is_closed()):
                    continue

                feature_index = len(detected) + 1
                detected.append(
                    DetectedCavity(
                        feature=CavityFeature(
                            feature_id=identifier(
                                geometry.source_id,
                                "cavity",
                                feature_index,
                            ),
                            center=point(
                                shell.CenterOfGravity,
                                "cavity center",
                            ),
                            bounding_box=bounding_box(shell),
                            volume_mm3=abs(
                                finite_float(
                                    getattr(shell, "Volume", 0.0),
                                    "cavity volume",
                                )
                            ),
                            opening_feature_ids=(),
                        ),
                        owner_index=owner_index,
                    )
                )
        return tuple(detected)

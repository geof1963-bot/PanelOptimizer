# -*- coding: utf-8 -*-
"""Conservative B-rep seam-wall quality evidence for V7.10 output."""

from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class SeamWallQuality:
    """Scalar evidence used to reject obvious corrugated seam artifacts."""

    face_count: int
    minimum_face_area_mm2: float
    tiny_face_count: int
    maximum_adjacent_normal_jump_deg: float
    suspected_fin_count: int


def inspect_seam_walls(shape: object) -> SeamWallQuality:
    """Inspect final B-rep faces without relying on mesh repair.

    The metric is intentionally conservative: small vertical faces are
    counted as possible seam walls, while tiny faces and abrupt normal changes
    are reported as evidence for review rather than silently repaired.
    """
    faces = tuple(getattr(shape, "Faces", ()))
    wall_faces = []
    normals = []
    for face in faces:
        box = face.BoundBox
        if float(box.ZLength) > 0.5:
            wall_faces.append(face)
            try:
                normal = face.normalAt(0.0, 0.0)
                length = math.sqrt(float(normal.x) ** 2 + float(normal.y) ** 2 + float(normal.z) ** 2)
                if length > 1.0e-9:
                    normals.append((float(normal.x) / length, float(normal.y) / length, float(normal.z) / length))
            except Exception:
                continue
    areas = tuple(float(face.Area) for face in wall_faces)
    tiny = sum(area < 0.05 for area in areas)
    jumps = []
    for first, second in zip(normals, normals[1:]):
        dot = max(-1.0, min(1.0, abs(sum(a * b for a, b in zip(first, second)))))
        jumps.append(math.degrees(math.acos(dot)))
    suspected = sum(
        1 for face in wall_faces
        if float(face.Area) < 0.5 and float(face.BoundBox.ZLength) > 2.0
    )
    return SeamWallQuality(
        face_count=len(wall_faces),
        minimum_face_area_mm2=min(areas, default=0.0),
        tiny_face_count=tiny,
        maximum_adjacent_normal_jump_deg=max(jumps, default=0.0),
        suspected_fin_count=suspected,
    )

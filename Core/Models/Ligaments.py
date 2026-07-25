# -*- coding: utf-8 -*-
"""Immutable continuous-material ligament observations."""

from __future__ import annotations

from dataclasses import dataclass

from .Common import Point3D


@dataclass(frozen=True, slots=True)
class MaterialLigamentObservation:
    """One measured continuous-material segment between two boundaries.

    Attributes:
        observation_id: Deterministic ID using
            ``{source_id}:geometry:ligament:{index:04d}`` in canonical
            boundary-pair order.
        start: Endpoint on the first boundary, in model coordinates and mm.
        end: Endpoint on the second boundary, in model coordinates and mm.
        width_mm: Exact geometric separation represented by ``start`` and
            ``end``, in mm.
        first_boundary_id: Stable source-element or topology-feature ID for
            the boundary containing ``start``.
        second_boundary_id: Stable source-element or topology-feature ID for
            the boundary containing ``end``.
        related_feature_ids: Topology feature IDs adjacent to the measured
            material segment.
        source_element_ids: Deterministic source face, edge, or vertex IDs
            contributing its boundaries.

    This observation is geometric evidence that the transverse segment is
    continuous material.  It records no longitudinal centerline or extent and
    does not classify the material as thin, wide, adequate, manufacturable, or
    suitable for a seam.
    """

    observation_id: str
    start: Point3D
    end: Point3D
    width_mm: float
    first_boundary_id: str
    second_boundary_id: str
    related_feature_ids: tuple[str, ...] = ()
    source_element_ids: tuple[str, ...] = ()

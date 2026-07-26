# -*- coding: utf-8 -*-
"""Conservative exact reflection-symmetry observations."""

from __future__ import annotations

from ..Models import (
    Direction3D,
    GeometrySnapshot,
    SymmetryObservation,
    TopologyAnalysis,
)
from ._Utilities import same_shape

__all__ = ["SymmetryAnalyzer"]


class SymmetryAnalyzer:
    """Describe only exactly proven principal-plane reflection symmetry."""

    _MODEL_AXIS_NORMALS = (
        Direction3D(1.0, 0.0, 0.0),
        Direction3D(0.0, 1.0, 0.0),
        Direction3D(0.0, 0.0, 1.0),
    )

    def analyze(
        self,
        geometry: GeometrySnapshot,
        topology: TopologyAnalysis,
        shape: object,
    ) -> tuple[SymmetryObservation, ...]:
        """Return exact reflection evidence for three deterministic planes.

        The only candidates are the model-coordinate planes through
        ``GeometrySnapshot.center`` with normals +X, +Y, and +Z, in that
        order.  Each plane is tested by mirroring a transient, forward-
        oriented material copy and requiring the B-rep subtraction to contain
        no solid in either direction.  Bounds, volume, centroid, and topology
        counts are never sufficient evidence by themselves.

        Exact accepted symmetry has zero measured deviation.  Approximate
        reflection and rotational symmetry are conservatively omitted because
        the current stage defines no geometry-only classification threshold or
        non-arbitrary rotational-order search.
        """
        del topology
        material = self._material_shape(shape)
        if material is None:
            return ()

        observations: list[SymmetryObservation] = []
        for normal in self._MODEL_AXIS_NORMALS:
            if not self._is_exact_reflection(
                material,
                geometry.center,
                normal,
            ):
                continue
            index = len(observations) + 1
            observations.append(
                SymmetryObservation(
                    observation_id=(
                        f"{geometry.source_id}:geometry:symmetry:"
                        f"{index:04d}"
                    ),
                    symmetry_type="reflection",
                    origin=geometry.center,
                    direction=normal,
                    rotational_order=None,
                    maximum_deviation_mm=0.0,
                    related_feature_ids=(),
                )
            )
        return tuple(observations)

    @staticmethod
    def _material_shape(shape: object) -> object | None:
        """Return a transient forward-oriented copy of all material solids.

        Open shells and compounds containing topology not owned by their
        solids are omitted, preventing a solid-only comparison from silently
        ignoring source geometry.  Reversing transient copies makes the proof
        independent of whole-solid orientation.
        """
        try:
            import Part
        except ImportError:
            return None

        source_solids = tuple(getattr(shape, "Solids", ()))
        if not source_solids:
            return None
        source_edges = tuple(getattr(shape, "Edges", ()))
        solid_edges = tuple(
            edge
            for solid in source_solids
            for edge in getattr(solid, "Edges", ())
        )
        if any(
            not any(same_shape(edge, solid_edge) for solid_edge in solid_edges)
            for edge in source_edges
        ):
            return None

        solids: list[object] = []
        try:
            for source_solid in source_solids:
                solid = source_solid.copy()
                if str(getattr(solid, "Orientation", "")) == "Reversed":
                    solid.reverse()
                if bool(solid.isNull()) or not bool(solid.isValid()):
                    return None
                solids.append(solid)
            if len(solids) == 1:
                return solids[0]
            return Part.makeCompound(tuple(solids))
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return None

    @staticmethod
    def _is_exact_reflection(
        material: object,
        origin: object,
        normal: Direction3D,
    ) -> bool:
        """Prove equality with a mirror using mutual solid subtraction."""
        try:
            from FreeCAD import Vector

            mirrored = material.mirror(
                Vector(origin.x_mm, origin.y_mm, origin.z_mm),
                Vector(normal.x, normal.y, normal.z),
            )
            first_difference = material.cut(mirrored)
            second_difference = mirrored.cut(material)
            return (
                not tuple(getattr(first_difference, "Solids", ()))
                and not tuple(getattr(second_difference, "Solids", ()))
            )
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return False

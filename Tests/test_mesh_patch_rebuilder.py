# -*- coding: utf-8 -*-
"""Focused V4.26 local mesh-patch and STL regression tests."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

try:
    import FreeCAD
    import Mesh
    import MeshPart
    import Part
except ImportError:  # pragma: no cover - ordinary Python contract discovery
    FreeCAD = Mesh = MeshPart = Part = None

from Core.Exceptions import SplitOperationError
from Core.MacroSplitCore import MacroSplitCore
from Core.MeshPatchRebuilder import (
    ANGULAR_DEFLECTION_DEGREES,
    LINEAR_DEFLECTION_MM,
    MeshPatchRebuilder,
    build_macro_mesh_parts,
    export_mesh_parts,
    mesh_metrics,
)


@unittest.skipIf(Part is None, "FreeCAD Part/Mesh modules are unavailable")
class MeshPatchRebuilderTests(unittest.TestCase):
    """Exercise reconstruction without touching the source B-rep."""

    @staticmethod
    def _bounds(shape):
        box = shape.BoundBox
        return (box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax)

    @staticmethod
    def _mesh(shape):
        import math

        return MeshPart.meshFromShape(
            Shape=shape,
            LinearDeflection=LINEAR_DEFLECTION_MM,
            AngularDeflection=math.radians(ANGULAR_DEFLECTION_DEGREES),
            Relative=False,
        )

    @staticmethod
    def _without_facets(mesh, removed):
        points, facets = mesh.Topology
        kept = [facet for index, facet in enumerate(facets) if index not in removed]
        return Mesh.Mesh((list(points), kept))

    def test_planar_missing_patch_and_narrow_strip_are_rebuilt(self):
        source = Part.makeBox(10.0, 8.0, 2.0)
        original_volume = float(source.Volume)
        original_bounds = self._bounds(source)
        complete = self._mesh(source)
        top = [
            index for index, facet in enumerate(complete.Facets)
            if sum(point[2] for point in facet.Points) / 3.0 > 1.999
        ]
        self.assertGreaterEqual(len(top), 2)
        for removed_count in (1, 2):
            damaged = self._without_facets(
                complete, set(top[:removed_count])
            )
            repaired, before, after, patches, added, vertices, movement = (
                MeshPatchRebuilder().rebuild_mesh(damaged, source)
            )
            self.assertGreater(before.open_edge_count, 0)
            self.assertEqual(after.open_edge_count, 0)
            self.assertTrue(after.is_solid)
            self.assertEqual(after.non_manifold_edge_count, 0)
            self.assertGreaterEqual(added, removed_count)
            self.assertEqual(vertices, 0)
            self.assertEqual(movement, 0.0)
            self.assertTrue(patches)
            self.assertAlmostEqual(float(source.Volume), original_volume)
            self.assertEqual(self._bounds(source), original_bounds)

    def test_annular_patch_preserves_inner_hole(self):
        source = Part.makeCylinder(6.0, 2.0).cut(Part.makeCylinder(2.0, 2.0))
        original_volume = float(source.Volume)
        original_bounds = self._bounds(source)
        complete = self._mesh(source)
        top = {
            index for index, facet in enumerate(complete.Facets)
            if sum(point[2] for point in facet.Points) / 3.0 > 1.999
        }
        damaged = self._without_facets(
            complete, top,
        )
        repaired, before, after, patches, _added, _vertices, _movement = (
            MeshPatchRebuilder().rebuild_mesh(damaged, source)
        )
        self.assertGreater(before.open_edge_count, 0)
        self.assertEqual(after.open_edge_count, 0)
        self.assertTrue(after.is_solid)
        self.assertTrue(any(patch.inner_boundary_count == 1 for patch in patches))
        self.assertAlmostEqual(after.volume_mm3, float(source.Volume), delta=5.0)
        self.assertAlmostEqual(float(source.Volume), original_volume)
        self.assertEqual(self._bounds(source), original_bounds)

    def test_non_planar_boundary_is_rejected(self):
        source = Part.makeBox(10.0, 10.0, 2.0)
        # Four side facets leave a deliberately warped quadrilateral opening.
        points = [
            (0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0),
            (0, 0, 2), (10, 0, 2), (10, 10, 2.1), (0, 10, 2),
        ]
        facets = [
            (0, 1, 5), (0, 5, 4), (1, 2, 6), (1, 6, 5),
            (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7),
            (0, 3, 2), (0, 2, 1),
        ]
        damaged = Mesh.Mesh(([FreeCAD.Vector(*point) for point in points], facets))
        with self.assertRaisesRegex(SplitOperationError, "non-planar|ambiguous"):
            MeshPatchRebuilder().rebuild_mesh(damaged, source)

    def test_intentional_perforation_is_not_filled(self):
        source = Part.makeBox(12.0, 12.0, 2.0).cut(
            Part.makeCylinder(2.0, 2.0, FreeCAD.Vector(6.0, 6.0, 0.0))
        )
        repaired, before, after, patches, *_ = MeshPatchRebuilder().rebuild(source)
        self.assertEqual(before.open_edge_count, 0)
        self.assertEqual(after.open_edge_count, 0)
        self.assertEqual(patches, ())
        self.assertTrue(repaired.isSolid())

    def test_exported_mesh_reopens_watertight(self):
        source = Part.makeBox(10.0, 8.0, 2.0)
        repaired, _before, after, *_ = MeshPatchRebuilder().rebuild(source)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.stl"
            repaired.write(str(path))
            reopened = Mesh.Mesh(str(path))
            metrics = mesh_metrics(reopened)
            self.assertEqual(metrics.open_edge_count, 0)
            self.assertTrue(metrics.is_solid)
            self.assertEqual(metrics.connected_component_count, 1)
            self.assertEqual(metrics.size_mm, after.size_mm)

    def test_four_part_pipeline_is_deterministic_and_transactional(self):
        source = Part.makeBox(100.0, 80.0, 8.0)
        before = (float(source.Volume), self._bounds(source))
        macro = MacroSplitCore().cut(source)
        first = build_macro_mesh_parts(macro)
        second = build_macro_mesh_parts(macro)
        self.assertEqual(tuple(part.name for part in first), (
            "Part_1", "Part_2", "Part_3", "Part_4"
        ))
        self.assertEqual(
            tuple((part.before, part.after, part.patches) for part in first),
            tuple((part.before, part.after, part.patches) for part in second),
        )
        self.assertTrue(all(part.after.is_solid for part in first))
        self.assertEqual((float(source.Volume), self._bounds(source)), before)
        with tempfile.TemporaryDirectory() as directory:
            artifacts = export_mesh_parts(first, directory)
            self.assertEqual(tuple(item.name for item in artifacts), (
                "Part_1", "Part_2", "Part_3", "Part_4"
            ))
            self.assertTrue(all(item.byte_count > 0 for item in artifacts))
            self.assertTrue(all(item.reopened.is_solid for item in artifacts))

    def test_each_final_part_is_tessellated_once_and_stage_times_are_recorded(self):
        macro = MacroSplitCore().cut(Part.makeBox(100.0, 80.0, 8.0))
        original = MeshPatchRebuilder.rebuild
        calls = []

        def counted(rebuilder, source_shape, timings=None):
            calls.append(source_shape)
            return original(rebuilder, source_shape, timings=timings)

        timings = {}
        with patch.object(MeshPatchRebuilder, "rebuild", new=counted):
            parts = build_macro_mesh_parts(macro, timings=timings)
        self.assertEqual(len(parts), 4)
        self.assertEqual(len(calls), 4)
        self.assertGreaterEqual(timings["mesh"], 0.0)
        self.assertGreaterEqual(timings["mesh_repair"], 0.0)

    def test_limits_block_export_and_commit_failure_restores_previous_set(self):
        source = Part.makeBox(100.0, 80.0, 8.0)
        macro = MacroSplitCore().cut(source)
        blocked = build_macro_mesh_parts(
            macro,
            SimpleNamespace(MAX_PART_WIDTH=49.0, MAX_PART_HEIGHT=100.0),
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(Exception, "configured X/Y limits"):
                export_mesh_parts(blocked, directory)

        parts = build_macro_mesh_parts(macro)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = {}
            for name in ("Part_1", "Part_2", "Part_3", "Part_4"):
                data = f"old-{name}".encode("ascii")
                (root / f"{name}.stl").write_bytes(data)
                old[name] = data
            import Core.MeshPatchRebuilder as module
            real_replace = module.os.replace

            def fail_second_commit(source_path, destination_path):
                if ".Part_2.paneloptimizer.partial.stl" in str(source_path):
                    raise OSError("synthetic commit failure")
                return real_replace(source_path, destination_path)

            with patch.object(module.os, "replace", side_effect=fail_second_commit):
                with self.assertRaisesRegex(Exception, "previous files were restored"):
                    export_mesh_parts(parts, directory)
            for name, data in old.items():
                self.assertEqual((root / f"{name}.stl").read_bytes(), data)
            self.assertFalse(tuple(root.glob(".*.paneloptimizer.*.stl")))


if __name__ == "__main__":
    unittest.main()

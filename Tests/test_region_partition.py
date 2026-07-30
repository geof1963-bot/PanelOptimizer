# -*- coding: utf-8 -*-
"""Focused V4.74 explicit sinuous XY-region regressions."""

from __future__ import annotations

import tempfile
import unittest

try:
    import Part
    from FreeCAD import Vector
except ImportError:  # pragma: no cover
    Part = Vector = None

from Core.DowelPlanner import DowelPlanner
from Core.LipBuilder import LipBuilder
from Core.MacroSplitCore import MacroSplitCore
from Core.MeshPatchRebuilder import build_macro_mesh_parts, export_mesh_parts
from Core.SinuousSeamPath import SinuousSeamPathFinder


@unittest.skipIf(Part is None, "FreeCAD Part module is unavailable")
class RegionPartitionTests(unittest.TestCase):
    @staticmethod
    def _representative():
        source = Part.makeBox(594.0, 594.0, 8.0)
        for y_value in (60.0, 150.0, 444.0, 534.0):
            source = source.cut(
                Part.makeCylinder(12.0, 8.0, Vector(300.0, y_value, 0.0))
            )
        for x_value in (60.0, 150.0, 444.0, 534.0):
            source = source.cut(
                Part.makeCylinder(12.0, 8.0, Vector(x_value, 294.0, 0.0))
            )
        return source

    @staticmethod
    def _plan(source):
        finder = SinuousSeamPathFinder()
        bounds = source.BoundBox
        panel_bounds = (
            float(bounds.XMin), float(bounds.XMax),
            float(bounds.YMin), float(bounds.YMax),
        )
        return finder.topology_shortlist(
            finder.generate(source), panel_bounds
        )[0]

    def test_straight_guides_construct_four_closed_covering_regions(self):
        source = Part.makeBox(100.0, 100.0, 8.0)
        plan = SinuousSeamPathFinder().generate(source)
        result = MacroSplitCore().cut_regions(source, seam_plan=plan)
        self.assertEqual(result.partition_method, "sinuous_xy_regions")
        self.assertEqual(result.solid_count, 4)
        self.assertEqual(result.region_solid_counts, (1, 1, 1, 1))
        self.assertTrue(all(area > 0.0 for area in result.region_areas_mm2))
        self.assertAlmostEqual(sum(result.region_areas_mm2), 10000.0, places=5)

    def test_sinuous_regions_preserve_exact_groove_material_accounting(self):
        source = Part.makeBox(300.0, 300.0, 8.0)
        for x_value, y_value in (
            (152.0, 50.0), (152.0, 250.0),
            (50.0, 148.0), (250.0, 148.0),
        ):
            source = source.cut(
                Part.makeCylinder(8.0, 8.0, Vector(x_value, y_value, 0.0))
            )
        before = source.exportBrepToString()
        plan = self._plan(source)
        direct = MacroSplitCore().cut(source, seam_plan=plan)
        regions = MacroSplitCore().cut_regions(source, seam_plan=plan)
        self.assertTrue(plan.vertical.followed_feature_ids)
        self.assertTrue(plan.horizontal.followed_feature_ids)
        self.assertEqual(regions.solid_count, 4)
        self.assertAlmostEqual(
            regions.result_volume_mm3, direct.result_volume_mm3, places=4
        )
        self.assertAlmostEqual(sum(regions.region_areas_mm2), 90000.0, places=4)
        self.assertEqual(source.exportBrepToString(), before)

    def test_irregular_perforated_representative_has_no_fifth_part(self):
        source = self._representative()
        before = source.exportBrepToString()
        plan = self._plan(source)
        result = MacroSplitCore().cut_regions(source, seam_plan=plan)
        self.assertEqual(result.solid_count, 4)
        self.assertEqual(result.region_solid_counts, (1, 1, 1, 1))
        self.assertEqual(len(result.shape.Solids), 4)
        self.assertTrue(all(
            report.original_profile_preserved
            for path in (plan.vertical, plan.horizontal)
            for report in path.hole_offset_reports
        ))
        self.assertEqual(source.exportBrepToString(), before)

    def test_region_parts_complete_dowels_lips_mesh_and_stl_pipeline(self):
        source = self._representative()
        before = source.exportBrepToString()
        macro = MacroSplitCore().cut_regions(
            source, seam_plan=self._plan(source)
        )
        planner = DowelPlanner()
        dowels = planner.plan(macro)
        self.assertEqual(
            tuple(len(branch.accepted_dowel_ids) for branch in dowels.branches),
            (4, 4, 4, 4),
        )
        drilled = planner.apply(macro, dowels)
        lipped = LipBuilder().apply(
            drilled.macro_result, dowel_cutters=drilled.cutters
        )
        self.assertTrue(all(report.volume_added_mm3 > 0.0 for report in lipped.reports))
        meshes = build_macro_mesh_parts(lipped.macro_result)
        self.assertTrue(all(
            item.after.open_edge_count == 0
            and item.after.non_manifold_edge_count == 0
            and item.after.connected_component_count == 1
            and item.after.is_solid
            for item in meshes
        ))
        with tempfile.TemporaryDirectory() as directory:
            artifacts = export_mesh_parts(meshes, directory)
        self.assertEqual(len(artifacts), 4)
        self.assertTrue(all(item.reopened.is_solid for item in artifacts))
        self.assertEqual(source.exportBrepToString(), before)


if __name__ == "__main__":
    unittest.main()

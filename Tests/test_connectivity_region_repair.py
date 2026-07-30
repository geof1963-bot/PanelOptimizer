# -*- coding: utf-8 -*-
"""Focused V4.74A connectivity-aware region partition regressions."""

from __future__ import annotations

import tempfile
import time
import unittest
from dataclasses import replace

try:
    import Part
    from FreeCAD import Vector
except ImportError:  # pragma: no cover
    Part = Vector = None

from Commands.SplitPanelCommand import _progressive_four_part_split
from Core.DowelPlanner import DowelPlanner
from Core.ConnectivityRepair import diagnose_region_connectivity
from Core.Exceptions import RegionConnectivityError
from Core.LipBuilder import LipBuilder
from Core.MacroPartExtractor import MacroPartExtractor
from Core.MacroSplitCore import MacroSplitCore
from Core.MeshPatchRebuilder import build_macro_mesh_parts, export_mesh_parts
from Core.SinuousSeamPath import Point2D, SinuousSeamPathFinder


@unittest.skipIf(Part is None, "FreeCAD Part module is unavailable")
class ConnectivityRegionRepairTests(unittest.TestCase):
    """Exercise one actual ownership island and its local curved repair."""

    @staticmethod
    def _fixture():
        source = Part.makeBox(594.0, 594.0, 8.0)
        source = source.cut(
            Part.makeBox(30.0, 40.0, 8.0, Vector(282.0, 20.0, 0.0))
        )
        source = source.cut(
            Part.makeBox(40.0, 30.0, 8.0, Vector(450.0, 282.0, 0.0))
        )
        finder = SinuousSeamPathFinder()
        original = finder.generate(source)
        self_bounds = (0.0, 594.0, 0.0, 594.0)
        plan = finder.topology_shortlist(original, self_bounds)[0]
        dangerous_points = (
            Point2D(297.0, 0.0),
            Point2D(297.0, 28.0),
            Point2D(267.0, 33.0),
            Point2D(267.0, 48.0),
            Point2D(297.0, 53.0),
            Point2D(297.0, 594.0),
        )
        dangerous_vertical = replace(
            plan.vertical,
            points=dangerous_points,
            path_length_mm=sum(
                ((b.x_mm - a.x_mm) ** 2 + (b.y_mm - a.y_mm) ** 2) ** 0.5
                for a, b in zip(dangerous_points, dangerous_points[1:])
            ),
            maximum_deviation_mm=30.0,
            segment_count_before_cleanup=5,
            segment_count_after_cleanup=5,
        )
        dangerous = replace(plan, vertical=dangerous_vertical)
        return source, finder, dangerous, self_bounds

    def test_disconnected_region_is_diagnosed_and_mapped(self):
        source, _finder, dangerous, _bounds = self._fixture()
        before = source.exportBrepToString()
        with self.assertRaises(RegionConnectivityError) as caught:
            MacroSplitCore().cut_regions(source, seam_plan=dangerous)
        diagnosis = caught.exception.diagnosis
        self.assertEqual(diagnosis.region_index, 2)
        self.assertGreaterEqual(len(diagnosis.components), 2)
        self.assertEqual(diagnosis.secondary.nearest_seam, "vertical")
        self.assertEqual(diagnosis.secondary.nearest_detour_id, "VDET_001")
        self.assertEqual(diagnosis.secondary.nearest_segment_id, "VSEG_003")
        self.assertGreater(diagnosis.secondary.volume_mm3, 0.0)
        self.assertEqual(len(diagnosis.secondary.bounds_mm), 6)
        self.assertGreaterEqual(diagnosis.secondary.opening_distance_mm, 0.0)
        message = str(caught.exception)
        self.assertIn("Secondary volume:", message)
        self.assertIn("Repair attempts: 0", message)
        self.assertEqual(source.exportBrepToString(), before)

    def test_bounded_local_repair_restores_the_complete_pipeline(self):
        source, finder, dangerous, bounds = self._fixture()
        before = source.exportBrepToString()
        started = time.perf_counter()
        result = _progressive_four_part_split(
            finder,
            (dangerous,),
            bounds,
            lambda candidate: MacroSplitCore().cut_regions(
                source, seam_plan=candidate
            ),
        )
        repaired, validations, _rejected, _success, diagnostics, repair_elapsed = result
        self.assertIsNotNone(repaired, "\n".join(diagnostics))
        self.assertLessEqual(repaired.connectivity_repair_attempts, 8)
        self.assertLessEqual(validations, 8)
        self.assertEqual(repaired.region_solid_counts, (1, 1, 1, 1))
        self.assertEqual(repaired.solid_count, 4)
        self.assertNotEqual(
            repaired.seam_plan.vertical.points,
            dangerous.vertical.points,
        )
        self.assertEqual(repaired.seam_plan.horizontal, dangerous.horizontal)
        self.assertEqual(repaired.seam_plan.vertical.detour_levels, (2,))
        self.assertGreater(repaired.seam_plan.vertical.maximum_deviation_mm, 0.5)
        self.assertTrue(all(
            report.original_profile_preserved
            for path in (repaired.seam_plan.vertical, repaired.seam_plan.horizontal)
            for report in path.hole_offset_reports
        ))
        extraction = MacroPartExtractor().extract(
            repaired, "V474A", accept_closed_invalid=True, verify_overlap=False
        )
        self.assertTrue(extraction.execution.result.all_parts_printable)
        self.assertTrue(all(
            part.size_x_mm <= 330.0 and part.size_y_mm <= 330.0
            for part in extraction.execution.result.parts
        ))
        planner = DowelPlanner()
        dowel_plan = planner.plan(repaired)
        self.assertEqual(
            tuple(len(branch.accepted_dowel_ids) for branch in dowel_plan.branches),
            (4, 4, 4, 4),
        )
        drilled = planner.apply(repaired, dowel_plan)
        lipped = LipBuilder().apply(
            drilled.macro_result, dowel_cutters=drilled.cutters
        )
        self.assertTrue(all(item.volume_added_mm3 > 0.0 for item in lipped.reports))
        self.assertEqual(lipped.macro_result.seam_plan, repaired.seam_plan)
        meshes = build_macro_mesh_parts(lipped.macro_result)
        self.assertTrue(all(item.after.is_solid for item in meshes))
        with tempfile.TemporaryDirectory() as directory:
            artifacts = export_mesh_parts(meshes, directory)
        self.assertEqual(len(artifacts), 4)
        self.assertTrue(all(item.reopened.is_solid for item in artifacts))
        self.assertEqual(source.exportBrepToString(), before)
        self.assertLessEqual(repair_elapsed, 20.0)
        self.assertLess(time.perf_counter() - started, 60.0)

    @staticmethod
    def _classify_secondary(secondary, panel_bounds=None):
        """Return classification evidence beside a 426,956 mm^3 main body."""
        main = Part.makeBox(267.0, 199.979775, 8.0, Vector(20.0, 100.0, 0.0))
        finder = SinuousSeamPathFinder()
        plan = finder.topology_shortlist(
            finder.generate(Part.makeBox(594.0, 594.0, 8.0)),
            (0.0, 594.0, 0.0, 594.0),
        )[0]
        diagnosis = diagnose_region_connectivity(
            1,
            (main, secondary),
            plan,
            panel_bounds or (0.0, 0.0, 0.0, 594.0, 594.0, 8.0),
            8.0,
        )
        return diagnosis.secondary

    def test_tiny_shallow_sliver_is_non_structural(self):
        sliver = Part.makeBox(
            3.0, 4.378457, 1.4, Vector(295.5, 80.0, 0.0)
        )
        evidence = self._classify_secondary(sliver)
        self.assertAlmostEqual(evidence.volume_mm3, 18.3895194, places=5)
        self.assertEqual(evidence.classification, "NON_STRUCTURAL_SLIVER")
        self.assertLess(evidence.volume_ratio, 0.0002)
        self.assertFalse(evidence.spans_substantial_thickness)

    def test_meaningful_1922_mm3_is_structural(self):
        island = Part.makeBox(15.5, 15.5, 8.0, Vector(289.0, 80.0, 0.0))
        evidence = self._classify_secondary(island)
        self.assertAlmostEqual(evidence.volume_mm3, 1922.0, places=5)
        self.assertEqual(evidence.classification, "STRUCTURAL")

    def test_small_volume_alone_is_insufficient(self):
        full_thickness = Part.makeBox(
            1.0, 2.0, 8.0, Vector(296.5, 80.0, 0.0)
        )
        evidence = self._classify_secondary(full_thickness)
        self.assertLess(evidence.volume_mm3, 50.0)
        self.assertEqual(evidence.classification, "STRUCTURAL")

    def test_shallow_thickness_alone_is_insufficient(self):
        wide = Part.makeBox(20.0, 20.0, 1.0, Vector(287.0, 80.0, 0.0))
        evidence = self._classify_secondary(wide)
        self.assertFalse(evidence.spans_substantial_thickness)
        self.assertEqual(evidence.classification, "STRUCTURAL")

    def test_exterior_component_is_never_discarded(self):
        exterior = Part.makeBox(
            3.0, 4.0, 1.4, Vector(0.0, 80.0, 0.0)
        )
        evidence = self._classify_secondary(exterior)
        self.assertTrue(evidence.touches_panel_exterior)
        self.assertEqual(evidence.classification, "STRUCTURAL")

    def test_sliver_only_region_does_not_trigger_connectivity_repair(self):
        panel = Part.makeBox(594.0, 594.0, 8.0)
        main = panel.cut(
            Part.makeBox(6.0, 8.0, 8.0, Vector(292.0, 78.0, 0.0))
        )
        sliver = Part.makeBox(
            3.0, 4.378457, 1.4, Vector(293.5, 80.0, 0.0)
        )
        source = Part.makeCompound((main, sliver))
        before = source.exportBrepToString()
        finder = SinuousSeamPathFinder()
        plan = finder.topology_shortlist(
            finder.generate(panel), (0.0, 594.0, 0.0, 594.0)
        )[0]
        result = _progressive_four_part_split(
            finder,
            (plan,),
            (0.0, 594.0, 0.0, 594.0),
            lambda candidate: MacroSplitCore().cut_regions(
                source, seam_plan=candidate
            ),
        )[0]
        self.assertIsNotNone(result)
        self.assertEqual(result.connectivity_repair_attempts, 0)
        self.assertEqual(result.seam_plan, plan)
        self.assertEqual(result.region_solid_counts, (1, 1, 1, 1))
        self.assertEqual(result.solid_count, 4)
        self.assertEqual(sum(result.region_discarded_sliver_counts), 1)
        observations = tuple(
            item
            for diagnosis in result.region_component_diagnostics
            for item in diagnosis.components
        )
        ignored = tuple(
            item for item in observations
            if item.classification == "NON_STRUCTURAL_SLIVER"
        )
        self.assertEqual(len(ignored), 1)
        self.assertAlmostEqual(ignored[0].volume_mm3, 18.3895194, places=5)
        meshes = build_macro_mesh_parts(result)
        self.assertTrue(all(item.after.is_solid for item in meshes))
        self.assertTrue(all(item.after.open_edge_count == 0 for item in meshes))
        self.assertTrue(all(
            item.after.non_manifold_edge_count == 0 for item in meshes
        ))
        self.assertTrue(all(
            item.after.connected_component_count == 1 for item in meshes
        ))
        with tempfile.TemporaryDirectory() as directory:
            artifacts = export_mesh_parts(meshes, directory)
        self.assertEqual(len(artifacts), 4)
        self.assertTrue(all(item.reopened.is_solid for item in artifacts))
        self.assertEqual(source.exportBrepToString(), before)


if __name__ == "__main__":
    unittest.main()

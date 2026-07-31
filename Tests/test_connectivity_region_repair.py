# -*- coding: utf-8 -*-
"""Focused V4.74A connectivity-aware region partition regressions."""

from __future__ import annotations

import math
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
from Core.ConnectivityRepair import (
    RegionConnectivityDiagnosis,
    classify_region_components,
    diagnose_region_connectivity,
)
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

    def test_exact_real_metrics_are_non_structural(self):
        sliver = Part.makeBox(
            3.0, 4.378457, 1.4, Vector(295.5, 80.0, 0.0)
        )
        evidence = self._classify_secondary(sliver)
        exact = replace(
            evidence,
            volume_mm3=18.389520,
            footprint_mm2=259.070744,
            thickness_mm=1.400001,
            volume_ratio=0.00004307,
            opening_distance_mm=1.419807,
            touches_panel_exterior=False,
        )
        diagnosis = classify_region_components(
            replace(
                diagnose_region_connectivity(
                    1,
                    (
                        Part.makeBox(
                            267.0, 199.979775, 8.0,
                            Vector(20.0, 100.0, 0.0),
                        ),
                        sliver,
                    ),
                    SinuousSeamPathFinder().topology_shortlist(
                        SinuousSeamPathFinder().generate(
                            Part.makeBox(594.0, 594.0, 8.0)
                        ),
                        (0.0, 594.0, 0.0, 594.0),
                    )[0],
                    (0.0, 0.0, 0.0, 594.0, 594.0, 8.0),
                    8.0,
                ),
                components=(
                    replace(evidence, rank=1, classification="STRUCTURAL"),
                    exact,
                ),
            ),
            8.0,
        )
        result = diagnosis.secondary
        self.assertTrue(result.volume_ok)
        self.assertTrue(result.volume_ratio_ok)
        self.assertTrue(result.thickness_ok)
        self.assertTrue(result.footprint_ok)
        self.assertTrue(result.opening_proximity_ok)
        self.assertFalse(result.touches_panel_exterior)
        self.assertFalse(result.silhouette_risk)
        self.assertFalse(result.full_thickness)
        self.assertEqual(result.classification, "NON_STRUCTURAL_SLIVER")

    def test_internal_boundary_proximity_does_not_make_sliver_structural(self):
        sliver = Part.makeBox(
            3.0, 4.378457, 1.4, Vector(295.5, 80.0, 0.0)
        )
        evidence = self._classify_secondary(sliver)
        for changes in (
            {"seam_distance_mm": 0.0, "opening_distance_mm": math.inf},
            {"seam_distance_mm": 20.0, "opening_distance_mm": 0.0},
            {"seam_distance_mm": 20.0, "opening_distance_mm": math.inf},
        ):
            diagnosis = classify_region_components(
                replace(
                    diagnose_region_connectivity(
                        1,
                        (
                            Part.makeBox(
                                267.0, 199.979775, 8.0,
                                Vector(20.0, 100.0, 0.0),
                            ),
                            sliver,
                        ),
                        SinuousSeamPathFinder().topology_shortlist(
                            SinuousSeamPathFinder().generate(
                                Part.makeBox(594.0, 594.0, 8.0)
                            ),
                            (0.0, 594.0, 0.0, 594.0),
                        )[0],
                        (0.0, 0.0, 0.0, 594.0, 594.0, 8.0),
                        8.0,
                    ),
                    components=(
                        replace(evidence, rank=1, classification="STRUCTURAL"),
                        replace(evidence, **changes),
                    ),
                ),
                8.0,
            )
            self.assertEqual(
                diagnosis.secondary.classification,
                "NON_STRUCTURAL_SLIVER",
            )

    def test_meaningful_1922_mm3_is_structural(self):
        island = Part.makeBox(15.5, 15.5, 8.0, Vector(289.0, 80.0, 0.0))
        evidence = self._classify_secondary(island)
        self.assertAlmostEqual(evidence.volume_mm3, 1922.0, places=5)
        self.assertEqual(evidence.classification, "STRUCTURAL")

    def test_exact_v475_sparse_fragments_are_non_structural(self):
        seed = self._classify_secondary(
            Part.makeBox(3.0, 4.0, 1.4, Vector(295.5, 80.0, 0.0))
        )
        main = replace(
            seed,
            rank=1,
            volume_mm3=378_831.0,
            thickness_mm=8.0,
            volume_ratio=1.0,
            classification="STRUCTURAL",
        )
        fragments = (
            (82.781151, 1.400001, 1018.072151, 0.00021841, 59.129351),
            (75.769892, 1.400001, 2031.973827, 0.00019991, 54.121313),
        )
        components = [main]
        for rank, (volume, thickness, bbox_area, ratio, _area) in enumerate(
            fragments, start=2
        ):
            components.append(replace(
                seed,
                rank=rank,
                volume_mm3=volume,
                thickness_mm=thickness,
                footprint_mm2=bbox_area,
                volume_ratio=ratio,
                touches_panel_exterior=False,
                silhouette_risk=False,
            ))
        diagnosis = classify_region_components(
            RegionConnectivityDiagnosis(2, tuple(components)),
            8.0,
        )
        for component, expected in zip(
            diagnosis.components[1:], fragments
        ):
            self.assertAlmostEqual(
                component.effective_footprint_mm2, expected[4], places=5
            )
            self.assertEqual(
                component.classification, "NON_STRUCTURAL_SLIVER"
            )
            self.assertFalse(component.footprint_ok)

    def test_exact_v475_region_profile_has_one_structural_component(self):
        seed = self._classify_secondary(
            Part.makeBox(3.0, 4.0, 1.4, Vector(295.5, 80.0, 0.0))
        )
        volumes = (
            378_831.0,
            82.781151,
            75.769892,
            0.431282,
            0.121570,
            0.051269,
            0.002448,
        )
        components = []
        for rank, volume in enumerate(volumes, start=1):
            thickness = 8.0 if rank == 1 else 1.400001
            components.append(replace(
                seed,
                rank=rank,
                volume_mm3=volume,
                thickness_mm=thickness,
                footprint_mm2=2031.973827 if rank in (2, 3) else 1.0,
                volume_ratio=1.0 if rank == 1 else volume / volumes[0],
                touches_panel_exterior=False,
                classification="STRUCTURAL",
            ))
        diagnosis = classify_region_components(
            RegionConnectivityDiagnosis(2, tuple(components)),
            8.0,
        )
        self.assertEqual(diagnosis.raw_solid_count, 7)
        self.assertEqual(diagnosis.sliver_count, 6)
        self.assertEqual(diagnosis.structural_count, 1)

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

    def test_original_outer_wire_contact_is_structural(self):
        panel = Part.makeBox(594.0, 594.0, 8.0)
        exterior_surface = MacroSplitCore._original_exterior_surface(
            panel, 0.0, 8.0, Part, Vector
        )
        main = Part.makeBox(
            267.0, 199.979775, 8.0, Vector(20.0, 100.0, 0.0)
        )
        fragment = Part.makeBox(3.0, 4.0, 1.4, Vector(0.0, 80.0, 0.0))
        finder = SinuousSeamPathFinder()
        plan = finder.topology_shortlist(
            finder.generate(panel), (0.0, 594.0, 0.0, 594.0)
        )[0]
        evidence = diagnose_region_connectivity(
            1,
            (main, fragment),
            plan,
            (0.0, 0.0, 0.0, 594.0, 594.0, 8.0),
            8.0,
            exterior_surface,
        ).secondary
        self.assertTrue(evidence.touches_panel_exterior)
        self.assertTrue(evidence.silhouette_risk)
        self.assertEqual(evidence.classification, "STRUCTURAL")

    def test_sliver_only_region_does_not_trigger_connectivity_repair(self):
        panel = Part.makeBox(594.0, 594.0, 8.0)
        main = panel.cut(
            Part.makeBox(3.0, 260.1, 8.0, Vector(294.5, 19.5, 0.0))
        )
        sliver = Part.makeBox(
            1.0, 259.070744, 0.05, Vector(295.5, 20.0, 0.0)
        ).fuse(
            Part.makeBox(
                1.0,
                4.02665094322152,
                1.350001,
                Vector(295.5, 20.0, 0.05),
            )
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
        self.assertAlmostEqual(ignored[0].volume_mm3, 18.389520, places=5)
        self.assertAlmostEqual(ignored[0].footprint_mm2, 259.070744, places=5)
        self.assertAlmostEqual(ignored[0].thickness_mm, 1.400001, places=5)
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

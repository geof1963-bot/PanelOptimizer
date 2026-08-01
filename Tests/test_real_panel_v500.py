# -*- coding: utf-8 -*-
"""Conditional end-to-end regression for the local real production panel."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

try:
    import FreeCAD
except ImportError:  # pragma: no cover
    FreeCAD = None

import Commands.SplitPanelCommand as split_module


ROOT = Path(__file__).resolve().parents[1]
REAL_PANEL = ROOT / "RealTests" / "Circus Blocs et background_test workbench.FCStd"


@unittest.skipIf(FreeCAD is None, "FreeCAD is unavailable")
@unittest.skipUnless(REAL_PANEL.is_file(), "Real production FCStd is unavailable")
class RealPanelV501Tests(unittest.TestCase):
    """Exercise one exact real command run and share its immutable evidence."""

    @classmethod
    def setUpClass(cls):
        cls.document = FreeCAD.openDocument(str(REAL_PANEL))
        cls.source = cls.document.getObject("FINAL_PANEL")
        if cls.source is None:
            raise AssertionError("FINAL_PANEL is absent from the real FCStd")
        cls.source_before = cls.source.Shape.exportBrepToString()
        cls.previous_selection = getattr(split_module.FreeCADGui, "Selection", None)
        split_module.FreeCADGui.Selection = SimpleNamespace(
            getSelection=lambda: [cls.source]
        )
        cls.directory = tempfile.TemporaryDirectory()
        cls.command = split_module.PanelOptimizerSplitPanelCommand()
        cls.command._select_output_directory = lambda: cls.directory.name
        started = time.perf_counter()
        cls.command.Activated()
        cls.wall_seconds = time.perf_counter() - started
        cls.evidence = cls.command._last_run_evidence

    @classmethod
    def tearDownClass(cls):
        if cls.previous_selection is not None:
            split_module.FreeCADGui.Selection = cls.previous_selection
        cls.directory.cleanup()
        FreeCAD.closeDocument(cls.document.Name)

    def test_real_final_panel_completes_and_reopens_four_stls(self):
        self.assertIsNotNone(self.evidence)
        outputs = tuple(
            Path(self.directory.name) / f"Part_{index}.stl"
            for index in range(1, 5)
        )
        self.assertTrue(all(path.is_file() for path in outputs))
        self.assertTrue(all(path.stat().st_size > 0 for path in outputs))
        self.assertEqual(self.source_before, self.source.Shape.exportBrepToString())
        self.assertTrue(all(
            artifact.reopened.open_edge_count == 0
            and artifact.reopened.non_manifold_edge_count == 0
            and artifact.reopened.connected_component_count == 1
            and artifact.reopened.is_solid
            for artifact in self.evidence["stl_artifacts"]
        ))

    def test_real_vertical_and_horizontal_seams_have_artistic_detours(self):
        seam_plan = self.evidence["seam_plan"]
        for path in (seam_plan.vertical, seam_plan.horizontal):
            self.assertGreaterEqual(len(path.detour_ids), 2)
            self.assertGreaterEqual(len(path.followed_feature_ids), 2)
            self.assertGreater(path.maximum_deviation_mm, 0.5)
            if path.axis == "vertical":
                self.assertLess(path.longest_straight_segment_mm, 80.0)
            else:
                self.assertLess(path.longest_straight_segment_mm, 100.0)
            self.assertTrue(all(
                report.original_profile_preserved
                for report in path.hole_offset_reports
            ))

    def test_real_performance_and_printability_regression(self):
        timings = self.evidence["timings"]
        self.assertLess(timings["dowel_plan"], 90.0)
        # A durable regression threshold against the measured 521.390 s V5.00
        # run.  The stricter 180 s production target is reported, never faked.
        self.assertLess(timings["total"], 300.0)
        self.assertLess(self.wall_seconds, 310.0)
        self.assertTrue(all(
            x_value <= 330.0 and y_value <= 330.0
            for x_value, y_value, _z_value
            in self.evidence["part_dimensions_mm"]
        ))

    def test_real_canonical_dowel_axes_are_coaxial(self):
        reports = self.evidence["coaxiality_reports"]
        self.assertTrue(reports)
        self.assertTrue(all(item.is_coaxial for item in reports))
        self.assertTrue(all(item.third_part_hits == () for item in reports))
        self.assertTrue(all(item.angular_mismatch_deg <= 0.1 for item in reports))
        self.assertTrue(all(item.centerline_mismatch_mm <= 0.02 for item in reports))


if __name__ == "__main__":
    unittest.main()

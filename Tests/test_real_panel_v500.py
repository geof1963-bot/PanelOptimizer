# -*- coding: utf-8 -*-
"""Conditional end-to-end regression for the local real production panel."""

from __future__ import annotations

import tempfile
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
class RealPanelV500Tests(unittest.TestCase):
    """Exercise the exact Split Panel command when the local FCStd exists."""

    def test_real_final_panel_completes_and_reopens_four_stls(self):
        document = FreeCAD.openDocument(str(REAL_PANEL))
        try:
            source = document.getObject("FINAL_PANEL")
            self.assertIsNotNone(source)
            before = source.Shape.exportBrepToString()
            previous_selection = getattr(
                split_module.FreeCADGui, "Selection", None
            )
            split_module.FreeCADGui.Selection = SimpleNamespace(
                getSelection=lambda: [source]
            )
            with tempfile.TemporaryDirectory() as directory:
                command = split_module.PanelOptimizerSplitPanelCommand()
                command._select_output_directory = lambda: directory
                command.Activated()
                outputs = tuple(
                    Path(directory) / f"Part_{index}.stl"
                    for index in range(1, 5)
                )
                self.assertTrue(all(path.is_file() for path in outputs))
                self.assertTrue(all(path.stat().st_size > 0 for path in outputs))
            self.assertEqual(before, source.Shape.exportBrepToString())
        finally:
            if previous_selection is not None:
                split_module.FreeCADGui.Selection = previous_selection
            FreeCAD.closeDocument(document.Name)


if __name__ == "__main__":
    unittest.main()

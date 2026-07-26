# -*- coding: utf-8 -*-
"""Regression coverage for FreeCAD Mod-directory import semantics."""

from __future__ import annotations

import importlib
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import Part
except ImportError:  # pragma: no cover - exercised outside FreeCAD
    Part = None


@unittest.skipIf(Part is None, "FreeCAD Part module is unavailable")
class FreeCADLocalImportTests(unittest.TestCase):
    """Load runtime modules with only Mod/PanelOptimizer importable."""

    def test_commands_and_core_load_without_paneloptimizer_package(self):
        """Analyze runs through Core imports when its parent is unavailable."""
        repository = Path(__file__).resolve().parents[1]
        repository_parent = repository.parent
        isolated_path = [
            entry
            for entry in sys.path
            if os.path.abspath(entry or os.curdir)
            != os.path.abspath(repository_parent)
        ]
        isolated_path.insert(0, str(repository))

        with patch.object(sys, "path", isolated_path):
            sys.modules.pop("PanelOptimizer", None)
            self.assertIsNone(importlib.util.find_spec("PanelOptimizer"))

            analyze_module = importlib.import_module("Commands.AnalyzeCommand")
            importlib.import_module("Commands.SplitPanelCommand")
            importlib.import_module("Core.AnalyzerEngine")
            importlib.import_module("Core.SplitWorkflow")
            importlib.import_module("Core.SplitterEngine")
            importlib.import_module("Core.ExportEngine")

        shape = Part.makeBox(20, 20, 5)
        selected = types.SimpleNamespace(
            Name="ImportRegressionPanel",
            Label="Import regression panel",
            Shape=shape,
        )
        messages = []
        warnings = []
        freecad_stub = types.SimpleNamespace(
            ActiveDocument=object(),
            Console=types.SimpleNamespace(
                PrintMessage=messages.append,
                PrintWarning=warnings.append,
                PrintError=warnings.append,
            ),
        )
        freecad_gui_stub = types.SimpleNamespace(
            Selection=types.SimpleNamespace(
                getSelection=lambda: (selected,),
            ),
        )

        with patch.object(analyze_module, "FreeCAD", freecad_stub), patch.object(
            analyze_module,
            "FreeCADGui",
            freecad_gui_stub,
        ):
            analyze_module.PanelOptimizerAnalyzeCommand().Activated()

        self.assertEqual(warnings, [])
        self.assertTrue(any("Faces : 6" in message for message in messages))
        self.assertNotIn("PanelOptimizer", sys.modules)


if __name__ == "__main__":
    unittest.main()

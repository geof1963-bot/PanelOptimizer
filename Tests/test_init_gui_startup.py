# -*- coding: utf-8 -*-
"""Regression tests for FreeCAD workbench startup orchestration."""

from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class _WorkbenchStub:
    """Record workbench UI declarations without requiring a running GUI."""

    def __init__(self):
        self.toolbars = []
        self.menus = []
        self.context_menus = []

    def appendToolbar(self, name, commands):
        self.toolbars.append((name, tuple(commands)))

    def appendMenu(self, name, commands):
        self.menus.append((name, tuple(commands)))

    def appendContextMenu(self, name, commands):
        self.context_menus.append((name, tuple(commands)))


class InitGuiStartupTests(unittest.TestCase):
    """Execute InitGui using FreeCAD-style split globals and locals."""

    def test_startup_without_file_registers_one_workbench(self):
        """Path resolution and registration do not require ``__file__``."""
        user_data = os.path.join("C:\\", "FreeCADUserData")
        messages = []
        registered = []
        freecad = types.ModuleType("FreeCAD")
        freecad.getUserAppDataDir = lambda: user_data
        freecad.Console = types.SimpleNamespace(
            PrintMessage=messages.append,
        )
        freecad_gui = types.ModuleType("FreeCADGui")
        freecad_gui.addWorkbench = registered.append

        commands = types.ModuleType("Commands")
        commands.__path__ = ()
        analyze_command = types.ModuleType("Commands.AnalyzeCommand")
        split_command = types.ModuleType("Commands.SplitPanelCommand")
        module_stubs = {
            "FreeCAD": freecad,
            "FreeCADGui": freecad_gui,
            "Commands": commands,
            "Commands.AnalyzeCommand": analyze_command,
            "Commands.SplitPanelCommand": split_command,
        }
        source_path = Path(__file__).resolve().parents[1] / "InitGui.py"
        execution_globals = {
            "__name__": "PanelOptimizer_InitGui_startup_test",
            "Workbench": _WorkbenchStub,
            "FreeCAD": freecad,
            "FreeCADGui": freecad_gui,
            "os": os,
        }
        execution_locals = {}
        self.assertNotIn("__file__", execution_globals)
        self.assertNotIn("__file__", execution_locals)

        with patch.dict(sys.modules, module_stubs):
            source = source_path.read_text(encoding="utf-8")
            exec(
                compile(source, str(source_path), "exec"),
                execution_globals,
                execution_locals,
            )

            self.assertEqual(len(registered), 1)
            workbench = registered[0]
            expected_root = os.path.abspath(
                os.path.join(user_data, "Mod", "PanelOptimizer")
            )
            self.assertEqual(
                execution_locals["MODULE_DIRECTORY"],
                expected_root,
            )
            self.assertEqual(
                execution_locals["ICON_DIRECTORY"],
                os.path.join(
                    expected_root,
                    "Gui",
                    "Resources",
                    "icons",
                ),
            )
            self.assertEqual(
                workbench.Icon,
                execution_locals["WORKBENCH_ICON"],
            )

            workbench.Initialize()
            workbench.Activated()
            workbench.ContextMenu("View")
            workbench.Deactivated()

        expected_commands = (
            "PanelOptimizer_Analyze",
            "PanelOptimizer_SplitPanel",
        )
        self.assertEqual(
            workbench.toolbars,
            [("PanelOptimizer", expected_commands)],
        )
        self.assertEqual(
            workbench.menus,
            [("PanelOptimizer", expected_commands)],
        )
        self.assertEqual(
            workbench.context_menus,
            [("PanelOptimizer", expected_commands)],
        )
        self.assertTrue(any("activated" in message for message in messages))
        self.assertTrue(any("deactivated" in message for message in messages))


if __name__ == "__main__":
    unittest.main()

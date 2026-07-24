# PanelOptimizer – Master Specification

Version: 3.01
Status: Living document

---

# Project

PanelOptimizer is a FreeCAD Workbench dedicated to preparing large artistic panels for FDM 3D printing.

The workbench automatically analyzes a solid panel and splits it into printable parts while making the final assembly joints as invisible as possible.

This is a long-term professional software project.

---

# Primary objective

Starting from a single FreeCAD solid:

- analyze the geometry
- determine an optimal split strategy
- generate 4 printable solids
- export 4 STL files
- generate invisible joints
- minimize visible seams after assembly

---

# Printing constraints

Printer:

Creality K2 Plus

Maximum printable area accepted by PanelOptimizer:

330 mm × 330 mm

Final assembled panel:

594 × 594 mm

Thickness:

8 mm

Material:

PETG

---

# Invisible joint philosophy

Straight cuts should be avoided whenever possible.

Whenever geometry allows it, the cutting path should follow existing holes, curves or artistic shapes.

The objective is to make the joint disappear after:

- gluing
- dowel positioning
- polyester filler
- sanding
- painting

---

# Future capabilities

The workbench will eventually support:

- automatic geometry analysis
- candidate split generation
- split optimization
- join generation
- dowel generation
- STL export
- project report generation

---

# Software architecture

PanelOptimizer/

    Core/
        BaseObject.py
        Exceptions.py
        Settings.py
        Geometry.py
        Analyzer.py
        PathFinder.py
        Joinery.py
        Splitter.py
        Exporter.py

    Commands/

    Resources/

    Tests/

---

# Responsibilities

Geometry

Loads and analyzes FreeCAD geometry.

Analyzer

Detects interesting geometric areas.

PathFinder

Searches for optimal cutting paths.

Joinery

Creates invisible joints and dowels.

Splitter

Builds the final printable solids.

Exporter

Exports STL files and reports.

---

# Development rules

The project follows these principles:

- Python 3.11
- FreeCAD 1.1.x
- PEP8
- Type hints
- Docstrings
- Logging
- SOLID architecture
- One responsibility per class
- Modular design
- Git versioning

---

# Git workflow

Main branch

Stable versions only.

Develop branch

Daily development.

Codex branches

Created automatically when needed.

---

# Coding rules

Never duplicate code.

Prefer reusable classes.

Avoid large functions.

Always document public classes.

Avoid breaking existing APIs.

Raise explicit exceptions.

Never use magic numbers.

---

# Objective

PanelOptimizer must become a professional FreeCAD Workbench dedicated to preparing large decorative panels for FDM printing with invisible assembly joints.
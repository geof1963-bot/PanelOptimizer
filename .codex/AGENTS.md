# AGENTS.md

## Project

This repository contains the development of the FreeCAD workbench
PanelOptimizer.

The project is intended to become production-quality software.

---

## Mission

Your goal is NOT to generate isolated code snippets.

Your goal is to continuously improve the whole project while keeping the architecture clean and coherent.

Always think at repository scale.

---

## Main objective

Starting from one FreeCAD solid:

1. Analyze geometry.
2. Find an optimal split.
3. Produce four printable solids.
4. Generate invisible assembly joints.
5. Export STL files.

The generated parts must fit inside a 330 × 330 mm printable area.

---

## Technical constraints

Target software:

- FreeCAD 1.1.x
- Python 3.11

Printing:

- Creality K2 Plus
- PETG
- Final panel: 594 × 594 × 8 mm

---

## Architecture

Respect the existing architecture.

Core modules:

- BaseObject
- Exceptions
- Settings
- Geometry
- Analyzer
- PathFinder
- Joinery
- Splitter
- Exporter

Do not merge responsibilities between modules.

---

## Coding standards

Always use:

- PEP8
- type hints
- docstrings
- logging
- explicit exceptions

Never duplicate code.

Keep classes focused.

Keep functions reasonably short.

---

## Git

Never modify the main branch directly.

Work on dedicated Codex branches.

Produce clean commits.

Group related changes together.

---

## Before coding

Always inspect the repository first.

Reuse existing classes whenever possible.

Do not recreate functionality that already exists.

---

## When implementing a feature

Think about:

- maintainability
- readability
- extensibility
- robustness

Never optimize prematurely.

---

## FreeCAD

Never break compatibility with FreeCAD 1.1.x.

Avoid dependencies outside the Python standard library unless explicitly requested.

---

## Long-term objective

PanelOptimizer should become one of the most advanced FreeCAD workbenches dedicated to preparing large artistic panels for FDM printing with nearly invisible assembly joints.

Every contribution should move the project toward this objective.
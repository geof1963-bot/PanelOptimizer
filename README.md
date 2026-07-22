# PanelOptimizer

PanelOptimizer is a FreeCAD 1.1.x Workbench dedicated to preparing large artistic panels for FDM 3D printing.

The objective is **not simply to split a model**, but to optimize the finished assembled panel so that the joints become almost invisible after:

- 3D printing
- assembly
- epoxy gluing
- polyester filler
- sanding
- primer
- satin black painting

---

# Philosophy

Traditional STL splitters optimize the cut.

**PanelOptimizer optimizes the finished panel.**

The workbench searches for cut paths that naturally follow the existing geometry of the artwork in order to minimize the visibility of the joints.

The project is specifically designed for decorative panels, illuminated sculptures and wall art.

---

# Main Features

Current development roadmap:

- Geometry analysis
- Hole detection
- Region detection
- Corridor analysis
- Intelligent split planning
- Automatic panel splitting
- Invisible joinery generation
- Automatic dowel placement
- Chamfers and filler grooves
- STL export
- STEP export (future)

---

# Printing Constraints

Target printer:

- Creality K2 Plus

Maximum allowed size for each generated part:

- **330 × 330 mm**

This limit is mandatory.

Any generated solution exceeding this size must be rejected.

---

# Final Goal

Starting from a single FreeCAD solid, PanelOptimizer will:

1. Analyze the geometry.
2. Detect holes and natural corridors.
3. Compute several optimized split solutions.
4. Generate four printable solids.
5. Create invisible joinery.
6. Add dowel holes automatically.
7. Export four STL files ready for printing.

---

# Workbench Structure

```
PanelOptimizer/

├── Commands/
├── Core/
├── Export/
├── Gui/
├── Init.py
├── InitGui.py
├── metadata.txt
└── package.xml
```

---

# Core Modules

### Geometry

Basic geometric utilities.

### Analyzer

Geometry inspection and statistics.

### Splitter

Creation of the four printable solids.

### Joinery (future)

Generation of:

- chamfers
- filler grooves
- lips
- dowel holes
- assembly marks

### Exporter

Automatic STL generation.

---

# Development Principles

- Modular architecture
- No duplicated code
- No experimental macros
- One engine per feature
- Maintainable Python code
- GitHub-first development

---

# Current Version

**V3.01**

Status:

- Workbench architecture
- Core initialization
- GUI integration

---

# Repository

https://github.com/geof1963-bot/PanelOptimizer

---

# License

GPL-3.0-or-later

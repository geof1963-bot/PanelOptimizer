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

## V4.10 pragmatic macro split prototype

The current workbench reproduces the proven crossed-groove macro geometry:

1. Open a document and select one panel object.
2. Click **Macro Split Panel**.
3. PanelOptimizer copies the selected shape and cuts the macro's asymmetric
   full-length grooves at the source bounding-box X/Y center.
4. The document receives one `FINAL_PANEL_BEVELED` result object.

The source remains visible and unchanged. This path intentionally does not run
AnalyzerEngine and can therefore preserve the practical macro behavior on
deep-analysis-invalid input. Four-part extraction, printable-size validation,
four-file STL export, intelligent seams, path scoring, and joinery are not part
of V4.10.

The previous V4.00 `SplitterEngine`, result writer, and `ExportEngine` remain in
the repository for later evaluation and are not deleted by this mission.

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

**V4.00**

Status:

- Functional deterministic four-part solid split
- Effective printable-limit validation
- Transactional four-file STL export
- Existing analysis architecture

---

# Repository

https://github.com/geof1963-bot/PanelOptimizer

---

# License

GPL-3.0-or-later

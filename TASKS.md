# PanelOptimizer - Development Roadmap

Project Version: 3.x

Status: Active Development

---

# Phase 1 — Foundation

- [x] Create Git repository
- [x] Create workbench structure
- [x] Init.py
- [x] InitGui.py
- [x] BaseObject.py
- [x] Exceptions.py
- [x] Settings.py
- [x] Master specification
- [x] Codex instructions

---

# Phase 2 — Geometry Engine

Priority: HIGH

- [ ] Geometry.py
    - [ ] Load FreeCAD object
    - [ ] Read Shape
    - [ ] Bounding Box
    - [ ] Width
    - [ ] Height
    - [ ] Thickness
    - [ ] Area
    - [ ] Volume
    - [ ] Center
    - [ ] Faces
    - [ ] Edges
    - [ ] Vertices
    - [ ] Validation

---

# Phase 3 — Analyzer

Priority: HIGH

- [ ] Detect islands
- [ ] Detect holes
- [ ] Detect thin bridges
- [ ] Detect printable limits
- [ ] Build analysis report

---

# Phase 4 — PathFinder

Priority: VERY HIGH

- [ ] Generate candidate split paths
- [ ] Follow artistic curves
- [ ] Avoid straight cuts whenever possible
- [ ] Compute split cost
- [ ] Rank solutions

---

# Phase 5 — Joinery

Priority: VERY HIGH

- [ ] Dowel generation
- [ ] Alignment
- [ ] Invisible joint geometry
- [ ] Assembly helpers

---

# Phase 6 — Splitter

Priority: VERY HIGH

- [ ] Build printable solids
- [ ] Verify 330 mm limit
- [ ] Produce four independent solids

---

# Phase 7 — Export

Priority: HIGH

- [ ] STL export
- [ ] Project report
- [ ] Export settings

---

# Phase 8 — Commands

- [ ] AnalyzeCommand
- [ ] SplitPanelCommand
- [ ] ExportCommand

---

# Phase 9 — User Interface

- [ ] Toolbar
- [ ] Icons
- [ ] Preferences
- [ ] Task panels

---

# Phase 10 — Tests

- [ ] Geometry tests
- [ ] Analyzer tests
- [ ] Split tests
- [ ] Regression tests

---

# Phase 11 — Documentation

- [ ] API documentation
- [ ] User manual
- [ ] Examples
- [ ] Tutorials

---

# Long-term objective

PanelOptimizer should become the reference FreeCAD workbench for preparing large artistic panels for FDM printing with nearly invisible assembly joints.
# PanelOptimizer V1.0
# Software Architecture

---

# 1. Purpose

PanelOptimizer is a FreeCAD Workbench dedicated to automatically preparing large artistic panels for FDM 3D printing.

Its objective is not simply to split a model.

Its objective is to **find the best possible split** according to geometric, mechanical and aesthetic criteria.

The final result must consist of several printable blocks while making assembly joints as invisible as possible.

---

# 2. Global Processing Pipeline

```
FreeCAD Object

        │

        ▼

Validation

        │

        ▼

Geometry Analysis

        │

        ▼

Topology Analysis

        │

        ▼

Feature Detection

        │

        ▼

Cut Corridor Generation

        │

        ▼

Candidate Generation

        │

        ▼

Rule Engine

        │

        ▼

Candidate Ranking

        │

        ▼

User Selection

        │

        ▼

Splitter

        │

        ▼

Joinery Generator

        │

        ▼

STL Export
```

Every stage enriches the project knowledge.

No stage modifies the original model.

---

# 3. Architectural Layers

PanelOptimizer is divided into four independent layers.

```
User Interface

↓

Commands

↓

Engine

↓

Export
```

Each layer has only one responsibility.

---

# 4. Geometry Engine

Responsible for understanding the geometry.

Modules:

- Face Analyzer
- Edge Analyzer
- Vertex Analyzer
- Surface Classifier

Output:

Geometry Database

---

# 5. Topology Engine

Responsible for relationships.

Questions answered:

- Which faces touch each other?
- Which edges belong to each face?
- Which loops form holes?
- Which regions are connected?

Output:

Topology Graph

---

# 6. Feature Engine

Responsible for recognizing meaningful geometric entities.

Examples:

- Circular hole
- Decorative opening
- Island
- Thin branch
- External contour
- Text
- Logo
- Fillet
- Chamfer

Output:

Feature List

---

# 7. Corridor Engine

Responsible for locating areas where a split would be visually acceptable.

A corridor is not a cut.

A corridor is a region where a cut could travel.

Output:

Cut Corridors

---

# 8. Candidate Generator

Generates hundreds or thousands of possible split solutions.

Each solution contains:

- split curves
- resulting blocks
- estimated dimensions

No quality judgement is performed here.

---

# 9. Rule Engine

Scores every candidate.

Each rule is completely independent.

Examples:

Rule_MaxPrinterSize

Rule_HideJoint

Rule_FollowHole

Rule_FollowCurve

Rule_BlockBalance

Rule_Strength

Rule_Printability

Rules can be enabled, disabled or weighted.

---

# 10. Candidate Ranking

Sorts all generated candidates.

Produces:

Top 5

Top 10

Top 20

Only the highest ranked candidates are presented.

---

# 11. User Decision

The user remains in control.

The software proposes.

The user decides.

---

# 12. Split Engine

Creates the real split surfaces.

Produces independent solids.

---

# 13. Joinery Engine

Creates assembly features.

Possible future systems:

- Flat joints
- Pins
- Keys
- Puzzle joints
- Dovetails

---

# 14. Export Engine

Exports:

- STL
- STEP
- FreeCAD document

---

# 15. Design Principles

The architecture follows these principles.

• One module = one responsibility.

• No duplicated calculations.

• No GUI code inside the Engine.

• The original model is never modified.

• Every stage enriches the analysis.

• Every module can be tested independently.

• Every future improvement should require adding modules rather than rewriting existing ones.

---

# 16. Long-term Vision

PanelOptimizer is not a splitter.

It is an optimization engine dedicated to preparing complex artistic models for additive manufacturing.

The software searches for the best possible compromise between:

- aesthetics
- strength
- printability
- assembly quality
- manufacturing time

The chosen split is therefore the result of an optimization process rather than a predefined algorithm.
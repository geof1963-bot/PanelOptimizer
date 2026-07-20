# PanelOptimizer V1.0
# Data Model

---

# Philosophy

The Engine never works directly on FreeCAD objects.

The Engine works on its own data model.

FreeCAD objects are converted into Engine objects during the analysis stage.

This guarantees modularity and future portability.

---

# Main Objects

```
Model

│

├── Faces

├── Edges

├── Vertices

├── Features

├── Corridors

├── Candidates

└── Blocks
```

---

# FaceData

Represents one BRep face.

Properties

- id
- type
- area
- center
- normal
- bounding_box

Classification

- planar
- cylindrical
- conical
- spherical
- bspline

Orientation

- horizontal
- vertical

Topology

- neighbour_faces
- edges
- vertices

Flags

- printable
- candidate
- visited

---

# EdgeData

Represents one edge.

Properties

- id
- type
- length
- tangent

Topology

- adjacent_faces

Flags

- external
- internal

---

# VertexData

Represents one vertex.

Properties

- id
- position

Topology

- connected_edges

---

# FeatureData

Represents one meaningful geometric entity.

Examples

- hole

- island

- branch

- contour

- text

- logo

- pocket

Properties

- type

- faces

- edges

- bounding_box

- importance

---

# CorridorData

Represents one possible split corridor.

Properties

- id

- feature

- faces

- edges

- width

- visibility_score

- strength_score

---

# CutCandidate

Represents one complete split proposal.

Contains

- cut curves

- generated blocks

- estimated dimensions

- estimated print time

- score

---

# BlockData

Represents one printable block.

Properties

- volume

- dimensions

- center_of_mass

- printable

- orientation

- estimated_print_time

---

# AnalysisResult

Contains every result produced during analysis.

```
AnalysisResult

│

├── Geometry

├── Topology

├── Features

├── Corridors

├── Candidates

└── Statistics
```

---

# Statistics

Stores global information.

Examples

- face count

- edge count

- feature count

- corridor count

- candidate count

- block count

---

# RuleScore

Stores scoring information.

Example

Rule_MaxSize

+100

Rule_HideJoint

+25

Rule_Strength

−15

Total Score

92

---

# Relationships

```
Model

│

├── FaceData

│

├── EdgeData

│

├── VertexData

│

└── FeatureData

↓

CorridorData

↓

CutCandidate

↓

BlockData
```

---

# Design Rules

Every object is immutable once produced.

Each Engine module enriches the model.

No module destroys previous information.

The complete model always remains available.

---

# Long-term Goal

The Data Model must be independent from:

- FreeCAD

- GUI

- STL

- STEP

It represents the internal knowledge of the Engine.
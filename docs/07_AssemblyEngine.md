# PanelOptimizer V1.0
# 07_AssemblyEngine.md

---

# Philosophy

The purpose of PanelOptimizer is not to generate printable parts.

Its purpose is to design an invisible assembly.

The printed parts are only a consequence.

The Assembly Engine is responsible for transforming a printable model into an assembly that becomes visually and tactually invisible after:

- printing
- gluing
- filler application
- curing
- sanding
- painting

---

# Global Architecture

```
Geometry Engine

↓

Topology Engine

↓

Feature Engine

↓

Assembly Engine

↓

Splitter

↓

Export
```

The Assembly Engine becomes the heart of the project.

---

# Responsibilities

The Assembly Engine must determine:

- where the joint should pass

- which profile the joint should use

- where dowels should be inserted

- how many dowels are required

- glue surfaces

- filler reserve

- expected mechanical behaviour

- expected finishing quality

---

# Internal Modules

```
Assembly Engine

│

├── Joint Planner

├── Joint Profile Generator

├── Dowel Planner

├── Glue Analyzer

├── Filler Analyzer

├── Strength Analyzer

└── Assembly Evaluator
```

---

# Joint Planner

Purpose

Determine the best joint path.

Input

Geometry

Topology

Features

Output

Joint Path

The path should:

- avoid visible regions

- follow decorative openings whenever possible

- minimise visual impact

---

# Joint Profile Generator

Purpose

Generate the joint cross-section.

The profile is independent from the path.

Parameters

Opening width

Depth

Bottom width

Chamfer angle

Internal radius

Residual thickness

The profile may vary continuously along the joint.

---

# Dowel Planner

Purpose

Automatically position alignment dowels.

Input

Joint path

Panel thickness

Available material

Output

Complete dowel layout

Each dowel stores

Position

Diameter

Length

Insertion depth

Assembly direction

Clearance

Accessibility

---

# Dowel Placement Rules

Never place a dowel

- too close to an edge

- inside a decorative hole

- inside a thin branch

Maintain

minimum material thickness

Prefer

staggered placement

Avoid

perfect alignment of every dowel

The number of dowels is calculated automatically.

---

# Glue Analyzer

Purpose

Estimate bonding quality.

Evaluates

Bonding surface

Glue accessibility

Glue continuity

Glue volume

---

# Filler Analyzer

Purpose

Estimate the probability of obtaining an invisible repair.

Evaluates

Filler volume

Filler depth

Expected shrinkage

Sanding accessibility

Paint continuity

This module directly targets the final visual quality.

---

# Strength Analyzer

Purpose

Estimate the mechanical behaviour.

Evaluates

Remaining material

Stress concentration

Assembly rigidity

Handling resistance

---

# Assembly Evaluator

Purpose

Compute the global assembly score.

Evaluation categories

Geometry

Assembly

Strength

Repair

Printing

Aesthetics

The Engine never evaluates only the split.

It evaluates the complete assembly.

---

# AssemblyData

The Assembly Engine produces one object.

```
AssemblyData

Joint

Profile

Dowels

Glue

Filler

Strength

Score
```

This object becomes the reference for every following operation.

---

# Design Philosophy

The joint is not considered a cut.

It is considered a future repaired surface.

Every decision should maximise the probability that the repair becomes invisible.

---

# Future Extensions

Possible future assembly systems

Wood dowels

Printed pins

Rectangular keys

Continuous splines

Puzzle joints

Dovetails

Magnetic alignment

Hybrid systems

The architecture must remain compatible with all future assembly methods.

---

# Ultimate Goal

The success of PanelOptimizer is not measured by the quality of the split.

It is measured by the quality of the finished artwork.

After assembly, filler, sanding and painting:

The observer should be unable to determine where the object was divided.

Neither visually.

Nor by touch.

This is the primary optimisation objective of the Assembly Engine.
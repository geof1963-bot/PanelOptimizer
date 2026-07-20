# PanelOptimizer V1.0
# 08_DesignPrinciples.md

---

# Design Philosophy

PanelOptimizer is not a CAD automation tool.

It is a decision engine.

Its purpose is to analyse a printable model and propose the best assembly strategy according to engineering and artistic criteria.

---

# Primary Objective

The optimisation target is not the cut.

The optimisation target is the finished artwork.

Every algorithm must contribute to this objective.

---

# Fundamental Principles

## 1

Never optimise one criterion alone.

Always optimise the global assembly.

---

## 2

The original model is never modified.

Every operation creates a new result.

---

## 3

Geometry analysis must remain independent from optimisation.

---

## 4

The optimisation engine must remain independent from FreeCAD.

---

## 5

Every module has only one responsibility.

---

## 6

Every generated solution must be explainable.

The Engine must never produce a "black box" decision.

---

## 7

The user always remains in control.

The software proposes.

The user decides.

---

# Engineering Priorities

The Engine always seeks the best compromise between

Invisible repair

↓

Mechanical strength

↓

Assembly simplicity

↓

Printability

↓

Printing time

↓

Material consumption

---

# Hard Constraints

These constraints are mandatory.

Maximum printer size

Valid solids

Printable geometry

Assembly feasibility

If one constraint fails

↓

Candidate rejected

---

# Soft Constraints

Soft constraints improve quality.

Hidden joint

Balanced blocks

Reduced filler

Reduced sanding

Reduced print time

Improved glue surface

Higher rigidity

---

# User Preferences

The user may choose optimisation priorities.

Examples

Invisible finish

Maximum strength

Fast printing

Easy assembly

Minimal filler

Professional finish

The optimisation adapts without changing the Engine.

---

# Explainability

Every solution must explain

Why this path

Why these dowels

Why this profile

Why this score

The Engine should never produce unexplained results.

---

# Modularity

Every future improvement should consist of

adding modules

rather than

rewriting existing ones.

---

# Experimental Validation

Whenever possible

engineering decisions should be based on

real printed experiments

rather than assumptions.

Joint profiles

Glue behaviour

Filler shrinkage

Sanding quality

Painting results

become part of the Engine knowledge.

---

# Long-Term Vision

PanelOptimizer should progressively accumulate practical manufacturing knowledge.

The software therefore evolves not only by adding algorithms,

but also by learning from experimental results.

Its ultimate purpose is to maximise the quality of the finished artistic panel rather than the quality of the digital split.
# PanelOptimizer V1.0
# 06_JointProfiles.md

---

# Philosophy

The objective of PanelOptimizer is **not** to split a model.

Its objective is to create an assembly joint that becomes invisible after:

- printing
- gluing
- filler application
- curing
- sanding
- painting

The split itself is only a manufacturing operation.

The real product designed by the Engine is the **joint**.

---

# Design Objective

After finishing, the joint must satisfy two conditions.

## Visual

No visible line under normal lighting.

## Tactile

No detectable depression or ridge when running a finger across the surface.

This second criterion is mandatory.

---

# Fundamental Principle

The Engine does not optimise:

• a cut

It optimises:

• the future repair.

The joint geometry must therefore anticipate:

- filler shrinkage
- sanding
- paint thickness
- long-term stability

---

# Joint Structure

A joint is composed of two independent elements.

```
Joint Path

↓

Joint Profile
```

The path defines **where** the joint is located.

The profile defines **how** the material is removed.

Both are optimized independently.

---

# Joint Parameters

Each profile is defined by measurable parameters.

```
Opening Width (W)

Depth (D)

Residual Thickness (T)

Bottom Width (B)

Side Angle (A)

Internal Radius (R)

Glue Surface (G)

Filler Volume (V)

Assembly Direction
```

---

# Profile Families

## JP-01

Simple asymmetrical bevel.

```
\__|
```

Current reference profile.

Advantages

- simple machining

- easy positioning

Weaknesses

- limited filler reserve

- sharp internal corner

---

## JP-02

Rounded bottom.

```
\__)
```

Advantages

- reduced stress concentration

- improved filler adhesion

---

## JP-03

Large radius profile.

```
\____)
```

Designed to minimise visible shrinkage.

---

## JP-04

Large filler reservoir.

```
\_______)
```

Maximum filler volume.

Used for highly visible surfaces.

---

## JP-05

Spline profile.

Smooth continuous curvature.

Designed for premium artistic finishes.

---

## JP-06

Variable profile.

The profile changes continuously along the joint.

Example

Near decorative holes

↓

small profile

Large flat areas

↓

larger profile

---

# Evaluation Criteria

Every profile is evaluated using the following criteria.

## Filler Volume

Higher is generally better.

---

## Glue Surface

Must remain sufficient.

---

## Structural Strength

The remaining material must resist handling.

---

## Printability

The joint must remain printable without defects.

---

## Sanding Accessibility

The filler must remain easy to sand.

---

## Shrinkage Resistance

Primary criterion.

The profile should minimise visible depressions after curing.

---

## Visual Invisibility

No visible line after painting.

---

## Tactile Invisibility

No detectable discontinuity.

This is considered the ultimate success criterion.

---

# Experimental Validation

Every profile should be experimentally validated.

Procedure

Print

↓

Glue

↓

Apply filler

↓

Wait

↓

Sand

↓

Prime

↓

Paint

↓

Inspect

↓

Touch

↓

Score

The experimental score becomes the reference.

---

# Future Adaptive Profiles

Future versions of PanelOptimizer may generate custom profiles automatically.

The profile width

depth

radius

or asymmetry

may vary continuously depending on:

- local geometry

- visibility

- structural importance

- finishing requirements

---

# Long-Term Vision

PanelOptimizer should not simply determine where to split a model.

It should determine which joint geometry offers the highest probability of becoming completely invisible after the entire finishing process.

The optimisation target is therefore not the cut itself.

The optimisation target is the finished artwork.
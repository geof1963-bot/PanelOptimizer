# PanelOptimizer V1.0
# Rule Engine

---

# Philosophy

The Rule Engine evaluates every split candidate.

It never creates candidates.

It only scores them.

Each rule is completely independent.

The final score is the weighted sum of all enabled rules.

---

# Evaluation Pipeline

```
Candidate

↓

Rule 1

↓

Rule 2

↓

Rule 3

↓

...

↓

Final Score
```

---

# Rule Categories

The rules are divided into categories.

Geometry

Topology

Mechanical

Printing

Aesthetics

User Preferences

---

# Geometry Rules

## Rule_MaxPrinterSize

Purpose

Every block must fit inside the printer volume.

Weight

Mandatory

Failure

Candidate rejected.

---

## Rule_BlockBalance

Purpose

Keep all blocks approximately the same size.

Score

Higher if volumes are balanced.

---

## Rule_MinimumThickness

Purpose

Avoid creating fragile thin walls.

---

# Topology Rules

## Rule_FollowExistingContours

Reward cuts following existing geometry.

---

## Rule_AvoidIslands

Avoid isolating small decorative elements.

---

## Rule_PreserveConnectivity

Prevent unnecessary fragmentation.

---

# Mechanical Rules

## Rule_Strength

Avoid cuts through structurally important regions.

---

## Rule_GlueSurface

Maximize bonding area.

---

## Rule_AssemblyAccessibility

Ensure assembly remains practical.

---

# Printing Rules

## Rule_Printability

Each block must remain printable.

---

## Rule_MinimizeSupports

Prefer orientations requiring fewer supports.

---

## Rule_PrintTime

Reduce total printing time.

---

# Aesthetic Rules

## Rule_HideJoint

The joint should be difficult to see.

---

## Rule_FollowHole

Prefer cuts following decorative holes.

---

## Rule_FollowCurve

Prefer natural curves.

---

## Rule_AvoidFlatArea

Avoid visible cuts across large flat surfaces.

---

## Rule_Symmetry

Prefer visually balanced solutions.

---

# User Rules

The user may change rule weights.

Example

```
HideJoint

100

Strength

80

PrintTime

20

GlueSurface

40
```

---

# Rule Result

Each rule returns

```
RuleResult

Name

Score

Maximum

Comment
```

Example

```
HideJoint

92 /100

Joint follows decorative holes.
```

---

# Candidate Score

The final score contains

Geometry

Topology

Mechanical

Printing

Aesthetic

Total

---

# Candidate Explanation

Every proposed solution explains its score.

Example

```
Total

93

Advantages

+ follows decorative openings

+ balanced blocks

+ invisible joint

Weaknesses

− slightly longer print time
```

The Engine should always explain its decisions.

---

# Candidate Ranking

Candidates are sorted by score.

Only the highest ranked candidates remain.

Typical values

Generated

1000

Ranked

100

Displayed

5

---

# Rule Interface

Every future rule follows the same interface.

```
evaluate(candidate, model)

↓

RuleResult
```

The Rule Engine never knows the internal implementation.

It only aggregates results.

---

# Rule Independence

Rules never communicate directly.

Each rule only analyses the candidate.

This guarantees modularity.

---

# Future Rule Plugins

Future versions should load rules automatically.

Example

```
Rules/

Rule_MaxPrinterSize.py

Rule_HideJoint.py

Rule_Strength.py

Rule_UserPreference.py
```

Adding a new rule should require no modification of the Rule Engine.

---

# Long-Term Vision

The Rule Engine transforms PanelOptimizer from a geometric splitter into a decision engine.

The software does not search for one split.

It evaluates thousands of possible solutions and recommends the most suitable ones according to engineering and artistic criteria.
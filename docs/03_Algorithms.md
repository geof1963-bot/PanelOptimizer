# PanelOptimizer V1.0
# Algorithms

---

# Philosophy

PanelOptimizer is not a splitter.

PanelOptimizer is an optimization engine.

Its goal is to search, evaluate and rank possible split solutions.

No solution is predefined.

The software discovers the best candidates automatically.

---

# Global Workflow

```
Input Model

↓

Validation

↓

Geometry Analysis

↓

Topology Analysis

↓

Feature Extraction

↓

Corridor Detection

↓

Candidate Generation

↓

Rule Evaluation

↓

Ranking

↓

User Selection

↓

Split Generation

↓

Joinery Generation

↓

Export
```

---

# Stage 1

Geometry Analysis

Input

FreeCAD Shape

Output

Geometry Database

Tasks

- Read all faces
- Read all edges
- Read all vertices
- Compute normals
- Compute bounding boxes
- Classify surfaces

---

# Stage 2

Topology Analysis

Input

Geometry Database

Output

Topology Graph

Tasks

- Detect adjacency
- Detect loops
- Detect connected regions
- Detect external contour

---

# Stage 3

Feature Detection

Input

Topology Graph

Output

Feature List

Possible Features

- holes

- islands

- branches

- thin regions

- decorative openings

- text

- logos

---

# Stage 4

Corridor Detection

Input

Feature List

Output

Corridor List

A corridor represents a preferred area for a future split.

Possible corridor sources

- hole contours

- decorative curves

- thin branches

- existing edges

- hidden regions

---

# Stage 5

Candidate Generation

Input

Corridors

Output

Candidate List

The generator combines corridors into complete split solutions.

Hundreds or thousands of candidates may be created.

---

# Stage 6

Rule Evaluation

Input

Candidates

Output

Scored Candidates

Each candidate is evaluated independently.

Each rule contributes to the final score.

---

# Stage 7

Ranking

Candidates are sorted.

Only the best candidates remain.

Typical values

Generated

1000

Kept

20

Displayed

5

---

# Stage 8

User Selection

The user compares the proposed solutions.

The Engine never chooses automatically.

The final decision belongs to the user.

---

# Stage 9

Split Generation

Creates

- split surfaces

- independent solids

The original object remains unchanged.

---

# Stage 10

Joinery

Possible systems

- flat joints

- pins

- puzzle

- dovetail

- keys

---

# Stage 11

Export

Creates

STL

STEP

FreeCAD Document

---

# Candidate Generation Strategy

The Generator should never search randomly.

Instead it combines meaningful corridors.

Example

Hole A

↓

Hole B

↓

Outer contour

↓

Candidate

---

# Rule Engine

Each rule produces a partial score.

Example

MaxSize

+100

HiddenJoint

+40

BalancedBlocks

+25

WeakRegion

−60

Total

105

---

# Optimization Loop

```
Generate Candidate

↓

Evaluate

↓

Score

↓

Keep Best

↓

Generate Next
```

---

# Stopping Criteria

Generation stops when

- enough candidates exist

or

- no better candidate is found

or

- computation time limit reached

---

# Future Improvements

Possible future algorithms

Genetic Algorithm

Simulated Annealing

Monte Carlo

A*

Graph Search

Machine Learning

The architecture should remain compatible with future optimization methods.

---

# Long-Term Vision

PanelOptimizer should evolve into a generic optimization engine capable of finding aesthetically and mechanically optimal split strategies for any printable artistic object.
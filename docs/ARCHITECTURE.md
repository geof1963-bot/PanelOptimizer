Mission V3.06A - Create ARCHITECTURE.md

Read the repository before making changes.

Objective

Create a new document:

docs/ARCHITECTURE.md

This document becomes the technical reference for the whole project.

It must describe the architecture only.

It must NOT describe implementation details.

It must NOT contain algorithms.

It must remain valid even if future implementations change.

The document should contain the following sections.

----------------------------------------------------

# 1. Vision

Explain the purpose of PanelOptimizer.

PanelOptimizer is a FreeCAD workbench whose goal is to intelligently split large printable panels into smaller printable parts while minimizing the visibility of assembly joints.

The project is intended to become a generic panel optimization engine rather than a solution dedicated to one artwork.

----------------------------------------------------

# 2. Core Principles

Describe the fundamental principles:

- Single Responsibility
- Immutable data models
- Pipeline architecture
- No global state
- Dependency Injection
- Explicit data contracts
- Deterministic algorithms whenever possible

----------------------------------------------------

# 3. Global Pipeline

Describe the complete pipeline.

FreeCAD Shape

↓

GeometryEngine

↓

GeometrySnapshot

↓

AnalyzerEngine

↓

AnalysisReport

↓

PathFinderEngine

↓

SplitPlan

↓

JoineryEngine

↓

JoineryPlan

↓

SplitterEngine

↓

PrintablePart[]

↓

ExportEngine

↓

ExportReport

Explain the responsibility of every stage.

----------------------------------------------------

# 4. Engine Responsibilities

Describe every engine.

GeometryEngine

AnalyzerEngine

PathFinderEngine

JoineryEngine

SplitterEngine

ExportEngine

Each engine must explain:

Purpose

Inputs

Outputs

What it MUST NOT do

----------------------------------------------------

# 5. Data Models

Describe every model contained in Core.Models.

Explain why models are immutable.

Explain why they never contain business logic.

----------------------------------------------------

# 6. Dependency Rules

Document the dependency rules.

Engines communicate only through Core.Models.

No engine imports another engine.

GUI never contains business logic.

Commands never implement algorithms.

Geometry models never know FreeCAD documents.

----------------------------------------------------

# 7. Future Evolution

Explain that new engines may appear later.

Examples:

MeshAnalyzer

CostOptimizer

OrientationOptimizer

SupportOptimizer

SimulationEngine

without modifying existing engines.

----------------------------------------------------

# 8. Development Rules

Every commit must implement one coherent feature.

Architecture first.

Implementation second.

Tests before optimisation.

No magic numbers.

Settings centralized.

----------------------------------------------------

# 9. Long-Term Vision

Describe the ambition.

PanelOptimizer should become a reusable optimization framework capable of supporting multiple manufacturing technologies and future optimization engines.

----------------------------------------------------

Use Markdown.

Use Mermaid diagrams where appropriate.

Keep the document clear, professional and implementation-independent.

When finished:

1. List every created or modified file.
2. Summarize the architecture in a few sentences.
3. Wait for approval before changing any source code.
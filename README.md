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

## V4.26 watertight mesh output

The current workbench reproduces the proven crossed-groove geometry and then
extracts four printable parts:

1. Open a document and select one panel object.
2. Click **Split Panel**.
3. PanelOptimizer copies the selected shape and cuts the macro's asymmetric
   full-length grooves at the source bounding-box X/Y center.
4. A `0.5 mm` full-depth section continuing from each groove bottom directly
   separates the result into four solids during the two macro-style cuts.
5. The fixed V4.24 tessellation is applied to each solid. Planar open boundary
   components are reconstructed locally without changing the B-rep; nested
   loops remain holes and ambiguous non-planar components are rejected.
6. The document receives `PanelOptimizer_Result` with `Part_1` through
   `Part_4` in deterministic quadrant order.
7. If every part satisfies `Settings.Split.MAX_PART_WIDTH/HEIGHT`, select an
   output directory for transactional `Part_1.stl` through `Part_4.stl` export.
   All four files are reopened and must be watertight before commit.

The source remains visible and unchanged. This path intentionally does not run
AnalyzerEngine and can therefore preserve the practical macro behavior on
deep-analysis-invalid input. Each V4.21 part must nevertheless be one closed,
positive-volume solid. Mesh patching accepts only deterministic planar boundary
cycles, creates no B-rep geometry, and preserves part bounds and coherent
volume. No SliceAPI, general-fuse, global remeshing, or generic hole filling is
used. Intelligent seams, path scoring, automatic offset optimization, and
joinery are not part of V4.26.

The previous fixed-split `SplitterEngine`, result writer, and `ExportEngine` remain in
the repository for later evaluation and are not deleted by this mission.

## V4.30 practical sinuous seams

The Split Panel command now extracts inner wires from the panel's largest
horizontal top face without invoking AnalyzerEngine. Within a configurable
30 mm corridor it may approach and follow a simplified monotone portion of an
opening boundary, while keeping a 12 mm straight exclusion zone around the
single X/Y seam intersection. Offsets retain their V4.21 sign convention.

The existing asymmetric groove and full-depth slot are applied as overlapping,
united straight profile segments along each selected XY path. Candidate routes
are tried conservatively: any result other than exactly four solids is rejected,
then a one-seam detour or the proven straight fallback is attempted. Final
printability, V4.26 watertight reconstruction, and transactional four-STL
validation remain unchanged. Two owned lightweight preview objects show the
actual accepted paths in the document. No global graph solver or scoring
system is involved.

## V4.40 assembly-alignment dowel holes

After V4.30 has produced exactly four transient solids, `DowelPlanner` splits
the accepted seams into the four mating branches and targets three positions
per branch. Candidate points start at 25/50/75 percent of branch arc length and
move deterministically in 5 mm increments when required. The planner enforces
the configured center and outer-edge exclusions, checks a 2 mm material margin
against sampled opening boundaries, and performs local B-rep subtraction tests
to prove that exactly the intended pair of parts contains material at the
candidate cylinder.

Each accepted 4.3 mm diameter, 30 mm long horizontal cutter is centered on the
seam at `ZMin + 2.5 mm`; its axis is the canonical XY normal to the local seam
tangent. The same cylinder is subtracted from only the two mating transient
parts, which makes the paired holes coaxial. The source and seam paths remain
unchanged. `PanelOptimizer_Dowels` previews the planned cylinders, while only
the four drilled parts proceed to the unchanged V4.26 mesh and transactional
    STL pipeline. No dowel solid, strength score, lip, or other joinery is created.

## Connectivity-aware region repair

Explicit sinuous XY ownership remains the current partition strategy. If an
artistic opening and a local seam detour isolate a secondary material
component, region extraction records its volume, bounds, centroid, nearest seam
segment/detour, and opening distance. A bounded local search then shortens only
that contour-following detour and rebuilds all four regions. The repaired route
must retain curved vertical and horizontal seams, one crossing, protected hole
profiles, printable dimensions, and exactly one physical solid per region
before dowels, lips, mesh repair, or STL export can run. Search is limited to
eight exact repair attempts and 20 seconds; disconnected material is never
fused or bridged.

## V4.74B non-structural B-rep slivers

Before connectivity repair is considered, every secondary ownership solid is now
classified independently. A component is ignored only when absolute volume,
volume ratio, Z-thickness ratio, and XY footprint are all below conservative
configured limits, it lies close to a seam or artistic boundary, and it does
not touch the panel exterior. Any substantial or silhouette-relevant signal
keeps the component structural and sends it through the unchanged local
connectivity-repair path. Confirmed slivers are neither fused nor bridged;
they are omitted from the printable region and recorded in extraction
diagnostics. The existing watertight, single-component mesh and reopened-STL
checks remain the final authority for all four parts.

V4.74C records every individual classifier predicate in the extraction
diagnostics. Sparse fragments use a conservative 300 mm² bounding-box
footprint limit, while opening and seam proximity are supporting evidence and
not structural vetoes. Silhouette protection is evaluated against a surface
extruded from the original panel top face's `OuterWire`; internal artistic-hole
wires and transient seam/region boundaries are not included.

V4.74D extends connectivity repair to multiple structural islands. Classified
slivers remain excluded, while structural islands are prioritized by volume
and seam distance. A bounded greedy beam emits one local curved level reduction
per responsible detour, exactly rebuilds all four regions, and keeps a child
only when structural component count or isolated volume improves. Multiple
detours may therefore be reduced progressively without resetting either seam.
Search retains the best state and is bounded to 12 repair steps, 12 exact
connectivity validations, and 30 seconds. Diagnostics include raw, sliver, and
structural counts plus the complete per-detour repair history.

V4.75 makes connected-region partitioning the sole Split Panel production
path. The GUI command delegates seam generation, ownership extraction, sliver
classification, progressive repair, and final `1/1/1/1` validation to one
orchestrator. Post-cutter multi-solid results now raise structured connectivity
evidence instead of the former immediate extraction error. Historical reserve
routes and raw `solid_count == 4` acceptance are no longer used. Dowels, lips,
mesh generation, and STL export begin only after all four region connectivity
counts are exactly one. Normal command output starts with
`PanelOptimizer Split Pipeline V5.10` and reports raw/sliver/structural counts
for every final region.

Structural-fragment classification uses the effective material footprint
(`volume / Z thickness`) instead of XY bounding-box extent. Volume ratio,
thickness ratio, effective area, and original exterior/silhouette protection
jointly determine whether secondary material is structural. Production logs
record both bounding-box and effective footprints for every secondary
component.

V4.77 adds one bounded residual mesh-closure pass after the existing V4.26
local reconstruction. It triangulates only closed loops of at most eight open
edges with small perimeter and area, uses existing boundary vertices without
smoothing, and retains the final manifold, component, solid, bounds, volume,
and reopened-STL validations. Large intentional openings remain rejected.

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

**V5.10**

Status:

- Real `FINAL_PANEL` production pipeline validated end-to-end
- Both seams follow real artistic contours, including a connected vertical route
- Bounded staged dowel planning and batched drilling/lip construction
- Watertight transactional four-file STL export and reopen validation
- Curved vertical exit transitions remove long straight visual bridges; route,
  split, and lip stages retain detailed production diagnostics.
- Execution-local OCC reuse consolidates surface extraction and shared lip
  candidate clipping without persistent caches or geometry-policy changes.

---

# Repository

https://github.com/geof1963-bot/PanelOptimizer

---

# License

GPL-3.0-or-later

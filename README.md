# PanelOptimizer

PanelOptimizer is a FreeCAD Workbench dedicated to preparing large artistic panels for FDM 3D printing.

## Goal

Automatically split a large panel into printable parts while preserving the visual continuity of the artwork.

The workbench is designed for decorative panels with complex openings and organic curves.

## Main Features

- Analyze a 3D panel.
- Detect printable boundaries.
- Automatically divide the model into four printable blocks.
- Keep each block below the printer size limit (330 mm).
- Generate invisible joints following the existing geometry.
- Export one STL file per block.

## Target Printer

- Creality K2 Plus

## Development Status

Early development.

## Roadmap

- Geometry analyzer
- Boundary detection
- Path optimizer
- Automatic splitter
- Joinery generator
- STL exporter

## License

MIT License
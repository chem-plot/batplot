# Changelog

## [1.8.46] - 2026-07-07
- Added Histogram mode, use batplot -h to learn more


## [1.8.45] - 2026-06-30
- Bug fixes with backend setting


## [1.8.44] - 2026-06-25
- Bug fixes


## [1.8.43] - 2026-06-25
- Bug fixes


## [1.8.42] - 2026-06-12
- Bug fixes


## [1.8.41] - 2026-06-12
- Bug fixes
- Complete update of the codebase


## [Unreleased]
- New `file:q` suffix marks a file's x data as already in Q (no conversion, implies Q axis)
- Auto Q mode (from `file:wl` / `.qye` / `--wl`) no longer requires `--xaxis q` when some files lack wavelength info; such files are assumed already in Q with a printed note

## [1.8.40] - 2026-05-27
- Bug fixes


## [1.8.39] - 2026-05-01
- Bug fixes for BatX operando plot


## [1.8.38] - 2026-04-03
- Bug fixes


## [1.8.37] - 2026-03-31
- Bug fixes


## [1.8.36] - 2026-03-30
- Bug fixes


## [1.8.35] - 2026-03-26
- Bug fixes


## [1.8.34] - 2026-03-24
- Bug fixes


## [1.8.32] - 2026-03-24
- Improved multi-file support for EC mode


## [1.8.33] - 2026-03-24
- Bug fixes


## [1.8.25] - 2026-03-16
- Improved interactive menu functionality for colors/ticks
- Bug fixes


## [1.8.26] - 2026-03-16
- Improved interactive menu functionality for ec mode
- Bug fixes


## [1.8.27] - 2026-03-16
- Improved interactive menu functionality for cpc mode
- Improved interactive menu display
- Bug fixes


## [1.8.28] - 2026-03-16
- Bug fixes


## [1.8.29] - 2026-03-16
- Improved compatibility of --convert with --readcol: conversion now respects per-file, per-extension, and global column selection
- Use custom columns when converting XRD data: batplot data.csv --readcol 3 4 --convert 1.54 q
- Per-file columns for convert: batplot f1.txt --readcol 2 3 f2.txt --readcol 5 6 --convert 1.54 q
- Fixed --all style.bps --readcol 2 3: style files no longer steal readcol; global readcol applies to all data files


## [1.8.30] - 2026-03-16
- Bug fixes
- Improved reader for different data formats


## [1.8.31] - 2026-03-16
- Major update: support for batX plotting, navigate to the folder containing EC data and brml files, and run batplot --operando --i


## [Unreleased]
- **Canvas mode** (`--canvas`): Combine multiple .pkl sessions into one layout. `batplot xrd.pkl operando.pkl gc.pkl dqdv.pkl --canvas` — displays all sessions in a grid; use numbers (1–9) to edit each panel with its interactive menu; layout commands (1x1, 2x2, etc.); export (e) or save canvas (s) to .pkl for later editing. Supports EC, operando, CPC sessions. XY/1D sessions not yet supported in canvas.
- CV: Multi-file combined mode — when multiple .mpt/.txt files are provided with `--cv`, all files are overlaid on one figure (like GC/dQ/dV). Full c (cycles/colors) menu: fall:, f1:1,5,10, fall viridis, etc. p, i, s, b work correctly.
- GC/CV/dQdV: `fall:1 2 3 5 4` — show cycles 1,2,3,5 for ALL files, one color per file from palette 4 (file 1→first color, file last→last color).
- GC/CV/dQdV: Per-file cycle selection in c (cycles/colors): type `f1:1,5,10 f2:2,4,6 viridis` to show different cycles per file (file 1: cycles 1,5,10; file 2: cycles 2,4,6). Use `f1:all` for all cycles in a file.
- EC/CV/dQdV: Simplified multi-file palette: press c, then type `fall viridis` (all files), `f1-5 viridis` (files 1–5), or `f1 f3 f5 4`—no intermediate file selection step
- CPC: In ly/ry color submenu, added file range palette: `1-5 viridis`, `1 3 5 4` to apply palette to files 1–5 or 1,3,5
- EC/CV/dQdV: File-palette colors persist via p (print style), i (import style), s (save session), or b (undo). Style export now includes per-file cycle styles for multi-file plots.

## [1.8.24] - 2026-03-03
- Improved interactive menu functionality for colors/ticks
- Bug fixes


## [1.8.23] - 2026-02-28
- Major update: batplot now support Bruker .brml and .raw files, you can treat them the same as .xy files (still testing)
- .brml and .raw are also supported in operando mode
- Improved --readcol flag, now you can assign the columns to read for each file by using --readcol m n after each file
    e.g. batplot file1.xy --readcol 1 2 file2.xy --readcol 4 6 this will plot col 1 as x and col 2 as y for file1, and col 4 as x and col 6 as y for file2
         batplot file.xy --readcol 1 2 1 3 1 4 1 5 this will plot 4 curves with col 1 as x and col 2, 3, 4, 5 as y


## [1.8.22] - 2026-02-27
- Major update: batplot now support Bruker .brml and .raw files, you can treat them the same as .xy files
- Improved --readcol flag, now you can assign the columns to read for each file by using --readcol m n after each file
    e.g. batplot file1.xy --readcol 1 2 file2.xy --readcol 4 6 this will plot col 1 as x and col 2 as y for file1, and col 4 as x and col 6 as y for file2
         batplot file.xy --readcol 1 2 1 3 1 4 1 5 this will plot 5 curves with col 1 as x and col 2, 3, 4, 5 as y


## [1.8.21] - 2026-02-13
- Improved functionality in operando mode with CIF files


## [1.8.20] - 2026-02-12
- Operando mode now supports CIF tick labels, add cif files in your command together with operando path to try!


## [1.8.19] - 2026-02-10
- Add support for GC data with user defined segments to separate charge and discharge, useful for BatX EC data


## [1.8.18] - 2026-02-10
- Add support for GC plot with only Potential vs Time


## [1.8.17] - 2026-02-09
- Add support for BatX GC plot


## [1.8.16] - 2026-02-08
- GC and dQdV modes now support multiple files


## [1.8.15] - 2026-02-08
- GC and dQdV modes now support multiple files


## [1.8.14] - 2026-02-07
- Fixed title offset command crash in EC/GC interactive menu
- Fixed bugs in color command
- Major update: GC and dQdV modes now support multiple files

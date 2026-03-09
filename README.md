# batplot

**Interactive plotting tool for battery and materials characterization data**

`batplot` is a Python CLI tool for visualizing and analyzing electrochemical and structural characterization data with interactive styling and session management. The electrochemistry and operando plots were inspired from Amalie Skurtveit's python scripts (https://github.com/piieceofcake?tab=repositories).

## Features

- **Electrochemistry Modes**: Galvanostatic cycling (GC), cyclic voltammetry (CV), differential capacity (dQdV), capacity per cycle (CPC) with multi-file support
- **Normal xy plot**: Designed for XRD, PDF, XAS (XANES/EXAFS) but also support other types
- **Operando Analysis**: Correlate in-situ characterizations (XRD/PDF/XAS) with electrochemical data
- **Interactive plotting**: Real-time editing customized for each type of plottings
- **Session Persistence**: Save and reload complete plot states with `.pkl` files
- **Style Management**: Import/export plot styles as `.bps`/`.bpsg` files
- **Batch Processing**: Export each file separately with `--all`

## Installation

```bash
pip install batplot
```

## Quick Start

Tutorial: https://drive.google.com/file/d/1NTFJWNBbWW4mgz0H5ZelGjuOBWxoFgkr/view

---

## 1D (XY) Mode — XRD, PDF, XAS and much more

In batplot, --xaxis is frequently used to indicate the data type.

### Basic plotting

```bash

# Specify X-axis type (Q, 2theta, r, k, energy, time or any user defined names)
# By defauly, batplot will skip the header lines, plot the first and second columns as x and y
# Q and q are equivalent (case-insensitive)
batplot pattern.xye --xaxis 2theta
batplot data.qye --xaxis q
batplot data.txt --xaxis whatever

# Set X-axis range
batplot pattern.xye --xaxis 2theta --xrange 10 80

# Save to file (default .svg if no extension)
batplot pattern.xye --xaxis 2theta --out figure
batplot pattern.txt --xaxis Energy --out figure.png
```

### Wavelength and Q conversion for XRD data

```bash
# Convert 2θ to Q using wavelength (Å), --xaxis is no longer needed as providing wavelength is implying that user wants to convert and plot the data in Q space
batplot data.raw --wl 1.5406 

# Per-file wavelength: file.xye:1.54, in this case --xaxis is also not needed and files will be plotted in Q space
batplot scan1.brml:1.5406 scan2.xye:0.7093

# Convert and export to converted/ subfolder (q and Q equivalent)
batplot data.xye --convert 1.54 q
batplot data.qye --convert q 1.54
```

### Stacking and normalization

```bash
# Stack curves vertically (auto-normalizes)
batplot file1.xy file2.xy --stack

# Control spacing between stacked curves
batplot file1.xy file2.xy --stack --delta 0.15

# Normalize intensity to 0–1 (without stacking)
batplot file.xy --norm
```

### Dual y-axis (right y-axis)

```bash
# Plot selected files on the right y-axis (--ry disables --stack)
batplot file1.xy --ry file2.xy --ry file3.xy file4.xy --ry --interactive
# Files 1, 2, 4 use right y-axis; file 3 uses left y-axis

# With --txaxis: right y-axis curves use the top x-axis (default: shared bottom x)
batplot file1.xy --ry file2.xy --txaxis --interactive
```

### Column selection and multi-curve

```bash
# Read columns 2 and 3 as X, Y (1-indexed)
batplot data.xy --readcol 2 3

# Per-file columns
batplot file1.xy --readcol 2 3 file2.xy --readcol 4 5

# Multiple curves from same file (cols 1,2 and 1,3)
batplot data.xy --readcol 1 2 1 3

# Range: col 1 as x, cols 2–20 as 19 y-curves
batplot file.txt --readcol 1 2-20
```

### Derivatives and EXAFS

```bash
# Plot first derivative (dy/dx)
batplot file.xy --1d --stack

# EXAFS k-weighting
batplot data.chik --chik           # χ(k)
batplot data.chik --k2chik        # k²χ(k), most common
batplot data.chik --k3chik --xrange 2 12
```

### Interactive menu

```bash
# Open interactive menu for styling, ranges, export, session save
batplot pattern.xye --interactive
batplot file1.xy file2.xy --stack --interactive
batplot allfiles --xaxis 2theta --xrange 15 75 --interactive
```

---

## Electrochemistry Mode

### Data export requirements from instruments

- **Neware**: Customized report — check all boxes
- **Biologic**: Export all info to .mpt file

### Galvanostatic cycling (GC)

```bash
# From .csv (capacity in file)
batplot battery.csv --gc

# From .mpt (requires --mass in mg)
batplot battery.mpt --gc --mass 7.0

# With interactive menu
batplot battery.csv --gc --interactive
```

### Cyclic voltammetry (CV)

```bash
batplot cyclic.mpt --cv
batplot cyclic.mpt --cv --interactive
```

### Differential capacity (dQ/dV)

```bash
batplot battery.csv --dqdv
batplot battery.csv --dqdv --interactive
```

### Capacity per cycle (CPC)

```bash
# Single file
batplot stability.csv --cpc
batplot stability.mpt --cpc --mass 5.4

# Multiple files with individual colors
batplot file1.csv file2.mpt --cpc --mass 6.0 --interactive
```

### Time vs potential

```bash
# Plot time (h) vs potential from CSV/MPT
batplot battery.csv --xaxis time --interactive
```

### Potential window (custom potential–time .mpt)

```bash
# Two columns: potential, time. Use --pw and --cd to plot as GC
batplot custom.mpt --gc --pw 0.01 3 --cd 0.2 --interactive
```

---

## Operando Mode

```bash
# Contour from folder of .xy/.xye/.qye/.dat
batplot --operando --interactive

# With folder path
batplot /path/to/data --operando --interactive

# Q conversion from 2θ
batplot --operando --wl 0.25995 --interactive

# Derivative contour
batplot --operando --1d --interactive

# With CIF tick labels
batplot folder phase.cif:1.54 --operando --interactive
```

---

## Plotting multiple files

```bash
# All XY files in current directory on same figure
batplot allfiles
batplot allfiles --stack --interactive

# Only specific extension (natural-sorted)
batplot allxyfiles
batplot "/path/to/data" allnorfiles --interactive

# Explicit file list
batplot file1.xye file2.qye structure.cif:1.54 --stack --interactive
```

---

## Batch export (--all)

Export each file as a separate figure to `batplot_svg/`:

```bash
batplot --all
batplot --all --format png
batplot --all --xaxis 2theta --xrange 10 80
batplot --all style.bps --gc --mass 7
```

---

## Supported File Formats

| Type | Formats |
|------|---------|
| **Electrochemistry** | `.csv` (Neware), `.mpt` (Biologic), `.xlsx` (Landt/Lanhe CPC) |
| **XRD / PDF** | `.xye`, `.xy`, `.qye`, `.dat`, `.csv`, `.txt`; Bruker `.brml`, `.raw` |
| **XAS** | `.nor`, `.chik`, `.chir` |
| **Generic** | Use `--readcol` and `--xaxis` for custom formats |

---

## Interactive Features

With `--interactive`:
- **Cycle/Scan Control**: Toggle visibility, change colors
- **Styling**: Line widths, markers, fonts
- **Axes**: Labels, limits, ticks, spine styles
- **Export**: Sessions (`.pkl`), styles (`.bps`/`.bpsg`), high-res images
- **Live Preview**: All changes update in real-time

---

## Help & Documentation

```bash
batplot --help              # General help
batplot --help xy           # XY mode guide
batplot --help ec           # Electrochemistry guide
batplot --help op           # Operando guide
batplot --version           # Version and release notes
batplot --manual            # Open illustrated manual
```

- [USER_MANUAL.md](USER_MANUAL.md) — Detailed usage and workflows
- [FLAGS_REFERENCE.md](FLAGS_REFERENCE.md) — Complete flag reference by mode

---

## Requirements

- Python ≥ 3.9
- numpy
- matplotlib

## License

See [LICENSE](LICENSE)

## Author & Contact

Tian Dai  
tianda@uio.no  
University of Oslo  
https://www.mn.uio.no/kjemi/english/people/aca/tianda/  
https://github.com/chem-plot/

**Subscribe for Updates**: Join batplot-lab@kjemi.uio.no for updates. If not from UiO, email sympa@kjemi.uio.no with subject: "subscribe batplot-lab@kjemi.uio.no your-name"

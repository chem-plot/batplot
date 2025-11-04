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
- **Batch Processing**: Plot multiple files simultaneously with automatic SVG export

## Installation

```bash
pip install batplot
```

## Quick Start

### XRD / PDF / XAS and much more

```bash
# Single diffraction pattern in 2theta
batplot pattern.xye --xaxis 2theta

# Interactive styling
batplot pattern.xye --interactive

# Plot all XY files in directory on same figure
batplot allfiles
batplot allfiles --stack --interactive
batplot allfiles --xaxis 2theta --xrange 10 80

# Batch mode: export all XY files to SVG
batplot --all

# Batch mode with options: custom axis and range
batplot --all --xaxis 2theta --xrange 10 80

# Normalize data (--stack mode auto-normalizes by default)
batplot allfiles --norm

# Batch mode: convert 2theta to Q
batplot --all --wl 1.5406
```

### Electrochemistry

```bash
# Galvanostatic cycling with interactive menu
batplot battery.csv --gc --interactive

# Cyclic voltammetry
batplot cyclic.mpt --cv --interactive

# Differential capacity
batplot battery.csv --dqdv

# Capacity per cycle - single file
batplot stability.mpt --cpc --mass 5.4 --interactive

# Capacity per cycle - multiple files with individual color control
batplot file1.csv file2.csv file3.mpt --cpc --mass 5.4 --interactive

# Batch processing: export all EC files to SVG
batplot --gc --all --mass 7.0       # All .mpt/.csv files (.mpt needs --mass, .csv doesn't)
batplot --cv --all                  # All .mpt files (CV mode)
batplot --dqdv --all                # All .csv files (dQdV mode)
batplot --cpc --all --mass 6.2      # All .mpt/.csv files (.mpt needs --mass, .csv doesn't)

# Batch processing with style/geometry: apply consistent formatting to all files
batplot --all mystyle.bps --gc --mass 7.0   # Apply .bps style to all GC files
batplot --all config.bpsg --cv              # Apply .bpsg style+geometry to all CV files
batplot --all style.bps --dqdv              # Apply style to all dQdV files
batplot --all geom.bpsg --cpc --mass 5.4    # Apply style+geometry to all CPC files
```

### Operando Analysis

```bash
# Correlate in-situ XRD with electrochemistry
# (Place both .xye and .mpt files in same directory)
batplot --operando --interactive

# Operando mode without electrochemistry data
# (Only .xye files, no .mpt file)
batplot --operando --interactive
```

## Supported File Formats

| Type | Formats |
|------|---------|
| **Electrochemistry** | `.csv` (Neware raw data; summary format for CPC), `.mpt` (Biologic), `.xlsx` (Landt/Lanhe summary for CPC) |
| **XRD / PDF** | `.xye`, `.xy`, `.qye`, `.dat` |
| **XAS** | `.nor`, `.chik`, `.chir` |
| **Others** | `user defined` (plot first two columns as x and y) |

## Interactive Features

When launched with `--interactive`:
- **Cycle/Scan Control**: Toggle visibility, change colors
- **Styling**: Line widths, markers, transparency
- **Axes**: Labels, limits, ticks, spine styles
- **Export**: Save sessions (`.pkl`), styles (`.bps`/`.bpsg`), or high-res images
- **Live Preview**: All changes update in real-time

## Documentation

For detailed usage, see [USER_MANUAL.md](USER_MANUAL.md)

## Requirements

- Python ≥ 3.7
- numpy
- matplotlib

## License

See [LICENSE](LICENSE)

## Author & Contact

Tian Dai (tianda@uio.no)  
University of Oslo

**GitHub**: https://github.com/tiandai-chem/batplot

**Subscribe for Updates**: Join batplot-lab@kjemi.uio.no for updates, feature announcements, and community feedback. If you are not from UiO, send an email to sympa@kjemi.uio.no with the exact subject line with your name: "subscribe batplot-lab@kjemi.uio.no your-name"

# batplot User Manual
**v1.7.5, 2025-11-21**

Batplot is a lightweight CLI tool for plotting XRD, PDF, XAS, electrochemistry, and operando data, featuring interactive and batch modes.
The electrochemistry and operando plotting functions are inspired by the script written by Amalie, Erlend and Casper.

**Supported Python versions:** 3.9–3.13

---

## Installation

```bash
pip install batplot
```

## Table of Contents

1. [Overview](#overview)
2. [XY Mode](#normal-xy-mode)
3. [Electrochemistry Mode](#electrochemistry-mode)
4. [Operando Mode](#operando-mode)
5. [Command-Line Flags Reference](#command-line-flags-reference)

---

## 1. Overview

Batplot supports three main figure types:
- **Normal XY**: For XRD, PDF, XAS, and general 2D data.
- **Electrochemistry (EC)**: For battery cycling and related data.
- **Operando**: For synchronized plotting of structural and electrochemical data.

**Key features:**
- Interactive menu for live editing.
- Save and reuse styles via `.bps` (style) or `.bpsg` (style+geometry) files.
- Save and reload full sessions as `.pkl` files for future editing.

---

## 2. Normal XY Mode

### Supported Inputs

- XRD: `.xye`, `.xy`, `.qye`, `.dat`, `.csv`, `.txt`
- PDF: `.gr`
- XAS: `.nor` (energy), `.chik` (k), `.chir` (FT-EXAFS R)
- Crystallography: `.cif` (reflection ticks/labels only)
- Generic/undefined: `.xy`, `.dat`, `.txt` or other types (will read the first two columns and plot as x and y)

### Plotting Modes

**Single/Multiple Files**: Specify files individually for precise control.

**All Files Together (`allfiles` / `all<ext>files`)**: Plot all supported files in the current directory on the **same figure**. Use `allfiles` for every extension, or `allxyfiles`, `allnorfiles`, etc. to restrict to a single file type. Files are loaded in natural (human) order so `scan2.xy` appears before `scan10.xy`. Supports all options (--stack, --interactive, --xaxis, etc.).

**Batch Mode (`--all`)**: Export each file as a **separate SVG**. Perfect for preparing publication figures. Supports options like --xaxis, --xrange, --wl, --norm.

| Command | What it does | Interactive? | Output |
|---------|--------------|--------------|--------|
| `batplot file1.xy file2.xy` | Plot specific files together | Yes | Single figure |
| `batplot allfiles` | Plot all XY files together | Yes | Single figure |
| `batplot allxyfiles` | Plot only `.xy` files together | Yes | Single figure |
| `batplot --all` | Export each file separately | No | Multiple SVG files |

### Example Usage

```bash
batplot file1.xye:1.54 file2.qye
# Plot two files; .xye is converted to Q with wavelength 1.54 Å

batplot file1.xye file2.dat --wl 1.54
# Plot two 2theta files in Q space with wavelength 1.54 Å

batplot file1.xye file2.xye --xaxis 2theta --i
# Plot with 2theta as X axis and open interactive menu

batplot file1.xye:0.25995 file2.qye --stack --i
# Stack two files and open the interactive menu

batplot file1.xye file2.xye. --wl 1.54 --stack --i
# Stack two files and open the interactive menu

batplot file1.xye:0.25995 file2.qye structure1.cif structure2.cif --stack --i
# Stack two files with reference cif ticks and open the interactive menu

batplot allfiles
# Plot all XY files in current directory on the same figure

batplot allfiles --stack --i
# Plot all XY files stacked with interactive menu

batplot allfiles --xaxis 2theta --xrange 10 80 --i
# Plot all files with custom axis, range, and interactive menu

batplot allfiles --norm --i
# Plot all files with normalized intensities

batplot allxyfiles
# Only plot .xy files (natural ordering: file2 before file10)

batplot "/path/to/data" allnorfiles --i
# Plot only .nor files from a folder with the interactive menu

batplot --all
# Batch mode: save all supported files in the current folder as SVG images

batplot --all --xaxis 2theta --xrange 10 80
# Batch mode with custom X-axis type and range

batplot --all --wl 1.5406
# Batch mode: convert 2theta to Q with wavelength 1.5406 Å

batplot --all style.bps
# Batch mode: apply style.bps to all XY files
# Applies: fonts, colors, line widths, tick parameters, spine properties

batplot --all ./Style/style.bps
# Batch mode: apply style from relative path (e.g., ./Style/style.bps)
# Supports absolute paths, relative paths, and paths with/without extensions

batplot --all config.bpsg
# Batch mode: apply style+geometry to all XY files
# Applies: all style elements PLUS axis labels and limits

batplot --all ./Style/config.bpsg
# Batch mode: apply style+geometry from relative path

batplot file1.xy file2.xye style.bps --out output.svg
# Normal mode: apply style to multiple files and export as figure
# Style file can be included in the file list along with data files

batplot file1.xy file2.xye ./Style/style.bps --out output.svg
# Normal mode: apply style from relative path to multiple files

batplot file1.xy file2.xy --1d --stack --i
# Plot the first derivative (dy/dx) of file1 and file2 with interactive menu
```

### Derivative Plotting

The `--1d` and `--2d` flags (both equivalent) allow you to plot the first derivative (dy/dx) of your datasets. This is useful for identifying peaks, inflection points, and analyzing the rate of change in your data.

**Examples:**
```bash
batplot file1.xy file2.xy --1d --stack --i
# Plot 1st derivatives of file1 and file2, stacked with interactive menu

batplot allfiles --1d --interactive
# Plot 1st derivatives of all XY files with interactive menu

batplot file1.xy --1d --xrange 10 80
# Plot 1st derivative with custom X-axis range
```

**Note:** The derivative is calculated using numpy's gradient function, which automatically handles non-uniform spacing in your X-axis data. The derivative calculation is applied after data loading and axis conversion, but before any transformations (EXAFS k-weighting, normalization, etc.).

### Column Selection (`--readcol`)

By default, batplot reads the first two columns as x and y. Use `--readcol` to select different columns (1-indexed). Three modes are supported:

1. **Per-file**: Assign different x,y columns to different files.
   ```bash
   batplot file1.xy --readcol 2 3 file2.xye --readcol 4 5
   # file1: columns 2 (x) and 3 (y); file2: columns 4 (x) and 5 (y)
   ```

2. **Multi-curve**: Plot multiple curves from the same file using alternate x,y column pairs.
   ```bash
   batplot data.xy --readcol 1 2 1 3
   # Two curves: (cols 1,2) and (cols 1,3) on the same figure
   ```

3. **With wavelength**: When a file has per-file wavelength (e.g. `file.xy:1.54`), the x column is treated as 2θ and converted to Q using that wavelength.
   ```bash
   batplot scan.xy:1.54 --readcol 2 3
   # Column 2 = 2θ, converted to Q using λ=1.54 Å; column 3 = intensity
   ```

**Extension-specific**: Use `--readcolxy`, `--readcolxye`, `--readcolqye`, etc. for per-extension defaults, or `--readcol<ext>` for custom extensions (e.g. `--readcolafes 2 3` for `.afes` files).

### Wavelength Specification

Batplot supports flexible wavelength specification for XRD data conversion and CIF tick calculation. You can specify wavelengths globally using `--wl` or per-file using colon syntax.

**Note:** For `--xaxis` and `--convert`, **Q and q are equivalent** (case-insensitive). Use either `--xaxis Q` or `--xaxis q`, and `--convert 1.54 q` or `--convert 1.54 Q`.

**Per-file wavelength syntax:**

1. **Single wavelength**: `file:wl`
   - For data files: converts 2theta to Q using the specified wavelength
   - For CIF files: calculates 2theta tick positions using the specified wavelength (requires `--xaxis 2theta`)

2. **Dual wavelength**: `file:wl1:wl2`
   - Converts data from 2theta using first wavelength (wl1) to Q, then back to 2theta using second wavelength (wl2)
   - Useful for comparing data collected at different wavelengths
   - Crosshair will display both original 2theta (λ₁) and current 2theta (λ₂)

**Examples:**

```bash
# Single wavelength for Q conversion (Q and q are equivalent for --xaxis)
batplot data.xye:1.5406 --xaxis Q
batplot data.xye:1.5406 --xaxis q
# Converts 2theta data to Q using Cu Kα wavelength

# CIF file with wavelength for 2theta tick calculation
batplot data.xye pattern.cif:0.25448 --xaxis 2theta --interactive
# CIF ticks are calculated in 2theta range using synchrotron wavelength 0.25448 Å

# Dual wavelength conversion
batplot data.xye:0.25:1.54 --xaxis 2theta --interactive
# Converts: 2theta (λ=0.25) → Q → 2theta (λ=1.54)
# Crosshair shows both original and converted 2theta values

# Multiple files with different wavelengths
batplot file1.xye:1.5406 file2.xye:0.7093 pattern.cif:1.5406 --xaxis 2theta
# Each file uses its own wavelength; CIF ticks use 1.5406 Å
```

**Note:** When using dual wavelength conversion, the crosshair (press `n` in interactive mode) will automatically display both the original 2theta (calculated from λ₁) and the current 2theta (displayed axis, calculated from λ₂), along with Q and d-spacing values.

### EXAFS k-Weighting

For EXAFS (Extended X-ray Absorption Fine Structure) data in k-space, batplot provides four k-weighting options to emphasize different features of the data:

| Flag | Transformation | Y-axis Label | Use Case |
|------|---------------|--------------|----------|
| `--chik` | χ(k) | χ(k) | Standard EXAFS oscillations |
| `--kchik` | k × χ(k) | kχ(k) (Å⁻¹) | Emphasize mid-k features |
| `--k2chik` | k² × χ(k) | k²χ(k) (Å⁻²) | Most common weighting, balances signal |
| `--k3chik` | k³ × χ(k) | k³χ(k) (Å⁻³) | Emphasize high-k features, heavy backscatterers |

**Example Usage:**

```bash
batplot data.chik --chik
# Plot standard χ(k) with proper axis labels

batplot data.chik --kchik --interactive
# k-weighted plot with interactive menu

batplot data.chik --k2chik --out k2chik.svg
# Most common k²χ(k) weighting, save as SVG

batplot data.chik --k3chik --xrange 2 12 --interactive
# k³-weighted plot with custom k-range

batplot file1.chik file2.chik --k2chik --stack --interactive
# Compare multiple samples with k² weighting
```

**Note:** All k-weighting flags automatically set the x-axis to k (Å⁻¹) and apply the appropriate mathematical transformation to the y-data.

---

## 3. Electrochemistry Mode

### Supported Inputs

- Neware `.csv` (GC, dQdV, CPC - both raw data and summary format)
- Biologic `.mpt` (GC, CV, CPC)
- **Custom potential–time `.mpt` (potential window)** — Two columns: potential (V), time (h). Use `--pw V_MIN V_MAX --cd current_density` to plot as GC.
- **Landt/Lanhe `.xlsx` (CPC)** - Chinese battery tester Excel files
- **Summary CSV format (CPC)** - Cycle-level capacity data

#### Summary Format Support for CPC Mode

Batplot supports **cycle-level summary files** for CPC plotting in both **CSV** and **Excel (`.xlsx`)** formats. These files contain one row per cycle with charge/discharge capacity columns, rather than point-by-point data.

**Supported formats:**
- **CSV**: Standard comma-separated values
- **Excel (`.xlsx`)**: Landt/Lanhe (often labeled "Lan Dian / Lan He" in English) battery tester files with Chinese headers

**Expected structure for CSV:**
- **Row 1**: Column headers (English)
- **Row 2 onwards**: Cycle data (one row per cycle)

**Expected structure for Excel:**
- **Row 1**: File/sample name (e.g., "RATE-KB-2HAOJIPIAN_033_3") - automatically ignored
- **Row 2**: Column headers (Chinese or English)
- **Row 3 onwards**: Cycle data (one row per cycle)

**Required columns for summary format:**
- `Cycle Index` (or the Chinese header typically transliterated as "Xunhuan Xuhao") - Cycle number
- `Chg. Spec. Cap.(mAh/g)` (or "Chongdian Bi Rongliang/mAh/g") - Charge specific capacity
- `DChg. Spec. Cap.(mAh/g)` (or "Fangdian Bi Rongliang/mAh/g") - Discharge specific capacity
- **Optional**: Efficiency column (`Chg.-DChg. Eff(%)` or "Xiaolv/%")

**Note:** Potential and current columns are optional for summary files. If not present, synthetic values are generated internally for compatibility.

**Example usage:**
```bash
# Single Excel file (Landt/Lanhe)
batplot --cpc battery_test.xlsx --interactive

# Single CSV summary file
batplot --cpc cycle_summary.csv --interactive

# Multiple summary files with color control
batplot --cpc sample1.xlsx sample2.csv sample3.xlsx --interactive

# Mix summary files with raw data files
batplot --cpc summary.csv summary.xlsx neware_raw.csv biologic.mpt --mass 5.4 --interactive
# Note: --mass only needed for .mpt files
```

### Plotting Modes

**GC (Galvanostatic Cycling)**: Potential vs. capacity plots showing charge/discharge cycles.

**CV (Cyclic Voltammetry)**: Potential vs. current plots for electrochemical characterization. Supports full interactive menu with cycle-by-cycle styling, colors, visibility control, and session save/load.

**dQdV**: Differential capacity analysis (dQ/dV vs. potential).

**CPC (Capacity Per Cycle)**: Plot charge/discharge capacity and coulombic efficiency vs. cycle number. Supports multiple files with individual color customization.

### Potential window mode (`--pw`, custom potential–time to GC)

For **custom .mpt files** that contain only two columns — **potential (V)** and **time (hours)** — you can plot them as galvanostatic cycling (capacity vs. potential) by converting time to capacity and using a potential window to separate charge and discharge.

**File format:** Plain text, tab- or space-separated: column 1 = potential (V), column 2 = time (h). No header required.

**Flags:**
- `--pw V_MIN V_MAX` — Potential window (V). Data near these values are used to separate charge/discharge (e.g. `--pw 0.01 3`).
- `--cd VALUE` — Current density in mA/g. Capacity (mAh/g) = current density × time (h). Required when using `--pw`.
- `--b TOL_UPPER TOL_LOWER` — Optional. Tolerance in V for detecting the upper and lower potential boundaries (default 0.05 and 0.005). Example: `--b 0.05 0.005`.

**Examples:**
```bash
# Basic: plot custom potential–time .mpt as GC (capacity vs. potential)
batplot file.mpt --gc --cd 0.2 --pw 0.01 3

# With custom boundary tolerances and interactive menu
batplot file.mpt --gc --cd 0.2 --pw 0.01 3 --b 0.05 0.005 --interactive
```

### Example Usage

```bash
batplot file.csv --gc --interactive
# Plot GC data with interactive menu

batplot file.csv --dqdv
# Plot dQdV curve

batplot file.mpt --cv --interactive
# Plot CV data with full interactive menu support

batplot file.csv --xaxis time --interactive
# Plot time (h) vs potential (V) from CSV file with full interactive menu
# All interactive commands (p, i, s, b, f, l, etc.) are available

batplot file.mpt --xaxis time --interactive
# Plot time (h) vs potential (V) from MPT file with interactive menu

batplot file1.csv file2.csv --xaxis time --stack --interactive
# Plot multiple time-potential curves stacked with interactive menu

batplot file1.csv file2.csv file3.mpt --cpc --mass 6.2 --interactive
# Plot multiple CPC files on same axes with interactive menu
# Each file can be styled individually (colors)
# Line styles, fonts, and markers apply globally
# Note: --mass only required for .mpt files

batplot file.csv --cpc --interactive
# Plot single CPC file with interactive menu
```

### Time Mode (`--xaxis time`)

When using `--xaxis time` with CSV or MPT files, batplot plots time (in hours) on the X-axis and potential (in volts) on the Y-axis, similar to the EC panel in operando mode. This mode supports:
- Full interactive menu with all features (p, i, s, b, f, l, m, etc.)
- Multiple file plotting
- Stack mode (`--stack`) for offset curves
- Range control (`--xrange`)
- All standard styling and export options

The time mode automatically extracts time columns (e.g., "Total Time", "time/s") and potential columns (e.g., "Voltage(V)", "Ewe/V") from the file and converts time to hours.

### CPC Interactive Menu Features

When using `--cpc --interactive`, you get access to:
- **Global styling**: Line styles (l), fonts (f), and marker sizes (m) apply to all curves
- **Individual colors**: Use `c` command to select specific files by number and assign colors
  - Charge color is set directly; discharge color auto-generates a similar shade
  - Efficiency triangles can be colored independently
- **File visibility**: Toggle visibility of individual files with `v` command
- **Clean export**: File numbering is removed from legend labels when exporting figures
- **Session save**: Save complete project state including all files and styles with `s` command

### Batch Mode

Export all EC files in a directory to SVG format:

```bash
batplot --gc --all --mass 7.0
# Process all .mpt and .csv files in current directory (GC mode)
# Note: --mass only required for .mpt files; .csv files already contain capacity data
# Outputs saved to batplot_svg/ subdirectory

batplot --cv --all
# Process all .mpt files (CV mode)

batplot --dqdv --all
# Process all .csv files (dQdV mode)

batplot --cpc --all --mass 5.4
# Process all .mpt and .csv files (CPC mode)
# Note: --mass only required for .mpt files

batplot --gc /path/to/folder --mass 6.0
# Process files in specific directory
```

### Batch Mode with Style/Geometry

Apply consistent formatting to all EC files using `.bps` (style) or `.bpsg` (style+geometry) configuration files:

```bash
batplot --all mystyle.bps --gc --mass 7.0
# Apply style.bps formatting to all GC files in current directory
# Applies: fonts, colors, line widths, tick parameters, spine properties

batplot --all ./Style/mystyle.bps --gc --mass 7.0
# Apply style from relative path (e.g., ./Style/mystyle.bps)
# Supports absolute paths, relative paths, and paths with/without extensions

batplot --all config.bpsg --cv
# Apply style+geometry to all CV files
# Applies: all style elements PLUS axis labels and limits

batplot --all ./Style/config.bpsg --cv
# Apply style+geometry from relative path

batplot --all style.bps --dqdv
# Apply style to all dQdV files

batplot --all ./Style/style.bps --dqdv
# Apply style from relative path

batplot --all geom.bpsg --cpc --mass 5.4
# Apply style+geometry to all CPC files

batplot --all ./Style/geom.bpsg --cpc --mass 5.4
# Apply style+geometry from relative path
```

### Normal Mode with Style Files

Apply style files to multiple EC files and export each as a separate figure:

```bash
batplot file1.csv file2.mpt style.bps --gc --mass 7.0
# Apply style to multiple GC files, each exported to Figures/ directory

batplot file1.csv file2.mpt ./Style/style.bps --gc --mass 7.0
# Apply style from relative path to multiple GC files
# Style file can be included in the file list along with data files

batplot file1.mpt file2.txt style.bpsg --cv
# Apply style+geometry to multiple CV files

batplot file1.mpt file2.txt ./Style/style.bpsg --cv
# Apply style+geometry from relative path to multiple CV files

batplot file1.csv file2.csv style.bps --dqdv
# Apply style to multiple dQdV files

batplot file1.csv file2.csv ./Style/style.bps --dqdv
# Apply style from relative path to multiple dQdV files

batplot file1.csv file2.mpt style.bpsg --cpc --mass 6.0
# Apply style+geometry to multiple CPC files

batplot file1.csv file2.mpt ./Style/style.bpsg --cpc --mass 6.0
# Apply style+geometry from relative path to multiple CPC files
```

**Workflow: Create Once, Apply to All**
1. Create a perfect plot interactively: `batplot file.mpt --gc --mass 7.0 --interactive`
2. Adjust formatting (fonts, colors, ticks, geometry) as desired
3. Export style: Press `p` → `ps` (style only) or `psg` (style+geometry)
4. Apply to all files: `batplot --all mystyle.bps --gc --mass 7.0`
5. All files in directory now have identical, publication-ready formatting!

**Style Files:**
- `.bps` files contain style settings: fonts, colors, line widths, tick parameters, spines
- `.bpsg` files contain style + geometry: everything in `.bps` plus axis labels and limits
- Create style files from interactive mode or edit JSON manually

**Note**: 
- Batch mode automatically exports SVG plots to `batplot_svg/` subdirectory
- For GC and CPC modes: `.csv` files don't need `--mass` (capacity already in file)
- For GC and CPC modes: `.mpt` files require `--mass` parameter
- Interactive mode (`--interactive`) is only available for single-file plotting

---

## 4. Operando Mode

Use `--operando` or `--contour` (identical behavior).

### Requirements

- Place operando files (`.xye`, `.qye`, `.xy`, `.dat`) in the directory.
- Optionally include a `.mpt` file for dual-panel mode (side panel: time/potential/temperature etc.).
- Optionally add CIF files for phase tick labels (below or above the operando panel).
- Navigate to the folder before running Batplot.

### CIF Tick Labels in Operando Mode

You can overlay CIF reflection tick labels on the operando contour, using the same x-axis (2θ or Q, via `--wl` as in 1D mode):

```bash
batplot folder phase.cif:1.54 --operando --interactive
# Add CIF tick labels below the operando panel (λ=1.54 Å for 2θ mode)

batplot folder phase1.cif:1.54 phase2.cif:0.71 --operando --wl 1.54 --interactive
# Multiple CIF phases with different wavelengths

batplot folder phase.cif:0.71 --operando --wl 0.709 --xaxis 2theta --interactive
# Operando data (e.g. .qye in Q) is converted to 2θ using --wl; CIF tick positions
# are converted to 2θ from the CIF reflections using the same wavelength
```

In the interactive menu, press **c** to open the CIF submenu:
- **z**: Toggle hkl labels on/off
- **t**: Toggle CIF titles (phase names)
- **h**: Toggle highlight for overlay (makes ticks readable when overlaid on the contour)
- **p**: Toggle placement (below or above the operando panel)
- **v**: Adjust vertical position of each CIF set
- **o**: Change color per CIF set
- **m**: Apply colormap to all CIF sets (tab10 is the initial palette)
- **f**: Change font (family and size) of CIF titles
- **r**: Rename CIF set labels
- **n**: Hide or show name per CIF set
- **x**: Show or hide entire CIF set (ticks + labels) per set

### Example Usage

```bash
batplot --operando --interactive
# Launch operando mode with interactive editing
# Shows dual-panel view if .mpt file is present, single panel otherwise

batplot --contour --interactive [FOLDER]
# Same as --operando (alias)

batplot --operando --wl 0.25995 --interactive
# Launch operando mode with interactive editing, converting x axis from 2theta to Q space
```

### Interactive Menu

The operando interactive menu has four columns: **(Styles)**, **(Operando)**, **(Side Panel)**, **(Options)**. The Side Panel column contains commands for the optional time/potential (or other) trace when a `.mpt` file is present: **et** (time range), **ex** (X range), **ey** (Y-axis type), **er** (rename), **eg** (grid lines).

### Operando-Only Mode

If no `.mpt` file is present, operando mode displays only the contour plot. The interactive menu adapts to allow full control of all four spines (left, right, top, bottom) for the single panel.

---

## 5. Command-Line Flags Reference

This section summarizes all command-line flags by mode, with usage examples. For detailed descriptions of each flag, see [FLAGS_REFERENCE.md](FLAGS_REFERENCE.md).

### 1D (XY) Mode

| Flag | Description | Example |
|------|-------------|---------|
| `--interactive` | Open interactive menu for styling, ranges, fonts, export | `batplot file.xy --interactive` |
| `--delta` | Spacing between stacked curves | `batplot file1.xy file2.xy --stack --delta 0.1` |
| `--norm` | Normalize intensity to 0–1 range | `batplot file.xy --norm` |
| `--xrange` | Set X-axis range (min max) | `batplot file.xy --xrange 10 80` |
| `--out` | Save figure to file | `batplot file.xy --out plot.svg` |
| `--xaxis` | X-axis type: Q, 2theta, r, k, energy, time. Q and q equivalent | `batplot file.xy --xaxis 2theta` |
| `--wl` | Wavelength (Å) for Q conversion | `batplot file.xye --wl 1.5406 --xaxis Q` |
| `--ro` | Swap X and Y axes | `batplot file.csv --xaxis time --ro` |
| `--stack` | Stack curves vertically | `batplot file1.xy file2.xy --stack` |
| `--1d` / `--2d` | Plot first derivative (dy/dx) | `batplot file.xy --1d --stack` |
| `--chik` | EXAFS χ(k) plot | `batplot data.chik --chik` |
| `--kchik` | EXAFS kχ(k) plot | `batplot data.chik --kchik` |
| `--k2chik` | EXAFS k²χ(k) plot | `batplot data.chik --k2chik` |
| `--k3chik` | EXAFS k³χ(k) plot | `batplot data.chik --k3chik` |
| `--readcol` | Columns for X and Y (1-indexed) | `batplot file.xy --readcol 2 3` |
| `--readcolxy` | Columns for .xy files only | `batplot file.xy --readcolxy 2 3` |
| `--readcolxye` | Columns for .xye files only | `batplot file.xye --readcolxye 2 3` |
| `--readcolqye` | Columns for .qye files only | `batplot file.qye --readcolqye 2 3` |
| `--readcolnor` | Columns for .nor files only | `batplot file.nor --readcolnor 2 3` |
| `--readcoldat` | Columns for .dat files only | `batplot file.dat --readcoldat 2 3` |
| `--readcolcsv` | Columns for .csv files only | `batplot file.csv --readcolcsv 2 3` |
| `--convert` | Convert XRD data (wl→wl, wl→q, q→wl). q and Q equivalent | `batplot file.xye --convert 1.54 q` |
| `--all` | Batch mode: export each file separately | `batplot --all` |
| `--format` | Export format: svg, png, pdf, jpg, eps, tif | `batplot --all --format png` |

**1D examples:**

```bash
# Basic plot with interactive menu
batplot file1.xye file2.qye --interactive

# Stack with wavelength and spacing
batplot file1.xye:1.54 file2.xye --stack --delta 0.2 --interactive

# Derivative plot
batplot file1.xy file2.xy --1d --stack --interactive

# Batch export with style
batplot --all style.bps --xaxis 2theta --xrange 10 80

# Per-file column selection
batplot file1.xy --readcol 2 3 file2.xy --readcol 4 5
```

---

### EC (Electrochemistry) Mode

| Flag | Description | Example |
|------|-------------|---------|
| `--gc` | Galvanostatic cycling (capacity vs potential) | `batplot file.mpt --gc --mass 7` |
| `--dqdv` | Differential capacity (dQ/dV vs potential) | `batplot file.csv --dqdv` |
| `--cv` | Cyclic voltammetry (potential vs current) | `batplot file.mpt --cv` |
| `--cpc` | Capacity per cycle (capacity & efficiency vs cycle) | `batplot file.csv --cpc` |
| `--mass` | Active mass in mg (required for .mpt in GC/CPC) | `batplot file.mpt --gc --mass 6.5` |
| `--interactive` | Open interactive menu | `batplot file.csv --gc --interactive` |
| `--xaxis time` | Plot time vs potential (EC CSV/MPT) | `batplot file.csv --xaxis time --interactive` |
| `--ro` | Swap X and Y axes | `batplot file.mpt --gc --ro --mass 7` |
| `--pw` | Potential window (V_MIN V_MAX) for custom potential–time | `batplot file.mpt --gc --pw 0.01 3 --cd 0.2` |
| `--cd` | Current density (mA/g) for --pw mode | `batplot file.mpt --gc --pw 0.01 3 --cd 0.2` |
| `--b` | Boundary tolerance for --pw (upper lower) | `batplot file.mpt --gc --pw 0.01 3 --cd 0.2 --b 0.05 0.005` |
| `--all` | Batch mode: export each EC file separately | `batplot --gc --all --mass 7` |
| `--format` | Export format | `batplot --gc --all --mass 7 --format png` |
| `--out` | Save figure to file | `batplot file.csv --gc --out plot.svg` |

**EC examples:**

```bash
# GC from .mpt (requires --mass)
batplot file.mpt --gc --mass 7.0 --interactive

# GC from .csv (capacity in file)
batplot file.csv --gc --interactive

# CPC with per-file mass
batplot f1.mpt --mass 6.5 f2.csv f3.mpt --mass 7.0 --cpc

# dQ/dV
batplot file.csv --dqdv --interactive

# CV
batplot file.mpt --cv --interactive

# Time vs potential
batplot file.csv --xaxis time --interactive

# Batch with style
batplot --all style.bps --gc --mass 7

# Potential window mode (custom potential–time .mpt)
batplot file.mpt --gc --pw 0.01 3 --cd 0.2 --interactive
```

---

### Operando Mode

| Flag | Description | Example |
|------|-------------|---------|
| `--operando` | Operando contour mode | `batplot --operando --interactive` |
| `--contour` | Alias for --operando | `batplot --contour --interactive [FOLDER]` |
| `--interactive` | Open interactive menu | `batplot --operando --interactive` |
| `--wl` | Wavelength for Q conversion | `batplot --operando --wl 0.25995 --interactive` |
| `--xaxis` | X-axis type (e.g. 2theta) | `batplot --operando --xaxis 2theta` |
| `--1d` / `--2d` | Plot derivatives as contour | `batplot --operando --1d --interactive` |

**Operando examples:**

```bash
# Basic operando with interactive menu
batplot --operando --interactive

# With folder path
batplot --contour --interactive /path/to/data

# Q conversion from 2theta
batplot --operando --wl 0.25995 --interactive

# 2theta axis
batplot --operando --xaxis 2theta --interactive

# Derivative contour
batplot --operando --1d --interactive

# With CIF tick labels
batplot folder phase.cif:1.54 --operando --interactive
```

---

### Shared Flags (All Modes)

| Flag | Description |
|------|-------------|
| `--help` | Show help |
| `--help xy` | XY mode help |
| `--help ec` | EC mode help |
| `--help op` | Operando mode help |
| `--version` | Show version |
| `--manual` | Open illustrated manual |

---

## Contact & Support

For questions, bug reports, or feature requests:

Tian Dai
- **Email**: tianda@uio.no
- **Mailing List**: Subscribe to batplot-lab@kjemi.uio.no for updates, feature announcements, and community discussions

Feel free to reach out via email!

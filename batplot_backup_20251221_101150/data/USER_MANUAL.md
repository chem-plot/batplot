# batplot User Manual
**v1.7.5, 2025-11-21**

Batplot is a lightweight CLI tool for plotting XRD, PDF, XAS, electrochemistry, and operando data, featuring interactive and batch modes.
The electrochemistry and operando plotting functions are inspired by the script written by Amalie, Erlend and Casper.

**Supported Python versions:** 3.7–3.13

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
- Generic/undefined: `.xy`, `.dat` or other types (will read the first two columns and plot as x and y)

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

batplot file1.xye file2.xye --xaxis 2theta --interactive
# Plot with 2theta as X axis and open interactive menu

batplot file1.xye:0.25995 file2.qye --stack --interactive
# Stack two files and open the interactive menu

batplot file1.xye file2.xye. --wl 1.54 --stack --interactive
# Stack two files and open the interactive menu

batplot file1.xye:0.25995 file2.qye structure1.cif structure2.cif --stack --interactive
# Stack two files with reference cif ticks and open the interactive menu

batplot allfiles
# Plot all XY files in current directory on the same figure

batplot allfiles --stack --interactive
# Plot all XY files stacked with interactive menu

batplot allfiles --xaxis 2theta --xrange 10 80 --interactive
# Plot all files with custom axis, range, and interactive menu

batplot allfiles --norm --interactive
# Plot all files with normalized intensities

batplot allxyfiles
# Only plot .xy files (natural ordering: file2 before file10)

batplot "/path/to/data" allnorfiles --interactive
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
```

### Wavelength Specification

Batplot supports flexible wavelength specification for XRD data conversion and CIF tick calculation. You can specify wavelengths globally using `--wl` or per-file using colon syntax.

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
# Single wavelength for Q conversion
batplot data.xye:1.5406 --xaxis Q
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

**Note:** Voltage and current columns are optional for summary files. If not present, synthetic values are generated internally for compatibility.

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

**GC (Galvanostatic Cycling)**: Voltage vs. capacity plots showing charge/discharge cycles.

**CV (Cyclic Voltammetry)**: Voltage vs. current plots for electrochemical characterization. Supports full interactive menu with cycle-by-cycle styling, colors, visibility control, and session save/load.

**dQdV**: Differential capacity analysis (dQ/dV vs. voltage).

**CPC (Capacity Per Cycle)**: Plot charge/discharge capacity and coulombic efficiency vs. cycle number. Supports multiple files with individual color customization.

### Example Usage

```bash
batplot file.csv --gc --interactive
# Plot GC data with interactive menu

batplot file.csv --dqdv
# Plot dQdV curve

batplot file.mpt --cv --interactive
# Plot CV data with full interactive menu support

batplot file.csv --xaxis time --interactive
# Plot time (h) vs voltage (V) from CSV file with full interactive menu
# All interactive commands (p, i, s, b, f, l, etc.) are available

batplot file.mpt --xaxis time --interactive
# Plot time (h) vs voltage (V) from MPT file with interactive menu

batplot file1.csv file2.csv --xaxis time --stack --interactive
# Plot multiple time-voltage curves stacked with interactive menu

batplot file1.csv file2.csv file3.mpt --cpc --mass 6.2 --interactive
# Plot multiple CPC files on same axes with interactive menu
# Each file can be styled individually (colors)
# Line styles, fonts, and markers apply globally
# Note: --mass only required for .mpt files

batplot file.csv --cpc --interactive
# Plot single CPC file with interactive menu
```

### Time Mode (`--xaxis time`)

When using `--xaxis time` with CSV or MPT files, batplot plots time (in hours) on the X-axis and voltage (in volts) on the Y-axis, similar to the EC panel in operando mode. This mode supports:
- Full interactive menu with all features (p, i, s, b, f, l, m, etc.)
- Multiple file plotting
- Stack mode (`--stack`) for offset curves
- Range control (`--xrange`)
- All standard styling and export options

The time mode automatically extracts time columns (e.g., "Total Time", "time/s") and voltage columns (e.g., "Voltage(V)", "Ewe/V") from the file and converts time to hours.

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

### Requirements

- Place operando files (`.xye`, `.qye`, `.xy`, `.dat`) in the directory.
- Optionally include EC file (`.mpt`) for dual-panel mode with electrochemistry.
- Navigate to the folder before running Batplot.

### Example Usage

```bash
batplot --operando --interactive
# Launch operando mode with interactive editing
# Shows dual-panel view if .mpt file is present, single panel otherwise

batplot --operando --wl 0.25995 --interactive
# Launch operando mode with interactive editing, converting x axis from 2theta to Q space
```

### Operando-Only Mode

If no `.mpt` file is present, operando mode displays only the contour plot. The interactive menu adapts to allow full control of all four spines (left, right, top, bottom) for the single panel.

---

## Contact & Support

For questions, bug reports, or feature requests:

- **GitHub**: https://github.com/tiandai-chem/batplot
- **Email**: tianda@uio.no
- **Mailing List**: Subscribe to batplot-lab@kjemi.uio.no for updates, feature announcements, and community discussions

Feel free to open an issue on GitHub or reach out via email!

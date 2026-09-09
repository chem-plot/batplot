# 12. Summary of Flags

All flags use the double-dash (`--`) prefix. Below are tables organized by mode. Interactive **menu keys** live in each mode chapter (see [Interactive menus index](10-interactive-menus.md)), not here.

## 12.1  General Flags 

__Flag__

__Description__

__Example__

--interactive / --i

Open the live interactive menu alongside the figure

```text
batplot file.xy --interactive
```

--out FILE

Save figure to file (default .svg if no extension)

```text
batplot file.xy --out plot.svg
```

--all

Batch mode: export each file as a separate figure

```text
batplot --all
```

--xaxis TYPE

Optional X-axis type or label: Q, q, 2theta, r, k, energy, time, or custom. Not required for simple two-column plotting.

```text
batplot file.xy --xaxis 2theta
```

--help/--h

Show help (add `xy`, `ec`, `op`, or `histo` for mode-specific help)

```text
batplot --help ec
```

--version/--v

Show version and release notes

```text
batplot --version
```

--manual/--m

Open the online user manual (https://chem-plot.github.io/batplot/)

```text
batplot --manual
```

## 12.2  1D / XY Mode Flags/Keywords

__Flag__

__Description__

__Example__

--wl λ

Wavelength (Å) for 2θ ↔ Q conversion

```text
batplot file.xye --wl 1.5406
```

--xrange MIN MAX

Set X-axis display range

```text
batplot file.xy --xrange 10 80
```

--stack

Stack curves vertically (auto-normalizes)

```text
batplot f1.xy f2.xy --stack
```

--delta N

Spacing between stacked curves

```text
batplot f1.xy f2.xy --stack --delta 0.2
```

--norm

Normalize Y intensity to the 0 to 1 range

```text
batplot file.xy --norm
```

--ro

Swap X and Y axes

```text
batplot file.csv --xaxis time --ro
```

--1d / --2d

Plot first derivative dy/dx

```text
batplot file.xy -1d --stack
```

--chik

EXAFS χ(k) plot

```text
batplot data.chik --chik
```

--kchik

EXAFS kχ(k): emphasize mid-k features

```text
batplot data.chik --kchik
```

--k2chik

EXAFS k²χ(k): most common weighting

```text
batplot data.chik --k2chik
```

--k3chik

EXAFS k³χ(k): emphasize high-k / heavy backscatterers

```text
batplot data.chik --k3chik
```

--readcol X Y

Specify X and Y columns (1-indexed, per-file or multi-curve)

```text
batplot file.xy --readcol 2 3
```

--readcol<ext> X Y

Columns for selected extension only

```text
batplot --operando --readcoldat 2 3
```

--convert λ1 λ2 / q

Convert XRD and export to converted/ subfolder

```text
batplot file.xye --convert 1.54 q
```

```text
batplot file.xy --convert 1.54 0.71
```

allfiles

Plot all files under the path

```text
batplot allfiles --xaxis 2theta
```

all<ext>files

Plot all files with selected extension under the path

```text
batplot alltxtfiles --xaxis Energy
```

!!! note

    allfiles is a keyword, not a flag, it is not the same as --all flag.

## 12.3  Electrochemistry (EC) Mode Flags

__Flag__

__Description__

__Example__

--gc

Galvanostatic cycling: potential vs. specific capacity

```text
batplot file.mpt --gc --mass 7
```

--cv

Cyclic voltammetry: potential vs. current

```text
batplot file.mpt --cv
```

--dqdv

Differential capacity: dQ/dV vs. potential

```text
batplot file.csv --dqdv
```

--cpc

Capacity per cycle \+ coulombic efficiency

```text
batplot file.csv --cpc
```

--mass MG

Active material mass in mg (required for .mpt files in GC/CPC)

```text
batplot file.mpt --gc --mass 6.5
```

--xaxis time

Plot time (h) vs. potential from Neware .csv or Biologic .mpt files

```text
batplot file.csv --xaxis time --i
```

--ro

Swap X and Y axes

```text
batplot file.mpt --gc --ro --mass 7
```

--epc

Energy per cycle (if supported)

```text
batplot file.csv --epc --i
```

## 12.4  *Operando* Mode Flags

__Flag__

__Description__

__Example__

--operando

Launch *operando* / contour mode from current folder or path

```text
batplot --operando --i
```

--contour

Alias for --operando (identical behavior)

```text
batplot --contour --i /path/
```

--wl λ

Wavelength (Å) to convert *operando* data from 2θ to Q

```text
batplot --operando --wl 1.54 --i
```

--xaxis

Specify data type

```text
batplot --operando --xaxis 2theta
```

--1d / --2d

Plot derivatives of each scan as the contour

```text
batplot --operando --1d --i
```

--readcolc / --readcols

Contour scan columns / EC side-panel columns

```text
batplot --operando --readcolc 2 3 --readcols 1 2 --i
```

--average / --sum

Average or sum scans when assembling the contour

```text
batplot --operando --average --i
```

## 12.5 Histogram Mode Flags

```text
batplot sizes.csv --histo --i
```

```text
batplot data.txt --histo --histocol Length
```

```text
batplot sizes.csv --histo --histocol 1 --binwidth 1 --i
```

```text
batplot sizes.csv --histo --histocol 1 --bins 40 --i
```

```text
batplot sizes.csv --histo --histocol 1 --xrange 0 16 --i
```

| Flag | What it does |
|------|--------------|
| `--histo` | Histogram mode |
| `--histocol N` | Column number or header name |
| `--binwidth W` | Bin width |
| `--bins N` | Number of bins |
| `--xrange A B` | Display range |

## 12.6 Utilities and sessions

Full worked terminal output for these lives in [Utilities](11-utilities.md). Quick commands:

```text
batplot --showcol file.csv
```

```text
batplot data.txt --strip-header 5
```

```text
batplot file.xy --xaxis 2theta --save
```

```text
batplot --all --format png
```

```text
batplot a.xy --ry b.xy --txaxis --i
```

| Flag | What it does |
|------|--------------|
| `--showcol` | Preview columns |
| `--strip-header N` | Drop first N lines → `stripped/` |
| `--save` | Save `.pkl` session(s) without `--i` |
| `--format EXT` | Batch export image format |
| `--ry` / `--txaxis` | Right y-axis / top x for `--ry` curves |

## 12.7 Extra EC flags

```text
batplot cell.mpt --gc --mass 7 --i
```

```text
batplot cell.csv --gc --cd 0.1 --pw 2.5 4.2 --i
```

| Flag | What it does |
|------|--------------|
| `--pw A B` | Potential window (custom GC; use with `--cd`) |
| `--cd RATE` | C-rate / related custom GC helper (use with `--pw`) |
| `--mass M` | Active mass (mg, or `12g`) |

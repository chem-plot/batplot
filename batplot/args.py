"""Argument parsing for batplot CLI.

This module handles all command-line argument parsing for batplot. It defines
the command-line interface, including:
- All command-line flags and options
- Help text for each mode (XY, EC, Operando)
- Argument validation and conversion
- Colored help output (if rich library is available)

HOW COMMAND-LINE ARGUMENTS WORK:
--------------------------------
When you run (for example) 'batplot --xaxis 2theta file.xy --i', Python's argparse library:
1. Parses the command line into structured arguments
2. Validates that required arguments are present
3. Converts string arguments to appropriate types (int, float, bool, etc.)
4. Groups related arguments together
5. Provides helpful error messages if arguments are invalid

This module defines all the valid arguments and their meanings.
"""

from __future__ import annotations

import argparse
import sys
import re

# ====================================================================
# HELP OUTPUT
# ====================================================================
# The 'rich' library provides colored terminal output. If available,
# it is used to make help text more readable by highlighting:
# - Command-line flags in cyan
# - File extensions in yellow
# - Example commands in green
# - Section headers in blue
#
# If rich is not installed, we fall back to plain text (still works fine).
# ====================================================================
try:
    from rich.console import Console  # type: ignore[import]
    from rich.markup import escape  # type: ignore[import]
    _console = Console()
    _HAS_RICH = True
except ImportError:
    _console = None
    _HAS_RICH = False


def _colorize_help(text: str) -> str:
    """
    Add colors to help text by highlighting flags and special elements.
    
    HOW IT WORKS:
    ------------
    Uses regular expressions to find patterns in help text and wrap them
    with rich markup codes for colored output.
    
    Patterns colored:
    - Command-line flags: --flag or -f → cyan
    - File extensions: .xy, .csv, etc. → yellow
    - Example commands: batplot ... → green
    - Section headers: lines ending with : → bold blue
    - Bullet points: • → bold
    
    Example:
        Input:  "batplot file.qye --i"
        Output: "[green]batplot[/green] [yellow]file.qye[/yellow] [cyan]--i[/cyan]"
    
    Args:
        text: Plain help text (uncolored)
        
    Returns:
        Text with rich markup codes for colored output
        (or original text if rich is not available)
    """
    if not _HAS_RICH:
        return text  # No coloring available, return as-is
    
    # STEP 1: Escape any existing markup to prevent conflicts
    # This ensures that if the help text already contains rich markup,
    # we don't accidentally break it
    text = escape(text)
    
    # STEP 2: Color command-line flags
    # Pattern: --flag-name or -f (single letter flag)
    # Example: "--i" → "[cyan]--i[/cyan]"
    text = re.sub(r'(--[\w-]+)', r'[cyan]\1[/cyan]', text)  # Long flags (--flag)
    text = re.sub(r'(\s-[a-zA-Z]\b)', r'[cyan]\1[/cyan]', text)  # Short flags (-f)
    
    # STEP 3: Color file extensions
    # Pattern: .extension (2-4 characters)
    # Example: ".xy" → "[yellow].xy[/yellow]"
    text = re.sub(r'(\.\w{2,4}\b)', r'[yellow]\1[/yellow]', text)
    
    # STEP 4: Color example commands
    # Pattern: "batplot" followed by arguments
    # Example: "batplot file.xy --i" → "[green]batplot file.xy --i[/green]"
    text = re.sub(r'(batplot\s+[^\n]+)', r'[green]\1[/green]', text)
    
    # STEP 5: Color section headers
    # Pattern: Lines that start with capital letter and end with colon
    # Example: "Examples:" → "[bold blue]Examples:[/bold blue]"
    text = re.sub(r'^([A-Z][\w\s/()]+:)$', r'[bold blue]\1[/bold blue]', text, flags=re.MULTILINE)
    
    # STEP 6: Make bullet points bold
    text = text.replace('•', '[bold]•[/bold]')
    
    return text


def _print_help(text: str) -> None:
    """Print help text with optional coloring.
    
    Args:
        text: Help text to print
    """
    if _HAS_RICH and _console:
        colored_text = _colorize_help(text)
        _console.print(colored_text)
    else:
        print(text)


def _print_general_help() -> None:
    # Import version here to avoid circular imports
    try:
        from . import __version__
        version_str = f"batplot v{__version__} — quick plotting for lab data\n\n"
    except ImportError:
        version_str = "batplot — quick plotting for lab data\n\n"
    
    msg = (
        version_str +
        "What it does:\n"
        "  • XY: XRD/PDF/XAS/User defined curves\n"
        "  • EC: Galvanostatic cycling(GC)/Capacity per cycle(CPC)/Diffrential capacity(dQdV)/Cyclic Voltammetry(CV) from Neware (.csv) or Biologic (.mpt)\n"
        "  • Operando: contour from .xy/.xye/.dat/.brml; Bruker .brml (cyc1/cyc2/cyc3) with optional .mpt or DataLogger CSV side panel\n"
        "  • Batch: export vector plots for all files in a directory\n"
        "  • Interactive mode: --i flag opens a menu for styling, ranges, export, and save\n\n"
        "How to run (basics):\n"
        "  [1D (XY) — XRD, PDF, XAS]\n"
        "    batplot file.xy file2.qye --i              # Plot with interactive menu\n"
        "    batplot pattern.xye --xaxis 2theta --xrange 10 80    # XRD: 2θ axis, zoom 10–80°\n"
        "    batplot data.xye:1.5406 --wl 1.54 --i     # Wavelength for Q conversion\n"
        "    batplot file.xy --out figure.svg                     # Save to file (default .svg)\n"
        "    batplot file1.xy file2.xy --stack --i      # Stack curves\n"
        "    batplot file1.xy:1.54 file2.qye structure.cif --stack --i  # Stack + CIF\n"
        "    batplot file1.xy --ry file2.xy --ry --i    # Dual y-axis\n"
        "    batplot allfiles --i                      # All files in directory\n"
        "    batplot --all                                       # Batch: export each to Figures/\n\n"
        "  [Electrochemistry]\n"
        "    batplot --gc file.mpt --mass 7.0 --i       # GC from .mpt\n"
        "    batplot --gc file.csv --i                 # GC from .csv\n"
        "    batplot --dqdv file.csv --i               # dQ/dV\n"
        "    batplot --cv file.mpt --i                 # Cyclic voltammetry\n"
        "    batplot --cpc file.csv --mass 3.52 --i     # Capacity per cycle\n\n"
        "  [Operando]\n"
        "    batplot --operando --i [FOLDER]  # Contour from folder\n"
        "    batplot Path/to/file --operando --wl 0.709 --i  # Bruker .brml, Q conversion\n\n"
        "Features:\n"
        "  • Interactive (--i): styling, ranges, fonts, export, sessions\n"
        "  • XRD wavelength: --wl 1.54 or file.xye:1.5406 for Q conversion\n"
        "  • X-axis range: --xrange min max\n"
        "  • Save: --out filename (default .svg)\n"
        "  • Batch: --all exports each file to Figures/\n"
        "  • More: --help xy / --help ec / --help op\n\n"
        
        "More help:\n"
        "  batplot --version       # Version and release info (with option to show full release notes)\n"
        "  batplot --showcol FILE [FILE...]   # Preview column names + first 10 values per column\n"
        "  batplot --help          # This help\n"
        "  batplot --help xy       # XY file plotting guide\n"
        "  batplot --help ec       # Electrochemistry (GC/dQdV/CV/CPC) guide\n"
        "  batplot --help op       # Operando contour guide (also: batplot --help contour)\n"
        "  batplot --manual        # Open the illustrated txt manual with highlights\n\n"

        "Contact & Updates:\n"
        "  Subscribe to batplot-lab@kjemi.uio.no for updates\n"
        "  (If you are not from UiO, send an email to sympa@kjemi.uio.no with the subject line \"subscribe batplot-lab@kjemi.uio.no your-name\")\n"
        "  Author name: Tian Dai\n"
        "  Email: tianda@uio.no\n"
        "  Personal page: https://www.mn.uio.no/kjemi/english/people/aca/tianda/\n"
        "  GitHub: https://github.com/chem-plot/batplot\n"
        "  Kindly cite Tian's github page if the plot is used for publication\n"
        )
    _print_help(msg)


def _print_xy_help() -> None:
    msg = (
        "XY plots (XRD/PDF/XAS and many more)\n\n"
        "Supported files: .xye .xy .qye .dat .csv .gr .nor .chik .chir .txt .brml .raw .xrdml .rasx and other formats. CIF overlays supported.\n\n"
        "Axis detection: .qye→Q, .gr→r, .nor→energy, .chik→k, .chir→r, else use --xaxis (Q, 2theta, r, k, energy, time or user defined).\n"
        "If mixing 2θ data in Q, give wavelength per-file (file.xye:1.5406) or global flag --wl.\n"
        "A wavelength can be converted into a different wave length by file.xye:1.54:0.709.\n"
        "For electrochemistry CSV/MPT time-potential plots, use --xaxis time.\n\n"
        "Examples:\n"
        "  batplot file.xy file2.xye --xaxis 2theta --i         # Plot XRD data in 2theta space\n"
        "  batplot file1.xye:1.5406 file2.txt:0.709 --i         # Plot XRD data in different wavelengths in q space\n"
        "  batplot data1.xye data2.xye --wl 1.54 --i            # Same Wavelength for Q conversion\n"
        "  batplot file.xy --out figure.svg                     # Save to file\n"
        "  batplot a.xye:1.5406 b.qye --stack --i               # Stack in q space\n"
        "  batplot pattern.qye ticks.cif --xaxis q --i          # XRD + CIF ticks\n"
        "  batplot file1.xy file2.xy --1d --stack --i           # First derivative\n"
        "  batplot allfiles --i                                 # All files in directory\n"
        "  batplot allfiles --xaxis 2theta --xrange 10 80       # All with axis and range\n"
        "  batplot --all --xaxis 2theta --xrange 10 80          # Batch: export each file → Figures/\n"
        "  batplot file1.xy file2.xye --xaxis 2theta style.bps  # Style + export\n\n"
        "Tips and options:\n"
        "[XY plot]\n"
        "  --i            : open interactive menu for styling, ranges, fonts, export, sessions\n"
        "  --delta <float>           : spacing between curves, e.g. --delta 0.1\n"
        "  --norm                    : normalize intensity to 0-1 range. Stack mode (--stack) auto-normalizes\n"
        "  --chik                    : EXAFS χ(k) plot (sets labels to k (Å⁻¹) vs χ(k))\n"
        "  --kchik                   : multiply y by x for EXAFS kχ(k) plots (sets labels to k (Å⁻¹) vs kχ(k) (Å⁻¹))\n"
        "  --k2chik                  : multiply y by x² for EXAFS k²χ(k) plots (sets labels to k (Å⁻¹) vs k²χ(k) (Å⁻²))\n"
        "  --k3chik                  : multiply y by x³ for EXAFS k³χ(k) plots (sets labels to k (Å⁻¹) vs k³χ(k) (Å⁻³))\n"
        "  --1d                      : plot the first derivative (dy/dx) of the datasets\n"
        "  --2d                      : plot the first derivative (dy/dx) of the datasets (alias for --1d)\n"
        "  --xrange <min> <max>      : set x-axis range, e.g. --xrange 0 10\n"
        "  --out <filename>          : save figure to file, e.g. --out file.svg\n"
        "  --xaxis <type>            : set x-axis type (Q, 2theta, r, k, energy, rft, time, or user defined)\n"
        "                              Q and q are equivalent (case-insensitive). e.g. --xaxis 2theta, --xaxis Q, --xaxis time\n"
        "  --ro                      : swap x and y axes (exchange x and y values before plotting)\n"
        "                              e.g. --xaxis time --ro plots time as y-axis and potential as x-axis\n"
        "  --wl <float>              : set wavelength for Q conversion for all files, e.g. --wl 1.5406\n"
        "  --convert <from> <to>     : convert XRD data and export to 'converted' subfolder:\n"
        "                              - <wl1> <wl2>  : convert 2θ from wavelength1 to wavelength2\n"
        "                              - <wl> q or Q  : convert 2θ (with wavelength) to Q space (q and Q equivalent)\n"
        "                              - q or Q <wl>  : convert Q space to 2θ (with wavelength)\n"
        "                              Works with --readcol for custom column layout (per-file, per-ext, or global):\n"
        "                                batplot data.csv --readcol 3 4 --convert 1.54 q\n"
        "                                batplot f1.txt --readcol 2 3 f2.txt --readcol 5 6 --convert 1.54 q\n"
        "                              Directory: pass a folder to convert all .xy/.xye/.qye/.dat/.csv/.txt files:\n"
        "                                batplot /path/to/folder --convert 0.25448 1.54\n"
        "                              Batch in current folder: use allfiles token (non-convertible files are skipped):\n"
        "                                batplot allfiles --convert q 1.54\n"
        "                              Examples:\n"
        "                                batplot file.xye --convert 1.54 0.25\n"
        "                                batplot file.xye --convert 1.54 q\n"
        "                                batplot file.qye --convert Q 1.54\n"
        "  File wavelength syntax   : specify wavelength(s) per file using colon syntax:\n"
        "                              - file:wl          : single wavelength (for Q conversion or CIF 2theta calculation)\n"
        "                              - file:wl1:wl2     : dual wavelength (convert 2theta→Q using wl1, then Q→2theta using wl2)\n"
        "                              - file.cif:wl      : CIF file with wavelength for 2theta tick calculation\n"
        "                              Examples:\n"
        "                                batplot data.xye:1.5406 --xaxis 2theta\n"
        "                                batplot data.xye:0.25:1.54 --xaxis 2theta\n"
        "                                batplot data.xye pattern.cif:0.25448 --xaxis 2theta\n"
        "  --readcol <x_col> <y_col> : specify which columns to read as x and y (1-indexed)\n"
        "    Per-file:  file1.xy --readcol 2 3 file2.xy --readcol 4 5  (different cols per file)\n"
        "    Multi-curve: file.xy --readcol 1 2 1 3  (plot cols 1,2 and 1,3 as two curves)\n"
        "    Range: file.txt --readcol 1 2-20  (col 1 as x, cols 2..20 as 19 y-curves)\n"
        "    With wavelength: file.xy:1.54 --readcol 2 3  (col 2 as 2θ, convert to Q using λ=1.54 Å)\n"
        "    With --convert: file.csv --readcol 3 4 --convert 1.54 q  (custom cols for conversion)\n"
        "  --readcolxy <x> <y>       : read columns for .xy files only\n"
        "  --readcolxye <x> <y>      : read columns for .xye files only\n"
        "  --readcolqye <x> <y>      : read columns for .qye files only\n"
        "  --readcolnor <x> <y>      : read columns for .nor files only\n"
        "  --readcoldat <x> <y>      : read columns for .dat files only\n"
        "  --readcolcsv <x> <y>      : read columns for .csv files only\n"
        "  --readcol<ext> <x> <y>    : read columns for custom extension (e.g., --readcolafes 2 3 for .afes files)\n"
        "  --fullprof <args>         : FullProf overlay options\n"
        "  --stack                   : stack curves vertically (auto-enables normalization)\n"
        "  --ry                      : plot preceding file(s) on right y-axis (dual y-axis). Disables --stack.\n"
        "                              Example: batplot file1.xy --ry file2.xy --ry file3.xy file4.xy --ry\n"
        "                              plots file1, file2, file4 on right y-axis; file3 on left.\n"
        "  --txaxis                  : with --ry, use top x-axis for right y-axis curves (default: shared bottom x)\n"
    )
    _print_help(msg)


def _print_ec_help() -> None:
    msg = (
        "Electrochemistry (GC, dQ/dV, CV, and CPC)\n\n"
        "Data export requirements from instruments:\n"
        "  • Neware: Customized report — check all boxes\n"
        "  • Biologic: Export all info to .mpt file\n\n"
        "Use --i for styling, colors, line widths, axis scales, etc.\n"
        "GC from .mpt: requires active mass in mg to compute mAh g⁻¹.\n"
        "  batplot --gc file.mpt --mass 6.5 --i\n\n"
        "GC from supported .csv: specific capacity read directly when available; use --mass for\n"
        "  Neware absolute-capacity files (Cycle Index / Step Index / DataPoint format).\n"
        "  batplot --gc file.csv\n"
        "  batplot --gc file.csv --mass 3.52       # Neware absolute-capacity CSV\n\n"
        "Per-file mass: repeat --mass once per file that needs it, in file order.\n"
        "  batplot f1.mpt --mass 6.5 f2.csv f3.mpt --mass 7.0 --gc\n"
        "  batplot f1.csv --mass 3.52 f2.mpt --mass 5.0 --cpc\n"
        "  # Files without --mass between them use the global --mass value (or none)\n"
        "  # Single --mass applies to all files: batplot f1.mpt f2.mpt --gc --mass 7.0\n\n"
        "dQ/dV from supported .csv (pre-calculated column or computed from GC data):\n"
        "  batplot --dqdv file.csv\n"
        "  batplot --dqdv file.csv --mass 3.52     # Neware absolute-capacity CSV\n\n"
        "Cyclic voltammetry (CV) from .mpt or .txt: plots potential vs current for each cycle.\n"
        "  batplot --cv file.mpt\n"
        "  batplot --cv file.txt\n\n"
        "Capacity-per-cycle (CPC) with coulombic efficiency from .csv, .xlsx, or .mpt.\n"
        "Supports multiple files with individual color customization:\n"
        "  batplot --cpc file.csv                 # Neware CSV (specific capacity)\n"
        "  batplot --cpc file.csv --mass 3.52     # Neware absolute-capacity CSV\n"
        "  batplot --cpc file.xlsx                # Landt/Lanhe Excel (Chinese tester)\n"
        "  batplot --cpc file.mpt --mass 1.2              # Biologic MPT\n"
        "  batplot file1.csv --mass 3.52 file2.mpt --mass 1.2 --cpc   # Per-file mass\n"
        "  batplot --cpc file1.csv file2.xlsx file3.mpt --mass 1.2 --i\n\n"
        "Excel support: Landt/Lanhe (蓝电/蓝河) .xlsx files with Chinese headers:\n"
        "  Expected structure: Row 1=filename, Row 2=headers, Row 3+=data\n\n"
        "Batch mode: --all exports each file to Figures/ (default .svg). Use --format png for raster.\n"
        "  batplot --gc --all --mass 7.0          # All GC files\n"
        "  batplot --cv --all                     # All CV files\n"
        "  batplot --all style.bps --gc --mass 7   # Batch with style\n"
        "  batplot --all ./Style/geom.bpsg --cpc --mass 6  # Apply style+geom from relative path\n\n"
        "Normal mode with style files: Apply style to multiple files and export.\n"
        "  batplot file1.csv file2.mpt style.bps --gc --mass 7 --out output.svg  # GC mode\n"
        "  batplot file1.csv file2.mpt ./Style/style.bps --gc --mass 7 --out output.svg  # Style from relative path\n"
        "  batplot file1.mpt file2.txt style.bpsg --cv                           # CV mode\n"
        "  batplot file1.mpt file2.txt ./Style/style.bpsg --cv                   # Style+geom from relative path\n"
        "  batplot file1.csv file2.csv style.bps --dqdv                          # dQdV mode\n"
        "  batplot file1.csv file2.csv ./Style/style.bps --dqdv                  # Style from relative path\n"
        "  batplot file1.csv file2.mpt style.bpsg --cpc --mass 6                 # CPC mode\n"
        "  batplot file1.csv file2.mpt ./Style/style.bpsg --cpc --mass 6         # Style+geom from relative path\n\n"
        "Multi-file (EC/CV/dQdV): Press c, then type fall viridis (all files), f1-5 viridis (files 1–5), or f1 f3 f5 4.\n"
        "CPC (ly/ry): Type 1-5 viridis or 1 3 5 4 for file range. Exported via p, restored via i/s/b.\n\n"
        "Interactive (--i): choose cycles, colors/palettes, line widths, axis scales (linear/log/symlog),\n"
        "rename axes, toggle ticks/titles/spines, print/export/import style (.bps/.bpsg), save session (.pkl).\n"
        "Multi-file: In c (cycles/colors), type fall viridis (all files), f1-5 viridis (files 1–5), or f1 f3 f5 4 (files 1,3,5).\n"
        "Note: Batch mode (--all) exports SVG files automatically; --i is for single-file plotting only.\n\n"
        "Axis swapping:\n"
        "  --ro                      : swap x and y axes (exchange x and y values before plotting)\n"
        "                              e.g. --gc --ro plots potential as x-axis and capacity as y-axis\n"
        "                              e.g. --xaxis time --ro plots time as y-axis and potential as x-axis\n"
    )
    _print_help(msg)


def _print_op_help() -> None:
    msg = (
        "Operando contour plots (--operando or --contour, same behavior)\n\n"
        "Example usage:\n"
        "  batplot --operando --i --wl 0.25995  # Interactive mode with Q conversion\n"
        "  batplot --contour --i [FOLDER]      # Same as --operando\n"
        "  batplot --operando --xaxis 2theta              # Using 2theta axis\n"
        "  batplot --operando --1d --i           # Plot derivatives as contour with interactive menu\n"
        "  batplot --operando --2d --i          # Plot derivatives (alias for --1d)\n\n"
        "Bruker operando (.brml):\n"
        "  • Place .brml files (e.g. XX_cyc1.brml, XX_cyc2.brml) in the folder.\n"
        "  • Each .brml is expanded into per-scan rows; files sorted by cyc1/cyc2/cyc3.\n"
        "  • Use --wl for Q conversion: batplot RA_O5 --operando --wl 0.709 --i\n"
        "  • EC side panel: .mpt or Biologic DataLogger CSV (*--DataLogger.csv), sorted by cyc.\n"
        "  • Time vs potential is concatenated across files (continuous time axis).\n\n"
        "Standard XY files:\n"
        "  • Folder should contain .xy/.xye/.qye/.dat files.\n"
        "  • Intensity scale is auto-adjusted between min/max values.\n"
        "  • If no .qye present, provide --xaxis 2theta or set --wl for Q conversion.\n"
        "  • If a .mpt file is present, a side panel is added for dual-panel mode (time/potential/temp/etc.).\n"
        "  • Without a .mpt file, operando-only mode shows the contour plot alone.\n"
        "  • --1d / --2d: plot the first derivative (dy/dx) of each scan as a contour plot.\n\n"
        "Column selection (operando-specific):\n"
        "  --readcolc <x> <y>  : columns for contour plot (x,y in .xy/.xye/.qye/.dat files)\n"
        "  --readcols <x> <y>  : columns for side panel (x,y in .mpt file)\n"
        "  Example: batplot --operando --readcolc 2 3 --readcols 1 2 --i\n\n"
        "Interactive (--i): menu has (Styles), (Operando), (Side Panel), (Options) columns.\n"
        "Resize axes/canvas, change colormap, set intensity range (oz), side-panel options,\n"
        "geometry tweaks, toggle spines/ticks/labels, print/export/import style, save session.\n"
    )
    _print_help(msg)


def build_parser() -> argparse.ArgumentParser:
    """
    Build the argument parser for batplot command-line interface.
    
    HOW ARGUMENT PARSING WORKS:
    --------------------------
    This function creates an ArgumentParser object that defines all valid
    command-line arguments for batplot. When you run 'batplot file.xy --i',
    argparse uses this parser to:
    1. Recognize which arguments are valid
    2. Extract values from the command line
    3. Convert them to appropriate Python types (int, float, bool, etc.)
    4. Store them in a namespace object (args.files, args.interactive, etc.)
    
    ARGUMENT TYPES:
    --------------
    - Positional arguments: 'files' - list of file paths (can be 0 or more)
    - Flags (boolean): '--i' - True if present, False if absent
    - Options with values: '--mass 7.0' - requires a value (float in this case)
    - Optional arguments: '--help xy' - can have optional value
    
    WHY add_help=False?
    -------------------
    We use a custom help system that supports topic-specific help:
    - 'batplot --help' → general help
    - 'batplot --help xy' → XY mode help
    - 'batplot --help ec' → EC mode help
    - 'batplot --help op' → Operando mode help
    
    This gives users more targeted help instead of one giant help page.
    
    Returns:
        Configured ArgumentParser object ready to parse command-line arguments
    """
    # Create parser with custom help system (we handle help ourselves)
    parser = argparse.ArgumentParser(add_help=False)
    
    # ====================================================================
    # TOPIC-AWARE HELP SYSTEM
    # ====================================================================
    # Instead of standard --help, we support topic-specific help:
    #   batplot --help        → general help
    #   batplot --help xy     → XY mode help
    #   batplot --help ec     → EC mode help
    #   batplot --help op     → Operando mode help
    #
    # nargs="?" means the argument is optional:
    #   - If not provided: const="" (empty string)
    #   - If provided: uses the value (e.g., "xy", "ec", "op")
    # ====================================================================
    parser.add_argument("--help", nargs="?", const="", metavar="topic",
                        help=argparse.SUPPRESS)  # SUPPRESS hides from auto-generated help
    parser.add_argument("--version", action="store_true", dest="version",
                        help="Show version and current release info, then exit.")
    parser.add_argument(
        "--showcol",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--manual", action="store_true", help=argparse.SUPPRESS)
    
    # ====================================================================
    # POSITIONAL ARGUMENTS (FILE PATHS)
    # ====================================================================
    # 'files' is a positional argument, meaning it doesn't need a flag.
    # nargs="*" means it accepts 0 or more values (list).
    # Examples:
    #   batplot file1.xy file2.xy        → args.files = ['file1.xy', 'file2.xy']
    #   batplot allfiles                 → args.files = ['allfiles']
    #   batplot --i            → args.files = [] (empty list)
    # ====================================================================
    parser.add_argument("files", nargs="*", help=argparse.SUPPRESS)
    parser.add_argument("--delta", type=float, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--autoscale", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--xrange", nargs=2, type=float, help=argparse.SUPPRESS)
    parser.add_argument("--out", type=str, help=argparse.SUPPRESS)
    parser.add_argument("--errors", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--xaxis", type=str, help=argparse.SUPPRESS)
    parser.add_argument("--convert", nargs=2, metavar=("FROM", "TO"), 
                        help="Convert XRD data: wavelength-to-wavelength (e.g., 1.54 0.25), wavelength-to-Q (e.g., 1.54 q), or Q-to-wavelength (e.g., q 1.54). Exports to 'converted' subfolder.")
    parser.add_argument("--extract-brml-scans", nargs="?", const="", metavar="OUT_DIR",
                        help="Extract each XRD scan from .brml file to separate .xy files. Optional OUT_DIR (default: <brml_stem>_scans).")
    parser.add_argument("--wl", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--fullprof", nargs="+", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--norm", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--chik", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--kchik", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--k2chik", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--k3chik", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--i", "--interactive", action="store_true", dest="interactive", help=argparse.SUPPRESS)
    parser.add_argument("--savefig", type=str, help=argparse.SUPPRESS)
    parser.add_argument("--stack", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--ry", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--txaxis", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--operando", "--contour", action="store_true", dest="operando", help=argparse.SUPPRESS)
    parser.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--gc", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--mass", type=float, action='append', help=argparse.SUPPRESS)
    parser.add_argument("--dqdv", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--cv", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--cpc", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--epc", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--pw", nargs=2, type=float, metavar=('V_MIN', 'V_MAX'),
                       help=argparse.SUPPRESS)
    parser.add_argument("--cd", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--b", nargs=2, type=float, metavar=('TOL_UPPER', 'TOL_LOWER'),
                       help=argparse.SUPPRESS)
    parser.add_argument("--anode", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--cathode", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--ro", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--all", type=str, nargs='?', const='all', help=argparse.SUPPRESS)
    parser.add_argument("--format", type=str, default='svg', 
                       choices=['svg', 'png', 'pdf', 'jpg', 'jpeg', 'eps', 'tif', 'tiff'],
                       help=argparse.SUPPRESS)
    parser.add_argument("--readcol", nargs=2, type=int, metavar=('X_COL', 'Y_COL'),
                       help=argparse.SUPPRESS)
    # Add extension-specific readcol arguments
    parser.add_argument("--readcolxy", nargs=2, type=int, metavar=('X_COL', 'Y_COL'),
                       help=argparse.SUPPRESS)
    parser.add_argument("--readcolxye", nargs=2, type=int, metavar=('X_COL', 'Y_COL'),
                       help=argparse.SUPPRESS)
    parser.add_argument("--readcolqye", nargs=2, type=int, metavar=('X_COL', 'Y_COL'),
                       help=argparse.SUPPRESS)
    parser.add_argument("--readcolnor", nargs=2, type=int, metavar=('X_COL', 'Y_COL'),
                       help=argparse.SUPPRESS)
    parser.add_argument("--readcoldat", nargs=2, type=int, metavar=('X_COL', 'Y_COL'),
                       help=argparse.SUPPRESS)
    parser.add_argument("--readcolcsv", nargs=2, type=int, metavar=('X_COL', 'Y_COL'),
                       help=argparse.SUPPRESS)
    parser.add_argument("--readcolc", nargs=2, type=int, metavar=('X_COL', 'Y_COL'),
                       help=argparse.SUPPRESS)
    parser.add_argument("--readcols", nargs=2, type=int, metavar=('X_COL', 'Y_COL'),
                       help=argparse.SUPPRESS)
    parser.add_argument("--1d", action="store_true", dest="derivative_1d", help=argparse.SUPPRESS)
    parser.add_argument("--2d", action="store_true", dest="derivative_2d", help=argparse.SUPPRESS)
    parser.add_argument("--canvas", action="store_true", dest="canvas",
                        help="Canvas mode: combine multiple .pkl sessions into one layout. Use numbers to edit each panel.")
    return parser


def parse_args(argv=None):
    """
    Parse command-line arguments with support for dynamic --readcol<ext> flags.
    
    HOW IT WORKS:
    ------------
    This function:
    1. Scans command line for custom --readcol<ext> flags (e.g., --readcolafes)
    2. Dynamically adds them to the parser (so argparse recognizes them)
    3. Parses all arguments using the parser
    4. Handles topic-specific help requests
    
    WHY DYNAMIC ARGUMENTS?
    ---------------------
    We support custom file extensions (e.g., .afes files). Users can specify
    which columns to read using --readcol<ext> syntax:
        batplot file.afes --readcolafes 2 3
    
    We can't know all possible extensions ahead of time, so we:
    1. Scan the command line first to find --readcol<ext> patterns
    2. Add them to the parser dynamically
    3. Then parse normally
    
    Args:
        argv: Optional list of command-line arguments (for testing).
              If None, uses sys.argv[1:] (skips program name).
    
    Returns:
        Parsed arguments namespace object with all arguments as attributes.
        Example: args.files, args.interactive, args.mass, etc.
    """
    # ====================================================================
    # STEP 1: SCAN FOR CUSTOM --readcol<ext> FLAGS
    # ====================================================================
    # Before parsing, we need to find any custom --readcol<ext> flags
    # (e.g., --readcolafes) and add them to the parser dynamically.
    #
    # Why? We support arbitrary file extensions, and users can specify
    # column selection for any extension using --readcol<ext> syntax.
    #
    # Example:
    #   batplot file.afes --readcolafes 2 3
    #   This means: for .afes files, read column 2 as x, column 3 as y
    # ====================================================================
    
    # Get command-line arguments (skip program name 'batplot')
    if argv is None:
        argv = sys.argv[1:]
    
    # Normalize short forms to long forms (both -x and --x for common flags)
    _SHORT_TO_LONG = {
        '-h': '--help', '--h': '--help',
        '-v': '--version', '-V': '--version', '--v': '--version',
        '-m': '--manual', '--m': '--manual',
        '-i': '--i', '-d': '--delta', '-r': '--xrange', '-o': '--out', '-c': '--convert',
        '-b': '--b',
    }
    argv = [_SHORT_TO_LONG.get(a, a) for a in argv]
    
    # Find all --readcol<ext> patterns in command line
    # Pattern: --readcol followed by lowercase letters/numbers
    # Example: --readcolafes → ext = 'afes'
    custom_readcol_exts = set()
    i = 0
    while i < len(argv):
        arg = argv[i]
        # Match pattern: --readcol<extension>
        match = re.match(r'^--readcol([a-z0-9]+)$', arg)
        if match:
            ext = match.group(1)  # Extract extension name
            # Skip predefined extensions (already in parser) and operando-specific (readcolc, readcols)
            if ext not in ['xy', 'xye', 'qye', 'nor', 'dat', 'csv', 'c', 's']:
                custom_readcol_exts.add(ext)
        i += 1
    
    # ====================================================================
    # STEP 1a: PRE-PARSE --ry FOR RIGHT Y-AXIS FILES
    # ====================================================================
    # Pattern: file1.xy --ry file2.xy --ry file3.xy file4.xy --ry
    # --ry applies to the file that immediately precedes it. Files 1, 2, 4 go to right y-axis.
    # Remove --ry from argv; build right_y_by_file for post-parse attachment.
    # ====================================================================
    right_y_by_file = {}  # file_token -> True if right-y
    argv_no_ry = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == '--ry':
            # Mark the immediately preceding token (if it's a file) as right-y
            if argv_no_ry and not argv_no_ry[-1].startswith('-'):
                prev = argv_no_ry[-1]
                right_y_by_file[prev] = True
            i += 1
            continue
        argv_no_ry.append(arg)
        i += 1
    argv = argv_no_ry

    # ====================================================================
    # STEP 1b: PRE-PARSE --readcol FOR PER-FILE, MULTI-CURVE, AND RANGE
    # ====================================================================
    # When pattern is "file --readcol m n" or "file --readcol x1 y1 x2 y2 ...",
    # or "file --readcol 1 2-20" (range: col 1 as x, cols 2..20 as y),
    # associate readcol with the preceding file. Remove from argv so argparse
    # does not consume it. When --readcol appears before any file (global),
    # store in global_readcol_expanded for post-parse.
    # Keys use the exact file token (e.g. "file.xy:1.54") for wavelength match.
    # Style files (.bps, .bpsg, .bpcfg) are NOT treated as file tokens so that
    # "batplot --all style.bps --readcol 2 3" uses global readcol, not per-file.
    # ====================================================================
    readcol_by_file = {}
    global_readcol_expanded = None
    filtered_argv = []
    last_file_token = None
    _STYLE_EXTENSIONS = ('.bps', '.bpsg', '.bpcfg')
    i = 0
    while i < len(argv):
        arg = argv[i]
        # Track non-option tokens as potential file specs (exclude style files)
        if not arg.startswith('-'):
            arg_lower = arg.lower()
            if not arg_lower.endswith(_STYLE_EXTENSIONS):
                last_file_token = arg
        if arg == '--readcol' and i + 1 < len(argv):
            tokens = []
            j = i + 1
            while j < len(argv):
                t = argv[j]
                if t.lstrip('-').isdigit():
                    tokens.append(('int', int(t)))
                    j += 1
                elif re.match(r'^\d+-\d+$', t):
                    tokens.append(('range', t))
                    j += 1
                else:
                    break
            # Range syntax: 1 2-20 → col 1 as x, cols 2..20 as y
            if len(tokens) == 2 and tokens[0][0] == 'int' and tokens[1][0] == 'range':
                x_col = tokens[0][1]
                lo, hi = map(int, tokens[1][1].split('-'))
                if lo <= hi:
                    pairs = [(x_col, c) for c in range(lo, hi + 1)]
                else:
                    pairs = [(x_col, c) for c in range(lo, hi - 1, -1)]
                if last_file_token is not None:
                    readcol_by_file[last_file_token] = pairs
                else:
                    global_readcol_expanded = pairs
                i = j
                continue
            # Integer pairs: 1 2 or 1 2 1 3 1 4 ...
            if len(tokens) >= 2 and len(tokens) % 2 == 0 and all(x[0] == 'int' for x in tokens):
                ints = [x[1] for x in tokens]
                pairs = [(ints[k], ints[k + 1]) for k in range(0, len(ints), 2)]
                if last_file_token is not None:
                    readcol_by_file[last_file_token] = pairs[0] if len(pairs) == 1 else pairs
                else:
                    global_readcol_expanded = pairs[0] if len(pairs) == 1 else pairs
                i = j
                continue
        filtered_argv.append(arg)
        i += 1
    
    argv = filtered_argv
    
    # ====================================================================
    # STEP 2: BUILD PARSER AND ADD DYNAMIC ARGUMENTS
    # ====================================================================
    # Create the base parser (with all standard arguments)
    parser = build_parser()
    
    # Add custom --readcol<ext> arguments dynamically
    # This allows argparse to recognize and parse them
    for ext in custom_readcol_exts:
        parser.add_argument(f"--readcol{ext}", nargs=2, type=int, metavar=('X_COL', 'Y_COL'),
                           help=argparse.SUPPRESS)
    
    # ====================================================================
    # STEP 3: HANDLE HELP REQUESTS (TOPIC-SPECIFIC HELP)
    # ====================================================================
    # We use parse_known_args() first to handle help requests without
    # complaining about unknown arguments. This allows:
    #   batplot --help xy    → XY mode help
    #   batplot --help ec    → EC mode help
    #   batplot --help op    → Operando mode help
    #
    # If help is requested, we print it and exit immediately (don't continue parsing).
    # ====================================================================
    
    # Parse with known_args_only=True to avoid errors from unknown arguments
    # This is needed because we might have custom --readcol<ext> flags that
    # weren't in the parser yet when we built it
    ns, _unknown = parser.parse_known_args(argv)
    if getattr(ns, "manual", False):
        try:
            from .manual import open_manual_url  # Lazy import avoids matplotlib startup unless needed
            open_manual_url()
            if _HAS_RICH and _console:
                _console.print("\n[green]Opened manual in browser[/green]")
            else:
                print("\nOpened manual in browser")
        except Exception as exc:  # pragma: no cover - best effort
            if _HAS_RICH and _console:
                _console.print(f"\n[red]Failed to open manual:[/red] {exc}")
            else:
                print(f"\nFailed to open manual: {exc}")
        sys.exit(0)
    
    topic = getattr(ns, 'help', None)
    
    if topic is not None:
        # Help was requested, print topic-specific help and exit
        t = (topic or '').strip().lower()
        if t in ("", "help"):
            _print_general_help()  # General help (no topic specified)
        elif t in ("xy",):
            _print_xy_help()  # XY mode help
        elif t in ("ec", "gc", "dqdv"):
            _print_ec_help()  # EC mode help (GC, dQ/dV, CV, CPC)
        elif t in ("op", "operando", "contour"):
            _print_op_help()  # Operando mode help
        else:
            # Unknown topic, show general help with warning
            _print_general_help()
            if _HAS_RICH and _console:
                _console.print("\n[yellow]Unknown help topic. Use: xy, ec, op[/yellow]")
            else:
                print("\nUnknown help topic. Use: xy, ec, op")
        sys.exit(0)  # Exit after showing help (don't continue to actual plotting)
    
    # ====================================================================
    # STEP 4: PARSE ALL ARGUMENTS (NORMAL OPERATION)
    # ====================================================================
    # No help requested, so parse all arguments normally.
    # This will raise an error if required arguments are missing or invalid.
    # ====================================================================
    args = parser.parse_args(argv)
    
    # ====================================================================
    # STEP 5: BUILD readcol_by_ext DICTIONARY
    # ====================================================================
    # Collect all --readcol<ext> arguments into a convenient dictionary
    # mapping file extension to (x_col, y_col) tuple.
    #
    # Example:
    #   User runs: batplot file.xy --readcolxy 2 3 file.afes --readcolafes 4 5
    #   Result: args.readcol_by_ext = {'.xy': (2, 3), '.afes': (4, 5)}
    #
    # This makes it easy to look up column specification for any file extension.
    # ====================================================================
    args.readcol_by_ext = {}
    
    # Check all predefined and custom extensions
    for ext in ['xy', 'xye', 'qye', 'nor', 'dat', 'csv'] + list(custom_readcol_exts):
        attr_name = f'readcol{ext}'  # e.g., 'readcolxy', 'readcolafes'
        if hasattr(args, attr_name):
            val = getattr(args, attr_name)  # Get (x_col, y_col) tuple or None
            if val is not None:
                # Store with dot prefix (e.g., '.xy' not 'xy') for easy matching
                args.readcol_by_ext[f'.{ext}'] = val
    
    # Attach per-file readcol from pre-parse (file --readcol m n or multi-curve or range)
    args.readcol_by_file = readcol_by_file

    # Global --readcol with range expansion (e.g. --readcol 1 2-20 before any file)
    if global_readcol_expanded is not None:
        args.readcol = global_readcol_expanded

    # Attach right-y indices from pre-parse (file --ry marks preceding file for right y-axis)
    args.right_y_indices = frozenset(
        i for i, f in enumerate(getattr(args, 'files', []) or [])
        if right_y_by_file.get(f, False)
    )

    # args.readcol is (x_col, y_col) tuple from argparse when global --readcol used

    return args


__all__ = ["build_parser", "parse_args"]

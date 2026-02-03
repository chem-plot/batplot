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
# COLORED HELP OUTPUT
# ====================================================================
# The 'rich' library provides colored terminal output. If available,
# we use it to make help text more readable by highlighting:
# - Command-line flags in cyan
# - File extensions in yellow
# - Example commands in green
# - Section headers in blue
#
# If rich is not installed, we fall back to plain text (still works fine).
# ====================================================================
try:
    from rich.console import Console
    from rich.markup import escape
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
    # Example: "--interactive" → "[cyan]--interactive[/cyan]"
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
        "  • Operando: contour maps from a folder of .xy/.xye/.dat/.txt and optional file as side panel\n"
        "  • Batch: export vector plots for all files in a directory\n\n"
        "  • Interactive mode: --i / --interactive flag opens a menu for styling, ranges, export, and save\n\n"
        "How to run (basics):\n"
        "  [1D(XY) curves]\n"
        "    batplot file1.xy file2.qye [option1] [option2]             # 1D curves, read the first two columns as X and Y axis by default\n"
        "    batplot allfiles                       # Plot all files in current directory on same figure\n"
        "    batplot allfiles /path/to/dir          # Plot all files in specified directory\n"
        "    batplot allfiles --i                   # Plot all files with interactive menu\n"
        "    batplot allxyfiles                     # Plot only .xy files (natural sorted)\n"
        "    batplot /path/to/data allnorfiles --i  # Plot only .nor files from a directory\n"
        "    batplot --all                          # Batch mode: all XY files → Figures/ as .svg\n"
        "    batplot --all --format png             # Batch mode: export as .png files\n"
        "    batplot --all --xaxis 2theta --xrange 10 80  # Batch mode with custom axis and range\n"
        "    batplot --all style.bps                # Batch with style: apply style.bps to all files\n"
        "    batplot --all ./Style/style.bps        # Batch with style: use relative path to style file\n"
        "    batplot --all config.bpsg              # Batch with style+geom: apply to all XY files\n"
        "    batplot file1.xy:1.54 file2.qye --stack  # Stack mode: stack all files vertically\n"
        "    batplot file1.xy:1.54 file2.qye structure.cif --stack --i # Stack mode: stack all files vertically with cif ticks\n"
        "    batplot file1.qye file2.qye style.bps  # Apply style to multiple files and export\n"
        "    batplot file1.xy file2.xye ./Style/style.bps  # Apply style from relative path\n\n"
        "  [Electrochemistry]\n"
        "    batplot --gc file.mpt --mass 7.0       # EC GC from .mpt (requires --mass mg)\n"
        "    batplot --gc file.csv --i              # EC GC from supported .csv (no mass required) with interactive menu\n"
        "    batplot --gc --all --mass 7.0          # Batch: all .mpt/.csv → Figures/ as .svg\n"
        "    batplot --gc --all --mass 7 --format png  # Batch: export as .png files\n"
        "    batplot --all --dqdv style.bps --mass 7  # Batch with style: apply style.bps to all GC files\n"
        "    batplot --all --gc ./Style/style.bps --mass 7  # Batch with style: use relative path\n"
        "    batplot --all --cpc config.bpsg         # Batch with style+geom: apply to all CV files\n"
        "    batplot --all --cv ./Style/config.bpsg  # Batch with style+geom: use relative path\n"
        "    batplot --dqdv FILE.csv                # EC dQ/dV from supported .csv\n"
        "    batplot --dqdv --all                   # Batch: all .csv in directory (dQdV mode)\n"
        "    batplot --cv FILE.mpt                  # EC CV (cyclic voltammetry) from .mpt\n"
        "    batplot --cv FILE.txt                  # EC CV (cyclic voltammetry) from .txt\n"
        "    batplot --cv --all                     # Batch: all .mpt/.txt in directory (CV mode)\n\n"
        "  [Operando]\n"
        "    batplot --operando --i [FOLDER]        # Operando contour (with or without .mpt file)\n\n"
            "Features:\n"
        "  • Quick plotting with sensible defaults, no config files needed\n"
        "  • Supports many common file formats (see -h xy/ec/op)\n"
        "  • Interactive menus (--interactive): styling, ranges, fonts, export, sessions\n"
        "  • Batch processing: use 'allfiles' / 'all<ext>files' to plot together, or --all for separate files\n"
        "  • Batch exports saved to Figures/ subdirectory (default: .svg format)\n"
        "  • Batch styling: apply .bps/.bpsg files to all exports (use --all flag)\n"
        "  • Format option: use --format png/pdf/jpg/etc to change export format\n\n"
        
        "More help:\n"
        "  batplot -h xy   # XY file plotting guide\n"
        "  batplot -h ec   # Electrochemistry (GC/dQdV/CV/CPC) guide\n"
        "  batplot -h op   # Operando guide\n"
        "  batplot -m      # Open the illustrated txt manual with highlights\n\n"

        "Contact & Updates:\n"
        "  Subscribe to batplot-lab@kjemi.uio.no for updates\n"
        "  (If you are not from UiO, send an email to sympa@kjemi.uio.no with the subject line \"subscribe batplot-lab@kjemi.uio.no your-name\")\n"
        "  Kindly cite the pypi package page (https://pypi.org/project/batplot/) if the plot is used for publication\n"
        "  Email: tianda@uio.no\n"
        "  Personal page: https://www.mn.uio.no/kjemi/english/people/aca/tianda/\n"
        )
    _print_help(msg)


def _print_xy_help() -> None:
    msg = (
        "XY plots (XRD/PDF/XAS and many more)\n\n"
        "Supported files: .xye .xy .qye .dat .csv .gr .nor .chik .chir .txt and other user specified formats. CIF overlays supported.\n\n"
        "Axis detection: .qye→Q, .gr→r, .nor→energy, .chik→k, .chir→r, else use --xaxis (Q, 2theta, r, k, energy, time or user defined).\n"
        "If mixing 2θ data in Q, give wavelength per-file (file.xye:1.5406) or global flag --wl.\n"
        "A wavelength can be converted into a different wave length by file.xye:1.54:0.709.\n"
        "For electrochemistry CSV/MPT time-voltage plots, use --xaxis time.\n\n"
        "Examples:\n"
        "  batplot a.xye:1.5406 b.qye --stack --i\n"
        "  batplot a.dat b.xy --wl 1.54 --i\n"
        "  batplot pattern.qye ticks.cif:1.54 --i\n\n"
        "Plot all files together:\n"
        "  batplot allfiles                       # Plot all XY files on same figure\n"
        "  batplot allfiles /path/to/dir          # Plot all XY files in specified directory\n"
        "  batplot allfiles --stack --interactive # Stack all files with interactive menu\n"
        "  batplot allfiles --xaxis 2theta --xrange 10 80  # All files with custom axis and range\n"
        "  batplot allfiles --wl 1.5406 --delta 0.2        # All files with wavelength and spacing\n"
        "  batplot allxyfiles                     # Only plot .xy files (natural sorting)\n"
        "  batplot \"/path with spaces\" allnorfiles --interactive  # Restrict to .nor files in a folder\n\n"
        "Batch mode (separate file for each, saved to Figures/ subdirectory):\n"
        "  batplot --all                          # Export all XY files as .svg (default)\n"
        "  batplot --all --format png             # Export all XY files as .png\n"
        "  batplot --all --xaxis 2theta           # Batch mode with custom axis type\n"
        "  batplot --all --xrange 10 80           # Batch mode with X-axis range\n"
        "  batplot --all --wl 1.5406              # Batch mode with wavelength conversion\n"
        "  batplot --all style.bps                # Apply style.bps to all XY files\n"
        "  batplot --all ./Style/style.bps        # Apply style from relative path (e.g., ./Style/style.bps)\n"
        "  batplot --all config.bpsg              # Apply style+geometry to all XY files\n"
        "  batplot --all ./Style/config.bpsg      # Apply style+geometry from relative path\n\n"
        "Normal mode with style files (apply style to multiple files and export):\n"
        "  batplot file1.xy file2.xye style.bps --out output.svg  # Apply style and export\n"
        "  batplot file1.xy file2.xye ./Style/style.bps --out output.svg  # Style from relative path\n"
        "  batplot file1.xy file2.xye style.bpsg --xaxis 2theta   # Apply style+geometry\n"
        "  batplot file1.xy file2.xye ./Style/style.bpsg --xaxis 2theta  # Style+geom from relative path\n\n"
        "Tips and options:\n"
        "[XY plot]\n"
        "  --interactive / -i        : open interactive menu for styling, ranges, fonts, export, sessions\n"
        "  --delta/-d <float>        : spacing between curves, e.g. --delta 0.1\n"
        "  --norm                    : normalize intensity to 0-1 range. Stack mode (--stack) auto-normalizes\n"
        "  --chik                    : EXAFS χ(k) plot (sets labels to k (Å⁻¹) vs χ(k))\n"
        "  --kchik                   : multiply y by x for EXAFS kχ(k) plots (sets labels to k (Å⁻¹) vs kχ(k) (Å⁻¹))\n"
        "  --k2chik                  : multiply y by x² for EXAFS k²χ(k) plots (sets labels to k (Å⁻¹) vs k²χ(k) (Å⁻²))\n"
        "  --k3chik                  : multiply y by x³ for EXAFS k³χ(k) plots (sets labels to k (Å⁻¹) vs k³χ(k) (Å⁻³))\n"
        "  --xrange/-r <min> <max>   : set x-axis range, e.g. --xrange 0 10\n"
        "  --out/-o <filename>       : save figure to file, e.g. --out file.svg\n"
        "  --xaxis <type>            : set x-axis type (Q, 2theta, r, k, energy, rft, time, or user defined)\n"
        "                              e.g. --xaxis 2theta, or --xaxis time for electrochemistry CSV/MPT time-voltage plots\n"
        "  --ro                      : swap x and y axes (exchange x and y values before plotting)\n"
        "                              e.g. --xaxis time --ro plots time as y-axis and voltage as x-axis\n"
        "  --wl <float>              : set wavelength for Q conversion for all files, e.g. --wl 1.5406\n"
        "  File wavelength syntax   : specify wavelength(s) per file using colon syntax:\n"
        "                              - file:wl          : single wavelength (for Q conversion or CIF 2theta calculation)\n"
        "                              - file:wl1:wl2     : dual wavelength (convert 2theta→Q using wl1, then Q→2theta using wl2)\n"
        "                              - file.cif:wl      : CIF file with wavelength for 2theta tick calculation\n"
        "                              Examples:\n"
        "                                batplot data.xye:1.5406 --xaxis 2theta\n"
        "                                batplot data.xye:0.25:1.54 --xaxis 2theta\n"
        "                                batplot data.xye pattern.cif:0.25448 --xaxis 2theta\n"
        "  --readcol <x_col> <y_col> : specify which columns to read as x and y (1-indexed), e.g. --readcol 2 3\n"
        "  --readcolxy <x> <y>       : read columns for .xy files only\n"
        "  --readcolxye <x> <y>      : read columns for .xye files only\n"
        "  --readcolqye <x> <y>      : read columns for .qye files only\n"
        "  --readcolnor <x> <y>      : read columns for .nor files only\n"
        "  --readcoldat <x> <y>      : read columns for .dat files only\n"
        "  --readcolcsv <x> <y>      : read columns for .csv files only\n"
        "  --readcol<ext> <x> <y>    : read columns for custom extension (e.g., --readcolafes 2 3 for .afes files)\n"
        "  --fullprof <args>         : FullProf overlay options\n"
        "  --stack                   : stack curves vertically (auto-enables normalization)\n"
    )
    _print_help(msg)


def _print_ec_help() -> None:
    msg = (
        "Electrochemistry (GC, dQ/dV, CV, and CPC)\n\n"
        "Use --interactive for styling, colors, line widths, axis scales, etc.\n"
        "GC from .mpt: requires active mass in mg to compute mAh g⁻¹.\n"
        "  batplot --gc file.mpt --mass 6.5 --interactive\n\n"
        "GC from supported .csv: specific capacity is read directly (no --mass).\n"
        "  batplot --gc file.csv\n\n"
        "dQ/dV from supported .csv:\n"
        "  batplot --dqdv file.csv\n\n"
        "Cyclic voltammetry (CV) from .mpt or .txt: plots voltage vs current for each cycle.\n"
        "  batplot --cv file.mpt\n"
        "  batplot --cv file.txt\n\n"
        "Capacity-per-cycle (CPC) with coulombic efficiency from .csv, .xlsx, or .mpt.\n"
        "Supports multiple files with individual color customization:\n"
        "  batplot --cpc file.csv                 # Neware CSV\n"
        "  batplot --cpc file.xlsx                # Landt/Lanhe Excel (Chinese tester)\n"
        "  batplot --cpc file.mpt --mass 1.2      # Biologic MPT\n"
        "  batplot --cpc file1.csv file2.xlsx file3.mpt --mass 1.2 --interactive\n\n"
        "Excel support: Landt/Lanhe (蓝电/蓝河) .xlsx files with Chinese headers:\n"
        "  Expected structure: Row 1=filename, Row 2=headers, Row 3+=data\n"
        "Batch mode: Process all files and export to Figures/ subdirectory (default: .svg).\n"
        "  batplot --gc --all --mass 7.0          # All .mpt/.csv files (.mpt requires --mass)\n"
        "  batplot --gc --all --mass 7 --format png  # Export as .png instead of .svg\n"
        "  batplot --cv --all                     # All .mpt/.txt files (CV mode)\n"
        "  batplot --dqdv --all                   # All .csv files (dQdV mode)\n"
        "  batplot --cpc --all --mass 5.4         # All .mpt/.csv/.xlsx (.mpt requires --mass)\n"
        "  batplot --gc /path/to/folder --mass 6  # Process specific directory\n\n"
        "Batch mode with style/geometry: Apply .bps/.bpsg files to all batch exports.\n"
        "  batplot --all style.bps --gc --mass 7  # Apply style to all GC plots\n"
        "  batplot --all ./Style/style.bps --gc --mass 7  # Apply style from relative path\n"
        "  batplot --all config.bpsg --cv         # Apply style+geometry to all CV plots\n"
        "  batplot --all ./Style/config.bpsg --cv  # Apply style+geometry from relative path\n"
        "  batplot --all my.bps --dqdv            # Apply style to all dQdV plots\n"
        "  batplot --all ./Style/my.bps --dqdv    # Apply style from relative path\n"
        "  batplot --all geom.bpsg --cpc --mass 6 # Apply style+geom to all CPC plots\n"
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
        "Interactive (--interactive): choose cycles, colors/palettes, line widths, axis scales (linear/log/symlog),\n"
        "rename axes, toggle ticks/titles/spines, print/export/import style (.bps/.bpsg), save session (.pkl).\n"
        "Note: Batch mode (--all) exports SVG files automatically; --interactive is for single-file plotting only.\n\n"
        "Axis swapping:\n"
        "  --ro                      : swap x and y axes (exchange x and y values before plotting)\n"
        "                              e.g. --gc --ro plots voltage as x-axis and capacity as y-axis\n"
        "                              e.g. --xaxis time --ro plots time as y-axis and voltage as x-axis\n"
    )
    _print_help(msg)


def _print_op_help() -> None:
    msg = (
        "Operando contour plots\n\n"
        "Example usage:\n"
        "  batplot --operando --interactive --wl 0.25995  # Interactive mode with Q conversion\n"
        "  batplot --operando --xaxis 2theta              # Using 2theta axis\n\n"
        "  • Folder should contain XY files (.xy/.xye/.qye/.dat).\n"
        "  • Intensity scale is auto-adjusted between min/max values.\n"
        "  • If no .qye present, provide --xaxis 2theta or set --wl for Q conversion.\n"
        "  • If a .mpt file is present, an EC side panel is added for dual-panel mode.\n"
        "  • Without a .mpt file, operando-only mode shows the contour plot alone.\n\n"
        "Interactive (--interactive): resize axes/canvas, change colormap, set intensity range (oz),\n"
        "EC y-axis options (time ↔ ions), geometry tweaks, toggle spines/ticks/labels,\n"
        "print/export/import style, save session.\n"
    )
    _print_help(msg)


def build_parser() -> argparse.ArgumentParser:
    """
    Build the argument parser for batplot command-line interface.
    
    HOW ARGUMENT PARSING WORKS:
    --------------------------
    This function creates an ArgumentParser object that defines all valid
    command-line arguments for batplot. When you run 'batplot file.xy --interactive',
    argparse uses this parser to:
    1. Recognize which arguments are valid
    2. Extract values from the command line
    3. Convert them to appropriate Python types (int, float, bool, etc.)
    4. Store them in a namespace object (args.files, args.interactive, etc.)
    
    ARGUMENT TYPES:
    --------------
    - Positional arguments: 'files' - list of file paths (can be 0 or more)
    - Flags (boolean): '--interactive' - True if present, False if absent
    - Options with values: '--mass 7.0' - requires a value (float in this case)
    - Optional arguments: '--help xy' - can have optional value
    
    WHY add_help=False?
    -------------------
    We use a custom help system that supports topic-specific help:
    - 'batplot -h' → general help
    - 'batplot -h xy' → XY mode help
    - 'batplot -h ec' → EC mode help
    - 'batplot -h op' → Operando mode help
    
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
    #   batplot -h        → general help
    #   batplot -h xy     → XY mode help
    #   batplot -h ec     → EC mode help
    #   batplot -h op     → Operando mode help
    #
    # nargs="?" means the argument is optional:
    #   - If not provided: const="" (empty string)
    #   - If provided: uses the value (e.g., "xy", "ec", "op")
    # ====================================================================
    parser.add_argument("--help", "-h", nargs="?", const="", metavar="topic",
                        help=argparse.SUPPRESS)  # SUPPRESS hides from auto-generated help
    parser.add_argument("--manual", "-m", action="store_true", help=argparse.SUPPRESS)
    
    # ====================================================================
    # POSITIONAL ARGUMENTS (FILE PATHS)
    # ====================================================================
    # 'files' is a positional argument, meaning it doesn't need a flag.
    # nargs="*" means it accepts 0 or more values (list).
    # Examples:
    #   batplot file1.xy file2.xy        → args.files = ['file1.xy', 'file2.xy']
    #   batplot allfiles                 → args.files = ['allfiles']
    #   batplot --interactive            → args.files = [] (empty list)
    # ====================================================================
    parser.add_argument("files", nargs="*", help=argparse.SUPPRESS)
    parser.add_argument("--delta", "-d", type=float, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--autoscale", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--xrange", "-r", nargs=2, type=float, help=argparse.SUPPRESS)
    parser.add_argument("--out", "-o", type=str, help=argparse.SUPPRESS)
    parser.add_argument("--errors", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--xaxis", type=str, help=argparse.SUPPRESS)
    parser.add_argument("--convert", "-c", nargs="+", help=argparse.SUPPRESS)
    parser.add_argument("--wl", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--fullprof", nargs="+", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--norm", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--chik", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--kchik", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--k2chik", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--k3chik", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("-i", "--interactive", action="store_true", dest="interactive", help=argparse.SUPPRESS)
    parser.add_argument("--savefig", type=str, help=argparse.SUPPRESS)
    parser.add_argument("--stack", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--operando", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--gc", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--mass", type=float, help=argparse.SUPPRESS)
    parser.add_argument("--dqdv", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--cv", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--cpc", action="store_true", help=argparse.SUPPRESS)
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
    import re
    
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
            # Skip predefined extensions (already in parser)
            if ext not in ['xy', 'xye', 'qye', 'nor', 'dat', 'csv']:
                custom_readcol_exts.add(ext)
        i += 1
    
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
    #   batplot -h xy    → XY mode help
    #   batplot -h ec    → EC mode help
    #   batplot -h op    → Operando mode help
    #
    # If help is requested, we print it and exit immediately (don't continue parsing).
    # ====================================================================
    
    # Parse with known_args_only=True to avoid errors from unknown arguments
    # This is needed because we might have custom --readcol<ext> flags that
    # weren't in the parser yet when we built it
    ns, _unknown = parser.parse_known_args(argv)
    if getattr(ns, "manual", False):
        try:
            from .manual import show_manual  # Lazy import avoids matplotlib startup unless needed
            pdf_path = show_manual(open_viewer=True)
            if _HAS_RICH and _console:
                _console.print(f"\n[green]Opened manual:[/green] {pdf_path}")
            else:
                print(f"\nOpened manual: {pdf_path}")
        except Exception as exc:  # pragma: no cover - rendering is best effort
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
        elif t in ("op", "operando"):
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
    
    return args


__all__ = ["build_parser", "parse_args"]

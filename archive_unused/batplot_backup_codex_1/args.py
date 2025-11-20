"""Argument parsing for batplot CLI."""

from __future__ import annotations

import argparse
import sys
import re

# Try to import rich for colored output
try:
    from rich.console import Console
    from rich.markup import escape
    _console = Console()
    _HAS_RICH = True
except ImportError:
    _console = None
    _HAS_RICH = False


def _colorize_help(text: str) -> str:
    """Add colors to help text by highlighting flags and special elements.
    
    Args:
        text: Plain help text
        
    Returns:
        Text with rich markup for colored output
    """
    if not _HAS_RICH:
        return text
    
    # Escape any existing markup
    text = escape(text)
    
    # Color all flags (--flag or -f)
    text = re.sub(r'(--[\w-]+)', r'[cyan]\1[/cyan]', text)
    text = re.sub(r'(\s-[a-zA-Z]\b)', r'[cyan]\1[/cyan]', text)
    
    # Color file extensions
    text = re.sub(r'(\.\w{2,4}\b)', r'[yellow]\1[/yellow]', text)
    
    # Color example commands (batplot at start of line or after whitespace)
    text = re.sub(r'(batplot\s+[^\n]+)', r'[green]\1[/green]', text)
    
    # Color section headers (lines ending with :)
    text = re.sub(r'^([A-Z][\w\s/()]+:)$', r'[bold blue]\1[/bold blue]', text, flags=re.MULTILINE)
    
    # Color special markers
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
        "  • XY: XRD/PDF/XAS/... curves\n"
        "  • EC: GC/CPC/dQdV/CV (from .csv or .mpt)\n"
        "  • Operando: contour maps from a folder of XY and .mpt files\n"
        "  • Batch: export SVG plots for all files in a directory\n\n"
        "  • Interactive mode: -i / --interactive flag opens a menu for styling, ranges, fonts, export, sessions\n\n"
    "How to run (basics):\n"
    "  [XY curves]\n"
    "    batplot file1.xy file2.qye [option1] [option2]             # XY curves\n"
    "    batplot allfiles                       # Plot all XY files in current directory on same figure\n"
    "    batplot allfiles /path/to/dir          # Plot all XY files in specified directory\n"
    "    batplot allfiles --interactive         # Plot all files with interactive menu\n"
    "    batplot --all                          # Batch mode: all XY files → Figures/ as .svg\n"
    "    batplot --all --format png             # Batch mode: export as .png files\n"
    "    batplot --all --xaxis 2theta --xrange 10 80  # Batch mode with custom axis and range\n\n"
    "  [Electrochemistry]\n"
    "    batplot --gc FILE.mpt --mass 7.0       # EC GC from .mpt (requires --mass mg)\n"
    "    batplot --gc FILE.csv                  # EC GC from supported .csv (no mass required)\n"
    "    batplot --gc --all --mass 7.0          # Batch: all .mpt/.csv → Figures/ as .svg\n"
    "    batplot --gc --all --mass 7 --format pdf  # Batch: export as .pdf files\n"
    "    batplot --all --gc style.bps --mass 7  # Batch with style: apply style.bps to all GC files\n"
    "    batplot --all --cv config.bpsg         # Batch with style+geom: apply to all CV files\n"
    "    batplot --dqdv FILE.csv                # EC dQ/dV from supported .csv\n"
    "    batplot --dqdv --all                   # Batch: all .csv in directory (dQdV mode)\n"
    "    batplot --cv FILE.mpt                  # EC CV (cyclic voltammetry) from .mpt\n"
    "    batplot --cv FILE.txt                  # EC CV (cyclic voltammetry) from .txt\n"
    "    batplot --cv --all                     # Batch: all .mpt/.txt in directory (CV mode)\n\n"
    "  [Operando]\n"
    "    batplot --operando [FOLDER]            # Operando contour (with or without .mpt file)\n\n"
        "Features:\n"
        "  • Quick plotting with sensible defaults, no config files needed\n"
        "  • Supports many common file formats (see -h xy/ec/op)\n"
        "  • Interactive menus (--interactive): styling, ranges, fonts, export, sessions\n"
        "  • Batch processing: use 'allfiles' to plot all on same figure, or --all for separate files\n"
        "  • Batch exports saved to Figures/ subdirectory (default: .svg format)\n"
        "  • Batch styling: apply .bps/.bpsg files to all exports (use --all flag)\n"
        "  • Format option: use --format png/pdf/jpg/etc to change export format\n\n"
    
    "More help:\n"
    "  batplot -h xy   # XY file plotting guide\n"
    "  batplot -h ec   # Electrochemistry (GC/dQdV/CV/CPC) guide\n"
    "  batplot -h op   # Operando guide\n"
    "  Manual: https://github.com/tiandai-chem/batplot/blob/main/USER_MANUAL.md\n\n"
    "Contact & Updates:\n"
    "  Subscribe to batplot-lab@kjemi.uio.no for updates\n"
    "  (If you are not from UiO, send an email to sympa@kjemi.uio.no with the subject line \"subscribe batplot-lab@kjemi.uio.no your-name\")\n"
    "  GitHub: https://github.com/tiandai-chem/batplot\n"
    "  Kindly cite the github page if the plot is used for publication\n"
    "  Email: tianda@uio.no\n"
    )
    _print_help(msg)


def _print_xy_help() -> None:
    msg = (
        "XY plots (diffraction/PDF/XAS)\n\n"
        "Supported files: .xye .xy .qye .dat .csv .gr .nor .chik .chir .txt (2-col). CIF overlays supported.\n\n"
        "Axis detection: .qye→Q, .gr→r, .nor→energy, .chik→k, .chir→r, else use --xaxis (Q, 2theta, r, k, energy, rft, time).\n"
        "If mixing 2θ data in Q, give wavelength per-file (file.xye:1.5406) or global --wl.\n"
        "For electrochemistry CSV/MPT time-voltage plots, use --xaxis time.\n\n"
        "Examples:\n"
        "  batplot a.xye:1.5406 b.qye --stack --interactive\n"
        "  batplot a.dat b.xy --wl 1.54 --out fig.svg\n"
        "  batplot pattern.qye ticks.cif --interactive\n\n"
        "Plot all files together:\n"
        "  batplot allfiles                       # Plot all XY files on same figure\n"
        "  batplot allfiles /path/to/dir          # Plot all XY files in specified directory\n"
        "  batplot allfiles --stack --interactive # Stack all files with interactive menu\n"
        "  batplot allfiles --xaxis 2theta --xrange 10 80  # All files with custom axis and range\n"
        "  batplot allfiles --wl 1.5406 --delta 0.2        # All files with wavelength and spacing\n\n"
        "Batch mode (separate file for each, saved to Figures/ subdirectory):\n"
        "  batplot --all                          # Export all XY files as .svg (default)\n"
        "  batplot --all --format png             # Export all XY files as .png\n"
        "  batplot --all --xaxis 2theta           # Batch mode with custom axis type\n"
        "  batplot --all --xrange 10 80           # Batch mode with X-axis range\n"
        "  batplot --all --wl 1.5406              # Batch mode with wavelength conversion\n\n"
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
    "  --wl <float>              : set wavelength for Q conversion for all files, e.g. --wl 1.5406\n"
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
        "  batplot --all --gc style.bps --mass 7  # Apply style to all GC plots\n"
        "  batplot --all --cv config.bpsg         # Apply style+geometry to all CV plots\n"
        "  batplot --all --dqdv my.bps            # Apply style to all dQdV plots\n"
        "  batplot --all --cpc geom.bpsg --mass 6 # Apply style+geom to all CPC plots\n\n"
        "Interactive (--interactive): choose cycles, colors/palettes, line widths, axis scales (linear/log/symlog),\n"
        "rename axes, toggle ticks/titles/spines, print/export/import style (.bps/.bpsg), save session (.pkl).\n"
        "Note: Batch mode (--all) exports SVG files automatically; --interactive is for single-file plotting only.\n"
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
    # We use a custom help so users can request topic help via `-h xy|ec|op`.
    parser = argparse.ArgumentParser(add_help=False)
    # Topic-aware help flag (optional argument)
    parser.add_argument("--help", "-h", nargs="?", const="", metavar="topic",
                        help=argparse.SUPPRESS)
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
    import re
    
    # First, scan for custom --readcol<ext> flags and dynamically add them to parser
    if argv is None:
        argv = sys.argv[1:]
    
    # Find all --readcol<ext> patterns
    custom_readcol_exts = set()
    i = 0
    while i < len(argv):
        arg = argv[i]
        match = re.match(r'^--readcol([a-z0-9]+)$', arg)
        if match:
            ext = match.group(1)
            # Skip the predefined ones
            if ext not in ['xy', 'xye', 'qye', 'nor', 'dat', 'csv']:
                custom_readcol_exts.add(ext)
        i += 1
    
    parser = build_parser()
    
    # Dynamically add custom extension readcol arguments
    for ext in custom_readcol_exts:
        parser.add_argument(f"--readcol{ext}", nargs=2, type=int, metavar=('X_COL', 'Y_COL'),
                           help=argparse.SUPPRESS)
    
    # We need to parse known args first to handle our custom help without errors
    ns, _unknown = parser.parse_known_args(argv)
    topic = getattr(ns, 'help', None)
    if topic is not None:
        t = (topic or '').strip().lower()
        if t in ("", "help"):
            _print_general_help()
        elif t in ("xy",):
            _print_xy_help()
        elif t in ("ec", "gc", "dqdv"):
            _print_ec_help()
        elif t in ("op", "operando"):
            _print_op_help()
        else:
            _print_general_help()
            if _HAS_RICH and _console:
                _console.print("\n[yellow]Unknown help topic. Use: xy, ec, op[/yellow]")
            else:
                print("\nUnknown help topic. Use: xy, ec, op")
        sys.exit(0)
    # No help requested: parse fully
    args = parser.parse_args(argv)
    
    # Store a dictionary mapping extension to column specification
    args.readcol_by_ext = {}
    for ext in ['xy', 'xye', 'qye', 'nor', 'dat', 'csv'] + list(custom_readcol_exts):
        attr_name = f'readcol{ext}'
        if hasattr(args, attr_name):
            val = getattr(args, attr_name)
            if val is not None:
                args.readcol_by_ext[f'.{ext}'] = val
    
    return args


__all__ = ["build_parser", "parse_args"]

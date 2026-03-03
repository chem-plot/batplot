"""Operando (time/sequence) contour plotting utilities.

This module provides functions to create operando contour plots from a folder
of diffraction data files. Operando plots show how diffraction patterns change
over time (or scan number) as a 2D intensity map.

WHAT IS AN OPERANDO PLOT?
------------------------
An operando plot is a 2D visualization where:
- X-axis: Diffraction angle (2θ) or momentum transfer (Q)
- Y-axis: Time/scan number (which file/measurement in sequence)
- Color/Z-axis: Intensity (how bright the diffraction signal is)

Example use cases:
- Watching a material transform during heating (phase transitions)
- Monitoring battery electrode changes during cycling
- Tracking crystal growth over time
- Observing chemical reactions in real-time

HOW IT WORKS:
------------
1. Scan folder for XRD/PDF/XAS or other data files
2. Load each file as one "scan" (one row in the contour)
3. Create a common X-axis grid (interpolate all scans to same grid)
4. Stack all scans vertically to form a 2D array
5. Display as intensity contour (color map)
6. Optionally add electrochemistry/temperature/other data as side panel (if .mpt file present)

AXIS MODE DETECTION:
-------------------
The X-axis type is determined automatically:
- If --xaxis Q specified → Use Q-space (convert .xy/.xye to Q via --wl if needed)
- If --xaxis 2theta specified → Use 2θ (degrees); convert .qye to 2θ via --wl if needed
- If files are .qye and no --xaxis → Use Q-space (already in Q)
- If --wl specified and no --xaxis → Convert 2θ to Q using wavelength
- With CIF files: tick positions are always computed in Q from the CIF, then converted
  to 2θ when axis_mode is 2theta (using --wl or per-file wavelength)
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

import numpy as np  # type: ignore[import]
import matplotlib.pyplot as plt  # type: ignore[import]

from .converters import convert_to_qye
from .readers import robust_loadtxt_skipheader, read_mpt_file, is_bruker_raw, read_xrd_vendor_file
from .cif import cif_reflection_positions, list_reflections_with_hkl, build_hkl_label_map_from_list
from .utils import natural_sort_key
from matplotlib.transforms import blended_transform_factory  # type: ignore[import]
from matplotlib.lines import Line2D  # type: ignore[import]
from matplotlib import patheffects  # type: ignore[import]

# Import colorbar drawing function for non-interactive mode
try:
    from .operando_ec_interactive import _draw_custom_colorbar
except ImportError:
    # Fallback if interactive module not available
    _draw_custom_colorbar = None

SUPPORTED_EXT = {".xy", ".xye", ".qye", ".dat", ".brml", ".raw", ".xrdml", ".rasx"}
# Standard diffraction file extensions that have known x-axis meanings
KNOWN_DIFFRACTION_EXT = {".xy", ".xye", ".qye", ".dat", ".nor", ".chik", ".chir", ".brml", ".raw", ".xrdml", ".rasx"}
# File types to exclude from operando data (system/session files and electrochemistry)
EXCLUDED_EXT = {".mpt", ".pkl", ".json", ".txt", ".md", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".DS_Store", ".xlsx", ".xls", ".csv"}

# Keep the colorbar width deterministic (in inches) so interactive tweaks or saved
# sessions never pick up whatever Matplotlib auto-sized for the current figure.
DEFAULT_COLORBAR_WIDTH_IN = 0.23

_two_theta_re = re.compile(r"2[tT]heta|2th", re.IGNORECASE)
_q_re = re.compile(r"^q$", re.IGNORECASE)
_r_re = re.compile(r"^r(adial)?$", re.IGNORECASE)

def _infer_axis_mode(args, any_qye: bool, has_unknown_ext: bool):
    # Priority: explicit --xaxis, else .qye presence (Q), else wavelength (Q), else default 2theta with warning
    # If unknown extensions are present, use "user defined" mode
    if has_unknown_ext and not args.xaxis:
        return "user_defined"
    if args.xaxis:
        axis_str = args.xaxis.strip()
        if _q_re.match(axis_str):
            return "Q"
        if _r_re.match(axis_str):
            return "r"
        if _two_theta_re.search(axis_str):
            return "2theta"
        print(f"[operando] Unrecognized --xaxis '{args.xaxis}', assuming 2theta.")
        return "2theta"
    if any_qye:
        return "Q"
    if getattr(args, 'wl', None) is not None:
        return "Q"
    print("[operando] No --xaxis or --wl supplied and no .qye files; assuming 2theta (degrees). Use --xaxis 2theta to silence this message.")
    return "2theta"

def _load_curve(path: Path, readcol=None):
    suffix = path.suffix.lower()
    if suffix in ('.brml', '.xrdml', '.rasx') or (suffix == '.raw' and is_bruker_raw(str(path))):
        x, y, _, _ = read_xrd_vendor_file(str(path))
        return np.asarray(x, float), np.asarray(y, float)

    data = robust_loadtxt_skipheader(str(path))
    if data.ndim == 1:
        if data.size < 2:
            raise ValueError(f"File {path} has insufficient numeric data")
        x = data[0::2]
        y = data[1::2]
    else:
        # Handle --readcol flag to select specific columns
        if readcol:
            x_col, y_col = readcol
            # Convert from 1-indexed to 0-indexed
            x_col_idx = x_col - 1
            y_col_idx = y_col - 1
            if x_col_idx < 0 or x_col_idx >= data.shape[1]:
                raise ValueError(f"X column {x_col} out of range in {path} (has {data.shape[1]} columns)")
            if y_col_idx < 0 or y_col_idx >= data.shape[1]:
                raise ValueError(f"Y column {y_col} out of range in {path} (has {data.shape[1]} columns)")
            x = data[:, x_col_idx]
            y = data[:, y_col_idx]
        else:
            x = data[:,0]
            y = data[:,1]
    return np.asarray(x, float), np.asarray(y, float)

def _maybe_convert_to_Q(x, wl):
    # Accept degrees (2theta) -> Q
    # Q = 4π sin(theta)/λ ; theta = (2θ)/2
    theta = np.radians(x/2.0)
    return 4.0 * np.pi * np.sin(theta) / wl


def _maybe_convert_Q_to_2theta(x, wl):
    """Convert Q (Å⁻¹) array to 2θ (degrees). Q = 4π sin(θ)/λ → 2θ = 2 arcsin(Qλ/(4π))."""
    if wl is None:
        return x
    s = np.asarray(x, float) * wl / (4 * np.pi)
    with np.errstate(invalid='ignore'):
        out = np.degrees(2 * np.arcsin(np.clip(s, 0, 1)))
    return np.where(np.isfinite(out), out, np.nan)


def _Q_to_2theta_operando(peaksQ, wl):
    """Convert Q positions to 2θ (degrees) for operando CIF ticks."""
    out = []
    if wl is None:
        return out
    for q in peaksQ:
        s = q * wl / (4 * np.pi)
        if 0 <= s < 1:
            out.append(np.degrees(2 * np.arcsin(s)))
    return out


def _draw_operando_cif_ticks(op_ax, fig, cif_tick_series, cif_hkl_label_map,
                            axis_mode, wl, show_hkl=False, show_titles=True,
                            placement='below', y_positions=None, highlight=None,
                            title_font=None, title_visible=None, set_visible=None):
    """Draw CIF tick labels as figure annotations (no separate axis).
    
    Tick lines and labels are drawn using a blended transform: x from operando
    data coords (aligned with 2θ/Q), y from figure coords (below operando panel).
    
    If highlight=True, adds bbox and path_effects so ticks remain visible when
    overlaid on the operando contour.
    
    title_font: dict with 'family' and/or 'size' for title text (None = use default)
    title_visible: list of bool, one per set; if None, all visible when show_titles
    set_visible: list of bool, one per set; if False, skip drawing that CIF set entirely
    """

    if highlight is None:
        highlight = getattr(fig, '_operando_cif_highlight', False)
    if title_font is None:
        title_font = getattr(fig, '_operando_cif_title_font', None) or {}
    if title_visible is None:
        title_visible = getattr(fig, '_operando_cif_title_visible', None)
    if set_visible is None:
        set_visible = getattr(fig, '_operando_cif_set_visible', None)
    default_title_fontsize = max(8, int(0.55 * plt.rcParams.get('font.size', 12)))
    title_fs = title_font.get('size')
    if title_fs is not None:
        try:
            default_title_fontsize = max(6, int(float(title_fs)))
        except (ValueError, TypeError):
            pass
    title_family = title_font.get('family')
    use_2th = (axis_mode == '2theta')
    pe = []
    if highlight:
        try:
            pe = [patheffects.withStroke(linewidth=2.5, foreground='white')]
        except Exception:
            pass
    title_bbox = dict(boxstyle='round,pad=0.2', fc='white', ec='0.7', alpha=0.85) if highlight else None
    default_wl = wl if wl is not None else 1.5406

    xlow, xhigh = op_ax.get_xlim()
    trans = blended_transform_factory(op_ax.transData, fig.transFigure)

    for art in getattr(fig, '_operando_cif_tick_art', []):
        try:
            art.remove()
        except Exception:
            pass
    new_art = []

    ax_pos = op_ax.get_position()
    if placement == 'below':
        y_base = ax_pos.ymin - 0.02
        dy = -0.025
    else:
        y_base = ax_pos.ymax + 0.02
        dy = 0.025

    n_sets = len(cif_tick_series)
    if y_positions is not None and len(y_positions) == n_sets:
        y_figs = list(y_positions)
    else:
        y_figs = [y_base + i * dy for i in range(n_sets)]

    tick_height = 0.015
    # Title baseline aligns with tick baseline (y_fig): va='baseline' places text baseline at y

    for i, (lab, fname, peaksQ, wl_entry, qmax_sim, color) in enumerate(cif_tick_series):
        if set_visible is not None and i < len(set_visible) and not set_visible[i]:
            continue
        y_fig = y_figs[i] if i < len(y_figs) else (y_base + i * dy)
        show_this_title = show_titles
        if title_visible is not None and i < len(title_visible):
            show_this_title = show_titles and title_visible[i]
        txt_kw = dict(fontsize=default_title_fontsize, color=color, bbox=title_bbox, path_effects=pe if pe else None)
        if title_family:
            txt_kw['fontfamily'] = title_family

        if use_2th:
            wl_use = wl_entry if wl_entry is not None else default_wl
            domain_peaks = _Q_to_2theta_operando(peaksQ, wl_use)
        else:
            domain_peaks = list(peaksQ)

        domain_peaks = [p for p in domain_peaks if xlow <= p <= xhigh]
        if not domain_peaks:
            if show_this_title:
                txt = fig.text(xlow, y_fig, f" {lab}", transform=trans, ha='left', va='baseline', **txt_kw)
                new_art.append(txt)
            continue

        label_map = cif_hkl_label_map.get(fname, {}) if show_hkl else {}
        effective_show_hkl = show_hkl and peaksQ and label_map and len(domain_peaks) <= 4000
        lbl_bbox = dict(boxstyle='round,pad=0.1', fc='white', ec='none', alpha=0.85) if highlight else None

        for p in domain_peaks:
            ln = Line2D([p, p], [y_fig, y_fig + tick_height], color=color, lw=1.2 if highlight else 1.0, alpha=0.95 if highlight else 0.9,
                        transform=trans, clip_on=False, zorder=5 if highlight else 3)
            if pe:
                try:
                    ln.set_path_effects(pe)
                except Exception:
                    pass
            fig.add_artist(ln)
            new_art.append(ln)
            if effective_show_hkl:
                if use_2th and wl_entry:
                    theta_rad = np.radians(p / 2.0)
                    Qp = 4 * np.pi * np.sin(theta_rad) / wl_entry
                else:
                    Qp = p
                lbl = label_map.get(round(Qp, 6))
                if lbl:
                    t_hkl = fig.text(p, y_fig + tick_height + 0.005, lbl, transform=trans,
                                     ha='center', va='bottom', fontsize=7, rotation=90, color=color, clip_on=False,
                                     bbox=lbl_bbox, path_effects=pe if pe else None)
                    new_art.append(t_hkl)

        if show_this_title:
            txt = fig.text(xlow, y_fig, f" {lab}", transform=trans, ha='left', va='baseline', **txt_kw)
            new_art.append(txt)

    fig._operando_cif_tick_art = new_art
    fig._operando_cif_y_positions = y_figs
    try:
        fig.canvas.draw_idle()
    except Exception:
        pass


def plot_operando_folder(folder: str, args, cif_files=None) -> Tuple[plt.Figure, plt.Axes, Dict[str, Any]]:
    """
    Plot operando contour from a folder of diffraction files.
    
    HOW IT WORKS:
    ------------
    This function creates a 2D intensity contour plot from a sequence of
    diffraction patterns. The workflow:
    
    1. **Scan folder**: Find all diffraction data files (.xy, .xye, .qye, .dat)
    2. **Load data**: Read each file as one "scan" (one time point)
    3. **Determine axis mode**: Detect if data is in 2θ or Q space
    4. **Convert if needed**: Convert 2θ to Q if wavelength provided
    5. **Create common grid**: Interpolate all scans to same X-axis grid
    6. **Stack scans**: Build 2D array (n_scans × n_x_points)
    7. **Create contour**: Display as intensity map using imshow/pcolormesh
    8. **Add colorbar**: Show intensity scale
    9. **Optional EC panel**: If .mpt file found, add electrochemistry side panel
    
    DATA INTERPOLATION:
    ------------------
    Different scans might have different X-axis points (different angle ranges
    or resolutions). We create a common grid by:
    - Finding global min/max X values across all scans
    - Creating evenly spaced grid points
    - Interpolating each scan to this common grid
    
    This ensures all scans align perfectly for the contour plot.
    
    ELECTROCHEMISTRY INTEGRATION:
    ----------------------------
    If a .mpt file is found in the folder, an electrochemistry plot is added
    as a side panel. This shows voltage/capacity vs time alongside the
    diffraction contour, allowing correlation between structural changes
    (diffraction) and electrochemical behavior (voltage).
    
    Args:
        folder: Path to directory containing diffraction data files
        args: Argument namespace with attributes:
        cif_files: Optional list of CIF file paths (with optional :wl suffix, e.g. phase.cif:1.54)
            - xaxis: X-axis type ('Q', '2theta', 'r', etc.)
            - wl: Wavelength for 2θ→Q conversion (if needed)
            - raw: Whether to use raw intensity (no processing)
            - interactive: Whether to launch interactive menu
            - savefig/out: Optional output filename
        
    Returns:
        Tuple of (figure, axes, metadata_dict) where:
        - figure: Matplotlib figure object
        - axes: Main axes object (contour plot)
        - metadata_dict: Dictionary containing:
            - 'files': List of file paths used
            - 'axis_mode': Detected axis mode ('Q', '2theta', etc.)
            - 'x_grid': Common X-axis grid (1D array)
            - 'imshow': Image object (for colormap changes)
            - 'colorbar': Colorbar object (for intensity scale)
            - 'has_ec': Whether EC panel was added
            - 'ec_ax': EC axes object (if has_ec is True)
    """
    p = Path(folder)
    if not p.is_dir():
        raise FileNotFoundError(f"Not a directory: {folder}")
    
    # Accept all file types except those in EXCLUDED_EXT
    # Filter out macOS resource fork files starting with ._
    # Also check that filename is not .DS_Store (which has no extension)
    files = sorted([f for f in p.iterdir() 
                    if f.is_file() 
                    and f.suffix.lower() not in EXCLUDED_EXT 
                    and f.name != ".DS_Store"
                    and not f.name.startswith("._")], 
                   key=lambda p: natural_sort_key(p.name))
    if not files:
        raise FileNotFoundError("No data files found in folder (excluding system/session files)")
    
    # Check if we have .qye files to help determine axis mode
    any_qye = any(f.suffix.lower() == ".qye" for f in files)
    # Since we accept all file types now, has_unknown_ext is effectively always True unless all are in KNOWN_DIFFRACTION_EXT
    has_unknown_ext = not all(f.suffix.lower() in KNOWN_DIFFRACTION_EXT for f in files)
    axis_mode = _infer_axis_mode(args, any_qye, has_unknown_ext)
    wl = getattr(args, 'wl', None)

    x_arrays = []
    y_arrays = []
    loaded_filenames = []  # track which files made it into the contour (some may be skipped)
    for f in files:
        readcol = None
        if hasattr(args, 'readcol_by_file') and args.readcol_by_file:
            for key in (str(f), f.name):
                if key in args.readcol_by_file:
                    rc = args.readcol_by_file[key]
                    readcol = rc[0] if isinstance(rc, list) and rc and isinstance(rc[0], (tuple, list)) else rc
                    break
        if readcol is None and hasattr(args, 'readcol_by_ext') and f.suffix.lower() in args.readcol_by_ext:
            readcol = args.readcol_by_ext[f.suffix.lower()]
        if readcol is None:
            readcol = getattr(args, 'readcol', None)
            if readcol and isinstance(readcol, list) and readcol and isinstance(readcol[0], (tuple, list)):
                readcol = readcol[0]
        try:
            x, y = _load_curve(f, readcol=readcol)
        except Exception as e:
            print(f"Skip {f.name}: {e}")
            continue
        # Convert axis if needed (but not for user_defined mode)
        if axis_mode == "Q":
            if f.suffix.lower() == ".qye":
                pass  # already Q
            else:
                if wl is None:
                    # If user wants Q without wavelength we cannot proceed for this file
                    print(f"Skip {f.name}: need wavelength (--wl) for Q conversion")
                    continue
                x = _maybe_convert_to_Q(x, wl)
        elif axis_mode == "2theta" and f.suffix.lower() == ".qye":
            # .qye files are in Q; user wants 2theta → convert Q to 2theta
            if wl is None:
                print(f"Skip {f.name}: need wavelength (--wl) for Q→2theta conversion")
                continue
            x = _maybe_convert_Q_to_2theta(x, wl)
        # No normalization - keep raw intensity values
        x_arrays.append(x)
        y_arrays.append(y)
        loaded_filenames.append(f.name)

    if not x_arrays:
        raise RuntimeError("No curves loaded after filtering/conversion.")

    # ====================================================================
    # CREATE COMMON X-AXIS GRID AND INTERPOLATE ALL SCANS
    # ====================================================================
    # Different scans might have:
    # - Different angle ranges (some from 10-80°, others from 20-70°)
    # - Different resolutions (some with 1000 points, others with 500)
    # - Slightly different X values (measurement variations)
    #
    # To create a contour plot, all scans must have the SAME X-axis grid.
    # We solve this by:
    # 1. Finding the global min/max X values (covers all scans)
    # 2. Creating a common evenly-spaced grid
    # 3. Interpolating each scan to this common grid
    #
    # This ensures perfect alignment for the 2D contour visualization.
    # ====================================================================
    
    # STEP 1: Find global X-axis range
    # Find the minimum and maximum X values across ALL scans
    # This determines the range of our common grid
    xmin = min(arr.min() for arr in x_arrays if arr.size)  # Global minimum
    xmax = max(arr.max() for arr in x_arrays if arr.size)  # Global maximum
    
    # STEP 2: Determine grid resolution
    # Use the maximum number of points from any scan as the grid size
    # This preserves the highest resolution available
    base_len = int(max(arr.size for arr in x_arrays))
    
    # STEP 3: Create evenly-spaced common grid
    # np.linspace creates evenly spaced points from xmin to xmax
    # Example: xmin=10, xmax=80, base_len=1000 → 1000 evenly spaced points
    grid_x = np.linspace(xmin, xmax, base_len)
    
    # STEP 4: Interpolate each scan to common grid
    # For each scan, interpolate its Y values to the common X grid
    stack = []
    for x, y in zip(x_arrays, y_arrays):
        if x.size < 2:
            # Can't interpolate with less than 2 points, fill with NaN
            interp = np.full_like(grid_x, np.nan)
        else:
            # Linear interpolation: find Y value at each grid_x point
            # np.interp() does linear interpolation:
            #   - For grid_x[i] between x[j] and x[j+1], interpolate between y[j] and y[j+1]
            #   - left=np.nan: If grid_x < x.min(), use NaN (outside scan range)
            #   - right=np.nan: If grid_x > x.max(), use NaN (outside scan range)
            interp = np.interp(grid_x, x, y, left=np.nan, right=np.nan)
        stack.append(interp)
    
    # STEP 5: Stack all interpolated scans into 2D array
    # np.vstack() stacks arrays vertically (one scan per row)
    # Result shape: (n_scans, n_x_points)
    # Example: 50 scans × 1000 points = (50, 1000) array
    Z = np.vstack(stack)  # shape (n_scans, n_x)

    # Debug: show scan index -> filename mapping (--debug or BATPLOT_OPERANDO_DEBUG=1)
    if getattr(args, 'debug', False) or os.environ.get('BATPLOT_OPERANDO_DEBUG', '0') == '1':
        print("[operando] Scan index -> filename:")
        for idx, fname in enumerate(loaded_filenames):
            print(f"  Scan {idx}: {fname}")

    # STEP 5.5: Apply first derivative if --1d or --2d flag is set
    # This calculates dy/dx for each scan using np.gradient
    if getattr(args, 'derivative_1d', False) or getattr(args, 'derivative_2d', False):
        print("[operando] Applying first derivative (dy/dx) to each scan...")
        Z_deriv = np.zeros_like(Z)
        for i in range(Z.shape[0]):
            row = Z[i, :]
            # Calculate derivative using gradient (handles NaN gracefully in numpy 1.20+)
            # Use the grid spacing for proper derivative calculation
            dx = grid_x[1] - grid_x[0] if len(grid_x) > 1 else 1.0
            # Replace NaN with interpolated values for gradient, then mask back
            valid_mask = ~np.isnan(row)
            if np.sum(valid_mask) > 1:
                # For valid regions, calculate gradient
                deriv = np.gradient(row, dx)
                # Keep NaN where original was NaN
                deriv[~valid_mask] = np.nan
                Z_deriv[i, :] = deriv
            else:
                Z_deriv[i, :] = np.nan
        Z = Z_deriv

    # Detect an electrochemistry .mpt file in the same folder (if any)
    # Filter out macOS resource fork files (starting with ._)
    mpt_files = sorted([f for f in p.iterdir() if f.suffix.lower() == ".mpt" and not f.name.startswith("._")], key=lambda p: natural_sort_key(p.name))  # pick first if present
    has_ec = len(mpt_files) > 0
    ec_ax = None

    if has_ec:
        # Wider canvas to accommodate side-by-side plots
        fig = plt.figure(figsize=(11, 6))
        gs = fig.add_gridspec(nrows=1, ncols=2, width_ratios=[3.5, 1.2], wspace=0.25)
        ax = fig.add_subplot(gs[0, 0])
    else:
        fig, ax = plt.subplots(figsize=(8,6))
    # Use imshow for speed; mask nans
    Zm = np.ma.masked_invalid(Z)
    extent = (grid_x.min(), grid_x.max(), 0, Zm.shape[0]-1)
    # Bottom-to-top visual order (scan 0 at bottom) to match EC time progression -> origin='lower'
    im = ax.imshow(Zm, aspect='auto', origin='lower', extent=extent, cmap='viridis', interpolation='nearest')
    # Store the colormap name explicitly so it can be retrieved reliably when saving
    setattr(im, '_operando_cmap_name', 'viridis')
    # Create custom colorbar axes on the left (will be positioned by layout function)
    # Create a dummy axes that will be replaced by the custom colorbar in interactive menu
    cbar_ax = fig.add_axes([0.0, 0.0, 0.01, 0.01])  # Temporary position, will be repositioned
    # Create a mock colorbar object for compatibility with existing code
    # The actual colorbar will be drawn by _draw_custom_colorbar in the interactive menu
    class MockColorbar:
        def __init__(self, ax, im):
            self.ax = ax
            self._im = im
        def set_label(self, label):
            ax._colorbar_label = label
        def update_normal(self, im):
            # This will be replaced by _update_custom_colorbar in interactive menu
            pass
    cbar = MockColorbar(cbar_ax, im)
    # Store label
    cbar_ax._colorbar_label = 'Intensity'
    ax.set_ylabel('Scan index')
    if axis_mode == 'Q':
        # Use mathtext for reliable superscript minus; plain unicode '⁻' can fail with some fonts
        ax.set_xlabel(r'Q (Å$^{-1}$)')  # renders as Å^{-1}
    elif axis_mode == 'r':
        ax.set_xlabel(r'r (Å)')
    elif axis_mode == 'user_defined':
        ax.set_xlabel('user defined')
    else:
        ax.set_xlabel('2θ (deg)')
    # No title for operando plot (requested)

    # If an EC .mpt exists, attach it to the right with the same height (Voltage vs Time in hours)
    if has_ec:
        try:
            ec_path = mpt_files[0]
            
            # Check if user specified custom columns via --readcolmpt
            readcol_mpt = None
            if hasattr(args, 'readcol_by_ext') and '.mpt' in args.readcol_by_ext:
                readcol_mpt = args.readcol_by_ext['.mpt']
            
            if readcol_mpt:
                # User explicitly specified columns - respect their choice
                data = robust_loadtxt_skipheader(str(ec_path))
                if data.ndim == 1:
                    data = data.reshape(1, -1)
                if data.shape[1] < 2:
                    raise ValueError(f"MPT file {ec_path.name} has insufficient columns")
                
                # Apply column selection (1-indexed -> 0-indexed)
                x_col, y_col = readcol_mpt
                x_col_idx = x_col - 1
                y_col_idx = y_col - 1
                if x_col_idx < 0 or x_col_idx >= data.shape[1]:
                    raise ValueError(f"X column {x_col} out of range in {ec_path.name} (has {data.shape[1]} columns)")
                if y_col_idx < 0 or y_col_idx >= data.shape[1]:
                    raise ValueError(f"Y column {y_col} out of range in {ec_path.name} (has {data.shape[1]} columns)")
                
                x_data = data[:, x_col_idx]
                y_data = data[:, y_col_idx]
                current_mA = None
                # User-specified: plot exactly as specified (X on x-axis, Y on y-axis)
                x_label = f'Column {x_col}'
                y_label = f'Column {y_col}'
            else:
                # Auto-detect format: Read time series from .mpt
                result = read_mpt_file(str(ec_path), mode='time')
                
                # Check if we got labels (5 elements) or old format (3 elements)
                if len(result) == 5:
                    x_data, y_data, current_mA, x_label, y_label = result
                    # For EC-Lab files: x_label='Time (h)', y_label='Voltage (V)'
                    # For simple files: x_label could be 'Time(h)', 'time', etc.
                    # EC-Lab files: read_mpt_file already converts time from seconds to hours
                    # operando plots with voltage on X-axis and time on Y-axis
                    
                    # Check if labels indicate time/voltage data (flexible matching)
                    x_lower = x_label.lower().replace(' ', '').replace('_', '')
                    y_lower = y_label.lower().replace(' ', '').replace('_', '')
                    has_time_in_x = 'time' in x_lower
                    has_voltage_in_x = 'voltage' in x_lower or 'ewe' in x_lower
                    has_time_in_y = 'time' in y_lower
                    has_voltage_in_y = 'voltage' in y_lower or 'ewe' in y_lower
                    
                    is_time_voltage = (has_time_in_x or has_time_in_y) and (has_voltage_in_x or has_voltage_in_y)
                    
                    if x_label == 'Time (h)' and y_label == 'Voltage (V)':
                        # EC-Lab file: time is already in hours from read_mpt_file, just swap axes
                        time_h = np.asarray(x_data, float)  # Already in hours, no conversion needed
                        voltage_v = np.asarray(y_data, float)
                        x_data = voltage_v
                        y_data = time_h
                        x_label = 'Voltage (V)'
                        y_label = 'Time (h)'
                    elif is_time_voltage:
                        # Simple file with time/voltage columns
                        # Determine which column is which, then arrange: voltage on X, time on Y
                        if has_time_in_x and has_voltage_in_y:
                            # Columns are: Time, Voltage -> swap to Voltage, Time
                            time_h = np.asarray(x_data, float)
                            voltage_v = np.asarray(y_data, float)
                            x_data = voltage_v
                            y_data = time_h
                            x_label = 'Voltage (V)'
                            y_label = 'Time (h)'
                        elif has_voltage_in_x and has_time_in_y:
                            # Columns are: Voltage, Time -> already correct order
                            voltage_v = np.asarray(x_data, float)
                            time_h = np.asarray(y_data, float)
                            x_data = voltage_v
                            y_data = time_h
                            x_label = 'Voltage (V)'
                            y_label = 'Time (h)'
                        else:
                            # Ambiguous or both in same column - default behavior
                            x_data = np.asarray(x_data, float)
                            y_data = np.asarray(y_data, float)
                    else:
                        # Generic file: use raw data as-is, keep original labels
                        x_data = np.asarray(x_data, float)
                        y_data = np.asarray(y_data, float)
                else:
                    # Old format compatibility (shouldn't happen anymore)
                    # Support both 3-tuple and 4+/5-tuple returns by ignoring any extra elements.
                    x_data, y_data, current_mA, *_ = result
                    x_data = np.asarray(x_data, float)
                    y_data = np.asarray(y_data, float) / 3600.0
                    x_label, y_label = 'Voltage (V)', 'Time (h)'
            
            # Add the EC axes on the right
            ec_ax = fig.add_subplot(gs[0, 1])
            ln_ec, = ec_ax.plot(x_data, y_data, lw=1.0, color='tab:blue')
            ec_ax.set_xlabel(x_label)
            ec_ax.set_ylabel(y_label)
            # Match interactive defaults: put EC Y axis on the right
            try:
                ec_ax.yaxis.tick_right()
                ec_ax.yaxis.set_label_position('right')
                _title = ec_ax.get_title()
                if isinstance(_title, str) and _title.strip():
                    ec_ax.set_title(_title, loc='right')
            except Exception:
                pass
            # Keep a clean look, no grid
            # Align visually: ensure similar vertical span display
            try:
                # Remove vertical margins and clamp to exact data bounds
                ec_ax.margins(y=0)
                ymin = float(np.nanmin(y_data)) if getattr(np, 'nanmin', None) else float(np.min(y_data))
                ymax = float(np.nanmax(y_data)) if getattr(np, 'nanmax', None) else float(np.max(y_data))
                ec_ax.set_ylim(ymin, ymax)
            except Exception:
                pass
            # Add a small right margin on EC X to give space for right-side ticks/labels
            try:
                x0, x1 = ec_ax.get_xlim()
                xr = (x1 - x0) if x1 > x0 else 0.0
                if xr > 0:
                    ec_ax.set_xlim(x0, x1 + 0.02 * xr)
                    setattr(ec_ax, '_xlim_expanded_default', True)
            except Exception:
                pass
            # Stash EC data and line for interactive transforms
            try:
                ec_ax._ec_time_h = y_data  # Store y_data (could be time or any y value)
                ec_ax._ec_voltage_v = x_data  # Store x_data (could be voltage or any x value)
                ec_ax._ec_current_mA = current_mA
                ec_ax._ec_line = ln_ec
                ec_ax._ec_y_mode = 'time'  # or 'ions'
                ec_ax._ion_annots = []
                ec_ax._ion_params = {"mass_mg": None, "cap_per_ion_mAh_g": None}
            except Exception:
                pass
        except Exception as e:
            print(f"[operando] Failed to attach electrochem plot: {e}")

    cif_files_provided = cif_files and len(cif_files) > 0

    # --- Default layout: set operando plot width to 5 inches (centered) ---
    try:
        fig_w_in, fig_h_in = fig.get_size_inches()
        # Current geometry in fractions
        ax_x0, ax_y0, ax_wf, ax_hf = ax.get_position().bounds
        cb_x0, cb_y0, cb_wf, cb_hf = cbar.ax.get_position().bounds
        # Convert to inches
        desired_ax_w_in = 5.0
        ax_h_in = ax_hf * fig_h_in
        cb_w_in = min(DEFAULT_COLORBAR_WIDTH_IN, fig_w_in)
        cb_gap_in = max(0.0, (ax_x0 - (cb_x0 + cb_wf)) * fig_w_in)
        ec_gap_in = 0.0
        ec_w_in = 0.0
        if ec_ax is not None:
            ec_x0, ec_y0, ec_wf, ec_hf = ec_ax.get_position().bounds
            ec_gap_in = max(0.0, (ec_x0 - (ax_x0 + ax_wf)) * fig_w_in)
            ec_w_in = ec_wf * fig_w_in
            # Match interactive default: shrink EC gap and rebalance widths
            try:
                # Decrease gap more aggressively with a sensible minimum
                # Increase the multiplier from 0.2 to 0.35 for more spacing
                ec_gap_in = max(0.05, ec_gap_in * 0.35)
                # Transfer a fraction of width from EC to operando while keeping total similar
                combined = (desired_ax_w_in if desired_ax_w_in > 0 else ax_wf * fig_w_in) + ec_w_in
                ax_w_in_current = desired_ax_w_in if desired_ax_w_in > 0 else (ax_wf * fig_w_in)
                if combined > 0 and ec_w_in > 0.5:
                    transfer = min(ec_w_in * 0.18, combined * 0.12)
                    min_ec = 0.8
                    if ec_w_in - transfer < min_ec:
                        transfer = max(0.0, ec_w_in - min_ec)
                    desired_ax_w_in = ax_w_in_current + transfer
                    ec_w_in = max(min_ec, ec_w_in - transfer)
            except Exception:
                pass
            # Apply gap adjustment when EC panel exists (multiply by 0.75 to move colorbar closer)
            cb_gap_in = cb_gap_in * 0.75
        else:
            # When no EC panel, increase gap to move colorbar further left (multiply by 1.3)
            cb_gap_in = cb_gap_in * 1.1
        # Clamp desired width if it would overflow the canvas
        reserved = cb_w_in + cb_gap_in + ec_gap_in + ec_w_in
        max_ax_w = max(0.25, fig_w_in - reserved - 0.02)
        ax_w_in = min(desired_ax_w_in, max_ax_w)
        # Convert inches to fractions
        ax_wf_new = max(0.0, ax_w_in / fig_w_in)
        ax_hf_new = max(0.0, ax_h_in / fig_h_in)
        cb_wf_new = max(0.0, cb_w_in / fig_w_in)
        cb_gap_f = max(0.0, cb_gap_in / fig_w_in)
        ec_gap_f = max(0.0, ec_gap_in / fig_w_in)
        ec_wf_new = max(0.0, ec_w_in / fig_w_in)
        # Center group horizontally
        total_wf = cb_wf_new + cb_gap_f + ax_wf_new + ec_gap_f + ec_wf_new
        group_left = 0.5 - total_wf / 2.0
        y0 = 0.5 - ax_hf_new / 2.0
        # Positions
        cb_x0_new = group_left
        ax_x0_new = cb_x0_new + cb_wf_new + cb_gap_f
        ec_x0_new = ax_x0_new + ax_wf_new + ec_gap_f if ec_ax is not None else None
        # Apply (operando, cbar, ec – CIF ticks drawn as figure annotations, no separate axis)
        ax.set_position([ax_x0_new, y0, ax_wf_new, ax_hf_new])
        cbar.ax.set_position([cb_x0_new, y0, cb_wf_new, ax_hf_new])
        if ec_ax is not None and ec_x0_new is not None:
            ec_ax.set_position([ec_x0_new, y0, ec_wf_new, ax_hf_new])
        
        # Draw the colorbar (even in non-interactive mode)
        if _draw_custom_colorbar is not None:
            try:
                cbar_label = getattr(cbar.ax, '_colorbar_label', 'Intensity')
                _draw_custom_colorbar(cbar.ax, im, cbar_label, 'highlow')
            except Exception:
                pass
        
        # Persist inches so interactive menu can pick them up
        try:
            setattr(cbar.ax, '_fixed_cb_w_in', cb_w_in)
            # Store both names for compatibility across interactive menus
            setattr(cbar.ax, '_fixed_cb_gap_in', cb_gap_in)
            setattr(cbar.ax, '_fixed_gap_in', cb_gap_in)
            # Mark as adjusted so interactive mode doesn't apply 0.75 multiplier again
            setattr(cbar.ax, '_cb_gap_adjusted', True)
            if ec_ax is not None:
                setattr(ec_ax, '_fixed_ec_gap_in', ec_gap_in)
                setattr(ec_ax, '_fixed_ec_w_in', ec_w_in)
                # Mark as adjusted so interactive menu won't adjust twice
                setattr(ec_ax, '_ec_gap_adjusted', True)
                setattr(ec_ax, '_ec_op_width_adjusted', True)
            setattr(ax, '_fixed_ax_w_in', ax_w_in)
            setattr(ax, '_fixed_ax_h_in', ax_h_in)
        except Exception:
            pass
        try:
            fig.canvas.draw()
        except Exception:
            fig.canvas.draw_idle()
    except Exception:
        # Non-fatal: keep Matplotlib's default layout
        pass

    # CIF tick labels: load and draw if cif_files provided (figure annotations, no axis)
    cif_tick_series = []
    cif_hkl_label_map = {}
    if cif_files and len(cif_files) > 0:
        xmin_g, xmax_g = float(grid_x.min()), float(grid_x.max())
        qmax_sim = max(xmax_g * 1.1, 10.0) if axis_mode == 'Q' else 10.0
        use_2th = (axis_mode == '2theta')
        default_wl = wl if wl is not None else 1.5406
        for i, entry in enumerate(cif_files):
            parts = entry.split(":")
            if len(parts) > 1 and len(parts[0]) == 1 and parts[0].isalpha():
                fname = parts[0] + ":" + parts[1]
                parts = [fname] + parts[2:]
            else:
                fname = parts[0]
            wl_file = default_wl
            if len(parts) >= 2:
                try:
                    wl_file = float(parts[1])
                except ValueError:
                    pass
            if not Path(fname).is_file():
                print(f"[operando] CIF not found: {fname}")
                continue
            try:
                refl_wl = wl_file if use_2th else None
                refl = cif_reflection_positions(fname, Qmax=qmax_sim, wavelength=refl_wl)
                hkl_list = list_reflections_with_hkl(fname, Qmax=qmax_sim, wavelength=refl_wl)
                cif_hkl_label_map[fname] = build_hkl_label_map_from_list(hkl_list)
                label = Path(fname).name
                if wl_file and use_2th:
                    label += f" (λ={wl_file:.5f} Å)"
                # Use tab10 cycle for distinct default colors
                try:
                    tab10 = plt.get_cmap('tab10')
                    default_col = tab10(i % 10)
                except Exception:
                    default_col = 'k'
                cif_tick_series.append((label, str(Path(fname).resolve()), refl, wl_file if use_2th else None, qmax_sim, default_col))
            except Exception as e:
                print(f"[operando] CIF error {fname}: {e}")
        if cif_tick_series:
            _draw_operando_cif_ticks(
                ax, fig, cif_tick_series, cif_hkl_label_map,
                axis_mode=axis_mode, wl=wl,
                show_hkl=False, show_titles=True, placement='below',
            )
            ax._operando_cif_tick_series = cif_tick_series
            ax._operando_cif_hkl_label_map = cif_hkl_label_map
            fig._operando_cif_show_hkl = False
            fig._operando_cif_show_titles = True
            fig._operando_cif_colormap = 'tab10'
            fig._operando_cif_highlight = False
            fig._operando_cif_title_font = {}
            fig._operando_cif_title_visible = None
            fig._operando_cif_set_visible = None
            fig._operando_cif_placement = 'below'
            fig._operando_cif_y_positions = list(getattr(fig, '_operando_cif_y_positions', []))
            fig._operando_axis_mode = axis_mode
            fig._operando_wl = wl

    meta = {
        'files': [f.name for f in files],
        'axis_mode': axis_mode,
        'x_grid': grid_x,
        'imshow': im,
        'colorbar': cbar,
        'has_ec': bool(has_ec),
    }
    if ec_ax is not None:
        meta['ec_ax'] = ec_ax
    if cif_tick_series:
        meta['cif_tick_series'] = cif_tick_series
        meta['cif_hkl_label_map'] = cif_hkl_label_map
    return fig, ax, meta

__all__ = ["plot_operando_folder"]

"""Operando (time/sequence) contour plotting utilities.

This module provides a single helper `plot_operando_folder` that scans a folder
for diffraction data files (.xy, .xye, .qye, .dat) and renders them as
an intensity contour (imshow / pcolormesh) stack vs scan index.

Rules:
- X axis: 2θ by default; if --xaxis Q provided, or files are .qye, or a global
  wavelength is specified and conversion is desired, Q will be used.
- No automatic normalization is applied; Z-scale (colorbar) is auto-adjusted
  to span from min to max intensity across all data.
- Sort files alphabetically for deterministic order.

Returned figure/axes so caller can further tweak or save.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

import numpy as np
import matplotlib.pyplot as plt

from .converters import convert_to_qye
from .readers import robust_loadtxt_skipheader, read_mpt_file

SUPPORTED_EXT = {".xy", ".xye", ".qye", ".dat"}
# Standard diffraction file extensions that have known x-axis meanings
KNOWN_DIFFRACTION_EXT = {".xy", ".xye", ".qye", ".dat", ".nor", ".chik", ".chir"}
# File types to exclude from operando data (system/session files and electrochemistry)
EXCLUDED_EXT = {".mpt", ".pkl", ".json", ".txt", ".md", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".DS_Store"}

_two_theta_re = re.compile(r"2[tT]heta|2th", re.IGNORECASE)
_q_re = re.compile(r"^q$", re.IGNORECASE)

def _natural_sort_key(path: Path) -> list:
    """Generate a natural sorting key for filenames with numbers.
    
    Converts 'file_10.xy' to ['file_', 10, '.xy'] so numerical parts are sorted numerically.
    This ensures file_2.xy comes before file_10.xy (natural order).
    """
    parts = []
    for match in re.finditer(r'(\d+|\D+)', path.name):
        text = match.group(0)
        if text.isdigit():
            parts.append(int(text))
        else:
            parts.append(text.lower())
    return parts

def _infer_axis_mode(args, any_qye: bool, has_unknown_ext: bool):
    # Priority: explicit --xaxis, else .qye presence (Q), else wavelength (Q), else default 2theta with warning
    # If unknown extensions are present, use "user defined" mode
    if has_unknown_ext and not args.xaxis:
        return "user_defined"
    if args.xaxis:
        if _q_re.match(args.xaxis.strip()):
            return "Q"
        if _two_theta_re.search(args.xaxis):
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

def plot_operando_folder(folder: str, args) -> Tuple[plt.Figure, plt.Axes, Dict[str, Any]]:
    """Plot operando contour from a folder of diffraction files.
    
    Args:
        folder: Path to directory containing diffraction data files
        args: Argument namespace with attributes: xaxis, wl, raw, interactive, savefig, out
        
    Returns:
        Tuple of (figure, axes, metadata_dict)
        metadata_dict contains: files, axis_mode, x_grid, imshow, colorbar, has_ec, ec_ax
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
                   key=_natural_sort_key)
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
    readcol = getattr(args, 'readcol', None)
    for f in files:
        try:
            x, y = _load_curve(f, readcol=readcol)
        except Exception as e:
            print(f"Skip {f.name}: {e}")
            continue
        # Convert to Q if needed (but not for user_defined mode)
        if axis_mode == "Q":
            if f.suffix.lower() == ".qye":
                pass  # already Q
            else:
                if wl is None:
                    # If user wants Q without wavelength we cannot proceed for this file
                    print(f"Skip {f.name}: need wavelength (--wl) for Q conversion")
                    continue
                x = _maybe_convert_to_Q(x, wl)
        # No normalization - keep raw intensity values
        x_arrays.append(x)
        y_arrays.append(y)

    if not x_arrays:
        raise RuntimeError("No curves loaded after filtering/conversion.")

    # Create common X grid (union, simple linear interpolation) for contour
    # Determine global min/max and pick reasonable number of points (~max original length)
    xmin = min(arr.min() for arr in x_arrays if arr.size)
    xmax = max(arr.max() for arr in x_arrays if arr.size)
    base_len = int(max(arr.size for arr in x_arrays))
    grid_x = np.linspace(xmin, xmax, base_len)
    stack = []
    for x, y in zip(x_arrays, y_arrays):
        if x.size < 2:
            interp = np.full_like(grid_x, np.nan)
        else:
            interp = np.interp(grid_x, x, y, left=np.nan, right=np.nan)
        stack.append(interp)
    Z = np.vstack(stack)  # shape (n_scans, n_x)

    # Detect an electrochemistry .mpt file in the same folder (if any)
    # Filter out macOS resource fork files (starting with ._)
    mpt_files = sorted([f for f in p.iterdir() if f.suffix.lower() == ".mpt" and not f.name.startswith("._")], key=_natural_sort_key)  # pick first if present
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
    # Place colorbar on the left
    cbar = fig.colorbar(im, ax=ax, location='left', pad=0.15)
    cbar.ax.yaxis.set_ticks_position('left')
    cbar.ax.yaxis.set_label_position('left')
    cbar.set_label('Intensity')
    ax.set_ylabel('Scan index')
    if axis_mode == 'Q':
        # Use mathtext for reliable superscript minus; plain unicode '⁻' can fail with some fonts
        ax.set_xlabel(r'Q (Å$^{-1}$)')  # renders as Å^{-1}
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
                    # EC-Lab returns time in seconds, needs conversion to hours
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
                        # EC-Lab file: convert time to hours and swap axes
                        time_h = np.asarray(x_data, float) / 3600.0
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
                    x_data, y_data, current_mA = result
                    x_data = np.asarray(y_data, float)
                    y_data = np.asarray(x_data, float) / 3600.0
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

    # --- Default layout: set operando plot width to 5 inches (centered) ---
    try:
        fig_w_in, fig_h_in = fig.get_size_inches()
        # Current geometry in fractions
        ax_x0, ax_y0, ax_wf, ax_hf = ax.get_position().bounds
        cb_x0, cb_y0, cb_wf, cb_hf = cbar.ax.get_position().bounds
        # Convert to inches
        desired_ax_w_in = 5.0
        ax_h_in = ax_hf * fig_h_in
        cb_w_in = cb_wf * fig_w_in
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
        # Apply
        ax.set_position([ax_x0_new, y0, ax_wf_new, ax_hf_new])
        cbar.ax.set_position([cb_x0_new, y0, cb_wf_new, ax_hf_new])
        if ec_ax is not None and ec_x0_new is not None:
            ec_ax.set_position([ec_x0_new, y0, ec_wf_new, ax_hf_new])
        # Persist inches so interactive menu can pick them up
        try:
            setattr(cbar.ax, '_fixed_cb_w_in', cb_w_in)
            # Store both names for compatibility across interactive menus
            setattr(cbar.ax, '_fixed_cb_gap_in', cb_gap_in)
            setattr(cbar.ax, '_fixed_gap_in', cb_gap_in)
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
    return fig, ax, meta

__all__ = ["plot_operando_folder"]

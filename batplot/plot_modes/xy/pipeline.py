"""The default 1D XY plotting pipeline.

This is the fall-through route of ``batplot`` (no EC / operando / session
flag): it reads the input files, determines the x-axis type, builds the
figure (stacking, normalization, dual-axis, CIF tick overlays, ...), saves
or shows it, and opens the XY interactive menu when requested.

Extracted verbatim from ``batplot.batplot.batplot_main`` into its own module
under :mod:`batplot.plot_modes.xy`. All collaborators are imported from their
owning submodules so there is no circular import back to
:mod:`batplot.batplot`.
"""

from __future__ import annotations

import os
import sys
import json
import pickle
from typing import Any, cast

import numpy as np  # type: ignore
import matplotlib.pyplot as plt  # type: ignore[import-untyped]

from ...batch import _apply_xy_style
from ...ec_common import _apply_default_ec_layout, _default_ec_figsize
from ..._mpl_backend import (
    ensure_gui_backend,
    hold_figure_open,
    prime_interactive_figure,
    require_interactive_display,
    show_figure_if_possible,
)
from ...color_utils import get_colormap
from ...utils import (
    _confirm_overwrite,
    xy_cif_stack_y_offset,
    xy_cif_tick_stack_layout,
    xy_cif_add_phase_title,
    xy_cif_row_spacing_yr,
    xy_cif_stack_bottom_margin_yr,
)
from ...cif import (
    simulate_cif_pattern_Q,
    cif_reflection_positions,
    list_reflections_with_hkl,
    build_hkl_label_map_from_list,
)
from ...readers import (
    read_fullprof_rowwise,
    robust_loadtxt_skipheader,
    read_gr_file,
    read_xrd_vendor_file,
    is_bruker_raw,
    read_csv_time_voltage,
    read_mpt_time_voltage,
    is_biologic_datalogger_csv,
    read_biologic_datalogger_time_voltage,
)
from ...plotting import update_labels
from .interactive import interactive_menu

# Global state flag (mirrors the original module-level default in batplot.batplot;
# read when persisting CIF globals for the interactive menu).
keep_canvas_fixed = False


def run_xy_pipeline(args) -> int:
    ensure_gui_backend(args)
    # ---------------- Plotting ----------------
    offset = 0.0
    direction = -1 if args.stack else 1  # stack downward
    if args.interactive:
        plt.ion()
    # All single-axes modes (XY, GC, CV, dQ/dV, CPC) share one default canvas
    # and plot-frame size so a fresh plot looks identical across modes.
    fig, ax = plt.subplots(figsize=_default_ec_figsize())
    ax2 = None  # Right y-axis (twinx), created when --ry curves exist
    
    # Shared default margins (same plot frame as the electrochem modes).
    # This prevents labels/titles from being cut off at the edges.
    try:
        _apply_default_ec_layout(fig)
    except Exception:
        pass

    y_data_list = []
    x_data_list = []
    labels_list = []
    orig_y = []
    label_text_objects = []
    right_y_curve_indices = []  # Curve indices that use right y-axis (--ry)
    # New lists to preserve full data & offsets
    x_full_list = []
    raw_y_full_list = []
    offsets_list = []

    # ---------------- Determine X-axis type ----------------
    def _ext_token(path):
        return os.path.splitext(path)[1].lower()  # includes leading dot
    
    # Check for CSV/MPT files with --xaxis time
    any_csv = any(f.lower().endswith((".csv", ".mpt")) for f in args.files)
    use_time_mode = any_csv and args.xaxis and args.xaxis.lower() == "time"
    
    if use_time_mode:
        # Special mode: plot time (h) vs potential (V) for electrochemistry CSV/MPT files
        axis_mode = "time"
    else:
        # Regular XRD/PDF/XAS mode - proceed with normal detection
        any_qye = any(f.lower().endswith(".qye") for f in args.files)
        any_gr  = any(f.lower().endswith(".gr")  for f in args.files)
        any_nor = any(f.lower().endswith(".nor") for f in args.files)
        any_chik = any("chik" in _ext_token(f) for f in args.files)
        any_chir = any("chir" in _ext_token(f) for f in args.files)
        any_txt = any(f.lower().endswith(".txt") for f in args.files)
        from ..common.sources import path_token_without_suffix

        any_cif = any(
            path_token_without_suffix(f).lower().endswith(".cif") for f in args.files
        )
        any_xrd_vendor = any(f.lower().endswith((".raw", ".brml", ".xrdml", ".rasx")) for f in args.files)
        non_cif_count = sum(
            0 if path_token_without_suffix(f).lower().endswith(".cif") else 1
            for f in args.files
        )
        cif_only = any_cif and non_cif_count == 0
        # Check for wavelength / :q parameters, excluding Windows drive colons.
        def has_wavelength_param(f):
            from ..common.sources import split_path_token

            _path, rest = split_path_token(f)
            return bool(rest)

        any_lambda = any(has_wavelength_param(f) for f in args.files) or args.wl is not None

        # Incompatibilities (no mixing of fundamentally different axis domains)
        if sum(bool(x) for x in (any_gr, any_nor, any_chik, any_chir, (any_qye or any_lambda or any_cif or any_xrd_vendor))) > 1:
            raise ValueError("Cannot mix .gr (r), .nor (energy), .chik (k), .chir (FT-EXAFS R), and Q/2θ/CIF data together. Split runs.")

        # Automatic axis selection based on file extensions
        if any_qye:
            axis_mode = "Q"
        elif any_gr:
            axis_mode = "r"
        elif any_nor:
            axis_mode = "energy"
        elif any_chik:
            axis_mode = "k"
        elif any_chir:
            axis_mode = "rft"
        elif any_txt:
            # .txt is generic: --xaxis / --wl / file:wl set XRD (or other) mode;
            # otherwise plot cols 1–2 with labels X / Y (quick plot).
            if args.xaxis:
                # Normalize case: 'q' or 'Q' → 'Q' (uppercase), everything else lowercase
                axis_mode = "Q" if args.xaxis.upper() == "Q" else args.xaxis.lower()
            elif getattr(args, 'wl', None) is not None or any_lambda:
                axis_mode = "Q"
            else:
                axis_mode = "generic"
        elif any_lambda or any_cif or any_xrd_vendor:
            # XRD vendor formats (.raw, .brml, .xrdml, .rasx) are 2theta; CIF is Q; file:wl implies Q domain
            # Explicit --xaxis always wins (including d), same as the plain-file branch below.
            if args.xaxis and args.xaxis.lower() in ("2theta", "two_theta", "tth"):
                axis_mode = "2theta"
            elif args.xaxis and args.xaxis.upper() == "Q":
                axis_mode = "Q"
            elif args.xaxis and str(args.xaxis).lower() == "d":
                axis_mode = "d"
            elif getattr(args, 'wl', None) is not None:
                # User gave --wl: default to Q and convert using file metadata or --wl
                axis_mode = "Q"
            elif any_lambda:
                # Per-file wavelength suffix (file:wl) implies Q mode by default
                axis_mode = "Q"
            elif any_cif and cif_only:
                # CIF alone: peaks are native in Q — no --wl / --xaxis required
                axis_mode = "Q"
            elif any_cif:
                # Data + CIF without λ: keep 2θ for the measured curve (CIF needs λ below)
                axis_mode = "2theta"
            else:
                # No explicit wavelength info: use 2theta so x-axis scale/label are correct
                axis_mode = "2theta"
        elif args.xaxis:
            # Normalize case: 'q' or 'Q' → 'Q' (uppercase), everything else lowercase
            axis_mode = "Q" if args.xaxis.upper() == "Q" else args.xaxis.lower()
        else:
            # .xy / .xye / .csv / etc. without --xaxis or --wl: quick plot cols 1–2 as X/Y
            axis_mode = "generic"

    use_Q   = axis_mode == "Q"
    use_2th = axis_mode == "2theta"
    use_r   = axis_mode == "r"
    use_E   = axis_mode == "energy"
    use_k   = axis_mode == "k"      # NEW
    use_rft = axis_mode == "rft"    # NEW
    use_time = axis_mode == "time"  # NEW: electrochemistry time mode

    # Keep args.xaxis in sync with resolved mode so Options ``u`` / session dump
    # always know 2θ vs Q vs d (e.g. inferred 2θ without a typed --xaxis).
    if axis_mode in ("Q", "2theta", "d", "r", "energy", "k", "rft"):
        try:
            args.xaxis = "Q" if axis_mode == "Q" else axis_mode
        except Exception:
            pass

    # Initialize wavelength_file from args.wl (may be overridden per-file later)
    wavelength_file = getattr(args, 'wl', None)

    # Validate: if using 2theta mode with CIF files, wavelength is required
    # (--wl). Unchanged when --xaxis / --wl are used: still requires args.wl
    # for 2θ+CIF (file:wl alone does not satisfy this gate — historic behavior).
    if use_2th and any_cif and not wavelength_file:
        raise ValueError(
            "Cannot display CIF files in 2θ mode without wavelength.\n"
            "Please provide wavelength using:\n"
            "  --wl <wavelength_in_angstrom>\n"
            "  or append ':<wavelength_in_angstrom>' to the CIF filename (e.g., pattern.cif:1.5406)"
        )

    # ---------------- Read and plot files ----------------
    # Helper to extract discrete peak positions from a simulated CIF pattern by local maxima picking
    def _extract_peak_positions(Q_array, I_array, min_rel_height=0.05):
        if Q_array.size == 0 or I_array.size == 0:
            return []
        Imax = I_array.max() if I_array.size else 0
        if Imax <= 0:
            return []
        thr = Imax * min_rel_height
        peaks = []
        for i in range(1, len(I_array)-1):
            if I_array[i] >= thr and I_array[i] >= I_array[i-1] and I_array[i] >= I_array[i+1]:
                # simple peak refine by local quadratic (optional)
                y1,y2,y3 = I_array[i-1], I_array[i], I_array[i+1]
                x1,x2,x3 = Q_array[i-1], Q_array[i], Q_array[i+1]
                denom = (y1 - 2*y2 + y3)
                if abs(denom) > 1e-12:
                    dx = 0.5*(y1 - y3)/denom
                    if -0.6 < dx < 0.6:
                        xc = x2 + dx*(x3 - x1)/2.0
                        if Q_array[0] <= xc <= Q_array[-1]:
                            peaks.append(xc)
                            continue
                peaks.append(Q_array[i])
        return peaks

    # Will accumulate CIF tick series to render after main curves
    cif_tick_series = []  # list of (label, filename, peak_positions_Q, wavelength_or_None, qmax_simulated, color)
    cif_hkl_map = {}      # filename -> list of (Q,h,k,l)
    cif_hkl_label_map = {}  # filename -> dict of Q -> label string
    cif_numbering_enabled = True  # show numbering for CIF tick sets (mixed mode only)
    cif_extend_suspended = False  # guard flag to prevent auto extension during certain operations
    QUIET_CIF_EXTEND = True  # suppress extension debug output

    # Cached wavelength for CIF tick conversion (prevents interactive blocking prompts)
    cif_cached_wavelength = None
    show_cif_hkl = False
    show_cif_titles = True  # show CIF filename labels by default

    # Store wavelength info per file for crosshair display
    file_wavelength_info = []  # List of dicts: {'original_wl': float or None, 'conversion_wl': float or None}
    
    # Separate style files from data files; build right_y_data_indices (--ry)
    data_files = []
    right_y_data_indices = set()
    style_file_path = None
    for i, f in enumerate(args.files):
        ext = os.path.splitext(f)[1].lower()
        if ext in ('.bps', '.bpsg', '.bpcfg'):
            if style_file_path is None:
                style_file_path = f
            else:
                print(f"Warning: Multiple style files provided, using first: {style_file_path}")
        else:
            data_files.append(f)
            if i in getattr(args, 'right_y_indices', frozenset()):
                right_y_data_indices.add(len(data_files) - 1)
    
    # --ry disables --stack (dual y-axis incompatible with stacked curves)
    if right_y_data_indices:
        args.stack = False
    
    # If no data files remain, exit
    if not data_files:
        print("No data files found (only style files provided).")
        exit(1)
    
    # Load style file if provided
    style_cfg = None
    if style_file_path:
        if not os.path.isfile(style_file_path):
            print(f"Warning: Style file not found: {style_file_path}")
        else:
            try:
                with open(style_file_path, 'r', encoding='utf-8') as f:
                    style_cfg = json.load(f)
                print(f"Using style file: {os.path.basename(style_file_path)}")
            except Exception as e:
                print(f"Warning: Could not load style file {style_file_path}: {e}")
    
    # Track files for which the "assuming already in Q" note was printed (once per file)
    _q_assumed_note_shown = set()

    # Use data_files instead of args.files for processing
    for idx_file, file_entry in enumerate(data_files):
        # Handle Windows paths (C:\... / \\?\C:\...) vs wavelength parameters (file:wl)
        from ..common.sources import split_path_token

        fname, rest = split_path_token(file_entry)
        parts = [fname] + list(rest)
        # Parse wavelength parameters: file:wl, file:wl1:wl2, file.cif:wl, or file:q
        wavelength_file = None
        original_wavelength = None  # First wavelength (for Q conversion)
        conversion_wavelength = None  # Second wavelength (for 2theta conversion back)
        file_in_q = False  # file:q → x data already in Q (Å⁻¹), no 2θ→Q conversion
        if len(parts) == 2:
            # Single wavelength (file:wl, file.cif:wl) or explicit Q marker (file:q)
            if parts[1].strip().lower() == 'q':
                file_in_q = True
            else:
                try:
                    wavelength_file = float(parts[1])
                    original_wavelength = wavelength_file
                except ValueError:
                    pass
        elif len(parts) == 3:
            # Dual wavelength: file:wl1:wl2
            try:
                original_wavelength = float(parts[1])
                conversion_wavelength = float(parts[2])
                wavelength_file = conversion_wavelength  # Use second for final conversion
            except ValueError:
                pass
        if wavelength_file is None:
            wavelength_file = args.wl
        if not os.path.isfile(fname):
            print(f"File not found: {fname}")
            continue
        file_ext = os.path.splitext(fname)[1].lower()
        is_chik = "chik" in file_ext
        is_chir = "chir" in file_ext
        is_cif  = file_ext == '.cif'
        label = os.path.basename(fname)
        if wavelength_file and not use_r and not use_E and file_ext not in (".gr", ".nor", ".cif") and not (file_in_q and not use_2th):
            if conversion_wavelength is not None:
                label += f" (λ₁={original_wavelength:.5f}→λ₂={conversion_wavelength:.5f} Å)"
            else:
                label += f" (λ={wavelength_file:.5f} Å)"
        # Wavelength info for this file (appended per curve in loop below for alignment)

        # ---- Read data (time mode for CSV/MPT or regular mode) ----
        curves_to_plot = None  # Set by each branch that produces plottable curves
        if use_time and file_ext in ('.csv', '.mpt'):
            # Time mode: read time (h) vs potential (V) for electrochemistry files
            try:
                if file_ext == '.csv':
                    if is_biologic_datalogger_csv(fname):
                        x, y = read_biologic_datalogger_time_voltage(fname)
                    else:
                        x, y = read_csv_time_voltage(fname)
                elif file_ext == '.mpt':
                    x, y = read_mpt_time_voltage(fname)
                e = None
                curves_to_plot = [(x, y, e, label)]
            except Exception as e_read:
                print(f"Error reading {fname} in time mode: {e_read}")
                continue
        elif is_cif:
            try:
                # Simulate pattern directly in Q space regardless of current axis_mode
                Q_sim, I_sim = simulate_cif_pattern_Q(fname)
                x = Q_sim
                y = I_sim
                e = None
                # Force axis mode if needed (do not override an explicit d / Q / 2θ choice)
                if axis_mode not in ("Q", "2theta", "d") and not (use_Q or use_2th):
                    use_Q = True
                    axis_mode = "Q"
                # Reflection list and per-Q hkl labels (no wavelength cutoff in pure Q domain)
                qmax_sim = float(Q_sim[-1]) if len(Q_sim) else 0.0
                refl = cif_reflection_positions(fname, Qmax=qmax_sim, wavelength=None)
                hkl_list = list_reflections_with_hkl(fname, Qmax=qmax_sim, wavelength=None)
                cif_hkl_label_map[fname] = build_hkl_label_map_from_list(hkl_list)
                # Store wavelength for CIF ticks: use provided wavelength if in 2theta mode
                cif_wl = wavelength_file if use_2th and wavelength_file else None
                # default tick color black
                cif_tick_series.append((label, fname, refl, cif_wl, qmax_sim, 'k'))
                # If CIF mixed with other data types, do NOT plot intensity curve (ticks only)
                if not cif_only:
                    continue  # skip rest of loop so curve isn't added
            except Exception as e_read:
                print(f"Error simulating CIF {fname}: {e_read}")
                continue
        elif file_ext == ".gr":
            try:
                x, y = read_gr_file(fname)
                e = None
                curves_to_plot = [(x, y, e, label)]
            except Exception as e_read:
                print(f"Error reading {fname}: {e_read}")
                continue
        elif file_ext in (".brml", ".xrdml", ".rasx") or (file_ext == ".raw" and is_bruker_raw(fname)):
            # Bruker .raw (magic RAW4.00) and .brml; .xrdml/.rasx raise in read_xrd_vendor_file
            try:
                x, y, e, wl_from_file = read_xrd_vendor_file(fname)
                if wavelength_file is None and wl_from_file is not None:
                    wavelength_file = wl_from_file
                    original_wavelength = wl_from_file
                curves_to_plot = [(x, y, e, label)]
            except Exception as e_read:
                print(f"Error reading {fname}: {e_read}")
                continue
        elif file_ext == ".raw":
            # .raw from non-Bruker instrument: load as generic text (use --xaxis/--readcol if needed)
            try:
                data = robust_loadtxt_skipheader(fname)
            except Exception as e_read:
                print(f"Error reading {fname}: {e_read}")
                continue
            if data.ndim == 1:
                data = data.reshape(1, -1)
            if data.shape[1] < 2:
                print(f"Invalid data format in {fname}: expected at least 2 columns, got {data.shape[1]}")
                continue
            readcol_spec = None
            if hasattr(args, 'readcol_by_file') and file_entry in args.readcol_by_file:
                readcol_spec = args.readcol_by_file[file_entry]
            elif hasattr(args, 'readcol_by_ext') and file_ext in args.readcol_by_ext:
                readcol_spec = args.readcol_by_ext[file_ext]
            elif args.readcol:
                readcol_spec = args.readcol
            if readcol_spec:
                pairs = [tuple(readcol_spec)] if isinstance(readcol_spec[0], int) else list(readcol_spec)
            else:
                pairs = [(1, 2)]
            xy_curves = []
            for (x_col, y_col) in pairs:
                x_col_idx, y_col_idx = x_col - 1, y_col - 1
                if x_col_idx < 0 or x_col_idx >= data.shape[1] or y_col_idx < 0 or y_col_idx >= data.shape[1]:
                    print(f"Error: Columns {x_col},{y_col} out of range in {fname} (has {data.shape[1]} columns)")
                    continue
                ec = None if readcol_spec else (data[:, 2] if data.shape[1] >= 3 else None)
                xy_curves.append((data[:, x_col_idx].copy(), data[:, y_col_idx].copy(), ec,
                                  label + (f" (cols {x_col},{y_col})" if len(pairs) > 1 else "")))
            if xy_curves:
                curves_to_plot = xy_curves
            else:
                curves_to_plot = [(data[:, 0], data[:, 1], data[:, 2] if data.shape[1] >= 3 else None, label)]
        elif args.fullprof and file_ext == ".dat":
            # Must run before the generic .dat reader (otherwise --fullprof is dead).
            try:
                y_plot, n_rows = read_fullprof_rowwise(fname)
                xstart, xend, xstep = args.fullprof[0], args.fullprof[1], args.fullprof[2]
                x_plot = np.linspace(xstart, xend, len(y_plot))
                wavelength = args.fullprof[3] if len(args.fullprof) >= 4 else wavelength_file
                if use_Q and wavelength:
                    theta_rad = np.radians(x_plot / 2)
                    x_plot = 4 * np.pi * np.sin(theta_rad) / wavelength
                e_plot = None
                curves_to_plot = [(x_plot, y_plot, e_plot, label)]
            except Exception as e:
                print(f"Error reading FullProf-style {fname}: {e}")
                continue
        elif file_ext in [".nor", ".xy", ".xye", ".qye", ".dat", ".csv"] or is_chik or is_chir:
            try:
                data = robust_loadtxt_skipheader(fname)
            except Exception as e_read:
                print(f"Error reading {fname}: {e_read}"); continue
            if data.ndim == 1: data = data.reshape(1, -1)
            if data.shape[1] < 2:
                print(f"Invalid data format in {fname}"); continue
            # Handle --readcol flag: per-file (readcol_by_file) > per-ext > global
            # Supports multi-curve: readcol_spec can be (x,y) or [(x1,y1),(x2,y2),...]
            readcol_spec = None
            if hasattr(args, 'readcol_by_file') and file_entry in args.readcol_by_file:
                readcol_spec = args.readcol_by_file[file_entry]
            elif hasattr(args, 'readcol_by_ext') and file_ext in args.readcol_by_ext:
                readcol_spec = args.readcol_by_ext[file_ext]
            elif args.readcol:
                readcol_spec = args.readcol
            # Normalize to list of (x_col, y_col) pairs for multi-curve support
            if readcol_spec:
                pairs = [tuple(readcol_spec)] if isinstance(readcol_spec[0], int) else list(readcol_spec)
            else:
                pairs = [(1, 2)]  # Default: cols 1 and 2 (1-indexed)
            xy_curves = []  # List of (x, y, e, curve_label) for this file
            for (x_col, y_col) in pairs:
                x_col_idx = x_col - 1
                y_col_idx = y_col - 1
                if x_col_idx < 0 or x_col_idx >= data.shape[1]:
                    print(f"Error: X column {x_col} out of range in {fname} (has {data.shape[1]} columns)")
                    continue
                if y_col_idx < 0 or y_col_idx >= data.shape[1]:
                    print(f"Error: Y column {y_col} out of range in {fname} (has {data.shape[1]} columns)")
                    continue
                xc = data[:, x_col_idx].copy()
                yc = data[:, y_col_idx].copy()
                ec = None  # Error bars not supported with custom column selection
                cl = label + (f" (cols {x_col},{y_col})" if len(pairs) > 1 else "")
                xy_curves.append((xc, yc, ec, cl))
            if not xy_curves:
                continue
            curves_to_plot = xy_curves
        else:
            # Unknown extension: attempt to read as 2-column (x, y) data
            try:
                data = robust_loadtxt_skipheader(fname)
            except Exception as e_read:
                print(f"Error reading {fname} (unknown extension '{file_ext}'): {e_read}")
                continue
            if data.ndim == 1: data = data.reshape(1, -1)
            if data.shape[1] < 2:
                print(f"Invalid data format in {fname}: expected at least 2 columns, got {data.shape[1]}")
                continue
            # Handle --readcol: per-file > per-ext > global, supports multi-curve
            readcol_spec = None
            if hasattr(args, 'readcol_by_file') and file_entry in args.readcol_by_file:
                readcol_spec = args.readcol_by_file[file_entry]
            elif hasattr(args, 'readcol_by_ext') and file_ext in args.readcol_by_ext:
                readcol_spec = args.readcol_by_ext[file_ext]
            elif args.readcol:
                readcol_spec = args.readcol
            if readcol_spec:
                pairs = [tuple(readcol_spec)] if isinstance(readcol_spec[0], int) else list(readcol_spec)
            else:
                pairs = [(1, 2)]
            xy_curves = []
            for (x_col, y_col) in pairs:
                x_col_idx, y_col_idx = x_col - 1, y_col - 1
                if x_col_idx < 0 or x_col_idx >= data.shape[1] or y_col_idx < 0 or y_col_idx >= data.shape[1]:
                    print(f"Error: Columns {x_col},{y_col} out of range in {fname} (has {data.shape[1]} columns)")
                    continue
                ec = None if readcol_spec else (data[:, 2] if data.shape[1] >= 3 else None)
                xy_curves.append((data[:, x_col_idx].copy(), data[:, y_col_idx].copy(), ec,
                                  label + (f" (cols {x_col},{y_col})" if len(pairs) > 1 else "")))
            if xy_curves:
                curves_to_plot = xy_curves
            else:
                # Fallback: default columns 1 and 2
                curves_to_plot = [(data[:, 0], data[:, 1], data[:, 2] if data.shape[1] >= 3 else None, label)]
            # Warn once per unknown extension type
            if not hasattr(args, '_warned_extensions'):
                args._warned_extensions = set()
            if file_ext and file_ext not in args._warned_extensions:
                args._warned_extensions.add(file_ext)
                print(
                    f"Note: Reading '{file_ext}' file as 2-column (x, y) data "
                    "(labels X / Y unless --xaxis / --wl is set)."
                )

        if not curves_to_plot:
            continue

        for (x, y, e, curve_label) in curves_to_plot:
            file_wavelength_info.append({
                'original_wl': original_wavelength,
                'conversion_wl': conversion_wavelength,
                'final_wl': wavelength_file
            })
            # ---- X-axis conversion logic updated (no conversion for energy or time) ----
            if use_time:
                # Time mode: data already in hours, no conversion needed
                x_plot = x
            elif use_2th and original_wavelength is not None and conversion_wavelength is not None:
                # Dual wavelength conversion: 2theta -> Q (wl1) -> 2theta (wl2)
                theta_rad = np.radians(x / 2.0)
                Q = 4 * np.pi * np.sin(theta_rad) / original_wavelength
                sin_theta = Q * conversion_wavelength / (4 * np.pi)
                valid_mask = np.abs(sin_theta) <= 1.0
                if not np.all(valid_mask):
                    n_invalid = np.sum(~valid_mask)
                    q_max_possible = 4 * np.pi / conversion_wavelength
                    print(f"Warning: {n_invalid} data points exceed Q_max={q_max_possible:.2f} Å⁻¹ for λ={conversion_wavelength} Å")
                    print(f"         Truncating data to physically accessible range.")
                x = x[valid_mask]
                y = y[valid_mask]
                sin_theta = sin_theta[valid_mask]
                theta_new_rad = np.arcsin(sin_theta)
                x_plot = np.degrees(2 * theta_new_rad)
            elif use_2th and (file_ext == ".qye" or file_in_q) and wavelength_file:
                # Convert Q to 2theta for .qye or file:q data when wavelength is provided
                sin_theta = x * wavelength_file / (4 * np.pi)
                valid_mask = np.abs(sin_theta) <= 1.0
                if not np.all(valid_mask):
                    n_invalid = np.sum(~valid_mask)
                    q_max_possible = 4 * np.pi / wavelength_file
                    print(f"Warning: {n_invalid} data points exceed Q_max={q_max_possible:.2f} Å⁻¹ for λ={wavelength_file} Å")
                    print(f"         Truncating data to physically accessible range.")
                x = x[valid_mask]
                y = y[valid_mask]
                sin_theta = sin_theta[valid_mask]
                theta_rad = np.arcsin(sin_theta)
                x_plot = np.degrees(2 * theta_rad)
            elif use_Q and file_ext not in (".qye", ".gr", ".nor"):
                # In Q mode, 2θ-type data with a wavelength (file:wl or --wl) are converted
                # to Q. Files marked file:q, or files without any wavelength info, are
                # assumed to be already in Q (a note is printed for the latter so silent
                # mis-plots of unconverted 2θ data are easy to spot).
                if file_in_q:
                    # Explicit file:q marker → x data already in Q, no conversion
                    x_plot = x
                elif original_wavelength is not None:
                    theta_rad = np.radians(x/2)
                    x_plot = 4*np.pi*np.sin(theta_rad)/original_wavelength
                elif wavelength_file:
                    theta_rad = np.radians(x/2)
                    x_plot = 4*np.pi*np.sin(theta_rad)/wavelength_file
                else:
                    if (file_ext in (".xy", ".xye", ".dat", ".csv", ".raw")
                        and not is_chik and not is_chir
                        and not (getattr(args, "xaxis", None) and str(args.xaxis).upper() == "Q")
                        and fname not in _q_assumed_note_shown):
                        _q_assumed_note_shown.add(fname)
                        print(f"Note: no wavelength given for '{os.path.basename(fname)}'; "
                              "assuming its x-axis is already in Q (Å⁻¹).\n"
                              "      Use 'file:wl' to convert from 2θ, or 'file:q' to mark Q data explicitly.")
                    x_plot = x
            else:
                # r, energy, k, rft, or already Q: direct
                x_plot = x

            # ---- Store full (converted) arrays BEFORE cropping ----
            x_full = x_plot.copy()
            y_full_raw = y.copy()

            # ---- Calculate first derivative if requested ----
            if getattr(args, 'derivative_1d', False) or getattr(args, 'derivative_2d', False):
                if len(y_full_raw) > 1:
                    dy_dx = np.gradient(y_full_raw, x_full)
                    y_full_raw = dy_dx
                else:
                    print(f"Warning: Cannot calculate derivative for {fname}: insufficient data points")
                    continue

            raw_y_full_list.append(y_full_raw)
            x_full_list.append(x_full)

            # ---- Apply xrange (for initial display only; full data kept above) ----
            y_plot = y_full_raw
            e_plot = e
            if args.xrange:
                mask = (x_full>=args.xrange[0]) & (x_full<=args.xrange[1])
                ax.set_xlim(args.xrange[0], args.xrange[1])
                x_plot = x_full[mask]
                y_plot = y_full_raw[mask]
                if e_plot is not None:
                    e_plot = e_plot[mask]
            else:
                x_plot = x_full

            # ---- Apply EXAFS k-weighting transformation if requested ----
            if getattr(args, 'k3chik', False):
                y_plot = y_plot * (x_plot ** 3)
                y_full_raw = y_full_raw * (x_full ** 3)
                raw_y_full_list[-1] = y_full_raw
            elif getattr(args, 'k2chik', False):
                y_plot = y_plot * (x_plot ** 2)
                y_full_raw = y_full_raw * (x_full ** 2)
                raw_y_full_list[-1] = y_full_raw
            elif getattr(args, 'kchik', False):
                y_plot = y_plot * x_plot
                y_full_raw = y_full_raw * x_full
                raw_y_full_list[-1] = y_full_raw

            # ---- Normalize (display subset) ----
            should_normalize = args.stack or getattr(args, 'norm', False)
            if should_normalize:
                if y_plot.size:
                    y_min = float(y_plot.min())
                    y_max = float(y_plot.max())
                    span = y_max - y_min
                    if span > 0:
                        y_norm = (y_plot - y_min) / span
                    else:
                        y_norm = np.zeros_like(y_plot)
                else:
                    y_norm = y_plot
            else:
                y_norm = y_plot

            is_right_y = idx_file in right_y_data_indices
            # ---- Apply offset (waterfall vs stack) ----
            if is_right_y:
                # Right-y curves overlay on ax2 (no offset)
                y_plot_offset = y_norm
                offsets_list.append(0.0)
                if ax2 is None:
                    ax2 = ax.twinx()
                    # With --txaxis: right-y curves use top x-axis (ax2.twiny())
                    if getattr(args, 'txaxis', False):
                        ax2 = ax2.twiny()
            elif args.stack:
                y_plot_offset = y_norm + offset
                y_range = (y_norm.max() - y_norm.min()) if y_norm.size else 0.0
                gap = y_range + (args.delta * (y_range if args.autoscale else 1.0))
                offsets_list.append(offset)
                offset -= gap
            else:
                increment = (y_norm.max() - y_norm.min()) * args.delta if (args.autoscale and y_norm.size) else args.delta
                y_plot_offset = y_norm + offset
                offsets_list.append(offset)
                offset += increment

            # ---- Plot curve ----
            if getattr(args, 'ro', False):
                x_plotted = y_plot_offset
                y_plotted = x_plot
            else:
                x_plotted = x_plot
                y_plotted = y_plot_offset

            target_ax = ax2 if (is_right_y and ax2 is not None) else ax
            # With --ry: assign explicit colors so plot, Colors menu (c), labels, and p/i/s/b stay consistent.
            # Matplotlib twinx uses a separate color cycle; explicit colors avoid mismatch across axes.
            if right_y_data_indices:
                try:
                    curve_idx = len(y_data_list)
                    curve_color = plt.cm.tab10(curve_idx % 10)
                    target_ax.plot(x_plotted, y_plotted, "-", lw=1, alpha=0.8, color=curve_color)
                except Exception:
                    target_ax.plot(x_plotted, y_plotted, "-", lw=1, alpha=0.8)
            else:
                target_ax.plot(x_plotted, y_plotted, "-", lw=1, alpha=0.8)
            x_data_list.append(x_plotted)
            y_data_list.append(y_plotted.copy())
            labels_list.append(curve_label)
            # Offset-free baseline for session dump/load and smooth/offset reset (p/i/s/b).
            # Under --ro the displayed Y is former X (no stack offset on that axis).
            if getattr(args, "ro", False):
                orig_y.append(np.asarray(y_plotted, dtype=float).copy())
            else:
                orig_y.append(np.asarray(y_norm, dtype=float).copy())
            if is_right_y:
                right_y_curve_indices.append(len(y_data_list) - 1)

    # Immutable full-domain backup for X expand / .pkl save (never replace with crops).
    try:
        from .full_data import install_master_full

        install_master_full(fig, x_full_list, raw_y_full_list, force=True)
    except Exception:
        pass

    # ---------------- Force axis to fit all data before labels ----------------
    ax.relim()
    ax.autoscale_view()
    if ax2 is not None:
        ax2.relim()
        ax2.autoscale_view()
    fig.canvas.draw()

    # Store the x/y limits that were used for data normalization (.bpsg save/restore)
    ax._norm_xlim = tuple(ax.get_xlim())
    ax._norm_ylim = tuple(ax.get_ylim())

    # Define a sample_tick safely (may be None if no labels yet)
    sample_tick = None
    xt_lbls = ax.get_xticklabels()
    if xt_lbls:
        sample_tick = xt_lbls[0]

    else:
        yt_lbls = ax.get_yticklabels()
        if yt_lbls:
            sample_tick = yt_lbls[0]

    # ---------------- Initial label creation (REPLACED BLOCK) ----------------
    # Remove the old simple per-curve placement loop and use:
    label_text_objects = []
    tick_fs = sample_tick.get_fontsize() if sample_tick else plt.rcParams.get('font.size', 16)
    # get_fontname() may not exist on some backends; use family from rcParams if missing
    try:
        tick_fn = sample_tick.get_fontname() if sample_tick else plt.rcParams.get('font.sans-serif', ['DejaVu Sans'])[0]
    except Exception:
        tick_fn = plt.rcParams.get('font.sans-serif', ['DejaVu Sans'])[0]

    if args.stack:
        x_max = ax.get_xlim()[1]
        for i, y_plot_offset in enumerate(y_data_list):
            y_max_curve = y_plot_offset.max() if len(y_plot_offset) else ax.get_ylim()[1]
            txt = ax.text(x_max, y_max_curve,
                          f"{i+1}: {labels_list[i]}",
                          va='top', ha='right',
                          fontsize=tick_fs, fontname=tick_fn,
                          transform=ax.transData)
            label_text_objects.append(txt)
    else:
        n = len(y_data_list)
        top_pad = 0.02
        start_y = 0.98
        spacing = min(0.08, max(0.025, 0.90 / max(n, 1)))
        for i in range(n):
            y_pos = start_y - i * spacing
            if y_pos < 0.02:
                y_pos = 0.02
            txt = ax.text(1.0, y_pos,
                          f"{i+1}: {labels_list[i]}",
                          va='top', ha='right',
                          fontsize=tick_fs, fontname=tick_fn,
                          transform=ax.transAxes)
            label_text_objects.append(txt)

    # Right y-axis state (--ry): build curve->line mapping BEFORE first update_labels
    # so label colors correctly match curves on both axes (plotting.py uses fig._xy_lines_by_curve)
    fig._xy_ax2 = ax2
    fig._xy_use_top_x = bool(getattr(args, 'txaxis', False))
    fig._xy_right_y_curve_indices = frozenset(right_y_curve_indices)
    _lines_by_curve = []
    _left_indices = sorted(i for i in range(len(y_data_list)) if i not in right_y_curve_indices)
    _right_sorted = sorted(right_y_curve_indices)
    for i in range(len(y_data_list)):
        if i in right_y_curve_indices:
            k = _right_sorted.index(i)
            _lines_by_curve.append(ax2.lines[k] if ax2 and k < len(ax2.lines) else None)
        else:
            k = _left_indices.index(i)
            _lines_by_curve.append(ax.lines[k] if k < len(ax.lines) else None)
    fig._xy_lines_by_curve = _lines_by_curve

    # Persist diffraction axis mode for interactive ``u`` / CIF redraw / session.
    # Dual-wl file:λ1:λ2 → Q uses λ1; dual-remapped 2θ uses λ2. Persist the λ
    # that matches the plotted domain (not always conversion_wl / final_wl).
    try:
        from .axis_units import set_xy_axis_mode
        if axis_mode in ("Q", "2theta", "d"):
            _ow = locals().get("original_wavelength")
            _cw = locals().get("conversion_wavelength")
            _fw = locals().get("wavelength_file")
            if axis_mode == "Q":
                persist_wl = _ow if _ow is not None else _fw
            elif axis_mode == "2theta":
                persist_wl = _fw if _fw is not None else _ow
            else:
                # d: Bragg λ is the one used to build Q (λ1 for dual / single file:wl)
                persist_wl = _ow if _ow is not None else _fw
            if persist_wl is None:
                persist_wl = getattr(args, "wl", None)
            set_xy_axis_mode(fig, axis_mode, wavelength=persist_wl)
            # Dual-remapped 2θ display (λ₂) — crosshair shows both λs
            try:
                fig._xy_dual_wl_display = bool(  # type: ignore[attr-defined]
                    use_2th
                    and _ow is not None
                    and _cw is not None
                    and any(
                        (info or {}).get("original_wl") is not None
                        and (info or {}).get("conversion_wl") is not None
                        for info in (file_wavelength_info or [])
                    )
                )
            except Exception:
                pass
            # Persist dual-wl pairs for session/style/Options ``u`` after reload
            try:
                fig._xy_file_wavelength_info = list(file_wavelength_info or [])  # type: ignore[attr-defined]
            except Exception:
                pass
        elif axis_mode == "generic":
            # Quick plot (no --xaxis / --wl): never invent 2θ for Options ``u``
            set_xy_axis_mode(fig, "unknown", wavelength=None)
        elif axis_mode in ("r", "energy", "k", "rft", "time"):
            set_xy_axis_mode(fig, "other", wavelength=None)
    except Exception:
        pass

    # Ensure consistent initial placement (especially for stacked mode)
    update_labels(ax, y_data_list, label_text_objects, args.stack, False)
    
    # Initialize curve names visibility (default to visible)
    fig._curve_names_visible = True
    # Initialize stack label position (default to top/max)
    fig._stack_label_at_bottom = False
    fig._label_anchor_left = False

    # ---------------- CIF tick overlay (after labels placed) ----------------
    def _ensure_wavelength_for_2theta():
        """Ensure wavelength assigned to all CIF tick sets without prompting.

        Prefer fig / ``--wl`` / ``file:wl`` / entry λ (same as Options ``u``).
        Cu Kα 1.5406 Å is only a last-resort BC default.
        """
        nonlocal cif_cached_wavelength
        if not cif_tick_series:
            return None
        # If any entry already has wavelength, use and cache it
        for _lab,_fname,_peaks,_wl,_qmax,_color in cif_tick_series:
            if _wl is not None:
                cif_cached_wavelength = _wl
                return _wl
        from .axis_units import resolve_cif_draw_wavelength
        wl = resolve_cif_draw_wavelength(
            fig=fig,
            args=args,
            cif_series=cif_tick_series,
            file_wavelength_info=file_wavelength_info,
            axis_mode="2theta",
        )
        if wl is None:
            wl = cif_cached_wavelength
        if wl is None:
            return None
        cif_cached_wavelength = wl
        for i,(lab, fname, peaksQ, w0, qmax_sim, color) in enumerate(cif_tick_series):
            cif_tick_series[i] = (lab, fname, peaksQ, wl, qmax_sim, color)
        return wl

    def _Q_to_2theta(peaksQ, wl):
        out = []
        if wl is None:
            return out
        for q in peaksQ:
            s = q*wl/(4*np.pi)
            if 0 <= s < 1:
                out.append(np.degrees(2*np.arcsin(s)))
        return out

    def extend_cif_tick_series(xmax_domain):
        """Extend CIF peak list if x-range upper bound increases beyond simulated Qmax.
        xmax_domain: upper x limit in current axis units (Q / 2θ / d).
        """
        if globals().get('cif_extend_suspended', False):
            return
        if not cif_tick_series:
            return
        from .axis_units import get_xy_axis_mode, xmax_domain_to_Q
        axis_mode = get_xy_axis_mode(
            fig, use_Q=use_Q, use_r=use_r, use_E=use_E, use_k=use_k, use_rft=use_rft,
            use_2th=bool(use_2th), xaxis=getattr(args, "xaxis", None), ax=ax,
        )
        if axis_mode not in ("2theta", "Q", "d"):
            # Unknown axis: do not invent Q (wrong ticks on old 2θ / blank xlabel)
            return
        # Determine target Q for extension depending on axis
        wl_any = None
        if axis_mode == "2theta":
            for entry in cif_tick_series:
                try:
                    if entry[3] is not None:
                        wl_any = entry[3]
                        break
                except Exception:
                    pass
            if wl_any is None:
                wl_any = _ensure_wavelength_for_2theta()
        updated = False
        try:
            xlim_now = ax.get_xlim()
        except Exception:
            xlim_now = None
        for i,(lab,fname,peaksQ,wl,qmax_sim,color) in enumerate(cif_tick_series):
            wl_use = wl if wl is not None else wl_any
            Q_target = xmax_domain_to_Q(
                xmax_domain, axis_mode, wl=wl_use, xlim=xlim_now,
            )
            if not QUIET_CIF_EXTEND:
                try:
                    print(f"[CIF extend check] {lab}: current Qmax={qmax_sim:.3f}, target Q={Q_target:.3f}")
                except Exception:
                    pass
            if Q_target > qmax_sim + 1e-6:
                new_Qmax = Q_target + 0.25
                try:
                    # Only apply wavelength constraint for 2θ axis; in Q/d enumerate freely
                    refl = cif_reflection_positions(
                        fname, Qmax=new_Qmax,
                        wavelength=(wl if (wl and axis_mode == "2theta") else None),
                    )
                    cif_tick_series[i] = (lab, fname, refl, wl, float(new_Qmax), color)
                    if not QUIET_CIF_EXTEND:
                        print(f"Extended CIF ticks for {lab} to Qmax={new_Qmax:.2f} (count={len(refl)})")
                    updated = True
                except Exception as e:
                    print(f"Warning: could not extend CIF peaks for {lab}: {e}")
        if updated:
            # After update, redraw ticks
            draw_cif_ticks()

    def draw_cif_ticks():
        # Interactive menu mutates _bp.cif_tick_series; session/menu paths may use a
        # different list than this closure. fig._batplot_cif_tick_series stays synced
        # from interactive_menu so redraw sees renames (r→t), reorder, colors, etc.
        cif_series_draw = getattr(fig, '_batplot_cif_tick_series', None)
        if cif_series_draw is None:
            cif_series_draw = cif_tick_series
        if not cif_series_draw:
            # Clear leftover artists after undo of the last/only CIF set.
            for art in getattr(ax, '_cif_tick_art', []):
                try:
                    art.remove()
                except Exception:
                    pass
            ax._cif_tick_art = []
            try:
                fig.canvas.draw_idle()
            except Exception:
                pass
            return
        # Preserve current limits before drawing - use actual current limits
        # to prevent any movement when toggling
        prev_xlim = ax.get_xlim()
        prev_ylim = ax.get_ylim()
        
        # Store initial limits as fixed reference point to prevent incremental movement
        # This ensures that repeated 'z' commands don't cause drift
        # Only set once on first call, then reuse to prevent drift
        if not hasattr(ax, '_cif_initial_ylim'):
            ax._cif_initial_ylim = tuple(prev_ylim)
        fixed_ylim = ax._cif_initial_ylim
        fixed_yr = fixed_ylim[1] - fixed_ylim[0]
        if fixed_yr <= 0: fixed_yr = 1.0
        
        # Check visibility flags first to decide if we need to adjust y-axis.
        # Prefer figure attrs (batch / reopened sessions); __main__ is process-global.
        show_titles = show_cif_titles  # Use closure variable
        try:
            if hasattr(fig, '_bp_show_cif_titles'):
                show_titles = bool(getattr(fig, '_bp_show_cif_titles', True))
            else:
                _bp_module = sys.modules.get('__main__')
                if _bp_module is not None and hasattr(_bp_module, 'show_cif_titles'):
                    show_titles = bool(getattr(_bp_module, 'show_cif_titles', True))
        except Exception:
            pass
        
        # Optional per-set visibility list (maintained by interactive menu).
        set_visible = None
        try:
            vis = None
            if hasattr(fig, '_bp_cif_set_visible'):
                vis = list(getattr(fig, '_bp_cif_set_visible') or [])
            else:
                _bp_module = sys.modules.get('__main__')
                if _bp_module is not None and hasattr(_bp_module, 'cif_set_visible'):
                    vis = list(getattr(_bp_module, 'cif_set_visible') or [])
            if isinstance(vis, list) and len(vis) == len(cif_series_draw):
                set_visible = [bool(v) for v in vis]
        except Exception:
            pass
        # Effective number of visible CIF rows (for spacing and y-limit expansion)
        if set_visible is None:
            n_rows = len(cif_series_draw)
        else:
            n_rows = max(1, sum(1 for v in set_visible if v))
        
        show_hkl_for_spacing = False
        try:
            if hasattr(fig, '_bp_show_cif_hkl'):
                show_hkl_for_spacing = bool(getattr(fig, '_bp_show_cif_hkl', False))
            else:
                _bp_module_sp = sys.modules.get('__main__')
                if _bp_module_sp is not None and hasattr(_bp_module_sp, 'show_cif_hkl'):
                    show_hkl_for_spacing = bool(getattr(_bp_module_sp, 'show_cif_hkl', False))
        except Exception:
            pass
        if not show_hkl_for_spacing:
            try:
                show_hkl_for_spacing = bool(globals().get('show_cif_hkl', False))
            except Exception:
                pass
        
        stacked_data = bool(args.stack or len(y_data_list) > 1)
        # Calculate base and spacing based on FIXED y-axis limits (not current)
        # This prevents incremental movement when toggling
        if stacked_data:
            global_min = min(float(a.min()) for a in y_data_list if len(a)) if y_data_list else fixed_ylim[0]
            base = global_min - 0.08 * fixed_yr
        else:
            global_min = min(float(a.min()) for a in y_data_list if len(a)) if y_data_list else 0.0
            base = global_min - 0.06 * fixed_yr
        spacing = xy_cif_row_spacing_yr(
            fixed_yr,
            show_titles=show_titles,
            show_hkl=show_hkl_for_spacing,
            stacked_or_multi_y=stacked_data,
        )
        bottom_margin = xy_cif_stack_bottom_margin_yr(fixed_yr, show_titles=show_titles)
        
        # Only adjust y-axis limits if titles are visible
        needed_min = base - (n_rows - 1) * spacing - bottom_margin
        # One y-limit state for the whole draw: must match what we keep after drawing.
        # Previously we set ylim to fixed_ylim / (needed_min, fixed_ylim[1]), drew with that yr,
        # then replaced ylim with prev_ylim — different ymax/yr broke title–tick alignment per row.
        if not show_titles:
            ylim_draw = tuple(prev_ylim)
        elif needed_min >= prev_ylim[0]:
            ylim_draw = tuple(prev_ylim)
        else:
            new_ymin = min(needed_min, prev_ylim[0])
            ylim_draw = (new_ymin, prev_ylim[1])
        ax.set_ylim(cast(Any, ylim_draw))

        cur_ylim = ax.get_ylim()
        yr = cur_ylim[1] - cur_ylim[0]
        if yr <= 0: yr = 1.0
        # Clear previous
        for art in getattr(ax, '_cif_tick_art', []):
            try: art.remove()
            except Exception: pass
        new_art = []
        mixed_mode = (not cif_only)  # cif_only variable defined earlier in script context
        # Prefer figure attr; __main__/globals are process-global leftovers.
        show_hkl = False
        try:
            if hasattr(fig, '_bp_show_cif_hkl'):
                show_hkl = bool(getattr(fig, '_bp_show_cif_hkl', False))
            else:
                _bp_module = sys.modules.get('__main__')
                if _bp_module is not None and hasattr(_bp_module, 'show_cif_hkl'):
                    show_hkl = bool(getattr(_bp_module, 'show_cif_hkl', False))
        except Exception:
            pass
        if not show_hkl:
            try:
                show_hkl = bool(globals().get('show_cif_hkl', False))
            except Exception:
                pass
        from .axis_units import domain_peak_to_Q, get_xy_axis_mode, peaks_Q_to_domain
        axis_mode_draw = get_xy_axis_mode(
            fig, use_Q=use_Q, use_r=use_r, use_E=use_E, use_k=use_k, use_rft=use_rft,
            use_2th=bool(use_2th), xaxis=getattr(args, "xaxis", None), ax=ax,
        )
        # Unknown / non-XRD: titles only (never invent Q — misplaces ticks on 2θ)
        xrd_draw = axis_mode_draw in ("2theta", "Q", "d")
        visible_idx = 0
        for i,(lab, fname, peaksQ, wl, qmax_sim, color) in enumerate(cif_series_draw):
            if set_visible is not None and i < len(set_visible) and not set_visible[i]:
                continue
            y_line = base - visible_idx * spacing + xy_cif_stack_y_offset(fig, i)
            tick_h, hkl_y = xy_cif_tick_stack_layout(y_line, yr)
            if not xrd_draw:
                domain_peaks = []
            else:
                if axis_mode_draw == "2theta" and wl is None:
                    wl = _ensure_wavelength_for_2theta()
                domain_peaks = peaks_Q_to_domain(peaksQ, axis_mode_draw, wl)
            # --- NEW: restrict to current visible x-range for performance ---
            xlow, xhigh = ax.get_xlim()
            if domain_peaks:
                # domain_peaks may be numpy array or list; create filtered list
                domain_peaks = [p for p in domain_peaks if xlow <= p <= xhigh]
            if not domain_peaks:
                # No peaks in current window; still write label row and continue (if titles are visible)
                if show_titles:
                    # Removed numbering; keep space padding
                    label_text = f" {lab}"
                    xy_cif_add_phase_title(
                        ax, prev_xlim[0], y_line, tick_h, label_text,
                        max(8, int(0.55 * plt.rcParams.get('font.size', 12))), color, new_art,
                    )
                visible_idx += 1
                continue
            # Build map for quick hkl lookup by Q (only if hkl labels are enabled).
            # Prefer fig-backed map so interactively added CIFs (same path keys)
            # are visible even if the closure map was not mutated in place.
            label_map = {}
            if show_hkl:
                hkl_src = getattr(fig, '_batplot_cif_hkl_label_map', None)
                if not isinstance(hkl_src, dict):
                    hkl_src = cif_hkl_label_map
                label_map = (hkl_src or {}).get(fname, {}) or {}
            # --- Optimized tick & hkl label drawing ---
            # Check if we should show hkl labels: need show_hkl, peaks, AND a non-empty label_map
            if show_hkl and peaksQ and label_map:
                # Guard against pathological large peak lists (can freeze UI)
                if len(peaksQ) > 4000 or len(domain_peaks) > 4000:
                    print(f"[hkl] Too many peaks in {lab} (>{len(peaksQ)}) – skipping hkl labels. Press 'z' again to toggle off.")
                    # still draw ticks below without labels
                    effective_show_hkl = False
                else:
                    effective_show_hkl = True
            else:
                effective_show_hkl = False

            # Precompute rounding function once
            if effective_show_hkl:
                # For 2θ axis we convert back to Q then round; otherwise Q directly
                for p in domain_peaks:
                    ln, = ax.plot([p, p], [y_line, y_line + tick_h], color=color, lw=1.0, alpha=0.9, zorder=3)
                    new_art.append(ln)
                    Qp = domain_peak_to_Q(p, axis_mode_draw, wl)
                    if Qp is None:
                        continue
                    Qp_rounded = round(Qp, 6)
                    lbl = label_map.get(Qp_rounded)
                    if lbl:
                        t_hkl = ax.text(p, hkl_y, lbl, ha='center', va='bottom', fontsize=7, rotation=90, color=color)
                        new_art.append(t_hkl)
            else:
                # Just draw ticks (no hkl labels)
                for p in domain_peaks:
                    ln, = ax.plot([p, p], [y_line, y_line + tick_h], color=color, lw=1.0, alpha=0.9, zorder=3)
                    new_art.append(ln)
            # Removed numbering; keep space padding (placed per CIF row)
            # Only add title label if show_cif_titles is True
            if show_titles:
                label_text = f" {lab}"
                xy_cif_add_phase_title(
                    ax, prev_xlim[0], y_line, tick_h, label_text,
                    max(8, int(0.55 * plt.rcParams.get('font.size', 12))), color, new_art,
                )
            visible_idx += 1
        ax._cif_tick_art = new_art
        ax.set_xlim(prev_xlim)
        # y-axis already set to ylim_draw before draw; avoid second set_ylim (changed yr vs. tick/title geometry)
        # Store simplified metadata for hover: list of dicts with 'x','y','label'
        hover_meta = []
        show_hkl = globals().get('show_cif_hkl', False)
        # Build mapping from Q to label text if available
        for i,(lab, fname, peaksQ, wl, qmax_sim, color) in enumerate(cif_series_draw):
            if axis_mode_draw == "2theta" and wl is None:
                wl = getattr(ax, '_cif_hover_wl', None)
            # Recreate domain peaks consistent with those drawn (limit to view)
            if axis_mode_draw == "2theta" and wl is None:
                continue
            domain_peaks = peaks_Q_to_domain(peaksQ, axis_mode_draw, wl)
            xlow, xhigh = ax.get_xlim()
            domain_peaks = [p for p in domain_peaks if xlow <= p <= xhigh]
            if not domain_peaks:
                continue
            # y baseline for this series (same spacing as main CIF draw)
            show_hkl_h = bool(globals().get('show_cif_hkl', False))
            try:
                _bm = sys.modules.get('__main__')
                if _bm is not None and hasattr(_bm, 'show_cif_hkl'):
                    show_hkl_h = bool(getattr(_bm, 'show_cif_hkl', False))
            except Exception:
                pass
            _stacked = bool(args.stack or len(y_data_list) > 1)
            if _stacked:
                global_min = min(float(a.min()) for a in y_data_list if len(a)) if y_data_list else ax.get_ylim()[0]
                base = global_min - 0.08 * yr
            else:
                global_min = min(float(a.min()) for a in y_data_list if len(a)) if y_data_list else 0.0
                base = global_min - 0.06 * yr
            spacing = xy_cif_row_spacing_yr(
                yr, show_titles=show_titles, show_hkl=show_hkl_h, stacked_or_multi_y=_stacked
            )
            y_line = base - i * spacing + xy_cif_stack_y_offset(fig, i)
            if show_hkl:
                hkl_src = getattr(fig, '_batplot_cif_hkl_label_map', None)
                if not isinstance(hkl_src, dict):
                    hkl_src = cif_hkl_label_map
                label_map = (hkl_src or {}).get(fname, {}) or {}
            else:
                label_map = {}
            for p in domain_peaks:
                Qp = domain_peak_to_Q(p, axis_mode_draw, wl)
                lbl = None
                if Qp is not None:
                    lbl = label_map.get(round(Qp, 6), None)
                hover_meta.append({'x': p, 'y': y_line, 'hkl': lbl, 'series': lab})
        ax._cif_tick_hover_meta = hover_meta
        fig.canvas.draw_idle()

        # Install hover handler once
        if not hasattr(ax, '_cif_hover_cid'):
            tooltip = ax.text(0,0,"", va='bottom', ha='left', fontsize=8,
                              color='black', bbox=dict(boxstyle='round,pad=0.2', fc='1.0', ec='0.7', alpha=0.85),
                              visible=False)
            ax._cif_hover_tooltip = tooltip
            def _on_move(event):
                if event.inaxes != ax:
                    if tooltip.get_visible():
                        tooltip.set_visible(False); fig.canvas.draw_idle()
                    return
                meta = getattr(ax, '_cif_tick_hover_meta', None)
                if not meta:
                    if tooltip.get_visible():
                        tooltip.set_visible(False); fig.canvas.draw_idle()
                    return
                x = event.xdata; y = event.ydata
                # Find nearest tick within pixel tolerance
                trans = ax.transData
                best = None; best_d2 = 25  # squared pixel distance threshold (5 px)
                for entry in meta:
                    px, py = trans.transform((entry['x'], entry['y']))
                    ex, ey = trans.transform((x, y))
                    d2 = (px-ex)**2 + (py-ey)**2
                    if d2 < best_d2:
                        best_d2 = d2; best = entry
                if best is None:
                    if tooltip.get_visible():
                        tooltip.set_visible(False); fig.canvas.draw_idle()
                    return
                # Compose text — read live axis mode (Options ``u`` may have converted)
                hkl_txt = best['hkl'] if best.get('hkl') else ''
                try:
                    from .axis_units import get_xy_axis_mode
                    mode = get_xy_axis_mode(
                        fig, use_Q=use_Q, use_r=use_r, use_E=use_E, use_k=use_k, use_rft=use_rft,
                        use_2th=bool(use_2th), xaxis=getattr(args, "xaxis", None), ax=ax,
                    )
                    if mode not in ("2theta", "Q", "d"):
                        mode = "2theta" if use_2th else ("Q" if use_Q else "unknown")
                except Exception:
                    mode = "2theta" if use_2th else ("Q" if use_Q else "unknown")
                if mode == "Q":
                    tip = f"{best['series']}\nQ={best['x']:.4f}"
                elif mode == "2theta":
                    tip = f"{best['series']}\n2θ={best['x']:.4f}"
                elif mode == "d":
                    tip = f"{best['series']}\nd={best['x']:.4f}"
                else:
                    tip = f"{best['series']} {best['x']:.4f}"
                if hkl_txt:
                    tip += f"\n{hkl_txt}"
                tooltip.set_text(tip)
                tooltip.set_position((best['x'], best['y'] + 0.025*yr))
                if not tooltip.get_visible():
                    tooltip.set_visible(True)
                fig.canvas.draw_idle()
            cid = fig.canvas.mpl_connect('motion_notify_event', _on_move)
            ax._cif_hover_cid = cid

    # Always expose the live series + draw helpers so interactive ``cif`` → ``a``
    # can add the first CIF without restarting (empty series draws nothing).
    try:
        fig._batplot_cif_tick_series = cif_tick_series
        fig._batplot_cif_hkl_label_map = cif_hkl_label_map
    except Exception:
        pass
    if cif_tick_series:
        # Auto-assign distinct colors for CIF tick series.
        # For multiple CIF series:
        #   - If <= 10 files, use 'tab10' but in a re-ordered sequence to
        #     maximize visual separation between adjacent colors.
        #   - If > 10 files, use 'viridis' with evenly spaced samples.
        #
        # This overrides any previous per-series color so that the requested
        # colormap behavior is always enforced.
        if len(cif_tick_series) > 1:
            try:
                n_cif = len(cif_tick_series)
                if n_cif <= 10:
                    tab10_cmap = get_colormap('tab10')
                    tab10 = tab10_cmap.colors if tab10_cmap is not None and hasattr(tab10_cmap, 'colors') else None
                    if not tab10:
                        raise ValueError("tab10 colormap unavailable")
                    # Reorder indices for more distinct neighboring colors
                    order = [0, 3, 6, 1, 4, 7, 2, 5, 8, 9]
                    new_series = []
                    for i, (lab, fname, peaksQ, wl, qmax_sim, col) in enumerate(cif_tick_series):
                        idx = order[i] if i < len(order) else i % len(tab10)
                        color = tab10[idx]
                        new_series.append((lab, fname, peaksQ, wl, qmax_sim, color))
                else:
                    cmap = get_colormap('viridis')
                    if cmap is None:
                        raise ValueError("viridis colormap unavailable")
                    positions = np.linspace(0.0, 1.0, n_cif)
                    new_series = []
                    for (pos, (lab, fname, peaksQ, wl, qmax_sim, col)) in zip(positions, cif_tick_series):
                        color = cmap(pos)
                        new_series.append((lab, fname, peaksQ, wl, qmax_sim, color))
                cif_tick_series[:] = new_series
            except Exception:
                pass
        if use_2th:
            _ensure_wavelength_for_2theta()
        draw_cif_ticks()
    # expose helpers for interactive updates (including empty → add CIF)
    ax._cif_extend_func = extend_cif_tick_series
    ax._cif_draw_func = draw_cif_ticks

    # Handle EXAFS k-weighted χ(k) mode labels
    if getattr(args, 'k3chik', False):
        x_label = r"k ($\mathrm{\AA}^{-1}$)"
        y_label = r"k$^3$χ(k) ($\mathrm{\AA}^{-3}$)"
    elif getattr(args, 'k2chik', False):
        x_label = r"k ($\mathrm{\AA}^{-1}$)"
        y_label = r"k$^2$χ(k) ($\mathrm{\AA}^{-2}$)"
    elif getattr(args, 'kchik', False):
        x_label = r"k ($\mathrm{\AA}^{-1}$)"
        y_label = r"kχ(k) ($\mathrm{\AA}^{-1}$)"
    elif getattr(args, 'chik', False):
        x_label = r"k ($\mathrm{\AA}^{-1}$)"
        y_label = r"χ(k)"
    else:
        if use_E: x_label = "Energy (eV)"
        elif use_r: x_label = r"r (Å)"
        elif use_k: x_label = r"k ($\mathrm{\AA}^{-1}$)"
        elif use_rft: x_label = "Radial distance (Å)"
        elif use_Q: x_label = r"Q ($\mathrm{\AA}^{-1}$)"
        elif use_2th: x_label = "2θ (deg)"
        elif axis_mode == "d":
            x_label = r"d ($\mathrm{\AA}$)"
        elif use_time: x_label = "Time (h)"
        elif axis_mode == "generic":
            x_label = "X"
        elif args.xaxis:
            x_label = str(args.xaxis)
        else:
            x_label = "X"
        
        # Y-axis label: normalized if --stack or --norm, or voltage for time mode
        should_normalize = args.stack or getattr(args, 'norm', False)
        if use_time:
            y_label = "Potential (V)"
        elif should_normalize:
            y_label = "Normalized intensity (a.u.)"
        elif axis_mode == "generic":
            y_label = "Y"
        else:
            y_label = "Intensity"
    
    # Swap axis labels if --ro flag is set
    if getattr(args, 'ro', False):
        ax.set_xlabel(y_label, fontsize=16)
        ax.set_ylabel(x_label, fontsize=16)
        # Right y-axis (--ry): same swap when ax2 exists
        if ax2 is not None:
            ax2.set_ylabel(x_label, fontsize=16)
    else:
        ax.set_xlabel(x_label, fontsize=16)
        ax.set_ylabel(y_label, fontsize=16)
        # Right y-axis (--ry): same label as left when ax2 exists
        if ax2 is not None:
            ax2.set_ylabel(y_label, fontsize=16)

    # Store originals for axis-title toggle restoration (t menu bn/ln)
    try:
        ax._stored_xlabel = ax.get_xlabel()
        ax._stored_ylabel = ax.get_ylabel()
    except Exception:
        pass

    # --- FINAL LABEL POSITION PASS ---
    # Some downstream operations (e.g. CIF tick overlay extending y-limits or auto margin
    # adjustments by certain backends) can occur after the initial label placement,
    # leading to visibly misplaced curve labels on first show. We perform a final
    # synchronous draw + update_labels here to lock them to the correct coordinates
    # before any saving / interactive session starts. (Subsequent interactions still
    # use the existing callbacks / update logic.)
    try:
        fig.canvas.draw()  # ensure limits are finalized
        update_labels(ax, y_data_list, label_text_objects, args.stack, False)
    except Exception:
        pass

    # ---------------- Apply style file if provided ----------------
    if style_cfg:
        try:
            _apply_xy_style(fig, ax, style_cfg)
            # Redraw after applying style
            fig.canvas.draw()
        except Exception as e:
            print(f"Warning: Error applying style file: {e}")

    # ---------------- Save figure object ----------------
    if args.savefig:
        # Remove numbering for exported figure object (if ticks present)
        if cif_tick_series and 'cif_numbering_enabled' in globals() and cif_numbering_enabled:
            prev_num = cif_numbering_enabled
            cif_numbering_enabled = False
            if 'draw_cif_ticks' in globals():
                draw_cif_ticks()
            target = _confirm_overwrite(args.savefig)
            if target:
                with open(target, "wb") as f:
                    pickle.dump(fig, f)
            cif_numbering_enabled = prev_num
            if 'draw_cif_ticks' in globals():
                draw_cif_ticks()
        else:
            target = _confirm_overwrite(args.savefig)
            if target:
                with open(target, "wb") as f:
                    pickle.dump(fig, f)
        if target:
            print(f"Saved figure object to {target}")

    # ---------------- Show and interactive menu ----------------
    from ...cli_save import run_cli_save_if_requested, save_xy_session, should_show_plot

    def _do_xy_cli_save(target: str) -> None:
        save_xy_session(
            target,
            fig=fig,
            ax=ax,
            x_data_list=x_data_list,
            y_data_list=y_data_list,
            orig_y=orig_y,
            x_full_list=x_full_list,
            raw_y_full_list=raw_y_full_list,
            offsets_list=offsets_list,
            labels=labels_list,
            delta=args.delta,
            args=args,
            cif_tick_series=cif_tick_series if cif_tick_series else None,
            cif_hkl_map=cif_hkl_map,
            cif_hkl_label_map=cif_hkl_label_map,
            show_cif_hkl=bool(show_cif_hkl),
            show_cif_titles=bool(show_cif_titles),
        )

    if run_cli_save_if_requested(
        args,
        [os.path.abspath(f) for f in data_files],
        purpose="project save",
        default_stem=os.path.splitext(os.path.basename(data_files[0]))[0] if len(data_files) == 1 else None,
        combined_plot=len(data_files) > 1,
        save_fn=_do_xy_cli_save,
    ):
        try:
            plt.close(fig)
        except Exception:
            pass
        return 0

    if args.interactive:
        if not require_interactive_display(args, context="XY interactive menu"):
            return 0
        prime_interactive_figure(fig)
        # Increase default upper margin (more space): reduce 'top' value once and lock
        try:
            sp = fig.subplotpars
            if sp.top >= 0.88:  # only if near default
                fig.subplots_adjust(top=0.88)
                fig._interactive_top_locked = True
        except Exception:
            pass
        
        # CRITICAL: Disable automatic layout adjustments to ensure parameter independence
        # This prevents matplotlib from moving axes when labels are changed
        try:
            fig.set_layout_engine('none')
        except AttributeError:
            # Older matplotlib versions - disable tight_layout
            try:
                fig.set_tight_layout(False)
            except Exception:
                pass

        # Track whether data axes were swapped via --ro for this figure
        try:
            fig._ro_active = bool(getattr(args, "ro", False))
        except Exception:
            pass
        
        # Build CIF globals dict for explicit passing
        cif_globals = {
            'cif_tick_series': cif_tick_series,
            'cif_hkl_map': cif_hkl_map,
            'cif_hkl_label_map': cif_hkl_label_map,
            'show_cif_hkl': show_cif_hkl,
            'show_cif_titles': show_cif_titles,
            'cif_extend_suspended': cif_extend_suspended,
            'keep_canvas_fixed': keep_canvas_fixed,
            'file_wavelength_info': file_wavelength_info,
        }
        
        interactive_menu(
            fig, ax, y_data_list, x_data_list, labels_list,
            orig_y, label_text_objects, args.delta, x_label, args,
            x_full_list, raw_y_full_list, offsets_list,
            use_Q, use_r, use_E, use_k, use_rft, use_2th,
            cif_globals=cif_globals,
        )
        hold_figure_open()
    elif args.out:
        out_file = args.out
        if not os.path.splitext(out_file)[1]:
            out_file += ".svg"
        # Confirm overwrite for export path
        export_target = _confirm_overwrite(out_file)
        if not export_target:
            print("Export canceled.")
        else:
            for i, txt in enumerate(label_text_objects):
                txt.set_text(labels_list[i])
            # Temporarily disable numbering for export
            if cif_tick_series and 'cif_numbering_enabled' in globals() and cif_numbering_enabled:
                prev_num = cif_numbering_enabled
                cif_numbering_enabled = False
                if 'draw_cif_ticks' in globals():
                    draw_cif_ticks()
                # Transparent background for SVG exports
                _, _ext = os.path.splitext(export_target)
                if _ext.lower() == '.svg':
                    try:
                        _fig_fc = fig.get_facecolor()
                    except Exception:
                        _fig_fc = None
                    try:
                        _ax_fc = ax.get_facecolor()
                    except Exception:
                        _ax_fc = None
                    try:
                        if getattr(fig, 'patch', None) is not None:
                            fig.patch.set_alpha(0.0); fig.patch.set_facecolor('none')
                        if getattr(ax, 'patch', None) is not None:
                            ax.patch.set_alpha(0.0); ax.patch.set_facecolor('none')
                    except Exception:
                        pass
                    try:
                        fig.savefig(export_target, dpi=300, transparent=True, facecolor='none', edgecolor='none')
                    finally:
                        try:
                            if _fig_fc is not None and getattr(fig, 'patch', None) is not None:
                                fig.patch.set_alpha(1.0); fig.patch.set_facecolor(_fig_fc)
                        except Exception:
                            pass
                        try:
                            if _ax_fc is not None and getattr(ax, 'patch', None) is not None:
                                ax.patch.set_alpha(1.0); ax.patch.set_facecolor(_ax_fc)
                        except Exception:
                            pass
                else:
                    fig.savefig(export_target, dpi=300)
                cif_numbering_enabled = prev_num
                if 'draw_cif_ticks' in globals():
                    draw_cif_ticks()
            else:
                # Transparent background for SVG exports
                _, _ext = os.path.splitext(export_target)
                if _ext.lower() == '.svg':
                    try:
                        _fig_fc = fig.get_facecolor()
                    except Exception:
                        _fig_fc = None
                    try:
                        _ax_fc = ax.get_facecolor()
                    except Exception:
                        _ax_fc = None
                    try:
                        if getattr(fig, 'patch', None) is not None:
                            fig.patch.set_alpha(0.0); fig.patch.set_facecolor('none')
                        if getattr(ax, 'patch', None) is not None:
                            ax.patch.set_alpha(0.0); ax.patch.set_facecolor('none')
                    except Exception:
                        pass
                    try:
                        fig.savefig(export_target, dpi=300, transparent=True, facecolor='none', edgecolor='none')
                    finally:
                        try:
                            if _fig_fc is not None and getattr(fig, 'patch', None) is not None:
                                fig.patch.set_alpha(1.0); fig.patch.set_facecolor(_fig_fc)
                        except Exception:
                            pass
                        try:
                            if _ax_fc is not None and getattr(ax, 'patch', None) is not None:
                                ax.patch.set_alpha(1.0); ax.patch.set_facecolor(_ax_fc)
                        except Exception:
                            pass
                else:
                    fig.savefig(export_target, dpi=300)
            print(f"Saved plot to {export_target}")
    elif should_show_plot(args):
        show_figure_if_possible(args)
    
    # Success
    return 0

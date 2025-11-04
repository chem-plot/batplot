"""batplot - Interactive plotting for XRD, PDF, XAS and electrochemistry data.

This module can be imported as a library (safe, no side effects) or run as CLI (via batplot_main()).
"""

from __future__ import annotations

# Import all dependencies at module level (no side effects)
from .electrochem_interactive import electrochem_interactive_menu
from .args import parse_args as _bp_parse_args
from .interactive import interactive_menu
from .batch import batch_process, batch_process_ec
from .converters import convert_to_qye
from .session import (
    dump_session as _bp_dump_session,
    load_ec_session,
    load_operando_session,
    load_cpc_session,
)
from .operando import plot_operando_folder
from .plotting import update_labels
from .utils import _confirm_overwrite, normalize_label_text
from .readers import (
    read_csv_file, 
    read_fullprof_rowwise, 
    robust_loadtxt_skipheader, 
    read_gr_file,
    read_mpt_file,
    read_ec_csv_file,
    read_ec_csv_dqdv_file,
    read_csv_time_voltage,
    read_mpt_time_voltage,
)
from .cif import (
    simulate_cif_pattern_Q,
    cif_reflection_positions,
    list_reflections_with_hkl,
    build_hkl_label_map_from_list,
)
from .ui import (
    apply_font_changes as _ui_apply_font_changes,
    sync_fonts as _ui_sync_fonts,
    position_top_xlabel as _ui_position_top_xlabel,
    position_right_ylabel as _ui_position_right_ylabel,
    update_tick_visibility as _ui_update_tick_visibility,
    ensure_text_visibility as _ui_ensure_text_visibility,
    resize_plot_frame as _ui_resize_plot_frame,
    resize_canvas as _ui_resize_canvas,
)
from .style import (
    print_style_info as _bp_print_style_info,
    export_style_config as _bp_export_style_config,
    apply_style_config as _bp_apply_style_config,
)

import numpy as np
import sys
import os
import pickle
import random
import argparse
import re
import matplotlib as _mpl
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator, NullFormatter

# Try to import optional interactive menus
try:
    from .operando_ec_interactive import operando_ec_interactive_menu
except ImportError:
    operando_ec_interactive_menu = None

try:
    from .cpc_interactive import cpc_interactive_menu
except ImportError:
    cpc_interactive_menu = None

# Global state variables (used by interactive menus and style system)
keep_canvas_fixed = False


def _natural_sort_key(filename: str) -> list:
    """Generate a natural sorting key for filenames with numbers.
    
    Converts 'file_10.xy' to ['file_', 10, '.xy'] so numerical parts are sorted numerically.
    This ensures file_2.xy comes before file_10.xy (natural order).
    """
    parts = []
    for match in re.finditer(r'(\d+|\D+)', filename):
        text = match.group(0)
        if text.isdigit():
            parts.append(int(text))
        else:
            parts.append(text.lower())
    return parts


def batplot_main() -> int:
    """Main entry point for batplot CLI.
    
    Parses arguments and executes the appropriate plotting mode.
    This function contains all the side-effect code that was previously at module level.
    
    Returns:
        Exit code (0 for success, non-zero for error)
    """
    # Parse CLI arguments
    args = _bp_parse_args()

    # Check if no input provided (no files and no special flags)
    has_special_flag = any([
        getattr(args, 'gc', False),
        getattr(args, 'cv', False),
        getattr(args, 'dqdv', False),
        getattr(args, 'cpc', False),
        getattr(args, 'operando', False),
        getattr(args, 'all', None) is not None,
        getattr(args, 'convert', None) is not None,
    ])
    
    if not args.files and not has_special_flag:
        print("No input provided, nothing to do.")
        print("Use 'batplot -h' to see help.")
        return 0

    # --- EC Batch Mode: process all EC files in a directory ---
    # Check if any EC mode is active and user specified 'all' or a directory
    ec_mode_active = any([
        getattr(args, 'gc', False),
        getattr(args, 'cv', False),
        getattr(args, 'dqdv', False),
        getattr(args, 'cpc', False)
    ])
    
    # Check for --all flag (with or without style file)
    if ec_mode_active and getattr(args, 'all', None) is not None:
        batch_process_ec(os.getcwd(), args)
        exit()
    
    if ec_mode_active and len(args.files) == 1:
        sole = args.files[0]
        if sole.lower() == 'all':
            batch_process_ec(os.getcwd(), args)
            exit()
        elif os.path.isdir(sole):
            batch_process_ec(os.path.abspath(sole), args)
            exit()

    # --- CV mode: plot voltage vs current for each cycle from .mpt ---
    if getattr(args, 'cv', False):
        import os as _os
        import matplotlib.pyplot as _plt
        if len(args.files) != 1:
            print("CV mode: provide exactly one file (.mpt or .txt).")
            exit(1)
        ec_file = args.files[0]
        if not _os.path.isfile(ec_file):
            print(f"File not found: {ec_file}")
            exit(1)
        try:
            # Support both .mpt and .txt formats
            if ec_file.lower().endswith('.txt'):
                from .readers import read_biologic_txt_file
                voltage, current, cycles = read_biologic_txt_file(ec_file, mode='cv')
            else:
                voltage, current, cycles = read_mpt_file(ec_file, mode='cv')
            # Normalize cycle indices to start at 1
            # Find the first cycle with at least 2 data points (needed for plotting)
            cyc_int_raw = np.array(np.rint(cycles), dtype=int)
            if cyc_int_raw.size:
                unique_cycles_raw = np.unique(cyc_int_raw)
                valid_min_c = None
                for c in sorted(unique_cycles_raw):
                    if np.sum(cyc_int_raw == c) >= 2:
                        valid_min_c = int(c)
                        break
                
                if valid_min_c is not None:
                    shift = 1 - valid_min_c
                else:
                    min_c = int(np.min(cyc_int_raw))
                    shift = 1 - min_c if min_c <= 0 else 0
            else:
                shift = 0
            cyc_int = cyc_int_raw + shift
            cycles_present = sorted(int(c) for c in np.unique(cyc_int)) if cyc_int.size else [1]
            # Color palette
            base_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                           '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
            # Ensure font and canvas settings match GC/dQdV
            _plt.rcParams.update({
                'font.family': 'sans-serif',
                'font.sans-serif': ['Arial', 'DejaVu Sans', 'Helvetica', 'STIXGeneral', 'Liberation Sans', 'Arial Unicode MS'],
                'mathtext.fontset': 'dejavusans',
                'font.size': 16
            })
            fig, ax = _plt.subplots(figsize=(10, 6))
            cycle_lines = {}
            for cyc in cycles_present:
                mask = (cyc_int == cyc)
                idx = np.where(mask)[0]
                if idx.size >= 2:
                    # Insert NaNs between non-consecutive indices for proper cycle breaks
                    parts_x = []
                    parts_y = []
                    start = 0
                    for k in range(1, idx.size):
                        if idx[k] != idx[k-1] + 1:
                            parts_x.append(voltage[idx[start:k]])
                            parts_y.append(current[idx[start:k]])
                            start = k
                    parts_x.append(voltage[idx[start:]])
                    parts_y.append(current[idx[start:]])
                    X = []
                    Y = []
                    for i, (px, py) in enumerate(zip(parts_x, parts_y)):
                        if i > 0:
                            X.append(np.array([np.nan]))
                            Y.append(np.array([np.nan]))
                        X.append(px)
                        Y.append(py)
                    x_b = np.concatenate(X) if X else np.array([])
                    y_b = np.concatenate(Y) if Y else np.array([])
                    ln, = ax.plot(x_b, y_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                  linewidth=2.0, label=str(cyc), alpha=0.8)
                    cycle_lines[cyc] = ln
            ax.set_xlabel('Voltage (V)', labelpad=8.0)
            ax.set_ylabel('Current (mA)', labelpad=8.0)
            legend = ax.legend(title='Cycle')
            legend.get_title().set_fontsize('medium')
            # Match GC/dQdV: consistent label/title displacement and canvas
            fig.subplots_adjust(left=0.12, right=0.95, top=0.88, bottom=0.15)
            # Interactive menu: use electrochem_interactive_menu for consistency with GC
            if args.interactive:
                try:
                    _plt.ion()
                except Exception:
                    pass
                _plt.show(block=False)
                try:
                    electrochem_interactive_menu(fig, ax, cycle_lines)
                except Exception as _ie:
                    print(f"Interactive menu failed: {_ie}")
                _plt.show()
            else:
                _plt.show()
            exit(0)
        except Exception as e:
            print(f"CV plot failed: {e}")
            exit(1)


    """
    batplot_v1.0.10: Interactively plot:
        XRD data .xye, .xy, .qye, .dat, .csv
        PDF data .gr
        XAS data .nor, .chik, .chir
        More features to be added.
    """


    # Ensure an interactive (GUI) backend when a window is expected (interactive mode or operando/GC plots)
    def _ensure_gui_backend_for_interactive():
        try:
            argv = sys.argv
        except Exception:
            argv = []
        # Trigger if interactive is requested OR when operando/GC plotting likely calls show()
        wants_interactive = any(flag in argv for flag in ("--interactive",))
        wants_interactive = wants_interactive or ("--operando" in argv)
        wants_interactive = wants_interactive or ("--gc" in argv)
        if not wants_interactive:
            return
        # If MPLBACKEND is set to a GUI backend, respect it; if it's non-interactive, we'll override below
        env_be = os.environ.get("MPLBACKEND")
        if env_be:
            low = env_be.lower()
            if low in {"macosx","tkagg","qtagg"}:
                return
        try:
            be = _mpl.get_backend()
        except Exception:
            be = None
        def _is_noninteractive(name):
            if not isinstance(name, str):
                return False
            low = name.lower()
            return ("agg" in low) or ("inline" in low) or (low in {"pdf","ps","svg","template"})
        if not _is_noninteractive(be):
            return
        # Try GUI backends in order of likelihood
        candidates = [
            ("darwin", ["MacOSX", "TkAgg", "QtAgg"]),
            ("win", ["TkAgg", "QtAgg"]),
            ("other", ["TkAgg", "QtAgg"]),
        ]
        plat = sys.platform
        if plat == "darwin":
            order = candidates[0][1]
        elif plat.startswith("win"):
            order = candidates[1][1]
        else:
            order = candidates[2][1]
        import importlib.util as _ilus
        for cand in order:
            try:
                if cand == "TkAgg":
                    if _ilus.find_spec("tkinter") is None:
                        continue
                elif cand == "QtAgg":
                    if (_ilus.find_spec("PyQt5") is None) and (_ilus.find_spec("PySide6") is None):
                        continue
                # MacOSX: attempt; will fail on non-framework builds
                _mpl.use(cand, force=True)
                break
            except Exception:
                continue

    _ensure_gui_backend_for_interactive()

    import matplotlib.pyplot as plt
    # Note: All imports moved to module level for clean import behavior
    
    # Set global default font
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['Arial', 'DejaVu Sans', 'Helvetica', 'STIXGeneral', 'Liberation Sans', 'Arial Unicode MS'],
        'mathtext.fontset': 'dejavusans',   # keeps math consistent with Arial-like sans
        'font.size': 16
    })

    # Parse CLI arguments early; many top-level branches depend on args
    args = _bp_parse_args()


    """
    Note: CIF parsing and simulation helpers now come from batplot.cif.
    This file defers to simulate_cif_pattern_Q and cif_reflection_positions
    imported above to avoid duplicating heavy logic here.
    """

    # ---------------- Conversion Function ----------------
    # Implemented in batplot.converters as convert_to_qye

    # Readers now live in batplot.readers; avoid duplicating implementations here.

    # ---------------- .gr (Pair Distribution Function) Reading ----------------

    # Label layout handled by plotting.update_labels imported at top.

    #!/ End of legacy inline interactive_menu.
    # Normal XY interactive menu is imported from batplot.interactive as `interactive_menu`.

    # Galvanostatic cycling mode check: .mpt or supported .csv file with --gc flag
    if getattr(args, 'gc', False):
        import os as _os
        import matplotlib.pyplot as _plt
    
        if len(args.files) != 1:
            print("GC mode: provide exactly one file argument (.mpt or .csv).")
            exit(1)
    
        ec_file = args.files[0]
        if not _os.path.isfile(ec_file):
            print(f"File not found: {ec_file}")
            exit(1)
    
        try:
            # Branch by extension
            if ec_file.lower().endswith('.mpt'):
                # For .mpt, mass is required to compute specific capacity
                mass_mg = getattr(args, 'mass', None)
                if mass_mg is None:
                    print("GC mode (.mpt): --mass parameter is required (active material mass in milligrams).")
                    print("Example: batplot file.mpt --gc --mass 7.0")
                    exit(1)
                specific_capacity, voltage, cycle_numbers, charge_mask, discharge_mask = read_mpt_file(ec_file, mode='gc', mass_mg=mass_mg)
                x_label_gc = r'Specific Capacity (mAh g$^{-1}$)'
                cap_x = specific_capacity
            elif ec_file.lower().endswith('.csv'):
                # For supported CSV export, use specific capacity directly when available (no mass required)
                cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = read_ec_csv_file(ec_file, prefer_specific=True)
                x_label_gc = r'Specific Capacity (mAh g$^{-1}$)'
            else:
                print("GC mode: file must be .mpt or .csv")
                exit(1)

            # Create the plot
            fig, ax = _plt.subplots(figsize=(10, 6))

            # Build per-cycle lines for charge and discharge
            def _contiguous_blocks(mask):
                inds = np.where(mask)[0]
                if inds.size == 0:
                    return []
                blocks = []
                start = inds[0]
                prev = inds[0]
                for j in inds[1:]:
                    if j == prev + 1:
                        prev = j
                    else:
                        blocks.append((start, prev))
                        start = j
                        prev = j
                blocks.append((start, prev))
                return blocks

            def _broken_arrays_from_indices(idx: np.ndarray, x: np.ndarray, y: np.ndarray):
                """Insert NaNs between non-consecutive indices so a single Line2D can represent disjoint segments."""
                if idx.size == 0:
                    return np.array([]), np.array([])
                parts_x = []
                parts_y = []
                start = 0
                for k in range(1, idx.size):
                    if idx[k] != idx[k-1] + 1:
                        parts_x.append(x[idx[start:k]])
                        parts_y.append(y[idx[start:k]])
                        start = k
                parts_x.append(x[idx[start:]])
                parts_y.append(y[idx[start:]])
                # Concatenate with NaN separators
                X = []
                Y = []
                for i, (px, py) in enumerate(zip(parts_x, parts_y)):
                    if i > 0:
                        X.append(np.array([np.nan]))
                        Y.append(np.array([np.nan]))
                    X.append(px)
                    Y.append(py)
                return np.concatenate(X) if X else np.array([]), np.concatenate(Y) if Y else np.array([])

            if cycle_numbers is not None:
                # Normalize cycle indices to start at 1 (BioLogic may start at 0)
                # But first, identify cycles with sufficient data (>= 2 points) to be plotted
                cyc_int_raw = np.array(np.rint(cycle_numbers), dtype=int)
                if cyc_int_raw.size:
                    # Find the minimum cycle number that has at least 2 data points
                    unique_cycles_raw = np.unique(cyc_int_raw)
                    valid_min_c = None
                    for c in sorted(unique_cycles_raw):
                        if np.sum(cyc_int_raw == c) >= 2:
                            valid_min_c = int(c)
                            break
                    
                    if valid_min_c is not None:
                        # Shift so the first valid cycle becomes cycle 1
                        shift = 1 - valid_min_c
                    else:
                        # No valid cycles found, use original min
                        min_c = int(np.min(cyc_int_raw))
                        shift = 1 - min_c if min_c <= 0 else 0
                else:
                    shift = 0
                
                cyc_int = cyc_int_raw + shift
                cycles_present = sorted(int(c) for c in np.unique(cyc_int))
            else:
                cycles_present = [1]

            # Determine if cycle numbers are meaningful
            inferred = len(cycles_present) <= 1
            if inferred:
                ch_blocks = _contiguous_blocks(charge_mask)
                dch_blocks = _contiguous_blocks(discharge_mask)
                cycles_present = list(range(1, max(len(ch_blocks), len(dch_blocks)) + 1)) if (ch_blocks or dch_blocks) else [1]

            # Prepare colors
            base_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                       '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

            # Mapping: cycle_number -> {'charge': Line2D|None, 'discharge': Line2D|None}
            cycle_lines = {}

            if not inferred and cycle_numbers is not None:
                for cyc in cycles_present:
                    # Charge
                    mask_c = (cyc_int == cyc) & charge_mask
                    idx = np.where(mask_c)[0]
                    if idx.size >= 2:
                        x_b, y_b = _broken_arrays_from_indices(idx, cap_x, voltage)
                        # Label only once per cycle for legend: Cycle N
                        ln_c, = ax.plot(x_b, y_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                        linewidth=2.0, label=str(cyc), alpha=0.8)
                    else:
                        ln_c = None
                    # Discharge
                    mask_d = (cyc_int == cyc) & discharge_mask
                    idxd = np.where(mask_d)[0]
                    if idxd.size >= 2:
                        xd_b, yd_b = _broken_arrays_from_indices(idxd, cap_x, voltage)
                        # Use no legend entry for the second line of the same cycle
                        lbl = '_nolegend_' if ln_c is not None else str(cyc)
                        ln_d, = ax.plot(xd_b, yd_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                        linewidth=2.0, label=lbl, alpha=0.8)
                    else:
                        ln_d = None
                    cycle_lines[cyc] = {"charge": ln_c, "discharge": ln_d}
            else:
                # Infer cycles by alternating contiguous charge/discharge blocks
                ch_blocks = _contiguous_blocks(charge_mask)
                dch_blocks = _contiguous_blocks(discharge_mask)
                N = max(len(ch_blocks), len(dch_blocks))
                for i in range(N):
                    cyc = i + 1
                    ln_c = None
                    if i < len(ch_blocks):
                        a, b = ch_blocks[i]
                        idx = np.arange(a, b + 1)
                        x_b, y_b = _broken_arrays_from_indices(idx, cap_x, voltage)
                        ln_c, = ax.plot(x_b, y_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                        linewidth=2.0, label=str(cyc), alpha=0.8)
                    ln_d = None
                    if i < len(dch_blocks):
                        a, b = dch_blocks[i]
                        idx = np.arange(a, b + 1)
                        xd_b, yd_b = _broken_arrays_from_indices(idx, cap_x, voltage)
                        lbl = '_nolegend_' if ln_c is not None else str(cyc)
                        ln_d, = ax.plot(xd_b, yd_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                        linewidth=2.0, label=lbl, alpha=0.8)
                    cycle_lines[cyc] = {"charge": ln_c, "discharge": ln_d}
            # Labels with consistent labelpad
            ax.set_xlabel(x_label_gc, labelpad=8.0)
            ax.set_ylabel('Voltage (V)', labelpad=8.0)
            legend = ax.legend(title='Cycle')
            legend.get_title().set_fontsize('medium')
            # No background grid by default for GC plots
        
            # Adjust layout to ensure top and bottom labels/titles are visible
            fig.subplots_adjust(left=0.12, right=0.95, top=0.88, bottom=0.15)

            # Save if requested
            outname = args.savefig or args.out
            if outname:
                if not _os.path.splitext(outname)[1]:
                    outname += '.svg'
                # Transparent background for SVG exports
                _, _ext = _os.path.splitext(outname)
                if _ext.lower() == '.svg':
                    # Fix for Affinity Designer/Photo compatibility issues
                    # Use 'none' to embed fonts as text (not paths) - prevents phantom labels
                    # Set hashsalt to empty to avoid duplicate text elements
                    _plt.rcParams['svg.fonttype'] = 'none'
                    _plt.rcParams['svg.hashsalt'] = None
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
                        fig.savefig(outname, dpi=300, transparent=True, facecolor='none', edgecolor='none')
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
                    fig.savefig(outname, dpi=300)
                print(f"GC plot saved to {outname} ({x_label_gc})")

            # Show plot / interactive menu
            if args.interactive:
                # Guard against non-interactive backends (e.g., Agg)
                try:
                    _backend = _plt.get_backend()
                except Exception:
                    _backend = "unknown"
                # TkAgg, QtAgg, Qt5Agg, WXAgg, MacOSX etc. are interactive
                _interactive_backends = {"tkagg", "qt5agg", "qt4agg", "qtagg", "wxagg", "macosx", "gtk3agg", "gtk4agg", "wx", "qt", "gtk", "gtk3", "gtk4"}
                _is_noninteractive = isinstance(_backend, str) and (_backend.lower() not in _interactive_backends) and ("agg" in _backend.lower() or _backend.lower() in {"pdf","ps","svg","template"})
                if _is_noninteractive:
                    print(f"Matplotlib backend '{_backend}' is non-interactive; a window cannot be shown.")
                    print("Tips: unset MPLBACKEND or set a GUI backend, e.g. on macOS:")
                    print("  export MPLBACKEND=MacOSX   # built-in macOS backend")
                    print("  export MPLBACKEND=TkAgg    # if Tk is available")
                    print("  export MPLBACKEND=QtAgg    # if PyQt is installed")
                    print("Or run without --interactive and use --out to save the figure.")
                else:
                    # Turn on interactive mode and show non-blocking window
                    try:
                        _plt.ion()
                    except Exception:
                        pass
                    _plt.show(block=False)
                    try:
                        electrochem_interactive_menu(fig, ax, cycle_lines)
                    except Exception as _ie:
                        print(f"Interactive menu failed: {_ie}")
                    # Keep window open after menu
                    _plt.show()
            else:
                if not (args.savefig or args.out):
                    # Only show when a GUI backend is available
                    try:
                        _backend = _plt.get_backend()
                    except Exception:
                        _backend = "unknown"
                    # TkAgg, QtAgg, Qt5Agg, WXAgg, MacOSX etc. are interactive
                    _interactive_backends = {"tkagg", "qt5agg", "qt4agg", "qtagg", "wxagg", "macosx", "gtk3agg", "gtk4agg", "wx", "qt", "gtk", "gtk3", "gtk4"}
                    _is_noninteractive = isinstance(_backend, str) and (_backend.lower() not in _interactive_backends) and ("agg" in _backend.lower() or _backend.lower() in {"pdf","ps","svg","template"})
                    if not _is_noninteractive:
                        _plt.show()
                    else:
                        print(f"Matplotlib backend '{_backend}' is non-interactive; use --out to save the figure.")
            exit()
        except Exception as _e:
            print(f"GC plot failed: {_e}")
            exit(1)

    # Capacity-per-cycle (CPC) summary from CSV or .mpt with coulombic efficiency
    if getattr(args, 'cpc', False):
        import os as _os
        import numpy as _np

        if len(args.files) < 1:
            print("CPC mode: provide at least one file (.csv, .xlsx, or .mpt).")
            exit(1)
        
        # Process multiple files
        file_data = []  # List of dicts with file info and data
        # Use warm colors (reds/oranges) for capacity (charge/discharge)
        # Use cool colors (blues/cyans) for efficiency for clear visual distinction
        import matplotlib.cm as cm
        import matplotlib.colors as mcolors
        n_files = len(args.files)
        
        # Warm colors for capacity: red to orange spectrum
        warm_cmap = cm.get_cmap('YlOrRd', n_files + 2)  # +2 to skip very light yellows
        # Cool colors for efficiency: blue to cyan spectrum  
        cool_cmap = cm.get_cmap('cool', n_files)
        
        # Generate colors from colormaps, skip lightest colors for capacity
        capacity_colors = [mcolors.rgb2hex(warm_cmap(i + 2)[:3]) for i in range(n_files)]
        efficiency_colors = [mcolors.rgb2hex(cool_cmap(i)[:3]) for i in range(n_files)]
        
        for file_idx, ec_file in enumerate(args.files):
            if not _os.path.isfile(ec_file):
                print(f"File not found: {ec_file}")
                continue

            ext = _os.path.splitext(ec_file)[1].lower()
            file_basename = _os.path.basename(ec_file)
            
            try:
                if ext in ['.csv', '.xlsx', '.xls']:
                    cap_x, voltage, cycles, chg_mask, dchg_mask = read_ec_csv_file(ec_file, prefer_specific=True)
                    cyc = _np.array(cycles, dtype=int)
                    unique_cycles = _np.unique(cyc)
                    unique_cycles = unique_cycles[_np.isfinite(unique_cycles)]
                    unique_cycles = [int(x) for x in unique_cycles]
                    if not unique_cycles:
                        unique_cycles = [1]
                    cyc_nums = []
                    cap_charge = []
                    cap_discharge = []
                    eff = []
                    for c in sorted(unique_cycles):
                        m_c = (cyc == c)
                        qchg = _np.nanmax(cap_x[m_c & chg_mask]) if _np.any(m_c & chg_mask) else _np.nan
                        qdch = _np.nanmax(cap_x[m_c & dchg_mask]) if _np.any(m_c & dchg_mask) else _np.nan
                        eta = (qdch / qchg * 100.0) if (_np.isfinite(qchg) and qchg > 0 and _np.isfinite(qdch)) else _np.nan
                        cyc_nums.append(c)
                        cap_charge.append(qchg)
                        cap_discharge.append(qdch)
                        eff.append(eta)
                    cyc_nums = _np.array(cyc_nums, dtype=float)
                    cap_charge = _np.array(cap_charge, dtype=float)
                    cap_discharge = _np.array(cap_discharge, dtype=float)
                    eff = _np.array(eff, dtype=float)
                elif ext == '.mpt':
                    mass_mg = getattr(args, 'mass', None)
                    if mass_mg is None:
                        print(f"Skipped {file_basename}: CPC mode (.mpt) requires --mass parameter.")
                        continue
                    cyc_nums, cap_charge, cap_discharge, eff = read_mpt_file(ec_file, mode='cpc', mass_mg=mass_mg)
                else:
                    print(f"Skipped {file_basename}: unsupported format (must be .csv, .xlsx, or .mpt)")
                    continue
                
                # Assign colors: distinct hue for each file
                capacity_color = capacity_colors[file_idx % len(capacity_colors)]
                efficiency_color = efficiency_colors[file_idx % len(efficiency_colors)]
                
                file_data.append({
                    'filename': file_basename,
                    'filepath': ec_file,
                    'cyc_nums': cyc_nums,
                    'cap_charge': cap_charge,
                    'cap_discharge': cap_discharge,
                    'eff': eff,
                    'color': capacity_color,
                    'eff_color': efficiency_color,
                    'visible': True
                })
                
            except Exception as e:
                print(f"Failed to read {file_basename}: {e}")
                continue
        
        if not file_data:
            print("No valid CPC data files to plot.")
            exit(1)

        # Plot (same figsize as GC)
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.set_xlabel('Cycle number', labelpad=8.0)
        ax.set_ylabel(r'Specific Capacity (mAh g$^{-1}$)', labelpad=8.0)
        ax.grid(True, alpha=0.25, linestyle='--', linewidth=0.8)

        ax2 = ax.twinx()
        ax2.set_ylabel('Efficiency (%)', labelpad=8.0)
        
        # Create scatter plots for each file
        for file_info in file_data:
            cyc_nums = file_info['cyc_nums']
            cap_charge = file_info['cap_charge']
            cap_discharge = file_info['cap_discharge']
            eff = file_info['eff']
            color = file_info['color']  # Warm color for capacity
            eff_color = file_info['eff_color']  # Cold color for efficiency
            label = file_info['filename']
            
            # For single file, use simple labels; for multiple files, prefix with filename
            if len(file_data) == 1:
                label_chg = 'Charge capacity'
                label_dch = 'Discharge capacity'
                label_eff = 'Coulombic efficiency'
            else:
                label_chg = f'{label} (Chg)'
                label_dch = f'{label} (Dch)'
                label_eff = f'{label} (Eff)'
            
            # Use slightly different shades for charge/discharge from same file
            from matplotlib.colors import to_rgb, rgb_to_hsv, hsv_to_rgb
            rgb = to_rgb(color)
            # Discharge: shift hue slightly and reduce brightness for clear distinction
            hsv = rgb_to_hsv(rgb)
            h, s, v = hsv
            h_new = (h - 0.05) % 1.0  # Shift hue slightly (more red/brown)
            v_new = max(0.3, v * 0.75)  # Darker but not too dark
            discharge_color = hsv_to_rgb([h_new, s, v_new])
            
            sc_charge = ax.scatter(cyc_nums, cap_charge, color=color, label=label_chg, 
                                  s=32, zorder=3, alpha=0.8, marker='o')
            sc_discharge = ax.scatter(cyc_nums, cap_discharge, color=discharge_color, label=label_dch, 
                                     s=32, zorder=3, alpha=0.8, marker='s')
            sc_eff = ax2.scatter(cyc_nums, eff, color=eff_color, marker='^', label=label_eff, 
                               s=40, alpha=0.7, zorder=3)
            
            # Store scatter artists in file_info for interactive menu
            file_info['sc_charge'] = sc_charge
            file_info['sc_discharge'] = sc_discharge
            file_info['sc_eff'] = sc_eff

        # Set efficiency y-range to 0-120 by default
        ax2.set_ylim(0, 120)

        # Compose a combined legend
        try:
            h1, l1 = ax.get_legend_handles_labels()
            h2, l2 = ax2.get_legend_handles_labels()
            ax.legend(h1 + h2, l1 + l2, loc='best', borderaxespad=1.0)
        except Exception:
            pass

        # Adjust layout to ensure top and bottom labels/titles are visible
        fig.subplots_adjust(left=0.12, right=0.88, top=0.88, bottom=0.15)
    
        if args.interactive and cpc_interactive_menu is not None:
            # Guard against non-interactive backends (e.g., Agg)
            try:
                _backend = plt.get_backend()
            except Exception:
                _backend = "unknown"
            # TkAgg, QtAgg, Qt5Agg, WXAgg, MacOSX etc. are interactive
            _interactive_backends = {"tkagg", "qt5agg", "qt4agg", "qtagg", "wxagg", "macosx", "gtk3agg", "gtk4agg", "wx", "qt", "gtk", "gtk3", "gtk4"}
            _is_noninteractive = isinstance(_backend, str) and (_backend.lower() not in _interactive_backends) and ("agg" in _backend.lower() or _backend.lower() in {"pdf","ps","svg","template"})
            if _is_noninteractive:
                print(f"Matplotlib backend '{_backend}' is non-interactive; a window cannot be shown.")
                print("Tips: unset MPLBACKEND or set a GUI backend, e.g. on macOS:")
                print("  export MPLBACKEND=MacOSX   # built-in macOS backend")
                print("  export MPLBACKEND=TkAgg    # if Tk is available")
                print("  export MPLBACKEND=QtAgg    # if PyQt is installed")
                print("Or run without --interactive and use --out to save the figure.")
            else:
                try:
                    plt.ion()
                except Exception:
                    pass
                plt.show(block=False)
                try:
                    # Pass file_data for multi-file support, but keep backward compatibility
                    if len(file_data) == 1:
                        # Single file: use original signature
                        cpc_interactive_menu(fig, ax, ax2, 
                                           file_data[0]['sc_charge'], 
                                           file_data[0]['sc_discharge'], 
                                           file_data[0]['sc_eff'])
                    else:
                        # Multiple files: pass file_data list
                        cpc_interactive_menu(fig, ax, ax2, 
                                           file_data[0]['sc_charge'], 
                                           file_data[0]['sc_discharge'], 
                                           file_data[0]['sc_eff'],
                                           file_data=file_data)
                except Exception as _ie:
                    print(f"CPC interactive menu failed: {_ie}")
                # Keep window open after menu
                plt.show()
        else:
            if not (args.savefig or args.out):
                try:
                    _backend = plt.get_backend()
                except Exception:
                    _backend = "unknown"
                # TkAgg, QtAgg, Qt5Agg, WXAgg, MacOSX etc. are interactive
                _interactive_backends = {"tkagg", "qt5agg", "qt4agg", "qtagg", "wxagg", "macosx", "gtk3agg", "gtk4agg", "wx", "qt", "gtk", "gtk3", "gtk4"}
                _is_noninteractive = isinstance(_backend, str) and (_backend.lower() not in _interactive_backends) and ("agg" in _backend.lower() or _backend.lower() in {"pdf","ps","svg","template"})
                if not _is_noninteractive:
                    plt.show()
                else:
                    print(f"Matplotlib backend '{_backend}' is non-interactive; use --out to save the figure.")
        exit(0)

    # dQ/dV plotting mode for supported .csv electrochemistry exports
    if getattr(args, 'dqdv', False):
        import os as _os
        import matplotlib.pyplot as _plt

        if len(args.files) != 1:
            print("dQ/dV mode: provide exactly one .csv file.")
            exit(1)

        ec_file = args.files[0]
        if not _os.path.isfile(ec_file):
            print(f"File not found: {ec_file}")
            exit(1)
        if not ec_file.lower().endswith('.csv'):
            print("dQ/dV mode: file must be a supported cycler .csv export.")
            exit(1)

        try:
            # Load voltage, dQ/dV, cycles, and charge/discharge masks
            voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = read_ec_csv_dqdv_file(ec_file, prefer_specific=True)

            # Create the plot
            fig, ax = _plt.subplots(figsize=(10, 6))

            # Helpers to split into contiguous index blocks and join with NaNs for single Line2D per role
            def _contiguous_blocks(mask):
                inds = np.where(mask)[0]
                if inds.size == 0:
                    return []
                blocks = []
                start = inds[0]
                prev = inds[0]
                for j in inds[1:]:
                    if j == prev + 1:
                        prev = j
                    else:
                        blocks.append((start, prev))
                        start = j
                        prev = j
                blocks.append((start, prev))
                return blocks

            def _broken_arrays_from_indices(idx: np.ndarray, x: np.ndarray, y: np.ndarray):
                if idx.size == 0:
                    return np.array([]), np.array([])
                parts_x = []
                parts_y = []
                start = 0
                for k in range(1, idx.size):
                    if idx[k] != idx[k-1] + 1:
                        parts_x.append(x[idx[start:k]])
                        parts_y.append(y[idx[start:k]])
                        start = k
                parts_x.append(x[idx[start:]])
                parts_y.append(y[idx[start:]])
                X = []
                Y = []
                for i, (px, py) in enumerate(zip(parts_x, parts_y)):
                    if i > 0:
                        X.append(np.array([np.nan]))
                        Y.append(np.array([np.nan]))
                    X.append(px)
                    Y.append(py)
                return np.concatenate(X) if X else np.array([]), np.concatenate(Y) if Y else np.array([])

            # Normalize cycle indices to start at 1
            # Find the first cycle with at least 2 data points (needed for plotting)
            cyc_int_raw = np.array(np.rint(cycles), dtype=int)
            if cyc_int_raw.size:
                unique_cycles_raw = np.unique(cyc_int_raw)
                valid_min_c = None
                for c in sorted(unique_cycles_raw):
                    if np.sum(cyc_int_raw == c) >= 2:
                        valid_min_c = int(c)
                        break
                
                if valid_min_c is not None:
                    shift = 1 - valid_min_c
                else:
                    min_c = int(np.min(cyc_int_raw))
                    shift = 1 - min_c if min_c <= 0 else 0
            else:
                shift = 0
            cyc_int = cyc_int_raw + shift
            cycles_present = sorted(int(c) for c in np.unique(cyc_int)) if cyc_int.size else [1]

            # Color palette
            base_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                           '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

            # Build mapping cycle -> {'charge': line or None, 'discharge': line or None}
            cycle_lines = {}
            for cyc in cycles_present:
                # Charge
                mask_c = (cyc_int == cyc) & charge_mask
                idx_c = np.where(mask_c)[0]
                if idx_c.size >= 2:
                    x_b, y_b = _broken_arrays_from_indices(idx_c, voltage, dqdv)
                    ln_c, = ax.plot(x_b, y_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                    linewidth=2.0, label=str(cyc), alpha=0.8)
                else:
                    ln_c = None
                # Discharge
                mask_d = (cyc_int == cyc) & discharge_mask
                idx_d = np.where(mask_d)[0]
                if idx_d.size >= 2:
                    xd_b, yd_b = _broken_arrays_from_indices(idx_d, voltage, dqdv)
                    lbl = '_nolegend_' if ln_c is not None else str(cyc)
                    ln_d, = ax.plot(xd_b, yd_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                    linewidth=2.0, label=lbl, alpha=0.8)
                else:
                    ln_d = None
                cycle_lines[cyc] = {"charge": ln_c, "discharge": ln_d}

            # Labels with consistent labelpad (same as GC/CPC)
            ax.set_xlabel('Voltage (V)', labelpad=8.0)
            ax.set_ylabel(y_label, labelpad=8.0)
            legend = ax.legend(title='Cycle')
            legend.get_title().set_fontsize('medium')
            # No background grid by default (same as GC)
        
            # Adjust layout to ensure top and bottom labels/titles are visible (same as GC/CPC)
            fig.subplots_adjust(left=0.12, right=0.95, top=0.88, bottom=0.15)

            # Save if requested
            outname = args.savefig or args.out
            if outname:
                if not _os.path.splitext(outname)[1]:
                    outname += '.svg'
                _, _ext = _os.path.splitext(outname)
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
                        fig.savefig(outname, dpi=300, transparent=True, facecolor='none', edgecolor='none')
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
                    fig.savefig(outname, dpi=300)
                print(f"dQ/dV plot saved to {outname} ({y_label})")

            # Show / interactive
            if args.interactive:
                try:
                    _backend = _plt.get_backend()
                except Exception:
                    _backend = "unknown"
                # TkAgg, QtAgg, Qt5Agg, WXAgg, MacOSX etc. are interactive
                _interactive_backends = {"tkagg", "qt5agg", "qt4agg", "qtagg", "wxagg", "macosx", "gtk3agg", "gtk4agg", "wx", "qt", "gtk", "gtk3", "gtk4"}
                _is_noninteractive = isinstance(_backend, str) and (_backend.lower() not in _interactive_backends) and ("agg" in _backend.lower() or _backend.lower() in {"pdf","ps","svg","template"})
                if _is_noninteractive:
                    print(f"Matplotlib backend '{_backend}' is non-interactive; a window cannot be shown.")
                    print("Tips: unset MPLBACKEND or set a GUI backend, e.g. on macOS:")
                    print("  export MPLBACKEND=MacOSX   # built-in macOS backend")
                    print("  export MPLBACKEND=TkAgg    # if Tk is available")
                    print("  export MPLBACKEND=QtAgg    # if PyQt is installed")
                    print("Or run without --interactive and use --out to save the figure.")
                else:
                    try:
                        _plt.ion()
                    except Exception:
                        pass
                    _plt.show(block=False)
                    try:
                        electrochem_interactive_menu(fig, ax, cycle_lines)
                    except Exception as _ie:
                        print(f"Interactive menu failed: {_ie}")
                    _plt.show()
            else:
                if not (args.savefig or args.out):
                    try:
                        _backend = _plt.get_backend()
                    except Exception:
                        _backend = "unknown"
                    # TkAgg, QtAgg, Qt5Agg, WXAgg, MacOSX etc. are interactive
                    _interactive_backends = {"tkagg", "qt5agg", "qt4agg", "qtagg", "wxagg", "macosx", "gtk3agg", "gtk4agg", "wx", "qt", "gtk", "gtk3", "gtk4"}
                    _is_noninteractive = isinstance(_backend, str) and (_backend.lower() not in _interactive_backends) and ("agg" in _backend.lower() or _backend.lower() in {"pdf","ps","svg","template"})
                    if not _is_noninteractive:
                        _plt.show()
                    else:
                        print(f"Matplotlib backend '{_backend}' is non-interactive; use --out to save the figure.")
            exit()

        except Exception as _e:
            print(f"dQ/dV plot failed: {_e}")
            exit(1)

    # Operando contour plotting mode (folder-based)
    if getattr(args, 'operando', False):
        import os as _os
        import matplotlib.pyplot as _plt
        try:
            # Determine target folder: explicit folder arg or current directory
            if len(args.files) == 0:
                folder = os.getcwd()
            elif len(args.files) == 1 and _os.path.isdir(args.files[0]):
                folder = _os.path.abspath(args.files[0])
            elif len(args.files) == 1 and not _os.path.isdir(args.files[0]):
                print("Operando mode expects a folder (or no argument to use current folder).")
                exit(1)
            else:
                print("Operando mode: provide at most one folder or no argument.")
                exit(1)

            # Build plot
            fig, ax, meta = plot_operando_folder(folder, args)
            im = meta.get('imshow')
            cbar = meta.get('colorbar')
            has_ec = bool(meta.get('has_ec'))
            ec_ax = meta.get('ec_ax') if has_ec else None

            # Save if requested
            outname = args.savefig or args.out
            if outname:
                if not _os.path.splitext(outname)[1]:
                    outname += '.svg'
                _, _ext = _os.path.splitext(outname)
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
                        if ec_ax is not None and getattr(ec_ax, 'patch', None) is not None:
                            ec_ax.patch.set_alpha(0.0); ec_ax.patch.set_facecolor('none')
                    except Exception:
                        pass
                    try:
                        fig.savefig(outname, dpi=300, transparent=True, facecolor='none', edgecolor='none')
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
                    fig.savefig(outname, dpi=300)
                print(f"Operando plot saved to {outname}")

            # Interactive or show
            if args.interactive:
                try:
                    _backend = _plt.get_backend()
                except Exception:
                    _backend = "unknown"
                # TkAgg, QtAgg, Qt5Agg, WXAgg, MacOSX etc. are interactive
                _interactive_backends = {"tkagg", "qt5agg", "qt4agg", "qtagg", "wxagg", "macosx", "gtk3agg", "gtk4agg", "wx", "qt", "gtk", "gtk3", "gtk4"}
                _is_noninteractive = isinstance(_backend, str) and (_backend.lower() not in _interactive_backends) and ("agg" in _backend.lower() or _backend.lower() in {"pdf","ps","svg","template"})
                if _is_noninteractive:
                    print(f"Matplotlib backend '{_backend}' is non-interactive; a window cannot be shown.")
                    print("Tips: unset MPLBACKEND or set a GUI backend")
                    print("Or run without --interactive and use --out to save the figure.")
                else:
                    try:
                        _plt.ion()
                    except Exception:
                        pass
                    try:
                        _plt.show(block=False)
                    except Exception:
                        pass
                    try:
                        # Call interactive menu regardless of EC presence
                        # When ec_ax is None, EC-related commands will be disabled
                        if operando_ec_interactive_menu is not None:
                            operando_ec_interactive_menu(fig, ax, im, cbar, ec_ax)
                        else:
                            print("Interactive menu not available.")
                    except Exception as _ie:
                        print(f"Interactive menu failed: {_ie}")
                    _plt.show()
            else:
                if not (args.savefig or args.out):
                    try:
                        _backend = _plt.get_backend()
                    except Exception:
                        _backend = "unknown"
                    # TkAgg, QtAgg, Qt5Agg, WXAgg, MacOSX etc. are interactive
                    _interactive_backends = {"tkagg", "qt5agg", "qt4agg", "qtagg", "wxagg", "macosx", "gtk3agg", "gtk4agg", "wx", "qt", "gtk", "gtk3", "gtk4"}
                    _is_noninteractive = isinstance(_backend, str) and (_backend.lower() not in _interactive_backends) and ("agg" in _backend.lower() or _backend.lower() in {"pdf","ps","svg","template"})
                    if not _is_noninteractive:
                        _plt.show()
                    else:
                        print(f"Matplotlib backend '{_backend}' is non-interactive; use --out to save the figure.")
            exit()
        except Exception as _e:
            print(f"Operando plot failed: {_e}")
            exit(1)

    if len(args.files) == 1:
        sole = args.files[0]
        if sole.lower() == 'all':
            batch_process(os.getcwd(), args)
            exit()
        elif sole.lower() == 'allfiles':
            # Plot all XY files in current directory on the same figure (including arbitrary extensions)
            known_ext = {'.xye', '.xy', '.qye', '.dat', '.csv', '.gr', '.nor', '.chik', '.chir', '.txt'}
            excluded_ext = {'.cif', '.pkl', '.py', '.md', '.json', '.yml', '.yaml', '.sh', '.bat'}
            all_xy_files = []
            unknown_ext_files = []
            
            for f in sorted(os.listdir(os.getcwd()), key=_natural_sort_key):
                if not os.path.isfile(os.path.join(os.getcwd(), f)):
                    continue
                ext = os.path.splitext(f)[1].lower()
                # Skip excluded extensions
                if ext in excluded_ext or not ext:
                    continue
                # Include known extensions
                if ext in known_ext:
                    all_xy_files.append(f)
                else:
                    # Include unknown extensions (will be treated as 2-column data)
                    all_xy_files.append(f)
                    unknown_ext_files.append(f)
            
            if not all_xy_files:
                print("No data files found in current directory.")
                exit(1)
            
            if unknown_ext_files:
                print(f"Warning: Found {len(unknown_ext_files)} file(s) with unknown extension(s):")
                for uf in unknown_ext_files[:5]:  # Show first 5
                    print(f"  - {uf}")
                if len(unknown_ext_files) > 5:
                    print(f"  ... and {len(unknown_ext_files) - 5} more")
                print("These will be read as 2-column (x, y) data.")
                if not args.xaxis:
                    print("Tip: Use --xaxis to specify the x-axis type (e.g., --xaxis 2theta, --xaxis Q, --xaxis r)")
            
            print(f"Found {len(all_xy_files)} files to plot together")
            args.files = all_xy_files
            # Continue to normal plotting mode with all files
        elif os.path.isdir(sole):
            batch_process(os.path.abspath(sole), args)
            exit()

    # --- XY Batch Mode: check for --all flag for XY files ---
    # Handle --all flag for XY batch processing (consistent with EC batch mode)
    if not ec_mode_active and getattr(args, 'all', None) is not None:
        batch_process(os.getcwd(), args)
        exit()
    
    # ---------------- Normal (multi-file) path continues below ----------------
    # Apply conditional default for delta (normal mode only)
    if args.delta is None:
        args.delta = 0.1 if args.stack else 0.0

    # ---------------- Automatic session (.pkl) load shortcut ----------------
    # If user invokes: batplot session.pkl [--interactive]
    if len(args.files) == 1 and args.files[0].lower().endswith('.pkl'):
        sess_path = args.files[0]
        if not os.path.isfile(sess_path):
            print(f"Session file not found: {sess_path}")
            exit(1)
        try:
            with open(sess_path, 'rb') as f:
                sess = pickle.load(f)
            if not isinstance(sess, dict) or 'version' not in sess:
                print("Not a valid batplot session file.")
                exit(1)
        except Exception as e:
            print(f"Failed to load session: {e}")
            exit(1)
        # If it's an EC GC session, load and open EC interactive menu directly
        if isinstance(sess, dict) and sess.get('kind') == 'ec_gc':
            try:
                import matplotlib.pyplot as _plt
                res = load_ec_session(sess_path)
                if not res:
                    print("Failed to load EC session.")
                    exit(1)
                fig, ax, cycle_lines = res
                try:
                    _plt.ion()
                except Exception:
                    pass
                try:
                    _plt.show(block=False)
                except Exception:
                    pass
                try:
                    electrochem_interactive_menu(fig, ax, cycle_lines)
                except Exception as _ie:
                    print(f"Interactive menu failed: {_ie}")
                _plt.show()
                exit()
            except Exception as e:
                print(f"EC session load failed: {e}")
                exit(1)
        # If it's an operando+EC session, load and open the combined interactive menu
        if isinstance(sess, dict) and sess.get('kind') == 'operando_ec':
            try:
                import matplotlib.pyplot as _plt
                res = load_operando_session(sess_path)
                if not res:
                    print("Failed to load operando+EC session.")
                    exit(1)
                fig2, ax2, im2, cbar2, ec_ax2 = res
                # Always open interactive menu for session files
                try:
                    _plt.ion()
                except Exception:
                    pass
                try:
                    _plt.show(block=False)
                except Exception:
                    pass
                try:
                    if operando_ec_interactive_menu is not None:
                        operando_ec_interactive_menu(fig2, ax2, im2, cbar2, ec_ax2)
                except Exception as _ie:
                    print(f"Interactive menu failed: {_ie}")
                _plt.show()
                exit()
            except Exception as e:
                print(f"Operando+EC session load failed: {e}")
                exit(1)

        # If it's a CPC session, load and open CPC interactive menu
        if isinstance(sess, dict) and sess.get('kind') == 'cpc':
            try:
                import matplotlib.pyplot as _plt
                res = load_cpc_session(sess_path)
                if not res:
                    print("Failed to load CPC session.")
                    exit(1)
                fig_c, ax_c, ax2_c, sc_c, sc_d, sc_e = res
                try:
                    _plt.ion()
                except Exception:
                    pass
                try:
                    _plt.show(block=False)
                except Exception:
                    pass
                try:
                    if cpc_interactive_menu is not None:
                        cpc_interactive_menu(fig_c, ax_c, ax2_c, sc_c, sc_d, sc_e)
                except Exception as _ie:
                    print(f"CPC interactive menu failed: {_ie}")
                _plt.show()
                exit()
            except Exception as e:
                print(f"CPC session load failed: {e}")
                exit(1)

        # Reconstruct minimal state and go to interactive if requested
        plt.ion() if args.interactive else None
        fig, ax = plt.subplots(figsize=(8,6))
        y_data_list = []
        x_data_list = []
        labels_list = []
        orig_y = []
        label_text_objects = []
        x_full_list = []
        raw_y_full_list = []
        offsets_list = []
        tick_state = {
            'bx': True,'tx': False,'ly': True,'ry': False,
            'mbx': False,'mtx': False,'mly': False,'mry': False
        }
        saved_stack = bool(sess.get('args_subset', {}).get('stack', False))
        # Pull data
        # --- Robust reconstruction of stored curves ---
        x_loaded = sess.get('x_data', [])
        y_loaded = sess.get('y_data', [])  # stored plotted (baseline+offset) values
        orig_loaded = sess.get('orig_y', [])  # stored baseline (normalized/raw w/out offsets)
        offsets_saved = sess.get('offsets', [])
        n_curves = len(x_loaded)
        for i in range(n_curves):
            x_arr = np.array(x_loaded[i])
            off = offsets_saved[i] if i < len(offsets_saved) else 0.0
            if orig_loaded and i < len(orig_loaded):
                base = np.array(orig_loaded[i])
            else:
                # Fallback: derive baseline by subtracting offset from stored y (handles legacy sessions)
                y_arr_full = np.array(y_loaded[i]) if i < len(y_loaded) else np.array([])
                base = y_arr_full - off
            y_plot = base + off
            x_data_list.append(x_arr)
            orig_y.append(base)
            y_data_list.append(y_plot)
            ax.plot(x_arr, y_plot, lw=1)
            x_full_list.append(x_arr.copy())
            raw_y_full_list.append(base.copy())
        offsets_list[:] = offsets_saved if offsets_saved else [0.0]*n_curves
        # Apply stored line styles (if any)
        try:
            stored_styles = sess.get('line_styles', [])
            for ln, st in zip(ax.lines, stored_styles):
                if 'color' in st: ln.set_color(st['color'])
                if 'linewidth' in st: ln.set_linewidth(st['linewidth'])
                if 'linestyle' in st:
                    try: ln.set_linestyle(st['linestyle'])
                    except Exception: pass
                if 'alpha' in st and st['alpha'] is not None: ln.set_alpha(st['alpha'])
                if 'marker' in st and st['marker'] is not None:
                    try: ln.set_marker(st['marker'])
                    except Exception: pass
                if 'markersize' in st and st['markersize'] is not None:
                    try: ln.set_markersize(st['markersize'])
                    except Exception: pass
                if 'markerfacecolor' in st and st['markerfacecolor'] is not None:
                    try: ln.set_markerfacecolor(st['markerfacecolor'])
                    except Exception: pass
                if 'markeredgecolor' in st and st['markeredgecolor'] is not None:
                    try: ln.set_markeredgecolor(st['markeredgecolor'])
                    except Exception: pass
        except Exception:
            pass
        labels_list[:] = sess.get('labels', [f"Curve {i+1}" for i in range(len(y_data_list))])
        delta = sess.get('delta', 0.0)
        ax.set_xlabel(sess.get('axis', {}).get('xlabel', 'X'))
        ax.set_ylabel(sess.get('axis', {}).get('ylabel', 'Intensity'))
        
        # Restore normalization ranges (if saved)
        axis_cfg = sess.get('axis', {})
        if 'norm_xlim' in axis_cfg and axis_cfg['norm_xlim'] is not None:
            ax._norm_xlim = tuple(axis_cfg['norm_xlim'])
        if 'norm_ylim' in axis_cfg and axis_cfg['norm_ylim'] is not None:
            ax._norm_ylim = tuple(axis_cfg['norm_ylim'])
        
        # Restore display limits
        if 'xlim' in axis_cfg:
            ax.set_xlim(*axis_cfg['xlim'])
        if 'ylim' in axis_cfg:
            ax.set_ylim(*axis_cfg['ylim'])
        # Apply figure size & dpi if stored
        fig_cfg = sess.get('figure', {})
        try:
            if fig_cfg.get('size') and isinstance(fig_cfg['size'], (list, tuple)) and len(fig_cfg['size']) == 2:
                fw, fh = fig_cfg['size']
                if not globals().get('keep_canvas_fixed', True):
                    fig.set_size_inches(float(fw), float(fh), forward=True)
                else:
                    # Keep canvas size as current; avoid surprising resize on load
                    pass
            # Don't restore saved DPI - use system default to avoid display-dependent issues
            # (Retina displays, Windows scaling, etc. can cause saved DPI to differ)
            # Keeping figure size in inches ensures consistent appearance across platforms
        except Exception:
            pass
        # Restore spines (linewidth, color, visibility) and subplot margins/tick widths (for CLI .pkl load)
        try:
            spine_specs = fig_cfg.get('spines', {})
            if spine_specs:
                for name, spec in spine_specs.items():
                    spn = ax.spines.get(name)
                    if not spn: continue
                    if 'linewidth' in spec: spn.set_linewidth(spec['linewidth'])
                    if 'color' in spec and spec['color'] is not None: spn.set_edgecolor(spec['color'])
                    if 'visible' in spec: spn.set_visible(bool(spec['visible']))
            else:
                # legacy fallback
                legacy_vis = fig_cfg.get('spine_vis', {})
                for name, vis in legacy_vis.items():
                    spn = ax.spines.get(name)
                    if spn:
                        spn.set_visible(bool(vis))
            spm = fig_cfg.get('subplot_margins')
            if spm and all(k in spm for k in ('left','right','bottom','top')):
                fig.subplots_adjust(left=spm['left'], right=spm['right'], bottom=spm['bottom'], top=spm['top'])
            
            # Restore exact frame size if stored (for precision)
            frame_size = fig_cfg.get('frame_size')
            if frame_size and isinstance(frame_size, (list, tuple)) and len(frame_size) == 2:
                target_w_in, target_h_in = map(float, frame_size)
                # Get current canvas size
                canvas_w_in, canvas_h_in = fig.get_size_inches()
                # Calculate needed fractions to achieve exact frame size
                if canvas_w_in > 0 and canvas_h_in > 0:
                    # Get current position to preserve centering
                    bbox = ax.get_position()
                    center_x = (bbox.x0 + bbox.x1) / 2.0
                    center_y = (bbox.y0 + bbox.y1) / 2.0
                    # Calculate new fractions
                    new_w_frac = target_w_in / canvas_w_in
                    new_h_frac = target_h_in / canvas_h_in
                    # Reposition to maintain centering
                    new_left = center_x - new_w_frac / 2.0
                    new_right = center_x + new_w_frac / 2.0
                    new_bottom = center_y - new_h_frac / 2.0
                    new_top = center_y + new_h_frac / 2.0
                    # Apply
                    fig.subplots_adjust(left=new_left, right=new_right, bottom=new_bottom, top=new_top)
        except Exception:
            pass
        # Font
        font_cfg = sess.get('font', {})
        if font_cfg.get('chain'):
            plt.rcParams['font.family'] = 'sans-serif'
            plt.rcParams['font.sans-serif'] = font_cfg['chain']
        if font_cfg.get('size'):
            plt.rcParams['font.size'] = font_cfg['size']
        # Tick state restore
        saved_tick = sess.get('tick_state', {})
        for k,v in saved_tick.items():
            if k in tick_state: tick_state[k] = v
        # Persist on axes for interactive menu initialization
        try:
            ax._saved_tick_state = dict(tick_state)
        except Exception:
            pass
        # Tick widths restore
        try:
            tw = sess.get('tick_widths', {})
            if tw.get('x_major') is not None:
                ax.tick_params(axis='x', which='major', width=float(tw['x_major']))
            if tw.get('x_minor') is not None:
                ax.tick_params(axis='x', which='minor', width=float(tw['x_minor']))
            if tw.get('y_major') is not None:
                ax.tick_params(axis='y', which='major', width=float(tw['y_major']))
            if tw.get('y_minor') is not None:
                ax.tick_params(axis='y', which='minor', width=float(tw['y_minor']))
        except Exception:
            pass
        # Tick lengths restore
        try:
            tl = sess.get('tick_lengths', {})
            if tl.get('x_major') is not None or tl.get('y_major') is not None:
                major_len = tl.get('x_major') or tl.get('y_major')
                ax.tick_params(axis='both', which='major', length=major_len)
                if not hasattr(fig, '_tick_lengths'):
                    fig._tick_lengths = {}
                fig._tick_lengths['major'] = major_len
            if tl.get('x_minor') is not None or tl.get('y_minor') is not None:
                minor_len = tl.get('x_minor') or tl.get('y_minor')
                ax.tick_params(axis='both', which='minor', length=minor_len)
                if not hasattr(fig, '_tick_lengths'):
                    fig._tick_lengths = {}
                fig._tick_lengths['minor'] = minor_len
        except Exception:
            pass
        
        # Restore WASD state (spine, ticks, labels, title visibility for all 4 sides)
        try:
            wasd = sess.get('wasd_state', {})
            if wasd:
                # Store the xlabel/ylabel before applying WASD (to restore hidden titles later if needed)
                stored_xlabel = ax.get_xlabel()
                stored_ylabel = ax.get_ylabel()
                
                # Apply spine visibility
                for side in ('top', 'bottom', 'left', 'right'):
                    state = wasd.get(side, {})
                    sp = ax.spines.get(side)
                    if sp and 'spine' in state:
                        sp.set_visible(bool(state['spine']))
                
                # Apply tick and label visibility
                for side in ('top', 'bottom', 'left', 'right'):
                    state = wasd.get(side, {})
                    if side in ('top', 'bottom'):
                        # X-axis ticks
                        tick_key = 'tick1On' if side == 'top' else 'tick2On'
                        label_key = 'label1On' if side == 'top' else 'label2On'
                        if 'ticks' in state:
                            ax.tick_params(axis='x', which='major', **{tick_key: bool(state['ticks'])})
                        if 'labels' in state:
                            ax.tick_params(axis='x', which='major', **{label_key: bool(state['labels'])})
                        if 'minor' in state:
                            ax.tick_params(axis='x', which='minor', **{tick_key: bool(state['minor'])})
                    else:
                        # Y-axis ticks
                        tick_key = 'tick1On' if side == 'left' else 'tick2On'
                        label_key = 'label1On' if side == 'left' else 'label2On'
                        if 'ticks' in state:
                            ax.tick_params(axis='y', which='major', **{tick_key: bool(state['ticks'])})
                        if 'labels' in state:
                            ax.tick_params(axis='y', which='major', **{label_key: bool(state['labels'])})
                        if 'minor' in state:
                            ax.tick_params(axis='y', which='minor', **{tick_key: bool(state['minor'])})
                
                # Apply title visibility - CRITICAL: Check title state before restoring labels
                # Bottom xlabel
                bottom_title_on = wasd.get('bottom', {}).get('title', True)
                if bottom_title_on:
                    ax.set_xlabel(stored_xlabel)
                else:
                    ax.set_xlabel('')  # Hidden by user via s5
                    # Store the hidden label for later restoration
                    if stored_xlabel:
                        setattr(ax, '_stored_xlabel', stored_xlabel)
                
                # Left ylabel  
                left_title_on = wasd.get('left', {}).get('title', True)
                if left_title_on:
                    ax.set_ylabel(stored_ylabel)
                else:
                    ax.set_ylabel('')  # Hidden by user via a5
                    # Store the hidden label for later restoration
                    if stored_ylabel:
                        setattr(ax, '_stored_ylabel', stored_ylabel)
                
                # Top xlabel (if exists)
                top_title_on = wasd.get('top', {}).get('title', False)
                setattr(ax, '_top_xlabel_on', top_title_on)
                
                # Right ylabel (if exists)
                right_title_on = wasd.get('right', {}).get('title', False)
                setattr(ax, '_right_ylabel_on', right_title_on)
        except Exception as e:
            # Don't fail session load if WASD restoration fails
            print(f"Warning: Could not fully restore WASD state: {e}")
        
        # Rebuild label texts
        for i, lab in enumerate(labels_list):
            txt = ax.text(1.0, 1.0, f"{i+1}: {lab}", ha='right', va='top', transform=ax.transAxes,
                          fontsize=plt.rcParams.get('font.size', 12))
            label_text_objects.append(txt)
        # Restore curve names visibility
        try:
            curve_names_visible = bool(sess.get('curve_names_visible', True))
            for txt in label_text_objects:
                txt.set_visible(curve_names_visible)
            fig._curve_names_visible = curve_names_visible
        except Exception:
            pass
        # Restore stack label position preference
        try:
            stack_label_at_bottom = bool(sess.get('stack_label_at_bottom', False))
            fig._stack_label_at_bottom = stack_label_at_bottom
        except Exception:
            pass
        # Restore grid state
        try:
            grid_state = bool(sess.get('grid', False))
            ax.grid(grid_state, color='0.85', linestyle='-', linewidth=0.5, alpha=0.7)
        except Exception:
            pass
        # CIF tick series (optional)
        cif_tick_series = sess.get('cif_tick_series') or []
        cif_hkl_map = {k: [tuple(v) for v in val] for k,val in sess.get('cif_hkl_map', {}).items()}
        cif_hkl_label_map = {k: dict(v) for k,v in sess.get('cif_hkl_label_map', {}).items()}
        cif_numbering_enabled = True
        cif_extend_suspended = False
        show_cif_hkl = sess.get('show_cif_hkl', False)
        show_cif_titles = sess.get('show_cif_titles', True)
        # Provide minimal stubs to satisfy interactive menu dependencies
        # Axis mode restoration informs downstream toggles (e.g., CIF conversions, crosshair availability)
        axis_mode_restored = sess.get('axis_mode', 'unknown')
        use_Q = axis_mode_restored == 'Q'
        use_r = axis_mode_restored == 'r'
        use_E = axis_mode_restored == 'energy'
        use_k = axis_mode_restored == 'k'
        use_rft = axis_mode_restored == 'rft'
        use_2th = axis_mode_restored == '2theta'
        x_label = ax.get_xlabel() or 'X'
        def update_tick_visibility_local():
            # Major ticks/labels
            ax.tick_params(axis='x', bottom=tick_state['bx'], top=tick_state['tx'], labelbottom=tick_state['bx'], labeltop=tick_state['tx'])
            ax.tick_params(axis='y', left=tick_state['ly'], right=tick_state['ry'], labelleft=tick_state['ly'], labelright=tick_state['ry'])
            # Minor ticks
            if tick_state.get('mbx') or tick_state.get('mtx'):
                ax.xaxis.set_minor_locator(AutoMinorLocator())
                ax.xaxis.set_minor_formatter(NullFormatter())
                ax.tick_params(axis='x', which='minor', bottom=tick_state.get('mbx', False), top=tick_state.get('mtx', False), labelbottom=False, labeltop=False)
            else:
                ax.tick_params(axis='x', which='minor', bottom=False, top=False, labelbottom=False, labeltop=False)
            if tick_state.get('mly') or tick_state.get('mry'):
                ax.yaxis.set_minor_locator(AutoMinorLocator())
                ax.yaxis.set_minor_formatter(NullFormatter())
                ax.tick_params(axis='y', which='minor', left=tick_state.get('mly', False), right=tick_state.get('mry', False), labelleft=False, labelright=False)
            else:
                ax.tick_params(axis='y', which='minor', left=False, right=False, labelleft=False, labelright=False)
        update_tick_visibility_local()
        # Ensure label positions correct
        stack_label_bottom = bool(sess.get('stack_label_at_bottom', False))
        update_labels(ax, y_data_list, label_text_objects, saved_stack, stack_label_bottom)
        if cif_tick_series:
            # Provide draw/extend helpers compatible with interactive menu using original placement logic
            def _session_q_to_2theta(peaksQ, wl):
                if wl is None:
                    return []
                out = []
                for q in peaksQ:
                    s = q*wl/(4*np.pi)
                    if 0 <= s < 1:
                        out.append(np.degrees(2*np.arcsin(s)))
                return out

            def _session_ensure_wavelength(default_wl=1.5406):
                # Prefer any stored wl, else args.wl, else provided default
                for _lab,_fname,_peaks,_wl,_qmax,_color in cif_tick_series:
                    if _wl is not None:
                        return _wl
                return getattr(args, 'wl', None) or default_wl

            def _session_cif_extend(xmax_domain):
                # Minimal extension: do nothing (could replicate original if needed)
                return

            def _session_cif_draw():
                if not cif_tick_series:
                    return
                try:
                    cur_ylim = ax.get_ylim(); yr = cur_ylim[1]-cur_ylim[0]
                    if yr <= 0: yr = 1.0
                    if saved_stack or len(y_data_list) > 1:
                        global_min = min(float(a.min()) for a in y_data_list if len(a)) if y_data_list else cur_ylim[0]
                        base = global_min - 0.08*yr; spacing = 0.05*yr
                    else:
                        global_min = min(float(a.min()) for a in y_data_list if len(a)) if y_data_list else 0.0
                        base = global_min - 0.06*yr; spacing = 0.04*yr
                    needed_min = base - (len(cif_tick_series)-1)*spacing - 0.04*yr
                    if needed_min < cur_ylim[0]:
                        ax.set_ylim(needed_min, cur_ylim[1]); cur_ylim = ax.get_ylim(); yr = cur_ylim[1]-cur_ylim[0]
                    # Clear previous artifacts
                    for art in getattr(ax, '_cif_tick_art', []):
                        try: art.remove()
                        except Exception: pass
                    new_art = []
                    show_hkl_local = bool(show_cif_hkl)
                    wl_any = _session_ensure_wavelength()
                    # Draw each series
                    for i,(lab,fname,peaksQ,wl,qmax_sim,color) in enumerate(cif_tick_series):
                        y_line = base - i*spacing
                        # Convert peaks to axis domain
                        if use_2th:
                            wl_use = wl if wl is not None else wl_any
                            domain_peaks = _session_q_to_2theta(peaksQ, wl_use)
                        else:
                            domain_peaks = peaksQ
                        # Clip to visible x-range
                        xlow,xhigh = ax.get_xlim()
                        domain_peaks = [p for p in domain_peaks if xlow <= p <= xhigh]
                        # Build hkl label map (keys are Q values, not 2θ)
                        label_map = cif_hkl_label_map.get(fname, {}) if show_hkl_local else {}
                        if show_hkl_local and len(domain_peaks) > 4000:
                            show_hkl_local = False  # safety
                        for p in domain_peaks:
                            ln, = ax.plot([p,p],[y_line, y_line+0.02*yr], color=color, lw=1.0, alpha=0.9, zorder=3)
                            new_art.append(ln)
                            if show_hkl_local:
                                # When axis is 2θ convert back to Q to look up hkl label
                                if use_2th and (wl or wl_any):
                                    theta = np.radians(p/2.0)
                                    Qp = 4*np.pi*np.sin(theta)/(wl if wl is not None else wl_any)
                                else:
                                    Qp = p
                                lbl = label_map.get(round(Qp,6))
                                if lbl:
                                    t_hkl = ax.text(p, y_line+0.022*yr, lbl, ha='center', va='bottom', fontsize=7, rotation=90, color=color)
                                    new_art.append(t_hkl)
                        # Removed numbering prefix; keep one leading space for padding from axis
                        label_text = f" {lab}"
                        txt = ax.text(ax.get_xlim()[0], y_line+0.005*yr, label_text,
                                      ha='left', va='bottom', fontsize=max(8,int(0.55*plt.rcParams.get('font.size',12))), color=color)
                        new_art.append(txt)
                    ax._cif_tick_art = new_art
                    fig.canvas.draw_idle()
                except Exception:
                    pass
            ax._cif_extend_func = _session_cif_extend
            ax._cif_draw_func = _session_cif_draw
            ax._cif_draw_func()

        # Restore axis title duplicates/visibility exactly as saved
        titles = sess.get('axis_titles', {})
        try:
            # Bottom X title
            if titles.get('has_bottom_x') is False:
                ax.set_xlabel("")
            # Left Y title
            if titles.get('has_left_y') is False:
                ax.set_ylabel("")
            # Top X duplicate
            if titles.get('top_x'):
                lbl_text = ax.get_xlabel()
                if lbl_text:
                    if not hasattr(ax,'_top_xlabel_artist') or ax._top_xlabel_artist is None:
                        ax._top_xlabel_artist = ax.text(0.5, 1.02, lbl_text, ha='center', va='bottom', transform=ax.transAxes)
                    else:
                        ax._top_xlabel_artist.set_text(lbl_text)
                        ax._top_xlabel_artist.set_visible(True)
                    ax._top_xlabel_on = True
                    # Position based on tick_state
                    try:
                        _ui_position_top_xlabel(ax, fig, tick_state)
                    except Exception:
                        pass
            else:
                if hasattr(ax,'_top_xlabel_artist') and ax._top_xlabel_artist is not None:
                    try:
                        ax._top_xlabel_artist.set_visible(False)
                    except Exception:
                        pass
                ax._top_xlabel_on = False
            # Right Y duplicate
            if titles.get('right_y'):
                base = ax.get_ylabel()
                if base:
                    if hasattr(ax,'_right_ylabel_artist') and ax._right_ylabel_artist is not None:
                        try: ax._right_ylabel_artist.remove()
                        except Exception: pass
                    ax._right_ylabel_artist = ax.text(1.02, 0.5, base, rotation=90, va='center', ha='left', transform=ax.transAxes)
                    ax._right_ylabel_on = True
                    try:
                        _ui_position_right_ylabel(ax, fig, tick_state)
                    except Exception:
                        pass
            else:
                if hasattr(ax,'_right_ylabel_artist') and ax._right_ylabel_artist is not None:
                    try:
                        ax._right_ylabel_artist.remove()
                    except Exception:
                        pass
                    ax._right_ylabel_artist = None
                ax._right_ylabel_on = False
        except Exception:
            pass
        # Always open interactive menu for session files
        try:
            args.stack = saved_stack
        except Exception:
            pass
        # Restore autoscale/raw flags for consistent behavior with saved session
        try:
            args_subset = sess.get('args_subset', {})
            if 'autoscale' in args_subset:
                args.autoscale = bool(args_subset['autoscale'])
            if 'norm' in args_subset:
                args.norm = bool(args_subset['norm'])
        except Exception:
            pass
        try:
            plt.ion()
        except Exception:
            pass
        try:
            plt.show(block=False)
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
    
        interactive_menu(fig, ax, y_data_list, x_data_list, labels_list,
                         orig_y, label_text_objects, delta, x_label, args,
                         x_full_list, raw_y_full_list, offsets_list,
                         use_Q, use_r, use_E, use_k, use_rft)
        plt.show()
        exit()

    # ---------------- Handle conversion ----------------
    if args.convert:
        if args.wl is None:
            print("Error: --wl is required for --convert")
       
            exit(1)
        convert_to_qye(args.convert, args.wl)
        exit()

    # ---------------- Plotting ----------------
    offset = 0.0
    direction = -1 if args.stack else 1  # stack downward
    if args.interactive:
        plt.ion()
    fig, ax = plt.subplots(figsize=(8, 6))

    y_data_list = []
    x_data_list = []
    labels_list = []
    orig_y = []
    label_text_objects = []
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
        # Special mode: plot time (h) vs voltage (V) for electrochemistry CSV/MPT files
        axis_mode = "time"
    else:
        # Regular XRD/PDF/XAS mode - proceed with normal detection
        any_qye = any(f.lower().endswith(".qye") for f in args.files)
        any_gr  = any(f.lower().endswith(".gr")  for f in args.files)
        any_nor = any(f.lower().endswith(".nor") for f in args.files)
        any_chik = any("chik" in _ext_token(f) for f in args.files)
        any_chir = any("chir" in _ext_token(f) for f in args.files)
        any_txt = any(f.lower().endswith(".txt") for f in args.files)
        any_cif = any(f.lower().endswith(".cif") for f in args.files)
        non_cif_count = sum(0 if f.lower().endswith('.cif') else 1 for f in args.files)
        cif_only = any_cif and non_cif_count == 0
        any_lambda = any(":" in f for f in args.files) or args.wl is not None

        # Incompatibilities (no mixing of fundamentally different axis domains)
        if sum(bool(x) for x in (any_gr, any_nor, any_chik, any_chir, (any_qye or any_lambda or any_cif))) > 1:
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
            # .txt is generic, require --xaxis
            if args.xaxis:
                axis_mode = args.xaxis
            else:
                raise ValueError("Unknown file type. Use: batplot file.txt --xaxis [Q|2theta|r|k|energy|rft] or batplot -h for help.")
        elif any_lambda or any_cif:
            if args.xaxis and args.xaxis.lower() in ("2theta","two_theta","tth"):
                axis_mode = "2theta"
            else:
                # If wavelength is provided, user wants to convert to Q
                # CIF files are in Q space
                axis_mode = "Q"
        elif args.xaxis:
            axis_mode = args.xaxis
        else:
            raise ValueError("Unknown file type. Use: batplot file.csv --xaxis [Q|2theta|r|k|energy|rft] or batplot -h for help.")

    use_Q   = axis_mode == "Q"
    use_2th = axis_mode == "2theta"
    use_r   = axis_mode == "r"
    use_E   = axis_mode == "energy"
    use_k   = axis_mode == "k"      # NEW
    use_rft = axis_mode == "rft"    # NEW
    use_time = axis_mode == "time"  # NEW: electrochemistry time mode

    # Validate: if using 2theta mode with CIF files, wavelength is required
    if use_2th and any_cif and not wavelength_file:
        raise ValueError(
            "Cannot display CIF files in 2θ mode without wavelength.\n"
            "Please provide wavelength using:\n"
            "  --wl <wavelength_in_angstrom>\n"
            "  or include wavelength in filename (e.g., data_wl1.5406.xy)\n"
            "  or use Q mode (remove --xaxis 2theta)"
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

    for idx_file, file_entry in enumerate(args.files):
        parts = file_entry.split(":")
        fname = parts[0]
        wavelength_file = float(parts[-1]) if len(parts) > 1 else args.wl
        if not os.path.isfile(fname):
            print(f"File not found: {fname}")
            continue
        file_ext = os.path.splitext(fname)[1].lower()
        is_chik = "chik" in file_ext
        is_chir = "chir" in file_ext
        is_cif  = file_ext == '.cif'
        label = os.path.basename(fname)
        if wavelength_file and not use_r and not use_E and file_ext not in (".gr", ".nor", ".cif"):
            label += f" (λ={wavelength_file:.5f} Å)"

        # ---- Read data (time mode for CSV/MPT or regular mode) ----
        if use_time and file_ext in ('.csv', '.mpt'):
            # Time mode: read time (h) vs voltage (V) for electrochemistry files
            try:
                if file_ext == '.csv':
                    x, y = read_csv_time_voltage(fname)
                elif file_ext == '.mpt':
                    x, y = read_mpt_time_voltage(fname)
                e = None
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
                # Force axis mode if needed
                if not (use_Q or use_2th):
                    use_Q = True
                # Reflection list and per-Q hkl labels (no wavelength cutoff in pure Q domain)
                qmax_sim = float(Q_sim[-1]) if len(Q_sim) else 0.0
                refl = cif_reflection_positions(fname, Qmax=qmax_sim, wavelength=None)
                hkl_list = list_reflections_with_hkl(fname, Qmax=qmax_sim, wavelength=None)
                cif_hkl_label_map[fname] = build_hkl_label_map_from_list(hkl_list)
                # default tick color black
                cif_tick_series.append((label, fname, refl, None, qmax_sim, 'k'))
                # If CIF mixed with other data types, do NOT plot intensity curve (ticks only)
                if not cif_only:
                    continue  # skip rest of loop so curve isn't added
            except Exception as e_read:
                print(f"Error simulating CIF {fname}: {e_read}")
                continue
        elif file_ext == ".gr":
            try:
                x, y = read_gr_file(fname); e = None
            except Exception as e_read:
                print(f"Error reading {fname}: {e_read}"); continue
        elif file_ext in [".nor", ".xy", ".xye", ".qye", ".dat", ".csv"] or is_chik or is_chir:
            try:
                data = robust_loadtxt_skipheader(fname)
            except Exception as e_read:
                print(f"Error reading {fname}: {e_read}"); continue
            if data.ndim == 1: data = data.reshape(1, -1)
            if data.shape[1] < 2:
                print(f"Invalid data format in {fname}"); continue
            # Handle --readcol flag to select specific columns
            # Check for extension-specific readcol first, then fall back to general --readcol
            readcol_spec = None
            if hasattr(args, 'readcol_by_ext') and file_ext in args.readcol_by_ext:
                readcol_spec = args.readcol_by_ext[file_ext]
            elif args.readcol:
                readcol_spec = args.readcol
            
            if readcol_spec:
                x_col, y_col = readcol_spec
                # Convert from 1-indexed to 0-indexed
                x_col_idx = x_col - 1
                y_col_idx = y_col - 1
                if x_col_idx < 0 or x_col_idx >= data.shape[1]:
                    print(f"Error: X column {x_col} out of range in {fname} (has {data.shape[1]} columns)")
                    continue
                if y_col_idx < 0 or y_col_idx >= data.shape[1]:
                    print(f"Error: Y column {y_col} out of range in {fname} (has {data.shape[1]} columns)")
                    continue
                x, y = data[:, x_col_idx], data[:, y_col_idx]
                e = None  # Error bars not supported with custom column selection
            else:
                x, y = data[:, 0], data[:, 1]
                e = data[:, 2] if data.shape[1] >= 3 else None
            # For .csv, .dat, .xy, .xye, .qye, .nor, .chik, .chir, this robustly skips headers
        elif args.fullprof and file_ext == ".dat":
            try:
                y_plot, n_rows = read_fullprof_rowwise(fname)
                xstart, xend, xstep = args.fullprof[0], args.fullprof[1], args.fullprof[2]
                x_plot = np.linspace(xstart, xend, len(y_plot))
                wavelength = args.fullprof[3] if len(args.fullprof)>=4 else wavelength_file
                if use_Q and wavelength:
                    theta_rad = np.radians(x_plot / 2)
                    x_plot = 4*np.pi*np.sin(theta_rad)/wavelength
                e_plot = None
            except Exception as e:
                print(f"Error reading FullProf-style {fname}: {e}")
                continue
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
            # Handle --readcol flag to select specific columns
            # Check for extension-specific readcol first, then fall back to general --readcol
            readcol_spec = None
            if hasattr(args, 'readcol_by_ext') and file_ext in args.readcol_by_ext:
                readcol_spec = args.readcol_by_ext[file_ext]
            elif args.readcol:
                readcol_spec = args.readcol
            
            if readcol_spec:
                x_col, y_col = readcol_spec
                # Convert from 1-indexed to 0-indexed
                x_col_idx = x_col - 1
                y_col_idx = y_col - 1
                if x_col_idx < 0 or x_col_idx >= data.shape[1]:
                    print(f"Error: X column {x_col} out of range in {fname} (has {data.shape[1]} columns)")
                    continue
                if y_col_idx < 0 or y_col_idx >= data.shape[1]:
                    print(f"Error: Y column {y_col} out of range in {fname} (has {data.shape[1]} columns)")
                    continue
                x, y = data[:, x_col_idx], data[:, y_col_idx]
                e = None  # Error bars not supported with custom column selection
            else:
                x, y = data[:, 0], data[:, 1]
                e = data[:, 2] if data.shape[1] >= 3 else None
            # Warn once per unknown extension type
            if not hasattr(args, '_warned_extensions'):
                args._warned_extensions = set()
            if file_ext and file_ext not in args._warned_extensions:
                args._warned_extensions.add(file_ext)
                print(f"Note: Reading '{file_ext}' file as 2-column (x, y) data. Use --xaxis to specify x-axis type if needed.")

        # ---- X-axis conversion logic updated (no conversion for energy or time) ----
        if use_time:
            # Time mode: data already in hours, no conversion needed
            x_plot = x
        elif use_Q and file_ext not in (".qye", ".gr", ".nor"):
            if wavelength_file:
                theta_rad = np.radians(x/2)
                x_plot = 4*np.pi*np.sin(theta_rad)/wavelength_file
            else:
                x_plot = x
        else:
            # r, energy, k, rft, or already Q: direct
            x_plot = x

        # ---- Store full (converted) arrays BEFORE cropping ----
        x_full = x_plot.copy()
        y_full_raw = y.copy()
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
            # Multiply y by x³ for EXAFS k³χ(k) plots
            y_plot = y_plot * (x_plot ** 3)
            y_full_raw = y_full_raw * (x_full ** 3)
            raw_y_full_list[-1] = y_full_raw
        elif getattr(args, 'k2chik', False):
            # Multiply y by x² for EXAFS k²χ(k) plots
            y_plot = y_plot * (x_plot ** 2)
            y_full_raw = y_full_raw * (x_full ** 2)
            raw_y_full_list[-1] = y_full_raw
        elif getattr(args, 'kchik', False):
            # Multiply y by x for EXAFS kχ(k) plots
            y_plot = y_plot * x_plot
            y_full_raw = y_full_raw * x_full
            raw_y_full_list[-1] = y_full_raw
        # elif getattr(args, 'chik', False): no multiplication needed, just label change

        # ---- Normalize (display subset) ----
        # Auto-normalize for --stack mode, or explicit --norm flag
        should_normalize = args.stack or getattr(args, 'norm', False)
        if should_normalize:
            # Min–max normalization to 0..1 within the currently displayed (cropped) segment
            if y_plot.size:
                y_min = float(y_plot.min())
                y_max = float(y_plot.max())
                span = y_max - y_min
                if span > 0:
                    y_norm = (y_plot - y_min) / span
                else:
                    # Flat line -> all zeros
                    y_norm = np.zeros_like(y_plot)
            else:
                y_norm = y_plot
        else:
            y_norm = y_plot

        # ---- Apply offset (waterfall vs stack) ----
        if args.stack:
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
        ax.plot(x_plot, y_plot_offset, "-", lw=1, alpha=0.8)
        y_data_list.append(y_plot_offset.copy())
        x_data_list.append(x_plot)
        labels_list.append(label)
        # Store current normalized (subset) (used by rearrange logic)
        orig_y.append(y_norm.copy())

    # ---------------- Force axis to fit all data before labels ----------------
    ax.relim()
    ax.autoscale_view()
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
    tick_fs = sample_tick.get_fontsize() if sample_tick else plt.rcParams.get('font.size', 12)
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

    # Ensure consistent initial placement (especially for stacked mode)
    update_labels(ax, y_data_list, label_text_objects, args.stack, False)
    
    # Initialize curve names visibility (default to visible)
    fig._curve_names_visible = True
    # Initialize stack label position (default to top/max)
    fig._stack_label_at_bottom = False

    # ---------------- CIF tick overlay (after labels placed) ----------------
    def _ensure_wavelength_for_2theta():
        """Ensure wavelength assigned to all CIF tick sets without prompting.

        Order of preference:
          1. Existing wavelength already stored in any series.
          2. args.wl if provided by user.
          3. Previously cached value (cif_cached_wavelength).
          4. Default 1.5406 Å.
        """
        global cif_cached_wavelength
        if not cif_tick_series:
            return None
        # If any entry already has wavelength, use and cache it
        for _lab,_fname,_peaks,_wl,_qmax,_color in cif_tick_series:
            if _wl is not None:
                cif_cached_wavelength = _wl
                return _wl
        wl = getattr(args, 'wl', None)
        if wl is None:
            wl = cif_cached_wavelength if cif_cached_wavelength is not None else 1.5406
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
        xmax_domain: upper x limit in current axis units (Q or 2θ).
        """
        if globals().get('cif_extend_suspended', False):
            return
        if not cif_tick_series:
            return
        # Determine target Q for extension depending on axis
        wl_any = None
        if use_2th:
            # Ensure wavelength known
            for _,_,_,wl_,_ in cif_tick_series:
                if wl_ is not None:
                    wl_any = wl_
                    break
            if wl_any is None:
                wl_any = _ensure_wavelength_for_2theta()
        updated = False
        for i,(lab,fname,peaksQ,wl,qmax_sim,color) in enumerate(cif_tick_series):
            if use_2th:
                wl_use = wl if wl is not None else wl_any
                theta_rad = np.radians(min(xmax_domain, 179.9)/2.0)
                Q_target = 4*np.pi*np.sin(theta_rad)/wl_use if wl_use else qmax_sim
            else:
                Q_target = xmax_domain
            if not QUIET_CIF_EXTEND:
                try:
                    print(f"[CIF extend check] {lab}: current Qmax={qmax_sim:.3f}, target Q={Q_target:.3f}")
                except Exception:
                    pass
            if Q_target > qmax_sim + 1e-6:
                new_Qmax = Q_target + 0.25
                try:
                    # Only apply wavelength constraint for 2θ axis; in Q axis enumerate freely
                    refl = cif_reflection_positions(fname, Qmax=new_Qmax, wavelength=(wl if (wl and use_2th) else None))
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
        if not cif_tick_series:
            return
        cur_ylim = ax.get_ylim(); yr = cur_ylim[1]-cur_ylim[0]
        if yr <= 0: yr = 1.0
        if args.stack or len(y_data_list) > 1:
            global_min = min(float(a.min()) for a in y_data_list if len(a)) if y_data_list else cur_ylim[0]
            base = global_min - 0.08*yr; spacing = 0.05*yr
        else:
            global_min = min(float(a.min()) for a in y_data_list if len(a)) if y_data_list else 0.0
            base = global_min - 0.06*yr; spacing = 0.04*yr
        needed_min = base - (len(cif_tick_series)-1)*spacing - 0.04*yr
        if needed_min < cur_ylim[0]:
            ax.set_ylim(needed_min, cur_ylim[1]); cur_ylim = ax.get_ylim(); yr = cur_ylim[1]-cur_ylim[0]
        # Clear previous
        for art in getattr(ax, '_cif_tick_art', []):
            try: art.remove()
            except Exception: pass
        new_art = []
        mixed_mode = (not cif_only)  # cif_only variable defined earlier in script context
        show_hkl = globals().get('show_cif_hkl', False)
        for i,(lab, fname, peaksQ, wl, qmax_sim, color) in enumerate(cif_tick_series):
            y_line = base - i*spacing
            if use_2th:
                if wl is None: wl = _ensure_wavelength_for_2theta()
                domain_peaks = _Q_to_2theta(peaksQ, wl)
            else:
                domain_peaks = peaksQ
            # --- NEW: restrict to current visible x-range for performance ---
            xlow, xhigh = ax.get_xlim()
            if domain_peaks:
                # domain_peaks may be numpy array or list; create filtered list
                domain_peaks = [p for p in domain_peaks if xlow <= p <= xhigh]
            if not domain_peaks:
                # No peaks in current window; still write label row and continue
                # Removed numbering; keep space padding
                label_text = f" {lab}"
                txt = ax.text(ax.get_xlim()[0], y_line + 0.005*yr, label_text,
                              ha='left', va='bottom', fontsize=max(8,int(0.55*plt.rcParams.get('font.size',12))), color=color)
                new_art.append(txt)
                continue
            # Build map for quick hkl lookup by Q
            hkl_entries = cif_hkl_map.get(fname, [])
            # dictionary keyed by Q value
            hkl_by_q = {}
            for qval,h,k,l in hkl_entries:
                hkl_by_q.setdefault(qval, []).append((h,k,l))
            label_map = cif_hkl_label_map.get(fname, {})
            # --- Optimized tick & hkl label drawing ---
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
                    ln, = ax.plot([p,p],[y_line, y_line+0.02*yr], color=color, lw=1.0, alpha=0.9, zorder=3)
                    new_art.append(ln)
                    if use_2th and wl:
                        theta = np.radians(p/2.0)
                        Qp = 4*np.pi*np.sin(theta)/wl
                    else:
                        Qp = p
                    lbl = label_map.get(round(Qp,6))
                    if lbl:
                        t_hkl = ax.text(p, y_line+0.022*yr, lbl, ha='center', va='bottom', fontsize=7, rotation=90, color=color)
                        new_art.append(t_hkl)
            else:
                # Just draw ticks (no hkl labels)
                for p in domain_peaks:
                    ln, = ax.plot([p,p],[y_line, y_line+0.02*yr], color=color, lw=1.0, alpha=0.9, zorder=3)
                    new_art.append(ln)
            # Removed numbering; keep space padding (placed per CIF row)
            # Only add title label if show_cif_titles is True
            if globals().get('show_cif_titles', True):
                label_text = f" {lab}"
                txt = ax.text(ax.get_xlim()[0], y_line + 0.005*yr, label_text,
                              ha='left', va='bottom', fontsize=max(8,int(0.55*plt.rcParams.get('font.size',12))), color=color)
                new_art.append(txt)
        ax._cif_tick_art = new_art
        # Store simplified metadata for hover: list of dicts with 'x','y','label'
        hover_meta = []
        show_hkl = globals().get('show_cif_hkl', False)
        # Build mapping from Q to label text if available
        for i,(lab, fname, peaksQ, wl, qmax_sim, color) in enumerate(cif_tick_series):
            if use_2th and wl is None:
                wl = getattr(ax, '_cif_hover_wl', None)
            # Recreate domain peaks consistent with those drawn (limit to view)
            if use_2th:
                if wl is None: continue
                domain_peaks = _Q_to_2theta(peaksQ, wl)
            else:
                domain_peaks = peaksQ
            xlow, xhigh = ax.get_xlim()
            domain_peaks = [p for p in domain_peaks if xlow <= p <= xhigh]
            if not domain_peaks:
                continue
            # y baseline for this series (same logic as above)
            if args.stack or len(y_data_list) > 1:
                global_min = min(float(a.min()) for a in y_data_list if len(a)) if y_data_list else ax.get_ylim()[0]
                base = global_min - 0.08*yr; spacing = 0.05*yr
            else:
                global_min = min(float(a.min()) for a in y_data_list if len(a)) if y_data_list else 0.0
                base = global_min - 0.06*yr; spacing = 0.04*yr
            y_line = base - i*spacing
            label_map = cif_hkl_label_map.get(fname, {}) if show_hkl else {}
            for p in domain_peaks:
                if use_2th and wl:
                    theta = np.radians(p/2.0); Qp = 4*np.pi*np.sin(theta)/wl
                else:
                    Qp = p
                lbl = label_map.get(round(Qp,6), None)
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
                # Compose text
                hkl_txt = best['hkl'] if best.get('hkl') else ''
                tip = f"{best['series']}\nQ={best['x']:.4f}" if use_Q else (f"{best['series']}\n2θ={best['x']:.4f}" if use_2th else f"{best['series']} {best['x']:.4f}")
                if hkl_txt:
                    tip += f"\n{hkl_txt}"
                tooltip.set_text(tip)
                tooltip.set_position((best['x'], best['y'] + 0.025*yr))
                if not tooltip.get_visible():
                    tooltip.set_visible(True)
                fig.canvas.draw_idle()
            cid = fig.canvas.mpl_connect('motion_notify_event', _on_move)
            ax._cif_hover_cid = cid

    if cif_tick_series:
        # Auto-assign distinct colors if all are default 'k'
        if len(cif_tick_series) > 1:
            if all(c[-1] == 'k' for c in cif_tick_series):
                try:
                    cmap_name = 'tab10' if len(cif_tick_series) <= 10 else 'hsv'
                    cmap = plt.get_cmap(cmap_name)
                    new_series = []
                    for i,(lab,fname,peaksQ,wl,qmax_sim,col) in enumerate(cif_tick_series):
                        color = cmap(i / max(1,(len(cif_tick_series)-1)))
                        new_series.append((lab,fname,peaksQ,wl,qmax_sim,color))
                    cif_tick_series[:] = new_series
                except Exception:
                    pass
        if use_2th:
            _ensure_wavelength_for_2theta()
        draw_cif_ticks()
        # expose helpers for interactive updates
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
        elif use_2th: x_label = r"$2\theta$ (deg)"
        elif use_time: x_label = "Time (h)"
        elif args.xaxis:
            x_label = str(args.xaxis)
        else:
            x_label = "X"
        
        # Y-axis label: normalized if --stack or --norm, or voltage for time mode
        should_normalize = args.stack or getattr(args, 'norm', False)
        if use_time:
            y_label = "Voltage (V)"
        elif should_normalize:
            y_label = "Normalized intensity (a.u.)"
        else:
            y_label = "Intensity"
    
    ax.set_xlabel(x_label, fontsize=16)
    ax.set_ylabel(y_label, fontsize=16)

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
    if args.interactive:
        # Show the current figure once (non-blocking) so interactive menu updates reuse this window
        try:
            plt.ion()
        except Exception:
            pass
        try:
            # Using canvas draw without show first avoids new-window creation on some backends
            fig.canvas.draw_idle(); fig.canvas.flush_events()
        except Exception:
            pass
        try:
            plt.show(block=False)
        except Exception:
            pass
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
        
        # Build CIF globals dict for explicit passing
        cif_globals = {
            'cif_tick_series': cif_tick_series,
            'cif_hkl_map': cif_hkl_map,
            'cif_hkl_label_map': cif_hkl_label_map,
            'show_cif_hkl': show_cif_hkl,
            'show_cif_titles': show_cif_titles,
            'cif_extend_suspended': cif_extend_suspended,
            'keep_canvas_fixed': keep_canvas_fixed,
        }
        
        interactive_menu(
            fig, ax, y_data_list, x_data_list, labels_list,
            orig_y, label_text_objects, args.delta, x_label, args,
            x_full_list, raw_y_full_list, offsets_list,
            use_Q, use_r, use_E, use_k, use_rft,
            cif_globals=cif_globals,
        )
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
    else:
        # Default: show the plot in non-interactive, non-save mode
        try:
            _backend = plt.get_backend()
        except Exception:
            _backend = "unknown"
        # TkAgg, QtAgg, Qt5Agg, WXAgg, MacOSX etc. are interactive
        _interactive_backends = {"tkagg", "qt5agg", "qt4agg", "qtagg", "wxagg", "macosx", "gtk3agg", "gtk4agg", "wx", "qt", "gtk", "gtk3", "gtk4"}
        _is_noninteractive = isinstance(_backend, str) and (_backend.lower() not in _interactive_backends) and ("agg" in _backend.lower() or _backend.lower() in {"pdf","ps","svg","template"})
        if not _is_noninteractive:
            plt.show()
        else:
            print(f"Matplotlib backend '{_backend}' is non-interactive; use --out to save the figure.")
    
    # Success
    return 0


# Entry point for CLI
if __name__ == "__main__":
    sys.exit(batplot_main())

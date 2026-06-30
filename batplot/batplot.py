"""batplot - Interactive plotting for 1D, electrochemistry and operando contour plots.
   It is designed for researchers working on materials science and electrochemistry, aiming to speed up the plotting process.
"""

from __future__ import annotations

from typing import Tuple, cast

# Import all dependencies at module level
from .plot_modes.electrochem.interactive import electrochem_interactive_menu
from .args import parse_args as _bp_parse_args
from .plot_modes.xy.interactive import interactive_menu
from .batch import batch_process, batch_process_ec, _apply_ec_style, _apply_xy_style
from .converters import convert_xrd_data
from .session import (
    dump_session as _bp_dump_session,
    load_xy_session,
    load_ec_session,
    load_operando_session,
    load_cpc_session,
    _apply_axes_bbox as _session_apply_axes_bbox,
    _try_extract_version_from_pickle,
    _get_current_numpy_version,
)
from .plot_modes.operando.plot import plot_operando_folder
from .plotting import update_labels
from .utils import (
    _confirm_overwrite,
    normalize_label_text,
    natural_sort_key,
    ensure_subdirectory,
    xy_cif_stack_y_offset,
    xy_cif_tick_stack_layout,
    xy_cif_add_phase_title,
    xy_cif_row_spacing_yr,
    xy_cif_stack_bottom_margin_yr,
)
from .readers import (
    read_csv_file,
    read_fullprof_rowwise,
    robust_loadtxt_skipheader,
    read_gr_file,
    read_xrd_vendor_file,
    is_bruker_raw,
    read_mpt_file,
    read_ec_csv_file,
    read_ec_csv_dqdv_file,
    compute_dqdv_numerical,
    read_mpt_dqdv_file,
    read_csv_time_voltage,
    read_mpt_time_voltage,
    read_cs_b_csv_file,
    is_cs_b_format,
    is_biologic_datalogger_csv,
    read_biologic_datalogger_csv,
    read_biologic_datalogger_dqdv_file,
    read_biologic_datalogger_time_voltage,
    _load_csv_header_and_rows,
    read_biologic_txt_file,
    read_batx_file,
    read_indexed_voltage_time_file,
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
from .version_check import UPDATE_INFO, _read_changelog_from_package
from . import __version__

import numpy as np  # type: ignore
import sys
import os
import pickle
import json
import random
import argparse
import re
import importlib.util
import matplotlib as _mpl  # type: ignore[import-untyped]
import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import matplotlib.cm as cm  # type: ignore[import-untyped]
import matplotlib.colors as mcolors  # type: ignore[import-untyped]
from matplotlib.ticker import AutoMinorLocator, NullFormatter  # type: ignore[import-untyped]
from matplotlib.colors import to_rgb, rgb_to_hsv, hsv_to_rgb  # type: ignore[import-untyped]
from matplotlib.colors import to_rgb  # type: ignore[import-untyped]

# Try to import optional interactive menus
try:
    from .plot_modes.operando.interactive import operando_ec_interactive_menu
except ImportError:
    operando_ec_interactive_menu = None


# Shared electrochem routing helpers (extracted to batplot.ec_common to keep the
# mode-specific routing modules free of a circular import back to this dispatcher).
from .ec_common import (
    _run_saved_dqdv_2d_companion,
    _resolve_mass,
    _figsize_for_frame,
    _default_ec_figsize,
    _default_cpc_figsize,
    _apply_default_ec_layout,
    _EC_DEFAULT_FIGSIZE,
    _EC_DEFAULT_LAYOUT,
    _CPC_DEFAULT_LAYOUT,
    _EC_DEFAULT_FRAME_SIZE,
)


try:
    from .plot_modes.cpc.interactive import cpc_interactive_menu, _generate_similar_color, _build_compact_cpc_legend
except ImportError:
    cpc_interactive_menu = None
    _build_compact_cpc_legend = None
    # Fallback function if import fails
    def _generate_similar_color(base_color):
        """Generate a similar but distinguishable color for discharge from charge color."""
        try:
            rgb = to_rgb(base_color)
            hsv = rgb_to_hsv(rgb)
            h, s, v = hsv
            h_new = (h + 0.04) % 1.0
            s_new = max(0.3, s * 0.85)
            v_new = max(0.4, v * 0.9)
            rgb_new = hsv_to_rgb([h_new, s_new, v_new])
            # Convert numpy array to tuple to avoid truth value ambiguity
            if hasattr(rgb_new, 'tolist'):
                return tuple(rgb_new.tolist())
            return tuple(rgb_new)
        except Exception:
            try:
                rgb = to_rgb(base_color)
                return tuple(max(0, c * 0.7) for c in rgb)
            except Exception:
                return base_color

# Global state variables (used by interactive menus and style system)
keep_canvas_fixed = False


ALLFILES_KNOWN_EXTENSIONS = {'.xye', '.xy', '.qye', '.dat', '.csv', '.gr', '.nor', '.chik', '.chir', '.txt', '.mpt', '.brml', '.raw', '.xrdml', '.rasx'}
ALLFILES_EXCLUDED_EXTENSIONS = {'.cif', '.pkl', '.py', '.md', '.json', '.yml', '.yaml', '.sh', '.bat'}


def _prepare_allfiles_directory(target_dir: str, args, use_relative_paths: bool = False,
                                allowed_exts: set[str] | None = None) -> None:
    """Populate args.files with data files under target_dir (optionally filtered by extension)."""
    all_xy_files = []
    unknown_ext_files = [] if allowed_exts is None else None

    try:
        entries = sorted(os.listdir(target_dir), key=natural_sort_key)
    except Exception as exc:
        print(f"Failed to list directory '{target_dir}': {exc}")
        exit(1)

    for f in entries:
        full_path = os.path.join(target_dir, f)
        if not os.path.isfile(full_path):
            continue
        ext = os.path.splitext(f)[1].lower()
        if ext in ALLFILES_EXCLUDED_EXTENSIONS or not ext:
            continue
        if allowed_exts is not None:
            if ext not in allowed_exts:
                continue
        else:
            # Default mode: keep unknown types but track for warning
            if ext not in ALLFILES_KNOWN_EXTENSIONS and unknown_ext_files is not None:
                unknown_ext_files.append(f)
        store_path = f if use_relative_paths else full_path
        all_xy_files.append(store_path)

    if not all_xy_files:
        if allowed_exts:
            ext_list = ", ".join(sorted(allowed_exts))
            print(f"No {ext_list} files found in directory: {target_dir}")
        else:
            print(f"No data files found in directory: {target_dir}")
        exit(1)

    if allowed_exts is None and unknown_ext_files:
        print(f"Warning: Found {len(unknown_ext_files)} file(s) with unknown extension(s):")
        for uf in unknown_ext_files[:5]:
            print(f"  - {uf}")
        if len(unknown_ext_files) > 5:
            print(f"  ... and {len(unknown_ext_files) - 5} more")
        print("These will be read as 2-column (x, y) data.")
        if not args.xaxis:
            print("Tip: Use --xaxis to specify the x-axis type (e.g., --xaxis 2theta, --xaxis Q, --xaxis r)")

    print(f"Found {len(all_xy_files)} files to plot together")
    args.files = all_xy_files


def _maybe_expand_allfiles_argument(args, ec_mode_active: bool = False) -> None:
    """Handle 'allfiles' argument appearing anywhere by expanding directory contents."""
    if ec_mode_active or not args.files:
        return
    token_info = []
    non_token_entries = []
    for original in args.files:
        lower = original.lower()
        if lower.startswith('all') and lower.endswith('files'):
            middle = lower[3:-5]
            token_info.append((original, middle))
        else:
            non_token_entries.append(original)
    if not token_info:
        return
    if len(token_info) > 1:
        print("Specify only one all*files token (e.g., allfiles or allxyfiles) at a time.")
        exit(1)
    _, middle = token_info[0]
    if len(non_token_entries) > 1:
        print("When using all*files tokens, provide zero or one directory argument.")
        exit(1)
    if middle:
        ext = f".{middle}"
        if ext not in ALLFILES_KNOWN_EXTENSIONS:
            allowed = ", ".join(sorted(e.strip('.') for e in ALLFILES_KNOWN_EXTENSIONS))
            print(f"Unknown all-files token 'all{middle}files'. Allowed extensions: {allowed}")
            exit(1)
        allowed_exts = {ext}
    else:
        allowed_exts = None
    if len(non_token_entries) == 1:
        dir_arg = non_token_entries[0]
        if not os.path.isdir(dir_arg):
            print(f"Directory not found: {dir_arg}")
            exit(1)
        target_dir = os.path.abspath(dir_arg)
        use_relative = False
    else:
        target_dir = os.getcwd()
        use_relative = True
    _prepare_allfiles_directory(target_dir, args, use_relative_paths=use_relative,
                                allowed_exts=allowed_exts)


def _handle_cv_mode(args) -> int:
    from .plot_modes.electrochem.routing import handle_cv_mode
    return handle_cv_mode(args)


def _run_convert_route(args) -> int | None:
    """Run --convert routing before plotting; return None when not applicable."""
    if not args.convert:
        return None
    if not args.files:
        print("Error: --convert requires file(s) or a directory to convert")
        return 1

    from .utils import natural_sort_key

    convert_ext = {'.xy', '.xye', '.qye', '.dat', '.csv', '.txt'}
    expanded = []
    for p in args.files:
        if os.path.isfile(p):
            ext = os.path.splitext(p)[1].lower()
            if ext in convert_ext:
                expanded.append(p)
            else:
                print(f"Warning: Skipping non-convertible file: {p}")
        elif os.path.isdir(p):
            for f in sorted(os.listdir(p), key=natural_sort_key):
                fp = os.path.join(p, f)
                if os.path.isfile(fp) and os.path.splitext(f)[1].lower() in convert_ext:
                    expanded.append(fp)
        else:
            print(f"Warning: Not a file or directory: {p}")
    if not expanded:
        print("Error: No convertible files found (.xy, .xye, .qye, .dat, .csv, .txt)")
        return 1

    from_param, to_param = args.convert
    convert_xrd_data(expanded, from_param, to_param, args=args)
    return 0


def _run_canvas_route(args) -> int | None:
    """Run --canvas session-combine routing; return None when not applicable."""
    if not (getattr(args, 'canvas', False) and args.files):
        return None
    if not all(f.lower().endswith('.pkl') for f in args.files):
        print("Canvas mode requires all files to be .pkl session files.")
        return 1
    try:
        from .canvas_interactive import run_canvas_mode

        run_canvas_mode(args.files)
        return 0
    except Exception as e:
        print(f"Canvas mode failed: {e}")
        import traceback

        traceback.print_exc()
        return 1


def batplot_main() -> int:  # type: ignore
    """
    Main entry point for batplot CLI.
    
    This is the central routing function that:
    1. Parses command-line arguments
    2. Determines which mode to use (XY, EC, Operando, Batch, etc.)
    3. Routes to the appropriate handler function
    4. Handles errors and returns exit codes
    
    HOW ROUTING WORKS:
    -----------------
    batplot supports multiple modes, determined by command-line flags:
    
    XY MODE (default):
        batplot file1.xy file2.xy          → Normal XY plotting
        batplot allfiles                    → Plot all files together
        batplot --all                       → Batch mode (separate files)
    
    EC MODES (electrochemistry):
        batplot --gc file.mpt --mass 7.0    → Galvanostatic cycling
        batplot --cv file.mpt               → Cyclic voltammetry
        batplot --dqdv file.csv             → Differential capacity
        batplot --cpc file.csv              → Capacity per cycle
    
    OPERANDO MODE:
        batplot --operando folder/          → Contour plot from folder
    
    BATCH MODES:
        batplot --all                       → Batch XY mode
        batplot --gc --all --mass 7.0       → Batch EC mode
    
    CONVERSION:
        batplot --convert file.xy --wl 1.54 → Convert 2θ to Q
    
    The function checks flags in priority order and routes accordingly.
    
    Returns:
        Exit code: 0 for success, non-zero for error
        (Follows Unix convention: 0 = success, non-zero = error)
    """
    # ====================================================================
    # STEP 1: PARSE COMMAND-LINE ARGUMENTS
    # ====================================================================
    # Parse all command-line arguments into a namespace object.
    # This includes files, flags (--gc, --cv, etc.), and options (--mass, --wl, etc.)
    # ====================================================================
    args = _bp_parse_args()

    # --version / -V: show version and release info then exit
    if getattr(args, 'version', False):
        try:
            print(f"batplot v{__version__}")
            msg = UPDATE_INFO.get('custom_message') or (UPDATE_INFO.get('update_notes') or [None])[0]
            if msg:
                print(msg)
            try:
                choice = input("\nShow full release notes? [y/N]: ").strip().lower()
                if choice in ('y', 'yes'):
                    changelog = _read_changelog_from_package()
                    if changelog:
                        print("\n--- Full release notes (CHANGELOG) ---\n")
                        print(changelog)
                        print("\n--- End of release notes ---\n")
                    else:
                        print("  Release notes not included in this build.")
            except (KeyboardInterrupt, EOFError):
                print()
        except Exception:
            print(f"batplot v{__version__}")
        return 0

    # --showcol: print column names (if any) and first data rows, then exit
    if getattr(args, "showcol", False):
        if not args.files:
            print("batplot --showcol: provide at least one data file.")
            return 1
        from .showcol import run_showcol

        return run_showcol(args.files)

    # ====================================================================
    # STEP 2: VALIDATE INPUT
    # ====================================================================
    # Check if user provided any input (files or special flags).
    # If nothing provided, show help message and exit gracefully.
    # ====================================================================
    
    # Check for special flags that don't require file arguments
    # These modes can work without explicit file arguments (e.g., --all scans directory)
    has_special_flag = any([
        getattr(args, 'gc', False),      # Galvanostatic cycling mode
        getattr(args, 'cv', False),      # Cyclic voltammetry mode
        getattr(args, 'dqdv', False),    # Differential capacity mode
        getattr(args, 'cpc', False),     # Capacity per cycle mode
        getattr(args, 'operando', False), # Operando contour mode
        getattr(args, 'all', None) is not None,  # Batch mode flag
        getattr(args, 'convert', None) is not None,  # Conversion mode
    ])
    
    # If no files AND no special flags, nothing to do
    if not args.files and not has_special_flag:
        print("No input provided, nothing to do.")
        print("Use 'batplot --v' for version and release info, 'batplot --h' for CLI help, or 'batplot --m' to open the user manual.")
        return 0  # Exit successfully (not an error, just nothing to do)

    from ._mpl_backend import ensure_gui_backend

    ensure_gui_backend(args)

    # ====================================================================
    # STEP 3: ROUTE TO APPROPRIATE MODE HANDLER
    # ====================================================================
    # Check flags in priority order and route to corresponding handler.
    # Priority matters: some modes are checked before others.
    # ====================================================================
    
    # ====================================================================
    # EC BATCH MODE (HIGHEST PRIORITY)
    # ====================================================================
    # If any EC mode is active AND user specified batch processing,
    # route to EC batch handler (processes all EC files in directory).
    #
    # EC batch mode examples:
    #   batplot --gc --all --mass 7.0        → Process all .mpt/.csv files
    #   batplot --cv --all                   → Process all .mpt/.txt files
    #   batplot --gc all --mass 7.0          → Same as above (alternative syntax)
    #   batplot --gc /path/to/folder --mass 7 → Process specific directory
    # ====================================================================
    
    # Check if any EC mode is active
    ec_mode_active = any([
        getattr(args, 'gc', False),      # Galvanostatic cycling
        getattr(args, 'cv', False),      # Cyclic voltammetry
        getattr(args, 'dqdv', False),    # Differential capacity
        getattr(args, 'cpc', False),     # Capacity per cycle
        getattr(args, 'epc', False),     # Energy per cycle
    ])
    
    # Check for --all flag (explicit batch mode)
    if ec_mode_active and getattr(args, 'all', None) is not None:
        # Process all EC files in current directory
        batch_process_ec(os.getcwd(), args)
        exit()  # Exit after batch processing (don't continue to other modes)
    
    # Check for 'all' as file argument or directory path
    if ec_mode_active and len(args.files) == 1:
        sole = args.files[0]
        if sole.lower() == 'all':
            # User typed 'all' as file argument (alternative syntax)
            batch_process_ec(os.getcwd(), args)
            exit()
        elif os.path.isdir(sole):
            # User provided directory path
            batch_process_ec(os.path.abspath(sole), args)
            exit()

    # --- CV mode: plot potential vs current for each cycle from .mpt ---
    if getattr(args, 'cv', False):
        return _handle_cv_mode(args)


    """
    batplot_v1.0.10: Interactively plot:
        XRD data .xye, .xy, .qye, .dat, .csv
        PDF data .gr
        XAS data .nor, .chik, .chir
        More features to be added.
    """


    # Set global default font
    plt.rcParams.update({
        'font.family': 'sans-serif',
        # Use DejaVu Sans first to ensure good Unicode coverage (subscripts,
        # superscripts, Greek, etc.), then fall back to other common fonts.
        'font.sans-serif': ['DejaVu Sans', 'Arial', 'Helvetica', 'STIXGeneral', 'Liberation Sans', 'Arial Unicode MS'],
        'mathtext.fontset': 'dejavusans',   # keeps math consistent with sans-serif
        'font.size': 16
    })

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
    # Normal XY interactive menu is imported from batplot.plot_modes.xy.interactive as `interactive_menu`.

    # Galvanostatic cycling mode check: .mpt or supported .csv file with --gc flag
    if getattr(args, 'gc', False):
        from .plot_modes.electrochem.routing import handle_gc_mode
        return handle_gc_mode(args)

    # Capacity-per-cycle (CPC) summary from CSV or .mpt with coulombic efficiency
    if getattr(args, 'cpc', False) or getattr(args, 'epc', False):
        from .plot_modes.cpc.routing import handle_cpc_mode
        return handle_cpc_mode(args)

    # dQ/dV plotting mode for supported .csv electrochemistry exports
    if getattr(args, 'dqdv', False):
        from .plot_modes.electrochem.routing import handle_dqdv_mode
        return handle_dqdv_mode(args)

    # Operando contour plotting mode (folder-based)
    if getattr(args, 'operando', False):
        from .plot_modes.operando.routing import handle_operando_mode
        return handle_operando_mode(args)

    _maybe_expand_allfiles_argument(args, ec_mode_active)

    # ---------------- Handle --convert (before batch/sole logic) ----------------
    convert_status = _run_convert_route(args)
    if convert_status is not None:
        return convert_status

    if len(args.files) == 1:
        sole = args.files[0]
        if sole.lower() == 'all':
            batch_process(os.getcwd(), args)
            exit()
        elif sole.lower() == 'allfiles':
            _prepare_allfiles_directory(os.getcwd(), args, use_relative_paths=True)
            # Continue to normal plotting mode with all files
        elif os.path.isdir(sole):
            batch_process(os.path.abspath(sole), args)
            exit()

    # --- XY Batch Mode: check for --all flag for XY files ---
    # Handle --all flag for XY batch processing (consistent with EC batch mode)
    if not ec_mode_active and getattr(args, 'all', None) is not None:
        batch_process(os.getcwd(), args)
        exit()

    # ---------------- Canvas mode: combine multiple .pkl sessions ----------------
    canvas_status = _run_canvas_route(args)
    if canvas_status is not None:
        return canvas_status
    
    # ---------------- Normal (multi-file) path continues below ----------------
    # Apply conditional default for delta (normal mode only)
    if args.delta is None:
        args.delta = 0.1 if args.stack else 0.0

    # ---------------- Automatic session (.pkl) load shortcut ----------------
    # If user invokes: batplot session.pkl [--interactive]
    if len(args.files) == 1 and args.files[0].lower().endswith('.pkl'):
        from .plot_modes.session_routing import handle_session_reload
        return handle_session_reload(args)

    from .plot_modes.xy.pipeline import run_xy_pipeline
    return run_xy_pipeline(args)


# Entry point for CLI
if __name__ == "__main__":
    sys.exit(batplot_main())

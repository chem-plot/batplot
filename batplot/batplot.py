"""batplot - Interactive plotting for 1D, electrochemistry and operando contour plots.
   It is designed for researchers working on materials science and electrochemistry, aiming to speed up the plotting process.
"""

from __future__ import annotations

# Import all dependencies at module level
from .electrochem_interactive import electrochem_interactive_menu
from .args import parse_args as _bp_parse_args
from .interactive import interactive_menu
from .batch import batch_process, batch_process_ec, _apply_ec_style, _apply_xy_style
from .converters import convert_xrd_data
from .session import (
    dump_session as _bp_dump_session,
    load_ec_session,
    load_operando_session,
    load_cpc_session,
    _apply_axes_bbox as _session_apply_axes_bbox,
    _try_extract_version_from_pickle,
    _get_current_numpy_version,
)
from .operando import plot_operando_folder
from .plotting import update_labels
from .utils import _confirm_overwrite, normalize_label_text, natural_sort_key, ensure_subdirectory
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
    read_mpt_dqdv_file,
    read_csv_time_voltage,
    read_mpt_time_voltage,
    read_cs_b_csv_file,
    is_cs_b_format,
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
    from .operando_ec_interactive import operando_ec_interactive_menu
except ImportError:
    operando_ec_interactive_menu = None

try:
    from .cpc_interactive import cpc_interactive_menu, _generate_similar_color
except ImportError:
    cpc_interactive_menu = None
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
    """
    Handle CV mode plotting and routing.
    Returns an integer exit code (0 for success, non-zero for error).
    """
    # Separate style files from data files
    data_files = []
    style_file_path = None
    for f in args.files:
        ext = os.path.splitext(f)[1].lower()
        if ext in ('.bps', '.bpsg', '.bpcfg'):
            if style_file_path is None:
                style_file_path = f
            else:
                print(f"Warning: Multiple style files provided, using first: {style_file_path}")
        else:
            data_files.append(f)

    if not data_files:
        print("CV mode: no data files found (only style files provided).")
        return 1

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

    # Process each data file
    out_dir = None
    if len(data_files) > 1 and (args.savefig or args.out):
        # Multiple files: create output directory
        out_dir = ensure_subdirectory('Figures', os.getcwd())

    for ec_file in data_files:
        if not os.path.isfile(ec_file):
            print(f"File not found: {ec_file}")
            if len(data_files) > 1:
                continue
            return 1
        try:
            # Support both .mpt and .txt formats
            if ec_file.lower().endswith('.txt'):
                voltage, current, cycles = read_biologic_txt_file(ec_file, mode='cv')
            else:
                # read_mpt_file can return different tuple sizes depending on mode;
                # in CV mode we only use the first three elements (voltage, current, cycles).
                mpt_result = read_mpt_file(ec_file, mode='cv')
                voltage = mpt_result[0]
                current = mpt_result[1]
                cycles = mpt_result[2]
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
            plt.rcParams.update({
                'font.family': 'sans-serif',
                # Prefer DejaVu Sans first because it has good Unicode
                # coverage (including subscript/superscript digits), then
                # fall back to other common sans-serif fonts.
                'font.sans-serif': ['DejaVu Sans', 'Arial', 'Helvetica', 'STIXGeneral', 'Liberation Sans', 'Arial Unicode MS'],
                'mathtext.fontset': 'dejavusans',
                'font.size': 16
            })
            fig, ax = plt.subplots(figsize=(10, 6))
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
            # Swap axis labels if --ro flag is set
            if getattr(args, 'ro', False):
                ax.set_xlabel('Current (mA)', labelpad=8.0)
                ax.set_ylabel('Voltage (V)', labelpad=8.0)
            else:
                ax.set_xlabel('Voltage (V)', labelpad=8.0)
                ax.set_ylabel('Current (mA)', labelpad=8.0)
            legend = ax.legend(title='Cycle')
            if legend is not None:
                try:
                    legend.set_frame_on(False)
                except Exception:
                    pass
            legend.get_title().set_fontsize('medium')
            fig._ec_legend_title = "Cycle"
            # Match GC/dQdV: consistent label/title displacement and canvas
            fig.subplots_adjust(left=0.12, right=0.95, top=0.88, bottom=0.15)

            # Apply style file if provided
            if style_cfg:
                try:
                    _apply_ec_style(fig, ax, style_cfg)
                    # Redraw after applying style
                    if hasattr(fig, 'canvas'):
                        fig.canvas.draw()
                except Exception as e:
                    print(f"Warning: Error applying style file: {e}")

            # Save if requested
            if len(data_files) > 1 and (args.savefig or args.out):
                # Multiple files: save to Figures/ directory
                base_name = os.path.splitext(os.path.basename(ec_file))[0]
                output_format = getattr(args, 'format', 'svg')
                outname = os.path.join(out_dir or "", f"{base_name}.{output_format}")
                try:
                    _, _ext = os.path.splitext(outname)
                    if _ext.lower() == '.svg':
                        plt.rcParams['svg.fonttype'] = 'none'
                        plt.rcParams['svg.hashsalt'] = None
                    fig.savefig(outname, dpi=300, transparent=True if _ext.lower() == '.svg' else False)
                    print(f"CV plot saved to {outname}")
                except Exception as e:
                    print(f"Warning: Could not save CV plot: {e}")

            # Interactive menu: use electrochem_interactive_menu for consistency with GC
            if args.interactive:
                try:
                    plt.ion()
                except Exception:
                    pass
                plt.show(block=False)
                # Track whether data axes were swapped via --ro for this EC figure
                try:
                    fig._ro_active = bool(getattr(args, "ro", False))
                except Exception:
                    pass
                try:
                    fig._bp_source_paths = [os.path.abspath(ec_file)]
                except Exception:
                    pass
                try:
                    electrochem_interactive_menu(fig, ax, cycle_lines, file_path=ec_file)
                except Exception as _ie:
                    print(f"Interactive menu failed: {_ie}")
                plt.show()
            else:
                if not (args.savefig or args.out):
                    plt.show()
                # For multiple files, close the figure and continue to next file
                if len(data_files) > 1:
                    plt.close(fig)
                    continue
                return 0
        except Exception as e:
            print(f"CV plot failed for {ec_file}: {e}")
            if len(data_files) > 1:
                continue
            return 1

    # Exit after processing all files
    if len(data_files) > 1:
        print(f"Processed {len(data_files)} CV files.")
        return 0

    return 0


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
        print("Use 'batplot -v' for version and release info, 'batplot -h' for CLI help, or 'batplot -m' to open the txt manual.")
        return 0  # Exit successfully (not an error, just nothing to do)

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
        getattr(args, 'dqdv', False),     # Differential capacity
        getattr(args, 'cpc', False)       # Capacity per cycle
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

    # --- CV mode: plot voltage vs current for each cycle from .mpt ---
    if getattr(args, 'cv', False):
        return _handle_cv_mode(args)


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
        wants_interactive = wants_interactive or ("--operando" in argv or "--contour" in argv)
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
        for cand in order:
            try:
                if cand == "TkAgg":
                    if importlib.util.find_spec("tkinter") is None:
                        continue
                elif cand == "QtAgg":
                    if (importlib.util.find_spec("PyQt5") is None) and (importlib.util.find_spec("PySide6") is None):
                        continue
                # MacOSX: attempt; will fail on non-framework builds
                _mpl.use(cand, force=True)
                break
            except Exception:
                continue

    _ensure_gui_backend_for_interactive()

    # Set global default font
    plt.rcParams.update({
        'font.family': 'sans-serif',
        # Use DejaVu Sans first to ensure good Unicode coverage (subscripts,
        # superscripts, Greek, etc.), then fall back to other common fonts.
        'font.sans-serif': ['DejaVu Sans', 'Arial', 'Helvetica', 'STIXGeneral', 'Liberation Sans', 'Arial Unicode MS'],
        'mathtext.fontset': 'dejavusans',   # keeps math consistent with sans-serif
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
        # Separate style files from data files
        data_files = []
        style_file_path = None
        for f in args.files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ('.bps', '.bpsg', '.bpcfg'):
                if style_file_path is None:
                    style_file_path = f
                else:
                    print(f"Warning: Multiple style files provided, using first: {style_file_path}")
            else:
                data_files.append(f)
        
        if not data_files:
            print("GC mode: no data files found (only style files provided).")
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
        
        # Process each data file
        out_dir = None
        if len(data_files) > 1 and (args.savefig or args.out):
            # Multiple files: create output directory
            out_dir = ensure_subdirectory('Figures', os.getcwd())

        # GC multi-file: one figure with all files overlaid (same for interactive and non-interactive)
        if len(data_files) > 1:
            fig, ax = plt.subplots(figsize=(10, 6))
            file_data = []
            base_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                           '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
            x_label_gc = r'Specific Capacity (mAh g$^{-1}$)'

            def _contiguous_blocks(mask):
                inds = np.where(mask)[0]
                if inds.size == 0:
                    return []
                blocks = []
                start, prev = inds[0], inds[0]
                for j in inds[1:]:
                    if j == prev + 1:
                        prev = j
                    else:
                        blocks.append((start, prev))
                        start, prev = j, j
                blocks.append((start, prev))
                return blocks

            def _broken_arrays_from_indices(idx, x, y):
                if idx.size == 0:
                    return np.array([]), np.array([])
                parts_x, parts_y = [], []
                start = 0
                for k in range(1, idx.size):
                    if idx[k] != idx[k - 1] + 1:
                        parts_x.append(x[idx[start:k]])
                        parts_y.append(y[idx[start:k]])
                        start = k
                parts_x.append(x[idx[start:]])
                parts_y.append(y[idx[start:]])
                X, Y = [], []
                for i, (px, py) in enumerate(zip(parts_x, parts_y)):
                    if i > 0:
                        X.append(np.array([np.nan]))
                        Y.append(np.array([np.nan]))
                    X.append(px)
                    Y.append(py)
                return np.concatenate(X) if X else np.array([]), np.concatenate(Y) if Y else np.array([])

            for file_idx, ec_file in enumerate(data_files):
                if not os.path.isfile(ec_file) or not (ec_file.lower().endswith('.mpt') or ec_file.lower().endswith('.csv')):
                    continue
                try:
                    if ec_file.lower().endswith('.mpt'):
                        mass_mg = getattr(args, 'mass', None)
                        if mass_mg is None:
                            continue
                        specific_capacity, voltage, cycle_numbers, charge_mask, discharge_mask = read_mpt_file(ec_file, mode='gc', mass_mg=mass_mg)
                        cap_x = specific_capacity
                    elif ec_file.lower().endswith('.csv'):
                        try:
                            header, _, _ = _load_csv_header_and_rows(ec_file)
                            if is_cs_b_format(header):
                                cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = read_cs_b_csv_file(ec_file, mode='gc')
                            else:
                                cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = read_ec_csv_file(ec_file, prefer_specific=True)
                        except Exception:
                            cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = read_ec_csv_file(ec_file, prefer_specific=True)
                    else:
                        continue
                    color_offset = (file_idx * 5) % len(base_colors)
                    if cycle_numbers is not None:
                        cyc_int_raw = np.array(np.rint(cycle_numbers), dtype=int)
                        min_c = int(np.min(cyc_int_raw)) if cyc_int_raw.size else 1
                        shift = 1 - min_c if min_c <= 0 else 0
                        cyc_int = cyc_int_raw + shift
                        cycles_present = sorted(int(c) for c in np.unique(cyc_int))
                    else:
                        cycles_present = [1]
                    inferred = len(cycles_present) <= 1
                    if inferred:
                        ch_blocks = _contiguous_blocks(charge_mask)
                        dch_blocks = _contiguous_blocks(discharge_mask)
                        cycles_present = list(range(1, max(len(ch_blocks), len(dch_blocks)) + 1)) if (ch_blocks or dch_blocks) else [1]
                    # Legend: multi-file use filename (or display_name) so legend reflects data
                    file_lbl = os.path.basename(ec_file) if len(data_files) > 1 else ""
                    cycle_lines = {}
                    if not inferred and cycle_numbers is not None:
                        for cyc in cycles_present:
                            mask_c = (cyc_int == cyc) & charge_mask
                            idx = np.where(mask_c)[0]
                            ln_c = None
                            if idx.size >= 2:
                                x_b, y_b = _broken_arrays_from_indices(idx, cap_x, voltage)
                                col = base_colors[(color_offset + cyc - 1) % len(base_colors)]
                                leg_cyc = f"{file_lbl}: {cyc}" if file_lbl else str(cyc)
                                if getattr(args, 'ro', False):
                                    ln_c, = ax.plot(y_b, x_b, '-', color=col, linewidth=2.0, label=leg_cyc, alpha=0.8)
                                else:
                                    ln_c, = ax.plot(x_b, y_b, '-', color=col, linewidth=2.0, label=leg_cyc, alpha=0.8)
                            mask_d = (cyc_int == cyc) & discharge_mask
                            idxd = np.where(mask_d)[0]
                            ln_d = None
                            if idxd.size >= 2:
                                xd_b, yd_b = _broken_arrays_from_indices(idxd, cap_x, voltage)
                                lbl = '_nolegend_' if ln_c is not None else (f"{file_lbl}: {cyc}" if file_lbl else str(cyc))
                                col = base_colors[(color_offset + cyc - 1) % len(base_colors)]
                                if getattr(args, 'ro', False):
                                    ln_d, = ax.plot(yd_b, xd_b, '-', color=col, linewidth=2.0, label=lbl, alpha=0.8)
                                else:
                                    ln_d, = ax.plot(xd_b, yd_b, '-', color=col, linewidth=2.0, label=lbl, alpha=0.8)
                            cycle_lines[cyc] = {"charge": ln_c, "discharge": ln_d}
                    else:
                        ch_blocks = _contiguous_blocks(charge_mask)
                        dch_blocks = _contiguous_blocks(discharge_mask)
                        N = max(len(ch_blocks), len(dch_blocks))
                        for i in range(N):
                            cyc = i + 1
                            col = base_colors[(color_offset + cyc - 1) % len(base_colors)]
                            leg_cyc = f"{file_lbl}: {cyc}" if file_lbl else str(cyc)
                            ln_c = None
                            if i < len(ch_blocks):
                                a, b = ch_blocks[i]
                                idx = np.arange(a, b + 1)
                                x_b, y_b = _broken_arrays_from_indices(idx, cap_x, voltage)
                                if getattr(args, 'ro', False):
                                    ln_c, = ax.plot(y_b, x_b, '-', color=col, linewidth=2.0, label=leg_cyc, alpha=0.8)
                                else:
                                    ln_c, = ax.plot(x_b, y_b, '-', color=col, linewidth=2.0, label=leg_cyc, alpha=0.8)
                            ln_d = None
                            if i < len(dch_blocks):
                                a, b = dch_blocks[i]
                                idx = np.arange(a, b + 1)
                                xd_b, yd_b = _broken_arrays_from_indices(idx, cap_x, voltage)
                                lbl = '_nolegend_' if ln_c is not None else (f"{file_lbl}: {cyc}" if file_lbl else str(cyc))
                                if getattr(args, 'ro', False):
                                    ln_d, = ax.plot(yd_b, xd_b, '-', color=col, linewidth=2.0, label=lbl, alpha=0.8)
                                else:
                                    ln_d, = ax.plot(xd_b, yd_b, '-', color=col, linewidth=2.0, label=lbl, alpha=0.8)
                            cycle_lines[cyc] = {"charge": ln_c, "discharge": ln_d}
                    file_data.append({
                        'filename': os.path.basename(ec_file),
                        'display_name': os.path.basename(ec_file),
                        'cycle_lines': cycle_lines,
                        'visible': True,
                        'filepath': ec_file,
                    })
                except Exception as _e:
                    print(f"GC multi-file: skip {ec_file}: {_e}")
            if not file_data:
                print("GC multi-file: no files loaded.")
                exit(1)
            if getattr(args, 'ro', False):
                ax.set_xlabel('Voltage (V)', labelpad=8.0)
                ax.set_ylabel(x_label_gc, labelpad=8.0)
            else:
                ax.set_xlabel(x_label_gc, labelpad=8.0)
                ax.set_ylabel('Voltage (V)', labelpad=8.0)
            ax.legend(title='Cycle')
            fig._ec_legend_title = "Cycle"
            fig.subplots_adjust(left=0.12, right=0.95, top=0.88, bottom=0.15)
            if style_cfg:
                try:
                    _apply_ec_style(fig, ax, style_cfg)
                    if hasattr(fig, 'canvas'):
                        fig.canvas.draw()
                except Exception as e:
                    print(f"Warning: Error applying style file: {e}")
            try:
                plt.ion()
            except Exception:
                pass
            plt.show(block=False)
            try:
                fig._bp_source_paths = [os.path.abspath(f.get('filepath', '')) for f in file_data if f.get('filepath')]
            except Exception:
                pass
            if args.interactive:
                try:
                    electrochem_interactive_menu(fig, ax, file_data=file_data)
                except Exception as _ie:
                    print(f"Interactive menu failed: {_ie}")
                plt.show()
            else:
                if out_dir and (args.savefig or getattr(args, 'out', None)):
                    out_path = getattr(args, 'out', None)
                    if not out_path:
                        ext = getattr(args, 'format', 'svg') or 'svg'
                        out_path = os.path.join(out_dir, f'GC_combined.{ext}')
                    try:
                        fig.savefig(out_path, dpi=300, bbox_inches='tight')
                        print(f"Saved {out_path}")
                    except Exception as e:
                        print(f"Could not save: {e}")
                try:
                    plt.ioff()
                except Exception:
                    pass
                print(f"Processed {len(file_data)} GC files.")
                plt.show(block=True)
            exit(0)

        for ec_file_idx, ec_file in enumerate(data_files):
            if not os.path.isfile(ec_file):
                print(f"File not found: {ec_file}")
                continue
            
            try:
                # Check for potential-window mode first (custom voltage-time format)
                if getattr(args, 'pw', None) is not None:
                    v_min, v_max = args.pw
                    current_density = getattr(args, 'cd', None)
                    if current_density is None:
                        print("Potential-window mode: --cd parameter is required (current density in mA/g).")
                        print("Example: batplot file.mpt --pw 0.01 3 --cd 0.2")
                        if len(data_files) > 1:
                            continue
                        else:
                            exit(1)
                    # Import the potential-window (voltage-time to GC) reader
                    b_tol = getattr(args, 'b', None)
                    tol_upper = b_tol[0] if b_tol is not None and len(b_tol) >= 2 else 0.05
                    tol_lower = b_tol[1] if b_tol is not None and len(b_tol) >= 2 else 0.005
                    cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = read_batx_file(ec_file, v_min, v_max, current_density, tol_upper=tol_upper, tol_lower=tol_lower)
                    x_label_gc = r'Specific Capacity (mAh g$^{-1}$)'
                # Branch by extension
                elif ec_file.lower().endswith('.mpt'):
                    # If anode/cathode flags are set, try indexed voltage-time format first
                    if getattr(args, 'anode', False) or getattr(args, 'cathode', False):
                        is_anode = bool(getattr(args, 'anode', False))
                        cd = getattr(args, 'cd', None)
                        cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = read_indexed_voltage_time_file(
                            ec_file,
                            is_anode=is_anode,
                            current_density=cd,
                        )
                        x_label_gc = r'Specific Capacity (mAh g$^{-1}$)' if cd is not None else "Relative Capacity (h)"
                    else:
                        # For standard .mpt, mass is required to compute specific capacity
                        mass_mg = getattr(args, 'mass', None)
                        if mass_mg is None:
                            print("GC mode (.mpt): --mass parameter is required (active material mass in milligrams).")
                            print("Example: batplot file.mpt --gc --mass 7.0")
                            if len(data_files) > 1:
                                continue
                            else:
                                exit(1)
                        specific_capacity, voltage, cycle_numbers, charge_mask, discharge_mask = read_mpt_file(ec_file, mode='gc', mass_mg=mass_mg)
                        x_label_gc = r'Specific Capacity (mAh g$^{-1}$)'
                        cap_x = specific_capacity
                elif ec_file.lower().endswith('.csv'):
                    # Check if this is CS-B format
                    try:
                        header, _, _ = _load_csv_header_and_rows(ec_file)
                        if is_cs_b_format(header):
                            # Use CS-B format reader
                            cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = read_cs_b_csv_file(ec_file, mode='gc')
                        else:
                            # Use standard CSV reader
                            cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = read_ec_csv_file(ec_file, prefer_specific=True)
                    except Exception:
                        # Fallback to standard reader
                        cap_x, voltage, cycle_numbers, charge_mask, discharge_mask = read_ec_csv_file(ec_file, prefer_specific=True)
                    x_label_gc = r'Specific Capacity (mAh g$^{-1}$)'
                else:
                    print(f"GC mode: file must be .mpt or .csv: {ec_file}")
                    if len(data_files) > 1:
                        continue
                    else:
                        exit(1)

                # Create the plot
                fig, ax = plt.subplots(figsize=(10, 6))

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
                            # Swap x and y if --ro flag is set
                            if getattr(args, 'ro', False):
                                ln_c, = ax.plot(y_b, x_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                                linewidth=2.0, label=str(cyc), alpha=0.8)
                            else:

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
                            # Swap x and y if --ro flag is set
                            if getattr(args, 'ro', False):
                                ln_d, = ax.plot(yd_b, xd_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                                linewidth=2.0, label=lbl, alpha=0.8)
                            else:

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
                            # Swap x and y if --ro flag is set
                            if getattr(args, 'ro', False):
                                ln_c, = ax.plot(y_b, x_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                                linewidth=2.0, label=str(cyc), alpha=0.8)
                            else:

                                ln_c, = ax.plot(x_b, y_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                            linewidth=2.0, label=str(cyc), alpha=0.8)
                        ln_d = None
                        if i < len(dch_blocks):
                            a, b = dch_blocks[i]
                            idx = np.arange(a, b + 1)
                            xd_b, yd_b = _broken_arrays_from_indices(idx, cap_x, voltage)
                            lbl = '_nolegend_' if ln_c is not None else str(cyc)
                            # Swap x and y if --ro flag is set
                            if getattr(args, 'ro', False):
                                ln_d, = ax.plot(yd_b, xd_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                                linewidth=2.0, label=lbl, alpha=0.8)
                            else:

                                ln_d, = ax.plot(xd_b, yd_b, '-', color=base_colors[(cyc-1) % len(base_colors)],
                                            linewidth=2.0, label=lbl, alpha=0.8)
                        cycle_lines[cyc] = {"charge": ln_c, "discharge": ln_d}
                # Labels with consistent labelpad
                # Swap axis labels if --ro flag is set
                if getattr(args, 'ro', False):
                    ax.set_xlabel('Voltage (V)', labelpad=8.0)
                    ax.set_ylabel(x_label_gc, labelpad=8.0)
                else:
                    ax.set_xlabel(x_label_gc, labelpad=8.0)
                    ax.set_ylabel('Voltage (V)', labelpad=8.0)
                legend = ax.legend(title='Cycle')
                if legend is not None:
                    try:
                        legend.set_frame_on(False)
                    except Exception:
                        pass
                legend.get_title().set_fontsize('medium')
                fig._ec_legend_title = "Cycle"
                # No background grid by default for GC plots
            
                # Adjust layout to ensure top and bottom labels/titles are visible
                fig.subplots_adjust(left=0.12, right=0.95, top=0.88, bottom=0.15)
                
                # Apply style file if provided
                if style_cfg:
                    try:
                        _apply_ec_style(fig, ax, style_cfg)
                        # Redraw after applying style
                        fig.canvas.draw() if hasattr(fig, 'canvas') else None
                    except Exception as e:
                        print(f"Warning: Error applying style file: {e}")

                # Save if requested
                if len(data_files) > 1 and (args.savefig or args.out):
                    # Multiple files: save to Figures/ directory
                    base_name = os.path.splitext(os.path.basename(ec_file))[0]
                    output_format = getattr(args, 'format', 'svg')
                    outname = os.path.join(out_dir or "", f"{base_name}.{output_format}")
                else:
                    outname = args.savefig or args.out
                if outname:
                    if not os.path.splitext(outname)[1]:
                        outname += '.svg'
                    # Transparent background for SVG exports
                    _, _ext = os.path.splitext(outname)
                    if _ext.lower() == '.svg':
                        # Fix for Affinity Designer/Photo compatibility issues
                        # Use 'none' to embed fonts as text (not paths) - prevents phantom labels
                        # Set hashsalt to empty to avoid duplicate text elements
                        plt.rcParams['svg.fonttype'] = 'none'
                        plt.rcParams['svg.hashsalt'] = None
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
                        # Turn on interactive mode and show non-blocking window
                        try:
                            plt.ion()
                        except Exception:
                            pass
                        plt.show(block=False)
                        try:
                            fig._bp_source_paths = [os.path.abspath(ec_file)]
                        except Exception:
                            pass
                        try:
                            electrochem_interactive_menu(fig, ax, cycle_lines, file_path=ec_file)
                        except Exception as _ie:
                            print(f"Interactive menu failed: {_ie}")
                        # Keep window open after menu
                        plt.show()
                else:
                    if not (args.savefig or args.out):
                        # Only show when a GUI backend is available
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
                # For multiple files, close the figure and continue to next file
                if len(data_files) > 1:
                    plt.close(fig)
                    continue
                else:
                    exit()
            except Exception as _e:
                print(f"GC plot failed for {ec_file}: {_e}")
                if len(data_files) > 1:
                    continue
                else:
                    exit(1)
        # Exit after processing all files
        if len(data_files) > 1:
            print(f"Processed {len(data_files)} GC files.")
            exit()

    # Capacity-per-cycle (CPC) summary from CSV or .mpt with coulombic efficiency
    if getattr(args, 'cpc', False):
        # Separate style files from data files
        data_files = []
        style_file_path = None
        for f in args.files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ('.bps', '.bpsg', '.bpcfg'):
                if style_file_path is None:
                    style_file_path = f
                else:
                    print(f"Warning: Multiple style files provided, using first: {style_file_path}")
            else:
                data_files.append(f)
        
        if len(data_files) < 1:
            print("CPC mode: provide at least one file (.csv, .xlsx, or .mpt).")
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
        
        # Process multiple files
        file_data = []  # List of dicts with file info and data
        # Use tab10 for capacity and viridis for efficiency
        n_files = len(data_files)
        
        # Use tab10 hardcoded colors for capacity (matching interactive menu)
        default_tab10_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                               '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        if n_files <= 1:
            capacity_colors = [default_tab10_colors[0]]
            eff_positions = [0.55]
        else:
            capacity_colors = [default_tab10_colors[i % len(default_tab10_colors)] for i in range(n_files)]
            eff_positions = np.linspace(0.08, 0.88, n_files)
        
        # Use viridis for efficiency
        efficiency_cmap = cm.get_cmap('viridis')
        efficiency_colors = [mcolors.rgb2hex(efficiency_cmap(pos)[:3]) for pos in eff_positions]
        
        for file_idx, ec_file in enumerate(data_files):
            if not os.path.isfile(ec_file):
                print(f"File not found: {ec_file}")
                continue

            ext = os.path.splitext(ec_file)[1].lower()
            file_basename = os.path.basename(ec_file)
            
            try:
                if ext in ['.csv', '.xlsx', '.xls']:
                    # Check if this is CS-B format
                    try:
                        header, _, _ = _load_csv_header_and_rows(ec_file)
                        if is_cs_b_format(header):
                            # Use CS-B format reader for CPC
                            cyc_nums, cap_charge, cap_discharge, eff = read_cs_b_csv_file(ec_file, mode='cpc')
                        else:
                            # Use standard CSV reader
                            cap_x, voltage, cycles, chg_mask, dchg_mask = read_ec_csv_file(ec_file, prefer_specific=True)
                            cyc = np.array(cycles, dtype=int)
                            unique_cycles = np.unique(cyc)
                            unique_cycles = unique_cycles[np.isfinite(unique_cycles)]
                            unique_cycles = [int(x) for x in unique_cycles]
                            if not unique_cycles:
                                unique_cycles = [1]
                            cyc_nums = []
                            cap_charge = []
                            cap_discharge = []
                            eff = []
                            for c in sorted(unique_cycles):
                                m_c = (cyc == c)
                                qchg = np.nanmax(cap_x[m_c & chg_mask]) if np.any(m_c & chg_mask) else np.nan
                                qdch = np.nanmax(cap_x[m_c & dchg_mask]) if np.any(m_c & dchg_mask) else np.nan
                                eta = (qdch / qchg * 100.0) if (np.isfinite(qchg) and qchg > 0 and np.isfinite(qdch)) else np.nan
                                cyc_nums.append(c)
                                cap_charge.append(qchg)
                                cap_discharge.append(qdch)
                                eff.append(eta)
                            cyc_nums = np.array(cyc_nums, dtype=float)
                            cap_charge = np.array(cap_charge, dtype=float)
                            cap_discharge = np.array(cap_discharge, dtype=float)
                            eff = np.array(eff, dtype=float)
                    except Exception as e:
                        # Fallback to standard reader
                        cap_x, voltage, cycles, chg_mask, dchg_mask = read_ec_csv_file(ec_file, prefer_specific=True)
                        cyc = np.array(cycles, dtype=int)
                        unique_cycles = np.unique(cyc)
                        unique_cycles = unique_cycles[np.isfinite(unique_cycles)]
                        unique_cycles = [int(x) for x in unique_cycles]
                        if not unique_cycles:
                            unique_cycles = [1]
                        cyc_nums = []
                        cap_charge = []
                        cap_discharge = []
                        eff = []
                        for c in sorted(unique_cycles):
                            m_c = (cyc == c)
                            qchg = np.nanmax(cap_x[m_c & chg_mask]) if np.any(m_c & chg_mask) else np.nan
                            qdch = np.nanmax(cap_x[m_c & dchg_mask]) if np.any(m_c & dchg_mask) else np.nan
                            eta = (qdch / qchg * 100.0) if (np.isfinite(qchg) and qchg > 0 and np.isfinite(qdch)) else np.nan
                            cyc_nums.append(c)
                            cap_charge.append(qchg)
                            cap_discharge.append(qdch)
                            eff.append(eta)
                        cyc_nums = np.array(cyc_nums, dtype=float)
                        cap_charge = np.array(cap_charge, dtype=float)
                        cap_discharge = np.array(cap_discharge, dtype=float)
                        eff = np.array(eff, dtype=float)
                elif ext == '.mpt':
                    mass_mg = getattr(args, 'mass', None)
                    if mass_mg is None:
                        print(f"Skipped {file_basename}: CPC mode (.mpt) requires --mass parameter.")
                        continue
                    cyc_nums, cap_charge, cap_discharge, eff = read_mpt_file(ec_file, mode='cpc', mass_mg=mass_mg)
                else:
                    print(f"Skipped {file_basename}: unsupported format (must be .csv, .xlsx, or .mpt)")
                    continue
                
                # Assign colors: distinct hue per file
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
            color = file_info['color']  # Base color for capacity (both charge/discharge)
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
            
            # Capacity curves: same color, different fill style
            # - Charge: filled square
            # - Discharge: hollow square (edge only)
            sc_charge = ax.scatter(
                cyc_nums,
                cap_charge,
                label=label_chg,
                s=32,
                zorder=3,
                alpha=0.8,
                marker='s',
                color=color,
            )
            sc_discharge = ax.scatter(
                cyc_nums,
                cap_discharge,
                label=label_dch,
                s=32,
                zorder=3,
                alpha=0.8,
                marker='s',
                facecolor='none',
                edgecolor=color,
            )
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
            combined_handles = h1 + h2
            combined_labels = l1 + l2
            if combined_handles:
                # Don't use labelcolor='linecolor' for scatter plots with hollow markers
                # as it causes issues with color extraction
                leg = ax.legend(
                    combined_handles, combined_labels,
                    loc='best',
                    frameon=False,
                    handlelength=1.0,
                    handletextpad=0.35,
                    labelspacing=0.25,
                    borderaxespad=0.5,
                    borderpad=0.3,
                    columnspacing=0.6,
                )
        except Exception as e:
            print(f"Warning: Could not create CPC legend: {e}")

        # Adjust layout to ensure top and bottom labels/titles are visible
        fig.subplots_adjust(left=0.12, right=0.88, top=0.88, bottom=0.15)
        
        # Check for style file in file list
        style_file_path = None
        for f in args.files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ('.bps', '.bpsg', '.bpcfg'):
                style_file_path = f
                break
        
        # Load and apply style file if provided
        if style_file_path:
            if os.path.isfile(style_file_path):
                try:
                    with open(style_file_path, 'r', encoding='utf-8') as f:
                        style_cfg = json.load(f)
                    print(f"Using style file: {os.path.basename(style_file_path)}")
                    _apply_ec_style(fig, ax, style_cfg)
                    # Also apply to twin axis
                    _apply_ec_style(fig, ax2, style_cfg)
                    # Redraw after applying style
                    if hasattr(fig, 'canvas'):
                        fig.canvas.draw()
                except Exception as e:
                    print(f"Warning: Error applying style file: {e}")
            else:
                print(f"Warning: Style file not found: {style_file_path}")
    
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
                    # Always pass file_data so filename is available
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
        # Separate style files from data files
        data_files = []
        style_file_path = None
        for f in args.files:
            ext = os.path.splitext(f)[1].lower()
            if ext in ('.bps', '.bpsg', '.bpcfg'):
                if style_file_path is None:
                    style_file_path = f
                else:
                    print(f"Warning: Multiple style files provided, using first: {style_file_path}")
            else:
                data_files.append(f)
        
        if not data_files:
            print("dQ/dV mode: no data files found (only style files provided).")
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
        
        # Process each data file
        out_dir = None
        if len(data_files) > 1 and (args.savefig or args.out):
            # Multiple files: create output directory
            out_dir = ensure_subdirectory('Figures', os.getcwd())

        def _mask_segments(mask: np.ndarray, role: str):
            inds = np.where(mask)[0]
            if inds.size == 0:
                return []
            segs = []
            start, prev = inds[0], inds[0]
            for idx in inds[1:]:
                if idx == prev + 1:
                    prev = idx
                else:
                    segs.append((start, prev, role))
                    start, prev = idx, idx
            segs.append((start, prev, role))
            return segs

        # dQ/dV multi-file: one figure with all files overlaid (same for interactive and non-interactive)
        if len(data_files) > 1:
            fig, ax = plt.subplots(figsize=(10, 6))
            ax._is_dqdv_mode = True
            file_data = []
            base_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                           '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
            y_label_used = None
            for file_idx, ec_file in enumerate(data_files):
                if not os.path.isfile(ec_file) or not (ec_file.lower().endswith('.csv') or ec_file.lower().endswith('.mpt')):
                    continue
                try:
                    if ec_file.lower().endswith('.mpt'):
                        mass_mg = getattr(args, 'mass', None)
                        if mass_mg is None or mass_mg <= 0:
                            continue
                        voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = read_mpt_dqdv_file(ec_file, mass_mg=mass_mg, prefer_specific=True)
                    else:
                        try:
                            header, _, _ = _load_csv_header_and_rows(ec_file)
                            if is_cs_b_format(header):
                                voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = read_cs_b_csv_file(ec_file, mode='dqdv')
                            else:
                                voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = read_ec_csv_dqdv_file(ec_file, prefer_specific=True)
                        except Exception:
                            voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = read_ec_csv_dqdv_file(ec_file, prefer_specific=True)
                    if y_label_used is None:
                        y_label_used = y_label
                    segments = _mask_segments(charge_mask, 'charge') + _mask_segments(discharge_mask, 'discharge')
                    segments.sort(key=lambda x: x[0])
                    cycle_lines = {}
                    cycle_id = 1
                    cycle_lines[cycle_id] = {"charge": None, "discharge": None}
                    color_offset = (file_idx * 5) % len(base_colors)

                    def _append_segment(line_obj, x_new, y_new):
                        try:
                            x_old = np.asarray(line_obj.get_xdata(), float)
                            y_old = np.asarray(line_obj.get_ydata(), float)
                            x_cat = np.concatenate([x_old, np.array([np.nan]), x_new])
                            y_cat = np.concatenate([y_old, np.array([np.nan]), y_new])
                            line_obj.set_xdata(x_cat)
                            line_obj.set_ydata(y_cat)
                        except Exception:
                            pass

                    for start, end, role in segments:
                        if end - start + 1 < 2:
                            continue
                        idx = np.arange(start, end + 1)
                        x_seg, y_seg = voltage[idx], dqdv[idx]
                        current = cycle_lines.setdefault(cycle_id, {"charge": None, "discharge": None})
                        color = base_colors[(color_offset + cycle_id - 1) % len(base_colors)]
                        first_seg = current['charge'] is None and current['discharge'] is None
                        if current[role] is not None:
                            if current['charge'] and current['discharge']:
                                cycle_id += 1
                                current = cycle_lines.setdefault(cycle_id, {"charge": None, "discharge": None})
                            else:
                                if getattr(args, 'ro', False):
                                    _append_segment(current[role], y_seg, x_seg)
                                else:
                                    _append_segment(current[role], x_seg, y_seg)
                                continue
                        # Multi-file: label as "filename: cycle" so legend reflects data
                        file_lbl = os.path.basename(ec_file) if len(data_files) > 1 else ""
                        label = (f"{file_lbl}: {cycle_id}" if file_lbl else str(cycle_id)) if first_seg else '_nolegend_'
                        if getattr(args, 'ro', False):
                            ln, = ax.plot(y_seg, x_seg, '-', color=color, linewidth=2.0, label=label, alpha=0.8)
                        else:
                            ln, = ax.plot(x_seg, y_seg, '-', color=color, linewidth=2.0, label=label, alpha=0.8)
                        current[role] = ln
                        if current['charge'] and current['discharge']:
                            cycle_id += 1
                    if cycle_lines.get(cycle_id) == {"charge": None, "discharge": None}:
                        cycle_lines.pop(cycle_id, None)
                    file_data.append({
                        'filename': os.path.basename(ec_file),
                        'display_name': os.path.basename(ec_file),
                        'cycle_lines': cycle_lines,
                        'visible': True,
                        'filepath': ec_file,
                    })
                except Exception as _e:
                    print(f"dQ/dV multi-file: skip {ec_file}: {_e}")
            if not file_data:
                print("dQ/dV multi-file: no files loaded.")
                exit(1)
            if getattr(args, 'ro', False):
                ax.set_xlabel(y_label_used or 'dQ/dV', labelpad=8.0)
                ax.set_ylabel('Voltage (V)', labelpad=8.0)
            else:
                ax.set_xlabel('Voltage (V)', labelpad=8.0)
                ax.set_ylabel(y_label_used or 'dQ/dV', labelpad=8.0)
            ax.legend(title='Cycle')
            fig._ec_legend_title = "Cycle"
            fig.subplots_adjust(left=0.12, right=0.95, top=0.88, bottom=0.15)
            if style_cfg:
                try:
                    _apply_ec_style(fig, ax, style_cfg)
                    if hasattr(fig, 'canvas'):
                        fig.canvas.draw()
                except Exception as e:
                    print(f"Warning: Error applying style file: {e}")
            try:
                plt.ion()
            except Exception:
                pass
            plt.show(block=False)
            try:
                fig._bp_source_paths = [os.path.abspath(f.get('filepath', '')) for f in file_data if f.get('filepath')]
            except Exception:
                pass
            if args.interactive:
                try:
                    electrochem_interactive_menu(fig, ax, file_data=file_data)
                except Exception as _ie:
                    print(f"Interactive menu failed: {_ie}")
                plt.show()
            else:
                if out_dir and (args.savefig or getattr(args, 'out', None)):
                    out_path = getattr(args, 'out', None)
                    if not out_path:
                        ext = getattr(args, 'format', 'svg') or 'svg'
                        out_path = os.path.join(out_dir, f'dQdV_combined.{ext}')
                    try:
                        fig.savefig(out_path, dpi=300, bbox_inches='tight')
                        print(f"Saved {out_path}")
                    except Exception as e:
                        print(f"Could not save: {e}")
                try:
                    plt.ioff()
                except Exception:
                    pass
                print(f"Processed {len(file_data)} dQ/dV files.")
                plt.show(block=True)
            exit(0)

        for ec_file in data_files:
            if not os.path.isfile(ec_file):
                print(f"File not found: {ec_file}")
                continue
            if not (ec_file.lower().endswith('.csv') or ec_file.lower().endswith('.mpt')):
                print(f"dQ/dV mode: file must be a supported cycler .csv or .mpt export: {ec_file}")
                continue
            
            try:
                # Load voltage, dQ/dV, cycles, and charge/discharge masks
                if ec_file.lower().endswith('.mpt'):
                    # .mpt files require mass for dQ/dV calculation
                    mass_mg = getattr(args, 'mass', None)
                    if mass_mg is None or mass_mg <= 0:
                        print(f"dQ/dV mode (.mpt): --mass parameter is required (active material mass in milligrams).")
                        print(f"Example: batplot {ec_file} --dqdv --mass 7.0")
                        continue
                    voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = read_mpt_dqdv_file(ec_file, mass_mg=mass_mg, prefer_specific=True)
                else:
                    # Check if this is CS-B format
                    try:
                        header, _, _ = _load_csv_header_and_rows(ec_file)
                        if is_cs_b_format(header):
                            # Use CS-B format reader
                            voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = read_cs_b_csv_file(ec_file, mode='dqdv')
                        else:
                            # Use standard CSV reader
                            voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = read_ec_csv_dqdv_file(ec_file, prefer_specific=True)
                    except Exception:
                        # Fallback to standard reader
                        voltage, dqdv, cycles, charge_mask, discharge_mask, y_label = read_ec_csv_dqdv_file(ec_file, prefer_specific=True)

                # Create the plot
                fig, ax = plt.subplots(figsize=(10, 6))

                segments = _mask_segments(charge_mask, 'charge') + _mask_segments(discharge_mask, 'discharge')
                segments.sort(key=lambda item: item[0])

                base_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                               '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

                cycle_lines = {}
                ax._is_dqdv_mode = True
                cycle_id = 1
                cycle_lines[cycle_id] = {"charge": None, "discharge": None}

                def _append_segment(line_obj, x_new, y_new):
                    try:
                        x_old = np.asarray(line_obj.get_xdata(), float)
                        y_old = np.asarray(line_obj.get_ydata(), float)
                        x_cat = np.concatenate([x_old, np.array([np.nan]), x_new])
                        y_cat = np.concatenate([y_old, np.array([np.nan]), y_new])
                        line_obj.set_xdata(x_cat)
                        line_obj.set_ydata(y_cat)
                    except Exception:
                        pass

                for start, end, role in segments:
                    if end - start + 1 < 2:
                        continue
                    idx = np.arange(start, end + 1)
                    x_seg = voltage[idx]
                    y_seg = dqdv[idx]
                    current = cycle_lines.setdefault(cycle_id, {"charge": None, "discharge": None})
                    color = base_colors[(cycle_id - 1) % len(base_colors)]
                    first_segment = current['charge'] is None and current['discharge'] is None

                    if current[role] is not None:
                        if current['charge'] is not None and current['discharge'] is not None:
                            cycle_id += 1
                            current = cycle_lines.setdefault(cycle_id, {"charge": None, "discharge": None})
                        else:
                            # Swap x and y if --ro flag is set when appending segment
                            if getattr(args, 'ro', False):
                                _append_segment(current[role], y_seg, x_seg)
                            else:
                                _append_segment(current[role], x_seg, y_seg)
                            continue

                    label = str(cycle_id) if first_segment else '_nolegend_'
                    # Swap x and y if --ro flag is set
                    if getattr(args, 'ro', False):
                        ln, = ax.plot(y_seg, x_seg, '-', color=color, linewidth=2.0, label=label, alpha=0.8)
                    else:
                        ln, = ax.plot(x_seg, y_seg, '-', color=color, linewidth=2.0, label=label, alpha=0.8)
                    current[role] = ln

                    if current['charge'] is not None and current['discharge'] is not None:
                        cycle_id += 1

                if cycle_lines.get(cycle_id) == {"charge": None, "discharge": None}:
                    cycle_lines.pop(cycle_id, None)

                # Labels with consistent labelpad (same as GC/CPC)
                # Swap axis labels if --ro flag is set
                if getattr(args, 'ro', False):
                    ax.set_xlabel(y_label, labelpad=8.0)
                    ax.set_ylabel('Voltage (V)', labelpad=8.0)
                else:

                    ax.set_xlabel('Voltage (V)', labelpad=8.0)
                ax.set_ylabel(y_label, labelpad=8.0)
                legend = ax.legend(title='Cycle')
                if legend is not None:
                    try:
                        legend.set_frame_on(False)
                    except Exception:
                        pass
                legend.get_title().set_fontsize('medium')
                fig._ec_legend_title = "Cycle"
                # No background grid by default (same as GC)
            
                # Adjust layout to ensure top and bottom labels/titles are visible (same as GC/CPC)
                fig.subplots_adjust(left=0.12, right=0.95, top=0.88, bottom=0.15)
                
                # Apply style file if provided
                if style_cfg:
                    try:
                        _apply_ec_style(fig, ax, style_cfg)
                        # Redraw after applying style
                        if hasattr(fig, 'canvas'):
                            fig.canvas.draw()
                    except Exception as e:
                        print(f"Warning: Error applying style file: {e}")

                # Save if requested
                if len(data_files) > 1 and (args.savefig or args.out):
                    # Multiple files: save to Figures/ directory
                    base_name = os.path.splitext(os.path.basename(ec_file))[0]
                    output_format = getattr(args, 'format', 'svg')
                    outname = os.path.join(out_dir or "", f"{base_name}.{output_format}")
                else:
                    outname = args.savefig or args.out
                if outname:
                    if not os.path.splitext(outname)[1]:
                        outname += '.svg'
                    _, _ext = os.path.splitext(outname)
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
                            fig._bp_source_paths = [os.path.abspath(ec_file)]
                        except Exception:
                            pass
                        try:
                            electrochem_interactive_menu(fig, ax, cycle_lines, file_path=ec_file)
                        except Exception as _ie:
                            print(f"Interactive menu failed: {_ie}")
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
                # For multiple files, close the figure and continue to next file
                if len(data_files) > 1:
                    plt.close(fig)
                    continue
                else:
                    exit()
            except Exception as _e:
                print(f"dQ/dV plot failed for {ec_file}: {_e}")
                if len(data_files) > 1:
                    continue
                else:
                    exit(1)
        # Exit after processing all files
        if len(data_files) > 1:
            print(f"Processed {len(data_files)} dQ/dV files.")
            exit(0)

    # Operando contour plotting mode (folder-based)
    if getattr(args, 'operando', False):
        try:
            # Determine target folder and optional CIF files
            # Usage: batplot folder [phase.cif:1.54 ...] --operando -i
            folder = None
            cif_files = []
            for f in args.files:
                if os.path.isdir(f):
                    if folder is None:
                        folder = os.path.abspath(f)
                    else:
                        print("Operando mode: provide at most one folder.")
                        exit(1)
                else:
                    # CIF file (optionally with :wl), e.g. phase.cif:1.54
                    parts = f.split(":")
                    if len(parts) >= 1:
                        fname = parts[0]
                        if len(parts) > 1 and len(parts[0]) == 1 and parts[0].isalpha():
                            # Windows drive letter: C:\path\to\file.cif:1.54
                            fname = parts[0] + ":" + parts[1]
                            parts = [fname] + (parts[2:] if len(parts) > 2 else [])
                        if os.path.splitext(fname)[1].lower() == '.cif':
                            cif_files.append(f)
            if folder is None:
                folder = os.getcwd()

            # Build plot (pass cif_files for CIF tick labels)
            fig, ax, meta = plot_operando_folder(folder, args, cif_files=cif_files)
            im = meta.get('imshow')
            cbar = meta.get('colorbar')
            has_ec = bool(meta.get('has_ec'))
            ec_ax = meta.get('ec_ax') if has_ec else None

            # Save if requested
            outname = args.savefig or args.out
            if outname:
                if not os.path.splitext(outname)[1]:
                    outname += '.svg'
                _, _ext = os.path.splitext(outname)
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
                    _backend = plt.get_backend()
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
                        plt.ion()
                    except Exception:
                        pass
                    try:
                        plt.show(block=False)
                    except Exception:
                        pass
                    try:
                        # Call interactive menu regardless of EC presence
                        # When ec_ax is None, EC-related commands will be disabled
                        if operando_ec_interactive_menu is not None:
                            operando_ec_interactive_menu(fig, ax, im, cbar, ec_ax, file_paths=args.files)
                        else:
                            print("Interactive menu not available.")
                    except Exception as _ie:
                        print(f"Interactive menu failed: {_ie}")
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
            exit()
        except Exception as _e:
            print(f"Operando plot failed: {_e}")
            exit(1)

    _maybe_expand_allfiles_argument(args, ec_mode_active)

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
        except ModuleNotFoundError as e:
            # Handle numpy._core and other module import errors
            if '_core' in str(e) or 'numpy' in str(e).lower():
                # Try to extract version info before the error
                saved_versions = _try_extract_version_from_pickle(sess_path)
                current_numpy = _get_current_numpy_version()
                
                saved_numpy = saved_versions.get('numpy', 'unknown')
                
                print(f"\nERROR: NumPy version mismatch detected when loading: {sess_path}")
                print("This session was saved with a different NumPy version.")
                print()
                print(f"Session was saved with:  NumPy {saved_numpy}")
                print(f"Currently installed:     NumPy {current_numpy}")
                print()
                print("The error 'No module named numpy._core' indicates:")
                print("  - Session saved with NumPy 2.0+ but loading with NumPy <2.0, OR")
                print("  - Session saved with NumPy <2.0 but loading with NumPy 2.0+")
                print()
                print("Solutions:")
                if saved_numpy != 'unknown':
                    print(f"  1. Install matching version: pip install 'numpy=={saved_numpy}'")
                else:
                    print("  1. Try installing NumPy <2.0: pip install 'numpy<2.0'")
                    print("     OR try installing NumPy 2.0+: pip install 'numpy>=2.0'")
                print("  2. Recreate the session from original data files")
            else:
                print(f"\nERROR: Module import error when loading: {sess_path}")
                print(f"Error: {e}")
                print("This usually indicates a package version mismatch.")
            exit(1)
        except Exception as e:
            print(f"Failed to load session: {e}")
            exit(1)
        # If it's an EC GC session, load and open EC interactive menu directly
        if isinstance(sess, dict) and sess.get('kind') == 'ec_gc':
            try:
                res = load_ec_session(sess_path)
                if not res:
                    print("Failed to load EC session.")
                    exit(1)
                # Multi-file session returns (fig, ax, None, file_data); single-file returns (fig, ax, cycle_lines)
                if len(res) == 4 and res[2] is None:
                    fig, ax, _ignored, file_data = res
                    try:
                        plt.ion()
                    except Exception:
                        pass
                    try:
                        plt.show(block=False)
                    except Exception:
                        pass
                    try:
                        fig._last_session_save_path = os.path.abspath(sess_path)
                    except Exception:
                        pass
                    try:
                        source_list = list(getattr(fig, '_bp_source_paths', []) or [])
                        sess_abs = os.path.abspath(sess_path)
                        if sess_abs not in source_list:
                            source_list.append(sess_abs)
                        fig._bp_source_paths = source_list
                    except Exception:
                        pass
                    try:
                        electrochem_interactive_menu(fig, ax, file_data=file_data)
                    except Exception as _ie:
                        print(f"Interactive menu failed: {_ie}")
                else:
                    fig, ax, cycle_lines = res
                    try:
                        plt.ion()
                    except Exception:
                        pass
                    try:
                        plt.show(block=False)
                    except Exception:
                        pass
                    try:
                        fig._last_session_save_path = os.path.abspath(sess_path)
                    except Exception:
                        pass
                    try:
                        source_list = list(getattr(fig, '_bp_source_paths', []) or [])
                        sess_abs = os.path.abspath(sess_path)
                        if sess_abs not in source_list:
                            source_list.append(sess_abs)
                        fig._bp_source_paths = source_list
                    except Exception:
                        pass
                    try:
                        electrochem_interactive_menu(fig, ax, cycle_lines, file_path=sess_path)
                    except Exception as _ie:
                        print(f"Interactive menu failed: {_ie}")
                plt.show()
                exit()
            except Exception as e:
                print(f"EC session load failed: {e}")
                exit(1)
        # If it's an operando+EC session, load and open the combined interactive menu
        if isinstance(sess, dict) and sess.get('kind') == 'operando_ec':
            try:
                res = load_operando_session(sess_path)
                if not res:
                    print("Failed to load operando+EC session.")
                    exit(1)
                fig2, ax2, im2, cbar2, ec_ax2 = res
                # Always open interactive menu for session files
                try:
                    plt.ion()
                except Exception:
                    pass
                try:
                    plt.show(block=False)
                except Exception:
                    pass
                # Seed last-session path so 'os' overwrite command is available immediately
                try:
                    fig2._last_session_save_path = os.path.abspath(sess_path)
                except Exception:
                    pass
                try:
                    if operando_ec_interactive_menu is not None:
                        operando_ec_interactive_menu(fig2, ax2, im2, cbar2, ec_ax2)
                except Exception as _ie:
                    print(f"Interactive menu failed: {_ie}")
                plt.show()
                exit()
            except Exception as e:
                print(f"Operando+EC session load failed: {e}")
                exit(1)

        # If it's a CPC session, load and open CPC interactive menu
        if isinstance(sess, dict) and sess.get('kind') == 'cpc':
            try:
                res = load_cpc_session(sess_path)
                if not res:
                    print("Failed to load CPC session.")
                    exit(1)
                fig_c, ax_c, ax2_c, sc_c, sc_d, sc_e, file_data = res
                try:
                    plt.ion()
                except Exception:
                    pass
                try:
                    plt.show(block=False)
                except Exception:
                    pass
                # Seed last-session path so 'os' overwrite command is available immediately
                try:
                    fig_c._last_session_save_path = os.path.abspath(sess_path)
                except Exception:
                    pass
                try:
                    if cpc_interactive_menu is not None:
                        cpc_interactive_menu(fig_c, ax_c, ax2_c, sc_c, sc_d, sc_e, file_data=file_data)
                except Exception as _ie:
                    print(f"CPC interactive menu failed: {_ie}")
                plt.show()
                exit()
            except Exception as e:
                print(f"CPC session load failed: {e}")
                exit(1)

        # Reconstruct minimal state and go to interactive if requested
        plt.ion() if args.interactive else None
        fig, ax = plt.subplots(figsize=(8,6))
        # Restore ro flag from session (if present) so style/geom imports can enforce compatibility
        try:
            fig._ro_active = bool(sess.get('ro_active', False))
        except Exception:
            pass
        y_data_list = []
        x_data_list = []
        labels_list = []
        orig_y = []
        label_text_objects = []
        x_full_list = []
        raw_y_full_list = []
        offsets_list = []
        # Load tick_state from wasd_state if available (version 2+), otherwise use defaults
        wasd_loaded = sess.get('wasd_state')
        if wasd_loaded and isinstance(wasd_loaded, dict):
            # Convert wasd_state to tick_state format
            tick_state = {}
            for side_key, prefix in [('top', 't'), ('bottom', 'b'), ('left', 'l'), ('right', 'r')]:
                s = wasd_loaded.get(side_key, {})
                tick_state[f'{prefix}_ticks'] = bool(s.get('ticks', side_key in ('bottom', 'left')))
                tick_state[f'{prefix}_labels'] = bool(s.get('labels', side_key in ('bottom', 'left')))
                tick_state[f'm{prefix}x' if prefix in 'tb' else f'm{prefix}y'] = bool(s.get('minor', False))
            # Legacy keys for backward compatibility
            tick_state['bx'] = tick_state.get('b_ticks', True)
            tick_state['tx'] = tick_state.get('t_ticks', False)
            tick_state['ly'] = tick_state.get('l_ticks', True)
            tick_state['ry'] = tick_state.get('r_ticks', False)
            tick_state['mbx'] = tick_state.get('mbx', False)
            tick_state['mtx'] = tick_state.get('mtx', False)
            tick_state['mly'] = tick_state.get('mly', False)
            tick_state['mry'] = tick_state.get('mry', False)
        else:
            # Fallback to legacy tick_state or defaults
            tick_state = sess.get('tick_state', {
                'bx': True,'tx': False,'ly': True,'ry': False,
                'mbx': False,'mtx': False,'mly': False,'mry': False
            })
        saved_stack = bool(sess.get('args_subset', {}).get('stack', False))
        # Pull data
        # --- Robust reconstruction of stored curves ---
        x_loaded = sess.get('x_data', [])
        y_loaded = sess.get('y_data', [])  # stored plotted (baseline+offset) values
        orig_loaded = sess.get('orig_y', [])  # stored baseline (normalized/raw w/out offsets)
        offsets_saved = sess.get('offsets', [])
        # Restore processed data (for smooth/reduce operations)
        original_x_data_list = sess.get('original_x_data_list')
        original_y_data_list = sess.get('original_y_data_list')
        smooth_settings = sess.get('smooth_settings')
        if original_x_data_list is not None:
            fig._original_x_data_list = [np.array(a) for a in original_x_data_list]
        if original_y_data_list is not None:
            fig._original_y_data_list = [np.array(a) for a in original_y_data_list]
        full_processed_x_data_list = sess.get('full_processed_x_data_list')
        full_processed_y_data_list = sess.get('full_processed_y_data_list')
        if full_processed_x_data_list is not None:
            fig._full_processed_x_data_list = [np.array(a) for a in full_processed_x_data_list]
        if full_processed_y_data_list is not None:
            fig._full_processed_y_data_list = [np.array(a) for a in full_processed_y_data_list]
        if smooth_settings is not None:
            fig._smooth_settings = dict(smooth_settings)
        last_smooth_settings = sess.get('last_smooth_settings')
        if last_smooth_settings is not None:
            fig._last_smooth_settings = dict(last_smooth_settings)
        # Restore derivative data (for derivative operations)
        pre_derivative_x_data_list = sess.get('pre_derivative_x_data_list')
        pre_derivative_y_data_list = sess.get('pre_derivative_y_data_list')
        pre_derivative_ylabel = sess.get('pre_derivative_ylabel')
        derivative_order = sess.get('derivative_order')
        if pre_derivative_x_data_list is not None:
            fig._pre_derivative_x_data_list = [np.array(a) for a in pre_derivative_x_data_list]
        if pre_derivative_y_data_list is not None:
            fig._pre_derivative_y_data_list = [np.array(a) for a in pre_derivative_y_data_list]
        if pre_derivative_ylabel is not None:
            fig._pre_derivative_ylabel = str(pre_derivative_ylabel)
        if derivative_order is not None:
            fig._derivative_order = int(derivative_order)
        derivative_reversed = sess.get('derivative_reversed')
        if derivative_reversed is not None:
            fig._derivative_reversed = bool(derivative_reversed)
        n_curves = len(x_loaded)
        for i in range(n_curves):
            # Ensure arrays are 1D and have matching shapes
            x_arr = np.asarray(x_loaded[i], dtype=float).flatten()
            off = offsets_saved[i] if i < len(offsets_saved) else 0.0
            if orig_loaded and i < len(orig_loaded):
                base = np.asarray(orig_loaded[i], dtype=float).flatten()
            else:
                # Fallback: derive baseline by subtracting offset from stored y (handles legacy sessions)
                y_arr_full = np.asarray(y_loaded[i], dtype=float).flatten() if i < len(y_loaded) else np.array([], dtype=float)
                base = y_arr_full - off
            # Ensure x and y have matching lengths
            if x_arr.size != base.size:
                print(f"Warning: Curve {i+1} has mismatched x/y lengths ({x_arr.size} vs {base.size}). Trimming to match.")
                min_len = min(x_arr.size, base.size)
                x_arr = x_arr[:min_len]
                base = base[:min_len]
            y_plot = base + off
            x_data_list.append(x_arr)
            orig_y.append(base)
            y_data_list.append(y_plot)
            ax.plot(x_arr, y_plot, lw=1)
            x_full_list.append(x_arr.copy())
            raw_y_full_list.append(base.copy())
        offsets_list[:] = offsets_saved if offsets_saved else [0.0]*n_curves
        try:
            axes_bbox = sess.get('figure', {}).get('axes_bbox')
            if _session_apply_axes_bbox(ax, axes_bbox):
                try:
                    fig._skip_initial_text_visibility = True
                except Exception:
                    pass
        except Exception:
            pass
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
        # Apply tick state (labels visibility) BEFORE setting axis labels
        try:
            ax.tick_params(axis='x',
                          bottom=tick_state.get('b_ticks', tick_state.get('bx', True)),
                          labelbottom=tick_state.get('b_labels', tick_state.get('bx', True)),
                          top=tick_state.get('t_ticks', tick_state.get('tx', False)),
                          labeltop=tick_state.get('t_labels', tick_state.get('tx', False)))
            ax.tick_params(axis='y',
                          left=tick_state.get('l_ticks', tick_state.get('ly', True)),
                          labelleft=tick_state.get('l_labels', tick_state.get('ly', True)),
                          right=tick_state.get('r_ticks', tick_state.get('ry', False)),
                          labelright=tick_state.get('r_labels', tick_state.get('ry', False)))
        except Exception:
            pass
        ax.set_xlabel(sess.get('axis', {}).get('xlabel', 'X'))
        ax.set_ylabel(sess.get('axis', {}).get('ylabel', 'Intensity'))
        # Store tick_state on axes for interactive menu
        try:
            ax._saved_tick_state = dict(tick_state)
        except Exception:
            pass
        
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
                try:
                    fig._skip_initial_text_visibility = True
                except Exception:
                    pass
            
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
                    try:
                        fig._skip_initial_text_visibility = True
                    except Exception:
                        pass
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
        # Tick direction restore (t submenu)
        try:
            tick_direction = sess.get('tick_direction', 'out')
            if tick_direction:
                setattr(fig, '_tick_direction', tick_direction)
                ax.tick_params(axis='both', which='both', direction=tick_direction)
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
                          fontsize=plt.rcParams.get('font.size', 16))
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
        try:
            fig._label_anchor_left = bool(sess.get('label_anchor_left', False))
        except Exception:
            pass
        # Restore grid state
        try:
            grid_state = bool(sess.get('grid', False))
            if grid_state:
                ax.grid(True, color='0.85', linestyle='-', linewidth=0.5, alpha=0.7)
            else:
                ax.grid(False)
        except Exception:
            pass
        # CIF tick series (optional)
        cif_tick_series = sess.get('cif_tick_series') or []
        cif_hkl_map = {k: [tuple(v) for v in val] for k,val in sess.get('cif_hkl_map', {}).items()}
        cif_hkl_label_map = {k: dict(v) for k,v in sess.get('cif_hkl_label_map', {}).items()}
        cif_numbering_enabled = True
        cif_extend_suspended = False
        # Restore CIF visibility flags - default to False for hkl (labels hidden by default)
        # and True for titles (shown by default)
        show_cif_hkl = bool(sess.get('show_cif_hkl', False))
        show_cif_titles = bool(sess.get('show_cif_titles', True))
        
        # Store CIF state in __main__ module for interactive menu to access
        # This ensures CIF commands (z, hkl, j) are available in the menu
        try:
            _bp_module = sys.modules.get('__main__')
            if _bp_module is not None and cif_tick_series:
                setattr(_bp_module, 'cif_tick_series', list(cif_tick_series))
                setattr(_bp_module, 'cif_hkl_map', cif_hkl_map)
                setattr(_bp_module, 'cif_hkl_label_map', cif_hkl_label_map)
                setattr(_bp_module, 'show_cif_hkl', bool(show_cif_hkl))
                setattr(_bp_module, 'show_cif_titles', bool(show_cif_titles))
                setattr(_bp_module, 'cif_extend_suspended', False)
        except Exception:
            pass
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
                    # Preserve current limits before drawing - use actual current limits
                    # to prevent any movement when toggling
                    prev_xlim = ax.get_xlim()
                    prev_ylim = ax.get_ylim()
                    
                    # Use current ylim as fixed reference to prevent incremental movement
                    # This ensures that repeated 'z' commands don't cause drift
                    # Store it only once on first call, then reuse
                    if not hasattr(ax, '_cif_initial_ylim'):
                        ax._cif_initial_ylim = tuple(prev_ylim)
                    fixed_ylim = ax._cif_initial_ylim
                    fixed_yr = fixed_ylim[1] - fixed_ylim[0]
                    if fixed_yr <= 0: fixed_yr = 1.0
                    
                    # Check visibility flag first
                    show_titles_local = bool(show_cif_titles)  # Use closure variable from outer scope
                    # Also check figure attribute and module attribute as fallback
                    try:
                        # Check figure attribute first (from interactive menu)
                        if hasattr(fig, '_bp_show_cif_titles'):
                            show_titles_local = bool(getattr(fig, '_bp_show_cif_titles', show_titles_local))
                        # Check __main__ module (for backward compatibility)
                        _bp_module = sys.modules.get('__main__')
                        if _bp_module is not None and hasattr(_bp_module, 'show_cif_titles'):
                            show_titles_local = bool(getattr(_bp_module, 'show_cif_titles', show_titles_local))
                    except Exception:
                        pass
                    
                    # Check hkl visibility - check __main__ module first (where interactive menu stores it)
                    # then fall back to closure variable
                    show_hkl_local = False
                    try:
                        _bp_module = sys.modules.get('__main__')
                        if _bp_module is not None and hasattr(_bp_module, 'show_cif_hkl'):
                            show_hkl_local = bool(getattr(_bp_module, 'show_cif_hkl', False))
                    except Exception:
                        pass
                    # Fall back to closure variable if not found in module
                    if not show_hkl_local:
                        try:
                            show_hkl_local = bool(show_cif_hkl)
                        except Exception:
                            pass
                    
                    # Calculate base and spacing based on FIXED y-axis limits (not current)
                    # This prevents incremental movement when toggling
                    if saved_stack or len(y_data_list) > 1:
                        global_min = min(float(a.min()) for a in y_data_list if len(a)) if y_data_list else fixed_ylim[0]
                        base = global_min - 0.08*fixed_yr; spacing = 0.05*fixed_yr
                    else:
                        global_min = min(float(a.min()) for a in y_data_list if len(a)) if y_data_list else 0.0
                        base = global_min - 0.06*fixed_yr; spacing = 0.04*fixed_yr
                    
                    # Only adjust y-axis limits if titles are visible
                    needed_min = base - (len(cif_tick_series)-1)*spacing - 0.04*fixed_yr
                    if show_titles_local and needed_min < fixed_ylim[0]:
                        # Expand y-axis only if needed, using fixed limits as reference
                        ax.set_ylim(needed_min, fixed_ylim[1])
                    else:
                        # Restore to fixed limits if no expansion needed
                        ax.set_ylim(fixed_ylim)
                    
                    # Get current limits for drawing (after potential expansion)
                    cur_ylim = ax.get_ylim()
                    yr = cur_ylim[1] - cur_ylim[0]
                    if yr <= 0: yr = 1.0
                    
                    # Clear previous artifacts
                    for art in getattr(ax, '_cif_tick_art', []):
                        try: art.remove()
                        except Exception: pass
                    new_art = []
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
                        # Only use label_map if hkl labels are enabled
                        label_map = {}
                        if show_hkl_local:
                            label_map = cif_hkl_label_map.get(fname, {})
                        if show_hkl_local and len(domain_peaks) > 4000:
                            show_hkl_local = False  # safety
                            label_map = {}  # Clear label map if too many peaks
                        for p in domain_peaks:
                            # Use color from tuple (preserved from session)
                            ln, = ax.plot([p,p],[y_line, y_line+0.02*yr], color=color, lw=1.0, alpha=0.9, zorder=3)
                            new_art.append(ln)
                            # Only show hkl labels if explicitly enabled
                            if show_hkl_local:
                                # When axis is 2θ convert back to Q to look up hkl label
                                if use_2th and (wl or wl_any):
                                    theta = np.radians(p/2.0)
                                    Qp = 4*np.pi*np.sin(theta)/(wl if wl is not None else wl_any)
                                else:
                                    Qp = p
                                Qp_rounded = round(Qp, 6)
                                lbl = label_map.get(Qp_rounded)
                                if lbl:
                                    # Use same color as tick line
                                    t_hkl = ax.text(p, y_line+0.022*yr, lbl, ha='center', va='bottom', fontsize=7, rotation=90, color=color)
                                    new_art.append(t_hkl)
                        # Only add title label if show_cif_titles is True
                        if show_titles_local:
                            label_text = f" {lab}"
                            # Align CIF title baseline with tick baseline for this row
                            txt = ax.text(prev_xlim[0], y_line, label_text,
                                          ha='left', va='bottom', fontsize=max(8,int(0.55*plt.rcParams.get('font.size',16))), color=color)
                            new_art.append(txt)
                    ax._cif_tick_art = new_art
                    # Restore x-axis limits
                    ax.set_xlim(prev_xlim)
                    # Restore y-axis: if titles are hidden, always restore; if titles are shown, only restore if we didn't need to expand
                    # Use prev_ylim (current limits before drawing) to prevent any movement
                    if not show_titles_local:
                        # Titles hidden: always restore original limits
                        ax.set_ylim(prev_ylim)
                    elif needed_min >= prev_ylim[0]:
                        # Titles shown but no expansion needed: restore original limits
                        ax.set_ylim(prev_ylim)
                    else:
                        # Expansion needed: use the minimum of needed_min and prev_ylim[0] to prevent incremental growth
                        # This ensures that repeated toggles don't cause drift
                        new_ymin = min(needed_min, prev_ylim[0])
                        ax.set_ylim(new_ymin, prev_ylim[1])
                    fig.canvas.draw_idle()
                except Exception:
                    pass
            ax._cif_extend_func = _session_cif_extend
            ax._cif_draw_func = _session_cif_draw
            ax._cif_draw_func()

        # Restore axis title duplicates/visibility exactly as saved
        titles = sess.get('axis_titles', {})
        title_texts = sess.get('axis_title_texts', {})
        bottom_text = title_texts.get('bottom_x') or title_texts.get('bottom')
        left_text = title_texts.get('left_y') or title_texts.get('left')
        top_text = title_texts.get('top_x') or title_texts.get('top')
        right_text = title_texts.get('right_y') or title_texts.get('right')
        try:
            if bottom_text is not None:
                ax._stored_xlabel = bottom_text
            if left_text is not None:
                ax._stored_ylabel = left_text
            if top_text:
                ax._top_xlabel_text_override = top_text
            elif hasattr(ax, '_top_xlabel_text_override'):
                delattr(ax, '_top_xlabel_text_override')
            if right_text:
                ax._right_ylabel_text_override = right_text
            elif hasattr(ax, '_right_ylabel_text_override'):
                delattr(ax, '_right_ylabel_text_override')
            # Bottom X title
            if titles.get('has_bottom_x') is False:
                ax.xaxis.label.set_visible(False)
            else:
                ax.xaxis.label.set_visible(True)
                if bottom_text is not None:
                    ax.set_xlabel(bottom_text)
                elif hasattr(ax, '_stored_xlabel'):
                    ax.set_xlabel(ax._stored_xlabel)
            try:
                _ui_position_bottom_xlabel(ax, fig, tick_state)
            except Exception:
                pass
            # Left Y title
            if titles.get('has_left_y') is False:
                ax.yaxis.label.set_visible(False)
            else:
                ax.yaxis.label.set_visible(True)
                if left_text is not None:
                    ax.set_ylabel(left_text)
                elif hasattr(ax, '_stored_ylabel'):
                    ax.set_ylabel(ax._stored_ylabel)
            try:
                _ui_position_left_ylabel(ax, fig, tick_state)
            except Exception:
                pass
            # Top X duplicate
            ax._top_xlabel_on = bool(titles.get('top_x', False))
            try:
                _ui_position_top_xlabel(ax, fig, tick_state)
            except Exception:
                pass
            if not ax._top_xlabel_on and hasattr(ax, '_top_xlabel_artist') and ax._top_xlabel_artist is not None:
                try:
                    ax._top_xlabel_artist.set_visible(False)
                except Exception:
                    pass
            # Right Y duplicate
            ax._right_ylabel_on = bool(titles.get('right_y', False))
            try:
                _ui_position_right_ylabel(ax, fig, tick_state)
            except Exception:
                pass
            if not ax._right_ylabel_on and hasattr(ax, '_right_ylabel_artist') and ax._right_ylabel_artist is not None:
                try:
                    ax._right_ylabel_artist.set_visible(False)
                except Exception:
                    pass
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
    
        # Prepare CIF globals for interactive menu (ensures CIF commands are available)
        cif_globals_dict = None
        if cif_tick_series:
            cif_globals_dict = {
                'cif_tick_series': list(cif_tick_series),
                'cif_hkl_map': cif_hkl_map,
                'cif_hkl_label_map': cif_hkl_label_map,
                'show_cif_hkl': bool(show_cif_hkl),
                'show_cif_titles': bool(show_cif_titles),
                'cif_extend_suspended': False,
                'keep_canvas_fixed': True,
            }
        
        interactive_menu(fig, ax, y_data_list, x_data_list, labels_list,
                         orig_y, label_text_objects, delta, x_label, args,
                         x_full_list, raw_y_full_list, offsets_list,
                         use_Q, use_r, use_E, use_k, use_rft,
                         cif_globals=cif_globals_dict)
        plt.show()
        exit()

    # ---------------- Handle conversion ----------------
    if args.convert:
        if not args.files:
            print("Error: --convert requires file(s) to convert")
            exit(1)
        from_param, to_param = args.convert
        convert_xrd_data(args.files, from_param, to_param)
        exit()

    # ---------------- Plotting ----------------
    offset = 0.0
    direction = -1 if args.stack else 1  # stack downward
    if args.interactive:
        # Interactive: keep a reasonably compact default size so the window
        # fits well on most screens; margins are handled by the menu logic.
        plt.ion()
        figsize = (8, 6)
    else:
        # Non-interactive (no --i): use a slightly larger canvas so that labels,
        # titles, legends, and CIF ticks are not clipped even with long filenames.
        # The size (9, 6.4) keeps a similar aspect ratio but with a bit more room
        # than the interactive default while still fitting comfortably on screen.
        figsize = (9.5, 6.4)
    fig, ax = plt.subplots(figsize=figsize)
    
    # Set consistent margins for all modes.
    # This prevents labels/titles from being cut off at the edges.
    try:
        fig.subplots_adjust(left=0.125, right=0.9, top=0.88, bottom=0.11)
    except Exception:
        pass

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
        any_xrd_vendor = any(f.lower().endswith((".raw", ".brml", ".xrdml", ".rasx")) for f in args.files)
        non_cif_count = sum(0 if f.lower().endswith('.cif') else 1 for f in args.files)
        cif_only = any_cif and non_cif_count == 0
        # Check for wavelength parameters (file:wl), but exclude Windows drive letters (C:\...)
        def has_wavelength_param(f):
            if ":" not in f:
                return False
            # Check if it's a Windows path (single letter followed by :\ or :/)
            if len(f) >= 2 and f[1] == ':' and len(f[0]) == 1 and f[0].isalpha():
                # This is a Windows drive letter, check after the drive path
                # Look for additional colons beyond the drive letter
                return ":" in f[2:]
            return True
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
            # .txt is generic, require --xaxis
            if args.xaxis:
                # Normalize case: 'q' or 'Q' → 'Q' (uppercase), everything else lowercase
                axis_mode = "Q" if args.xaxis.upper() == "Q" else args.xaxis.lower()
            else:
                raise ValueError("Unknown file type. Use: batplot file.txt --xaxis [Q|2theta|r|k|energy|rft] or batplot -h for help.")
        elif any_lambda or any_cif or any_xrd_vendor:
            # XRD vendor formats (.raw, .brml, .xrdml, .rasx) are 2theta; CIF is Q; file:wl implies Q domain
            if args.xaxis and args.xaxis.lower() in ("2theta","two_theta","tth"):
                axis_mode = "2theta"
            elif args.xaxis and args.xaxis.upper() == "Q":
                axis_mode = "Q"
            elif getattr(args, 'wl', None) is not None:
                # User gave --wl: default to Q and convert using file metadata or --wl
                axis_mode = "Q"
            elif any_lambda:
                # Per-file wavelength suffix (file:wl) implies Q mode by default
                axis_mode = "Q"
            elif any_cif:
                # CIF without global wavelength: keep 2theta axis (ticks will be converted if/when wavelength is known)
                axis_mode = "2theta"
            else:
                # No explicit wavelength info: use 2theta so x-axis scale/label are correct
                axis_mode = "2theta"
        elif args.xaxis:
            # Normalize case: 'q' or 'Q' → 'Q' (uppercase), everything else lowercase
            axis_mode = "Q" if args.xaxis.upper() == "Q" else args.xaxis.lower()
        else:
            raise ValueError("Unknown file type. Use: batplot file.csv --xaxis [Q|2theta|r|k|energy|rft] or batplot -h for help.")

    use_Q   = axis_mode == "Q"
    use_2th = axis_mode == "2theta"
    use_r   = axis_mode == "r"
    use_E   = axis_mode == "energy"
    use_k   = axis_mode == "k"      # NEW
    use_rft = axis_mode == "rft"    # NEW
    use_time = axis_mode == "time"  # NEW: electrochemistry time mode

    # Initialize wavelength_file from args.wl (may be overridden per-file later)
    wavelength_file = getattr(args, 'wl', None)

    # Validate: if using 2theta mode with CIF files, wavelength is required
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
    
    # Separate style files from data files
    data_files = []
    style_file_path = None
    for f in args.files:
        ext = os.path.splitext(f)[1].lower()
        if ext in ('.bps', '.bpsg', '.bpcfg'):
            if style_file_path is None:
                style_file_path = f
            else:
                print(f"Warning: Multiple style files provided, using first: {style_file_path}")
        else:
            data_files.append(f)
    
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
    
    # Use data_files instead of args.files for processing
    for idx_file, file_entry in enumerate(data_files):
        # Handle Windows paths (C:\...) vs wavelength parameters (file:wl)
        # On Windows, check if first part is a single letter (drive letter)
        parts = file_entry.split(":")
        if len(parts) > 1 and len(parts[0]) == 1 and parts[0].isalpha():
            # Windows drive letter detected (e.g., "C" from "C:\path")
            # Rejoin the first two parts as the filename
            fname = parts[0] + ":" + parts[1]
            parts = [fname] + parts[2:]  # Reconstruct parts with full Windows path
        else:
            fname = parts[0]
        # Parse wavelength parameters: file:wl1 or file:wl1:wl2 or file.cif:wl
        wavelength_file = None
        original_wavelength = None  # First wavelength (for Q conversion)
        conversion_wavelength = None  # Second wavelength (for 2theta conversion back)
        if len(parts) == 2:
            # Single wavelength: file:wl or file.cif:wl
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
        if wavelength_file and not use_r and not use_E and file_ext not in (".gr", ".nor", ".cif"):
            if conversion_wavelength is not None:
                label += f" (λ₁={original_wavelength:.5f}→λ₂={conversion_wavelength:.5f} Å)"
            else:
                label += f" (λ={wavelength_file:.5f} Å)"
        # Wavelength info for this file (appended per curve in loop below for alignment)

        # ---- Read data (time mode for CSV/MPT or regular mode) ----
        curves_to_plot = None  # Set by each branch that produces plottable curves
        if use_time and file_ext in ('.csv', '.mpt'):
            # Time mode: read time (h) vs voltage (V) for electrochemistry files
            try:
                if file_ext == '.csv':
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
                # Force axis mode if needed
                if not (use_Q or use_2th):
                    use_Q = True
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
                print(f"Note: Reading '{file_ext}' file as 2-column (x, y) data. Use --xaxis to specify x-axis type if needed.")

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
            elif use_2th and file_ext == ".qye" and wavelength_file:
                # Convert Q to 2theta for .qye files when wavelength is provided
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
                # In Q mode, 2θ-type XRD data normally require a wavelength for conversion.
                # However, if the user explicitly forced Q with '--xaxis Q', we assume all
                # x-values are already in Q and skip wavelength validation.
                if (original_wavelength is None
                    and wavelength_file is None
                    and file_ext in (".xy", ".xye", ".dat", ".csv", ".raw")
                    and not is_chik and not is_chir
                    and not (getattr(args, "xaxis", None) and str(args.xaxis).upper() == "Q")):
                    raise ValueError(
                        "In Q mode, wavelength must be provided for all 2θ XRD data files unless you explicitly force Q with '--xaxis Q'.\n"
                        f"Missing wavelength for file: {fname}\n"
                        "Provide wavelength via '--wl <wavelength_in_angstrom>' or using 'file:wl' syntax for every 2θ file, "
                        "or rerun with '--xaxis Q' if all inputs should be treated as already in Q space."
                    )
                if original_wavelength is not None:
                    theta_rad = np.radians(x/2)
                    x_plot = 4*np.pi*np.sin(theta_rad)/original_wavelength
                elif wavelength_file:
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
            if getattr(args, 'ro', False):
                x_plotted = y_plot_offset
                y_plotted = x_plot
            else:
                x_plotted = x_plot
                y_plotted = y_plot_offset

            ax.plot(x_plotted, y_plotted, "-", lw=1, alpha=0.8)
            x_data_list.append(x_plotted)
            y_data_list.append(y_plotted.copy())
            labels_list.append(curve_label)
            orig_y.append(y_plotted.copy())

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
        
        # Check visibility flags first to decide if we need to adjust y-axis
        show_titles = show_cif_titles  # Use closure variable
        try:
            # Check __main__ module first (for backward compatibility)
            _bp_module = sys.modules.get('__main__')
            if _bp_module is not None and hasattr(_bp_module, 'show_cif_titles'):
                show_titles = bool(getattr(_bp_module, 'show_cif_titles', True))
            # Also check if stored on figure/axes (from interactive menu)
            if hasattr(fig, '_bp_show_cif_titles'):
                show_titles = bool(getattr(fig, '_bp_show_cif_titles', True))
        except Exception:
            pass
        
        # Optional per-set visibility list (maintained by interactive menu).
        set_visible = None
        try:
            _bp_module = sys.modules.get('__main__')
            if _bp_module is not None and hasattr(_bp_module, 'cif_set_visible'):
                vis = list(getattr(_bp_module, 'cif_set_visible') or [])
                if len(vis) == len(cif_tick_series):
                    set_visible = [bool(v) for v in vis]
        except Exception:
            pass
        # Effective number of visible CIF rows (for spacing and y-limit expansion)
        if set_visible is None:
            n_rows = len(cif_tick_series)
        else:
            n_rows = max(1, sum(1 for v in set_visible if v))
        
        # Calculate base and spacing based on FIXED y-axis limits (not current)
        # This prevents incremental movement when toggling
        if args.stack or len(y_data_list) > 1:
            global_min = min(float(a.min()) for a in y_data_list if len(a)) if y_data_list else fixed_ylim[0]
            base = global_min - 0.08*fixed_yr; spacing = 0.05*fixed_yr
        else:
            global_min = min(float(a.min()) for a in y_data_list if len(a)) if y_data_list else 0.0
            base = global_min - 0.06*fixed_yr; spacing = 0.04*fixed_yr
        
        # Only adjust y-axis limits if titles are visible
        needed_min = base - (n_rows-1)*spacing - 0.04*fixed_yr
        if show_titles and needed_min < fixed_ylim[0]:
            # Expand y-axis only if needed, using fixed limits as reference
            ax.set_ylim(needed_min, fixed_ylim[1])
        else:
            # Restore to fixed limits if no expansion needed
            ax.set_ylim(fixed_ylim)
        
        # Get current limits for drawing (after potential expansion)
        cur_ylim = ax.get_ylim()
        yr = cur_ylim[1] - cur_ylim[0]
        if yr <= 0: yr = 1.0
        # Clear previous
        for art in getattr(ax, '_cif_tick_art', []):
            try: art.remove()
            except Exception: pass
        new_art = []
        mixed_mode = (not cif_only)  # cif_only variable defined earlier in script context
        # Check hkl visibility - check __main__ module first (where interactive menu stores it)
        # then fall back to closure variable
        show_hkl = False
        try:
            _bp_module = sys.modules.get('__main__')
            if _bp_module is not None and hasattr(_bp_module, 'show_cif_hkl'):
                show_hkl = bool(getattr(_bp_module, 'show_cif_hkl', False))
        except Exception:
            pass
        # Fall back to closure variable if not found in module
        if not show_hkl:
            try:
                show_hkl = bool(globals().get('show_cif_hkl', False))
            except Exception:
                pass
        visible_idx = 0
        for i,(lab, fname, peaksQ, wl, qmax_sim, color) in enumerate(cif_tick_series):
            if set_visible is not None and i < len(set_visible) and not set_visible[i]:
                continue
            y_line = base - visible_idx*spacing
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
                # No peaks in current window; still write label row and continue (if titles are visible)
                if show_titles:
                    # Removed numbering; keep space padding
                    label_text = f" {lab}"
                    # Align CIF title baseline with tick baseline for this row
                    txt = ax.text(prev_xlim[0], y_line, label_text,
                                  ha='left', va='bottom', fontsize=max(8,int(0.55*plt.rcParams.get('font.size',12))), color=color)
                    new_art.append(txt)
                continue
            # Build map for quick hkl lookup by Q (only if hkl labels are enabled)
            label_map = {}
            if show_hkl:
                label_map = cif_hkl_label_map.get(fname, {})
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
                    ln, = ax.plot([p,p],[y_line, y_line+0.02*yr], color=color, lw=1.0, alpha=0.9, zorder=3)
                    new_art.append(ln)
                    if use_2th and wl:
                        theta = np.radians(p/2.0)
                        Qp = 4*np.pi*np.sin(theta)/wl
                    else:
                        Qp = p
                    Qp_rounded = round(Qp, 6)
                    lbl = label_map.get(Qp_rounded)
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
            if show_titles:
                label_text = f" {lab}"
                # Align CIF title baseline with tick baseline for this row
                txt = ax.text(prev_xlim[0], y_line, label_text,
                              ha='left', va='bottom', fontsize=max(8,int(0.55*plt.rcParams.get('font.size',12))), color=color)
                new_art.append(txt)
            visible_idx += 1
        ax._cif_tick_art = new_art
        # Restore both x and y-axis limits to prevent movement
        ax.set_xlim(prev_xlim)
        # Restore y-axis: if titles are hidden, always restore; if titles are shown, only restore if we didn't need to expand
        if not show_titles:
            # Titles hidden: always restore original limits
            ax.set_ylim(prev_ylim)
        elif needed_min >= prev_ylim[0]:
            # Titles shown but no expansion needed: restore original limits
            ax.set_ylim(prev_ylim)
        else:
            # Expansion needed: use the minimum of needed_min and prev_ylim[0] to prevent incremental growth
            # This ensures that repeated toggles don't cause drift
            new_ymin = min(needed_min, prev_ylim[0])
            ax.set_ylim(new_ymin, prev_ylim[1])
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
                    tab10 = plt.get_cmap('tab10').colors
                    # Reorder indices for more distinct neighboring colors
                    order = [0, 3, 6, 1, 4, 7, 2, 5, 8, 9]
                    new_series = []
                    for i, (lab, fname, peaksQ, wl, qmax_sim, col) in enumerate(cif_tick_series):
                        idx = order[i] if i < len(order) else i % len(tab10)
                        color = tab10[idx]
                        new_series.append((lab, fname, peaksQ, wl, qmax_sim, color))
                else:
                    cmap = plt.get_cmap('viridis')
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
        elif use_2th: x_label = "2θ (deg)"
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
    
    # Swap axis labels if --ro flag is set
    if getattr(args, 'ro', False):
        ax.set_xlabel(y_label, fontsize=16)
        ax.set_ylabel(x_label, fontsize=16)
    else:

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

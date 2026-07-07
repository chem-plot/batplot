"""Top-level routing for reloading saved ``.pkl`` sessions.

Extracted verbatim from ``batplot.batplot.batplot_main``. When the user runs
``batplot session.pkl`` this module loads the session, dispatches to the
matching interactive menu (XY / EC / operando+EC / CPC) and -- for legacy
sessions without a recognised ``kind`` -- reconstructs a minimal XY figure.

All collaborators are imported from their owning submodules so this module
does not depend on :mod:`batplot.batplot` (no circular import).
"""

from __future__ import annotations

import os
import sys
import pickle
from typing import Any, Tuple, cast

import numpy as np  # type: ignore
import matplotlib.pyplot as plt  # type: ignore[import-untyped]
from matplotlib.ticker import AutoMinorLocator, NullFormatter  # type: ignore[import-untyped]

from ..ec_common import _run_saved_dqdv_2d_companion
from .._mpl_backend import (
    ensure_gui_backend,
    hold_figure_open,
    is_interactive_backend,
    prime_interactive_figure,
    running_headless,
    warn_if_noninteractive,
)
from ..session import (
    load_xy_session,
    load_ec_session,
    load_operando_session,
    load_cpc_session,
    _apply_axes_bbox as _session_apply_axes_bbox,
    _try_extract_version_from_pickle,
    _get_current_numpy_version,
)
from ..plotting import update_labels
from ..utils import (
    xy_cif_stack_y_offset,
    xy_cif_tick_stack_layout,
    xy_cif_add_phase_title,
    xy_cif_row_spacing_yr,
    xy_cif_stack_bottom_margin_yr,
)
from ..ui import (
    position_top_xlabel as _ui_position_top_xlabel,
    position_right_ylabel as _ui_position_right_ylabel,
    position_bottom_xlabel as _ui_position_bottom_xlabel,
    position_left_ylabel as _ui_position_left_ylabel,
)
from .xy.interactive import interactive_menu, normalize_xy_menu_kwargs
from .electrochem.interactive import electrochem_interactive_menu

try:
    from .cpc.interactive import cpc_interactive_menu
except ImportError:
    cpc_interactive_menu = None

try:
    from .operando.interactive import operando_ec_interactive_menu
except ImportError:
    operando_ec_interactive_menu = None


_VALID_SESSION_KINDS = frozenset({"histo", "ec_gc", "cpc", "operando_ec", "xy"})


def _is_valid_session_header(sess: object) -> bool:
    """Return True for legacy XY sessions and kind-tagged mode sessions."""
    if not isinstance(sess, dict):
        return False
    kind = sess.get("kind")
    if kind in _VALID_SESSION_KINDS:
        return True
    # Legacy XY / batplot sessions without an explicit kind field.
    return "version" in sess


def _load_session_dict_with_diagnostics(sess_path: str) -> tuple[dict | None, int | None]:
    """Load a session header dict, preserving the existing NumPy mismatch diagnostics."""
    try:
        with open(sess_path, 'rb') as f:
            sess = pickle.load(f)
        if not _is_valid_session_header(sess):
            print("Not a valid batplot session file.")
            return None, 1
        return sess, None
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
        return None, 1
    except Exception as e:
        print(f"Failed to load session: {e}")
        return None, 1


def handle_session_reload(args) -> int:
    ensure_gui_backend(args)
    if not is_interactive_backend() and not running_headless():
        warn_if_noninteractive("saved session reload")
        return 1
    sess_path = args.files[0]
    if not os.path.isfile(sess_path):
        print(f"Session file not found: {sess_path}")
        exit(1)
    sess, session_error = _load_session_dict_with_diagnostics(sess_path)
    if session_error is not None:
        return session_error
    if sess is None:
        # Unreachable: the loader always pairs a None session with an error code.
        print("Not a valid batplot session file.")
        return 1
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
                prime_interactive_figure(fig)
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
                fig, ax, cycle_lines = cast(Tuple[Any, Any, Any], res)
                prime_interactive_figure(fig)
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
            try:
                _run_saved_dqdv_2d_companion(fig, sess_path)
            except Exception as _c2d:
                print(f"Saved dQ/dV 2D companion: {_c2d}")
            hold_figure_open()
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
            prime_interactive_figure(fig2)
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
            hold_figure_open()
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
            prime_interactive_figure(fig_c)
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
            hold_figure_open()
            exit()
        except Exception as e:
            print(f"CPC session load failed: {e}")
            exit(1)

    # If it's a histogram session, load and open histogram interactive menu
    if isinstance(sess, dict) and sess.get('kind') == 'histo':
        try:
            from .histo.session import load_histo_session
            from .histo.interactive import histo_interactive_menu
            from .histo.load import load_table

            res = load_histo_session(sess_path)
            if not res:
                print("Failed to load histogram session.")
                exit(1)
            fig_h, ax_h, state_h = res
            prime_interactive_figure(fig_h)
            try:
                fig_h._last_session_save_path = os.path.abspath(sess_path)
            except Exception:
                pass
            table_loader = None
            source = getattr(state_h, "source_path", "") or ""
            if source and os.path.isfile(source):
                table_loader = lambda src=source: load_table(src)
            try:
                histo_interactive_menu(fig_h, ax_h, state_h, table_loader=table_loader)
            except Exception as _ie:
                print(f"Histogram interactive menu failed: {_ie}")
            hold_figure_open()
            exit()
        except Exception as e:
            print(f"Histogram session load failed: {e}")
            exit(1)

    # XY sessions include legacy files without a kind plus current kind='xy'.
    # Use the dedicated loader so saved full-range arrays stay available after load.
    if isinstance(sess, dict) and sess.get('kind') in (None, 'xy'):
        try:
            res = load_xy_session(sess_path)
            if not res:
                print("Failed to load XY session.")
                exit(1)
            fig_xy, ax_xy, menu_kwargs = res
            prime_interactive_figure(fig_xy)
            try:
                fig_xy._last_session_save_path = os.path.abspath(sess_path)
            except Exception:
                pass
            try:
                interactive_menu(fig_xy, ax_xy, **normalize_xy_menu_kwargs(menu_kwargs))
            except Exception as _ie:
                print(f"Interactive menu failed: {_ie}")
            hold_figure_open()
            exit()
        except Exception as e:
            print(f"XY session load failed: {e}")
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
    right_y_loaded = frozenset(sess.get('right_y_curve_indices', []))
    ax2_loaded = None
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
        is_right = i in right_y_loaded
        if is_right:
            if ax2_loaded is None:
                ax2_loaded = ax.twinx()
                if sess.get('txaxis', False):
                    ax2_loaded = ax2_loaded.twiny()
            ax2_loaded.plot(x_arr, y_plot, lw=1)
        else:
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
    # Restore right-y state (--ry) for interactive
    if ax2_loaded is not None:
        fig._xy_ax2 = ax2_loaded
        fig._xy_use_top_x = bool(sess.get('txaxis', False))
        fig._xy_right_y_curve_indices = right_y_loaded
        _left_idx = sorted(i for i in range(n_curves) if i not in right_y_loaded)
        _right_idx = sorted(right_y_loaded)
        _lines_by_curve = []
        for i in range(n_curves):
            if i in right_y_loaded:
                k = _right_idx.index(i)
                _lines_by_curve.append(ax2_loaded.lines[k] if k < len(ax2_loaded.lines) else None)
            else:
                k = _left_idx.index(i)
                _lines_by_curve.append(ax.lines[k] if k < len(ax.lines) else None)
        fig._xy_lines_by_curve = _lines_by_curve
    else:
        fig._xy_ax2 = None
        fig._xy_right_y_curve_indices = frozenset()
        fig._xy_lines_by_curve = None

    # Apply stored line styles (if any)
    try:
        stored_styles = sess.get('line_styles', [])
        lines_to_style = (fig._xy_lines_by_curve if fig._xy_lines_by_curve else ax.lines)
        for ln, st in zip(lines_to_style, stored_styles):
            if ln is None:
                continue
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
                    # x-axis: tick2/label2 = top, tick1/label1 = bottom
                    tick_key = 'tick2On' if side == 'top' else 'tick1On'
                    label_key = 'label2On' if side == 'top' else 'label1On'
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
        try:
            fig._batplot_cif_tick_series = cif_tick_series
        except Exception:
            pass
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
            _ser = getattr(fig, '_batplot_cif_tick_series', None) or cif_tick_series
            for _lab,_fname,_peaks,_wl,_qmax,_color in _ser:
                if _wl is not None:
                    return _wl
            return getattr(args, 'wl', None) or default_wl

        def _session_cif_extend(xmax_domain):
            # Minimal extension: do nothing (could replicate original if needed)
            return

        def _session_cif_draw():
            cif_series_draw = getattr(fig, '_batplot_cif_tick_series', None)
            if cif_series_draw is None:
                cif_series_draw = cif_tick_series
            if not cif_series_draw:
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
                
                _stacked_s = bool(saved_stack or len(y_data_list) > 1)
                if _stacked_s:
                    global_min = min(float(a.min()) for a in y_data_list if len(a)) if y_data_list else fixed_ylim[0]
                    base = global_min - 0.08 * fixed_yr
                else:
                    global_min = min(float(a.min()) for a in y_data_list if len(a)) if y_data_list else 0.0
                    base = global_min - 0.06 * fixed_yr
                spacing = xy_cif_row_spacing_yr(
                    fixed_yr,
                    show_titles=show_titles_local,
                    show_hkl=show_hkl_local,
                    stacked_or_multi_y=_stacked_s,
                )
                _cif_bottom_m = xy_cif_stack_bottom_margin_yr(fixed_yr, show_titles=show_titles_local)
                needed_min = base - (len(cif_series_draw) - 1) * spacing - _cif_bottom_m
                if not show_titles_local:
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
                
                # Clear previous artifacts
                for art in getattr(ax, '_cif_tick_art', []):
                    try: art.remove()
                    except Exception: pass
                new_art = []
                wl_any = _session_ensure_wavelength()
                
                # Draw each series
                for i,(lab,fname,peaksQ,wl,qmax_sim,color) in enumerate(cif_series_draw):
                    y_line = base - i * spacing + xy_cif_stack_y_offset(fig, i)
                    tick_h, hkl_y = xy_cif_tick_stack_layout(y_line, yr)
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
                        ln, = ax.plot([p, p], [y_line, y_line + tick_h], color=color, lw=1.0, alpha=0.9, zorder=3)
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
                                t_hkl = ax.text(p, hkl_y, lbl, ha='center', va='bottom', fontsize=7, rotation=90, color=color)
                                new_art.append(t_hkl)
                    # Only add title label if show_cif_titles is True
                    if show_titles_local:
                        label_text = f" {lab}"
                        xy_cif_add_phase_title(
                            ax, prev_xlim[0], y_line, tick_h, label_text,
                            max(8, int(0.55 * plt.rcParams.get('font.size', 16))), color, new_art,
                        )
                ax._cif_tick_art = new_art
                ax.set_xlim(prev_xlim)
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
        # Right y-axis (--ry): set ax2 ylabel when dual axes exist
        if ax2_loaded is not None and right_text:
            ax2_loaded.set_ylabel(right_text, fontsize=16)
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
    prime_interactive_figure(fig)

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
            'cif_tick_series': cif_tick_series,
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
    hold_figure_open()
    exit()

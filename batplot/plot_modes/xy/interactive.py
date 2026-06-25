"""Interactive menu for normal XY plots (moved from monolithic batplot.py).

This module provides interactive_menu(fig, ax, ...). It mirrors the previous
implementation but lives outside batplot.py to match the pattern used by other
interactive modes (EC, Operando).
"""

from __future__ import annotations

import os
import sys
from typing import Optional, Dict, Any, List, cast

import numpy as np  # type: ignore[import]
import matplotlib.pyplot as plt  # type: ignore[import]
from matplotlib.ticker import (  # type: ignore[import]
    AutoMinorLocator, MultipleLocator,
    NullLocator,
)

from ...plotting import apply_curve_color, update_labels
from ...utils import (
    normalize_label_text,
)
from ...ui import (
    apply_font_changes as _ui_apply_font_changes,
    sync_fonts as _ui_sync_fonts,
    position_top_xlabel as _ui_position_top_xlabel,
    position_right_ylabel as _ui_position_right_ylabel,
    position_bottom_xlabel as _ui_position_bottom_xlabel,
    position_left_ylabel as _ui_position_left_ylabel,
    ensure_text_visibility as _ui_ensure_text_visibility,
    resize_plot_frame as _ui_resize_plot_frame,
    resize_canvas as _ui_resize_canvas,
    set_spine_side_color as _ui_set_spine_side_color,
    capture_axes_tick_locators,
    restore_axes_tick_locators,
)
from .style import (
    print_style_info as _bp_print_style_info,
    apply_style_config as _bp_apply_style_config,
    capture_xy_axis_style,
    apply_xy_axis_style,
)
from ...config import load_config, save_config
from .style import export_style_config as _export_style_config
import sys as _sys_snap

from ..common.terminal import (
    colorize_inline_commands as _colorize_inline_commands,
    colorize_prompt as _colorize_prompt,
    safe_input as _common_safe_input,
)
from ..common.menu_rendering import (
    colorize_menu_item,
)
from ..common.sources import normalize_source_paths
from ..common.title_offsets import (
    capture_title_offsets,
    reset_title_offsets,
    restore_title_offsets,
)
from ..common.spines import (
    apply_changed_side_title_positions,
    apply_flat_tick_params,
    build_wasd_state,
    default_flat_tick_state,
    legacy_tick_state_to_flat,
    run_spine_tick_menu,
    sync_legacy_tick_keys,
    sync_tick_state_from_wasd,
)
from ..common.menus import run_font_menu, run_option_menu
from ..common.files import format_file_timestamp
from .actions import (
    XyActionContext,
    handle_figure_export,
    handle_quick_overwrite_figure,
    handle_quick_overwrite_session,
    handle_quick_overwrite_style,
    handle_save_session,
    handle_style_export,
    handle_style_import,
    handle_undo,
)
from .arrange import run_rearrange_menu
from .axis_range import run_x_range_menu, run_y_range_menu
from .cif import run_cif_ticks_menu
from .colors import run_xy_color_menu
from .derivative import run_derivative_menu
from .game import play_jump_game
from .labels import run_xy_rename_menu
from .line_style import run_line_style_menu
from .menu import print_xy_menu
from .peaks import run_peak_finder_menu
from .smoothing import run_smoothing_menu


def _safe_input(prompt: str = "", *, cancel_on_interrupt: bool = True) -> str:
    """Wrapper around input() that suppresses macOS IMKCFRunLoopWakeUpReliable warnings.

    On **Ctrl+C** (or EOF on stdin), returns ``""`` by default so prompts behave like cancel
    and the interactive menu keeps running instead of exiting with a traceback.
    Set ``cancel_on_interrupt=False`` to re-raise (e.g. tests).
    """
    return _common_safe_input(prompt, cancel_on_interrupt=cancel_on_interrupt)


def normalize_xy_menu_kwargs(menu_kwargs: dict) -> dict:
    """Return kwargs safe for :func:`interactive_menu` (legacy ``labels_list`` alias)."""
    out = dict(menu_kwargs)
    if "labels_list" in out and "labels" not in out:
        out["labels"] = out.pop("labels_list")
    elif "labels_list" in out:
        out.pop("labels_list", None)
    return out


# pyright: ignore[reportGeneralTypeIssues]
def interactive_menu(fig, ax, y_data_list, x_data_list, labels, orig_y,
                     label_text_objects, delta, x_label, args,
                     x_full_list, raw_y_full_list, offsets_list,
                     use_Q, use_r, use_E, use_k, use_rft,
                     cif_globals: Optional[Dict[str, Any]] = None,
                     canvas_mode: bool = False,
                     labels_list: Optional[List[str]] = None):
    """Interactive menu for XY plots.
    
    Args:
        fig: matplotlib Figure
        ax: matplotlib Axes
        y_data_list: List of y-data arrays (with offsets applied)
        x_data_list: List of x-data arrays (cropped to current view)
        labels: List of curve labels
        orig_y: List of baseline y-data (normalized, no offset)
        label_text_objects: List of matplotlib Text objects for curve labels
        delta: Current offset spacing value
        x_label: X-axis label string
        args: Argument namespace from CLI
        x_full_list: List of full x-data arrays (uncropped)
        raw_y_full_list: List of full raw y-data arrays
        offsets_list: List of current offset values per curve
        use_Q, use_r, use_E, use_k, use_rft: Boolean flags for axis mode
        cif_globals: Optional dict containing CIF-related state:
            - 'cif_tick_series': list of CIF tick data
            - 'cif_hkl_map': dict mapping filenames to hkl reflections
            - 'cif_hkl_label_map': dict mapping Q to hkl label strings
            - 'show_cif_hkl': bool flag for hkl label visibility
            - 'cif_extend_suspended': bool flag to prevent re-entrant extension
            - 'keep_canvas_fixed': bool flag for canvas resize behavior
    """
    if labels_list is not None:
        labels = labels_list
    # Use the provided fig/ax as-is; do not close or switch figures to avoid spawning new windows
    
    # Handle CIF globals - prefer explicit parameter, fallback to __main__ for backward compatibility
    if cif_globals is None:
        # Legacy path: try to access __main__ module for CIF state
        _bp = sys.modules.get('__main__')
        if _bp is not None and hasattr(_bp, 'cif_tick_series'):
            cif_globals = {
                'cif_tick_series': getattr(_bp, 'cif_tick_series', None),
                'cif_hkl_map': getattr(_bp, 'cif_hkl_map', None),
                'cif_hkl_label_map': getattr(_bp, 'cif_hkl_label_map', None),
                'show_cif_hkl': getattr(_bp, 'show_cif_hkl', False),
                'show_cif_titles': getattr(_bp, 'show_cif_titles', True),
                'cif_extend_suspended': getattr(_bp, 'cif_extend_suspended', False),
                'keep_canvas_fixed': getattr(_bp, 'keep_canvas_fixed', False),
            }
        else:
            cif_globals = {}
    
    # Provide a consistent interface for accessing CIF state
    _bp = type('CIFState', (), cif_globals)() if cif_globals else None

    def _sync_fig_cif_tick_series():
        """Keep fig._batplot_cif_tick_series aligned with menu state for CIF redraw."""
        if _bp is None:
            return
        try:
            _cts = getattr(_bp, 'cif_tick_series', None)
            if _cts is not None:
                fig._batplot_cif_tick_series = _cts
        except Exception:
            pass

    _sync_fig_cif_tick_series()

    def _cif_series_for_session():
        """CIF list for save (s), export (p), and undo snapshot: same as redraw (fig-backed)."""
        try:
            c = getattr(fig, '_batplot_cif_tick_series', None)
            if c is not None:
                return c
        except Exception:
            pass
        if _bp is not None:
            return getattr(_bp, 'cif_tick_series', None)
        return None

    def _print_cif_phase_list(cts):
        for i, (lab, fname, *_rest) in enumerate(cts):
            print(f"  {i+1}: {lab} ({os.path.basename(fname)})")

    def _apply_cif_phase_label_rename(idx: int, new_label: str) -> None:
        """Update one CIF phase row label and redraw (shared by main r→t and cif→r)."""
        cts = getattr(_bp, 'cif_tick_series', None) if _bp is not None else None
        if not cts or not (0 <= idx < len(cts)):
            return
        try:
            push_state("cif-rename")
        except Exception:
            pass
        _, fname, peaksQ, wl_e, qmax, col = cts[idx]
        if _bp is not None:
            setattr(_bp, 'cif_extend_suspended', True)
        if hasattr(ax, '_cif_tick_art'):
            try:
                for art in list(getattr(ax, '_cif_tick_art', [])):
                    try:
                        art.remove()
                    except Exception:
                        pass
                ax._cif_tick_art = []
            except Exception:
                pass
        cts[idx] = (new_label, fname, peaksQ, wl_e, qmax, col)
        if _bp is not None:
            setattr(_bp, 'cif_tick_series', cts)
        _sync_fig_cif_tick_series()
        if hasattr(ax, '_cif_draw_func'):
            ax._cif_draw_func()
        try:
            fig.canvas.draw()
        except Exception:
            pass
        if _bp is not None:
            setattr(_bp, 'cif_extend_suspended', False)

    try:
        source_file_paths = normalize_source_paths(
            getattr(args, 'files', []) or [],
            require_exists=True,
            require_file=True,
        )
    except Exception:
        source_file_paths = []
    try:
        fig._bp_source_paths = list(source_file_paths)
    except Exception:
        pass

    # Initialize rotation state (0, 90, 180, or 270 degrees)
    if not hasattr(ax, '_rotation_angle'):
        ax._rotation_angle = 0

    # Initialize stack label position state (True = bottom, False = top/max)
    if not hasattr(fig, '_stack_label_at_bottom'):
        fig._stack_label_at_bottom = False
    # Track horizontal anchor (False=right, True=left)
    if not hasattr(fig, '_label_anchor_left'):
        fig._label_anchor_left = False

    # Line lookup for dual y-axis (--ry): curve index -> Line2D (ax or ax2)
    _lines_by_curve = getattr(fig, '_xy_lines_by_curve', None)
    def _line(i) -> Any:
        if _lines_by_curve is not None and 0 <= i < len(_lines_by_curve):
            return _lines_by_curve[i]
        try:
            return ax.lines[i]
        except (IndexError, TypeError):
            return None
    def _nlines():
        return len(_lines_by_curve) if _lines_by_curve is not None else len(ax.lines)
    def _iter_lines():
        return enumerate(_lines_by_curve) if _lines_by_curve is not None else enumerate(ax.lines)

    # ANSI color codes for menu highlighting
    def colorize_menu(text):
        return colorize_menu_item(text)
    
    colorize_prompt = _colorize_prompt

    colorize_inline_commands = _colorize_inline_commands
    
    # REPLACED print_main_menu with column layout (now hides 'd' and 'y' in --stack)
    is_diffraction = use_Q or (not use_r and not use_E and not use_k and not use_rft)  # 2θ or Q
    def print_main_menu():
        print_xy_menu(
            fig=fig,
            stack=args.stack,
            is_diffraction=is_diffraction,
            colorize_menu=colorize_menu,
        )

    # --- Helper for spine visibility ---
    def set_spine_visible(which, visible):
        if which in ax.spines:
            ax.spines[which].set_visible(visible)
            fig.canvas.draw_idle()

    def get_spine_visible(which):
        if which in ax.spines:
            return ax.spines[which].get_visible()
        return False
    # Initial menu display REMOVED to avoid double print
    ax.set_aspect('auto', adjustable='datalim')

    def on_xlim_change(event_ax):
        stack_label_bottom = getattr(fig, '_stack_label_at_bottom', False)
        update_labels(event_ax, y_data_list, label_text_objects, args.stack, stack_label_bottom)
        # Extend CIF ticks if needed when user pans/zooms horizontally
        try:
            if (
                _bp is not None
                and (not getattr(_bp, 'cif_extend_suspended', False))
                and hasattr(ax, '_cif_extend_func') and hasattr(ax, '_cif_draw_func') and callable(ax._cif_extend_func)
            ):
                current_xlim = ax.get_xlim()
                xmax = current_xlim[1]
                ax._cif_extend_func(xmax)
        except Exception:
            pass
        fig.canvas.draw()
    ax.callbacks.connect('xlim_changed', on_xlim_change)

    # --------- UPDATED unified font update helper ----------
    def apply_font_changes(new_size=None, new_family=None):
        return _ui_apply_font_changes(ax, fig, label_text_objects, normalize_label_text, new_size, new_family)

    # Generic font sync (even when size/family unchanged) so newly created labels/twin axes inherit the rcParams size
    def sync_fonts():
        return _ui_sync_fonts(ax, fig, label_text_objects)

    # Adjust vertical position of duplicate top X label depending on top tick visibility
    def position_top_xlabel():
        return _ui_position_top_xlabel(ax, fig, tick_state)

    def position_right_ylabel():
        return _ui_position_right_ylabel(ax, fig, tick_state)
    
    def position_bottom_xlabel():
        return _ui_position_bottom_xlabel(ax, fig, tick_state)
    
    def position_left_ylabel():
        return _ui_position_left_ylabel(ax, fig, tick_state)
    
    def _current_label_position() -> str:
        vertical = "bottom" if getattr(fig, '_stack_label_at_bottom', False) else "top"
        horizontal = "left" if getattr(fig, '_label_anchor_left', False) else "right"
        return f"{vertical}-{horizontal}"
    
    def _apply_legend_position(bottom: bool, left: bool) -> None:
        fig._stack_label_at_bottom = bottom
        fig._label_anchor_left = left
        update_labels(ax, y_data_list, label_text_objects, args.stack, bottom)
        try:
            fig.canvas.draw_idle()
        except Exception:
            pass
    
    def _title_offset_menu():
        """Interactive nudging for duplicate top/right titles."""
        def _dpi():
            try:
                return float(fig.dpi)
            except Exception:
                return 72.0

        def _px_value(attr):
            try:
                pts = float(getattr(ax, attr, 0.0) or 0.0)
            except Exception:
                pts = 0.0
            return pts * _dpi() / 72.0

        def _set_attr(attr, pts):
            try:
                setattr(ax, attr, float(pts))
            except Exception:
                pass

        def _nudge(attr, delta_px):
            try:
                current_pts = float(getattr(ax, attr, 0.0) or 0.0)
            except Exception:
                current_pts = 0.0
            delta_pts = float(delta_px) * 72.0 / _dpi()
            _set_attr(attr, current_pts + delta_pts)

        snapshot_taken = False

        def _ensure_snapshot():
            nonlocal snapshot_taken
            if not snapshot_taken:
                push_state("title-offset")
                snapshot_taken = True

        def _top_menu():
            if not getattr(ax, '_top_xlabel_on', False):
                print("Top duplicate title is currently hidden (toggle with w5).")
                return
            while True:
                current_y_px = _px_value('_top_xlabel_manual_offset_y_pts')
                current_x_px = _px_value('_top_xlabel_manual_offset_x_pts')
                print(f"Top title offset: Y={current_y_px:+.2f} px (positive=up), X={current_x_px:+.2f} px (positive=right)")
                sub = _safe_input(colorize_prompt("top (w=up, s=down, a=left, d=right, 0=reset, q=back): ")).strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub == '0':
                    _ensure_snapshot()
                    _set_attr('_top_xlabel_manual_offset_y_pts', 0.0)
                    _set_attr('_top_xlabel_manual_offset_x_pts', 0.0)
                elif sub == 'w':
                    _ensure_snapshot()
                    _nudge('_top_xlabel_manual_offset_y_pts', +1.0)
                elif sub == 's':
                    _ensure_snapshot()
                    _nudge('_top_xlabel_manual_offset_y_pts', -1.0)
                elif sub == 'a':
                    _ensure_snapshot()
                    _nudge('_top_xlabel_manual_offset_x_pts', -1.0)
                elif sub == 'd':
                    _ensure_snapshot()
                    _nudge('_top_xlabel_manual_offset_x_pts', +1.0)
                else:
                    print("Unknown choice (use w/s/a/d/0/q).")
                    continue
                position_top_xlabel()
                try:
                    fig.canvas.draw_idle()
                except Exception:
                    pass

        def _right_menu():
            if not getattr(ax, '_right_ylabel_on', False):
                print("Right duplicate title is currently hidden (toggle with d5).")
                return
            while True:
                current_x_px = _px_value('_right_ylabel_manual_offset_x_pts')
                current_y_px = _px_value('_right_ylabel_manual_offset_y_pts')
                print(f"Right title offset: X={current_x_px:+.2f} px (positive=right), Y={current_y_px:+.2f} px (positive=up)")
                sub = _safe_input(colorize_prompt("right (d=right, a=left, w=up, s=down, 0=reset, q=back): ")).strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub == '0':
                    _ensure_snapshot()
                    _set_attr('_right_ylabel_manual_offset_x_pts', 0.0)
                    _set_attr('_right_ylabel_manual_offset_y_pts', 0.0)
                elif sub == 'd':
                    _ensure_snapshot()
                    _nudge('_right_ylabel_manual_offset_x_pts', +1.0)
                elif sub == 'a':
                    _ensure_snapshot()
                    _nudge('_right_ylabel_manual_offset_x_pts', -1.0)
                elif sub == 'w':
                    _ensure_snapshot()
                    _nudge('_right_ylabel_manual_offset_y_pts', +1.0)
                elif sub == 's':
                    _ensure_snapshot()
                    _nudge('_right_ylabel_manual_offset_y_pts', -1.0)
                else:
                    print("Unknown choice (use d/a/w/s/0/q).")
                    continue
                position_right_ylabel()
                try:
                    fig.canvas.draw_idle()
                except Exception:
                    pass

        def _bottom_menu():
            if not ax.get_xlabel():
                print("Bottom title is currently hidden.")
                return
            while True:
                current_y_px = _px_value('_bottom_xlabel_manual_offset_y_pts')
                print(f"Bottom title offset: Y={current_y_px:+.2f} px (positive=down)")
                sub = _safe_input(colorize_prompt("bottom (s=down, w=up, 0=reset, q=back): ")).strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub == '0':
                    _ensure_snapshot()
                    _set_attr('_bottom_xlabel_manual_offset_y_pts', 0.0)
                elif sub == 's':
                    _ensure_snapshot()
                    _nudge('_bottom_xlabel_manual_offset_y_pts', +1.0)
                elif sub == 'w':
                    _ensure_snapshot()
                    _nudge('_bottom_xlabel_manual_offset_y_pts', -1.0)
                else:
                    print("Unknown choice (use s/w/0/q).")
                    continue
                position_bottom_xlabel()
                try:
                    fig.canvas.draw_idle()
                except Exception:
                    pass

        def _left_menu():
            if not ax.get_ylabel():
                print("Left title is currently hidden.")
                return
            while True:
                current_x_px = _px_value('_left_ylabel_manual_offset_x_pts')
                print(f"Left title offset: X={current_x_px:+.2f} px (positive=left)")
                sub = _safe_input(colorize_prompt("left (a=left, d=right, 0=reset, q=back): ")).strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub == '0':
                    _ensure_snapshot()
                    _set_attr('_left_ylabel_manual_offset_x_pts', 0.0)
                elif sub == 'a':
                    _ensure_snapshot()
                    _nudge('_left_ylabel_manual_offset_x_pts', +1.0)
                elif sub == 'd':
                    _ensure_snapshot()
                    _nudge('_left_ylabel_manual_offset_x_pts', -1.0)
                else:
                    print("Unknown choice (use a/d/0/q).")
                    continue
                position_left_ylabel()
                try:
                    fig.canvas.draw_idle()
                except Exception:
                    pass

        while True:
            print(colorize_inline_commands("Title offsets:"))
            print("  " + colorize_menu('w : adjust top title (w=up, s=down, a=left, d=right)'))
            print("  " + colorize_menu('s : adjust bottom title (s=down, w=up)'))
            print("  " + colorize_menu('a : adjust left title (a=left, d=right)'))
            print("  " + colorize_menu('d : adjust right title (d=right, a=left, w=up, s=down)'))
            print("  " + colorize_menu('r : reset all offsets'))
            print("  " + colorize_menu('q : back to toggle menu'))
            choice = _safe_input(colorize_prompt(
                "Title offset (w/s/a/d/r/q per list above): "
            )).strip().lower()
            if not choice:
                continue
            if choice == 'q':
                break
            if choice == 'w':
                _top_menu()
                continue
            if choice == 's':
                _bottom_menu()
                continue
            if choice == 'a':
                _left_menu()
                continue
            if choice == 'd':
                _right_menu()
                continue
            if choice == 'r':
                _ensure_snapshot()
                reset_title_offsets(ax)
                position_top_xlabel()
                position_bottom_xlabel()
                position_left_ylabel()
                position_right_ylabel()
                try:
                    fig.canvas.draw_idle()
                except Exception:
                    pass
                print("Reset manual offsets for all titles.")
                continue
            print("Unknown option. Use w/s/a/d/r/q.")
    
    # -------------------------------------------------------

    # --------- NEW: Resize only the plotting frame (axes), keep canvas (figure) size fixed ----------
    def resize_plot_frame():
        return _ui_resize_plot_frame(fig, ax, y_data_list, label_text_objects, args, update_labels)

    def resize_canvas():
        return _ui_resize_canvas(fig, ax)
    # -------------------------------------------------

    # ---- Tick / label visibility state ----
    # New model: separate tick marks vs tick labels per side
    # Keys:
    #   b_ticks, b_labels, t_ticks, t_labels, l_ticks, l_labels, r_ticks, r_labels
    # Minor ticks remain: mbx, mtx, mly, mry
    # Back-compat: also maintain synthetic bx/tx/ly/ry (mapped to *_ticks) for helpers.
    saved_ts = getattr(ax, '_saved_tick_state', None)
    def _make_default_tick_state():
        return default_flat_tick_state()

    def _from_legacy(legacy: dict):
        return legacy_tick_state_to_flat(legacy)

    def _sync_legacy_tick_keys():
        # Mirror current *_ticks into legacy bx/tx/ly/ry keys for code that reads them
        sync_legacy_tick_keys(tick_state)

    if isinstance(saved_ts, dict):
        if any(k in saved_ts for k in ('b_ticks','t_ticks','l_ticks','r_ticks')):
            # Already new-format; start from defaults then overlay
            tick_state = _make_default_tick_state()
            for k,v in saved_ts.items():
                if k in tick_state:
                    tick_state[k] = v
        else:
            tick_state = _from_legacy(saved_ts)
    else:
        tick_state = _make_default_tick_state()
    _sync_legacy_tick_keys()

    if hasattr(ax, '_saved_tick_state'):
        try:
            delattr(ax, '_saved_tick_state')
        except Exception:
            pass

    # NEW: dynamic margin adjustment for top/right ticks
    # Flag to preserve a manual/initial interactive top margin override
    if not hasattr(fig, '_interactive_top_locked'):
        fig._interactive_top_locked = False

    def adjust_margins():
        """Lightweight margin tweak based on tick visibility.

        Unlike the old version this DOES NOT try to aggressively reallocate
        space or change apparent plot size; it only adds a small padding on
        sides that show ticks so labels have breathing room. Intended to be
        idempotent and minimally invasive. Called during initial setup & some
        style operations, but not on every tick toggle anymore.
        """
        sp = fig.subplotpars
        # Start from current to avoid jumping
        left, right, bottom, top = sp.left, sp.right, sp.bottom, sp.top
        pad = 0.01  # modest expansion per active side
        max_pad = 0.10
        # Expand outward (shrinks axes) only if room
        if tick_state['ly'] and left < 0.25:
            left = min(left + pad, 0.40)
        if tick_state['ry'] and (1 - right) < 0.25:
            right = max(right - pad, 0.60)
        if tick_state['bx'] and bottom < 0.25:
            bottom = min(bottom + pad, 0.40)
        if tick_state['tx'] and (1 - top) < 0.25:
            top = max(top - pad, 0.60)

        # Keep minimum plot span
        if right - left < 0.25:
            # Undo horizontal change proportionally
            mid = (left + right) / 2
            left = mid - 0.125
            right = mid + 0.125
        if top - bottom < 0.25:
            mid = (bottom + top) / 2
            bottom = mid - 0.125
            top = mid + 0.125

        fig.subplots_adjust(left=left, right=right, bottom=bottom, top=top)

    def ensure_text_visibility(max_iterations=4, check_only=False):
        return _ui_ensure_text_visibility(fig, ax, label_text_objects, max_iterations, check_only)

    def update_tick_visibility():
        apply_flat_tick_params(ax, tick_state)

    # NOTE: We keep margins stable (no auto-adjust on every toggle)
    if getattr(fig, '_skip_initial_text_visibility', False):
        try:
            delattr(fig, '_skip_initial_text_visibility')
        except Exception:
            pass
    else:
        ensure_text_visibility()
    fig.canvas.draw_idle()

    # NEW helper (was referenced in 'h' menu but not defined previously)
    def print_tick_state():
        _C = '\033[96m'; _R = '\033[0m'
        def onoff(v):
            return 'ON ' if bool(v) else 'off'
        sides = (
            ('bottom',
             get_spine_visible('bottom'),
             tick_state.get('b_ticks', True),
             tick_state.get('mbx', False),
             tick_state.get('b_labels', True),
             bool(ax.get_xlabel())),
            ('top',
             get_spine_visible('top'),
             tick_state.get('t_ticks', False),
             tick_state.get('mtx', False),
             tick_state.get('t_labels', False),
             bool(getattr(ax, '_top_xlabel_on', False))),
            ('left',
             get_spine_visible('left'),
             tick_state.get('l_ticks', True),
             tick_state.get('mly', False),
             tick_state.get('l_labels', True),
             bool(ax.get_ylabel())),
            ('right',
             get_spine_visible('right'),
             tick_state.get('r_ticks', False),
             tick_state.get('mry', False),
             tick_state.get('r_labels', False),
             bool(getattr(ax, '_right_ylabel_on', False))),
        )
        print(f"\033[1mToggle spines state:\033[0m")
        print(f"  {'Side':<7}  spine  major  minor  labels title")
        for name, spine, mj, mn, lbl, title in sides:
            print(f"  {_C}{name:<7}{_R} {onoff(spine)}  {onoff(mj)}   {onoff(mn)}   {onoff(lbl)}  {onoff(title)}")
        # Tick direction
        tick_dir = getattr(fig, '_tick_direction', 'out')
        print(f"  Tick direction  : {_C}{tick_dir}{_R}")
        # Tick lengths
        tl = getattr(fig, '_tick_lengths', {}) or {}
        maj_l = tl.get('major')
        min_l = tl.get('minor')
        if maj_l is not None:
            print(f"  Tick length     : {_C}major={maj_l:.2g}{_R}  {_C}minor={min_l:.2g}{_R}" if min_l is not None else f"  Tick length     : {_C}major={maj_l:.2g}{_R}")
        else:
            print(f"  Tick length     : default")
        # Tick spacing
        def _sp_str(loc):
            try:
                if isinstance(loc, MultipleLocator):
                    return str(loc._edge.step)
                return "auto"
            except Exception:
                return "auto"
        def _mn_str(loc):
            try:
                if isinstance(loc, AutoMinorLocator):
                    n = loc._ndivs
                    return f"{n-1}/interval"
                if isinstance(loc, NullLocator):
                    return "off"
                if isinstance(loc, MultipleLocator):
                    return f"step={loc._edge.step}"
                return "auto"
            except Exception:
                return "auto"
        print(f"  Tick spacing    : {_C}x{_R}={_sp_str(ax.xaxis.get_major_locator())}  {_C}y{_R}={_sp_str(ax.yaxis.get_major_locator())}")
        print(f"  Minor count     : {_C}x{_R}={_mn_str(ax.xaxis.get_minor_locator())}  {_C}y{_R}={_mn_str(ax.yaxis.get_minor_locator())}")

    # NEW: style / diagnostics printer (clean version)
    def print_style_info():
        cts = getattr(_bp, 'cif_tick_series', None) if _bp is not None else None
        # Read show_cif_hkl from __main__ module (where it's stored when toggled)
        show_hkl = None
        try:
            _bp_module = sys.modules.get('__main__')
            if _bp_module is not None and hasattr(_bp_module, 'show_cif_hkl'):
                show_hkl = bool(getattr(_bp_module, 'show_cif_hkl', False))
        except Exception:
            pass
        # Fall back to _bp object if not in __main__
        if show_hkl is None and _bp is not None:
            show_hkl = bool(getattr(_bp, 'show_cif_hkl', False)) if hasattr(_bp, 'show_cif_hkl') else None
        return _bp_print_style_info(
            fig, ax,
            y_data_list, labels,
            offsets_list,
            x_full_list, raw_y_full_list,
            args, delta,
            label_text_objects,
            tick_state,
            cts,
            show_hkl,
        )

    # NEW: export current style to .bpcfg
    def export_style_config(filename, base_path=None, overwrite_path=None, force_kind=None):
        cts = _cif_series_for_session()
        show_titles = bool(getattr(_bp, 'show_cif_titles', True)) if _bp is not None else True
        return _export_style_config(
            filename,
            fig,
            ax,
            y_data_list,
            labels,
            delta,
            args,
            tick_state,
            offsets_list,
            cts,
            label_text_objects,
            base_path,
            show_cif_titles=show_titles,
            overwrite_path=overwrite_path,
            force_kind=force_kind,
        )

    # NEW: apply imported style config (restricted application)
    def apply_style_config(filename):
        cts = _cif_series_for_session()
        hkl_map = getattr(_bp, 'cif_hkl_label_map', None) if _bp is not None else None
        res = _bp_apply_style_config(
            filename,
            fig,
            ax,
            x_data_list,
            y_data_list,
            orig_y,
            offsets_list,
            label_text_objects,
            args,
            tick_state,
            labels,
            update_labels,
            cts,
            hkl_map,
            adjust_margins,
        )
        _sync_fig_cif_tick_series()
        try:
            if _bp is not None:
                if hasattr(fig, '_bp_show_cif_hkl'):
                    setattr(_bp, 'show_cif_hkl', bool(fig._bp_show_cif_hkl))
                if hasattr(fig, '_bp_show_cif_titles'):
                    setattr(_bp, 'show_cif_titles', bool(fig._bp_show_cif_titles))
                if hasattr(fig, '_bp_cif_set_visible'):
                    setattr(_bp, 'cif_set_visible', list(fig._bp_cif_set_visible))
        except Exception:
            pass
        # Sync top/right tick label2 fonts with current rcParams after style import
        try:
            fam_chain = plt.rcParams.get('font.sans-serif')
            fam0 = fam_chain[0] if isinstance(fam_chain, list) and fam_chain else None
            size0 = plt.rcParams.get('font.size', None)
            if fam0 or size0 is not None:
                for t in ax.xaxis.get_major_ticks():
                    if hasattr(t, 'label2'):
                        if size0 is not None: t.label2.set_size(size0)
                        if fam0: t.label2.set_family(fam0)
                for t in ax.yaxis.get_major_ticks():
                    if hasattr(t, 'label2'):
                        if size0 is not None: t.label2.set_size(size0)
                        if fam0: t.label2.set_family(fam0)
        except Exception:
            pass
        return res

    # Initialize with current defaults
    update_tick_visibility()

    # --- Crosshair state & toggle function (UPDATED) ---
    # Get wavelength info from cif_globals if available
    file_wavelength_info = cif_globals.get('file_wavelength_info', []) if cif_globals else []
    
    crosshair = {
        'active': False,
        'hline': None,
        'vline': None,
        'text': None,
        'cid_motion': None,
        'wavelength': None  # only used when axis is 2theta (fallback if no file info)
    }

    def toggle_crosshair():
        if not crosshair['active']:
            # Only ask for wavelength if it's diffraction data, not using Q, and no file wavelength info
            if is_diffraction and not use_Q and not file_wavelength_info:
                try:
                    wl_in = _safe_input("Enter wavelength in Å for Q,d display (blank=skip, q=cancel): ").strip()
                    if wl_in.lower() == 'q':
                        print("Canceled.")
                        return
                    if wl_in:
                        crosshair['wavelength'] = float(wl_in)
                    else:
                        crosshair['wavelength'] = None
                except ValueError:
                    print("Invalid wavelength. Skipping Q,d calculation.")
                    crosshair['wavelength'] = None
            vline = ax.axvline(x=ax.get_xlim()[0], color='0.35', ls='--', lw=0.8, alpha=0.85, zorder=9999)
            hline = ax.axhline(y=ax.get_ylim()[0], color='0.35', ls='--', lw=0.8, alpha=0.85, zorder=9999)
            txt = ax.text(1.0, 1.0, "",
                          ha='right', va='bottom',
                          transform=ax.transAxes,
                          fontsize=max(9, int(0.6 * plt.rcParams.get('font.size', 16))),
                          color='0.15',
                          bbox=dict(boxstyle='round,pad=0.25', fc='white', ec='0.7', alpha=0.8))

            def on_move(event):
                if event.inaxes != ax or event.xdata is None or event.ydata is None:
                    return
                x = float(event.xdata)
                y = float(event.ydata)
                vline.set_xdata([x, x])
                hline.set_ydata([y, y])

                # For diffraction data, show Q/d calculations
                if is_diffraction:
                    if use_Q:
                        Q = x
                        if Q != 0:
                            d = 2 * np.pi / Q
                            txt.set_text(f"Q={Q:.6g}\nd={d:.6g} Å\ny={y:.6g}")
                        else:
                            txt.set_text(f"Q={Q:.6g}\nd=∞\ny={y:.6g}")
                    elif use_r:
                        txt.set_text(f"r={x:.6g} Å\ny={y:.6g}")
                    else:
                        # 2θ mode
                        # Check if we have file wavelength info (dual wavelength conversion)
                        wl_info = file_wavelength_info[0] if file_wavelength_info else None
                        if wl_info and wl_info.get('original_wl') is not None and wl_info.get('conversion_wl') is not None:
                            # Dual wavelength: show original 2theta and current 2theta
                            orig_wl = wl_info['original_wl']
                            conv_wl = wl_info['conversion_wl']
                            # Current 2theta is x
                            # Calculate original 2theta: current 2theta -> Q -> original 2theta
                            theta_rad = np.radians(x / 2.0)
                            Q = 4 * np.pi * np.sin(theta_rad) / conv_wl
                            # Convert Q back to original 2theta
                            sin_theta_orig = Q * orig_wl / (4 * np.pi)
                            sin_theta_orig = np.clip(sin_theta_orig, -1.0, 1.0)
                            theta_orig_rad = np.arcsin(sin_theta_orig)
                            orig_2theta = np.degrees(2 * theta_orig_rad)
                            if Q != 0:
                                d = 2 * np.pi / Q
                                txt.set_text(f"2θ={x:.6g}° (λ₂={conv_wl:.5f})\n2θ₀={orig_2theta:.6g}° (λ₁={orig_wl:.5f})\nQ={Q:.6g}\nd={d:.6g} Å\ny={y:.6g}")
                            else:
                                txt.set_text(f"2θ={x:.6g}° (λ₂={conv_wl:.5f})\n2θ₀={orig_2theta:.6g}° (λ₁={orig_wl:.5f})\nQ=0\nd=∞\ny={y:.6g}")
                        elif crosshair['wavelength'] is not None:
                            lam = crosshair['wavelength']
                            theta_rad = np.radians(x / 2.0)
                            Q = 4 * np.pi * np.sin(theta_rad) / lam
                            if Q != 0:
                                d = 2 * np.pi / Q
                                txt.set_text(f"2θ={x:.6g}°\nQ={Q:.6g}\nd={d:.6g} Å\ny={y:.6g}")
                            else:
                                txt.set_text(f"2θ={x:.6g}°\nQ=0\nd=∞\ny={y:.6g}")
                        else:
                            txt.set_text(f"2θ={x:.6g}°\ny={y:.6g}")
                else:
                    # For non-diffraction data, just show x and y values
                    txt.set_text(f"x={x:.6g}\ny={y:.6g}")

                fig.canvas.draw_idle()

            cid = fig.canvas.mpl_connect('motion_notify_event', on_move)
            crosshair.update({'active': True, 'hline': hline, 'vline': vline,
                              'text': txt, 'cid_motion': cid})
            print("Crosshair ON. Move mouse over axes. Press 'n' again to turn off.")
        else:
            if crosshair['cid_motion'] is not None:
                fig.canvas.mpl_disconnect(crosshair['cid_motion'])
            for k in ('hline', 'vline', 'text'):
                art = crosshair[k]
                if art is not None:
                    try:
                        art.remove()
                    except Exception:
                        pass
            crosshair.update({'active': False, 'hline': None, 'vline': None,
                              'text': None, 'cid_motion': None})
            fig.canvas.draw_idle()
            print("Crosshair OFF.")
    # --- End crosshair additions (UPDATED) ---

    # -------- Session helper now provided by batplot.session (dump only here) --------

    
    # history management:
    state_history = []

    # ====================================================================
    # SMOOTHING AND REDUCE ROWS HELPER FUNCTIONS
    # ====================================================================
    
    def _get_last_reduce_rows_settings(method: str) -> dict:
        """Get last reduce rows settings from config file.
        
        Args:
            method: Method name ('delete_skip', 'delete_missing', 'merge')
        
        Returns:
            Dictionary with last settings for the method, or empty dict if none
        """
        config = load_config()
        last_settings = config.get('last_reduce_rows_settings', {})
        return last_settings.get(method, {})
    
    def _save_last_reduce_rows_settings(method: str, settings: dict) -> None:
        """Save last reduce rows settings to config file.
        
        Args:
            method: Method name ('delete_skip', 'delete_missing', 'merge')
            settings: Dictionary with settings to save
        """
        config = load_config()
        if 'last_reduce_rows_settings' not in config:
            config['last_reduce_rows_settings'] = {}
        config['last_reduce_rows_settings'][method] = settings
        save_config(config)
    
    def _get_last_smooth_settings_from_config() -> dict:
        """Get last smooth settings from config file (persistent across sessions).
        
        Returns:
            Dictionary with last smooth settings, or empty dict if none
        """
        config = load_config()
        return config.get('last_smooth_settings', {})
    
    def _save_last_smooth_settings_to_config(settings: dict) -> None:
        """Save last smooth settings to config file (persistent across sessions).
        
        Args:
            settings: Dictionary with smooth settings to save
        """
        config = load_config()
        config['last_smooth_settings'] = settings
        save_config(config)
    
    def _ensure_original_data():
        """Ensure original data is stored for all curves."""
        if not hasattr(fig, '_original_x_data_list'):
            fig._original_x_data_list = [np.array(a, copy=True) for a in x_data_list]
            fig._original_y_data_list = [np.array(a, copy=True) for a in y_data_list]
    
    def _update_full_processed_data():
        """Update the full processed data (after all processing steps, before any X-range filtering)."""
        # This stores the complete processed data (reduce + smooth + derivative) for X-range filtering
        fig._full_processed_x_data_list = [np.array(a, copy=True) for a in x_data_list]
        fig._full_processed_y_data_list = [np.array(a, copy=True) for a in y_data_list]
    
    def _reset_to_original():
        """Reset all curves to original data."""
        if not hasattr(fig, '_original_x_data_list'):
            return (False, 0, 0)
        reset_count = 0
        total_points = 0
        for i in range(min(len(fig._original_x_data_list), _nlines())):
            try:
                orig_x = fig._original_x_data_list[i]
                orig_y = fig._original_y_data_list[i]
                # Restore offsets
                if i < len(offsets_list):
                    orig_y_with_offset = orig_y + offsets_list[i]
                else:
                    orig_y_with_offset = orig_y.copy()
                _line(i).set_data(orig_x, orig_y_with_offset)
                x_data_list[i] = orig_x.copy()
                y_data_list[i] = orig_y_with_offset.copy()
                reset_count += 1
                total_points += len(orig_x)
            except Exception:
                pass
        # Clear processing settings
        if hasattr(fig, '_smooth_settings'):
            delattr(fig, '_smooth_settings')
        return (reset_count > 0, reset_count, total_points)

    def _apply_data_changes():
        """Update plot and data lists after data modification."""
        for i in range(min(_nlines(), len(x_data_list), len(y_data_list))):
            try:
                _line(i).set_data(x_data_list[i], y_data_list[i])
            except Exception:
                pass
        try:
            fig.canvas.draw_idle()
        except Exception:
            pass

    def _update_ylabel_for_derivative(order: int, current_label: Optional[str] = None, is_reversed: bool = False) -> str:
        """Generate appropriate y-axis label for derivative.
        
        Args:
            order: 1 for first derivative, 2 for second derivative
            current_label: Current y-axis label (optional)
            is_reversed: True for reversed derivative (dx/dy), False for normal (dy/dx)
        
        Returns:
            New y-axis label string
        """
        if current_label is None:
            current_label = ax.get_ylabel() or "Y"
        
        # Try to detect common patterns and update accordingly
        current_lower = current_label.lower()
        
        if is_reversed:
            # Reversed derivative: dx/dy or d²x/dy²
            y_label = current_label if current_label and current_label != "Y" else (ax.get_ylabel() or "Y")
            if order == 1:
                # First reversed derivative: dx/dy
                if x_label:
                    return f"d({x_label})/d({y_label})"
                else:
                    return f"dx/d({y_label})"
            else:  # order == 2
                # Second reversed derivative: d²x/dy²
                if x_label:
                    return f"d²({x_label})/d({y_label})²"
                else:
                    return f"d²x/d({y_label})²"
        
        # Normal derivative: dy/dx or d²y/dx²
        if order == 1:
            # First derivative: dy/dx or dY/dX
            if "/" in current_label:
                # If already has derivative notation, try to increment
                if "d²" in current_label or "d2" in current_lower:
                    # Change from 2nd to 1st (shouldn't normally happen, but handle it)
                    new_label = current_label.replace("d²", "d").replace("d2", "d")
                    return new_label
                elif "d" in current_label.lower() and "/" in current_label:
                    # Already has derivative, keep as is but update order if needed
                    return current_label
            # Add d/dx prefix or suffix
            if x_label:
                if any(op in current_label for op in ["/", "(", "["]):
                    # Complex label, prepend d/dx
                    return f"d({current_label})/d({x_label})"
                else:
                    # Simple label, use d/dx notation
                    return f"d({current_label})/d({x_label})"
            else:
                return f"d({current_label})/dx"
        else:  # order == 2
            # Second derivative: d²y/dx² or d2Y/dX2
            if "/" in current_label:
                if "d²" in current_label or "d2" in current_lower:
                    # Already 2nd derivative, keep as is
                    return current_label
                elif "d" in current_label.lower() and "/" in current_label:
                    # First derivative, convert to second
                    new_label = current_label.replace("d(", "d²(").replace("d2(", "d²(").replace("d/", "d²/").replace("/d(", "²/d(")
                    return new_label
            # Add d²/dx² prefix
            if x_label:
                if any(op in current_label for op in ["/", "(", "["]):
                    return f"d²({current_label})/d({x_label})²"
                else:
                    return f"d²({current_label})/d({x_label})²"
            else:
                return f"d²({current_label})/dx²"
        
        return current_label

    def _ensure_pre_derivative_data():
        """Ensure pre-derivative data is stored for reset."""
        if not hasattr(fig, '_pre_derivative_x_data_list'):
            fig._pre_derivative_x_data_list = [np.array(a, copy=True) for a in x_data_list]
            fig._pre_derivative_y_data_list = [np.array(a, copy=True) for a in y_data_list]
            fig._pre_derivative_ylabel = ax.get_ylabel() or ""

    def _reset_from_derivative():
        """Reset all curves from derivative back to pre-derivative state."""
        if not hasattr(fig, '_pre_derivative_x_data_list'):
            return (False, 0, 0)
        reset_count = 0
        total_points = 0
        for i in range(min(len(fig._pre_derivative_x_data_list), _nlines())):
            try:
                pre_x = fig._pre_derivative_x_data_list[i]
                pre_y = fig._pre_derivative_y_data_list[i]
                # Restore offsets
                if i < len(offsets_list):
                    pre_y_with_offset = pre_y + offsets_list[i]
                else:
                    pre_y_with_offset = pre_y.copy()
                _line(i).set_data(pre_x, pre_y_with_offset)
                x_data_list[i] = pre_x.copy()
                y_data_list[i] = pre_y_with_offset.copy()
                reset_count += 1
                total_points += len(pre_x)
            except Exception:
                pass
        # Restore y-axis label
        if hasattr(fig, '_pre_derivative_ylabel'):
            ax.set_ylabel(fig._pre_derivative_ylabel)
        # Clear derivative settings
        if hasattr(fig, '_derivative_order'):
            delattr(fig, '_derivative_order')
        return (reset_count > 0, reset_count, total_points)

    def _capture_tick_minor_count(ax_obj):
        """Return {x, y} AutoMinorLocator ndivs, or None if not AutoMinorLocator."""
        def _ndivs(locator):
            try:
                if isinstance(locator, AutoMinorLocator):
                    return int(locator._ndivs)
            except Exception:
                pass
            return None
        return {
            'x': _ndivs(ax_obj.xaxis.get_minor_locator()),
            'y': _ndivs(ax_obj.yaxis.get_minor_locator()),
        }

    def _restore_tick_minor_count(ax_obj, counts):
        """Restore minor tick count from a dict captured by _capture_tick_minor_count."""
        if not counts:
            return
        for axis_obj, key in ((ax_obj.xaxis, 'x'), (ax_obj.yaxis, 'y')):
            val = counts.get(key)
            if val is not None:
                try:
                    axis_obj.set_minor_locator(AutoMinorLocator(int(val)))
                except Exception:
                    pass

    def push_state(note=""):
        """Snapshot current editable state (before a modifying action)."""
        try:
            # Helper to capture a representative tick line width
            def _tick_width(axis_obj, which):
                try:
                    tick_kw = axis_obj._major_tick_kw if which == 'major' else axis_obj._minor_tick_kw
                    width = tick_kw.get('width')
                    if width is None:
                        axis_name = getattr(axis_obj, 'axis_name', 'x')
                        rc_key = f"{axis_name}tick.{which}.width"
                        width = plt.rcParams.get(cast(Any, rc_key))
                    if width is not None:
                        return float(width)
                except Exception:
                    return None
                return None
            _cts_for_snap = _cif_series_for_session()
            snap = {
                "note": note,
                "xlim": ax.get_xlim(),
                "ylim": ax.get_ylim(),
                "tick_state": tick_state.copy(),
                "font_size": plt.rcParams.get('font.size'),
                "font_chain": list(plt.rcParams.get('font.sans-serif', [])),
                "mathtext_fontset": plt.rcParams.get('mathtext.fontset'),
                "labels": list(labels),
                "delta": delta,
                "lines": [],
                "fig_size": list(fig.get_size_inches()),
                "fig_dpi": fig.dpi,
                "axes_bbox": [float(v) for v in ax.get_position().bounds],  # x0,y0,w,h
                "axis_labels": {"xlabel": ax.get_xlabel(), "ylabel": ax.get_ylabel()},
                "axis_titles": {"top_x": bool(getattr(ax, '_top_xlabel_on', False)),
                                 "right_y": bool(getattr(ax, '_right_ylabel_on', False)),
                                 "has_bottom_x": bool(ax.xaxis.label.get_visible()),
                                 "has_left_y": bool(ax.yaxis.label.get_visible())},
                "title_offsets": capture_title_offsets(ax),
                "spines": {name: {"lw": sp.get_linewidth(), "color": sp.get_edgecolor(), "visible": sp.get_visible()} for name, sp in ax.spines.items()},
                "tick_widths": {
                    "x_major": _tick_width(ax.xaxis, 'major'),
                    "x_minor": _tick_width(ax.xaxis, 'minor'),
                    "y_major": _tick_width(ax.yaxis, 'major'),
                    "y_minor": _tick_width(ax.yaxis, 'minor')
                },
                "tick_lengths": dict(getattr(fig, '_tick_lengths', {'major': None, 'minor': None})),
                "tick_direction": getattr(fig, '_tick_direction', 'out'),
                "tick_spacing": capture_axes_tick_locators(ax, ('x', 'y')),
                "tick_minor_count": _capture_tick_minor_count(ax),
                "cif_tick_series": (list(_cts_for_snap) if _cts_for_snap is not None else None),
                "show_cif_hkl": (bool(getattr(_bp, 'show_cif_hkl')) if _bp is not None and hasattr(_bp, 'show_cif_hkl') else False),
                "show_cif_titles": (bool(getattr(_bp, 'show_cif_titles')) if _bp is not None and hasattr(_bp, 'show_cif_titles') else True),
                "rotation_angle": getattr(ax, '_rotation_angle', 0),
                "stack_label_at_bottom": getattr(fig, '_stack_label_at_bottom', False),
                "label_anchor_left": getattr(fig, '_label_anchor_left', False),
                "grid": any(line.get_visible() for line in ax.get_xgridlines() + ax.get_ygridlines()),
                "curve_palettes": list(getattr(fig, '_curve_palette_history', []) or []),
                "axis_style": capture_xy_axis_style(ax),
            }
            # Optional per-set CIF visibility state for 1D mode
            try:
                _bp_module_snap = _sys_snap.modules.get('__main__')
                if _bp_module_snap is not None and hasattr(_bp_module_snap, 'cif_set_visible'):
                    snap["cif_set_visible"] = list(getattr(_bp_module_snap, 'cif_set_visible') or [])
            except Exception:
                pass
            try:
                snap["cif_stack_y_offsets"] = list(getattr(fig, '_bp_cif_stack_y_offsets', []) or [])
            except Exception:
                pass
            # Line + data arrays
            for i, ln in _iter_lines():
                snap["lines"].append({
                    "index": i,
                    "x": np.array(ln.get_xdata(), copy=True),
                    "y": np.array(ln.get_ydata(), copy=True),
                    "color": ln.get_color(),
                    "lw": ln.get_linewidth(),
                    "ls": ln.get_linestyle(),
                    "marker": ln.get_marker(),
                    "markersize": getattr(ln, 'get_markersize', lambda: None)(),
                    "mfc": getattr(ln, 'get_markerfacecolor', lambda: None)(),
                    "mec": getattr(ln, 'get_markeredgecolor', lambda: None)(),
                    "alpha": ln.get_alpha()
                })
            # Data lists
            snap["x_data_list"] = [np.array(a, copy=True) for a in x_data_list]
            snap["y_data_list"] = [np.array(a, copy=True) for a in y_data_list]
            snap["orig_y"]      = [np.array(a, copy=True) for a in orig_y]
            snap["offsets"]     = list(offsets_list)
            # Processed data (for smooth/reduce operations)
            if hasattr(fig, '_original_x_data_list'):
                snap["original_x_data_list"] = [np.array(a, copy=True) for a in fig._original_x_data_list]
                snap["original_y_data_list"] = [np.array(a, copy=True) for a in fig._original_y_data_list]
            if hasattr(fig, '_full_processed_x_data_list'):
                snap["full_processed_x_data_list"] = [np.array(a, copy=True) for a in fig._full_processed_x_data_list]
                snap["full_processed_y_data_list"] = [np.array(a, copy=True) for a in fig._full_processed_y_data_list]
            if hasattr(fig, '_smooth_settings'):
                snap["smooth_settings"] = dict(fig._smooth_settings)
            if hasattr(fig, '_last_smooth_settings'):
                snap["last_smooth_settings"] = dict(fig._last_smooth_settings)
            # Derivative data (for derivative operations)
            if hasattr(fig, '_pre_derivative_x_data_list'):
                snap["pre_derivative_x_data_list"] = [np.array(a, copy=True) for a in fig._pre_derivative_x_data_list]
                snap["pre_derivative_y_data_list"] = [np.array(a, copy=True) for a in fig._pre_derivative_y_data_list]
                snap["pre_derivative_ylabel"] = str(getattr(fig, '_pre_derivative_ylabel', ''))
            if hasattr(fig, '_derivative_order'):
                snap["derivative_order"] = int(fig._derivative_order)
            if hasattr(fig, '_derivative_reversed'):
                snap["derivative_reversed"] = bool(fig._derivative_reversed)
            # Label text content
            snap["label_texts"] = [t.get_text() for t in label_text_objects]
            snap["label_text_visible"] = [bool(t.get_visible()) for t in label_text_objects]
            state_history.append(snap)
            if len(state_history) > 40:
                state_history.pop(0)
        except Exception as e:
            print(f"Warning: could not snapshot state: {e}")

    def restore_state():
        nonlocal delta
        if not state_history:
            print("No undo history.")
            return
        snap = state_history.pop()
        try:
            # Basic numeric state
            ax.set_xlim(*snap["xlim"]) 
            ax.set_ylim(*snap["ylim"]) 
            # Tick state
            snap_ts = snap.get("tick_state", {})
            for k, v in snap_ts.items():
                if k in tick_state:
                    tick_state[k] = v
            # If snapshot was legacy-only, map bx/tx/ly/ry into new keys
            if not any(k in snap_ts for k in ('b_ticks','t_ticks','l_ticks','r_ticks')):
                if 'bx' in snap_ts:
                    tick_state['b_ticks'] = bool(snap_ts.get('bx', tick_state['bx']))
                    tick_state['b_labels'] = bool(snap_ts.get('bx', tick_state['bx']))
                if 'tx' in snap_ts:
                    tick_state['t_ticks'] = bool(snap_ts.get('tx', tick_state['tx']))
                    tick_state['t_labels'] = bool(snap_ts.get('tx', tick_state['tx']))
                if 'ly' in snap_ts:
                    tick_state['l_ticks'] = bool(snap_ts.get('ly', tick_state['ly']))
                    tick_state['l_labels'] = bool(snap_ts.get('ly', tick_state['ly']))
                if 'ry' in snap_ts:
                    tick_state['r_ticks'] = bool(snap_ts.get('ry', tick_state['ry']))
                    tick_state['r_labels'] = bool(snap_ts.get('ry', tick_state['ry']))
            _sync_legacy_tick_keys()
            update_tick_visibility()

            # Fonts
            if snap["font_chain"]:
                plt.rcParams['font.family'] = 'sans-serif'
                plt.rcParams['font.sans-serif'] = snap["font_chain"]
            if snap["font_size"]:
                try:
                    plt.rcParams['font.size'] = snap["font_size"]
                except Exception:
                    pass
            if snap.get("mathtext_fontset"):
                try:
                    plt.rcParams['mathtext.fontset'] = snap["mathtext_fontset"]
                except Exception:
                    pass
            # Apply restored font settings to all existing text objects
            # This ensures labels, tick labels, etc. update to match restored font size/family
            try:
                sync_fonts()
            except Exception:
                pass

            # Figure size & dpi
            if snap.get("fig_size") and isinstance(snap["fig_size"], (list, tuple)) and len(snap["fig_size"])==2:
                try:
                    fig.set_size_inches(snap["fig_size"][0], snap["fig_size"][1], forward=True)
                except Exception:
                    pass
                # No message needed - canvas size is managed by system
            # Don't restore DPI from undo - use system default to avoid display-dependent issues
            
            # Restore axes (plot frame) via stored bbox if present
            if snap.get("axes_bbox") and isinstance(snap["axes_bbox"], (list, tuple)) and len(snap["axes_bbox"])==4:
                try:
                    x0,y0,w,h = snap["axes_bbox"]
                    left = x0; bottom = y0; right = x0 + w; top = y0 + h
                    if 0 < left < right <=1 and 0 < bottom < top <=1:
                        fig.subplots_adjust(left=left, right=right, bottom=bottom, top=top)
                except Exception:
                    pass

            # Axis labels (use low-level API to avoid layout recalculation)
            axis_labels = snap.get("axis_labels", {})
            if axis_labels.get("xlabel") is not None:
                ax.xaxis.label.set_text(axis_labels["xlabel"])
            if axis_labels.get("ylabel") is not None:
                ax.yaxis.label.set_text(axis_labels["ylabel"])
            at = snap.get("axis_titles", {})
            try:
                if "has_bottom_x" in at:
                    ax.xaxis.label.set_visible(bool(at["has_bottom_x"]))
                if "has_left_y" in at:
                    ax.yaxis.label.set_visible(bool(at["has_left_y"]))
            except Exception:
                pass
            # Manual offsets for all titles - support both old and new format
            restore_title_offsets(ax, snap.get("title_offsets", {}))

            # Axis title duplicates (top X / right Y)
            # Top X
            try:
                ax._top_xlabel_on = bool(at.get('top_x', False))
                position_top_xlabel()
            except Exception:
                pass
            # Right Y
            try:
                ax._right_ylabel_on = bool(at.get('right_y', False))
                position_right_ylabel()
            except Exception:
                pass
            # Note: Do NOT call position_bottom_xlabel() / position_left_ylabel() here
            # as it causes title drift when combined with fig.canvas.draw() below.
            # Title offsets are already restored from snapshot above.

            # Spines (linewidth, color, visibility)
            for name, spec in snap.get("spines", {}).items():
                sp_obj = ax.spines.get(name)
                if sp_obj is None:
                    continue
                try:
                    if "lw" in spec:
                        sp_obj.set_linewidth(spec["lw"])
                    if "color" in spec and spec["color"] is not None:
                        _ui_set_spine_side_color(ax, name, spec["color"], fig=fig)
                    if "visible" in spec:
                        try:
                            sp_obj.set_visible(bool(spec["visible"]))
                        except Exception:
                            pass
                except Exception:
                    pass

            # Tick widths
            tw = snap.get("tick_widths", {})
            try:
                if tw.get("x_major") is not None:
                    ax.tick_params(axis='x', which='major', width=tw["x_major"])
                if tw.get("x_minor") is not None:
                    ax.tick_params(axis='x', which='minor', width=tw["x_minor"]) 
                if tw.get("y_major") is not None:
                    ax.tick_params(axis='y', which='major', width=tw["y_major"]) 
                if tw.get("y_minor") is not None:
                    ax.tick_params(axis='y', which='minor', width=tw["y_minor"]) 
            except Exception:
                pass

            # Tick lengths
            tl = snap.get("tick_lengths", {})
            try:
                if tl.get("major") is not None:
                    ax.tick_params(axis='both', which='major', length=tl["major"])
                if tl.get("minor") is not None:
                    ax.tick_params(axis='both', which='minor', length=tl["minor"])
                if tl:
                    fig._tick_lengths = dict(tl)
            except Exception:
                pass

            # Tick direction
            try:
                tick_dir = snap.get("tick_direction", 'out')
                ax.tick_params(axis='both', which='both', direction=tick_dir)
                fig._tick_direction = tick_dir
            except Exception:
                pass

            # Tick spacing (n command)
            try:
                restore_axes_tick_locators(ax, snap.get("tick_spacing"), ('x', 'y'))
            except Exception:
                pass

            # Minor tick count (m command)
            try:
                _restore_tick_minor_count(ax, snap.get("tick_minor_count"))
            except Exception:
                pass

            # Tick/label colors and labelpads
            try:
                axis_style = snap.get("axis_style")
                if axis_style:
                    spine_specs = {
                        name: {"color": spec.get("color")}
                        for name, spec in snap.get("spines", {}).items()
                    }
                    apply_xy_axis_style(ax, axis_style, fig=fig, spines_cfg=spine_specs)
                    _ui_position_bottom_xlabel(ax, fig, tick_state)
                    _ui_position_left_ylabel(ax, fig, tick_state)
            except Exception:
                pass

            # Labels list
            labels[:] = snap["labels"]

            # Data & lines
            if len(snap["lines"]) == _nlines():
                for item in snap["lines"]:
                    i = item["index"]
                    ln = _line(i)
                    ln.set_data(item["x"], item["y"])
                    ln.set_linewidth(item["lw"])
                    ln.set_linestyle(item["ls"])
                    if item["marker"] is not None:
                        ln.set_marker(item["marker"])
                    if item.get("markersize") is not None:
                        try:
                            ln.set_markersize(item["markersize"])
                        except Exception:
                            pass
                    if item["alpha"] is not None:
                        ln.set_alpha(item["alpha"])
                    apply_curve_color(ln, item["color"])
                    if item.get("mfc") is not None:
                        try:
                            if str(item["mfc"]).lower() == "none":
                                ln.set_markerfacecolor("none")
                        except Exception:
                            pass
                    if item.get("mec") is not None:
                        try:
                            if str(item["mec"]).lower() == "none":
                                ln.set_markeredgecolor("none")
                        except Exception:
                            pass

            # Replace lists
            x_data_list[:] = [np.array(a, copy=True) for a in snap["x_data_list"]]
            y_data_list[:] = [np.array(a, copy=True) for a in snap["y_data_list"]]
            orig_y[:]      = [np.array(a, copy=True) for a in snap["orig_y"]]
            offsets_list[:] = list(snap["offsets"]) 
            delta = snap.get("delta", delta)
            
            # Restore processed data (for smooth/reduce operations)
            if "original_x_data_list" in snap:
                fig._original_x_data_list = [np.array(a, copy=True) for a in snap["original_x_data_list"]]
                fig._original_y_data_list = [np.array(a, copy=True) for a in snap["original_y_data_list"]]
            elif hasattr(fig, '_original_x_data_list'):
                # Clear if not in snapshot
                delattr(fig, '_original_x_data_list')
                delattr(fig, '_original_y_data_list')
            if "full_processed_x_data_list" in snap:
                fig._full_processed_x_data_list = [np.array(a, copy=True) for a in snap["full_processed_x_data_list"]]
                fig._full_processed_y_data_list = [np.array(a, copy=True) for a in snap["full_processed_y_data_list"]]
            elif hasattr(fig, '_full_processed_x_data_list'):
                # Clear if not in snapshot
                delattr(fig, '_full_processed_x_data_list')
                delattr(fig, '_full_processed_y_data_list')
            if "smooth_settings" in snap:
                fig._smooth_settings = dict(snap["smooth_settings"])
            elif hasattr(fig, '_smooth_settings'):
                delattr(fig, '_smooth_settings')
            if "last_smooth_settings" in snap:
                fig._last_smooth_settings = dict(snap["last_smooth_settings"])
            elif hasattr(fig, '_last_smooth_settings'):
                delattr(fig, '_last_smooth_settings')
            # Restore derivative data (for derivative operations)
            if "pre_derivative_x_data_list" in snap:
                fig._pre_derivative_x_data_list = [np.array(a, copy=True) for a in snap["pre_derivative_x_data_list"]]
                fig._pre_derivative_y_data_list = [np.array(a, copy=True) for a in snap["pre_derivative_y_data_list"]]
                fig._pre_derivative_ylabel = str(snap.get("pre_derivative_ylabel", ""))
            elif hasattr(fig, '_pre_derivative_x_data_list'):
                delattr(fig, '_pre_derivative_x_data_list')
                delattr(fig, '_pre_derivative_y_data_list')
                if hasattr(fig, '_pre_derivative_ylabel'):
                    delattr(fig, '_pre_derivative_ylabel')
            if "derivative_order" in snap:
                fig._derivative_order = int(snap["derivative_order"])
            elif hasattr(fig, '_derivative_order'):
                delattr(fig, '_derivative_order')
            if "derivative_reversed" in snap:
                fig._derivative_reversed = bool(snap["derivative_reversed"])
            elif hasattr(fig, '_derivative_reversed'):
                delattr(fig, '_derivative_reversed')
            # Restore y-axis label if derivative was applied
            if "derivative_order" in snap:
                try:
                    current_ylabel = ax.get_ylabel() or ""
                    order = int(snap["derivative_order"])
                    is_reversed = snap.get("derivative_reversed", False)
                    new_ylabel = _update_ylabel_for_derivative(order, current_ylabel, is_reversed=is_reversed)
                    ax.set_ylabel(new_ylabel)
                except Exception:
                    pass
            
            # DON'T recalculate y_data_list - trust the snapshotted data to avoid offset drift
            # The snapshot already captured the correct y_data_list with offsets applied.
            # Recalculating from orig_y + offsets_list can introduce floating-point errors
            # or inconsistencies if the data underwent transformations (normalize, etc.)
            
            # Update line data with restored values from snapshot
            # This ensures line visual data matches the snapshotted data lists exactly
            for i in range(min(_nlines(), len(x_data_list), len(y_data_list))):
                try:
                    _line(i).set_data(x_data_list[i], y_data_list[i])
                except Exception:
                    pass

            # Restore rotation angle
            if 'rotation_angle' in snap:
                ax._rotation_angle = snap['rotation_angle']

            # Restore legend position (stack_label_at_bottom)
            if 'stack_label_at_bottom' in snap:
                fig._stack_label_at_bottom = bool(snap['stack_label_at_bottom'])
            if 'label_anchor_left' in snap:
                fig._label_anchor_left = bool(snap['label_anchor_left'])

            if snap.get("curve_palettes"):
                fig._curve_palette_history = [
                    {
                        'palette': rec.get('palette'),
                        'indices': list(rec.get('indices', [])),
                        'low_clip': float(rec.get('low_clip', 0.08)),
                        'high_clip': float(rec.get('high_clip', 0.85)),
                    }
                    for rec in snap["curve_palettes"]
                    if rec.get('palette') and rec.get('indices')
                ]
            elif hasattr(fig, '_curve_palette_history'):
                delattr(fig, '_curve_palette_history')

            # Restore grid state
            if 'grid' in snap:
                try:
                    if snap['grid']:
                        ax.grid(True, color='0.85', linestyle='-', linewidth=0.5, alpha=0.7)
                    else:
                        ax.grid(False)
                except Exception:
                    pass

            # CIF tick sets & label visibility (write back to batplot module globals)
            if _bp is not None and snap.get("cif_tick_series") is not None and hasattr(_bp, 'cif_tick_series'):
                try:
                    getattr(_bp, 'cif_tick_series')[:] = [tuple(t) for t in snap["cif_tick_series"]]
                except Exception:
                    pass
                _sync_fig_cif_tick_series()
            if _bp is not None and 'show_cif_hkl' in snap:
                try:
                    new_state = bool(snap['show_cif_hkl'])
                    setattr(_bp, 'show_cif_hkl', new_state)
                    # Also store in __main__ module so draw function can access it
                    try:
                        _bp_module = sys.modules.get('__main__')
                        if _bp_module is not None:
                            setattr(_bp_module, 'show_cif_hkl', new_state)
                    except Exception:
                        pass
                except Exception:
                    pass
            if _bp is not None and 'show_cif_titles' in snap:
                try:
                    new_state = bool(snap['show_cif_titles'])
                    setattr(_bp, 'show_cif_titles', new_state)
                    # Also update figure attribute and __main__ module
                    fig._bp_show_cif_titles = new_state
                    try:
                        _bp_module = sys.modules.get('__main__')
                        if _bp_module is not None:
                            setattr(_bp_module, 'show_cif_titles', new_state)
                    except Exception:
                        pass
                except Exception:
                    pass
            # Restore CIF per-set visibility if present
            if 'cif_set_visible' in snap:
                try:
                    _bp_module = sys.modules.get('__main__')
                    if _bp_module is not None:
                        setattr(_bp_module, 'cif_set_visible', list(snap['cif_set_visible']))
                except Exception:
                    pass
            if 'cif_stack_y_offsets' in snap:
                try:
                    fig._bp_cif_stack_y_offsets = list(snap['cif_stack_y_offsets'])
                except Exception:
                    pass
            # Redraw CIF ticks after restoration if available
            if hasattr(ax, '_cif_draw_func'):
                try:
                    ax._cif_draw_func()
                except Exception:
                    pass

            # Restore label texts (keep numbering style)
            for i, txt in enumerate(label_text_objects):
                base = labels[i] if i < len(labels) else ""
                txt.set_text(f"{i+1}: {base}")

            update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
            label_vis = snap.get("label_text_visible")
            if isinstance(label_vis, list):
                for txt, visible in zip(label_text_objects, label_vis):
                    try:
                        txt.set_visible(bool(visible))
                    except Exception:
                        pass
                try:
                    fig._curve_names_visible = any(bool(v) for v in label_vis)
                except Exception:
                    pass
            try:
                globals()['tick_state'] = tick_state
            except Exception:
                pass
            try:
                fig.canvas.draw()
            except Exception:
                try: fig.canvas.draw_idle()
                except Exception: pass
            print("Undo: restored previous state.")
        except Exception as e:
            print(f"Error restoring state: {e}")


    def _xy_action_context():
        return XyActionContext(
            fig=fig,
            ax=ax,
            x_data_list=x_data_list,
            y_data_list=y_data_list,
            orig_y=orig_y,
            x_full_list=x_full_list,
            raw_y_full_list=raw_y_full_list,
            offsets_list=offsets_list,
            labels=labels,
            label_text_objects=label_text_objects,
            delta=delta,
            args=args,
            tick_state=tick_state,
            source_file_paths=source_file_paths,
            bp=_bp,
            safe_input=_safe_input,
            colorize_prompt=colorize_prompt,
            format_file_timestamp=format_file_timestamp,
            cif_series_for_session=_cif_series_for_session,
            print_style_info=print_style_info,
            export_style_config=export_style_config,
            apply_style_config=apply_style_config,
            push_state=push_state,
            restore_state=restore_state,
        )

    pending_key = None
    while True:
        try:
            print_main_menu()
            if pending_key is not None:
                key = pending_key
                pending_key = None
            else:
                key = _safe_input(colorize_prompt("Press a key: ")).strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\n\nExiting interactive menu...")
            break
        
        if not key:
            continue

        # NEW: disable 'y' and 'd' in stack mode
        if args.stack and key in ('y', 'd'):
            print("Option disabled in --stack mode.")
            continue

        if key == 'q':
            if canvas_mode:
                break
            try:
                confirm = _safe_input(colorize_prompt("Quit interactive? Remember to save (e=export, s=save). Quit now? (y/n): ")).strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nExiting interactive menu...")
                break
            if confirm == 'y':
                break
            elif confirm in ('e', 's'):
                pending_key = confirm
                continue
            else:
                continue
        elif key in ('cif', 'z', 'j'):
            run_cif_ticks_menu(
                ax=ax, fig=fig, _bp=_bp,
                colorize_menu=colorize_menu, colorize_prompt=colorize_prompt,
                _safe_input=_safe_input, push_state=push_state,
                _print_cif_phase_list=_print_cif_phase_list,
                _apply_cif_phase_label_rename=_apply_cif_phase_label_rename,
                _sync_fig_cif_tick_series=_sync_fig_cif_tick_series,
            )
        elif key == 'h':  # legend submenu
            try:
                while True:
                    print("\n\033[1mLegend submenu:\033[0m")
                    print("  " + colorize_menu("v: show/hide curve names"))
                    current_pos = _current_label_position()
                    print(f"  {colorize_menu(f's: legend position (current: {current_pos})')}")
                    print(f"  {colorize_menu('q: back to main menu')}")
                    sub_key = _safe_input(colorize_prompt("Choose (v/s/q): ")).strip().lower()
                    
                    if sub_key == 'q':
                        break
                    elif sub_key == 'v':
                        # Toggle curve name labels visibility
                        push_state("legend-visibility")
                        first_visible = label_text_objects[0].get_visible() if label_text_objects else True
                        new_state = not first_visible
                        for lbl in label_text_objects:
                            lbl.set_visible(new_state)
                        fig._curve_names_visible = new_state
                        stack_label_bottom = getattr(fig, '_stack_label_at_bottom', False)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, stack_label_bottom)
                        fig.canvas.draw_idle()
                        print(f"Curve name labels {'ON' if new_state else 'OFF'}.")
                    elif sub_key == 's':
                        print("\nChoose legend position:")
                        print("  " + colorize_menu("1: top-right"))
                        print("  " + colorize_menu("2: top-left"))
                        print("  " + colorize_menu("3: bottom-right"))
                        print("  " + colorize_menu("4: bottom-left"))
                        choice = _safe_input(colorize_prompt("Position (1-4, q=cancel): ")).strip().lower()
                        options = {
                            '1': (False, False),
                            '2': (False, True),
                            '3': (True, False),
                            '4': (True, True),
                        }
                        if not choice or choice == 'q':
                            continue
                        if choice in options:
                            push_state("legend-position")
                            bottom, left = options[choice]
                            _apply_legend_position(bottom, left)
                            new_pos = f"{'bottom' if bottom else 'top'}-{'left' if left else 'right'}"
                            print(f"Legend position changed to {new_pos}.")
                        else:
                            print("Unknown option.")
                    else:
                        print("Unknown option.")
            except Exception as e:
                print(f"Error in legend submenu: {e}")
            continue
        elif key == 'j':  # toggle CIF title labels (filename labels)
            # Check if CIF files exist before allowing this command
            has_cif = False
            try:
                has_cif = any(f.split(':')[0].lower().endswith('.cif') for f in args.files)
                if not has_cif and _bp is not None:
                    has_cif = bool(getattr(_bp, 'cif_tick_series', None))
            except Exception:
                pass
            if not has_cif:
                print("Unknown option.")
                continue
            try:
                push_state("toggle-cif-titles")
                # Preserve both x and y-axis limits to prevent movement
                prev_xlim = ax.get_xlim()
                prev_ylim = ax.get_ylim()
                # Flip visibility flag for CIF titles
                cur = bool(getattr(_bp, 'show_cif_titles', True)) if _bp is not None else True
                new_state = not cur
                if _bp is not None:
                    setattr(_bp, 'show_cif_titles', new_state)
                # Also store on figure for draw_cif_ticks to access
                fig._bp_show_cif_titles = new_state
                # Also update __main__ module for backward compatibility
                try:
                    _bp_module = sys.modules.get('__main__')
                    if _bp_module is not None:
                        setattr(_bp_module, 'show_cif_titles', new_state)
                except Exception:
                    pass
                # Avoid re-entrant extension while redrawing
                prev_ext = bool(getattr(_bp, 'cif_extend_suspended', False)) if _bp is not None else False
                if _bp is not None:
                    setattr(_bp, 'cif_extend_suspended', True)
                if hasattr(ax, '_cif_draw_func'):
                    ax._cif_draw_func()
                if _bp is not None:
                    setattr(_bp, 'cif_extend_suspended', prev_ext)
                print(f"CIF title labels {'ON' if new_state else 'OFF'}.")
            except Exception as e:
                print(f"Error toggling CIF titles: {e}")
            continue
        elif key == 'b':  # <-- UNDO
            handle_undo(_xy_action_context())
            continue
        elif key == 'n':
            try:
                toggle_crosshair()
            except Exception as e:
                print(f"Error toggling crosshair: {e}")
            continue
        elif key == 'os':
            # Quick overwrite of last saved session (.pkl)
            handle_quick_overwrite_session(_xy_action_context())
            continue
        elif key in ('ops', 'opsg'):
            # Quick overwrite of last exported style file (.bps / .bpsg)
            handle_quick_overwrite_style(_xy_action_context(), key)
            continue
        elif key == 'oe':
            # Quick overwrite of last exported figure
            handle_quick_overwrite_figure(_xy_action_context())
            continue
        elif key == 's':
            # Save current interactive session with numbered overwrite picker
            handle_save_session(_xy_action_context())
            continue
        elif key == 'w':  # hidden game remains on 'i'
            play_jump_game(_safe_input); continue
        elif key == 'c':
            run_xy_color_menu(
                ax=ax,
                fig=fig,
                labels=labels,
                y_data_list=y_data_list,
                label_text_objects=label_text_objects,
                stack=args.stack,
                args_files=args.files,
                line_getter=_line,
                bp=_bp,
                get_cif_series=lambda: (getattr(_bp, 'cif_tick_series', None) if _bp is not None else None),
                sync_fig_cif_tick_series=_sync_fig_cif_tick_series,
                position_top_xlabel=position_top_xlabel,
                position_right_ylabel=position_right_ylabel,
                push_state=push_state,
                safe_input=_safe_input,
                colorize_prompt=colorize_prompt,
            )
        elif key == 'r':
            run_xy_rename_menu(
                ax=ax,
                fig=fig,
                labels=labels,
                label_text_objects=label_text_objects,
                args_files=args.files,
                get_cif_series=lambda: (getattr(_bp, 'cif_tick_series', None) if _bp is not None else None),
                print_cif_phase_list=_print_cif_phase_list,
                apply_cif_phase_label_rename=_apply_cif_phase_label_rename,
                position_top_xlabel=position_top_xlabel,
                position_bottom_xlabel=position_bottom_xlabel,
                position_right_ylabel=position_right_ylabel,
                position_left_ylabel=position_left_ylabel,
                sync_fonts=sync_fonts,
                push_state=push_state,
                safe_input=_safe_input,
            )
        elif key == 'a':
            run_rearrange_menu(
                args=args, ax=ax, fig=fig, labels=labels,
                label_text_objects=label_text_objects,
                x_data_list=x_data_list, y_data_list=y_data_list,
                orig_y=orig_y, offsets_list=offsets_list,
                x_full_list=x_full_list, raw_y_full_list=raw_y_full_list,
                delta=delta, push_state=push_state,
                _safe_input=_safe_input, _line=_line, _lines_by_curve=_lines_by_curve,
            )
        elif key == 'x':
            run_x_range_menu(
                args=args, ax=ax, fig=fig, labels=labels,
                label_text_objects=label_text_objects,
                x_data_list=x_data_list, y_data_list=y_data_list,
                orig_y=orig_y, offsets_list=offsets_list,
                x_full_list=x_full_list, raw_y_full_list=raw_y_full_list,
                push_state=push_state, _safe_input=_safe_input, _line=_line,
                colorize_menu=colorize_menu, colorize_prompt=colorize_prompt,
            )
        elif key == 'y':  # <-- Y-RANGE HANDLER (now only reachable if not args.stack)
            run_y_range_menu(
                args=args, ax=ax, fig=fig,
                label_text_objects=label_text_objects,
                y_data_list=y_data_list, push_state=push_state,
                _safe_input=_safe_input,
                colorize_menu=colorize_menu, colorize_prompt=colorize_prompt,
            )
        elif key == 'd':  # <-- DERIVATIVE HANDLER
            run_derivative_menu(
                args=args, ax=ax, fig=fig,
                label_text_objects=label_text_objects,
                x_data_list=x_data_list, y_data_list=y_data_list,
                offsets_list=offsets_list, push_state=push_state,
                _safe_input=_safe_input,
                _apply_data_changes=_apply_data_changes,
                _ensure_pre_derivative_data=_ensure_pre_derivative_data,
                _reset_from_derivative=_reset_from_derivative,
                _update_full_processed_data=_update_full_processed_data,
                _update_ylabel_for_derivative=_update_ylabel_for_derivative,
                colorize_menu=colorize_menu, colorize_prompt=colorize_prompt,
            )
        elif key == 'o':  # <-- OFFSET HANDLER (now only reachable if not args.stack)
            print("\n\033[1mOffset adjustment menu:\033[0m")
            print(f"  {colorize_menu('1-{}: adjust individual curve offset'.format(len(labels)))}")
            print(f"  {colorize_menu('a: set spacing between curves')}")
            print(f"  {colorize_menu('r: reset all offsets to 0')}")
            print(f"  {colorize_menu('d: change delta spacing (original behavior)')}")
            print(f"  {colorize_menu('q: back to main menu')}")
            
            while True:
                offset_cmd = _safe_input("Offset> ").strip().lower()
                
                if offset_cmd == 'q' or offset_cmd == '':
                    break
                    
                elif offset_cmd == 'r':
                    # Reset all offsets to 0
                    try:
                        push_state("reset-offsets")
                        for i in range(len(labels)):
                            if i >= _nlines():
                                continue
                            # Get current x-data from the line
                            current_x = np.asarray(_line(i).get_xdata(), dtype=float)
                            # Reset to normalized data without any offset
                            y_norm = orig_y[i]
                            y_data_list[i] = y_norm.copy()
                            offsets_list[i] = 0.0
                            # Update x_data_list to match current line data
                            x_data_list[i] = current_x.copy()
                            _line(i).set_data(current_x, y_norm)
                        
                        ax.relim()
                        ax.autoscale_view(scalex=False, scaley=True)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                        fig.canvas.draw()
                        print("All offsets reset to 0")
                    except Exception as e:
                        print(f"Error resetting offsets: {e}")
                    
                elif offset_cmd == 'a':
                    # Set spacing between curves (separates all curves)
                    try:
                        if len(labels) <= 1:
                            print("Warning: Only one curve loaded; spacing cannot be applied.")
                            continue
                        
                        # Calculate current spacing (average difference between consecutive offsets)
                        current_spacing = 0.0
                        if len(offsets_list) > 1:
                            spacing_diffs = []
                            sorted_indices = sorted(range(len(offsets_list)), key=lambda i: offsets_list[i] if i < len(offsets_list) else 0.0)
                            for j in range(len(sorted_indices) - 1):
                                idx1, idx2 = sorted_indices[j], sorted_indices[j + 1]
                                off1 = offsets_list[idx1] if idx1 < len(offsets_list) else 0.0
                                off2 = offsets_list[idx2] if idx2 < len(offsets_list) else 0.0
                                spacing_diffs.append(abs(off2 - off1))
                            if spacing_diffs:
                                current_spacing = sum(spacing_diffs) / len(spacing_diffs)
                        
                        spacing_input = _safe_input("Enter spacing value between curves (current avg: {:.4g}): ".format(current_spacing)).strip()
                        if not spacing_input:
                            print("Canceled.")
                            continue
                        
                        spacing_value = float(spacing_input)
                        push_state("curve-spacing")
                        
                        # Apply spacing to separate all curves
                        # Find the minimum current offset to use as baseline
                        min_offset = min(offsets_list) if offsets_list else 0.0
                        
                        # Sort curves by their current offset to maintain order
                        curve_order = sorted(range(len(labels)), key=lambda i: offsets_list[i] if i < len(offsets_list) else 0.0)
                        
                        # Apply cumulative spacing starting from the minimum offset
                        current_offset = min_offset
                        for i, curve_idx in enumerate(curve_order):
                            if curve_idx >= _nlines():
                                continue
                            # Get current x-data from the line
                            current_x = np.asarray(_line(curve_idx).get_xdata(), dtype=float)
                            y_norm = orig_y[curve_idx]
                            
                            # Set new offset with spacing
                            offsets_list[curve_idx] = current_offset
                            y_with_offset = y_norm + current_offset
                            y_data_list[curve_idx] = y_with_offset
                            x_data_list[curve_idx] = current_x.copy()
                            _line(curve_idx).set_data(current_x, y_with_offset)
                            
                            # Calculate spacing for next curve based on current curve's range
                            if i < len(curve_order) - 1:  # Not the last curve
                                y_range = (y_norm.max() - y_norm.min()) if y_norm.size else 0.0
                                if args.stack:
                                    # In stack mode, spacing is relative to curve range
                                    gap = y_range + (spacing_value * (y_range if args.autoscale else 1.0))
                                    current_offset -= gap
                                else:
                                    # In normal mode, spacing is absolute or relative
                                    increment = (y_range * spacing_value) if (args.autoscale and y_norm.size) else spacing_value
                                    current_offset += increment
                        
                        ax.relim()
                        ax.autoscale_view(scalex=False, scaley=True)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                        fig.canvas.draw()
                        print("Spacing of {:.4g} applied to separate all curves".format(spacing_value))
                        
                    except ValueError:
                        print("Invalid spacing value")
                    except Exception as e:
                        print(f"Error applying spacing: {e}")
                        
                elif offset_cmd == 'd':
                    # Original delta spacing behavior
                    if len(labels) <= 1:
                        print("Warning: Only one curve loaded; applying an offset is not recommended.")
                    try:
                        new_delta_str = _safe_input(f"Enter new offset spacing (current={delta}): ").strip()
                        if not new_delta_str:
                            print("Canceled.")
                            continue
                        new_delta = float(new_delta_str)
                        push_state("delta-spacing")
                        delta = new_delta
                        offsets_list[:] = []
                        if args.stack:
                            current_offset = 0.0
                            for i, y_norm in enumerate(orig_y):
                                if i >= _nlines():
                                    continue
                                # Get current x-data from the line
                                current_x = np.asarray(_line(i).get_xdata(), dtype=float)
                                y_with_offset = y_norm + current_offset
                                y_data_list[i] = y_with_offset
                                offsets_list.append(current_offset)
                                # Update x_data_list to match current line data
                                x_data_list[i] = current_x.copy()
                                _line(i).set_data(current_x, y_with_offset)
                                y_range = (y_norm.max() - y_norm.min()) if y_norm.size else 0.0
                                gap = y_range + (delta * (y_range if args.autoscale else 1.0))
                                current_offset -= gap
                        else:
                            current_offset = 0.0
                            for i, y_norm in enumerate(orig_y):
                                if i >= _nlines():
                                    continue
                                # Get current x-data from the line
                                current_x = np.asarray(_line(i).get_xdata(), dtype=float)
                                y_with_offset = y_norm + current_offset
                                y_data_list[i] = y_with_offset
                                offsets_list.append(current_offset)
                                # Update x_data_list to match current line data
                                x_data_list[i] = current_x.copy()
                                _line(i).set_data(current_x, y_with_offset)
                                increment = (y_norm.max() - y_norm.min()) * delta if (args.autoscale and y_norm.size) else delta
                                current_offset += increment
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                        ax.relim(); ax.autoscale_view(scalex=False, scaley=True)
                        fig.canvas.draw()
                        print(f"Offsets updated with delta={delta}")
                    except ValueError:
                        print("Invalid delta value")
                    except Exception as e:
                        print(f"Error updating offsets: {e}")
                        
                elif offset_cmd.isdigit():
                    # Adjust individual curve offset
                    try:
                        curve_num = int(offset_cmd)
                        if curve_num < 1 or curve_num > len(labels):
                            print("Invalid curve number (1-{})".format(len(labels)))
                            continue
                        
                        idx = curve_num - 1
                        if idx >= _nlines():
                            print("Invalid curve number.")
                            continue
                        
                        current_offset = offsets_list[idx] if idx < len(offsets_list) else 0.0
                        
                        individual_offset_input = _safe_input("Enter offset for curve {} (current: {:.4g}): ".format(
                            curve_num, current_offset)).strip()
                        if not individual_offset_input:
                            print("Canceled.")
                            continue
                        
                        individual_offset = float(individual_offset_input)
                        push_state("curve-{}-offset".format(curve_num))
                        
                        # Get current x-data from the line to ensure we're working with actual displayed data
                        current_x = np.asarray(_line(idx).get_xdata(), dtype=float)
                        # Apply individual offset to this curve
                        y_norm = orig_y[idx]
                        offsets_list[idx] = individual_offset
                        y_with_offset = y_norm + individual_offset
                        y_data_list[idx] = y_with_offset
                        # Update x_data_list to match current line data
                        x_data_list[idx] = current_x.copy()
                        _line(idx).set_data(current_x, y_with_offset)
                        
                        ax.relim()
                        ax.autoscale_view(scalex=False, scaley=True)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                        fig.canvas.draw()
                        print("Curve {} offset set to: {:.4g}".format(curve_num, individual_offset))
                        
                    except ValueError:
                        print("Invalid offset value")
                    except Exception as e:
                        print(f"Error setting curve offset: {e}")
                else:
                    print("Unknown command. Use 1-{}, a, r, d, or q".format(len(labels)))
        elif key == 'l':
            run_line_style_menu(
                ax=ax,
                fig=fig,
                lines_by_curve=_lines_by_curve,
                line_getter=_line,
                line_count=_nlines,
                push_state=push_state,
                safe_input=_safe_input,
                colorize_menu=colorize_menu,
                colorize_prompt=colorize_prompt,
            )
        elif key == 'f':
            def _apply_xy_font_family(family):
                push_state("font-change")
                apply_font_changes(new_family=family)
                position_top_xlabel()
                position_right_ylabel()
                fig.canvas.draw()
            def _apply_xy_font_size(size):
                push_state("font-change")
                apply_font_changes(new_size=size)
                position_top_xlabel()
                position_right_ylabel()
                fig.canvas.draw()
            run_font_menu(
                safe_input=_safe_input,
                colorize_menu=colorize_menu,
                colorize_prompt=colorize_prompt,
                get_current_family=lambda: plt.rcParams.get('font.sans-serif', [''])[0],
                get_current_size=lambda: plt.rcParams.get('font.size', None),
                apply_family=_apply_xy_font_family,
                apply_size=_apply_xy_font_size,
                fonts=['Arial', 'Helvetica', 'Times New Roman', 'STIXGeneral', 'DejaVu Sans'],
            )
        elif key == 'g':
            try:
                def _resize_xy_frame():
                    push_state("resize-frame")
                    resize_plot_frame()
                    update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                def _resize_xy_canvas():
                    push_state("resize-canvas")
                    resize_canvas()
                run_option_menu(
                    prompt="Resize (p/c/q): ",
                    options={
                        "p": ("plot frame", _resize_xy_frame),
                        "c": ("canvas", _resize_xy_canvas),
                    },
                    safe_input=_safe_input,
                    colorize_menu=colorize_menu,
                    colorize_prompt=colorize_prompt,
                )
            except Exception as e:
                print(f"Error in resize submenu: {e}")
        elif key == 'h':
            # Legend submenu
            try:
                while True:
                    print("\n\033[1mLegend submenu:\033[0m")
                    print("  " + colorize_menu("v: show/hide curve names"))
                    current_pos = "bottom-right" if getattr(fig, '_stack_label_at_bottom', False) else "top-right"
                    print("  " + colorize_menu(f"s: legend position (current: {current_pos})"))
                    print("  " + colorize_menu("q: back to main menu"))
                    sub_key = _safe_input(colorize_prompt("Choose (v/s/q): ")).strip().lower()
                    
                    if sub_key == 'q':
                        break
                    elif sub_key == 'v':
                        push_state("curve-names")
                        # Check current visibility from first label
                        current_visible = True
                        if label_text_objects and len(label_text_objects) > 0:
                            try:
                                current_visible = label_text_objects[0].get_visible()
                            except Exception:
                                current_visible = True
                        
                        # Toggle all labels
                        new_visible = not current_visible
                        for txt in label_text_objects:
                            try:
                                txt.set_visible(new_visible)
                            except Exception:
                                pass
                        
                        # Store state on figure for persistence
                        fig._curve_names_visible = new_visible
                        
                        status = "shown" if new_visible else "hidden"
                        print(f"Curve names {status}")
                        stack_label_bottom = getattr(fig, '_stack_label_at_bottom', False)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, stack_label_bottom)
                        try:
                            fig.canvas.draw()
                        except Exception:
                            fig.canvas.draw_idle()
                    elif sub_key == 's':
                        push_state("label-position")
                        # Toggle label position between top-right and bottom-right
                        current_bottom = getattr(fig, '_stack_label_at_bottom', False)
                        fig._stack_label_at_bottom = not current_bottom
                        new_pos = "bottom-right" if fig._stack_label_at_bottom else "top-right"
                        update_labels(ax, y_data_list, label_text_objects, args.stack, fig._stack_label_at_bottom)
                        print(f"Legend position changed to {new_pos}.")
                        try:
                            fig.canvas.draw()
                        except Exception:
                            fig.canvas.draw_idle()
                    else:
                        print("Unknown option.")
            except Exception as e:
                print(f"Error in legend submenu: {e}")
        elif key == 't':
            try:
                wasd = build_wasd_state(
                    get_spine_visible=get_spine_visible,
                    tick_state=tick_state,
                    title_visible={
                        'top': bool(getattr(ax, '_top_xlabel_on', False)),
                        'bottom': bool(ax.xaxis.label.get_visible()),
                        'left': bool(ax.yaxis.label.get_visible()),
                        'right': bool(getattr(ax, '_right_ylabel_on', False)),
                    },
                    tick_defaults={'top': False, 'bottom': True, 'left': True, 'right': False},
                    label_defaults={'top': False, 'bottom': True, 'left': True, 'right': False},
                )
                def _sync_xy_tick_state():
                    sync_tick_state_from_wasd(
                        tick_state,
                        wasd,
                        tick_defaults={'top': False, 'bottom': True, 'left': True, 'right': False},
                        label_defaults={'top': False, 'bottom': True, 'left': True, 'right': False},
                    )
                    _sync_legacy_tick_keys()
                    try:
                        ax._saved_tick_state = dict(tick_state)
                    except Exception:
                        pass
                def _apply_xy_wasd(changed_sides=None):
                    if changed_sides is None:
                        changed_sides = {'bottom', 'top', 'left', 'right'}
                    for side in ('top', 'bottom', 'left', 'right'):
                        set_spine_visible(side, bool(wasd[side]['spine']))
                    apply_flat_tick_params(ax, tick_state)
                    if bool(wasd['bottom']['title']):
                        if hasattr(ax, '_stored_xlabel') and isinstance(ax._stored_xlabel, str) and ax._stored_xlabel:
                            ax.xaxis.label.set_text(ax._stored_xlabel)
                        ax.xaxis.label.set_visible(True)
                    else:
                        if not hasattr(ax, '_stored_xlabel'):
                            try:
                                ax._stored_xlabel = ax.xaxis.label.get_text()
                            except Exception:
                                ax._stored_xlabel = ''
                        ax.xaxis.label.set_visible(False)
                    ax._top_xlabel_on = bool(wasd['top']['title'])
                    if not ax._top_xlabel_on and hasattr(ax, '_top_xlabel_artist') and ax._top_xlabel_artist is not None:
                        try:
                            ax._top_xlabel_artist.set_visible(False)
                        except Exception:
                            pass
                    if bool(wasd['left']['title']):
                        if hasattr(ax, '_stored_ylabel') and isinstance(ax._stored_ylabel, str) and ax._stored_ylabel:
                            ax.yaxis.label.set_text(ax._stored_ylabel)
                        ax.yaxis.label.set_visible(True)
                    else:
                        if not hasattr(ax, '_stored_ylabel'):
                            try:
                                ax._stored_ylabel = ax.yaxis.label.get_text()
                            except Exception:
                                ax._stored_ylabel = ''
                        ax.yaxis.label.set_visible(False)
                    ax._right_ylabel_on = bool(wasd['right']['title'])
                    if not ax._right_ylabel_on and hasattr(ax, '_right_ylabel_artist') and ax._right_ylabel_artist is not None:
                        try:
                            ax._right_ylabel_artist.set_visible(False)
                        except Exception:
                            pass
                    update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                    sync_fonts()
                    apply_changed_side_title_positions(
                        changed_sides,
                        bottom=position_bottom_xlabel,
                        top=position_top_xlabel,
                        left=position_left_ylabel,
                        right=position_right_ylabel,
                    )
                def _draw_xy_spine_menu():
                    try:
                        fig.canvas.draw()
                    except Exception:
                        fig.canvas.draw_idle()
                run_spine_tick_menu(
                    fig=fig,
                    wasd=wasd,
                    safe_input=_safe_input,
                    colorize_prompt=colorize_prompt,
                    colorize_inline_commands=colorize_inline_commands,
                    push_state=push_state,
                    sync_tick_state=_sync_xy_tick_state,
                    apply_wasd=_apply_xy_wasd,
                    draw=_draw_xy_spine_menu,
                    mode_label="stack plot axes",
                    back_label="stack plot menu",
                    axis_map={'x': ax.xaxis, 'y': ax.yaxis},
                    direction_axes=[ax],
                    length_axes=[ax],
                    title_offset_handler=_title_offset_menu,
                    on_quit=lambda: setattr(ax, '_saved_tick_state', dict(tick_state)),
                    print_state=print_tick_state,
                )
                continue
            except Exception as e:
                print(f"Error in tick visibility menu: {e}")
        elif key == 'p':
            handle_style_export(_xy_action_context())
        elif key == 'i':
            handle_style_import(_xy_action_context())
        elif key == 'e':
            handle_figure_export(_xy_action_context())
        elif key == 'sm':
            run_smoothing_menu(
                fig=fig,
                x_data_list=x_data_list,
                y_data_list=y_data_list,
                offsets_list=offsets_list,
                ensure_original_data=_ensure_original_data,
                reset_to_original=_reset_to_original,
                apply_data_changes=_apply_data_changes,
                update_full_processed_data=_update_full_processed_data,
                get_last_reduce_rows_settings=_get_last_reduce_rows_settings,
                save_last_reduce_rows_settings=_save_last_reduce_rows_settings,
                get_last_smooth_settings_from_config=_get_last_smooth_settings_from_config,
                save_last_smooth_settings_to_config=_save_last_smooth_settings_to_config,
                push_state=push_state,
                safe_input=_safe_input,
                colorize_menu=colorize_menu,
                colorize_prompt=colorize_prompt,
            )
        elif key == 'v':
            run_peak_finder_menu(
                ax=ax,
                x_data_list=x_data_list,
                y_data_list=y_data_list,
                offsets_list=offsets_list,
                labels=labels,
                source_file_paths=source_file_paths,
                safe_input=_safe_input,
                colorize_menu=colorize_menu,
                colorize_prompt=_colorize_prompt,
            )

__all__ = ["interactive_menu"]

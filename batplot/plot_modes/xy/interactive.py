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
    finalize_spine_colors,
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
    colorize_menu as _shared_colorize_menu,
    prompt_menu_key,
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
    current_tick_width,
    default_flat_tick_state,
    legacy_tick_state_to_flat,
    run_spine_tick_menu,
    set_primary_axis_title,
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
from ..common.line_dash import capture_dash_pattern, clear_dash_pattern, restore_dash_pattern
from .menu import print_xy_menu
from .peaks import run_peak_finder_menu
from .smoothing import run_smoothing_menu
from .axis_units import resolve_wavelength, run_axis_units_menu
from .offset_menu import run_offset_menu
from .undo_state import xy_push_state, xy_restore_state


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
                     use_Q, use_r, use_E, use_k, use_rft, use_2th=False,
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
        use_Q, use_r, use_E, use_k, use_rft, use_2th: Boolean flags for axis mode
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

    # Always provide a CIF state object so ``cif`` → ``a`` works without CLI CIF.
    if not cif_globals:
        cif_globals = {}
    if cif_globals.get('cif_tick_series') is None:
        cif_globals['cif_tick_series'] = []
    if cif_globals.get('cif_hkl_map') is None:
        cif_globals['cif_hkl_map'] = {}
    if cif_globals.get('cif_hkl_label_map') is None:
        cif_globals['cif_hkl_label_map'] = {}
    cif_globals.setdefault('show_cif_hkl', False)
    cif_globals.setdefault('show_cif_titles', True)
    cif_globals.setdefault('cif_extend_suspended', False)
    cif_globals.setdefault('keep_canvas_fixed', False)

    # Provide a consistent interface for accessing CIF state
    _bp = type('CIFState', (), cif_globals)()

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

    # ANSI color codes for menu highlighting (+ dashed description frame)
    def colorize_menu(text):
        return _shared_colorize_menu(text)
    
    colorize_prompt = _colorize_prompt

    colorize_inline_commands = _colorize_inline_commands
    
    # REPLACED print_main_menu with column layout (now hides 'd' and 'y' in --stack)
    # Diffraction = known XRD mode only (never treat blank/unknown as 2θ).
    try:
        from .axis_units import AXIS_MODES, get_xy_axis_mode, set_xy_axis_mode

        _mode0 = get_xy_axis_mode(
            fig,
            use_Q=use_Q,
            use_r=use_r,
            use_E=use_E,
            use_k=use_k,
            use_rft=use_rft,
            use_2th=bool(use_2th),
            xaxis=getattr(args, "xaxis", None),
            ax=ax,
        )
        if _mode0 in AXIS_MODES:
            # Never clobber a file:wl / pipeline λ with a conflicting --wl
            _wl_set = None
            if getattr(fig, "_xy_wavelength", None) is None:
                _wl_set = getattr(args, "wl", None)
            set_xy_axis_mode(fig, _mode0, wavelength=_wl_set)
            is_diffraction = True
        else:
            is_diffraction = False
    except Exception:
        is_diffraction = use_Q or (
            (not use_r) and (not use_E) and (not use_k) and (not use_rft)
            and str(getattr(args, "xaxis", "") or "").lower() in (
                "2theta", "2th", "tth", "two_theta", "q", "d",
            )
        )
        if use_Q:
            is_diffraction = True

    def print_main_menu():
        print_xy_menu(
            fig=fig,
            stack=args.stack,
            is_diffraction=is_diffraction,
            colorize_menu=colorize_menu,
        )

    # --- Helper for spine visibility (sync twin for --ry / --txaxis) ---
    def set_spine_visible(which, visible):
        from .spines import set_xy_spine_visible

        set_xy_spine_visible(fig, ax, which, visible)
        try:
            fig.canvas.draw_idle()
        except Exception:
            pass

    def get_spine_visible(which):
        from .spines import xy_twin_context

        ax2, use_top = xy_twin_context(fig)
        if ax2 is not None and which == "right" and which in ax2.spines:
            return ax2.spines[which].get_visible()
        if ax2 is not None and use_top and which in ("top", "bottom") and which in ax2.spines:
            return ax2.spines[which].get_visible()
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
    def resize_plot_frame(*, on_before_change=None):
        return _ui_resize_plot_frame(
            fig, ax, y_data_list, label_text_objects, args, update_labels,
            on_before_change=on_before_change,
        )

    def resize_canvas(*, on_before_change=None):
        return _ui_resize_canvas(fig, ax, on_before_change=on_before_change)
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
        hkl_map = getattr(_bp, 'cif_hkl_label_map', None) if _bp is not None else None
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
            cif_hkl_label_map=hkl_map,
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
        # Keep dual-wl / λ pairs live for Options ``u`` and crosshair after ``i``
        try:
            _fwi = list(getattr(fig, "_xy_file_wavelength_info", None) or [])
            if isinstance(file_wavelength_info, list):
                file_wavelength_info[:] = _fwi
            if isinstance(cif_globals, dict):
                cif_globals["file_wavelength_info"] = list(file_wavelength_info)
        except Exception:
            pass
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
    # Get wavelength info from cif_globals if available (prefer fig after session/style)
    file_wavelength_info = []
    if cif_globals:
        file_wavelength_info = list(cif_globals.get('file_wavelength_info', []) or [])
    if not file_wavelength_info:
        file_wavelength_info = list(getattr(fig, '_xy_file_wavelength_info', None) or [])
    if cif_globals is not None and isinstance(cif_globals, dict):
        cif_globals['file_wavelength_info'] = file_wavelength_info
    try:
        fig._xy_file_wavelength_info = list(file_wavelength_info)
    except Exception:
        pass
    
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
            from .axis_units import (
                format_xrd_crosshair_x_lines,
                get_xy_axis_mode,
                resolve_wavelength,
            )
            axis_mode_ch = get_xy_axis_mode(
                fig, use_Q=use_Q, use_r=use_r, use_E=use_E, use_k=use_k, use_rft=use_rft,
                use_2th=bool(use_2th), xaxis=getattr(args, "xaxis", None), ax=ax,
            )
            # Bind λ for full 2θ/Q/d readout. Dual-remapped 2θ uses both λs in
            # on_move; otherwise resolve from --wl / file:wl / session attrs.
            if is_diffraction and axis_mode_ch in ("2theta", "Q", "d"):
                _dual_disp = bool(getattr(fig, "_xy_dual_wl_display", False))
                if not (_dual_disp and axis_mode_ch == "2theta"):
                    known = resolve_wavelength(
                        fig=fig, args=args,
                        cif_series=_cif_series_for_session(),
                        file_wavelength_info=file_wavelength_info,
                        axis_mode=axis_mode_ch,
                    )
                    if known is not None:
                        crosshair['wavelength'] = float(known)
                    elif axis_mode_ch == "2theta":
                        # Prompt only for native 2θ (Q/d can still show Q↔d without λ).
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
                    else:
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
                # Twin (--ry / --txaxis) sits on top for hit-testing; accept both.
                ax2_xh = getattr(fig, "_xy_ax2", None)
                allowed = (ax,) if ax2_xh is None else (ax, ax2_xh)
                if event.inaxes not in allowed or event.x is None or event.y is None:
                    return
                try:
                    pt = ax.transData.inverted().transform((event.x, event.y))
                    x = float(pt[0])
                    y = float(pt[1])
                except Exception:
                    if event.xdata is None or event.ydata is None:
                        return
                    x = float(event.xdata)
                    y = float(event.ydata)
                y_right = None
                if ax2_xh is not None:
                    try:
                        pt2 = ax2_xh.transData.inverted().transform((event.x, event.y))
                        y_right = float(pt2[1])
                    except Exception:
                        y_right = None
                vline.set_xdata([x, x])
                hline.set_ydata([y, y])

                # For diffraction data, show 2θ / Q / d when λ is known
                if is_diffraction:
                    mode = get_xy_axis_mode(
                        fig, use_Q=use_Q, use_r=use_r, use_E=use_E, use_k=use_k, use_rft=use_rft,
                        use_2th=bool(use_2th), xaxis=getattr(args, "xaxis", None), ax=ax,
                    )
                    if mode == "Q" or (mode not in ("2theta", "d") and use_Q):
                        x_lines = format_xrd_crosshair_x_lines(
                            x, axis_mode="Q", wavelength=crosshair.get("wavelength"),
                        )
                        txt.set_text("\n".join(x_lines + [f"y={y:.6g}"]))
                    elif mode == "d":
                        x_lines = format_xrd_crosshair_x_lines(
                            x, axis_mode="d", wavelength=crosshair.get("wavelength"),
                        )
                        txt.set_text("\n".join(x_lines + [f"y={y:.6g}"]))
                    elif use_r:
                        txt.set_text(f"r={x:.6g} Å\ny={y:.6g}")
                    else:
                        # 2θ mode — dual UI only when data were dual-remapped to λ₂ 2θ
                        wl_info = file_wavelength_info[0] if file_wavelength_info else None
                        if (
                            bool(getattr(fig, "_xy_dual_wl_display", False))
                            and wl_info
                            and wl_info.get('original_wl') is not None
                            and wl_info.get('conversion_wl') is not None
                        ):
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
                        else:
                            x_lines = format_xrd_crosshair_x_lines(
                                x,
                                axis_mode="2theta",
                                wavelength=crosshair.get("wavelength"),
                            )
                            txt.set_text("\n".join(x_lines + [f"y={y:.6g}"]))
                else:
                    # For non-diffraction data, just show x and y values
                    if y_right is not None:
                        txt.set_text(f"x={x:.6g}\ny={y:.6g}\ny₂={y_right:.6g}")
                    else:
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
        """Ensure original data is stored for all curves.

        Prefer untrimmed ``x_full_list`` / ``raw_y_full_list`` (and fig master
        backups) when they cover more than the current display window so later
        X expansion / smooth-reset does not freeze a cropped viewport as the
        "original".

        ``_original_y_data_list`` is always stored **without** stack offsets
        (``_reset_to_original`` re-adds them).
        """
        from .full_data import sync_live_full_lists, upgrade_originals_from_full

        # Keep live full lists / master at the longest known domain first.
        sync_live_full_lists(
            fig,
            x_full_list,
            raw_y_full_list,
            x_data_list=x_data_list,
            y_fallback_list=[
                (np.asarray(y_data_list[i], dtype=float).flatten()
                 - (float(offsets_list[i]) if i < len(offsets_list) else 0.0))
                for i in range(len(y_data_list))
            ],
        )
        if hasattr(fig, "_original_x_data_list"):
            upgrade_originals_from_full(fig, x_full_list, raw_y_full_list)
            return
        n = len(x_data_list)
        ox: list = []
        oy: list = []
        for i in range(n):
            xf = np.asarray(x_full_list[i], dtype=float).flatten() if i < len(x_full_list) else np.array([])
            yf = np.asarray(raw_y_full_list[i], dtype=float).flatten() if i < len(raw_y_full_list) else np.array([])
            xd = np.asarray(x_data_list[i], dtype=float).flatten()
            yd = np.asarray(y_data_list[i], dtype=float).flatten()
            off = float(offsets_list[i]) if i < len(offsets_list) else 0.0
            if xf.size > xd.size and xf.size == yf.size:
                ox.append(np.array(xf, copy=True))
                oy.append(np.array(yf, copy=True))
            else:
                ox.append(np.array(xd, copy=True))
                oy.append(np.array(yd - off, copy=True))
        fig._original_x_data_list = ox
        fig._original_y_data_list = oy
        upgrade_originals_from_full(fig, x_full_list, raw_y_full_list)

    def _update_full_processed_data():
        """Store processed curve buffers for X-range filtering.

        When originals are wider than the current display crop and the plot is
        not stack/norm-normalized (raw originals would have a different scale),
        re-run the last smooth settings across the full original X so expansion
        can keep processing. Otherwise store the current (possibly cropped)
        display arrays.
        """
        n = len(x_data_list)
        fx: list = []
        fy: list = []
        settings = getattr(fig, '_smooth_settings', None) or {}
        method = settings.get('method')
        use_full_originals = (
            hasattr(fig, '_original_x_data_list')
            and not (getattr(args, 'stack', False) or getattr(args, 'norm', False))
            and method in ('adjacent_average', 'savgol', 'fft')
        )
        for i in range(n):
            xd = np.asarray(x_data_list[i], dtype=float).flatten()
            yd = np.asarray(y_data_list[i], dtype=float).flatten()
            off = float(offsets_list[i]) if i < len(offsets_list) else 0.0
            if use_full_originals and i < len(fig._original_x_data_list):
                ox = np.asarray(fig._original_x_data_list[i], dtype=float).flatten()
                oy = np.asarray(fig._original_y_data_list[i], dtype=float).flatten()
                if ox.size > xd.size and ox.size == oy.size:
                    try:
                        if method == 'adjacent_average':
                            from .data_ops import _adjacent_average_smooth
                            sy = _adjacent_average_smooth(oy, int(settings.get('points', 5)))
                        elif method == 'savgol':
                            from ..common.smoothing import savgol_smooth as _savgol_smooth
                            sy = _savgol_smooth(oy, int(settings.get('window', 5)), int(settings.get('poly', 2)))
                        else:
                            from .data_ops import _fft_smooth
                            sy = _fft_smooth(
                                oy,
                                cutoff=float(settings.get('cutoff', 0.1)),
                            )
                        fx.append(np.array(ox, copy=True))
                        fy.append(np.asarray(sy, dtype=float).flatten() + off)
                        continue
                    except Exception:
                        pass
            fx.append(np.array(xd, copy=True))
            fy.append(np.array(yd, copy=True))
        fig._full_processed_x_data_list = fx
        fig._full_processed_y_data_list = fy

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
        # Clear processing settings and stale full-processed buffers so X-expand /
        # session save (s) / style capture (p) do not keep smoothed crops.
        for attr in (
            '_smooth_settings',
            '_full_processed_x_data_list',
            '_full_processed_y_data_list',
        ):
            if hasattr(fig, attr):
                try:
                    delattr(fig, attr)
                except Exception:
                    pass
        return (reset_count > 0, reset_count, total_points)

    def _apply_data_changes():
        """Update plot and data lists after data modification."""
        for i in range(min(_nlines(), len(x_data_list), len(y_data_list))):
            try:
                _line(i).set_data(x_data_list[i], y_data_list[i])
            except Exception:
                pass
        try:
            from .axis_range import relim_xy_twins

            relim_xy_twins(fig, ax, scalex=False, scaley=True)
        except Exception:
            pass
        try:
            fig.canvas.draw_idle()
        except Exception:
            pass

    def _update_ylabel_for_derivative(order: int, current_label: Optional[str] = None, is_reversed: bool = False) -> str:
        """Delegate to shared helper; keeps interactive callers unchanged."""
        from .derivative import update_ylabel_for_derivative
        return update_ylabel_for_derivative(
            order,
            current_label,
            is_reversed=is_reversed,
            x_label=x_label,
            fallback_ylabel=(ax.get_ylabel() or "Y"),
        )

    def _ensure_pre_derivative_data():
        """Ensure pre-derivative data is stored for reset."""
        if not hasattr(fig, '_pre_derivative_x_data_list'):
            fig._pre_derivative_x_data_list = [np.array(a, copy=True) for a in x_data_list]
            fig._pre_derivative_y_data_list = [np.array(a, copy=True) for a in y_data_list]
            from ..common.axis_state import primary_axis_label_text
            fig._pre_derivative_ylabel = primary_axis_label_text(ax, "y")

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
                # Pre-derivative snapshots are taken from y_data_list (already
                # includes stack offsets) — do not add offsets again.
                pre_y = np.asarray(pre_y, dtype=float).copy()
                _line(i).set_data(pre_x, pre_y)
                x_data_list[i] = np.asarray(pre_x, dtype=float).copy()
                y_data_list[i] = pre_y
                reset_count += 1
                total_points += len(pre_x)
            except Exception:
                pass
        # Restore y-axis label
        if hasattr(fig, '_pre_derivative_ylabel'):
            ax.set_ylabel(fig._pre_derivative_ylabel)
            ax._stored_ylabel = fig._pre_derivative_ylabel
        # Clear derivative settings and stale processed buffers so X-expand
        # (and p/i/s/b round-trips) do not reuse derivative-smoothed arrays.
        for attr in (
            '_derivative_order',
            '_derivative_reversed',
            '_full_processed_x_data_list',
            '_full_processed_y_data_list',
            '_smooth_settings',
        ):
            if hasattr(fig, attr):
                try:
                    delattr(fig, attr)
                except Exception:
                    pass
        return (reset_count > 0, reset_count, total_points)

    def push_state(note=""):
        """Snapshot current editable state (before a modifying action)."""
        return xy_push_state(
            state_history=state_history, fig=fig, ax=ax, tick_state=tick_state,
            labels=labels, delta=delta,
            x_data_list=x_data_list, y_data_list=y_data_list, orig_y=orig_y,
            offsets_list=offsets_list, x_full_list=x_full_list,
            raw_y_full_list=raw_y_full_list, label_text_objects=label_text_objects,
            bp=_bp, cif_series_for_session=_cif_series_for_session,
            iter_lines=_iter_lines, note=note,
        )

    def restore_state():
        nonlocal delta, use_Q, use_2th
        delta, use_Q, use_2th = xy_restore_state(
            state_history=state_history, fig=fig, ax=ax, args=args,
            tick_state=tick_state, labels=labels,
            x_data_list=x_data_list, y_data_list=y_data_list, orig_y=orig_y,
            offsets_list=offsets_list, x_full_list=x_full_list,
            raw_y_full_list=raw_y_full_list, label_text_objects=label_text_objects,
            bp=_bp, delta=delta, use_Q=use_Q, use_2th=use_2th,
            file_wavelength_info=file_wavelength_info, cif_globals=cif_globals,
            sync_legacy_tick_keys=_sync_legacy_tick_keys,
            update_tick_visibility=update_tick_visibility,
            sync_fonts=sync_fonts,
            position_top_xlabel=position_top_xlabel,
            position_right_ylabel=position_right_ylabel,
            update_ylabel_for_derivative=_update_ylabel_for_derivative,
            sync_fig_cif_tick_series=_sync_fig_cif_tick_series,
            line=_line, nlines=_nlines,
        )

    def pop_undo():
        """Drop the most recently pushed undo snapshot.

        Used by style/session/export handlers when an operation fails after
        ``push_state`` succeeds; keeps the undo stack consistent.
        """
        nonlocal state_history
        if state_history:
            state_history.pop()


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
            pop_undo=pop_undo,
        )

    pending_key = None
    while True:
        try:
            print_main_menu()
            if pending_key is not None:
                key = pending_key
                pending_key = None
            else:
                key = prompt_menu_key()
        except (KeyboardInterrupt, EOFError):
            print("\n\nExiting interactive menu...")
            break
        
        if not key:
            continue

        # Disable keys hidden from the stack-mode menu
        if args.stack and key in ('y', 'd', 'o'):
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
        elif key in ('cif', 'z'):
            # Note: top-level `j` is CIF title toggle (handled below), not CIF menu.
            try:
                from .axis_units import get_xy_axis_mode
                _axis_is_2th = get_xy_axis_mode(
                    fig, use_Q=use_Q, use_r=use_r, use_E=use_E, use_k=use_k, use_rft=use_rft,
                    use_2th=bool(use_2th), xaxis=getattr(args, "xaxis", None), ax=ax,
                ) == "2theta"
            except Exception:
                _mode_fb = getattr(fig, "_xy_axis_mode", None)
                if _mode_fb in ("2theta", "Q", "d"):
                    _axis_is_2th = _mode_fb == "2theta"
                else:
                    # Prefer stored hint; never treat unknown as 2θ
                    _hint = getattr(args, "xaxis", None) or getattr(fig, "_xy_xaxis_hint", None)
                    if _hint is not None and str(_hint).lower() in ("2theta", "2th", "tth", "two_theta"):
                        _axis_is_2th = True
                    else:
                        _axis_is_2th = False
            run_cif_ticks_menu(
                ax=ax, fig=fig, _bp=_bp,
                colorize_menu=colorize_menu, colorize_prompt=colorize_prompt,
                _safe_input=_safe_input, push_state=push_state,
                _print_cif_phase_list=_print_cif_phase_list,
                _apply_cif_phase_label_rename=_apply_cif_phase_label_rename,
                _sync_fig_cif_tick_series=_sync_fig_cif_tick_series,
                use_2th=_axis_is_2th,
                default_wl=getattr(args, 'wl', None) or getattr(fig, '_xy_wavelength', None),
                y_data_list=y_data_list,
                # On failed CIF add, restore the pre-add snap (not discard-only).
                pop_undo=restore_state,
            )
        elif key == 'u':
            if not is_diffraction:
                print("Unknown option.")
                continue
            try:
                def _set_use_Q(flag: bool):
                    nonlocal use_Q, use_2th
                    use_Q = bool(flag)
                    if flag:
                        use_2th = False

                def _set_use_2th(flag: bool):
                    nonlocal use_Q, use_2th
                    use_2th = bool(flag)
                    if flag:
                        use_Q = False

                new_mode = run_axis_units_menu(
                    fig=fig,
                    ax=ax,
                    args=args,
                    x_data_list=x_data_list,
                    x_full_list=x_full_list,
                    y_data_list=y_data_list,
                    use_Q=use_Q,
                    use_r=use_r,
                    use_E=use_E,
                    use_k=use_k,
                    use_rft=use_rft,
                    use_2th=bool(use_2th),
                    get_cif_series=_cif_series_for_session,
                    sync_fig_cif_tick_series=_sync_fig_cif_tick_series,
                    file_wavelength_info=file_wavelength_info,
                    push_state=push_state,
                    # On failed convert: full restore (not discard-only pop)
                    pop_undo=restore_state,
                    set_use_Q=_set_use_Q,
                    set_use_2th=_set_use_2th,
                    _safe_input=_safe_input,
                    colorize_menu=colorize_menu,
                    colorize_prompt=colorize_prompt,
                )
                if new_mode:
                    use_Q = new_mode == "Q"
                    use_2th = new_mode == "2theta"
                    is_diffraction = new_mode in ("2theta", "Q", "d")
                # Keep active crosshair λ in sync after convert to/from 2θ
                if new_mode and crosshair.get("active"):
                    try:
                        wl_ch = resolve_wavelength(
                            fig=fig,
                            args=args,
                            cif_series=_cif_series_for_session(),
                            file_wavelength_info=file_wavelength_info,
                            axis_mode=new_mode,
                        )
                        if wl_ch is not None:
                            crosshair["wavelength"] = float(wl_ch)
                    except Exception:
                        pass
            except Exception as e:
                print(f"Error in axis units menu: {e}")
            continue
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
                # Windows-safe CIF detect (drive letter colon is not a suffix).
                from ..common.sources import cif_present

                has_cif = cif_present(
                    getattr(args, "files", None),
                    (lambda: getattr(_bp, "cif_tick_series", None)) if _bp is not None else None,
                )
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
                tick_state=tick_state,
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
                pop_undo=pop_undo,
            )
        elif key == 'o':  # offset (blocked above when args.stack)
            delta = run_offset_menu(
                ax=ax, fig=fig, args=args, labels=labels, orig_y=orig_y,
                x_data_list=x_data_list, y_data_list=y_data_list,
                offsets_list=offsets_list, delta=delta,
                line=_line, nlines=_nlines,
                push_state=push_state, safe_input=_safe_input,
                colorize_menu=colorize_menu,
                label_text_objects=label_text_objects,
            )
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
            from ..common.font_extras import (
                apply_fig_font_weight,
                apply_fig_text_highlight,
                get_fig_font_weight,
                get_fig_text_highlight,
                get_fig_text_highlight_style,
            )
            from ..common.fonts import collect_fig_font_artists

            def _xy_font_artists():
                ax2 = getattr(fig, "_xy_ax2", None)
                return collect_fig_font_artists(
                    ax,
                    fig,
                    include_title=True,
                    include_axes_texts=True,
                    extra_axes=[ax2] if ax2 is not None else None,
                    extra_artists=list(label_text_objects or []),
                )

            def _draw_xy_font_change():
                position_top_xlabel()
                position_right_ylabel()
                try:
                    fig.canvas.draw()
                except Exception:
                    fig.canvas.draw_idle()

            def _apply_xy_font_family(family):
                push_state("font-change")
                apply_font_changes(new_family=family)
                _draw_xy_font_change()

            def _apply_xy_font_size(size):
                push_state("font-change")
                apply_font_changes(new_size=size)
                _draw_xy_font_change()

            def _apply_xy_font_weight(weight):
                push_state("font-weight")
                apply_fig_font_weight(fig, _xy_font_artists(), weight)
                _draw_xy_font_change()

            def _toggle_xy_highlight():
                push_state("font-highlight")
                apply_fig_text_highlight(
                    fig, _xy_font_artists(), not get_fig_text_highlight(fig)
                )
                _draw_xy_font_change()

            def _set_xy_hl_fc(fc):
                push_state("font-highlight")
                apply_fig_text_highlight(
                    fig, _xy_font_artists(), get_fig_text_highlight(fig), fc=fc
                )
                _draw_xy_font_change()

            def _set_xy_hl_alpha(alpha):
                push_state("font-highlight")
                apply_fig_text_highlight(
                    fig, _xy_font_artists(), get_fig_text_highlight(fig), alpha=alpha
                )
                _draw_xy_font_change()

            def _set_xy_hl_pad(pad):
                push_state("font-highlight")
                apply_fig_text_highlight(
                    fig, _xy_font_artists(), get_fig_text_highlight(fig), pad=pad
                )
                _draw_xy_font_change()

            run_font_menu(
                safe_input=_safe_input,
                colorize_menu=colorize_menu,
                colorize_prompt=colorize_prompt,
                get_current_family=lambda: plt.rcParams.get('font.sans-serif', [''])[0],
                get_current_size=lambda: plt.rcParams.get('font.size', None),
                apply_family=_apply_xy_font_family,
                apply_size=_apply_xy_font_size,
                get_current_weight=lambda: get_fig_font_weight(fig),
                apply_weight=_apply_xy_font_weight,
                get_current_highlight=lambda: get_fig_text_highlight(fig),
                get_highlight_style=lambda: get_fig_text_highlight_style(fig),
                apply_highlight_toggle=_toggle_xy_highlight,
                apply_highlight_facecolor=_set_xy_hl_fc,
                apply_highlight_alpha=_set_xy_hl_alpha,
                apply_highlight_pad=_set_xy_hl_pad,
                highlight_fig=fig,
                fonts=['Arial', 'Helvetica', 'Times New Roman', 'STIXGeneral', 'DejaVu Sans'],
            )
        elif key == 'g':
            try:
                def _resize_xy_frame():
                    resize_plot_frame(on_before_change=lambda: push_state("resize-frame"))
                    update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                def _resize_xy_canvas():
                    resize_canvas(on_before_change=lambda: push_state("resize-canvas"))
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
        # Note: duplicate unreachable legend ``h`` branch removed (2026-07-14).
        # Legend submenu is handled by the first ``key == 'h'`` branch above.
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
                    from .spines import sync_xy_twin_wasd, xy_twin_context

                    if changed_sides is None:
                        changed_sides = {'bottom', 'top', 'left', 'right'}
                    for side in ('top', 'bottom', 'left', 'right'):
                        set_spine_visible(side, bool(wasd[side]['spine']))
                    apply_flat_tick_params(ax, tick_state)
                    sync_xy_twin_wasd(ax, fig, wasd)
                    set_primary_axis_title(
                        ax, "x",
                        on=bool(wasd['bottom']['title']),
                        stored_attr="_stored_xlabel",
                    )
                    ax._top_xlabel_on = bool(wasd['top']['title'])
                    if not ax._top_xlabel_on and hasattr(ax, '_top_xlabel_artist') and ax._top_xlabel_artist is not None:
                        try:
                            ax._top_xlabel_artist.set_visible(False)
                        except Exception:
                            pass
                    set_primary_axis_title(
                        ax, "y",
                        on=bool(wasd['left']['title']),
                        stored_attr="_stored_ylabel",
                    )
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
                        finalize_spine_colors(fig, ax, tick_state=tick_state, draw=False)
                    except Exception:
                        pass
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
                    direction_axes=(
                        lambda _ax2: [ax, _ax2] if _ax2 is not None else [ax]
                    )(getattr(fig, "_xy_ax2", None)),
                    length_axes=(
                        lambda _ax2: [ax, _ax2] if _ax2 is not None else [ax]
                    )(getattr(fig, "_xy_ax2", None)),
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
                pop_undo=pop_undo,
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
        else:
            print("Unknown option.")

__all__ = ["interactive_menu"]

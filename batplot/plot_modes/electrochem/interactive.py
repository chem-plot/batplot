"""Interactive menu for electrochemistry (.mpt GC) plots.

Provides a minimal interactive loop when running:
  batplot file.mpt --gc --mass <mg> --interactive

"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple, cast
import os

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
from ...ui import (
    resize_plot_frame, resize_canvas,
    update_tick_visibility as _ui_update_tick_visibility,
    position_top_xlabel as _ui_position_top_xlabel,
    position_right_ylabel as _ui_position_right_ylabel,
    position_bottom_xlabel as _ui_position_bottom_xlabel,
    position_left_ylabel as _ui_position_left_ylabel,
    set_spine_side_color as _ui_set_spine_side_color,
    capture_axes_tick_locators,
    restore_axes_tick_locators,
    finalize_spine_colors,
)
from ..common.menu_rendering import prompt_menu_key
from .menu import _colorize_menu, print_electrochem_menu as _print_menu
from matplotlib.ticker import (  # type: ignore[import-untyped]
    MaxNLocator,
    AutoMinorLocator,
    NullFormatter,
    NullLocator,
    MultipleLocator,
    AutoLocator,
)
from ...plotting import update_labels as _update_labels
from ...ec_common import _default_ec_figsize
import matplotlib as mpl  # type: ignore[import-untyped]
from ...color_utils import (
    color_block,
)
from ..common.crosshair_export import register_crosshair
from ..common.terminal import (
    colorize_inline_commands as _colorize_inline_commands,
    colorize_prompt as _colorize_prompt,
    safe_input as _safe_input,
)
from ..common.spines import (
    apply_changed_side_title_positions,
    apply_frame_and_tick_widths,
    apply_wasd_spines,
    apply_wasd_tick_params,
    build_wasd_state,
    current_tick_width,
    parse_frame_tick_widths,
    run_spine_tick_menu,
    sync_tick_state_from_wasd,
)
from ..common.fonts import (
    apply_font_family_to_artists,
    apply_font_size_to_artists,
    axis_text_artists,
    collect_fig_font_artists,
    legend_text_artists,
    secondary_xaxis_text_artists,
    set_font_family_defaults,
    set_font_size_default,
)
from ..common.font_extras import (
    apply_fig_font_weight,
    apply_fig_text_highlight,
    apply_font_extras_from_cfg,
    font_extras_export_dict,
    get_fig_font_weight,
    get_fig_text_highlight,
    get_fig_text_highlight_style,
    refresh_font_extras_on_artists,
)
from ..common.menus import run_axis_limit_menu, run_font_menu, run_legend_position_menu, run_option_menu
from ..common.files import format_file_timestamp as _format_file_timestamp
from ..common.smoothing import savgol_smooth as _savgol_smooth
from ..common.sources import normalize_source_paths
from .dqdv_2d import (
    _dqdv_build_butterfly_contour_stack,
    _dqdv_butterfly_xz_from_line,
    _dqdv_2d_ensure_center_lines,
    _dqdv_2d_ensure_voltage_formatter,
    _dqdv_2d_restore_custom_labels,
    _dqdv_2d_row_tick_indices,
    _dqdv_2d_set_row_y_ticks,
    _dqdv_2d_style_axes,
    _dqdv_2d_voltage_tick_formatter,
    _dqdv_interp_unique_sorted_x,
    bind_dqdv_2d_contour_figure,
    build_dqdv_2d_snapshot,
    reapply_dqdv_2d_contour_axes,
    restore_dqdv_2d_companion_figure,
    update_dqdv_2d_potential_window,
)
from .export import _ec_savefig_plot_window
from .actions import (
    ElectrochemActionContext,
    handle_export_figure_command,
    handle_import_style_command,
    handle_quick_overwrite_figure_command,
    handle_quick_overwrite_session_command,
    handle_quick_overwrite_style_command,
    handle_save_session_command,
    handle_style_command,
    handle_undo_command,
)
from .colors import (
    _apply_colors,
    _apply_curve_linewidth,
    _expand_cycle_number_tokens,
    _format_cycles_compact,
    _iter_cycle_lines,
    _parse_cycle_tokens,
    _parse_fall_cycles_tokens,
    _parse_file_palette_tokens,
    _parse_per_file_cycle_tokens,
    _resolve_palette_alias,
    _set_visible_cycles,
    run_ec_cycles_menu,
)
from .labels import run_ec_rename_menu
from .legend import (
    _apply_file_display_names_to_legend,
    _apply_legend_position,
    _get_legend_title,
    _get_legend_user_pref,
    _legend_handles_labels_ncol,
    _legend_no_frame,
    _rebuild_legend,
    _sanitize_legend_offset,
    _set_legend_user_pref,
    _store_legend_title,
    _visible_legend_entries,
)
from .legend_order import run_ec_legend_order_menu
from .line_style import run_ec_line_style_menu
from .spine_colors import run_ec_spine_color_menu
from .style import (
    _apply_cycle_styles,
    _export_style_dialog,
    _get_geometry_snapshot,
    _get_style_snapshot,
    _print_style_snapshot,
    apply_dual_top_axis_style,
    capture_cycle_styles_snapshot,
    capture_dual_top_axis,
    capture_ec_curve_marker_defaults,
)

def _apply_stored_axis_colors(ax):
    try:
        color = getattr(ax, '_stored_xlabel_color', None)
        if color:
            ax.xaxis.label.set_color(color)
    except Exception:
        pass
    try:
        color = getattr(ax, '_stored_ylabel_color', None)
        if color:
            ax.yaxis.label.set_color(color)
    except Exception:
        pass
    try:
        top_artist = getattr(ax, '_top_xlabel_artist', None)
        color = getattr(ax, '_stored_top_xlabel_color', None)
        if top_artist is not None and color:
            top_artist.set_color(color)
    except Exception:
        pass
    try:
        right_artist = getattr(ax, '_right_ylabel_artist', None)
        color = getattr(ax, '_stored_right_ylabel_color', None)
        if right_artist is not None and color:
            right_artist.set_color(color)
    except Exception:
        pass


def _apply_spine_color(ax, fig, tick_state, spine_name: str, color) -> None:
    if color is None:
        return
    try:
        _ui_set_spine_side_color(ax, spine_name, color, fig=fig)
        if spine_name == 'top':
            _ui_position_top_xlabel(ax, fig, tick_state)
        elif spine_name == 'bottom':
            ax._stored_xlabel_color = color
            _ui_position_bottom_xlabel(ax, fig, tick_state)
        elif spine_name == 'left':
            ax._stored_ylabel_color = color
            _ui_position_left_ylabel(ax, fig, tick_state)
        elif spine_name == 'right':
            _ui_position_right_ylabel(ax, fig, tick_state)
    except Exception:
        pass
    _apply_stored_axis_colors(ax)


def _diffcap_clean_series(x: np.ndarray, y: np.ndarray, min_step: float = 1e-3) -> Tuple[np.ndarray, np.ndarray, int]:
    """Remove points where ΔPotential < min_step (default 1 mV) while preserving order."""
    if x.size <= 1:
        return x, y, 0
    keep_indices = [0]
    last_x = x[0]
    removed = 0
    for idx in range(1, x.size):
        if abs(x[idx] - last_x) >= min_step:
            keep_indices.append(idx)
            last_x = x[idx]
        else:
            removed += 1
    if removed == 0:
        return x, y, 0
    keep = np.array(keep_indices, dtype=int)
    return x[keep], y[keep], removed


def _apply_stored_smooth_settings(cycle_lines: Dict[int, Dict[str, Optional[Any]]], fig) -> None:
    """Apply stored smooth settings to newly visible cycles that haven't been smoothed yet."""
    if not hasattr(fig, '_dqdv_smooth_settings'):
        return
    settings = fig._dqdv_smooth_settings
    if not settings:
        return
    
    method = settings.get('method')
    if method == 'diffcap':
        min_step = settings.get('min_step', 0.001)
        window = settings.get('window', 9)
        poly = settings.get('poly', 3)
        for cyc, parts in cycle_lines.items():
            iter_parts = [(None, parts)] if not isinstance(parts, dict) else parts.items()
            for role, ln in iter_parts:
                if ln is None or not ln.get_visible():
                    continue
                # Only apply if this cycle hasn't been smoothed yet
                if hasattr(ln, '_smooth_applied') and ln._smooth_applied:
                    continue
                xdata = np.asarray(ln.get_xdata(), float)
                ydata = np.asarray(ln.get_ydata(), float)
                if xdata.size != ydata.size:
                    n = int(min(xdata.size, ydata.size))
                    if n < 3:
                        continue
                    xdata = xdata[:n]
                    ydata = ydata[:n]
                if xdata.size < 3:
                    continue
                # Get original data if available, otherwise use current data
                if hasattr(ln, '_original_xdata'):
                    xdata = np.asarray(ln._original_xdata, float)
                    ydata = np.asarray(ln._original_ydata, float)
                    if xdata.size != ydata.size:
                        n = int(min(xdata.size, ydata.size))
                        if n < 3:
                            continue
                        xdata = xdata[:n]
                        ydata = ydata[:n]
                else:
                    ln._original_xdata = np.array(xdata, copy=True)
                    ln._original_ydata = np.array(ydata, copy=True)
                x_clean, y_clean, removed = _diffcap_clean_series(xdata, ydata, min_step)
                if x_clean.size < poly + 2:
                    continue
                y_smooth = _savgol_smooth(y_clean, window, poly)
                ln.set_xdata(x_clean)
                ln.set_ydata(y_smooth)
                ln._smooth_applied = True
    elif method == 'voltage_step':
        threshold_v = settings.get('threshold_v', 0.0005)
        for cyc, parts in cycle_lines.items():
            for role in ("charge", "discharge"):
                ln = parts.get(role) if isinstance(parts, dict) else parts
                if ln is None or not ln.get_visible():
                    continue
                # Only apply if this cycle hasn't been smoothed yet
                if hasattr(ln, '_smooth_applied') and ln._smooth_applied:
                    continue
                xdata = np.asarray(ln.get_xdata(), float)
                ydata = np.asarray(ln.get_ydata(), float)
                if xdata.size != ydata.size:
                    n = int(min(xdata.size, ydata.size))
                    if n < 3:
                        continue
                    xdata = xdata[:n]
                    ydata = ydata[:n]
                if xdata.size < 3:
                    continue
                # Get original data if available, otherwise use current data
                if hasattr(ln, '_original_xdata'):
                    xdata = np.asarray(ln._original_xdata, float)
                    ydata = np.asarray(ln._original_ydata, float)
                    if xdata.size != ydata.size:
                        n = int(min(xdata.size, ydata.size))
                        if n < 3:
                            continue
                        xdata = xdata[:n]
                        ydata = ydata[:n]
                else:
                    ln._original_xdata = np.array(xdata, copy=True)
                    ln._original_ydata = np.array(ydata, copy=True)
                dv = np.abs(np.diff(xdata))
                mask = np.ones_like(xdata, dtype=bool)
                mask[1:] &= dv >= threshold_v
                mask[:-1] &= dv >= threshold_v
                filtered_x = xdata[mask]
                filtered_y = ydata[mask]
                if len(filtered_x) < len(xdata):
                    ln.set_xdata(filtered_x)
                    ln.set_ydata(filtered_y)
                    ln._smooth_applied = True
    elif method == 'outlier':
        outlier_method = settings.get('outlier_method', '1')
        threshold = settings.get('threshold', 5.0)
        for cyc, parts in cycle_lines.items():
            for role in ("charge", "discharge"):
                ln = parts.get(role) if isinstance(parts, dict) else parts
                if ln is None or not ln.get_visible():
                    continue
                # Only apply if this cycle hasn't been smoothed yet
                if hasattr(ln, '_smooth_applied') and ln._smooth_applied:
                    continue
                xdata = np.asarray(ln.get_xdata(), float)
                ydata = np.asarray(ln.get_ydata(), float)
                if xdata.size != ydata.size:
                    n = int(min(xdata.size, ydata.size))
                    if n < 5:
                        continue
                    xdata = xdata[:n]
                    ydata = ydata[:n]
                if xdata.size < 5:
                    continue
                # Get original data if available, otherwise use current data
                if hasattr(ln, '_original_xdata'):
                    xdata = np.asarray(ln._original_xdata, float)
                    ydata = np.asarray(ln._original_ydata, float)
                    if xdata.size != ydata.size:
                        n = int(min(xdata.size, ydata.size))
                        if n < 5:
                            continue
                        xdata = xdata[:n]
                        ydata = ydata[:n]
                else:
                    ln._original_xdata = np.array(xdata, copy=True)
                    ln._original_ydata = np.array(ydata, copy=True)
                if outlier_method == '1':
                    mean_y = np.nanmean(ydata)
                    std_y = np.nanstd(ydata)
                    if not np.isfinite(std_y) or std_y == 0:
                        continue
                    zscores = np.abs((ydata - mean_y) / std_y)
                    mask = zscores <= threshold
                else:
                    median_y = np.nanmedian(ydata)
                    mad = np.nanmedian(np.abs(ydata - median_y))
                    if not np.isfinite(mad) or mad == 0:
                        continue
                    deviations = np.abs(ydata - median_y) / mad
                    mask = deviations <= threshold
                filtered_x = xdata[mask]
                filtered_y = ydata[mask]
                if len(filtered_x) < len(xdata):
                    ln.set_xdata(filtered_x)
                    ln.set_ydata(filtered_y)
                    ln._smooth_applied = True


def _ec_font_artists(ax):
    fig = ax.get_figure()
    return collect_fig_font_artists(ax, fig, include_title=True, include_axes_texts=True)


def _apply_font_family(ax, family: str):
    try:
        set_font_family_defaults(family, update_mathtext=True)
        apply_font_family_to_artists(_ec_font_artists(ax), family)
        refresh_font_extras_on_artists(ax.get_figure(), _ec_font_artists(ax))
    except Exception:
        pass


def _apply_font_size(ax, size: float):
    """Apply font size to all text elements on the axes."""
    try:
        set_font_size_default(size)
        apply_font_size_to_artists(_ec_font_artists(ax), size)
        refresh_font_extras_on_artists(ax.get_figure(), _ec_font_artists(ax))
    except Exception:
        pass


# pyright: ignore[reportGeneralTypeIssues]
def electrochem_interactive_menu(fig, ax, cycle_lines: Optional[Dict[int, Dict[str, Optional[Any]]]] = None, file_path=None, file_data: Optional[List[Dict]] = None, canvas_mode: bool = False):
    # --- Multi-file: normalize to file_data list; single file keeps existing behavior ---
    if file_data is None:
        if cycle_lines is None:
            raise ValueError("electrochem_interactive_menu requires cycle_lines or file_data")
        file_path_str = (os.path.basename(file_path) if file_path else "Data")
        file_data = [{
            "filename": file_path_str,
            "cycle_lines": cycle_lines,
            "visible": True,
            "filepath": file_path,
        }]
    else:
        file_data = list(file_data)
        for i, f in enumerate(file_data):
            if "visible" not in f:
                f["visible"] = True
            if "filename" not in f:
                f["filename"] = os.path.basename(f.get("filepath", "Data")) if f.get("filepath") else "Data"
            if "display_name" not in f:
                f["display_name"] = f.get("filename", str(i + 1))
    is_multi_file = len(file_data) > 1
    # Effective cycle_lines for single-file backward compat (first file).
    # Always a dict here: the only None path (file_data is None and cycle_lines
    # is None) already raised ValueError above. Narrow the type so the menu's
    # cycle_lines usages are not flagged as operating on Optional/None.
    cycle_lines = file_data[0]["cycle_lines"]
    assert cycle_lines is not None
    # Store on figure so _rebuild_legend / _apply_legend_position can use
    try:
        fig._ec_file_data = file_data
        fig._ec_is_multi_file = is_multi_file
        if is_multi_file and not hasattr(fig, '_ec_legend_file_order'):
            fig._ec_legend_file_order = list(range(len(file_data)))
    except Exception:
        pass

    def _print_file_list(_file_data, _current_idx=0):
        """Print numbered file list with visibility marker (multi-file only)."""
        if not is_multi_file or not _file_data:
            return
        for i, f in enumerate(_file_data):
            vis = "visible" if f.get("visible", True) else "hidden"
            name = f.get("filename", "?")
            mark = ">" if i == _current_idx else " "
            print(f"  {mark} {i+1}: {name} [{vis}]")

    def _set_file_visibility(f_entry: Dict, visible: bool):
        """Set all lines in a file's cycle_lines to visible or not."""
        f_entry["visible"] = visible
        cl = f_entry.get("cycle_lines") or {}
        for cyc, parts in cl.items():
            if isinstance(parts, dict):
                for role in ("charge", "discharge"):
                    ln = parts.get(role)
                    if ln is not None:
                        try:
                            ln.set_visible(visible)
                        except Exception:
                            pass
            else:
                try:
                    parts.set_visible(visible)
                except Exception:
                    pass

    def _iter_visible_cycle_lines():
        """Iterate over (cyc, role, ln) for all visible files."""
        for f in file_data:
            if not f.get("visible", True):
                continue
            for item in _iter_cycle_lines(f.get("cycle_lines") or {}):
                yield item

    def _apply_display_mode(mode: str) -> None:
        """Apply charge/discharge display mode across all visible files.

        Respects cycle selection: only applies to cycles that are currently visible
        (selected in c: cycles/colors). Hidden cycles stay hidden.

        mode:
            'both'      -> show both charge and discharge (no filtering)
            'charge'    -> show only charge curves (hide discharge)
            'discharge' -> show only discharge curves (hide charge)

        CV curves (no separate charge/discharge) are always shown.
        """
        valid_modes = {"both", "charge", "discharge"}
        if mode not in valid_modes:
            return

        for f in file_data:
            if not f.get("visible", True):
                continue
            cl = f.get("cycle_lines") or {}
            for cyc, parts in cl.items():
                if isinstance(parts, dict):
                    chg = parts.get("charge")
                    dch = parts.get("discharge")
                    # Skip cycles hidden by user (cycle selection in c: cycles/colors)
                    cycle_selected = (
                        (chg is not None and chg.get_visible()) or
                        (dch is not None and dch.get_visible())
                    )
                    if not cycle_selected:
                        continue
                    # Charge
                    if chg is not None:
                        try:
                            chg.set_visible(mode in ("both", "charge"))
                        except Exception:
                            pass
                    # Discharge
                    if dch is not None:
                        try:
                            dch.set_visible(mode in ("both", "discharge"))
                        except Exception:
                            pass
                else:
                    # CV-style single line: always visible regardless of mode
                    try:
                        parts.set_visible(True)
                    except Exception:
                        pass

    # --- Tick/label state and helpers (similar to normal XY menu) ---
    tick_state = getattr(ax, '_saved_tick_state', {
        'bx': True,
        'tx': False,
        'ly': True,
        'ry': False,
        'mbx': False,
        'mtx': False,
        'mly': False,
        'mry': False,
    })

    base_ylabel = ax.get_ylabel() or ''
    if not hasattr(ax, '_stored_xlabel'):
        ax._stored_xlabel = ax.get_xlabel() or ''
    if not hasattr(ax, '_stored_ylabel'):
        ax._stored_ylabel = base_ylabel
    if not hasattr(ax, '_stored_xlabel_color'):
        try:
            ax._stored_xlabel_color = ax.xaxis.label.get_color()
        except Exception:
            ax._stored_xlabel_color = None
    if not hasattr(ax, '_stored_ylabel_color'):
        try:
            ax._stored_ylabel_color = ax.yaxis.label.get_color()
        except Exception:
            ax._stored_ylabel_color = None
    if not hasattr(ax, '_stored_top_xlabel_color'):
        ax._stored_top_xlabel_color = ax.xaxis.label.get_color()
    if not hasattr(ax, '_stored_right_ylabel_color'):
        ax._stored_right_ylabel_color = ax.yaxis.label.get_color()
    
    # Detect dQdV mode: check stored flag first, then fall back to y-label detection
    # This handles cases where the user renamed the y-axis and saved/reloaded the session
    is_dqdv = getattr(ax, '_is_dqdv_mode', None)
    if is_dqdv is None:
        # Initial detection: check if y-label contains "dQ"
        is_dqdv = 'dQ' in base_ylabel
        # Store the mode on the axes for persistence
        ax._is_dqdv_mode = is_dqdv

    # Menu title: dQdV / GC / CV
    is_gc = False
    for _cyc, parts in (cycle_lines or {}).items():
        is_gc = isinstance(parts, dict)
        break
    if is_dqdv:
        menu_title = "dQdV Interactive Menu"
    elif is_gc:
        menu_title = "GC Interactive Menu"
    else:
        menu_title = "CV Interactive Menu"

    # Store original x/y limits for 'auto' command (restore to original data range)
    if not hasattr(ax, '_original_xlim'):
        # Get original limits from all visible files' cycle lines
        try:
            all_x = []
            all_y = []
            for cyc, role, ln in _iter_visible_cycle_lines():
                try:
                    xd = np.asarray(ln.get_xdata(), dtype=float)
                    yd = np.asarray(ln.get_ydata(), dtype=float)
                    if xd.size > 0:
                        all_x.extend([xd.min(), xd.max()])
                    if yd.size > 0:
                        all_y.extend([yd.min(), yd.max()])
                except Exception:
                    pass
            if all_x:
                ax._original_xlim = (min(all_x), max(all_x))
            else:
                ax._original_xlim = ax.get_xlim()
            if all_y:
                ax._original_ylim = (min(all_y), max(all_y))
            else:
                ax._original_ylim = ax.get_ylim()
        except Exception:
            ax._original_xlim = ax.get_xlim()
            ax._original_ylim = ax.get_ylim()

    source_inputs = []
    if file_path:
        source_inputs.append(file_path)
    source_inputs.extend(getattr(fig, '_bp_source_paths', None) or [])
    source_paths = normalize_source_paths(source_inputs, require_exists=True)
    if not source_paths and hasattr(ax, 'figure'):
        source_paths = normalize_source_paths(
            getattr(ax.figure, '_bp_source_paths', None) or [],
            require_exists=True,
        )
    try:
        fig._bp_source_paths = list(source_paths)
    except Exception:
        pass

    def _set_spine_visible(which: str, visible: bool):
        sp = ax.spines.get(which)
        if sp is not None:
            try:
                sp.set_visible(bool(visible))
            except Exception:
                pass

    def _get_spine_visible(which: str) -> bool:
        sp = ax.spines.get(which)
        try:
            return bool(sp.get_visible()) if sp is not None else False
        except Exception:
            return False

    def _update_tick_visibility():
        # Use shared UI helper for consistent behavior
        try:
            _ui_update_tick_visibility(ax, tick_state)
        except Exception:
            pass
        # Persist on axes
        try:
            ax._saved_tick_state = dict(tick_state)
        except Exception:
            pass
        # Keep label spacing consistent with XY behavior
        try:
            _ui_position_bottom_xlabel(ax, ax.figure, tick_state)
            _ui_position_left_ylabel(ax, ax.figure, tick_state)
        except Exception:
            pass

    def _title_offset_menu():
        """Allow nudging duplicate top/right titles by single-pixel increments."""
        # Import UI positioning functions locally to ensure they're accessible in nested functions
        
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
                print("Top duplicate title is currently hidden (enable with w5).")
                return
            while True:
                current_y_px = _px_value('_top_xlabel_manual_offset_y_pts')
                current_x_px = _px_value('_top_xlabel_manual_offset_x_pts')
                print(f"Top title offset: Y={current_y_px:+.2f} px (positive=up), X={current_x_px:+.2f} px (positive=right)")
                sub = _safe_input(_colorize_prompt("top (w=up, s=down, a=left, d=right, 0=reset, q=back): ")).strip().lower()
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
                _ui_position_top_xlabel(ax, fig, tick_state)
                try:
                    fig.canvas.draw_idle()
                except Exception:
                    pass

        def _right_menu():
            if not getattr(ax, '_right_ylabel_on', False):
                print("Right duplicate title is currently hidden (enable with d5).")
                return
            while True:
                current_x_px = _px_value('_right_ylabel_manual_offset_x_pts')
                current_y_px = _px_value('_right_ylabel_manual_offset_y_pts')
                print(f"Right title offset: X={current_x_px:+.2f} px (positive=right), Y={current_y_px:+.2f} px (positive=up)")
                sub = _safe_input(_colorize_prompt("right (d=right, a=left, w=up, s=down, 0=reset, q=back): ")).strip().lower()
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
                _ui_position_right_ylabel(ax, fig, tick_state)
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
                sub = _safe_input(_colorize_prompt("bottom (s=down, w=up, 0=reset, q=back): ")).strip().lower()
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
                _ui_position_bottom_xlabel(ax, fig, tick_state)
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
                sub = _safe_input(_colorize_prompt("left (a=left, d=right, 0=reset, q=back): ")).strip().lower()
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
                _ui_position_left_ylabel(ax, fig, tick_state)
                try:
                    fig.canvas.draw_idle()
                except Exception:
                    pass

        while True:
            print(_colorize_inline_commands("Title offsets:"))
            print("  " + _colorize_menu('w : adjust top title (w=up, s=down, a=left, d=right)'))
            print("  " + _colorize_menu('s : adjust bottom title (s=down, w=up)'))
            print("  " + _colorize_menu('a : adjust left title (a=left, d=right)'))
            print("  " + _colorize_menu('d : adjust right title (d=right, a=left, w=up, s=down)'))
            print("  " + _colorize_menu('r : reset all offsets'))
            print("  " + _colorize_menu('q : return'))
            choice = _safe_input(_colorize_prompt(
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
                _set_attr('_top_xlabel_manual_offset_y_pts', 0.0)
                _set_attr('_top_xlabel_manual_offset_x_pts', 0.0)
                _set_attr('_bottom_xlabel_manual_offset_y_pts', 0.0)
                _set_attr('_left_ylabel_manual_offset_x_pts', 0.0)
                _set_attr('_right_ylabel_manual_offset_x_pts', 0.0)
                _set_attr('_right_ylabel_manual_offset_y_pts', 0.0)
                _ui_position_top_xlabel(ax, fig, tick_state)
                _ui_position_bottom_xlabel(ax, fig, tick_state)
                _ui_position_left_ylabel(ax, fig, tick_state)
                _ui_position_right_ylabel(ax, fig, tick_state)
                try:
                    fig.canvas.draw_idle()
                except Exception:
                    pass
                print("Reset manual offsets for all titles.")
                continue
            print("Unknown option. Use w/s/a/d/r/q.")

    def _apply_nice_ticks():
            try:
                # Only enforce MaxNLocator for linear scales; let Matplotlib defaults handle log/symlog
                if (getattr(ax, 'get_xscale', None) and ax.get_xscale() == 'linear'):
                    ax.xaxis.set_major_locator(MaxNLocator(nbins='auto', steps=[1, 2, 5], min_n_ticks=4))
                if (getattr(ax, 'get_yscale', None) and ax.get_yscale() == 'linear'):
                    ax.yaxis.set_major_locator(MaxNLocator(nbins='auto', steps=[1, 2, 5], min_n_ticks=4))
            except Exception:
                pass
    # Ensure nice ticks on entry and apply initial visibility
    _apply_nice_ticks()
    _update_tick_visibility()
    _ui_position_top_xlabel(ax, fig, tick_state)
    _ui_position_right_ylabel(ax, fig, tick_state)
    _store_legend_title(fig, ax)
    # Union of cycle numbers across all files (single file = first file's keys)
    all_cycles = sorted(set(cyc for f in file_data for cyc in (f.get("cycle_lines") or {}).keys()))

    # Initialize legend visibility preference
    if not hasattr(fig, '_ec_legend_user_visible'):
        try:
            leg0 = ax.get_legend()
            visible = True
            if leg0 is not None:
                visible = bool(leg0.get_visible())
            _set_legend_user_pref(fig, visible)
        except Exception:
            _set_legend_user_pref(fig, True)
    else:
        if not _get_legend_user_pref(fig):
            leg0 = ax.get_legend()
            if leg0 is not None:
                try:
                    leg0.set_visible(False)
                except Exception:
                    pass
    # ---------------- Undo stack ----------------
    state_history: List[dict] = []

    def _tick_width(axis_obj, which: str):
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
    def _locator_step(locator):
        try:
            if isinstance(locator, MultipleLocator):
                return float(locator._edge.step)
        except Exception:
            pass
        return None
    def _locator_ndivs(locator):
        try:
            if isinstance(locator, AutoMinorLocator):
                return int(locator._ndivs)
        except Exception:
            pass
        return None

    def push_state(note: str = ""):
        try:
            snap = {
                'note': note,
                'xlim': ax.get_xlim(),
                'ylim': ax.get_ylim(),
                'xscale': ax.get_xscale(),
                'yscale': ax.get_yscale(),
                'xlabel': ax.get_xlabel(),
                'ylabel': ax.get_ylabel(),
                'tick_state': dict(tick_state),
                'wasd_state': dict(getattr(fig, '_ec_wasd_state', {})) if hasattr(fig, '_ec_wasd_state') else {},
                'fig_size': list(fig.get_size_inches()),
                'axes_bbox': [float(v) for v in ax.get_position().bounds],
                'rotation_angle': getattr(fig, '_ec_rotation_angle', 0),
                'labelpads': {
                    'x': getattr(ax.xaxis, 'labelpad', None),
                    'y': getattr(ax.yaxis, 'labelpad', None),
                },
                'spines': {name: {
                    'lw': (ax.spines.get(name).get_linewidth() if ax.spines.get(name) else None),
                    'visible': (ax.spines.get(name).get_visible() if ax.spines.get(name) else None),
                    'color': (ax.spines.get(name).get_edgecolor() if ax.spines.get(name) else None)
                } for name in ('bottom','top','left','right')},
                'display_mode': getattr(fig, '_ec_display_mode', 'both'),
                'xaxis_dual': {
                    'mode': getattr(fig, '_xaxis_mode', 'capacity'),
                    'c_theoretical': getattr(fig, '_xaxis_c_theoretical', None),
                    'swapped': getattr(fig, '_xaxis_swapped', False),
                    'top_axis': capture_dual_top_axis(fig, ax),
                },
                '_dqdv_smooth_settings': dict(getattr(fig, '_dqdv_smooth_settings', {})),
                'tick_widths': {
                    'x_major': _tick_width(ax.xaxis, 'major'),
                    'x_minor': _tick_width(ax.xaxis, 'minor'),
                    'y_major': _tick_width(ax.yaxis, 'major'),
                    'y_minor': _tick_width(ax.yaxis, 'minor')
                },
                'tick_lengths': dict(getattr(fig, '_tick_lengths', {'major': None, 'minor': None})),
                'tick_direction': getattr(fig, '_tick_direction', 'out'),
                'tick_spacing': capture_axes_tick_locators(ax, ('x', 'y')),
                'font_size': plt.rcParams.get('font.size'),
                'font_family': plt.rcParams.get('font.family'),
                'font_sans_serif': list(plt.rcParams.get('font.sans-serif', [])),
                'mathtext_fontset': plt.rcParams.get('mathtext.fontset'),
                'font_extras': font_extras_export_dict(fig),
                'axis_label_colors': {
                    'x': getattr(ax, '_stored_xlabel_color', None) or ax.xaxis.label.get_color(),
                    'y': getattr(ax, '_stored_ylabel_color', None) or ax.yaxis.label.get_color(),
                },
                'titles': {
                    'top_x': bool(getattr(ax, '_top_xlabel_on', False)),
                    'right_y': bool(getattr(ax, '_right_ylabel_on', False))
                },
                'title_offsets': {
                    'top_y': float(getattr(ax, '_top_xlabel_manual_offset_y_pts', 0.0) or 0.0),
                    'top_x': float(getattr(ax, '_top_xlabel_manual_offset_x_pts', 0.0) or 0.0),
                    'bottom_y': float(getattr(ax, '_bottom_xlabel_manual_offset_y_pts', 0.0) or 0.0),
                    'left_x': float(getattr(ax, '_left_ylabel_manual_offset_x_pts', 0.0) or 0.0),
                    'right_x': float(getattr(ax, '_right_ylabel_manual_offset_x_pts', 0.0) or 0.0),
                    'right_y': float(getattr(ax, '_right_ylabel_manual_offset_y_pts', 0.0) or 0.0),
                },
                'legend': {
                    'visible': False,
                    'position_inches': None,
                },
                'grid': False,
                'lines': []
            }
            # Grid state
            try:
                current_grid = False
                for line in ax.get_xgridlines() + ax.get_ygridlines():
                    if line.get_visible():
                        current_grid = True
                        break
                snap['grid'] = current_grid
            except Exception:
                snap['grid'] = ax.xaxis._gridOnMajor if hasattr(ax.xaxis, '_gridOnMajor') else False
            try:
                leg_obj = ax.get_legend()
                snap['legend']['visible'] = bool(leg_obj.get_visible()) if leg_obj is not None else False
            except Exception:
                pass
            try:
                snap['legend']['title'] = _get_legend_title(fig)
            except Exception:
                snap['legend']['title'] = None
            try:
                legend_xy = getattr(fig, '_ec_legend_xy_in', None)
                if legend_xy is not None:
                    snap['legend']['position_inches'] = (float(legend_xy[0]), float(legend_xy[1]))
            except Exception:
                snap['legend']['position_inches'] = None
            try:
                snap['legend_user_visible'] = getattr(fig, '_ec_legend_user_visible', None)
            except Exception:
                pass
            for i, ln in enumerate(ax.lines):
                try:
                    snap['lines'].append({
                        'index': i,
                        'x': np.array(ln.get_xdata(), copy=True),
                        'y': np.array(ln.get_ydata(), copy=True),
                        'color': ln.get_color(),
                        'lw': ln.get_linewidth(),
                        'ls': ln.get_linestyle(),
                        'alpha': ln.get_alpha(),
                        'visible': ln.get_visible(),
                        'marker': ln.get_marker(),
                        'markersize': getattr(ln, 'get_markersize', lambda: None)(),
                        'markerfacecolor': getattr(ln, 'get_markerfacecolor', lambda: None)(),
                        'markeredgecolor': getattr(ln, 'get_markeredgecolor', lambda: None)()
                    })
                except Exception:
                    snap['lines'].append({'index': i})
            if is_multi_file and file_data:
                snap['file_visibility'] = [f.get('visible', True) for f in file_data]
                snap['file_display_names'] = [f.get('display_name', f.get('filename', str(i))) for i, f in enumerate(file_data)]
                snap['legend_file_order'] = list(getattr(fig, '_ec_legend_file_order', None) or range(len(file_data)))
            try:
                cs, cs_pf = capture_cycle_styles_snapshot(cycle_lines, file_data if is_multi_file else None)
                snap['cycle_styles'] = cs
                if cs_pf is not None:
                    snap['cycle_styles_per_file'] = cs_pf
            except Exception:
                pass
            try:
                clw, cms = capture_ec_curve_marker_defaults(cycle_lines)
                snap['curve_linewidth'] = clw
                if cms:
                    snap['curve_markers'] = cms
            except Exception:
                pass
            state_history.append(snap)
            if len(state_history) > 40:
                state_history.pop(0)
        except Exception:
            # Minimal fallback so undo still works if full snapshot fails
            try:
                fallback = {
                    'note': f"{note}-fallback",
                    'xlim': ax.get_xlim(),
                    'ylim': ax.get_ylim(),
                    'legend': {
                        'visible': bool(ax.get_legend().get_visible()) if ax.get_legend() else False,
                        'position_inches': getattr(fig, '_ec_legend_xy_in', None),
                        'title': _get_legend_title(fig),
                    },
                    'lines': []
                }
                for i, ln in enumerate(ax.lines):
                    try:
                        fallback['lines'].append({
                            'index': i,
                            'color': ln.get_color(),
                            'visible': ln.get_visible(),
                        })
                    except Exception:
                        fallback['lines'].append({'index': i})
                if is_multi_file and file_data:
                    fallback['file_visibility'] = [f.get('visible', True) for f in file_data]
                    fallback['file_display_names'] = [f.get('display_name', f.get('filename', str(i))) for i, f in enumerate(file_data)]
                    fallback['legend_file_order'] = list(getattr(fig, '_ec_legend_file_order', None) or range(len(file_data)))
                state_history.append(fallback)
                if len(state_history) > 40:
                    state_history.pop(0)
            except Exception:
                pass

    def pop_undo():
        if state_history:
            state_history.pop()

    def restore_state():
        if not state_history:
            print("No undo history.")
            return
        snap = state_history.pop()
        try:
            try:
                fs = snap.get('fig_size')
                if fs and isinstance(fs, (list, tuple)) and len(fs) == 2:
                    fig.set_size_inches(float(fs[0]), float(fs[1]), forward=True)
            except Exception:
                pass
            # Scales, limits, labels
            try:
                ax.set_xscale(snap.get('xscale','linear'))
                ax.set_yscale(snap.get('yscale','linear'))
            except Exception:
                pass
            try:
                ax.set_xlim(*snap.get('xlim', ax.get_xlim()))
                ax.set_ylim(*snap.get('ylim', ax.get_ylim()))
                _apply_nice_ticks()
            except Exception:
                pass
            try:
                bbox = snap.get('axes_bbox')
                if bbox and isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                    x0, y0, width, height = [float(v) for v in bbox]
                    if 0 <= x0 < x0 + width <= 1 and 0 <= y0 < y0 + height <= 1:
                        ax.set_position([x0, y0, width, height])
            except Exception:
                pass
            try:
                ax.set_xlabel(snap.get('xlabel') or '')
                ax.set_ylabel(snap.get('ylabel') or '')
            except Exception:
                pass
            # Tick state
            st = snap.get('tick_state', {})
            for k,v in st.items():
                if k in tick_state:
                    tick_state[k] = bool(v)
            # WASD state
            wasd_snap = snap.get('wasd_state', {})
            if wasd_snap:
                setattr(fig, '_ec_wasd_state', wasd_snap)
                _sync_tick_state()
                _apply_wasd()
            _update_tick_visibility()
            # Rotation angle
            try:
                rot_angle = snap.get('rotation_angle', 0)
                setattr(fig, '_ec_rotation_angle', rot_angle)
            except Exception:
                pass
            # Spines
            for name, spec in snap.get('spines', {}).items():
                sp = ax.spines.get(name)
                if not sp: continue
                if spec.get('lw') is not None:
                    try: sp.set_linewidth(spec['lw'])
                    except Exception: pass
                if spec.get('visible') is not None:
                    try: sp.set_visible(bool(spec['visible']))
                    except Exception: pass
                if spec.get('color') is not None:
                    try:
                        _ui_set_spine_side_color(ax, name, spec['color'], fig=fig)
                    except Exception:
                        pass
            # Tick widths
            tw = snap.get('tick_widths', {})
            try:
                if tw.get('x_major') is not None:
                    ax.tick_params(axis='x', which='major', width=tw['x_major'])
                if tw.get('x_minor') is not None:
                    ax.tick_params(axis='x', which='minor', width=tw['x_minor'])
                if tw.get('y_major') is not None:
                    ax.tick_params(axis='y', which='major', width=tw['y_major'])
                if tw.get('y_minor') is not None:
                    ax.tick_params(axis='y', which='minor', width=tw['y_minor'])
            except Exception:
                pass
            # Tick lengths
            tl = snap.get('tick_lengths', {})
            try:
                if tl.get('major') is not None:
                    ax.tick_params(axis='both', which='major', length=tl['major'])
                if tl.get('minor') is not None:
                    ax.tick_params(axis='both', which='minor', length=tl['minor'])
                if tl:
                    fig._tick_lengths = dict(tl)
            except Exception:
                pass
            # Tick direction
            try:
                tick_dir = snap.get('tick_direction', 'out')
                if tick_dir:
                    setattr(fig, '_tick_direction', tick_dir)
                    ax.tick_params(axis='both', which='both', direction=tick_dir)
            except Exception:
                pass
            # Tick spacing / minor locators (after WASD restore above)
            try:
                restore_axes_tick_locators(ax, snap.get('tick_spacing'), ('x', 'y'))
            except Exception:
                pass
            try:
                tick_state_snap = getattr(ax, '_saved_tick_state', None) or snap.get('tick_state', {})
                finalize_spine_colors(fig, ax, tick_state=tick_state_snap)
            except Exception:
                pass
            # Font size and family
            try:
                font_size = snap.get('font_size')
                if font_size is not None:
                    mpl.rcParams['font.size'] = font_size
                    _apply_font_size(ax, font_size)
                    _rebuild_legend(ax)
            except Exception:
                pass
            try:
                font_family = snap.get('font_family')
                font_sans_serif = snap.get('font_sans_serif')
                if font_family is not None:
                    mpl.rcParams['font.family'] = font_family
                if font_sans_serif is not None:
                    mpl.rcParams['font.sans-serif'] = font_sans_serif
                    # Apply to axes if family was set
                    if font_family or font_sans_serif:
                        # Get the actual font family to use
                        if font_sans_serif and len(font_sans_serif) > 0:
                            _apply_font_family(ax, font_sans_serif[0])
                        elif font_family:
                            _apply_font_family(ax, font_family)
                    _rebuild_legend(ax)
            except Exception:
                pass
            try:
                mathtext_fontset = snap.get('mathtext_fontset')
                if mathtext_fontset:
                    mpl.rcParams['mathtext.fontset'] = mathtext_fontset
            except Exception:
                pass
            try:
                apply_font_extras_from_cfg(fig, _ec_font_artists(ax), snap.get('font_extras'))
            except Exception:
                pass
            try:
                axis_label_colors = snap.get('axis_label_colors') or {}
                if axis_label_colors.get('x') is not None:
                    ax.xaxis.label.set_color(axis_label_colors['x'])
                    ax._stored_xlabel_color = axis_label_colors['x']
                if axis_label_colors.get('y') is not None:
                    ax.yaxis.label.set_color(axis_label_colors['y'])
                    ax._stored_ylabel_color = axis_label_colors['y']
            except Exception:
                pass
            # Title offsets - all four titles
            try:
                offsets = snap.get('title_offsets', {})
                # Support both old format (top/right) and new format (top_y/top_x/bottom_y/left_x/right_x/right_y)
                try:
                    if 'top_y' in offsets:
                        ax._top_xlabel_manual_offset_y_pts = float(offsets.get('top_y', 0.0) or 0.0)
                    else:
                        # Backward compatibility: old format used 'top' for y-offset
                        ax._top_xlabel_manual_offset_y_pts = float(offsets.get('top', 0.0) or 0.0)
                except Exception:
                    ax._top_xlabel_manual_offset_y_pts = 0.0
                try:
                    ax._top_xlabel_manual_offset_x_pts = float(offsets.get('top_x', 0.0) or 0.0)
                except Exception:
                    ax._top_xlabel_manual_offset_x_pts = 0.0
                try:
                    ax._bottom_xlabel_manual_offset_y_pts = float(offsets.get('bottom_y', 0.0) or 0.0)
                except Exception:
                    ax._bottom_xlabel_manual_offset_y_pts = 0.0
                try:
                    ax._left_ylabel_manual_offset_x_pts = float(offsets.get('left_x', 0.0) or 0.0)
                except Exception:
                    ax._left_ylabel_manual_offset_x_pts = 0.0
                try:
                    if 'right_x' in offsets:
                        ax._right_ylabel_manual_offset_x_pts = float(offsets.get('right_x', 0.0) or 0.0)
                    else:
                        # Backward compatibility: old format used 'right' for x-offset
                        ax._right_ylabel_manual_offset_x_pts = float(offsets.get('right', 0.0) or 0.0)
                except Exception:
                    ax._right_ylabel_manual_offset_x_pts = 0.0
                try:
                    ax._right_ylabel_manual_offset_y_pts = float(offsets.get('right_y', 0.0) or 0.0)
                except Exception:
                    ax._right_ylabel_manual_offset_y_pts = 0.0
                ax._top_xlabel_on = bool(snap.get('titles',{}).get('top_x', False))
                ax._right_ylabel_on = bool(snap.get('titles',{}).get('right_y', False))
                # Note: Do NOT call position functions during undo restore as it causes title drift
                # Title offsets are already restored from snapshot above
            except Exception:
                pass
            # Restore labelpads (for title positioning)
            try:
                pads = snap.get('labelpads', {})
                if pads:
                    if pads.get('x') is not None:
                        ax.xaxis.labelpad = pads['x']
                    if pads.get('y') is not None:
                        ax.yaxis.labelpad = pads['y']
            except Exception:
                pass
            # Lines (by index)
            try:
                if len(ax.lines) == len(snap.get('lines', [])):
                    for item in snap['lines']:
                        idx = item.get('index')
                        if idx is None or idx >= len(ax.lines):
                            continue
                        ln = ax.lines[idx]
                        if 'x' in item and 'y' in item:
                            ln.set_data(item['x'], item['y'])
                        if item.get('color') is not None:
                            ln.set_color(item['color'])
                        if item.get('lw') is not None:
                            ln.set_linewidth(item['lw'])
                        if item.get('ls') is not None:
                            ln.set_linestyle(item['ls'])
                        if item.get('alpha') is not None:
                            ln.set_alpha(item['alpha'])
                        if item.get('visible') is not None:
                            ln.set_visible(bool(item['visible']))
                        if item.get('marker') is not None:
                            ln.set_marker(item['marker'])
                        if item.get('markersize') is not None:
                            try:
                                ln.set_markersize(item['markersize'])
                            except Exception:
                                pass
                        if item.get('markerfacecolor') is not None:
                            try:
                                ln.set_markerfacecolor(item['markerfacecolor'])
                            except Exception:
                                pass
                        if item.get('markeredgecolor') is not None:
                            try:
                                ln.set_markeredgecolor(item['markeredgecolor'])
                            except Exception:
                                pass
            except Exception:
                pass
            # Sync file_data visibility after line restore (multi-file)
            try:
                if is_multi_file and file_data and 'file_visibility' in snap:
                    vis_list = snap.get('file_visibility', [])
                    for i, f in enumerate(file_data):
                        if i < len(vis_list):
                            f['visible'] = bool(vis_list[i])
            except Exception:
                pass
            # Restore display_mode (d command)
            try:
                dm = snap.get('display_mode')
                if dm in ('charge', 'discharge', 'both'):
                    fig._ec_display_mode = dm
                    _apply_display_mode(dm)
            except Exception:
                pass
            # Restore xaxis_dual (a, x commands)
            try:
                xd = snap.get('xaxis_dual')
                if isinstance(xd, dict):
                    fig._xaxis_mode = xd.get('mode', 'capacity')
                    fig._xaxis_c_theoretical = xd.get('c_theoretical')
                    fig._xaxis_swapped = bool(xd.get('swapped', False))
                    # Recreate secondary axis for dual mode
                    mode = fig._xaxis_mode
                    c_th = fig._xaxis_c_theoretical
                    swapped = fig._xaxis_swapped
                    if hasattr(fig, '_xaxis_secondary') and fig._xaxis_secondary is not None:
                        try:
                            fig._xaxis_secondary.remove()
                        except Exception:
                            pass
                        fig._xaxis_secondary = None
                    if mode == 'dual' and c_th is not None:
                        c_th = float(c_th)
                        if swapped:
                            def _bt_ions(v): return v * c_th
                            def _tb_cap(v): return v / c_th
                            bottom_to_top, top_to_bottom = _bt_ions, _tb_cap
                        else:
                            def _bt_cap(v): return v / c_th
                            def _tb_ions(v): return v * c_th
                            bottom_to_top, top_to_bottom = _bt_cap, _tb_ions
                        try:
                            secax = ax.secondary_xaxis('top', functions=(bottom_to_top, top_to_bottom))
                            fig._xaxis_secondary = secax
                            cap_lbl = "Specific Capacity (mAh g$^{{-1}}$)"
                            ion_lbl = f"Number of ions (C / {c_th:g} mAh g$^{{-1}}$)"
                            if swapped:
                                ax.set_xlabel(ion_lbl)
                                secax.set_xlabel(cap_lbl)
                            else:
                                ax.set_xlabel(cap_lbl)
                                secax.set_xlabel(ion_lbl)
                            apply_dual_top_axis_style(secax, xd.get('top_axis'))
                        except Exception:
                            pass
                    elif mode == 'ions' and c_th is not None:
                        # Lines already restored from snap (x=ions); just set label
                        ax.set_xlabel(f"Number of ions (C / {float(c_th):g} mAh g$^{{-1}}$)")
            except Exception:
                pass
            # Per-cycle styles (c command) and global marker template
            try:
                curve_markers = snap.get('curve_markers', {})
                if curve_markers:
                    for cyc, role, ln in _iter_cycle_lines(cycle_lines):
                        try:
                            if 'linestyle' in curve_markers:
                                ln.set_linestyle(curve_markers['linestyle'])
                            if 'marker' in curve_markers:
                                ln.set_marker(curve_markers['marker'])
                            if 'markersize' in curve_markers:
                                ln.set_markersize(curve_markers['markersize'])
                            if 'markerfacecolor' in curve_markers:
                                ln.set_markerfacecolor(curve_markers['markerfacecolor'])
                            if 'markeredgecolor' in curve_markers:
                                ln.set_markeredgecolor(curve_markers['markeredgecolor'])
                        except Exception:
                            pass
                curve_linewidth = snap.get('curve_linewidth')
                if curve_linewidth is not None:
                    try:
                        fig._ec_curve_linewidth = float(curve_linewidth)
                    except Exception:
                        pass
                    for cyc, role, ln in _iter_cycle_lines(cycle_lines):
                        try:
                            ln.set_linewidth(float(curve_linewidth))
                        except Exception:
                            pass
                cycle_styles_per_file_cfg = snap.get('cycle_styles_per_file')
                cycle_styles_cfg = snap.get('cycle_styles')
                if cycle_styles_per_file_cfg and is_multi_file and file_data and len(cycle_styles_per_file_cfg) == len(file_data):
                    for i, f in enumerate(file_data):
                        cl = f.get('cycle_lines')
                        if cl and i < len(cycle_styles_per_file_cfg):
                            _apply_cycle_styles(cl, cycle_styles_per_file_cfg[i])
                elif cycle_styles_cfg:
                    if is_multi_file and file_data:
                        for f in file_data:
                            cl = f.get('cycle_lines')
                            if cl:
                                _apply_cycle_styles(cl, cycle_styles_cfg)
                    else:
                        _apply_cycle_styles(cycle_lines, cycle_styles_cfg)
            except Exception:
                pass
            # Restore dQ/dV smooth settings (sm command)
            try:
                smooth_cfg = snap.get('_dqdv_smooth_settings')
                if isinstance(smooth_cfg, dict):
                    fig._dqdv_smooth_settings = dict(smooth_cfg)
                    # Line data is already restored from snap['lines']; smooth_cfg is metadata for future cycle changes
                else:
                    fig._dqdv_smooth_settings = {}
            except Exception:
                pass
            # Restore file display names (multi-file) and update legend labels
            try:
                if is_multi_file and file_data and snap.get('file_display_names'):
                    names = snap.get('file_display_names', [])
                    for i, f in enumerate(file_data):
                        if i < len(names):
                            f['display_name'] = names[i]
                    _apply_file_display_names_to_legend(file_data)
            except Exception:
                pass
            # Restore legend file order (ra command)
            try:
                if is_multi_file and file_data and 'legend_file_order' in snap:
                    order = snap.get('legend_file_order')
                    if isinstance(order, (list, tuple)) and len(order) == len(file_data):
                        fig._ec_legend_file_order = list(order)
            except Exception:
                pass
            # Grid state
            if 'grid' in snap:
                try:
                    grid_enabled = snap.get('grid', False)
                    if grid_enabled:
                        ax.grid(True, color='0.85', linestyle='-', linewidth=0.5, alpha=0.7)
                    else:
                        ax.grid(False)
                except Exception:
                    pass
            legend_snap = snap.get('legend', {})
            if legend_snap:
                try:
                    if 'title' in legend_snap:
                        fig._ec_legend_title = legend_snap.get('title') or _get_legend_title(fig)
                    xy = legend_snap.get('position_inches')
                    fig._ec_legend_xy_in = _sanitize_legend_offset(fig, xy) if xy is not None else None
                except Exception:
                    pass
            if 'legend_user_visible' in snap:
                try:
                    fig._ec_legend_user_visible = bool(snap['legend_user_visible'])
                except Exception:
                    pass
            _rebuild_legend(ax)
            if legend_snap:
                try:
                    if legend_snap.get('visible'):
                        _apply_legend_position(fig, ax)
                    leg_obj = ax.get_legend()
                    if leg_obj is not None:
                        leg_obj.set_visible(bool(legend_snap.get('visible', False)))
                except Exception:
                    pass
            try:
                tick_state_snap = getattr(ax, '_saved_tick_state', None) or snap.get('tick_state', {})
                finalize_spine_colors(fig, ax, tick_state=tick_state_snap)
            except Exception:
                pass
            try:
                fig.canvas.draw()
            except Exception:
                fig.canvas.draw_idle()
            print("Undo: restored previous state.")
        except Exception as e:
            print(f"Undo failed: {e}")
    _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
    if is_multi_file:
        _print_file_list(file_data)
        # Rebuild legend with n columns (one per file) when entering multi-file menu
        try:
            _rebuild_legend(ax)
            if hasattr(fig, "canvas") and fig.canvas is not None:
                fig.canvas.draw_idle()
        except Exception:
            pass
    current_file_idx = 0
    pending_key = None
    ec_actions = ElectrochemActionContext(
        fig=fig,
        ax=ax,
        cycle_lines=cycle_lines,
        file_data=file_data,
        tick_state=tick_state,
        source_paths=source_paths,
        all_cycles=all_cycles,
        is_dqdv=is_dqdv,
        is_multi_file=is_multi_file,
        menu_title=menu_title,
        canvas_mode=canvas_mode,
        print_menu=_print_menu,
        push_state=push_state,
        pop_undo=pop_undo,
        restore_state=restore_state,
        format_file_timestamp=_format_file_timestamp,
        savefig_plot_window=_ec_savefig_plot_window,
        rebuild_legend=_rebuild_legend,
        get_style_snapshot=_get_style_snapshot,
        get_geometry_snapshot=_get_geometry_snapshot,
        print_style_snapshot=_print_style_snapshot,
        export_style_dialog=_export_style_dialog,
        apply_font_family=_apply_font_family,
        apply_font_size=_apply_font_size,
        apply_spine_color=_apply_spine_color,
        iter_cycle_lines=_iter_cycle_lines,
        apply_cycle_styles=_apply_cycle_styles,
        apply_stored_smooth_settings=_apply_stored_smooth_settings,
        sanitize_legend_offset=_sanitize_legend_offset,
        apply_file_display_names_to_legend=_apply_file_display_names_to_legend,
        apply_display_mode=_apply_display_mode,
        ui_position_top_xlabel=_ui_position_top_xlabel,
        ui_position_bottom_xlabel=_ui_position_bottom_xlabel,
        ui_position_left_ylabel=_ui_position_left_ylabel,
        ui_position_right_ylabel=_ui_position_right_ylabel,
        apply_legend_position=_apply_legend_position,
        set_legend_user_pref=_set_legend_user_pref,
    )

    # Crosshair state
    crosshair = {'active': False, 'hline': None, 'vline': None, 'text': None, 'cid_motion': None}
    register_crosshair(fig, crosshair)

    def _toggle_crosshair_ec():
        if not crosshair['active']:
            vline = ax.axvline(x=ax.get_xlim()[0], color='0.35', ls='--', lw=0.8, alpha=0.85, zorder=9999)
            hline = ax.axhline(y=ax.get_ylim()[0], color='0.35', ls='--', lw=0.8, alpha=0.85, zorder=9999)
            txt = ax.text(1.0, 1.0, "", ha='right', va='bottom', transform=ax.transAxes,
                          fontsize=max(9, int(0.6 * plt.rcParams.get('font.size', 16))),
                          color='0.15', bbox=dict(boxstyle='round,pad=0.25', fc='white', ec='0.7', alpha=0.8))

            def on_move(event):
                if event.inaxes != ax or event.xdata is None or event.ydata is None:
                    return
                x = float(event.xdata)
                y = float(event.ydata)
                vline.set_xdata([x, x])
                hline.set_ydata([y, y])
                xmode = getattr(fig, '_xaxis_mode', 'capacity')
                c_th = getattr(fig, '_xaxis_c_theoretical', None)
                swapped = getattr(fig, '_xaxis_swapped', False)
                if xmode == 'dual' and c_th is not None:
                    c_th = float(c_th)
                    if swapped:
                        cap_val = x * c_th
                        ions_val = x
                        txt.set_text(f"Capacity={cap_val:.4g} mAh/g\nIons={ions_val:.4g}\nV={y:.4g}")
                    else:
                        cap_val = x
                        ions_val = x / c_th
                        txt.set_text(f"Capacity={cap_val:.4g} mAh/g\nIons={ions_val:.4g}\nV={y:.4g}")
                elif xmode == 'ions' and c_th is not None:
                    cap_val = x * float(c_th)
                    txt.set_text(f"Ions={x:.4g}\nCapacity={cap_val:.4g} mAh/g\nV={y:.4g}")
                else:
                    txt.set_text(f"x={x:.4g}\nV={y:.4g}")
                fig.canvas.draw_idle()

            cid = fig.canvas.mpl_connect('motion_notify_event', on_move)
            crosshair.update({'active': True, 'hline': hline, 'vline': vline, 'text': txt, 'cid_motion': cid})
            print("Crosshair ON. Move mouse over axes. Press 'n' again to turn off.")
        else:
            if crosshair['cid_motion'] is not None:
                fig.canvas.mpl_disconnect(crosshair['cid_motion'])
            for k in ('hline', 'vline', 'text'):
                art = crosshair.get(k)
                if art is not None:
                    try:
                        art.remove()
                    except Exception:
                        pass
            crosshair.update({'active': False, 'hline': None, 'vline': None, 'text': None, 'cid_motion': None})
            fig.canvas.draw_idle()
            print("Crosshair OFF.")

    def _handle_key_sm():
            nonlocal choice, cyc, idx, ln, parts, sub
            if not is_dqdv:
                print("Smoothing is only available in dQ/dV mode.")
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                return
            # Multi-file: choose target file(s) for smoothing
            smooth_target_list = [cycle_lines]
            if is_multi_file:
                _print_file_list(file_data, current_file_idx)
                choice = _safe_input(f"Select file numbers (1-{len(file_data)}), all (a), or q=cancel: ").strip().lower()
                if choice == 'q':
                    _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                    _print_file_list(file_data, current_file_idx)
                    return
                if choice in ('a', 'all'):
                    smooth_target_list = [f['cycle_lines'] for f in file_data if f.get('visible', True)]
                else:
                    try:
                        idx = int(choice)
                        if 1 <= idx <= len(file_data):
                            smooth_target_list = [file_data[idx - 1]['cycle_lines']]
                        else:
                            print("Invalid file number.")
                            return
                    except ValueError:
                        print("Invalid input.")
                        return
            while True:
                print("\n\033[1mdQ/dV Data Filtering (Neware method)\033[0m")
                print("Commands:")
                print("  " + _colorize_menu("a: apply potential step filter (removes small ΔV points)"))
                print("  " + _colorize_menu("d: DiffCap smooth (≥1 mV ΔV + Savitzky–Golay, order 3, window 9)"))
                print("  " + _colorize_menu("o: remove outliers (removes abrupt dQ/dV spikes)"))
                print("  " + _colorize_menu("r: reset to original data"))
                print("  " + _colorize_menu("q: back to main menu"))
                sub = _safe_input(_colorize_prompt(
                    "dQ/dV filter command (a/d/o/r per list above, q=back to main menu): "
                )).strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub == 'r':
                    push_state("smooth-reset")
                    restored_count = 0
                    try:
                        for _tcl in smooth_target_list:
                            for cyc, parts in _tcl.items():
                                for role in ("charge", "discharge"):
                                    ln = parts.get(role) if isinstance(parts, dict) else parts
                                    if ln is None:
                                        continue
                                    if hasattr(ln, '_original_xdata'):
                                        ln.set_xdata(ln._original_xdata)
                                        ln.set_ydata(ln._original_ydata)
                                        if hasattr(ln, '_smooth_applied'):
                                            delattr(ln, '_smooth_applied')
                                        restored_count += 1
                        if restored_count:
                            print(f"Reset {restored_count} curve(s) to original data.")
                            # Clear stored smooth settings
                            if hasattr(fig, '_dqdv_smooth_settings'):
                                fig._dqdv_smooth_settings = {}
                            fig.canvas.draw_idle()
                        else:
                            print("No filtered data to reset.")
                    except Exception as e:
                        print(f"Error resetting filter: {e}")
                    continue
                if sub == 'a':
                    try:
                        while True:
                            threshold_input = _safe_input("Enter minimum potential step in mV (default 0.5 mV, 'q'=quit, 'e'=explain): ").strip()
                            if threshold_input.lower() == 'q':
                                break
                            if threshold_input.lower() == 'e':
                                print("\n--- Potential Step Filter Explanation ---")
                                print("This filter removes data points where the potential change (ΔV) between")
                                print("consecutive points is smaller than the threshold.")
                                print("\nExample: If threshold = 0.5 mV, any point where |V[i+1] - V[i]| < 0.5 mV")
                                print("will be removed. This helps eliminate noisy or redundant measurements.")
                                print("\nTypical values: 0.1-1.0 mV (smaller = more aggressive filtering)")
                                print("Higher values remove more points but may oversmooth the data.")
                                print("----------------------------------------\n")
                                continue
                            threshold_mv = 0.5 if not threshold_input else float(threshold_input)
                            break
                        if threshold_input.lower() == 'q':  # User quit
                            continue
                        threshold_v = threshold_mv / 1000.0
                        if threshold_v <= 0:
                            print("Threshold must be positive.")
                            continue
                        push_state("smooth-apply")
                        # Store smooth settings for future cycle changes
                        if not hasattr(fig, '_dqdv_smooth_settings'):
                            fig._dqdv_smooth_settings = {}
                        fig._dqdv_smooth_settings.update({
                            'method': 'voltage_step',
                            'threshold_v': threshold_v
                        })
                        filtered = 0
                        total_before = 0
                        total_after = 0
                        for _tcl in smooth_target_list:
                            for cyc, parts in _tcl.items():
                                for role in ("charge", "discharge"):
                                    ln = parts.get(role) if isinstance(parts, dict) else parts
                                    if ln is None or not ln.get_visible():
                                        continue
                                    xdata = np.asarray(ln.get_xdata(), float)
                                    ydata = np.asarray(ln.get_ydata(), float)
                                    if xdata.size != ydata.size:
                                        n = int(min(xdata.size, ydata.size))
                                        if n < 3:
                                            continue
                                        xdata = xdata[:n]
                                        ydata = ydata[:n]
                                    if xdata.size < 3:
                                        continue
                                    if not hasattr(ln, '_original_xdata'):
                                        ln._original_xdata = np.array(xdata, copy=True)
                                        ln._original_ydata = np.array(ydata, copy=True)
                                    dv = np.abs(np.diff(xdata))
                                    mask = np.ones_like(xdata, dtype=bool)
                                    mask[1:] &= dv >= threshold_v
                                    mask[:-1] &= dv >= threshold_v
                                    filtered_x = xdata[mask]
                                    filtered_y = ydata[mask]
                                    before = len(xdata)
                                    after = len(filtered_x)
                                    if after < before:
                                        ln.set_xdata(filtered_x)
                                        ln.set_ydata(filtered_y)
                                        ln._smooth_applied = True
                                        filtered += 1
                                        total_before += before
                                        total_after += after
                        if filtered:
                            removed = total_before - total_after
                            pct = 100 * removed / total_before if total_before else 0
                            print(f"Filtered {filtered} curve(s); removed {removed} of {total_before} points ({pct:.1f}%).")
                            print("Tip: Increase threshold to aggressively filter points (always applied to raw data).")
                            fig.canvas.draw_idle()
                        else:
                            print("No curves affected by current threshold.")
                    except ValueError:
                        print("Invalid number.")
                    continue
                if sub == 'd':
                    try:
                        print("DiffCap smoothing per Thompson et al. (2020): clean ΔV < threshold and apply Savitzky–Golay (order 3).")
                        while True:
                            delta_input = _safe_input("Minimum ΔV between points (mV, default 1.0, 'q'=quit, 'e'=explain): ").strip()
                            if delta_input.lower() == 'q':
                                break
                            if delta_input.lower() == 'e':
                                print("\n--- Minimum ΔV Explanation ---")
                                print("First step: Remove points where potential change is too small.")
                                print("This threshold (in mV) determines the minimum potential difference")
                                print("required between consecutive points. Points with smaller ΔV are")
                                print("removed as noise before smoothing.")
                                print("\nTypical values: 0.5-2.0 mV")
                                print("Smaller values = keep more points (less aggressive cleaning)")
                                print("Larger values = remove more points (more aggressive cleaning)")
                                print("--------------------------------\n")
                                continue
                            min_step = 0.001 if not delta_input else max(float(delta_input), 0.0) / 1000.0
                            if min_step <= 0:
                                print("ΔV threshold must be positive.")
                                continue
                            break
                        # Only skip if user explicitly quit with 'q', not if they pressed Enter (empty = use default)
                        if delta_input and delta_input.lower() == 'q':  # User quit at previous step
                            continue
                        while True:
                            window_input = _safe_input("Savitzky–Golay window (odd, default 9, 'q'=quit, 'e'=explain): ").strip()
                            if window_input.lower() == 'q':
                                break
                            if window_input.lower() == 'e':
                                print("\n--- Savitzky–Golay Window Explanation ---")
                                print("The window size determines how many neighboring points are used")
                                print("to smooth each data point. Must be an odd number (3, 5, 7, 9, 11, ...).")
                                print("\nLarger window = smoother result but may lose fine details")
                                print("Smaller window = preserves more detail but less smoothing")
                                print("\nTypical values: 5-15 (9 is a good default)")
                                print("Window must be larger than polynomial order.")
                                print("------------------------------------------\n")
                                continue
                            window = 9 if not window_input else int(window_input)
                            break
                        # Only skip if user explicitly quit with 'q', not if they pressed Enter (empty = use default)
                        if window_input and window_input.lower() == 'q':  # User quit at previous step
                            continue
                        while True:
                            poly_input = _safe_input("Polynomial order (default 3, 'q'=quit, 'e'=explain): ").strip()
                            if poly_input.lower() == 'q':
                                break
                            if poly_input.lower() == 'e':
                                print("\n--- Polynomial Order Explanation ---")
                                print("The polynomial order determines the complexity of the smoothing")
                                print("function. Higher order = more flexible curve fitting.")
                                print("\nOrder 1 = linear (straight line) - very smooth, may oversimplify")
                                print("Order 3 = cubic (default) - good balance of smoothness and detail")
                                print("Order 5+ = higher complexity - preserves more features, less smooth")
                                print("\nTypical values: 1-5 (3 is recommended)")
                                print("Order must be less than window size.")
                                print("--------------------------------------\n")
                                continue
                            poly = 3 if not poly_input else int(poly_input)
                            break
                        # Only skip if user explicitly quit with 'q', not if they pressed Enter (empty = use default)
                        if poly_input and poly_input.lower() == 'q':  # User quit at previous step
                            continue
                    except ValueError:
                        print("Invalid number.")
                        continue
                    if window < 3:
                        window = 3
                    if window % 2 == 0:
                        window += 1
                    if poly < 1:
                        poly = 1
                    push_state("smooth-diffcap")
                    # Store smooth settings for future cycle changes
                    if not hasattr(fig, '_dqdv_smooth_settings'):
                        fig._dqdv_smooth_settings = {}
                    fig._dqdv_smooth_settings.update({
                        'method': 'diffcap',
                        'min_step': min_step,
                        'window': window,
                        'poly': poly
                    })
                    cleaned_curves = 0
                    total_removed = 0
                    for _tcl in smooth_target_list:
                        for cyc, parts in _tcl.items():
                            iter_parts = [(None, parts)] if not isinstance(parts, dict) else [(k, v) for k, v in parts.items()]
                            for role, ln in iter_parts:
                                if ln is None or not ln.get_visible():
                                    continue
                                xdata = np.asarray(ln.get_xdata(), float)
                                ydata = np.asarray(ln.get_ydata(), float)
                                if xdata.size != ydata.size:
                                    n = int(min(xdata.size, ydata.size))
                                    if n < 3:
                                        continue
                                    xdata = xdata[:n]
                                    ydata = ydata[:n]
                                if xdata.size < 3:
                                    continue
                                if not hasattr(ln, '_original_xdata'):
                                    ln._original_xdata = np.array(xdata, copy=True)
                                    ln._original_ydata = np.array(ydata, copy=True)
                                x_clean, y_clean, removed = _diffcap_clean_series(xdata, ydata, min_step)
                                if x_clean.size < poly + 2:
                                    continue
                                y_smooth = _savgol_smooth(y_clean, window, poly)
                                ln.set_xdata(x_clean)
                                ln.set_ydata(y_smooth)
                                ln._smooth_applied = True
                                cleaned_curves += 1
                                total_removed += removed
                    if cleaned_curves:
                        print(f"DiffCap smoothing applied to {cleaned_curves} curve(s); removed {total_removed} noisy points.")
                        fig.canvas.draw_idle()
                    else:
                        print("No curves were smoothed (not enough data after cleaning).")
                    continue
                if sub == 'o':
                    print("Outlier removal methods:")
                    print("  " + _colorize_menu("1: Z-score (enter standard deviation threshold, default 5.0)"))
                    print("  " + _colorize_menu("2: MAD (median absolute deviation, default factor 6.0)"))
                    while True:
                        method = _safe_input("Method (1/2, blank=cancel, 'q'=quit, 'e'=explain): ").strip()
                        if not method or method.lower() == 'q':
                            break
                        if method.lower() == 'e':
                            print("\n--- Outlier Removal Methods Explanation ---")
                            print("Method 1 - Z-score:")
                            print("  Removes points where |(value - mean) / std| > threshold")
                            print("  Works well for normally distributed data")
                            print("  Default threshold: 5.0 (removes points >5 standard deviations)")
                            print("\nMethod 2 - MAD (Median Absolute Deviation):")
                            print("  Removes points where |(value - median) / MAD| > threshold")
                            print("  More robust to outliers (uses median instead of mean)")
                            print("  Default threshold: 6.0 (removes points >6 MAD units)")
                            print("\nHigher threshold = removes fewer points (less aggressive)")
                            print("Lower threshold = removes more points (more aggressive)")
                            print("Typical thresholds: 3.0-10.0")
                            print("--------------------------------------------\n")
                            continue
                        if method not in ('1', '2'):
                            print("Unknown method.")
                            continue
                        break
                    if not method:  # User canceled/quitted
                        continue
                    try:
                        while True:
                            thresh_input = _safe_input("Enter threshold (blank=default, 'q'=quit, 'e'=explain): ").strip()
                            if thresh_input.lower() == 'q':
                                break
                            if thresh_input.lower() == 'e':
                                if method == '1':
                                    print("\n--- Z-score Threshold Explanation ---")
                                    print("Threshold determines how many standard deviations a point can")
                                    print("deviate from the mean before being considered an outlier.")
                                    print("\nDefault: 5.0 (removes points where |z-score| > 5)")
                                    print("Higher values (6-10) = remove only extreme outliers")
                                    print("Lower values (2-4) = remove more points, including moderate spikes")
                                    print("\nExample: threshold=5.0 means points >5σ from mean are removed")
                                    print("--------------------------------------\n")
                                else:
                                    print("\n--- MAD Threshold Explanation ---")
                                    print("Threshold determines how many MAD units a point can deviate")
                                    print("from the median before being considered an outlier.")
                                    print("\nDefault: 6.0 (removes points where |MAD-score| > 6)")
                                    print("Higher values (7-10) = remove only extreme outliers")
                                    print("Lower values (3-5) = remove more points, including moderate spikes")
                                    print("\nMAD is more robust than standard deviation for noisy data.")
                                    print("----------------------------------\n")
                                continue
                            if method == '1':
                                z_threshold = 5.0 if not thresh_input else float(thresh_input)
                                if z_threshold <= 0:
                                    print("Threshold must be positive.")
                                    continue
                            else:
                                mad_threshold = 6.0 if not thresh_input else float(thresh_input)
                                if mad_threshold <= 0:
                                    print("Threshold must be positive.")
                                    continue
                            break
                        # Only skip if user explicitly quit with 'q', not if they pressed Enter (empty = use default)
                        if thresh_input and thresh_input.lower() == 'q':  # User quit
                            continue
                        push_state("smooth-outlier")
                        # Store smooth settings for future cycle changes
                        if not hasattr(fig, '_dqdv_smooth_settings'):
                            fig._dqdv_smooth_settings = {}
                        thresh_val = z_threshold if method == '1' else mad_threshold
                        fig._dqdv_smooth_settings.update({
                            'method': 'outlier',
                            'outlier_method': method,
                            'threshold': thresh_val
                        })
                        filtered = 0
                        total_before = 0
                        total_after = 0
                        for _tcl in smooth_target_list:
                            for cyc, parts in _tcl.items():
                                for role in ("charge", "discharge"):
                                    ln = parts.get(role) if isinstance(parts, dict) else parts
                                    if ln is None or not ln.get_visible():
                                        continue
                                    xdata = np.asarray(ln.get_xdata(), float)
                                    ydata = np.asarray(ln.get_ydata(), float)
                                    if xdata.size != ydata.size:
                                        n = int(min(xdata.size, ydata.size))
                                        if n < 5:
                                            continue
                                        xdata = xdata[:n]
                                        ydata = ydata[:n]
                                    if xdata.size < 5:
                                        continue
                                    if not hasattr(ln, '_original_xdata'):
                                        ln._original_xdata = np.array(xdata, copy=True)
                                        ln._original_ydata = np.array(ydata, copy=True)
                                    if method == '1':
                                        mean_y = np.nanmean(ydata)
                                        std_y = np.nanstd(ydata)
                                        if not np.isfinite(std_y) or std_y == 0:
                                            continue
                                        zscores = np.abs((ydata - mean_y) / std_y)
                                        mask = zscores <= z_threshold
                                    else:
                                        median_y = np.nanmedian(ydata)
                                        mad = np.nanmedian(np.abs(ydata - median_y))
                                        if not np.isfinite(mad) or mad == 0:
                                            continue
                                        deviations = np.abs(ydata - median_y) / mad
                                        mask = deviations <= mad_threshold
                                    filtered_x = xdata[mask]
                                    filtered_y = ydata[mask]
                                    before = len(xdata)
                                    after = len(filtered_x)
                                    if after < before:
                                        ln.set_xdata(filtered_x)
                                        ln.set_ydata(filtered_y)
                                        ln._smooth_applied = True
                                        filtered += 1
                                        total_before += before
                                        total_after += after
                        if filtered:
                            removed = total_before - total_after
                            pct = 100 * removed / total_before if total_before else 0
                            method_name = "Z-score" if method == '1' else "MAD"
                            print(f"Removed outliers from {filtered} curve(s) using {method_name} (threshold={thresh_val}).")
                            print(f"Removed {removed} of {total_before} points ({pct:.1f}%).")
                            print("Tip: Adjust threshold to control sensitivity (always applied to raw data).")
                            fig.canvas.draw_idle()
                        else:
                            print("No outliers found with current threshold.")
                    except ValueError:
                        print("Invalid number.")
                    continue
                print("Unknown command. Use a/o/r/q.")
            _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
            return

    def _handle_key_2d():
            nonlocal parts
            if not is_dqdv:
                print("2d contour is only available in dQ/dV mode.")
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                return
            try:
                from ..operando.interactive import operando_ec_interactive_menu as _op_ec_menu
            except ImportError:
                _op_ec_menu = None
            if _op_ec_menu is None:
                print("Contour interactive module is not available.")
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                return
            try:
                raw = _safe_input(_colorize_prompt(
                    "Potential window for 2D map: enter two voltages V_lo V_hi (e.g. 1 3), or q=cancel: "
                )).strip()
            except (KeyboardInterrupt, EOFError):
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                return
            if not raw or raw.lower() == 'q':
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                return
            parts = raw.replace(',', ' ').split()
            if len(parts) < 2:
                print("Enter exactly two numbers: lower and upper potential (V).")
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                return
            try:
                v_a, v_b = float(parts[0]), float(parts[1])
            except ValueError:
                print("Invalid numbers.")
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                return
            v_lo, v_hi = min(v_a, v_b), max(v_a, v_b)
            nx = 320
            try:
                built = _dqdv_build_butterfly_contour_stack(file_data, v_lo, v_hi, nx=nx)
            except Exception as e:
                print(f"Could not build 2D map: {e}")
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                return
            if built is None:
                print("No dQ/dV points in that potential window for visible cycles (check range and cycle visibility).")
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                return
            Z, gx, row_labels = built
            cfig = None
            cax = None
            im = None
            dv = float(v_hi - v_lo)
            try:
                cfig, cax = plt.subplots(figsize=_default_ec_figsize())
                Zm = np.ma.masked_invalid(Z)
                extent = (0.0, float(2 * dv), -0.5, float(Zm.shape[0] - 0.5))
                im = cax.imshow(
                    Zm, aspect="auto", origin="lower", extent=extent,
                    cmap="viridis", interpolation="nearest",
                )
                setattr(im, "_operando_cmap_name", "viridis")
                zlab = (ax.get_ylabel() or "").strip() or "dQ/dV"
                bind_dqdv_2d_contour_figure(
                    cfig, cax, im, v_lo, v_hi, row_labels, zlab=zlab,
                    file_data=file_data, nx=nx,
                )
                cbar_ax = cfig.add_axes((0.0, 0.0, 0.01, 0.01))

                class _MockColorbar:
                    def __init__(self, cax, im_ref):
                        self.ax = cax
                        self._im = im_ref

                    def set_label(self, label):
                        cax._colorbar_label = label

                    def update_normal(self, im_ref):
                        pass

                cbar = _MockColorbar(cbar_ax, im)
                cbar_ax._colorbar_label = zlab
                _paths = []
                for fd in file_data:
                    fp = fd.get("filepath")
                    if isinstance(fp, str) and fp:
                        _paths.append(fp)
                print(
                    "\n2D map uses the current line data (including smoothing). "
                    "Contour menu: same as operando without EC panel. Press q to return to dQ/dV menu.\n"
                )
                try:
                    cfig.canvas.draw()
                except Exception:
                    cfig.canvas.draw_idle()
                _op_ec_menu(cfig, cax, im, cbar, None, file_paths=_paths, canvas_mode=canvas_mode)
            except Exception as e:
                print(f"2D contour view failed: {e}")
            finally:
                try:
                    if (
                        cfig is not None
                        and cax is not None
                        and im is not None
                        and plt.fignum_exists(cfig.number)
                    ):
                        snap = build_dqdv_2d_snapshot(
                            cfig, cax, im, v_lo, v_hi, row_labels,
                            (ax.get_ylabel() or "").strip() or "dQ/dV",
                            cbar,
                        )
                        if snap is not None:
                            fig._dqdv_2d_snapshot = snap
                        else:
                            print("Warning: dQ/dV 2D snapshot could not be built (map may not persist on EC save).")
                except Exception as e:
                    print(f"Warning: could not capture dQ/dV 2D snapshot: {e}")
                try:
                    if cfig is not None and plt.fignum_exists(cfig.number):
                        plt.close(cfig)
                except Exception:
                    pass
                try:
                    fig.canvas.draw_idle()
                except Exception:
                    pass
            _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
            if is_multi_file:
                _print_file_list(file_data, current_file_idx)
            return

    def _handle_key_a():
            nonlocal ln, sub
            if is_dqdv:
                print("Capacity/ion conversion is not available in dQ/dV mode.")
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                return
            # Initialize dual axis state if not present
            if not hasattr(fig, '_xaxis_mode'):
                fig._xaxis_mode = 'capacity'  # 'capacity', 'ions', or 'dual'
            if not hasattr(fig, '_xaxis_c_theoretical'):
                fig._xaxis_c_theoretical = None
            if not hasattr(fig, '_xaxis_secondary'):
                fig._xaxis_secondary = None  # Store secondary axis object
            if not hasattr(fig, '_xaxis_swapped'):
                fig._xaxis_swapped = False  # If True, ions on bottom, capacity on top
            
            # X-axis submenu: number-of-ions vs capacity with dual mode
            while True:
                # Show current state
                current_mode = getattr(fig, '_xaxis_mode', 'capacity')
                c_th = getattr(fig, '_xaxis_c_theoretical', None)
                swapped = getattr(fig, '_xaxis_swapped', False)
                
                print("\nX-axis configuration:")
                print(f"  Current mode: {current_mode}")
                if c_th:
                    print(f"  Theoretical capacity: {c_th} mAh g⁻¹")
                if current_mode == 'dual':
                    bottom_label = "Ions" if swapped else "Capacity"
                    top_label = "Capacity" if swapped else "Ions"
                    print(f"  Bottom: {bottom_label}, Top: {top_label}")
                print("\nOptions:")
                print("  " + _colorize_menu("c : capacity only (bottom)"))
                print("  " + _colorize_menu("n : number of ions only (bottom)"))
                print("  " + _colorize_menu("d : dual mode (capacity bottom, ions top)"))
                if current_mode == 'dual':
                    print("  " + _colorize_menu("s : swap axes (switch top/bottom)"))
                if c_th:
                    print("  " + _colorize_menu("u : update theoretical capacity"))
                print("  " + _colorize_menu("q : back to main menu"))
                
                sub = _safe_input(_colorize_prompt(
                    "X-axis mode (c/n/d/s/u/q per menu above): "
                )).strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub == 'n':
                    # Get theoretical capacity
                    c_th_input = getattr(fig, '_xaxis_c_theoretical', None)
                    c_th = c_th_input
                    if not c_th_input:
                        print("Input the theoretical capacity per 1 active ion (mAh g^-1), e.g., 125")
                        c_th = None
                        while c_th is None:
                            val = _safe_input("C_theoretical_per_ion (q=back): ").strip()
                            if not val or val.lower() == 'q':
                                break
                            try:
                                parsed = float(val)
                                if parsed <= 0:
                                    print("Theoretical capacity must be positive.")
                                    continue
                                c_th = parsed
                            except Exception:
                                print("Invalid number.")
                        if c_th is None:
                            continue
                    
                    # Remove any existing secondary axis
                    if hasattr(fig, '_xaxis_secondary') and fig._xaxis_secondary is not None:
                        try:
                            fig._xaxis_secondary.remove()
                        except Exception:
                            pass
                        fig._xaxis_secondary = None
                    
                    # Store original x-data once, then set new x = orig_x / c_th
                    push_state("x=n(ions)")
                    for ln in ax.lines:
                        try:
                            if not hasattr(ln, "_orig_xdata_gc"):
                                x0 = np.asarray(ln.get_xdata(), dtype=float)
                                setattr(ln, "_orig_xdata_gc", x0.copy())
                            x_orig = getattr(ln, "_orig_xdata_gc")
                            ln.set_xdata(x_orig / c_th)
                        except Exception:
                            continue
                    
                    # Store state
                    fig._xaxis_mode = 'ions'
                    fig._xaxis_c_theoretical = c_th
                    # Construct label with proper mathtext for superscript
                    # Configure mathtext fontset BEFORE setting the label to ensure consistency
                    try:
                        font_fam = plt.rcParams.get('font.sans-serif', [''])
                        font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                        
                        # Configure mathtext to use the same font family
                        if font_fam_str:
                            # Configure mathtext fontset to match the regular font
                            # For Arial-like fonts, use dejavusans; for Times/STIX, use stix
                            lf = font_fam_str.lower()
                            if any(k in lf for k in ('stix', 'times', 'roman')):
                                mpl.rcParams['mathtext.fontset'] = 'stix'
                            else:
                                # Use dejavusans for Arial, Helvetica, etc. (closest match to Arial)
                                mpl.rcParams['mathtext.fontset'] = 'dejavusans'
                            mpl.rcParams['mathtext.default'] = 'regular'
                    except Exception:
                        pass
                    
                    label_text = f"Number of ions (C / {c_th:g} mAh g$^{{-1}}$)"
                    ax.set_xlabel(label_text)
                    
                    # Apply current font settings to the label to ensure consistency
                    try:
                        font_fam = plt.rcParams.get('font.sans-serif', [''])
                        font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                        font_size = plt.rcParams.get('font.size', None)
                        if font_fam_str:
                            ax.xaxis.label.set_family(font_fam_str)
                        if font_size is not None:
                            ax.xaxis.label.set_size(font_size)
                        # Force label to re-render with updated mathtext fontset by updating the text
                        ax.set_xlabel(label_text)
                    except Exception:
                        pass
                    _apply_nice_ticks()
                    try:
                        ax.relim(); ax.autoscale_view()
                    except Exception:
                        pass
                    try:
                        fig.canvas.draw()
                    except Exception:
                        fig.canvas.draw_idle()
                    print(f"✓ Ions mode enabled (bottom x-axis)")
                elif sub == 'c':
                    # Remove any existing secondary axis
                    if hasattr(fig, '_xaxis_secondary') and fig._xaxis_secondary is not None:
                        try:
                            fig._xaxis_secondary.remove()
                        except Exception:
                            pass
                        fig._xaxis_secondary = None
                    
                    # Restore original capacity on x if available
                    push_state("x=capacity")
                    any_restored = False
                    for ln in ax.lines:
                        try:
                            if hasattr(ln, "_orig_xdata_gc"):
                                x_orig = getattr(ln, "_orig_xdata_gc")
                                ln.set_xdata(x_orig)
                                any_restored = True
                        except Exception:
                            continue
                    
                    # Store state
                    fig._xaxis_mode = 'capacity'
                    # Construct label with proper mathtext for superscript
                    # Configure mathtext fontset BEFORE setting the label to ensure consistency
                    try:
                        font_fam = plt.rcParams.get('font.sans-serif', [''])
                        font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                        
                        # Configure mathtext to use the same font family
                        if font_fam_str:
                            # Configure mathtext fontset to match the regular font
                            # For Arial-like fonts, use dejavusans; for Times/STIX, use stix
                            lf = font_fam_str.lower()
                            if any(k in lf for k in ('stix', 'times', 'roman')):
                                mpl.rcParams['mathtext.fontset'] = 'stix'
                            else:
                                # Use dejavusans for Arial, Helvetica, etc. (closest match to Arial)
                                mpl.rcParams['mathtext.fontset'] = 'dejavusans'
                            mpl.rcParams['mathtext.default'] = 'regular'
                    except Exception:
                        pass
                    
                    label_text = "Specific Capacity (mAh g$^{{-1}}$)"
                    ax.set_xlabel(label_text)
                    
                    # Apply current font settings to the label to ensure consistency
                    try:
                        font_fam = plt.rcParams.get('font.sans-serif', [''])
                        font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                        font_size = plt.rcParams.get('font.size', None)
                        if font_fam_str:
                            ax.xaxis.label.set_family(font_fam_str)
                        if font_size is not None:
                            ax.xaxis.label.set_size(font_size)
                        # Force label to re-render with updated mathtext fontset by updating the text
                        ax.set_xlabel(label_text)
                    except Exception:
                        pass
                    if any_restored:
                        _apply_nice_ticks()
                        try:
                            ax.relim(); ax.autoscale_view()
                        except Exception:
                            pass
                        try:
                            fig.canvas.draw()
                        except Exception:
                            fig.canvas.draw_idle()
                    print(f"✓ Capacity mode enabled (bottom x-axis)")
                elif sub == 'd':
                    # Dual mode: capacity on bottom, ions on top (or swapped)
                    # Get theoretical capacity
                    c_th_input = getattr(fig, '_xaxis_c_theoretical', None)
                    c_th = c_th_input
                    if not c_th_input:
                        print("Input the theoretical capacity per 1 active ion (mAh g^-1), e.g., 125")
                        c_th = None
                        while c_th is None:
                            val = _safe_input("C_theoretical_per_ion (q=back): ").strip()
                            if not val or val.lower() == 'q':
                                break
                            try:
                                parsed = float(val)
                                if parsed <= 0:
                                    print("Theoretical capacity must be positive.")
                                    continue
                                c_th = parsed
                            except Exception:
                                print("Invalid number.")
                        if c_th is None:
                            continue
                    
                    push_state("x=dual")
                    
                    # Store original x-data and ensure primary axis shows capacity
                    for ln in ax.lines:
                        try:
                            if not hasattr(ln, "_orig_xdata_gc"):
                                x0 = np.asarray(ln.get_xdata(), dtype=float)
                                setattr(ln, "_orig_xdata_gc", x0.copy())
                            # Restore to capacity (primary data)
                            x_orig = getattr(ln, "_orig_xdata_gc")
                            ln.set_xdata(x_orig)
                        except Exception:
                            continue
                    
                    # Remove existing secondary axis if any
                    if hasattr(fig, '_xaxis_secondary') and fig._xaxis_secondary is not None:
                        try:
                            fig._xaxis_secondary.remove()
                        except Exception:
                            pass
                    
                    # Define conversion functions
                    def capacity_to_ions(capacity):
                        return capacity / c_th
                    
                    def ions_to_capacity(ions):
                        return ions * c_th
                    
                    # Create secondary x-axis on top
                    try:
                        secax = ax.secondary_xaxis('top', functions=(capacity_to_ions, ions_to_capacity))
                        fig._xaxis_secondary = secax
                        
                        # Configure mathtext fontset
                        try:
                            font_fam = plt.rcParams.get('font.sans-serif', [''])
                            font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                            if font_fam_str:
                                lf = font_fam_str.lower()
                                if any(k in lf for k in ('stix', 'times', 'roman')):
                                    mpl.rcParams['mathtext.fontset'] = 'stix'
                                else:
                                    mpl.rcParams['mathtext.fontset'] = 'dejavusans'
                                mpl.rcParams['mathtext.default'] = 'regular'
                        except Exception:
                            pass
                        
                        # Set labels
                        capacity_label = "Specific Capacity (mAh g$^{{-1}}$)"
                        ions_label = f"Number of ions (C / {c_th:g} mAh g$^{{-1}}$)"
                        
                        ax.set_xlabel(capacity_label)
                        secax.set_xlabel(ions_label)
                        
                        # Apply font settings to both labels
                        try:
                            font_fam = plt.rcParams.get('font.sans-serif', [''])
                            font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                            font_size = plt.rcParams.get('font.size', None)
                            if font_fam_str:
                                ax.xaxis.label.set_family(font_fam_str)
                                secax.xaxis.label.set_family(font_fam_str)
                            if font_size is not None:
                                ax.xaxis.label.set_size(font_size)
                                secax.xaxis.label.set_size(font_size)
                        except Exception:
                            pass
                        
                        # Store state
                        fig._xaxis_mode = 'dual'
                        fig._xaxis_c_theoretical = c_th
                        fig._xaxis_swapped = False
                        
                        _apply_nice_ticks()
                        try:
                            ax.relim(); ax.autoscale_view()
                        except Exception:
                            pass
                        try:
                            fig.canvas.draw()
                        except Exception:
                            fig.canvas.draw_idle()
                        
                        print(f"✓ Dual mode enabled")
                        print(f"  Bottom: Capacity (mAh g⁻¹)")
                        print(f"  Top: Number of ions (C / {c_th} mAh g⁻¹)")
                    except Exception as e:
                        print(f"Error creating dual axis: {e}")
                        fig._xaxis_mode = 'capacity'
                elif sub == 's':
                    # Swap axes (only available in dual mode)
                    if getattr(fig, '_xaxis_mode', 'capacity') != 'dual':
                        print("Swap is only available in dual mode. Use 'd' first.")
                        continue
                    
                    c_th = getattr(fig, '_xaxis_c_theoretical', None)
                    if not c_th:
                        print("Error: No theoretical capacity stored.")
                        continue
                    
                    push_state("x=swap")
                    
                    swapped = getattr(fig, '_xaxis_swapped', False)
                    new_swapped = not swapped
                    
                    # Remove existing secondary axis
                    if hasattr(fig, '_xaxis_secondary') and fig._xaxis_secondary is not None:
                        try:
                            fig._xaxis_secondary.remove()
                        except Exception:
                            pass
                    
                    # Update primary axis data and labels based on swap state
                    for ln in ax.lines:
                        try:
                            if hasattr(ln, "_orig_xdata_gc"):
                                x_orig = getattr(ln, "_orig_xdata_gc")
                                if new_swapped:
                                    # Ions on bottom: divide by c_th
                                    ln.set_xdata(x_orig / c_th)
                                else:
                                    # Capacity on bottom: restore original
                                    ln.set_xdata(x_orig)
                        except Exception:
                            continue
                    
                    # Define conversion functions
                    if new_swapped:
                        # Bottom = ions, Top = capacity
                        def _bottom_to_top_ions(ions):
                            return ions * c_th

                        def _top_to_bottom_capacity(capacity):
                            return capacity / c_th

                        bottom_to_top = _bottom_to_top_ions
                        top_to_bottom = _top_to_bottom_capacity
                    else:
                        # Bottom = capacity, Top = ions
                        def _bottom_to_top_capacity(capacity):
                            return capacity / c_th

                        def _top_to_bottom_ions(ions):
                            return ions * c_th

                        bottom_to_top = _bottom_to_top_capacity
                        top_to_bottom = _top_to_bottom_ions
                    
                    # Create new secondary axis
                    try:
                        secax = ax.secondary_xaxis('top', functions=(bottom_to_top, top_to_bottom))
                        fig._xaxis_secondary = secax
                        
                        # Configure mathtext fontset
                        try:
                            font_fam = plt.rcParams.get('font.sans-serif', [''])
                            font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                            if font_fam_str:
                                lf = font_fam_str.lower()
                                if any(k in lf for k in ('stix', 'times', 'roman')):
                                    mpl.rcParams['mathtext.fontset'] = 'stix'
                                else:
                                    mpl.rcParams['mathtext.fontset'] = 'dejavusans'
                                mpl.rcParams['mathtext.default'] = 'regular'
                        except Exception:
                            pass
                        
                        # Set labels based on swap state
                        capacity_label = "Specific Capacity (mAh g$^{{-1}}$)"
                        ions_label = f"Number of ions (C / {c_th:g} mAh g$^{{-1}}$)"
                        
                        if new_swapped:
                            ax.set_xlabel(ions_label)
                            secax.set_xlabel(capacity_label)
                        else:
                            ax.set_xlabel(capacity_label)
                            secax.set_xlabel(ions_label)
                        
                        # Apply font settings
                        try:
                            font_fam = plt.rcParams.get('font.sans-serif', [''])
                            font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                            font_size = plt.rcParams.get('font.size', None)
                            if font_fam_str:
                                ax.xaxis.label.set_family(font_fam_str)
                                secax.xaxis.label.set_family(font_fam_str)
                            if font_size is not None:
                                ax.xaxis.label.set_size(font_size)
                                secax.xaxis.label.set_size(font_size)
                        except Exception:
                            pass
                        
                        # Update state
                        fig._xaxis_swapped = new_swapped
                        
                        _apply_nice_ticks()
                        try:
                            ax.relim(); ax.autoscale_view()
                        except Exception:
                            pass
                        try:
                            fig.canvas.draw()
                        except Exception:
                            fig.canvas.draw_idle()
                        
                        bottom_label = "Ions" if new_swapped else "Capacity"
                        top_label = "Capacity" if new_swapped else "Ions"
                        print(f"✓ Axes swapped")
                        print(f"  Bottom: {bottom_label}")
                        print(f"  Top: {top_label}")
                    except Exception as e:
                        print(f"Error swapping axes: {e}")
                elif sub == 'u':
                    # Update theoretical capacity
                    while True:
                        current_c_th = getattr(fig, '_xaxis_c_theoretical', None)
                        if current_c_th:
                            print(f"Current theoretical capacity: {current_c_th} mAh g⁻¹")
                        print("Input new theoretical capacity per 1 active ion (mAh g^-1), e.g., 125")
                        val = _safe_input("C_theoretical_per_ion (q=back): ").strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_c_th = float(val)
                            if new_c_th <= 0:
                                print("Theoretical capacity must be positive.")
                                continue
                        except Exception:
                            print("Invalid number.")
                            continue

                        # Update stored value
                        old_c_th = getattr(fig, '_xaxis_c_theoretical', None)
                        fig._xaxis_c_theoretical = new_c_th
                        print(f"Updated theoretical capacity: {old_c_th} → {new_c_th} mAh g⁻¹")

                        # If in ions or dual mode, update the display
                        current_mode = getattr(fig, '_xaxis_mode', 'capacity')
                        if current_mode == 'ions':
                            push_state("update-c-theoretical")
                            for ln in ax.lines:
                                try:
                                    if hasattr(ln, "_orig_xdata_gc"):
                                        x_orig = getattr(ln, "_orig_xdata_gc")
                                        ln.set_xdata(x_orig / new_c_th)
                                except Exception:
                                    continue
                            label_text = f"Number of ions (C / {new_c_th:g} mAh g$^{{-1}}$)"
                            ax.set_xlabel(label_text)
                            _apply_nice_ticks()
                            try:
                                ax.relim(); ax.autoscale_view()
                            except Exception:
                                pass
                            try:
                                fig.canvas.draw()
                            except Exception:
                                fig.canvas.draw_idle()
                        elif current_mode == 'dual':
                            push_state("update-c-theoretical-dual")
                            swapped = getattr(fig, '_xaxis_swapped', False)
                            if hasattr(fig, '_xaxis_secondary') and fig._xaxis_secondary is not None:
                                try:
                                    fig._xaxis_secondary.remove()
                                except Exception:
                                    pass
                            for ln in ax.lines:
                                try:
                                    if hasattr(ln, "_orig_xdata_gc"):
                                        x_orig = getattr(ln, "_orig_xdata_gc")
                                        if swapped:
                                            ln.set_xdata(x_orig / new_c_th)
                                        else:
                                            ln.set_xdata(x_orig)
                                except Exception:
                                    continue
                            if swapped:
                                def _bottom_to_top_ions_new(ions):
                                    return ions * new_c_th
                                def _top_to_bottom_capacity_new(capacity):
                                    return capacity / new_c_th
                                bottom_to_top = _bottom_to_top_ions_new
                                top_to_bottom = _top_to_bottom_capacity_new
                            else:
                                def _bottom_to_top_capacity_new(capacity):
                                    return capacity / new_c_th
                                def _top_to_bottom_ions_new(ions):
                                    return ions * new_c_th
                                bottom_to_top = _bottom_to_top_capacity_new
                                top_to_bottom = _top_to_bottom_ions_new
                            try:
                                secax = ax.secondary_xaxis('top', functions=(bottom_to_top, top_to_bottom))
                                fig._xaxis_secondary = secax
                                capacity_label = "Specific Capacity (mAh g$^{{-1}}$)"
                                ions_label = f"Number of ions (C / {new_c_th:g} mAh g$^{{-1}}$)"
                                if swapped:
                                    ax.set_xlabel(ions_label)
                                    secax.set_xlabel(capacity_label)
                                else:
                                    ax.set_xlabel(capacity_label)
                                    secax.set_xlabel(ions_label)
                                try:
                                    font_fam = plt.rcParams.get('font.sans-serif', [''])
                                    font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                                    font_size = plt.rcParams.get('font.size', None)
                                    if font_fam_str:
                                        secax.xaxis.label.set_family(font_fam_str)
                                    if font_size is not None:
                                        secax.xaxis.label.set_size(font_size)
                                except Exception:
                                    pass
                                _apply_nice_ticks()
                                try:
                                    ax.relim(); ax.autoscale_view()
                                except Exception:
                                    pass
                                try:
                                    fig.canvas.draw()
                                except Exception:
                                    fig.canvas.draw_idle()
                            except Exception as e:
                                print(f"Error updating dual axis: {e}")
                        else:
                            print("Theoretical capacity updated (will be used if you switch to ions/dual mode)")
                else:
                    print(f"Unknown option: {sub}")
            _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
            return

    while True:
        try:
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
        if key == 'n':
            try:
                _toggle_crosshair_ec()
            except Exception as e:
                print(f"Error toggling crosshair: {e}")
            _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
            continue
        if key == 'v':
            # Show/hide files (multi-file only)
            try:
                if is_multi_file:
                    while True:
                        _print_file_list(file_data, current_file_idx)
                        choice = _safe_input(
                            _colorize_prompt(f"Toggle visibility (1-{len(file_data)}, a=all, q=back): ")
                        ).strip()
                        if not choice or choice.lower() == 'q':
                            break
                        if choice.lower() in ('a', 'all'):
                            push_state("visibility")
                            any_visible = any(f.get("visible", True) for f in file_data)
                            new_state = not any_visible
                            for f in file_data:
                                _set_file_visibility(f, new_state)
                        else:
                            try:
                                idx = int(choice) - 1
                                if 0 <= idx < len(file_data):
                                    push_state("visibility")
                                    f = file_data[idx]
                                    new_vis = not f.get("visible", True)
                                    _set_file_visibility(f, new_vis)
                                else:
                                    print("Invalid file number.")
                                    continue
                            except ValueError:
                                print("Invalid input.")
                                continue
                        try:
                            _rebuild_legend(ax)
                            fig.canvas.draw()  # pyright: ignore[reportOptionalMemberAccess]
                        except Exception:
                            fig.canvas.draw_idle()  # pyright: ignore[reportOptionalMemberAccess]
                else:
                    print("File visibility (v) is only available with multiple files.")
            except Exception as e:
                print(f"Visibility toggle failed: {e}")
            _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
            if is_multi_file:
                _print_file_list(file_data, current_file_idx)
            continue
        if key == 'q':
            if canvas_mode:
                break
            try:
                confirm = _safe_input(_colorize_prompt("Quit EC interactive? Remember to save (e=export, s=save). Quit now? (y/n): ")).strip().lower()
            except Exception:
                confirm = 'y'
            if confirm == 'y':
                break
            elif confirm in ('e', 's'):
                pending_key = confirm
                continue
            else:
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                continue
        elif key == 'b':
            handle_undo_command(ec_actions)
            continue
        elif key == 'd':
            # Display mode: charge-only / discharge-only / both
            try:
                while True:
                    print("\nDisplay mode for GC/dQdV/CV/CPC:")
                    print("  " + _colorize_menu("c: show only charge curves (hide discharge)"))
                    print("  " + _colorize_menu("d: show only discharge curves (hide charge)"))
                    print("  " + _colorize_menu("b: show both charge and discharge"))
                    print("  " + _colorize_menu("Which cycles are shown & colors: main menu c (e.g. 2-30 1 = cycles 2–30, palette 1 / tab10)"))
                    print("  " + _colorize_menu("q: back"))
                    sub = _safe_input(_colorize_prompt("Display (c/d/b/q): ")).strip().lower()
                    if not sub or sub == 'q':
                        break
                    if sub == 'c':
                        push_state("display-charge")
                        _apply_display_mode("charge")
                        try:
                            fig._ec_display_mode = "charge"
                        except Exception:
                            pass
                    elif sub == 'd':
                        push_state("display-discharge")
                        _apply_display_mode("discharge")
                        try:
                            fig._ec_display_mode = "discharge"
                        except Exception:
                            pass
                    elif sub == 'b':
                        push_state("display-both")
                        _apply_display_mode("both")
                        try:
                            fig._ec_display_mode = "both"
                        except Exception:
                            pass
                    else:
                        print("Unknown choice (use c, d, b, or q).")
                    try:
                        _rebuild_legend(ax)
                        fig.canvas.draw()  # pyright: ignore[reportOptionalMemberAccess]
                    except Exception:
                        fig.canvas.draw_idle()  # pyright: ignore[reportOptionalMemberAccess]
            except Exception as e:
                print(f"Display mode change failed: {e}")
            _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
            if is_multi_file:
                _print_file_list(file_data, current_file_idx)
            continue
        elif key == 'e':
            handle_export_figure_command(ec_actions)
            continue
        elif key == 'h':
            # Legend submenu: toggle visibility and move legend in inches relative to canvas center.
            try:
                fig = cast(Any, ax.figure) or fig  # keep existing fig if axes were detached
                if not hasattr(fig, '_ec_legpos_cid') or getattr(fig, '_ec_legpos_cid') is None:
                    def _on_resize_ec(event):
                        try:
                            leg = ax.get_legend()
                            if leg is None or not leg.get_visible():
                                return
                            if _apply_legend_position(fig, ax):
                                fig.canvas.draw_idle()
                        except Exception:
                            pass
                    fig._ec_legpos_cid = fig.canvas.mpl_connect('resize_event', _on_resize_ec)

                def _ec_toggle_legend():
                    try:
                        leg = ax.get_legend()
                        if leg is not None and leg.get_visible():
                            leg.set_visible(False)
                            _set_legend_user_pref(fig, False)
                            _rebuild_legend(ax)
                        else:
                            _set_legend_user_pref(fig, True)
                            _rebuild_legend(ax)
                        fig.canvas.draw_idle()
                    except Exception:
                        pass

                def _ec_apply_legend_pos():
                    _store_legend_title(fig, ax)
                    if not _apply_legend_position(fig, ax):
                        handles, labels, ncol = _legend_handles_labels_ncol(ax)
                        if handles:
                            _legend_no_frame(ax, handles, labels, loc='best', borderaxespad=1.0, title=_get_legend_title(fig), ncol=ncol)
                    fig.canvas.draw_idle()

                run_legend_position_menu(
                    fig=fig,
                    get_legend=ax.get_legend,
                    get_position=lambda: getattr(fig, '_ec_legend_xy_in', (0.0, 0.0)),
                    set_position=lambda xy: setattr(fig, '_ec_legend_xy_in', xy),
                    sanitize_offset=lambda xy: _sanitize_legend_offset(fig, xy),
                    toggle_legend=_ec_toggle_legend,
                    apply_position=_ec_apply_legend_pos,
                    push_state=push_state,
                    safe_input=_safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=_colorize_prompt,
                )
            except Exception:
                pass
            _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
            continue
        elif key == 'p':
            handle_style_command(ec_actions)
            continue
        elif key == 'i':
            handle_import_style_command(ec_actions)
            continue
        elif key == 'l':
            run_ec_line_style_menu(
                fig=fig,
                ax=ax,
                cycle_lines=cycle_lines,
                file_data=file_data,
                current_file_idx=current_file_idx,
                is_multi_file=is_multi_file,
                is_dqdv=is_dqdv,
                print_file_list=_print_file_list,
                iter_cycle_lines=_iter_cycle_lines,
                rebuild_legend=_rebuild_legend,
                apply_stored_smooth_settings=_apply_stored_smooth_settings,
                push_state=push_state,
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
            )
            _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
            continue
        elif key == 'k':
            run_ec_spine_color_menu(
                fig=fig,
                ax=ax,
                tick_state=tick_state,
                apply_spine_color=_apply_spine_color,
                push_state=push_state,
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
            )
            _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
            continue
        elif key == 'r':
            updated_base_ylabel = run_ec_rename_menu(
                fig=fig,
                ax=ax,
                file_data=file_data,
                tick_state=tick_state,
                push_state=push_state,
                rebuild_legend=_rebuild_legend,
                print_file_list=_print_file_list,
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
                ui_position_top_xlabel=_ui_position_top_xlabel,
                ui_position_bottom_xlabel=_ui_position_bottom_xlabel,
                ui_position_left_ylabel=_ui_position_left_ylabel,
                ui_position_right_ylabel=_ui_position_right_ylabel,
            )
            if updated_base_ylabel is not None:
                base_ylabel = updated_base_ylabel
            _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
            continue
        elif key == 'ra':
            run_ec_legend_order_menu(
                fig=fig,
                ax=ax,
                file_data=file_data,
                is_multi_file=is_multi_file,
                print_file_list=_print_file_list,
                rebuild_legend=_rebuild_legend,
                push_state=push_state,
                safe_input=_safe_input,
            )
            _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
            continue
        elif key == 't':
            # Unified WASD: w/a/s/d x 1..5 => spine, ticks, minor, labels, title
            try:
                wasd = getattr(fig, '_ec_wasd_state', None)
                if not isinstance(wasd, dict):
                    wasd = build_wasd_state(
                        get_spine_visible=_get_spine_visible,
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
                    setattr(fig, '_ec_wasd_state', wasd)
                def _apply_wasd(changed_sides=None):
                    assert wasd is not None  # always a dict once this runs
                    # If no changed_sides specified, reposition all sides (for load style, etc.)
                    if changed_sides is None:
                        changed_sides = {'bottom', 'top', 'left', 'right'}
                    
                    # Check if in dual x-axis mode
                    is_dual_xaxis = getattr(fig, '_xaxis_mode', 'capacity') == 'dual'
                    secax = getattr(fig, '_xaxis_secondary', None) if is_dual_xaxis else None
                    
                    apply_wasd_spines(
                        ax,
                        wasd,
                        axes_by_side={'top': secax} if is_dual_xaxis and secax is not None else None,
                    )
                    
                    if is_dual_xaxis and secax is not None:
                        try:
                            apply_wasd_tick_params(ax, wasd, x_sides=('bottom',), y_sides=('left', 'right'))
                            apply_wasd_tick_params(secax, wasd, x_sides=('top',), y_sides=())
                        except Exception:
                            apply_wasd_tick_params(ax, wasd)
                    else:
                        apply_wasd_tick_params(ax, wasd)

                    # Titles
                    # Bottom x-axis label (primary axis)
                    if bool(wasd['bottom']['title']):
                        if hasattr(ax,'_stored_xlabel') and isinstance(ax._stored_xlabel,str) and ax._stored_xlabel:
                            ax.set_xlabel(ax._stored_xlabel)
                            ax.xaxis.label.set_visible(True)
                            _apply_stored_axis_colors(ax)
                    else:
                        if not hasattr(ax,'_stored_xlabel'):
                            try: ax._stored_xlabel = ax.get_xlabel()
                            except Exception: ax._stored_xlabel = ''
                        ax.set_xlabel("")
                        ax.xaxis.label.set_visible(False)
                    
                    # Top x-axis label (secondary axis in dual mode, or primary in normal mode)
                    ax._top_xlabel_on = bool(wasd['top']['title'])
                    if is_dual_xaxis and secax is not None:
                        # Control secondary axis label visibility
                        try:
                            if bool(wasd['top']['title']):
                                secax.xaxis.label.set_visible(True)
                            else:
                                secax.xaxis.label.set_visible(False)
                        except Exception:
                            pass  # Silently ignore if secondary axis is broken
                    if bool(wasd['left']['title']):
                        if hasattr(ax,'_stored_ylabel') and isinstance(ax._stored_ylabel,str) and ax._stored_ylabel:
                            ax.set_ylabel(ax._stored_ylabel)
                            ax.yaxis.label.set_visible(True)
                            _apply_stored_axis_colors(ax)
                    else:
                        if not hasattr(ax,'_stored_ylabel'):
                            try: ax._stored_ylabel = ax.get_ylabel()
                            except Exception: ax._stored_ylabel = ''
                        ax.set_ylabel("")
                        ax.yaxis.label.set_visible(False)
                    ax._right_ylabel_on = bool(wasd['right']['title'])
                    
                    # Only reposition sides that were actually changed
                    # This prevents unnecessary title movement when toggling unrelated elements
                    def _position_top():
                        _ui_position_top_xlabel(ax, fig, tick_state)
                        _apply_stored_axis_colors(ax)

                    def _position_right():
                        _ui_position_right_ylabel(ax, fig, tick_state)
                        _apply_stored_axis_colors(ax)

                    apply_changed_side_title_positions(
                        changed_sides,
                        bottom=lambda: _ui_position_bottom_xlabel(ax, fig, tick_state),
                        top=_position_top,
                        left=lambda: _ui_position_left_ylabel(ax, fig, tick_state),
                        right=_position_right,
                    )
                    try:
                        finalize_spine_colors(fig, ax, tick_state=tick_state)
                    except Exception:
                        pass
                def _sync_tick_state():
                    assert wasd is not None  # always a dict once this runs
                    sync_tick_state_from_wasd(
                        tick_state,
                        wasd,
                        tick_defaults={'top': False, 'bottom': True, 'left': True, 'right': False},
                        label_defaults={'top': False, 'bottom': True, 'left': True, 'right': False},
                    )
                def _draw_spine_menu():
                    try:
                        finalize_spine_colors(fig, ax, tick_state=tick_state)
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
                    colorize_prompt=_colorize_prompt,
                    colorize_inline_commands=_colorize_inline_commands,
                    push_state=push_state,
                    sync_tick_state=_sync_tick_state,
                    apply_wasd=_apply_wasd,
                    draw=_draw_spine_menu,
                    mode_label="electrochemistry axes",
                    back_label="electrochemistry menu",
                    axis_map={'x': ax.xaxis, 'y': ax.yaxis},
                    direction_axes=[ax],
                    length_axes=[ax],
                    title_offset_handler=_title_offset_menu,
                )
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                continue
            except Exception as e:
                print(f"Error in WASD tick visibility menu: {e}")
            _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
            continue
        elif key == 's':
            handle_save_session_command(ec_actions)
            continue
        elif key == 'c':
            run_ec_cycles_menu(
                fig=fig,
                ax=ax,
                cycle_lines=cycle_lines,
                file_data=file_data,
                current_file_idx=current_file_idx,
                all_cycles=all_cycles,
                is_multi_file=is_multi_file,
                is_dqdv=is_dqdv,
                menu_title=menu_title,
                canvas_mode=canvas_mode,
                print_file_list=_print_file_list,
                print_menu=_print_menu,
                colorize_menu=_colorize_menu,
                colorize_inline_commands=_colorize_inline_commands,
                colorize_prompt=_colorize_prompt,
                safe_input=_safe_input,
                push_state=push_state,
                parse_fall_cycles_tokens=_parse_fall_cycles_tokens,
                parse_per_file_cycle_tokens=_parse_per_file_cycle_tokens,
                parse_file_palette_tokens=_parse_file_palette_tokens,
                parse_cycle_tokens=_parse_cycle_tokens,
                set_visible_cycles=_set_visible_cycles,
                apply_colors=_apply_colors,
                apply_curve_linewidth=_apply_curve_linewidth,
                apply_stored_smooth_settings=_apply_stored_smooth_settings,
                apply_display_mode=_apply_display_mode,
                rebuild_legend=_rebuild_legend,
                apply_nice_ticks=_apply_nice_ticks,
            )
            _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
            continue
        elif key == 'a':
            # X-axis submenu: number-of-ions vs capacity (not available in dQdV mode)
            _handle_key_a()
            continue
        elif key == 'f':
            def _draw_font_change():
                try:
                    fig.canvas.draw()
                except Exception:
                    fig.canvas.draw_idle()
            def _apply_ec_font_family(family):
                push_state("font-family")
                _apply_font_family(ax, family)
                _rebuild_legend(ax)
                _draw_font_change()
            def _apply_ec_font_size(size):
                push_state("font-size")
                _apply_font_size(ax, size)
                _rebuild_legend(ax)
                _draw_font_change()
            def _apply_ec_font_weight(weight):
                push_state("font-weight")
                apply_fig_font_weight(fig, _ec_font_artists(ax), weight)
                _rebuild_legend(ax)
                _draw_font_change()
            def _toggle_ec_highlight():
                push_state("font-highlight")
                apply_fig_text_highlight(fig, _ec_font_artists(ax), not get_fig_text_highlight(fig))
                _draw_font_change()
            def _set_ec_hl_fc(fc):
                push_state("font-highlight")
                apply_fig_text_highlight(fig, _ec_font_artists(ax), get_fig_text_highlight(fig), fc=fc)
                _draw_font_change()
            def _set_ec_hl_alpha(alpha):
                push_state("font-highlight")
                apply_fig_text_highlight(fig, _ec_font_artists(ax), get_fig_text_highlight(fig), alpha=alpha)
                _draw_font_change()
            def _set_ec_hl_pad(pad):
                push_state("font-highlight")
                apply_fig_text_highlight(fig, _ec_font_artists(ax), get_fig_text_highlight(fig), pad=pad)
                _draw_font_change()
            run_font_menu(
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
                get_current_family=lambda: plt.rcParams.get('font.sans-serif', [''])[0],
                get_current_size=lambda: mpl.rcParams.get('font.size', None),
                apply_family=_apply_ec_font_family,
                apply_size=_apply_ec_font_size,
                get_current_weight=lambda: get_fig_font_weight(fig),
                apply_weight=_apply_ec_font_weight,
                get_current_highlight=lambda: get_fig_text_highlight(fig),
                get_highlight_style=lambda: get_fig_text_highlight_style(fig),
                apply_highlight_toggle=_toggle_ec_highlight,
                apply_highlight_facecolor=_set_ec_hl_fc,
                apply_highlight_alpha=_set_ec_hl_alpha,
                apply_highlight_pad=_set_ec_hl_pad,
            )
            _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
            continue
        elif key == 'x':
            def _draw_ec_axis_limits():
                _apply_nice_ticks()
                try:
                    leg = ax.get_legend()
                    if leg is not None and leg.get_visible():
                        _apply_legend_position(fig, ax)
                except Exception:
                    pass
                fig.canvas.draw()
            def _auto_x_limits():
                ax.set_xlim(*getattr(ax, '_original_xlim', ax.get_xlim()))
                ax.relim()
                ax.autoscale_view(scalex=True, scaley=False)
            run_axis_limit_menu(
                axis_name="X",
                prompt_name="X",
                get_limits=ax.get_xlim,
                set_limits=lambda lo, hi: ax.set_xlim(lo, hi),
                auto_limits=_auto_x_limits,
                push_state=push_state,
                state_label="x-limits",
                draw=_draw_ec_axis_limits,
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
                normalize_pair=False,
            )
            _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
            continue
        elif key == 'y':
            def _draw_ec_y_limits():
                _apply_nice_ticks()
                try:
                    leg = ax.get_legend()
                    if leg is not None and leg.get_visible():
                        _apply_legend_position(fig, ax)
                except Exception:
                    pass
                fig.canvas.draw()
            def _auto_y_limits():
                ax.set_ylim(*getattr(ax, '_original_ylim', ax.get_ylim()))
                ax.relim()
                ax.autoscale_view(scalex=False, scaley=True)
            run_axis_limit_menu(
                axis_name="Y",
                prompt_name="Y",
                get_limits=ax.get_ylim,
                set_limits=lambda lo, hi: ax.set_ylim(lo, hi),
                auto_limits=_auto_y_limits,
                push_state=push_state,
                state_label="y-limits",
                draw=_draw_ec_y_limits,
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
            )
            _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
            continue
        elif key == 'g':
            if canvas_mode:
                print("Geometry is controlled from the canvas menu (g).")
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                continue
            def _redraw_ec_geometry():
                try:
                    _apply_nice_ticks()
                    fig.canvas.draw()
                except Exception:
                    fig.canvas.draw_idle()
            def _resize_ec_frame():
                push_state("resize-frame")
                try:
                    resize_plot_frame(fig, ax, [], [], type('Args', (), {'stack': False})(), _update_labels)
                except Exception as e:
                    print(f"Error changing plot frame: {e}")
                _redraw_ec_geometry()
            def _resize_ec_canvas():
                push_state("resize-canvas")
                try:
                    resize_canvas(fig, ax)
                except Exception as e:
                    print(f"Error changing canvas: {e}")
                _redraw_ec_geometry()
            run_option_menu(
                prompt="Geom (p/c/q): ",
                options={
                    "p": ("plot frame size", _resize_ec_frame),
                    "c": ("canvas size", _resize_ec_canvas),
                },
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
            )
            _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
            continue
        elif key == 'sm':
            # dQ/dV smoothing utilities (only available in dQdV mode)
            _handle_key_sm()
            continue
        elif key == '2d':
            # dQ/dV → butterfly potential vs cycle heatmap in a new figure; operando-only contour menu
            _handle_key_2d()
            continue
        elif key == 'oe':
            handle_quick_overwrite_figure_command(ec_actions)
            continue
        elif key == 'os':
            handle_quick_overwrite_session_command(ec_actions)
            continue
        elif key in ('ops', 'opsg'):
            handle_quick_overwrite_style_command(ec_actions, include_geometry=(key == 'opsg'))
            continue
        else:
            print("Unknown command.")
            _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)

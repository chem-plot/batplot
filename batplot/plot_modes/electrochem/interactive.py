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
from .overview import run_gc_overview
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
from ..common.line_dash import capture_dash_pattern, clear_dash_pattern, restore_dash_pattern
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
    _visible_cycle_numbers,
    _parse_file_palette_tokens,
    _parse_per_file_cycle_tokens,
    _resolve_palette_alias,
    _set_visible_cycles,
    set_ec_file_visibility,
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
from .dual_axis_menu import run_dual_axis_menu
from .smoothing_menu import _diffcap_clean_series, run_dqdv_smoothing_menu  # noqa: F401 (re-export)
from .undo_state import ec_push_state, ec_restore_state

def _apply_stored_axis_colors(ax, fig=None):
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
        # Dual: prefer SecondaryAxis's own title color (may differ from spine)
        if fig is not None and getattr(fig, '_xaxis_mode', 'capacity') == 'dual':
            sec = getattr(fig, '_xaxis_secondary', None)
            if sec is not None:
                sec_c = (
                    getattr(sec, '_bp_top_title_color', None)
                    or getattr(sec, '_stored_top_xlabel_color', None)
                    or color
                )
                if sec_c:
                    try:
                        sec.xaxis.label.set_color(sec_c)
                        sec._stored_top_xlabel_color = sec_c
                    except Exception:
                        pass
        elif color and fig is not None:
            sec = getattr(fig, '_xaxis_secondary', None)
            if sec is not None:
                try:
                    sec.xaxis.label.set_color(color)
                    sec._stored_top_xlabel_color = color
                except Exception:
                    pass
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
        # Dual ions top: set_spine_side_color syncs SecondaryAxis + primary top.
        is_dual = getattr(fig, "_xaxis_mode", "capacity") == "dual"
        if spine_name == "top" and is_dual and getattr(fig, "_xaxis_secondary", None) is not None:
            from .spine_colors import _apply_secondary_top_spine_color

            _apply_secondary_top_spine_color(fig, color, color)
        else:
            _ui_set_spine_side_color(
                ax, spine_name, color, fig=fig, tick_state=tick_state
            )
        if spine_name == 'top' and not is_dual:
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
    _apply_stored_axis_colors(ax, fig)


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
        """Show/hide a whole file without destroying its cycle selection."""
        set_ec_file_visibility(
            f_entry,
            visible,
            display_mode=getattr(fig, "_ec_display_mode", "both"),
        )

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
    try:
        # GC-only overview (charge/discharge capacity). Hidden for CV/dQdV menus.
        fig._ec_overview_enabled = bool(is_gc and not is_dqdv)
        fig._ec_is_gc = bool(is_gc)
    except Exception:
        pass

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
        # Use shared UI helper for consistent behavior.
        # Dual root cause: tick_state t_ticks/t_labels mean ions SecondaryAxis
        # chrome — applying them to primary draws capacity-scale ghost ticks.
        try:
            from .style import ec_dual_secax, seal_ec_axis_chrome

            if ec_dual_secax(fig) is not None:
                # Apply a/s/d (+ bottom) from tick_state; never primary top.
                ts = dict(tick_state)
                ts['t_ticks'] = False
                ts['t_labels'] = False
                ts['mtx'] = False
                if 'tx' in ts:
                    ts['tx'] = False
                _ui_update_tick_visibility(ax, ts)
                # Seal all sides: dual top → SecondaryAxis; a/s/d stay primary
                seal_ec_axis_chrome(
                    fig, ax, getattr(fig, '_ec_wasd_state', None),
                )
            else:
                _ui_update_tick_visibility(ax, tick_state)
        except Exception:
            try:
                _ui_update_tick_visibility(ax, tick_state)
            except Exception:
                pass
        # Persist on axes (keep real bookkeeping, including dual top flags)
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
            is_dual = getattr(fig, '_xaxis_mode', 'capacity') == 'dual'
            secax = getattr(fig, '_xaxis_secondary', None) if is_dual else None
            if is_dual and secax is not None:
                # Dual top title is SecondaryAxis.xaxis.label — nudge labelpad.
                while True:
                    try:
                        _pad = getattr(secax.xaxis, 'labelpad', 4.0)
                        pad = float(4.0 if _pad is None else _pad)
                    except Exception:
                        pad = 4.0
                    print(f"Dual top title labelpad: {pad:.1f} pts (w=+2, s=-2, 0=reset 4, q=back)")
                    sub = _safe_input(_colorize_prompt("top dual (w/s/0/q): ")).strip().lower()
                    if not sub:
                        continue
                    if sub == 'q':
                        break
                    if sub == '0':
                        pad = 4.0
                    elif sub == 'w':
                        pad += 2.0
                    elif sub == 's':
                        pad -= 2.0
                    else:
                        print("Unknown choice (use w/s/0/q).")
                        continue
                    _ensure_snapshot()
                    try:
                        secax.xaxis.labelpad = pad
                        fig.canvas.draw_idle()
                    except Exception:
                        pass
                return
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
                # Dual top title is SecondaryAxis labelpad — never capacity duplicate
                if getattr(fig, '_xaxis_mode', 'capacity') != 'dual':
                    _ui_position_top_xlabel(ax, fig, tick_state)
                else:
                    try:
                        secax = getattr(fig, '_xaxis_secondary', None)
                        if secax is not None:
                            secax.xaxis.labelpad = 4.0
                    except Exception:
                        pass
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

    def _has_custom_major_locator(axis_obj) -> bool:
        try:
            return isinstance(axis_obj.get_major_locator(), MultipleLocator)
        except Exception:
            return False

    def _apply_nice_ticks():
            try:
                # Only enforce MaxNLocator for linear scales; let Matplotlib defaults handle log/symlog.
                # Never overwrite a custom MultipleLocator from session / t>n.
                if (getattr(ax, 'get_xscale', None) and ax.get_xscale() == 'linear'
                        and not _has_custom_major_locator(ax.xaxis)):
                    ax.xaxis.set_major_locator(MaxNLocator(nbins='auto', steps=[1, 2, 5], min_n_ticks=4))
                if (getattr(ax, 'get_yscale', None) and ax.get_yscale() == 'linear'
                        and not _has_custom_major_locator(ax.yaxis)):
                    ax.yaxis.set_major_locator(MaxNLocator(nbins='auto', steps=[1, 2, 5], min_n_ticks=4))
            except Exception:
                pass
    # Ensure nice ticks on entry and apply initial visibility
    _apply_nice_ticks()
    _update_tick_visibility()
    # Dual top title is SecondaryAxis — never create capacity duplicate artist
    if getattr(fig, '_xaxis_mode', 'capacity') != 'dual':
        _ui_position_top_xlabel(ax, fig, tick_state)
    else:
        try:
            from .style import seal_ec_axis_chrome

            seal_ec_axis_chrome(fig, ax, getattr(fig, '_ec_wasd_state', None))
        except Exception:
            pass
    _ui_position_bottom_xlabel(ax, fig, tick_state)
    _ui_position_left_ylabel(ax, fig, tick_state)
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
        ec_push_state(
            state_history=state_history, fig=fig, ax=ax, tick_state=tick_state,
            cycle_lines=cycle_lines, file_data=file_data, is_multi_file=is_multi_file,
            note=note,
        )

    def pop_undo():
        if state_history:
            state_history.pop()

    def _ensure_ec_wasd():
        """Return fig._ec_wasd_state, building dual-aware defaults if missing."""
        wasd = getattr(fig, '_ec_wasd_state', None)
        if isinstance(wasd, dict):
            return wasd
        from .style import dual_top_spine_visible, dual_top_title_visible

        _is_dual_init = getattr(fig, '_xaxis_mode', 'capacity') == 'dual'
        wasd = build_wasd_state(
            get_spine_visible=(
                (lambda side: dual_top_spine_visible(fig, ax) if side == 'top'
                 else _get_spine_visible(side))
                if _is_dual_init else _get_spine_visible
            ),
            tick_state=tick_state,
            title_visible={
                'top': (
                    dual_top_title_visible(fig, ax)
                    if _is_dual_init
                    else bool(getattr(ax, '_top_xlabel_on', False))
                ),
                'bottom': bool(ax.xaxis.label.get_visible()),
                'left': bool(ax.yaxis.label.get_visible()),
                'right': bool(getattr(ax, '_right_ylabel_on', False)),
            },
            tick_defaults={'top': False, 'bottom': True, 'left': True, 'right': False},
            label_defaults={'top': False, 'bottom': True, 'left': True, 'right': False},
        )
        setattr(fig, '_ec_wasd_state', wasd)
        return wasd

    def _apply_wasd(changed_sides=None):
        """Menu-scoped WASD apply for all sides (also used by undo)."""
        from .style import apply_ec_wasd_chrome, ec_dual_secax

        wasd = _ensure_ec_wasd()
        if changed_sides is None:
            changed_sides = {'bottom', 'top', 'left', 'right'}

        apply_ec_wasd_chrome(fig, ax, wasd, apply_titles=True)
        try:
            _apply_stored_axis_colors(ax, fig)
        except Exception:
            pass

        is_dual_xaxis = ec_dual_secax(fig) is not None

        def _position_top():
            if is_dual_xaxis:
                return
            _ui_position_top_xlabel(ax, fig, tick_state)
            _apply_stored_axis_colors(ax, fig)

        def _position_right():
            _ui_position_right_ylabel(ax, fig, tick_state)
            _apply_stored_axis_colors(ax, fig)

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
        wasd = _ensure_ec_wasd()
        sync_tick_state_from_wasd(
            tick_state,
            wasd,
            tick_defaults={'top': False, 'bottom': True, 'left': True, 'right': False},
            label_defaults={'top': False, 'bottom': True, 'left': True, 'right': False},
        )
        try:
            ax._saved_tick_state = dict(tick_state)
        except Exception:
            pass

    def restore_state():
        ec_restore_state(
            state_history=state_history, fig=fig, ax=ax, tick_state=tick_state,
            cycle_lines=cycle_lines, file_data=file_data, is_multi_file=is_multi_file,
            apply_nice_ticks=_apply_nice_ticks,
            apply_wasd_state=lambda: (_sync_tick_state(), _apply_wasd()),
            update_tick_visibility=_update_tick_visibility,
            apply_display_mode=_apply_display_mode,
            apply_font_size=_apply_font_size,
            apply_font_family=_apply_font_family,
            ec_font_artists=_ec_font_artists,
        )
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
        run_dqdv_smoothing_menu(
            fig=fig, cycle_lines=cycle_lines, file_data=file_data,
            current_file_idx=current_file_idx, all_cycles=all_cycles,
            is_dqdv=is_dqdv, is_multi_file=is_multi_file,
            menu_title=menu_title, canvas_mode=canvas_mode,
            print_menu=_print_menu, print_file_list=_print_file_list,
            push_state=push_state, safe_input=_safe_input,
            colorize_menu=_colorize_menu, colorize_prompt=_colorize_prompt,
        )

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
            # Snapshot before companion mutates fig._dqdv_2d_snapshot (b undoes it).
            try:
                push_state("dqdv-2d")
            except Exception:
                pass
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
        run_dual_axis_menu(
            fig=fig, ax=ax, all_cycles=all_cycles, is_dqdv=is_dqdv,
            is_multi_file=is_multi_file, menu_title=menu_title, canvas_mode=canvas_mode,
            print_menu=_print_menu, push_state=push_state,
            apply_nice_ticks=_apply_nice_ticks, safe_input=_safe_input,
            colorize_menu=_colorize_menu, colorize_prompt=_colorize_prompt,
            restore_state=restore_state,
        )

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
                    print("  " + _colorize_menu(
                        "Which cycles are shown & colors: main menu c — "
                        "three color ways: (1) cycles+last palette digit "
                        "(2-30 1), (2) N:color, (3) all <palette>"
                    ))
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

                def _ec_rearrange_legend():
                    run_ec_legend_order_menu(
                        fig=fig,
                        ax=ax,
                        file_data=file_data,
                        is_multi_file=is_multi_file,
                        print_file_list=_print_file_list,
                        rebuild_legend=_rebuild_legend,
                        push_state=push_state,
                        safe_input=_safe_input,
                        restore_state=restore_state,
                    )

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
                    rearrange_legend=_ec_rearrange_legend if is_multi_file else None,
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
        elif key == 't':
            # Unified WASD: w/a/s/d x 1..5 => spine, ticks, minor, labels, title
            try:
                wasd = _ensure_ec_wasd()

                def _ec_live_dual_axes():
                    from .style import ec_dual_secax
                    out = [ax]
                    sec = ec_dual_secax(fig)
                    if sec is not None:
                        out.append(sec)
                    return out

                def _after_locator_edit():
                    from .style import sync_ec_dual_secax_x_locators
                    try:
                        # Persist bottom spacing for dual restore
                        maj = ax.xaxis.get_major_locator()
                        from matplotlib.ticker import MultipleLocator  # type: ignore[import-untyped]
                        if isinstance(maj, MultipleLocator):
                            try:
                                fig._ec_x_tick_spacing = float(maj._edge.step)  # type: ignore[attr-defined]
                            except Exception:
                                pass
                        sync_ec_dual_secax_x_locators(
                            fig, ax, getattr(fig, '_ec_wasd_state', None),
                        )
                    except Exception:
                        pass

                def _draw_spine_menu():
                    from .style import reseal_ec_chrome
                    try:
                        reseal_ec_chrome(
                            fig, ax, wasd=getattr(fig, '_ec_wasd_state', None),
                            tick_state=tick_state, apply_titles=True,
                        )
                    except Exception:
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
                    direction_axes=_ec_live_dual_axes(),
                    length_axes=_ec_live_dual_axes(),
                    direction_axes_provider=_ec_live_dual_axes,
                    length_axes_provider=_ec_live_dual_axes,
                    after_locator_edit=_after_locator_edit,
                    title_offset_handler=_title_offset_menu,
                    on_quit=lambda: setattr(ax, '_saved_tick_state', dict(tick_state)),
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
                highlight_fig=fig,
            )
            _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
            continue
        elif key == 'x':
            def _draw_ec_axis_limits():
                _apply_nice_ticks()
                try:
                    from .style import reseal_ec_chrome
                    reseal_ec_chrome(fig, ax, tick_state=tick_state)
                except Exception:
                    pass
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
                    from .style import reseal_ec_chrome
                    reseal_ec_chrome(fig, ax, tick_state=tick_state)
                except Exception:
                    pass
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
                    try:
                        from .style import reseal_ec_chrome
                        reseal_ec_chrome(fig, ax, tick_state=tick_state)
                    except Exception:
                        pass
                    fig.canvas.draw()
                except Exception:
                    fig.canvas.draw_idle()
            def _resize_ec_frame():
                try:
                    resize_plot_frame(
                        fig, ax, [], [], type('Args', (), {'stack': False})(), _update_labels,
                        on_before_change=lambda: push_state("resize-frame"),
                    )
                except Exception as e:
                    print(f"Error changing plot frame: {e}")
                _redraw_ec_geometry()
            def _resize_ec_canvas():
                try:
                    resize_canvas(
                        fig, ax,
                        on_before_change=lambda: push_state("resize-canvas"),
                    )
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
        elif key == 'o':
            if is_dqdv or not is_gc:
                print("Overview is only available in GC mode.")
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                continue
            try:
                run_gc_overview(
                    cycle_lines=cycle_lines,
                    file_data=file_data,
                    fig=fig,
                    safe_input=_safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=_colorize_prompt,
                    print_file_list=_print_file_list if is_multi_file else None,
                    include_hidden=False,
                )
            except Exception as e:
                print(f"Error in overview: {e}")
            _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
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

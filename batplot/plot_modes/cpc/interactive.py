"""Interactive menu for Capacity-Per-Cycle (CPC) plots.

This module provides the interactive menu for CPC (Capacity Per Cycle) mode.
CPC plots show how battery capacity changes over multiple cycles, displaying:
- Charge capacity vs cycle number
- Discharge capacity vs cycle number  
- Coulombic efficiency vs cycle number

HOW CPC MODE WORKS:
------------------
CPC mode reads battery cycling data and extracts:
1. Maximum charge capacity for each cycle
2. Maximum discharge capacity for each cycle
3. Coulombic efficiency = (discharge_capacity / charge_capacity) × 100%

These values are plotted as scatter points (one point per cycle), allowing you
to see capacity fade and efficiency trends over the battery's lifetime.

INTERACTIVE FEATURES:
--------------------
The interactive menu allows you to:
- Customize colors for each file (charge, discharge, efficiency)
- Adjust line/marker styles and sizes
- Show/hide individual files
- Modify axis ranges and labels
- Export style files (.bpcfg) for reuse
- Save/load sessions

MULTI-FILE SUPPORT:
-----------------
CPC mode can plot multiple files simultaneously, each with its own color scheme.
This is useful for comparing different battery cells, materials, or conditions.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import json
import os
import sys
import contextlib
from io import StringIO
import random as _random
import re
import traceback

import matplotlib.pyplot as plt  # type: ignore[import]
from matplotlib.ticker import AutoMinorLocator, NullFormatter, NullLocator, MultipleLocator, AutoLocator  # type: ignore[import]
from matplotlib.colors import to_hex  # type: ignore[import]
import numpy as np  # type: ignore[import]

from ...ui import (
    set_spine_side_color as _ui_set_spine_side_color,
    resize_plot_frame, resize_canvas,
    update_tick_visibility as _ui_update_tick_visibility,
    position_top_xlabel as _ui_position_top_xlabel,
    position_right_ylabel as _ui_position_right_ylabel,
    position_bottom_xlabel as _ui_position_bottom_xlabel,
    position_left_ylabel as _ui_position_left_ylabel,
    capture_axis_tick_locators,
    restore_axis_tick_locators,
)
from .menu import _colorize_menu, build_cpc_menu_columns, print_cpc_menu as _print_menu
from ...utils import (
    choose_save_path,
    choose_style_file,
    list_files_in_subdirectory,
    get_organized_path,
    natural_sort_key,
    ensure_exact_case_filename,
)
from ...color_utils import resolve_color_token
from .session import dump_cpc_session
from .colors import _generate_similar_color, run_cpc_color_menu
from .labels import run_cpc_rename_menu
from ..common.terminal import (
    colorize_inline_commands as _colorize_inline_commands,
    colorize_prompt as _colorize_prompt,
    safe_input as _safe_input,
)
from ..common.files import format_file_timestamp as _format_file_timestamp
from ..common.fonts import (
    apply_font_family_to_artists,
    apply_font_size_to_artists,
    axis_text_artists,
    legend_text_artists,
    set_font_family_defaults,
    set_font_size_default,
)
from ..common.menus import run_axis_limit_menu, run_dispatch_menu, run_font_menu, run_legend_position_menu, run_option_menu
from ..common.sources import file_data_source_paths
from ..common.spines import (
    apply_changed_side_title_positions,
    apply_frame_and_tick_widths,
    apply_wasd_spines,
    apply_wasd_tick_params,
    current_tick_width,
    parse_frame_tick_widths,
    run_spine_tick_menu,
    sync_tick_state_from_wasd,
)
from .legend import (
    _build_compact_cpc_legend,
    _color_of,
    _coerce_legend_color,
    _get_legend_title,
    _legend_no_frame,
    _normalize_spine_color,
    _reapply_cpc_legend_text_colors,
    _rebuild_legend,
    _sanitize_legend_offset,
    _visible_handles_labels,
)
from .snapshots import (
    _apply_cpc_geometry_snapshot,
    _get_geometry_snapshot,
    push_cpc_state,
    restore_cpc_state,
)
from .actions import (
    CpcActionContext,
    handle_figure_export,
    handle_quick_overwrite_figure,
    handle_quick_overwrite_session,
    handle_quick_overwrite_style,
    handle_save_session,
    handle_style_export,
    handle_style_import,
    handle_undo,
)


def _collect_file_paths(file_data) -> list:
    """Extract absolute file paths from file_data structures."""
    return file_data_source_paths(file_data)


def _get_current_file_artists(file_data, current_idx):
    """Get the scatter artists for the currently selected file."""
    if not file_data or current_idx >= len(file_data):
        return None, None, None
    file_info = file_data[current_idx]
    return file_info['sc_charge'], file_info['sc_discharge'], file_info['sc_eff']


def _print_file_list(file_data, current_idx):
    """Print list of files with current selection highlighted."""
    print("\n=== Files ===")
    for i, f in enumerate(file_data):
        marker = "→" if i == current_idx else " "
        vis = "✓" if f.get('visible', True) else "✗"
        print(f"{marker} {i+1}. [{vis}] {f['filename']}")
    print()


def _is_hollow_marker(artist) -> bool:
    """Check if a scatter artist has hollow markers (facecolor='none' or transparent)."""
    try:
        if hasattr(artist, 'get_facecolors'):
            face_arr = artist.get_facecolors()
            edge_arr = artist.get_edgecolors() if hasattr(artist, 'get_edgecolors') else None
            # facecolors='none' returns empty array; treat as hollow
            if face_arr is None or len(face_arr) == 0:
                return edge_arr is not None and len(edge_arr) > 0
            # Check if facecolor is fully transparent (alpha == 0 or very low)
            fc = face_arr[0]
            if len(fc) >= 4 and (fc[3] == 0 or (hasattr(fc[3], '__float__') and float(fc[3]) < 0.01)):
                return True
    except Exception:
        pass
    return False


def _style_snapshot(fig, ax, ax2, sc_charge, sc_discharge, sc_eff, file_data=None) -> Dict:
    try:
        fig_w, fig_h = map(float, fig.get_size_inches())
    except Exception:
        fig_w = fig_h = None

    def _color_of(artist) -> Optional[str]:
        """Return a representative color for a scatter/artist.
        
        For hollow markers (facecolor='none'), fall back to edgecolor so that
        style snapshots still capture the intended color.
        """
        try:
            # Prefer explicit color if available
            if hasattr(artist, 'get_color'):
                c = artist.get_color()
                # Normalize to a single hex/string value
                if isinstance(c, str):
                    return c
                if isinstance(c, (list, tuple)) and c:
                    return to_hex(c[0])
                return None
            # Fall back to facecolors / edgecolors for scatter
            face_arr = None
            edge_arr = None
            if hasattr(artist, 'get_facecolors'):
                face_arr = artist.get_facecolors()
            if hasattr(artist, 'get_edgecolors'):
                edge_arr = artist.get_edgecolors()
            # If facecolor is 'none' or empty, use edgecolor instead
            if face_arr is not None and len(face_arr):
                # Some backends use fully transparent facecolor for 'none'
                fc = face_arr[0]
                try:
                    if fc[3] > 0:
                        return to_hex(fc)
                except Exception:
                    return to_hex(fc)
            if edge_arr is not None and len(edge_arr):
                return to_hex(edge_arr[0])
        except Exception:
            pass
        return None

    fam = plt.rcParams.get('font.sans-serif', [''])
    fam0 = fam[0] if fam else ''
    fsize = plt.rcParams.get('font.size', None)
    mathtext_fs = plt.rcParams.get('mathtext.fontset', 'dejavusans')
    # Tick widths helper
    def _tick_width(axis_obj, which: str):
        try:
            tick_kw = axis_obj._major_tick_kw if which == 'major' else axis_obj._minor_tick_kw
            width = tick_kw.get('width')
            if width is None:
                axis_name = getattr(axis_obj, 'axis_name', 'x')
                rc_key = f"{axis_name}tick.{which}.width"
                width = plt.rcParams.get(rc_key)
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

    def _label_visible(lbl):
        try:
            return bool(lbl.get_visible()) and bool(lbl.get_text())
        except Exception:
            return bool(lbl.get_text()) if hasattr(lbl, 'get_text') else False

    # Current tick visibility (prefer persisted WASD state when available)
    tick_vis = {
        'bx': True, 'tx': False, 'ly': True, 'ry': True,
        'mbx': False, 'mtx': False, 'mly': False, 'mry': False,
    }
    try:
        wasd_from_fig = getattr(fig, '_cpc_wasd_state', None)
        if isinstance(wasd_from_fig, dict) and wasd_from_fig:
            # Use stored state (authoritative)
            tick_vis['bx'] = bool(wasd_from_fig.get('bottom', {}).get('labels', True))
            tick_vis['tx'] = bool(wasd_from_fig.get('top', {}).get('labels', False))
            tick_vis['ly'] = bool(wasd_from_fig.get('left', {}).get('labels', True))
            tick_vis['ry'] = bool(wasd_from_fig.get('right', {}).get('labels', True))
            tick_vis['mbx'] = bool(wasd_from_fig.get('bottom', {}).get('minor', False))
            tick_vis['mtx'] = bool(wasd_from_fig.get('top', {}).get('minor', False))
            tick_vis['mly'] = bool(wasd_from_fig.get('left', {}).get('minor', False))
            tick_vis['mry'] = bool(wasd_from_fig.get('right', {}).get('minor', False))
        else:
            # Infer from current axes state
            tick_vis['bx'] = any(lbl.get_visible() for lbl in ax.get_xticklabels())
            tick_vis['tx'] = False  # CPC doesn't duplicate top labels by default
            tick_vis['ly'] = any(lbl.get_visible() for lbl in ax.get_yticklabels())
            tick_vis['ry'] = any(lbl.get_visible() for lbl in ax2.get_yticklabels())
    except Exception:
        pass

    # Plot frame size
    ax_bbox = ax.get_position()
    frame_w_in = ax_bbox.width * fig_w if fig_w else None
    frame_h_in = ax_bbox.height * fig_h if fig_h else None

    # Build WASD-style state (20 parameters: 4 sides × 5 properties)
    # CPC: bottom/top are X-axis, left is primary Y (capacity), right is twin Y (efficiency)
    def _get_spine_visible(ax_obj, which: str) -> bool:
        sp = ax_obj.spines.get(which)
        try:
            return bool(sp.get_visible()) if sp is not None else False
        except Exception:
            return False
    
    wasd_state = getattr(fig, '_cpc_wasd_state', None)
    if not isinstance(wasd_state, dict) or not wasd_state:
        wasd_state = {
            'bottom': {
                'spine': _get_spine_visible(ax, 'bottom'),
                'ticks': bool(tick_vis.get('bx', True)),
                'minor': bool(tick_vis.get('mbx', False)),
                'labels': bool(tick_vis.get('bx', True)),  # bottom x labels
                'title': bool(ax.get_xlabel())  # bottom x title
            },
            'top': {
                'spine': _get_spine_visible(ax, 'top'),
                'ticks': bool(tick_vis.get('tx', False)),
                'minor': bool(tick_vis.get('mtx', False)),
                'labels': bool(tick_vis.get('tx', False)),
                'title': bool(getattr(ax, '_top_xlabel_text', None) and getattr(ax._top_xlabel_text, 'get_visible', lambda: False)())
            },
            'left': {
                'spine': _get_spine_visible(ax, 'left'),
                'ticks': bool(tick_vis.get('ly', True)),
                'minor': bool(tick_vis.get('mly', False)),
                'labels': bool(tick_vis.get('ly', True)),  # left y labels (capacity)
                'title': _label_visible(ax.yaxis.label)  # left y title
            },
            'right': {
                'spine': _get_spine_visible(ax2, 'right'),
                'ticks': bool(tick_vis.get('ry', True)),
                'minor': bool(tick_vis.get('mry', False)),
                'labels': bool(tick_vis.get('ry', True)),  # right y labels (efficiency)
                'title': _label_visible(ax2.yaxis.label)  # right y title respects visibility
            },
        }

    # Capture legend state
    legend_visible = False
    legend_xy_in = None
    try:
        leg = ax.get_legend() or ax2.get_legend()
        if leg is not None:
            legend_visible = leg.get_visible()
            # Get legend position stored in figure attribute
            legend_xy_in = getattr(fig, '_cpc_legend_xy_in', None)
    except Exception:
        pass

    # Grid state
    grid_enabled = False
    try:
        # Check if grid is currently on by looking at gridline visibility
        for line in ax.get_xgridlines() + ax.get_ygridlines():
            if line.get_visible():
                grid_enabled = True
                break
    except Exception:
        grid_enabled = ax.xaxis._gridOnMajor if hasattr(ax.xaxis, '_gridOnMajor') else False

    cfg = {
        'kind': 'cpc_style',
        'version': 2,
        'figure': {
            'canvas_size': [fig_w, fig_h],
            'frame_size': [frame_w_in, frame_h_in],
            'axes_fraction': [ax_bbox.x0, ax_bbox.y0, ax_bbox.width, ax_bbox.height]
        },
        # Track whether data axes were swapped via --ro when this style was saved
        'ro_active': bool(getattr(fig, '_ro_active', False)),
        'font': {'family': fam0, 'size': fsize, 'mathtext_fontset': mathtext_fs},
        'legend': {
            'visible': legend_visible,
            'position_inches': legend_xy_in,  # [x, y] offset from canvas center in inches
            'title': _get_legend_title(fig),
            'single_file_effective': (
                bool(getattr(fig, '_cpc_legend_single_file_effective', False)) or
                (file_data and len(file_data) > 1 and sum(1 for f in file_data if f.get('visible', True)) == 1)
            ),
        },
        'ticks': {
            'widths': {
                'x_major': _tick_width(ax.xaxis, 'major'),
                'x_minor': _tick_width(ax.xaxis, 'minor'),
                'ly_major': _tick_width(ax.yaxis, 'major'),
                'ly_minor': _tick_width(ax.yaxis, 'minor'),
                'ry_major': _tick_width(ax2.yaxis, 'major'),
                'ry_minor': _tick_width(ax2.yaxis, 'minor'),
            },
            'lengths': dict(getattr(fig, '_tick_lengths', {'major': None, 'minor': None})),
            'direction': getattr(fig, '_tick_direction', 'out'),
            'spacing': {
                **capture_axis_tick_locators(ax.xaxis, 'x'),
                **capture_axis_tick_locators(ax.yaxis, 'y'),
                **capture_axis_tick_locators(ax2.yaxis, 'ry'),
            },
        },
        'grid': grid_enabled,
        'wasd_state': wasd_state,
        'spines': {
            'bottom': {'linewidth': ax.spines.get('bottom').get_linewidth() if ax.spines.get('bottom') else None,
                       'visible': ax.spines.get('bottom').get_visible() if ax.spines.get('bottom') else None,
                       'color': ax.spines.get('bottom').get_edgecolor() if ax.spines.get('bottom') else None},
            'top':    {'linewidth': ax.spines.get('top').get_linewidth() if ax.spines.get('top') else None,
                       'visible': ax.spines.get('top').get_visible() if ax.spines.get('top') else None,
                       'color': ax.spines.get('top').get_edgecolor() if ax.spines.get('top') else None},
            'left':   {'linewidth': ax.spines.get('left').get_linewidth() if ax.spines.get('left') else None,
                       'visible': ax.spines.get('left').get_visible() if ax.spines.get('left') else None,
                       'color': ax.spines.get('left').get_edgecolor() if ax.spines.get('left') else None},
            'right':  {'linewidth': ax2.spines.get('right').get_linewidth() if ax2.spines.get('right') else None,
                       'visible': ax2.spines.get('right').get_visible() if ax2.spines.get('right') else None,
                       'color': ax2.spines.get('right').get_edgecolor() if ax2.spines.get('right') else None},
        },
        'spine_colors_auto': getattr(fig, '_cpc_spine_auto', False),
        'spine_colors': dict(getattr(fig, '_cpc_spine_colors', {})),
        'display_mode': getattr(fig, '_cpc_display_mode', 'both'),
        'labelpads': {
            'x': getattr(ax.xaxis, 'labelpad', None),
            'ly': getattr(ax.yaxis, 'labelpad', None),  # left y-axis (capacity)
            'ry': getattr(ax2.yaxis, 'labelpad', None),  # right y-axis (efficiency)
        },
        'title_offsets': {
            'top_y': float(getattr(ax, '_top_xlabel_manual_offset_y_pts', 0.0) or 0.0),
            'top_x': float(getattr(ax, '_top_xlabel_manual_offset_x_pts', 0.0) or 0.0),
            'bottom_y': float(getattr(ax, '_bottom_xlabel_manual_offset_y_pts', 0.0) or 0.0),
            'left_x': float(getattr(ax, '_left_ylabel_manual_offset_x_pts', 0.0) or 0.0),
            'right_x': float(getattr(ax2, '_right_ylabel_manual_offset_x_pts', 0.0) or 0.0),
            'right_y': float(getattr(ax2, '_right_ylabel_manual_offset_y_pts', 0.0) or 0.0),
        },
        'series': {
            'charge': {
                'color': _color_of(sc_charge),
                'marker': getattr(sc_charge, 'get_marker', lambda: 'o')(),
                'markersize': float(getattr(sc_charge, 'get_sizes', lambda: [32])()[0]) if hasattr(sc_charge, 'get_sizes') else 32.0,
                'alpha': float(sc_charge.get_alpha()) if sc_charge.get_alpha() is not None else 1.0,
                'hollow': _is_hollow_marker(sc_charge),
                'visible': bool(getattr(sc_charge, 'get_visible', lambda: True)()),
            },
            'discharge': {
                'color': _color_of(sc_discharge),
                'marker': getattr(sc_discharge, 'get_marker', lambda: 's')(),
                'markersize': float(getattr(sc_discharge, 'get_sizes', lambda: [32])()[0]) if hasattr(sc_discharge, 'get_sizes') else 32.0,
                'alpha': float(sc_discharge.get_alpha()) if sc_discharge.get_alpha() is not None else 1.0,
                'hollow': _is_hollow_marker(sc_discharge),
                'visible': bool(getattr(sc_discharge, 'get_visible', lambda: True)()),
            },
            'efficiency': {
                'color': _color_of(sc_eff) or '#2ca02c',
                'marker': getattr(sc_eff, 'get_marker', lambda: '^')(),
                'markersize': float(getattr(sc_eff, 'get_sizes', lambda: [40])()[0]) if hasattr(sc_eff, 'get_sizes') else 40.0,
                'alpha': float(sc_eff.get_alpha()) if sc_eff.get_alpha() is not None else 1.0,
                'visible': bool(getattr(sc_eff, 'get_visible', lambda: True)()),
                'hollow': _is_hollow_marker(sc_eff),
                'offsets': (sc_eff.get_offsets().tolist() if hasattr(sc_eff, 'get_offsets') and sc_eff.get_offsets().size else None),
            }
        }
    }
    
    # Add multi-file data if available
    if file_data and isinstance(file_data, list) and len(file_data) > 0:
        multi_files = []
        for f in file_data:
            sc_chg = f.get('sc_charge')
            sc_dchg = f.get('sc_discharge')
            sc_eff = f.get('sc_eff')
            file_info = {
                'filename': f.get('filename', 'unknown'),
                'visible': f.get('visible', True),
                'charge_visible': bool(getattr(sc_chg, 'get_visible', lambda: True)()) if sc_chg else True,
                'discharge_visible': bool(getattr(sc_dchg, 'get_visible', lambda: True)()) if sc_dchg else True,
                'charge_color': _color_of(sc_chg),
                'charge_marker': getattr(sc_chg, 'get_marker', lambda: 'o')() if sc_chg else 'o',
                'charge_hollow': _is_hollow_marker(sc_chg) if sc_chg else False,
                'discharge_color': _color_of(sc_dchg),
                'discharge_marker': getattr(sc_dchg, 'get_marker', lambda: 's')() if sc_dchg else 's',
                'discharge_hollow': _is_hollow_marker(sc_dchg) if sc_dchg else False,
                'efficiency_color': _color_of(sc_eff),
                'efficiency_marker': getattr(sc_eff, 'get_marker', lambda: '^')() if sc_eff else '^',
                'efficiency_hollow': _is_hollow_marker(sc_eff) if sc_eff else False,
                'efficiency_offsets': (sc_eff.get_offsets().tolist() if sc_eff and hasattr(sc_eff, 'get_offsets') and sc_eff.get_offsets().size else None),
            }
            # Save legend labels
            try:
                sc_chg = f.get('sc_charge')
                sc_dchg = f.get('sc_discharge')
                sc_eff = f.get('sc_eff')
                if sc_chg and hasattr(sc_chg, 'get_label'):
                    file_info['charge_label'] = sc_chg.get_label() or ''
                if sc_dchg and hasattr(sc_dchg, 'get_label'):
                    file_info['discharge_label'] = sc_dchg.get_label() or ''
                if sc_eff and hasattr(sc_eff, 'get_label'):
                    file_info['efficiency_label'] = sc_eff.get_label() or ''
            except Exception:
                pass
            multi_files.append(file_info)
        cfg['multi_files'] = multi_files
    else:
        # Single file mode: save legend labels
        try:
            cfg['series']['charge']['label'] = sc_charge.get_label() if hasattr(sc_charge, 'get_label') else ''
            cfg['series']['discharge']['label'] = sc_discharge.get_label() if hasattr(sc_discharge, 'get_label') else ''
            cfg['series']['efficiency']['label'] = sc_eff.get_label() if hasattr(sc_eff, 'get_label') else ''
        except Exception:
            pass
    
    return cfg

def _apply_style(fig, ax, ax2: Any, sc_charge, sc_discharge, sc_eff, cfg: Dict, file_data: Optional[List[Dict]] = None):
    """Apply style configuration to CPC plot.
    
    Args:
        fig, ax, ax2: Matplotlib figure and axes
        sc_charge, sc_discharge, sc_eff: Primary/selected file scatter artists
        cfg: Style configuration dict
        file_data: Optional list of file dicts for multi-file mode
    """
    is_multi_file = file_data is not None and len(file_data) > 1
    tick_state: Dict[str, bool] = {
        'bx': True, 'tx': False, 'ly': True, 'ry': True,
        'b_ticks': True, 't_ticks': False, 'l_ticks': True, 'r_ticks': True,
        'b_labels': True, 't_labels': False, 'l_labels': True, 'r_labels': True,
        'mbx': False, 'mtx': False, 'mly': False, 'mry': False,
    }

    def _set_spine_color(spine_name: str, color):
        if not hasattr(fig, '_cpc_spine_colors') or not isinstance(getattr(fig, '_cpc_spine_colors', None), dict):
            fig._cpc_spine_colors = {}
        color = _normalize_spine_color(color)
        if color is None:
            return
        fig._cpc_spine_colors[spine_name] = color
        axes_map = {
            'top': [ax, ax2],
            'bottom': [ax, ax2],
            'left': [ax],
            'right': [ax2],
        }
        for curr_ax in axes_map.get(spine_name, [ax, ax2]):
            if curr_ax is None or spine_name not in curr_ax.spines:
                continue
            try:
                _ui_set_spine_side_color(curr_ax, spine_name, color, fig=fig)
            except Exception:
                pass

    def _apply_legend_position():
        try:
            _rebuild_legend(ax, ax2, file_data, preserve_position=True)
        except Exception:
            pass

    # Store multi-file flag on figure so the menu can hide/show multi-file commands correctly
    try:
        fig._cpc_is_multi_file = bool(is_multi_file)
    except Exception:
        pass

    # Apply display_mode first if present (charge/discharge visibility)
    dm = cfg.get('display_mode')
    if dm in ('charge', 'discharge', 'both'):
        try:
            fig._cpc_display_mode = dm
            for f in (file_data or []):
                sc_c = f.get('sc_charge')
                sc_d = f.get('sc_discharge')
                if sc_c is not None:
                    sc_c.set_visible(dm in ('both', 'charge'))
                if sc_d is not None:
                    sc_d.set_visible(dm in ('both', 'discharge'))
        except Exception:
            pass
    elif file_data and not is_multi_file:
        # Single-file: apply from series if not using display_mode
        pass  # Handled below in series block
    
    # Save current labelpad values BEFORE any style changes
    saved_xlabelpad = None
    saved_ylabelpad = None
    saved_rylabelpad = None
    try:
        saved_xlabelpad = getattr(ax.xaxis, 'labelpad', None)
    except Exception:
        pass
    try:
        saved_ylabelpad = getattr(ax.yaxis, 'labelpad', None)
    except Exception:
        pass
    try:
        saved_rylabelpad = getattr(getattr(ax2, 'yaxis', None), 'labelpad', None)
    except Exception:
        pass
    
    def _apply_font_config():
        try:
            font = cfg.get('font', {})
            fam = font.get('family')
            size = font.get('size')
            mathtext_fs = font.get('mathtext_fontset')
            # Restore mathtext.fontset first (if explicitly saved)
            if mathtext_fs:
                try:
                    plt.rcParams['mathtext.fontset'] = mathtext_fs
                except Exception:
                    pass
            if fam:
                plt.rcParams['font.family'] = 'sans-serif'
                plt.rcParams['font.sans-serif'] = [fam, 'DejaVu Sans', 'Arial', 'Helvetica']
                # Set mathtext.fontset to match font family
                lf = fam.lower()
                if any(k in lf for k in ('stix', 'times', 'roman')):
                    plt.rcParams['mathtext.fontset'] = 'stix'
                else:
                    plt.rcParams['mathtext.fontset'] = 'dejavusans'
            if size is not None:
                plt.rcParams['font.size'] = float(size)
            # Apply to current axes tick labels and duplicate artists, if present
            if fam or size is not None:
                fam0 = fam if fam else None
                sz = float(size) if size is not None else None
                for a in (ax, ax2):
                    try:
                        if sz is not None:
                            a.xaxis.label.set_size(sz); a.yaxis.label.set_size(sz)
                        if fam0:
                            a.xaxis.label.set_family(fam0); a.yaxis.label.set_family(fam0)
                    except Exception:
                        pass
                    try:
                        labels = a.get_xticklabels() + a.get_yticklabels()
                        for t in labels:
                            if sz is not None: t.set_size(sz)
                            if fam0: t.set_family(fam0)
                    except Exception:
                        pass
                    # Top/right tick labels (label2)
                    try:
                        for t in a.xaxis.get_major_ticks():
                            if hasattr(t, 'label2'):
                                if sz is not None: t.label2.set_size(sz)
                                if fam0: t.label2.set_family(fam0)
                        for t in a.yaxis.get_major_ticks():
                            if hasattr(t, 'label2'):
                                if sz is not None: t.label2.set_size(sz)
                                if fam0: t.label2.set_family(fam0)
                    except Exception:
                        pass
                try:
                    art = getattr(ax, '_top_xlabel_artist', None)
                    if art is not None:
                        if sz is not None: art.set_fontsize(sz)
                        if fam0: art.set_fontfamily(fam0)
                except Exception:
                    pass
                try:
                    art = getattr(ax, '_right_ylabel_artist', None)
                    if art is not None:
                        if sz is not None: art.set_fontsize(sz)
                        if fam0: art.set_fontfamily(fam0)
                except Exception:
                    pass
        except Exception:
            pass
    _apply_font_config()

    # Apply canvas and frame size (from 'g' command: plot frame and canvas)
    try:
        fig_cfg = cfg.get('figure', {})
        # Get axes_fraction BEFORE changing canvas size (to preserve exact position)
        axes_frac = fig_cfg.get('axes_fraction')
        frame_size = fig_cfg.get('frame_size')
        
        canvas_size = fig_cfg.get('canvas_size')
        if canvas_size and isinstance(canvas_size, (list, tuple)) and len(canvas_size) == 2:
            # Use forward=False to prevent automatic subplot adjustment that can shift the plot
            fig.set_size_inches(canvas_size[0], canvas_size[1], forward=False)
        
        # Frame position: prefer axes_fraction (exact position), fall back to preserving position with frame_size
        if axes_frac and isinstance(axes_frac, (list, tuple)) and len(axes_frac) == 4:
            # Restore exact position from axes_fraction (this overrides any automatic adjustments)
            x0, y0, w, h = axes_frac
            ax.set_position([float(x0), float(y0), float(w), float(h)])
        elif frame_size:
            # Fall back to preserving current position with frame_size (for backward compatibility)
            if frame_size and isinstance(frame_size, (list, tuple)) and len(frame_size) == 2:
                fw_in, fh_in = frame_size
                canvas_w, canvas_h = fig.get_size_inches()
                if canvas_w > 0 and canvas_h > 0:
                    # Keep current left/bottom position, adjust width/height
                    current_pos = ax.get_position()
                    new_w = fw_in / canvas_w
                    new_h = fh_in / canvas_h
                    ax.set_position([current_pos.x0, current_pos.y0, new_w, new_h])
    except Exception:
        pass
    def _apply_series_config():
        try:
            s = cfg.get('series', {})
            ch = s.get('charge', {})
            dh = s.get('discharge', {})
            ef = s.get('efficiency', {})
            
            # Apply marker sizes and alpha globally to all files in multi-file mode
            if is_multi_file and file_data is not None:
                for f in file_data:
                    # Marker types (global)
                    if ch.get('marker') is not None and hasattr(f['sc_charge'], 'set_marker'):
                        f['sc_charge'].set_marker(ch['marker'])
                    if dh.get('marker') is not None and hasattr(f['sc_discharge'], 'set_marker'):
                        f['sc_discharge'].set_marker(dh['marker'])
                    if ef.get('marker') is not None and hasattr(f['sc_eff'], 'set_marker'):
                        f['sc_eff'].set_marker(ef['marker'])
                    # Marker sizes (global)
                    if ch.get('markersize') is not None and hasattr(f['sc_charge'], 'set_sizes'):
                        f['sc_charge'].set_sizes([float(ch['markersize'])])
                    if dh.get('markersize') is not None and hasattr(f['sc_discharge'], 'set_sizes'):
                        f['sc_discharge'].set_sizes([float(dh['markersize'])])
                    if ef.get('markersize') is not None and hasattr(f['sc_eff'], 'set_sizes'):
                        f['sc_eff'].set_sizes([float(ef['markersize'])])
                    
                    # Alpha (global)
                    if ch.get('alpha') is not None:
                        f['sc_charge'].set_alpha(float(ch['alpha']))
                    if dh.get('alpha') is not None:
                        f['sc_discharge'].set_alpha(float(dh['alpha']))
                    if ef.get('alpha') is not None:
                        f['sc_eff'].set_alpha(float(ef['alpha']))
                
                # Efficiency visibility (global)
                if 'visible' in ef:
                    eff_vis = bool(ef['visible'])
                    for f in file_data:
                        try:
                            f['sc_eff'].set_visible(eff_vis)
                        except Exception:
                            pass
                    try:
                        ax2.yaxis.label.set_visible(eff_vis)
                    except Exception:
                        pass
            else:
                # Single file mode: apply to provided artists only
                if ch:
                    if ch.get('color') is not None:
                        # Apply color respecting hollow marker style
                        if ch.get('hollow', False):
                            sc_charge.set_facecolors('none')
                            sc_charge.set_edgecolors(ch['color'])
                        else:
                            sc_charge.set_color(ch['color'])
                    if ch.get('marker') is not None and hasattr(sc_charge, 'set_marker'):
                        sc_charge.set_marker(ch['marker'])
                    if ch.get('markersize') is not None and hasattr(sc_charge, 'set_sizes'):
                        sc_charge.set_sizes([float(ch['markersize'])])
                    if ch.get('alpha') is not None:
                        sc_charge.set_alpha(float(ch['alpha']))
                    if 'visible' in ch:
                        try:
                            sc_charge.set_visible(bool(ch['visible']))
                        except Exception:
                            pass
                if dh:
                    if dh.get('color') is not None:
                        # Apply color respecting hollow marker style
                        if dh.get('hollow', False):
                            sc_discharge.set_facecolors('none')
                            sc_discharge.set_edgecolors(dh['color'])
                        else:
                            sc_discharge.set_color(dh['color'])
                    if dh.get('marker') is not None and hasattr(sc_discharge, 'set_marker'):
                        sc_discharge.set_marker(dh['marker'])
                    if dh.get('markersize') is not None and hasattr(sc_discharge, 'set_sizes'):
                        sc_discharge.set_sizes([float(dh['markersize'])])
                    if dh.get('alpha') is not None:
                        sc_discharge.set_alpha(float(dh['alpha']))
                    if 'visible' in dh:
                        try:
                            sc_discharge.set_visible(bool(dh['visible']))
                        except Exception:
                            pass
                if ef:
                    if ef.get('color') is not None:
                        try:
                            # Apply color respecting hollow marker style
                            if ef.get('hollow', False):
                                sc_eff.set_facecolors('none')
                                sc_eff.set_edgecolors(ef['color'])
                            else:
                                sc_eff.set_color(ef['color'])
                        except Exception:
                            pass
                    if ef.get('marker') is not None and hasattr(sc_eff, 'set_marker'):
                        sc_eff.set_marker(ef['marker'])
                    if ef.get('markersize') is not None and hasattr(sc_eff, 'set_sizes'):
                        sc_eff.set_sizes([float(ef['markersize'])])
                    if ef.get('alpha') is not None:
                        sc_eff.set_alpha(float(ef['alpha']))
                    if 'visible' in ef:
                        try:
                            sc_eff.set_visible(bool(ef['visible']))
                            ax2.yaxis.label.set_visible(bool(ef['visible']))
                        except Exception:
                            pass
                    if ef.get('offsets') is not None and hasattr(sc_eff, 'set_offsets'):
                        try:
                            arr = np.array(ef['offsets'])
                            curr = sc_eff.get_offsets()
                            if arr.size > 0 and (curr.size == 0 or curr.shape == arr.shape):
                                sc_eff.set_offsets(arr)
                        except Exception:
                            pass
                # Restore legend labels for single-file mode
                try:
                    if 'label' in ch and hasattr(sc_charge, 'set_label'):
                        sc_charge.set_label(ch['label'])
                    if 'label' in dh and hasattr(sc_discharge, 'set_label'):
                        sc_discharge.set_label(dh['label'])
                    if 'label' in ef and hasattr(sc_eff, 'set_label'):
                        sc_eff.set_label(ef['label'])
                except Exception:
                    pass
        except Exception:
            pass
    _apply_series_config()

    # Apply legend state (h command)
    def _apply_legend_config():
        try:
            leg_cfg = cfg.get('legend', {})
            if leg_cfg:
                leg_visible = leg_cfg.get('visible', True)
                leg_xy_in = leg_cfg.get('position_inches')
                if 'title' in leg_cfg:
                    fig._cpc_legend_title = leg_cfg.get('title') or _get_legend_title(fig)
                if leg_xy_in is not None:
                    fig._cpc_legend_xy_in = _sanitize_legend_offset(tuple(leg_xy_in))
                leg = ax.get_legend()
                if leg is not None:
                    leg.set_visible(leg_visible)
                if leg_visible:
                    _apply_legend_position()
                    # Re-apply legend label colors to match handles after position/visibility changes
                    try:
                        leg = ax.get_legend()
                        if leg is not None:
                            handles = list(getattr(leg, "legendHandles", []))
                            for h, txt in zip(handles, leg.get_texts()):
                                col = _color_of(h)
                                if col is None and hasattr(h, 'get_edgecolor'):
                                    col = h.get_edgecolor()
                                col = _coerce_legend_color(col)
                                if col is not None:
                                    txt.set_color(col)
                    except Exception:
                        pass
        except Exception:
            pass
    _apply_legend_config()

    # Apply tick visibility/widths and spines
    def _apply_tick_config():
        try:
            tk = cfg.get('ticks', {})
            # Try wasd_state first (version 2), fall back to visibility dict (version 1)
            wasd = cfg.get('wasd_state', {})
            if isinstance(wasd, dict) and wasd:
                try:
                    setattr(fig, '_cpc_wasd_state', wasd)
                except Exception:
                    pass
            if wasd:
                # Use WASD state (20 parameters)
                bx = bool(wasd.get('bottom', {}).get('labels', True))
                tx = bool(wasd.get('top', {}).get('labels', False))
                ly = bool(wasd.get('left', {}).get('labels', True))
                ry = bool(wasd.get('right', {}).get('labels', True))
                mbx = bool(wasd.get('bottom', {}).get('minor', False))
                mtx = bool(wasd.get('top', {}).get('minor', False))
                mly = bool(wasd.get('left', {}).get('minor', False))
                mry = bool(wasd.get('right', {}).get('minor', False))
            else:
                # Fall back to old visibility dict
                vis = tk.get('visibility', {})
                bx = bool(vis.get('bx', True))
                tx = bool(vis.get('tx', False))
                ly = bool(vis.get('ly', True))
                ry = bool(vis.get('ry', True))
                mbx = bool(vis.get('mbx', False))
                mtx = bool(vis.get('mtx', False))
                mly = bool(vis.get('mly', False))
                mry = bool(vis.get('mry', False))

            if isinstance(wasd, dict) and wasd:
                sync_tick_state_from_wasd(
                    tick_state,
                    wasd,
                    tick_defaults={'top': False, 'bottom': True, 'left': True, 'right': True},
                    label_defaults={'top': False, 'bottom': True, 'left': True, 'right': True},
                )
            else:
                tick_state.update({
                    'bx': bx, 'tx': tx, 'ly': ly, 'ry': ry,
                    'b_ticks': bx, 't_ticks': tx, 'l_ticks': ly, 'r_ticks': ry,
                    'b_labels': bx, 't_labels': tx, 'l_labels': ly, 'r_labels': ry,
                    'mbx': mbx, 'mtx': mtx, 'mly': mly, 'mry': mry,
                })
            try:
                ax._saved_tick_state = dict(tick_state)
            except Exception:
                pass
            
            if True:  # Always apply
                ax.tick_params(axis='x', bottom=bx, labelbottom=bx, top=tx, labeltop=tx)
                ax.tick_params(axis='y', left=ly, labelleft=ly)
                ax2.tick_params(axis='y', right=ry, labelright=ry)
                try:
                    ax.xaxis.label.set_visible(bool(wasd.get('bottom', {}).get('title', True)) if wasd else bx)
                    ax.yaxis.label.set_visible(bool(wasd.get('left', {}).get('title', True)) if wasd else ly)
                    ax2.yaxis.label.set_visible(bool(wasd.get('right', {}).get('title', True)) if wasd else ry)
                    if wasd:
                        top_title_on = bool(wasd.get('top', {}).get('title', False))
                        ax._top_xlabel_on = top_title_on
                        if not getattr(ax, '_stored_top_xlabel', None):
                            ax._stored_top_xlabel = ax.get_xlabel() or getattr(ax, '_stored_xlabel', '')
                        if top_title_on and getattr(ax, '_stored_top_xlabel', ''):
                            if not hasattr(ax, '_top_xlabel_text') or ax._top_xlabel_text is None:
                                ax._top_xlabel_text = ax.text(
                                    0.5, 1.0, '',
                                    transform=ax.transAxes,
                                    ha='center',
                                    va='bottom',
                                    fontsize=ax.xaxis.label.get_fontsize(),
                                    fontfamily=ax.xaxis.label.get_fontfamily(),
                                )
                            ax._top_xlabel_text.set_text(ax._stored_top_xlabel)
                            ax._top_xlabel_text.set_visible(True)
                            ax._top_xlabel_text.set_position((0.5, 1.07 if tx else 1.02))
                        elif hasattr(ax, '_top_xlabel_text') and ax._top_xlabel_text is not None:
                            ax._top_xlabel_text.set_visible(False)
                except Exception:
                    pass
                # Minor ticks
                if mbx or mtx:
                    ax.xaxis.set_minor_locator(AutoMinorLocator())
                    ax.xaxis.set_minor_formatter(NullFormatter())
                    ax.tick_params(axis='x', which='minor', bottom=mbx, top=mtx, labelbottom=False, labeltop=False)
                else:
                    # Clear minor locator if no minor ticks are enabled
                    ax.xaxis.set_minor_locator(NullLocator())
                    ax.xaxis.set_minor_formatter(NullFormatter())
                    ax.tick_params(axis='x', which='minor', bottom=False, top=False, labelbottom=False, labeltop=False)
                if mly:
                    ax.yaxis.set_minor_locator(AutoMinorLocator())
                    ax.yaxis.set_minor_formatter(NullFormatter())
                    ax.tick_params(axis='y', which='minor', left=True, labelleft=False)
                else:
                    # Clear minor locator if no minor ticks are enabled
                    ax.yaxis.set_minor_locator(NullLocator())
                    ax.yaxis.set_minor_formatter(NullFormatter())
                    ax.tick_params(axis='y', which='minor', left=False, labelleft=False)
                if mry:
                    ax2.yaxis.set_minor_locator(AutoMinorLocator())
                    ax2.yaxis.set_minor_formatter(NullFormatter())
                    ax2.tick_params(axis='y', which='minor', right=True, labelright=False)
                else:
                    # Clear minor locator if no minor ticks are enabled
                    ax2.yaxis.set_minor_locator(NullLocator())
                    ax2.yaxis.set_minor_formatter(NullFormatter())
                    ax2.tick_params(axis='y', which='minor', right=False, labelright=False)
            
            # Widths: support both version 2 (nested in 'widths') and version 1 (direct keys)
            widths = tk.get('widths', tk)  # Try nested first, fall back to tk itself
            if widths.get('x_major') is not None:
                ax.tick_params(axis='x', which='major', width=widths['x_major'])
            if widths.get('x_minor') is not None:
                ax.tick_params(axis='x', which='minor', width=widths['x_minor'])
            if widths.get('ly_major') is not None:
                ax.tick_params(axis='y', which='major', width=widths['ly_major'])
            if widths.get('ly_minor') is not None:
                ax.tick_params(axis='y', which='minor', width=widths['ly_minor'])
            if widths.get('ry_major') is not None:
                ax2.tick_params(axis='y', which='major', width=widths['ry_major'])
            if widths.get('ry_minor') is not None:
                ax2.tick_params(axis='y', which='minor', width=widths['ry_minor'])
            
            # Lengths: apply to both axes
            lengths = tk.get('lengths', {})
            if lengths.get('major') is not None:
                ax.tick_params(axis='both', which='major', length=lengths['major'])
                ax2.tick_params(axis='both', which='major', length=lengths['major'])
            if lengths.get('minor') is not None:
                ax.tick_params(axis='both', which='minor', length=lengths['minor'])
                ax2.tick_params(axis='both', which='minor', length=lengths['minor'])
            if lengths:
                fig._tick_lengths = dict(lengths)
            
            # Apply tick direction
            tick_direction = tk.get('direction', 'out')
            if tick_direction:
                setattr(fig, '_tick_direction', tick_direction)
                ax.tick_params(axis='both', which='both', direction=tick_direction)
                ax2.tick_params(axis='both', which='both', direction=tick_direction)
            # Tick spacing and minor locators
            spacing = tk.get('spacing', {})
            if spacing:
                restore_axis_tick_locators(ax.xaxis, spacing, 'x')
                restore_axis_tick_locators(ax.yaxis, spacing, 'y')
                restore_axis_tick_locators(ax2.yaxis, spacing, 'ry')
        except Exception:
            pass
    _apply_tick_config()

    def _apply_spine_config():
        try:
            sp = cfg.get('spines', {})
            for name, spec in sp.items():
                if name in ('bottom','top','left') and name in ax.spines:
                    target_axes = (ax, ax2) if name in ('bottom', 'top') else (ax,)
                    for target_ax in target_axes:
                        spn = target_ax.spines.get(name)
                        if spn is None:
                            continue
                        if spec.get('linewidth') is not None:
                            try:
                                spn.set_linewidth(float(spec['linewidth']))
                            except Exception:
                                pass
                        if spec.get('visible') is not None:
                            try:
                                spn.set_visible(bool(spec['visible']))
                            except Exception:
                                pass
                    if spec.get('color') is not None:
                        _set_spine_color(name, spec['color'])
                if name == 'right' and ax2.spines.get('right') is not None:
                    spn = ax2.spines.get('right')
                    if spec.get('linewidth') is not None:
                        try:
                            spn.set_linewidth(float(spec['linewidth']))
                        except Exception:
                            pass
                    if spec.get('visible') is not None:
                        try:
                            spn.set_visible(bool(spec['visible']))
                        except Exception:
                            pass
                    if spec.get('color') is not None:
                        _set_spine_color('right', spec['color'])
            # Draw before spine color restore so tick objects exist (even when right was hidden)
            try:
                fig.canvas.draw_idle()
            except Exception:
                pass
            # Restore spine colors from stored dict
            spine_colors = cfg.get('spine_colors', {})
            if spine_colors:
                for spine_name, color in spine_colors.items():
                    _set_spine_color(spine_name, color)
            # Restore auto setting
            spine_auto = cfg.get('spine_colors_auto', False)
            if spine_auto is not None:
                fig._cpc_spine_auto = bool(spine_auto)
                # If auto is enabled, apply colors immediately
                if fig._cpc_spine_auto and not (file_data and len(file_data) > 1):
                    try:
                        charge_col = _normalize_spine_color(_color_of(sc_charge))
                        eff_col = _normalize_spine_color(_color_of(sc_eff))
                        if charge_col and eff_col:
                            _set_spine_color('left', charge_col)
                            _set_spine_color('right', eff_col)
                    except Exception:
                        pass
        except Exception:
            pass
    _apply_spine_config()

    # Restore labelpads (preserve current if not in config)
    def _apply_labelpads_config():
        try:
            pads = cfg.get('labelpads', {})
            if pads:
                if pads.get('x') is not None:
                    ax.xaxis.labelpad = pads['x']
                elif saved_xlabelpad is not None:
                    ax.xaxis.labelpad = saved_xlabelpad
                if pads.get('ly') is not None:
                    ax.yaxis.labelpad = pads['ly']
                elif saved_ylabelpad is not None:
                    ax.yaxis.labelpad = saved_ylabelpad
                if pads.get('ry') is not None and ax2 is not None:
                    ax2.yaxis.labelpad = pads['ry']
                elif saved_rylabelpad is not None and ax2 is not None:
                    ax2.yaxis.labelpad = saved_rylabelpad
            else:
                # No labelpads in config, preserve current values
                if saved_xlabelpad is not None:
                    ax.xaxis.labelpad = saved_xlabelpad
                if saved_ylabelpad is not None:
                    ax.yaxis.labelpad = saved_ylabelpad
                if saved_rylabelpad is not None and ax2 is not None:
                    ax2.yaxis.labelpad = saved_rylabelpad
        except Exception:
            pass
    _apply_labelpads_config()

    # Grid state
    def _apply_grid_config():
        try:
            grid_enabled = cfg.get('grid', False)
            if grid_enabled:
                ax.grid(True, color='0.85', linestyle='-', linewidth=0.5, alpha=0.7)
            else:
                ax.grid(False)
        except Exception:
            pass
    _apply_grid_config()

    # Title offsets - all four titles
    def _apply_title_offsets_config():
        try:
            offsets = cfg.get('title_offsets', {})
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
                    ax2._right_ylabel_manual_offset_x_pts = float(offsets.get('right_x', 0.0) or 0.0)
                else:
                    # Backward compatibility: old format used 'right' for x-offset
                    ax2._right_ylabel_manual_offset_x_pts = float(offsets.get('right', 0.0) or 0.0)
            except Exception:
                ax2._right_ylabel_manual_offset_x_pts = 0.0
            try:
                ax2._right_ylabel_manual_offset_y_pts = float(offsets.get('right_y', 0.0) or 0.0)
            except Exception:
                ax2._right_ylabel_manual_offset_y_pts = 0.0
            # Reposition titles to apply offsets
            _ui_position_top_xlabel(ax, fig, tick_state)
            _ui_position_bottom_xlabel(ax, fig, tick_state)
            _ui_position_left_ylabel(ax, fig, tick_state)
            _ui_position_right_ylabel(ax2, fig, tick_state)
        except Exception:
            pass
    _apply_title_offsets_config()

    # Restore legend labels
    def _restore_legend_labels_config():
        try:
            if is_multi_file and file_data:
                multi_files = cfg.get('multi_files', [])
                if multi_files and len(multi_files) == len(file_data):
                    for i, f_info in enumerate(multi_files):
                        if i < len(file_data):
                            f = file_data[i]
                            if 'visible' in f_info:
                                try:
                                    file_visible = bool(f_info['visible'])
                                    f['visible'] = file_visible
                                    display_mode = getattr(fig, '_cpc_display_mode', 'both')
                                    artist_visibility = {
                                        'sc_charge': file_visible and display_mode in ('charge', 'both'),
                                        'sc_discharge': file_visible and display_mode in ('discharge', 'both'),
                                        'sc_eff': file_visible,
                                    }
                                    for artist_key, visible in artist_visibility.items():
                                        artist = f.get(artist_key)
                                        if artist is not None:
                                            artist.set_visible(visible)
                                except Exception:
                                    pass
                            # Restore colors FIRST (before labels), respecting hollow marker style
                            if 'charge_color' in f_info and f.get('sc_charge'):
                                try:
                                    col = f_info['charge_color']
                                    is_hollow = f_info.get('charge_hollow', False)
                                    if is_hollow:
                                        f['sc_charge'].set_facecolors('none')
                                        f['sc_charge'].set_edgecolors(col)
                                    else:
                                        f['sc_charge'].set_facecolor(col)
                                        f['sc_charge'].set_edgecolor(col)
                                    f['color'] = col
                                except Exception:
                                    pass
                            if 'discharge_color' in f_info and f.get('sc_discharge'):
                                try:
                                    col = f_info['discharge_color']
                                    is_hollow = f_info.get('discharge_hollow', False)
                                    if is_hollow:
                                        f['sc_discharge'].set_facecolors('none')
                                        f['sc_discharge'].set_edgecolors(col)
                                    else:
                                        f['sc_discharge'].set_facecolor(col)
                                        f['sc_discharge'].set_edgecolor(col)
                                except Exception:
                                    pass
                            if 'efficiency_color' in f_info and f.get('sc_eff'):
                                try:
                                    col = f_info['efficiency_color']
                                    is_hollow = f_info.get('efficiency_hollow', False)
                                    if is_hollow:
                                        f['sc_eff'].set_facecolors('none')
                                        f['sc_eff'].set_edgecolors(col)
                                    else:
                                        f['sc_eff'].set_facecolor(col)
                                        f['sc_eff'].set_edgecolor(col)
                                    f['eff_color'] = col
                                except Exception:
                                    pass
                            # Restore charge/discharge visibility (display mode)
                            # Only apply per-file if display_mode was not already applied above
                            if dm not in ('charge', 'discharge', 'both'):
                                if 'charge_visible' in f_info and f.get('sc_charge'):
                                    try:
                                        f['sc_charge'].set_visible(bool(f_info['charge_visible']))
                                    except Exception:
                                        pass
                                if 'discharge_visible' in f_info and f.get('sc_discharge'):
                                    try:
                                        f['sc_discharge'].set_visible(bool(f_info['discharge_visible']))
                                    except Exception:
                                        pass
                            # Restore legend labels
                            if 'charge_label' in f_info and f.get('sc_charge'):
                                try:
                                    f['sc_charge'].set_label(f_info['charge_label'])
                                except Exception:
                                    pass
                            if 'discharge_label' in f_info and f.get('sc_discharge'):
                                try:
                                    f['sc_discharge'].set_label(f_info['discharge_label'])
                                except Exception:
                                    pass
                            if 'efficiency_label' in f_info and f.get('sc_eff'):
                                try:
                                    f['sc_eff'].set_label(f_info['efficiency_label'])
                                except Exception:
                                    pass
                            if 'efficiency_offsets' in f_info and f_info['efficiency_offsets'] and f.get('sc_eff') and hasattr(f['sc_eff'], 'set_offsets'):
                                try:
                                    arr = np.array(f_info['efficiency_offsets'])
                                    curr = f['sc_eff'].get_offsets()
                                    if arr.size > 0 and (curr.size == 0 or curr.shape == arr.shape):
                                        f['sc_eff'].set_offsets(arr)
                                except Exception:
                                    pass
                            # Update filename if present
                            if 'filename' in f_info:
                                f['filename'] = f_info['filename']
            else:
                # Single file mode: restore legend labels
                s = cfg.get('series', {})
                ch = s.get('charge', {})
                dh = s.get('discharge', {})
                ef = s.get('efficiency', {})
                if 'label' in ch and hasattr(sc_charge, 'set_label'):
                    try:
                        sc_charge.set_label(ch['label'])
                    except Exception:
                        pass
                if 'label' in dh and hasattr(sc_discharge, 'set_label'):
                    try:
                        sc_discharge.set_label(dh['label'])
                    except Exception:
                        pass
                if 'label' in ef and hasattr(sc_eff, 'set_label'):
                    try:
                        sc_eff.set_label(ef['label'])
                    except Exception:
                        pass
            # Rebuild legend after restoring labels
            _rebuild_legend(ax, ax2, file_data, preserve_position=True)
            if cfg.get('legend', {}).get('visible') is False:
                for target_ax in (ax, ax2):
                    try:
                        leg = target_ax.get_legend()
                        if leg is not None:
                            leg.set_visible(False)
                    except Exception:
                        pass
        except Exception:
            pass
    _restore_legend_labels_config()

    try:
        fig.canvas.draw_idle()
    except Exception:
        pass


def cpc_interactive_menu(fig, ax, ax2: Any, sc_charge, sc_discharge, sc_eff, file_data: Optional[List[Dict]] = None, canvas_mode: bool = False):
    """
    Interactive menu for Capacity-Per-Cycle (CPC) plots.
    
    HOW CPC INTERACTIVE MENU WORKS:
    ------------------------------
    This function provides an interactive command-line menu for customizing CPC plots.
    CPC plots show battery capacity and efficiency over multiple cycles.
    
    PLOT STRUCTURE:
    --------------
    CPC plots have two Y-axes (twin axes):
    - Left Y-axis: Capacity (mAh/g or mAh) - shows charge and discharge capacity
    - Right Y-axis: Efficiency (%) - shows coulombic efficiency
    
    X-axis: Cycle number (1, 2, 3, ...)
    
    Each cycle is represented by scatter points:
    - Charge capacity point (left axis)
    - Discharge capacity point (left axis)
    - Efficiency point (right axis)
    
    MULTI-FILE MODE:
    --------------
    CPC mode supports plotting multiple files simultaneously:
    - Each file gets its own set of scatter points (charge, discharge, efficiency)
    - Each file can have different colors
    - Files can be shown/hidden individually
    - You can switch between files to edit their properties
    
    MENU COMMANDS:
    -------------
    The menu is organized into three categories:
    
    **Styles** (visual appearance):
    - f: font (size and family)
    - l: line (width and style)
    - m: marker sizes
    - c: colors (for charge, discharge, efficiency)
    - k: spine colors (plot border colors)
    - ry: show/hide efficiency (right Y-axis)
    - t: toggle spines (show/hide tick labels)
    - h: legend (show/hide)
    - g: size (figure and axes size)
    - v: show/hide files (multi-file mode)
    
    **Geometries** (axis ranges and labels):
    - r: rename titles (axis labels)
    - x: x range (cycle number range)
    - y: y ranges (capacity and efficiency ranges)
    
    **Options** (file operations):
    - p: print/export style/geometry (save .bpcfg file)
    - i: import style/geometry (load .bpcfg file)
    - e: export figure (save plot as image)
    - s: save project (save session as .pkl)
    - b: undo (revert last change)
    - q: quit (exit menu)
    
    Args:
        fig: Matplotlib figure object
        ax: Primary axes (left Y-axis, shows capacity)
        ax2: Twin axes (right Y-axis, shows efficiency)
        sc_charge: Scatter plot artist for charge capacity (primary file)
        sc_discharge: Scatter plot artist for discharge capacity (primary file)
        sc_eff: Scatter plot artist for efficiency (primary file)
        file_data: Optional list of dictionaries, one per file:
            - 'filename': File name (for display)
            - 'sc_charge': Scatter artist for charge capacity
            - 'sc_discharge': Scatter artist for discharge capacity
            - 'sc_eff': Scatter artist for efficiency
            - 'visible': Whether file is currently visible
            - 'filepath': Path to source file (optional)
    """
    # ====================================================================
    # MULTI-FILE MODE SETUP
    # ====================================================================
    # CPC mode can handle multiple files simultaneously. Each file gets its
    # own set of scatter points (charge, discharge, efficiency) with its
    # own colors. This allows comparing multiple battery cells or conditions.
    #
    # If file_data is provided, we're in multi-file mode.
    # If not provided, we create a single-file structure for backward compatibility.
    # ====================================================================
    if file_data is None:
        # Backward compatibility: create file_data structure from single file
        # This allows the function to work with old code that passes individual artists
        # Try to get filename from label if available
        filename = 'Data'
        try:
            if hasattr(sc_charge, 'get_label') and sc_charge.get_label():
                label = sc_charge.get_label()
                # Extract filename from label like "filename (Chg)" or use label as-is
                if ' (Chg)' in label:
                    filename = label.replace(' (Chg)', '')
                elif ' (Dch)' in label:
                    filename = label.replace(' (Dch)', '')
                elif label and label != 'Charge capacity':
                    filename = label
        except Exception:
            pass
        file_data = [{
            'filename': filename,
            'sc_charge': sc_charge,      # Charge capacity scatter artist
            'sc_discharge': sc_discharge,  # Discharge capacity scatter artist
            'sc_eff': sc_eff,            # Efficiency scatter artist
            'visible': True               # File is visible by default
        }]
    # Track which file is currently selected for editing (in multi-file mode)
    current_file_idx = 0  # Index of currently selected file (0 = first file)
    
    # Collect file paths for session saving (if available)
    file_paths = _collect_file_paths(file_data)

    # Multi-file flag: now that file_data is finalized
    is_multi_file = file_data is not None and len(file_data) > 1
    try:
        fig._cpc_is_multi_file = bool(is_multi_file)
    except Exception:
        pass
    
    # ====================================================================
    # TICK STATE MANAGEMENT
    # ====================================================================
    # CPC plots have two axes (primary + twin), so we need to track tick
    # visibility for both. The tick_state dictionary tracks:
    #
    # Primary axes (ax):
    #   - bx: bottom x-axis ticks and labels
    #   - tx: top x-axis ticks and labels
    #   - ly: left y-axis ticks and labels (capacity)
    #   - mbx: minor bottom x-axis ticks
    #   - mtx: minor top x-axis ticks
    #   - mly: minor left y-axis ticks
    #
    # Twin axes (ax2):
    #   - ry: right y-axis ticks and labels (efficiency)
    #   - mry: minor right y-axis ticks
    #
    # Users can toggle these with 't' command to customize plot appearance.
    # ====================================================================
    tick_state = {
        'bx': True,   # bottom x-axis (cycle numbers) - shown by default
        'tx': False,  # top x-axis - hidden by default
        'ly': True,   # left y-axis (capacity) - shown by default
        'ry': True,   # right y-axis (efficiency) - shown by default
        'mbx': False, # minor bottom x-axis ticks - hidden by default
        'mtx': False, # minor top x-axis ticks - hidden by default
        'mly': False, # minor left y-axis ticks - hidden by default
        'mry': False, # minor right y-axis ticks - hidden by default
    }
    try:
        saved_wasd = getattr(fig, '_cpc_wasd_state', None)
        if isinstance(saved_wasd, dict) and saved_wasd:
            sync_tick_state_from_wasd(
                tick_state,
                saved_wasd,
                tick_defaults={'top': False, 'bottom': True, 'left': True, 'right': True},
                label_defaults={'top': False, 'bottom': True, 'left': True, 'right': True},
            )
            # Keep axis-level cache in sync so any save path persists the current state.
            try:
                ax._saved_tick_state = dict(tick_state)
            except Exception:
                pass
    except Exception:
        pass

    # --- Undo stack using style snapshots ---
    state_history = []  # list of cfg dicts

    if not hasattr(fig, '_cpc_spine_colors') or not isinstance(getattr(fig, '_cpc_spine_colors'), dict):
        fig._cpc_spine_colors = {}

    def _set_spine_color(spine_name: str, color):
        if not hasattr(fig, '_cpc_spine_colors') or not isinstance(fig._cpc_spine_colors, dict):
            fig._cpc_spine_colors = {}
        color = _normalize_spine_color(color)
        if color is None:
            return
        fig._cpc_spine_colors[spine_name] = color
        axes_map = {
            'top': [ax, ax2],
            'bottom': [ax, ax2],
            'left': [ax],
            'right': [ax2],
        }
        target_axes = axes_map.get(spine_name, [ax, ax2])
        for curr_ax in target_axes:
            if curr_ax is None or spine_name not in curr_ax.spines:
                continue
            try:
                _ui_set_spine_side_color(curr_ax, spine_name, color, fig=fig)
            except Exception:
                pass

    def push_state(note: str = ""):
        push_cpc_state(
            state_history,
            fig=fig,
            ax=ax,
            ax2=ax2,
            sc_charge=sc_charge,
            sc_discharge=sc_discharge,
            sc_eff=sc_eff,
            file_data=file_data,
            tick_state=tick_state,
            note=note,
        )

    def restore_state():
        restore_cpc_state(
            state_history,
            fig=fig,
            ax=ax,
            ax2=ax2,
            sc_charge=sc_charge,
            sc_discharge=sc_discharge,
            sc_eff=sc_eff,
            file_data=file_data,
            tick_state=tick_state,
            update_ticks_func=_update_ticks,
        )

    def _update_ticks():
        try:
            # Apply shared visibility to primary ax; then adjust twin for right side
            _ui_update_tick_visibility(ax, tick_state)
            # Ensure left axis ticks/labels don't appear on right axis
            ax.tick_params(axis='y', right=False, labelright=False)
            # Right axis tick params follow r_* keys
            ax2.tick_params(axis='y',
                            right=tick_state.get('r_ticks', tick_state.get('ry', False)),
                            labelright=tick_state.get('r_labels', tick_state.get('ry', False)))
            # Minor right-y consistency
            if tick_state.get('mry'):
                ax2.yaxis.set_minor_locator(AutoMinorLocator()); ax2.yaxis.set_minor_formatter(NullFormatter())
                ax2.tick_params(axis='y', which='minor', right=True, labelright=False)
            else:
                ax2.tick_params(axis='y', which='minor', right=False, labelright=False)
            # Note: Do NOT call position functions during undo restore as it causes title drift
            # Title offsets are already restored from snapshot in restore_state()
            # Draw before re-applying spine colors so tick objects exist (even when right was hidden)
            try:
                fig.canvas.draw_idle()
            except Exception:
                pass
            try:
                for spine_name, color in getattr(fig, '_cpc_spine_colors', {}).items():
                    _set_spine_color(spine_name, color)
            except Exception:
                pass
            fig.canvas.draw_idle()
        except Exception:
            pass

    def _toggle_spine(code: str):
        # Map bl/tl/ll to ax; rl to ax2
        try:
            if code == 'bl':
                sp = ax.spines.get('bottom'); sp.set_visible(not sp.get_visible())
            elif code == 'tl':
                sp = ax.spines.get('top'); sp.set_visible(not sp.get_visible())
            elif code == 'll':
                sp = ax.spines.get('left'); sp.set_visible(not sp.get_visible())
            elif code == 'rl':
                sp = ax2.spines.get('right'); sp.set_visible(not sp.get_visible())
            fig.canvas.draw_idle()
        except Exception:
            pass

    def _sanitize_legend_offset(xy: object) -> Optional[tuple[float, float]]:
        if xy is None or not isinstance(xy, tuple) or len(xy) != 2:
            return None
        x_in, y_in = xy
        try:
            x_val = float(x_in)
            y_val = float(y_in)
        except Exception:
            return None
        fw, fh = fig.get_size_inches()
        if fw <= 0 or fh <= 0:
            return None
        max_offset = max(fw, fh) * 2.0
        if abs(x_val) > max_offset or abs(y_val) > max_offset:
            return None
        return (x_val, y_val)

    def _apply_legend_position():
        """Reapply legend position using stored inches offset. Uses _rebuild_legend so
        compact multi-file format (header row + per-file names) is preserved."""
        try:
            _rebuild_legend(ax, ax2, file_data, preserve_position=True)
        except Exception:
            pass

    # Ensure resize re-applies legend position in inches
    try:
        if not hasattr(fig, '_cpc_legpos_cid') or getattr(fig, '_cpc_legpos_cid') is None:
            def _on_resize(event):
                _apply_legend_position()
                try:
                    fig.canvas.draw_idle()
                except Exception:
                    pass
            fig._cpc_legpos_cid = fig.canvas.mpl_connect('resize_event', _on_resize)
    except Exception:
        pass

    # Crosshair state for CPC
    crosshair_cpc = {'active': False, 'hline': None, 'vline': None, 'text': None, 'cid_motion': None}

    def _toggle_crosshair_cpc():
        if not crosshair_cpc['active']:
            vline = ax.axvline(x=ax.get_xlim()[0], color='0.35', ls='--', lw=0.8, alpha=0.85, zorder=9999)
            hline = ax.axhline(y=ax.get_ylim()[0], color='0.35', ls='--', lw=0.8, alpha=0.85, zorder=9999)
            txt = ax.text(1.0, 1.0, "", ha='right', va='bottom', transform=ax.transAxes,
                          fontsize=max(9, int(0.6 * plt.rcParams.get('font.size', 16))),
                          color='0.15', bbox=dict(boxstyle='round,pad=0.25', fc='white', ec='0.7', alpha=0.8))

            def on_move(event):
                if event.inaxes not in (ax, ax2):
                    return
                if event.x is None or event.y is None:
                    return
                try:
                    pt_ax = ax.transData.inverted().transform((event.x, event.y))
                    pt_ax2 = ax2.transData.inverted().transform((event.x, event.y))
                    cycle = pt_ax[0]
                    cap = pt_ax[1]
                    eff = pt_ax2[1]
                    vline.set_xdata([cycle, cycle])
                    hline.set_ydata([cap, cap])
                    txt.set_text(f"Cycle={cycle:.2g}\nCapacity={cap:.4g}\nEfficiency={eff:.2%}")
                except Exception:
                    if event.xdata is not None and event.ydata is not None:
                        vline.set_xdata([event.xdata, event.xdata])
                        hline.set_ydata([event.ydata, event.ydata])
                        txt.set_text(f"x={event.xdata:.4g}\ny={event.ydata:.4g}")
                fig.canvas.draw_idle()

            cid = fig.canvas.mpl_connect('motion_notify_event', on_move)
            crosshair_cpc.update({'active': True, 'hline': hline, 'vline': vline, 'text': txt, 'cid_motion': cid})
            print("Crosshair ON. Move mouse over axes. Press 'n' again to turn off.")
        else:
            if crosshair_cpc['cid_motion'] is not None:
                fig.canvas.mpl_disconnect(crosshair_cpc['cid_motion'])
            for k in ('hline', 'vline', 'text'):
                art = crosshair_cpc.get(k)
                if art is not None:
                    try:
                        art.remove()
                    except Exception:
                        pass
            crosshair_cpc.update({'active': False, 'hline': None, 'vline': None, 'text': None, 'cid_motion': None})
            fig.canvas.draw_idle()
            print("Crosshair OFF.")

    def _handle_key_t():
        assert sc_eff is not None
        # Unified WASD toggles for spines/ticks/minor/labels/title per side
        # Import UI positioning functions locally to ensure they're accessible in nested functions
        
        try:
            # Local WASD state stored on figure to persist across openings
            wasd = getattr(fig, '_cpc_wasd_state', None)
            if not isinstance(wasd, dict):
                wasd = {
                    'top':    {'spine': bool(ax.spines.get('top').get_visible()) if ax.spines.get('top') else False,
                               'ticks': bool(tick_state.get('t_ticks', tick_state.get('tx', False))),
                               'minor': bool(tick_state.get('mtx', False)),
                               'labels': bool(tick_state.get('t_labels', tick_state.get('tx', False))),
                               'title': bool(getattr(ax, '_top_xlabel_on', False))},
                    'bottom': {'spine': bool(ax.spines.get('bottom').get_visible()) if ax.spines.get('bottom') else True,
                               'ticks': bool(tick_state.get('b_ticks', tick_state.get('bx', True))),
                               'minor': bool(tick_state.get('mbx', False)),
                               'labels': bool(tick_state.get('b_labels', tick_state.get('bx', True))),
                               'title': bool(ax.get_xlabel())},
                    'left':   {'spine': bool(ax.spines.get('left').get_visible()) if ax.spines.get('left') else True,
                               'ticks': bool(tick_state.get('l_ticks', tick_state.get('ly', True))),
                               'minor': bool(tick_state.get('mly', False)),
                               'labels': bool(tick_state.get('l_labels', tick_state.get('ly', True))),
                               'title': bool(ax.get_ylabel())},
                    'right':  {'spine': bool(ax2.spines.get('right').get_visible()) if ax2.spines.get('right') else True,
                               'ticks': bool(tick_state.get('r_ticks', tick_state.get('ry', True))),
                               'minor': bool(tick_state.get('mry', False)),
                               'labels': bool(tick_state.get('r_labels', tick_state.get('ry', True))),
                               'title': bool(ax2.yaxis.get_label().get_text()) and bool(sc_eff.get_visible())},
                }
                setattr(fig, '_cpc_wasd_state', wasd)

            def _apply_wasd(changed_sides=None):
                assert sc_eff is not None
                # If no changed_sides specified, reposition all sides (for load style, etc.)
                if changed_sides is None:
                    changed_sides = {'bottom', 'top', 'left', 'right'}
                
                apply_wasd_spines(ax, wasd, sides=('top', 'bottom', 'left'))
                apply_wasd_spines(ax2, wasd, sides=('top', 'bottom', 'right'))
                apply_wasd_tick_params(ax, wasd, y_sides=('left',), y_mode='left')
                apply_wasd_tick_params(ax2, wasd, x_sides=(), y_sides=('right',), y_mode='right')

                # Titles
                try:
                    # Bottom X title
                    if bool(wasd['bottom']['title']):
                        # Restore stored xlabel if present
                        if hasattr(ax, '_stored_xlabel') and isinstance(ax._stored_xlabel, str) and ax._stored_xlabel:
                            ax.set_xlabel(ax._stored_xlabel)
                    else:
                        # Store once
                        if not hasattr(ax, '_stored_xlabel'):
                            try:
                                ax._stored_xlabel = ax.get_xlabel()
                            except Exception:
                                ax._stored_xlabel = ''
                        ax.set_xlabel("")
                except Exception:
                    pass
                try:
                    # Top X title - create a text artist positioned at the top
                    # First ensure we have the original xlabel text stored
                    if not hasattr(ax, '_stored_top_xlabel') or not ax._stored_top_xlabel:
                        # Try to get from current xlabel first
                        current_xlabel = ax.get_xlabel()
                        if current_xlabel:
                            ax._stored_top_xlabel = current_xlabel
                        # If still empty, try from stored bottom xlabel
                        elif hasattr(ax, '_stored_xlabel') and ax._stored_xlabel:
                            ax._stored_top_xlabel = ax._stored_xlabel
                        else:
                            ax._stored_top_xlabel = ''
                    
                    if bool(wasd['top']['title']) and ax._stored_top_xlabel:
                        # Get or create the top xlabel artist
                        if not hasattr(ax, '_top_xlabel_text') or ax._top_xlabel_text is None:
                            # Create a new text artist at the top center
                            ax._top_xlabel_text = ax.text(0.5, 1.0, '', transform=ax.transAxes,
                                                          ha='center', va='bottom',
                                                          fontsize=ax.xaxis.label.get_fontsize(),
                                                          fontfamily=ax.xaxis.label.get_fontfamily())
                        # Update text and make visible
                        ax._top_xlabel_text.set_text(ax._stored_top_xlabel)
                        ax._top_xlabel_text.set_visible(True)
                        
                        # Dynamic positioning based on top tick labels visibility
                        # Only reposition top if it's in changed_sides
                        if 'top' in changed_sides:
                            try:
                                # Get renderer for measurements
                                renderer = fig.canvas.get_renderer()
                                
                                # Base padding
                                labelpad = ax.xaxis.labelpad if hasattr(ax.xaxis, 'labelpad') else 4.0
                                fig_h = fig.get_size_inches()[1]
                                ax_bbox = ax.get_position()
                                ax_h_inches = ax_bbox.height * fig_h
                                base_pad_axes = (labelpad / 72.0) / ax_h_inches if ax_h_inches > 0 else 0.02
                                
                                # If top tick labels are visible, measure their height and add spacing
                                extra_offset = 0.0
                                if bool(wasd['top']['labels']) and renderer is not None:
                                    try:
                                        max_h_px = 0.0
                                        for t in ax.xaxis.get_major_ticks():
                                            lab = getattr(t, 'label2', None)  # Top labels are label2
                                            if lab is not None and lab.get_visible():
                                                bb = lab.get_window_extent(renderer=renderer)
                                                if bb is not None:
                                                    max_h_px = max(max_h_px, float(bb.height))
                                        # Convert pixels to axes coordinates
                                        if max_h_px > 0 and ax_h_inches > 0:
                                            dpi = float(fig.dpi) if hasattr(fig, 'dpi') else 100.0
                                            max_h_inches = max_h_px / dpi
                                            extra_offset = max_h_inches / ax_h_inches
                                    except Exception:
                                        # Fallback to fixed offset if labels are on
                                        extra_offset = 0.05
                                
                                total_offset = 1.0 + base_pad_axes + extra_offset
                                ax._top_xlabel_text.set_position((0.5, total_offset))
                            except Exception:
                                # Fallback positioning
                                if bool(wasd['top']['labels']):
                                    ax._top_xlabel_text.set_position((0.5, 1.07))
                                else:
                                    ax._top_xlabel_text.set_position((0.5, 1.02))
                    else:
                        # Hide top label
                        if hasattr(ax, '_top_xlabel_text') and ax._top_xlabel_text is not None:
                            ax._top_xlabel_text.set_visible(False)
                except Exception:
                    pass
                try:
                    # Left Y title
                    if bool(wasd['left']['title']):
                        if hasattr(ax, '_stored_ylabel') and isinstance(ax._stored_ylabel, str) and ax._stored_ylabel:
                            ax.set_ylabel(ax._stored_ylabel)
                    else:
                        if not hasattr(ax, '_stored_ylabel'):
                            try:
                                ax._stored_ylabel = ax.get_ylabel()
                            except Exception:
                                ax._stored_ylabel = ''
                        ax.set_ylabel("")
                except Exception:
                    pass
                try:
                    # Right Y title - simple approach like left/bottom
                    if bool(wasd['right']['title']) and bool(sc_eff.get_visible()):
                        if hasattr(ax2, '_stored_ylabel') and isinstance(ax2._stored_ylabel, str) and ax2._stored_ylabel:
                            ax2.set_ylabel(ax2._stored_ylabel)
                    else:
                        if not hasattr(ax2, '_stored_ylabel'):
                            try:
                                ax2._stored_ylabel = ax2.get_ylabel()
                            except Exception:
                                ax2._stored_ylabel = ''
                        ax2.set_ylabel("")
                except Exception:
                    pass
                
                # Only reposition sides that were actually changed
                # This prevents unnecessary title movement when toggling unrelated elements
                apply_changed_side_title_positions(
                    changed_sides,
                    bottom=lambda: _ui_position_bottom_xlabel(ax, fig, tick_state),
                    left=lambda: _ui_position_left_ylabel(ax, fig, tick_state),
                )

            def _print_wasd():
                _Cw = '\033[96m'; _Rw = '\033[0m'
                def b(v):
                    return 'ON ' if bool(v) else 'off'
                print(f"\033[1mToggle spines state:\033[0m")
                print(f"  {'Side':<8}  spine  major  minor  labels title")
                for side_key, side_code in [('top','w'),('bottom','s'),('left','a'),('right','d')]:
                    s = wasd[side_key]
                    print(f"  {_Cw}{side_code}={side_key:<6}{_Rw} {b(s['spine'])}  {b(s['ticks'])}   {b(s['minor'])}   {b(s['labels'])}  {b(s['title'])}")
                # Tick direction
                tick_dir = getattr(fig, '_tick_direction', 'out')
                print(f"  Tick direction  : {_Cw}{tick_dir}{_Rw}")
                # Tick lengths
                tl = getattr(fig, '_tick_lengths', {}) or {}
                maj_l = tl.get('major')
                min_l = tl.get('minor')
                if maj_l is not None:
                    min_str = f"  minor={min_l:.2g}" if min_l is not None else ""
                    print(f"  Tick length     : {_Cw}major={maj_l:.2g}{_Rw}{min_str}")
                else:
                    print(f"  Tick length     : default")
                # Tick spacing
                def _sp(loc):
                    try:
                        if isinstance(loc, MultipleLocator):
                            return str(loc._edge.step)
                        return "auto"
                    except Exception:
                        return "auto"
                def _mn(loc):
                    try:
                        if isinstance(loc, AutoMinorLocator):
                            return f"{loc._ndivs-1}/interval"
                        if isinstance(loc, NullLocator):
                            return "off"
                        return "auto"
                    except Exception:
                        return "auto"
                print(f"  Tick spacing    : {_Cw}x{_Rw}={_sp(ax.xaxis.get_major_locator())}  {_Cw}y{_Rw}={_sp(ax.yaxis.get_major_locator())}  {_Cw}r{_Rw}={_sp(ax2.yaxis.get_major_locator())}")
                print(f"  Minor count     : {_Cw}x{_Rw}={_mn(ax.xaxis.get_minor_locator())}  {_Cw}y{_Rw}={_mn(ax.yaxis.get_minor_locator())}  {_Cw}r{_Rw}={_mn(ax2.yaxis.get_minor_locator())}")

            def _sync_cpc_tick_state():
                sync_tick_state_from_wasd(
                    tick_state,
                    wasd,
                    tick_defaults={'top': False, 'bottom': True, 'left': True, 'right': True},
                    label_defaults={'top': False, 'bottom': True, 'left': True, 'right': True},
                )
                try:
                    ax._saved_tick_state = dict(tick_state)
                except Exception:
                    pass
            def _draw_cpc_spine_menu():
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
                sync_tick_state=_sync_cpc_tick_state,
                apply_wasd=_apply_wasd,
                draw=_draw_cpc_spine_menu,
                mode_label="CPC axes",
                back_label="CPC menu",
                axis_map={'x': ax.xaxis, 'y': ax.yaxis, 'r': ax2.yaxis},
                direction_axes=[ax, ax2],
                length_axes=[ax, ax2],
                on_quit=lambda: setattr(ax, '_saved_tick_state', dict(tick_state)),
                print_state=_print_wasd,
            )
            _print_menu(fig); return
        except Exception as e:
            print(f"Error in WASD tick menu: {e}")
        _print_menu(fig); return

    _print_menu(fig)
    pending_key = None
    while True:
        try:
            # Update current file's scatter artists for commands that need them
            sc_charge, sc_discharge, sc_eff = _get_current_file_artists(file_data, current_file_idx)
            assert sc_charge is not None
            assert sc_discharge is not None
            assert sc_eff is not None
            
            if pending_key is not None:
                key = pending_key
                pending_key = None
            else:
                key = _safe_input(_colorize_prompt("Press a key: ")).strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\n\nExiting interactive menu...")
            break
        if not key:
            continue

        action_ctx = CpcActionContext(
            fig=fig,
            ax=ax,
            ax2=ax2,
            sc_charge=sc_charge,
            sc_discharge=sc_discharge,
            sc_eff=sc_eff,
            file_data=file_data,
            file_paths=file_paths,
            is_multi_file=is_multi_file,
            tick_state=tick_state,
            safe_input=_safe_input,
            colorize_prompt=_colorize_prompt,
            colorize_inline_commands=_colorize_inline_commands,
            print_menu=_print_menu,
            choose_save_path=choose_save_path,
            choose_style_file=choose_style_file,
            list_files_in_subdirectory=list_files_in_subdirectory,
            get_organized_path=get_organized_path,
            ensure_exact_case_filename=ensure_exact_case_filename,
            natural_sort_key=natural_sort_key,
            dump_cpc_session=dump_cpc_session,
            format_file_timestamp=_format_file_timestamp,
            rebuild_legend=_rebuild_legend,
            style_snapshot=_style_snapshot,
            apply_style=_apply_style,
            get_geometry_snapshot=_get_geometry_snapshot,
            push_state=push_state,
            restore_state=restore_state,
        )
        
        if key == 'n':
            try:
                _toggle_crosshair_cpc()
            except Exception as e:
                print(f"Error toggling crosshair: {e}")
            _print_menu(fig)
            continue
        # File visibility toggle command (v)
        if key == 'v':
            try:
                if is_multi_file:
                    _print_file_list(file_data, current_file_idx)
                    print("  " + _colorize_menu("1, 1 2 3, 1-4: toggle file(s)"))
                    print("  " + _colorize_menu("a: toggle all"))
                    print("  " + _colorize_menu("q: back"))
                    choice = _safe_input(_colorize_prompt(f"Select file numbers (1-{len(file_data)}), a=all, q=back: ")).strip()
                    if choice.lower() == 'q':
                        _print_menu(fig)
                        _print_file_list(file_data, current_file_idx)
                        continue
                    
                    push_state("visibility")
                    indices_to_toggle = []
                    if choice.lower() in ('a', 'all'):
                        indices_to_toggle = list(range(len(file_data)))
                    else:
                        # Parse: "1", "1 2 3", "1,2,3", "1-4", or mixed "1 2-4"
                        parts = choice.replace(',', ' ').split()
                        for p in parts:
                            p = p.strip()
                            if not p:
                                continue
                            if '-' in p and p.count('-') == 1:
                                try:
                                    lo, hi = p.split('-')
                                    lo_i = int(lo.strip()) - 1
                                    hi_i = int(hi.strip()) - 1
                                    for i in range(lo_i, hi_i + 1):
                                        if 0 <= i < len(file_data):
                                            indices_to_toggle.append(i)
                                except ValueError:
                                    pass
                            else:
                                try:
                                    idx = int(p) - 1
                                    if 0 <= idx < len(file_data):
                                        indices_to_toggle.append(idx)
                                except ValueError:
                                    pass
                        indices_to_toggle = sorted(set(indices_to_toggle))
                    
                    if indices_to_toggle:
                        for idx in indices_to_toggle:
                            f = file_data[idx]
                            new_vis = not f.get('visible', True)
                            f['visible'] = new_vis
                            f['sc_charge'].set_visible(new_vis)
                            f['sc_discharge'].set_visible(new_vis)
                            f['sc_eff'].set_visible(new_vis)
                        _rebuild_legend(ax, ax2, file_data, preserve_position=True)
                        fig.canvas.draw_idle()
                        names = [file_data[i].get('filename', f'File {i+1}') for i in indices_to_toggle]
                        print(f"Toggled: {', '.join(names)}")
                    else:
                        print("Invalid input. Use: 1, 1 2 3, 1-4, a, or q.")
                else:
                    # Single file mode: v is not meaningful (no per-file visibility)
                    print("File visibility (v) is only available in multi-file CPC mode.")
            except ValueError:
                print("Invalid input. Use: 1, 1 2 3, 1-4, a, or q.")
            except Exception as e:
                print(f"Visibility toggle failed: {e}")
            _print_menu(fig)
            if is_multi_file:
                _print_file_list(file_data, current_file_idx)
            continue
        
        if key == 'q':
            if canvas_mode:
                break
            try:
                confirm = _safe_input(_colorize_prompt("Quit CPC interactive? Remember to save (e=export, s=save). Quit now? (y/n): ")).strip().lower()
            except Exception:
                confirm = 'y'
            if confirm == 'y':
                break
            elif confirm in ('e', 's'):
                pending_key = confirm
                continue
            else:
                _print_menu(fig); continue
        elif key == 'b':
            handle_undo(action_ctx)
            continue
        elif key == 'c':
            try:
                run_cpc_color_menu(
                    fig=fig,
                    ax=ax,
                    ax2=ax2,
                    file_data=file_data,
                    is_multi_file=is_multi_file,
                    sc_charge=sc_charge,
                    sc_eff=sc_eff,
                    push_state=push_state,
                    set_spine_color=_set_spine_color,
                    rebuild_legend=_rebuild_legend,
                    safe_input=_safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=_colorize_prompt,
                )
            except Exception as e:
                print(f"Error in colors menu: {e}")
            _print_menu(fig)
            if is_multi_file:
                _print_file_list(file_data, current_file_idx)
            continue
        elif key == 'k':
            # Spine colors (w=top, a=left, s=bottom, d=right)
            try:
                while True:
                    print("\nSet spine colors (with matching tick and label colors):")
                    print(_colorize_inline_commands("  w : top spine    | a : left spine"))
                    print(_colorize_inline_commands("  s : bottom spine | d : right spine"))
                    print(_colorize_inline_commands("Example: w:red a:#4561F7 s:blue d:green"))
                    # Add auto function when only one file is loaded
                    if not is_multi_file:
                        auto_enabled = getattr(fig, '_cpc_spine_auto', False)
                        auto_status = "ON" if auto_enabled else "OFF"
                        print(_colorize_inline_commands(f"  auto : auto-apply capacity color to left y-axis, efficiency to right y-axis [{auto_status}]"))
                    print("  " + _colorize_menu("q: back to main menu"))
                    line = _safe_input(_colorize_prompt("Enter mappings (e.g., w:red a:#4561F7, q=back): ")).strip()
                    if not line or line.lower() == 'q':
                        break
                    # Handle auto toggle when only one file is loaded
                    if not is_multi_file and line.lower() in ('a', 'auto'):
                        auto_enabled = getattr(fig, '_cpc_spine_auto', False)
                        if auto_enabled:
                            # Turning OFF: push current (auto ON) state first so undo restores it
                            push_state("color-spine-auto")
                        fig._cpc_spine_auto = not auto_enabled
                        new_status = "ON" if fig._cpc_spine_auto else "OFF"
                        print(f"Auto mode: {new_status}")
                        if fig._cpc_spine_auto:
                            # Turning ON: push state, then apply auto colors
                            push_state("color-spine-auto")
                            try:
                                # Draw first so tick objects exist (even when right axis was hidden)
                                fig.canvas.draw_idle()
                                # Get capacity curve color (charge color)
                                charge_col = _normalize_spine_color(_color_of(sc_charge))
                                # Get efficiency curve color
                                eff_col = _normalize_spine_color(_color_of(sc_eff))
                                if charge_col and eff_col:
                                    _set_spine_color('left', charge_col)
                                    _set_spine_color('right', eff_col)
                                    print(f"Applied: left y-axis = {charge_col}, right y-axis = {eff_col}")
                                else:
                                    print("Could not get charge/efficiency colors from artists.")
                                fig.canvas.draw()
                            except Exception as e:
                                print(f"Error applying auto colors: {e}")
                        continue
                    push_state("color-spine")
                    # Draw first so tick objects exist (even when right axis was hidden)
                    try:
                        fig.canvas.draw_idle()
                    except Exception:
                        pass
                    # Map wasd to spine names
                    key_to_spine = {'w': 'top', 'a': 'left', 's': 'bottom', 'd': 'right'}
                    tokens = line.split()
                    manual_change_made = False
                    for token in tokens:
                        if ':' not in token:
                            # Skip auto keyword silently (handled above)
                            if token.lower() not in ('a', 'auto'):
                                print(f"Skip malformed token: {token}")
                            continue
                        key_part, color = token.split(':', 1)
                        key_part = key_part.lower()
                        if key_part not in key_to_spine:
                            print(f"Unknown key: {key_part} (use w/a/s/d)")
                            continue
                        spine_name = key_to_spine[key_part]
                        resolved = resolve_color_token(color, fig)
                        _set_spine_color(spine_name, resolved)
                        print(f"Set {spine_name} spine to {resolved}")
                        manual_change_made = True
                    # Disable auto mode if manual changes were made
                    if manual_change_made and not is_multi_file and getattr(fig, '_cpc_spine_auto', False):
                        fig._cpc_spine_auto = False
                        print("Auto mode disabled (manual spine color set)")
                    fig.canvas.draw()
            except Exception as e:
                print(f"Error in spine color menu: {e}")
            _print_menu(fig)
            if is_multi_file:
                _print_file_list(file_data, current_file_idx)
            continue
        elif key == 'e':
            handle_figure_export(action_ctx)
            continue
        elif key == 's':
            handle_save_session(action_ctx)
            continue
        elif key == 'p':
            handle_style_export(action_ctx)
            continue
        elif key == 'i':
            handle_style_import(action_ctx)
            continue
        elif key == 'd':
            # Display mode: charge-only / discharge-only / both
            try:
                while True:
                    print("\nDisplay mode for CPC:")
                    print("  " + _colorize_menu("c: show only charge capacity (hide discharge)"))
                    print("  " + _colorize_menu("d: show only discharge capacity (hide charge)"))
                    print("  " + _colorize_menu("b: show both charge and discharge"))
                    print("  " + _colorize_menu("q: back"))
                    sub = _safe_input(_colorize_prompt("Display (c/d/b/q): ")).strip().lower()
                    if not sub or sub == 'q':
                        break
                    if sub == 'c':
                        push_state("display-charge")
                        for f in file_data:
                            sc_c = f.get('sc_charge')
                            sc_d = f.get('sc_discharge')
                            if sc_c is not None:
                                sc_c.set_visible(True)
                            if sc_d is not None:
                                sc_d.set_visible(False)
                        try:
                            fig._cpc_display_mode = "charge"
                        except Exception:
                            pass
                    elif sub == 'd':
                        push_state("display-discharge")
                        for f in file_data:
                            sc_c = f.get('sc_charge')
                            sc_d = f.get('sc_discharge')
                            if sc_c is not None:
                                sc_c.set_visible(False)
                            if sc_d is not None:
                                sc_d.set_visible(True)
                        try:
                            fig._cpc_display_mode = "discharge"
                        except Exception:
                            pass
                    elif sub == 'b':
                        push_state("display-both")
                        for f in file_data:
                            sc_c = f.get('sc_charge')
                            sc_d = f.get('sc_discharge')
                            if sc_c is not None:
                                sc_c.set_visible(True)
                            if sc_d is not None:
                                sc_d.set_visible(True)
                        try:
                            fig._cpc_display_mode = "both"
                        except Exception:
                            pass
                    else:
                        print("Unknown choice (use c, d, b, or q).")
                    _rebuild_legend(ax, ax2, file_data, preserve_position=True)
                    fig.canvas.draw_idle()
            except Exception as e:
                print(f"Display mode change failed: {e}")
            _print_menu(fig)
            if is_multi_file:
                _print_file_list(file_data, current_file_idx)
            continue
        elif key == 'ry':
            # Toggle efficiency visibility on the right axis
            try:
                push_state("toggle-eff")
                
                # Capture current legend position BEFORE toggling visibility
                # This ensures the position is preserved when legend is rebuilt
                try:
                    if not hasattr(fig, '_cpc_legend_xy_in') or getattr(fig, '_cpc_legend_xy_in') is None:
                        leg0 = ax.get_legend()
                        if leg0 is not None and leg0.get_visible():
                            try:
                                # Ensure renderer exists
                                try:
                                    renderer = fig.canvas.get_renderer()
                                except Exception:
                                    fig.canvas.draw()
                                    renderer = fig.canvas.get_renderer()
                                bb = leg0.get_window_extent(renderer=renderer)
                                cx = 0.5 * (bb.x0 + bb.x1)
                                cy = 0.5 * (bb.y0 + bb.y1)
                                fx, fy = fig.transFigure.inverted().transform((cx, cy))
                                fw, fh = fig.get_size_inches()
                                offset = ((fx - 0.5) * fw, (fy - 0.5) * fh)
                                offset = _sanitize_legend_offset(offset)
                                if offset is not None:
                                    fig._cpc_legend_xy_in = offset
                            except Exception:
                                pass
                except Exception:
                    pass
                
                # Determine current visibility state (check if any efficiency is visible)
                if is_multi_file:
                    # In multi-file mode, check if any efficiency is visible
                    any_eff_visible = any(f.get('sc_eff', {}).get_visible() if hasattr(f.get('sc_eff'), 'get_visible') else True for f in file_data if f.get('sc_eff'))
                    new_vis = not any_eff_visible
                else:
                    # Single file mode
                    vis = bool(sc_eff.get_visible()) if hasattr(sc_eff, 'get_visible') else True
                    new_vis = not vis
                
                # 1. Hide/show efficiency points (all files in multi-file mode)
                if is_multi_file:
                    for f in file_data:
                        eff_sc = f.get('sc_eff')
                        if eff_sc is not None:
                            try:
                                eff_sc.set_visible(new_vis)
                            except Exception:
                                pass
                else:
                    sc_eff.set_visible(new_vis)
                
                # 2. Hide/show right y-axis title
                try:
                    ax2.yaxis.label.set_visible(new_vis)
                except Exception:
                    pass
                
                # 3. Hide/show right y-axis ticks and labels (only affect ax2, don't touch ax)
                try:
                    ax2.tick_params(axis='y', right=new_vis, labelright=new_vis)
                    # Update tick_state
                    tick_state['ry'] = bool(new_vis)
                except Exception:
                    pass
                
                # Persist WASD state so save/load and styles honor the toggle
                try:
                    wasd = getattr(fig, '_cpc_wasd_state', None)
                    if not isinstance(wasd, dict):
                        wasd = {
                            'top':    {'spine': bool(ax.spines.get('top').get_visible()) if ax.spines.get('top') else False,
                                       'ticks': bool(tick_state.get('t_ticks', tick_state.get('tx', False))),
                                       'minor': bool(tick_state.get('mtx', False)),
                                       'labels': bool(tick_state.get('t_labels', tick_state.get('tx', False))),
                                       'title': bool(getattr(ax, '_top_xlabel_on', False))},
                            'bottom': {'spine': bool(ax.spines.get('bottom').get_visible()) if ax.spines.get('bottom') else True,
                                       'ticks': bool(tick_state.get('b_ticks', tick_state.get('bx', True))),
                                       'minor': bool(tick_state.get('mbx', False)),
                                       'labels': bool(tick_state.get('b_labels', tick_state.get('bx', True))),
                                       'title': bool(ax.xaxis.label.get_visible()) and bool(ax.get_xlabel())},
                            'left':   {'spine': bool(ax.spines.get('left').get_visible()) if ax.spines.get('left') else True,
                                       'ticks': bool(tick_state.get('l_ticks', tick_state.get('ly', True))),
                                       'minor': bool(tick_state.get('mly', False)),
                                       'labels': bool(tick_state.get('l_labels', tick_state.get('ly', True))),
                                       'title': bool(ax.yaxis.label.get_visible()) and bool(ax.get_ylabel())},
                            'right':  {'spine': bool(ax2.spines.get('right').get_visible()) if ax2.spines.get('right') else True,
                                       'ticks': bool(tick_state.get('r_ticks', tick_state.get('ry', True))),
                                       'minor': bool(tick_state.get('mry', False)),
                                       'labels': bool(tick_state.get('r_labels', tick_state.get('ry', True))),
                                       'title': bool(ax2.yaxis.label.get_visible()) and bool(ax2.get_ylabel())},
                        }
                    wasd.setdefault('right', {})
                    wasd['right']['ticks'] = bool(new_vis)
                    wasd['right']['labels'] = bool(new_vis)
                    wasd['right']['title'] = bool(new_vis)
                    setattr(fig, '_cpc_wasd_state', wasd)
                except Exception:
                    pass
                
                # 4. Rebuild legend to remove/add efficiency entries (preserve position)
                _rebuild_legend(ax, ax2, file_data, preserve_position=True)
                
                fig.canvas.draw_idle()
            except Exception:
                pass
            _print_menu(fig); continue
        elif key == 'h':
            # Legend submenu: toggle visibility and move legend in inches relative to canvas center.
            try:

                def _cpc_toggle_legend():
                    try:
                        leg = ax.get_legend()
                        if leg is not None and leg.get_visible():
                            leg.set_visible(False)
                        else:
                            handles, _labels = _visible_handles_labels(ax, ax2)
                            if handles:
                                _rebuild_legend(ax, ax2, file_data, preserve_position=True)
                            else:
                                print("No visible legend items found.")
                        fig.canvas.draw_idle()
                    except Exception as e:
                        print(f"Error toggling legend: {e}")
                        traceback.print_exc()

                def _cpc_apply_legend_pos():
                    _apply_legend_position()
                    fig.canvas.draw_idle()

                run_legend_position_menu(
                    fig=fig,
                    get_legend=ax.get_legend,
                    get_position=lambda: getattr(fig, '_cpc_legend_xy_in', (0.0, 0.0)),
                    set_position=lambda xy: setattr(fig, '_cpc_legend_xy_in', xy),
                    sanitize_offset=_sanitize_legend_offset,
                    toggle_legend=_cpc_toggle_legend,
                    apply_position=_cpc_apply_legend_pos,
                    push_state=push_state,
                    safe_input=_safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=_colorize_prompt,
                )
            except Exception:
                pass
            _print_menu(fig); continue
        elif key == 'f':
            def _apply_cpc_font_family(fam):
                push_state("font-family")
                set_font_family_defaults(fam, sans_serif_stack=True)
                artists = []
                for a in (ax, ax2):
                    artists.extend(axis_text_artists(a))
                artists.extend([
                    getattr(ax, '_top_xlabel_artist', None),
                    getattr(ax, '_top_xlabel_text', None),
                    getattr(ax2, '_right_ylabel_artist', None),
                ])
                try:
                    artists.extend(legend_text_artists(ax.get_legend()))
                except Exception:
                    pass
                apply_font_family_to_artists(artists, fam)
                fig.canvas.draw_idle()
            def _apply_cpc_font_size(size):
                push_state("font-size")
                set_font_size_default(size)
                artists = []
                for a in (ax, ax2):
                    artists.extend(axis_text_artists(a))
                artists.extend([
                    getattr(ax, '_top_xlabel_artist', None),
                    getattr(ax, '_top_xlabel_text', None),
                    getattr(ax2, '_right_ylabel_artist', None),
                ])
                try:
                    artists.extend(legend_text_artists(ax.get_legend()))
                except Exception:
                    pass
                apply_font_size_to_artists(artists, size)
                fig.canvas.draw_idle()
            run_font_menu(
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
                get_current_family=lambda: plt.rcParams.get('font.sans-serif', [''])[0],
                get_current_size=lambda: plt.rcParams.get('font.size', None),
                apply_family=_apply_cpc_font_family,
                apply_size=_apply_cpc_font_size,
                blank_exits=True,
            )
            _print_menu(fig); continue
        elif key == 'l':
            # Line widths submenu: frame/ticks vs grid
            try:
                while True:
                    # Show current widths summary
                    try:
                        cur_sp_lw = {name: (ax.spines.get(name).get_linewidth() if ax.spines.get(name) else None)
                                      for name in ('bottom','top','left','right')}
                    except Exception:
                        cur_sp_lw = {}
                    x_maj = current_tick_width(ax.xaxis, 'major')
                    x_min = current_tick_width(ax.xaxis, 'minor')
                    ly_maj = current_tick_width(ax.yaxis, 'major')
                    ly_min = current_tick_width(ax.yaxis, 'minor')
                    ry_maj = current_tick_width(ax2.yaxis, 'major')
                    ry_min = current_tick_width(ax2.yaxis, 'minor')
                    print("Line widths:")
                    if cur_sp_lw:
                        print("  Frame spines lw:", 
                              " ".join(f"{k}={v:.3g}" if isinstance(v,(int,float)) else f"{k}=?" for k,v in cur_sp_lw.items()))
                    print(f"  Tick widths: xM={x_maj if x_maj is not None else '?'} xm={x_min if x_min is not None else '?'} lyM={ly_maj if ly_maj is not None else '?'} lym={ly_min if ly_min is not None else '?'} ryM={ry_maj if ry_maj is not None else '?'} rym={ry_min if ry_min is not None else '?'}")
                    print("\033[1mLine submenu:\033[0m")
                    print(f"  {_colorize_menu('f  : change frame (axes spines) and tick widths')}")
                    print(f"  {_colorize_menu('g  : toggle grid lines')}")
                    print(f"  {_colorize_menu('q  : return')}")
                    sub = _safe_input(_colorize_prompt("Choose (f/g/q): ")).strip().lower()
                    if not sub:
                        continue
                    if sub == 'q':
                        break
                    if sub == 'f':
                        fw_in = _safe_input("Enter frame/tick width (e.g., 1.5) or 'm M' (major minor) or q: ").strip()
                        if not fw_in or fw_in.lower() == 'q':
                            print("Canceled.")
                            continue
                        try:
                            push_state("framewidth")
                            frame_w, tick_major, tick_minor = parse_frame_tick_widths(fw_in)
                            apply_frame_and_tick_widths(
                                [ax, ax2],
                                frame_width=frame_w,
                                major_width=tick_major,
                                minor_width=tick_minor,
                            )
                            fig.canvas.draw()
                            print(f"Set frame width={frame_w}, major tick width={tick_major}, minor tick width={tick_minor}")
                        except ValueError:
                            print("Invalid numeric value(s).")
                    elif sub == 'g':
                        push_state("grid")
                        # Toggle grid state - check if any gridlines are visible
                        current_grid = False
                        try:
                            # Check if grid is currently on by looking at gridline visibility
                            for line in ax.get_xgridlines() + ax.get_ygridlines():
                                if line.get_visible():
                                    current_grid = True
                                    break
                        except Exception:
                            current_grid = ax.xaxis._gridOnMajor if hasattr(ax.xaxis, '_gridOnMajor') else False
                        
                        new_grid_state = not current_grid
                        if new_grid_state:
                            # Enable grid with light styling
                            ax.grid(True, color='0.85', linestyle='-', linewidth=0.5, alpha=0.7)
                        else:
                            # Disable grid
                            ax.grid(False)
                        fig.canvas.draw()
                        print(f"Grid {'enabled' if new_grid_state else 'disabled'}.")
                    else:
                        print("Unknown option.")
            except Exception as e:
                print(f"Error in line submenu: {e}")
            _print_menu(fig); continue
        elif key == 'm':
            try:
                while True:
                    print("Current marker sizes:")
                    try:
                        c_ms = getattr(sc_charge, 'get_sizes', lambda: [32])()[0]
                    except Exception:
                        c_ms = 32
                    try:
                        d_ms = getattr(sc_discharge, 'get_sizes', lambda: [32])()[0]
                    except Exception:
                        d_ms = 32
                    try:
                        e_ms = getattr(sc_eff, 'get_sizes', lambda: [40])()[0]
                    except Exception:
                        e_ms = 40
                    print(f"  charge ms={c_ms}, discharge ms={d_ms}, efficiency ms={e_ms}")
                    spec = _safe_input("Set new marker size for all series (q=back): ").strip().lower()
                    if not spec or spec == 'q':
                        break
                    try:
                        num = float(spec)
                        push_state("marker-size")
                        # Apply to current file's artists
                        if hasattr(sc_charge, 'set_sizes'):
                            sc_charge.set_sizes([num])
                        if hasattr(sc_discharge, 'set_sizes'):
                            sc_discharge.set_sizes([num])
                        if hasattr(sc_eff, 'set_sizes'):
                            sc_eff.set_sizes([num])
                        # In multi-file mode, also apply to all files' capacity/efficiency
                        if is_multi_file and file_data:
                            for f in file_data:
                                ch = f.get('sc_charge')
                                dh = f.get('sc_discharge')
                                ef = f.get('sc_eff')
                                try:
                                    if ch is not None and hasattr(ch, 'set_sizes'):
                                        ch.set_sizes([num])
                                except Exception:
                                    pass
                                try:
                                    if dh is not None and hasattr(dh, 'set_sizes'):
                                        dh.set_sizes([num])
                                except Exception:
                                    pass
                                try:
                                    if ef is not None and hasattr(ef, 'set_sizes'):
                                        ef.set_sizes([num])
                                except Exception:
                                    pass
                        fig.canvas.draw_idle()
                    except Exception:
                        print("Invalid value.")
            except Exception as e:
                print(f"Error: {e}")
            _print_menu(fig); continue
        elif key == 't':
            _handle_key_t()
            continue
        elif key == 'g':
            def _resize_cpc_frame():
                try:
                    push_state("resize-frame")
                    resize_plot_frame(fig, ax, [], [], type('Args', (), {'stack': False})(), lambda *_: None)
                except Exception as e:
                    print(f"Resize failed: {e}")
            def _resize_cpc_canvas():
                try:
                    push_state("resize-canvas")
                    resize_canvas(fig, ax)
                except Exception as e:
                    print(f"Resize failed: {e}")
            run_option_menu(
                prompt="Geom (p/c/q): ",
                options={
                    "p": ("plot frame", _resize_cpc_frame),
                    "c": ("canvas", _resize_cpc_canvas),
                },
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
            )
            _print_menu(fig); continue
        elif key == 'r':
            run_cpc_rename_menu(
                fig=fig,
                ax=ax,
                ax2=ax2,
                file_data=file_data,
                current_file_idx=current_file_idx,
                is_multi_file=is_multi_file,
                push_state=push_state,
                rebuild_legend=_rebuild_legend,
                print_file_list=_print_file_list,
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
            )
            _print_menu(fig); continue
        elif key == 'x':
            def _draw_cpc_x_range():
                try:
                    ax.relim()
                    ax.autoscale_view(scalex=True, scaley=False)
                except Exception:
                    pass
                try:
                    leg = ax.get_legend()
                    if leg is not None and leg.get_visible():
                        _apply_legend_position()
                except Exception:
                    pass
                fig.canvas.draw_idle()
            def _auto_cpc_x_range():
                try:
                    all_x = []
                    for sc in [sc_charge, sc_discharge]:
                        if sc is not None and hasattr(sc, 'get_offsets'):
                            offsets = sc.get_offsets()
                            if offsets.size > 0:
                                all_x.extend([offsets[:, 0].min(), offsets[:, 0].max()])
                    if all_x:
                        ax.set_xlim(min(all_x), max(all_x))
                    else:
                        print("No original data available.")
                except Exception as e:
                    print(f"Error restoring original X range: {e}")
            run_axis_limit_menu(
                axis_name="X",
                prompt_name="X",
                get_limits=ax.get_xlim,
                set_limits=lambda lo, hi: ax.set_xlim(lo, hi),
                auto_limits=_auto_cpc_x_range,
                push_state=push_state,
                state_label="x-range",
                draw=_draw_cpc_x_range,
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
                invalid_message="Invalid numbers.",
            )
            _print_menu(fig); continue
        elif key == 'y':
            def _redraw_cpc_left_y():
                try:
                    ax.relim()
                    ax.autoscale_view(scalex=False, scaley=True)
                except Exception:
                    pass
                try:
                    leg = ax.get_legend()
                    if leg is not None and leg.get_visible():
                        _apply_legend_position()
                except Exception:
                    pass
                fig.canvas.draw_idle()
            def _redraw_cpc_right_y():
                try:
                    ax2.relim()
                    ax2.autoscale_view(scalex=False, scaley=True)
                except Exception:
                    pass
                try:
                    leg = ax.get_legend()
                    if leg is not None and leg.get_visible():
                        _apply_legend_position()
                except Exception:
                    pass
                fig.canvas.draw_idle()
            def _auto_cpc_left_y():
                try:
                    all_y = []
                    for sc in [sc_charge, sc_discharge]:
                        if sc is not None and hasattr(sc, 'get_offsets'):
                            offsets = sc.get_offsets()
                            if offsets.size > 0:
                                all_y.extend([offsets[:, 1].min(), offsets[:, 1].max()])
                    if all_y:
                        ax.set_ylim(min(all_y), max(all_y))
                    else:
                        print("No original data available.")
                except Exception as e:
                    print(f"Error restoring original left Y range: {e}")
            def _auto_cpc_right_y():
                try:
                    if sc_eff is not None and hasattr(sc_eff, 'get_offsets'):
                        offsets = sc_eff.get_offsets()
                        if offsets.size > 0:
                            ax2.set_ylim(float(offsets[:, 1].min()), float(offsets[:, 1].max()))
                        else:
                            print("No original data available.")
                    else:
                        print("No original data available.")
                except Exception as e:
                    print(f"Error restoring original right Y range: {e}")
            def _run_cpc_left_y_menu():
                run_axis_limit_menu(
                    axis_name="left Y",
                    prompt_name="Left Y",
                    get_limits=ax.get_ylim,
                    set_limits=lambda lo, hi: ax.set_ylim(lo, hi),
                    auto_limits=_auto_cpc_left_y,
                    push_state=push_state,
                    state_label="y-left-range",
                    draw=_redraw_cpc_left_y,
                    safe_input=_safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=_colorize_prompt,
                    invalid_message="Invalid numbers.",
                )
            def _run_cpc_right_y_menu():
                assert sc_eff is not None
                try:
                    eff_on = bool(sc_eff.get_visible())
                except Exception:
                    eff_on = True
                if not eff_on:
                    print("Right Y is not shown; enable efficiency with 'ry' first.")
                    return
                run_axis_limit_menu(
                    axis_name="right Y",
                    prompt_name="Right Y",
                    get_limits=ax2.get_ylim,
                    set_limits=lambda lo, hi: ax2.set_ylim(lo, hi),
                    auto_limits=_auto_cpc_right_y,
                    push_state=push_state,
                    state_label="y-right-range",
                    draw=_redraw_cpc_right_y,
                    safe_input=_safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=_colorize_prompt,
                    invalid_message="Invalid numbers.",
                )
            run_dispatch_menu(
                prompt="Y-axis target (ly=left capacity, ry=right efficiency, q=back): ",
                options={
                    "ly": "left Y-axis (capacity)",
                    "ry": "right Y-axis (efficiency)",
                },
                handle_choice=lambda choice: _run_cpc_left_y_menu() if choice == 'ly' else (_run_cpc_right_y_menu() if choice == 'ry' else print("Unknown Y target.")),
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
            )
            _print_menu(fig); continue
        elif key == 'ie':
            # Invert coulombic efficiency values around 100% for the current file(s)
            try:
                if sc_eff is None or not hasattr(sc_eff, 'get_offsets'):
                    print("No efficiency data to invert.")
                    _print_menu(fig); continue
                if is_multi_file:
                    _print_file_list(file_data, current_file_idx)
                    choice = _safe_input(
                        f"Select file numbers (1-{len(file_data)}) to invert efficiency, a for all, or q=cancel: "
                    ).strip().lower()
                    if not choice or choice == 'q':
                        _print_menu(fig); continue
                    targets = []
                    if choice in ('a', 'all'):
                        targets = list(range(len(file_data)))
                    else:
                        try:
                            idx = int(choice) - 1
                            if 0 <= idx < len(file_data):
                                targets = [idx]
                            else:
                                print("Invalid file number.")
                                _print_menu(fig); continue
                        except ValueError:
                            print("Invalid choice.")
                            _print_menu(fig); continue
                    push_state("invert-efficiency")
                    for idx in targets:
                        f = file_data[idx]
                        eff_sc = f.get('sc_eff')
                        if eff_sc is None or not hasattr(eff_sc, 'get_offsets'):
                            continue
                        offsets = eff_sc.get_offsets()
                        if offsets.size == 0:
                            continue
                        xs = offsets[:, 0]
                        ys = offsets[:, 1]
                        # Invert around 100% (y -> 100 - y + 100 = 200 - y)
                        new_ys = 200.0 - ys
                        eff_sc.set_offsets(list(zip(xs, new_ys)))
                    fig.canvas.draw_idle()
                    print("Inverted efficiency for selected file(s).")
                else:
                    offsets = sc_eff.get_offsets()
                    if offsets.size == 0:
                        print("No efficiency data to invert.")
                        _print_menu(fig); continue
                    xs = offsets[:, 0]
                    ys = offsets[:, 1]
                    push_state("invert-efficiency")
                    new_ys = 200.0 - ys
                    sc_eff.set_offsets(list(zip(xs, new_ys)))
                    fig.canvas.draw_idle()
                    print("Inverted efficiency for current dataset.")
            except Exception as e:
                print(f"Error in efficiency inversion: {e}")
            _print_menu(fig); continue
        elif key == 'oe':
            handle_quick_overwrite_figure(action_ctx)
            continue
        elif key == 'os':
            handle_quick_overwrite_session(action_ctx)
            continue
        elif key in ('ops', 'opsg'):
            handle_quick_overwrite_style(action_ctx, include_geometry=(key == 'opsg'))
            continue
        else:
            print("Unknown key.")
            _print_menu(fig); continue


__all__ = ["cpc_interactive_menu"]

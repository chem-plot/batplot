"""CPC style snapshot / apply (mode-owned, extracted from interactive).

Keeps ``.bps`` / ``.bpsg`` / undo / batch style contracts identical to the
previous ``interactive`` implementations. Interactive menu re-exports these
symbols for backward-compatible imports.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

import numpy as np  # type: ignore[import]
import matplotlib.pyplot as plt  # type: ignore[import]
from matplotlib.colors import to_hex  # type: ignore[import]
from matplotlib.ticker import (  # type: ignore[import]
    AutoMinorLocator,
    MultipleLocator,
    NullFormatter,
    NullLocator,
)

from ...ui import (
    set_spine_side_color as _ui_set_spine_side_color,
    finalize_spine_colors_cpc,
    capture_axis_tick_locators,
    restore_axis_tick_locators,
    position_top_xlabel as _ui_position_top_xlabel,
    position_right_ylabel as _ui_position_right_ylabel,
    position_bottom_xlabel as _ui_position_bottom_xlabel,
    position_left_ylabel as _ui_position_left_ylabel,
)
from ..common.fonts import collect_fig_font_artists, legend_text_artists
from ..common.font_extras import (
    apply_font_extras_from_cfg,
    apply_session_font_cfg,
    font_extras_export_dict,
)
from ..common.spines import sync_tick_state_from_wasd, current_tick_width
from .legend import (
    _coerce_legend_color,
    _color_of,
    _get_legend_title,
    _normalize_spine_color,
    _rebuild_legend,
    _sanitize_legend_offset,
)


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


def _cpc_font_artists(ax, ax2, fig=None):
    if fig is None:
        try:
            fig = ax.get_figure()
        except Exception:
            fig = None
    artists: list = []
    for a in (ax, ax2):
        if a is None:
            continue
        artists.extend(collect_fig_font_artists(a, fig, include_title=True))
    try:
        artists.extend(legend_text_artists(ax.get_legend()))
    except Exception:
        pass
    return artists


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
        return current_tick_width(axis_obj, which)
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
        'font': {'family': fam0, 'size': fsize, 'mathtext_fontset': mathtext_fs, **font_extras_export_dict(fig)},
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
        'axis_labels': {
            'xlabel': ax.get_xlabel() or getattr(ax, '_stored_xlabel', '') or '',
            'ylabel_left': ax.get_ylabel() or getattr(ax, '_stored_ylabel', '') or '',
            'ylabel_right': ax2.get_ylabel() or getattr(ax2, '_stored_ylabel', '') or '',
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
                'efficiency_visible': bool(getattr(sc_eff, 'get_visible', lambda: True)()) if sc_eff else True,
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

    axis_labels = cfg.get('axis_labels') or {}
    try:
        if axis_labels.get('xlabel'):
            ax.set_xlabel(str(axis_labels['xlabel']))
            ax._stored_xlabel = str(axis_labels['xlabel'])
        if axis_labels.get('ylabel_left'):
            ax.set_ylabel(str(axis_labels['ylabel_left']))
            ax._stored_ylabel = str(axis_labels['ylabel_left'])
        if axis_labels.get('ylabel_right') and ax2 is not None:
            ax2.set_ylabel(str(axis_labels['ylabel_right']))
            ax2._stored_ylabel = str(axis_labels['ylabel_right'])
    except Exception:
        pass
    
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
            try:
                apply_font_extras_from_cfg(fig, _cpc_font_artists(ax, ax2, fig), font)
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
                        ax2.set_visible(eff_vis)
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
                            eff_vis = bool(ef['visible'])
                            sc_eff.set_visible(eff_vis)
                            ax2.set_visible(eff_vis)
                            ax2.yaxis.label.set_visible(eff_vis)
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
                if 'single_file_effective' in leg_cfg:
                    fig._cpc_legend_single_file_effective = bool(leg_cfg.get('single_file_effective'))
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
                # Use WASD state (ticks and labels are independent)
                b_ticks = bool(wasd.get('bottom', {}).get('ticks', True))
                t_ticks = bool(wasd.get('top', {}).get('ticks', False))
                l_ticks = bool(wasd.get('left', {}).get('ticks', True))
                r_ticks = bool(wasd.get('right', {}).get('ticks', True))
                b_labels = bool(wasd.get('bottom', {}).get('labels', True))
                t_labels = bool(wasd.get('top', {}).get('labels', False))
                l_labels = bool(wasd.get('left', {}).get('labels', True))
                r_labels = bool(wasd.get('right', {}).get('labels', True))
                mbx = bool(wasd.get('bottom', {}).get('minor', False))
                mtx = bool(wasd.get('top', {}).get('minor', False))
                mly = bool(wasd.get('left', {}).get('minor', False))
                mry = bool(wasd.get('right', {}).get('minor', False))
                # Legacy combined flags (kept for older callers that only check bx/tx/…)
                bx = bool(b_ticks and b_labels)
                tx = bool(t_ticks and t_labels)
                ly = bool(l_ticks and l_labels)
                ry = bool(r_ticks and r_labels)
            else:
                # Fall back to old visibility dict (combined tick+label flags)
                vis = tk.get('visibility', {})
                bx = bool(vis.get('bx', True))
                tx = bool(vis.get('tx', False))
                ly = bool(vis.get('ly', True))
                ry = bool(vis.get('ry', True))
                b_ticks = b_labels = bx
                t_ticks = t_labels = tx
                l_ticks = l_labels = ly
                r_ticks = r_labels = ry
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
                    'b_ticks': b_ticks, 't_ticks': t_ticks, 'l_ticks': l_ticks, 'r_ticks': r_ticks,
                    'b_labels': b_labels, 't_labels': t_labels, 'l_labels': l_labels, 'r_labels': r_labels,
                    'mbx': mbx, 'mtx': mtx, 'mly': mly, 'mry': mry,
                })
            try:
                ax._saved_tick_state = dict(tick_state)
            except Exception:
                pass
            
            if True:  # Always apply
                ax.tick_params(
                    axis='x',
                    bottom=b_ticks, labelbottom=b_labels,
                    top=t_ticks, labeltop=t_labels,
                )
                ax.tick_params(axis='y', left=l_ticks, labelleft=l_labels)
                ax2.tick_params(axis='y', right=r_ticks, labelright=r_labels)
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
                            ax._top_xlabel_text.set_position((0.5, 1.07 if t_labels else 1.02))
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
        try:
            finalize_spine_colors_cpc(fig, ax, ax2, tick_state=tick_state)
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
                # Saved efficiency visibility: per-file when present, else the
                # global series toggle (ry).  Never force efficiency back on.
                eff_cfg_visible = cfg.get('series', {}).get('efficiency', {}).get('visible')
                if multi_files and len(multi_files) == len(file_data):
                    for i, f_info in enumerate(multi_files):
                        if i < len(file_data):
                            f = file_data[i]
                            if 'visible' in f_info:
                                try:
                                    file_visible = bool(f_info['visible'])
                                    f['visible'] = file_visible
                                    display_mode = getattr(fig, '_cpc_display_mode', 'both')
                                    eff_visible = f_info.get('efficiency_visible', eff_cfg_visible)
                                    eff_visible = True if eff_visible is None else bool(eff_visible)
                                    artist_visibility = {
                                        'sc_charge': file_visible and display_mode in ('charge', 'both'),
                                        'sc_discharge': file_visible and display_mode in ('discharge', 'both'),
                                        'sc_eff': file_visible and eff_visible,
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
                            if 'charge_marker' in f_info and f.get('sc_charge'):
                                try:
                                    f['sc_charge'].set_marker(f_info['charge_marker'])
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
                            if 'discharge_marker' in f_info and f.get('sc_discharge'):
                                try:
                                    f['sc_discharge'].set_marker(f_info['discharge_marker'])
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
                            if 'efficiency_marker' in f_info and f.get('sc_eff'):
                                try:
                                    f['sc_eff'].set_marker(f_info['efficiency_marker'])
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
        apply_session_font_cfg(fig, cfg.get('font', {}), ax, ax2)
    except Exception:
        pass

    try:
        fig.canvas.draw_idle()
    except Exception:
        pass

__all__ = ["_is_hollow_marker", "_cpc_font_artists", "_style_snapshot", "_apply_style"]

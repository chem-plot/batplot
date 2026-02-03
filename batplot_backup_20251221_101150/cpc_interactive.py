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

from typing import Dict, Optional
import json
import os
import sys
import contextlib
from io import StringIO

import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator, NullFormatter, NullLocator
import random as _random


class _FilterIMKWarning:
    """Filter that suppresses macOS IMKCFRunLoopWakeUpReliable warnings while preserving other errors."""
    def __init__(self, original_stderr):
        self.original_stderr = original_stderr
    
    def write(self, message):
        # Filter out the harmless macOS IMK warning
        if 'IMKCFRunLoopWakeUpReliable' not in message:
            self.original_stderr.write(message)
    
    def flush(self):
        self.original_stderr.flush()


def _safe_input(prompt: str = "") -> str:
    """Wrapper around input() that suppresses macOS IMKCFRunLoopWakeUpReliable warnings.
    
    This is a harmless macOS system message that appears when using input() in terminals.
    """
    # Filter stderr to hide macOS IMK warnings while preserving other errors
    original_stderr = sys.stderr
    sys.stderr = _FilterIMKWarning(original_stderr)
    try:
        result = input(prompt)
        return result
    except (KeyboardInterrupt, EOFError):
        raise
    finally:
        sys.stderr = original_stderr

from .ui import (
    resize_plot_frame, resize_canvas,
    update_tick_visibility as _ui_update_tick_visibility,
    position_top_xlabel as _ui_position_top_xlabel,
    position_right_ylabel as _ui_position_right_ylabel,
    position_bottom_xlabel as _ui_position_bottom_xlabel,
    position_left_ylabel as _ui_position_left_ylabel,
)
from .utils import (
    _confirm_overwrite,
    choose_save_path,
    convert_label_shortcuts,
    choose_style_file,
    list_files_in_subdirectory,
    get_organized_path,
)
import time
from .color_utils import resolve_color_token, color_block, palette_preview, manage_user_colors, get_user_color_list, ensure_colormap


def _legend_no_frame(ax, *args, **kwargs):
    # Compact legend defaults and labelcolor matching marker/line color
    kwargs.setdefault('frameon', False)
    kwargs.setdefault('handlelength', 1.0)
    kwargs.setdefault('handletextpad', 0.35)
    kwargs.setdefault('labelspacing', 0.25)
    kwargs.setdefault('borderaxespad', 0.5)
    kwargs.setdefault('borderpad', 0.3)
    kwargs.setdefault('columnspacing', 0.6)
    # Let matplotlib color legend text from line/marker colors
    kwargs.setdefault('labelcolor', 'linecolor')
    leg = ax.legend(*args, **kwargs)
    if leg is not None:
        try:
            leg.set_frame_on(False)
        except Exception:
            pass
    return leg


def _visible_handles_labels(ax, ax2):
    """Return handles/labels for visible artists only."""
    try:
        h1, l1 = ax.get_legend_handles_labels()
    except Exception:
        h1, l1 = [], []
    try:
        h2, l2 = ax2.get_legend_handles_labels()
    except Exception:
        h2, l2 = [], []
    H, L = [], []
    for h, l in list(zip(h1, l1)) + list(zip(h2, l2)):
        try:
            if hasattr(h, 'get_visible') and not h.get_visible():
                continue
        except Exception:
            pass
        H.append(h); L.append(l)
    return H, L

def _colorize_menu(text):
    """Colorize menu items: command in cyan, colon in white, description in default."""
    if ':' not in text:
        return text
    parts = text.split(':', 1)
    cmd = parts[0].strip()
    desc = parts[1].strip() if len(parts) > 1 else ''
    return f"\033[96m{cmd}\033[0m: {desc}"  # Cyan for command, default for description


def _color_of(artist):
    """Return a representative color for a Line2D/PathCollection."""
    try:
        if artist is None:
            return None
        if hasattr(artist, 'get_color'):
            c = artist.get_color()
            if isinstance(c, (list, tuple)) and c and not isinstance(c, str):
                return c[0]
            return c
        if hasattr(artist, 'get_facecolors'):
            arr = artist.get_facecolors()
            if arr is not None and len(arr):
                from matplotlib.colors import to_hex
                return to_hex(arr[0])
    except Exception:
        return None
    return None


def _get_legend_title(fig, default: Optional[str] = None) -> Optional[str]:
    """Fetch stored legend title, falling back to current legend text or None."""
    try:
        title = getattr(fig, '_cpc_legend_title', None)
        if isinstance(title, str) and title:
            return title
    except Exception:
        pass
    try:
        for ax in getattr(fig, 'axes', []):
            leg = ax.get_legend()
            if leg is not None:
                t = leg.get_title().get_text()
                if t:
                    return t
    except Exception:
        pass
    return default


def _colorize_prompt(text):
    """Colorize commands within input prompts. Handles formats like (s=size, f=family, q=return) or (y/n)."""
    import re
    pattern = r'\(([a-z]+=[^,)]+(?:,\s*[a-z]+=[^,)]+)*|[a-z]+(?:/[a-z]+)+)\)'
    
    def colorize_match(match):
        content = match.group(1)
        if '/' in content:
            parts = content.split('/')
            colored_parts = [f"\033[96m{p.strip()}\033[0m" for p in parts]
            return f"({'/'.join(colored_parts)})"
        else:
            parts = content.split(',')
            colored_parts = []
            for part in parts:
                part = part.strip()
                if '=' in part:
                    cmd, desc = part.split('=', 1)
                    colored_parts.append(f"\033[96m{cmd.strip()}\033[0m={desc.strip()}")
                else:
                    colored_parts.append(part)
            return f"({', '.join(colored_parts)})"
    
    return re.sub(pattern, colorize_match, text)


def _colorize_inline_commands(text):
    """Colorize inline command examples in help text. Colors quoted examples and specific known commands."""
    import re
    # Color quoted command examples (like 's2 w5 a4', 'w2 w5')
    text = re.sub(r"'([a-z0-9\s_-]+)'", lambda m: f"'\033[96m{m.group(1)}\033[0m'", text)
    # Color specific known commands: q, i, l, list, help, all
    text = re.sub(r'\b(q|i|l|list|help|all)\b(?=\s*[=,]|\s*$)', lambda m: f"\033[96m{m.group(1)}\033[0m", text)
    return text


def _collect_file_paths(file_data) -> list:
    """Extract absolute file paths from file_data structures."""
    paths = []
    if isinstance(file_data, list):
        for entry in file_data:
            if isinstance(entry, dict):
                path = entry.get('filepath')
                if path:
                    paths.append(path)
    elif isinstance(file_data, dict):
        path = file_data.get('filepath')
        if path:
            paths.append(path)
    return paths


def _generate_similar_color(base_color):
    """Generate a similar but distinguishable color for discharge from charge color."""
    try:
        from matplotlib.colors import to_rgb, rgb_to_hsv, hsv_to_rgb
        import numpy as np
        
        # Convert to RGB
        rgb = to_rgb(base_color)
        # Convert to HSV
        hsv = rgb_to_hsv(rgb)
        
        # Adjust hue slightly (+/- 15 degrees) and reduce saturation/brightness slightly
        h, s, v = hsv
        h_new = (h + 0.04) % 1.0  # Shift hue slightly
        s_new = max(0.3, s * 0.85)  # Reduce saturation
        v_new = max(0.4, v * 0.9)  # Slightly darker
        
        # Convert back to RGB
        rgb_new = hsv_to_rgb([h_new, s_new, v_new])
        return rgb_new
    except Exception:
        # Fallback to a darker version
        try:
            from matplotlib.colors import to_rgb
            rgb = to_rgb(base_color)
            return tuple(max(0, c * 0.7) for c in rgb)
        except Exception:
            return base_color


def _print_menu():
    col1 = [
        " f: font",
        " l: line",
        " m: marker sizes",
        " c: colors",
        " k: spine colors",
        "ry: show/hide efficiency",
        " t: toggle axes",
        " h: legend",
        " g: size",
        " v: show/hide files",
    ]
    col2 = [
        "r: rename",
        "x: x range",
        "y: y ranges",
    ]
    col3 = [
        "p: print(export) style/geom",
        "i: import style/geom",
        "e: export figure",
        "s: save project",
        "b: undo",
        "q: quit",
    ]
    w1 = max(18, *(len(s) for s in col1))
    w2 = max(18, *(len(s) for s in col2))
    w3 = max(12, *(len(s) for s in col3))
    rows = max(len(col1), len(col2), len(col3))
    print("\n\033[1mCPC interactive menu:\033[0m")  # Bold title
    print(f"  \033[93m{'(Styles)':<{w1}}\033[0m \033[93m{'(Geometries)':<{w2}}\033[0m \033[93m{'(Options)':<{w3}}\033[0m")  # Yellow headers
    for i in range(rows):
        p1 = _colorize_menu(col1[i]) if i < len(col1) else ""
        p2 = _colorize_menu(col2[i]) if i < len(col2) else ""
        p3 = _colorize_menu(col3[i]) if i < len(col3) else ""
        # Add padding to account for ANSI escape codes
        pad1 = w1 + (9 if i < len(col1) else 0)
        pad2 = w2 + (9 if i < len(col2) else 0)
        pad3 = w3 + (9 if i < len(col3) else 0)
        print(f"  {p1:<{pad1}} {p2:<{pad2}} {p3:<{pad3}}")


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


def _rebuild_legend(ax, ax2, file_data, preserve_position=True):
    """Rebuild legend from all visible files.
    
    Args:
        preserve_position: If True, preserve legend position after rebuilding.
    """
    try:
        fig = ax.figure
        # Get stored position before rebuilding. If none is stored yet, try to
        # capture the current on-canvas position once so subsequent rebuilds
        # (e.g., after renaming) do not jump to a new "best" location.
        xy_in = None
        if preserve_position:
            try:
                xy_in = getattr(fig, '_cpc_legend_xy_in', None)
            except Exception:
                xy_in = None
            if xy_in is None:
                try:
                    leg0 = ax.get_legend()
                    if leg0 is not None and leg0.get_visible():
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
                            xy_in = offset
                except Exception:
                    pass
        
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        # Filter to only visible items
        h_all, l_all = [], []
        for h, l in zip(h1 + h2, l1 + l2):
            if h.get_visible():
                h_all.append(h)
                l_all.append(l)
        
        if h_all:
            # Get legend title (None if not set, to avoid showing "Legend")
            leg_title = _get_legend_title(fig, default=None)
            
            if xy_in is not None and preserve_position:
                # Use stored position
                try:
                    fw, fh = fig.get_size_inches()
                    fx = 0.5 + float(xy_in[0]) / float(fw)
                    fy = 0.5 + float(xy_in[1]) / float(fh)
                    _legend_no_frame(ax, h_all, l_all, loc='center', bbox_to_anchor=(fx, fy), bbox_transform=fig.transFigure, borderaxespad=1.0, title=leg_title)
                except Exception:
                    _legend_no_frame(ax, h_all, l_all, loc='best', borderaxespad=1.0, title=leg_title)
            else:
                _legend_no_frame(ax, h_all, l_all, loc='best', borderaxespad=1.0, title=leg_title)
        else:
            leg = ax.get_legend()
            if leg:
                leg.set_visible(False)
    except Exception:
        pass


def _get_geometry_snapshot(ax, ax2) -> Dict:
    """Collects a snapshot of geometry settings (axes labels and limits)."""
    geom = {
        'xlim': list(ax.get_xlim()),
        'ylim_left': list(ax.get_ylim()),
        'xlabel': ax.get_xlabel() or '',
        'ylabel_left': ax.get_ylabel() or '',
    }
    if ax2 is not None:
        geom['ylim_right'] = list(ax2.get_ylim())
        geom['ylabel_right'] = ax2.get_ylabel() or ''
    return geom


def _style_snapshot(fig, ax, ax2, sc_charge, sc_discharge, sc_eff, file_data=None) -> Dict:
    try:
        fig_w, fig_h = map(float, fig.get_size_inches())
    except Exception:
        fig_w = fig_h = None

    def _color_of(artist) -> Optional[str]:
        try:
            if hasattr(artist, 'get_color'):
                c = artist.get_color()
                # scatter returns array sometimes; pick first
                if isinstance(c, (list, tuple)) and c and not isinstance(c, str):
                    return c[0]
                return c
            if hasattr(artist, 'get_facecolors'):
                arr = artist.get_facecolors()
                if arr is not None and len(arr):
                    from matplotlib.colors import to_hex
                    return to_hex(arr[0])
        except Exception:
            pass
        return None

    fam = plt.rcParams.get('font.sans-serif', [''])
    fam0 = fam[0] if fam else ''
    fsize = plt.rcParams.get('font.size', None)
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
        leg = ax.get_legend()
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
        'font': {'family': fam0, 'size': fsize},
        'legend': {
            'visible': legend_visible,
            'position_inches': legend_xy_in,  # [x, y] offset from canvas center in inches
            'title': _get_legend_title(fig),
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
            'direction': getattr(fig, '_tick_direction', 'out')
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
            },
            'discharge': {
                'color': _color_of(sc_discharge),
                'marker': getattr(sc_discharge, 'get_marker', lambda: 's')(),
                'markersize': float(getattr(sc_discharge, 'get_sizes', lambda: [32])()[0]) if hasattr(sc_discharge, 'get_sizes') else 32.0,
                'alpha': float(sc_discharge.get_alpha()) if sc_discharge.get_alpha() is not None else 1.0,
            },
            'efficiency': {
                'color': (sc_eff.get_facecolors()[0].tolist() if hasattr(sc_eff, 'get_facecolors') and len(sc_eff.get_facecolors()) else '#2ca02c'),
                'marker': getattr(sc_eff, 'get_marker', lambda: '^')(),
                'markersize': float(getattr(sc_eff, 'get_sizes', lambda: [40])()[0]) if hasattr(sc_eff, 'get_sizes') else 40.0,
                'alpha': float(sc_eff.get_alpha()) if sc_eff.get_alpha() is not None else 1.0,
                'visible': bool(getattr(sc_eff, 'get_visible', lambda: True)()),
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
                'charge_color': _color_of(sc_chg),
                'charge_marker': getattr(sc_chg, 'get_marker', lambda: 'o')() if sc_chg else 'o',
                'discharge_color': _color_of(sc_dchg),
                'discharge_marker': getattr(sc_dchg, 'get_marker', lambda: 's')() if sc_dchg else 's',
                'efficiency_color': _color_of(sc_eff),
                'efficiency_marker': getattr(sc_eff, 'get_marker', lambda: '^')() if sc_eff else '^',
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


def _apply_style(fig, ax, ax2, sc_charge, sc_discharge, sc_eff, cfg: Dict, file_data=None):
    """Apply style configuration to CPC plot.
    
    Args:
        fig, ax, ax2: Matplotlib figure and axes
        sc_charge, sc_discharge, sc_eff: Primary/selected file scatter artists
        cfg: Style configuration dict
        file_data: Optional list of file dicts for multi-file mode
    """
    is_multi_file = file_data is not None and len(file_data) > 1
    
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
        saved_rylabelpad = getattr(ax2.yaxis, 'labelpad', None) if ax2 is not None else None
    except Exception:
        pass
    
    try:
        font = cfg.get('font', {})
        fam = font.get('family')
        size = font.get('size')
        if fam:
            plt.rcParams['font.family'] = 'sans-serif'
            plt.rcParams['font.sans-serif'] = [fam, 'DejaVu Sans', 'Arial', 'Helvetica']
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
    try:
        s = cfg.get('series', {})
        ch = s.get('charge', {})
        dh = s.get('discharge', {})
        ef = s.get('efficiency', {})
        
        # Apply marker sizes and alpha globally to all files in multi-file mode
        if is_multi_file:
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
                    sc_charge.set_color(ch['color'])
                if ch.get('marker') is not None and hasattr(sc_charge, 'set_marker'):
                    sc_charge.set_marker(ch['marker'])
                if ch.get('markersize') is not None and hasattr(sc_charge, 'set_sizes'):
                    sc_charge.set_sizes([float(ch['markersize'])])
                if ch.get('alpha') is not None:
                    sc_charge.set_alpha(float(ch['alpha']))
            if dh:
                if dh.get('color') is not None:
                    sc_discharge.set_color(dh['color'])
                if dh.get('marker') is not None and hasattr(sc_discharge, 'set_marker'):
                    sc_discharge.set_marker(dh['marker'])
                if dh.get('markersize') is not None and hasattr(sc_discharge, 'set_sizes'):
                    sc_discharge.set_sizes([float(dh['markersize'])])
                if dh.get('alpha') is not None:
                    sc_discharge.set_alpha(float(dh['alpha']))
            if ef:
                if ef.get('color') is not None:
                    try:
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
    except Exception:
        pass
    # Apply legend state (h command)
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
                            if isinstance(col, (list, tuple)) and len(col) and not isinstance(col, str):
                                col = col[0]
                            try:
                                import numpy as _np
                                if hasattr(col, "__len__") and not isinstance(col, str):
                                    col = tuple(_np.array(col).ravel().tolist())
                            except Exception:
                                pass
                            if col is not None:
                                txt.set_color(col)
                except Exception:
                    pass
    except Exception:
        pass
    # Apply tick visibility/widths and spines
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
        
        if True:  # Always apply
            ax.tick_params(axis='x', bottom=bx, labelbottom=bx, top=tx, labeltop=tx)
            ax.tick_params(axis='y', left=ly, labelleft=ly)
            ax2.tick_params(axis='y', right=ry, labelright=ry)
            try:
                ax.xaxis.label.set_visible(bool(wasd.get('bottom', {}).get('title', True)) if wasd else bx)
                ax.yaxis.label.set_visible(bool(wasd.get('left', {}).get('title', True)) if wasd else ly)
                ax2.yaxis.label.set_visible(bool(wasd.get('right', {}).get('title', True)) if wasd else ry)
            except Exception:
                pass
            # Minor ticks
            from matplotlib.ticker import AutoMinorLocator, NullFormatter, NullLocator, NullLocator
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
    except Exception:
        pass
    try:
        sp = cfg.get('spines', {})
        for name, spec in sp.items():
            if name in ('bottom','top','left') and name in ax.spines:
                spn = ax.spines.get(name)
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
                    charge_col = _color_of(sc_charge)
                    eff_col = _color_of(sc_eff)
                    _set_spine_color('left', charge_col)
                    _set_spine_color('right', eff_col)
                except Exception:
                    pass
    except Exception:
        pass
    # Restore labelpads (preserve current if not in config)
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
    # Grid state
    try:
        grid_enabled = cfg.get('grid', False)
        if grid_enabled:
            ax.grid(True, color='0.85', linestyle='-', linewidth=0.5, alpha=0.7)
        else:
            ax.grid(False)
    except Exception:
        pass
    # Title offsets - all four titles
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
    # Restore legend labels
    try:
        if is_multi_file and file_data:
            multi_files = cfg.get('multi_files', [])
            if multi_files and len(multi_files) == len(file_data):
                for i, f_info in enumerate(multi_files):
                    if i < len(file_data):
                        f = file_data[i]
                        # Restore colors FIRST (before labels)
                        if 'charge_color' in f_info and f.get('sc_charge'):
                            try:
                                col = f_info['charge_color']
                                f['sc_charge'].set_color(col)
                                f['color'] = col
                                # Force update of facecolors for scatter plots
                                if hasattr(f['sc_charge'], 'set_facecolors'):
                                    from matplotlib.colors import to_rgba
                                    rgba = to_rgba(col)
                                    f['sc_charge'].set_facecolors(rgba)
                            except Exception:
                                pass
                        if 'discharge_color' in f_info and f.get('sc_discharge'):
                            try:
                                col = f_info['discharge_color']
                                f['sc_discharge'].set_color(col)
                                # Force update of facecolors for scatter plots
                                if hasattr(f['sc_discharge'], 'set_facecolors'):
                                    from matplotlib.colors import to_rgba
                                    rgba = to_rgba(col)
                                    f['sc_discharge'].set_facecolors(rgba)
                            except Exception:
                                pass
                        if 'efficiency_color' in f_info and f.get('sc_eff'):
                            try:
                                col = f_info['efficiency_color']
                                f['sc_eff'].set_color(col)
                                f['eff_color'] = col
                                # Force update of facecolors for scatter plots
                                if hasattr(f['sc_eff'], 'set_facecolors'):
                                    from matplotlib.colors import to_rgba
                                    rgba = to_rgba(col)
                                    f['sc_eff'].set_facecolors(rgba)
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
    except Exception:
        pass
    try:
        fig.canvas.draw_idle()
    except Exception:
        pass


def _format_file_timestamp(filepath: str) -> str:
    """Format file modification time for display.
    
    Args:
        filepath: Full path to the file
        
    Returns:
        Formatted timestamp string (e.g., "2024-01-15 14:30") or empty string if error
    """
    try:
        mtime = os.path.getmtime(filepath)
        # Format as YYYY-MM-DD HH:MM
        return time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
    except Exception:
        return ""


def cpc_interactive_menu(fig, ax, ax2, sc_charge, sc_discharge, sc_eff, file_data=None):
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
    - t: toggle axes (show/hide tick labels)
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
    is_multi_file = file_data is not None and len(file_data) > 1
    
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
            tick_state['bx'] = bool(saved_wasd.get('bottom', {}).get('labels', tick_state['bx']))
            tick_state['tx'] = bool(saved_wasd.get('top', {}).get('labels', tick_state['tx']))
            tick_state['ly'] = bool(saved_wasd.get('left', {}).get('labels', tick_state['ly']))
            tick_state['ry'] = bool(saved_wasd.get('right', {}).get('labels', tick_state['ry']))
            tick_state['mbx'] = bool(saved_wasd.get('bottom', {}).get('minor', tick_state['mbx']))
            tick_state['mtx'] = bool(saved_wasd.get('top', {}).get('minor', tick_state['mtx']))
            tick_state['mly'] = bool(saved_wasd.get('left', {}).get('minor', tick_state['mly']))
            tick_state['mry'] = bool(saved_wasd.get('right', {}).get('minor', tick_state['mry']))
    except Exception:
        pass

    # --- Undo stack using style snapshots ---
    state_history = []  # list of cfg dicts

    if not hasattr(fig, '_cpc_spine_colors') or not isinstance(getattr(fig, '_cpc_spine_colors'), dict):
        fig._cpc_spine_colors = {}

    def _set_spine_color(spine_name: str, color: str):
        if not hasattr(fig, '_cpc_spine_colors') or not isinstance(fig._cpc_spine_colors, dict):
            fig._cpc_spine_colors = {}
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
            sp = curr_ax.spines[spine_name]
            try:
                sp.set_edgecolor(color)
            except Exception:
                pass
            try:
                if spine_name in ('top', 'bottom'):
                    curr_ax.tick_params(axis='x', which='both', colors=color)
                    curr_ax.xaxis.label.set_color(color)
                elif spine_name == 'left':
                    curr_ax.tick_params(axis='y', which='both', colors=color)
                    curr_ax.yaxis.label.set_color(color)
                elif spine_name == 'right':
                    curr_ax.tick_params(axis='y', which='both', colors=color)
                    curr_ax.yaxis.label.set_color(color)
            except Exception:
                pass

    def push_state(note: str = ""):
        try:
            snap = _style_snapshot(fig, ax, ax2, sc_charge, sc_discharge, sc_eff, file_data)
            snap['__note__'] = note
            # Also persist current tick_state explicitly
            snap.setdefault('ticks', {}).setdefault('visibility', dict(tick_state))
            state_history.append(snap)
            if len(state_history) > 40:
                state_history.pop(0)
        except Exception:
            pass

    def restore_state():
        if not state_history:
            print("No undo history.")
            return
        cfg = state_history.pop()
        try:
            _apply_style(fig, ax, ax2, sc_charge, sc_discharge, sc_eff, cfg, file_data)
            # Restore local tick_state from cfg
            vis = (cfg.get('ticks') or {}).get('visibility') or {}
            for k, v in vis.items():
                if k in tick_state:
                    tick_state[k] = bool(v)
            _update_ticks()
            # Re-apply legend text colors after state restore (undo)
            try:
                leg = ax.get_legend()
                if leg is not None:
                    handles = list(getattr(leg, "legendHandles", []))
                    for h, txt in zip(handles, leg.get_texts()):
                        col = _color_of(h)
                        if col is None and hasattr(h, 'get_edgecolor'):
                            col = h.get_edgecolor()
                        if isinstance(col, (list, tuple)) and len(col) and not isinstance(col, str):
                            col = col[0]
                        try:
                            import numpy as _np
                            if hasattr(col, "__len__") and not isinstance(col, str):
                                col = tuple(_np.array(col).ravel().tolist())
                        except Exception:
                            pass
                        if col is not None:
                            txt.set_color(col)
            except Exception:
                pass
            try:
                fig.canvas.draw()
            except Exception:
                fig.canvas.draw_idle()
            print("Undo: restored previous state.")
        except Exception as e:
            print(f"Undo failed: {e}")

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
            # Position label spacings (bottom/left) for consistency
            _ui_position_bottom_xlabel(ax, fig, tick_state)
            _ui_position_left_ylabel(ax, fig, tick_state)
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

    def _sanitize_legend_offset(xy: Optional[tuple]) -> Optional[tuple]:
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
        """Reapply legend position using stored inches offset relative to canvas center."""
        try:
            xy_in = _sanitize_legend_offset(getattr(fig, '_cpc_legend_xy_in', None))
            if xy_in is None:
                return
            # Compute figure-fraction anchor from inches
            fw, fh = fig.get_size_inches()
            if fw <= 0 or fh <= 0:
                return
            fx = 0.5 + float(xy_in[0]) / float(fw)
            fy = 0.5 + float(xy_in[1]) / float(fh)
            # Use current visible handles/labels
            H, L = _visible_handles_labels(ax, ax2)
            if H:
                _legend_no_frame(
                    ax,
                    H,
                    L,
                    loc='center',
                    bbox_to_anchor=(fx, fy),
                    bbox_transform=fig.transFigure,
                    borderaxespad=1.0,
                    title=_get_legend_title(fig),
                )
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

    _print_menu()
    
    while True:
        try:
            # Update current file's scatter artists for commands that need them
            sc_charge, sc_discharge, sc_eff = _get_current_file_artists(file_data, current_file_idx)
            
            key = _safe_input("Press a key: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\n\nExiting interactive menu...")
            break
        if not key:
            continue
        
        # File visibility toggle command (v)
        if key == 'v':
            try:
                if is_multi_file:
                    _print_file_list(file_data, current_file_idx)
                    choice = _safe_input(f"Toggle visibility for file (1-{len(file_data)}), 'a' for all, or q=cancel: ").strip()
                    if choice.lower() == 'q':
                        _print_menu()
                        _print_file_list(file_data, current_file_idx)
                        continue
                    
                    push_state("visibility")
                    if choice.lower() == 'a':
                        # Toggle all
                        any_visible = any(f.get('visible', True) for f in file_data)
                        new_state = not any_visible
                        for f in file_data:
                            f['visible'] = new_state
                            f['sc_charge'].set_visible(new_state)
                            f['sc_discharge'].set_visible(new_state)
                            f['sc_eff'].set_visible(new_state)
                    else:
                        idx = int(choice) - 1
                        if 0 <= idx < len(file_data):
                            f = file_data[idx]
                            new_vis = not f.get('visible', True)
                            f['visible'] = new_vis
                            f['sc_charge'].set_visible(new_vis)
                            f['sc_discharge'].set_visible(new_vis)
                            f['sc_eff'].set_visible(new_vis)
                        else:
                            print("Invalid file number.")
                else:
                    # Single file mode: toggle efficiency
                    push_state("visibility-eff")
                    # Capture current legend position BEFORE toggling visibility
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
                    vis = sc_eff.get_visible()
                    sc_eff.set_visible(not vis)
                    try:
                        ax2.yaxis.label.set_visible(not vis)
                    except Exception:
                        pass
                
                _rebuild_legend(ax, ax2, file_data, preserve_position=True)
                fig.canvas.draw_idle()
            except ValueError:
                print("Invalid input.")
            except Exception as e:
                print(f"Visibility toggle failed: {e}")
            _print_menu()
            if is_multi_file:
                _print_file_list(file_data, current_file_idx)
            continue
        
        if key == 'q':
            try:
                confirm = _safe_input(_colorize_prompt("Quit CPC interactive? Remember to save! Quit now? (y/n): ")).strip().lower()
            except Exception:
                confirm = 'y'
            if confirm == 'y':
                break
            else:
                _print_menu(); continue
        elif key == 'b':
            restore_state()
            _print_menu(); continue
        elif key == 'c':
            # Colors submenu: ly (left Y series) and ry (right Y efficiency), with user colors and palettes
            try:
                # Note: Individual series may use different colors, so we can't show a single "current" palette
                # Use same palettes as EC interactive
                palette_opts = ['tab10', 'Set2', 'Dark2', 'viridis', 'plasma']
                def _palette_color(name, idx=0, total=1, default_val=0.4):
                    import matplotlib.cm as cm
                    import matplotlib.colors as mcolors
                    import numpy as _np
                    # Ensure colormap is registered before use
                    if not ensure_colormap(name):
                        # Fallback to viridis if colormap can't be registered
                        name = 'viridis'
                        ensure_colormap(name)
                    try:
                        cmap = cm.get_cmap(name)
                    except Exception:
                        # Fallback if get_cmap fails
                        ensure_colormap('viridis')
                        cmap = cm.get_cmap('viridis')
                    
                    # Special handling for tab10 to match hardcoded colors exactly
                    if name.lower() == 'tab10':
                        default_tab10_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                                               '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
                        return default_tab10_colors[idx % len(default_tab10_colors)]
                    
                    # For discrete colormaps (Set2, Dark2), access colors directly
                    if hasattr(cmap, 'colors') and cmap.colors is not None:
                        # Discrete colormap: access colors directly by index
                        colors = cmap.colors
                        rgb = colors[idx % len(colors)]
                        if isinstance(rgb, tuple) and len(rgb) >= 3:
                            return mcolors.rgb2hex(rgb[:3])
                    
                    # For continuous colormaps (viridis, plasma), sample evenly
                    if total == 1:
                        vals = [0.55]
                    elif total == 2:
                        vals = [0.15, 0.85]
                    else:
                        vals = _np.linspace(0.08, 0.88, total)
                    rgb = cmap(vals[idx % len(vals)])
                    return mcolors.rgb2hex(rgb[:3])
                def _resolve_color(spec, idx=0, total=1, default_cmap='tab10'):
                    spec = spec.strip()
                    if not spec:
                        return None
                    if spec.lower() == 'r':
                        return _palette_color(default_cmap, idx, total, 0.4)
                    # user colors: u# or plain number referencing saved list
                    uc = None
                    if spec.lower().startswith('u') and len(spec) > 1 and spec[1:].isdigit():
                        uc = resolve_color_token(spec, fig)
                    elif spec.isdigit():
                        # number as palette index if within palette list
                        n = int(spec)
                        if 1 <= n <= len(palette_opts):
                            palette_name = palette_opts[n-1]
                            return _palette_color(palette_name, idx, total, 0.4)
                    if uc:
                        return uc
                    # Check if spec is a palette name (case-insensitive)
                    spec_lower = spec.lower()
                    base = spec.rstrip('_r').rstrip('_R')
                    base_lower = base.lower()
                    # Check against palette_opts (case-insensitive)
                    for pal in palette_opts:
                        if spec_lower == pal.lower() or base_lower == pal.lower() or spec_lower == (pal + '_r').lower():
                            return _palette_color(pal if not spec.endswith('_r') and not spec.endswith('_R') else spec, idx, total, 0.4)
                    # Fall back to resolve_color_token for hex colors, named colors, etc.
                    return resolve_color_token(spec, fig)

                while True:
                    print("\nColors: ly=capacity curves, ry=efficiency triangles, u=user colors, q=back")
                    sub = _safe_input("Colors> ").strip().lower()
                    if not sub:
                        continue
                    if sub == 'q':
                        break
                    if sub == 'u':
                        manage_user_colors(fig); continue
                    if sub == 'ly':
                        push_state("colors-ly")
                        print("\nCurrent capacity curves:")
                        for i, f in enumerate(file_data, 1):
                            cur = _color_of(f['sc_charge'])
                            vis_mark = "●" if f.get('visible', True) else "○"
                            print(f"  {i}. {vis_mark} {f['filename']}  {color_block(cur)} {cur}")
                        uc = get_user_color_list(fig)
                        if uc:
                            print("\nSaved colors (refer as number or u#):")
                            for i, c in enumerate(uc, 1):
                                print(f"  {i}: {color_block(c)} {c}")
                        print("\nPalettes:")
                        for idx, name in enumerate(palette_opts, 1):
                            bar = palette_preview(name)
                            print(f"  {idx}. {name}")
                            if bar:
                                print(f"      {bar}")
                        color_input = _safe_input("Enter file+color pairs (e.g., 1:2 2:3 or 1 2 2 3) or palette/number for all, q=cancel: ").strip()
                        if not color_input or color_input.lower() == 'q':
                            continue
                        tokens = color_input.split()
                        if len(tokens) == 1:
                            # Single token: apply palette to all files
                            spec = tokens[0]
                            for i, f in enumerate(file_data):
                                charge_col = _resolve_color(spec, i, len(file_data), default_cmap='tab10')
                                if not charge_col:
                                    continue
                                discharge_col = _generate_similar_color(charge_col)
                                try:
                                    f['sc_charge'].set_color(charge_col)
                                    f['sc_discharge'].set_color(discharge_col)
                                    f['color'] = charge_col
                                    # Force update of facecolors for scatter plots
                                    if hasattr(f['sc_charge'], 'set_facecolors'):
                                        from matplotlib.colors import to_rgba
                                        rgba = to_rgba(charge_col)
                                        f['sc_charge'].set_facecolors(rgba)
                                    if hasattr(f['sc_discharge'], 'set_facecolors'):
                                        from matplotlib.colors import to_rgba
                                        rgba = to_rgba(discharge_col)
                                        f['sc_discharge'].set_facecolors(rgba)
                                except Exception as e:
                                    print(f"Error setting color: {e}")
                                    pass
                        else:
                            # Multiple tokens: parse file:color pairs
                            def _apply_manual_entries(tokens):
                                idx_color_pairs = []
                                i = 0
                                while i < len(tokens):
                                    tok = tokens[i]
                                    if ':' in tok:
                                        idx_str, color = tok.split(':', 1)
                                    else:
                                        if i + 1 >= len(tokens):
                                            print(f"Skip incomplete entry: {tok}")
                                            break
                                        idx_str = tok
                                        color = tokens[i + 1]
                                        i += 1
                                    idx_color_pairs.append((idx_str, color))
                                    i += 1
                                for idx_str, color in idx_color_pairs:
                                    try:
                                        file_idx = int(idx_str) - 1
                                    except ValueError:
                                        print(f"Bad index: {idx_str}")
                                        continue
                                    if not (0 <= file_idx < len(file_data)):
                                        print(f"Index out of range: {idx_str}")
                                        continue
                                    resolved = resolve_color_token(color, fig)
                                    charge_col = resolved if resolved else color
                                    if not charge_col:
                                        continue
                                    discharge_col = _generate_similar_color(charge_col)
                                    try:
                                        file_data[file_idx]['sc_charge'].set_color(charge_col)
                                        file_data[file_idx]['sc_discharge'].set_color(discharge_col)
                                        file_data[file_idx]['color'] = charge_col
                                        # Force update of facecolors for scatter plots
                                        if hasattr(file_data[file_idx]['sc_charge'], 'set_facecolors'):
                                            from matplotlib.colors import to_rgba
                                            rgba = to_rgba(charge_col)
                                            file_data[file_idx]['sc_charge'].set_facecolors(rgba)
                                        if hasattr(file_data[file_idx]['sc_discharge'], 'set_facecolors'):
                                            from matplotlib.colors import to_rgba
                                            rgba = to_rgba(discharge_col)
                                            file_data[file_idx]['sc_discharge'].set_facecolors(rgba)
                                    except Exception:
                                        pass
                            _apply_manual_entries(tokens)
                        if not is_multi_file and getattr(fig, '_cpc_spine_auto', False):
                            try:
                                cur_col = _color_of(sc_charge)
                                if cur_col:
                                    _set_spine_color('left', cur_col)
                            except Exception:
                                pass
                        try:
                            _rebuild_legend(ax, ax2, file_data); fig.canvas.draw_idle()
                        except Exception:
                            pass
                    elif sub == 'ry':
                        push_state("colors-ry")
                        print("\nCurrent efficiency curves:")
                        for i, f in enumerate(file_data, 1):
                            cur = _color_of(f['sc_eff'])
                            vis_mark = "●" if f.get('visible', True) else "○"
                            print(f"  {i}. {vis_mark} {f['filename']}  {color_block(cur)} {cur}")
                        uc = get_user_color_list(fig)
                        if uc:
                            print("\nSaved colors (refer as number or u#):")
                            for i, c in enumerate(uc, 1):
                                print(f"  {i}: {color_block(c)} {c}")
                        print("\nPalettes:")
                        for idx, name in enumerate(palette_opts, 1):
                            bar = palette_preview(name)
                            print(f"  {idx}. {name}")
                            if bar:
                                print(f"      {bar}")
                        color_input = _safe_input("Enter file+color pairs (e.g., 1:2 2:3 or 1 2 2 3) or palette/number for all, q=cancel: ").strip()
                        if not color_input or color_input.lower() == 'q':
                            continue
                        tokens = color_input.split()
                        if len(tokens) == 1:
                            # Single token: apply palette to all files
                            spec = tokens[0]
                            for i, f in enumerate(file_data):
                                col = _resolve_color(spec, i, len(file_data), default_cmap='viridis')
                                if not col:
                                    continue
                                try:
                                    f['sc_eff'].set_color(col)
                                    f['eff_color'] = col
                                    # Force update of facecolors for scatter plots
                                    if hasattr(f['sc_eff'], 'set_facecolors'):
                                        from matplotlib.colors import to_rgba
                                        rgba = to_rgba(col)
                                        f['sc_eff'].set_facecolors(rgba)
                                except Exception:
                                    pass
                        else:
                            # Multiple tokens: parse file:color pairs
                            def _apply_manual_entries_eff(tokens):
                                idx_color_pairs = []
                                i = 0
                                while i < len(tokens):
                                    tok = tokens[i]
                                    if ':' in tok:
                                        idx_str, color = tok.split(':', 1)
                                    else:
                                        if i + 1 >= len(tokens):
                                            print(f"Skip incomplete entry: {tok}")
                                            break
                                        idx_str = tok
                                        color = tokens[i + 1]
                                        i += 1
                                    idx_color_pairs.append((idx_str, color))
                                    i += 1
                                for idx_str, color in idx_color_pairs:
                                    try:
                                        file_idx = int(idx_str) - 1
                                    except ValueError:
                                        print(f"Bad index: {idx_str}")
                                        continue
                                    if not (0 <= file_idx < len(file_data)):
                                        print(f"Index out of range: {idx_str}")
                                        continue
                                    resolved = resolve_color_token(color, fig)
                                    col = resolved if resolved else color
                                    if not col:
                                        continue
                                    try:
                                        file_data[file_idx]['sc_eff'].set_color(col)
                                        file_data[file_idx]['eff_color'] = col
                                        # Force update of facecolors for scatter plots
                                        if hasattr(file_data[file_idx]['sc_eff'], 'set_facecolors'):
                                            from matplotlib.colors import to_rgba
                                            rgba = to_rgba(col)
                                            file_data[file_idx]['sc_eff'].set_facecolors(rgba)
                                    except Exception:
                                        pass
                            _apply_manual_entries_eff(tokens)
                        if not is_multi_file and getattr(fig, '_cpc_spine_auto', False):
                            try:
                                cur_col = _color_of(sc_eff)
                                if cur_col:
                                    _set_spine_color('right', cur_col)
                            except Exception:
                                pass
                        try:
                            _rebuild_legend(ax, ax2, file_data); fig.canvas.draw_idle()
                        except Exception:
                            pass
                    else:
                        print("Unknown option.")
            except Exception as e:
                print(f"Error in colors menu: {e}")
            _print_menu()
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
                        print(_colorize_inline_commands(f"  a : auto (apply capacity curve color to left y-axis, efficiency to right y-axis) [{auto_status}]"))
                    print("q: back to main menu")
                    line = _safe_input("Enter mappings (e.g., w:red a:#4561F7) or q: ").strip()
                    if not line or line.lower() == 'q':
                        break
                    # Handle auto toggle when only one file is loaded
                    if not is_multi_file and line.lower() == 'a':
                        auto_enabled = getattr(fig, '_cpc_spine_auto', False)
                        fig._cpc_spine_auto = not auto_enabled
                        new_status = "ON" if fig._cpc_spine_auto else "OFF"
                        print(f"Auto mode: {new_status}")
                        if fig._cpc_spine_auto:
                            # Apply auto colors immediately
                            push_state("color-spine-auto")
                            try:
                                # Get capacity curve color (charge color)
                                charge_col = _color_of(sc_charge)
                                # Get efficiency curve color
                                eff_col = _color_of(sc_eff)
                                # Apply to left and right spines
                                _set_spine_color('left', charge_col)
                                _set_spine_color('right', eff_col)
                                print(f"Applied: left y-axis = {charge_col}, right y-axis = {eff_col}")
                                fig.canvas.draw()
                            except Exception as e:
                                print(f"Error applying auto colors: {e}")
                        continue
                    push_state("color-spine")
                    # Map wasd to spine names
                    key_to_spine = {'w': 'top', 'a': 'left', 's': 'bottom', 'd': 'right'}
                    tokens = line.split()
                    for token in tokens:
                        if ':' not in token:
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
                    fig.canvas.draw()
            except Exception as e:
                print(f"Error in spine color menu: {e}")
            _print_menu()
            if is_multi_file:
                _print_file_list(file_data, current_file_idx)
            continue
        elif key == 'e':
            try:
                base_path = choose_save_path(file_paths, purpose="figure export")
                if not base_path:
                    _print_menu()
                    continue
                print(f"\nChosen path: {base_path}")
                # List existing figure files from Figures/ subdirectory
                fig_extensions = ('.svg', '.png', '.jpg', '.jpeg', '.pdf', '.eps', '.tif', '.tiff')
                file_list = list_files_in_subdirectory(fig_extensions, 'figure', base_path=base_path)
                files = [f[0] for f in file_list]
                if files:
                    figures_dir = os.path.join(base_path, 'Figures')
                    print(f"Existing figure files in {figures_dir}:")
                    for i, (fname, fpath) in enumerate(file_list, 1):
                        timestamp = _format_file_timestamp(fpath)
                        if timestamp:
                            print(f"  {i}: {fname}  ({timestamp})")
                        else:
                            print(f"  {i}: {fname}")
                
                last_figure_path = getattr(fig, '_last_figure_export_path', None)
                if last_figure_path:
                    fname = _safe_input("Export filename (default .svg if no extension), number to overwrite, or o to overwrite last (q=cancel): ").strip()
                else:
                    fname = _safe_input("Export filename (default .svg if no extension) or number to overwrite (q=cancel): ").strip()
                if not fname or fname.lower() == 'q':
                    _print_menu(); continue
                
                # Check for 'o' option
                if fname.lower() == 'o':
                    if not last_figure_path:
                        print("No previous export found.")
                        _print_menu(); continue
                    if not os.path.exists(last_figure_path):
                        print(f"Previous export file not found: {last_figure_path}")
                        _print_menu(); continue
                    yn = _safe_input(f"Overwrite '{os.path.basename(last_figure_path)}'? (y/n): ").strip().lower()
                    if yn != 'y':
                        _print_menu(); continue
                    target = last_figure_path
                # Check if user selected a number
                elif fname.isdigit() and files:
                    idx = int(fname)
                    if 1 <= idx <= len(files):
                        name = files[idx-1]
                        yn = _safe_input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                        if yn != 'y':
                            _print_menu(); continue
                        target = file_list[idx-1][1]  # Full path from list
                    else:
                        print("Invalid number.")
                        _print_menu(); continue
                else:
                    root, ext = os.path.splitext(fname)
                    if ext == '':
                        fname = fname + '.svg'
                    # Use organized path unless it's an absolute path
                    if os.path.isabs(fname):
                        target = fname
                    else:
                        target = get_organized_path(fname, 'figure', base_path=base_path)
                    if os.path.exists(target):
                        yn = _safe_input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
                        if yn != 'y':
                            _print_menu(); continue
                if target:
                    # Ensure exact case is preserved (important for macOS case-insensitive filesystem)
                    from .utils import ensure_exact_case_filename
                    target = ensure_exact_case_filename(target)
                    
                    # Save current legend position before export (savefig can change layout)
                    saved_legend_pos = None
                    try:
                        saved_legend_pos = getattr(fig, '_cpc_legend_xy_in', None)
                    except Exception:
                        pass
                    
                    # Remove numbering from legend labels before export
                    original_labels = {}
                    if is_multi_file:
                        try:
                            for i, f in enumerate(file_data, 1):
                                # Store original labels
                                original_labels[f['sc_charge']] = f['sc_charge'].get_label()
                                original_labels[f['sc_discharge']] = f['sc_discharge'].get_label()
                                original_labels[f['sc_eff']] = f['sc_eff'].get_label()
                                
                                # Remove "N. " prefix from labels
                                base_label = f['filename']
                                f['sc_charge'].set_label(f'{base_label} charge')
                                f['sc_discharge'].set_label(f'{base_label} discharge')
                                f['sc_eff'].set_label(f'{base_label} efficiency')
                            
                            # Rebuild legend without numbers
                            _rebuild_legend(ax, ax2, file_data)
                        except Exception:
                            pass
                    
                    # Export the figure
                    _, _ext = os.path.splitext(target)
                    if _ext.lower() == '.svg':
                        # Temporarily force transparent patches so SVG background stays transparent
                        try:
                            _fig_fc = fig.get_facecolor()
                        except Exception:
                            _fig_fc = None
                        try:
                            _ax_fc = ax.get_facecolor()
                        except Exception:
                            _ax_fc = None
                        try:
                            _ax2_fc = ax2.get_facecolor()
                        except Exception:
                            _ax2_fc = None
                        try:
                            if getattr(fig, 'patch', None) is not None:
                                fig.patch.set_alpha(0.0); fig.patch.set_facecolor('none')
                            if getattr(ax, 'patch', None) is not None:
                                ax.patch.set_alpha(0.0); ax.patch.set_facecolor('none')
                            if getattr(ax2, 'patch', None) is not None:
                                ax2.patch.set_alpha(0.0); ax2.patch.set_facecolor('none')
                        except Exception:
                            pass
                        try:
                            fig.savefig(target, bbox_inches='tight', transparent=True, facecolor='none', edgecolor='none')
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
                            try:
                                if _ax2_fc is not None and getattr(ax2, 'patch', None) is not None:
                                    ax2.patch.set_alpha(1.0); ax2.patch.set_facecolor(_ax2_fc)
                            except Exception:
                                pass
                        print(f"Exported figure to {target}")
                        fig._last_figure_export_path = target
                        
                        # Restore original labels and legend position
                        if is_multi_file and original_labels:
                            try:
                                for artist, label in original_labels.items():
                                    artist.set_label(label)
                                _rebuild_legend(ax, ax2, file_data)
                            except Exception:
                                pass
                        # Restore legend position after savefig (which may have changed layout)
                        if saved_legend_pos is not None:
                            try:
                                fig._cpc_legend_xy_in = saved_legend_pos
                                _rebuild_legend(ax, ax2, file_data)
                                fig.canvas.draw_idle()
                            except Exception:
                                pass
                    else:
                        fig.savefig(target, bbox_inches='tight')
                        print(f"Exported figure to {target}")
                        fig._last_figure_export_path = target
                        
                        # Restore original labels and legend position
                        if is_multi_file and original_labels:
                            try:
                                for artist, label in original_labels.items():
                                    artist.set_label(label)
                                _rebuild_legend(ax, ax2, file_data)
                            except Exception:
                                pass
                        # Restore legend position after savefig (which may have changed layout)
                        if saved_legend_pos is not None:
                            try:
                                fig._cpc_legend_xy_in = saved_legend_pos
                                _rebuild_legend(ax, ax2, file_data)
                                fig.canvas.draw_idle()
                            except Exception:
                                pass
            except Exception as e:
                print(f"Export failed: {e}")
            _print_menu(); continue
        elif key == 's':
            # Save CPC session (.pkl) with all data and styles
            try:
                from .session import dump_cpc_session
                # Sync current tick/title visibility (including minors) into stored WASD state before save
                try:
                    wasd = getattr(fig, '_cpc_wasd_state', {})
                    if not isinstance(wasd, dict):
                        wasd = {}
                    # bottom
                    w = wasd.setdefault('bottom', {})
                    w['ticks'] = bool(tick_state.get('b_ticks', tick_state.get('bx', True)))
                    w['labels'] = bool(tick_state.get('b_labels', tick_state.get('bx', True)))
                    w['minor'] = bool(tick_state.get('mbx', False))
                    w['title'] = bool(ax.xaxis.label.get_visible())
                    try:
                        sp = ax.spines.get('bottom')
                        w['spine'] = bool(sp.get_visible()) if sp else w.get('spine', True)
                    except Exception:
                        pass
                    # top
                    w = wasd.setdefault('top', {})
                    w['ticks'] = bool(tick_state.get('t_ticks', tick_state.get('tx', False)))
                    w['labels'] = bool(tick_state.get('t_labels', tick_state.get('tx', False)))
                    w['minor'] = bool(tick_state.get('mtx', False))
                    w['title'] = bool(getattr(ax, '_top_xlabel_on', False))
                    try:
                        sp = ax.spines.get('top')
                        w['spine'] = bool(sp.get_visible()) if sp else w.get('spine', False)
                    except Exception:
                        pass
                    # left
                    w = wasd.setdefault('left', {})
                    w['ticks'] = bool(tick_state.get('l_ticks', tick_state.get('ly', True)))
                    w['labels'] = bool(tick_state.get('l_labels', tick_state.get('ly', True)))
                    w['minor'] = bool(tick_state.get('mly', False))
                    w['title'] = bool(ax.yaxis.label.get_visible())
                    try:
                        sp = ax.spines.get('left')
                        w['spine'] = bool(sp.get_visible()) if sp else w.get('spine', True)
                    except Exception:
                        pass
                    # right
                    w = wasd.setdefault('right', {})
                    w['ticks'] = bool(tick_state.get('r_ticks', tick_state.get('ry', True)))
                    w['labels'] = bool(tick_state.get('r_labels', tick_state.get('ry', True)))
                    w['minor'] = bool(tick_state.get('mry', False))
                    w['title'] = bool(ax2.yaxis.label.get_visible() if ax2 is not None else False)
                    try:
                        sp = ax2.spines.get('right') if ax2 is not None else None
                        w['spine'] = bool(sp.get_visible()) if sp else w.get('spine', True)
                    except Exception:
                        pass
                    setattr(fig, '_cpc_wasd_state', wasd)
                except Exception:
                    pass
                folder = choose_save_path(file_paths, purpose="CPC session save")
                if not folder:
                    _print_menu(); continue
                print(f"\nChosen path: {folder}")
                try:
                    files = sorted([f for f in os.listdir(folder) if f.lower().endswith('.pkl')])
                except Exception:
                    files = []
                if files:
                    print("Existing .pkl files:")
                    for i, f in enumerate(files, 1):
                        filepath = os.path.join(folder, f)
                        timestamp = _format_file_timestamp(filepath)
                        if timestamp:
                            print(f"  {i}: {f}  ({timestamp})")
                        else:
                            print(f"  {i}: {f}")
                last_session_path = getattr(fig, '_last_session_save_path', None)
                if last_session_path:
                    prompt = "Enter new filename (no ext needed), number to overwrite, or o to overwrite last (q=cancel): "
                else:
                    prompt = "Enter new filename (no ext needed) or number to overwrite (q=cancel): "
                choice = _safe_input(prompt).strip()
                if not choice or choice.lower() == 'q':
                    _print_menu(); continue
                if choice.lower() == 'o':
                    # Overwrite last saved session
                    if not last_session_path:
                        print("No previous save found.")
                        _print_menu(); continue
                    if not os.path.exists(last_session_path):
                        print(f"Previous save file not found: {last_session_path}")
                        _print_menu(); continue
                    yn = _safe_input(f"Overwrite '{os.path.basename(last_session_path)}'? (y/n): ").strip().lower()
                    if yn != 'y':
                        _print_menu(); continue
                    dump_cpc_session(last_session_path, fig=fig, ax=ax, ax2=ax2, sc_charge=sc_charge, sc_discharge=sc_discharge, sc_eff=sc_eff, file_data=file_data, skip_confirm=True)
                    print(f"Overwritten session to {last_session_path}")
                    _print_menu(); continue
                if choice.isdigit() and files:
                    idx = int(choice)
                    if 1 <= idx <= len(files):
                        name = files[idx-1]
                        yn = _safe_input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                        if yn != 'y':
                            _print_menu(); continue
                        target = os.path.join(folder, name)
                        dump_cpc_session(target, fig=fig, ax=ax, ax2=ax2, sc_charge=sc_charge, sc_discharge=sc_discharge, sc_eff=sc_eff, file_data=file_data, skip_confirm=True)
                        fig._last_session_save_path = target
                        _print_menu(); continue
                    else:
                        print("Invalid number.")
                        _print_menu(); continue
                if choice.lower() != 'o':
                    name = choice
                    root, ext = os.path.splitext(name)
                    if ext == '':
                        name = name + '.pkl'
                    target = name if os.path.isabs(name) else os.path.join(folder, name)
                    if os.path.exists(target):
                        yn = _safe_input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
                        if yn != 'y':
                            _print_menu(); continue
                    dump_cpc_session(target, fig=fig, ax=ax, ax2=ax2, sc_charge=sc_charge, sc_discharge=sc_discharge, sc_eff=sc_eff, file_data=file_data, skip_confirm=True)
                    fig._last_session_save_path = target
            except Exception as e:
                print(f"Save failed: {e}")
            _print_menu(); continue
        elif key == 'p':
            try:
                style_menu_active = True
                while style_menu_active:
                    # Print style info first
                    snap = _style_snapshot(fig, ax, ax2, sc_charge, sc_discharge, sc_eff, file_data)
                    snap['kind'] = 'cpc_style'  # Default, will be updated if psg is chosen
                    
                    print("\n--- CPC Style (Styles column only) ---")
                    
                    # Figure size (g command)
                    fig_cfg = snap.get('figure', {})
                    canvas = fig_cfg.get('canvas_size')
                    frame = fig_cfg.get('frame_size')
                    if canvas and all(v is not None for v in canvas):
                        print(f"Canvas size (inches): {canvas[0]:.3f} x {canvas[1]:.3f}")
                    if frame and all(v is not None for v in frame):
                        print(f"Plot frame size (inches): {frame[0]:.3f} x {frame[1]:.3f}")
                    
                    # Font (f command)
                    ft = snap.get('font', {})
                    print(f"Font: family='{ft.get('family', '')}', size={ft.get('size', '')}")
                    
                    # Line widths (l command)
                    spines = snap.get('spines', {})
                    if spines:
                        print("Spines:")
                        for name in ('bottom', 'top', 'left', 'right'):
                            props = spines.get(name, {})
                            lw = props.get('linewidth', '?')
                            vis = props.get('visible', False)
                            col = props.get('color')
                            print(f"  {name:<6} lw={lw} visible={vis} color={col}")
                    # Spine colors (k command)
                    spine_colors = snap.get('spine_colors', {})
                    if spine_colors:
                        print("Spine colors:")
                        for name, color in spine_colors.items():
                            print(f"  {name}: {color}")
                    spine_auto = snap.get('spine_colors_auto', False)
                    if spine_auto:
                        print(f"Spine colors auto: ON (capacity → left y-axis, efficiency → right y-axis)")
                    
                    ticks = snap.get('ticks', {})
                    print(f"Tick widths: x_major={ticks.get('x_major_width')}, x_minor={ticks.get('x_minor_width')}")
                    print(f"             ly_major={ticks.get('ly_major_width')}, ly_minor={ticks.get('ly_minor_width')}")
                    print(f"             ry_major={ticks.get('ry_major_width')}, ry_minor={ticks.get('ry_minor_width')}")
                    tick_direction = ticks.get('direction', 'out')
                    print(f"Tick direction: {tick_direction}")
                    
                    # Grid
                    grid_enabled = snap.get('grid', False)
                    print(f"Grid: {'enabled' if grid_enabled else 'disabled'}")
                    
                    # Multi-file colors (c command) - if available
                    multi_files = snap.get('multi_files', [])
                    if multi_files:
                        print("\nMulti-file colors:")
                        for i, finfo in enumerate(multi_files, 1):
                            vis_mark = "●" if finfo.get('visible', True) else "○"
                            fname = finfo.get('filename', 'unknown')
                            ch_col = finfo.get('charge_color', 'N/A')
                            dh_col = finfo.get('discharge_color', 'N/A')
                            ef_col = finfo.get('efficiency_color', 'N/A')
                            print(f"  {i}. {vis_mark} {fname}")
                            print(f"     charge={ch_col}, discharge={dh_col}, efficiency={ef_col}")
                    
                    # Marker sizes (m command) and Colors (c command) for single-file or default
                    s = snap.get('series', {})
                    ch = s.get('charge', {}); dh = s.get('discharge', {}); ef = s.get('efficiency', {})
                    if not multi_files:
                        # Only show single-file series info if not multi-file
                        print(f"Charge: color={ch.get('color')}, markersize={ch.get('markersize')}, alpha={ch.get('alpha')}")
                        print(f"Discharge: color={dh.get('color')}, markersize={dh.get('markersize')}, alpha={dh.get('alpha')}")
                        print(f"Efficiency: color={ef.get('color')}, markersize={ef.get('markersize')}, alpha={ef.get('alpha')}, visible={ef.get('visible')}")
                    else:
                        # Show marker sizes (common across all files in multi-mode)
                        print(f"\nMarker sizes (all files): charge={ch.get('markersize')}, discharge={dh.get('markersize')}, efficiency={ef.get('markersize')}")
                        print(f"Alpha (all files): charge={ch.get('alpha')}, discharge={dh.get('alpha')}, efficiency={ef.get('alpha')}")
                        print(f"Efficiency visible: {ef.get('visible')}")
                    
                    # Legend (h command)
                    leg_cfg = snap.get('legend', {})
                    leg_vis = leg_cfg.get('visible', False)
                    leg_pos = leg_cfg.get('position_inches')
                    if leg_pos:
                        print(f"Legend: visible={leg_vis}, position (inches from center)=({leg_pos[0]:.3f}, {leg_pos[1]:.3f})")
                    else:
                        print(f"Legend: visible={leg_vis}, position=auto")
                    
                    # Toggle axes (t command) - Per-side matrix (20 parameters)
                    def _onoff(v):
                        return 'ON ' if bool(v) else 'off'
                    
                    wasd = snap.get('wasd_state', {})
                    if wasd:
                        print("Per-side: spine, major, minor, labels, title")
                        for side in ('bottom', 'top', 'left', 'right'):
                            s = wasd.get(side, {})
                            spine_val = _onoff(s.get('spine', False))
                            major_val = _onoff(s.get('ticks', False))
                            minor_val = _onoff(s.get('minor', False))
                            labels_val = _onoff(s.get('labels', False))
                            title_val = _onoff(s.get('title', False))
                            print(f"  {side:<6}: spine={spine_val} major={major_val} minor={minor_val} labels={labels_val} title={title_val}")
                    
                    print("--- End Style ---\n")
                    
                    # List available style files (.bps, .bpsg, .bpcfg) in Styles/ subdirectory
                    style_file_list = list_files_in_subdirectory(('.bps', '.bpsg', '.bpcfg'), 'style')
                    _bpcfg_files = [f[0] for f in style_file_list]
                    if _bpcfg_files:
                        print("Existing style files in Styles/ (.bps/.bpsg):")
                        for _i, (fname, fpath) in enumerate(style_file_list, 1):
                            timestamp = _format_file_timestamp(fpath)
                            if timestamp:
                                print(f"  {_i}: {fname}  ({timestamp})")
                            else:
                                print(f"  {_i}: {fname}")
                    
                    last_style_path = getattr(fig, '_last_style_export_path', None)
                    if last_style_path:
                        sub = _safe_input(_colorize_prompt("Style submenu: (e=export, o=overwrite last, q=return, r=refresh): ")).strip().lower()
                    else:
                        sub = _safe_input(_colorize_prompt("Style submenu: (e=export, q=return, r=refresh): ")).strip().lower()
                    if sub == 'q':
                        break
                    if sub == 'r' or sub == '':
                        continue
                    if sub == 'o':
                        # Overwrite last exported style file
                        if not last_style_path:
                            print("No previous export found.")
                            continue
                        if not os.path.exists(last_style_path):
                            print(f"Previous export file not found: {last_style_path}")
                            continue
                        yn = _safe_input(f"Overwrite '{os.path.basename(last_style_path)}'? (y/n): ").strip().lower()
                        if yn != 'y':
                            continue
                        # Rebuild config based on current state
                        snap = _style_snapshot(fig, ax, ax2, sc_charge, sc_discharge, sc_eff, file_data)
                        # Determine if last export was style-only or style+geometry
                        try:
                            with open(last_style_path, 'r', encoding='utf-8') as f:
                                old_cfg = json.load(f)
                            if old_cfg.get('kind') == 'cpc_style_geom':
                                snap['kind'] = 'cpc_style_geom'
                                snap['geometry'] = _get_geometry_snapshot(ax, ax2)
                            else:
                                snap['kind'] = 'cpc_style'
                        except Exception:
                            snap['kind'] = 'cpc_style'
                        with open(last_style_path, 'w', encoding='utf-8') as f:
                            json.dump(snap, f, indent=2)
                        print(f"Overwritten style to {last_style_path}")
                        style_menu_active = False
                        break
                    if sub == 'e':
                        # Ask for ps or psg
                        print("Export options:")
                        print("  ps  = style only (.bps)")
                        print("  psg = style + geometry (.bpsg)")
                        exp_choice = _safe_input(_colorize_prompt("Export choice (ps/psg, q=cancel): ")).strip().lower()
                        if not exp_choice or exp_choice == 'q':
                            print("Style export canceled.")
                            continue
                        
                        if exp_choice == 'ps':
                            # Style only
                            snap = _style_snapshot(fig, ax, ax2, sc_charge, sc_discharge, sc_eff, file_data)
                            snap['kind'] = 'cpc_style'
                            default_ext = '.bps'
                        elif exp_choice == 'psg':
                            # Style + Geometry
                            snap = _style_snapshot(fig, ax, ax2, sc_charge, sc_discharge, sc_eff, file_data)
                            snap['kind'] = 'cpc_style_geom'
                            snap['geometry'] = _get_geometry_snapshot(ax, ax2)
                            default_ext = '.bpsg'
                            geom = snap.get('geometry', {})
                            print("\n--- Geometry ---")
                            print(f"X-axis label: {geom.get('xlabel', '')}")
                            print(f"Y-axis label (left): {geom.get('ylabel_left', '')}")
                            if 'ylabel_right' in geom:
                                print(f"Y-axis label (right): {geom.get('ylabel_right', '')}")
                            xlim = geom.get('xlim', [])
                            if xlim and len(xlim) == 2:
                                print(f"X limits: {xlim[0]:.4g} to {xlim[1]:.4g}")
                            ylim_l = geom.get('ylim_left', [])
                            if ylim_l and len(ylim_l) == 2:
                                print(f"Y limits (left): {ylim_l[0]:.4g} to {ylim_l[1]:.4g}")
                            ylim_r = geom.get('ylim_right', [])
                            if ylim_r and len(ylim_r) == 2:
                                print(f"Y limits (right): {ylim_r[0]:.4g} to {ylim_r[1]:.4g}")
                        else:
                            print(f"Unknown option: {exp_choice}")
                            continue
                        
                        save_base = choose_save_path(file_paths, purpose="style export")
                        if not save_base:
                            print("Style export canceled.")
                            continue
                        print(f"\nChosen path: {save_base}")
                        style_extensions = ('.bps', '.bpsg', '.bpcfg')
                        file_list = list_files_in_subdirectory(style_extensions, 'style', base_path=save_base)
                        files = [f[0] for f in file_list]
                        if files:
                            styles_dir = os.path.join(save_base, 'Styles')
                            print(f"Existing {default_ext} files in {styles_dir}:")
                            for i, (fname, fpath) in enumerate(file_list, 1):
                                timestamp = _format_file_timestamp(fpath)
                                if timestamp:
                                    print(f"  {i}: {fname}  ({timestamp})")
                                else:
                                    print(f"  {i}: {fname}")
                        if last_style_path:
                            choice = _safe_input("Enter new filename, number to overwrite, or o to overwrite last (q=cancel): ").strip()
                        else:
                            choice = _safe_input("Enter new filename or number to overwrite (q=cancel): ").strip()
                        if not choice or choice.lower() == 'q':
                            print("Style export canceled.")
                            continue
                        if choice.lower() == 'o':
                            # Overwrite last exported style file
                            if not last_style_path:
                                print("No previous export found.")
                                continue
                            if not os.path.exists(last_style_path):
                                print(f"Previous export file not found: {last_style_path}")
                                continue
                            yn = _safe_input(f"Overwrite '{os.path.basename(last_style_path)}'? (y/n): ").strip().lower()
                            if yn != 'y':
                                continue
                            # Rebuild config based on current state
                            snap = _style_snapshot(fig, ax, ax2, sc_charge, sc_discharge, sc_eff, file_data)
                            # Determine if last export was style-only or style+geometry
                            try:
                                with open(last_style_path, 'r', encoding='utf-8') as f:
                                    old_cfg = json.load(f)
                                if old_cfg.get('kind') == 'cpc_style_geom':
                                    snap['kind'] = 'cpc_style_geom'
                                    snap['geometry'] = _get_geometry_snapshot(ax, ax2)
                                else:
                                    snap['kind'] = 'cpc_style'
                            except Exception:
                                snap['kind'] = 'cpc_style'
                            with open(last_style_path, 'w', encoding='utf-8') as f:
                                json.dump(snap, f, indent=2)
                            print(f"Overwritten style to {last_style_path}")
                            style_menu_active = False
                            break
                        target = None
                        if choice.isdigit() and files:
                            idx = int(choice)
                            if 1 <= idx <= len(files):
                                name = files[idx-1]
                                yn = _safe_input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                                if yn == 'y':
                                    target = file_list[idx-1][1]  # Full path from list
                            else:
                                print("Invalid number.")
                                continue
                        else:
                            name = choice
                            # Add default extension if no extension provided
                            if not any(name.lower().endswith(ext) for ext in ['.bps', '.bpsg', '.bpcfg']):
                                name = name + default_ext
                            # Use organized path unless it's an absolute path
                            if os.path.isabs(name):
                                target = name
                            else:
                                target = get_organized_path(name, 'style', base_path=save_base)
                            if os.path.exists(target):
                                yn = _safe_input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
                                if yn != 'y':
                                    target = None
                        if target:
                            with open(target, 'w', encoding='utf-8') as f:
                                json.dump(snap, f, indent=2)
                            print(f"Exported CPC style to {target}")
                            fig._last_style_export_path = target
                        style_menu_active = False  # Exit style submenu and return to main menu
                        break
                    else:
                        print("Unknown choice.")
            except Exception as e:
                print(f"Error in style submenu: {e}")
            _print_menu(); continue
        elif key == 'i':
            try:
                path = choose_style_file(file_paths, purpose="style import")
                if not path:
                    _print_menu(); continue
                push_state("import-style")
                with open(path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                
                # Check file type
                kind = cfg.get('kind', '')
                if kind not in ('cpc_style', 'cpc_style_geom'):
                    print("Not a CPC style file."); _print_menu(); continue
                
                has_geometry = (kind == 'cpc_style_geom' and 'geometry' in cfg)
                
                # Apply style
                _apply_style(fig, ax, ax2, sc_charge, sc_discharge, sc_eff, cfg, file_data)
                
                # Apply geometry if present
                if has_geometry:
                    try:
                        geom = cfg.get('geometry', {})
                        if 'xlabel' in geom and geom['xlabel']:
                            ax.set_xlabel(geom['xlabel'])
                        if 'ylabel_left' in geom and geom['ylabel_left']:
                            ax.set_ylabel(geom['ylabel_left'])
                        if ax2 is not None and 'ylabel_right' in geom and geom['ylabel_right']:
                            ax2.set_ylabel(geom['ylabel_right'])
                        if 'xlim' in geom and isinstance(geom['xlim'], list) and len(geom['xlim']) == 2:
                            ax.set_xlim(geom['xlim'][0], geom['xlim'][1])
                        if 'ylim_left' in geom and isinstance(geom['ylim_left'], list) and len(geom['ylim_left']) == 2:
                            ax.set_ylim(geom['ylim_left'][0], geom['ylim_left'][1])
                        if ax2 is not None and 'ylim_right' in geom and isinstance(geom['ylim_right'], list) and len(geom['ylim_right']) == 2:
                            ax2.set_ylim(geom['ylim_right'][0], geom['ylim_right'][1])
                        print("Applied geometry (labels and limits)")
                        fig.canvas.draw_idle()
                    except Exception as e:
                        print(f"Warning: Could not apply geometry: {e}")
                        
            except Exception as e:
                print(f"Error importing style: {e}")
            _print_menu(); continue
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
            _print_menu(); continue
        elif key == 'h':
            # Legend submenu: toggle visibility, set position in inches relative to canvas center (0,0)
            try:
                # If no stored inches yet, try computing from the current legend bbox
                try:
                    if not hasattr(fig, '_cpc_legend_xy_in') or getattr(fig, '_cpc_legend_xy_in') is None:
                        leg0 = ax.get_legend()
                        if leg0 is not None:
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
                                # Convert display -> figure fraction
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
                # Show current status and position
                leg = ax.get_legend()
                vis = bool(leg.get_visible()) if leg is not None else False
                fw, fh = fig.get_size_inches()
                xy_in = getattr(fig, '_cpc_legend_xy_in', (0.0, 0.0))
                xy_in = _sanitize_legend_offset(xy_in) or (0.0, 0.0)
                print(f"Legend is {'ON' if vis else 'off'}; position (inches from center): x={xy_in[0]:.2f}, y={xy_in[1]:.2f}")
                while True:
                    sub = _safe_input("Legend: t=toggle, p=set position, q=back: ").strip().lower()
                    if not sub:
                        continue
                    if sub == 'q':
                        break
                    if sub == 't':
                        try:
                            push_state("legend-toggle")
                            leg = ax.get_legend()
                            if leg is not None and leg.get_visible():
                                leg.set_visible(False)
                            else:
                                # Ensure a legend exists at the stored position
                                H, L = _visible_handles_labels(ax, ax2)
                                if H:
                                    offset = _sanitize_legend_offset(getattr(fig, '_cpc_legend_xy_in', None))
                                    if offset is not None:
                                        fig._cpc_legend_xy_in = offset
                                        _apply_legend_position()
                                    else:
                                        _legend_no_frame(ax, H, L, loc='best', borderaxespad=1.0)
                            fig.canvas.draw_idle()
                        except Exception:
                            pass
                    elif sub == 'p':
                        # Position submenu with x and y subcommands
                        while True:
                            xy_in = getattr(fig, '_cpc_legend_xy_in', (0.0, 0.0))
                            xy_in = _sanitize_legend_offset(xy_in) or (0.0, 0.0)
                            print(f"Current position: x={xy_in[0]:.2f}, y={xy_in[1]:.2f}")
                            pos_cmd = _safe_input("Position: (x y) or x=x only, y=y only, q=back: ").strip().lower()
                            if not pos_cmd or pos_cmd == 'q':
                                break
                            if pos_cmd == 'x':
                                # X only: stay in loop
                                while True:
                                    xy_in = getattr(fig, '_cpc_legend_xy_in', (0.0, 0.0))
                                    xy_in = _sanitize_legend_offset(xy_in) or (0.0, 0.0)
                                    print(f"Current position: x={xy_in[0]:.2f}, y={xy_in[1]:.2f}")
                                    val = _safe_input(f"Enter new x position (current y: {xy_in[1]:.2f}, q=back): ").strip()
                                    if not val or val.lower() == 'q':
                                        break
                                    try:
                                        x_in = float(val)
                                    except (ValueError, KeyboardInterrupt):
                                        print("Invalid number, ignored.")
                                        continue
                                    push_state("legend-position")
                                    try:
                                        fig._cpc_legend_xy_in = (x_in, xy_in[1])
                                        fig._cpc_legend_xy_in = _sanitize_legend_offset(fig._cpc_legend_xy_in)
                                        _apply_legend_position()
                                        fig.canvas.draw_idle()
                                        print(f"Legend position updated: x={x_in:.2f}, y={xy_in[1]:.2f}")
                                    except Exception:
                                        pass
                            elif pos_cmd == 'y':
                                # Y only: stay in loop
                                while True:
                                    xy_in = getattr(fig, '_cpc_legend_xy_in', (0.0, 0.0))
                                    xy_in = _sanitize_legend_offset(xy_in) or (0.0, 0.0)
                                    print(f"Current position: x={xy_in[0]:.2f}, y={xy_in[1]:.2f}")
                                    val = _safe_input(f"Enter new y position (current x: {xy_in[0]:.2f}, q=back): ").strip()
                                    if not val or val.lower() == 'q':
                                        break
                                    try:
                                        y_in = float(val)
                                    except (ValueError, KeyboardInterrupt):
                                        print("Invalid number, ignored.")
                                        continue
                                    push_state("legend-position")
                                    try:
                                        fig._cpc_legend_xy_in = (xy_in[0], y_in)
                                        fig._cpc_legend_xy_in = _sanitize_legend_offset(fig._cpc_legend_xy_in)
                                        _apply_legend_position()
                                        fig.canvas.draw_idle()
                                        print(f"Legend position updated: x={xy_in[0]:.2f}, y={y_in:.2f}")
                                    except Exception:
                                        pass
                            else:
                                # Try to parse as "x y" format
                                parts = pos_cmd.replace(',', ' ').split()
                                if len(parts) != 2:
                                    print("Need two numbers or 'x'/'y' command."); continue
                                try:
                                    x_in = float(parts[0]); y_in = float(parts[1])
                                except Exception:
                                    print("Invalid numbers."); continue
                                push_state("legend-position")
                                try:
                                    fig._cpc_legend_xy_in = (x_in, y_in)
                                    fig._cpc_legend_xy_in = _sanitize_legend_offset(fig._cpc_legend_xy_in)
                                    _apply_legend_position()
                                    fig.canvas.draw_idle()
                                    print(f"Legend position updated: x={x_in:.2f}, y={y_in:.2f}")
                                except Exception:
                                    pass
                    else:
                        print("Unknown option.")
            except Exception:
                pass
            _print_menu(); continue
        elif key == 'f':
            sub = _safe_input("Font: f=family, s=size, q=back: ").strip().lower()
            if sub == 'q' or not sub:
                _print_menu(); continue
            if sub == 'f':
                fam = _safe_input("Enter font family (e.g., Arial, DejaVu Sans): ").strip()
                if fam:
                    try:
                        push_state("font-family")
                        plt.rcParams['font.family'] = 'sans-serif'
                        plt.rcParams['font.sans-serif'] = [fam, 'DejaVu Sans', 'Arial', 'Helvetica']
                        # Apply to labels, ticks, and duplicate artists immediately
                        for a in (ax, ax2):
                            try:
                                a.xaxis.label.set_family(fam); a.yaxis.label.set_family(fam)
                            except Exception:
                                pass
                            try:
                                for t in a.get_xticklabels() + a.get_yticklabels():
                                    t.set_family(fam)
                            except Exception:
                                pass
                            # Update top and right tick labels (label2)
                            try:
                                for tick in a.xaxis.get_major_ticks():
                                    if hasattr(tick, 'label2'):
                                        tick.label2.set_family(fam)
                                for tick in a.yaxis.get_major_ticks():
                                    if hasattr(tick, 'label2'):
                                        tick.label2.set_family(fam)
                            except Exception:
                                pass
                        try:
                            art = getattr(ax, '_top_xlabel_artist', None)
                            if art is not None:
                                art.set_fontfamily(fam)
                            # Also update the new text artist
                            txt = getattr(ax, '_top_xlabel_text', None)
                            if txt is not None:
                                txt.set_fontfamily(fam)
                        except Exception:
                            pass
                        try:
                            # Right ylabel artist is on ax2, not ax
                            art = getattr(ax2, '_right_ylabel_artist', None)
                            if art is not None:
                                art.set_fontfamily(fam)
                        except Exception:
                            pass
                        # Update legend font
                        try:
                            leg = ax.get_legend()
                            if leg is not None:
                                for txt in leg.get_texts():
                                    txt.set_fontfamily(fam)
                        except Exception:
                            pass
                        fig.canvas.draw_idle()
                    except Exception:
                        pass
            elif sub == 's':
                val = _safe_input("Enter font size (number): ").strip()
                try:
                    size = float(val)
                    push_state("font-size")
                    plt.rcParams['font.size'] = size
                    # Apply to labels, ticks, and duplicate artists immediately
                    for a in (ax, ax2):
                        try:
                            a.xaxis.label.set_size(size)
                            a.yaxis.label.set_size(size)
                        except Exception:
                            pass
                        try:
                            for t in a.get_xticklabels() + a.get_yticklabels():
                                t.set_size(size)
                        except Exception:
                            pass
                        # Update top and right tick labels (label2)
                        try:
                            for tick in a.xaxis.get_major_ticks():
                                if hasattr(tick, 'label2'):
                                    tick.label2.set_size(size)
                            for tick in a.yaxis.get_major_ticks():
                                if hasattr(tick, 'label2'):
                                    tick.label2.set_size(size)
                        except Exception:
                            pass
                    try:
                        art = getattr(ax, '_top_xlabel_artist', None)
                        if art is not None:
                            art.set_fontsize(size)
                        # Also update the new text artist
                        txt = getattr(ax, '_top_xlabel_text', None)
                        if txt is not None:
                            txt.set_fontsize(size)
                    except Exception:
                        pass
                    try:
                        # Right ylabel artist is on ax2, not ax
                        art = getattr(ax2, '_right_ylabel_artist', None)
                        if art is not None:
                            art.set_fontsize(size)
                    except Exception:
                        pass
                    # Update legend font size
                    try:
                        leg = ax.get_legend()
                        if leg is not None:
                            for txt in leg.get_texts():
                                txt.set_fontsize(size)
                    except Exception:
                        pass
                    fig.canvas.draw_idle()
                except Exception:
                    print("Invalid size.")
            _print_menu(); continue
        elif key == 'l':
            # Line widths submenu: frame/ticks vs grid
            try:
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
                while True:
                    # Show current widths summary
                    try:
                        cur_sp_lw = {name: (ax.spines.get(name).get_linewidth() if ax.spines.get(name) else None)
                                      for name in ('bottom','top','left','right')}
                    except Exception:
                        cur_sp_lw = {}
                    x_maj = _tick_width(ax.xaxis, 'major')
                    x_min = _tick_width(ax.xaxis, 'minor')
                    ly_maj = _tick_width(ax.yaxis, 'major')
                    ly_min = _tick_width(ax.yaxis, 'minor')
                    ry_maj = _tick_width(ax2.yaxis, 'major')
                    ry_min = _tick_width(ax2.yaxis, 'minor')
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
                        parts = fw_in.split()
                        try:
                            push_state("framewidth")
                            if len(parts) == 1:
                                frame_w = float(parts[0])
                                tick_major = frame_w
                                tick_minor = frame_w * 0.6
                            else:
                                frame_w = float(parts[0])
                                tick_major = float(parts[1])
                                tick_minor = float(tick_major) * 0.7
                            # Set frame width for all spines (ax and ax2)
                            for sp in ax.spines.values():
                                sp.set_linewidth(frame_w)
                            for sp in ax2.spines.values():
                                sp.set_linewidth(frame_w)
                            # Set tick widths for both axes
                            ax.tick_params(which='major', width=tick_major)
                            ax.tick_params(which='minor', width=tick_minor)
                            ax2.tick_params(which='major', width=tick_major)
                            ax2.tick_params(which='minor', width=tick_minor)
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
            _print_menu(); continue
        elif key == 'm':
            try:
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
                spec = _safe_input("Set marker size: 'c <ms>', 'd <ms>', 'e <ms>' (q=cancel): ").strip().lower()
                if not spec or spec == 'q':
                    _print_menu(); continue
                parts = spec.split()
                if len(parts) != 2:
                    print("Need two tokens."); _print_menu(); continue
                role, val = parts[0], parts[1]
                try:
                    num = float(val)
                    push_state("marker-size")
                    if role == 'c' and hasattr(sc_charge, 'set_sizes'):
                        sc_charge.set_sizes([num])
                    elif role == 'd' and hasattr(sc_discharge, 'set_sizes'):
                        sc_discharge.set_sizes([num])
                    elif role == 'e' and hasattr(sc_eff, 'set_sizes'):
                        sc_eff.set_sizes([num])
                    fig.canvas.draw_idle()
                except Exception:
                    print("Invalid value.")
            except Exception as e:
                print(f"Error: {e}")
            _print_menu(); continue
        elif key == 't':
            # Unified WASD toggles for spines/ticks/minor/labels/title per side
            # Import UI positioning functions locally to ensure they're accessible in nested functions
            from .ui import position_top_xlabel as _ui_position_top_xlabel, position_bottom_xlabel as _ui_position_bottom_xlabel, position_left_ylabel as _ui_position_left_ylabel, position_right_ylabel as _ui_position_right_ylabel
            
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
                    # If no changed_sides specified, reposition all sides (for load style, etc.)
                    if changed_sides is None:
                        changed_sides = {'bottom', 'top', 'left', 'right'}
                    
                    # Apply spines
                    # Note: top and bottom spines are shared between ax and ax2
                    try:
                        ax.spines['top'].set_visible(bool(wasd['top']['spine']))
                        ax.spines['bottom'].set_visible(bool(wasd['bottom']['spine']))
                        ax.spines['left'].set_visible(bool(wasd['left']['spine']))
                        # Also control top/bottom on ax2 since they're shared
                        ax2.spines['top'].set_visible(bool(wasd['top']['spine']))
                        ax2.spines['bottom'].set_visible(bool(wasd['bottom']['spine']))
                    except Exception:
                        pass
                    try:
                        ax2.spines['right'].set_visible(bool(wasd['right']['spine']))
                    except Exception:
                        pass
                    # Major ticks and tick labels
                    try:
                        ax.tick_params(axis='x', top=bool(wasd['top']['ticks']), bottom=bool(wasd['bottom']['ticks']),
                                       labeltop=bool(wasd['top']['labels']), labelbottom=bool(wasd['bottom']['labels']))
                        ax.tick_params(axis='y', left=bool(wasd['left']['ticks']), labelleft=bool(wasd['left']['labels']))
                        ax2.tick_params(axis='y', right=bool(wasd['right']['ticks']), labelright=bool(wasd['right']['labels']))
                    except Exception:
                        pass
                    # Minor ticks
                    try:
                        if wasd['top']['minor'] or wasd['bottom']['minor']:
                            ax.xaxis.set_minor_locator(AutoMinorLocator())
                            ax.xaxis.set_minor_formatter(NullFormatter())
                        else:
                            # Clear minor locator if no minor ticks are enabled
                            ax.xaxis.set_minor_locator(NullLocator())
                            ax.xaxis.set_minor_formatter(NullFormatter())
                        ax.tick_params(axis='x', which='minor', top=bool(wasd['top']['minor']), bottom=bool(wasd['bottom']['minor']),
                                       labeltop=False, labelbottom=False)
                    except Exception:
                        pass
                    try:
                        if wasd['left']['minor']:
                            ax.yaxis.set_minor_locator(AutoMinorLocator())
                            ax.yaxis.set_minor_formatter(NullFormatter())
                        else:
                            # Clear minor locator if no minor ticks are enabled
                            ax.yaxis.set_minor_locator(NullLocator())
                            ax.yaxis.set_minor_formatter(NullFormatter())
                        ax.tick_params(axis='y', which='minor', left=bool(wasd['left']['minor']), labelleft=False)
                    except Exception:
                        pass
                    try:
                        if wasd['right']['minor']:
                            ax2.yaxis.set_minor_locator(AutoMinorLocator())
                            ax2.yaxis.set_minor_formatter(NullFormatter())
                        else:
                            # Clear minor locator if no minor ticks are enabled
                            ax2.yaxis.set_minor_locator(NullLocator())
                            ax2.yaxis.set_minor_formatter(NullFormatter())
                        ax2.tick_params(axis='y', which='minor', right=bool(wasd['right']['minor']), labelright=False)
                    except Exception:
                        pass
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
                    if 'bottom' in changed_sides:
                        _ui_position_bottom_xlabel(ax, fig, tick_state)
                    if 'left' in changed_sides:
                        _ui_position_left_ylabel(ax, fig, tick_state)

                def _print_wasd():
                    def b(v):
                        return 'ON ' if bool(v) else 'off'
                    print(_colorize_inline_commands("State (top/bottom/left/right):"))
                    print(_colorize_inline_commands(f"  top    w1:{b(wasd['top']['spine'])} w2:{b(wasd['top']['ticks'])} w3:{b(wasd['top']['minor'])} w4:{b(wasd['top']['labels'])} w5:{b(wasd['top']['title'])}"))
                    print(_colorize_inline_commands(f"  bottom s1:{b(wasd['bottom']['spine'])} s2:{b(wasd['bottom']['ticks'])} s3:{b(wasd['bottom']['minor'])} s4:{b(wasd['bottom']['labels'])} s5:{b(wasd['bottom']['title'])}"))
                    print(_colorize_inline_commands(f"  left   a1:{b(wasd['left']['spine'])} a2:{b(wasd['left']['ticks'])} a3:{b(wasd['left']['minor'])} a4:{b(wasd['left']['labels'])} a5:{b(wasd['left']['title'])}"))
                    print(_colorize_inline_commands(f"  right  d1:{b(wasd['right']['spine'])} d2:{b(wasd['right']['ticks'])} d3:{b(wasd['right']['minor'])} d4:{b(wasd['right']['labels'])} d5:{b(wasd['right']['title'])}"))

                print(_colorize_inline_commands("WASD toggles: direction (w/a/s/d) x action (1..5)"))
                print(_colorize_inline_commands("  1=spine   2=ticks   3=minor ticks   4=tick labels   5=axis title"))
                print(_colorize_inline_commands("Examples: 'w2 w5' to toggle top ticks and top title; 'd2 d5' for right."))
                print(_colorize_inline_commands("Type 'i' to invert tick direction, 'l' to change tick length, 'list' to show current state, 'q' to go back."))
                print(_colorize_inline_commands("  p = adjust title offsets (w=top, s=bottom, a=left, d=right)"))
                while True:
                    cmd = _safe_input(_colorize_prompt("t> ")).strip().lower()
                    if not cmd:
                        continue
                    if cmd == 'q':
                        break
                    if cmd == 'i':
                        # Invert tick direction (toggle between 'out' and 'in')
                        push_state("tick-direction")
                        current_dir = getattr(fig, '_tick_direction', 'out')
                        new_dir = 'in' if current_dir == 'out' else 'out'
                        setattr(fig, '_tick_direction', new_dir)
                        ax.tick_params(axis='both', which='both', direction=new_dir)
                        ax2.tick_params(axis='both', which='both', direction=new_dir)
                        print(f"Tick direction: {new_dir}")
                        try:
                            fig.canvas.draw()
                        except Exception:
                            fig.canvas.draw_idle()
                        continue
                    if cmd == 'l':
                        # Change tick length (major and minor automatically set to 70%)
                        try:
                            # Get current major tick length from axes
                            current_major = ax.xaxis.get_major_ticks()[0].tick1line.get_markersize() if ax.xaxis.get_major_ticks() else 4.0
                            print(f"Current major tick length: {current_major}")
                            new_length_str = _safe_input("Enter new major tick length (e.g., 6.0): ").strip()
                            if not new_length_str:
                                continue
                            new_major = float(new_length_str)
                            if new_major <= 0:
                                print("Length must be positive.")
                                continue
                            new_minor = new_major * 0.7  # Auto-set minor to 70%
                            push_state("tick-length")
                            # Apply to all four axes on both ax and ax2
                            ax.tick_params(axis='both', which='major', length=new_major)
                            ax.tick_params(axis='both', which='minor', length=new_minor)
                            ax2.tick_params(axis='both', which='major', length=new_major)
                            ax2.tick_params(axis='both', which='minor', length=new_minor)
                            # Store for persistence
                            if not hasattr(fig, '_tick_lengths'):
                                fig._tick_lengths = {}
                            fig._tick_lengths.update({'major': new_major, 'minor': new_minor})
                            print(f"Set major tick length: {new_major}, minor: {new_minor:.2f}")
                            try:
                                fig.canvas.draw()
                            except Exception:
                                fig.canvas.draw_idle()
                        except ValueError:
                            print("Invalid number.")
                        except Exception as e:
                            print(f"Error setting tick length: {e}")
                        continue
                    if cmd == 'list':
                        _print_wasd(); continue
                    if cmd == 'p':
                        # Title offset menu
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

                        def _right_menu():
                            if not ax2.get_ylabel():
                                print("Right title is currently hidden.")
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
                                _ui_position_right_ylabel(ax2, fig, tick_state)
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
                            choice = _safe_input(_colorize_prompt("p> ")).strip().lower()
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
                                _ui_position_right_ylabel(ax2, fig, tick_state)
                                try:
                                    fig.canvas.draw_idle()
                                except Exception:
                                    pass
                                print("Reset manual offsets for all titles.")
                                continue
                            print("Unknown option. Use w/s/a/d/r/q.")
                        continue
                    parts = cmd.split()
                    changed = False
                    changed_sides = set()  # Track which sides were affected
                    for p in parts:
                        if len(p) != 2:
                            print(f"Unknown code: {p}"); continue
                        d, n = p[0], p[1]
                        side = {'w':'top','a':'left','s':'bottom','d':'right'}.get(d)
                        if side is None or n not in '12345':
                            print(f"Unknown code: {p}"); continue
                        key = { '1':'spine', '2':'ticks', '3':'minor', '4':'labels', '5':'title' }[n]
                        wasd[side][key] = not bool(wasd[side][key])
                        changed = True
                        # Track which side was changed to only reposition affected sides
                        # Labels and titles affect positioning, but spine/tick toggles don't necessarily
                        if key in ('labels', 'title'):
                            changed_sides.add(side)
                        # Keep tick_state in sync with new separate keys + legacy combined flags
                        if side == 'top' and key == 'ticks':
                            tick_state['t_ticks'] = bool(wasd['top']['ticks'])
                            tick_state['tx'] = bool(wasd['top']['ticks'] and wasd['top']['labels'])
                        if side == 'top' and key == 'labels':
                            tick_state['t_labels'] = bool(wasd['top']['labels'])
                            tick_state['tx'] = bool(wasd['top']['ticks'] and wasd['top']['labels'])
                        if side == 'bottom' and key == 'ticks':
                            tick_state['b_ticks'] = bool(wasd['bottom']['ticks'])
                            tick_state['bx'] = bool(wasd['bottom']['ticks'] and wasd['bottom']['labels'])
                        if side == 'bottom' and key == 'labels':
                            tick_state['b_labels'] = bool(wasd['bottom']['labels'])
                            tick_state['bx'] = bool(wasd['bottom']['ticks'] and wasd['bottom']['labels'])
                        if side == 'left' and key == 'ticks':
                            tick_state['l_ticks'] = bool(wasd['left']['ticks'])
                            tick_state['ly'] = bool(wasd['left']['ticks'] and wasd['left']['labels'])
                        if side == 'left' and key == 'labels':
                            tick_state['l_labels'] = bool(wasd['left']['labels'])
                            tick_state['ly'] = bool(wasd['left']['ticks'] and wasd['left']['labels'])
                        if side == 'right' and key == 'ticks':
                            tick_state['r_ticks'] = bool(wasd['right']['ticks'])
                            tick_state['ry'] = bool(wasd['right']['ticks'] and wasd['right']['labels'])
                        if side == 'right' and key == 'labels':
                            tick_state['r_labels'] = bool(wasd['right']['labels'])
                            tick_state['ry'] = bool(wasd['right']['ticks'] and wasd['right']['labels'])
                        if side == 'top' and key == 'minor':
                            tick_state['mtx'] = bool(wasd['top']['minor'])
                        if side == 'bottom' and key == 'minor':
                            tick_state['mbx'] = bool(wasd['bottom']['minor'])
                        if side == 'left' and key == 'minor':
                            tick_state['mly'] = bool(wasd['left']['minor'])
                        if side == 'right' and key == 'minor':
                            tick_state['mry'] = bool(wasd['right']['minor'])
                    if changed:
                        push_state("wasd-toggle")
                        _apply_wasd(changed_sides if changed_sides else None)
                        # Single draw at the end after all positioning is complete
                        try:
                            fig.canvas.draw()
                        except Exception:
                            fig.canvas.draw_idle()
            except Exception as e:
                print(f"Error in WASD tick menu: {e}")
            _print_menu(); continue
        elif key == 'g':
            while True:
                print("Geometry: p=plot frame, c=canvas, q=back")
                sub = _safe_input("Geom> ").strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub == 'p':
                    # We don't have y_data_list/labels; we just trigger a redraw after resize
                    try:
                        push_state("resize-frame")
                        resize_plot_frame(fig, ax, [], [], type('Args', (), {'stack': False})(), lambda *_: None)
                    except Exception as e:
                        print(f"Resize failed: {e}")
                elif sub == 'c':
                    try:
                        push_state("resize-canvas")
                        resize_canvas(fig, ax)
                    except Exception as e:
                        print(f"Resize failed: {e}")
            _print_menu(); continue
        elif key == 'r':
            # Rename axis titles
            print("Tip: Use LaTeX/mathtext for special characters:")
            print("  Subscript: H$_2$O → H₂O  |  Superscript: m$^2$ → m²")
            print("  Bullet: $\\bullet$ → •   |  Greek: $\\alpha$, $\\beta$  |  Angstrom: $\\AA$ → Å")
            print("  Shortcuts: g{super(-1)} → g$^{\\mathrm{-1}}$  |  Li{sub(2)}O → Li$_{\\mathrm{2}}$O")
            while True:
                print("Rename: x=x-axis, ly=left y-axis, ry=right y-axis, l=legend labels, q=back")
                sub = _safe_input("Rename> ").strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub == 'l':
                    # Rename legend labels (file name in legend)
                    if not is_multi_file:
                        # Single file mode: rename the default file
                        current_file = file_data[0]
                        sc_chg = current_file['sc_charge']
                        sc_dchg = current_file['sc_discharge']
                        sc_eff = current_file['sc_eff']
                        
                        # Get current labels
                        chg_label = sc_chg.get_label() or ''
                        dchg_label = sc_dchg.get_label() or ''
                        eff_label = sc_eff.get_label() or ''
                        
                        # Extract base filename (everything before " charge", " discharge", or " efficiency")
                        # Also handle patterns like "filename (Chg)", "filename (Dchg)", "filename (Eff)"
                        base_name = current_file.get('filename', 'Data')
                        
                        # Try to extract from labels
                        import re
                        for label in [chg_label, dchg_label, eff_label]:
                            if label:
                                # First try to extract from bracket pattern: "filename (Chg)" -> "filename"
                                bracket_match = re.search(r'^(.+?)\s*\([^)]+\)\s*$', label)
                                if bracket_match:
                                    potential_base = bracket_match.group(1).strip()
                                    if potential_base:
                                        base_name = potential_base
                                        break
                                else:
                                    # Try to extract from text suffix patterns
                                    for suffix in [' charge', ' discharge', ' efficiency']:
                                        if label.endswith(suffix):
                                            potential_base = label[:-len(suffix)].strip()
                                            if potential_base:
                                                base_name = potential_base
                                                break
                                    if base_name != current_file.get('filename', 'Data'):
                                        break
                        
                        print(f"Current file name in legend: '{base_name}'")
                        new_name = _safe_input("Enter new file name (q=cancel): ").strip()
                        if new_name and new_name.lower() != 'q':
                            new_name = convert_label_shortcuts(new_name)
                            try:
                                push_state("rename-legend")
                                
                                # Extract bracket content from original labels if present
                                import re
                                chg_bracket = ''
                                dchg_bracket = ''
                                eff_bracket = ''
                                
                                # Check for bracket patterns in original labels
                                chg_match = re.search(r'\(([^)]+)\)', chg_label)
                                if chg_match:
                                    chg_bracket = chg_match.group(1)
                                dchg_match = re.search(r'\(([^)]+)\)', dchg_label)
                                if dchg_match:
                                    dchg_bracket = dchg_match.group(1)
                                    # Fix capitalization: Dchg -> DChg
                                    if dchg_bracket.lower() == 'dchg':
                                        dchg_bracket = 'DChg'
                                eff_match = re.search(r'\(([^)]+)\)', eff_label)
                                if eff_match:
                                    eff_bracket = eff_match.group(1)
                                
                                # If no brackets found, extract from label suffix or use defaults
                                if not chg_bracket:
                                    # Try to extract from " charge" suffix
                                    if chg_label.endswith(' charge'):
                                        chg_bracket = 'Chg'
                                    else:
                                        chg_bracket = 'Chg'
                                if not dchg_bracket:
                                    # Try to extract from " discharge" suffix
                                    if dchg_label.endswith(' discharge'):
                                        dchg_bracket = 'DChg'
                                    else:
                                        dchg_bracket = 'DChg'
                                if not eff_bracket:
                                    # Try to extract from " efficiency" suffix
                                    if eff_label.endswith(' efficiency'):
                                        eff_bracket = 'Eff'
                                    else:
                                        eff_bracket = 'Eff'
                                
                                # Build new labels with brackets preserved
                                new_chg_label = f"{new_name} ({chg_bracket})"
                                new_dchg_label = f"{new_name} ({dchg_bracket})"
                                new_eff_label = f"{new_name} ({eff_bracket})"
                                
                                # Update labels
                                sc_chg.set_label(new_chg_label)
                                sc_dchg.set_label(new_dchg_label)
                                sc_eff.set_label(new_eff_label)
                                
                                # Update filename in file_data
                                current_file['filename'] = new_name
                                
                                # Rebuild legend (preserve position)
                                _rebuild_legend(ax, ax2, file_data, preserve_position=True)
                                fig.canvas.draw_idle()
                                print(f"Legend labels updated: '{new_chg_label}', '{new_dchg_label}', '{new_eff_label}'")
                            except Exception as e:
                                print(f"Error: {e}")
                    else:
                        # Multi-file mode: show file list and let user select
                        print("\nAvailable files:")
                        _print_file_list(file_data, current_file_idx)
                        file_choice = _safe_input("Enter file number to rename (q=cancel): ").strip()
                        if file_choice and file_choice.lower() != 'q':
                            try:
                                file_idx = int(file_choice) - 1
                                if 0 <= file_idx < len(file_data):
                                    current_file = file_data[file_idx]
                                    sc_chg = current_file['sc_charge']
                                    sc_dchg = current_file['sc_discharge']
                                    sc_eff = current_file['sc_eff']
                                    
                                    # Get current labels
                                    chg_label = sc_chg.get_label() or ''
                                    dchg_label = sc_dchg.get_label() or ''
                                    eff_label = sc_eff.get_label() or ''
                                    
                                    # Extract base filename
                                    base_name = current_file.get('filename', 'Data')
                                    import re
                                    for label in [chg_label, dchg_label, eff_label]:
                                        if label:
                                            # First try to extract from bracket pattern: "filename (Chg)" -> "filename"
                                            bracket_match = re.search(r'^(.+?)\s*\([^)]+\)\s*$', label)
                                            if bracket_match:
                                                potential_base = bracket_match.group(1).strip()
                                                if potential_base:
                                                    base_name = potential_base
                                                    break
                                            else:
                                                # Try to extract from text suffix patterns
                                                for suffix in [' charge', ' discharge', ' efficiency']:
                                                    if label.endswith(suffix):
                                                        potential_base = label[:-len(suffix)].strip()
                                                        if potential_base:
                                                            base_name = potential_base
                                                            break
                                                if base_name != current_file.get('filename', 'Data'):
                                                    break
                                    
                                    print(f"Current file name in legend: '{base_name}'")
                                    new_name = _safe_input("Enter new file name (q=cancel): ").strip()
                                    if new_name and new_name.lower() != 'q':
                                        new_name = convert_label_shortcuts(new_name)
                                        try:
                                            push_state("rename-legend")
                                            
                                            # Extract bracket content from original labels if present
                                            import re
                                            chg_bracket = ''
                                            dchg_bracket = ''
                                            eff_bracket = ''
                                            
                                            # Check for bracket patterns in original labels
                                            chg_match = re.search(r'\(([^)]+)\)', chg_label)
                                            if chg_match:
                                                chg_bracket = chg_match.group(1)
                                            dchg_match = re.search(r'\(([^)]+)\)', dchg_label)
                                            if dchg_match:
                                                dchg_bracket = dchg_match.group(1)
                                                # Fix capitalization: Dchg -> DChg
                                                if dchg_bracket.lower() == 'dchg':
                                                    dchg_bracket = 'DChg'
                                            eff_match = re.search(r'\(([^)]+)\)', eff_label)
                                            if eff_match:
                                                eff_bracket = eff_match.group(1)
                                            
                                            # If no brackets found, extract from label suffix or use defaults
                                            if not chg_bracket:
                                                # Try to extract from " charge" suffix
                                                if chg_label.endswith(' charge'):
                                                    chg_bracket = 'Chg'
                                                else:
                                                    chg_bracket = 'Chg'
                                            if not dchg_bracket:
                                                # Try to extract from " discharge" suffix
                                                if dchg_label.endswith(' discharge'):
                                                    dchg_bracket = 'DChg'
                                                else:
                                                    dchg_bracket = 'DChg'
                                            if not eff_bracket:
                                                # Try to extract from " efficiency" suffix
                                                if eff_label.endswith(' efficiency'):
                                                    eff_bracket = 'Eff'
                                                else:
                                                    eff_bracket = 'Eff'
                                            
                                            # Build new labels with brackets preserved
                                            new_chg_label = f"{new_name} ({chg_bracket})"
                                            new_dchg_label = f"{new_name} ({dchg_bracket})"
                                            new_eff_label = f"{new_name} ({eff_bracket})"
                                            
                                            # Update labels
                                            sc_chg.set_label(new_chg_label)
                                            sc_dchg.set_label(new_dchg_label)
                                            sc_eff.set_label(new_eff_label)
                                            
                                            # Update filename in file_data
                                            current_file['filename'] = new_name
                                            
                                            # Rebuild legend (preserve position)
                                            _rebuild_legend(ax, ax2, file_data, preserve_position=True)
                                            fig.canvas.draw_idle()
                                            print(f"Legend labels updated: '{new_chg_label}', '{new_dchg_label}', '{new_eff_label}'")
                                        except Exception as e:
                                            print(f"Error: {e}")
                                else:
                                    print("Invalid file number.")
                            except (ValueError, KeyboardInterrupt):
                                print("Invalid input.")
                elif sub == 'x':
                    current = ax.get_xlabel()
                    print(f"Current x-axis title: '{current}'")
                    new_title = _safe_input("Enter new x-axis title (q=cancel): ")
                    if new_title and new_title.lower() != 'q':
                        new_title = convert_label_shortcuts(new_title)
                        try:
                            push_state("rename-x")
                            ax.set_xlabel(new_title)
                            # Update stored titles for top/bottom
                            ax._stored_xlabel = new_title
                            ax._stored_top_xlabel = new_title
                            # If top title is visible, update it
                            if hasattr(ax, '_top_xlabel_text') and ax._top_xlabel_text is not None:
                                if ax._top_xlabel_text.get_visible():
                                    ax._top_xlabel_text.set_text(new_title)
                            fig.canvas.draw_idle()
                            print(f"X-axis title updated to: '{new_title}'")
                        except Exception as e:
                            print(f"Error: {e}")
                elif sub == 'ly':
                    current = ax.get_ylabel()
                    print(f"Current left y-axis title: '{current}'")
                    new_title = _safe_input("Enter new left y-axis title (q=cancel): ")
                    if new_title and new_title.lower() != 'q':
                        new_title = convert_label_shortcuts(new_title)
                        try:
                            push_state("rename-ly")
                            ax.set_ylabel(new_title)
                            # Update stored title
                            ax._stored_ylabel = new_title
                            fig.canvas.draw_idle()
                            print(f"Left y-axis title updated to: '{new_title}'")
                        except Exception as e:
                            print(f"Error: {e}")
                elif sub == 'ry':
                    current = ax2.get_ylabel()
                    print(f"Current right y-axis title: '{current}'")
                    new_title = _safe_input("Enter new right y-axis title (q=cancel): ")
                    if new_title and new_title.lower() != 'q':
                        new_title = convert_label_shortcuts(new_title)
                        try:
                            push_state("rename-ry")
                            ax2.set_ylabel(new_title)
                            # Update stored title
                            if not hasattr(ax2, '_stored_ylabel'):
                                ax2._stored_ylabel = ''
                            ax2._stored_ylabel = new_title
                            fig.canvas.draw_idle()
                            print(f"Right y-axis title updated to: '{new_title}'")
                        except Exception as e:
                            print(f"Error: {e}")
                else:
                    print("Unknown option.")
            _print_menu(); continue
        elif key == 'x':
            while True:
                current_xlim = ax.get_xlim()
                print(f"Current X range: {current_xlim[0]:.6g} to {current_xlim[1]:.6g}")
                rng = _safe_input("Enter x-range: min max, w=upper only, s=lower only, a=auto (restore original), q=back: ").strip()
                if not rng or rng.lower() == 'q':
                    break
                if rng.lower() == 'w':
                    # Upper only: change upper limit, fix lower - stay in loop
                    while True:
                        current_xlim = ax.get_xlim()
                        print(f"Current X range: {current_xlim[0]:.6g} to {current_xlim[1]:.6g}")
                        val = _safe_input(f"Enter new upper X limit (current lower: {current_xlim[0]:.6g}, q=back): ").strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_upper = float(val)
                        except (ValueError, KeyboardInterrupt):
                            print("Invalid value, ignored.")
                            continue
                        push_state("x-range")
                        ax.set_xlim(current_xlim[0], new_upper)
                        ax.relim()
                        ax.autoscale_view(scalex=True, scaley=False)
                        # Reapply legend position after axis change to prevent movement
                        try:
                            leg = ax.get_legend()
                            if leg is not None and leg.get_visible():
                                _apply_legend_position()
                        except Exception:
                            pass
                        fig.canvas.draw_idle()
                        print(f"X range updated: {ax.get_xlim()[0]:.6g} to {ax.get_xlim()[1]:.6g}")
                    continue
                if rng.lower() == 's':
                    # Lower only: change lower limit, fix upper - stay in loop
                    while True:
                        current_xlim = ax.get_xlim()
                        print(f"Current X range: {current_xlim[0]:.6g} to {current_xlim[1]:.6g}")
                        val = _safe_input(f"Enter new lower X limit (current upper: {current_xlim[1]:.6g}, q=back): ").strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_lower = float(val)
                        except (ValueError, KeyboardInterrupt):
                            print("Invalid value, ignored.")
                            continue
                        push_state("x-range")
                        ax.set_xlim(new_lower, current_xlim[1])
                        ax.relim()
                        ax.autoscale_view(scalex=True, scaley=False)
                        # Reapply legend position after axis change to prevent movement
                        try:
                            leg = ax.get_legend()
                            if leg is not None and leg.get_visible():
                                _apply_legend_position()
                        except Exception:
                            pass
                        fig.canvas.draw_idle()
                        print(f"X range updated: {ax.get_xlim()[0]:.6g} to {ax.get_xlim()[1]:.6g}")
                    continue
                if rng.lower() == 'a':
                    # Auto: restore original range from scatter plots
                    push_state("x-range-auto")
                    try:
                        all_x = []
                        for sc in [sc_charge, sc_discharge]:
                            if sc is not None and hasattr(sc, 'get_offsets'):
                                offsets = sc.get_offsets()
                                if offsets.size > 0:
                                    all_x.extend([offsets[:, 0].min(), offsets[:, 0].max()])
                        if all_x:
                            orig_min = min(all_x)
                            orig_max = max(all_x)
                            ax.set_xlim(orig_min, orig_max)
                            ax.relim()
                            ax.autoscale_view(scalex=True, scaley=False)
                            fig.canvas.draw_idle()
                            print(f"X range restored to original: {ax.get_xlim()[0]:.6g} to {ax.get_xlim()[1]:.6g}")
                        else:
                            print("No original data available.")
                    except Exception as e:
                        print(f"Error restoring original X range: {e}")
                    continue
                parts = rng.replace(',', ' ').split()
                if len(parts) != 2:
                    print("Need two numbers.")
                else:
                    try:
                        lo = float(parts[0]); hi = float(parts[1])
                        if lo == hi:
                            print("Min and max cannot be equal.")
                        else:
                            push_state("x-range")
                            ax.set_xlim(min(lo, hi), max(lo, hi))
                            fig.canvas.draw_idle()
                    except Exception:
                        print("Invalid numbers.")
            _print_menu(); continue
        elif key == 'y':
            while True:
                print("Y-ranges: ly=left axis, ry=right axis, q=back")
                ycmd = _safe_input("Y> ").strip().lower()
                if not ycmd:
                    continue
                if ycmd == 'q':
                    break
                if ycmd == 'ly':
                    while True:
                        current_ylim = ax.get_ylim()
                        print(f"Current left Y range: {current_ylim[0]:.6g} to {current_ylim[1]:.6g}")
                        rng = _safe_input("Enter left y-range: min max, w=upper only, s=lower only, a=auto (restore original), q=back: ").strip()
                        if not rng or rng.lower() == 'q':
                            break
                        if rng.lower() == 'w':
                            # Upper only: change upper limit, fix lower - stay in loop
                            while True:
                                current_ylim = ax.get_ylim()
                                print(f"Current left Y range: {current_ylim[0]:.6g} to {current_ylim[1]:.6g}")
                                val = _safe_input(f"Enter new upper left Y limit (current lower: {current_ylim[0]:.6g}, q=back): ").strip()
                                if not val or val.lower() == 'q':
                                    break
                                try:
                                    new_upper = float(val)
                                except (ValueError, KeyboardInterrupt):
                                    print("Invalid value, ignored.")
                                    continue
                                push_state("y-left-range")
                                ax.set_ylim(current_ylim[0], new_upper)
                                ax.relim()
                                ax.autoscale_view(scalex=False, scaley=True)
                                # Reapply legend position after axis change to prevent movement
                                try:
                                    leg = ax.get_legend()
                                    if leg is not None and leg.get_visible():
                                        _apply_legend_position()
                                except Exception:
                                    pass
                                fig.canvas.draw_idle()
                                print(f"Left Y range updated: {ax.get_ylim()[0]:.6g} to {ax.get_ylim()[1]:.6g}")
                            continue
                        if rng.lower() == 's':
                            # Lower only: change lower limit, fix upper - stay in loop
                            while True:
                                current_ylim = ax.get_ylim()
                                print(f"Current left Y range: {current_ylim[0]:.6g} to {current_ylim[1]:.6g}")
                                val = _safe_input(f"Enter new lower left Y limit (current upper: {current_ylim[1]:.6g}, q=back): ").strip()
                                if not val or val.lower() == 'q':
                                    break
                                try:
                                    new_lower = float(val)
                                except (ValueError, KeyboardInterrupt):
                                    print("Invalid value, ignored.")
                                    continue
                                push_state("y-left-range")
                                ax.set_ylim(new_lower, current_ylim[1])
                                ax.relim()
                                ax.autoscale_view(scalex=False, scaley=True)
                                # Reapply legend position after axis change to prevent movement
                                try:
                                    leg = ax.get_legend()
                                    if leg is not None and leg.get_visible():
                                        _apply_legend_position()
                                except Exception:
                                    pass
                                fig.canvas.draw_idle()
                                print(f"Left Y range updated: {ax.get_ylim()[0]:.6g} to {ax.get_ylim()[1]:.6g}")
                            continue
                        if rng.lower() == 'a':
                            # Auto: restore original range from scatter plots
                            push_state("y-left-range-auto")
                            try:
                                all_y = []
                                for sc in [sc_charge, sc_discharge]:
                                    if sc is not None and hasattr(sc, 'get_offsets'):
                                        offsets = sc.get_offsets()
                                        if offsets.size > 0:
                                            all_y.extend([offsets[:, 1].min(), offsets[:, 1].max()])
                                if all_y:
                                    orig_min = min(all_y)
                                    orig_max = max(all_y)
                                    ax.set_ylim(orig_min, orig_max)
                                    ax.relim()
                                    ax.autoscale_view(scalex=False, scaley=True)
                                    fig.canvas.draw_idle()
                                    print(f"Left Y range restored to original: {ax.get_ylim()[0]:.6g} to {ax.get_ylim()[1]:.6g}")
                                else:
                                    print("No original data available.")
                            except Exception as e:
                                print(f"Error restoring original left Y range: {e}")
                            continue
                        parts = rng.replace(',', ' ').split()
                        if len(parts) != 2:
                            print("Need two numbers."); continue
                        try:
                            lo = float(parts[0]); hi = float(parts[1])
                            if lo == hi:
                                print("Min and max cannot be equal."); continue
                            push_state("y-left-range")
                            ax.set_ylim(min(lo, hi), max(lo, hi))
                            fig.canvas.draw_idle()
                        except Exception:
                            print("Invalid numbers.")
                elif ycmd == 'ry':
                    while True:
                        try:
                            eff_on = bool(sc_eff.get_visible())
                        except Exception:
                            eff_on = True
                        if not eff_on:
                            print("Right Y is not shown; enable efficiency with 'ry' first.")
                            break
                        current_ylim = ax2.get_ylim()
                        print(f"Current right Y range: {current_ylim[0]:.6g} to {current_ylim[1]:.6g}")
                        rng = _safe_input("Enter right y-range: min max, w=upper only, s=lower only, a=auto (restore original), q=back: ").strip()
                        if not rng or rng.lower() == 'q':
                            break
                        if rng.lower() == 'w':
                            # Upper only: change upper limit, fix lower - stay in loop
                            while True:
                                current_ylim = ax2.get_ylim()
                                print(f"Current right Y range: {current_ylim[0]:.6g} to {current_ylim[1]:.6g}")
                                val = _safe_input(f"Enter new upper right Y limit (current lower: {current_ylim[0]:.6g}, q=back): ").strip()
                                if not val or val.lower() == 'q':
                                    break
                                try:
                                    new_upper = float(val)
                                except (ValueError, KeyboardInterrupt):
                                    print("Invalid value, ignored.")
                                    continue
                                push_state("y-right-range")
                                ax2.set_ylim(current_ylim[0], new_upper)
                                ax2.relim()
                                ax2.autoscale_view(scalex=False, scaley=True)
                                # Reapply legend position after axis change to prevent movement
                                try:
                                    leg = ax.get_legend()
                                    if leg is not None and leg.get_visible():
                                        _apply_legend_position()
                                except Exception:
                                    pass
                                fig.canvas.draw_idle()
                                print(f"Right Y range updated: {ax2.get_ylim()[0]:.6g} to {ax2.get_ylim()[1]:.6g}")
                            continue
                        if rng.lower() == 's':
                            # Lower only: change lower limit, fix upper - stay in loop
                            while True:
                                current_ylim = ax2.get_ylim()
                                print(f"Current right Y range: {current_ylim[0]:.6g} to {current_ylim[1]:.6g}")
                                val = _safe_input(f"Enter new lower right Y limit (current upper: {current_ylim[1]:.6g}, q=back): ").strip()
                                if not val or val.lower() == 'q':
                                    break
                                try:
                                    new_lower = float(val)
                                except (ValueError, KeyboardInterrupt):
                                    print("Invalid value, ignored.")
                                    continue
                                push_state("y-right-range")
                                ax2.set_ylim(new_lower, current_ylim[1])
                                ax2.relim()
                                ax2.autoscale_view(scalex=False, scaley=True)
                                # Reapply legend position after axis change to prevent movement
                                try:
                                    leg = ax.get_legend()
                                    if leg is not None and leg.get_visible():
                                        _apply_legend_position()
                                except Exception:
                                    pass
                                fig.canvas.draw_idle()
                                print(f"Right Y range updated: {ax2.get_ylim()[0]:.6g} to {ax2.get_ylim()[1]:.6g}")
                            continue
                        if rng.lower() == 'a':
                            # Auto: restore original range from efficiency scatter plot
                            push_state("y-right-range-auto")
                            try:
                                if sc_eff is not None and hasattr(sc_eff, 'get_offsets'):
                                    offsets = sc_eff.get_offsets()
                                    if offsets.size > 0:
                                        orig_min = float(offsets[:, 1].min())
                                        orig_max = float(offsets[:, 1].max())
                                        ax2.set_ylim(orig_min, orig_max)
                                        ax2.relim()
                                        ax2.autoscale_view(scalex=False, scaley=True)
                                        fig.canvas.draw_idle()
                                        print(f"Right Y range restored to original: {ax2.get_ylim()[0]:.6g} to {ax2.get_ylim()[1]:.6g}")
                                    else:
                                        print("No original data available.")
                                else:
                                    print("No original data available.")
                            except Exception as e:
                                print(f"Error restoring original right Y range: {e}")
                            continue
                        parts = rng.replace(',', ' ').split()
                        if len(parts) != 2:
                            print("Need two numbers."); continue
                        try:
                            lo = float(parts[0]); hi = float(parts[1])
                            if lo == hi:
                                print("Min and max cannot be equal."); continue
                            push_state("y-right-range")
                            ax2.set_ylim(min(lo, hi), max(lo, hi))
                            fig.canvas.draw_idle()
                        except Exception:
                            print("Invalid numbers.")
            _print_menu(); continue
        else:
            print("Unknown key.")
            _print_menu(); continue


__all__ = ["cpc_interactive_menu"]

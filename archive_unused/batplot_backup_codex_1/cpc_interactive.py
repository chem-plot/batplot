"""Interactive menu for Capacity-Per-Cycle (CPC) plots.

Controls focus on style/geometry, and print/export/import of a .bpcfg style.
"""
from __future__ import annotations

from typing import Dict, Optional
import json
import os

import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator, NullFormatter
import random as _random

from .ui import (
    resize_plot_frame, resize_canvas,
    update_tick_visibility as _ui_update_tick_visibility,
    position_top_xlabel as _ui_position_top_xlabel,
    position_right_ylabel as _ui_position_right_ylabel,
    position_bottom_xlabel as _ui_position_bottom_xlabel,
    position_left_ylabel as _ui_position_left_ylabel,
)
from .utils import _confirm_overwrite


def _colorize_menu(text):
    """Colorize menu items: command in cyan, colon in white, description in default."""
    if ':' not in text:
        return text
    parts = text.split(':', 1)
    cmd = parts[0].strip()
    desc = parts[1].strip() if len(parts) > 1 else ''
    return f"\033[96m{cmd}\033[0m: {desc}"  # Cyan for command, default for description


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
        "r: rename titles",
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


def _rebuild_legend(ax, ax2, file_data):
    """Rebuild legend from all visible files."""
    try:
        h1, l1 = ax.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        # Filter to only visible items
        h_all, l_all = [], []
        for h, l in zip(h1 + h2, l1 + l2):
            if h.get_visible():
                h_all.append(h)
                l_all.append(l)
        if h_all:
            ax.legend(h_all, l_all, loc='best', borderaxespad=1.0)
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
    def _tick_width(axis, which: str):
        try:
            ticks = axis.get_major_ticks() if which == 'major' else axis.get_minor_ticks()
            for t in ticks:
                ln = t.tick1line
                if ln.get_visible():
                    return ln.get_linewidth()
        except Exception:
            return None
        return None

    # Current tick visibility (best-effort from axes)
    tick_vis = {
        'bx': True,
        'tx': False,
        'ly': True,
        'ry': True,
        'mbx': False,
        'mtx': False,
        'mly': False,
        'mry': False,
    }
    try:
        # Infer from current axes state
        import matplotlib as _mpl
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
            'title': bool(ax.get_ylabel())  # left y title
        },
        'right': {
            'spine': _get_spine_visible(ax2, 'right'),
            'ticks': bool(tick_vis.get('ry', True)),
            'minor': bool(tick_vis.get('mry', False)),
            'labels': bool(tick_vis.get('ry', True)),  # right y labels (efficiency)
            'title': bool(ax2.get_ylabel())  # right y title
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

    cfg = {
        'kind': 'cpc_style',
        'version': 2,
        'figure': {
            'canvas_size': [fig_w, fig_h],
            'frame_size': [frame_w_in, frame_h_in]
        },
        'font': {'family': fam0, 'size': fsize},
        'legend': {
            'visible': legend_visible,
            'position_inches': legend_xy_in  # [x, y] offset from canvas center in inches
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
        'wasd_state': wasd_state,
        'spines': {
            'bottom': {'linewidth': ax.spines.get('bottom').get_linewidth() if ax.spines.get('bottom') else None,
                       'visible': ax.spines.get('bottom').get_visible() if ax.spines.get('bottom') else None},
            'top':    {'linewidth': ax.spines.get('top').get_linewidth() if ax.spines.get('top') else None,
                       'visible': ax.spines.get('top').get_visible() if ax.spines.get('top') else None},
            'left':   {'linewidth': ax.spines.get('left').get_linewidth() if ax.spines.get('left') else None,
                       'visible': ax.spines.get('left').get_visible() if ax.spines.get('left') else None},
            'right':  {'linewidth': ax2.spines.get('right').get_linewidth() if ax2.spines.get('right') else None,
                       'visible': ax2.spines.get('right').get_visible() if ax2.spines.get('right') else None},
        },
        'labelpads': {
            'x': getattr(ax.xaxis, 'labelpad', None),
            'ly': getattr(ax.yaxis, 'labelpad', None),  # left y-axis (capacity)
            'ry': getattr(ax2.yaxis, 'labelpad', None),  # right y-axis (efficiency)
        },
        'series': {
            'charge': {
                'color': _color_of(sc_charge),
                'markersize': float(getattr(sc_charge, 'get_sizes', lambda: [32])()[0]) if hasattr(sc_charge, 'get_sizes') else 32.0,
                'alpha': float(sc_charge.get_alpha()) if sc_charge.get_alpha() is not None else 1.0,
            },
            'discharge': {
                'color': _color_of(sc_discharge),
                'markersize': float(getattr(sc_discharge, 'get_sizes', lambda: [32])()[0]) if hasattr(sc_discharge, 'get_sizes') else 32.0,
                'alpha': float(sc_discharge.get_alpha()) if sc_discharge.get_alpha() is not None else 1.0,
            },
            'efficiency': {
                'color': (sc_eff.get_facecolors()[0].tolist() if hasattr(sc_eff, 'get_facecolors') and len(sc_eff.get_facecolors()) else '#2ca02c'),
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
            file_info = {
                'filename': f.get('filename', 'unknown'),
                'visible': f.get('visible', True),
                'charge_color': _color_of(f.get('sc_charge')),
                'discharge_color': _color_of(f.get('sc_discharge')),
                'efficiency_color': _color_of(f.get('sc_eff')),
            }
            multi_files.append(file_info)
        cfg['multi_files'] = multi_files
    
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
        canvas_size = fig_cfg.get('canvas_size')
        if canvas_size and isinstance(canvas_size, (list, tuple)) and len(canvas_size) == 2:
            fig.set_size_inches(canvas_size[0], canvas_size[1], forward=True)
        
        # Frame size: calculate position from inches
        frame_size = fig_cfg.get('frame_size')
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
                if ch.get('markersize') is not None and hasattr(sc_charge, 'set_sizes'):
                    sc_charge.set_sizes([float(ch['markersize'])])
                if ch.get('alpha') is not None:
                    sc_charge.set_alpha(float(ch['alpha']))
            if dh:
                if dh.get('color') is not None:
                    sc_discharge.set_color(dh['color'])
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
            
            # Store position for later use
            if leg_xy_in is not None:
                fig._cpc_legend_xy_in = leg_xy_in
            
            leg = ax.get_legend()
            if leg is not None:
                leg.set_visible(leg_visible)
                
                # Reposition legend if position is stored
                if leg_visible and leg_xy_in is not None:
                    try:
                        fig_w, fig_h = fig.get_size_inches()
                        cx, cy = fig_w / 2.0, fig_h / 2.0
                        x_in, y_in = leg_xy_in
                        fx = (cx + x_in) / fig_w
                        fy = (cy + y_in) / fig_h
                        
                        h1, l1 = ax.get_legend_handles_labels()
                        h2, l2 = ax2.get_legend_handles_labels()
                        ax.legend(h1 + h2, l1 + l2, loc='center', bbox_to_anchor=(fx, fy), 
                                 bbox_transform=fig.transFigure, borderaxespad=1.0)
                    except Exception:
                        pass
    except Exception:
        pass
    # Apply tick visibility/widths and spines
    try:
        tk = cfg.get('ticks', {})
        # Try wasd_state first (version 2), fall back to visibility dict (version 1)
        wasd = cfg.get('wasd_state', {})
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
            # Minor ticks
            from matplotlib.ticker import AutoMinorLocator, NullFormatter
            if mbx or mtx:
                ax.xaxis.set_minor_locator(AutoMinorLocator()); ax.xaxis.set_minor_formatter(NullFormatter())
                ax.tick_params(axis='x', which='minor', bottom=mbx, top=mtx, labelbottom=False, labeltop=False)
            else:
                ax.tick_params(axis='x', which='minor', bottom=False, top=False, labelbottom=False, labeltop=False)
            if mly:
                ax.yaxis.set_minor_locator(AutoMinorLocator()); ax.yaxis.set_minor_formatter(NullFormatter())
                ax.tick_params(axis='y', which='minor', left=True, labelleft=False)
            else:
                ax.tick_params(axis='y', which='minor', left=False, labelleft=False)
            if mry:
                ax2.yaxis.set_minor_locator(AutoMinorLocator()); ax2.yaxis.set_minor_formatter(NullFormatter())
                ax2.tick_params(axis='y', which='minor', right=True, labelright=False)
            else:
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
                if spn is None: continue
                if spec.get('linewidth') is not None:
                    try: spn.set_linewidth(float(spec['linewidth']))
                    except Exception: pass
                if spec.get('visible') is not None:
                    try: spn.set_visible(bool(spec['visible']))
                    except Exception: pass
            if name == 'right' and ax2.spines.get('right') is not None:
                spn = ax2.spines.get('right')
                if spec.get('linewidth') is not None:
                    try: spn.set_linewidth(float(spec['linewidth']))
                    except Exception: pass
                if spec.get('visible') is not None:
                    try: spn.set_visible(bool(spec['visible']))
                    except Exception: pass
    except Exception:
        pass
    # Restore labelpads
    try:
        pads = cfg.get('labelpads', {})
        if pads:
            if pads.get('x') is not None:
                ax.xaxis.labelpad = pads['x']
            if pads.get('ly') is not None:
                ax.yaxis.labelpad = pads['ly']
            if pads.get('ry') is not None:
                ax2.yaxis.labelpad = pads['ry']
    except Exception:
        pass
    try:
        fig.canvas.draw_idle()
    except Exception:
        pass


def cpc_interactive_menu(fig, ax, ax2, sc_charge, sc_discharge, sc_eff, file_data=None):
    """CPC interactive menu with optional multi-file support.
    
    Args:
        fig, ax, ax2: Matplotlib figure and axes
        sc_charge, sc_discharge, sc_eff: Primary file scatter artists (for backward compatibility)
        file_data: Optional list of dicts with file info and scatter artists for multi-file mode
    """
    # Multi-file mode setup
    is_multi_file = file_data is not None and len(file_data) > 1
    if file_data is None:
        # Backward compatibility: create file_data from single file
        file_data = [{
            'filename': 'Data',
            'sc_charge': sc_charge,
            'sc_discharge': sc_discharge,
            'sc_eff': sc_eff,
            'visible': True
        }]
    
    current_file_idx = 0  # Index of currently selected file for editing
    
    # Tick state for CPC (primary ax + twin right ax2)
    tick_state = {
        'bx': True,  # bottom x
        'tx': False, # top x
        'ly': True,  # left y (primary)
        'ry': True,  # right y (twin)
        'mbx': False,
        'mtx': False,
        'mly': False,
        'mry': False,
    }

    # --- Undo stack using style snapshots ---
    state_history = []  # list of cfg dicts

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

    def _apply_legend_position():
        """Reapply legend position using stored inches offset relative to canvas center."""
        try:
            xy_in = getattr(fig, '_cpc_legend_xy_in', None)
            leg = ax.get_legend()
            if xy_in is None or leg is None:
                return
            # Compute figure-fraction anchor from inches
            fw, fh = fig.get_size_inches()
            if fw <= 0 or fh <= 0:
                return
            fx = 0.5 + float(xy_in[0]) / float(fw)
            fy = 0.5 + float(xy_in[1]) / float(fh)
            # Use current handles/labels
            h1, l1 = ax.get_legend_handles_labels()
            h2, l2 = ax2.get_legend_handles_labels()
            if h1 or h2:
                ax.legend(h1 + h2, l1 + l2, loc='center', bbox_to_anchor=(fx, fy), bbox_transform=fig.transFigure, borderaxespad=1.0)
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
    if is_multi_file:
        print(f"\n[Multi-file mode: {len(file_data)} files loaded]")
        _print_file_list(file_data, current_file_idx)
    
    while True:
        # Update current file's scatter artists for commands that need them
        sc_charge, sc_discharge, sc_eff = _get_current_file_artists(file_data, current_file_idx)
        
        key = input("Press a key: ").strip().lower()
        if not key:
            continue
        
        # File visibility toggle command (v)
        if key == 'v':
            try:
                if is_multi_file:
                    _print_file_list(file_data, current_file_idx)
                    choice = input(f"Toggle visibility for file (1-{len(file_data)}), 'a' for all, or q=cancel: ").strip()
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
                    vis = sc_eff.get_visible()
                    sc_eff.set_visible(not vis)
                    try:
                        ax2.yaxis.label.set_visible(not vis)
                    except Exception:
                        pass
                
                _rebuild_legend(ax, ax2, file_data)
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
                confirm = input(_colorize_prompt("Quit CPC interactive? Remember to save! Quit now? (y/n): ")).strip().lower()
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
            # Colors submenu: ly (left Y series) and ry (right Y efficiency)
            try:
                while True:
                    print("\nColors: ly=capacity curves, ry=efficiency triangles, q=back")
                    sub = input("Colors> ").strip().lower()
                    if not sub:
                        continue
                    if sub == 'q':
                        break
                    if sub == 'ly':
                        if is_multi_file:
                            # Show file list for selection
                            print("\nSelect curve to color:")
                            for i, f in enumerate(file_data, 1):
                                vis_mark = "●" if f.get('visible', True) else "○"
                                print(f"  {i}. {vis_mark} {f['filename']}")
                            choice = input("Enter curve number (1-{}) or 'a' for all, q=cancel: ".format(len(file_data))).strip()
                            if not choice or choice.lower() == 'q':
                                continue
                            
                            push_state("colors-ly")
                            if choice.lower() == 'a':
                                # Apply to all files
                                print("\nCharge color palettes (discharge will be auto-generated):")
                                print("  1. Reds: #d62728, #c62828, #b71c1c, #8b0000, #a30000")
                                print("  2. Oranges: #ff7f0e, #ff6f00, #ff5722, #f4511e, #e64a19")
                                print("  3. Pinks/Magentas: #e377c2, #d81b60, #c2185b, #ad1457, #880e4f")
                                print("  4. Purples: #9c27b0, #8e24aa, #7b1fa2, #6a1b9a, #4a148c")
                                print("  5. Deep oranges/reds: #d84315, #bf360c, #c2185b, #d32f2f, #c62828")
                                spec = input("Enter color (name/hex), palette number (1-5), or 'r' for random (q=cancel): ").strip()
                                if not spec or spec.lower() == 'q':
                                    continue
                                for i, f in enumerate(file_data):
                                    if spec.lower() == 'r':
                                        # Use Viridis colormap
                                        import matplotlib.cm as cm
                                        import matplotlib.colors as mcolors
                                        viridis = cm.get_cmap('viridis', 10)
                                        charge_col = mcolors.rgb2hex(viridis(_random.random())[:3])

                                    elif spec in ['1', '2', '3', '4', '5']:
                                        # Use selected palette
                                        charge_palettes = [
                                            ['#d62728', '#c62828', '#b71c1c', '#8b0000', '#a30000'],
                                            ['#ff7f0e', '#ff6f00', '#ff5722', '#f4511e', '#e64a19'],
                                            ['#e377c2', '#d81b60', '#c2185b', '#ad1457', '#880e4f'],
                                            ['#9c27b0', '#8e24aa', '#7b1fa2', '#6a1b9a', '#4a148c'],
                                            ['#d84315', '#bf360c', '#c2185b', '#d32f2f', '#c62828']
                                        ]
                                        palette = charge_palettes[int(spec) - 1]
                                        charge_col = palette[i % len(palette)]
                                    else:
                                        charge_col = spec
                                    discharge_col = _generate_similar_color(charge_col)
                                    try:
                                        f['sc_charge'].set_color(charge_col)
                                        f['sc_discharge'].set_color(discharge_col)
                                        f['color'] = charge_col
                                    except Exception:
                                        pass
                            else:
                                # Apply to selected file
                                try:
                                    idx = int(choice) - 1
                                    if 0 <= idx < len(file_data):
                                        print("\nCharge color palettes (discharge will be auto-generated):")
                                        print("  1. Reds: #d62728, #c62828, #b71c1c, #8b0000, #a30000")
                                        print("  2. Oranges: #ff7f0e, #ff6f00, #ff5722, #f4511e, #e64a19")
                                        print("  3. Pinks/Magentas: #e377c2, #d81b60, #c2185b, #ad1457, #880e4f")
                                        print("  4. Purples: #9c27b0, #8e24aa, #7b1fa2, #6a1b9a, #4a148c")
                                        print("  5. Deep oranges/reds: #d84315, #bf360c, #c2185b, #d32f2f, #c62828")
                                        spec = input("Enter color (name/hex), palette number (1-5), or 'r' for random (q=cancel): ").strip()
                                        if not spec or spec.lower() == 'q':
                                            continue
                                        if spec.lower() == 'r':
                                            # Use Viridis colormap
                                            import matplotlib.cm as cm
                                            import matplotlib.colors as mcolors
                                            viridis = cm.get_cmap('viridis', 10)
                                            charge_col = mcolors.rgb2hex(viridis(_random.random())[:3])
                                        elif spec in ['1', '2', '3', '4', '5']:
                                            # Use selected palette
                                            charge_palettes = [
                                                ['#d62728', '#c62828', '#b71c1c', '#8b0000', '#a30000'],
                                                ['#ff7f0e', '#ff6f00', '#ff5722', '#f4511e', '#e64a19'],
                                                ['#e377c2', '#d81b60', '#c2185b', '#ad1457', '#880e4f'],
                                                ['#9c27b0', '#8e24aa', '#7b1fa2', '#6a1b9a', '#4a148c'],
                                                ['#d84315', '#bf360c', '#c2185b', '#d32f2f', '#c62828']
                                            ]
                                            palette = charge_palettes[int(spec) - 1]
                                            charge_col = palette[0]  # Use first color from palette for single file
                                        else:
                                            charge_col = spec
                                        discharge_col = _generate_similar_color(charge_col)
                                        try:
                                            file_data[idx]['sc_charge'].set_color(charge_col)
                                            file_data[idx]['sc_discharge'].set_color(discharge_col)
                                            file_data[idx]['color'] = charge_col
                                        except Exception:
                                            pass
                                    else:
                                        print("Invalid file number.")
                                except ValueError:
                                    print("Invalid input.")
                        else:
                            # Single file mode
                            push_state("colors-ly")
                            print("\nCharge color palettes (discharge will be auto-generated):")
                            print("  1. Reds: #d62728, #c62828, #b71c1c, #8b0000, #a30000")
                            print("  2. Oranges: #ff7f0e, #ff6f00, #ff5722, #f4511e, #e64a19")
                            print("  3. Pinks/Magentas: #e377c2, #d81b60, #c2185b, #ad1457, #880e4f")
                            print("  4. Purples: #9c27b0, #8e24aa, #7b1fa2, #6a1b9a, #4a148c")
                            print("  5. Deep oranges/reds: #d84315, #bf360c, #c2185b, #d32f2f, #c62828")
                            spec = input("Enter color (name/hex), palette number (1-5), or 'r' for random (q=cancel): ").strip()
                            if not spec or spec.lower() == 'q':
                                continue
                            if spec.strip().lower() == 'r':
                                # Use Viridis colormap
                                import matplotlib.cm as cm
                                import matplotlib.colors as mcolors
                                viridis = cm.get_cmap('viridis', 10)
                                charge_col = mcolors.rgb2hex(viridis(_random.random())[:3])
                            elif spec in ['1', '2', '3', '4', '5']:
                                # Use selected palette
                                charge_palettes = [
                                    ['#d62728', '#c62828', '#b71c1c', '#8b0000', '#a30000'],
                                    ['#ff7f0e', '#ff6f00', '#ff5722', '#f4511e', '#e64a19'],
                                    ['#e377c2', '#d81b60', '#c2185b', '#ad1457', '#880e4f'],
                                    ['#9c27b0', '#8e24aa', '#7b1fa2', '#6a1b9a', '#4a148c'],
                                    ['#d84315', '#bf360c', '#c2185b', '#d32f2f', '#c62828']
                                ]
                                palette = charge_palettes[int(spec) - 1]
                                charge_col = palette[0]  # Use first color from palette
                            else:
                                charge_col = spec
                            discharge_col = _generate_similar_color(charge_col)
                            try:
                                sc_charge.set_color(charge_col)
                                sc_discharge.set_color(discharge_col)
                            except Exception:
                                pass
                        try:
                            _rebuild_legend(ax, ax2, file_data)
                            fig.canvas.draw_idle()
                        except Exception:
                            pass
                    elif sub == 'ry':
                        push_state("colors-ry")
                        if is_multi_file:
                            # Show file list for efficiency triangle selection
                            print("\nSelect curve's efficiency to color:")
                            for i, f in enumerate(file_data, 1):
                                vis_mark = "●" if f.get('visible', True) else "○"
                                print(f"  {i}. {vis_mark} {f['filename']}")
                            choice = input("Enter curve number (1-{}) or 'a' for all, q=cancel: ".format(len(file_data))).strip()
                            if not choice or choice.lower() == 'q':
                                continue
                            
                            if choice.lower() == 'a':
                                print("\nEfficiency color palettes:")
                                print("  1. Blues: #1f77b4, #1976d2, #1565c0, #0d47a1, #01579b")
                                print("  2. Cyans/Teals: #17becf, #00acc1, #0097a7, #00838f, #006064")
                                print("  3. Purples/Indigos: #9467bd, #5e35b1, #512da8, #4527a0, #311b92")
                                print("  4. Deep blues: #2196f3, #1e88e5, #1976d2, #1565c0, #0d47a1")
                                print("  5. Dark cyans/purples: #0097a7, #00838f, #006064, #5e35b1, #4527a0")
                                val = input("Enter color (hex/name), palette number (1-5), or 'r' for random (q=cancel): ").strip()
                                if not val or val.lower() == 'q':
                                    continue
                                for i, f in enumerate(file_data):
                                    if val.lower() == 'r':
                                        # Use Plasma colormap
                                        import matplotlib.cm as cm
                                        import matplotlib.colors as mcolors
                                        plasma = cm.get_cmap('plasma', 10)
                                        col = mcolors.rgb2hex(plasma(_random.random())[:3])
                                    elif val in ['1', '2', '3', '4', '5']:
                                        # Use selected palette
                                        efficiency_palettes = [
                                            ['#1f77b4', '#1976d2', '#1565c0', '#0d47a1', '#01579b'],
                                            ['#17becf', '#00acc1', '#0097a7', '#00838f', '#006064'],
                                            ['#9467bd', '#5e35b1', '#512da8', '#4527a0', '#311b92'],
                                            ['#2196f3', '#1e88e5', '#1976d2', '#1565c0', '#0d47a1'],
                                            ['#0097a7', '#00838f', '#006064', '#5e35b1', '#4527a0']
                                        ]
                                        palette = efficiency_palettes[int(val) - 1]
                                        col = palette[i % len(palette)]
                                    else:
                                        col = val
                                    try:
                                        f['sc_eff'].set_color(col)
                                        f['eff_color'] = col  # Store efficiency color
                                    except Exception:
                                        pass
                            else:
                                try:
                                    idx = int(choice) - 1
                                    if 0 <= idx < len(file_data):
                                        print("\nEfficiency color palettes:")
                                        print("  1. Blues: #1f77b4, #1976d2, #1565c0, #0d47a1, #01579b")
                                        print("  2. Cyans/Teals: #17becf, #00acc1, #0097a7, #00838f, #006064")
                                        print("  3. Purples/Indigos: #9467bd, #5e35b1, #512da8, #4527a0, #311b92")
                                        print("  4. Deep blues: #2196f3, #1e88e5, #1976d2, #1565c0, #0d47a1")
                                        print("  5. Dark cyans/purples: #0097a7, #00838f, #006064, #5e35b1, #4527a0")
                                        val = input("Enter color (hex/name), palette number (1-5), or 'r' for random (q=cancel): ").strip()
                                        if not val or val.lower() == 'q':
                                            continue
                                        if val.lower() == 'r':
                                            # Use Plasma colormap
                                            import matplotlib.cm as cm
                                            import matplotlib.colors as mcolors
                                            plasma = cm.get_cmap('plasma', 10)
                                            col = mcolors.rgb2hex(plasma(_random.random())[:3])
                                        elif val in ['1', '2', '3', '4', '5']:
                                            # Use selected palette
                                            efficiency_palettes = [
                                                ['#1f77b4', '#1976d2', '#1565c0', '#0d47a1', '#01579b'],
                                                ['#17becf', '#00acc1', '#0097a7', '#00838f', '#006064'],
                                                ['#9467bd', '#5e35b1', '#512da8', '#4527a0', '#311b92'],
                                                ['#2196f3', '#1e88e5', '#1976d2', '#1565c0', '#0d47a1'],
                                                ['#0097a7', '#00838f', '#006064', '#5e35b1', '#4527a0']
                                            ]
                                            palette = efficiency_palettes[int(val) - 1]
                                            col = palette[0]  # Use first color from palette for single file
                                        else:
                                            col = val
                                        try:
                                            file_data[idx]['sc_eff'].set_color(col)
                                            file_data[idx]['eff_color'] = col  # Store efficiency color
                                        except Exception:
                                            pass
                                    else:
                                        print("Invalid file number.")
                                except ValueError:
                                    print("Invalid input.")
                        else:
                            # Single file mode
                            print("\nEfficiency color palettes:")
                            print("  1. Blues: #1f77b4, #1976d2, #1565c0, #0d47a1, #01579b")
                            print("  2. Cyans/Teals: #17becf, #00acc1, #0097a7, #00838f, #006064")
                            print("  3. Purples/Indigos: #9467bd, #5e35b1, #512da8, #4527a0, #311b92")
                            print("  4. Deep blues: #2196f3, #1e88e5, #1976d2, #1565c0, #0d47a1")
                            print("  5. Dark cyans/purples: #0097a7, #00838f, #006064, #5e35b1, #4527a0")
                            val = input("Enter color (hex/name), palette number (1-5), or 'r' for random (q=cancel): ").strip()
                            if not val or val.lower() == 'q':
                                continue
                            if val.lower() == 'r':
                                # Use Plasma colormap
                                import matplotlib.cm as cm
                                import matplotlib.colors as mcolors
                                plasma = cm.get_cmap('plasma', 10)
                                col = mcolors.rgb2hex(plasma(_random.random())[:3])
                            elif val in ['1', '2', '3', '4', '5']:
                                # Use selected palette
                                efficiency_palettes = [
                                    ['#1f77b4', '#1976d2', '#1565c0', '#0d47a1', '#01579b'],
                                    ['#17becf', '#00acc1', '#0097a7', '#00838f', '#006064'],
                                    ['#9467bd', '#5e35b1', '#512da8', '#4527a0', '#311b92'],
                                    ['#2196f3', '#1e88e5', '#1976d2', '#1565c0', '#0d47a1'],
                                    ['#0097a7', '#00838f', '#006064', '#5e35b1', '#4527a0']
                                ]
                                palette = efficiency_palettes[int(val) - 1]
                                col = palette[0]  # Use first color from palette
                            else:
                                col = val
                            try:
                                sc_eff.set_color(col)
                            except Exception:
                                pass
                        try:
                            _rebuild_legend(ax, ax2, file_data)
                            fig.canvas.draw_idle()
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
                print("Set spine colors (with matching tick and label colors):")
                print(_colorize_inline_commands("  w : top spine    | a : left spine"))
                print(_colorize_inline_commands("  s : bottom spine | d : right spine"))
                print(_colorize_inline_commands("Example: w:red a:#4561F7 s:blue d:green"))
                line = input("Enter mappings (e.g., w:red a:#4561F7) or q: ").strip()
                if line and line.lower() != 'q':
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
                        # Set for both axes
                        for curr_ax in [ax, ax2]:
                            if curr_ax is None:
                                continue
                            if spine_name not in curr_ax.spines:
                                continue
                            try:
                                # Set spine color
                                curr_ax.spines[spine_name].set_edgecolor(color)
                                # Set tick colors and axis label color for this axis
                                if spine_name in ('top', 'bottom'):
                                    curr_ax.tick_params(axis='x', which='both', colors=color)
                                    curr_ax.xaxis.label.set_color(color)
                                else:  # left or right
                                    curr_ax.tick_params(axis='y', which='both', colors=color)
                                    curr_ax.yaxis.label.set_color(color)
                            except Exception as e:
                                print(f"Error setting {spine_name} color: {e}")
                        print(f"Set {spine_name} spine to {color}")
                    fig.canvas.draw()
                else:
                    print("Canceled.")
            except Exception as e:
                print(f"Error in spine color menu: {e}")
            _print_menu()
            if is_multi_file:
                _print_file_list(file_data, current_file_idx)
            continue
        elif key == 'e':
            try:
                # List existing figure files from Figures/ subdirectory
                from .utils import list_files_in_subdirectory, get_organized_path
                fig_extensions = ('.svg', '.png', '.jpg', '.jpeg', '.pdf', '.eps', '.tif', '.tiff')
                file_list = list_files_in_subdirectory(fig_extensions, 'figure')
                files = [f[0] for f in file_list]
                if files:
                    print("Existing figure files in Figures/:")
                    for i, f in enumerate(files, 1):
                        print(f"  {i}: {f}")
                
                fname = input("Export filename (default .svg if no extension) or number to overwrite (q=cancel): ").strip()
                if not fname or fname.lower() == 'q':
                    _print_menu(); continue
                
                # Check if user selected a number
                if fname.isdigit() and files:
                    idx = int(fname)
                    if 1 <= idx <= len(files):
                        name = files[idx-1]
                        yn = input(f"Overwrite '{name}'? (y/n): ").strip().lower()
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
                        target = get_organized_path(fname, 'figure')
                    if os.path.exists(target):
                        yn = input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
                        if yn != 'y':
                            _print_menu(); continue
                if target:
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
                    fig.savefig(target, bbox_inches='tight')
                    print(f"Exported figure to {target}")
                    
                    # Restore original labels
                    if is_multi_file and original_labels:
                        try:
                            for artist, label in original_labels.items():
                                artist.set_label(label)
                            _rebuild_legend(ax, ax2, file_data)
                        except Exception:
                            pass
            except Exception as e:
                print(f"Export failed: {e}")
            _print_menu(); continue
        elif key == 's':
            # Save CPC session (.pkl) with all data and styles
            try:
                from .session import dump_cpc_session
                folder = os.getcwd()
                try:
                    files = sorted([f for f in os.listdir(folder) if f.lower().endswith('.pkl')])
                except Exception:
                    files = []
                if files:
                    print("Existing .pkl files:")
                    for i, f in enumerate(files, 1):
                        print(f"  {i}: {f}")
                choice = input("Enter new filename or number to overwrite (q=cancel): ").strip()
                if not choice or choice.lower() == 'q':
                    _print_menu(); continue
                if choice.isdigit() and files:
                    idx = int(choice)
                    if 1 <= idx <= len(files):
                        name = files[idx-1]
                        yn = input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                        if yn != 'y':
                            _print_menu(); continue
                        target = os.path.join(folder, name)
                    else:
                        print("Invalid number.")
                        _print_menu(); continue
                else:
                    name = choice
                    root, ext = os.path.splitext(name)
                    if ext == '':
                        name = name + '.pkl'
                    target = name if os.path.isabs(name) else os.path.join(folder, name)
                    if os.path.exists(target):
                        yn = input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
                        if yn != 'y':
                            _print_menu(); continue
                dump_cpc_session(target, fig=fig, ax=ax, ax2=ax2, sc_charge=sc_charge, sc_discharge=sc_discharge, sc_eff=sc_eff, file_data=file_data, skip_confirm=True)
            except Exception as e:
                print(f"Save failed: {e}")
            _print_menu(); continue
        elif key == 'p':
            try:
                print("Print & Export: ps=style only (.bps), psg=style+geometry (.bpsg), q=cancel")
                choice = input("p> ").strip().lower()
                if not choice or choice == 'q':
                    _print_menu()
                    continue
                
                snap = _style_snapshot(fig, ax, ax2, sc_charge, sc_discharge, sc_eff, file_data)
                
                if choice == 'ps':
                    # Style only
                    snap['kind'] = 'cpc_style'
                    default_ext = '.bps'
                elif choice == 'psg':
                    # Style + Geometry
                    snap['kind'] = 'cpc_style_geom'
                    snap['geometry'] = _get_geometry_snapshot(ax, ax2)
                    default_ext = '.bpsg'
                else:
                    print(f"Unknown option: {choice}")
                    _print_menu()
                    continue
                
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
                        print(f"  {name:<6} lw={lw} visible={vis}")
                
                ticks = snap.get('ticks', {})
                print(f"Tick widths: x_major={ticks.get('x_major_width')}, x_minor={ticks.get('x_minor_width')}")
                print(f"             ly_major={ticks.get('ly_major_width')}, ly_minor={ticks.get('ly_minor_width')}")
                print(f"             ry_major={ticks.get('ry_major_width')}, ry_minor={ticks.get('ry_minor_width')}")
                tick_direction = ticks.get('direction', 'out')
                print(f"Tick direction: {tick_direction}")
                
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
                
                # Show geometry if included
                if choice == 'psg':
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
                
                print("--- End Style ---\n")
                # List existing files and allow numeric overwrite on export
                from .utils import list_files_in_subdirectory, get_organized_path
                style_extensions = ('.bps', '.bpsg', '.bpcfg')
                file_list = list_files_in_subdirectory(style_extensions, 'style')
                files = [f[0] for f in file_list]
                if files:
                    print(f"Existing style files in Styles/:")
                    for i, f in enumerate(files, 1):
                        print(f"  {i}: {f}")
                sub = input(_colorize_prompt("Style submenu: (e=export, q=return): ")).strip().lower()
                if sub == 'e':
                    choice = input("Enter new filename or number to overwrite (q=cancel): ").strip()
                    if not choice or choice.lower() == 'q':
                        _print_menu(); continue
                    target = None
                    if choice.isdigit() and files:
                        idx = int(choice)
                        if 1 <= idx <= len(files):
                            name = files[idx-1]
                            yn = input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                            if yn == 'y':
                                target = file_list[idx-1][1]  # Full path from list
                        else:
                            print("Invalid number."); _print_menu(); continue
                    else:
                        name = choice
                        # Add default extension if no extension provided
                        if not any(name.lower().endswith(ext) for ext in ['.bps', '.bpsg', '.bpcfg']):
                            name = name + default_ext
                        # Use organized path unless it's an absolute path
                        if os.path.isabs(name):
                            target = name
                        else:
                            target = get_organized_path(name, 'style')
                        if os.path.exists(target):
                            yn = input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
                            if yn != 'y':
                                target = None
                    if target:
                        with open(target, 'w', encoding='utf-8') as f:
                            json.dump(snap, f, indent=2)
                        print(f"Exported CPC style to {target}")
            except Exception as e:
                print(f"Error printing/exporting style: {e}")
            _print_menu(); continue
        elif key == 'i':
            try:
                from .utils import list_files_in_subdirectory, get_organized_path
                style_extensions = ('.bps', '.bpsg', '.bpcfg')
                file_list = list_files_in_subdirectory(style_extensions, 'style')
                files = [f[0] for f in file_list]
                if files:
                    print("Available style files in Styles/:")
                    for i, f in enumerate(files, 1):
                        print(f"  {i}: {f}")
                inp = input("Enter number or filename (.bps/.bpsg; q=cancel): ").strip()
                if not inp or inp.lower() == 'q':
                    _print_menu(); continue
                push_state("import-style")
                if inp.isdigit() and files:
                    idx = int(inp)
                    if 1 <= idx <= len(files):
                        path = file_list[idx-1][1]  # Full path from list
                    else:
                        print("Invalid number."); _print_menu(); continue
                else:
                    # User provided a filename
                    if os.path.isabs(inp):
                        path = inp
                    else:
                        # Try to find in Styles/ subdirectory with various extensions
                        found = False
                        for ext in ['.bps', '.bpsg', '.bpcfg']:
                            name = inp if inp.lower().endswith(ext) else inp + ext
                            alt_path = get_organized_path(name, 'style')
                            if os.path.isfile(alt_path):
                                path = alt_path
                                found = True
                                break
                        if not found:
                            print("File not found in Styles/."); _print_menu(); continue
                
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
                vis = bool(sc_eff.get_visible()) if hasattr(sc_eff, 'get_visible') else True
                new_vis = not vis
                
                # 1. Hide/show efficiency points
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
                
                # 4. Rebuild legend to remove/add efficiency entry
                try:
                    h1, l1 = ax.get_legend_handles_labels()
                except Exception:
                    h1, l1 = [], []
                try:
                    h2, l2 = ax2.get_legend_handles_labels()
                except Exception:
                    h2, l2 = [], []
                
                # Filter out efficiency entry if hidden
                eff_label = None
                try:
                    eff_label = sc_eff.get_label()
                except Exception:
                    pass
                
                pairs1 = list(zip(h1, l1))
                pairs2 = list(zip(h2, l2))
                
                def _keep(pair):
                    h, l = pair
                    # Drop invisible handles
                    try:
                        if hasattr(h, 'get_visible') and not h.get_visible():
                            return False
                    except Exception:
                        pass
                    # Drop the efficiency label when hidden
                    if eff_label and (l == eff_label) and not new_vis:
                        return False
                    return True
                
                vis_pairs1 = [p for p in pairs1 if _keep(p)]
                vis_pairs2 = [p for p in pairs2 if _keep(p)]
                H = [h for h, _ in vis_pairs1 + vis_pairs2]
                L = [l for _, l in vis_pairs1 + vis_pairs2]
                
                if H:
                    try:
                        # Honor stored inch-based anchor if present; else fallback to 'best'
                        xy_in = getattr(fig, '_cpc_legend_xy_in', None)
                        if xy_in is not None:
                            try:
                                fw, fh = fig.get_size_inches()
                                fx = 0.5 + float(xy_in[0]) / float(fw)
                                fy = 0.5 + float(xy_in[1]) / float(fh)
                                ax.legend(H, L, loc='center', bbox_to_anchor=(fx, fy), bbox_transform=fig.transFigure, borderaxespad=1.0)
                            except Exception:
                                ax.legend(H, L, loc='best', borderaxespad=1.0)
                        else:
                            ax.legend(H, L, loc='best', borderaxespad=1.0)
                    except Exception:
                        pass
                else:
                    # No visible series: hide legend if present
                    try:
                        leg = ax.get_legend()
                        if leg is not None:
                            leg.set_visible(False)
                    except Exception:
                        pass
                
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
                                fig._cpc_legend_xy_in = ((fx - 0.5) * fw, (fy - 0.5) * fh)
                            except Exception:
                                pass
                except Exception:
                    pass
                # Show current status and position
                leg = ax.get_legend()
                vis = bool(leg.get_visible()) if leg is not None else False
                fw, fh = fig.get_size_inches()
                xy_in = getattr(fig, '_cpc_legend_xy_in', (0.0, 0.0))
                print(f"Legend is {'ON' if vis else 'off'}; position (inches from center): x={xy_in[0]:.2f}, y={xy_in[1]:.2f}")
                while True:
                    sub = input("Legend: t=toggle, m=set position (x y inches), q=back: ").strip().lower()
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
                                h1, l1 = ax.get_legend_handles_labels()
                                h2, l2 = ax2.get_legend_handles_labels()
                                if h1 or h2:
                                    if hasattr(fig, '_cpc_legend_xy_in') and getattr(fig, '_cpc_legend_xy_in') is not None:
                                        _apply_legend_position()
                                    else:
                                        ax.legend(h1 + h2, l1 + l2, loc='best', borderaxespad=1.0)
                            fig.canvas.draw_idle()
                        except Exception:
                            pass
                    elif sub == 'm':
                        push_state("legend-move")
                        xy_in = getattr(fig, '_cpc_legend_xy_in', (0.0, 0.0))
                        print(f"Current position: x={xy_in[0]:.2f}, y={xy_in[1]:.2f}")
                        vals = input("Enter legend position x y (inches from center; e.g., 0.0 0.0): ").strip()
                        parts = vals.replace(',', ' ').split()
                        if len(parts) != 2:
                            print("Need two numbers."); continue
                        try:
                            x_in = float(parts[0]); y_in = float(parts[1])
                        except Exception:
                            print("Invalid numbers."); continue
                        # Store and apply
                        try:
                            fig._cpc_legend_xy_in = (x_in, y_in)
                            _apply_legend_position()
                            fig.canvas.draw_idle()
                        except Exception:
                            pass
                    else:
                        print("Unknown option.")
            except Exception:
                pass
            _print_menu(); continue
        elif key == 'f':
            sub = input("Font: f=family, s=size, q=back: ").strip().lower()
            if sub == 'q' or not sub:
                _print_menu(); continue
            if sub == 'f':
                fam = input("Enter font family (e.g., Arial, DejaVu Sans): ").strip()
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
                val = input("Enter font size (number): ").strip()
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
            # Line widths: frame and ticks
            try:
                fw_in = input("Enter frame/tick width (e.g., 1.5) or 'm M' (major minor) or q: ").strip()
                if not fw_in or fw_in.lower() == 'q':
                    print("Canceled.")
                    _print_menu(); continue
                parts = fw_in.split()
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
            except Exception as e:
                print(f"Error setting line widths: {e}")
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
                spec = input("Set marker size: 'c <ms>', 'd <ms>', 'e <ms>' (q=cancel): ").strip().lower()
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
                            ax.xaxis.set_minor_locator(AutoMinorLocator()); ax.xaxis.set_minor_formatter(NullFormatter())
                        ax.tick_params(axis='x', which='minor', top=bool(wasd['top']['minor']), bottom=bool(wasd['bottom']['minor']),
                                       labeltop=False, labelbottom=False)
                    except Exception:
                        pass
                    try:
                        if wasd['left']['minor']:
                            ax.yaxis.set_minor_locator(AutoMinorLocator()); ax.yaxis.set_minor_formatter(NullFormatter())
                        ax.tick_params(axis='y', which='minor', left=bool(wasd['left']['minor']), labelleft=False)
                    except Exception:
                        pass
                    try:
                        if wasd['right']['minor']:
                            ax2.yaxis.set_minor_locator(AutoMinorLocator()); ax2.yaxis.set_minor_formatter(NullFormatter())
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
                    print("State (top/bottom/left/right):")
                    print(f"  top    w1:{b(wasd['top']['spine'])} w2:{b(wasd['top']['ticks'])} w3:{b(wasd['top']['minor'])} w4:{b(wasd['top']['labels'])} w5:{b(wasd['top']['title'])}")
                    print(f"  bottom s1:{b(wasd['bottom']['spine'])} s2:{b(wasd['bottom']['ticks'])} s3:{b(wasd['bottom']['minor'])} s4:{b(wasd['bottom']['labels'])} s5:{b(wasd['bottom']['title'])}")
                    print(f"  left   a1:{b(wasd['left']['spine'])} a2:{b(wasd['left']['ticks'])} a3:{b(wasd['left']['minor'])} a4:{b(wasd['left']['labels'])} a5:{b(wasd['left']['title'])}")
                    print(f"  right  d1:{b(wasd['right']['spine'])} d2:{b(wasd['right']['ticks'])} d3:{b(wasd['right']['minor'])} d4:{b(wasd['right']['labels'])} d5:{b(wasd['right']['title'])}")

                print(_colorize_inline_commands("WASD toggles: direction (w/a/s/d) x action (1..5)"))
                print(_colorize_inline_commands("  1=spine   2=ticks   3=minor ticks   4=tick labels   5=axis title"))
                print(_colorize_inline_commands("Examples: 'w2 w5' to toggle top ticks and top title; 'd2 d5' for right."))
                print(_colorize_inline_commands("Type 'i' to invert tick direction, 'l' to change tick length, 'list' to show current state, 'q' to go back."))
                while True:
                    cmd = input("t> ").strip().lower()
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
                            new_length_str = input("Enter new major tick length (e.g., 6.0): ").strip()
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
                sub = input("Geom> ").strip().lower()
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
                        resize_canvas(fig)
                    except Exception as e:
                        print(f"Resize failed: {e}")
            _print_menu(); continue
        elif key == 'r':
            # Rename axis titles
            print("Tip: Use LaTeX/mathtext for special characters:")
            print("  Subscript: H$_2$O → H₂O  |  Superscript: m$^2$ → m²")
            print("  Greek: $\\alpha$, $\\beta$  |  Angstrom: $\\AA$ → Å")
            while True:
                print("Rename titles: x=x-axis, ly=left y-axis, ry=right y-axis, q=back")
                sub = input("Rename> ").strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub == 'x':
                    current = ax.get_xlabel()
                    print(f"Current x-axis title: '{current}'")
                    new_title = input("Enter new x-axis title (q=cancel): ")
                    if new_title and new_title.lower() != 'q':
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
                    new_title = input("Enter new left y-axis title (q=cancel): ")
                    if new_title and new_title.lower() != 'q':
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
                    new_title = input("Enter new right y-axis title (q=cancel): ")
                    if new_title and new_title.lower() != 'q':
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
                rng = input("Enter x-range: min max (q=back): ").strip()
                if not rng or rng.lower() == 'q':
                    break
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
                ycmd = input("Y> ").strip().lower()
                if not ycmd:
                    continue
                if ycmd == 'q':
                    break
                if ycmd == 'ly':
                    rng = input("Enter left y-range: min max (q=cancel): ").strip()
                    if not rng or rng.lower() == 'q':
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
                    try:
                        eff_on = bool(sc_eff.get_visible())
                    except Exception:
                        eff_on = True
                    if not eff_on:
                        print("Right Y is not shown; enable efficiency with 'ry' first.")
                        continue
                    rng = input("Enter right y-range: min max (q=cancel): ").strip()
                    if not rng or rng.lower() == 'q':
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

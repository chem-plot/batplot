"""Style and geometry helpers for EC interactive mode."""

from __future__ import annotations

from typing import Any, Dict, Optional, cast
import json
import os

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
from matplotlib import colors as mcolors  # type: ignore[import-untyped]
from matplotlib.ticker import AutoMinorLocator, MultipleLocator  # type: ignore[import-untyped]

from ...color_utils import color_block
from ...plotting import apply_curve_color
from ...utils import _colorize_option_keys, _confirm_overwrite, get_organized_path, list_files_in_subdirectory
from ..common.terminal import safe_input as _safe_input
from .colors import _iter_cycle_lines
from .legend import _get_legend_title


def _get_geometry_snapshot(fig, ax) -> Dict:
    """Collects a snapshot of geometry settings (axes labels and limits)."""
    out = {
        'xlim': list(ax.get_xlim()),
        'ylim': list(ax.get_ylim()),
        'xlabel': ax.get_xlabel() or '',
        'ylabel': ax.get_ylabel() or '',
    }
    try:
        dm = getattr(fig, '_ec_display_mode', 'both')
        if dm in ('charge', 'discharge', 'both'):
            out['display_mode'] = dm
    except Exception:
        pass
    return out


def _get_style_snapshot(fig, ax, cycle_lines: Dict, tick_state: Dict, file_data: Optional[list] = None) -> Dict:
    """Collects a comprehensive snapshot of the current plot style (no curve data). If file_data is provided (multi-file), includes file_display_names."""
    # Figure and font properties
    fig_w, fig_h = fig.get_size_inches()
    ax_bbox = ax.get_position()
    frame_w_in = ax_bbox.width * fig_w
    frame_h_in = ax_bbox.height * fig_h
    
    font_fam = plt.rcParams.get('font.sans-serif', [''])
    font_fam0 = font_fam[0] if font_fam else ''
    font_size = plt.rcParams.get('font.size')

    # Spine properties (including color for k command)
    spines = {}
    for name in ('bottom', 'top', 'left', 'right'):
        sp = ax.spines.get(name)
        if sp:
            try:
                ec = sp.get_edgecolor()
                color = mcolors.to_hex(ec) if ec is not None else None
            except Exception:
                color = None
            spines[name] = {
                'linewidth': sp.get_linewidth(),
                'visible': sp.get_visible(),
                'color': color,
            }

    # Tick widths
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

    tick_widths = {
        'x_major': _tick_width(ax.xaxis, 'major'),
        'x_minor': _tick_width(ax.xaxis, 'minor'),
        'y_major': _tick_width(ax.yaxis, 'major'),
        'y_minor': _tick_width(ax.yaxis, 'minor'),
    }
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

    # Tick direction
    tick_direction = getattr(fig, '_tick_direction', 'out')

    # Curve linewidth: get from stored value or first visible curve
    curve_linewidth = getattr(fig, '_ec_curve_linewidth', None)
    if curve_linewidth is None:
        try:
            for cyc, parts in cycle_lines.items():
                for role in ("charge", "discharge"):
                    ln = parts.get(role)
                    if ln is not None:
                        try:
                            curve_linewidth = float(ln.get_linewidth() or 1.0)
                            break
                        except Exception:
                            pass
                if curve_linewidth is not None:
                    break
        except Exception:
            pass
    if curve_linewidth is None:
        curve_linewidth = 1.0  # default

    # Curve marker properties: get from first visible curve
    curve_marker_props = {}
    try:
        for cyc, role, ln in _iter_cycle_lines(cycle_lines):
            try:
                curve_marker_props = {
                    'linestyle': ln.get_linestyle(),
                    'marker': ln.get_marker(),
                    'markersize': ln.get_markersize(),
                    'markerfacecolor': ln.get_markerfacecolor(),
                    'markeredgecolor': ln.get_markeredgecolor()
                }
                break
            except Exception:
                pass
            if curve_marker_props:
                break
    except Exception:
        pass

    def _line_color_hex(ln):
        try:
            return mcolors.to_hex(ln.get_color())
        except Exception:
            col = ln.get_color()
            if isinstance(col, str):
                return col
            try:
                return mcolors.to_hex(mcolors.to_rgba(col))
            except Exception:
                return None

    def _line_style_snapshot(ln):
        style = {}
        color_hex = _line_color_hex(ln)
        if color_hex:
            style['color'] = color_hex
        try:
            style['linewidth'] = float(ln.get_linewidth())
        except Exception:
            pass
        try:
            style['linestyle'] = ln.get_linestyle()
        except Exception:
            pass
        try:
            style['marker'] = ln.get_marker()
            style['markersize'] = float(ln.get_markersize())
            style['markerfacecolor'] = ln.get_markerfacecolor()
            style['markeredgecolor'] = ln.get_markeredgecolor()
        except Exception:
            pass
        try:
            style['alpha'] = ln.get_alpha()
        except Exception:
            pass
        style['visible'] = bool(ln.get_visible())
        return style

    cycle_styles = {}
    for cyc, parts in cycle_lines.items():
        entry = {}
        if isinstance(parts, dict):
            for role in ("charge", "discharge"):
                ln = parts.get(role)
                if ln is None:
                    continue
                style = _line_style_snapshot(ln)
                if style:
                    entry[role] = style
        else:
            ln = parts
            if ln is not None:
                style = _line_style_snapshot(ln)
                if style:
                    entry['line'] = style
        if entry:
            cycle_styles[str(cyc)] = entry

    # Multi-file: capture cycle_styles per file for p/i persistence
    cycle_styles_per_file = None
    if file_data is not None and len(file_data) > 1:
        cycle_styles_per_file = []
        for f in file_data:
            cl = f.get('cycle_lines')
            if not cl:
                cycle_styles_per_file.append({})
                continue
            per_file = {}
            for cyc, parts in cl.items():
                entry = {}
                if isinstance(parts, dict):
                    for role in ("charge", "discharge"):
                        ln = parts.get(role)
                        if ln is None:
                            continue
                        style = _line_style_snapshot(ln)
                        if style:
                            entry[role] = style
                else:
                    ln = parts
                    if ln is not None:
                        style = _line_style_snapshot(ln)
                        if style:
                            entry['line'] = style
                if entry:
                    per_file[str(cyc)] = entry
            cycle_styles_per_file.append(per_file)

    # Build WASD state (20 parameters) from current axes state
    def _get_spine_visible(which: str) -> bool:
        sp = ax.spines.get(which)
        try:
            return bool(sp.get_visible()) if sp is not None else False
        except Exception:
            return False
    
    wasd_state = {
        'top':    {
            'spine': _get_spine_visible('top'),
            'ticks': bool(tick_state.get('t_ticks', tick_state.get('tx', False))),
            'minor': bool(tick_state.get('mtx', False)),
            'labels': bool(tick_state.get('t_labels', tick_state.get('tx', False))),
            'title': bool(getattr(ax, '_top_xlabel_on', False))
        },
        'bottom': {
            'spine': _get_spine_visible('bottom'),
            'ticks': bool(tick_state.get('b_ticks', tick_state.get('bx', True))),
            'minor': bool(tick_state.get('mbx', False)),
            'labels': bool(tick_state.get('b_labels', tick_state.get('bx', True))),
            'title': bool(ax.get_xlabel())
        },
        'left':   {
            'spine': _get_spine_visible('left'),
            'ticks': bool(tick_state.get('l_ticks', tick_state.get('ly', True))),
            'minor': bool(tick_state.get('mly', False)),
            'labels': bool(tick_state.get('l_labels', tick_state.get('ly', True))),
            'title': bool(ax.get_ylabel())
        },
        'right':  {
            'spine': _get_spine_visible('right'),
            'ticks': bool(tick_state.get('r_ticks', tick_state.get('ry', False))),
            'minor': bool(tick_state.get('mry', False)),
            'labels': bool(tick_state.get('r_labels', tick_state.get('ry', False))),
            'title': bool(getattr(ax, '_right_ylabel_on', False))
        },
    }

    # Legend visibility/location
    legend_visible = False
    legend_xy_in = None
    try:
        leg = ax.get_legend()
        if leg is not None:
            legend_visible = bool(leg.get_visible())
            legend_xy_in = getattr(fig, '_ec_legend_xy_in', None)
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

    dual_top_axis = None
    try:
        secax = getattr(fig, '_xaxis_secondary', None)
        if secax is not None:
            top_spine = secax.spines.get('top')
            dual_top_axis = {
                'xlabel': secax.get_xlabel(),
                'xlabel_visible': bool(secax.xaxis.label.get_visible()),
                'label_color': mcolors.to_hex(secax.xaxis.label.get_color()),
                'spine_visible': bool(top_spine.get_visible()) if top_spine is not None else True,
                'spine_color': mcolors.to_hex(top_spine.get_edgecolor()) if top_spine is not None else None,
                'major_tick_color': (secax.xaxis.get_tick_params() or {}).get('color'),
            }
    except Exception:
        dual_top_axis = None

    result = {
        'kind': 'ec_style',
        'version': 2,
        'figure': {
            'canvas_size': [fig_w, fig_h],
            'frame_size': [frame_w_in, frame_h_in],
            'axes_fraction': [ax_bbox.x0, ax_bbox.y0, ax_bbox.width, ax_bbox.height],
        },
        'font': {
            'family': font_fam0,
            'size': font_size,
            'mathtext_fontset': plt.rcParams.get('mathtext.fontset'),
        },
        'axis_label_colors': {
            'x': mcolors.to_hex(getattr(ax, '_stored_xlabel_color', None) or ax.xaxis.label.get_color()),
            'y': mcolors.to_hex(getattr(ax, '_stored_ylabel_color', None) or ax.yaxis.label.get_color()),
        },
        'legend': {
            'visible': legend_visible,
            'position_inches': legend_xy_in,
            'title': _get_legend_title(fig),
        },
        'spines': spines,
        'ticks': {
            'widths': tick_widths,
            'lengths': dict(getattr(fig, '_tick_lengths', {}) or {}),
            'direction': tick_direction,
            'spacing': {
                'x_major_step': _locator_step(ax.xaxis.get_major_locator()),
                'x_minor_step': _locator_step(ax.xaxis.get_minor_locator()),
                'y_major_step': _locator_step(ax.yaxis.get_major_locator()),
                'y_minor_step': _locator_step(ax.yaxis.get_minor_locator()),
                'x_minor_ndivs': _locator_ndivs(ax.xaxis.get_minor_locator()),
                'y_minor_ndivs': _locator_ndivs(ax.yaxis.get_minor_locator()),
            },
        },
        'grid': grid_enabled,
        'wasd_state': wasd_state,
        'title_offsets': {
            'top_y': float(getattr(ax, '_top_xlabel_manual_offset_y_pts', 0.0) or 0.0),
            'top_x': float(getattr(ax, '_top_xlabel_manual_offset_x_pts', 0.0) or 0.0),
            'bottom_y': float(getattr(ax, '_bottom_xlabel_manual_offset_y_pts', 0.0) or 0.0),
            'left_x': float(getattr(ax, '_left_ylabel_manual_offset_x_pts', 0.0) or 0.0),
            'right_x': float(getattr(ax, '_right_ylabel_manual_offset_x_pts', 0.0) or 0.0),
            'right_y': float(getattr(ax, '_right_ylabel_manual_offset_y_pts', 0.0) or 0.0),
        },
        'curve_linewidth': curve_linewidth,
        'curve_markers': curve_marker_props,
        'rotation_angle': getattr(fig, '_ec_rotation_angle', 0),
        'display_mode': getattr(fig, '_ec_display_mode', 'both'),
        'cycle_styles': cycle_styles,
        'ro_active': bool(getattr(fig, '_ro_active', False)),
        'cycle_styles_per_file': cycle_styles_per_file,
        'xaxis_dual': {
            'mode': getattr(fig, '_xaxis_mode', 'capacity'),
            'c_theoretical': getattr(fig, '_xaxis_c_theoretical', None),
            'swapped': getattr(fig, '_xaxis_swapped', False),
            'top_axis': dual_top_axis,
        },
        '_dqdv_smooth_settings': dict(getattr(fig, '_dqdv_smooth_settings', {})),
    }
    if file_data is not None and len(file_data) > 0:
        result['file_display_names'] = [f.get('display_name', f.get('filename', str(i))) for i, f in enumerate(file_data)]
        result['file_visibility'] = [bool(f.get('visible', True)) for f in file_data]
        result['legend_file_order'] = list(getattr(fig, '_ec_legend_file_order', None) or range(len(file_data)))
    return result


def _apply_cycle_styles(cycle_lines: Dict[int, Dict[str, Optional[Any]]], style_cfg: Optional[Dict]) -> None:
    if not isinstance(style_cfg, dict):
        return
    def _apply_one_line_style(ln, style):
        if 'linewidth' in style:
            try:
                ln.set_linewidth(style['linewidth'])
            except Exception:
                pass
        if 'linestyle' in style:
            try:
                ln.set_linestyle(style['linestyle'])
            except Exception:
                pass
        if 'marker' in style:
            try:
                ln.set_marker(style['marker'])
            except Exception:
                pass
        if 'markersize' in style:
            try:
                ln.set_markersize(style['markersize'])
            except Exception:
                pass
        if 'color' in style:
            try:
                apply_curve_color(ln, style['color'])
            except Exception:
                pass
        else:
            if 'markerfacecolor' in style:
                try:
                    ln.set_markerfacecolor(style['markerfacecolor'])
                except Exception:
                    pass
            if 'markeredgecolor' in style:
                try:
                    ln.set_markeredgecolor(style['markeredgecolor'])
                except Exception:
                    pass
        if 'alpha' in style:
            try:
                ln.set_alpha(style['alpha'])
            except Exception:
                pass
        if 'visible' in style:
            try:
                ln.set_visible(bool(style['visible']))
            except Exception:
                pass

    for cyc_key, entry in style_cfg.items():
        try:
            cyc = int(cyc_key)
        except Exception:
            cyc = cyc_key
        if cyc not in cycle_lines:
            continue
        target = cycle_lines[cyc]
        if isinstance(target, dict):
            for role in ("charge", "discharge"):
                ln = target.get(role)
                style = entry.get(role) if isinstance(entry, dict) else None
                if ln is None or not isinstance(style, dict):
                    continue
                _apply_one_line_style(ln, style)
        else:
            ln = target
            style = None
            if isinstance(entry, dict):
                style = entry.get('line', entry)
            elif isinstance(entry, (list, tuple)):
                continue
            else:
                style = entry
            if ln is None or not isinstance(style, dict):
                continue
            _apply_one_line_style(ln, style)


def _print_style_snapshot(cfg: Dict):
    """Prints the style configuration in a user-friendly format matching operando style."""
    def _onoff(v):
        return 'ON ' if bool(v) else 'off'

    print("\n" + "=" * 60)
    print("  EC STYLE SUMMARY")
    print("=" * 60)
    print("Commands (Styles): f, l, k, t, h, g, d, sm | Geometries: c, r, x, y, a, ra")
    print()

    # ---- Canvas & Geometry (g) ----
    canvas_size = cfg.get('figure', {}).get('canvas_size', ['?', '?'])
    frame_size = cfg.get('figure', {}).get('frame_size', ['?', '?'])
    print("--- Canvas & Geometry ---")
    print(f"Canvas size (g): {canvas_size[0]:.3f} x {canvas_size[1]:.3f} in")
    print(f"Plot frame: {frame_size[0]:.3f} x {frame_size[1]:.3f} in")

    # ---- Font (f) ----
    font = cfg.get('font', {})
    print(f"\n--- Font (f) ---")
    print(f"Family='{font.get('family', '')}', size={font.get('size', '')}")

    # ---- Data axes (--ro) ----
    ro_active = bool(cfg.get('ro_active', False))
    rotation_angle = cfg.get('rotation_angle', 0)
    print(f"\n--- Data axes ---")
    print(f"Swapped via --ro: {'YES' if ro_active else 'no'}")
    if rotation_angle != 0:
        print(f"Rotation angle: {rotation_angle}°")

    # ---- Legend (h) ----
    leg_cfg = cfg.get('legend', {})
    if leg_cfg:
        leg_vis = bool(leg_cfg.get('visible', False))
        leg_pos = leg_cfg.get('position_inches')
        if isinstance(leg_pos, (list, tuple)) and len(leg_pos) == 2:
            try:
                lx = float(leg_pos[0])
                ly = float(leg_pos[1])
                pos_str = f"position=({lx:.3f}, {ly:.3f}) in (rel. center)"
            except Exception:
                pos_str = "position=stored"
        else:
            pos_str = "position=auto"
        print(f"\n--- Legend (h) ---")
        print(f"Visible: {'ON' if leg_vis else 'off'}, {pos_str}")
        legend_title = leg_cfg.get('title')
        if legend_title:
            print(f"Legend title: {legend_title}")

    # ---- Toggle spines (t) ----
    wasd = cfg.get('wasd_state', {})
    if wasd:
        print(f"\n--- Toggle spines (t) ---")
        print("WASD (w=top, a=left, s=bottom, d=right): 1=spine 2=ticks 3=minor 4=labels 5=title")
        for side_key, side_label in [('top', 'w'), ('left', 'a'), ('bottom', 's'), ('right', 'd')]:
            s = wasd.get(side_key, {})
            spine_val = _onoff(s.get('spine', False))
            major_val = _onoff(s.get('ticks', False))
            minor_val = _onoff(s.get('minor', False))
            labels_val = _onoff(s.get('labels', False))
            title_val = _onoff(s.get('title', False))
            print(f"  {side_label}1:{spine_val} {side_label}2:{major_val} {side_label}3:{minor_val} {side_label}4:{labels_val} {side_label}5:{title_val}")

    # ---- Line widths (l) ----
    tick_widths = cfg.get('ticks', {}).get('widths', {})
    x_maj = tick_widths.get('x_major')
    x_min = tick_widths.get('x_minor')
    y_maj = tick_widths.get('y_major')
    y_min = tick_widths.get('y_minor')
    spines = cfg.get('spines', {})
    frame_lw = spines.get('bottom', {}).get('linewidth', '?') if spines else '?'
    tick_direction = cfg.get('ticks', {}).get('direction', 'out')
    print(f"\n--- Line widths (l) ---")
    print(f"Frame: {frame_lw}")
    print(f"Ticks: X=({x_maj}, {x_min})  Y=({y_maj}, {y_min})")
    print(f"Tick direction: {tick_direction}")

    # ---- Spines (k) ----
    if spines:
        print("\n--- Spines (k) ---")
        for name in ('bottom', 'top', 'left', 'right'):
            props = spines.get(name, {})
            lw = props.get('linewidth', '?')
            vis = props.get('visible', False)
            col = props.get('color')
            print(f"  {name:<6} lw={lw} visible={vis} color={col}")

    # ---- Grid ----
    grid_enabled = cfg.get('grid', False)
    print(f"\n--- Grid ---")
    print(f"Grid: {'on' if grid_enabled else 'off'}")

    # ---- Curves (c, l) ----
    curve_linewidth = cfg.get('curve_linewidth')
    curve_markers = cfg.get('curve_markers', {})
    if curve_linewidth is not None or curve_markers:
        print(f"\n--- Curves (c, l) ---")
        if curve_linewidth is not None:
            print(f"Curve linewidth: {curve_linewidth:.3g}")
        if curve_markers:
            ls = curve_markers.get('linestyle', '-')
            mk = curve_markers.get('marker', 'None')
            ms = curve_markers.get('markersize', 0)
            print(f"Curve style: linestyle={ls} marker={mk} markersize={ms}")

    cycle_styles = cfg.get('cycle_styles', {})
    if cycle_styles:
        print("\n--- Cycle colors (c) ---")
        def _cycle_sort_key(key):
            try:
                return int(key)
            except Exception:
                return key
        for cyc_key in sorted(cycle_styles.keys(), key=_cycle_sort_key):
            entry = cycle_styles[cyc_key] or {}
            segments = []
            for role_label, role_key in (('charge', 'charge'), ('discharge', 'discharge'), ('line', 'line')):
                style = entry.get(role_key)
                if not isinstance(style, dict):
                    continue
                color = style.get('color', 'unknown')
                vis = 'ON' if style.get('visible', True) else 'off'
                # Show color block for better visualization
                try:
                    color_block_str = color_block(color) if color != 'unknown' else ''
                    segments.append(f"{role_label}={color_block_str} {color} ({vis})")
                except Exception:
                    segments.append(f"{role_label}={color} ({vis})")
            if segments:
                print(f"  Cycle {cyc_key}: {', '.join(segments)}")

    # ---- Legend file order (ra, multi-file) ----
    legend_order = cfg.get('legend_file_order')
    if legend_order and isinstance(legend_order, (list, tuple)):
        print("\n--- Legend order (ra) ---")
        print(f"Order: {[i+1 for i in legend_order]}")

    print("=" * 60 + "\n")


def _export_style_dialog(cfg: Dict, default_ext: str = '.bpcfg', base_path: Optional[str] = None):
    """Handles the dialog for exporting a style configuration to a file.
    
    Args:
        cfg: Configuration dictionary to export
        default_ext: Default file extension ('.bps' for style-only, '.bpsg' for style+geometry)
    """
    try:
        if base_path:
            print(f"\nChosen path: {base_path}")
        # List files with matching extension in Styles/ subdirectory
        file_list = list_files_in_subdirectory((default_ext, '.bpcfg'), 'style', base_path=base_path)
        bpcfg_files = [f[0] for f in file_list]
        if bpcfg_files:
            styles_root = base_path if base_path else os.getcwd()
            styles_dir = os.path.join(styles_root, 'Styles')
            print(f"Existing {default_ext} files in {styles_dir}:")
            for i, f in enumerate(bpcfg_files, 1):
                print(f"  \033[96m{i}\033[0m: {f}")
        
        n_files = len(bpcfg_files)
        exp_prompt = _colorize_option_keys(f"filename, 1-{n_files}: overwrite, q: cancel") if n_files else _colorize_option_keys("filename, q: cancel")
        choice = _safe_input(f"Export to file? ({exp_prompt}): ").strip()
        if not choice or choice.lower() == 'q':
            return

        target_path = ""
        if choice.isdigit() and bpcfg_files and 1 <= int(choice) <= len(bpcfg_files):
            target_path = file_list[int(choice) - 1][1]  # Full path from list
            if not _confirm_overwrite(target_path):
                return
        else:
            # Add default extension if no extension provided
            if not any(choice.lower().endswith(ext) for ext in ['.bps', '.bpsg', '.bpcfg']):
                filename_with_ext = f"{choice}{default_ext}"
            else:
                filename_with_ext = choice
            
            # Use organized path unless it's an absolute path
            if os.path.isabs(filename_with_ext):
                target_path = filename_with_ext
            else:
                target_path = get_organized_path(filename_with_ext, 'style', base_path=base_path)
            
            if not _confirm_overwrite(target_path):
                return
        
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2)
        print(f"Style exported to {target_path}")
        return target_path

    except Exception as e:
        print(f"Export failed: {e}")
        return None

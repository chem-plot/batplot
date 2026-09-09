"""Undo snapshot capture/restore for the electrochem interactive menu.

Extracted verbatim from interactive.py (the former nested ``push_state`` /
``restore_state``). The dispatcher keeps thin nested wrappers with the same
names, so the undo stack, snapshot fields, and message text are unchanged.
Callables that live inside the dispatcher (nice ticks, WASD sync, display
mode, ...) are injected as parameters to preserve late binding.
"""
from __future__ import annotations

import copy

import matplotlib as mpl  # type: ignore[import-untyped]
import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]

from ...ui import (
    capture_axes_tick_locators,
    finalize_spine_colors,
    resolve_spine_dump_color,
    restore_axes_tick_locators,
    set_spine_side_color as _ui_set_spine_side_color,
    sync_figure_geometry_caches,
)
from ..common.font_extras import apply_font_extras_from_cfg, font_extras_export_dict
from ..common.line_dash import capture_dash_pattern, clear_dash_pattern, restore_dash_pattern
from ..common.spines import current_tick_width
from ..common.session_helpers import _current_tick_length, _first_defined
from .colors import (
    _apply_visible_cycle_numbers,
    _iter_cycle_lines,
    _selected_cycle_numbers_for_file,
    _visible_cycle_numbers,
)
from .legend import (
    _apply_file_display_names_to_legend,
    _apply_legend_position,
    _get_legend_title,
    _rebuild_legend,
    _sanitize_legend_offset,
)
from .style import (
    _apply_cycle_styles,
    capture_cycle_styles_snapshot,
    capture_ec_curve_marker_defaults,
    ec_dual_secax,
    xaxis_dual_export_dict,
)


def _tick_width(axis_obj, which: str):
    return current_tick_width(axis_obj, which)


def ec_push_state(
    *,
    state_history,
    fig,
    ax,
    tick_state,
    cycle_lines,
    file_data,
    is_multi_file,
    note: str = "",
):
    """Append a full style/geometry/data snapshot to the undo stack."""
    try:
        _sec_for_titles = ec_dual_secax(fig)
        try:
            _top_title_on = (
                bool(_sec_for_titles.xaxis.label.get_visible())
                if _sec_for_titles is not None
                else bool(getattr(ax, '_top_xlabel_on', False))
            )
        except Exception:
            _top_title_on = bool(getattr(ax, '_top_xlabel_on', False))
        snap = {
            'note': note,
            'xlim': ax.get_xlim(),
            'ylim': ax.get_ylim(),
            'xscale': ax.get_xscale(),
            'yscale': ax.get_yscale(),
            # Prefer stored text (including empty) so cleared/hidden titles round-trip via ``b``.
            # Mode switches sync ``_stored_xlabel`` so ions/capacity undo stays correct.
            'xlabel': (
                str(ax._stored_xlabel) if hasattr(ax, '_stored_xlabel') and ax._stored_xlabel is not None
                else (ax.get_xlabel() or '')
            ),
            'ylabel': (
                str(ax._stored_ylabel) if hasattr(ax, '_stored_ylabel') and ax._stored_ylabel is not None
                else (ax.get_ylabel() or '')
            ),
            'tick_state': dict(tick_state),
            # Deep-copy nested side dicts — shallow dict() shares top/bottom/...
            # objects with the live fig state, so later w1/w2 toggles corrupt undo.
            'wasd_state': (
                {side: dict(state) for side, state in (getattr(fig, '_ec_wasd_state', {}) or {}).items()
                 if isinstance(state, dict)}
                if getattr(fig, '_ec_wasd_state', None) else {}
            ),
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
                'color': resolve_spine_dump_color(ax, name, fig),
            } for name in ('bottom','top','left','right')},
            'display_mode': getattr(fig, '_ec_display_mode', 'both'),
            'capacity_mode': getattr(fig, '_gc_capacity_mode', 'per_cycle') or 'per_cycle',
            'xaxis_dual': xaxis_dual_export_dict(fig, ax),
            '_dqdv_smooth_settings': dict(getattr(fig, '_dqdv_smooth_settings', {})),
            # Linked dQ/dV 2D companion snapshot (BC: older undos omit this key).
            'dqdv_2d_snapshot': copy.deepcopy(
                getattr(fig, '_dqdv_2d_snapshot', None)
            ),
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
                'top_x': _top_title_on,
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
                    'dash': capture_dash_pattern(ln),
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
                snap['visible_cycles_per_file'] = [
                    _selected_cycle_numbers_for_file(f) for f in file_data
                ]
            except Exception:
                pass
        else:
            try:
                snap['visible_cycles'] = _visible_cycle_numbers(cycle_lines) if cycle_lines else None
            except Exception:
                pass
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
        # Prefer fig._tick_lengths; fall back to live artists (session/p parity).
        try:
            lengths = dict(snap.get('tick_lengths') or {})
            if lengths.get('major') is None:
                lengths['major'] = _first_defined(
                    _current_tick_length(ax.xaxis, 'major'),
                    _current_tick_length(ax.yaxis, 'major'),
                )
            if lengths.get('minor') is None:
                lengths['minor'] = _first_defined(
                    _current_tick_length(ax.xaxis, 'minor'),
                    _current_tick_length(ax.yaxis, 'minor'),
                )
            snap['tick_lengths'] = lengths
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
            print("Warning: could not record undo snapshot; this edit is not undoable.")


def ec_restore_state(
    *,
    state_history,
    fig,
    ax,
    tick_state,
    cycle_lines,
    file_data,
    is_multi_file,
    apply_nice_ticks,
    apply_wasd_state,
    update_tick_visibility,
    apply_display_mode,
    apply_font_size,
    apply_font_family,
    ec_font_artists,
):
    """Pop the last snapshot from the undo stack and re-apply it."""
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
            apply_nice_ticks()
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
            sync_figure_geometry_caches(fig, ax)
        except Exception:
            pass
        try:
            from ...utils import finalize_axis_label_text

            xlabel = finalize_axis_label_text(snap.get('xlabel') or '')
            ylabel = finalize_axis_label_text(snap.get('ylabel') or '')
            ax.set_xlabel(xlabel)
            ax.set_ylabel(ylabel)
            ax._stored_xlabel = xlabel
            ax._stored_ylabel = ylabel
        except Exception:
            pass
        # Tick state
        st = snap.get('tick_state', {})
        for k,v in st.items():
            if k in tick_state:
                tick_state[k] = bool(v)
        # WASD state (copy nested sides so live toggles cannot mutate the snap)
        wasd_snap = snap.get('wasd_state', {})
        if wasd_snap:
            setattr(
                fig,
                '_ec_wasd_state',
                {
                    side: dict(state)
                    for side, state in wasd_snap.items()
                    if isinstance(state, dict)
                },
            )
            apply_wasd_state()
        update_tick_visibility()
        # Dual: re-seal all WASD sides + locators/colors after tick_state apply
        try:
            from .style import reseal_ec_chrome, sync_ec_dual_secax_x_locators

            reseal_ec_chrome(
                fig, ax, wasd=getattr(fig, '_ec_wasd_state', None),
                tick_state=getattr(ax, '_saved_tick_state', None),
            )
            sync_ec_dual_secax_x_locators(
                fig, ax, getattr(fig, '_ec_wasd_state', None),
            )
        except Exception:
            pass
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
                    _ui_set_spine_side_color(
                        ax,
                        name,
                        spec['color'],
                        fig=fig,
                        tick_state=getattr(ax, "_saved_tick_state", None)
                        or snap.get("tick_state"),
                    )
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
                apply_font_size(ax, font_size)
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
                        apply_font_family(ax, font_sans_serif[0])
                    elif font_family:
                        apply_font_family(ax, font_family)
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
            apply_font_extras_from_cfg(fig, ec_font_artists(ax), snap.get('font_extras'))
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
            _xd = snap.get('xaxis_dual') or {}
            _is_dual = isinstance(_xd, dict) and _xd.get('mode') == 'dual'
            ax._top_xlabel_on = False if _is_dual else bool(snap.get('titles', {}).get('top_x', False))
            ax._right_ylabel_on = bool(snap.get('titles', {}).get('right_y', False))
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
                        clear_dash_pattern(ln)
                    if item.get('dash'):
                        restore_dash_pattern(ln, item['dash'])
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
                apply_display_mode(dm)
        except Exception:
            pass
        try:
            cap_mode = snap.get('capacity_mode', 'per_cycle') or 'per_cycle'
            if cap_mode in ('per_cycle', 'cumulative'):
                fig._gc_capacity_mode = cap_mode
        except Exception:
            pass
        # Restore xaxis_dual (a, x commands)
        try:
            xd = snap.get('xaxis_dual')
            if isinstance(xd, dict):
                from .style import sanitize_fig_xaxis_swapped

                fig._xaxis_mode = xd.get('mode', 'capacity')
                fig._xaxis_c_theoretical = xd.get('c_theoretical')
                # Recreate secondary axis for dual mode
                mode = fig._xaxis_mode
                c_th = fig._xaxis_c_theoretical
                swapped = sanitize_fig_xaxis_swapped(
                    fig, mode=mode, swapped=xd.get('swapped', False),
                )
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
                        from .style import reapply_ec_dual_secondary_chrome

                        # Restore custom bottom xlabel + WASD top + colors after recreate
                        reapply_ec_dual_secondary_chrome(
                            fig,
                            ax,
                            wasd_state=snap.get('wasd_state'),
                            tick_lengths=snap.get('tick_lengths'),
                            tick_widths=snap.get('tick_widths'),
                            tick_direction=snap.get('tick_direction'),
                            xlabel_bottom=snap.get('xlabel'),
                            top_axis_cfg=xd.get('top_axis'),
                        )
                        # Honor bottom title hide (s5) after dual defaults
                        try:
                            bot = (snap.get('wasd_state') or {}).get('bottom') or {}
                            if isinstance(bot, dict) and 'title' in bot and not bot.get('title'):
                                ax.set_xlabel('')
                                ax.xaxis.label.set_visible(False)
                            elif snap.get('xlabel') is not None:
                                ax.set_xlabel(str(snap.get('xlabel')))
                                ax.xaxis.label.set_visible(True)
                                ax._stored_xlabel = str(snap.get('xlabel'))
                        except Exception:
                            pass
                        # Fonts ran before SecondaryAxis recreate — re-apply to ions chrome
                        try:
                            fs = snap.get('font_size')
                            if fs is not None:
                                apply_font_size(ax, fs)
                            fam = snap.get('font_sans_serif') or []
                            if fam:
                                apply_font_family(ax, fam[0])
                            elif snap.get('font_family'):
                                apply_font_family(ax, snap.get('font_family'))
                            apply_font_extras_from_cfg(
                                fig, ec_font_artists(ax), snap.get('font_extras')
                            )
                        except Exception:
                            pass
                    except Exception:
                        pass
                elif mode == 'ions' and c_th is not None:
                    # Lines already restored from snap (x=ions); prefer snap label.
                    # Intentional "" must not fall back to the ions default.
                    xlab = snap.get('xlabel')
                    if xlab is not None:
                        ax.set_xlabel(str(xlab))
                    else:
                        ax.set_xlabel(
                            f"Number of ions (C / {float(c_th):g} mAh g$^{{-1}}$)"
                        )
        except Exception:
            pass
        # Per-cycle styles (c command) and global marker template
        try:
            curve_markers = snap.get('curve_markers', {})
            if curve_markers:
                try:
                    fig._ec_curve_markers = dict(curve_markers)
                except Exception:
                    pass
                for cyc, role, ln in _iter_cycle_lines(cycle_lines):
                    try:
                        if 'linestyle' in curve_markers:
                            ln.set_linestyle(curve_markers['linestyle'])
                            clear_dash_pattern(ln)
                        if curve_markers.get('dash_pattern'):
                            restore_dash_pattern(ln, curve_markers['dash_pattern'])
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
        # Authoritative visible-cycle ids override per-line style flags (p/i/s parity)
        try:
            vis_per_file = snap.get('visible_cycles_per_file')
            if (
                vis_per_file is not None
                and is_multi_file
                and file_data
                and len(vis_per_file) == len(file_data)
            ):
                for f, vis in zip(file_data, vis_per_file):
                    cl = f.get('cycle_lines') or {}
                    if cl and vis is not None:
                        _apply_visible_cycle_numbers(cl, vis)
                    if not f.get('visible', True) and vis is not None:
                        try:
                            f['selected_cycles'] = sorted({int(c) for c in vis})
                        except Exception:
                            pass
                    if not f.get('visible', True):
                        for _cyc, _role, ln in _iter_cycle_lines(cl):
                            try:
                                ln.set_visible(False)
                            except Exception:
                                pass
            elif snap.get('visible_cycles') is not None:
                if is_multi_file and file_data:
                    for f in file_data:
                        cl = f.get('cycle_lines') or {}
                        if cl:
                            _apply_visible_cycle_numbers(cl, snap.get('visible_cycles'))
                else:
                    _apply_visible_cycle_numbers(cycle_lines, snap.get('visible_cycles'))
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
                    title_val = legend_snap.get('title')
                    fig._ec_legend_title = "" if title_val is None else str(title_val)
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
            from .style import reseal_ec_chrome, sync_ec_dual_secax_x_locators

            reseal_ec_chrome(fig, ax, tick_state=tick_state_snap)
            sync_ec_dual_secax_x_locators(fig, ax, getattr(fig, '_ec_wasd_state', None))
            finalize_spine_colors(fig, ax, tick_state=tick_state_snap)
        except Exception:
            try:
                tick_state_snap = getattr(ax, '_saved_tick_state', None) or snap.get('tick_state', {})
                finalize_spine_colors(fig, ax, tick_state=tick_state_snap)
            except Exception:
                pass
        # Restore / clear linked 2D companion snapshot (older snaps: key absent → clear).
        try:
            if 'dqdv_2d_snapshot' in snap:
                blob = snap.get('dqdv_2d_snapshot')
                if blob is None:
                    if hasattr(fig, '_dqdv_2d_snapshot'):
                        delattr(fig, '_dqdv_2d_snapshot')
                else:
                    fig._dqdv_2d_snapshot = copy.deepcopy(blob)
        except Exception:
            pass
        try:
            fig.canvas.draw()
        except Exception:
            fig.canvas.draw_idle()
        print("Undo: restored previous state.")
    except Exception as e:
        try:
            state_history.append(snap)
        except Exception:
            pass
        print(f"Undo failed: {e}")

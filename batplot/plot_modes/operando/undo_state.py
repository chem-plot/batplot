"""Undo snapshot capture/restore for the operando interactive menu.

Extracted verbatim from interactive.py (the former nested ``_snapshot`` /
``_restore``). The dispatcher keeps thin nested wrappers with the same names
and owns ``state_history``. Dispatcher-local callables (``set_fonts``,
``_get_spine_visible``, ...) and monkeypatch-sensitive module attributes
(``_axis_tick_width``, ``_maybe_reapply_dqdv_2d_contour``, ...) are injected
as parameters to preserve late binding; snapshot fields and messages are
unchanged.
"""
from __future__ import annotations

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]

from ...ui import (
    apply_wasd_minor_ticks,
    capture_axes_tick_locators,
    finalize_spine_colors_for_axes,
    position_bottom_xlabel as _ui_position_bottom_xlabel,
    position_left_ylabel as _ui_position_left_ylabel,
    position_right_ylabel as _ui_position_right_ylabel,
    position_top_xlabel as _ui_position_top_xlabel,
    resolve_spine_dump_color,
    restore_axes_tick_locators,
    set_spine_side_color as _ui_set_spine_side_color,
)
from ..common.font_extras import (
    apply_font_extras_from_cfg,
    font_extras_export_dict,
    refresh_font_extras_on_artists,
)
from ..common.interactive_state import right_y_major_visibility
from ..common.line_dash import capture_dash_pattern, clear_dash_pattern, restore_dash_pattern
from ..common.session_helpers import _artist_linewidth
from ..common.spines import (
    apply_wasd_spines,
    apply_wasd_tick_params,
    keep_yaxis_label_on_side,
    wasd_to_tick_state,
)
from ..common.title_offsets import capture_title_offsets, restore_title_offsets
from .ions_axis import (
    clear_ec_ion_overlays,
    install_ec_ions_y_display,
    restore_ec_time_y_display,
    restore_ion_overlays_from_state,
)
from .layout import (
    _apply_group_layout_inches,
    _ensure_fixed_params,
    _get_fig_size,
    _safe_set_clim,
    _update_custom_colorbar,
)
from .plot import _draw_operando_cif_ticks


def op_snapshot(
    *,
    state_history,
    fig,
    ax,
    im,
    cbar,
    ec_ax,
    get_spine_visible,
    axis_tick_width,
    note: str = "",
):
    """Append a full operando/EC snapshot to the undo stack."""
    try:
        fig_w, fig_h = _get_fig_size(fig)
        # Geometry inches
        cb_w_in_s, cb_gap_in_s, ec_gap_in_s, ec_w_in_s, ax_w_in_s, ax_h_in_s = _ensure_fixed_params(fig, ax, cbar.ax, ec_ax)
        # Axes & image
        op_xlim = ax.get_xlim(); op_ylim = ax.get_ylim()
        # EC axes (only if ec_ax exists)
        if ec_ax is not None:
            ec_xlim = ec_ax.get_xlim(); ec_ylim = ec_ax.get_ylim()
        else:
            ec_xlim = None; ec_ylim = None
        try:
            clim = im.get_clim()
        except Exception:
            clim = None
        # Full image remesh only needed when undoing Options ``u`` (large arrays).
        op_extent = None
        op_array = None
        if note == "axis-units":
            try:
                op_extent = tuple(float(v) for v in im.get_extent())
            except Exception:
                op_extent = None
            try:
                arr0 = im.get_array()
                if hasattr(arr0, "filled"):
                    op_array = np.ma.filled(arr0, np.nan).astype(float, copy=True)
                else:
                    op_array = np.asarray(arr0, dtype=float).copy()
            except Exception:
                op_array = None
            # Refuse incomplete remesh undo baseline (avoids mode/image desync)
            if op_array is None or op_extent is None or len(op_extent) != 4:
                print("Warning: could not capture image for axis-units undo.")
                return False
        # Get colormap name: first check if we stored it explicitly, otherwise try to get from colormap object
        cmap_name = getattr(im, '_operando_cmap_name', None)
        if cmap_name is None:
            cmap_name = getattr(im.get_cmap(), 'name', None)
        # EC mode and caches (only if ec_ax exists)
        if ec_ax is not None:
            mode = getattr(ec_ax, '_ec_y_mode', 'time')
            ions_abs = getattr(ec_ax, '_ions_abs', None)
            prev_xlim = getattr(ec_ax, '_prev_ec_xlim', None)
            ions_expanded = getattr(ec_ax, '_ions_xlim_expanded', False)
            saved_time_ylim = getattr(ec_ax, '_saved_time_ylim', None)
            ion_params = dict(getattr(ec_ax, '_ion_params', {})) if getattr(ec_ax, '_ion_params', None) else None
            ec_labels = getattr(ec_ax, '_custom_labels', {'x': ec_ax.get_xlabel(), 'y_time': None, 'y_ions': None})
            ion_guides = []
            for gl in getattr(ec_ax, '_ion_guides', []) or []:
                try:
                    ydata = np.asarray(gl.get_ydata(), float)
                    if ydata.size:
                        ion_guides.append(float(ydata[0]))
                except Exception:
                    pass
            ion_annots = []
            for ann in getattr(ec_ax, '_ion_annots', []) or []:
                try:
                    ion_annots.append({
                        'text': ann.get_text(),
                        'xy': tuple(float(v) for v in ann.xy),
                    })
                except Exception:
                    pass
        else:
            mode = 'time'
            ions_abs = None
            prev_xlim = None
            ions_expanded = False
            saved_time_ylim = None
            ion_params = None
            ec_labels = None
            ion_guides = []
            ion_annots = []
        # Labels & fonts
        op_labels = getattr(ax, '_custom_labels', {'x': ax.get_xlabel(), 'y': ax.get_ylabel()})
        fam = plt.rcParams.get('font.sans-serif', [])
        fsize = plt.rcParams.get('font.size', None)
        mathtext_fs = plt.rcParams.get('mathtext.fontset', 'dejavusans')
        # WASD state for both panes (minor flags from _saved_tick_state, not tick_params alone)
        op_ts_snap = getattr(ax, '_saved_tick_state', {}) or {}
        op_wasd = {
            'top':    {'spine': get_spine_visible(ax, 'top'),
                       'ticks': bool(op_ts_snap.get('t_ticks', op_ts_snap.get('tx', False))),
                       'minor': bool(op_ts_snap.get('mtx', False)),
                       'labels': bool(op_ts_snap.get('t_labels', op_ts_snap.get('tx', False))),
                       'title': bool(getattr(ax, '_top_xlabel_on', False))},
            'bottom': {'spine': get_spine_visible(ax, 'bottom'),
                       'ticks': bool(op_ts_snap.get('b_ticks', op_ts_snap.get('bx', True))),
                       'minor': bool(op_ts_snap.get('mbx', False)),
                       'labels': bool(op_ts_snap.get('b_labels', op_ts_snap.get('bx', True))),
                       'title': bool(ax.xaxis.label.get_visible())},
            'left':   {'spine': get_spine_visible(ax, 'left'),
                       'ticks': bool(op_ts_snap.get('l_ticks', op_ts_snap.get('ly', True))),
                       'minor': bool(op_ts_snap.get('mly', False)),
                       'labels': bool(op_ts_snap.get('l_labels', op_ts_snap.get('ly', True))),
                       'title': bool(ax.yaxis.label.get_visible())},
            'right':  {'spine': get_spine_visible(ax, 'right'),
                       'ticks': bool(op_ts_snap.get('r_ticks', op_ts_snap.get('ry', False))),
                       'minor': bool(op_ts_snap.get('mry', False)),
                       'labels': bool(op_ts_snap.get('r_labels', op_ts_snap.get('ry', False))),
                       'title': bool(getattr(ax, '_right_ylabel_on', False))},
        }
        # EC WASD state (only if ec_ax exists)
        if ec_ax is not None:
            # For EC, check if ylabel is currently visible (not hidden by user via d5)
            # EC uses the actual ylabel positioned on right, not a duplicate artist
            try:
                ec_ylabel_visible = bool(ec_ax.yaxis.label.get_visible())
            except Exception:
                ec_ylabel_visible = bool(ec_ax.get_ylabel())
            ec_ts_snap = getattr(ec_ax, '_saved_tick_state', {}) or {}
            # The EC y-axis lives on the right and is the panel's primary axis. Capture its
            # ACTUAL displayed tick/label visibility rather than trusting _saved_tick_state,
            # which can drift out of sync (e.g. after a session load stores r_ticks=False while
            # the ticks are actually shown). Using the stale state made undo (b) wrongly hide
            # the EC right ticks/labels after commands like oy.
            ec_right_ticks_vis, ec_right_labels_vis = right_y_major_visibility(ec_ax)
            ec_wasd = {
                'top':    {'spine': get_spine_visible(ec_ax, 'top'),
                           'ticks': bool(ec_ts_snap.get('t_ticks', ec_ts_snap.get('tx', False))),
                           'minor': bool(ec_ts_snap.get('mtx', False)),
                           'labels': bool(ec_ts_snap.get('t_labels', ec_ts_snap.get('tx', False))),
                           'title': bool(getattr(ec_ax, '_top_xlabel_on', False))},
                'bottom': {'spine': get_spine_visible(ec_ax, 'bottom'),
                           'ticks': bool(ec_ts_snap.get('b_ticks', ec_ts_snap.get('bx', True))),
                           'minor': bool(ec_ts_snap.get('mbx', False)),
                           'labels': bool(ec_ts_snap.get('b_labels', ec_ts_snap.get('bx', True))),
                           'title': bool(ec_ax.xaxis.label.get_visible())},
                'left':   {'spine': get_spine_visible(ec_ax, 'left'),
                           'ticks': bool(ec_ts_snap.get('l_ticks', False)),
                           'minor': bool(ec_ts_snap.get('mly', False)),
                           'labels': bool(ec_ts_snap.get('l_labels', False)),
                           'title': False},
                'right':  {'spine': get_spine_visible(ec_ax, 'right'),
                           'ticks': ec_right_ticks_vis,
                           'minor': bool(ec_ts_snap.get('mry', False)),
                           'labels': ec_right_labels_vis,
                           'title': ec_ylabel_visible},
            }
        else:
            ec_wasd = None
        # Visibility states
        cb_visible = bool(cbar.ax.get_visible())
        ec_visible = bool(ec_ax.get_visible()) if ec_ax is not None else None
        cb_label = getattr(cbar.ax, '_colorbar_label', cbar.ax.get_ylabel() or 'Intensity')
        cb_label_mode = getattr(fig, '_colorbar_label_mode', 'highlow')
        # Horizontal offsets (relative to canvas center, in inches)
        cb_h_offset = getattr(cbar.ax, '_cb_h_offset_in', 0.0)
        ec_h_offset = getattr(ec_ax, '_ec_h_offset_in', 0.0) if ec_ax is not None else None
        # Colorbar tick/label positions (left/right)
        cb_ticks_left = True
        cb_label_left = True
        try:
            cb_ticks_left = any(getattr(tick, 'tick1line', None) and tick.tick1line.get_visible() for tick in cbar.ax.yaxis.get_major_ticks())
            # label position is stored on axis; capture current setting
            cb_label_left = (cbar.ax.yaxis.get_label_position() == 'left')
        except Exception:
            pass
        # Label pads (save current labelpad values to restore later)
        op_labelpads = {
            'x': getattr(ax.xaxis, 'labelpad', None),
            'y': getattr(ax.yaxis, 'labelpad', None),
        }
        ec_labelpads = None
        if ec_ax is not None:
            ec_labelpads = {
                'x': getattr(ec_ax.xaxis, 'labelpad', None),
                'y': getattr(ec_ax.yaxis, 'labelpad', None),
            }
        # Spine and tick widths (l command) for undo
        op_spines_snap = {}
        for name in ('bottom', 'top', 'left', 'right'):
            sp = ax.spines.get(name)
            if sp:
                op_spines_snap[name] = {
                    'linewidth': float(sp.get_linewidth()),
                    'color': resolve_spine_dump_color(ax, name, fig),
                    'visible': bool(sp.get_visible()),
                }
        op_ticks_snap = {
            'x_major': axis_tick_width(ax.xaxis, 'major'),
            'x_minor': axis_tick_width(ax.xaxis, 'minor'),
            'y_major': axis_tick_width(ax.yaxis, 'major'),
            'y_minor': axis_tick_width(ax.yaxis, 'minor'),
        }
        ec_spines_snap = None
        ec_ticks_snap = None
        ec_line_style = None
        if ec_ax is not None:
            ec_spines_snap = {}
            for name in ('bottom', 'top', 'left', 'right'):
                sp = ec_ax.spines.get(name)
                if sp:
                    ec_spines_snap[name] = {
                        'linewidth': float(sp.get_linewidth()),
                        'color': resolve_spine_dump_color(ec_ax, name, fig),
                        'visible': bool(sp.get_visible()),
                    }
            ec_ticks_snap = {
                'x_major': axis_tick_width(ec_ax.xaxis, 'major'),
                'x_minor': axis_tick_width(ec_ax.xaxis, 'minor'),
                'y_major': axis_tick_width(ec_ax.yaxis, 'major'),
                'y_minor': axis_tick_width(ec_ax.yaxis, 'minor'),
            }
            ln = getattr(ec_ax, '_ec_line', None)
            if ln is None and ec_ax.lines:
                try:
                    ln = ec_ax.lines[0]
                except Exception:
                    ln = None
            if ln is not None:
                try:
                    ec_line_style = {
                        'color': ln.get_color(),
                        'linewidth': _artist_linewidth(ln),
                        'linestyle': ln.get_linestyle(),
                        'dash_pattern': capture_dash_pattern(ln),
                        'marker': ln.get_marker(),
                        'markersize': ln.get_markersize(),
                        'alpha': ln.get_alpha(),
                    }
                except Exception:
                    pass
        state_history.append({
            'note': note,
            'fig_size': (fig_w, fig_h),
            'geom': (cb_w_in_s, cb_gap_in_s, ec_gap_in_s, ec_w_in_s, ax_w_in_s, ax_h_in_s),
            'op_xlim': op_xlim, 'op_ylim': op_ylim,
            'op_extent': op_extent,
            'op_array': op_array,
            'operando_axis_mode': getattr(fig, '_operando_axis_mode', None),
            'operando_wl': getattr(fig, '_operando_wl', None),
            'ec_xlim': ec_xlim, 'ec_ylim': ec_ylim,
            'clim': clim, 'cmap': cmap_name,
            'ec_mode': mode,
            'ions_abs': (np.array(ions_abs, float) if ions_abs is not None else None),
            'prev_ec_xlim': prev_xlim,
            'ions_expanded': bool(ions_expanded),
            'saved_time_ylim': saved_time_ylim,
            'ion_params': ion_params,
            'ion_guides': ion_guides,
            'ion_annots': ion_annots,
            'op_labels': dict(op_labels) if isinstance(op_labels, dict) else {'x': ax.get_xlabel(), 'y': ax.get_ylabel()},
            'ec_labels': dict(ec_labels) if ec_labels is not None and isinstance(ec_labels, dict) else None,
            'font': {'family': list(fam), 'size': fsize, 'mathtext_fontset': mathtext_fs, **font_extras_export_dict(fig)},
            'op_wasd': dict(op_wasd),
            'ec_wasd': dict(ec_wasd) if ec_wasd is not None else None,
            'tick_lengths': getattr(fig, '_tick_lengths', None),
            'tick_direction': getattr(fig, '_tick_direction', 'out'),
            'tick_spacing_op': capture_axes_tick_locators(ax, ('x', 'y')),
            'tick_spacing_ec': capture_axes_tick_locators(ec_ax, ('x', 'y')) if ec_ax is not None else None,
            'cb_visible': cb_visible,
            'cb_label': str(cb_label),
            'cb_label_mode': cb_label_mode,
            'ec_visible': ec_visible,
            'cb_h_offset': float(cb_h_offset),
            'ec_h_offset': float(ec_h_offset) if ec_h_offset is not None else None,
            'cb_ticks_left': cb_ticks_left,
            'cb_label_left': cb_label_left,
            'op_labelpads': dict(op_labelpads),
            'ec_labelpads': dict(ec_labelpads) if ec_labelpads is not None else None,
            'op_title_offsets': capture_title_offsets(ax),
            'ec_title_offsets': capture_title_offsets(ec_ax) if ec_ax is not None else None,
            'op_spines': op_spines_snap,
            'op_ticks': op_ticks_snap,
            'ec_spines': ec_spines_snap,
            'ec_ticks': ec_ticks_snap,
            'ec_line_style': ec_line_style,
            'ec_grid': dict(getattr(ec_ax, '_ec_grid', None) or {}) if ec_ax is not None else None,
            'operando_cif': {
                'tick_series': list(getattr(ax, '_operando_cif_tick_series', None) or []),
                'hkl_label_map': dict(getattr(ax, '_operando_cif_hkl_label_map', None) or {}),
                'show_hkl': bool(getattr(fig, '_operando_cif_show_hkl', False)),
                'show_titles': bool(getattr(fig, '_operando_cif_show_titles', True)),
                'placement': str(getattr(fig, '_operando_cif_placement', 'below')),
                'y_positions': list(getattr(fig, '_operando_cif_y_positions', None) or []),
                'colormap': getattr(fig, '_operando_cif_colormap', None),
                'highlight': bool(getattr(fig, '_operando_cif_highlight', False)),
                'title_font': dict(getattr(fig, '_operando_cif_title_font', None) or {}),
                'title_visible': list(getattr(fig, '_operando_cif_title_visible', None) or []),
                'set_visible': list(getattr(fig, '_operando_cif_set_visible', None) or []),
            },
            'dqdv_2d': {
                'v_lo': float(getattr(fig, '_dqdv_2d_v_lo', 0.0)),
                'v_hi': float(getattr(fig, '_dqdv_2d_v_hi', 0.0)),
                'row_labels': [str(s) for s in (getattr(fig, '_dqdv_2d_row_labels', None) or [])],
                'zlabel': str(getattr(fig, '_dqdv_2d_zlabel', 'dQ/dV')),
            } if getattr(fig, '_is_dqdv_2d_contour', False) else None,
        })
        if len(state_history) > 40:
            state_history.pop(0)
        return True
    except Exception as e:
        print(f"Warning: snapshot failed: {e}")
        return False


def op_restore(
    *,
    state_history,
    fig,
    ax,
    im,
    cbar,
    ec_ax,
    set_fonts,
    operando_font_artists,
    maybe_reapply_dqdv_2d_contour,
    restore_dqdv_2d_operando_labels,
):
    """Pop the last snapshot from the undo stack and re-apply it."""
    if not state_history:
        print("No undo history."); return
    # Single pop (XY/EC/CPC parity). The old double-pop discarded the only
    # snapshot after the first edit so ``b`` printed "No undo history" and
    # left the figure unchanged.
    snap = state_history.pop()
    try:
        # Canvas size
        try:
            W, H = snap['fig_size']
            fig.set_size_inches(max(1.0, float(W)), max(1.0, float(H)), forward=True)
        except Exception:
            pass
        # Geometry inches
        try:
            cb_w_i, cb_gap_i, ec_gap_i, ec_w_i, ax_w_i, ax_h_i = snap['geom']
            _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, float(ax_w_i), float(ax_h_i), float(cb_w_i), float(cb_gap_i), float(ec_gap_i), float(ec_w_i))
        except Exception:
            pass
        # Horizontal offsets
        try:
            cb_h_offset = snap.get('cb_h_offset', 0.0)
            setattr(cbar.ax, '_cb_h_offset_in', float(cb_h_offset))
            ec_h_offset = snap.get('ec_h_offset')
            if ec_ax is not None and ec_h_offset is not None:
                setattr(ec_ax, '_ec_h_offset_in', float(ec_h_offset))
            elif ec_ax is not None:
                setattr(ec_ax, '_ec_h_offset_in', 0.0)
            # Reapply layout with restored offsets
            cb_w_i, cb_gap_i, ec_gap_i, ec_w_i, ax_w_i, ax_h_i = _ensure_fixed_params(fig, ax, cbar.ax, ec_ax)
            _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, ax_w_i, ax_h_i, cb_w_i, cb_gap_i, ec_gap_i, ec_w_i)
        except Exception:
            pass
        # Colorbar tick/label side (attrs survive later _update_custom_colorbar)
        try:
            cb_ticks_left = snap.get('cb_ticks_left', True)
            cb_label_left = snap.get('cb_label_left', True)
            cbar.ax._colorbar_ticks_left = bool(cb_ticks_left)
            cbar.ax._colorbar_label_left = bool(cb_label_left)
            cbar.ax.yaxis.set_ticks_position('left' if cb_ticks_left else 'right')
            cbar.ax.yaxis.set_label_position('left' if cb_label_left else 'right')
        except Exception:
            pass
        # Labels (2D dQ/dV: restored again after potential-window rebuild below)
        try:
            op_l = snap.get('op_labels', {})
            if getattr(fig, '_is_dqdv_2d_contour', False):
                restore_dqdv_2d_operando_labels(ax, op_l)
            elif isinstance(op_l, dict):
                # ``is not None`` so empty-string clears (p/i parity).
                if op_l.get('x') is not None:
                    ax.set_xlabel(str(op_l.get('x') or ''))
                    ax._stored_xlabel = op_l.get('x')
                if op_l.get('y') is not None:
                    ax.set_ylabel(str(op_l.get('y') or ''))
                    ax._stored_ylabel = op_l.get('y')
                try:
                    ax._custom_labels = dict(op_l)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            ec_l = snap.get('ec_labels', {})
            if ec_ax is not None and isinstance(ec_l, dict):
                if ec_l.get('x') is not None:
                    text = str(ec_l.get('x') or '')
                    ec_ax.set_xlabel(text)
                    ec_ax._stored_xlabel = text
                try:
                    ec_ax._custom_labels = dict(ec_l)
                except Exception:
                    pass
        except Exception:
            pass
        # Fonts - use set_fonts to properly update all labels including label2
        try:
            font = snap.get('font', {})
            fam = font.get('family')
            size = font.get('size')
            mathtext_fs = font.get('mathtext_fontset')
            # Restore mathtext.fontset first
            if mathtext_fs:
                try:
                    plt.rcParams['mathtext.fontset'] = mathtext_fs
                except Exception:
                    pass
            if fam or size is not None:
                # Convert family list back to string
                if isinstance(fam, list) and fam:
                    fam = fam[0]
                set_fonts(family=fam if fam else None, size=size if size is not None else None)
            try:
                apply_font_extras_from_cfg(fig, operando_font_artists(), font)
            except Exception:
                pass
        except Exception:
            pass
        # Operando axes and image
        try:
            # Restore axis mode / wavelength before CIF redraw below
            if snap.get('operando_axis_mode') in (
                '2theta', 'Q', 'd', 'r', 'user_defined', 'energy',
            ):
                fig._operando_axis_mode = snap.get('operando_axis_mode')
            if 'operando_wl' in snap:
                fig._operando_wl = snap.get('operando_wl')
        except Exception:
            pass
        try:
            if snap.get('op_array') is not None:
                im.set_data(np.asarray(snap['op_array'], dtype=float))
            if snap.get('op_extent') is not None and len(snap['op_extent']) == 4:
                im.set_extent(tuple(float(v) for v in snap['op_extent']))
        except Exception:
            pass
        try:
            if getattr(fig, '_is_dqdv_2d_contour', False):
                ax.set_ylim(*snap['op_ylim'])
            else:
                ax.set_xlim(*snap['op_xlim'])
                ax.set_ylim(*snap['op_ylim'])
        except Exception:
            pass
        try:
            # Keep spine-title restore text in sync with restored xlabel
            op_lab = snap.get('op_labels') or {}
            if isinstance(op_lab, dict) and op_lab.get('x') is not None:
                ax._stored_xlabel = op_lab.get('x')
        except Exception:
            pass
        try:
            if snap.get('clim') is not None:
                # Detach built-in colorbar update to avoid artist removal errors; we redraw custom below.
                try:
                    if hasattr(cbar, 'mappable'):
                        cbar.mappable = None
                    if hasattr(cbar, 'solids'):
                        cbar.solids = None
                except Exception:
                    pass
                lo, hi = snap['clim']; _safe_set_clim(im, float(lo), float(hi))
        except Exception:
            pass
        try:
            if snap.get('cmap'):
                cmap_name = snap['cmap']
                im.set_cmap(cmap_name)
                # Store the colormap name explicitly so it can be retrieved reliably when saving
                setattr(im, '_operando_cmap_name', cmap_name)
                if cbar is not None:
                    _update_custom_colorbar(cbar.ax, im)
        except Exception:
            pass
        # Restore colorbar side (ticks/label) and redraw custom colorbar to keep position
        try:
            if cbar is not None:
                cb_ticks_left = snap.get('cb_ticks_left', True)
                cb_label_left = snap.get('cb_label_left', True)
                cbar.ax._colorbar_ticks_left = bool(cb_ticks_left)
                cbar.ax._colorbar_label_left = bool(cb_label_left)
                cbar.ax.yaxis.set_ticks_position('left' if cb_ticks_left else 'right')
                cbar.ax.yaxis.set_label_position('left' if cb_label_left else 'right')
                cb_label = snap.get('cb_label', getattr(cbar.ax, '_colorbar_label', None))
                cb_label_mode = snap.get('cb_label_mode', getattr(fig, '_colorbar_label_mode', 'highlow'))
                if cb_label is not None:
                    cbar.ax._colorbar_label = cb_label
                fig._colorbar_label_mode = cb_label_mode
                _update_custom_colorbar(cbar.ax, im, label=cb_label, label_mode=cb_label_mode)
        except Exception:
            pass
        # EC axes
        try:
            if ec_ax is not None:
                ec_ax.set_xlim(*snap['ec_xlim']); ec_ax.set_ylim(*snap['ec_ylim'])
        except Exception:
            pass
        # EC y-mode
        try:
            if ec_ax is None:
                pass  # Skip EC mode restoration when no EC panel
            else:
                mode = snap.get('ec_mode', 'time')
                if mode == 'ions':
                    setattr(ec_ax, '_ec_y_mode', 'ions')
                    ions_abs = snap.get('ions_abs')
                    if ions_abs is not None:
                        setattr(ec_ax, '_ions_abs', np.asarray(ions_abs, float))
                    if snap.get('prev_ec_xlim') is not None:
                        setattr(ec_ax, '_prev_ec_xlim', tuple(snap.get('prev_ec_xlim')))
                    setattr(ec_ax, '_ions_xlim_expanded', bool(snap.get('ions_expanded', False)))
                    if snap.get('saved_time_ylim') is not None:
                        setattr(ec_ax, '_saved_time_ylim', tuple(snap.get('saved_time_ylim')))
                    if snap.get('ion_params'):
                        setattr(ec_ax, '_ion_params', dict(snap.get('ion_params')))
                    # Status-bar ions mapping + overlays only (time spine unchanged)
                    t = np.asarray(getattr(ec_ax, "_ec_time_h", []), float)
                    arr = getattr(ec_ax, "_ions_abs", None)
                    if arr is not None and t.size:
                        restore_ec_time_y_display(ec_ax)
                        install_ec_ions_y_display(ec_ax, t, arr, save_prev=False)
                    try:
                        # Key-presence: intentional "" must not become "Time (h)".
                        ec_labs = snap.get('ec_labels', {}) or {}
                        if 'y_time' in ec_labs and ec_labs.get('y_time') is not None:
                            text = str(ec_labs.get('y_time'))
                            ec_ax.set_ylabel(text)
                            ec_ax._stored_ylabel = text
                        else:
                            legacy = ec_labs.get('y_ions')
                            cur_lab = (ec_ax.get_ylabel() or '').strip()
                            if cur_lab.lower() in ('number of ions', 'ions') or legacy:
                                ec_ax.set_ylabel('Time (h)')
                                ec_ax._stored_ylabel = 'Time (h)'
                    except Exception:
                        pass
                    restore_ion_overlays_from_state(
                        ec_ax,
                        ion_guides=snap.get('ion_guides', []) or [],
                        ion_annots=snap.get('ion_annots', []) or [],
                    )
                    # Restore xlim adjustments used in ions mode if present
                    prev_xlim = snap.get('prev_ec_xlim')
                    ions_exp = bool(snap.get('ions_expanded', False))
                    if prev_xlim and not ions_exp:
                        try:
                            ec_ax.set_xlim(*prev_xlim)
                        except Exception:
                            pass
                else:
                    setattr(ec_ax, '_ec_y_mode', 'time')
                    # Remove ion guides and annotations when restoring to time mode
                    clear_ec_ion_overlays(ec_ax)
                    restore_ec_time_y_display(ec_ax)
                    try:
                        ec_labs = snap.get('ec_labels', {}) or {}
                        if 'y_time' in ec_labs and ec_labs.get('y_time') is not None:
                            text = str(ec_labs.get('y_time'))
                            ec_ax.set_ylabel(text)
                            ec_ax._stored_ylabel = text
                        else:
                            ec_ax.set_ylabel('Time (h)')
                            ec_ax._stored_ylabel = 'Time (h)'
                    except Exception:
                        pass
                    try:
                        keep_yaxis_label_on_side(ec_ax, 'right')
                    except Exception:
                        pass
                    st_ylim = snap.get('saved_time_ylim')
                    if st_ylim and isinstance(st_ylim,(list,tuple)) and len(st_ylim)==2:
                        try:
                            ec_ax.set_ylim(*st_ylim)
                        except Exception:
                            pass
        except Exception:
            pass
        # Restore WASD state for both panes
        try:
            op_wasd = snap.get('op_wasd')
            ec_wasd = snap.get('ec_wasd')
            if op_wasd:
                apply_wasd_spines(ax, op_wasd)
                apply_wasd_tick_params(
                    ax,
                    op_wasd,
                    y_sides=('left',),
                    y_mode='left',
                )
                for side in ['top', 'right']:
                    st = op_wasd.get(side, {})
                    # Title restoration
                    if side == 'top' and 'title' in st:
                        setattr(ax, '_top_xlabel_on', bool(st['title']))
                    elif side == 'right' and 'title' in st:
                        setattr(ax, '_right_ylabel_on', bool(st['title']))
            if ec_wasd and ec_ax is not None:
                apply_wasd_spines(ec_ax, ec_wasd)
                apply_wasd_tick_params(
                    ec_ax,
                    ec_wasd,
                    y_sides=('right',),
                    y_mode='right',
                )
                for side in ['top', 'right']:
                    st = ec_wasd.get(side, {})
                    # Title restoration
                    if side == 'top' and 'title' in st:
                        setattr(ec_ax, '_top_xlabel_on', bool(st['title']))
                    elif side == 'right' and 'title' in st:
                        # EC right title is actual ylabel, not duplicate
                        setattr(ec_ax, '_right_ylabel_on', bool(st['title']))
                        if bool(st['title']):
                            stored = getattr(ec_ax, '_stored_ylabel', None)
                            # Intentional "" must not be treated as missing.
                            if isinstance(stored, str):
                                ec_ax.set_ylabel(stored)
                        else:
                            if not hasattr(ec_ax, '_stored_ylabel'):
                                ec_ax._stored_ylabel = ec_ax.get_ylabel()
                            ec_ax.set_ylabel('')
            # Re-position titles using UI module functions
            try:
                # Build current tick state dict for UI functions
                op_tick_state = {}
                ec_tick_state = {}
                if op_wasd:
                    op_tick_state = wasd_to_tick_state(
                        op_wasd,
                        tick_defaults={'top': False, 'bottom': True, 'left': True, 'right': False},
                        label_defaults={'top': False, 'bottom': True, 'left': True, 'right': False},
                    )
                if ec_wasd:
                    ec_tick_state = wasd_to_tick_state(
                        ec_wasd,
                        tick_defaults={'top': False, 'bottom': True, 'left': False, 'right': True},
                        label_defaults={'top': False, 'bottom': True, 'left': False, 'right': True},
                    )
                try:
                    ax._saved_tick_state = dict(op_tick_state)
                    if ec_ax is not None:
                        ec_ax._saved_tick_state = dict(ec_tick_state)
                except Exception:
                    pass
                # Position titles
                _ui_position_top_xlabel(ax, fig, op_tick_state)
                _ui_position_bottom_xlabel(ax, fig, op_tick_state)
                _ui_position_left_ylabel(ax, fig, op_tick_state)
                _ui_position_right_ylabel(ax, fig, op_tick_state)
                if ec_ax is not None:
                    _ui_position_top_xlabel(ec_ax, fig, ec_tick_state)
                    _ui_position_bottom_xlabel(ec_ax, fig, ec_tick_state)
                    try:
                        keep_yaxis_label_on_side(
                            ec_ax, 'right',
                            visible=bool(getattr(ec_ax, '_right_ylabel_on', True)),
                        )
                    except Exception:
                        pass
                    # EC right title is the actual ylabel (already on the right); never build a duplicate artist
                    if hasattr(ec_ax, '_right_ylabel_artist') and ec_ax._right_ylabel_artist is not None:
                        try:
                            ec_ax._right_ylabel_artist.set_visible(False)
                        except Exception:
                            pass
            except Exception:
                pass
            # Restore title offsets
            try:
                op_offsets = snap.get('op_title_offsets', {})
                if op_offsets:
                    restore_title_offsets(ax, op_offsets)
                    # Reposition titles to apply offsets
                    _ui_position_top_xlabel(ax, fig, op_tick_state)
                    _ui_position_bottom_xlabel(ax, fig, op_tick_state)
                    _ui_position_left_ylabel(ax, fig, op_tick_state)
                    _ui_position_right_ylabel(ax, fig, op_tick_state)
                ec_offsets = snap.get('ec_title_offsets')
                if ec_offsets and ec_ax is not None:
                    restore_title_offsets(ec_ax, ec_offsets)
                    # Reposition titles to apply offsets
                    _ui_position_top_xlabel(ec_ax, fig, ec_tick_state)
                    _ui_position_bottom_xlabel(ec_ax, fig, ec_tick_state)
                    try:
                        keep_yaxis_label_on_side(
                            ec_ax, 'right',
                            visible=bool(getattr(ec_ax, '_right_ylabel_on', True)),
                        )
                    except Exception:
                        pass
                    # EC right title is the actual ylabel (already on the right); never build a duplicate artist
                    if hasattr(ec_ax, '_right_ylabel_artist') and ec_ax._right_ylabel_artist is not None:
                        try:
                            ec_ax._right_ylabel_artist.set_visible(False)
                        except Exception:
                            pass
            except Exception:
                pass
        except Exception:
            pass
        # Restore tick lengths
        try:
            tick_lengths = snap.get('tick_lengths')
            if tick_lengths and isinstance(tick_lengths, dict):
                major = tick_lengths.get('major')
                minor = tick_lengths.get('minor')
                if major is not None:
                    ax.tick_params(axis='both', which='major', length=major)
                    if ec_ax is not None:
                        ec_ax.tick_params(axis='both', which='major', length=major)
                if minor is not None:
                    ax.tick_params(axis='both', which='minor', length=minor)
                    if ec_ax is not None:
                        ec_ax.tick_params(axis='both', which='minor', length=minor)
                fig._tick_lengths = tick_lengths
        except Exception:
            pass
        # Restore tick direction
        try:
            tick_dir = snap.get('tick_direction', 'out')
            ax.tick_params(axis='both', which='both', direction=tick_dir)
            if ec_ax is not None:
                ec_ax.tick_params(axis='both', which='both', direction=tick_dir)
            fig._tick_direction = tick_dir
        except Exception:
            pass
        # Restore tick spacing / minor locators (after WASD tick_params above)
        try:
            restore_axes_tick_locators(ax, snap.get('tick_spacing_op'), ('x', 'y'))
            if ec_ax is not None:
                restore_axes_tick_locators(ec_ax, snap.get('tick_spacing_ec'), ('x', 'y'))
        except Exception:
            pass
        maybe_reapply_dqdv_2d_contour(fig, ax, im, cbar)
        # Re-apply WASD minor locators after spacing restore (undo order)
        try:
            op_wasd = snap.get('op_wasd')
            ec_wasd = snap.get('ec_wasd')
            if op_wasd:
                apply_wasd_minor_ticks(
                    ax, op_wasd,
                    y_minor_mode='left' if ec_ax is not None else 'both',
                )
            if ec_wasd and ec_ax is not None:
                apply_wasd_minor_ticks(ec_ax, ec_wasd, y_minor_mode='right')
        except Exception:
            pass
        # Restore spine linewidths and tick widths (l command)
        try:
            op_sp = snap.get('op_spines', {})
            if op_sp:
                for name, spec in op_sp.items():
                    sp = ax.spines.get(name)
                    if sp is not None and spec is not None:
                        if isinstance(spec, dict):
                            if spec.get('linewidth') is not None:
                                sp.set_linewidth(float(spec['linewidth']))
                            if spec.get('color') is not None:
                                _ui_set_spine_side_color(
                                    ax,
                                    name,
                                    spec['color'],
                                    fig=fig,
                                    tick_state=getattr(ax, "_saved_tick_state", None),
                                )
                            if spec.get('visible') is not None:
                                sp.set_visible(bool(spec['visible']))
                        else:
                            sp.set_linewidth(float(spec))
            op_tw = snap.get('op_ticks', {})
            if op_tw:
                if op_tw.get('x_major') is not None:
                    ax.tick_params(axis='x', which='major', width=op_tw['x_major'])
                if op_tw.get('x_minor') is not None:
                    ax.tick_params(axis='x', which='minor', width=op_tw['x_minor'])
                if op_tw.get('y_major') is not None:
                    ax.tick_params(axis='y', which='major', width=op_tw['y_major'])
                if op_tw.get('y_minor') is not None:
                    ax.tick_params(axis='y', which='minor', width=op_tw['y_minor'])
        except Exception:
            pass
        try:
            if ec_ax is not None:
                ec_sp = snap.get('ec_spines', {})
                if ec_sp:
                    for name, spec in ec_sp.items():
                        sp = ec_ax.spines.get(name)
                        if sp is not None and spec is not None:
                            if isinstance(spec, dict):
                                if spec.get('linewidth') is not None:
                                    sp.set_linewidth(float(spec['linewidth']))
                                if spec.get('color') is not None:
                                    _ui_set_spine_side_color(
                                        ec_ax,
                                        name,
                                        spec['color'],
                                        fig=fig,
                                        tick_state=getattr(ec_ax, "_saved_tick_state", None),
                                    )
                                if spec.get('visible') is not None:
                                    sp.set_visible(bool(spec['visible']))
                            else:
                                sp.set_linewidth(float(spec))
                ec_tw = snap.get('ec_ticks', {})
                if ec_tw:
                    if ec_tw.get('x_major') is not None:
                        ec_ax.tick_params(axis='x', which='major', width=ec_tw['x_major'])
                    if ec_tw.get('x_minor') is not None:
                        ec_ax.tick_params(axis='x', which='minor', width=ec_tw['x_minor'])
                    if ec_tw.get('y_major') is not None:
                        ec_ax.tick_params(axis='y', which='major', width=ec_tw['y_major'])
                    if ec_tw.get('y_minor') is not None:
                        ec_ax.tick_params(axis='y', which='minor', width=ec_tw['y_minor'])
        except Exception:
            pass
        # Restore EC line style (el command)
        try:
            ec_line_style = snap.get('ec_line_style')
            if ec_line_style and ec_ax is not None:
                ln = getattr(ec_ax, '_ec_line', None)
                if ln is None and ec_ax.lines:
                    try:
                        ln = ec_ax.lines[0]
                    except Exception:
                        ln = None
                if ln is not None:
                    if ec_line_style.get('color') is not None:
                        ln.set_color(ec_line_style['color'])
                    if ec_line_style.get('linewidth') is not None:
                        ln.set_linewidth(float(ec_line_style['linewidth']))
                    if ec_line_style.get('linestyle') is not None:
                        ln.set_linestyle(ec_line_style['linestyle'])
                        clear_dash_pattern(ln)
                    if ec_line_style.get('dash_pattern'):
                        restore_dash_pattern(ln, ec_line_style['dash_pattern'])
                    if 'alpha' in ec_line_style:
                        try:
                            ln.set_alpha(ec_line_style.get('alpha'))
                        except Exception:
                            pass
                    if ec_line_style.get('marker') is not None:
                        try:
                            ln.set_marker(ec_line_style['marker'])
                            if ec_line_style.get('markersize') is not None:
                                ln.set_markersize(float(ec_line_style['markersize']))
                            if ec_line_style['marker'] not in ('None', '', ' '):
                                color = ln.get_color()
                                ln.set_markerfacecolor(color)
                                ln.set_markeredgecolor(color)
                        except Exception:
                            pass
        except Exception:
            pass
        # Restore EC grid
        try:
            ec_grid_snap = snap.get('ec_grid')
            if ec_grid_snap and ec_ax is not None:
                g = dict(ec_grid_snap)
                g.setdefault('visible', False)
                g.setdefault('alpha', 0.3)
                g.setdefault('linestyle', '--')
                g.setdefault('color', '0.6')
                g.setdefault('which', 'major')
                ec_ax._ec_grid = g
                ec_ax.grid(
                    g['visible'],
                    which=g['which'],
                    axis='both',
                    alpha=float(g['alpha']),
                    color=str(g['color']),
                    linestyle=str(g['linestyle']),
                )
        except Exception:
            pass
        # Restore visibility states
        try:
            cb_vis = snap.get('cb_visible')
            if cb_vis is not None and cbar is not None:
                cbar.ax.set_visible(bool(cb_vis))
        except Exception:
            pass
        try:
            ec_vis = snap.get('ec_visible')
            if ec_vis is not None and ec_ax is not None:
                ec_ax.set_visible(bool(ec_vis))
        except Exception:
            pass
        # Restore operando CIF tick state (including empty = clear after add)
        try:
            cif_snap = snap.get('operando_cif')
            axis_mode = snap.get('operando_axis_mode') or getattr(fig, '_operando_axis_mode', None)
            if axis_mode is None:
                try:
                    from .axis_units import ensure_operando_axis_mode
                    axis_mode = ensure_operando_axis_mode(fig, ax)
                except Exception:
                    axis_mode = None
            if axis_mode is None:
                axis_mode = ""  # titles only; never invent Q
            wl = snap['operando_wl'] if 'operando_wl' in snap else getattr(fig, '_operando_wl', None)
            if not cif_snap or not cif_snap.get('tick_series'):
                ax._operando_cif_tick_series = []
                ax._operando_cif_hkl_label_map = {}
                fig._operando_cif_y_positions = []
                fig._operando_cif_title_visible = []
                fig._operando_cif_set_visible = []
                _draw_operando_cif_ticks(
                    ax, fig, [], {}, axis_mode=axis_mode, wl=wl,
                    show_hkl=False, show_titles=False, placement='below', y_positions=[],
                )
            else:
                fig._operando_cif_show_hkl = bool(cif_snap.get('show_hkl', False))
                fig._operando_cif_show_titles = bool(cif_snap.get('show_titles', True))
                fig._operando_cif_placement = str(cif_snap.get('placement', 'below'))
                y_pos = cif_snap.get('y_positions', [])
                fig._operando_cif_y_positions = list(y_pos) if y_pos else []
                fig._operando_cif_colormap = cif_snap.get('colormap')
                fig._operando_cif_highlight = bool(cif_snap.get('highlight', False))
                fig._operando_cif_title_font = dict(cif_snap.get('title_font') or {})
                fig._operando_cif_title_visible = list(cif_snap.get('title_visible') or [])
                fig._operando_cif_set_visible = list(cif_snap.get('set_visible') or [])
                tick_series_restore = cif_snap.get('tick_series')
                ax._operando_cif_tick_series = list(tick_series_restore or [])
                if cif_snap.get('hkl_label_map') is not None:
                    ax._operando_cif_hkl_label_map = dict(cif_snap.get('hkl_label_map') or {})
                cif_series = getattr(ax, '_operando_cif_tick_series', [])
                cif_hkl_map = getattr(ax, '_operando_cif_hkl_label_map', {})
                ax_pos = ax.get_position()
                y_base = ax_pos.ymin - 0.02 if fig._operando_cif_placement == 'below' else ax_pos.ymax + 0.02
                dy = -0.025 if fig._operando_cif_placement == 'below' else 0.025
                while len(fig._operando_cif_y_positions) < len(cif_series):
                    fig._operando_cif_y_positions.append(y_base + len(fig._operando_cif_y_positions) * dy)
                _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl,
                                         show_hkl=fig._operando_cif_show_hkl, show_titles=fig._operando_cif_show_titles,
                                         placement=fig._operando_cif_placement, y_positions=fig._operando_cif_y_positions)
        except Exception:
            pass
        # Restore label pads (critical for maintaining title positions)
        try:
            op_pads = snap.get('op_labelpads', {})
            if op_pads:
                if op_pads.get('x') is not None:
                    ax.xaxis.labelpad = op_pads['x']
                if op_pads.get('y') is not None:
                    ax.yaxis.labelpad = op_pads['y']
        except Exception:
            pass
        try:
            ec_pads = snap.get('ec_labelpads', {})
            if ec_pads and ec_ax is not None:
                if ec_pads.get('x') is not None:
                    ec_ax.xaxis.labelpad = ec_pads['x']
                if ec_pads.get('y') is not None:
                    ec_ax.yaxis.labelpad = ec_pads['y']
        except Exception:
            pass
        try:
            d2 = snap.get('dqdv_2d')
            if d2 and isinstance(d2, dict) and getattr(fig, '_is_dqdv_2d_contour', False):
                try:
                    fig._dqdv_2d_v_lo = float(d2['v_lo'])
                    fig._dqdv_2d_v_hi = float(d2['v_hi'])
                    fig._dqdv_2d_row_labels = [str(s) for s in (d2.get('row_labels') or [])]
                    if d2.get('zlabel') is not None:
                        fig._dqdv_2d_zlabel = str(d2['zlabel'])
                except Exception:
                    pass
                try:
                    from ..electrochem.dqdv_2d import update_dqdv_2d_potential_window
                    update_dqdv_2d_potential_window(
                        fig, ax, im,
                        float(fig._dqdv_2d_v_lo), float(fig._dqdv_2d_v_hi),
                    )
                except Exception:
                    pass
            maybe_reapply_dqdv_2d_contour(fig, ax, im, cbar)
            if getattr(fig, '_is_dqdv_2d_contour', False):
                restore_dqdv_2d_operando_labels(ax, snap.get('op_labels', {}))
        except Exception:
            pass
        try:
            refresh_font_extras_on_artists(fig, operando_font_artists())
        except Exception:
            pass
        try:
            axis_entries = [(ax, getattr(ax, "_saved_tick_state", None))]
            if ec_ax is not None:
                axis_entries.append((ec_ax, getattr(ec_ax, "_saved_tick_state", None)))
            finalize_spine_colors_for_axes(fig, axis_entries)
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

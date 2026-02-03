"""Session helpers for batplot interactive mode.

This module provides functions to persist and restore interactive plotting
state for both the general XY plots and operando+EC combined plots.
"""

from __future__ import annotations

import pickle
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import os

import matplotlib.pyplot as plt
import numpy as np

from .utils import _confirm_overwrite


def _current_tick_width(axis_obj, which: str):
    """Return the configured tick width for the given X/Y axis."""
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
        pass
    return None


def _axis_label_text(ax, attr_name: str, getter):
    try:
        stored = getattr(ax, attr_name)
        if isinstance(stored, str) and stored:
            return stored
    except Exception:
        pass
    try:
        return getter() or ''
    except Exception:
        return ''


def _apply_axes_bbox(ax, bbox) -> bool:
    """Apply stored axes bbox (left/right/bottom/top fractions)."""
    if not isinstance(bbox, dict):
        return False
    required = ('left', 'right', 'bottom', 'top')
    if not all(k in bbox for k in required):
        return False
    try:
        left = float(bbox['left'])
        right = float(bbox['right'])
        bottom = float(bbox['bottom'])
        top = float(bbox['top'])
        width = right - left
        height = top - bottom
        if width <= 0 or height <= 0:
            return False
        ax.set_position([left, bottom, width, height])
        return True
    except Exception:
        return False


def _get_primary_axis_label(ax, axis: str) -> str:
    """Get primary axis label text, falling back to stored value when hidden."""
    if axis == 'x':
        label = ax.xaxis.label
        stored_attr = '_stored_xlabel'
    else:
        label = ax.yaxis.label
        stored_attr = '_stored_ylabel'
    text = ''
    try:
        text = label.get_text() or ''
    except Exception:
        text = ''
    if not text and hasattr(ax, stored_attr):
        try:
            stored = getattr(ax, stored_attr)
            if stored:
                text = stored
        except Exception:
            text = ''
    return text or ''


def _get_duplicate_axis_label(ax, which: str, fallback: str = '') -> str:
    """Get duplicate axis label (top/right) text."""
    if which == 'top':
        artist_attr = '_top_xlabel_artist'
        override_attr = '_top_xlabel_text_override'
    else:
        artist_attr = '_right_ylabel_artist'
        override_attr = '_right_ylabel_text_override'
    if hasattr(ax, override_attr):
        try:
            override_val = getattr(ax, override_attr)
            if override_val:
                return override_val
        except Exception:
            pass
    artist = getattr(ax, artist_attr, None)
    if artist is not None and hasattr(artist, 'get_text'):
        try:
            txt = artist.get_text()
            if txt:
                return txt
        except Exception:
            pass
    return fallback or ''


# ------------------------- Generic XY session (existing) -------------------------


def dump_session(
    filename: str,
    *,
    fig,
    ax,
    x_data_list: Sequence[np.ndarray],
    y_data_list: Sequence[np.ndarray],
    orig_y: Sequence[np.ndarray],
    offsets_list: Sequence[float],
    labels: Sequence[str],
    delta: float,
    args,
    tick_state: Dict[str, bool],
    cif_tick_series: Iterable[Tuple[str, str, List[float], float | None, float, Any]] | None = None,
    cif_hkl_map: Dict[str, List[Tuple[float, int, int, int]]] | None = None,
    cif_hkl_label_map: Dict[str, Dict[float, str]] | None = None,
    show_cif_hkl: bool | None = None,
    show_cif_titles: bool | None = None,
    skip_confirm: bool = False,
) -> None:
    """Serialize the current interactive session to a pickle file.

    Parameters mirror the state captured in the original inline helper.
    skip_confirm: If True, skip overwrite confirmation (already confirmed by caller).
    """

    # Infer axis mode string
    if getattr(args, 'xaxis', None) in ("Q", "2theta", "r", "energy", "k", "rft"):
        axis_mode_session = args.xaxis
    else:
        # Best-effort inference from labels/units already set on axes
        xl = (ax.get_xlabel() or "").lower()
        if "q (" in xl:
            axis_mode_session = "Q"
        elif "$2\\theta$" in xl or "2" in xl and "theta" in xl:
            axis_mode_session = "2theta"
        elif xl.startswith("r ") or xl.startswith("r ("):
            axis_mode_session = "r"
        elif "energy" in xl:
            axis_mode_session = "energy"
        elif xl.startswith("k ") or xl.startswith("k ("):
            axis_mode_session = "k"
        elif "radial" in xl:
            axis_mode_session = "rft"
        else:
            axis_mode_session = "unknown"

    label_layout = 'stack' if getattr(args, 'stack', False) else 'block'

    # Axes frame size (in inches) to complement the canvas size
    bbox = ax.get_position()
    fw, fh = fig.get_size_inches()
    frame_w_in = bbox.width * fw
    frame_h_in = bbox.height * fh

    # Save spines state
    spines_state = {
        name: {
            'linewidth': sp.get_linewidth(),
            'color': sp.get_edgecolor(),
            'visible': sp.get_visible(),
        } for name, sp in ax.spines.items()
    }

    # Helper to capture a representative tick line width
    def _tick_width(axis, which: str):
        return _current_tick_width(axis, which)

    tick_widths = {
        'x_major': _tick_width(ax.xaxis, 'major'),
        'x_minor': _tick_width(ax.xaxis, 'minor'),
        'y_major': _tick_width(ax.yaxis, 'major'),
        'y_minor': _tick_width(ax.yaxis, 'minor'),
    }
    
    # Helper to get tick length
    def _tick_length(axis, which):
        try:
            ticks = axis.get_major_ticks() if which=='major' else axis.get_minor_ticks()
            for t in ticks:
                ln = t.tick1line
                if ln.get_visible():
                    return ln.get_markersize()
        except Exception:
            return None
        return None
    
    tick_lengths = {
        'x_major': _tick_length(ax.xaxis, 'major'),
        'x_minor': _tick_length(ax.xaxis, 'minor'),
        'y_major': _tick_length(ax.yaxis, 'major'),
        'y_minor': _tick_length(ax.yaxis, 'minor'),
    }

    sp = fig.subplotpars
    subplot_margins = {
        'left': float(sp.left),
        'right': float(sp.right),
        'bottom': float(sp.bottom),
        'top': float(sp.top),
    }
    
    # Helper to capture WASD state
    def _capture_wasd_state(axis):
        ts = getattr(axis, '_saved_tick_state', {})
        wasd = {}
        for side in ('top', 'bottom', 'left', 'right'):
            sp_obj = axis.spines.get(side)
            prefix = {'top': 't', 'bottom': 'b', 'left': 'l', 'right': 'r'}[side]
            # Consistent tick/title state logic for all sides
            if side == 'left':
                title_state = bool(axis.yaxis.label.get_visible())
            elif side == 'bottom':
                title_state = bool(axis.xaxis.label.get_visible())
            elif side == 'top':
                title_state = bool(getattr(axis, '_top_xlabel_on', False))
            elif side == 'right':
                title_state = bool(getattr(axis, '_right_ylabel_on', False))
            else:
                title_state = False
            wasd[side] = {
                'spine': bool(sp_obj.get_visible() if sp_obj else False),
                'ticks': bool(ts.get(f'{prefix}_ticks', ts.get({'top':'tx','bottom':'bx','left':'ly','right':'ry'}[side], side=='bottom' or side=='left'))),
                'minor': bool(ts.get(f'm{prefix}x' if side in ('top','bottom') else f'm{prefix}y', False)),
                'labels': bool(ts.get(f'{prefix}_labels', ts.get({'top':'tx','bottom':'bx','left':'ly','right':'ry'}[side], side=='bottom' or side=='left'))),
                'title': title_state,
            }
        return wasd
    
    wasd_state = _capture_wasd_state(ax)

    try:
        sess = {
            'version': 3,
            'x_data': [np.array(a) for a in x_data_list],
            'y_data': [np.array(a) for a in y_data_list],
            'orig_y': [np.array(a) for a in orig_y],
            'offsets': list(offsets_list),
            'labels': list(labels),
            'line_styles': [
                {
                    'color': ln.get_color(),
                    'linewidth': ln.get_linewidth(),
                    'linestyle': ln.get_linestyle(),
                    'alpha': ln.get_alpha(),
                    'marker': ln.get_marker(),
                    'markersize': ln.get_markersize(),
                    'markerfacecolor': ln.get_markerfacecolor(),
                    'markeredgecolor': ln.get_markeredgecolor(),
                } for ln in ax.lines
            ],
            'delta': float(delta),
            'label_layout': label_layout,
            'axis_mode': axis_mode_session,
            'axis': {
                'xlabel': ax.get_xlabel(),
                'ylabel': ax.get_ylabel(),
                'xlim': ax.get_xlim(),
                'ylim': ax.get_ylim(),
                'norm_xlim': getattr(ax, '_norm_xlim', None),  # x-range used for normalization
                'norm_ylim': getattr(ax, '_norm_ylim', None),  # y-range used for normalization
            },
            'figure': {
                'size': tuple(map(float, fig.get_size_inches())),
                'dpi': int(fig.dpi),
                'frame_size': (frame_w_in, frame_h_in),
                'axes_bbox': {
                    'left': float(bbox.x0),
                    'bottom': float(bbox.y0),
                    'right': float(bbox.x0 + bbox.width),
                    'top': float(bbox.y0 + bbox.height),
                },
                'subplot_margins': subplot_margins,
                'spines': spines_state,
            },
            'wasd_state': wasd_state,
            'tick_state': dict(tick_state),
            'tick_widths': tick_widths,
            'tick_lengths': tick_lengths,
            'font': {
                'size': plt.rcParams.get('font.size'),
                'chain': list(plt.rcParams.get('font.sans-serif', [])),
            },
            'args_subset': {
                'stack': bool(getattr(args, 'stack', False)),
                'autoscale': bool(getattr(args, 'autoscale', False)),
                'norm': bool(getattr(args, 'norm', False)),
            },
            'cif_tick_series': [tuple(t) for t in (cif_tick_series or [])],
            'cif_hkl_map': {k: [tuple(v) for v in val] for k, val in (cif_hkl_map or {}).items()},
            'cif_hkl_label_map': {k: dict(v) for k, v in (cif_hkl_label_map or {}).items()},
            'show_cif_hkl': bool(show_cif_hkl),
            'show_cif_titles': bool(show_cif_titles) if show_cif_titles is not None else True,
        }
        sess['axis_titles'] = {
            'top_x': bool(getattr(ax, '_top_xlabel_on', False)),
            'right_y': bool(getattr(ax, '_right_ylabel_on', False)),
            'has_bottom_x': bool(ax.xaxis.label.get_visible()),
            'has_left_y': bool(ax.yaxis.label.get_visible()),
        }
        sess['axis_title_texts'] = {
            'bottom_x': _get_primary_axis_label(ax, 'x'),
            'left_y': _get_primary_axis_label(ax, 'y'),
            'top_x': _get_duplicate_axis_label(ax, 'top', _get_primary_axis_label(ax, 'x')),
            'right_y': _get_duplicate_axis_label(ax, 'right', _get_primary_axis_label(ax, 'y')),
        }
        # Save curve names visibility
        sess['curve_names_visible'] = bool(getattr(fig, '_curve_names_visible', True))
        # Save stack label position preference
        sess['stack_label_at_bottom'] = bool(getattr(fig, '_stack_label_at_bottom', False))
        # Save grid state
        sess['grid'] = ax.xaxis._gridOnMajor if hasattr(ax.xaxis, '_gridOnMajor') else False
        if skip_confirm:
            target = filename
        else:
            target = _confirm_overwrite(filename)
            if not target:
                print("Session save canceled.")
                return
        with open(target, 'wb') as f:
            pickle.dump(sess, f)
        print(f"Session saved to {target}")
    except Exception as e:  # pragma: no cover - defensive path
        print(f"Error saving session: {e}")

# --------------------- Operando + EC combined session helpers --------------------

def dump_operando_session(
    filename: str,
    *,
    fig,
    ax,      # operando axes
    im,      # AxesImage for operando
    cbar,    # Colorbar object
    ec_ax=None,
    skip_confirm: bool = False,
) -> None:
    """Serialize the current operando+EC interactive session to a pickle file.

    Captures enough state to reconstruct the figure layout, operando image,
    colorbar, and optional EC panel including ions-mode formatting.
    
    Args:
        skip_confirm: If True, skip overwrite confirmation (already handled by caller).
    """
    try:
        # Figure & inches geometry
        fig_w, fig_h = map(float, fig.get_size_inches())
        dpi = int(fig.dpi)
        # Layout in inches (group-centered on restore)
        ax_x0, ax_y0, ax_wf, ax_hf = ax.get_position().bounds
        cb_x0, cb_y0, cb_wf, cb_hf = cbar.ax.get_position().bounds
        if ec_ax is not None:
            ec_x0, ec_y0, ec_wf, ec_hf = ec_ax.get_position().bounds
        else:
            ec_x0 = ec_y0 = ec_wf = ec_hf = 0.0
        # Prefer using fixed attributes if they exist (more reliable than calculating from positions)
        cb_w_in = getattr(cbar.ax, '_fixed_cb_w_in', cb_wf * fig_w)
        cb_gap_in = getattr(cbar.ax, '_fixed_cb_gap_in', (ax_x0 - (cb_x0 + cb_wf)) * fig_w)
        ax_w_in = getattr(ax, '_fixed_ax_w_in', ax_wf * fig_w)
        ax_h_in = getattr(ax, '_fixed_ax_h_in', ax_hf * fig_h)
        if ec_ax is not None:
            ec_gap_in = getattr(ec_ax, '_fixed_ec_gap_in', (ec_x0 - (ax_x0 + ax_wf)) * fig_w)
            ec_w_in = getattr(ec_ax, '_fixed_ec_w_in', ec_wf * fig_w)
        else:
            ec_gap_in = 0.0
            ec_w_in = 0.0

        # Operando image state
        import numpy as _np
        arr = im.get_array()
        # Use masked arrays to preserve NaNs if present
        data = _np.array(arr)  # preserves mask where possible
        extent = tuple(map(float, im.get_extent())) if hasattr(im, 'get_extent') else None
        cmap_name = getattr(im.get_cmap(), 'name', None)
        clim = tuple(map(float, im.get_clim())) if hasattr(im, 'get_clim') else None
        origin = getattr(im, 'origin', 'upper')
        interpolation = getattr(im, 'get_interpolation', lambda: None)() or 'nearest'

        # Labels and limits for operando
        # Capture label text and padding (labelpad)
        try:
            _xlp = float(getattr(ax.xaxis, 'labelpad', 0.0))
        except Exception:
            _xlp = 0.0
        try:
            _ylp = float(getattr(ax.yaxis, 'labelpad', 0.0))
        except Exception:
            _ylp = 0.0
        op_labels = {
            'xlabel': ax.get_xlabel(),
            'ylabel': ax.get_ylabel(),
            'xlim': tuple(map(float, ax.get_xlim())),
            'ylim': tuple(map(float, ax.get_ylim())),
            'x_labelpad': _xlp,
            'y_labelpad': _ylp,
        }
        op_custom = getattr(ax, '_custom_labels', {'x': None, 'y': None})

        # Colorbar label (Colorbar lacks get_label in some versions; use its axes ylabel)
        try:
            cb_label = cbar.ax.get_ylabel()
        except Exception:
            cb_label = ''
        # Capture color scale limits (clim) through the mappable
        try:
            cb_clim = tuple(map(float, im.get_clim()))
        except Exception:
            cb_clim = None

        # Helper to capture WASD state for an axis
        def _capture_wasd_state(axis):
            ts = getattr(axis, '_saved_tick_state', {})
            wasd = {}
            for side in ('top', 'bottom', 'left', 'right'):
                sp = axis.spines.get(side)
                prefix = {'top': 't', 'bottom': 'b', 'left': 'l', 'right': 'r'}[side]
                # For 'left' side ylabel: check if it's currently visible (has text)
                # If hidden but has stored text, the title state should be False (hidden)
                if side == 'left':
                    ylabel_text = axis.get_ylabel()
                    title_state = bool(ylabel_text)  # True only if currently visible with text
                elif side == 'bottom':
                    title_state = bool(axis.get_xlabel())
                elif side == 'top':
                    title_state = bool(getattr(axis, '_top_xlabel_on', False))
                elif side == 'right':
                    title_state = bool(getattr(axis, '_right_ylabel_on', False))
                else:
                    title_state = False
                
                wasd[side] = {
                    'spine': bool(sp.get_visible() if sp else False),
                    'ticks': bool(ts.get(f'{prefix}_ticks', ts.get({'top':'tx','bottom':'bx','left':'ly','right':'ry'}[side], side=='bottom' or side=='left'))),
                    'minor': bool(ts.get(f'm{prefix}x' if side in ('top','bottom') else f'm{prefix}y', False)),
                    'labels': bool(ts.get(f'{prefix}_labels', ts.get({'top':'tx','bottom':'bx','left':'ly','right':'ry'}[side], side=='bottom' or side=='left'))),
                    'title': title_state,
                }
            return wasd
        
        # Helper to capture spine and tick widths
        def _capture_spine_tick_widths(axis):
            spines = {}
            for name in ('bottom', 'top', 'left', 'right'):
                sp = axis.spines.get(name)
                if sp:
                    spines[name] = {
                        'linewidth': float(sp.get_linewidth()),
                        'visible': bool(sp.get_visible()),
                        'color': sp.get_edgecolor()
                    }
            
            ticks = {
                'x_major': _current_tick_width(axis.xaxis, 'major'),
                'x_minor': _current_tick_width(axis.xaxis, 'minor'),
                'y_major': _current_tick_width(axis.yaxis, 'major'),
                'y_minor': _current_tick_width(axis.yaxis, 'minor'),
            }
            return spines, ticks
        
        # Capture operando WASD state, spines, and tick widths
        op_wasd_state = _capture_wasd_state(ax)
        op_spines, op_ticks = _capture_spine_tick_widths(ax)

        # EC panel (optional)
        ec_state = None
        if ec_ax is not None:
            time_h = _np.asarray(getattr(ec_ax, '_ec_time_h', []), float)
            volt_v = _np.asarray(getattr(ec_ax, '_ec_voltage_v', []), float)
            curr_mA = _np.asarray(getattr(ec_ax, '_ec_current_mA', []), float)
            mode = getattr(ec_ax, '_ec_y_mode', 'time')
            xlim = tuple(map(float, ec_ax.get_xlim()))
            ylim = tuple(map(float, ec_ax.get_ylim()))
            # Persist prior time-mode ylim and any ions array/params
            saved_time_ylim = getattr(ec_ax, '_saved_time_ylim', None)
            ions_abs = _np.asarray(getattr(ec_ax, '_ions_abs', []), float) if getattr(ec_ax, '_ions_abs', None) is not None else None
            ion_params = getattr(ec_ax, '_ion_params', None)
            custom = getattr(ec_ax, '_custom_labels', {'x': None, 'y_time': None, 'y_ions': None})
            # EC line style (if present)
            ln = getattr(ec_ax, '_ec_line', None)
            if ln is None and getattr(ec_ax, 'lines', None):
                try:
                    ln = ec_ax.lines[0]
                except Exception:
                    ln = None
            line_style = None
            if ln is not None:
                try:
                    line_style = {
                        'color': ln.get_color(),
                        'linewidth': float(ln.get_linewidth() or 1.0),
                        'linestyle': ln.get_linestyle() or '-',
                        'alpha': ln.get_alpha(),
                    }
                except Exception:
                    line_style = None
            
            # Capture EC WASD state, spines, and tick widths
            ec_wasd_state = _capture_wasd_state(ec_ax)
            ec_spines, ec_ticks = _capture_spine_tick_widths(ec_ax)
            
            ec_state = {
                'time_h': time_h,
                'volt_v': volt_v,
                'curr_mA': curr_mA,
                'mode': mode,
                'xlim': xlim,
                'ylim': ylim,
                'saved_time_ylim': tuple(map(float, saved_time_ylim)) if isinstance(saved_time_ylim, (list, tuple)) else None,
                'ions_abs': ions_abs,
                'ion_params': ion_params,
                'custom_labels': custom,
                'line_style': line_style,
                'wasd_state': ec_wasd_state,
                'spines': ec_spines,
                'ticks': {'widths': ec_ticks},
                'stored_ylabel': getattr(ec_ax, '_stored_ylabel', None),  # Save hidden ylabel text
                'visible': bool(ec_ax.get_visible()),
            }

        # Get horizontal offsets if they exist
        cb_h_offset = getattr(cbar.ax, '_cb_h_offset_in', 0.0)
        ec_h_offset = getattr(ec_ax, '_ec_h_offset_in', 0.0) if ec_ax is not None else None
        
        sess = {
            'kind': 'operando_ec',
            'version': 2,
            'figure': {'size': (fig_w, fig_h), 'dpi': dpi},
            'layout_inches': {
                'cb_w_in': cb_w_in,
                'cb_gap_in': cb_gap_in,
                'ax_w_in': ax_w_in,
                'ax_h_in': ax_h_in,
                'ec_gap_in': ec_gap_in,
                'ec_w_in': ec_w_in,
                'cb_h_offset': float(cb_h_offset),
                'ec_h_offset': float(ec_h_offset) if ec_h_offset is not None else None,
            },
            'operando': {
                'array': data,
                'extent': extent,
                'cmap': cmap_name,
                'clim': clim,
                'origin': origin,
                'interpolation': interpolation,
                'labels': op_labels,
                'custom_labels': op_custom,
                'wasd_state': op_wasd_state,
                'spines': op_spines,
                'ticks': {'widths': op_ticks},
                'stored_ylabel': getattr(ax, '_stored_ylabel', None),  # Save hidden ylabel text
            },
            'colorbar': {
                'label': cb_label,
                'clim': cb_clim,
                'visible': bool(cbar.ax.get_visible()),
                'label_mode': getattr(fig, '_colorbar_label_mode', 'normal'),
            },
            'ec': ec_state,
            'font': {
                'size': plt.rcParams.get('font.size'),
                'chain': list(plt.rcParams.get('font.sans-serif', [])),
            },
        }
        if skip_confirm:
            target = filename
        else:
            target = _confirm_overwrite(filename)
            if not target:
                print("Session save canceled.")
                return
        with open(target, 'wb') as f:
            pickle.dump(sess, f)
        print(f"Operando session saved to {target}")
    except Exception as e:  # pragma: no cover - defensive path
        print(f"Error saving operando session: {e}")


def load_operando_session(filename: str):
    """Load an operando+EC session (.pkl) and reconstruct figure and axes.

    Returns: (fig, ax, im, cbar, ec_ax)
    """
    try:
        with open(filename, 'rb') as f:
            sess = pickle.load(f)
    except Exception as e:
        print(f"Failed to load session: {e}")
        return None

    if not isinstance(sess, dict) or sess.get('kind') != 'operando_ec':
        print("Not an operando+EC session file.")
        return None

    # Use standard DPI of 100 instead of saved DPI to avoid display-dependent issues
    # (Retina displays, Windows scaling, etc. can cause saved DPI to differ)
    fig = plt.figure(figsize=tuple(sess['figure']['size']), dpi=100)
    # Disable automatic layout adjustments to preserve saved geometry
    try:
        fig.set_layout_engine('none')
    except Exception:
        try:
            fig.set_tight_layout(False)
        except Exception:
            pass
    W, H = map(float, fig.get_size_inches())
    li = sess['layout_inches']
    cb_wf = max(0.0, float(li['cb_w_in']) / W)
    cb_gap_f = max(0.0, float(li['cb_gap_in']) / W)
    ax_wf = max(0.0, float(li['ax_w_in']) / W)
    ax_hf = max(0.0, float(li['ax_h_in']) / H)
    ec_wf = max(0.0, float(li.get('ec_w_in', 0.0)) / W)
    ec_gap_f = max(0.0, float(li.get('ec_gap_in', 0.0)) / W)

    total_wf = cb_wf + cb_gap_f + ax_wf + ec_gap_f + ec_wf
    group_left = 0.5 - total_wf / 2.0
    y0 = 0.5 - ax_hf / 2.0

    # Axes positions
    cb_x0 = group_left
    ax_x0 = cb_x0 + cb_wf + cb_gap_f
    ec_x0 = ax_x0 + ax_wf + ec_gap_f if ec_wf > 0 else None

    # Create axes
    ax = fig.add_axes([ax_x0, y0, ax_wf, ax_hf])
    cbar_ax = fig.add_axes([cb_x0, y0, cb_wf, ax_hf])

    # Recreate operando image
    from numpy import ma as _ma
    op = sess['operando']
    arr = _ma.masked_invalid(op['array'])
    extent = tuple(op['extent']) if op['extent'] is not None else None
    im = ax.imshow(arr, aspect='auto', origin=op.get('origin', 'upper'), extent=extent,
                   cmap=op.get('cmap') or 'viridis', interpolation=op.get('interpolation', 'nearest'))
    if op.get('clim'):
        try:
            im.set_clim(*op['clim'])
        except Exception:
            pass
    
    # Apply operando WASD state if version 2+ (BEFORE restoring labels!)
    version = sess.get('version', 1)
    if version >= 2:
        op_wasd = op.get('wasd_state')
        if op_wasd and isinstance(op_wasd, dict):
            from matplotlib.ticker import AutoMinorLocator, NullFormatter
            try:
                # Apply spines
                for side in ('top', 'bottom', 'left', 'right'):
                    if side in op_wasd and 'spine' in op_wasd[side]:
                        sp = ax.spines.get(side)
                        if sp:
                            sp.set_visible(bool(op_wasd[side]['spine']))
                # Apply ticks
                ax.tick_params(axis='x', 
                              top=bool(op_wasd.get('top', {}).get('ticks', False)),
                              bottom=bool(op_wasd.get('bottom', {}).get('ticks', True)),
                              labeltop=bool(op_wasd.get('top', {}).get('labels', False)),
                              labelbottom=bool(op_wasd.get('bottom', {}).get('labels', True)))
                ax.tick_params(axis='y',
                              left=bool(op_wasd.get('left', {}).get('ticks', True)),
                              right=bool(op_wasd.get('right', {}).get('ticks', False)),
                              labelleft=bool(op_wasd.get('left', {}).get('labels', True)),
                              labelright=bool(op_wasd.get('right', {}).get('labels', False)))
                # Apply minor ticks
                if op_wasd.get('top', {}).get('minor') or op_wasd.get('bottom', {}).get('minor'):
                    ax.xaxis.set_minor_locator(AutoMinorLocator())
                    ax.xaxis.set_minor_formatter(NullFormatter())
                ax.tick_params(axis='x', which='minor',
                              top=bool(op_wasd.get('top', {}).get('minor', False)),
                              bottom=bool(op_wasd.get('bottom', {}).get('minor', False)))
                if op_wasd.get('left', {}).get('minor') or op_wasd.get('right', {}).get('minor'):
                    ax.yaxis.set_minor_locator(AutoMinorLocator())
                    ax.yaxis.set_minor_formatter(NullFormatter())
                ax.tick_params(axis='y', which='minor',
                              left=bool(op_wasd.get('left', {}).get('minor', False)),
                              right=bool(op_wasd.get('right', {}).get('minor', False)))
                # Store WASD state
                op_ts = {}
                for side_key, prefix in [('top', 't'), ('bottom', 'b'), ('left', 'l'), ('right', 'r')]:
                    s = op_wasd.get(side_key, {})
                    op_ts[f'{prefix}_ticks'] = bool(s.get('ticks', False))
                    op_ts[f'{prefix}_labels'] = bool(s.get('labels', False))
                    op_ts[f'm{prefix}x' if prefix in 'tb' else f'm{prefix}y'] = bool(s.get('minor', False))
                ax._saved_tick_state = op_ts
                # Apply title flags (must be set before restoring labels below)
                ax._top_xlabel_on = bool(op_wasd.get('top', {}).get('title', False))
                ax._right_ylabel_on = bool(op_wasd.get('right', {}).get('title', False))
            except Exception as e:
                print(f"Warning: Could not apply operando WASD state: {e}")
    else:
        # For version 1 pkl files, assume default visibility
        op_wasd = None
    
    # Restore labels and labelpad (respecting WASD title state)
    # Bottom xlabel: restore if title is True (default) or if no WASD state
    bottom_title_on = op_wasd.get('bottom', {}).get('title', True) if op_wasd else True
    if bottom_title_on:
        ax.set_xlabel(op['labels'].get('xlabel') or '')
        try:
            lp = op['labels'].get('x_labelpad')
            if lp is not None:
                ax.set_xlabel(ax.get_xlabel(), labelpad=float(lp))
        except Exception:
            pass
    else:
        ax.set_xlabel('')  # Hidden by user via s5
    
    # Left ylabel: restore if title is True (default) or if no WASD state
    left_title_on = op_wasd.get('left', {}).get('title', True) if op_wasd else True
    if left_title_on:
        ax.set_ylabel(op['labels'].get('ylabel') or 'Scan index')
        try:
            lp = op['labels'].get('y_labelpad')
            if lp is not None:
                ax.set_ylabel(ax.get_ylabel(), labelpad=float(lp))
        except Exception:
            pass
    else:
        ax.set_ylabel('')  # Hidden by user via a5
    
    try:
        ax.set_xlim(*op['labels']['xlim'])
        ax.set_ylim(*op['labels']['ylim'])
    except Exception:
        pass
    # Persist custom labels
    setattr(ax, '_custom_labels', dict(op.get('custom_labels', {'x': None, 'y': None})))
    
    # Restore stored ylabel if present (for cases where ylabel was hidden with a5)
    stored_ylabel = op.get('stored_ylabel')
    if stored_ylabel is not None:
        setattr(ax, '_stored_ylabel', stored_ylabel)
        
        # Apply operando spines
        op_spines = op.get('spines', {})
        if op_spines:
            try:
                for name, props in op_spines.items():
                    sp = ax.spines.get(name)
                    if not sp:
                        continue
                    if 'linewidth' in props and props['linewidth'] is not None:
                        try:
                            sp.set_linewidth(float(props['linewidth']))
                        except Exception:
                            pass
                    if 'visible' in props and props['visible'] is not None:
                        try:
                            sp.set_visible(bool(props['visible']))
                        except Exception:
                            pass
                    if 'color' in props and props['color'] is not None:
                        try:
                            sp.set_edgecolor(props['color'])
                            if name in ('top', 'bottom'):
                                ax.tick_params(axis='x', which='both', colors=props['color'])
                                ax.xaxis.label.set_color(props['color'])
                            else:
                                ax.tick_params(axis='y', which='both', colors=props['color'])
                                ax.yaxis.label.set_color(props['color'])
                        except Exception:
                            pass
            except Exception:
                pass
        
        # Apply operando tick widths
        op_tick_widths = op.get('ticks', {}).get('widths', {})
        if op_tick_widths:
            try:
                if op_tick_widths.get('x_major'): ax.tick_params(axis='x', which='major', width=op_tick_widths['x_major'])
                if op_tick_widths.get('x_minor'): ax.tick_params(axis='x', which='minor', width=op_tick_widths['x_minor'])
                if op_tick_widths.get('y_major'): ax.tick_params(axis='y', which='major', width=op_tick_widths['y_major'])
                if op_tick_widths.get('y_minor'): ax.tick_params(axis='y', which='minor', width=op_tick_widths['y_minor'])
            except Exception:
                pass

    # Colorbar
    from matplotlib.colorbar import Colorbar as _Colorbar
    cbar = _Colorbar(cbar_ax, im)
    cbar.ax.yaxis.set_ticks_position('left')
    cbar.ax.yaxis.set_label_position('left')
    try:
        cb_meta = sess.get('colorbar', {})
        label_text = cb_meta.get('label')
        label_mode = cb_meta.get('label_mode', 'normal')
        # Set label on the colorbar's axes for better compatibility
        try:
            cbar.ax.set_ylabel(label_text or '')
        except Exception:
            cbar.set_label(label_text or '')
        if cb_meta.get('clim'):
            try:
                im.set_clim(*cb_meta['clim'])
            except Exception:
                pass
        # Persist custom colorbar attributes for interactive mode
        setattr(cbar.ax, '_colorbar_label', label_text or (cbar.ax.get_ylabel() or 'Intensity'))
        setattr(cbar.ax, '_colorbar_label_mode', label_mode)
        setattr(cbar.ax, '_colorbar_im', im)
        setattr(fig, '_colorbar_label_mode', label_mode)
    except Exception:
        pass

    # Optional EC panel
    ec_ax = None
    if ec_wf > 0 and ec_x0 is not None:
        ec_ax = fig.add_axes([ec_x0, y0, ec_wf, ax_hf])
        # Basic line
        ec = sess.get('ec') or {}
        th = ec.get('time_h')
        vv = ec.get('volt_v')
        if th is not None and vv is not None and len(th) == len(vv) and len(th) > 0:
            # Apply saved style or defaults
            st = (ec.get('line_style') or {})
            color = st.get('color', 'tab:blue')
            lw = float(st.get('linewidth', 1.0) or 1.0)
            ls = st.get('linestyle', '-') or '-'
            alpha = st.get('alpha', None)
            ln, = ec_ax.plot(vv, th, lw=lw, color=color, linestyle=ls, alpha=alpha)
            setattr(ec_ax, '_ec_line', ln)
        
        # Stash arrays for interactivity
        setattr(ec_ax, '_ec_time_h', th)
        setattr(ec_ax, '_ec_voltage_v', vv)
        setattr(ec_ax, '_ec_current_mA', ec.get('curr_mA'))
        # Limits
        try:
            if ec.get('xlim'): ec_ax.set_xlim(*ec['xlim'])
            if ec.get('ylim'): ec_ax.set_ylim(*ec['ylim'])
        except Exception:
            pass
        # Ticks/labels on right
        try:
            ec_ax.yaxis.tick_right(); ec_ax.yaxis.set_label_position('right')
        except Exception:
            pass
        # Custom labels storage
        setattr(ec_ax, '_custom_labels', dict(ec.get('custom_labels', {'x': None, 'y_time': None, 'y_ions': None})))
        # Persist saved time ylim
        if isinstance(ec.get('saved_time_ylim'), (list, tuple)):
            setattr(ec_ax, '_saved_time_ylim', tuple(ec['saved_time_ylim']))
        
        # Apply EC WASD state BEFORE setting labels (if version 2+)
        ec_wasd = None
        if version >= 2:
            ec_wasd = ec.get('wasd_state')
            if ec_wasd and isinstance(ec_wasd, dict):
                from matplotlib.ticker import AutoMinorLocator, NullFormatter
                try:
                    # Apply spines
                    for side in ('top', 'bottom', 'left', 'right'):
                        if side in ec_wasd and 'spine' in ec_wasd[side]:
                            sp = ec_ax.spines.get(side)
                            if sp:
                                sp.set_visible(bool(ec_wasd[side]['spine']))
                    # Apply ticks
                    ec_ax.tick_params(axis='x',
                                     top=bool(ec_wasd.get('top', {}).get('ticks', False)),
                                     bottom=bool(ec_wasd.get('bottom', {}).get('ticks', True)),
                                     labeltop=bool(ec_wasd.get('top', {}).get('labels', False)),
                                     labelbottom=bool(ec_wasd.get('bottom', {}).get('labels', True)))
                    ec_ax.tick_params(axis='y',
                                     left=bool(ec_wasd.get('left', {}).get('ticks', True)),
                                     right=bool(ec_wasd.get('right', {}).get('ticks', False)),
                                     labelleft=bool(ec_wasd.get('left', {}).get('labels', True)),
                                     labelright=bool(ec_wasd.get('right', {}).get('labels', False)))
                    # Apply minor ticks
                    if ec_wasd.get('top', {}).get('minor') or ec_wasd.get('bottom', {}).get('minor'):
                        ec_ax.xaxis.set_minor_locator(AutoMinorLocator())
                        ec_ax.xaxis.set_minor_formatter(NullFormatter())
                    ec_ax.tick_params(axis='x', which='minor',
                                     top=bool(ec_wasd.get('top', {}).get('minor', False)),
                                     bottom=bool(ec_wasd.get('bottom', {}).get('minor', False)))
                    if ec_wasd.get('left', {}).get('minor') or ec_wasd.get('right', {}).get('minor'):
                        ec_ax.yaxis.set_minor_locator(AutoMinorLocator())
                        ec_ax.yaxis.set_minor_formatter(NullFormatter())
                    ec_ax.tick_params(axis='y', which='minor',
                                     left=bool(ec_wasd.get('left', {}).get('minor', False)),
                                     right=bool(ec_wasd.get('right', {}).get('minor', False)))
                    # Store WASD state
                    ec_ts = {}
                    for side_key, prefix in [('top', 't'), ('bottom', 'b'), ('left', 'l'), ('right', 'r')]:
                        s = ec_wasd.get(side_key, {})
                        ec_ts[f'{prefix}_ticks'] = bool(s.get('ticks', False))
                        ec_ts[f'{prefix}_labels'] = bool(s.get('labels', False))
                        ec_ts[f'm{prefix}x' if prefix in 'tb' else f'm{prefix}y'] = bool(s.get('minor', False))
                    ec_ax._saved_tick_state = ec_ts
                    # Apply title flags
                    ec_ax._top_xlabel_on = bool(ec_wasd.get('top', {}).get('title', False))
                    ec_ax._right_ylabel_on = bool(ec_wasd.get('right', {}).get('title', False))
                except Exception as e:
                    print(f"Warning: Could not apply EC WASD state: {e}")
        
        # Set xlabel (respecting WASD title state for bottom)
        bottom_title_on = ec_wasd.get('bottom', {}).get('title', True) if ec_wasd else True
        if bottom_title_on:
            ec_ax.set_xlabel((ec.get('custom_labels') or {}).get('x') or 'Voltage (V)')
        else:
            ec_ax.set_xlabel('')  # Hidden by user via s5
        
        # Handle ions mode
        mode = ec.get('mode', 'time')
        setattr(ec_ax, '_ec_y_mode', mode)
        if mode == 'ions':
            try:
                # Rebuild ions formatter based on stored ions array if present; else leave time labels
                import numpy as _np
                t = _np.asarray(th, float)
                ions_abs = ec.get('ions_abs')
                ion_params = ec.get('ion_params')
                if ions_abs is None and ion_params and t is not None:
                    # Fallback: recompute ions from params
                    i_mA = _np.asarray(ec.get('curr_mA'), float)
                    v = _np.asarray(vv, float)
                    dt = _np.diff(t)
                    inc = _np.empty_like(t); inc[0] = 0.0
                    if t.size > 1:
                        inc[1:] = 0.5 * (i_mA[:-1] + i_mA[1:]) * dt
                    cap_mAh = _np.cumsum(inc)
                    mass_g = float(ion_params.get('mass_mg', 0.0)) / 1000.0
                    with _np.errstate(divide='ignore', invalid='ignore'):
                        cap_mAh_g = _np.where(mass_g>0, cap_mAh / mass_g, _np.nan)
                        ions_delta = _np.where(ion_params.get('cap_per_ion_mAh_g', 0.0)>0,
                                               cap_mAh_g / float(ion_params['cap_per_ion_mAh_g']), _np.nan)
                    ions_abs = float(ion_params.get('start_ions', 0.0)) + ions_delta
                if ions_abs is not None and t is not None and len(ions_abs) == len(t):
                    setattr(ec_ax, '_ions_abs', _np.asarray(ions_abs, float))
                    # Install formatter and label
                    from matplotlib.ticker import FuncFormatter, MaxNLocator
                    y0, y1 = ec_ax.get_ylim()
                    ions_y0 = float(_np.interp(y0, t, ions_abs, left=ions_abs[0], right=ions_abs[-1]))
                    ions_y1 = float(_np.interp(y1, t, ions_abs, left=ions_abs[0], right=ions_abs[-1]))
                    rng = abs(ions_y1 - ions_y0)
                    def _nice_step(r, approx=6):
                        if not _np.isfinite(r) or r <= 0:
                            return 1.0
                        raw = r / max(1, approx)
                        exp = _np.floor(_np.log10(raw))
                        base = raw / (10**exp)
                        if base < 1.5: step = 1.0
                        elif base < 3.5: step = 2.0
                        elif base < 7.5: step = 5.0
                        else: step = 10.0
                        return step * (10**exp)
                    step = _nice_step(rng)
                    def _fmt(y, pos):
                        try:
                            val = float(_np.interp(y, t, ions_abs, left=ions_abs[0], right=ions_abs[-1]))
                            if step > 0:
                                val = round(val / step) * step
                            s = ("%f" % val).rstrip('0').rstrip('.')
                            return s
                        except Exception:
                            return ""
                    ec_ax.yaxis.set_major_formatter(FuncFormatter(_fmt))
                    ec_ax.yaxis.set_major_locator(MaxNLocator(nbins='auto', steps=[1,2,5], min_n_ticks=4))
                    # Label (custom if set) - respect WASD right title state
                    right_title_on = ec_wasd.get('right', {}).get('title', True) if ec_wasd else True
                    if right_title_on:
                        lab = (ec_ax._custom_labels.get('y_ions') if getattr(ec_ax, '_custom_labels', {}).get('y_ions') else 'Number of ions')
                        ec_ax.set_ylabel(lab)
                    else:
                        ec_ax.set_ylabel('')  # Hidden by user via d5
            except Exception:
                pass
        else:
            # Time mode label - respect WASD right title state
            right_title_on = ec_wasd.get('right', {}).get('title', True) if ec_wasd else True
            if right_title_on:
                lab = (ec_ax._custom_labels.get('y_time') if getattr(ec_ax, '_custom_labels', {}).get('y_time') else 'Time (h)')
                try:
                    ec_ax.set_ylabel(lab)
                except Exception:
                    pass
            else:
                ec_ax.set_ylabel('')  # Hidden by user via d5
        
        # Restore stored ylabel if present (for cases where ylabel was hidden)
        stored_ylabel = ec.get('stored_ylabel')
        if stored_ylabel is not None:
            setattr(ec_ax, '_stored_ylabel', stored_ylabel)
        
        # Apply EC spines (WASD state already applied above)
        if version >= 2:
            # Apply EC spines
            ec_spines = ec.get('spines', {})
            if ec_spines:
                try:
                    for name, props in ec_spines.items():
                        sp = ec_ax.spines.get(name)
                        if not sp:
                            continue
                        if 'linewidth' in props and props['linewidth'] is not None:
                            try:
                                sp.set_linewidth(float(props['linewidth']))
                            except Exception:
                                pass
                        if 'visible' in props and props['visible'] is not None:
                            try:
                                sp.set_visible(bool(props['visible']))
                            except Exception:
                                pass
                        if 'color' in props and props['color'] is not None:
                            try:
                                sp.set_edgecolor(props['color'])
                                if name in ('top', 'bottom'):
                                    ec_ax.tick_params(axis='x', which='both', colors=props['color'])
                                    ec_ax.xaxis.label.set_color(props['color'])
                                else:
                                    ec_ax.tick_params(axis='y', which='both', colors=props['color'])
                                    ec_ax.yaxis.label.set_color(props['color'])
                            except Exception:
                                pass
                except Exception:
                    pass
            
            # Apply EC tick widths
            ec_tick_widths = ec.get('ticks', {}).get('widths', {})
            if ec_tick_widths:
                try:
                    if ec_tick_widths.get('x_major'): ec_ax.tick_params(axis='x', which='major', width=ec_tick_widths['x_major'])
                    if ec_tick_widths.get('x_minor'): ec_ax.tick_params(axis='x', which='minor', width=ec_tick_widths['x_minor'])
                    if ec_tick_widths.get('y_major'): ec_ax.tick_params(axis='y', which='major', width=ec_tick_widths['y_major'])
                    if ec_tick_widths.get('y_minor'): ec_ax.tick_params(axis='y', which='minor', width=ec_tick_widths['y_minor'])
                except Exception:
                    pass

    # Persist fixed inch parameters from loaded session to attributes
    # This ensures interactive menu can read correct values
    try:
        setattr(cbar_ax, '_fixed_cb_w_in', float(li['cb_w_in']))
        setattr(cbar_ax, '_fixed_cb_gap_in', float(li['cb_gap_in']))
        setattr(cbar_ax, '_cb_gap_adjusted', True)
        setattr(ax, '_fixed_ax_w_in', float(li['ax_w_in']))
        setattr(ax, '_fixed_ax_h_in', float(li['ax_h_in']))
        # Restore horizontal offsets
        cb_h_offset = li.get('cb_h_offset', 0.0)
        ec_h_offset = li.get('ec_h_offset')
        setattr(cbar_ax, '_cb_h_offset_in', float(cb_h_offset))
        if ec_ax is not None:
            setattr(ec_ax, '_fixed_ec_gap_in', float(li.get('ec_gap_in', 0.0)))
            setattr(ec_ax, '_fixed_ec_w_in', float(li.get('ec_w_in', 0.0)))
            # Set flags to prevent auto-adjustment of loaded session geometry
            setattr(ec_ax, '_ec_gap_adjusted', True)
            setattr(ec_ax, '_ec_op_width_adjusted', True)
            if ec_h_offset is not None:
                setattr(ec_ax, '_ec_h_offset_in', float(ec_h_offset))
            else:
                setattr(ec_ax, '_ec_h_offset_in', 0.0)
        elif ec_h_offset is not None:
            # EC panel doesn't exist but offset was saved - ignore it
            pass
    except Exception:
        pass

    # Apply saved fonts and trigger a refresh redraw
    try:
        f = sess.get('font', {})
        if f.get('chain'):
            plt.rcParams['font.family'] = 'sans-serif'
            plt.rcParams['font.sans-serif'] = f['chain']
        if f.get('size'):
            plt.rcParams['font.size'] = f['size']
    except Exception:
        pass

    # Restore visibility states for colorbar and EC panel
    try:
        cb_meta = sess.get('colorbar', {})
        cb_visible = cb_meta.get('visible', True)  # Default to visible if not saved
        cbar.ax.set_visible(bool(cb_visible))
    except Exception:
        pass
    
    try:
        if ec_ax is not None:
            ec = sess.get('ec') or {}
            ec_visible = ec.get('visible', True)  # Default to visible if not saved
            ec_ax.set_visible(bool(ec_visible))
    except Exception:
        pass

    # Return tuple
    # Rebuild legend based on visible lines
    try:
        handles = []
        labels = []
        for ln in ax.lines:
            if ln.get_visible() and not (ln.get_label() or '').startswith('_'):
                handles.append(ln)
                labels.append(ln.get_label() or '')
        if handles:
            ax.legend(handles, labels)
        else:
            leg = ax.get_legend()
            if leg is not None:
                try:
                    leg.remove()
                except Exception:
                    pass
    except Exception:
        pass
    try:
        fig.canvas.draw()
    except Exception:
        try:
            fig.canvas.draw_idle()
        except Exception:
            pass
    return fig, ax, im, cbar, ec_ax


__all__ = [
    "dump_session",
    "dump_operando_session",
    "load_operando_session",
    "dump_ec_session",
    "load_ec_session",
    "dump_cpc_session",
    "load_cpc_session",
]
 
# --------------------- Electrochem GC session helpers ---------------------------

def dump_ec_session(
    filename: str,
    *,
    fig,
    ax,
    cycle_lines: Dict[int, Dict[str, Any]],
    skip_confirm: bool = False,
) -> None:
    """Serialize electrochem GC plot (capacity vs voltage) including data and styles.

    Stores figure size/dpi, axis labels/limits, and for each cycle the charge and
    discharge line data (x,y) and basic line styles.
    
    Args:
        skip_confirm: If True, skip overwrite confirmation (already handled by caller).
    """
    try:
        fig_w, fig_h = map(float, fig.get_size_inches())
        dpi = int(fig.dpi)
        # Capture axis state
        # Label pads
        try:
            _xlp = float(getattr(ax.xaxis, 'labelpad', 0.0))
        except Exception:
            _xlp = 0.0
        try:
            _ylp = float(getattr(ax.yaxis, 'labelpad', 0.0))
        except Exception:
            _ylp = 0.0
        axis = {
            'xlabel': _axis_label_text(ax, '_stored_xlabel', ax.get_xlabel),
            'ylabel': _axis_label_text(ax, '_stored_ylabel', ax.get_ylabel),
            'xlim': tuple(map(float, ax.get_xlim())),
            'ylim': tuple(map(float, ax.get_ylim())),
            'xscale': getattr(ax, 'get_xscale', lambda: 'linear')(),
            'yscale': getattr(ax, 'get_yscale', lambda: 'linear')(),
            'x_labelpad': _xlp,
            'y_labelpad': _ylp,
            'xlabel_visible': bool(ax.xaxis.label.get_visible()),
            'ylabel_visible': bool(ax.yaxis.label.get_visible()),
            'xlabel_color': ax.xaxis.label.get_color(),
            'ylabel_color': ax.yaxis.label.get_color(),
        }
        # Helper to capture WASD state
        def _capture_wasd_state(axis):
            ts = getattr(axis, '_saved_tick_state', {})
            wasd = {}
            for side in ('top', 'bottom', 'left', 'right'):
                sp = axis.spines.get(side)
                prefix = {'top': 't', 'bottom': 'b', 'left': 'l', 'right': 'r'}[side]
                wasd[side] = {
                    'spine': bool(sp.get_visible() if sp else False),
                    'ticks': bool(ts.get(f'{prefix}_ticks', ts.get({'top':'tx','bottom':'bx','left':'ly','right':'ry'}[side], side=='bottom' or side=='left'))),
                    'minor': bool(ts.get(f'm{prefix}x' if side in ('top','bottom') else f'm{prefix}y', False)),
                    'labels': bool(ts.get(f'{prefix}_labels', ts.get({'top':'tx','bottom':'bx','left':'ly','right':'ry'}[side], side=='bottom' or side=='left'))),
                    'title': (
                        bool(getattr(axis, '_top_xlabel_on', False)) if side == 'top'
                        else bool(getattr(axis, '_right_ylabel_on', False)) if side == 'right'
                        else bool(axis.xaxis.label.get_visible()) if side == 'bottom'
                        else bool(axis.yaxis.label.get_visible())
                    ),
                }
            return wasd
        
        # Capture WASD state
        wasd_state = _capture_wasd_state(ax)
        
        # Tick visibility state (if present from interactive menu) - kept for backward compatibility
        tick_state = dict(getattr(ax, '_saved_tick_state', {
            'bx': True, 'tx': False, 'ly': True, 'ry': False,
            'mbx': False, 'mtx': False, 'mly': False, 'mry': False,
        }))
        # Representative tick widths
        def _tick_width(axis, which: str):
            return _current_tick_width(axis, which)
        tick_widths = {
            'x_major': _tick_width(ax.xaxis, 'major'),
            'x_minor': _tick_width(ax.xaxis, 'minor'),
            'y_major': _tick_width(ax.yaxis, 'major'),
            'y_minor': _tick_width(ax.yaxis, 'minor'),
        }
        # Tick direction
        tick_direction = getattr(fig, '_tick_direction', 'out')
        # Spines state
        spines_state = {
            name: {
                'linewidth': (ax.spines.get(name).get_linewidth() if ax.spines.get(name) else None),
                'visible': (ax.spines.get(name).get_visible() if ax.spines.get(name) else None),
                'color': (ax.spines.get(name).get_edgecolor() if ax.spines.get(name) else None),
            } for name in ('bottom','top','left','right')
        }
        # Duplicate axis title flags
        titles = {
            'top_x': bool(getattr(ax, '_top_xlabel_on', False)),
            'right_y': bool(getattr(ax, '_right_ylabel_on', False)),
        }
        # Subplot margins
        sp = fig.subplotpars
        subplot_margins = {
            'left': float(sp.left),
            'right': float(sp.right),
            'bottom': float(sp.bottom),
            'top': float(sp.top),
        }
        # Capture cycles
        lines_state: Dict[int, Dict[str, Any]] = {}
        for cyc, parts in cycle_lines.items():
            entry: Dict[str, Any] = {}
            # Handle both GC mode (dict with 'charge'/'discharge') and CV mode (direct Line2D)
            if isinstance(parts, dict):
                # GC mode: parts is a dict with 'charge' and 'discharge' Line2D objects
                for role in ("charge", "discharge"):
                    ln = parts.get(role)
                    if ln is None:
                        entry[role] = None
                        continue
                    try:
                        x = np.asarray(ln.get_xdata(), float)
                        y = np.asarray(ln.get_ydata(), float)
                    except Exception:
                        x = np.array([]); y = np.array([])
                    try:
                        st = {
                            'color': ln.get_color(),
                            'linewidth': float(ln.get_linewidth() or 1.0),
                            'linestyle': ln.get_linestyle() or '-',
                            'alpha': ln.get_alpha(),
                            'visible': bool(ln.get_visible()),
                            'label': ln.get_label() or '',
                        }
                    except Exception:
                        st = {'color': 'tab:blue', 'linewidth': 1.0, 'linestyle': '-', 'alpha': None, 'visible': True, 'label': ''}
                    entry[role] = {'x': x, 'y': y, 'style': st}
            else:
                # CV mode: parts is a Line2D object directly
                ln = parts
                try:
                    x = np.asarray(ln.get_xdata(), float)
                    y = np.asarray(ln.get_ydata(), float)
                except Exception:
                    x = np.array([]); y = np.array([])
                try:
                    st = {
                        'color': ln.get_color(),
                        'linewidth': float(ln.get_linewidth() or 1.0),
                        'linestyle': ln.get_linestyle() or '-',
                        'alpha': ln.get_alpha(),
                        'visible': bool(ln.get_visible()),
                        'label': ln.get_label() or '',
                    }
                except Exception:
                    st = {'color': 'tab:blue', 'linewidth': 1.0, 'linestyle': '-', 'alpha': None, 'visible': True, 'label': ''}
                # Store under 'line' key to distinguish from GC mode's 'charge'/'discharge' keys
                entry['line'] = {'x': x, 'y': y, 'style': st}
            lines_state[int(cyc)] = entry
        legend_visible = False
        legend_xy_in = None
        try:
            leg = ax.get_legend()
            if leg is not None:
                legend_visible = bool(leg.get_visible())
            xy = getattr(fig, '_ec_legend_xy_in', None)
            if isinstance(xy, (list, tuple)) and len(xy) == 2:
                legend_xy_in = (float(xy[0]), float(xy[1]))
        except Exception:
            legend_xy_in = None
        sess = {
            'kind': 'ec_gc',
            'version': 2,
            'figure': {'size': (fig_w, fig_h), 'dpi': dpi},
            'axis': axis,
            'subplot_margins': subplot_margins,
            'lines': lines_state,
            'font': {
                'size': plt.rcParams.get('font.size'),
                'chain': list(plt.rcParams.get('font.sans-serif', [])),
            },
            'legend': {
                'visible': legend_visible,
                'position_inches': legend_xy_in,
                'title': getattr(fig, '_ec_legend_title', None),
            },
            'wasd_state': wasd_state,
            'tick_state': tick_state,
            'tick_widths': tick_widths,
            'tick_direction': tick_direction,
            'spines': spines_state,
            'titles': titles,
            'mode': getattr(ax, '_is_dqdv_mode', None),  # Store dQdV mode flag
            'rotation_angle': getattr(fig, '_ec_rotation_angle', 0),  # Store rotation angle
            'source_paths': list(getattr(fig, '_bp_source_paths', []) or []),
            'grid': ax.xaxis._gridOnMajor if hasattr(ax.xaxis, '_gridOnMajor') else (
                any(line.get_visible() for line in ax.get_xgridlines() + ax.get_ygridlines()) if hasattr(ax, 'get_xgridlines') else False
            ),
        }
        if skip_confirm:
            target = filename
        else:
            target = _confirm_overwrite(filename)
            if not target:
                print("EC session save canceled.")
                return
        with open(target, 'wb') as f:
            pickle.dump(sess, f)
        print(f"EC session saved to {target}")
    except Exception as e:
        print(f"Error saving EC session: {e}")


def load_ec_session(filename: str):
    """Load an EC GC session and reconstruct figure, axes, and cycle_lines.

    Returns: (fig, ax, cycle_lines)
    """
    try:
        with open(filename, 'rb') as f:
            sess = pickle.load(f)
    except Exception as e:
        print(f"Failed to load EC session: {e}")
        return None

    if not isinstance(sess, dict) or sess.get('kind') != 'ec_gc':
        print("Not an EC GC session file.")
        return None

    # Use standard DPI of 100 instead of saved DPI to avoid display-dependent issues
    # (Retina displays, Windows scaling, etc. can cause saved DPI to differ)
    fig = plt.figure(figsize=tuple(sess['figure']['size']), dpi=100)
    # Preserve saved geometry by disabling auto layout
    try:
        fig.set_layout_engine('none')
    except Exception:
        try:
            fig.set_tight_layout(False)
        except Exception:
            pass
    ax = fig.add_subplot(111)
    try:
        fig._bp_source_paths = list(sess.get('source_paths', []) or [])
    except Exception:
        fig._bp_source_paths = []
    try:
        session_abs = os.path.abspath(filename)
        sources = list(getattr(fig, '_bp_source_paths', []) or [])
        if session_abs not in sources:
            sources.append(session_abs)
        fig._bp_source_paths = sources
    except Exception:
        pass

    def _sanitize_legend_offset(xy):
        if xy is None or not isinstance(xy, (list, tuple)) or len(xy) != 2:
            return None
        try:
            x_val = float(xy[0])
            y_val = float(xy[1])
        except Exception:
            return None
        fw, fh = fig.get_size_inches()
        if fw <= 0 or fh <= 0:
            return None
        max_offset = max(fw, fh) * 2.0
        if abs(x_val) > max_offset or abs(y_val) > max_offset:
            return None
        return (x_val, y_val)
    # Fonts
    try:
        f = sess.get('font', {})
        if f.get('chain'):
            plt.rcParams['font.family'] = 'sans-serif'
            plt.rcParams['font.sans-serif'] = f['chain']
        if f.get('size'):
            plt.rcParams['font.size'] = f['size']
    except Exception:
        pass

    # Apply subplot margins early (prevents label clipping on draw)
    try:
        spm = sess.get('subplot_margins', {})
        if all(k in spm for k in ('left','right','bottom','top')):
            fig.subplots_adjust(left=float(spm['left']), right=float(spm['right']), bottom=float(spm['bottom']), top=float(spm['top']))
        
        # Restore exact frame size if stored (for precision)
        frame_size = sess.get('frame_size')
        if frame_size and isinstance(frame_size, (list, tuple)) and len(frame_size) == 2:
            target_w_in, target_h_in = map(float, frame_size)
            # Get current canvas size
            canvas_w_in, canvas_h_in = fig.get_size_inches()
            # Calculate needed fractions to achieve exact frame size
            if canvas_w_in > 0 and canvas_h_in > 0:
                # Get current position to preserve centering
                bbox = ax.get_position()
                center_x = (bbox.x0 + bbox.x1) / 2.0
                center_y = (bbox.y0 + bbox.y1) / 2.0
                # Calculate new fractions
                new_w_frac = target_w_in / canvas_w_in
                new_h_frac = target_h_in / canvas_h_in
                # Reposition to maintain centering
                new_left = center_x - new_w_frac / 2.0
                new_right = center_x + new_w_frac / 2.0
                new_bottom = center_y - new_h_frac / 2.0
                new_top = center_y + new_h_frac / 2.0
                # Apply
                fig.subplots_adjust(left=new_left, right=new_right, bottom=new_bottom, top=new_top)
    except Exception:
        pass

    # Rebuild lines
    raw = sess.get('lines', {})
    cycle_lines: Dict[int, Dict[str, Any]] = {}
    # Use a color cycle but keep saved colors primarily
    for k in sorted(raw.keys(), key=lambda x: int(x)):
        cyc = int(k)
        parts = raw[k] or {}
        
        # Check if this is CV mode (has 'line' key) or GC mode (has 'charge'/'discharge' keys)
        if 'line' in parts:
            # CV mode: single line per cycle
            rec = parts.get('line')
            ln_obj = None
            if isinstance(rec, dict) and isinstance(rec.get('x'), np.ndarray) and isinstance(rec.get('y'), np.ndarray):
                x = np.asarray(rec['x'], float)
                y = np.asarray(rec['y'], float)
                st = rec.get('style', {})
                color = st.get('color', 'tab:blue')
                lw = float(st.get('linewidth', 1.0))
                ls = st.get('linestyle', '-') or '-'
                alpha = st.get('alpha', None)
                label = st.get('label', f'Cycle {cyc}')
                try:
                    ln_obj, = ax.plot(x, y, linestyle=ls, linewidth=lw, color=color, alpha=alpha, label=label)
                    vis = bool(st.get('visible', True))
                    ln_obj.set_visible(vis)
                except Exception:
                    pass
            cycle_lines[cyc] = ln_obj
        else:
            # GC mode: separate charge and discharge lines
            cyc_entry: Dict[str, Any] = {}
            for role in ("charge", "discharge"):
                rec = parts.get(role)
                ln_obj = None
                if isinstance(rec, dict) and isinstance(rec.get('x'), np.ndarray) and isinstance(rec.get('y'), np.ndarray):
                    x = np.asarray(rec['x'], float)
                    y = np.asarray(rec['y'], float)
                    st = rec.get('style', {})
                    color = st.get('color', 'tab:blue')
                    lw = float(st.get('linewidth', 1.0))
                    ls = st.get('linestyle', '-') or '-'
                    alpha = st.get('alpha', None)
                    label = st.get('label', f'Cycle {cyc}')
                    if role == 'discharge' and (not label or label.startswith('_')):
                        label = f'Cycle {cyc}' if rec.get('x') is None else '_nolegend_'
                    ln_args = {}
                    try:
                        ln_obj, = ax.plot(x, y, linestyle=ls, linewidth=lw, color=color, alpha=alpha, label=label)
                        vis = bool(st.get('visible', True))
                        ln_obj.set_visible(vis)
                    except Exception:
                        pass
                cyc_entry[role] = ln_obj
            cycle_lines[cyc] = cyc_entry

    # Axis labels/limits/scales
    # Store the labels first, then apply WASD state before actually setting them
    try:
        axis = sess.get('axis', {})
        stored_xlabel = axis.get('xlabel') or ''
        stored_ylabel = axis.get('ylabel') or ''
        xlabel_visible = axis.get('xlabel_visible', True)
        ylabel_visible = axis.get('ylabel_visible', True)
        xlabel_color = axis.get('xlabel_color')
        ylabel_color = axis.get('ylabel_color')
        
        # Scales first
        try:
            if axis.get('xscale'): ax.set_xscale(axis.get('xscale'))
            if axis.get('yscale'): ax.set_yscale(axis.get('yscale'))
        except Exception:
            pass
        if axis.get('xlim'): ax.set_xlim(*axis['xlim'])
        if axis.get('ylim'): ax.set_ylim(*axis['ylim'])
        # Label pads saved for later
        x_labelpad = axis.get('x_labelpad')
        y_labelpad = axis.get('y_labelpad')
    except Exception:
        stored_xlabel = ''
        stored_ylabel = ''
        x_labelpad = None
        y_labelpad = None
        xlabel_visible = True
        ylabel_visible = True
        xlabel_color = None
        ylabel_color = None
    if stored_xlabel:
        try:
            ax._stored_xlabel = stored_xlabel
        except Exception:
            pass
    if stored_ylabel:
        try:
            ax._stored_ylabel = stored_ylabel
        except Exception:
            pass
    try:
        if xlabel_color:
            ax._stored_xlabel_color = xlabel_color
        else:
            ax._stored_xlabel_color = ax.xaxis.label.get_color()
    except Exception:
        pass
    try:
        if ylabel_color:
            ax._stored_ylabel_color = ylabel_color
        else:
            ax._stored_ylabel_color = ax.yaxis.label.get_color()
    except Exception:
        pass
    if not hasattr(ax, '_stored_top_xlabel_color'):
        ax._stored_top_xlabel_color = ax.xaxis.label.get_color()
    if not hasattr(ax, '_stored_right_ylabel_color'):
        ax._stored_right_ylabel_color = ax.yaxis.label.get_color()

    # Spines
    try:
        sp_meta = sess.get('spines', {})
        for name, spec in sp_meta.items():
            sp = ax.spines.get(name)
            if not sp:
                continue
            if spec.get('linewidth') is not None:
                try:
                    sp.set_linewidth(float(spec['linewidth']))
                except Exception:
                    pass
            if spec.get('visible') is not None:
                try:
                    sp.set_visible(bool(spec['visible']))
                except Exception:
                    pass
            if spec.get('color') is not None:
                try:
                    sp.set_edgecolor(spec['color'])
                    if name in ('top', 'bottom'):
                        ax.tick_params(axis='x', which='both', colors=spec['color'])
                        ax.xaxis.label.set_color(spec['color'])
                        if name == 'top':
                            ax._stored_top_xlabel_color = spec['color']
                        else:
                            ax._stored_xlabel_color = spec['color']
                    else:
                        ax.tick_params(axis='y', which='both', colors=spec['color'])
                        ax.yaxis.label.set_color(spec['color'])
                        if name == 'left':
                            ax._stored_ylabel_color = spec['color']
                        else:
                            ax._stored_right_ylabel_color = spec['color']
                except Exception:
                    pass
    except Exception:
        pass

    # Apply WASD state if version 2+
    version = sess.get('version', 1)
    wasd = None
    if version >= 2:
        wasd = sess.get('wasd_state')
        if wasd and isinstance(wasd, dict):
            from matplotlib.ticker import AutoMinorLocator, NullFormatter
            try:
                # Apply spines
                for side in ('top', 'bottom', 'left', 'right'):
                    if side in wasd and 'spine' in wasd[side]:
                        sp = ax.spines.get(side)
                        if sp:
                            sp.set_visible(bool(wasd[side]['spine']))
                # Apply ticks
                ax.tick_params(axis='x', 
                              top=bool(wasd.get('top', {}).get('ticks', False)),
                              bottom=bool(wasd.get('bottom', {}).get('ticks', True)),
                              labeltop=bool(wasd.get('top', {}).get('labels', False)),
                              labelbottom=bool(wasd.get('bottom', {}).get('labels', True)))
                ax.tick_params(axis='y',
                              left=bool(wasd.get('left', {}).get('ticks', True)),
                              right=bool(wasd.get('right', {}).get('ticks', False)),
                              labelleft=bool(wasd.get('left', {}).get('labels', True)),
                              labelright=bool(wasd.get('right', {}).get('labels', False)))
                # Apply minor ticks
                if wasd.get('top', {}).get('minor') or wasd.get('bottom', {}).get('minor'):
                    ax.xaxis.set_minor_locator(AutoMinorLocator())
                    ax.xaxis.set_minor_formatter(NullFormatter())
                ax.tick_params(axis='x', which='minor',
                              top=bool(wasd.get('top', {}).get('minor', False)),
                              bottom=bool(wasd.get('bottom', {}).get('minor', False)))
                if wasd.get('left', {}).get('minor') or wasd.get('right', {}).get('minor'):
                    ax.yaxis.set_minor_locator(AutoMinorLocator())
                    ax.yaxis.set_minor_formatter(NullFormatter())
                ax.tick_params(axis='y', which='minor',
                              left=bool(wasd.get('left', {}).get('minor', False)),
                              right=bool(wasd.get('right', {}).get('minor', False)))
                # Store WASD state
                tick_state = {}
                for side_key, prefix in [('top', 't'), ('bottom', 'b'), ('left', 'l'), ('right', 'r')]:
                    s = wasd.get(side_key, {})
                    tick_state[f'{prefix}_ticks'] = bool(s.get('ticks', False))
                    tick_state[f'{prefix}_labels'] = bool(s.get('labels', False))
                    tick_state[f'm{prefix}x' if prefix in 'tb' else f'm{prefix}y'] = bool(s.get('minor', False))
                ax._saved_tick_state = tick_state
                # Apply title flags
                ax._top_xlabel_on = bool(wasd.get('top', {}).get('title', False))
                ax._right_ylabel_on = bool(wasd.get('right', {}).get('title', False))
            except Exception as e:
                print(f"Warning: Could not apply WASD state: {e}")
        
        # Apply tick widths from version 2
        tw = sess.get('tick_widths', {})
        if tw:
            try:
                if tw.get('x_major') is not None: ax.tick_params(axis='x', which='major', width=float(tw['x_major']))
                if tw.get('x_minor') is not None: ax.tick_params(axis='x', which='minor', width=float(tw['x_minor']))
                if tw.get('y_major') is not None: ax.tick_params(axis='y', which='major', width=float(tw['y_major']))
                if tw.get('y_minor') is not None: ax.tick_params(axis='y', which='minor', width=float(tw['y_minor']))
            except Exception:
                pass
        
        # Apply tick direction from version 2
        try:
            tick_direction = sess.get('tick_direction', 'out')
            if tick_direction:
                setattr(fig, '_tick_direction', tick_direction)
                ax.tick_params(axis='both', which='both', direction=tick_direction)
        except Exception:
            pass
        
        # Restore grid state
        try:
            grid_enabled = sess.get('grid', False)
            if grid_enabled:
                ax.grid(True, color='0.85', linestyle='-', linewidth=0.5, alpha=0.7)
            else:
                ax.grid(False)
        except Exception:
            pass
        
        # Apply rotation angle from version 2
        try:
            rotation_angle = sess.get('rotation_angle', 0)
            setattr(fig, '_ec_rotation_angle', rotation_angle)
        except Exception:
            pass
    else:
        # Version 1 backward compatibility
        try:
            tick_state = sess.get('tick_state', {})
            # Persist on axes for interactive menu init
            ax._saved_tick_state = dict(tick_state)
            # Apply visibility
            ax.tick_params(axis='x',
                           bottom=tick_state.get('bx', True), labelbottom=tick_state.get('bx', True),
                           top=tick_state.get('tx', False),   labeltop=tick_state.get('tx', False))
            ax.tick_params(axis='y',
                           left=tick_state.get('ly', True),  labelleft=tick_state.get('ly', True),
                           right=tick_state.get('ry', False), labelright=tick_state.get('ry', False))
            # Minor ticks
            if tick_state.get('mbx') or tick_state.get('mtx'):
                from matplotlib.ticker import AutoMinorLocator, NullFormatter
                ax.xaxis.set_minor_locator(AutoMinorLocator())
                ax.xaxis.set_minor_formatter(NullFormatter())
                ax.tick_params(axis='x', which='minor',
                               bottom=tick_state.get('mbx', False),
                               top=tick_state.get('mtx', False),
                               labelbottom=False, labeltop=False)
            else:
                ax.tick_params(axis='x', which='minor', bottom=False, top=False, labelbottom=False, labeltop=False)
            if tick_state.get('mly') or tick_state.get('mry'):
                from matplotlib.ticker import AutoMinorLocator, NullFormatter
                ax.yaxis.set_minor_locator(AutoMinorLocator())
                ax.yaxis.set_minor_formatter(NullFormatter())
                ax.tick_params(axis='y', which='minor',
                               left=tick_state.get('mly', False),
                               right=tick_state.get('mry', False),
                               labelleft=False, labelright=False)
            else:
                ax.tick_params(axis='y', which='minor', left=False, right=False, labelleft=False, labelright=False)
            # Widths
            tw = sess.get('tick_widths', {})
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

    # Restore axis labels/visibility after WASD application
    def _title_pref(side_visible: bool, side_key: str):
        if wasd and isinstance(wasd, dict):
            entry = wasd.get(side_key, {})
            if 'title' in entry:
                return bool(entry.get('title'))
        return bool(side_visible)
    bottom_pref = _title_pref(xlabel_visible, 'bottom')
    left_pref = _title_pref(ylabel_visible, 'left')
    if bottom_pref and stored_xlabel:
        ax.set_xlabel(stored_xlabel)
        ax.xaxis.label.set_visible(True)
        color = getattr(ax, '_stored_xlabel_color', None)
        if color:
            ax.xaxis.label.set_color(color)
    else:
        ax.set_xlabel('')
        ax.xaxis.label.set_visible(False)
    if left_pref and stored_ylabel:
        ax.set_ylabel(stored_ylabel)
        ax.yaxis.label.set_visible(True)
        color = getattr(ax, '_stored_ylabel_color', None)
        if color:
            ax.yaxis.label.set_color(color)
    else:
        ax.set_ylabel('')
        ax.yaxis.label.set_visible(False)

    # Duplicate titles
    try:
        titles = sess.get('titles', {})
        if titles.get('top_x'):
            lbl = ax.get_xlabel() or ''
            if lbl:
                txt = getattr(ax, '_top_xlabel_artist', None)
                if txt is None:
                    txt = ax.text(0.5, 1.02, lbl, ha='center', va='bottom', transform=ax.transAxes)
                    ax._top_xlabel_artist = txt
                else:
                    txt.set_text(lbl); txt.set_visible(True)
                ax._top_xlabel_on = True
                try:
                    color = getattr(ax, '_stored_top_xlabel_color', None)
                    if color and txt is not None:
                        txt.set_color(color)
                except Exception:
                    pass
        else:
            if hasattr(ax, '_top_xlabel_artist') and ax._top_xlabel_artist is not None:
                try: ax._top_xlabel_artist.set_visible(False)
                except Exception: pass
            ax._top_xlabel_on = False
        if titles.get('right_y'):
            lbl = ax.get_ylabel() or ''
            if lbl:
                if hasattr(ax, '_right_ylabel_artist') and ax._right_ylabel_artist is not None:
                    try: ax._right_ylabel_artist.remove()
                    except Exception: pass
                ax._right_ylabel_artist = ax.text(1.02, 0.5, lbl, rotation=90, va='center', ha='left', transform=ax.transAxes)
                ax._right_ylabel_on = True
                try:
                    color = getattr(ax, '_stored_right_ylabel_color', None)
                    if color and ax._right_ylabel_artist is not None:
                        ax._right_ylabel_artist.set_color(color)
                except Exception:
                    pass
        else:
            if hasattr(ax, '_right_ylabel_artist') and ax._right_ylabel_artist is not None:
                try: ax._right_ylabel_artist.remove()
                except Exception: pass
                ax._right_ylabel_artist = None
            ax._right_ylabel_on = False
    except Exception:
        pass
    
    # Restore mode flag (e.g., dQdV mode)
    try:
        mode = sess.get('mode')
        if mode is not None:
            ax._is_dqdv_mode = bool(mode)
    except Exception:
        pass

    # Legend visibility/position
    try:
        legend_cfg = sess.get('legend', {}) or {}
        legend_visible = bool(legend_cfg.get('visible', True))
        legend_xy = _sanitize_legend_offset(legend_cfg.get('position_inches'))
        legend_title = legend_cfg.get('title')
        if legend_title:
            fig._ec_legend_title = legend_title
        else:
            fig._ec_legend_title = legend_title or getattr(fig, '_ec_legend_title', None)
        if not getattr(fig, '_ec_legend_title', None):
            fig._ec_legend_title = "Cycle"
        try:
            fig._ec_legend_user_visible = legend_visible
        except Exception:
            pass
        if legend_xy is not None:
            fig._ec_legend_xy_in = legend_xy
        handles = []
        labels = []
        for ln in ax.lines:
            if ln.get_visible():
                lbl = ln.get_label() or ''
                if lbl.startswith('_'):
                    continue
                handles.append(ln)
                labels.append(lbl)
        if handles:
            if legend_xy is not None:
                fw, fh = fig.get_size_inches()
                if fw > 0 and fh > 0:
                    fx = 0.5 + legend_xy[0] / fw
                    fy = 0.5 + legend_xy[1] / fh
                    leg = ax.legend(handles, labels, loc='center',
                                    bbox_to_anchor=(fx, fy), bbox_transform=fig.transFigure,
                                    borderaxespad=1.0)
                else:
                    leg = ax.legend(handles, labels, loc='best', borderaxespad=1.0)
            else:
                leg = ax.legend(handles, labels, loc='best', borderaxespad=1.0)
            if leg is not None:
                try:
                    leg.set_frame_on(False)
                except Exception:
                    pass
                leg.set_visible(legend_visible)
                try:
                    title_text = getattr(fig, '_ec_legend_title', None) or "Cycle"
                    leg.set_title(title_text)
                except Exception:
                    pass
        else:
            leg = ax.get_legend()
            if leg is not None:
                try:
                    leg.remove()
                except Exception:
                    pass
    except Exception:
        pass
    
    try:
        fig.canvas.draw()
    except Exception:
        try:
            fig.canvas.draw_idle()
        except Exception:
            pass
    return fig, ax, cycle_lines

# --------------------- CPC (Capacity-Per-Cycle) session helpers -----------------

def dump_cpc_session(
    filename: str,
    *,
    fig,
    ax,
    ax2,
    sc_charge,
    sc_discharge,
    sc_eff,
    file_data=None,
    skip_confirm: bool = False,
):
    """Serialize CPC plot including scatter data, styles, axes, and legend position.

    Stores arrays for charge/discharge capacities and efficiency vs cycle number,
    marker styles, axis labels/limits, figure size/dpi, legend position, WASD states,
    tick widths, spines, frame size, and all visual styling.
    
    Args:
        file_data: Optional list of multi-file data dictionaries
        skip_confirm: If True, skip overwrite confirmation (already handled by caller).
    """
    try:
        import numpy as _np
        fig_w, fig_h = map(float, fig.get_size_inches())
        dpi = int(fig.dpi)
        
        # Extract scatter data
        def _scatter_xy(sc):
            try:
                offs = sc.get_offsets()
                arr = _np.asarray(offs, float)
                if arr.ndim == 2 and arr.shape[1] >= 2:
                    return _np.array(arr[:,0], float), _np.array(arr[:,1], float)
            except Exception:
                pass
            return _np.array([]), _np.array([])
        x_c, y_c = _scatter_xy(sc_charge)
        x_d, y_d = _scatter_xy(sc_discharge)
        x_e, y_e = _scatter_xy(sc_eff)
        
        # Colors and sizes
        def _color_of(sc):
            try:
                from matplotlib.colors import to_hex
                arr = getattr(sc, 'get_facecolors', lambda: None)()
                if arr is not None and len(arr):
                    return to_hex(arr[0])
                c = getattr(sc, 'get_color', lambda: None)()
                if c is not None:
                    if isinstance(c, (list, tuple)) and c and not isinstance(c, str):
                        return to_hex(c[0])
                    try:
                        return to_hex(c)
                    except Exception:
                        return c
            except Exception:
                pass
            return None
        
        def _size_of(sc, default=32.0):
            try:
                arr = sc.get_sizes()
                if arr is not None and len(arr):
                    return float(arr[0])
            except Exception:
                pass
            return float(default)
        
        # Axes frame size (in inches)
        bbox = ax.get_position()
        frame_w_in = bbox.width * fig_w
        frame_h_in = bbox.height * fig_h
        
        # Save spines state for both ax and ax2
        spines_state = {}
        for name, sp in ax.spines.items():
            spines_state[f'ax_{name}'] = {
                'linewidth': sp.get_linewidth(),
                'color': sp.get_edgecolor(),
                'visible': sp.get_visible(),
            }
        for name, sp in ax2.spines.items():
            spines_state[f'ax2_{name}'] = {
                'linewidth': sp.get_linewidth(),
                'color': sp.get_edgecolor(),
                'visible': sp.get_visible(),
            }
        
        # Helper to capture tick widths
        def _tick_width(axis, which: str):
            return _current_tick_width(axis, which)
        
        tick_widths = {
            'x_major': _tick_width(ax.xaxis, 'major'),
            'x_minor': _tick_width(ax.xaxis, 'minor'),
            'ly_major': _tick_width(ax.yaxis, 'major'),
            'ly_minor': _tick_width(ax.yaxis, 'minor'),
            'ry_major': _tick_width(ax2.yaxis, 'major'),
            'ry_minor': _tick_width(ax2.yaxis, 'minor'),
        }
        
        # Subplot margins
        sp = fig.subplotpars
        subplot_margins = {
            'left': float(sp.left),
            'right': float(sp.right),
            'bottom': float(sp.bottom),
            'top': float(sp.top),
        }
        
        # Capture WASD state from figure attribute
        wasd_state = getattr(fig, '_cpc_wasd_state', None)
        if not isinstance(wasd_state, dict):
            # Fallback: capture current state
            wasd_state = {
                'top': {
                    'spine': bool(ax.spines.get('top').get_visible() if ax.spines.get('top') else False),
                    'ticks': bool(ax.xaxis._major_tick_kw.get('tick2On', False)),
                    'minor': bool(ax.xaxis._minor_tick_kw.get('tick2On', False)),
                    'labels': bool(ax.xaxis._major_tick_kw.get('label2On', False)),
                    'title': bool(getattr(ax, '_top_xlabel_text', None) and getattr(ax, '_top_xlabel_text').get_visible()),
                },
                'bottom': {
                    'spine': bool(ax.spines.get('bottom').get_visible() if ax.spines.get('bottom') else True),
                    'ticks': bool(ax.xaxis._major_tick_kw.get('tick1On', True)),
                    'minor': bool(ax.xaxis._minor_tick_kw.get('tick1On', False)),
                    'labels': bool(ax.xaxis._major_tick_kw.get('label1On', True)),
                    'title': bool(ax.get_xlabel()),
                },
                'left': {
                    'spine': bool(ax.spines.get('left').get_visible() if ax.spines.get('left') else True),
                    'ticks': bool(ax.yaxis._major_tick_kw.get('tick1On', True)),
                    'minor': bool(ax.yaxis._minor_tick_kw.get('tick1On', False)),
                    'labels': bool(ax.yaxis._major_tick_kw.get('label1On', True)),
                    'title': bool(ax.get_ylabel()),
                },
                'right': {
                    'spine': bool(ax2.spines.get('right').get_visible() if ax2.spines.get('right') else True),
                    'ticks': bool(ax2.yaxis._major_tick_kw.get('tick2On', True)),
                    'minor': bool(ax2.yaxis._minor_tick_kw.get('tick2On', False)),
                    'labels': bool(ax2.yaxis._major_tick_kw.get('label2On', True)),
                    'title': bool(ax2.yaxis.get_label().get_text()) and bool(sc_eff.get_visible()),
                },
            }
        
        # Capture stored title texts
        stored_titles = {
            'xlabel': getattr(ax, '_stored_xlabel', ax.get_xlabel()),
            'ylabel': getattr(ax, '_stored_ylabel', ax.get_ylabel()),
            'top_xlabel': getattr(ax, '_stored_top_xlabel', ''),
            'right_ylabel': getattr(ax2, '_stored_ylabel', ax2.get_ylabel()),
        }
        
        meta = {
            'kind': 'cpc',
            'version': 2,  # Incremented version for new format
            'figure': {
                'size': (fig_w, fig_h),
                'dpi': dpi,
                'frame_size': (frame_w_in, frame_h_in),
                'axes_bbox': {
                    'left': float(bbox.x0),
                    'bottom': float(bbox.y0),
                    'right': float(bbox.x0 + bbox.width),
                    'top': float(bbox.y0 + bbox.height),
                },
                'subplot_margins': subplot_margins,
                'spines': spines_state,
            },
            'axis': {
                'xlabel': ax.get_xlabel(),
                'ylabel_left': ax.get_ylabel(),
                'ylabel_right': ax2.get_ylabel(),
                'xlim': tuple(map(float, ax.get_xlim())),
                'ylim_left': tuple(map(float, ax.get_ylim())),
                'ylim_right': tuple(map(float, ax2.get_ylim())),
                'x_labelpad': float(getattr(ax.xaxis, 'labelpad', 0.0) or 0.0),
                'y_left_labelpad': float(getattr(ax.yaxis, 'labelpad', 0.0) or 0.0),
                'y_right_labelpad': float(getattr(ax2.yaxis, 'labelpad', 0.0) or 0.0),
            },
            'series': {
                'charge': {
                    'x': x_c, 'y': y_c,
                    'color': _color_of(sc_charge),
                    'size': _size_of(sc_charge, 32.0),
                    'alpha': (float(sc_charge.get_alpha()) if sc_charge.get_alpha() is not None else None),
                    'visible': bool(getattr(sc_charge, 'get_visible', lambda: True)()),
                    'label': getattr(sc_charge, 'get_label', lambda: 'Charge capacity')() or 'Charge capacity',
                },
                'discharge': {
                    'x': x_d, 'y': y_d,
                    'color': _color_of(sc_discharge),
                    'size': _size_of(sc_discharge, 32.0),
                    'alpha': (float(sc_discharge.get_alpha()) if sc_discharge.get_alpha() is not None else None),
                    'visible': bool(getattr(sc_discharge, 'get_visible', lambda: True)()),
                    'label': getattr(sc_discharge, 'get_label', lambda: 'Discharge capacity')() or 'Discharge capacity',
                },
                'efficiency': {
                    'x': x_e, 'y': y_e,
                    'color': _color_of(sc_eff) or '#2ca02c',
                    'size': _size_of(sc_eff, 40.0),
                    'alpha': (float(sc_eff.get_alpha()) if sc_eff.get_alpha() is not None else None),
                    'visible': bool(getattr(sc_eff, 'get_visible', lambda: True)()),
                    'label': getattr(sc_eff, 'get_label', lambda: 'Coulombic efficiency')() or 'Coulombic efficiency',
                    'marker': '^',
                },
            },
            'legend': {
                'xy_in': getattr(fig, '_cpc_legend_xy_in', None),
                'visible': (bool(ax.get_legend().get_visible()) if ax.get_legend() is not None else False)
            },
            'wasd_state': wasd_state,
            'tick_widths': tick_widths,
            'stored_titles': stored_titles,
            'font': {
                'size': plt.rcParams.get('font.size'),
                'chain': list(plt.rcParams.get('font.sans-serif', [])),
            },
            'grid': ax.xaxis._gridOnMajor if hasattr(ax.xaxis, '_gridOnMajor') else (
                any(line.get_visible() for line in ax.get_xgridlines() + ax.get_ygridlines()) if hasattr(ax, 'get_xgridlines') else False
            ),
        }
        
        # Add multi-file data if available
        if file_data and isinstance(file_data, list) and len(file_data) > 0:
            multi_files = []
            for f in file_data:
                file_info = {
                    'filename': f.get('filename', 'unknown'),
                    'visible': f.get('visible', True),
                    'charge': {
                        'x': _np.array(_scatter_xy(f.get('sc_charge', sc_charge))[0]),
                        'y': _np.array(_scatter_xy(f.get('sc_charge', sc_charge))[1]),
                        'color': _color_of(f.get('sc_charge')),
                    },
                    'discharge': {
                        'x': _np.array(_scatter_xy(f.get('sc_discharge', sc_discharge))[0]),
                        'y': _np.array(_scatter_xy(f.get('sc_discharge', sc_discharge))[1]),
                        'color': _color_of(f.get('sc_discharge')),
                    },
                    'efficiency': {
                        'x': _np.array(_scatter_xy(f.get('sc_eff', sc_eff))[0]),
                        'y': _np.array(_scatter_xy(f.get('sc_eff', sc_eff))[1]),
                        'color': _color_of(f.get('sc_eff')),
                    }
                }
                multi_files.append(file_info)
            meta['multi_files'] = multi_files
        
        if skip_confirm:
            target = filename
        else:
            target = _confirm_overwrite(filename)
            if not target:
                print("CPC session save canceled.")
                return
        with open(target, 'wb') as f:
            pickle.dump(meta, f)
        print(f"CPC session saved to {target}")
    except Exception as e:
        print(f"Error saving CPC session: {e}")


def load_cpc_session(filename: str):
    """Load a CPC session and reconstruct fig, axes, and scatter artists.

    Returns: (fig, ax, ax2, sc_charge, sc_discharge, sc_eff)
    """
    try:
        with open(filename, 'rb') as f:
            sess = pickle.load(f)
    except Exception as e:
        print(f"Failed to load session: {e}")
        return None
    if not isinstance(sess, dict) or sess.get('kind') != 'cpc':
        print("Not a CPC session file.")
        return None
    try:
        # Use standard DPI of 100 instead of saved DPI to avoid display-dependent issues
        # (Retina displays, Windows scaling, etc. can cause saved DPI to differ)
        fig = plt.figure(figsize=tuple(sess['figure']['size']), dpi=100)
        # Disable auto layout
        try:
            fig.set_layout_engine('none')
        except Exception:
            try:
                fig.set_tight_layout(False)
            except Exception:
                pass
        ax = fig.add_subplot(111)
        ax2 = ax.twinx()
        # Fonts
        try:
            f = sess.get('font', {})
            if f.get('chain'):
                plt.rcParams['font.family'] = 'sans-serif'
                plt.rcParams['font.sans-serif'] = f['chain']
            if f.get('size'):
                plt.rcParams['font.size'] = f['size']
        except Exception:
            pass
        # Labels and limits
        ax_meta = sess.get('axis', {})
        try:
            ax.set_xlabel(ax_meta.get('xlabel') or 'Cycle number')
            ax.set_ylabel(ax_meta.get('ylabel_left') or r'Specific Capacity (mAh g$^{-1}$)')
            ax2.set_ylabel(ax_meta.get('ylabel_right') or 'Efficiency (%)')
            if ax_meta.get('xlim'): ax.set_xlim(*ax_meta['xlim'])
            if ax_meta.get('ylim_left'): ax.set_ylim(*ax_meta['ylim_left'])
            if ax_meta.get('ylim_right'): ax2.set_ylim(*ax_meta['ylim_right'])
            # Label pads
            try:
                lp = ax_meta.get('x_labelpad')
                if lp is not None:
                    ax.set_xlabel(ax_meta.get('xlabel') or 'Cycle number', labelpad=float(lp))
            except Exception:
                pass
            try:
                lp = ax_meta.get('y_left_labelpad')
                if lp is not None:
                    ax.set_ylabel(ax_meta.get('ylabel_left') or r'Specific Capacity (mAh g$^{-1}$)', labelpad=float(lp))
            except Exception:
                pass
            try:
                lp = ax_meta.get('y_right_labelpad')
                if lp is not None:
                    ax2.set_ylabel(ax_meta.get('ylabel_right') or 'Efficiency (%)', labelpad=float(lp))
            except Exception:
                pass
        except Exception:
            pass
        # Series
        sr = sess.get('series', {})
        ch = sr.get('charge', {})
        dh = sr.get('discharge', {})
        ef = sr.get('efficiency', {})
        def _mk_sc(axX, rec, default_marker='o'):
            import numpy as _np
            x_val = rec.get('x')
            x = _np.asarray(x_val if x_val is not None else [], float)
            y_val = rec.get('y')
            y = _np.asarray(y_val if y_val is not None else [], float)
            col = rec.get('color') or 'tab:blue'
            s = float(rec.get('size', 32.0) or 32.0)
            alpha = rec.get('alpha', None)
            marker = rec.get('marker', default_marker)
            lab = rec.get('label') or ''
            sc = axX.scatter(x, y, color=col, s=s, alpha=alpha, marker=marker, label=lab, zorder=3)
            try:
                sc.set_visible(bool(rec.get('visible', True)))
            except Exception:
                pass
            return sc
        sc_charge = _mk_sc(ax, ch, 'o')
        sc_discharge = _mk_sc(ax, dh, 'o')
        # efficiency on ax2 with triangles
        if 'marker' not in ef:
            ef['marker'] = '^'
        sc_eff = _mk_sc(ax2, ef, '^')
        
        # Restore spines state (version 2+)
        try:
            if not hasattr(fig, '_cpc_spine_colors') or not isinstance(fig._cpc_spine_colors, dict):
                fig._cpc_spine_colors = {}
            fig_meta = sess.get('figure', {})
            spines_state = fig_meta.get('spines', {})
            for key, props in spines_state.items():
                if key.startswith('ax_'):
                    name = key[3:]  # Remove 'ax_' prefix
                    if name in ax.spines:
                        sp = ax.spines[name]
                        if 'linewidth' in props:
                            sp.set_linewidth(props['linewidth'])
                        if 'color' in props:
                            sp.set_edgecolor(props['color'])
                            if name in ('top','bottom'):
                                ax.tick_params(axis='x', which='both', colors=props['color'])
                                ax.xaxis.label.set_color(props['color'])
                            else:
                                ax.tick_params(axis='y', which='both', colors=props['color'])
                                ax.yaxis.label.set_color(props['color'])
                            fig._cpc_spine_colors[name] = props['color']
                        if 'visible' in props:
                            sp.set_visible(props['visible'])
                elif key.startswith('ax2_'):
                    name = key[4:]  # Remove 'ax2_' prefix
                    if name in ax2.spines:
                        sp = ax2.spines[name]
                        if 'linewidth' in props:
                            sp.set_linewidth(props['linewidth'])
                        if 'color' in props:
                            sp.set_edgecolor(props['color'])
                            ax2.tick_params(axis='y', which='both', colors=props['color'])
                            ax2.yaxis.label.set_color(props['color'])
                            fig._cpc_spine_colors['right' if name == 'right' else name] = props['color']
                        if 'visible' in props:
                            sp.set_visible(props['visible'])
        except Exception:
            pass
        
        # Restore tick widths (version 2+)
        try:
            tick_widths = sess.get('tick_widths', {})
            if tick_widths.get('x_major') is not None:
                ax.tick_params(axis='x', which='major', width=tick_widths['x_major'])
            if tick_widths.get('x_minor') is not None:
                ax.tick_params(axis='x', which='minor', width=tick_widths['x_minor'])
            if tick_widths.get('ly_major') is not None:
                ax.tick_params(axis='y', which='major', width=tick_widths['ly_major'])
            if tick_widths.get('ly_minor') is not None:
                ax.tick_params(axis='y', which='minor', width=tick_widths['ly_minor'])
            if tick_widths.get('ry_major') is not None:
                ax2.tick_params(axis='y', which='major', width=tick_widths['ry_major'])
            if tick_widths.get('ry_minor') is not None:
                ax2.tick_params(axis='y', which='minor', width=tick_widths['ry_minor'])
        except Exception:
            pass
        
        # Restore tick direction (version 2+)
        try:
            tick_direction = sess.get('tick_direction', 'out')
            if tick_direction:
                setattr(fig, '_tick_direction', tick_direction)
                ax.tick_params(axis='both', which='both', direction=tick_direction)
                ax2.tick_params(axis='both', which='both', direction=tick_direction)
        except Exception:
            pass
        
        # Restore grid state
        try:
            grid_enabled = sess.get('grid', False)
            if grid_enabled:
                ax.grid(True, color='0.85', linestyle='-', linewidth=0.5, alpha=0.7)
            else:
                ax.grid(False)
        except Exception:
            pass
        
        # Restore subplot margins/frame size (version 2+)
        try:
            fig_meta = sess.get('figure', {})
            margins = fig_meta.get('subplot_margins', {})
            if margins is not None and isinstance(margins, dict):
                fig.subplots_adjust(
                    left=margins.get('left', 0.125),
                    right=margins.get('right', 0.9),
                    bottom=margins.get('bottom', 0.11),
                    top=margins.get('top', 0.88)
                )
            
            # Restore exact frame size if stored (for precision)
            frame_size = fig_meta.get('frame_size')
            if frame_size and isinstance(frame_size, (list, tuple)) and len(frame_size) == 2:
                target_w_in, target_h_in = map(float, frame_size)
                # Get current canvas size
                canvas_w_in, canvas_h_in = fig.get_size_inches()
                # Calculate needed fractions to achieve exact frame size
                if canvas_w_in > 0 and canvas_h_in > 0:
                    # Get current position to preserve centering
                    bbox = ax.get_position()
                    center_x = (bbox.x0 + bbox.x1) / 2.0
                    center_y = (bbox.y0 + bbox.y1) / 2.0
                    # Calculate new fractions
                    new_w_frac = target_w_in / canvas_w_in
                    new_h_frac = target_h_in / canvas_h_in
                    # Reposition to maintain centering
                    new_left = center_x - new_w_frac / 2.0
                    new_right = center_x + new_w_frac / 2.0
                    new_bottom = center_y - new_h_frac / 2.0
                    new_top = center_y + new_h_frac / 2.0
                    # Apply
                    fig.subplots_adjust(left=new_left, right=new_right, bottom=new_bottom, top=new_top)
        except Exception:
            pass
        
        # Restore WASD state (version 2+)
        try:
            wasd_state = sess.get('wasd_state', {})
            if wasd_state is not None and isinstance(wasd_state, dict) and wasd_state:
                # Store on figure for interactive menu
                fig._cpc_wasd_state = wasd_state
                
                # Apply WASD state
                from matplotlib.ticker import AutoMinorLocator, NullFormatter
                
                # Spines
                if 'top' in wasd_state:
                    ax.spines['top'].set_visible(wasd_state['top'].get('spine', False))
                    ax2.spines['top'].set_visible(wasd_state['top'].get('spine', False))
                if 'bottom' in wasd_state:
                    ax.spines['bottom'].set_visible(wasd_state['bottom'].get('spine', True))
                    ax2.spines['bottom'].set_visible(wasd_state['bottom'].get('spine', True))
                if 'left' in wasd_state:
                    ax.spines['left'].set_visible(wasd_state['left'].get('spine', True))
                if 'right' in wasd_state:
                    ax2.spines['right'].set_visible(wasd_state['right'].get('spine', True))
                
                # Tick visibility
                if 'top' in wasd_state and 'bottom' in wasd_state:
                    ax.tick_params(axis='x',
                                   top=wasd_state['top'].get('ticks', False),
                                   bottom=wasd_state['bottom'].get('ticks', True),
                                   labeltop=wasd_state['top'].get('labels', False),
                                   labelbottom=wasd_state['bottom'].get('labels', True))
                if 'left' in wasd_state:
                    ax.tick_params(axis='y',
                                   left=wasd_state['left'].get('ticks', True),
                                   labelleft=wasd_state['left'].get('labels', True))
                if 'right' in wasd_state:
                    ax2.tick_params(axis='y',
                                    right=wasd_state['right'].get('ticks', True),
                                    labelright=wasd_state['right'].get('labels', True))
                
                # Minor ticks
                if wasd_state.get('top', {}).get('minor') or wasd_state.get('bottom', {}).get('minor'):
                    ax.xaxis.set_minor_locator(AutoMinorLocator())
                    ax.xaxis.set_minor_formatter(NullFormatter())
                    ax.tick_params(axis='x', which='minor',
                                   top=wasd_state.get('top', {}).get('minor', False),
                                   bottom=wasd_state.get('bottom', {}).get('minor', False))
                if wasd_state.get('left', {}).get('minor'):
                    ax.yaxis.set_minor_locator(AutoMinorLocator())
                    ax.yaxis.set_minor_formatter(NullFormatter())
                    ax.tick_params(axis='y', which='minor', left=True)
                if wasd_state.get('right', {}).get('minor'):
                    ax2.yaxis.set_minor_locator(AutoMinorLocator())
                    ax2.yaxis.set_minor_formatter(NullFormatter())
                    ax2.tick_params(axis='y', which='minor', right=True)
        except Exception:
            pass
        
        # Restore tick widths (version 2+)
        try:
            tw = sess.get('tick_widths', {})
            if tw:
                if tw.get('x_major') is not None:
                    ax.tick_params(axis='x', which='major', width=float(tw['x_major']))
                if tw.get('x_minor') is not None:
                    ax.tick_params(axis='x', which='minor', width=float(tw['x_minor']))
                if tw.get('ly_major') is not None:
                    ax.tick_params(axis='y', which='major', width=float(tw['ly_major']))
                if tw.get('ly_minor') is not None:
                    ax.tick_params(axis='y', which='minor', width=float(tw['ly_minor']))
                if tw.get('ry_major') is not None:
                    ax2.tick_params(axis='y', which='major', width=float(tw['ry_major']))
                if tw.get('ry_minor') is not None:
                    ax2.tick_params(axis='y', which='minor', width=float(tw['ry_minor']))
        except Exception:
            pass
        
        # Restore stored title texts (version 2+)
        try:
            stored_titles = sess.get('stored_titles', {})
            if stored_titles is not None and isinstance(stored_titles, dict) and stored_titles:
                ax._stored_xlabel = stored_titles.get('xlabel', '')
                ax._stored_ylabel = stored_titles.get('ylabel', '')
                ax._stored_top_xlabel = stored_titles.get('top_xlabel', '')
                ax2._stored_ylabel = stored_titles.get('right_ylabel', '')
                
                # Create top xlabel text if it was visible
                if wasd_state.get('top', {}).get('title') and ax._stored_top_xlabel:
                    ax._top_xlabel_text = ax.text(0.5, 1.02, ax._stored_top_xlabel,
                                                   transform=ax.transAxes,
                                                   ha='center', va='bottom',
                                                   fontsize=ax.xaxis.label.get_fontsize(),
                                                   fontfamily=ax.xaxis.label.get_fontfamily())
        except Exception:
            pass
        
        # Legend
        try:
            handles1, labels1 = ax.get_legend_handles_labels()
            handles2, labels2 = ax2.get_legend_handles_labels()
            if handles1 or handles2:
                leg_meta = sess.get('legend', {})
                xy_in = leg_meta.get('xy_in')
                if xy_in is not None:
                    fw, fh = fig.get_size_inches()
                    fx = 0.5 + float(xy_in[0]) / float(fw)
                    fy = 0.5 + float(xy_in[1]) / float(fh)
                    ax.legend(handles1 + handles2, labels1 + labels2, loc='center', bbox_to_anchor=(fx, fy), bbox_transform=fig.transFigure, borderaxespad=1.0)
                    # persist inches on fig for interactive menu
                    try:
                        fig._cpc_legend_xy_in = (float(xy_in[0]), float(xy_in[1]))
                    except Exception:
                        pass
                else:
                    ax.legend(handles1 + handles2, labels1 + labels2, loc='best', borderaxespad=1.0)
                # Apply visibility
                vis = bool(leg_meta.get('visible', True))
                leg = ax.get_legend()
                if leg is not None:
                    leg.set_visible(vis)
        except Exception:
            pass
        try:
            fig.canvas.draw()
        except Exception:
            try:
                fig.canvas.draw_idle()
            except Exception:
                pass
        return fig, ax, ax2, sc_charge, sc_discharge, sc_eff
    except Exception as e:
        import traceback
        print(f"Error loading CPC session: {e}")
        traceback.print_exc()
        return None

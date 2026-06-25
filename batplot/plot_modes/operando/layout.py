"""Layout and custom colorbar helpers for operando interactive plots."""

from __future__ import annotations

import sys
from typing import Dict, Tuple

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

from .plot import _draw_operando_cif_ticks


def _finalize_operando_session_axes(fig, ax, ec_ax=None) -> None:
    """Re-apply axis title spacing after loading an operando+EC session.

    Older sessions stored small labelpad values that overlap tick labels at
    larger font sizes, and the EC side panel often saved right tick/label
    visibility as false while the y-axis title was still shown on the right.
    """
    from ...ui import (
        position_bottom_xlabel,
        position_left_ylabel,
        position_right_ylabel,
        position_top_xlabel,
    )
    from ..common.spines import keep_yaxis_label_on_side

    op_ts = dict(getattr(ax, '_saved_tick_state', {}) or {})
    if ax.get_xlabel():
        position_bottom_xlabel(ax, fig, op_ts)
    if getattr(ax, '_top_xlabel_on', False):
        position_top_xlabel(ax, fig, op_ts)
    if ax.get_ylabel():
        position_left_ylabel(ax, fig, op_ts)
    if getattr(ax, '_right_ylabel_on', False):
        position_right_ylabel(ax, fig, op_ts)

    if ec_ax is None:
        return

    ec_ts = dict(getattr(ec_ax, '_saved_tick_state', {}) or {})
    r_ticks = bool(ec_ts.get('r_ticks', ec_ts.get('ry', False)))
    r_labels = bool(ec_ts.get('r_labels', ec_ts.get('ry', False)))
    l_ticks = bool(ec_ts.get('l_ticks', ec_ts.get('ly', False)))
    l_labels = bool(ec_ts.get('l_labels', ec_ts.get('ly', False)))
    try:
        if r_ticks or r_labels:
            ec_ax.yaxis.tick_right()
        ec_ax.yaxis.set_label_position('right')
        ec_ax.tick_params(
            axis='y',
            left=l_ticks,
            right=r_ticks,
            labelleft=l_labels,
            labelright=r_labels,
        )
    except Exception:
        pass
    if ec_ax.get_xlabel():
        position_bottom_xlabel(ec_ax, fig, ec_ts)
    if getattr(ec_ax, '_top_xlabel_on', False):
        position_top_xlabel(ec_ax, fig, ec_ts)
    if ec_ax.get_ylabel():
        keep_yaxis_label_on_side(ec_ax, 'right', visible=True)
    dup = getattr(ec_ax, '_right_ylabel_artist', None)
    if dup is not None:
        try:
            dup.set_visible(False)
        except Exception:
            pass


def _get_fig_size(fig) -> Tuple[float, float]:
    """Get the figure size in inches."""
    width, height = fig.get_size_inches()
    return float(width), float(height)


def _get_geometry_snapshot(ax, ec_ax) -> Dict:
    """Collect a snapshot of current operando / EC axes geometry settings."""
    snapshot = {
        'operando': {
            'xlim': list(ax.get_xlim()),
            'ylim': list(ax.get_ylim()),
            'xlabel': ax.get_xlabel() or '',
            'ylabel': ax.get_ylabel() or '',
        }
    }
    if ec_ax is not None:
        snapshot['ec'] = {
            'xlim': list(ec_ax.get_xlim()),
            'ylim': list(ec_ax.get_ylim()),
            'xlabel': ec_ax.get_xlabel() or '',
            'ylabel': ec_ax.get_ylabel() or '',
        }
    return snapshot


def _draw_custom_colorbar(cbar_ax, im, label='Intensity', label_mode='highlow'):
    """Draw batplot's fixed-width custom colorbar."""
    cbar_ax.clear()
    cmap = im.get_cmap()
    vmin, vmax = im.get_clim()
    fontsize = plt.rcParams.get('font.size', 16)
    fontfamily = plt.rcParams.get('font.family', ['sans-serif'])
    if isinstance(fontfamily, list):
        fontfamily = fontfamily[0] if fontfamily else 'sans-serif'

    n_steps = 256
    if vmax < vmin:
        vmin, vmax = vmax, vmin
    gradient = np.linspace(vmin, vmax, n_steps).reshape(n_steps, 1)
    fig = cbar_ax.figure
    for attr in ('_cbar_high_text', '_cbar_low_text'):
        if hasattr(fig, attr):
            try:
                getattr(fig, attr).remove()
            except Exception:
                pass
            try:
                delattr(fig, attr)
            except Exception:
                pass

    cbar_ax.imshow(
        gradient, aspect='auto', cmap=cmap, extent=[0, 1, vmin, vmax],
        interpolation='nearest', origin='lower',
    )
    cbar_ax.set_xlim(0, 1)
    cbar_ax.set_ylim(vmin, vmax)
    cbar_ax.set_xticks([])
    cbar_ax.yaxis.set_ticks_position('left')
    cbar_ax.yaxis.set_label_position('left')

    if label_mode == 'highlow':
        cbar_ax.set_yticks([])
        cbar_ax.set_yticklabels([])
        v_offset = 0.02
        high_text = cbar_ax.text(
            0.5, 1.0 + v_offset, 'High', ha='center', va='bottom',
            transform=cbar_ax.transAxes, fontsize=fontsize, fontfamily=fontfamily,
        )
        low_text = cbar_ax.text(
            0.5, 0.0 - v_offset, 'Low', ha='center', va='top',
            transform=cbar_ax.transAxes, fontsize=fontsize, fontfamily=fontfamily,
        )
        fig._cbar_high_text = high_text
        fig._cbar_low_text = low_text
    else:
        cbar_ax.yaxis.set_major_locator(MaxNLocator(nbins=5, prune='both'))
        cbar_ax.tick_params(axis='y', labelsize=fontsize, left=True, labelleft=True)
        for tick_label in cbar_ax.get_yticklabels():
            tick_label.set_fontfamily(fontfamily)

    label_text = str(label) if label is not None else 'Intensity'
    cbar_ax.set_ylabel(
        label_text, fontsize=fontsize, fontfamily=fontfamily,
        rotation=90, va='center', ha='center', labelpad=10,
    )
    cbar_ax._colorbar_im = im
    cbar_ax._colorbar_label = label_text
    cbar_ax._colorbar_label_mode = label_mode


def _update_custom_colorbar(cbar_ax, im=None, label=None, label_mode=None):
    """Update the custom colorbar from stored references/defaults."""
    if im is None:
        im = getattr(cbar_ax, '_colorbar_im', None)
        if im is None:
            return
    if label is None:
        label = getattr(cbar_ax, '_colorbar_label', 'Intensity')
    if label_mode is None:
        label_mode = getattr(cbar_ax, '_colorbar_label_mode', 'highlow')
    _draw_custom_colorbar(cbar_ax, im, label, label_mode)


def _safe_set_clim(im, vmin, vmax):
    """Safely set color limits while suppressing known matplotlib colorbar errors."""

    class NullDevice:
        def write(self, s):
            pass

        def flush(self):
            pass

        def close(self):
            pass

    old_stderr = sys.stderr
    old_excepthook = sys.excepthook
    null_dev = NullDevice()

    def suppress_excepthook(exc_type, exc_value, exc_traceback):
        if exc_type == NotImplementedError and 'cannot remove artist' in str(exc_value).lower():
            return
        old_excepthook(exc_type, exc_value, exc_traceback)

    sys.stderr = null_dev
    sys.excepthook = suppress_excepthook
    try:
        im.set_clim(vmin, vmax)
    except NotImplementedError:
        pass
    except Exception:
        sys.stderr = old_stderr
        sys.excepthook = old_excepthook
        raise
    finally:
        sys.stderr = old_stderr
        sys.excepthook = old_excepthook


def _detach_mpl_colorbar_callbacks(cbar, im) -> None:
    """Detach a built-in Matplotlib Colorbar from mappable callbacks."""
    try:
        if cbar is None or im is None:
            return
        cax = getattr(cbar, 'ax', None)
        if cax is not None and getattr(cax, '_bp_detached_mpl_colorbar', False):
            return

        cid = None
        for attr in ('_cid', '_cid_colorbar', 'cid'):
            try:
                value = getattr(cbar, attr, None)
                if isinstance(value, int):
                    cid = value
                    break
            except Exception:
                pass
        if cid is not None:
            try:
                cbreg = getattr(im, 'callbacksSM', None)
                if cbreg is not None and hasattr(cbreg, 'disconnect'):
                    cbreg.disconnect(cid)
            except Exception:
                pass

        try:
            cbreg = getattr(im, 'callbacksSM', None)
            if cbreg is not None:
                if hasattr(cbreg, 'callbacks'):
                    try:
                        cbreg.callbacks.clear()
                    except Exception:
                        pass
                if hasattr(cbreg, '_signals'):
                    try:
                        for signal_dict in cbreg._signals.values():
                            if hasattr(signal_dict, 'clear'):
                                signal_dict.clear()
                    except Exception:
                        pass
        except Exception:
            pass

        try:
            if hasattr(cbar, 'update_normal'):
                def _noop_update(*args, **kwargs):
                    pass
                cbar.update_normal = _noop_update
        except Exception:
            pass
        try:
            if hasattr(cbar, 'mappable'):
                cbar.mappable = None
        except Exception:
            pass
        try:
            if hasattr(cbar, 'solids'):
                cbar.solids = None
        except Exception:
            pass
        if cax is not None:
            setattr(cax, '_bp_detached_mpl_colorbar', True)
    except Exception:
        return


def _ensure_fixed_params(fig, ax, cbar_ax, ec_ax):
    """Initialize and return fixed geometry parameters in inches."""
    fig_width_in, fig_height_in = _get_fig_size(fig)
    ax_x0, ax_y0, ax_width_frac, ax_height_frac = ax.get_position().bounds
    cb_x0, cb_y0, cb_width_frac, cb_height_frac = cbar_ax.get_position().bounds

    colorbar_width_in = getattr(cbar_ax, '_fixed_cb_w_in', cb_width_frac * fig_width_in)
    colorbar_gap_in = getattr(
        cbar_ax, '_fixed_cb_gap_in',
        (ax_x0 - (cb_x0 + cb_width_frac)) * fig_width_in,
    )
    axes_width_in = getattr(ax, '_fixed_ax_w_in', ax_width_frac * fig_width_in)
    axes_height_in = getattr(ax, '_fixed_ax_h_in', ax_height_frac * fig_height_in)

    if ec_ax is not None:
        ec_x0, ec_y0, ec_width_frac, ec_height_frac = ec_ax.get_position().bounds
        ec_gap_in = getattr(
            ec_ax, '_fixed_ec_gap_in',
            (ec_x0 - (ax_x0 + ax_width_frac)) * fig_width_in,
        )
        ec_width_in = getattr(ec_ax, '_fixed_ec_w_in', ec_width_frac * fig_width_in)
    else:
        ec_gap_in = 0.0
        ec_width_in = 0.0

    return (
        colorbar_width_in, colorbar_gap_in, ec_gap_in, ec_width_in,
        axes_width_in, axes_height_in,
    )


def _redraw_operando_cif_if_present(fig, ax):
    """Redraw CIF tick labels if present. Call after xlim or layout changes."""
    try:
        if not getattr(ax, '_operando_cif_tick_series', None):
            return
        cif_series = ax._operando_cif_tick_series
        cif_hkl_map = getattr(ax, '_operando_cif_hkl_label_map', {})
        axis_mode = getattr(fig, '_operando_axis_mode', '2theta')
        wl = getattr(fig, '_operando_wl', None)
        show_hkl = getattr(fig, '_operando_cif_show_hkl', False)
        show_titles = getattr(fig, '_operando_cif_show_titles', True)
        placement = getattr(fig, '_operando_cif_placement', 'below')
        y_positions = list(getattr(fig, '_operando_cif_y_positions', []))
        ax_pos = ax.get_position()
        y_base = ax_pos.ymin - 0.02 if placement == 'below' else ax_pos.ymax + 0.02
        dy = -0.025 if placement == 'below' else 0.025
        while len(y_positions) < len(cif_series):
            y_positions.append(y_base + len(y_positions) * dy)
        fig._operando_cif_y_positions = y_positions
        _draw_operando_cif_ticks(
            ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl,
            show_hkl=show_hkl, show_titles=show_titles, placement=placement,
            y_positions=y_positions,
        )
    except Exception:
        pass


def _apply_group_layout_inches(
    fig, ax, cbar_ax, ec_ax,
    ax_width_in: float, ax_height_in: float,
    colorbar_width_in: float, colorbar_gap_in: float,
    ec_gap_in: float, ec_width_in: float,
):
    """Position colorbar, operando panel, and optional EC panel by inch values."""
    fig_width_in, fig_height_in = _get_fig_size(fig)
    cb_h_offset_in = getattr(cbar_ax, '_cb_h_offset_in', 0.0)
    ec_h_offset_in = getattr(ec_ax, '_ec_h_offset_in', 0.0) if ec_ax is not None else 0.0

    ax_width_frac = max(0.0, ax_width_in / fig_width_in)
    ax_height_frac = max(0.0, ax_height_in / fig_height_in)
    colorbar_width_frac = max(0.0, colorbar_width_in / fig_width_in)
    colorbar_gap_frac = max(0.0, colorbar_gap_in / fig_width_in)
    cb_h_offset_frac = cb_h_offset_in / fig_width_in
    ec_h_offset_frac = ec_h_offset_in / fig_width_in

    if ec_ax is not None:
        ec_gap_frac = max(0.0, ec_gap_in / fig_width_in)
        ec_width_frac = max(0.0, ec_width_in / fig_width_in)
        total_width_frac = (
            colorbar_width_frac + colorbar_gap_frac
            + ax_width_frac + ec_gap_frac + ec_width_frac
        )
    else:
        ec_gap_frac = 0.0
        ec_width_frac = 0.0
        total_width_frac = colorbar_width_frac + colorbar_gap_frac + ax_width_frac

    group_left_edge = 0.5 - total_width_frac / 2.0
    vertical_center = 0.5 - ax_height_frac / 2.0
    base_colorbar_x0 = group_left_edge
    base_operando_x0 = base_colorbar_x0 + colorbar_width_frac + colorbar_gap_frac
    colorbar_height_frac = ax_height_frac

    colorbar_x0 = base_colorbar_x0 + cb_h_offset_frac
    operando_x0 = base_operando_x0
    ec_x0 = None
    if ec_ax is not None:
        base_ec_x0 = base_operando_x0 + ax_width_frac + ec_gap_frac
        ec_x0 = base_ec_x0 + ec_h_offset_frac

    ax.set_position([operando_x0, vertical_center, ax_width_frac, ax_height_frac])
    cbar_ax.set_position([colorbar_x0, vertical_center, colorbar_width_frac, colorbar_height_frac])
    if ec_ax is not None and ec_x0 is not None:
        ec_ax.set_position([ec_x0, vertical_center, ec_width_frac, ax_height_frac])

    setattr(cbar_ax, '_fixed_cb_w_in', colorbar_width_in)
    setattr(cbar_ax, '_fixed_cb_gap_in', colorbar_gap_in)
    if ec_ax is not None:
        setattr(ec_ax, '_fixed_ec_gap_in', ec_gap_in)
        setattr(ec_ax, '_fixed_ec_w_in', ec_width_in)
    setattr(ax, '_fixed_ax_w_in', ax_width_in)
    setattr(ax, '_fixed_ax_h_in', ax_height_in)

    try:
        if hasattr(cbar_ax, '_colorbar_im'):
            _update_custom_colorbar(cbar_ax)
    except Exception:
        pass

    _redraw_operando_cif_if_present(fig, ax)
    try:
        fig.canvas.draw()
    except Exception:
        fig.canvas.draw_idle()

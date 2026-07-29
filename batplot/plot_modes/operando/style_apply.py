"""Apply operando+EC style/geometry configuration from dict."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
from matplotlib.ticker import AutoMinorLocator, NullFormatter, NullLocator  # type: ignore[import-untyped]

from ...ui import (
    position_bottom_xlabel as _ui_position_bottom_xlabel,
    position_left_ylabel as _ui_position_left_ylabel,
    position_right_ylabel as _ui_position_right_ylabel,
    position_top_xlabel as _ui_position_top_xlabel,
    set_spine_side_color as _ui_set_spine_side_color,
    finalize_spine_colors_for_axes,
)
from ..common.spines import keep_yaxis_label_on_side
from ..common.title_offsets import restore_title_offsets
from .ions_axis import install_ec_ions_y_display
from .layout import (
    _apply_group_layout_inches,
    _ensure_fixed_params,
    _safe_set_clim,
    _update_custom_colorbar,
)
from .plot import _draw_operando_cif_ticks
from .interactive import _maybe_reapply_dqdv_2d_contour, _restore_dqdv_2d_operando_labels
from .actions import _apply_tick_lengths, _apply_tick_style


from ..common.font_extras import apply_font_extras_from_cfg, apply_session_font_cfg
from ..common.fonts import collect_operando_font_artists


def _apply_operando_fonts(family, size) -> None:
    try:
        if family:
            fam = family if isinstance(family, str) else str(family)
            plt.rcParams['font.sans-serif'] = [fam]
            plt.rcParams['font.family'] = 'sans-serif'
        if size is not None:
            plt.rcParams['font.size'] = float(size)
    except Exception:
        pass


def _restore_dqdv_2d_cfg(fig, cfg: Dict[str, Any]) -> None:
    d2_cfg = cfg.get('dqdv_2d')
    if d2_cfg and isinstance(d2_cfg, dict) and getattr(fig, '_is_dqdv_2d_contour', False):
        try:
            fig._dqdv_2d_v_lo = float(d2_cfg['v_lo'])
            fig._dqdv_2d_v_hi = float(d2_cfg['v_hi'])
            fig._dqdv_2d_row_labels = [str(s) for s in (d2_cfg.get('row_labels') or [])]
            if d2_cfg.get('zlabel') is not None:
                fig._dqdv_2d_zlabel = str(d2_cfg['zlabel'])
            fig._dqdv_2d_axis_mapping_version = int(d2_cfg.get('axis_mapping_version', 2))
        except Exception:
            pass


def _save_labelpads(ax, ec_ax) -> Tuple[Any, Any, Any, Any]:
    saved_op_xlabelpad = None
    saved_op_ylabelpad = None
    saved_ec_xlabelpad = None
    saved_ec_ylabelpad = None
    try:
        saved_op_xlabelpad = getattr(ax.xaxis, 'labelpad', None)
    except Exception:
        pass
    try:
        saved_op_ylabelpad = getattr(ax.yaxis, 'labelpad', None)
    except Exception:
        pass
    if ec_ax is not None:
        try:
            saved_ec_xlabelpad = getattr(ec_ax.xaxis, 'labelpad', None)
        except Exception:
            pass
        try:
            saved_ec_ylabelpad = getattr(ec_ax.yaxis, 'labelpad', None)
        except Exception:
            pass
    return saved_op_xlabelpad, saved_op_ylabelpad, saved_ec_xlabelpad, saved_ec_ylabelpad


def _apply_fonts_and_canvas(fig, ax, ec_ax, cbar, cfg: Dict[str, Any]) -> None:
    # Fonts
    font = cfg.get('font', {})
    fam = font.get('family')
    size = font.get('size')
    mathtext_fs = font.get('mathtext_fontset')
    if mathtext_fs:
        try:
            plt.rcParams['mathtext.fontset'] = mathtext_fs
        except Exception:
            pass
    if fam or size is not None:
        try:
            _apply_operando_fonts(fam, size)
        except Exception:
            pass
    try:
        apply_font_extras_from_cfg(
            fig,
            collect_operando_font_artists(fig, ax, ec_ax, cbar),
            font,
        )
    except Exception:
        pass

    # Canvas - support both 'size' (v1) and 'canvas_size' (v2)
    fig_cfg = cfg.get('figure', {})
    fig_sz = fig_cfg.get('canvas_size') or fig_cfg.get('size')
    if isinstance(fig_sz, (list, tuple)) and len(fig_sz) == 2:
        try:
            W = max(1.0, float(fig_sz[0])); H = max(1.0, float(fig_sz[1]))
            fig.set_size_inches(W, H, forward=True)
        except Exception:
            pass


def _apply_geometry_inches(
    fig,
    ax,
    cbar,
    ec_ax,
    cfg: Dict[str, Any],
    version,
    cb_w_in,
    cb_gap_in,
    ec_gap_in,
    ec_w_in,
    ax_w_in,
    ax_h_in,
) -> None:
    # Geometry inches
    # v1: stored in operando/ec/gaps sub-dicts
    # v2: stored in geometry dict
    if version >= 2:
        geom = cfg.get('geometry', {})
        if geom:
            try:
                new_op_w = geom.get('op_w_in')
                new_op_h = geom.get('op_h_in')
                new_ec_w = geom.get('ec_w_in')
                if new_op_w is not None:
                    ax_w_in = max(0.25, float(new_op_w))
                if new_op_h is not None:
                    ax_h_in = max(0.25, float(new_op_h))
                if new_ec_w is not None:
                    ec_w_in = max(0.25, float(new_ec_w))
                new_cb_w = geom.get('cb_w_in')
                new_cb_gap = geom.get('cb_gap_in')
                new_ec_gap = geom.get('ec_gap_in')
                if new_cb_w is not None:
                    cb_w_in = max(0.05, float(new_cb_w))
                if new_cb_gap is not None:
                    cb_gap_in = max(0.0, float(new_cb_gap))
                if new_ec_gap is not None:
                    ec_gap_in = max(0.0, float(new_ec_gap))
                # Restore horizontal offsets
                cb_h_offset = geom.get('cb_h_offset', 0.0)
                ec_h_offset = geom.get('ec_h_offset')
                setattr(cbar.ax, '_cb_h_offset_in', float(cb_h_offset))
                if ec_ax is not None:
                    if ec_h_offset is not None:
                        setattr(ec_ax, '_ec_h_offset_in', float(ec_h_offset))
                    else:
                        setattr(ec_ax, '_ec_h_offset_in', 0.0)
                _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)
            except Exception as e:
                print(f"Warning: Could not apply geometry: {e}")
    elif version == 1:
        cb_w_in, cb_gap_in, ec_gap_in_cur, ec_w_in_cur, ax_w_in_cur, ax_h_in_cur = _ensure_fixed_params(fig, ax, cbar.ax, ec_ax)
        op = cfg.get('operando', {})
        ec_cfg = cfg.get('ec', {})
        gaps = cfg.get('gaps', {})
        ax_w_in = float(op.get('ax_w_in', ax_w_in_cur))
        ax_h_in = float(op.get('ax_h_in', ax_h_in_cur))
        ec_w_in = float(ec_cfg.get('ec_w_in', ec_w_in_cur))
        cb_w_in = float(gaps.get('cb_w_in', cb_w_in))
        cb_gap_in = float(gaps.get('cb_gap_in', cb_gap_in))
        ec_gap_in = float(gaps.get('ec_gap_in', ec_gap_in_cur))
        _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)


def _apply_colormap_and_custom_labels(ax, im, cbar, op: Dict[str, Any]) -> None:
    # Colormap
    cmap = op.get('cmap')
    if cmap:
        try:
            im.set_cmap(cmap)
            # Store the colormap name explicitly so it can be retrieved reliably when saving
            setattr(im, '_operando_cmap_name', cmap)
            if cbar is not None:
                _update_custom_colorbar(cbar.ax, im)
        except Exception:
            pass

    op_custom = op.get('custom_labels')
    if isinstance(op_custom, dict):
        setattr(ax, '_custom_labels', dict(op_custom))
        if op_custom.get('x'):
            ax.set_xlabel(str(op_custom['x']))
        if op_custom.get('y'):
            ax.set_ylabel(str(op_custom['y']))


def _apply_operando_wasd_spines_ticks(fig, ax, op: Dict[str, Any], version) -> None:
    # Apply operando WASD state (v2)
    if version >= 2:
        op_wasd = op.get('wasd_state')
        if op_wasd and isinstance(op_wasd, dict):
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
                else:
                    # Clear minor locator if no minor ticks are enabled
                    ax.xaxis.set_minor_locator(NullLocator())
                    ax.xaxis.set_minor_formatter(NullFormatter())
                ax.tick_params(axis='x', which='minor',
                              top=bool(op_wasd.get('top', {}).get('minor', False)),
                              bottom=bool(op_wasd.get('bottom', {}).get('minor', False)))
                if op_wasd.get('left', {}).get('minor') or op_wasd.get('right', {}).get('minor'):
                    ax.yaxis.set_minor_locator(AutoMinorLocator())
                    ax.yaxis.set_minor_formatter(NullFormatter())
                else:
                    # Clear minor locator if no minor ticks are enabled
                    ax.yaxis.set_minor_locator(NullLocator())
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
                # Apply titles
                ax._top_xlabel_on = bool(op_wasd.get('top', {}).get('title', False))
                ax._right_ylabel_on = bool(op_wasd.get('right', {}).get('title', False))
                ax.xaxis.label.set_visible(bool(op_wasd.get('bottom', {}).get('title', True)))
                ax.yaxis.label.set_visible(bool(op_wasd.get('left', {}).get('title', True)))
            except Exception as e:
                print(f"Warning: Could not apply operando WASD state: {e}")

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
                            _ui_set_spine_side_color(ax, name, props['color'], fig=fig)
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
        _apply_tick_lengths(fig, ax, op.get('ticks', {}).get('lengths'))
        _apply_tick_style(fig, ax, op.get('ticks', {}))


def _apply_ec_wasd_spines_ticks_curve(fig, ec_ax, cfg: Dict[str, Any], version) -> None:
    # Apply EC WASD state (v2, only if EC panel exists)
    if version >= 2 and ec_ax is not None:
        ec_cfg = cfg.get('ec', {})
        ec_wasd = ec_cfg.get('wasd_state')
        if ec_wasd and isinstance(ec_wasd, dict):
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
                                 left=False,
                                 right=bool(ec_wasd.get('right', {}).get('ticks', True)),
                                 labelleft=False,
                                 labelright=bool(ec_wasd.get('right', {}).get('labels', True)))
                # Apply minor ticks
                if ec_wasd.get('top', {}).get('minor') or ec_wasd.get('bottom', {}).get('minor'):
                    ec_ax.xaxis.set_minor_locator(AutoMinorLocator())
                    ec_ax.xaxis.set_minor_formatter(NullFormatter())
                else:
                    # Clear minor locator if no minor ticks are enabled
                    ec_ax.xaxis.set_minor_locator(NullLocator())
                    ec_ax.xaxis.set_minor_formatter(NullFormatter())
                ec_ax.tick_params(axis='x', which='minor',
                                 top=bool(ec_wasd.get('top', {}).get('minor', False)),
                                 bottom=bool(ec_wasd.get('bottom', {}).get('minor', False)))
                if ec_wasd.get('left', {}).get('minor') or ec_wasd.get('right', {}).get('minor'):
                    ec_ax.yaxis.set_minor_locator(AutoMinorLocator())
                    ec_ax.yaxis.set_minor_formatter(NullFormatter())
                else:
                    # Clear minor locator if no minor ticks are enabled
                    ec_ax.yaxis.set_minor_locator(NullLocator())
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
                # Apply titles
                ec_ax._top_xlabel_on = bool(ec_wasd.get('top', {}).get('title', False))
                ec_ax._right_ylabel_on = bool(ec_wasd.get('right', {}).get('title', False))
                ec_ax.xaxis.label.set_visible(bool(ec_wasd.get('bottom', {}).get('title', True)))
                ec_right_title = bool(ec_wasd.get('right', {}).get('title', True))
                if ec_right_title:
                    if not ec_ax.get_ylabel() and hasattr(ec_ax, '_stored_ylabel'):
                        ec_ax.set_ylabel(ec_ax._stored_ylabel)
                else:
                    if not hasattr(ec_ax, '_stored_ylabel'):
                        ec_ax._stored_ylabel = ec_ax.get_ylabel()
                    ec_ax.set_ylabel('')
            except Exception as e:
                print(f"Warning: Could not apply EC WASD state: {e}")

        # Apply EC spines
        ec_spines = ec_cfg.get('spines', {})
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
                            _ui_set_spine_side_color(ec_ax, name, props['color'], fig=fig)
                        except Exception:
                            pass
            except Exception:
                pass

        # Apply EC tick widths
        ec_tick_widths = ec_cfg.get('ticks', {}).get('widths', {})
        if ec_tick_widths:
            try:
                if ec_tick_widths.get('x_major'): ec_ax.tick_params(axis='x', which='major', width=ec_tick_widths['x_major'])
                if ec_tick_widths.get('x_minor'): ec_ax.tick_params(axis='x', which='minor', width=ec_tick_widths['x_minor'])
                if ec_tick_widths.get('y_major'): ec_ax.tick_params(axis='y', which='major', width=ec_tick_widths['y_major'])
                if ec_tick_widths.get('y_minor'): ec_ax.tick_params(axis='y', which='minor', width=ec_tick_widths['y_minor'])
            except Exception:
                pass
        _apply_tick_lengths(fig, ec_ax, ec_cfg.get('ticks', {}).get('lengths'))
        _apply_tick_style(fig, ec_ax, ec_cfg.get('ticks', {}))

        # Apply EC curve properties (el command)
        ec_curve = ec_cfg.get('curve', {})
        if ec_curve:
            ln = getattr(ec_ax, '_ec_line', None)
            if ln is None and ec_ax.lines:
                ln = ec_ax.lines[0]
            if ln is not None:
                try:
                    if 'color' in ec_curve:
                        ln.set_color(ec_curve['color'])
                    if 'linewidth' in ec_curve:
                        ln.set_linewidth(float(ec_curve['linewidth']))
                except Exception as e:
                    print(f"Warning: Could not apply EC curve properties: {e}")


def _finalize_spine_colors(fig, ax, ec_ax) -> None:
    try:
        axis_entries = [(ax, getattr(ax, '_saved_tick_state', None))]
        if ec_ax is not None:
            axis_entries.append((ec_ax, getattr(ec_ax, '_saved_tick_state', None)))
        finalize_spine_colors_for_axes(fig, axis_entries)
    except Exception:
        pass


def _apply_reverse_intensity_cif_ions(
    fig,
    ax,
    im,
    ec_ax,
    cfg: Dict[str, Any],
    op: Dict[str, Any],
    *,
    silent: bool,
) -> Optional[bool]:
    """Apply reverse, intensity, CIF, and ions. Returns False to abort; None to continue."""
    # Apply reverse state (r command)
    try:
        # Operando Y-axis reverse
        op_y_reversed = op.get('y_reversed', False)
        if op_y_reversed:
            y0, y1 = ax.get_ylim()
            if y0 < y1:  # Only reverse if not already reversed
                ax.set_ylim(y1, y0)
        else:
            y0, y1 = ax.get_ylim()
            if y0 > y1:  # Un-reverse if currently reversed
                ax.set_ylim(y1, y0)
    except Exception as e:
        print(f"Warning: Could not apply operando reverse: {e}")

    if ec_ax is not None:
        try:
            # EC Y-axis reverse
            ec_cfg = cfg.get('ec', {})
            ec_y_reversed = ec_cfg.get('y_reversed', False)
            if ec_y_reversed:
                ey0, ey1 = ec_ax.get_ylim()
                if ey0 < ey1:  # Only reverse if not already reversed
                    ec_ax.set_ylim(ey1, ey0)
                    # Also update stored time ylim if present
                    if hasattr(ec_ax, '_saved_time_ylim') and isinstance(ec_ax._saved_time_ylim, (tuple, list)) and len(ec_ax._saved_time_ylim)==2:
                        lo, hi = ec_ax._saved_time_ylim
                        ec_ax._saved_time_ylim = (hi, lo)
            else:
                ey0, ey1 = ec_ax.get_ylim()
                if ey0 > ey1:  # Un-reverse if currently reversed
                    ec_ax.set_ylim(ey1, ey0)
                    # Also update stored time ylim if present
                    if hasattr(ec_ax, '_saved_time_ylim') and isinstance(ec_ax._saved_time_ylim, (tuple, list)) and len(ec_ax._saved_time_ylim)==2:
                        lo, hi = ec_ax._saved_time_ylim
                        ec_ax._saved_time_ylim = (hi, lo)
        except Exception as e:
            print(f"Warning: Could not apply EC reverse: {e}")

    # Apply intensity range (oz command)
    try:
        intensity_range = op.get('intensity_range')
        if intensity_range and isinstance(intensity_range, (list, tuple)) and len(intensity_range) == 2:
            _safe_set_clim(im, float(intensity_range[0]), float(intensity_range[1]))
            print(f"Applied intensity range: {intensity_range[0]:.4g} to {intensity_range[1]:.4g}")
    except Exception as e:
        print(f"Warning: Could not apply intensity range: {e}")

    # Apply CIF tick config (c command) if present and CIF data exists
    try:
        cif_cfg = cfg.get('cif', {})
        if cif_cfg and getattr(ax, '_operando_cif_tick_series', None):
            fig._operando_cif_show_hkl = bool(cif_cfg.get('show_hkl', False))
            fig._operando_cif_show_titles = bool(cif_cfg.get('show_titles', True))
            fig._operando_cif_placement = str(cif_cfg.get('placement', 'below'))
            y_pos = cif_cfg.get('y_positions', [])
            fig._operando_cif_y_positions = list(y_pos) if y_pos else []
            fig._operando_cif_colormap = cif_cfg.get('colormap')
            fig._operando_cif_highlight = bool(cif_cfg.get('highlight', False))
            fig._operando_cif_title_font = dict(cif_cfg.get('title_font') or {})
            fig._operando_cif_title_visible = list(cif_cfg.get('title_visible') or [])
            fig._operando_cif_set_visible = list(cif_cfg.get('set_visible') or [])
            labels = cif_cfg.get('labels', [])
            colors = cif_cfg.get('colors', [])
            if labels or colors:
                cif_series = list(ax._operando_cif_tick_series)
                n_updates = max(len(labels), len(colors))
                for idx in range(n_updates):
                    if idx < len(cif_series):
                        lab, fname, peaksQ, wl_e, qmax, _ = cif_series[idx]
                        if idx < len(labels) and labels[idx] is not None:
                            lab = str(labels[idx])
                        col = colors[idx] if idx < len(colors) else cif_series[idx][-1]
                        cif_series[idx] = (lab, fname, peaksQ, wl_e, qmax, col)
                ax._operando_cif_tick_series = cif_series
            axis_mode = getattr(fig, '_operando_axis_mode', '2theta')
            wl = getattr(fig, '_operando_wl', None)
            cif_hkl_map = getattr(ax, '_operando_cif_hkl_label_map', {})
            ax_pos = ax.get_position()
            y_base = ax_pos.ymin - 0.02 if fig._operando_cif_placement == 'below' else ax_pos.ymax + 0.02
            dy = -0.025 if fig._operando_cif_placement == 'below' else 0.025
            while len(fig._operando_cif_y_positions) < len(ax._operando_cif_tick_series):
                fig._operando_cif_y_positions.append(y_base + len(fig._operando_cif_y_positions) * dy)
            _draw_operando_cif_ticks(ax, fig, ax._operando_cif_tick_series, cif_hkl_map, axis_mode=axis_mode, wl=wl,
                                     show_hkl=fig._operando_cif_show_hkl, show_titles=fig._operando_cif_show_titles,
                                     placement=fig._operando_cif_placement, y_positions=fig._operando_cif_y_positions)
            print("Applied CIF tick config.")
    except Exception as e:
        print(f"Warning: Could not apply CIF config: {e}")

    # Apply ions mode (ey command)
    try:
        ec_cfg = cfg.get('ec', {})
        ec_y_mode = ec_cfg.get('y_mode', 'time')
        ion_params = ec_cfg.get('ion_params')

        if ec_y_mode == 'ions' and ion_params:
            # Same as original: AttributeError if ec_ax is None (caught below)
            if ec_ax is None:
                raise AttributeError("'NoneType' object has no attribute '_ion_params'")
            # Store parameters
            ec_ax._ion_params = ion_params
            ec_ax._ec_y_mode = 'ions'
            if ec_cfg.get('prev_ec_xlim') is not None:
                try:
                    ec_ax._prev_ec_xlim = tuple(ec_cfg.get('prev_ec_xlim'))
                except Exception:
                    pass
            ec_ax._ions_xlim_expanded = bool(ec_cfg.get('ions_xlim_expanded', False))

            # Compute and apply ions formatter

            time_h = getattr(ec_ax, '_ec_time_h', None)
            current_mA = getattr(ec_ax, '_ec_current_mA', None)
            voltage_v = getattr(ec_ax, '_ec_voltage_v', None)

            if current_mA is None:
                print("Error: Current data is required for ion counting but is not available in the .mpt file.")
                print("The .mpt file must contain the '<I>/mA' column to use this feature.")
                if not silent:
                    print("Error: Current data is required for ion counting but is not available.")
                return False

            if time_h is not None and current_mA is not None:
                t = np.asarray(time_h, float)
                i_mA = np.asarray(current_mA, float)
                v = np.asarray(voltage_v, float)

                # Cumulative trapezoidal integration for capacity (mAh)
                dt = np.diff(t)
                cap_increments = np.empty_like(t)
                cap_increments[0] = 0.0
                if t.size > 1:
                    cap_increments[1:] = 0.5 * (i_mA[:-1] + i_mA[1:]) * dt
                cap_mAh = np.cumsum(cap_increments)

                # Convert to specific capacity
                mass_g = float(ion_params.get('mass_mg', 0.0)) / 1000.0
                with np.errstate(divide='ignore', invalid='ignore'):
                    cap_mAh_g = np.where(mass_g > 0, cap_mAh / mass_g, np.nan)
                    ions_delta = np.where(
                        ion_params.get('cap_per_ion_mAh_g', 0.0) > 0,
                        cap_mAh_g / float(ion_params['cap_per_ion_mAh_g']),
                        np.nan
                    )

                ions_payload = ec_cfg.get('ions_abs')
                if ions_payload is not None and len(ions_payload) == len(t):
                    ions_abs = np.asarray(ions_payload, float)
                else:
                    ions_abs = float(ion_params.get('start_ions', 0.0)) + ions_delta
                ec_ax._ions_abs = ions_abs

                install_ec_ions_y_display(ec_ax, t, ions_abs)

                # Update label if not custom
                if not getattr(ec_ax, '_custom_labels', {}).get('y_ions'):
                    ec_ax.set_ylabel('Number of ions')
                for a in getattr(ec_ax, '_ion_annots', []):
                    try:
                        a.remove()
                    except Exception:
                        pass
                ec_ax._ion_annots = []
                for gl in getattr(ec_ax, '_ion_guides', []):
                    try:
                        gl.remove()
                    except Exception:
                        pass
                ec_ax._ion_guides = []
                for y_guide in ec_cfg.get('ion_guides', []) or []:
                    try:
                        ec_ax._ion_guides.append(ec_ax.axhline(y=float(y_guide), color='0.7', linestyle='--', linewidth=0.8, alpha=0.5, zorder=0))
                    except Exception:
                        pass
                for ann in ec_cfg.get('ion_annots', []) or []:
                    try:
                        txt = ec_ax.annotate(str(ann.get('text', '')), xy=tuple(ann.get('xy', (0.0, 0.0))), xytext=(0, 4), textcoords='offset points',
                                             ha='right', va='bottom', fontsize=9,
                                             bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='0.7', alpha=0.8))
                        ec_ax._ion_annots.append(txt)
                    except Exception:
                        pass

                print("Applied ions mode")
    except Exception as e:
        print(f"Warning: Could not apply ions mode: {e}")
    return None


def _apply_visibility_colorbar_ec_grid(
    fig,
    ax,
    im,
    cbar,
    ec_ax,
    cfg: Dict[str, Any],
) -> None:
    # Apply visibility states (n command)
    try:
        fig_cfg = cfg.get('figure', {})
        colorbar_cfg = cfg.get('colorbar', {})
        cb_visible = colorbar_cfg.get('visible')
        if cb_visible is None:
            cb_visible = fig_cfg.get('cb_visible')
        if cb_visible is not None:
            cbar.ax.set_visible(bool(cb_visible))

        # Restore colorbar label text and mode
        cb_label_mode = colorbar_cfg.get('mode', fig_cfg.get('cb_label_mode', 'highlow'))
        if cb_label_mode not in ('normal', 'highlow'):
            cb_label_mode = 'highlow'
        fig._colorbar_label_mode = cb_label_mode
        cb_label_text = colorbar_cfg.get('label')
        if cb_label_text is not None:
            cbar.ax._colorbar_label = cb_label_text
        try:
            _update_custom_colorbar(
                cbar.ax,
                im,
                label=cb_label_text if cb_label_text is not None else None,
                label_mode=cb_label_mode,
            )
        except Exception:
            pass
        if colorbar_cfg.get('ticks_left') is not None:
            cbar.ax.yaxis.set_ticks_position('left' if colorbar_cfg['ticks_left'] else 'right')
        if colorbar_cfg.get('label_left') is not None:
            cbar.ax.yaxis.set_label_position('left' if colorbar_cfg['label_left'] else 'right')
    except Exception:
        pass
    try:
        ec_cfg = cfg.get('ec', {})
        ec_custom = ec_cfg.get('custom_labels')
        if isinstance(ec_custom, dict) and ec_ax is not None:
            setattr(ec_ax, '_custom_labels', dict(ec_custom))
        st_ylim = ec_cfg.get('saved_time_ylim')
        if isinstance(st_ylim, (list, tuple)) and len(st_ylim) == 2 and ec_ax is not None:
            setattr(ec_ax, '_saved_time_ylim', (float(st_ylim[0]), float(st_ylim[1])))
        ec_visible = ec_cfg.get('visible')
        if ec_visible is not None and ec_ax is not None:
            ec_ax.set_visible(bool(ec_visible))
        ec_grid = ec_cfg.get('grid') or {}
        if ec_grid and ec_ax is not None:
            g = dict(ec_grid)
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


def _apply_title_offsets_and_labelpads(
    ax,
    ec_ax,
    cfg: Dict[str, Any],
    op: Dict[str, Any],
    saved_op_xlabelpad,
    saved_op_ylabelpad,
    saved_ec_xlabelpad,
    saved_ec_ylabelpad,
) -> None:
    # Restore title offsets BEFORE applying labelpads
    try:
        op_offsets = op.get('title_offsets', {})
        if op_offsets:
            restore_title_offsets(ax, op_offsets)
    except Exception as e:
        print(f"Warning: Could not apply operando title offsets: {e}")

    try:
        ec_cfg = cfg.get('ec', {})
        ec_offsets = ec_cfg.get('title_offsets', {})
        if ec_offsets and ec_ax is not None:
            restore_title_offsets(ec_ax, ec_offsets)
    except Exception as e:
        print(f"Warning: Could not apply EC title offsets: {e}")

    # Apply labelpads (title positioning) - preserve current if not in config
    try:
        op_pads = op.get('labelpads', {})
        if op_pads:
            if op_pads.get('x') is not None:
                ax.xaxis.labelpad = op_pads['x']
            elif saved_op_xlabelpad is not None:
                ax.xaxis.labelpad = saved_op_xlabelpad
            if op_pads.get('y') is not None:
                ax.yaxis.labelpad = op_pads['y']
            elif saved_op_ylabelpad is not None:
                ax.yaxis.labelpad = saved_op_ylabelpad
        else:
            # No labelpads in config, preserve current values
            if saved_op_xlabelpad is not None:
                ax.xaxis.labelpad = saved_op_xlabelpad
            if saved_op_ylabelpad is not None:
                ax.yaxis.labelpad = saved_op_ylabelpad
    except Exception as e:
        print(f"Warning: Could not apply operando labelpads: {e}")

    try:
        ec_cfg = cfg.get('ec', {})
        ec_pads = ec_cfg.get('labelpads', {})
        if ec_pads and ec_ax is not None:
            if ec_pads.get('x') is not None:
                ec_ax.xaxis.labelpad = ec_pads['x']
            elif saved_ec_xlabelpad is not None:
                ec_ax.xaxis.labelpad = saved_ec_xlabelpad
            if ec_pads.get('y') is not None:
                ec_ax.yaxis.labelpad = ec_pads['y']
            elif saved_ec_ylabelpad is not None:
                ec_ax.yaxis.labelpad = saved_ec_ylabelpad
        elif ec_ax is not None:
            # No labelpads in config, preserve current values
            if saved_ec_xlabelpad is not None:
                ec_ax.xaxis.labelpad = saved_ec_xlabelpad
            if saved_ec_ylabelpad is not None:
                ec_ax.yaxis.labelpad = saved_ec_ylabelpad
    except Exception as e:
        print(f"Warning: Could not apply EC labelpads: {e}")


def _reposition_titles(fig, ax, ec_ax) -> None:
    # Reposition titles to apply offsets (after labelpads are set)
    try:
        # Build tick_state for operando pane
        op_ts = getattr(ax, '_saved_tick_state', {})
        op_tick_state = {
            't_ticks': bool(op_ts.get('t_ticks', op_ts.get('tx', False))),
            't_labels': bool(op_ts.get('t_labels', op_ts.get('tx', False))),
            'b_ticks': bool(op_ts.get('b_ticks', op_ts.get('bx', True))),
            'b_labels': bool(op_ts.get('b_labels', op_ts.get('bx', True))),
            'l_ticks': bool(op_ts.get('l_ticks', op_ts.get('ly', True))),
            'l_labels': bool(op_ts.get('l_labels', op_ts.get('ly', True))),
            'r_ticks': bool(op_ts.get('r_ticks', op_ts.get('ry', False))),
            'r_labels': bool(op_ts.get('r_labels', op_ts.get('ry', False))),
        }
        _ui_position_top_xlabel(ax, fig, op_tick_state)
        _ui_position_bottom_xlabel(ax, fig, op_tick_state)
        _ui_position_left_ylabel(ax, fig, op_tick_state)
        _ui_position_right_ylabel(ax, fig, op_tick_state)
        if ec_ax is not None:
            ec_ts = getattr(ec_ax, '_saved_tick_state', {})
            ec_tick_state = {
                't_ticks': bool(ec_ts.get('t_ticks', ec_ts.get('tx', False))),
                't_labels': bool(ec_ts.get('t_labels', ec_ts.get('tx', False))),
                'b_ticks': bool(ec_ts.get('b_ticks', ec_ts.get('bx', True))),
                'b_labels': bool(ec_ts.get('b_labels', ec_ts.get('bx', True))),
                'l_ticks': bool(ec_ts.get('l_ticks', ec_ts.get('ly', True))),
                'l_labels': bool(ec_ts.get('l_labels', ec_ts.get('ly', True))),
                'r_ticks': bool(ec_ts.get('r_ticks', ec_ts.get('ry', False))),
                'r_labels': bool(ec_ts.get('r_labels', ec_ts.get('ry', False))),
            }
            _ui_position_top_xlabel(ec_ax, fig, ec_tick_state)
            _ui_position_bottom_xlabel(ec_ax, fig, ec_tick_state)
            try:
                keep_yaxis_label_on_side(ec_ax, 'right', visible=bool(ec_ax.get_ylabel()))
            except Exception:
                pass
            # EC right title is the actual ylabel (already on the right); never build a duplicate artist
            if hasattr(ec_ax, '_right_ylabel_artist') and ec_ax._right_ylabel_artist is not None:
                try:
                    ec_ax._right_ylabel_artist.set_visible(False)
                except Exception:
                    pass
    except Exception as e:
        print(f"Warning: Could not reposition titles: {e}")


def _apply_axes_geometry(fig, ax, ec_ax, cfg: Dict[str, Any], *, silent: bool) -> None:
    # Apply geometry if present
    try:
        geom = cfg.get('axes_geometry', {})
        op_geom = geom.get('operando', {})
        ec_geom = geom.get('ec', {})
        _is_d2 = bool(getattr(fig, '_is_dqdv_2d_contour', False))

        if not _is_d2:
            if op_geom.get('xlabel'):
                ax.set_xlabel(op_geom['xlabel'])
            if op_geom.get('ylabel'):
                ax.set_ylabel(op_geom['ylabel'])
        if 'xlim' in op_geom and isinstance(op_geom['xlim'], list) and len(op_geom['xlim']) == 2:
            if not _is_d2:
                ax.set_xlim(op_geom['xlim'][0], op_geom['xlim'][1])
        if 'ylim' in op_geom and isinstance(op_geom['ylim'], list) and len(op_geom['ylim']) == 2:
            ax.set_ylim(op_geom['ylim'][0], op_geom['ylim'][1])

        if ec_ax is not None and ec_geom:
            if ec_geom.get('xlabel'):
                ec_ax.set_xlabel(ec_geom['xlabel'])
            if ec_geom.get('ylabel'):
                ec_ax.set_ylabel(ec_geom['ylabel'])
            if 'xlim' in ec_geom and isinstance(ec_geom['xlim'], list) and len(ec_geom['xlim']) == 2:
                ec_ax.set_xlim(ec_geom['xlim'][0], ec_geom['xlim'][1])
            if 'ylim' in ec_geom and isinstance(ec_geom['ylim'], list) and len(ec_geom['ylim']) == 2:
                ec_ax.set_ylim(ec_geom['ylim'][0], ec_geom['ylim'][1])
                if getattr(ec_ax, '_ec_y_mode', 'time') == 'time':
                    try:
                        ec_ax._saved_time_ylim = tuple(ec_geom['ylim'])
                    except Exception:
                        pass

        if not silent: print("Applied geometry (labels and limits)")
        fig.canvas.draw_idle()
    except Exception as e:
        print(f"Warning: Could not apply geometry: {e}")


def apply_operando_ec_style_config(
    cfg: Dict[str, Any],
    *,
    fig,
    ax,
    im,
    cbar,
    ec_ax,
    silent: bool = False,
) -> bool:
    kind = cfg.get('kind', '')
    if kind and kind not in ('operando_ec_style', 'operando_ec_style_geom'):
        if not silent:
            print(f"Not an operando style file (kind={kind!r}).")
        return False

    cb_w_in, cb_gap_in, ec_gap_in, ec_w_in, ax_w_in, ax_h_in = _ensure_fixed_params(fig, ax, cbar.ax, ec_ax)

    _restore_dqdv_2d_cfg(fig, cfg)

    has_geometry = (kind == 'operando_ec_style_geom' and 'axes_geometry' in cfg)

    saved_op_xlabelpad, saved_op_ylabelpad, saved_ec_xlabelpad, saved_ec_ylabelpad = _save_labelpads(ax, ec_ax)

    version = cfg.get('version', 1)

    _apply_fonts_and_canvas(fig, ax, ec_ax, cbar, cfg)

    _apply_geometry_inches(
        fig, ax, cbar, ec_ax, cfg, version,
        cb_w_in, cb_gap_in, ec_gap_in, ec_w_in, ax_w_in, ax_h_in,
    )

    op = cfg.get('operando', {})
    _apply_colormap_and_custom_labels(ax, im, cbar, op)

    _apply_operando_wasd_spines_ticks(fig, ax, op, version)

    _apply_ec_wasd_spines_ticks_curve(fig, ec_ax, cfg, version)

    _finalize_spine_colors(fig, ax, ec_ax)

    if version >= 2:
        ions_result = _apply_reverse_intensity_cif_ions(
            fig, ax, im, ec_ax, cfg, op, silent=silent,
        )
        if ions_result is False:
            return False

    if version >= 2:
        _apply_visibility_colorbar_ec_grid(fig, ax, im, cbar, ec_ax, cfg)

    if version >= 2:
        _apply_title_offsets_and_labelpads(
            ax, ec_ax, cfg, op,
            saved_op_xlabelpad, saved_op_ylabelpad,
            saved_ec_xlabelpad, saved_ec_ylabelpad,
        )

    _reposition_titles(fig, ax, ec_ax)

    # Final redraw
    try:
        fig.canvas.draw()
    except Exception:
        fig.canvas.draw_idle()

    if has_geometry:
        _apply_axes_geometry(fig, ax, ec_ax, cfg, silent=silent)

    _maybe_reapply_dqdv_2d_contour(fig, ax, im, cbar)
    if getattr(fig, '_is_dqdv_2d_contour', False):
        geom = cfg.get('axes_geometry', {}) if has_geometry else {}
        op_geom = geom.get('operando', {}) if isinstance(geom, dict) else {}
        op_l = {
            'x': op_geom.get('xlabel') if op_geom.get('xlabel') else ax.get_xlabel(),
            'y': op_geom.get('ylabel') if op_geom.get('ylabel') else ax.get_ylabel(),
        }
        _restore_dqdv_2d_operando_labels(ax, op_l)
    try:
        apply_session_font_cfg(
            fig,
            cfg.get('font', {}),
            ax,
            ec_ax,
            artists=collect_operando_font_artists(fig, ax, ec_ax, cbar),
        )
    except Exception:
        pass
    try:
        fig.canvas.draw_idle()
    except Exception:
        pass
    return True


__all__ = ["apply_operando_ec_style_config"]

"""Apply EC style/geometry configuration from dict or file."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
from matplotlib.ticker import (  # type: ignore[import-untyped]
    AutoLocator,
    AutoMinorLocator,
    MultipleLocator,
    NullFormatter,
    NullLocator,
)

from .colors import _iter_cycle_lines
from .style import _apply_cycle_styles, apply_dual_top_axis_style
from .legend import (
    _apply_file_display_names_to_legend,
    _apply_legend_position,
    _get_legend_title,
    _rebuild_legend,
    _sanitize_legend_offset,
)
from ..common.font_extras import apply_font_extras_from_cfg, apply_session_font_cfg
from ..common.terminal import safe_input
from ...ui import (
    finalize_spine_colors,
    position_bottom_xlabel as _ui_position_bottom_xlabel,
    position_left_ylabel as _ui_position_left_ylabel,
    position_right_ylabel as _ui_position_right_ylabel,
    position_top_xlabel as _ui_position_top_xlabel,
)
from .interactive import (
    _apply_font_family,
    _apply_font_size,
    _apply_spine_color,
    _apply_stored_smooth_settings,
    _ec_font_artists,
)


def _apply_display_mode(
    mode: str,
    *,
    cycle_lines,
    file_data,
    is_multi_file: bool,
    iter_cycle_lines,
) -> None:
    valid_modes = {"both", "charge", "discharge"}
    if mode not in valid_modes:
        return

    def _apply_to_lines(cl):
        for cyc, parts in cl.items():
            if isinstance(parts, dict):
                chg = parts.get("charge")
                dch = parts.get("discharge")
                cycle_selected = (
                    (chg is not None and chg.get_visible())
                    or (dch is not None and dch.get_visible())
                )
                if not cycle_selected:
                    continue
                if chg is not None:
                    try:
                        chg.set_visible(mode in ("both", "charge"))
                    except Exception:
                        pass
                if dch is not None:
                    try:
                        dch.set_visible(mode in ("both", "discharge"))
                    except Exception:
                        pass
            else:
                try:
                    parts.set_visible(True)
                except Exception:
                    pass

    if is_multi_file and file_data:
        for f in file_data:
            if not f.get("visible", True):
                continue
            _apply_to_lines(f.get("cycle_lines") or {})
    else:
        _apply_to_lines(cycle_lines)


def _set_legend_user_pref(fig, visible: bool) -> None:
    try:
        fig._ec_legend_user_visible = bool(visible)
    except Exception:
        pass


def apply_ec_style_config(
    cfg: Dict[str, Any],
    *,
    fig,
    ax,
    cycle_lines: Dict[Any, Any],
    file_data: Optional[List[Dict[Any, Any]]],
    tick_state: Dict[str, Any],
    is_multi_file: bool = False,
    silent: bool = False,
) -> bool:
    """Apply an EC style/geometry dict. Returns False if skipped (e.g. ro mismatch)."""
    kind = cfg.get('kind', '')
    if kind and kind not in ('ec_style', 'ec_style_geom'):
        if not silent:
            print(f"Not an EC style file (kind={kind!r}).")
        return False

    file_ro = bool(cfg.get('ro_active', False))
    current_ro = bool(getattr(fig, '_ro_active', False))
    if file_ro != current_ro:
        if not silent:
            from ..common.state_capture import ro_states_compatible

            ro_states_compatible(cfg, fig, mode_label="EC style/geometry")
        return False

    geometry_cfg = cfg.get('geometry')
    if geometry_cfg is None:
        geometry_cfg = cfg.get('axes_geometry')
    has_geometry = (kind == 'ec_style_geom' and isinstance(geometry_cfg, dict))

    saved_xlabelpad = None
    saved_ylabelpad = None
    saved_axes_position = None
    try:
        saved_xlabelpad = getattr(ax.xaxis, 'labelpad', None)
    except Exception:
        pass
    try:
        saved_ylabelpad = getattr(ax.yaxis, 'labelpad', None)
    except Exception:
        pass
    try:
        saved_axes_position = ax.get_position()
    except Exception:
        pass

    pads_cfg = cfg.get('labelpads') or {}
    if pads_cfg.get('x') is not None:
        saved_xlabelpad = pads_cfg['x']
    if pads_cfg.get('y') is not None:
        saved_ylabelpad = pads_cfg['y']

    # --- Apply comprehensive style (no curve data) ---
    # Figure and font
    try:
        fig_cfg = cfg.get('figure', {})
        # Get axes_fraction BEFORE changing canvas size (to preserve exact position)
        axes_frac = fig_cfg.get('axes_fraction')
        frame_size = fig_cfg.get('frame_size')

        canvas_size = fig_cfg.get('canvas_size')
        if canvas_size and isinstance(canvas_size, list) and len(canvas_size) == 2:
            # Use forward=False to prevent automatic subplot adjustment that can shift the plot
            # We'll restore axes_fraction immediately after to set exact position
            fig.set_size_inches(canvas_size[0], canvas_size[1], forward=False)

        # Frame position: prefer axes_fraction (exact position), fall back to centering based on frame_size
        axes_position_changed = False
        if axes_frac and isinstance(axes_frac, (list, tuple)) and len(axes_frac) == 4:
            # Restore exact position from axes_fraction (this overrides any automatic adjustments)
            x0, y0, w, h = axes_frac
            left = float(x0)
            bottom = float(y0)
            right = left + float(w)
            top = bottom + float(h)
            if 0 < left < right <= 1 and 0 < bottom < top <= 1:
                w_frac = right - left
                h_frac = top - bottom
                if saved_axes_position is not None:
                    tol = 1e-6
                    if (abs(saved_axes_position.x0 - left) > tol or
                        abs(saved_axes_position.y0 - bottom) > tol or
                        abs(saved_axes_position.width - w_frac) > tol or
                        abs(saved_axes_position.height - h_frac) > tol):
                        axes_position_changed = True
                        ax.set_position([left, bottom, w_frac, h_frac])
                else:
                    axes_position_changed = True
                    ax.set_position([left, bottom, w_frac, h_frac])
        elif frame_size and isinstance(frame_size, (list, tuple)) and len(frame_size) == 2:
            # Fall back to centering based on frame_size (for backward compatibility)
            fw_in, fh_in = frame_size
            canvas_w, canvas_h = fig.get_size_inches()
            if canvas_w > 0 and canvas_h > 0:
                min_margin = 0.05
                w_frac = min(fw_in / canvas_w, 1 - 2 * min_margin)
                h_frac = min(fh_in / canvas_h, 1 - 2 * min_margin)
                left = (1 - w_frac) / 2
                bottom = (1 - h_frac) / 2
                if saved_axes_position is not None:
                    tol = 1e-6
                    new_pos = (left, bottom, w_frac, h_frac)
                    if (abs(saved_axes_position.x0 - new_pos[0]) > tol or
                        abs(saved_axes_position.y0 - new_pos[1]) > tol or
                        abs(saved_axes_position.width - new_pos[2]) > tol or
                        abs(saved_axes_position.height - new_pos[3]) > tol):
                        axes_position_changed = True
                        ax.set_position([left, bottom, w_frac, h_frac])
                else:
                    axes_position_changed = True
                    ax.set_position([left, bottom, w_frac, h_frac])

        font_cfg = cfg.get('font', {})
        if font_cfg.get('family'):
            _apply_font_family(ax, font_cfg['family'])
        if font_cfg.get('size') is not None:
            _apply_font_size(ax, float(font_cfg['size']))
        if font_cfg.get('mathtext_fontset'):
            try:
                plt.rcParams['mathtext.fontset'] = font_cfg['mathtext_fontset']
            except Exception:
                pass
        try:
            apply_font_extras_from_cfg(fig, _ec_font_artists(ax), font_cfg)
        except Exception:
            pass
        axis_labels = cfg.get('axis_labels') or {}
        try:
            if axis_labels.get('xlabel') is not None:
                ax.set_xlabel(str(axis_labels['xlabel']))
            if axis_labels.get('ylabel') is not None:
                ax.set_ylabel(str(axis_labels['ylabel']))
        except Exception:
            pass
        axis_label_colors = cfg.get('axis_label_colors') or {}
        try:
            if axis_label_colors.get('x'):
                ax.xaxis.label.set_color(axis_label_colors['x'])
                ax._stored_xlabel_color = axis_label_colors['x']
            if axis_label_colors.get('y'):
                ax.yaxis.label.set_color(axis_label_colors['y'])
                ax._stored_ylabel_color = axis_label_colors['y']
        except Exception:
            pass
    except Exception as e:
        print(f"Warning: Could not apply figure/font settings: {e}")

    # WASD state and dependent components
    try:
        wasd_state = cfg.get('wasd_state')
        if wasd_state and isinstance(wasd_state, dict):
            # Apply spines
            for name in ('top','bottom','left','right'):
                side = wasd_state.get(name, {})
                if name in ax.spines and 'spine' in side:
                    ax.spines[name].set_visible(bool(side['spine']))

            # Apply major ticks & labels
            top_s = wasd_state.get('top', {})
            bot_s = wasd_state.get('bottom', {})
            left_s = wasd_state.get('left', {})
            right_s = wasd_state.get('right', {})

            ax.tick_params(axis='x',
                          top=bool(top_s.get('ticks', False)),
                          bottom=bool(bot_s.get('ticks', True)),
                          labeltop=bool(top_s.get('labels', False)),
                          labelbottom=bool(bot_s.get('labels', True)))
            ax.tick_params(axis='y',
                          left=bool(left_s.get('ticks', True)),
                          right=bool(right_s.get('ticks', False)),
                          labelleft=bool(left_s.get('labels', True)),
                          labelright=bool(right_s.get('labels', False)))

            # Apply minor ticks - only set locator if minor ticks are enabled, otherwise clear it
            if top_s.get('minor') or bot_s.get('minor'):
                ax.xaxis.set_minor_locator(AutoMinorLocator())
                ax.xaxis.set_minor_formatter(NullFormatter())
            else:
                # Clear minor locator if no minor ticks are enabled
                ax.xaxis.set_minor_locator(NullLocator())
                ax.xaxis.set_minor_formatter(NullFormatter())
            ax.tick_params(axis='x', which='minor',
                          top=bool(top_s.get('minor', False)),
                          bottom=bool(bot_s.get('minor', False)),
                          labeltop=False, labelbottom=False)

            if left_s.get('minor') or right_s.get('minor'):
                ax.yaxis.set_minor_locator(AutoMinorLocator())
                ax.yaxis.set_minor_formatter(NullFormatter())
            else:
                # Clear minor locator if no minor ticks are enabled
                ax.yaxis.set_minor_locator(NullLocator())
                ax.yaxis.set_minor_formatter(NullFormatter())
            ax.tick_params(axis='y', which='minor',
                          left=bool(left_s.get('minor', False)),
                          right=bool(right_s.get('minor', False)),
                          labelleft=False, labelright=False)

            # Apply axis titles
            ax._top_xlabel_on = bool(top_s.get('title', False))
            ax._right_ylabel_on = bool(right_s.get('title', False))

            # Update tick_state for consistency
            tick_state['t_ticks'] = bool(top_s.get('ticks', False))
            tick_state['t_labels'] = bool(top_s.get('labels', False))
            tick_state['b_ticks'] = bool(bot_s.get('ticks', True))
            tick_state['b_labels'] = bool(bot_s.get('labels', True))
            tick_state['l_ticks'] = bool(left_s.get('ticks', True))
            tick_state['l_labels'] = bool(left_s.get('labels', True))
            tick_state['r_ticks'] = bool(right_s.get('ticks', False))
            tick_state['r_labels'] = bool(right_s.get('labels', False))
            tick_state['mtx'] = bool(top_s.get('minor', False))
            tick_state['mbx'] = bool(bot_s.get('minor', False))
            tick_state['mly'] = bool(left_s.get('minor', False))
            tick_state['mry'] = bool(right_s.get('minor', False))
            try:
                setattr(fig, '_ec_wasd_state', {
                    'top': dict(top_s),
                    'bottom': dict(bot_s),
                    'left': dict(left_s),
                    'right': dict(right_s),
                })
                ax._saved_tick_state = dict(tick_state)
            except Exception:
                pass

            # Don't reposition labels here - do it at the end after all style changes
            # This prevents font changes and other operations from triggering unnecessary recalculations

    except Exception as e:
        print(f"Warning: Could not apply tick visibility: {e}")

    # Spines and Ticks (widths)
    try:
        spines_cfg = cfg.get('spines', {})
        for name, props in spines_cfg.items():
            if name in ax.spines:
                if props.get('linewidth') is not None:
                    ax.spines[name].set_linewidth(props['linewidth'])
                if props.get('color') is not None:
                    _apply_spine_color(ax, fig, tick_state, name, props['color'])

        tick_widths = cfg.get('ticks', {}).get('widths', {})
        if tick_widths.get('x_major') is not None: ax.tick_params(axis='x', which='major', width=tick_widths['x_major'])
        if tick_widths.get('x_minor') is not None: ax.tick_params(axis='x', which='minor', width=tick_widths['x_minor'])
        if tick_widths.get('y_major') is not None: ax.tick_params(axis='y', which='major', width=tick_widths['y_major'])
        if tick_widths.get('y_minor') is not None: ax.tick_params(axis='y', which='minor', width=tick_widths['y_minor'])

        tick_lengths = cfg.get('ticks', {}).get('lengths', {})
        major_len = tick_lengths.get('major')
        minor_len = tick_lengths.get('minor')
        if major_len is not None:
            ax.tick_params(axis='both', which='major', length=float(major_len))
        if minor_len is not None:
            ax.tick_params(axis='both', which='minor', length=float(minor_len))
        if major_len is not None or minor_len is not None:
            fig._tick_lengths = dict(tick_lengths)

        # Apply tick direction
        tick_direction = cfg.get('ticks', {}).get('direction', 'out')
        if tick_direction:
            setattr(fig, '_tick_direction', tick_direction)
            ax.tick_params(axis='both', which='both', direction=tick_direction)
        # Apply tick spacing and minor count
        ec_spacing = cfg.get('ticks', {}).get('spacing', {})
        if ec_spacing:
            for axis_obj, maj_key, min_key, ndivs_key in [
                (ax.xaxis, 'x_major_step', 'x_minor_step', 'x_minor_ndivs'),
                (ax.yaxis, 'y_major_step', 'y_minor_step', 'y_minor_ndivs'),
            ]:
                try:
                    maj_step = ec_spacing.get(maj_key)
                    if maj_step is not None:
                        axis_obj.set_major_locator(MultipleLocator(float(maj_step)))
                    else:
                        axis_obj.set_major_locator(AutoLocator())
                except Exception:
                    pass
                try:
                    min_step = ec_spacing.get(min_key)
                    ndivs = ec_spacing.get(ndivs_key)
                    if min_step is not None:
                        axis_obj.set_minor_locator(MultipleLocator(float(min_step)))
                    elif ndivs is not None:
                        axis_obj.set_minor_locator(AutoMinorLocator(int(ndivs)))
                    else:
                        axis_obj.set_minor_locator(AutoMinorLocator())
                except Exception:
                    pass
    except Exception: pass
    try:
        finalize_spine_colors(fig, ax, tick_state=tick_state)
    except Exception:
        pass

    # Grid state
    try:
        grid_enabled = cfg.get('grid', False)
        if grid_enabled:
            ax.grid(True, color='0.85', linestyle='-', linewidth=0.5, alpha=0.7)
        else:
            ax.grid(False)
    except Exception: pass

    # Rotation angle
    try:
        rotation_angle = cfg.get('rotation_angle', 0)
        setattr(fig, '_ec_rotation_angle', rotation_angle)
    except Exception: pass

    # Curve linewidth (single value for all curves)
    try:
        curve_linewidth = cfg.get('curve_linewidth')
        if curve_linewidth is not None:
            # Store globally on fig so it persists
            setattr(fig, '_ec_curve_linewidth', float(curve_linewidth))
            # Apply to all curves
            for cyc, role, ln in _iter_cycle_lines(cycle_lines):
                try:
                    ln.set_linewidth(float(curve_linewidth))
                except Exception:
                    pass
    except Exception: pass

    # Curve marker properties (linestyle, marker, markersize, colors)
    try:
        curve_markers = cfg.get('curve_markers', {})
        if curve_markers:
            for cyc, role, ln in _iter_cycle_lines(cycle_lines):
                try:
                    if 'linestyle' in curve_markers:
                        ln.set_linestyle(curve_markers['linestyle'])
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
    except Exception: pass

    # Legend visibility/position
    legend_cfg = cfg.get('legend', {}) or {}
    legend_visible = None
    try:
        if legend_cfg:
            legend_visible = bool(legend_cfg.get('visible', True))
            xy = legend_cfg.get('position_inches')
            if xy is not None:
                fig._ec_legend_xy_in = _sanitize_legend_offset(fig, xy)
            else:
                fig._ec_legend_xy_in = None
            if 'title' in legend_cfg and legend_cfg['title']:
                fig._ec_legend_title = legend_cfg['title']
            fig._ec_legend_user_visible = bool(legend_visible)
    except Exception:
        legend_visible = None

    cycle_styles_per_file_cfg = cfg.get('cycle_styles_per_file')
    cycle_styles_cfg = cfg.get('cycle_styles')
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

    # Restore per-file visibility before display-mode filtering.
    # Cycle styles (above) already set per-curve visibility. Hidden files must
    # force all curves off; visible files keep the cycle-style visibility so a
    # re-show after hide does not depend on the peer's pre-apply line state.
    try:
        file_visibility = cfg.get('file_visibility')
        if file_visibility and file_data and len(file_visibility) == len(file_data):
            for f, visible in zip(file_data, file_visibility):
                file_visible = bool(visible)
                f['visible'] = file_visible
                if not file_visible:
                    for _cyc, _role, ln in _iter_cycle_lines(f.get('cycle_lines') or {}):
                        try:
                            ln.set_visible(False)
                        except Exception:
                            pass
    except Exception:
        pass

    # Restore display mode (d command) from style-only exports too.
    try:
        display_mode = cfg.get('display_mode')
        if display_mode in ('charge', 'discharge', 'both'):
            _apply_display_mode(
                display_mode,
                cycle_lines=cycle_lines,
                file_data=file_data,
                is_multi_file=is_multi_file,
                iter_cycle_lines=_iter_cycle_lines,
            )
            fig._ec_display_mode = display_mode
    except Exception:
        pass

    # Restore file display names (multi-file) from style
    try:
        names = cfg.get('file_display_names')
        if names and file_data and len(file_data) == len(names):
            for i, f in enumerate(file_data):
                if i < len(names):
                    f['display_name'] = names[i]
            _apply_file_display_names_to_legend(file_data)
            _rebuild_legend(ax)
    except Exception:
        pass

    # Restore legend file order (ra command)
    try:
        order = cfg.get('legend_file_order')
        if order and file_data and isinstance(order, (list, tuple)) and len(order) == len(file_data):
            fig._ec_legend_file_order = list(order)
            _rebuild_legend(ax)
    except Exception:
        pass

    # Restore dQ/dV smooth settings (sm command)
    try:
        smooth_cfg = cfg.get('_dqdv_smooth_settings')
        if isinstance(smooth_cfg, dict) and smooth_cfg:
            fig._dqdv_smooth_settings = dict(smooth_cfg)
            if is_multi_file and file_data:
                for f in file_data:
                    cl = f.get('cycle_lines')
                    if cl:
                        _apply_stored_smooth_settings(cl, fig)
            else:
                _apply_stored_smooth_settings(cycle_lines, fig)
    except Exception:
        pass

    # Restore dual x-axis state
    try:
        xaxis_dual_cfg = cfg.get('xaxis_dual')
        if xaxis_dual_cfg and isinstance(xaxis_dual_cfg, dict):
            mode = xaxis_dual_cfg.get('mode', 'capacity')
            c_th = xaxis_dual_cfg.get('c_theoretical')
            swapped = xaxis_dual_cfg.get('swapped', False)

            # When ions/dual mode: prompt to use saved capacity or enter new
            if mode in ('ions', 'dual') and c_th is not None:
                try:
                    c_th_val = float(c_th)
                    prompt = f"Imported style uses ions display (capacity {c_th_val:g} mAh/g). Use this [Enter] or enter new value: "
                    raw = safe_input(prompt, cancel_on_interrupt=True).strip()
                    if raw:
                        new_c = float(raw)
                        if new_c > 0:
                            c_th = new_c
                except (ValueError, EOFError):
                    pass

            # Store state on fig
            fig._xaxis_mode = mode
            fig._xaxis_c_theoretical = c_th
            fig._xaxis_swapped = swapped

            # Remove existing secondary axis if any
            if hasattr(fig, '_xaxis_secondary') and fig._xaxis_secondary is not None:
                try:
                    fig._xaxis_secondary.remove()
                except Exception:
                    pass
                fig._xaxis_secondary = None

            # Recreate dual axis if needed
            if mode == 'dual' and c_th is not None:
                # Transform data based on swap state
                for ln in ax.lines:
                    try:
                        if not hasattr(ln, "_orig_xdata_gc"):
                            x0 = np.asarray(ln.get_xdata(), dtype=float)
                            setattr(ln, "_orig_xdata_gc", x0.copy())
                        x_orig = getattr(ln, "_orig_xdata_gc")
                        if swapped:
                            # Ions on bottom
                            ln.set_xdata(x_orig / c_th)
                        else:
                            # Capacity on bottom
                            ln.set_xdata(x_orig)
                    except Exception:
                        continue

                # Define conversion functions
                if swapped:
                    def _bottom_to_top_ions(ions):
                        return ions * c_th

                    def _top_to_bottom_capacity(capacity):
                        return capacity / c_th

                    bottom_to_top = _bottom_to_top_ions
                    top_to_bottom = _top_to_bottom_capacity
                else:
                    def _bottom_to_top_capacity(capacity):
                        return capacity / c_th

                    def _top_to_bottom_ions(ions):
                        return ions * c_th

                    bottom_to_top = _bottom_to_top_capacity
                    top_to_bottom = _top_to_bottom_ions

                # Create secondary axis
                try:
                    secax = ax.secondary_xaxis('top', functions=(bottom_to_top, top_to_bottom))
                    fig._xaxis_secondary = secax

                    # Set labels based on swap state
                    capacity_label = "Specific Capacity (mAh g$^{{-1}}$)"
                    ions_label = f"Number of ions (C / {c_th:g} mAh g$^{{-1}}$)"

                    if swapped:
                        ax.set_xlabel(ions_label)
                        secax.set_xlabel(capacity_label)
                    else:
                        ax.set_xlabel(capacity_label)
                        secax.set_xlabel(ions_label)
                    top_axis_cfg = xaxis_dual_cfg.get('top_axis') if isinstance(xaxis_dual_cfg, dict) else None
                    apply_dual_top_axis_style(secax, top_axis_cfg if isinstance(top_axis_cfg, dict) else None)

                    # Apply font settings
                    try:
                        font_fam = plt.rcParams.get('font.sans-serif', [''])
                        font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                        font_size = plt.rcParams.get('font.size', None)
                        if font_fam_str:
                            secax.xaxis.label.set_family(font_fam_str)
                        if font_size is not None:
                            secax.xaxis.label.set_size(font_size)
                    except Exception:
                        pass
                except Exception as e:
                    print(f"Warning: Could not recreate dual x-axis: {e}")
            elif mode == 'ions' and c_th is not None:
                # Single ions mode
                for ln in ax.lines:
                    try:
                        if not hasattr(ln, "_orig_xdata_gc"):
                            x0 = np.asarray(ln.get_xdata(), dtype=float)
                            setattr(ln, "_orig_xdata_gc", x0.copy())
                        x_orig = getattr(ln, "_orig_xdata_gc")
                        ln.set_xdata(x_orig / c_th)
                    except Exception:
                        continue
    except Exception as e:
        print(f"Warning: Could not restore dual x-axis state: {e}")

    # Apply geometry if present (before final repositioning)
    if has_geometry:
        try:
            geom = geometry_cfg or {}
            if 'xlabel' in geom and geom['xlabel']:
                ax.set_xlabel(geom['xlabel'])
            if 'ylabel' in geom and geom['ylabel']:
                ax.set_ylabel(geom['ylabel'])
            if 'xlim' in geom and isinstance(geom['xlim'], list) and len(geom['xlim']) == 2:
                ax.set_xlim(geom['xlim'][0], geom['xlim'][1])
            if 'ylim' in geom and isinstance(geom['ylim'], list) and len(geom['ylim']) == 2:
                ax.set_ylim(geom['ylim'][0], geom['ylim'][1])
            dm = geom.get('display_mode')
            if dm in ('charge', 'discharge', 'both'):
                _apply_display_mode(
                    dm,
                    cycle_lines=cycle_lines,
                    file_data=file_data,
                    is_multi_file=is_multi_file,
                    iter_cycle_lines=_iter_cycle_lines,
                )
                try:
                    fig._ec_display_mode = dm
                except Exception:
                    pass
            if not silent: print("Applied geometry (labels and limits)")
        except Exception as e:
            print(f"Warning: Could not apply geometry: {e}")

    # Restore title offsets
    try:
        offsets = cfg.get('title_offsets', {})
        if offsets:
            ax._top_xlabel_manual_offset_y_pts = float(offsets.get('top_y', 0.0) or 0.0)
            ax._top_xlabel_manual_offset_x_pts = float(offsets.get('top_x', 0.0) or 0.0)
            ax._bottom_xlabel_manual_offset_y_pts = float(offsets.get('bottom_y', 0.0) or 0.0)
            ax._left_ylabel_manual_offset_x_pts = float(offsets.get('left_x', 0.0) or 0.0)
            ax._right_ylabel_manual_offset_x_pts = float(offsets.get('right_x', 0.0) or 0.0)
            ax._right_ylabel_manual_offset_y_pts = float(offsets.get('right_y', 0.0) or 0.0)
    except Exception:
        pass

    # Final label positioning - do this AFTER all style changes to prevent drift
    # Set pending labelpad before repositioning to preserve original values
    try:
        if saved_xlabelpad is not None:
            ax._pending_xlabelpad = saved_xlabelpad
        if saved_ylabelpad is not None:
            ax._pending_ylabelpad = saved_ylabelpad

        # Only reposition if axes position actually changed OR if fonts changed
        # This prevents unnecessary movement when nothing actually changed
        font_cfg = cfg.get('font', {})
        font_changed = (font_cfg.get('family') is not None or font_cfg.get('size') is not None)

        # Always reposition titles to apply offsets (even if nothing else changed)
        _ui_position_top_xlabel(ax, fig, tick_state)
        _ui_position_bottom_xlabel(ax, fig, tick_state)
        _ui_position_left_ylabel(ax, fig, tick_state)
        _ui_position_right_ylabel(ax, fig, tick_state)

        # Always ensure labelpad is exactly as it was before style import
        # This is a final safeguard against any drift
        if saved_xlabelpad is not None:
            ax.xaxis.labelpad = saved_xlabelpad
        if saved_ylabelpad is not None:
            ax.yaxis.labelpad = saved_ylabelpad
    except Exception:
        pass

    # Rebuild and reposition legend after all changes (including figure size changes)
    _rebuild_legend(ax)
    if legend_cfg:
        try:
            if legend_visible:
                _apply_legend_position(fig, ax)
            leg = ax.get_legend()
            if leg is not None:
                leg.set_visible(bool(legend_visible))
            _set_legend_user_pref(fig, bool(legend_visible))
        except Exception:
            pass
    try:
        # Trailing finalize after dual-top / label reposition / legend (tick_params may rebuild).
        finalize_spine_colors(fig, ax, tick_state=tick_state, draw=True)
    except Exception:
        pass
    try:
        apply_session_font_cfg(fig, cfg.get('font', {}), ax)
    except Exception:
        pass
    try:
        fig.canvas.draw_idle()
    except Exception:
        pass
    return True


def apply_ec_style_config_from_path(
    path: str,
    *,
    fig,
    ax,
    cycle_lines,
    file_data,
    tick_state,
    is_multi_file: bool = False,
    silent: bool = False,
) -> bool:
    import json
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            cfg = json.load(fh)
    except Exception as exc:
        if not silent:
            print(f"Could not read EC style file: {exc}")
        return False
    return apply_ec_style_config(
        cfg,
        fig=fig,
        ax=ax,
        cycle_lines=cycle_lines,
        file_data=file_data,
        tick_state=tick_state,
        is_multi_file=is_multi_file,
        silent=silent,
    )


__all__ = ["apply_ec_style_config", "apply_ec_style_config_from_path"]

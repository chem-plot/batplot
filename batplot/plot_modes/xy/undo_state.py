"""Undo snapshot capture/restore for the XY interactive menu.

Extracted verbatim from interactive.py (the former nested ``push_state`` /
``restore_state``). The dispatcher keeps thin nested wrappers with the same
names; ``xy_restore_state`` returns ``(delta, use_Q, use_2th)`` instead of
using ``nonlocal``. Callables that live inside the dispatcher are injected as
parameters to preserve late binding; snapshot fields and messages are
unchanged.
"""
from __future__ import annotations

import sys
import sys as _sys_snap

import numpy as np  # type: ignore[import]
import matplotlib.pyplot as plt  # type: ignore[import]
from matplotlib.ticker import AutoMinorLocator  # type: ignore[import]

from ...plotting import apply_curve_color, update_labels
from ...ui import (
    capture_axes_tick_locators,
    finalize_spine_colors,
    position_bottom_xlabel as _ui_position_bottom_xlabel,
    position_left_ylabel as _ui_position_left_ylabel,
    resolve_spine_dump_color,
    restore_axes_tick_locators,
    set_spine_side_color as _ui_set_spine_side_color,
    sync_figure_geometry_caches,
)
from ..common.font_extras import apply_font_extras_from_cfg, font_extras_export_dict
from ..common.fonts import collect_fig_font_artists
from ..common.line_dash import capture_dash_pattern, clear_dash_pattern, restore_dash_pattern
from ..common.axis_state import primary_axis_label_text
from ..common.spines import current_tick_width, set_primary_axis_title
from ..common.title_offsets import capture_title_offsets, restore_title_offsets
from .style import (
    _apply_xy_dual_y_layout,
    _get_duplicate_axis_text,
    _get_primary_axis_text,
    apply_xy_axis_style,
    capture_xy_axis_style,
)


def _capture_tick_minor_count(ax_obj):
    """Return {x, y} AutoMinorLocator ndivs, or None if not AutoMinorLocator."""
    def _ndivs(locator):
        try:
            if isinstance(locator, AutoMinorLocator):
                return int(locator._ndivs)
        except Exception:
            pass
        return None
    return {
        'x': _ndivs(ax_obj.xaxis.get_minor_locator()),
        'y': _ndivs(ax_obj.yaxis.get_minor_locator()),
    }

def _restore_tick_minor_count(ax_obj, counts):
    """Restore minor tick count from a dict captured by _capture_tick_minor_count."""
    if not counts:
        return
    for axis_obj, key in ((ax_obj.xaxis, 'x'), (ax_obj.yaxis, 'y')):
        val = counts.get(key)
        if val is not None:
            try:
                axis_obj.set_minor_locator(AutoMinorLocator(int(val)))
            except Exception:
                pass


def xy_push_state(
    *,
    state_history,
    fig,
    ax,
    tick_state,
    labels,
    delta,
    x_data_list,
    y_data_list,
    orig_y,
    offsets_list,
    x_full_list,
    raw_y_full_list,
    label_text_objects,
    bp,
    cif_series_for_session,
    iter_lines,
    note="",
):
    """Snapshot current editable state (before a modifying action)."""
    """Snapshot current editable state (before a modifying action)."""
    try:
        # Helper to capture a representative tick line width
        def _tick_width(axis_obj, which):
            return current_tick_width(axis_obj, which)
        _cts_for_snap = cif_series_for_session()
        _bottom_x_text = _get_primary_axis_text(ax, "x")
        _left_y_text = _get_primary_axis_text(ax, "y")
        _right_y_text = _get_duplicate_axis_text(
            ax, "_right_ylabel_artist", _left_y_text
        )
        _ax2_snap = getattr(fig, "_xy_ax2", None)
        _ylim_right = None
        if _ax2_snap is not None:
            try:
                # Keep intentional empty twin ylabel (do not `or` fallback).
                _right_y_text = _ax2_snap.get_ylabel()
            except Exception:
                pass
            try:
                _ylim_right = tuple(map(float, _ax2_snap.get_ylim()))
            except Exception:
                _ylim_right = None
        _norm_xlim = getattr(ax, "_norm_xlim", None)
        _norm_ylim = getattr(ax, "_norm_ylim", None)
        _cif_init_ylim = getattr(ax, "_cif_initial_ylim", None)
        snap = {
            "note": note,
            "xlim": ax.get_xlim(),
            "ylim": ax.get_ylim(),
            "ylim_right": _ylim_right,
            "norm_xlim": (
                (float(_norm_xlim[0]), float(_norm_xlim[1]))
                if isinstance(_norm_xlim, (list, tuple)) and len(_norm_xlim) == 2
                else None
            ),
            "norm_ylim": (
                (float(_norm_ylim[0]), float(_norm_ylim[1]))
                if isinstance(_norm_ylim, (list, tuple)) and len(_norm_ylim) == 2
                else None
            ),
            "cif_initial_ylim": (
                (float(_cif_init_ylim[0]), float(_cif_init_ylim[1]))
                if isinstance(_cif_init_ylim, (list, tuple)) and len(_cif_init_ylim) == 2
                else None
            ),
            "tick_state": tick_state.copy(),
            "font_size": plt.rcParams.get('font.size'),
            "font_chain": list(plt.rcParams.get('font.sans-serif', [])),
            "mathtext_fontset": plt.rcParams.get('mathtext.fontset'),
            "font_extras": font_extras_export_dict(fig),
            "labels": list(labels),
            "delta": delta,
            "lines": [],
            "fig_size": list(fig.get_size_inches()),
            "fig_dpi": fig.dpi,
            "axes_bbox": [float(v) for v in ax.get_position().bounds],  # x0,y0,w,h
            "axis_labels": {
                "xlabel": primary_axis_label_text(ax, "x"),
                "ylabel": primary_axis_label_text(ax, "y"),
            },
            "axis_titles": {"top_x": bool(getattr(ax, '_top_xlabel_on', False)),
                             "right_y": bool(getattr(ax, '_right_ylabel_on', False)),
                             "has_bottom_x": bool(ax.xaxis.label.get_visible()),
                             "has_left_y": bool(ax.yaxis.label.get_visible())},
            "axis_title_texts": {
                "top_x": _get_duplicate_axis_text(
                    ax, "_top_xlabel_artist", _bottom_x_text
                ),
                "bottom_x": _bottom_x_text,
                "left_y": _left_y_text,
                "right_y": _right_y_text,
            },
            "right_y_curve_indices": list(
                getattr(fig, "_xy_right_y_curve_indices", frozenset()) or []
            ),
            "txaxis": bool(getattr(fig, "_xy_use_top_x", False)),
            "title_offsets": capture_title_offsets(ax),
            "spines": (lambda _ax2, _use_top: {
                name: {
                    "lw": (
                        _ax2.spines[name].get_linewidth()
                        if _ax2 is not None
                        and name in _ax2.spines
                        and (
                            name == "right"
                            or (_use_top and name in ("top", "bottom"))
                        )
                        else sp.get_linewidth()
                    ),
                    "color": resolve_spine_dump_color(
                        _ax2 if (
                            _ax2 is not None
                            and (
                                name == "right"
                                or (_use_top and name in ("top", "bottom"))
                            )
                        ) else ax,
                        name,
                        fig,
                    ),
                    "visible": (
                        _ax2.spines[name].get_visible()
                        if _ax2 is not None
                        and name in _ax2.spines
                        and (
                            name == "right"
                            or (_use_top and name in ("top", "bottom"))
                        )
                        else sp.get_visible()
                    ),
                }
                for name, sp in ax.spines.items()
            })(getattr(fig, "_xy_ax2", None), bool(getattr(fig, "_xy_use_top_x", False))),
            "tick_widths": {
                "x_major": _tick_width(ax.xaxis, 'major'),
                "x_minor": _tick_width(ax.xaxis, 'minor'),
                "y_major": _tick_width(ax.yaxis, 'major'),
                "y_minor": _tick_width(ax.yaxis, 'minor')
            },
            "tick_lengths": dict(getattr(fig, '_tick_lengths', {'major': None, 'minor': None})),
            "tick_direction": getattr(fig, '_tick_direction', 'out'),
            "tick_spacing": capture_axes_tick_locators(ax, ('x', 'y')),
            "tick_minor_count": _capture_tick_minor_count(ax),
            "cif_tick_series": (list(_cts_for_snap) if _cts_for_snap is not None else None),
            "cif_hkl_label_map": (
                {str(k): dict(v) for k, v in dict(getattr(bp, 'cif_hkl_label_map', None) or {}).items()}
                if bp is not None else {}
            ),
            "show_cif_hkl": (bool(getattr(bp, 'show_cif_hkl')) if bp is not None and hasattr(bp, 'show_cif_hkl') else False),
            "show_cif_titles": (bool(getattr(bp, 'show_cif_titles')) if bp is not None and hasattr(bp, 'show_cif_titles') else True),
            "rotation_angle": getattr(ax, '_rotation_angle', 0),
            "stack_label_at_bottom": getattr(fig, '_stack_label_at_bottom', False),
            "label_anchor_left": getattr(fig, '_label_anchor_left', False),
            "grid": any(line.get_visible() for line in ax.get_xgridlines() + ax.get_ygridlines()),
            "curve_palettes": list(getattr(fig, '_curve_palette_history', []) or []),
            "axis_style": capture_xy_axis_style(ax),
            "xy_axis_mode": getattr(fig, "_xy_axis_mode", None),
            "xy_wavelength": getattr(fig, "_xy_wavelength", None),
            "xy_dual_wl_display": bool(getattr(fig, "_xy_dual_wl_display", False)),
            "xy_file_wavelength_info": list(getattr(fig, "_xy_file_wavelength_info", None) or []),
        }
        # Optional per-set CIF visibility state for 1D mode
        try:
            _bp_module_snap = _sys_snap.modules.get('__main__')
            if _bp_module_snap is not None and hasattr(_bp_module_snap, 'cif_set_visible'):
                snap["cif_set_visible"] = list(getattr(_bp_module_snap, 'cif_set_visible') or [])
        except Exception:
            pass
        try:
            snap["cif_stack_y_offsets"] = list(getattr(fig, '_bp_cif_stack_y_offsets', []) or [])
        except Exception:
            pass
        # Line + data arrays
        for i, ln in iter_lines():
            snap["lines"].append({
                "index": i,
                "x": np.array(ln.get_xdata(), copy=True),
                "y": np.array(ln.get_ydata(), copy=True),
                "color": ln.get_color(),
                "lw": ln.get_linewidth(),
                "ls": ln.get_linestyle(),
                "dash": capture_dash_pattern(ln),
                "marker": ln.get_marker(),
                "markersize": getattr(ln, 'get_markersize', lambda: None)(),
                "mfc": getattr(ln, 'get_markerfacecolor', lambda: None)(),
                "mec": getattr(ln, 'get_markeredgecolor', lambda: None)(),
                "alpha": ln.get_alpha()
            })
        # Data lists
        snap["x_data_list"] = [np.array(a, copy=True) for a in x_data_list]
        snap["y_data_list"] = [np.array(a, copy=True) for a in y_data_list]
        snap["orig_y"]      = [np.array(a, copy=True) for a in orig_y]
        snap["offsets"]     = list(offsets_list)
        try:
            snap["x_full_list"] = [np.array(a, copy=True) for a in x_full_list]
            snap["raw_y_full_list"] = [np.array(a, copy=True) for a in raw_y_full_list]
        except Exception:
            pass
        try:
            mx = getattr(fig, "_xy_master_x_full", None)
            my = getattr(fig, "_xy_master_y_full", None)
            if isinstance(mx, list) and isinstance(my, list) and mx and my:
                snap["master_x_full"] = [np.array(a, copy=True) for a in mx]
                snap["master_y_full"] = [np.array(a, copy=True) for a in my]
        except Exception:
            pass
        # Processed data (for smooth/reduce operations)
        if hasattr(fig, '_original_x_data_list'):
            snap["original_x_data_list"] = [np.array(a, copy=True) for a in fig._original_x_data_list]
            snap["original_y_data_list"] = [np.array(a, copy=True) for a in fig._original_y_data_list]
        if hasattr(fig, '_full_processed_x_data_list'):
            snap["full_processed_x_data_list"] = [np.array(a, copy=True) for a in fig._full_processed_x_data_list]
            snap["full_processed_y_data_list"] = [np.array(a, copy=True) for a in fig._full_processed_y_data_list]
        if hasattr(fig, '_smooth_settings'):
            snap["smooth_settings"] = dict(fig._smooth_settings)
        if hasattr(fig, '_last_smooth_settings'):
            snap["last_smooth_settings"] = dict(fig._last_smooth_settings)
        # Derivative data (for derivative operations)
        if hasattr(fig, '_pre_derivative_x_data_list'):
            snap["pre_derivative_x_data_list"] = [np.array(a, copy=True) for a in fig._pre_derivative_x_data_list]
            snap["pre_derivative_y_data_list"] = [np.array(a, copy=True) for a in fig._pre_derivative_y_data_list]
            snap["pre_derivative_ylabel"] = str(getattr(fig, '_pre_derivative_ylabel', ''))
        if hasattr(fig, '_derivative_order'):
            snap["derivative_order"] = int(fig._derivative_order)
        if hasattr(fig, '_derivative_reversed'):
            snap["derivative_reversed"] = bool(fig._derivative_reversed)
        # Label text content
        snap["label_texts"] = [t.get_text() for t in label_text_objects]
        snap["label_text_visible"] = [bool(t.get_visible()) for t in label_text_objects]
        state_history.append(snap)
        if len(state_history) > 40:
            state_history.pop(0)
        return True
    except Exception as e:
        print(f"Warning: could not snapshot state: {e}")
        return False
    return False


def xy_restore_state(
    *,
    state_history,
    fig,
    ax,
    args,
    tick_state,
    labels,
    x_data_list,
    y_data_list,
    orig_y,
    offsets_list,
    x_full_list,
    raw_y_full_list,
    label_text_objects,
    bp,
    delta,
    use_Q,
    use_2th,
    file_wavelength_info,
    cif_globals,
    sync_legacy_tick_keys,
    update_tick_visibility,
    sync_fonts,
    position_top_xlabel,
    position_right_ylabel,
    update_ylabel_for_derivative,
    sync_fig_cif_tick_series,
    line,
    nlines,
):
    """Pop the last undo snapshot and re-apply it. Returns (delta, use_Q, use_2th)."""
    if not state_history:
        print("No undo history.")
        return delta, use_Q, use_2th
    snap = state_history.pop()
    try:
        # Dual y-axis (--ry / --txaxis) before line/label restore (parity with style ``i``)
        try:
            if "right_y_curve_indices" in snap:
                right_indices = frozenset(int(i) for i in (snap.get("right_y_curve_indices") or []))
                use_top_x = bool(snap.get("txaxis", False))
                _apply_xy_dual_y_layout(fig, ax, right_indices, use_top_x)
        except Exception:
            pass
        # Basic numeric state
        ax.set_xlim(*snap["xlim"]) 
        ax.set_ylim(*snap["ylim"])
        try:
            if snap.get("norm_xlim") is not None and len(snap["norm_xlim"]) == 2:
                ax._norm_xlim = (float(snap["norm_xlim"][0]), float(snap["norm_xlim"][1]))
            elif hasattr(ax, "_norm_xlim") and "norm_xlim" in snap and snap.get("norm_xlim") is None:
                delattr(ax, "_norm_xlim")
        except Exception:
            pass
        try:
            if snap.get("norm_ylim") is not None and len(snap["norm_ylim"]) == 2:
                ax._norm_ylim = (float(snap["norm_ylim"][0]), float(snap["norm_ylim"][1]))
            elif hasattr(ax, "_norm_ylim") and "norm_ylim" in snap and snap.get("norm_ylim") is None:
                delattr(ax, "_norm_ylim")
        except Exception:
            pass
        try:
            if snap.get("cif_initial_ylim") is not None and len(snap["cif_initial_ylim"]) == 2:
                ax._cif_initial_ylim = (
                    float(snap["cif_initial_ylim"][0]),
                    float(snap["cif_initial_ylim"][1]),
                )
            elif (
                hasattr(ax, "_cif_initial_ylim")
                and "cif_initial_ylim" in snap
                and snap.get("cif_initial_ylim") is None
            ):
                delattr(ax, "_cif_initial_ylim")
        except Exception:
            pass
        # Diffraction axis mode / wavelength (Options ``u``)
        if "xy_axis_mode" in snap and snap.get("xy_axis_mode") in ("2theta", "Q", "d"):
            try:
                from .axis_units import set_xy_axis_mode
                set_xy_axis_mode(
                    fig,
                    snap["xy_axis_mode"],
                    wavelength=snap.get("xy_wavelength"),
                )
                use_Q = snap["xy_axis_mode"] == "Q"
                use_2th = snap["xy_axis_mode"] == "2theta"
                try:
                    setattr(args, "xaxis", snap["xy_axis_mode"])
                    if snap.get("xy_wavelength") is not None:
                        setattr(args, "wl", float(snap["xy_wavelength"]))
                except Exception:
                    pass
                if "xy_dual_wl_display" in snap:
                    try:
                        fig._xy_dual_wl_display = bool(snap.get("xy_dual_wl_display"))
                    except Exception:
                        pass
                if "xy_file_wavelength_info" in snap:
                    try:
                        _fwi = snap.get("xy_file_wavelength_info") or []
                        fig._xy_file_wavelength_info = list(_fwi) if isinstance(_fwi, list) else []
                        # Keep live interactive resolver in sync
                        if isinstance(file_wavelength_info, list):
                            file_wavelength_info[:] = list(fig._xy_file_wavelength_info)
                        if isinstance(cif_globals, dict):
                            cif_globals["file_wavelength_info"] = list(fig._xy_file_wavelength_info)
                    except Exception:
                        pass
            except Exception:
                pass
        # Tick state
        snap_ts = snap.get("tick_state", {})
        for k, v in snap_ts.items():
            if k in tick_state:
                tick_state[k] = v
        # If snapshot was legacy-only, map bx/tx/ly/ry into new keys
        if not any(k in snap_ts for k in ('b_ticks','t_ticks','l_ticks','r_ticks')):
            if 'bx' in snap_ts:
                tick_state['b_ticks'] = bool(snap_ts.get('bx', tick_state['bx']))
                tick_state['b_labels'] = bool(snap_ts.get('bx', tick_state['bx']))
            if 'tx' in snap_ts:
                tick_state['t_ticks'] = bool(snap_ts.get('tx', tick_state['tx']))
                tick_state['t_labels'] = bool(snap_ts.get('tx', tick_state['tx']))
            if 'ly' in snap_ts:
                tick_state['l_ticks'] = bool(snap_ts.get('ly', tick_state['ly']))
                tick_state['l_labels'] = bool(snap_ts.get('ly', tick_state['ly']))
            if 'ry' in snap_ts:
                tick_state['r_ticks'] = bool(snap_ts.get('ry', tick_state['ry']))
                tick_state['r_labels'] = bool(snap_ts.get('ry', tick_state['ry']))
        sync_legacy_tick_keys()
        update_tick_visibility()

        # Fonts
        if snap["font_chain"]:
            plt.rcParams['font.family'] = 'sans-serif'
            plt.rcParams['font.sans-serif'] = snap["font_chain"]
        if snap["font_size"]:
            try:
                plt.rcParams['font.size'] = snap["font_size"]
            except Exception:
                pass
        if snap.get("mathtext_fontset"):
            try:
                plt.rcParams['mathtext.fontset'] = snap["mathtext_fontset"]
            except Exception:
                pass
        # Apply restored font settings to all existing text objects
        # This ensures labels, tick labels, etc. update to match restored font size/family
        try:
            sync_fonts()
        except Exception:
            pass

        # Figure size & dpi
        if snap.get("fig_size") and isinstance(snap["fig_size"], (list, tuple)) and len(snap["fig_size"])==2:
            try:
                fig.set_size_inches(snap["fig_size"][0], snap["fig_size"][1], forward=True)
            except Exception:
                pass
            # No message needed - canvas size is managed by system
        # Don't restore DPI from undo - use system default to avoid display-dependent issues

        # Restore axes (plot frame) via stored bbox — set_position matches
        # style/session and survives after ``g`` (EC undo parity).
        if snap.get("axes_bbox") and isinstance(snap["axes_bbox"], (list, tuple)) and len(snap["axes_bbox"])==4:
            try:
                x0, y0, w, h = [float(v) for v in snap["axes_bbox"]]
                if 0 <= x0 < x0 + w <= 1 and 0 <= y0 < y0 + h <= 1:
                    ax.set_position([x0, y0, w, h])
            except Exception:
                pass
        try:
            sync_figure_geometry_caches(fig, ax)
        except Exception:
            pass

        # Axis labels + title visibility (store/clear via set_primary_axis_title).
        axis_labels = snap.get("axis_labels", {})
        at = snap.get("axis_titles", {})
        title_texts = snap.get("axis_title_texts") or {}
        try:
            bottom_text = title_texts.get("bottom_x")
            left_text = title_texts.get("left_y")
            top_text = title_texts.get("top_x")
            right_text = title_texts.get("right_y")
            if bottom_text is not None:
                ax._stored_xlabel = bottom_text
            elif axis_labels.get("xlabel") is not None:
                ax._stored_xlabel = axis_labels["xlabel"]
            if left_text is not None:
                ax._stored_ylabel = left_text
            elif axis_labels.get("ylabel") is not None:
                ax._stored_ylabel = axis_labels["ylabel"]
            if "has_bottom_x" in at:
                set_primary_axis_title(
                    ax, "x",
                    on=bool(at["has_bottom_x"]),
                    stored_attr="_stored_xlabel",
                )
            elif axis_labels.get("xlabel") is not None:
                ax.xaxis.label.set_text(axis_labels["xlabel"])
            if "has_left_y" in at:
                set_primary_axis_title(
                    ax, "y",
                    on=bool(at["has_left_y"]),
                    stored_attr="_stored_ylabel",
                )
            elif axis_labels.get("ylabel") is not None:
                ax.yaxis.label.set_text(axis_labels["ylabel"])
            if top_text is not None:
                if top_text:
                    ax._top_xlabel_text_override = top_text
                elif hasattr(ax, "_top_xlabel_text_override"):
                    delattr(ax, "_top_xlabel_text_override")
            if right_text is not None:
                ax._right_ylabel_text_override = str(right_text)
                ax2_restore = getattr(fig, "_xy_ax2", None)
                if ax2_restore is not None:
                    try:
                        ax2_restore.set_ylabel(str(right_text))
                    except Exception:
                        pass
        except Exception:
            pass
        # Manual offsets for all titles - support both old and new format
        restore_title_offsets(ax, snap.get("title_offsets", {}))

        # Axis title duplicates (top X / right Y)
        # Top X
        try:
            ax._top_xlabel_on = bool(at.get('top_x', False))
            position_top_xlabel()
        except Exception:
            pass
        # Right Y
        try:
            ax._right_ylabel_on = bool(at.get('right_y', False))
            position_right_ylabel()
        except Exception:
            pass
        # Twin ylim after dual-y rebuild (older snaps omit → leave twin).
        try:
            yr = snap.get("ylim_right")
            ax2_ylim = getattr(fig, "_xy_ax2", None)
            if (
                ax2_ylim is not None
                and isinstance(yr, (list, tuple))
                and len(yr) == 2
            ):
                ax2_ylim.set_ylim(float(yr[0]), float(yr[1]))
        except Exception:
            pass
        # Note: Do NOT call position_bottom_xlabel() / position_left_ylabel() here
        # as it causes title drift when combined with fig.canvas.draw() below.
        # Title offsets are already restored from snapshot above.

        # Font weight / highlight after duplicate titles exist so artists pick them up
        try:
            ax2 = getattr(fig, "_xy_ax2", None)
            font_artists = collect_fig_font_artists(
                ax,
                fig,
                include_title=True,
                include_axes_texts=True,
                extra_axes=[ax2] if ax2 is not None else None,
                extra_artists=list(label_text_objects or []),
            )
            apply_font_extras_from_cfg(fig, font_artists, snap.get("font_extras"))
        except Exception:
            pass

        # Spines (linewidth, color, visibility) — sync twin for --ry / --txaxis
        from .spines import set_xy_spine_visible, xy_twin_context

        for name, spec in snap.get("spines", {}).items():
            sp_obj = ax.spines.get(name)
            if sp_obj is None:
                continue
            try:
                if "lw" in spec:
                    sp_obj.set_linewidth(spec["lw"])
                    ax2_u, _ = xy_twin_context(fig)
                    if ax2_u is not None and name in ax2_u.spines and (
                        name == "right"
                        or (
                            bool(getattr(fig, "_xy_use_top_x", False))
                            and name in ("top", "bottom")
                        )
                    ):
                        try:
                            ax2_u.spines[name].set_linewidth(spec["lw"])
                        except Exception:
                            pass
                if "color" in spec and spec["color"] is not None:
                    _ui_set_spine_side_color(
                        ax, name, spec["color"], fig=fig, tick_state=tick_state
                    )
                    ax2_u, use_top = xy_twin_context(fig)
                    if ax2_u is not None and (
                        name == "right" or (use_top and name in ("top", "bottom"))
                    ):
                        _ui_set_spine_side_color(
                            ax2_u, name, spec["color"], fig=fig, tick_state=tick_state
                        )
                if "visible" in spec:
                    set_xy_spine_visible(fig, ax, name, bool(spec["visible"]))
            except Exception:
                pass
        # Tick widths
        tw = snap.get("tick_widths", {})
        try:
            if tw.get("x_major") is not None:
                ax.tick_params(axis='x', which='major', width=tw["x_major"])
            if tw.get("x_minor") is not None:
                ax.tick_params(axis='x', which='minor', width=tw["x_minor"]) 
            if tw.get("y_major") is not None:
                ax.tick_params(axis='y', which='major', width=tw["y_major"]) 
            if tw.get("y_minor") is not None:
                ax.tick_params(axis='y', which='minor', width=tw["y_minor"]) 
        except Exception:
            pass

        # Tick lengths
        tl = snap.get("tick_lengths", {})
        try:
            if tl.get("major") is not None:
                ax.tick_params(axis='both', which='major', length=tl["major"])
            if tl.get("minor") is not None:
                ax.tick_params(axis='both', which='minor', length=tl["minor"])
            if tl:
                fig._tick_lengths = dict(tl)
        except Exception:
            pass

        # Tick direction
        try:
            tick_dir = snap.get("tick_direction", 'out')
            ax.tick_params(axis='both', which='both', direction=tick_dir)
            fig._tick_direction = tick_dir
        except Exception:
            pass

        # Re-seal spine/tick colors after tick_params (widths/dir reset mark colors).
        try:
            spine_colors = {}
            for name, spec in (snap.get("spines") or {}).items():
                if isinstance(spec, dict) and spec.get("color") is not None:
                    spine_colors[str(name)] = spec["color"]
            if spine_colors:
                from .spines import apply_xy_spine_colors

                apply_xy_spine_colors(fig, ax, tick_state, spine_colors)
            finalize_spine_colors(fig, ax, tick_state=tick_state)
        except Exception:
            pass

        # Tick spacing (n command)
        try:
            restore_axes_tick_locators(ax, snap.get("tick_spacing"), ('x', 'y'))
        except Exception:
            pass

        # Minor tick count (m command)
        try:
            _restore_tick_minor_count(ax, snap.get("tick_minor_count"))
        except Exception:
            pass

        # Tick/label colors and labelpads
        try:
            axis_style = snap.get("axis_style")
            if axis_style:
                spine_specs = {
                    name: {"color": spec.get("color")}
                    for name, spec in snap.get("spines", {}).items()
                }
                apply_xy_axis_style(ax, axis_style, fig=fig, spines_cfg=spine_specs)
                _ui_position_bottom_xlabel(ax, fig, tick_state)
                _ui_position_left_ylabel(ax, fig, tick_state)
        except Exception:
            pass

        # Labels list
        labels[:] = snap["labels"]

        # Data & lines
        if len(snap["lines"]) == nlines():
            for item in snap["lines"]:
                i = item["index"]
                ln = line(i)
                ln.set_data(item["x"], item["y"])
                ln.set_linewidth(item["lw"])
                ln.set_linestyle(item["ls"])
                clear_dash_pattern(ln)
                if item.get("dash"):
                    restore_dash_pattern(ln, item["dash"])
                if item["marker"] is not None:
                    ln.set_marker(item["marker"])
                if item.get("markersize") is not None:
                    try:
                        ln.set_markersize(item["markersize"])
                    except Exception:
                        pass
                if item["alpha"] is not None:
                    ln.set_alpha(item["alpha"])
                apply_curve_color(ln, item["color"])
                if item.get("mfc") is not None:
                    try:
                        ln.set_markerfacecolor(item["mfc"])
                    except Exception:
                        pass
                if item.get("mec") is not None:
                    try:
                        ln.set_markeredgecolor(item["mec"])
                    except Exception:
                        pass

        # Replace lists
        x_data_list[:] = [np.array(a, copy=True) for a in snap["x_data_list"]]
        y_data_list[:] = [np.array(a, copy=True) for a in snap["y_data_list"]]
        orig_y[:]      = [np.array(a, copy=True) for a in snap["orig_y"]]
        offsets_list[:] = list(snap["offsets"]) 
        delta = snap.get("delta", delta)
        # Full uncropped arrays (rearrange / x-range depend on these)
        if "x_full_list" in snap and x_full_list is not None:
            try:
                x_full_list[:] = [np.array(a, copy=True) for a in snap["x_full_list"]]
            except Exception:
                pass
        if "raw_y_full_list" in snap and raw_y_full_list is not None:
            try:
                raw_y_full_list[:] = [np.array(a, copy=True) for a in snap["raw_y_full_list"]]
            except Exception:
                pass
        if "master_x_full" in snap and "master_y_full" in snap:
            try:
                from .full_data import install_master_full

                install_master_full(
                    fig,
                    snap["master_x_full"],
                    snap["master_y_full"],
                    force=True,
                )
            except Exception:
                pass
        else:
            # Keep master at least as wide as restored live full lists.
            try:
                from .full_data import install_master_full

                install_master_full(fig, x_full_list, raw_y_full_list, force=False)
            except Exception:
                pass

        # Restore processed data (for smooth/reduce operations)
        if "original_x_data_list" in snap:
            fig._original_x_data_list = [np.array(a, copy=True) for a in snap["original_x_data_list"]]
            fig._original_y_data_list = [np.array(a, copy=True) for a in snap["original_y_data_list"]]
        elif hasattr(fig, '_original_x_data_list'):
            # Clear if not in snapshot
            delattr(fig, '_original_x_data_list')
            delattr(fig, '_original_y_data_list')
        if "full_processed_x_data_list" in snap:
            fig._full_processed_x_data_list = [np.array(a, copy=True) for a in snap["full_processed_x_data_list"]]
            fig._full_processed_y_data_list = [np.array(a, copy=True) for a in snap["full_processed_y_data_list"]]
        elif hasattr(fig, '_full_processed_x_data_list'):
            # Clear if not in snapshot
            delattr(fig, '_full_processed_x_data_list')
            delattr(fig, '_full_processed_y_data_list')
        if "smooth_settings" in snap:
            fig._smooth_settings = dict(snap["smooth_settings"])
        elif hasattr(fig, '_smooth_settings'):
            delattr(fig, '_smooth_settings')
        if "last_smooth_settings" in snap:
            fig._last_smooth_settings = dict(snap["last_smooth_settings"])
        elif hasattr(fig, '_last_smooth_settings'):
            delattr(fig, '_last_smooth_settings')
        # Restore derivative data (for derivative operations)
        if "pre_derivative_x_data_list" in snap:
            fig._pre_derivative_x_data_list = [np.array(a, copy=True) for a in snap["pre_derivative_x_data_list"]]
            fig._pre_derivative_y_data_list = [np.array(a, copy=True) for a in snap["pre_derivative_y_data_list"]]
            fig._pre_derivative_ylabel = str(snap.get("pre_derivative_ylabel", ""))
        elif hasattr(fig, '_pre_derivative_x_data_list'):
            delattr(fig, '_pre_derivative_x_data_list')
            delattr(fig, '_pre_derivative_y_data_list')
            if hasattr(fig, '_pre_derivative_ylabel'):
                delattr(fig, '_pre_derivative_ylabel')
        if "derivative_order" in snap:
            fig._derivative_order = int(snap["derivative_order"])
        elif hasattr(fig, '_derivative_order'):
            delattr(fig, '_derivative_order')
        if "derivative_reversed" in snap:
            fig._derivative_reversed = bool(snap["derivative_reversed"])
        elif hasattr(fig, '_derivative_reversed'):
            delattr(fig, '_derivative_reversed')
        # Restore y-axis label if derivative was applied (legacy snaps only).
        # When axis_title_texts is present it is authoritative (parity with style ``i``).
        if "derivative_order" in snap and not isinstance(snap.get("axis_title_texts"), dict):
            try:
                current_ylabel = ax.get_ylabel() or ""
                order = int(snap["derivative_order"])
                is_reversed = snap.get("derivative_reversed", False)
                new_ylabel = update_ylabel_for_derivative(order, current_ylabel, is_reversed=is_reversed)
                ax.set_ylabel(new_ylabel)
            except Exception:
                pass

        # DON'T recalculate y_data_list - trust the snapshotted data to avoid offset drift
        # The snapshot already captured the correct y_data_list with offsets applied.
        # Recalculating from orig_y + offsets_list can introduce floating-point errors
        # or inconsistencies if the data underwent transformations (normalize, etc.)

        # Update line data with restored values from snapshot
        # This ensures line visual data matches the snapshotted data lists exactly
        for i in range(min(nlines(), len(x_data_list), len(y_data_list))):
            try:
                line(i).set_data(x_data_list[i], y_data_list[i])
            except Exception:
                pass

        # Restore rotation angle
        if 'rotation_angle' in snap:
            ax._rotation_angle = snap['rotation_angle']

        # Restore legend position (stack_label_at_bottom)
        if 'stack_label_at_bottom' in snap:
            fig._stack_label_at_bottom = bool(snap['stack_label_at_bottom'])
        if 'label_anchor_left' in snap:
            fig._label_anchor_left = bool(snap['label_anchor_left'])

        if snap.get("curve_palettes"):
            fig._curve_palette_history = [
                {
                    'palette': rec.get('palette'),
                    'indices': list(rec.get('indices', [])),
                    'low_clip': float(rec.get('low_clip', 0.08)),
                    'high_clip': float(rec.get('high_clip', 0.85)),
                }
                for rec in snap["curve_palettes"]
                if rec.get('palette') and rec.get('indices')
            ]
        elif hasattr(fig, '_curve_palette_history'):
            delattr(fig, '_curve_palette_history')

        # Restore grid state
        if 'grid' in snap:
            try:
                if snap['grid']:
                    ax.grid(True, color='0.85', linestyle='-', linewidth=0.5, alpha=0.7)
                else:
                    ax.grid(False)
            except Exception:
                pass

        # CIF tick sets & label visibility (write back to batplot module globals)
        if bp is not None and snap.get("cif_tick_series") is not None and hasattr(bp, 'cif_tick_series'):
            try:
                getattr(bp, 'cif_tick_series')[:] = [tuple(t) for t in snap["cif_tick_series"]]
            except Exception:
                pass
            sync_fig_cif_tick_series()
        if bp is not None and "cif_hkl_label_map" in snap:
            try:
                restored_hkl = {}
                for k, v in dict(snap.get("cif_hkl_label_map") or {}).items():
                    restored_hkl[str(k)] = dict(v) if isinstance(v, dict) else {}
                hkl_live = getattr(bp, "cif_hkl_label_map", None)
                if isinstance(hkl_live, dict):
                    hkl_live.clear()
                    hkl_live.update(restored_hkl)
                else:
                    setattr(bp, "cif_hkl_label_map", restored_hkl)
                    hkl_live = restored_hkl
                fig._batplot_cif_hkl_label_map = hkl_live  # type: ignore[attr-defined]
                _bp_module = sys.modules.get("__main__")
                if _bp_module is not None:
                    setattr(_bp_module, "cif_hkl_label_map", hkl_live)
            except Exception:
                pass
        if bp is not None and 'show_cif_hkl' in snap:
            try:
                new_state = bool(snap['show_cif_hkl'])
                setattr(bp, 'show_cif_hkl', new_state)
                # Keep figure attr aligned with titles / visibility (export + batch).
                fig._bp_show_cif_hkl = new_state  # type: ignore[attr-defined]
                # Also store in __main__ module so draw function can access it
                try:
                    _bp_module = sys.modules.get('__main__')
                    if _bp_module is not None:
                        setattr(_bp_module, 'show_cif_hkl', new_state)
                except Exception:
                    pass
            except Exception:
                pass
        if bp is not None and 'show_cif_titles' in snap:
            try:
                new_state = bool(snap['show_cif_titles'])
                setattr(bp, 'show_cif_titles', new_state)
                # Also update figure attribute and __main__ module
                fig._bp_show_cif_titles = new_state
                try:
                    _bp_module = sys.modules.get('__main__')
                    if _bp_module is not None:
                        setattr(_bp_module, 'show_cif_titles', new_state)
                except Exception:
                    pass
            except Exception:
                pass
        # Restore CIF per-set visibility if present
        if 'cif_set_visible' in snap:
            try:
                vis = list(snap['cif_set_visible'])
                _bp_module = sys.modules.get('__main__')
                if _bp_module is not None:
                    setattr(_bp_module, 'cif_set_visible', vis)
                fig._bp_cif_set_visible = vis  # type: ignore[attr-defined]
                if bp is not None:
                    setattr(bp, 'cif_set_visible', vis)
            except Exception:
                pass
        if 'cif_stack_y_offsets' in snap:
            try:
                fig._bp_cif_stack_y_offsets = list(snap['cif_stack_y_offsets'])
            except Exception:
                pass
        # Redraw CIF ticks after restoration if available
        if hasattr(ax, '_cif_draw_func'):
            try:
                ax._cif_draw_func()
            except Exception:
                pass

        # Restore label texts (keep numbering style)
        for i, txt in enumerate(label_text_objects):
            base = labels[i] if i < len(labels) else ""
            txt.set_text(f"{i+1}: {base}")

        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
        label_vis = snap.get("label_text_visible")
        if isinstance(label_vis, list):
            for txt, visible in zip(label_text_objects, label_vis):
                try:
                    txt.set_visible(bool(visible))
                except Exception:
                    pass
            try:
                fig._curve_names_visible = any(bool(v) for v in label_vis)
            except Exception:
                pass
        try:
            from . import interactive as _xy_interactive_mod
            _xy_interactive_mod.tick_state = tick_state
        except Exception:
            pass
        try:
            fig.canvas.draw()
        except Exception:
            try: fig.canvas.draw_idle()
            except Exception: pass
        print("Undo: restored previous state.")
    except Exception as e:
        # Keep the undo level so a failed ``b`` does not burn history.
        try:
            state_history.append(snap)
        except Exception:
            pass
        print(f"Error restoring state: {e}")
    return delta, use_Q, use_2th

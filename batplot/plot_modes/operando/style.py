"""Style config builders for operando interactive mode."""

from __future__ import annotations

from typing import Any, Tuple

import matplotlib.pyplot as plt
import numpy as np

from ...ui import capture_axes_tick_locators
from ..common.font_extras import apply_font_extras_from_cfg, font_extras_export_dict
from ..common.fonts import collect_fig_font_artists
from ..common.line_dash import capture_dash_pattern
from ..common.session_helpers import _current_tick_length
from ..common.spines import current_tick_width
from .layout import _ensure_fixed_params, _get_fig_size, _get_geometry_snapshot


def _axis_tick_width(axis_obj, which: str = 'major'):
    return current_tick_width(axis_obj, which)


def _axis_tick_length(axis_obj, which: str = "major"):
    # One capture rule with session/p/s/b (preserves length 0).
    return _current_tick_length(axis_obj, which)


def _actual_major_visibility(ax, side: str):
    try:
        if side in ("top", "bottom"):
            ticks = ax.xaxis.get_major_ticks()
            if not ticks:
                return None, None
            tick = ticks[0]
            line = tick.tick2line if side == "top" else tick.tick1line
            label = tick.label2 if side == "top" else tick.label1
        else:
            ticks = ax.yaxis.get_major_ticks()
            if not ticks:
                return None, None
            tick = ticks[0]
            line = tick.tick2line if side == "right" else tick.tick1line
            label = tick.label2 if side == "right" else tick.label1
        return bool(line.get_visible()), bool(label.get_visible())
    except Exception:
        return None, None


def _wasd_bool_from_state_or_actual(ts, side: str, prop: str, actual, default: bool) -> bool:
    prefix = {"top": "t", "bottom": "b", "left": "l", "right": "r"}[side]
    legacy = {"top": "tx", "bottom": "bx", "left": "ly", "right": "ry"}[side]
    if actual is not None:
        return bool(actual)
    return bool(ts.get(f"{prefix}_{prop}", ts.get(legacy, default)))


def build_operando_ec_style_config_v2(fig, ax, im, cbar, ec_ax, exp_choice: str) -> Tuple[dict, str]:
    """Build version-2 operando style JSON (.bps / .bpsg) with or without EC."""
    if exp_choice not in ("ps", "psg"):
        raise ValueError("exp_choice must be 'ps' or 'psg'")
    fig_w, fig_h = _get_fig_size(fig)
    cb_w_in, cb_gap_in, ec_gap_in, ec_w_in, ax_w_in, ax_h_in = _ensure_fixed_params(fig, ax, cbar.ax, ec_ax)
    fam = plt.rcParams.get("font.sans-serif", [""])[0]
    fsize = plt.rcParams.get("font.size", None)
    cmap_name = getattr(im, "_operando_cmap_name", None)
    if cmap_name is None:
        cmap_name = getattr(im.get_cmap(), "name", None)
    cb_vis = bool(cbar.ax.get_visible())
    ec_vis = bool(ec_ax.get_visible()) if ec_ax is not None else None
    cb_label_text = str(getattr(cbar.ax, "_colorbar_label", cbar.ax.get_ylabel() or "Intensity"))
    cb_label_mode = getattr(fig, "_colorbar_label_mode", "highlow")

    op_ts = getattr(ax, "_saved_tick_state", {}) or {}
    # Prefer on-screen major tick/label visibility (same as session dump).
    op_left_ticks, op_left_labels = _actual_major_visibility(ax, "left")
    op_top_ticks, op_top_labels = _actual_major_visibility(ax, "top")
    op_bottom_ticks, op_bottom_labels = _actual_major_visibility(ax, "bottom")
    op_right_ticks, op_right_labels = _actual_major_visibility(ax, "right")
    def _axis_title_visible(axis_obj, which: str) -> bool:
        try:
            lbl = axis_obj.yaxis.label if which == "y" else axis_obj.xaxis.label
            return bool(lbl.get_visible())
        except Exception:
            return bool(axis_obj.get_ylabel() if which == "y" else axis_obj.get_xlabel())

    op_wasd = {
        "left": {
            "spine": bool(ax.spines.get("left").get_visible() if ax.spines.get("left") else False),
            "ticks": _wasd_bool_from_state_or_actual(op_ts, "left", "ticks", op_left_ticks, True),
            "minor": bool(op_ts.get("mly", False)),
            "labels": _wasd_bool_from_state_or_actual(op_ts, "left", "labels", op_left_labels, True),
            "title": _axis_title_visible(ax, "y"),
        },
        "top": {
            "spine": bool(ax.spines.get("top").get_visible() if ax.spines.get("top") else False),
            "ticks": _wasd_bool_from_state_or_actual(op_ts, "top", "ticks", op_top_ticks, False),
            "minor": bool(op_ts.get("mtx", False)),
            "labels": _wasd_bool_from_state_or_actual(op_ts, "top", "labels", op_top_labels, False),
            "title": bool(getattr(ax, "_top_xlabel_on", False)),
        },
        "bottom": {
            "spine": bool(ax.spines.get("bottom").get_visible() if ax.spines.get("bottom") else False),
            "ticks": _wasd_bool_from_state_or_actual(op_ts, "bottom", "ticks", op_bottom_ticks, True),
            "minor": bool(op_ts.get("mbx", False)),
            "labels": _wasd_bool_from_state_or_actual(op_ts, "bottom", "labels", op_bottom_labels, True),
            "title": _axis_title_visible(ax, "x"),
        },
        "right": {
            "spine": bool(ax.spines.get("right").get_visible() if ax.spines.get("right") else False),
            "ticks": _wasd_bool_from_state_or_actual(op_ts, "right", "ticks", op_right_ticks, False),
            "minor": bool(op_ts.get("mry", False)),
            "labels": _wasd_bool_from_state_or_actual(op_ts, "right", "labels", op_right_labels, False),
            "title": bool(getattr(ax, "_right_ylabel_on", False)),
        },
    }

    if ec_ax is not None:
        ec_ts = getattr(ec_ax, "_saved_tick_state", {})
        ec_left_ticks, ec_left_labels = _actual_major_visibility(ec_ax, "left")
        ec_top_ticks, ec_top_labels = _actual_major_visibility(ec_ax, "top")
        ec_bottom_ticks, ec_bottom_labels = _actual_major_visibility(ec_ax, "bottom")
        ec_right_ticks, ec_right_labels = _actual_major_visibility(ec_ax, "right")
        ec_wasd = {
            "left": {
                "spine": bool(ec_ax.spines.get("left").get_visible() if ec_ax.spines.get("left") else False),
                "ticks": _wasd_bool_from_state_or_actual(ec_ts, "left", "ticks", ec_left_ticks, False),
                "minor": bool(ec_ts.get("mly", False)),
                "labels": _wasd_bool_from_state_or_actual(ec_ts, "left", "labels", ec_left_labels, False),
                "title": False,
            },
            "top": {
                "spine": bool(ec_ax.spines.get("top").get_visible() if ec_ax.spines.get("top") else False),
                "ticks": _wasd_bool_from_state_or_actual(ec_ts, "top", "ticks", ec_top_ticks, False),
                "minor": bool(ec_ts.get("mtx", False)),
                "labels": _wasd_bool_from_state_or_actual(ec_ts, "top", "labels", ec_top_labels, False),
                "title": bool(getattr(ec_ax, "_top_xlabel_on", False)),
            },
            "bottom": {
                "spine": bool(ec_ax.spines.get("bottom").get_visible() if ec_ax.spines.get("bottom") else False),
                "ticks": _wasd_bool_from_state_or_actual(ec_ts, "bottom", "ticks", ec_bottom_ticks, True),
                "minor": bool(ec_ts.get("mbx", False)),
                "labels": _wasd_bool_from_state_or_actual(ec_ts, "bottom", "labels", ec_bottom_labels, True),
                "title": _axis_title_visible(ec_ax, "x"),
            },
            "right": {
                "spine": bool(ec_ax.spines.get("right").get_visible() if ec_ax.spines.get("right") else False),
                "ticks": _wasd_bool_from_state_or_actual(ec_ts, "right", "ticks", ec_right_ticks, True),
                "minor": bool(ec_ts.get("mry", False)),
                "labels": _wasd_bool_from_state_or_actual(ec_ts, "right", "labels", ec_right_labels, True),
                "title": _axis_title_visible(ec_ax, "y"),
            },
        }
        # Ions mode is overlay-only — do not rewrite WASD for tick labels.
    else:
        ec_wasd = {}

    from ...ui import resolve_spine_dump_color

    op_spines = {}
    for name in ("bottom", "top", "left", "right"):
        sp = ax.spines.get(name)
        if sp:
            op_spines[name] = {
                "linewidth": float(sp.get_linewidth()),
                "visible": bool(sp.get_visible()),
                "color": resolve_spine_dump_color(ax, name, fig),
            }
    ec_spines = {}
    if ec_ax is not None:
        for name in ("bottom", "top", "left", "right"):
            sp = ec_ax.spines.get(name)
            if sp:
                ec_spines[name] = {
                    "linewidth": float(sp.get_linewidth()),
                    "visible": bool(sp.get_visible()),
                    "color": resolve_spine_dump_color(ec_ax, name, fig),
                }

    def _tw(axis_obj, which_axis: str = "x", which_tick: str = "major"):
        axis = axis_obj.xaxis if which_axis == "x" else axis_obj.yaxis
        return _axis_tick_width(axis, "major" if which_tick == "major" else "minor")

    op_ticks = {
        "x_major": _tw(ax, "x", "major"),
        "x_minor": _tw(ax, "x", "minor"),
        "y_major": _tw(ax, "y", "major"),
        "y_minor": _tw(ax, "y", "minor"),
    }
    op_tick_lengths = {
        "x_major": _axis_tick_length(ax.xaxis, "major"),
        "x_minor": _axis_tick_length(ax.xaxis, "minor"),
        "y_major": _axis_tick_length(ax.yaxis, "major"),
        "y_minor": _axis_tick_length(ax.yaxis, "minor"),
    }
    op_tick_locator_state = capture_axes_tick_locators(ax, ("x", "y"))
    ec_ticks = {}
    ec_tick_lengths = {}
    ec_tick_locator_state = {}
    if ec_ax is not None:
        ec_ticks = {
            "x_major": _tw(ec_ax, "x", "major"),
            "x_minor": _tw(ec_ax, "x", "minor"),
            "y_major": _tw(ec_ax, "y", "major"),
            "y_minor": _tw(ec_ax, "y", "minor"),
        }
        ec_tick_lengths = {
            "x_major": _axis_tick_length(ec_ax.xaxis, "major"),
            "x_minor": _axis_tick_length(ec_ax.xaxis, "minor"),
            "y_major": _axis_tick_length(ec_ax.yaxis, "major"),
            "y_minor": _axis_tick_length(ec_ax.yaxis, "minor"),
        }
        ec_tick_locator_state = capture_axes_tick_locators(ec_ax, ("x", "y"))

    ec_curve = {}
    if ec_ax is not None:
        ln = getattr(ec_ax, "_ec_line", None)
        if ln is None and ec_ax.lines:
            ln = ec_ax.lines[0]
        if ln is not None:
            try:
                ec_curve = {
                    "color": ln.get_color(),
                    "linewidth": float(ln.get_linewidth()),
                    "linestyle": ln.get_linestyle(),
                    "dash_pattern": capture_dash_pattern(ln),
                    "marker": ln.get_marker(),
                    "markersize": ln.get_markersize(),
                    "alpha": ln.get_alpha(),
                }
            except Exception:
                pass

    op_ylim_cur = ax.get_ylim()
    op_reversed = bool(op_ylim_cur[0] > op_ylim_cur[1])
    if ec_ax is not None:
        ec_ylim_cur = ec_ax.get_ylim()
        ec_reversed = bool(ec_ylim_cur[0] > ec_ylim_cur[1])
        ec_y_mode = getattr(ec_ax, "_ec_y_mode", "time")
        _ip = getattr(ec_ax, "_ion_params", None)
        ion_params = dict(_ip) if isinstance(_ip, dict) else _ip
        ion_guides = []
        for gl in getattr(ec_ax, "_ion_guides", []) or []:
            try:
                ydata = np.asarray(gl.get_ydata(), float)
                if ydata.size:
                    ion_guides.append(float(ydata[0]))
            except Exception:
                pass
        ion_annots = []
        for ann in getattr(ec_ax, "_ion_annots", []) or []:
            try:
                ion_annots.append({"text": ann.get_text(), "xy": tuple(float(v) for v in ann.xy)})
            except Exception:
                pass
        ec_labelpads = {
            "x": getattr(ec_ax.xaxis, "labelpad", None),
            "y": getattr(ec_ax.yaxis, "labelpad", None),
        }
        ec_custom_labels = dict(getattr(ec_ax, '_custom_labels', {'x': None, 'y_time': None, 'y_ions': None}))
        saved_time_ylim = getattr(ec_ax, '_saved_time_ylim', None)
        if isinstance(saved_time_ylim, (list, tuple)) and len(saved_time_ylim) == 2:
            saved_time_ylim = [float(saved_time_ylim[0]), float(saved_time_ylim[1])]
        else:
            saved_time_ylim = None
        ec_title_offsets = {
            "top_y": float(getattr(ec_ax, "_top_xlabel_manual_offset_y_pts", 0.0) or 0.0),
            "top_x": float(getattr(ec_ax, "_top_xlabel_manual_offset_x_pts", 0.0) or 0.0),
            "bottom_y": float(getattr(ec_ax, "_bottom_xlabel_manual_offset_y_pts", 0.0) or 0.0),
            "left_x": float(getattr(ec_ax, "_left_ylabel_manual_offset_x_pts", 0.0) or 0.0),
            "right_x": float(getattr(ec_ax, "_right_ylabel_manual_offset_x_pts", 0.0) or 0.0),
            "right_y": float(getattr(ec_ax, "_right_ylabel_manual_offset_y_pts", 0.0) or 0.0),
        }
        ec_grid = dict(getattr(ec_ax, "_ec_grid", None) or {})
    else:
        ec_reversed = False
        ec_y_mode = "time"
        ion_params = None
        ion_guides = []
        ion_annots = []
        ec_labelpads = {}
        ec_custom_labels = {'x': None, 'y_time': None, 'y_ions': None}
        saved_time_ylim = None
        ec_title_offsets = {}
        ec_grid = {}

    try:
        clim = im.get_clim()
        intensity_range = [float(clim[0]), float(clim[1])]
    except Exception:
        intensity_range = None

    op_labelpads = {"x": getattr(ax.xaxis, "labelpad", None), "y": getattr(ax.yaxis, "labelpad", None)}
    op_title_offsets = {
        "top_y": float(getattr(ax, "_top_xlabel_manual_offset_y_pts", 0.0) or 0.0),
        "top_x": float(getattr(ax, "_top_xlabel_manual_offset_x_pts", 0.0) or 0.0),
        "bottom_y": float(getattr(ax, "_bottom_xlabel_manual_offset_y_pts", 0.0) or 0.0),
        "left_x": float(getattr(ax, "_left_ylabel_manual_offset_x_pts", 0.0) or 0.0),
        "right_x": float(getattr(ax, "_right_ylabel_manual_offset_x_pts", 0.0) or 0.0),
        "right_y": float(getattr(ax, "_right_ylabel_manual_offset_y_pts", 0.0) or 0.0),
    }

    cb_h_offset = getattr(cbar.ax, "_cb_h_offset_in", 0.0)
    ec_h_offset = getattr(ec_ax, "_ec_h_offset_in", 0.0) if ec_ax is not None else None

    cb_ticks_left = True
    cb_label_left = True
    try:
        cb_ticks_left = any(
            getattr(tick, 'tick1line', None) and tick.tick1line.get_visible()
            for tick in cbar.ax.yaxis.get_major_ticks()
        )
        cb_label_left = (cbar.ax.yaxis.get_label_position() == 'left')
    except Exception:
        pass

    op_custom_labels = dict(getattr(ax, '_custom_labels', {'x': None, 'y': None}))

    cif_cfg = None
    series = list(getattr(ax, "_operando_cif_tick_series", None) or [])

    def _json_color(c):
        try:
            if isinstance(c, (list, tuple)) and len(c) >= 3:
                return [float(c[0]), float(c[1]), float(c[2])] + (
                    [float(c[3])] if len(c) > 3 else []
                )
        except Exception:
            pass
        return c

    def _json_peaks(peaks):
        try:
            return [float(v) for v in list(peaks)]
        except Exception:
            return list(peaks) if peaks is not None else []

    # Non-empty series: always export CIF metadata. Empty series: still embed
    # tick_series=[] on psg so batch undo can clear a first interactive add.
    # Style-only (.bps) with no CIF omits the block (legacy BC).
    if series or exp_choice != "ps":
        cif_cfg = {
            "show_hkl": bool(getattr(fig, "_operando_cif_show_hkl", False)),
            "show_titles": bool(getattr(fig, "_operando_cif_show_titles", True)),
            "placement": str(getattr(fig, "_operando_cif_placement", "below")),
            "y_positions": list(getattr(fig, "_operando_cif_y_positions", [])),
            "labels": [str(entry[0]) for entry in series],
            "files": [str(entry[1]) for entry in series],
            "colors": [_json_color(entry[-1]) for entry in series],
            "colormap": getattr(fig, "_operando_cif_colormap", None),
            "highlight": bool(getattr(fig, "_operando_cif_highlight", False)),
            "title_font": dict(getattr(fig, "_operando_cif_title_font", None) or {}),
            "title_visible": list(getattr(fig, "_operando_cif_title_visible", None) or []),
            "set_visible": list(getattr(fig, "_operando_cif_set_visible", None) or []),
        }
        # Embed peak data in style+geometry (psg) and batch capture so p/i/b
        # can round-trip CIF sets added interactively without re-reading files.
        if exp_choice != "ps":
            cif_cfg["tick_series"] = [
                [
                    str(e[0]),
                    str(e[1]),
                    _json_peaks(e[2]),
                    (None if e[3] is None else float(e[3])),
                    (None if e[4] is None else float(e[4])),
                    _json_color(e[5]),
                ]
                for e in series
            ]
            try:
                cif_cfg["hkl_label_map"] = dict(
                    getattr(ax, "_operando_cif_hkl_label_map", None) or {}
                )
            except Exception:
                cif_cfg["hkl_label_map"] = {}

    ec_payload = {
        "wasd_state": ec_wasd,
        "spines": ec_spines,
        "ticks": {
            "widths": ec_ticks,
            "lengths": ec_tick_lengths,
            "direction": getattr(fig, "_tick_direction", "out"),
            "locator_state": ec_tick_locator_state,
        },
        "curve": ec_curve,
        "grid": ec_grid,
        "y_mode": ec_y_mode,
        "ion_params": ion_params,
        # p/i contract: never embed ion time-series arrays (recompute on import).
        # Session ``s`` still persists ions_abs via dump_operando_session.
        "ion_guides": ion_guides,
        "ion_annots": ion_annots,
        "visible": ec_vis,
        "labelpads": ec_labelpads,
        "title_offsets": ec_title_offsets,
        "custom_labels": ec_custom_labels,
    }
    # View/limit bookkeeping is geometry (psg / session), not style-only ``ps``.
    if exp_choice != "ps":
        ec_payload["prev_ec_xlim"] = (
            tuple(getattr(ec_ax, "_prev_ec_xlim", ()))
            if ec_ax is not None and getattr(ec_ax, "_prev_ec_xlim", None) is not None
            else None
        )
        ec_payload["ions_xlim_expanded"] = (
            bool(getattr(ec_ax, "_ions_xlim_expanded", False)) if ec_ax is not None else False
        )
        ec_payload["saved_time_ylim"] = saved_time_ylim
    else:
        ec_payload["prev_ec_xlim"] = None
        ec_payload["ions_xlim_expanded"] = False
        ec_payload["saved_time_ylim"] = None

    cfg = {
        "kind": "operando_ec_style" if exp_choice == "ps" else "operando_ec_style_geom",
        "version": 2,
        "figure": {
            "cb_visible": cb_vis,
            "cb_label_mode": cb_label_mode,
        },
        "operando": {
            "cmap": cmap_name,
            "wasd_state": op_wasd,
            "spines": op_spines,
            "ticks": {
                "widths": op_ticks,
                "lengths": op_tick_lengths,
                "direction": getattr(fig, "_tick_direction", "out"),
                "locator_state": op_tick_locator_state,
            },
            "labelpads": op_labelpads,
            "title_offsets": op_title_offsets,
            "custom_labels": op_custom_labels,
        },
        "ec": ec_payload,
        "font": {"family": fam, "size": fsize, "mathtext_fontset": plt.rcParams.get("mathtext.fontset"), **font_extras_export_dict(fig)},
        "colorbar": {
            "label": cb_label_text,
            "mode": cb_label_mode,
            "visible": cb_vis,
            "ticks_left": cb_ticks_left,
            "label_left": cb_label_left,
        },
    }
    # Style+geometry (psg): persist canvas/panel inches, clim, reverse, axes limits.
    # Style-only (ps): omit view-geometry so import (i) does not resize/reclim/flip.
    if exp_choice != "ps":
        cfg["figure"]["canvas_size"] = [fig_w, fig_h]
        cfg["geometry"] = {
            "op_w_in": ax_w_in,
            "op_h_in": ax_h_in,
            "ec_w_in": ec_w_in,
            "cb_w_in": cb_w_in,
            "cb_gap_in": cb_gap_in,
            "ec_gap_in": ec_gap_in,
            "cb_h_offset": float(cb_h_offset),
            "ec_h_offset": float(ec_h_offset) if ec_h_offset is not None else None,
        }
        cfg["operando"]["y_reversed"] = op_reversed
        cfg["operando"]["intensity_range"] = intensity_range
        cfg["ec"]["y_reversed"] = ec_reversed
    default_ext = ".bps" if exp_choice == "ps" else ".bpsg"
    if exp_choice == "psg":
        cfg["axes_geometry"] = _get_geometry_snapshot(ax, ec_ax)
    if cif_cfg is not None:
        cfg["cif"] = cif_cfg
    if getattr(fig, "_is_dqdv_2d_contour", False):
        try:
            # Labels/zlabel are style; V_lo/V_hi rebuild the map → geometry only.
            d2 = {
                "row_labels": [str(s) for s in (fig._dqdv_2d_row_labels or [])],
                "zlabel": str(getattr(fig, "_dqdv_2d_zlabel", "dQ/dV")),
                "axis_mapping_version": int(getattr(fig, "_dqdv_2d_axis_mapping_version", 2)),
            }
            if exp_choice == "psg":
                d2["v_lo"] = float(fig._dqdv_2d_v_lo)
                d2["v_hi"] = float(fig._dqdv_2d_v_hi)
            cfg["dqdv_2d"] = d2
        except Exception:
            pass
    return cfg, default_ext

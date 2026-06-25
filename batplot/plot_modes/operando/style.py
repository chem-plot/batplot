"""Style config builders for operando interactive mode."""

from __future__ import annotations

from typing import Tuple

import matplotlib.pyplot as plt
import numpy as np

from ...ui import capture_axes_tick_locators
from .layout import _ensure_fixed_params, _get_fig_size, _get_geometry_snapshot


def _axis_tick_width(axis_obj, which: str = 'major'):
    try:
        ticks = axis_obj.get_major_ticks() if which == 'major' else axis_obj.get_minor_ticks()
        if not ticks:
            tick_kw = axis_obj._major_tick_kw if which == 'major' else axis_obj._minor_tick_kw
            width = tick_kw.get('width')
            if width is None:
                axis_name = getattr(axis_obj, 'axis_name', 'x')
                rc_key = f"{axis_name}tick.{which}.width"
                width = plt.rcParams.get(rc_key)
            return float(width) if width is not None else None
        for tick in ticks:
            line = tick.tick1line
            if line.get_visible():
                return float(line.get_linewidth())
            line2 = getattr(tick, 'tick2line', None)
            if line2 is not None and line2.get_visible():
                return float(line2.get_linewidth())
        return None
    except (AttributeError, TypeError, ValueError, KeyError):
        return None


def _axis_tick_length(axis_obj, which: str = "major"):
    try:
        ticks = axis_obj.get_major_ticks() if which == "major" else axis_obj.get_minor_ticks()
        if ticks:
            return float(ticks[0].tick1line.get_markersize())
    except Exception:
        pass
    try:
        tick_kw = axis_obj._major_tick_kw if which == "major" else axis_obj._minor_tick_kw
        length = tick_kw.get("size") or tick_kw.get("length")
        return float(length) if length is not None else None
    except Exception:
        return None


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

    op_ts = getattr(ax, "_saved_tick_state", {})
    op_wasd = {
        "left": {
            "spine": bool(ax.spines.get("left").get_visible() if ax.spines.get("left") else False),
            "ticks": bool(op_ts.get("l_ticks", op_ts.get("ly", True))),
            "minor": bool(op_ts.get("mly", False)),
            "labels": bool(op_ts.get("l_labels", op_ts.get("ly", True))),
            "title": bool(ax.get_ylabel()),
        },
        "top": {
            "spine": bool(ax.spines.get("top").get_visible() if ax.spines.get("top") else False),
            "ticks": bool(op_ts.get("t_ticks", op_ts.get("tx", False))),
            "minor": bool(op_ts.get("mtx", False)),
            "labels": bool(op_ts.get("t_labels", op_ts.get("tx", False))),
            "title": bool(getattr(ax, "_top_xlabel_on", False)),
        },
        "bottom": {
            "spine": bool(ax.spines.get("bottom").get_visible() if ax.spines.get("bottom") else False),
            "ticks": bool(op_ts.get("b_ticks", op_ts.get("bx", True))),
            "minor": bool(op_ts.get("mbx", False)),
            "labels": bool(op_ts.get("b_labels", op_ts.get("bx", True))),
            "title": bool(ax.get_xlabel()),
        },
        "right": {
            "spine": bool(ax.spines.get("right").get_visible() if ax.spines.get("right") else False),
            "ticks": bool(op_ts.get("r_ticks", op_ts.get("ry", False))),
            "minor": bool(op_ts.get("mry", False)),
            "labels": bool(op_ts.get("r_labels", op_ts.get("ry", False))),
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
                "title": bool(ec_ax.get_xlabel()),
            },
            "right": {
                "spine": bool(ec_ax.spines.get("right").get_visible() if ec_ax.spines.get("right") else False),
                "ticks": _wasd_bool_from_state_or_actual(ec_ts, "right", "ticks", ec_right_ticks, True),
                "minor": bool(ec_ts.get("mry", False)),
                "labels": _wasd_bool_from_state_or_actual(ec_ts, "right", "labels", ec_right_labels, True),
                "title": bool(ec_ax.get_ylabel()),
            },
        }
    else:
        ec_wasd = {}

    op_spines = {}
    for name in ("bottom", "top", "left", "right"):
        sp = ax.spines.get(name)
        if sp:
            op_spines[name] = {
                "linewidth": float(sp.get_linewidth()),
                "visible": bool(sp.get_visible()),
                "color": sp.get_edgecolor(),
            }
    ec_spines = {}
    if ec_ax is not None:
        for name in ("bottom", "top", "left", "right"):
            sp = ec_ax.spines.get(name)
            if sp:
                ec_spines[name] = {
                    "linewidth": float(sp.get_linewidth()),
                    "visible": bool(sp.get_visible()),
                    "color": sp.get_edgecolor(),
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
                ec_curve = {"color": ln.get_color(), "linewidth": float(ln.get_linewidth())}
            except Exception:
                pass

    op_ylim_cur = ax.get_ylim()
    op_reversed = bool(op_ylim_cur[0] > op_ylim_cur[1])
    if ec_ax is not None:
        ec_ylim_cur = ec_ax.get_ylim()
        ec_reversed = bool(ec_ylim_cur[0] > ec_ylim_cur[1])
        ec_y_mode = getattr(ec_ax, "_ec_y_mode", "time")
        ion_params = getattr(ec_ax, "_ion_params", None)
        ions_abs = getattr(ec_ax, "_ions_abs", None)
        try:
            ions_abs_payload = np.asarray(ions_abs, float).tolist() if ions_abs is not None else None
        except Exception:
            ions_abs_payload = None
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
        ions_abs_payload = None
        ion_guides = []
        ion_annots = []
        ec_labelpads = {}
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

    cif_cfg = None
    if getattr(ax, "_operando_cif_tick_series", None):
        cif_cfg = {
            "show_hkl": bool(getattr(fig, "_operando_cif_show_hkl", False)),
            "show_titles": bool(getattr(fig, "_operando_cif_show_titles", True)),
            "placement": str(getattr(fig, "_operando_cif_placement", "below")),
            "y_positions": list(getattr(fig, "_operando_cif_y_positions", [])),
            "labels": [str(entry[0]) for entry in ax._operando_cif_tick_series],
            "colors": [entry[-1] for entry in ax._operando_cif_tick_series],
            "colormap": getattr(fig, "_operando_cif_colormap", None),
            "highlight": bool(getattr(fig, "_operando_cif_highlight", False)),
            "title_font": dict(getattr(fig, "_operando_cif_title_font", None) or {}),
            "title_visible": list(getattr(fig, "_operando_cif_title_visible", None) or []),
            "set_visible": list(getattr(fig, "_operando_cif_set_visible", None) or []),
        }

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
        "y_reversed": ec_reversed,
        "y_mode": ec_y_mode,
        "ion_params": ion_params,
        "ions_abs": ions_abs_payload,
        "prev_ec_xlim": tuple(getattr(ec_ax, "_prev_ec_xlim", ())) if ec_ax is not None and getattr(ec_ax, "_prev_ec_xlim", None) is not None else None,
        "ions_xlim_expanded": bool(getattr(ec_ax, "_ions_xlim_expanded", False)) if ec_ax is not None else False,
        "ion_guides": ion_guides,
        "ion_annots": ion_annots,
        "visible": ec_vis,
        "labelpads": ec_labelpads,
        "title_offsets": ec_title_offsets,
    }

    cfg = {
        "kind": "operando_ec_style" if exp_choice == "ps" else "operando_ec_style_geom",
        "version": 2,
        "figure": {"canvas_size": [fig_w, fig_h], "cb_visible": cb_vis, "cb_label_mode": cb_label_mode},
        "geometry": {
            "op_w_in": ax_w_in,
            "op_h_in": ax_h_in,
            "ec_w_in": ec_w_in,
            "cb_h_offset": float(cb_h_offset),
            "ec_h_offset": float(ec_h_offset) if ec_h_offset is not None else None,
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
            "y_reversed": op_reversed,
            "intensity_range": intensity_range,
            "labelpads": op_labelpads,
            "title_offsets": op_title_offsets,
        },
        "ec": ec_payload,
        "font": {"family": fam, "size": fsize, "mathtext_fontset": plt.rcParams.get("mathtext.fontset")},
        "colorbar": {"label": cb_label_text, "mode": cb_label_mode, "visible": cb_vis},
    }
    default_ext = ".bps" if exp_choice == "ps" else ".bpsg"
    if exp_choice == "psg":
        cfg["axes_geometry"] = _get_geometry_snapshot(ax, ec_ax)
    if cif_cfg is not None:
        cfg["cif"] = cif_cfg
    if getattr(fig, "_is_dqdv_2d_contour", False):
        try:
            cfg["dqdv_2d"] = {
                "v_lo": float(fig._dqdv_2d_v_lo),
                "v_hi": float(fig._dqdv_2d_v_hi),
                "row_labels": [str(s) for s in (fig._dqdv_2d_row_labels or [])],
                "zlabel": str(getattr(fig, "_dqdv_2d_zlabel", "dQ/dV")),
                "axis_mapping_version": int(getattr(fig, "_dqdv_2d_axis_mapping_version", 2)),
            }
        except Exception:
            pass
    return cfg, default_ext

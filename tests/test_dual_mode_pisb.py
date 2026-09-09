"""GC dual + XY dual-wl: WASD top, rename, p/i/s/b, and BC."""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from types import SimpleNamespace

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import colors as mcolors

from batplot.plot_modes.common.axis_state import capture_axis_wasd_state
from batplot.plot_modes.electrochem.session import dump_ec_session, load_ec_session
from batplot.plot_modes.electrochem.style import (
    _get_style_snapshot,
    apply_dual_top_axis_style,
    ec_dual_secax,
    reapply_ec_dual_secondary_chrome,
    suppress_ec_dual_duplicate_top_title,
)
from batplot.plot_modes.electrochem.style_apply import apply_ec_style_config
from batplot.plot_modes.electrochem.undo_state import ec_push_state, ec_restore_state
from batplot.plot_modes.xy import axis_units as AU
from batplot.plot_modes.xy.style import apply_style_config as apply_xy_style
from batplot.plotting import update_labels
from batplot.ui import position_top_xlabel, set_spine_side_color


def _hex(c):
    return mcolors.to_hex(mcolors.to_rgb(c))


def _make_dual_gc(*, top_ticks=True, top_title=True, c_th=150.0):
    fig, ax = plt.subplots()
    x = np.linspace(0.0, 100.0, 20)
    y = np.linspace(3.0, 4.0, 20)
    (c,) = ax.plot(x, y, label="1")
    (d,) = ax.plot(x[::-1], y, label="_nolegend_")
    for ln in (c, d):
        ln._orig_xdata_gc = np.asarray(ln.get_xdata(), float).copy()
    sec = ax.secondary_xaxis("top", functions=(lambda v: v / c_th, lambda v: v * c_th))
    sec.set_xlabel(f"Number of ions (C / {c_th:g} mAh g$^{{-1}}$)")
    ax.set_xlabel("Specific Capacity (mAh g$^{-1}$)")
    ax.set_ylabel("Potential (V)")
    fig._xaxis_mode = "dual"
    fig._xaxis_c_theoretical = c_th
    fig._xaxis_swapped = False
    fig._xaxis_secondary = sec
    fig._gc_capacity_mode = "per_cycle"
    fig._ec_wasd_state = {
        "top": {
            "spine": True,
            "ticks": top_ticks,
            "minor": False,
            "labels": top_ticks,
            "title": top_title,
        },
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "right": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
    }
    reapply_ec_dual_secondary_chrome(fig, ax)
    cycle_lines = {1: {"charge": c, "discharge": d}}
    return fig, ax, sec, cycle_lines


def test_dual_wasd_top_title_no_capacity_duplicate():
    fig, ax, sec, _ = _make_dual_gc(top_title=True)
    suppress_ec_dual_duplicate_top_title(ax, fig)
    assert ax._top_xlabel_on is False
    assert bool(sec.xaxis.label.get_visible()) is True
    ax._top_xlabel_on = True
    position_top_xlabel(ax, fig, {})
    suppress_ec_dual_duplicate_top_title(ax, fig)
    art = getattr(ax, "_top_xlabel_artist", None)
    if art is not None:
        assert art.get_visible() is False
    plt.close(fig)


def test_dual_wasd_capture_reads_secondary():
    fig, ax, sec, _ = _make_dual_gc(top_ticks=True, top_title=True)
    sec.tick_params(axis="x", which="major", top=True, labeltop=True)
    fig.canvas.draw()
    wasd = capture_axis_wasd_state(ax, use_actual_major_visibility=True, top_axis=sec)
    assert wasd["top"]["ticks"] is True
    assert wasd["top"]["title"] is True
    plt.close(fig)


def test_dual_style_and_session_roundtrip(tmp_path: Path):
    fig, ax, sec, cycle_lines = _make_dual_gc()
    sec.set_xlabel("Custom ions")
    set_spine_side_color(sec, "top", "#008000", fig=fig, title_color="#123456")
    fig._tick_lengths = {"major": 9.0, "minor": 4.5}
    reapply_ec_dual_secondary_chrome(fig, ax, tick_lengths=fig._tick_lengths)

    cfg = _get_style_snapshot(fig, ax, cycle_lines, tick_state={})
    assert cfg["xaxis_dual"]["mode"] == "dual"
    assert cfg["xaxis_dual"]["top_axis"]["xlabel"] == "Custom ions"
    assert cfg["wasd_state"]["top"]["title"] is True

    fig2, ax2, _sec2, cycle_lines2 = _make_dual_gc(top_ticks=False, top_title=False)
    ok = apply_ec_style_config(
        cfg,
        fig=fig2,
        ax=ax2,
        cycle_lines=cycle_lines2,
        file_data=None,
        tick_state={},
        is_multi_file=False,
        silent=True,
    )
    assert ok is True
    sec2b = ec_dual_secax(fig2)
    assert sec2b is not None
    assert sec2b.get_xlabel() == "Custom ions"
    assert _hex(sec2b.xaxis.label.get_color()) == "#123456"
    assert ax2._top_xlabel_on is False

    pkl = tmp_path / "dual.pkl"
    dump_ec_session(str(pkl), fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)
    loaded = load_ec_session(str(pkl))
    assert loaded is not None
    fig3, ax3, _meta = loaded[:3]
    sec3 = ec_dual_secax(fig3)
    assert sec3 is not None
    assert sec3.get_xlabel() == "Custom ions"
    assert ax3._top_xlabel_on is False
    plt.close(fig)
    plt.close(fig2)
    plt.close(fig3)


def test_dual_undo_restores_rename_and_wasd_top():
    fig, ax, sec, cycle_lines = _make_dual_gc()
    sec.set_xlabel("Ions custom")
    ax.set_xlabel("Capacity custom")
    ax._stored_xlabel = "Capacity custom"
    set_spine_side_color(sec, "top", "green", fig=fig)
    tick_state = {
        "b_ticks": True, "t_ticks": True, "l_ticks": True, "r_ticks": False,
        "b_labels": True, "t_labels": True, "l_labels": True, "r_labels": False,
    }
    history: list = []

    def apply_wasd():
        reapply_ec_dual_secondary_chrome(fig, ax, wasd_state=getattr(fig, "_ec_wasd_state", None))

    ec_push_state(
        state_history=history,
        fig=fig,
        ax=ax,
        tick_state=tick_state,
        cycle_lines=cycle_lines,
        file_data=None,
        is_multi_file=False,
        note="before",
    )
    ax.set_xlabel("MUTATED")
    sec.set_xlabel("MUTATED TOP")
    fig._ec_wasd_state["top"]["ticks"] = False
    fig._ec_wasd_state["top"]["title"] = False
    reapply_ec_dual_secondary_chrome(fig, ax)

    ec_restore_state(
        state_history=history,
        fig=fig,
        ax=ax,
        tick_state=tick_state,
        cycle_lines=cycle_lines,
        file_data=None,
        is_multi_file=False,
        apply_wasd_state=apply_wasd,
        update_tick_visibility=lambda: None,
        apply_nice_ticks=lambda: None,
        apply_display_mode=lambda *_a, **_k: None,
        apply_font_size=lambda *_a, **_k: None,
        apply_font_family=lambda *_a, **_k: None,
        ec_font_artists=lambda *_a, **_k: [],
    )
    sec2 = ec_dual_secax(fig)
    assert sec2 is not None
    assert ax.get_xlabel() == "Capacity custom"
    assert sec2.get_xlabel() == "Ions custom"
    assert bool(sec2.xaxis.label.get_visible()) is True
    assert _hex(sec2.spines["top"].get_edgecolor()) == _hex("green")
    plt.close(fig)


def test_old_ions_session_without_orig_xdata_not_double_scaled(tmp_path: Path):
    ions_x = np.linspace(0.0, 0.5, 8)
    y = np.linspace(3.0, 4.0, 8)
    sess = {
        "kind": "ec_gc",
        "version": 2,
        "figure": {
            "size": (6.0, 4.0),
            "dpi": 100,
            "frame_size": (5.0, 3.5),
            "axes_bbox": {"left": 0.12, "bottom": 0.12, "right": 0.95, "top": 0.92},
        },
        "frame_size": (5.0, 3.5),
        "axis": {"xlim": (0.0, 0.5), "ylim": (3.0, 4.0)},
        "subplot_margins": {"left": 0.12, "right": 0.95, "bottom": 0.12, "top": 0.92},
        "lines": {
            1: {
                "charge": {
                    "x": ions_x,
                    "y": y,
                    "style": {
                        "color": "#1f77b4", "linewidth": 1.0, "linestyle": "-", "label": "1",
                        "visible": True, "alpha": None, "marker": None, "markersize": None,
                        "markerfacecolor": None, "markeredgecolor": None,
                    },
                },
                "discharge": {
                    "x": ions_x[::-1],
                    "y": y,
                    "style": {
                        "color": "#1f77b4", "linewidth": 1.0, "linestyle": "-", "label": "_nolegend_",
                        "visible": True, "alpha": None, "marker": None, "markersize": None,
                        "markerfacecolor": None, "markeredgecolor": None,
                    },
                },
            }
        },
        "visible_cycles": [1],
        "multi_file": False,
        "file_data": None,
        "font": {},
        "legend": {"visible": False, "position_inches": None, "title": "Cycle"},
        "wasd_state": {
            "top": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
            "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
            "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
            "right": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
        },
        "tick_state": {},
        "tick_widths": {},
        "tick_lengths": {},
        "tick_direction": "out",
        "spines": {},
        "titles": {"xlabel": "ions", "ylabel": "V", "xlabel_visible": True, "ylabel_visible": True},
        "title_offsets": {},
        "display_mode": "both",
        "xaxis_dual": {"mode": "ions", "c_theoretical": 150.0, "swapped": False},
        "source_paths": [],
        "grid": False,
        "ro_active": False,
    }
    path = tmp_path / "old_ions.pkl"
    with path.open("wb") as fh:
        pickle.dump(sess, fh, protocol=4)
    result = load_ec_session(str(path))
    assert result is not None
    fig2, ax2, _ = result[:3]
    xs = np.asarray(ax2.lines[0].get_xdata(), float)
    assert float(np.nanmax(xs)) > 0.2
    plt.close(fig2)


def test_xy_u_clears_top_override():
    fig, ax = plt.subplots()
    x = np.array([10.0, 20.0], dtype=float)
    y = np.array([1.0, 2.0], dtype=float)
    ax.plot(x, y)
    AU.set_xy_axis_mode(fig, "2theta", wavelength=1.54)
    ax.set_xlabel(AU.default_xlabel("2theta"))
    ax._top_xlabel_on = True
    ax._top_xlabel_text_override = "STALE 2THETA"
    position_top_xlabel(ax, fig, {})
    x_list = [x.copy()]
    AU.apply_xy_axis_unit_conversion(
        fig=fig,
        ax=ax,
        frm="2theta",
        to="Q",
        wl=1.54,
        x_data_list=x_list,
        x_full_list=[x.copy()],
        y_data_list=[y],
        cif_series=[],
        update_xlabel=True,
    )
    assert not hasattr(ax, "_top_xlabel_text_override")
    assert ax.get_xlabel()
    plt.close(fig)


def test_xy_old_bpsg_clears_live_dual_wl(tmp_path: Path):
    fig, ax = plt.subplots()
    x = np.linspace(10.0, 40.0, 20)
    y = np.ones_like(x)
    ax.plot(x, y)
    AU.set_xy_axis_mode(fig, "2theta", wavelength=0.709)
    fig._xy_dual_wl_display = True
    fig._xy_file_wavelength_info = [(0.709, 1.54)]
    path = tmp_path / "legacy.bpsg"
    path.write_text(
        json.dumps(
            {
                "kind": "xy_style_geom",
                "geometry": {
                    "xlabel": AU.default_xlabel("2theta"),
                    "ylabel": "I",
                    "xlim": [12.0, 38.0],
                    "ylim": [0.0, 2.0],
                    "axis_mode": "2theta",
                    "wavelength": 0.709,
                },
            }
        ),
        encoding="utf-8",
    )
    apply_xy_style(
        str(path),
        fig,
        ax,
        [x],
        [y],
        [y.copy()],
        [0.0],
        [],
        SimpleNamespace(wl=0.709, stack=False, files=[], ro=False, xaxis="2theta"),
        {
            "bx": True, "tx": False, "ly": True, "ry": False,
            "mbx": False, "mtx": False, "mly": False, "mry": False,
            "b_ticks": True, "t_ticks": False, "l_ticks": True, "r_ticks": False,
            "b_labels": True, "t_labels": False, "l_labels": True, "r_labels": False,
        },
        ["a"],
        update_labels,
    )
    assert bool(getattr(fig, "_xy_dual_wl_display", True)) is False
    assert list(getattr(fig, "_xy_file_wavelength_info", None) or []) == []
    plt.close(fig)


def test_apply_dual_top_partial_cfg_bc():
    fig, ax = plt.subplots()
    sec = ax.secondary_xaxis("top", functions=(lambda v: v, lambda v: v))
    apply_dual_top_axis_style(sec, {"xlabel": "ions only"}, fig=fig)
    assert sec.get_xlabel() == "ions only"
    apply_dual_top_axis_style(sec, None, fig=fig)
    plt.close(fig)

"""Hard gates for XY geometry keys across p / i / s / b.

Covers: live axes frame after ``g``/set_position, psg geometry block,
session axes_bbox authority, undo norm_*/cif_initial_ylim, style-only gate.
"""

from __future__ import annotations

import json
import pickle

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from batplot import session as S
from batplot.plot_modes.xy import style as ST
from batplot.plot_modes.xy.undo_state import xy_push_state, xy_restore_state


class _Args:
    stack = False
    xaxis = "2theta"
    wl = 1.5406
    autoscale = False
    norm = False
    files = []


def _noop(*_a, **_k):
    return None


def _push(fig, ax, hist):
    xy_push_state(
        state_history=hist,
        fig=fig,
        ax=ax,
        tick_state={
            "b_ticks": True, "b_labels": True, "bx": True,
            "l_ticks": True, "l_labels": True, "ly": True,
            "t_ticks": False, "t_labels": False, "tx": False,
            "r_ticks": False, "r_labels": False, "ry": False,
        },
        labels=["c1"],
        delta=0.0,
        x_data_list=[np.array([0.0, 1.0])],
        y_data_list=[np.array([1.0, 2.0])],
        orig_y=[np.array([1.0, 2.0])],
        offsets_list=[0.0],
        x_full_list=[np.array([0.0, 1.0])],
        raw_y_full_list=[np.array([1.0, 2.0])],
        label_text_objects=[],
        bp=None,
        cif_series_for_session=lambda: [],
        iter_lines=lambda: list(enumerate(ax.lines)),
        note="baseline",
    )


def _restore(fig, ax, hist):
    return xy_restore_state(
        state_history=hist,
        fig=fig,
        ax=ax,
        args=_Args(),
        tick_state={
            "b_ticks": True, "b_labels": True, "bx": True,
            "l_ticks": True, "l_labels": True, "ly": True,
            "t_ticks": False, "t_labels": False, "tx": False,
            "r_ticks": False, "r_labels": False, "ry": False,
        },
        labels=["c1"],
        x_data_list=[np.array([0.0, 1.0])],
        y_data_list=[np.array([1.0, 2.0])],
        orig_y=[np.array([1.0, 2.0])],
        offsets_list=[0.0],
        x_full_list=[np.array([0.0, 1.0])],
        raw_y_full_list=[np.array([1.0, 2.0])],
        label_text_objects=[],
        bp=None,
        delta=0.0,
        use_Q=False,
        use_2th=True,
        file_wavelength_info={},
        cif_globals={},
        sync_legacy_tick_keys=_noop,
        update_tick_visibility=_noop,
        sync_fonts=_noop,
        position_top_xlabel=_noop,
        position_right_ylabel=_noop,
        update_ylabel_for_derivative=lambda *a, **k: "Y",
        sync_fig_cif_tick_series=_noop,
        line=lambda i: ax.lines[i],
        nlines=lambda: len(ax.lines),
    )


def test_session_dump_subplot_margins_match_live_set_position(session_path):
    """After ``g``/set_position, dump must not store stale fig.subplotpars."""
    fig, ax = plt.subplots(figsize=(8.0, 6.0))
    ax.plot([0, 1], [1, 2])
    # Leave subplotpars at defaults, move axes with set_position (g menu path).
    ax.set_position([0.25, 0.30, 0.55, 0.50])
    live = ax.get_position().bounds
    path = session_path("xy_live_frame.pkl")
    S.dump_session(
        path,
        fig=fig,
        ax=ax,
        x_data_list=[np.array([0.0, 1.0])],
        y_data_list=[np.array([1.0, 2.0])],
        orig_y=[np.array([1.0, 2.0])],
        x_full_list=[np.array([0.0, 1.0])],
        raw_y_full_list=[np.array([1.0, 2.0])],
        offsets_list=[0.0],
        labels=["c1"],
        delta=0.0,
        args=_Args(),
        tick_state={},
        skip_confirm=True,
    )
    with open(path, "rb") as fh:
        sess = pickle.load(fh)
    spm = sess["figure"]["subplot_margins"]
    assert abs(spm["left"] - live[0]) < 1e-9
    assert abs(spm["bottom"] - live[1]) < 1e-9
    assert abs((spm["right"] - spm["left"]) - live[2]) < 1e-9
    assert abs((spm["top"] - spm["bottom"]) - live[3]) < 1e-9
    bbox = sess["figure"]["axes_bbox"]
    assert abs(bbox["left"] - live[0]) < 1e-9
    assert abs(bbox["bottom"] - live[1]) < 1e-9
    plt.close(fig)


def test_session_load_prefers_axes_bbox_over_stale_margins_and_frame(session_path):
    """Load must keep axes_bbox even if subplot_margins/frame_size disagree."""
    fig, ax = plt.subplots(figsize=(8.0, 6.0))
    ax.plot([0, 1], [1, 2])
    ax.set_position([0.22, 0.28, 0.50, 0.45])
    path = session_path("xy_bbox_authority.pkl")
    S.dump_session(
        path,
        fig=fig,
        ax=ax,
        x_data_list=[np.array([0.0, 1.0])],
        y_data_list=[np.array([1.0, 2.0])],
        orig_y=[np.array([1.0, 2.0])],
        x_full_list=[np.array([0.0, 1.0])],
        raw_y_full_list=[np.array([1.0, 2.0])],
        offsets_list=[0.0],
        labels=["c1"],
        delta=0.0,
        args=_Args(),
        tick_state={},
        skip_confirm=True,
    )
    # Corrupt secondary layout keys to mimic an old dump / race.
    with open(path, "rb") as fh:
        sess = pickle.load(fh)
    sess["figure"]["subplot_margins"] = {
        "left": 0.05, "right": 0.99, "bottom": 0.05, "top": 0.99
    }
    sess["figure"]["frame_size"] = (7.5, 5.5)
    with open(path, "wb") as fh:
        pickle.dump(sess, fh)

    res = S.load_xy_session(path)
    assert res is not None
    fig2, ax2, _mk = res
    b = ax2.get_position().bounds
    assert abs(b[0] - 0.22) < 1e-6
    assert abs(b[1] - 0.28) < 1e-6
    assert abs(b[2] - 0.50) < 1e-6
    assert abs(b[3] - 0.45) < 1e-6
    plt.close(fig)
    plt.close(fig2)


def test_psg_export_import_geometry_block(tmp_path):
    fig, ax = plt.subplots(figsize=(7.0, 5.0))
    ax.plot([0, 10], [0, 1])
    ax.set_xlim(2.0, 8.0)
    ax.set_ylim(-0.5, 1.5)
    ax.set_xlabel("Two theta")
    ax.set_ylabel("Intensity")
    ax._norm_xlim = (0.0, 10.0)
    ax._norm_ylim = (0.0, 1.0)
    ax._cif_initial_ylim = (-0.2, 1.2)
    ax.set_position([0.18, 0.20, 0.70, 0.65])
    fig._xy_axis_mode = "2theta"
    fig._xy_wavelength = 1.5406
    fig._xy_dual_wl_display = True
    style_path = tmp_path / "geom.bpsg"
    ST.export_style_config(
        str(style_path),
        fig,
        ax,
        [np.array([0, 1])],
        ["c1"],
        0.0,
        _Args(),
        {},
        [0.0],
        overwrite_path=str(style_path),
        force_kind="psg",
    )
    payload = json.loads(style_path.read_text(encoding="utf-8"))
    assert payload["kind"] == "xy_style_geom"
    geom = payload["geometry"]
    assert geom["xlim"] == [2.0, 8.0]
    assert geom["ylim"] == [-0.5, 1.5]
    assert geom["norm_xlim"] == [0.0, 10.0]
    assert geom["norm_ylim"] == [0.0, 1.0]
    assert geom["cif_initial_ylim"] == [-0.2, 1.2]
    assert geom["axis_mode"] == "2theta"
    assert abs(payload["figure"]["axes_fraction"][0] - 0.18) < 1e-9
    assert abs(payload["margins"]["left"] - 0.18) < 1e-9

    fig2, ax2 = plt.subplots(figsize=(10.0, 8.0))
    ax2.plot([0, 10], [0, 1])
    ax2.set_xlim(0, 10)
    ax2.set_ylim(0, 1)
    fig2._xy_axis_mode = "2theta"
    ST.apply_style_config(
        str(style_path),
        fig2,
        ax2,
        [np.array([0, 10])],
        [np.array([0, 1])],
        [np.array([0, 1])],
        [0.0],
        [],
        _Args(),
        {},
        ["c1"],
        update_labels_func=_noop,
    )
    assert ax2.get_xlim() == (2.0, 8.0)
    assert ax2.get_ylim() == (-0.5, 1.5)
    assert tuple(ax2._norm_xlim) == (0.0, 10.0)
    assert tuple(ax2._norm_ylim) == (0.0, 1.0)
    assert tuple(ax2._cif_initial_ylim) == (-0.2, 1.2)
    b = ax2.get_position().bounds
    assert abs(b[0] - 0.18) < 1e-6
    assert abs(b[2] - 0.70) < 1e-6
    plt.close(fig)
    plt.close(fig2)


def test_ps_does_not_apply_canvas_or_geometry_limits(tmp_path):
    fig, ax = plt.subplots(figsize=(6.0, 4.0))
    ax.plot([0, 1], [1, 2])
    ax.set_xlim(0, 1)
    ax.set_position([0.15, 0.15, 0.70, 0.70])
    style_path = tmp_path / "style.bps"
    ST.export_style_config(
        str(style_path),
        fig,
        ax,
        [np.array([1, 2])],
        ["c1"],
        0.0,
        _Args(),
        {},
        [0.0],
        overwrite_path=str(style_path),
        force_kind="ps",
    )
    payload = json.loads(style_path.read_text(encoding="utf-8"))
    assert payload["kind"] == "xy_style"
    assert "geometry" not in payload

    fig2, ax2 = plt.subplots(figsize=(9.0, 7.0))
    ax2.plot([0, 1], [1, 2])
    ax2.set_xlim(3, 4)
    ax2.set_position([0.05, 0.05, 0.90, 0.90])
    before = ax2.get_position().bounds
    ST.apply_style_config(
        str(style_path),
        fig2,
        ax2,
        [np.array([0, 1])],
        [np.array([1, 2])],
        [np.array([1, 2])],
        [0.0],
        [],
        _Args(),
        {},
        ["c1"],
        update_labels_func=_noop,
    )
    assert tuple(fig2.get_size_inches()) == (9.0, 7.0)
    assert ax2.get_xlim() == (3.0, 4.0)
    after = ax2.get_position().bounds
    assert all(abs(a - b) < 1e-6 for a, b in zip(before, after))
    plt.close(fig)
    plt.close(fig2)


def test_undo_restores_norm_limits_cif_ylim_and_set_position_frame():
    fig, ax = plt.subplots(figsize=(8.0, 6.0))
    ax.plot([0, 1], [1, 2])
    ax.set_xlim(1, 2)
    ax.set_ylim(3, 4)
    ax._norm_xlim = (0.0, 5.0)
    ax._norm_ylim = (0.0, 6.0)
    ax._cif_initial_ylim = (2.5, 4.5)
    ax.set_position([0.30, 0.25, 0.40, 0.55])
    hist: list = []
    _push(fig, ax, hist)

    ax.set_xlim(9, 10)
    ax.set_ylim(11, 12)
    ax._norm_xlim = (99.0, 100.0)
    ax._norm_ylim = (99.0, 100.0)
    ax._cif_initial_ylim = (0.0, 1.0)
    ax.set_position([0.05, 0.05, 0.90, 0.90])
    fig.set_size_inches(3.0, 3.0)

    _restore(fig, ax, hist)
    assert ax.get_xlim() == (1.0, 2.0)
    assert ax.get_ylim() == (3.0, 4.0)
    assert tuple(ax._norm_xlim) == (0.0, 5.0)
    assert tuple(ax._norm_ylim) == (0.0, 6.0)
    assert tuple(ax._cif_initial_ylim) == (2.5, 4.5)
    b = ax.get_position().bounds
    assert abs(b[0] - 0.30) < 1e-6
    assert abs(b[1] - 0.25) < 1e-6
    assert abs(b[2] - 0.40) < 1e-6
    assert abs(b[3] - 0.55) < 1e-6
    assert tuple(fig.get_size_inches()) == (8.0, 6.0)
    plt.close(fig)


def test_session_roundtrip_norm_and_cif_initial_ylim(session_path):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [1, 2])
    ax.set_xlim(1, 9)
    ax.set_ylim(2, 8)
    ax._norm_xlim = (0.0, 10.0)
    ax._norm_ylim = (0.0, 10.0)
    ax._cif_initial_ylim = (1.5, 8.5)
    path = session_path("xy_norm_cif.pkl")
    S.dump_session(
        path,
        fig=fig,
        ax=ax,
        x_data_list=[np.array([0.0, 1.0])],
        y_data_list=[np.array([1.0, 2.0])],
        orig_y=[np.array([1.0, 2.0])],
        x_full_list=[np.array([0.0, 1.0])],
        raw_y_full_list=[np.array([1.0, 2.0])],
        offsets_list=[0.0],
        labels=["c1"],
        delta=0.0,
        args=_Args(),
        tick_state={},
        skip_confirm=True,
    )
    res = S.load_xy_session(path)
    assert res is not None
    fig2, ax2, _mk = res
    assert ax2.get_xlim() == (1.0, 9.0)
    assert ax2.get_ylim() == (2.0, 8.0)
    assert tuple(ax2._norm_xlim) == (0.0, 10.0)
    assert tuple(ax2._norm_ylim) == (0.0, 10.0)
    assert tuple(ax2._cif_initial_ylim) == (1.5, 8.5)
    plt.close(fig)
    plt.close(fig2)

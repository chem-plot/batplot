"""Regressions for full-menu audit gaps (CPC d/v/ry, XY dual-Y, EC 2d undo)."""

from __future__ import annotations

import copy

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from batplot.plot_modes.cpc.panel_menus import apply_cpc_file_artist_visibility
from batplot.plot_modes.xy.spines import (
    capture_xy_wasd_state,
    set_xy_spine_visible,
    sync_xy_twin_wasd,
)


def test_cpc_display_mode_does_not_resurrect_hidden_file():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc_c = ax.scatter([1], [1])
    sc_d = ax.scatter([2], [2])
    sc_e = ax2.scatter([3], [3])
    file_data = [
        {
            "visible": False,
            "sc_charge": sc_c,
            "sc_discharge": sc_d,
            "sc_eff": sc_e,
            "filename": "hidden.csv",
        }
    ]
    fig._cpc_display_mode = "both"
    fig._cpc_wasd_state = {
        "right": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True}
    }
    apply_cpc_file_artist_visibility(fig, file_data)
    assert sc_c.get_visible() is False
    assert sc_d.get_visible() is False
    assert sc_e.get_visible() is False
    fig._cpc_display_mode = "charge"
    apply_cpc_file_artist_visibility(fig, file_data)
    assert sc_c.get_visible() is False
    assert sc_d.get_visible() is False
    plt.close(fig)


def test_cpc_v_respects_display_mode_and_ry_off():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc_c = ax.scatter([1], [1])
    sc_d = ax.scatter([2], [2])
    sc_e = ax2.scatter([3], [3])
    file_data = [
        {
            "visible": True,
            "sc_charge": sc_c,
            "sc_discharge": sc_d,
            "sc_eff": sc_e,
        }
    ]
    fig._cpc_display_mode = "charge"
    fig._cpc_wasd_state = {
        "right": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False}
    }
    apply_cpc_file_artist_visibility(fig, file_data, eff_on=False)
    assert sc_c.get_visible() is True
    assert sc_d.get_visible() is False
    assert sc_e.get_visible() is False
    plt.close(fig)


def test_cpc_style_eff_off_keeps_ax2_visible():
    """ry / style must not hide the twin axes object (right spine frame)."""
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    ax2.set_visible(True)
    sc_eff = ax2.scatter([1], [50])
    # Mimic fixed style path: tick/label only
    sc_eff.set_visible(False)
    ax2.yaxis.label.set_visible(False)
    ax2.tick_params(axis="y", right=False, labelright=False)
    assert ax2.get_visible() is True
    assert ax2.spines["right"].get_visible() is True
    plt.close(fig)


def test_xy_dual_y_wasd_syncs_twin_right_spine():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    fig._xy_ax2 = ax2
    fig._xy_use_top_x = False
    ax.plot([0, 1], [0, 1])
    ax2.plot([0, 1], [2, 1])
    set_xy_spine_visible(fig, ax, "right", False)
    assert ax.spines["right"].get_visible() is False
    assert ax2.spines["right"].get_visible() is False
    wasd = capture_xy_wasd_state(ax, fig, None)
    assert wasd["right"]["spine"] is False
    # Re-show via wasd apply
    wasd["right"]["spine"] = True
    sync_xy_twin_wasd(ax, fig, wasd)
    assert ax2.spines["right"].get_visible() is True
    plt.close(fig)


def test_ec_undo_push_captures_dqdv_2d_snapshot():
    from batplot.plot_modes.electrochem.undo_state import ec_push_state

    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    tick_state = {
        "bx": True,
        "tx": False,
        "ly": True,
        "ry": False,
        "b_ticks": True,
        "t_ticks": False,
        "l_ticks": True,
        "r_ticks": False,
        "b_labels": True,
        "t_labels": False,
        "l_labels": True,
        "r_labels": False,
    }
    ax._saved_tick_state = dict(tick_state)
    history = []
    fig._dqdv_2d_snapshot = {"v_lo": 1.0, "v_hi": 3.0, "nx": 10}
    ec_push_state(
        state_history=history,
        fig=fig,
        ax=ax,
        tick_state=tick_state,
        cycle_lines={},
        file_data=[{"filepath": "x.mpt"}],
        is_multi_file=False,
        note="before-2d",
    )
    assert history and history[-1].get("dqdv_2d_snapshot", {}).get("v_lo") == 1.0
    # Mutating live snapshot must not mutate the undo frame
    fig._dqdv_2d_snapshot["v_lo"] = 9.0
    assert history[-1]["dqdv_2d_snapshot"]["v_lo"] == 1.0
    plt.close(fig)

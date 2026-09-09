"""Dual GC top spine/ticks must hide BOTH primary + SecondaryAxis overlays."""

from __future__ import annotations

import pickle
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.electrochem.session import load_ec_session
from batplot.plot_modes.electrochem.style import (
    apply_ec_dual_top_wasd,
    apply_ec_wasd_chrome,
    ec_dual_secax,
    reapply_ec_dual_secondary_chrome,
    seal_ec_axis_chrome,
    seal_ec_dual_top_chrome,
)
from batplot.ui import update_tick_visibility


def _dual_fig():
    fig, ax = plt.subplots()
    ax.plot([0.0, 100.0], [3.0, 4.0])
    c_th = 162.5
    sec = ax.secondary_xaxis("top", functions=(lambda v: v / c_th, lambda v: v * c_th))
    sec.set_xlabel("Number of ions")
    ax.set_xlabel("Specific Capacity")
    fig._xaxis_mode = "dual"
    fig._xaxis_c_theoretical = c_th
    fig._xaxis_secondary = sec
    # Start with both overlays visible
    ax.spines["top"].set_visible(True)
    sec.spines["top"].set_visible(True)
    ax.tick_params(axis="x", which="major", top=True, labeltop=True)
    sec.tick_params(axis="x", which="major", top=True, labeltop=True)
    sec.xaxis.label.set_visible(True)
    fig._ec_wasd_state = {
        "top": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "right": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
    }
    return fig, ax, sec


def test_w1_hides_both_top_spines():
    fig, ax, sec = _dual_fig()
    fig._ec_wasd_state["top"]["spine"] = False
    apply_ec_dual_top_wasd(fig, ax, fig._ec_wasd_state)
    assert ax.spines["top"].get_visible() is False
    assert sec.spines["top"].get_visible() is False
    plt.close(fig)


def test_w2_w4_chrome_only_on_secax_never_primary_capacity():
    """Primary top uses capacity locator — must stay off or ghost ticks appear."""
    fig, ax, sec = _dual_fig()
    fig._ec_wasd_state["top"]["ticks"] = True
    fig._ec_wasd_state["top"]["labels"] = True
    apply_ec_dual_top_wasd(fig, ax, fig._ec_wasd_state)
    fig.canvas.draw()
    assert ax.xaxis.get_major_ticks()[0].tick2line.get_visible() is False
    assert sec.xaxis.get_major_ticks()[0].tick2line.get_visible() is True
    assert ax.xaxis.get_major_ticks()[0].label2.get_visible() is False
    assert sec.xaxis.get_major_ticks()[0].label2.get_visible() is True
    fig._ec_wasd_state["top"]["ticks"] = False
    fig._ec_wasd_state["top"]["labels"] = False
    apply_ec_dual_top_wasd(fig, ax, fig._ec_wasd_state)
    fig.canvas.draw()
    assert ax.xaxis.get_major_ticks()[0].tick2line.get_visible() is False
    assert sec.xaxis.get_major_ticks()[0].tick2line.get_visible() is False
    assert ax.xaxis.get_major_ticks()[0].label2.get_visible() is False
    assert sec.xaxis.get_major_ticks()[0].label2.get_visible() is False
    plt.close(fig)


def test_tick_state_apply_cannot_revive_primary_capacity_ghosts():
    """Root-cause gate: bookkeeping t_ticks=True must not light primary top.

    Undo / menu entry call update_tick_visibility(ax, tick_state) after WASD.
    That used to re-enable capacity-scale top ticks beside ions ticks.
    """
    fig, ax, sec = _dual_fig()
    fig._ec_wasd_state["top"]["ticks"] = True
    fig._ec_wasd_state["top"]["labels"] = True
    apply_ec_dual_top_wasd(fig, ax, fig._ec_wasd_state)
    # Simulate the buggy path: apply flat tick_state to PRIMARY
    tick_state = {
        "b_ticks": True, "b_labels": True,
        "t_ticks": True, "t_labels": True,
        "l_ticks": True, "l_labels": True,
        "r_ticks": False, "r_labels": False,
        "mbx": False, "mtx": False, "mly": False, "mry": False,
        "bx": True, "tx": True, "ly": True, "ry": False,
    }
    update_tick_visibility(ax, tick_state)
    fig.canvas.draw()
    # Without seal: primary ghosts are on (documents the bug class)
    assert ax.xaxis.get_major_ticks()[0].tick2line.get_visible() is True
    # Seal restores dual layer rules
    seal_ec_axis_chrome(fig, ax, fig._ec_wasd_state)
    fig.canvas.draw()
    assert ax.xaxis.get_major_ticks()[0].tick2line.get_visible() is False
    assert ax.xaxis.get_major_ticks()[0].label2.get_visible() is False
    assert sec.xaxis.get_major_ticks()[0].tick2line.get_visible() is True
    assert sec.xaxis.get_major_ticks()[0].label2.get_visible() is True
    plt.close(fig)


def test_apply_ec_wasd_chrome_all_sides_dual():
    """w/a/s/d all routed correctly: a/s/d on primary, w ticks on SecondaryAxis."""
    fig, ax, sec = _dual_fig()
    wasd = fig._ec_wasd_state
    wasd["top"]["ticks"] = True
    wasd["top"]["labels"] = True
    wasd["top"]["spine"] = True
    wasd["bottom"]["ticks"] = False
    wasd["bottom"]["labels"] = False
    wasd["left"]["ticks"] = False
    wasd["left"]["labels"] = True
    wasd["right"]["ticks"] = True
    wasd["right"]["labels"] = True
    wasd["right"]["spine"] = True
    apply_ec_wasd_chrome(fig, ax, wasd, apply_titles=True)
    fig.canvas.draw()
    # Top: secax only
    assert ax.xaxis.get_major_ticks()[0].tick2line.get_visible() is False
    assert sec.xaxis.get_major_ticks()[0].tick2line.get_visible() is True
    assert sec.xaxis.get_major_ticks()[0].label2.get_visible() is True
    # Bottom / left / right on primary
    assert ax.xaxis.get_major_ticks()[0].tick1line.get_visible() is False
    assert ax.xaxis.get_major_ticks()[0].label1.get_visible() is False
    assert ax.yaxis.get_major_ticks()[0].tick1line.get_visible() is False
    assert ax.yaxis.get_major_ticks()[0].label1.get_visible() is True
    assert ax.yaxis.get_major_ticks()[0].tick2line.get_visible() is True
    assert ax.yaxis.get_major_ticks()[0].label2.get_visible() is True
    # SecondaryAxis must not grow a second frame on a/s/d
    assert sec.spines["bottom"].get_visible() is False
    assert sec.spines["left"].get_visible() is False
    assert sec.spines["right"].get_visible() is False
    plt.close(fig)


def test_seal_alias_matches_axis_seal():
    fig, ax, sec = _dual_fig()
    fig._ec_wasd_state["top"]["ticks"] = True
    seal_ec_dual_top_chrome(fig, ax, fig._ec_wasd_state)
    fig.canvas.draw()
    assert ax.xaxis.get_major_ticks()[0].tick2line.get_visible() is False
    assert sec.xaxis.get_major_ticks()[0].tick2line.get_visible() is True
    plt.close(fig)


def test_w3_installs_secax_minor_locator_not_primary():
    """w3 must show ions minor ticks — NullLocator on SecondaryAxis was the bug."""
    from matplotlib.ticker import AutoMinorLocator, NullLocator

    from batplot.plot_modes.electrochem.style import apply_ec_wasd_chrome

    fig, ax, sec = _dual_fig()
    # Only top minors (classic w3 after dual enable)
    fig._ec_wasd_state["top"]["minor"] = True
    fig._ec_wasd_state["top"]["ticks"] = True
    fig._ec_wasd_state["bottom"]["minor"] = False
    apply_ec_wasd_chrome(fig, ax, fig._ec_wasd_state, apply_titles=True)
    fig.canvas.draw()
    assert isinstance(sec.xaxis.get_minor_locator(), AutoMinorLocator)
    # Primary must not own top.minor when only w3 (ions) is on
    assert isinstance(ax.xaxis.get_minor_locator(), NullLocator)
    assert sec.xaxis.get_minor_ticks()
    assert sec.xaxis.get_minor_ticks()[0].tick2line.get_visible() is True
    # a3 / s3 still work on primary
    fig._ec_wasd_state["bottom"]["minor"] = True
    fig._ec_wasd_state["left"]["minor"] = True
    apply_ec_wasd_chrome(fig, ax, fig._ec_wasd_state, apply_titles=True)
    fig.canvas.draw()
    assert isinstance(ax.xaxis.get_minor_locator(), AutoMinorLocator)
    assert isinstance(ax.yaxis.get_minor_locator(), AutoMinorLocator)
    assert ax.xaxis.get_minor_ticks()[0].tick1line.get_visible() is True
    assert ax.yaxis.get_minor_ticks()[0].tick1line.get_visible() is True
    # Dual top minors still on secax, not primary top
    assert sec.xaxis.get_minor_ticks()[0].tick2line.get_visible() is True
    assert ax.xaxis.get_minor_ticks()[0].tick2line.get_visible() is False
    plt.close(fig)


def test_w5_hides_ions_title_only():
    fig, ax, sec = _dual_fig()
    fig._ec_wasd_state["top"]["title"] = False
    apply_ec_dual_top_wasd(fig, ax, fig._ec_wasd_state)
    assert sec.xaxis.label.get_visible() is False
    assert ax._top_xlabel_on is False
    plt.close(fig)


def test_reapply_wasd_wins_over_top_axis_visibility():
    fig, ax, sec = _dual_fig()
    fig._ec_wasd_state["top"]["spine"] = False
    fig._ec_wasd_state["top"]["title"] = False
    reapply_ec_dual_secondary_chrome(
        fig,
        ax,
        wasd_state=fig._ec_wasd_state,
        top_axis_cfg={
            "xlabel": "Number of ions",
            "xlabel_visible": True,
            "spine_visible": True,
            "spine_color": "#000000",
            "label_color": "#000000",
        },
    )
    assert ax.spines["top"].get_visible() is False
    assert sec.spines["top"].get_visible() is False
    assert sec.xaxis.label.get_visible() is False
    assert sec.get_xlabel() == "Number of ions"
    plt.close(fig)


def test_load_heals_wasd_title_false_when_top_axis_says_visible(tmp_path: Path):
    ions_x = np.linspace(0.0, 100.0, 8)
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
        "axis": {
            "xlabel": "Specific Capacity (mAh g$^{-1}$)",
            "ylabel": "Potential",
            "xlim": (0.0, 100.0),
            "ylim": (3.0, 4.0),
            "xlabel_visible": True,
            "ylabel_visible": True,
        },
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
                    "orig_xdata_gc": ions_x,
                },
                "discharge": None,
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
        "titles": {
            "xlabel": "Specific Capacity (mAh g$^{-1}$)",
            "ylabel": "Potential",
            "xlabel_visible": True,
            "ylabel_visible": True,
            "top_x": False,
            "right_y": False,
        },
        "title_offsets": {},
        "display_mode": "both",
        "capacity_mode": "per_cycle",
        "xaxis_dual": {
            "mode": "dual",
            "c_theoretical": 162.5,
            "swapped": False,
            "top_axis": {
                "xlabel": "Number of ions (C / 162.5 mAh g$^{-1}$)",
                "xlabel_visible": True,
                "label_color": "#000000",
                "spine_visible": True,
                "spine_color": "#000000",
            },
        },
        "source_paths": [],
        "grid": False,
        "ro_active": False,
    }
    path = tmp_path / "heal_dual.pkl"
    with path.open("wb") as fh:
        pickle.dump(sess, fh, protocol=4)
    result = load_ec_session(str(path))
    assert result is not None
    fig, ax, _ = result[:3]
    sec = ec_dual_secax(fig)
    assert sec is not None
    # Healed: ions title back on
    assert bool(sec.xaxis.label.get_visible()) is True
    assert bool((getattr(fig, "_ec_wasd_state", {}) or {}).get("top", {}).get("title")) is True
    plt.close(fig)

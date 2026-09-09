"""Batch XY key isolation: each sync key must not hitchhike peers."""

from __future__ import annotations

import inspect

import matplotlib.pyplot as plt
import pytest
from matplotlib.colors import to_hex

from batplot.plot_modes.batch_session.load import XyPanel
from batplot.plot_modes.batch_session.menu_xy import (
    _line_getter,
    _print_batch_xy_current_curves,
)
from batplot.plot_modes.batch_session.xy_batch_helpers import (
    _apply_xy_batch_wasd_chrome,
    merge_xy_line_chrome_cfg,
    sync_ref_wasd_to_panels,
    tick_state_for,
)
import batplot.plot_modes.batch_session.menu_xy as menu_xy
import batplot.plot_modes.batch_session.xy_batch_helpers as xy_helpers


def _strip_ansi(text: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _two_xy_panels(*, dual_y: bool = False, txaxis: bool = False):
    panels = []
    for i, (col, lw) in enumerate((("#111111", 1.0), ("#00aa00", 3.0))):
        fig, ax = plt.subplots()
        (ln,) = ax.plot([0, 1, 2], [0, 1 + i, 2], color=col, lw=lw)
        ax.set_xlabel(f"X-{i}")
        ax._stored_xlabel = f"X-{i}"
        ax.set_ylabel(f"Y-{i}")
        ax._stored_ylabel = f"Y-{i}"
        ax.set_xlim(0, 10 + 10 * i)
        ax.set_ylim(0, 5 + i)
        ax.spines["bottom"].set_color("#0000ff" if i == 0 else "#ff00ff")
        ax.spines["bottom"].set_linewidth(lw)
        lines_by_curve = [ln]
        if dual_y:
            ax2 = ax.twinx()
            if txaxis:
                ax2 = ax2.twiny()
                fig._xy_use_top_x = True
            (ln2,) = ax2.plot([0, 1, 2], [10, 20, 30], color="#990000", lw=lw)
            fig._xy_ax2 = ax2
            lines_by_curve.append(ln2)
            ax2.set_xlim(ax.get_xlim())
        fig._xy_lines_by_curve = lines_by_curve
        fig._bp_wasd_state = {
            "top": {"spine": False, "ticks": False, "labels": False, "title": False, "minor": False},
            "bottom": {"spine": True, "ticks": True, "labels": True, "title": True, "minor": False},
            "left": {"spine": True, "ticks": True, "labels": True, "title": True, "minor": False},
            "right": {
                "spine": bool(dual_y),
                "ticks": bool(dual_y),
                "labels": bool(dual_y),
                "title": bool(dual_y),
                "minor": False,
            },
        }
        panels.append(
            XyPanel(
                path=f"xy_{i}.pkl",
                fig=fig,
                ax=ax,
                menu_kwargs={
                    "labels": ["left", "right"] if dual_y else ["a"],
                    "y_data_list": [[0, 1, 2]],
                    "args": type("A", (), {"stack": False})(),
                },
            )
        )
    return panels


def test_batch_xy_l_merge_keeps_peer_color_not_limits():
    peer = {
        "kind": "xy_style_geom",
        "grid": False,
        "geometry": {"xlim": [0, 20]},
        "spines": {"bottom": {"linewidth": 3.0, "color": "#ff00ff", "visible": True}},
        "ticks": {"x_major_width": 1.0, "spacing": {"x": 1}},
        "lines": [
            {"index": 0, "color": "#00aa00", "linewidth": 3.0, "linestyle": "-", "marker": "None"},
        ],
    }
    ref = {
        "kind": "xy_style_geom",
        "grid": True,
        "geometry": {"xlim": [9, 10]},
        "spines": {"bottom": {"linewidth": 1.0, "color": "#ff0000", "visible": True}},
        "ticks": {"x_major_width": 2.0, "spacing": {"x": 99}},
        "lines": [
            {"index": 0, "color": "#ff0000", "linewidth": 1.0, "linestyle": "--", "marker": "o"},
        ],
    }
    out = merge_xy_line_chrome_cfg(peer, ref)
    assert "geometry" not in out
    assert out["lines"][0]["color"] == "#00aa00"
    assert out["lines"][0]["linewidth"] == 1.0
    assert out["spines"]["bottom"]["color"] == "#ff00ff"
    assert out["spines"]["bottom"]["linewidth"] == 1.0
    assert out["ticks"]["spacing"]["x"] == 1


def test_batch_xy_t_applies_spine_visibility_and_keeps_peer_color():
    p1, p2 = _two_xy_panels()
    try:
        p1.fig._bp_wasd_state["bottom"]["spine"] = False
        p1.fig._bp_wasd_state["top"]["spine"] = True
        peer_spine_color = to_hex(p2.ax.spines["bottom"].get_edgecolor())
        sync_ref_wasd_to_panels(p1, [p1, p2])
        assert p2.ax.spines["bottom"].get_visible() is False
        assert p2.ax.spines["top"].get_visible() is True
        assert to_hex(p2.ax.spines["bottom"].get_edgecolor()) == peer_spine_color
        assert to_hex(p2.ax.lines[0].get_color()) == "#00aa00"
        assert p2.ax.get_xlim() == pytest.approx((0, 20))
        assert p2.ax.spines["bottom"].get_linewidth() == pytest.approx(3.0)
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_xy_t_syncs_twin_wasd():
    p1, p2 = _two_xy_panels(dual_y=True)
    try:
        p1.fig._bp_wasd_state["right"]["spine"] = False
        p1.fig._bp_wasd_state["right"]["ticks"] = False
        sync_ref_wasd_to_panels(p1, [p1, p2])
        ax2 = p2.fig._xy_ax2
        assert ax2.spines["right"].get_visible() is False
        assert to_hex(p2.fig._xy_lines_by_curve[0].get_color()) == "#00aa00"
        assert p2.ax.get_xlim() == pytest.approx((0, 20))
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_xy_x_y_wiring_twin_helpers():
    src = inspect.getsource(menu_xy._run_ref_range_menu)
    assert "_sync_xy_twin_xlim" in src
    assert "_autoscale_xy_right_y" in src


def test_batch_xy_txaxis_twin_xlim_helper():
    from batplot.plot_modes.xy.axis_range import _sync_xy_twin_xlim

    p1, _p2 = _two_xy_panels(dual_y=True, txaxis=True)
    try:
        p1.ax.set_xlim(1.0, 5.0)
        _sync_xy_twin_xlim(p1.fig, p1.ax)
        assert p1.fig._xy_ax2.get_xlim() == pytest.approx((1.0, 5.0))
    finally:
        plt.close(p1.fig)
        plt.close(_p2.fig)


def test_batch_xy_color_listing_uses_dual_y_lines(capsys):
    p1, _p2 = _two_xy_panels(dual_y=True)
    try:
        assert _line_getter(p1)(1) is p1.fig._xy_lines_by_curve[1]
        _print_batch_xy_current_curves(p1)
        out = _strip_ansi(capsys.readouterr().out)
        assert "left" in out
        assert "right" in out
        # Twin curve color must appear (not blank from primary-only index).
        assert "990000" in out.replace("#", "") or "#990000" in out
    finally:
        plt.close(p1.fig)
        plt.close(_p2.fig)


def test_batch_xy_wasd_apply_hides_bottom_title():
    p1, _p2 = _two_xy_panels()
    try:
        wasd = p1.fig._bp_wasd_state
        wasd["bottom"]["title"] = False
        ts = tick_state_for(p1)
        _apply_xy_batch_wasd_chrome(p1.fig, p1.ax, wasd, ts)
        assert p1.ax.xaxis.label.get_visible() is False
        assert getattr(p1.ax, "_stored_xlabel", None) == "X-0"
    finally:
        plt.close(p1.fig)
        plt.close(_p2.fig)


def test_batch_xy_t_menu_wires_twin_axes_and_wasd_body():
    src = inspect.getsource(xy_helpers.run_xy_batch_spine_menu)
    assert "_xy_ax2" in src
    assert "twin_axes" in src
    assert "_apply_xy_batch_wasd_chrome" in src
    sync_src = inspect.getsource(xy_helpers.sync_ref_wasd_to_panels)
    assert "_apply_xy_batch_wasd_chrome" in sync_src

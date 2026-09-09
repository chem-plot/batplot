"""Operando/EC spine colors must not hitchhike; EC right ticks must recolor."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_hex

from batplot.plot_modes.histo.spines import set_histo_spine_color
from batplot.plot_modes.operando.spine_colors import (
    _ensure_ec_tick_state,
    apply_operando_spine_color,
)
from batplot.plot_modes.xy.spines import apply_xy_spine_color, ensure_xy_tick_state
from batplot.ui import (
    _collect_visible_tick_line_colors,
    finalize_spine_colors,
    finalize_spine_colors_for_axes,
    set_spine_side_color,
)


def _make_operando_ec_fig():
    fig = plt.figure()
    ax = fig.add_subplot(121)
    ec = fig.add_subplot(122)
    ax.imshow([[0.0, 1.0], [1.0, 0.0]])
    ec.plot([1.0, 2.0, 3.0], [3.0, 2.0, 1.0])
    ec.yaxis.tick_right()
    ec.yaxis.set_label_position("right")
    return fig, ax, ec


def test_ec_d_red_does_not_recolor_contour_right_spine():
    """k→e→d:red must not hitchhike onto contour right (even without pre-register)."""
    fig, ax, ec = _make_operando_ec_fig()
    # Classic bug path: color EC first; contour never registered in hook list.
    ts = {
        "b_ticks": True,
        "b_labels": True,
        "t_ticks": False,
        "t_labels": False,
        "l_ticks": False,
        "l_labels": False,
        "r_ticks": True,
        "r_labels": True,
        "bx": True,
        "tx": False,
        "ly": False,
        "ry": True,
    }
    ec._saved_tick_state = dict(ts)
    before = to_hex(ax.spines["right"].get_edgecolor())
    set_spine_side_color(ec, "right", "red", fig=fig, tick_state=ts)
    finalize_spine_colors(fig, ax)  # must be a no-op on empty contour store
    assert to_hex(ax.spines["right"].get_edgecolor()) == before
    assert to_hex(ec.spines["right"].get_edgecolor()) == "#ff0000"
    plt.close(fig)


def test_ec_d_red_colors_right_tick_lines_and_labels():
    fig, ax, ec = _make_operando_ec_fig()
    # Wrong left-on bookkeeping — reconcile must flip to right for tick_right().
    ec._saved_tick_state = {
        "b_ticks": True,
        "b_labels": True,
        "t_ticks": False,
        "t_labels": False,
        "l_ticks": True,
        "l_labels": True,
        "r_ticks": False,
        "r_labels": False,
        "bx": True,
        "tx": False,
        "ly": True,
        "ry": False,
    }
    ts = _ensure_ec_tick_state(ec)
    assert ts.get("r_ticks") is True
    assert ts.get("l_ticks") is False
    apply_operando_spine_color(
        fig, ec, "right", "red", tick_state=ts, peer_ax=ax
    )
    finalize_spine_colors_for_axes(
        fig, [(ax, None), (ec, ts)], draw=True
    )
    ticks = _collect_visible_tick_line_colors(ec, "right")
    assert ticks, "EC right ticks should be visible"
    assert all(c == "#ff0000" for c in ticks)
    # Labels
    for t in ec.yaxis.get_major_ticks():
        assert to_hex(t.label2.get_color()) == "#ff0000"
    assert to_hex(ax.spines["right"].get_edgecolor()) != "#ff0000"
    plt.close(fig)


def test_xy_left_spine_color_updates_ticks():
    fig, ax = plt.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0])
    ts = ensure_xy_tick_state(ax, {})
    apply_xy_spine_color(fig, ax, ts, "left", "#00aa00")
    finalize_spine_colors(fig, ax, tick_state=ts, draw=True)
    ticks = _collect_visible_tick_line_colors(ax, "left")
    assert ticks and all(c == "#00aa00" for c in ticks)
    plt.close(fig)


def test_histo_bottom_spine_color_updates_ticks():
    fig, ax = plt.subplots()
    ax.hist([1.0, 2.0, 2.0, 3.0])
    set_histo_spine_color(fig, ax, "bottom", "#0000cc")
    finalize_spine_colors(
        fig, ax, tick_state=getattr(ax, "_saved_tick_state", None), draw=True
    )
    ticks = _collect_visible_tick_line_colors(ax, "bottom")
    assert ticks and all(c == "#0000cc" for c in ticks)
    plt.close(fig)


def test_solo_ec_left_spine_color_updates_ticks():
    fig, ax = plt.subplots()
    ax.plot([0.0, 1.0], [3.0, 4.0])
    ts = {
        "b_ticks": True,
        "b_labels": True,
        "t_ticks": False,
        "t_labels": False,
        "l_ticks": True,
        "l_labels": True,
        "r_ticks": False,
        "r_labels": False,
        "bx": True,
        "tx": False,
        "ly": True,
        "ry": False,
    }
    ax._saved_tick_state = dict(ts)
    set_spine_side_color(ax, "left", "#cc6600", fig=fig, tick_state=ts)
    finalize_spine_colors(fig, ax, tick_state=ts, draw=True)
    ticks = _collect_visible_tick_line_colors(ax, "left")
    assert ticks and all(c == "#cc6600" for c in ticks)
    plt.close(fig)

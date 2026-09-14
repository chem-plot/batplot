"""Tick visibility + tick/spine color contract across modes.

Locks the once-and-for-all contract:
  color → matching ticks/labels; opposite side untouched
  hide→show ticks → finalize restores color
  tick_params wipe → finalize / draw-hook restores
  hitchhiked right-ylabel heal (operando EC / CPC)
  operando both-pane finalize after t-like WASD
"""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest
from matplotlib.colors import to_hex

from batplot.plot_modes.common.spines import (
    apply_flat_tick_params,
    sync_tick_state_from_wasd,
    wasd_to_tick_state,
)
from batplot.plot_modes.operando.spine_colors import (
    apply_operando_spine_color,
    operando_pane_tick_entries,
)
from batplot.ui import (
    _cpc_scoped_tick_state,
    _collect_visible_tick_line_colors,
    _hex_color,
    ensure_spine_color_draw_hook,
    finalize_spine_colors,
    finalize_spine_colors_cpc,
    finalize_spine_colors_for_axes,
    heal_axis_label_colors_dict,
    heal_live_axis_title_colors_from_spines,
    heal_restored_axis_title_color,
    set_spine_side_color,
)


def _rgb(c):
    from matplotlib.colors import to_rgb

    return tuple(round(v, 5) for v in to_rgb(c))


def _default_ts(**overrides):
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
        "mbx": False,
        "mtx": False,
        "mly": False,
        "mry": False,
    }
    ts.update(overrides)
    return ts


def _assert_side_colored(ax, side: str, color: str) -> None:
    want = _hex_color(color)
    assert _hex_color(ax.spines[side].get_edgecolor()) == want
    lines = _collect_visible_tick_line_colors(ax, side)
    if lines:
        assert all(c == want for c in lines), (side, lines, want)


# ---------------------------------------------------------------------------
# Shared core
# ---------------------------------------------------------------------------


def test_empty_tick_state_dict_is_authoritative():
    """``{}`` must not fall through to saved/live defaults."""
    from batplot.ui import _resolve_tick_state

    fig, ax = plt.subplots()
    ax._saved_tick_state = _default_ts(l_ticks=True, r_ticks=True)
    resolved = _resolve_tick_state(ax, {})
    assert resolved == {}
    plt.close(fig)


def test_draw_hook_reseals_tick_colors_after_tick_params_wipe():
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ts = _default_ts()
    ax._saved_tick_state = dict(ts)
    set_spine_side_color(ax, "left", "#ff0000", fig=fig, tick_state=ts)
    ensure_spine_color_draw_hook(fig, ax)
    # Wipe live artists the way matplotlib rebuilds can.
    ax.tick_params(axis="y", which="both", colors="black", labelcolor="black")
    ax.spines["left"].set_edgecolor("black")
    fig.canvas.draw()
    # Draw hook / finalize should restore.
    finalize_spine_colors(fig, ax, tick_state=ts, draw=True)
    fig.canvas.draw()
    _assert_side_colored(ax, "left", "#ff0000")
    plt.close(fig)


@pytest.mark.parametrize("side,opp", [("bottom", "top"), ("left", "right")])
def test_xy_side_color_does_not_hitchhike_opposite_title(side, opp):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    match = "#0000ff"
    other = "#d47cbe"
    set_spine_side_color(ax, side, match, fig=fig, tick_state=_default_ts())
    set_spine_side_color(ax, opp, other, fig=fig, tick_state=_default_ts())
    fig.canvas.draw()
    if side == "bottom":
        assert _rgb(ax.xaxis.label.get_color()) == _rgb(match)
    else:
        assert _rgb(ax.yaxis.label.get_color()) == _rgb(match)
    plt.close(fig)


def test_hide_then_show_ticks_keeps_left_color():
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ts = _default_ts()
    ax._saved_tick_state = dict(ts)
    set_spine_side_color(ax, "left", "#00aa00", fig=fig, tick_state=ts)
    # Hide left ticks (t → a2)
    wasd = {
        "top": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "left": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": True},
        "right": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
    }
    sync_tick_state_from_wasd(ts, wasd)
    ax._saved_tick_state = dict(ts)
    apply_flat_tick_params(ax, ts)
    finalize_spine_colors(fig, ax, tick_state=ts, draw=True)
    # Show again
    wasd["left"]["ticks"] = True
    wasd["left"]["labels"] = True
    sync_tick_state_from_wasd(ts, wasd)
    ax._saved_tick_state = dict(ts)
    apply_flat_tick_params(ax, ts)
    finalize_spine_colors(fig, ax, tick_state=ts, draw=True)
    fig.canvas.draw()
    _assert_side_colored(ax, "left", "#00aa00")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Right-ylabel heal (operando EC / CPC)
# ---------------------------------------------------------------------------


def test_heal_right_ylabel_prefers_matching_spine():
    left_c = "#ff0000"
    right_c = "#00aa00"
    hitchhiked = left_c  # old bug: left spine painted onto right ylabel
    assert _rgb(
        heal_restored_axis_title_color(
            hitchhiked, matching_spine_color=right_c, opposite_spine_color=left_c
        )
    ) == _rgb(right_c)
    healed = heal_axis_label_colors_dict(
        {"y": hitchhiked},
        {"left": {"color": left_c}, "right": {"color": right_c}},
        y_label_position="right",
    )
    assert _rgb(healed["y"]) == _rgb(right_c)


def test_heal_live_right_ylabel_from_spines():
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax.yaxis.set_label_position("right")
    ax.yaxis.tick_right()
    ax.set_ylabel("Potential")
    ts = _default_ts(l_ticks=False, l_labels=False, r_ticks=True, r_labels=True, ly=False, ry=True)
    ax._saved_tick_state = dict(ts)
    set_spine_side_color(ax, "left", "#ff0000", fig=fig, tick_state=ts)
    set_spine_side_color(ax, "right", "#00aa00", fig=fig, tick_state=ts)
    # Simulate hitchhiked live title
    ax.yaxis.label.set_color("#ff0000")
    heal_live_axis_title_colors_from_spines(ax, fig)
    assert _rgb(ax.yaxis.label.get_color()) == _rgb("#00aa00")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Operando dual-pane
# ---------------------------------------------------------------------------


def test_operando_both_pane_finalize_after_wasd_keeps_peer_colors():
    fig = plt.figure()
    ax = fig.add_subplot(121)
    ec = fig.add_subplot(122)
    ax.imshow([[0.0, 1.0], [1.0, 0.0]])
    ec.plot([1, 2, 3], [3, 2, 1])
    ec.yaxis.tick_right()
    ec.yaxis.set_label_position("right")
    op_ts = _default_ts()
    ec_ts = _default_ts(
        l_ticks=False, l_labels=False, r_ticks=True, r_labels=True, ly=False, ry=True
    )
    ax._saved_tick_state = dict(op_ts)
    ec._saved_tick_state = dict(ec_ts)
    apply_operando_spine_color(fig, ax, "left", "#0000ff", tick_state=op_ts, peer_ax=ec)
    apply_operando_spine_color(fig, ec, "right", "#ff0000", tick_state=ec_ts, peer_ax=ax)
    # Simulate t toggle on contour: rebuild tick params then finalize BOTH panes
    apply_flat_tick_params(ax, op_ts)
    ax.tick_params(axis="y", colors="black", labelcolor="black")
    entries = operando_pane_tick_entries(ax, ec)
    finalize_spine_colors_for_axes(fig, entries, draw=True)
    fig.canvas.draw()
    assert _hex_color(ax.spines["left"].get_edgecolor()) == _hex_color("#0000ff")
    assert _hex_color(ec.spines["right"].get_edgecolor()) == _hex_color("#ff0000")
    # Contour must not steal EC right color
    before_ec = _hex_color(ec.spines["right"].get_edgecolor())
    finalize_spine_colors(fig, ax, tick_state=op_ts, draw=True)
    assert _hex_color(ec.spines["right"].get_edgecolor()) == before_ec
    plt.close(fig)


# ---------------------------------------------------------------------------
# CPC twin Y
# ---------------------------------------------------------------------------


def test_cpc_scoped_tick_state_clears_opposite_y():
    shared = _default_ts(r_ticks=True, r_labels=True, ry=True)
    left = _cpc_scoped_tick_state(shared, y_owner="left")
    right = _cpc_scoped_tick_state(shared, y_owner="right")
    assert left["r_ticks"] is False and left["l_ticks"] is True
    assert right["l_ticks"] is False and right["r_ticks"] is True


def test_cpc_color_survives_right_hide_show():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    ax.plot([0, 1], [0, 1])
    ax2.plot([0, 1], [1, 0])
    ts = _default_ts(r_ticks=True, r_labels=True, ry=True)
    ax._saved_tick_state = dict(ts)
    ax2._saved_tick_state = dict(ts)
    fig._cpc_spine_colors = {}
    set_spine_side_color(
        ax, "left", "#112233", fig=fig, tick_state=_cpc_scoped_tick_state(ts, y_owner="left")
    )
    set_spine_side_color(
        ax2, "right", "#445566", fig=fig, tick_state=_cpc_scoped_tick_state(ts, y_owner="right")
    )
    fig._cpc_spine_colors = {"left": "#112233", "right": "#445566"}
    # Hide right ticks
    ts["r_ticks"] = False
    ts["r_labels"] = False
    ts["ry"] = False
    ax2.tick_params(axis="y", right=False, labelright=False)
    finalize_spine_colors_cpc(fig, ax, ax2, tick_state=ts, draw=True)
    # Show again
    ts["r_ticks"] = True
    ts["r_labels"] = True
    ts["ry"] = True
    ax2.tick_params(axis="y", right=True, labelright=True, colors="black")
    fig.canvas.draw_idle()
    finalize_spine_colors_cpc(fig, ax, ax2, tick_state=ts, draw=True)
    fig.canvas.draw()
    assert _hex_color(ax.spines["left"].get_edgecolor()) == _hex_color("#112233")
    assert _hex_color(ax2.spines["right"].get_edgecolor()) == _hex_color("#445566")
    r_lines = _collect_visible_tick_line_colors(ax2, "right")
    if r_lines:
        assert all(c == _hex_color("#445566") for c in r_lines)
    plt.close(fig)


# ---------------------------------------------------------------------------
# EC dual top (smoke via primary finalize)
# ---------------------------------------------------------------------------


def test_ec_dual_top_color_after_visibility_toggle():
    fig, ax = plt.subplots()
    ax.plot([0.0, 100.0], [3.0, 4.0])
    sec = ax.secondary_xaxis("top", functions=(lambda x: x / 100.0, lambda x: x * 100.0))
    fig._xaxis_secondary = sec
    fig._xaxis_mode = "dual"
    ts = _default_ts(t_ticks=True, t_labels=True, tx=True)
    ax._saved_tick_state = dict(ts)
    set_spine_side_color(ax, "top", "#d47cbe", fig=fig, tick_state=ts)
    finalize_spine_colors(fig, ax, tick_state=ts, draw=True)
    # Toggle top ticks off then on (simulates w2)
    ts["t_ticks"] = False
    ts["t_labels"] = False
    finalize_spine_colors(fig, ax, tick_state=ts, draw=True)
    ts["t_ticks"] = True
    ts["t_labels"] = True
    finalize_spine_colors(fig, ax, tick_state=ts, draw=True)
    fig.canvas.draw()
    assert _hex_color(ax.spines["top"].get_edgecolor()) == _hex_color("#d47cbe")
    assert _hex_color(sec.spines["top"].get_edgecolor()) == _hex_color("#d47cbe")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Histo smoke
# ---------------------------------------------------------------------------


def test_histo_spine_color_ticks_match():
    from batplot.plot_modes.histo.spines import set_histo_spine_color

    fig, ax = plt.subplots()
    ax.bar([0, 1, 2], [1, 2, 1])
    ts = _default_ts()
    ax._saved_tick_state = dict(ts)
    set_histo_spine_color(fig, ax, "bottom", "#334455")
    finalize_spine_colors(fig, ax, tick_state=ts, draw=True)
    _assert_side_colored(ax, "bottom", "#334455")
    plt.close(fig)

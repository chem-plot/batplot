"""Spine colors for all WASD sides must survive p/i/s/b across modes (+ old pkl BC)."""

from __future__ import annotations

import pickle
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import to_hex

from batplot.plot_modes.histo.spines import (
    apply_histo_spine_snapshot,
    capture_histo_spine_snapshot,
    set_histo_spine_color,
)
from batplot.plot_modes.operando.spine_colors import apply_operando_spine_color
from batplot.plot_modes.xy.spines import (
    apply_xy_spine_color,
    apply_xy_spine_specs,
    ensure_xy_tick_state,
    set_xy_spine_visible,
)
from batplot.ui import (
    _collect_visible_tick_line_colors,
    finalize_spine_colors,
    finalize_spine_colors_cpc,
    finalize_spine_colors_for_axes,
    resolve_spine_dump_color,
    set_spine_side_color,
)

SIDES = ("top", "bottom", "left", "right")
COLORS = {
    "top": "#cc0000",
    "bottom": "#0033aa",
    "left": "#00aa00",
    "right": "#aa00aa",
}


def _assert_side_colored(ax, side: str, want: str) -> None:
    assert to_hex(ax.spines[side].get_edgecolor()) == want
    # Tick lines when that side is visibly on
    lines = _collect_visible_tick_line_colors(ax, side)
    if lines:
        assert all(c == want for c in lines), (side, lines, want)


def test_resolve_spine_dump_prefers_store_over_wiped_edgecolor():
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    set_spine_side_color(ax, "left", "#ff0000", fig=fig)
    # Simulate tick_params wiping live edgecolor while store remains.
    ax.spines["left"].set_edgecolor("black")
    assert resolve_spine_dump_color(ax, "left", fig) == "#ff0000"
    plt.close(fig)


def test_xy_all_wasd_sides_style_and_session_roundtrip(tmp_path: Path):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    # Enable all sides so ticks exist for color checks.
    ax.tick_params(
        axis="both",
        which="both",
        top=True,
        bottom=True,
        left=True,
        right=True,
        labeltop=True,
        labelbottom=True,
        labelleft=True,
        labelright=True,
    )
    ts = ensure_xy_tick_state(
        ax,
        {
            "b_ticks": True,
            "t_ticks": True,
            "l_ticks": True,
            "r_ticks": True,
            "b_labels": True,
            "t_labels": True,
            "l_labels": True,
            "r_labels": True,
            "bx": True,
            "tx": True,
            "ly": True,
            "ry": True,
        },
    )
    for side, color in COLORS.items():
        apply_xy_spine_color(fig, ax, ts, side, color)
    finalize_spine_colors(fig, ax, tick_state=ts, draw=True)
    for side, color in COLORS.items():
        _assert_side_colored(ax, side, color)

    # Style dump/import (p/i)
    from batplot.ui import resolve_spine_dump_color as rsd

    style = {
        "spines": {
            side: {
                "linewidth": ax.spines[side].get_linewidth(),
                "visible": True,
                "color": rsd(ax, side, fig),
            }
            for side in SIDES
        }
    }
    # Wipe artists then re-apply via style path
    for side in SIDES:
        ax.spines[side].set_edgecolor("black")
    apply_xy_spine_specs(fig, ax, ts, style["spines"])
    finalize_spine_colors(fig, ax, tick_state=ts, draw=True)
    for side, color in COLORS.items():
        _assert_side_colored(ax, side, color)

    # Old-pkl BC: edgecolor-only spines dict (no mode store)
    old = {
        side: {"linewidth": 1.0, "visible": True, "color": color}
        for side, color in COLORS.items()
    }
    fig2, ax2 = plt.subplots()
    ax2.plot([0, 1], [0, 1])
    ax2.tick_params(
        top=True, bottom=True, left=True, right=True,
        labeltop=True, labelbottom=True, labelleft=True, labelright=True,
    )
    apply_xy_spine_specs(fig2, ax2, ts, old)
    finalize_spine_colors(fig2, ax2, tick_state=ts, draw=True)
    for side, color in COLORS.items():
        assert to_hex(ax2.spines[side].get_edgecolor()) == color
    plt.close(fig)
    plt.close(fig2)


def test_ec_all_wasd_sides_and_old_pkl_edgecolor(tmp_path: Path):
    from batplot.plot_modes.electrochem.interactive import _apply_spine_color

    fig, ax = plt.subplots()
    ax.plot([0, 1], [3, 4])
    ax.tick_params(
        top=True, bottom=True, left=True, right=True,
        labeltop=True, labelbottom=True, labelleft=True, labelright=True,
    )
    ts = {
        "b_ticks": True,
        "t_ticks": True,
        "l_ticks": True,
        "r_ticks": True,
        "b_labels": True,
        "t_labels": True,
        "l_labels": True,
        "r_labels": True,
        "bx": True,
        "tx": True,
        "ly": True,
        "ry": True,
    }
    ax._saved_tick_state = dict(ts)
    for side, color in COLORS.items():
        _apply_spine_color(ax, fig, ts, side, color)
    finalize_spine_colors(fig, ax, tick_state=ts, draw=True)
    for side, color in COLORS.items():
        _assert_side_colored(ax, side, color)

    # Session-like dump prefers store after wipe
    ax.spines["left"].set_edgecolor("black")
    assert resolve_spine_dump_color(ax, "left", fig) == COLORS["left"]

    # Old pkl: only edgecolor in spines dict
    fig2, ax2 = plt.subplots()
    ax2.plot([0, 1], [3, 4])
    ax2._saved_tick_state = dict(ts)
    for side, color in COLORS.items():
        set_spine_side_color(ax2, side, color, fig=fig2, tick_state=ts)
    finalize_spine_colors(fig2, ax2, tick_state=ts, draw=True)
    blob = {
        side: {
            "linewidth": 1.0,
            "visible": True,
            "color": to_hex(ax2.spines[side].get_edgecolor()),
        }
        for side in SIDES
    }
    # Fresh axes, restore as old session would
    fig3, ax3 = plt.subplots()
    ax3.plot([0, 1], [3, 4])
    ax3._saved_tick_state = dict(ts)
    for side, spec in blob.items():
        set_spine_side_color(ax3, side, spec["color"], fig=fig3, tick_state=ts)
    finalize_spine_colors(fig3, ax3, tick_state=ts, draw=True)
    for side, color in COLORS.items():
        assert to_hex(ax3.spines[side].get_edgecolor()) == color
    plt.close("all")


def test_operando_ec_isolation_all_sides_and_style_roundtrip():
    fig = plt.figure()
    ax = fig.add_subplot(121)
    ec = fig.add_subplot(122)
    ax.imshow([[0.0, 1.0], [1.0, 0.0]])
    ec.plot([1.0, 2.0], [1.0, 2.0])
    ec.yaxis.tick_right()
    ec._saved_tick_state = {
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
    ax.tick_params(left=True, bottom=True, labelleft=True, labelbottom=True)
    # Color contour left + EC right — must not hitchhike
    apply_operando_spine_color(
        fig, ax, "left", COLORS["left"], peer_ax=ec
    )
    apply_operando_spine_color(
        fig,
        ec,
        "right",
        COLORS["right"],
        tick_state=ec._saved_tick_state,
        peer_ax=ax,
    )
    finalize_spine_colors_for_axes(
        fig,
        [(ax, getattr(ax, "_saved_tick_state", None)), (ec, ec._saved_tick_state)],
        draw=True,
    )
    assert to_hex(ax.spines["left"].get_edgecolor()) == COLORS["left"]
    assert to_hex(ec.spines["right"].get_edgecolor()) == COLORS["right"]
    assert to_hex(ax.spines["right"].get_edgecolor()) != COLORS["right"]
    ec_ticks = _collect_visible_tick_line_colors(ec, "right")
    assert ec_ticks and all(c == COLORS["right"] for c in ec_ticks)

    # Style dump uses stores even if edgecolor wiped
    ax.spines["left"].set_edgecolor("black")
    dumped = resolve_spine_dump_color(ax, "left", fig)
    assert dumped == COLORS["left"]

    # Re-apply as style_apply would (EC only) — contour must stay unhitched
    from batplot.ui import register_spine_color_axis

    register_spine_color_axis(fig, ax)
    register_spine_color_axis(fig, ec)
    set_spine_side_color(
        ec, "right", COLORS["right"], fig=fig, tick_state=ec._saved_tick_state
    )
    finalize_spine_colors(fig, ax)  # empty contour store → no hitchhike
    assert to_hex(ax.spines["right"].get_edgecolor()) != COLORS["right"]
    plt.close(fig)


def test_cpc_session_colors_after_wasd_with_tick_state():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    ax.plot([0, 1], [0, 1])
    ax2.plot([0, 1], [1, 0])
    fig._cpc_spine_colors = {"left": COLORS["left"], "right": COLORS["right"]}
    # Mimic session: store colors first, WASD then apply with tick_state
    ts = {
        "b_ticks": True,
        "t_ticks": False,
        "l_ticks": True,
        "r_ticks": True,
        "b_labels": True,
        "t_labels": False,
        "l_labels": True,
        "r_labels": True,
        "bx": True,
        "tx": False,
        "ly": True,
        "ry": True,
    }
    ax._saved_tick_state = dict(ts)
    axes_map = {"left": [ax], "right": [ax2], "top": [ax, ax2], "bottom": [ax, ax2]}
    for spine_name, color in fig._cpc_spine_colors.items():
        for curr in axes_map[spine_name]:
            set_spine_side_color(curr, spine_name, color, fig=fig, tick_state=ts)
    finalize_spine_colors_cpc(fig, ax, ax2, tick_state=ts, draw=True)
    assert to_hex(ax.spines["left"].get_edgecolor()) == COLORS["left"]
    assert to_hex(ax2.spines["right"].get_edgecolor()) == COLORS["right"]
    left_ticks = _collect_visible_tick_line_colors(ax, "left")
    right_ticks = _collect_visible_tick_line_colors(ax2, "right")
    assert left_ticks and all(c == COLORS["left"] for c in left_ticks)
    assert right_ticks and all(c == COLORS["right"] for c in right_ticks)

    # Old pkl BC: figure.spines ax_/ax2_ colors only (no spine_colors dict)
    old_sess = {
        "figure": {
            "spines": {
                "ax_left": {"linewidth": 1.0, "color": COLORS["left"], "visible": True},
                "ax2_right": {
                    "linewidth": 1.0,
                    "color": COLORS["right"],
                    "visible": True,
                },
            }
        },
        "wasd_state": {
            "top": {"spine": False, "ticks": False, "minor": False, "labels": False, "title": False},
            "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
            "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
            "right": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        },
    }
    figB, axB = plt.subplots()
    ax2B = axB.twinx()
    axB.plot([0, 1], [0, 1])
    ax2B.plot([0, 1], [1, 0])
    # Replay the fixed load order: collect colors → WASD → apply → finalize
    colors = {}
    for key, props in old_sess["figure"]["spines"].items():
        if key.startswith("ax_") and props.get("color") is not None:
            colors[key[3:]] = props["color"]
        elif key.startswith("ax2_") and props.get("color") is not None:
            name = key[4:]
            colors["right" if name == "right" else name] = props["color"]
    from batplot.plot_modes.common.spines import wasd_to_tick_state

    tsB = wasd_to_tick_state(
        old_sess["wasd_state"],
        tick_defaults={"top": False, "bottom": True, "left": True, "right": True},
        label_defaults={"top": False, "bottom": True, "left": True, "right": True},
    )
    axB._saved_tick_state = tsB
    figB._cpc_spine_colors = dict(colors)
    for spine_name, color in colors.items():
        for curr in {"left": [axB], "right": [ax2B]}.get(spine_name, []):
            set_spine_side_color(curr, spine_name, color, fig=figB, tick_state=tsB)
    finalize_spine_colors_cpc(figB, axB, ax2B, tick_state=tsB, draw=True)
    assert to_hex(axB.spines["left"].get_edgecolor()) == COLORS["left"]
    assert to_hex(ax2B.spines["right"].get_edgecolor()) == COLORS["right"]
    plt.close("all")


def test_histo_spine_snapshot_pisb_and_old_snap():
    fig, ax = plt.subplots()
    ax.hist([1, 2, 2, 3])
    for side, color in (("bottom", COLORS["bottom"]), ("left", COLORS["left"])):
        set_histo_spine_color(fig, ax, side, color)
    snap = capture_histo_spine_snapshot(fig, ax)
    assert snap["spine_colors"]["bottom"] == COLORS["bottom"]
    assert snap["spine_colors"]["left"] == COLORS["left"]

    fig2, ax2 = plt.subplots()
    ax2.hist([1, 2, 3])
    apply_histo_spine_snapshot(fig2, ax2, snap)
    assert to_hex(ax2.spines["bottom"].get_edgecolor()) == COLORS["bottom"]
    assert to_hex(ax2.spines["left"].get_edgecolor()) == COLORS["left"]

    # Old snap without spine_colors key — artist capture BC
    fig3, ax3 = plt.subplots()
    ax3.hist([1, 2, 3])
    set_histo_spine_color(fig3, ax3, "bottom", COLORS["bottom"])
    old_snap = capture_histo_spine_snapshot(fig3, ax3)
    old_snap.pop("spine_colors", None)
    # Keep live colors on fig3 then apply as old path would capture
    fig4, ax4 = plt.subplots()
    ax4.hist([1, 2, 3])
    # Transfer by applying colors after capturing from colored ax3
    from batplot.plot_modes.histo.spines import capture_histo_spine_colors_from_ax

    fig4._histo_spine_colors = capture_histo_spine_colors_from_ax(ax3)
    from batplot.plot_modes.histo.spines import apply_histo_spine_colors

    apply_histo_spine_colors(fig4, ax4, fig4._histo_spine_colors)
    assert to_hex(ax4.spines["bottom"].get_edgecolor()) == COLORS["bottom"]
    plt.close("all")


def test_dqdv_restore_passes_tick_state_for_ticks():
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ts = {
        "b_ticks": True,
        "t_ticks": False,
        "l_ticks": True,
        "r_ticks": False,
        "b_labels": True,
        "t_labels": False,
        "l_labels": True,
        "r_labels": False,
        "bx": True,
        "tx": False,
        "ly": True,
        "ry": False,
    }
    ax._saved_tick_state = dict(ts)
    blob = {
        "spines": {
            "bottom": {"color": COLORS["bottom"], "linewidth": 1.0, "visible": True},
            "left": {"color": COLORS["left"], "linewidth": 1.0, "visible": True},
        },
        "tick_state": dict(ts),
    }
    from batplot.ui import finalize_spine_colors

    for name, spec in blob["spines"].items():
        set_spine_side_color(
            ax, name, spec["color"], fig=fig, tick_state=blob["tick_state"]
        )
    finalize_spine_colors(fig, ax, tick_state=blob["tick_state"], draw=True)
    assert all(
        c == COLORS["bottom"] for c in _collect_visible_tick_line_colors(ax, "bottom")
    )
    assert all(
        c == COLORS["left"] for c in _collect_visible_tick_line_colors(ax, "left")
    )
    plt.close(fig)


def test_old_pkl_bytes_edgecolor_tuple_still_loads(tmp_path: Path):
    """Backward compat: old sessions stored RGBA tuples as spine color."""
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    # Simulate old dump with RGBA tuple
    old_color = (1.0, 0.0, 0.0, 1.0)
    path = tmp_path / "old_spines.pkl"
    with path.open("wb") as f:
        pickle.dump({"spines": {"left": {"color": old_color, "visible": True}}}, f)
    with path.open("rb") as f:
        sess = pickle.load(f)
    set_spine_side_color(ax, "left", sess["spines"]["left"]["color"], fig=fig)
    finalize_spine_colors(fig, ax, draw=True)
    assert to_hex(ax.spines["left"].get_edgecolor()) == "#ff0000"
    plt.close(fig)


def test_xy_twin_spine_specs_visibility_and_color_without_wasd():
    """``apply_xy_spine_specs`` must twin-sync visibility even when wasd is absent."""
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax2 = ax.twinx()
    ax2.plot([0, 1], [2, 3])
    fig._xy_ax2 = ax2
    ts = ensure_xy_tick_state(
        ax,
        {
            "b_ticks": True,
            "t_ticks": False,
            "l_ticks": True,
            "r_ticks": True,
            "b_labels": True,
            "t_labels": False,
            "l_labels": True,
            "r_labels": True,
            "bx": True,
            "tx": False,
            "ly": True,
            "ry": True,
        },
    )
    apply_xy_spine_color(fig, ax, ts, "right", "#aa00aa")
    apply_xy_spine_color(fig, ax, ts, "left", "#00aa00")
    set_xy_spine_visible(fig, ax, "right", False)
    finalize_spine_colors(fig, ax, tick_state=ts, draw=True)
    spines_cfg = {
        side: {
            "linewidth": ax.spines[side].get_linewidth(),
            "visible": ax.spines[side].get_visible(),
            "color": resolve_spine_dump_color(ax, side, fig),
        }
        for side in SIDES
    }
    # Poison twin then re-apply spines-only (old v1 / no-wasd path).
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_edgecolor("black")
    ax.spines["right"].set_visible(True)
    ax.spines["right"].set_edgecolor("black")
    apply_xy_spine_specs(fig, ax, ts, spines_cfg)
    finalize_spine_colors(fig, ax, tick_state=ts, draw=True)
    assert ax.spines["right"].get_visible() is False
    assert ax2.spines["right"].get_visible() is False
    assert to_hex(ax.spines["right"].get_edgecolor()) == "#aa00aa"
    assert to_hex(ax2.spines["right"].get_edgecolor()) == "#aa00aa"
    assert to_hex(ax.spines["left"].get_edgecolor()) == "#00aa00"
    plt.close(fig)

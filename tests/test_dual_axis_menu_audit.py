"""Audit GC a-menu (c/n/d/s/u) + dual top tick colors after k→w2."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.electrochem.dual_axis_menu import (
    _chrome_after_dual_recreate,
    _ensure_dual_wasd_top_defaults,
)
from batplot.plot_modes.electrochem.spine_colors import _apply_secondary_top_spine_color
from batplot.plot_modes.electrochem.style import apply_ec_wasd_chrome, ec_dual_secax
from batplot.ui import finalize_spine_colors


def _gc_fig():
    fig, ax = plt.subplots()
    x = np.linspace(0.0, 200.0, 20)
    y = np.linspace(3.0, 4.0, 20)
    (ln,) = ax.plot(x, y)
    ln._orig_xdata_gc = np.asarray(x, float).copy()
    ax.set_xlabel("Specific Capacity (mAh g$^{-1}$)")
    ax.set_ylabel("Potential")
    fig._xaxis_mode = "capacity"
    fig._xaxis_c_theoretical = None
    fig._xaxis_secondary = None
    fig._xaxis_swapped = False
    return fig, ax, ln


def test_color_k_then_w2_colors_secax_tick_marks():
    """k while ticks off must still color ticks after w2/w3 (was default black)."""
    fig, ax, _ = _gc_fig()
    c_th = 162.5
    sec = ax.secondary_xaxis("top", functions=(lambda v: v / c_th, lambda v: v * c_th))
    sec.set_xlabel("Number of ions")
    fig._xaxis_mode = "dual"
    fig._xaxis_secondary = sec
    fig._xaxis_c_theoretical = c_th
    fig._ec_wasd_state = {
        "top": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": True},
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "right": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
    }
    apply_ec_wasd_chrome(fig, ax, fig._ec_wasd_state)
    _apply_secondary_top_spine_color(fig, "#cc0000", "red")
    # Enable ticks after color (user path: k then t→w2/w4/w3)
    fig._ec_wasd_state["top"]["ticks"] = True
    fig._ec_wasd_state["top"]["labels"] = True
    fig._ec_wasd_state["top"]["minor"] = True
    apply_ec_wasd_chrome(fig, ax, fig._ec_wasd_state)
    finalize_spine_colors(fig, ax, tick_state={
        "t_ticks": True, "b_ticks": True, "t_labels": True, "b_labels": True,
        "l_ticks": True, "l_labels": True, "r_ticks": False, "r_labels": False,
        "tx": True, "bx": True, "ly": True, "ry": False,
        "mbx": False, "mtx": True, "mly": False, "mry": False,
    })
    fig.canvas.draw()
    maj = sec.xaxis.get_major_ticks()[0]
    assert maj.tick2line.get_color() == "#cc0000"
    assert maj.label2.get_color() == "#cc0000"
    assert sec.xaxis.get_minor_ticks()[0].tick2line.get_color() == "#cc0000"
    plt.close(fig)


def test_reenter_dual_does_not_force_first_enable_defaults():
    """Pressing d again must not wipe user top.ticks via first_enable."""
    fig, ax, _ = _gc_fig()
    c_th = 150.0
    sec = ax.secondary_xaxis("top", functions=(lambda v: v / c_th, lambda v: v * c_th))
    fig._xaxis_mode = "dual"
    fig._xaxis_secondary = sec
    fig._xaxis_c_theoretical = c_th
    fig._ec_wasd_state = {
        "top": {"spine": True, "ticks": True, "minor": True, "labels": True, "title": True},
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "right": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
    }
    # Recreate path with first_enable=False (already dual)
    _ensure_dual_wasd_top_defaults(fig, first_enable=False)
    assert fig._ec_wasd_state["top"]["ticks"] is True
    assert fig._ec_wasd_state["top"]["minor"] is True
    assert fig._ec_wasd_state["top"]["labels"] is True
    # first_enable=True only fills missing / forces spine+title
    fig._ec_wasd_state["top"]["spine"] = False
    fig._ec_wasd_state["top"]["title"] = False
    _ensure_dual_wasd_top_defaults(fig, first_enable=True)
    assert fig._ec_wasd_state["top"]["spine"] is True
    assert fig._ec_wasd_state["top"]["title"] is True
    assert fig._ec_wasd_state["top"]["ticks"] is True  # preserved
    plt.close(fig)


def test_swap_moves_spine_visibility_and_wasd_chrome():
    """Top spine OFF + bottom ON — after s, artists must invert (follow axes)."""
    from batplot.plot_modes.electrochem.dual_axis_menu import (
        _capture_primary_bottom_x,
        _pending_top_from_bottom_cfg,
        _swap_ec_dual_spine_color_stores,
        _swap_ec_dual_wasd_top_bottom,
    )
    from batplot.ui import finalize_spine_colors

    fig, ax, _ = _gc_fig()
    c_th = 162.5
    sec = ax.secondary_xaxis("top", functions=(lambda v: v / c_th, lambda v: v * c_th))
    fig._xaxis_mode = "dual"
    fig._xaxis_secondary = sec
    fig._xaxis_c_theoretical = c_th
    fig._xaxis_swapped = False
    # Top spine OFF, bottom spine ON (ticks/labels/title opposite too)
    fig._ec_wasd_state = {
        "top": {"spine": False, "ticks": True, "minor": False, "labels": True, "title": True},
        "bottom": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
        "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "right": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
    }
    apply_ec_wasd_chrome(fig, ax, fig._ec_wasd_state)
    assert ax.spines["top"].get_visible() is False
    assert sec.spines["top"].get_visible() is False
    assert ax.spines["bottom"].get_visible() is True

    old_bot = _capture_primary_bottom_x(ax)
    _swap_ec_dual_wasd_top_bottom(fig)
    _swap_ec_dual_spine_color_stores(fig, ax)
    fig._bp_pending_dual_top_axis = _pending_top_from_bottom_cfg(
        old_bot, fig._ec_wasd_state.get("top"),
    )
    # Stale artist state that previously survived chrome: bottom left OFF wrongly
    ax.spines["bottom"].set_visible(False)
    ax.spines["top"].set_visible(True)

    sec.remove()
    sec2 = ax.secondary_xaxis("top", functions=(lambda v: v * c_th, lambda v: v / c_th))
    fig._xaxis_secondary = sec2
    fig._xaxis_swapped = True
    ax.set_xlabel("ions")
    sec2.set_xlabel("capacity")
    _chrome_after_dual_recreate(fig, ax, keep_top_xlabel=False, keep_bottom_xlabel=False)
    finalize_spine_colors(fig, ax)
    fig.canvas.draw()
    sec_live = ec_dual_secax(fig)
    assert sec_live is not None
    # After swap: top gets former bottom (spine ON, ticks OFF, title OFF)
    assert fig._ec_wasd_state["top"]["spine"] is True
    assert fig._ec_wasd_state["bottom"]["spine"] is False
    assert ax.spines["top"].get_visible() is True
    assert sec_live.spines["top"].get_visible() is True
    assert ax.spines["bottom"].get_visible() is False
    assert ax.xaxis.get_major_ticks()[0].tick1line.get_visible() is True
    assert ax.xaxis.label.get_visible() is True
    assert sec_live.xaxis.get_major_ticks()[0].tick2line.get_visible() is False
    assert sec_live.xaxis.label.get_visible() is False
    plt.close(fig)


def test_swap_moves_top_ion_color_to_bottom():
    """Color ions on top, then s — ions color must move to bottom (not stick to top)."""
    from batplot.plot_modes.electrochem.dual_axis_menu import (
        _capture_primary_bottom_x,
        _pending_top_from_bottom_cfg,
        _swap_ec_dual_spine_color_stores,
        _swap_ec_dual_wasd_top_bottom,
    )
    from batplot.plot_modes.electrochem.style import capture_dual_top_axis
    from batplot.ui import finalize_spine_colors, set_spine_side_color

    fig, ax, _ = _gc_fig()
    c_th = 162.5
    sec = ax.secondary_xaxis("top", functions=(lambda v: v / c_th, lambda v: v * c_th))
    sec.set_xlabel(f"Number of ions (C / {c_th:g} mAh g$^{{-1}}$)")
    ax.set_xlabel("Specific Capacity (mAh g$^{-1}$)")
    fig._xaxis_mode = "dual"
    fig._xaxis_secondary = sec
    fig._xaxis_c_theoretical = c_th
    fig._xaxis_swapped = False
    fig._ec_wasd_state = {
        "top": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "right": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
    }
    apply_ec_wasd_chrome(fig, ax, fig._ec_wasd_state)
    # Distinct colors: ions top red, capacity bottom blue
    _apply_secondary_top_spine_color(fig, "#cc0000", "red")
    set_spine_side_color(ax, "bottom", "#0033aa", fig=fig)
    fig.canvas.draw()
    assert sec.spines["top"].get_edgecolor()[0] > 0.5  # reddish

    old_top = capture_dual_top_axis(fig, ax) or {}
    old_bot = _capture_primary_bottom_x(ax)
    assert old_top.get("spine_color") == "#cc0000"
    assert old_bot.get("spine_color") == "#0033aa"

    _swap_ec_dual_wasd_top_bottom(fig)
    _swap_ec_dual_spine_color_stores(fig, ax)
    fig._bp_pending_dual_top_axis = _pending_top_from_bottom_cfg(
        old_bot, fig._ec_wasd_state.get("top"),
    )
    sec.remove()
    # After swap: bottom=ions, top=capacity
    sec2 = ax.secondary_xaxis("top", functions=(lambda v: v * c_th, lambda v: v / c_th))
    fig._xaxis_secondary = sec2
    fig._xaxis_swapped = True
    ax.set_xlabel(f"Number of ions (C / {c_th:g} mAh g$^{{-1}}$)")
    sec2.set_xlabel("Specific Capacity (mAh g$^{-1}$)")
    _chrome_after_dual_recreate(fig, ax, keep_top_xlabel=False, keep_bottom_xlabel=False)
    set_spine_side_color(ax, "bottom", old_top["spine_color"], fig=fig)
    ax.xaxis.label.set_color(old_top.get("label_color") or old_top["spine_color"])
    finalize_spine_colors(fig, ax)
    fig.canvas.draw()

    # New top (capacity) = former bottom blue
    assert (fig._bp_spine_side_colors or {}).get("top") == "#0033aa"
    # New bottom (ions) = former top red
    assert (fig._bp_spine_side_colors or {}).get("bottom") == "#cc0000"
    from matplotlib.colors import to_hex
    assert to_hex(sec2.spines["top"].get_edgecolor()) == "#0033aa"
    assert to_hex(ax.spines["bottom"].get_edgecolor()) == "#cc0000"
    plt.close(fig)


def test_chrome_after_dual_keeps_tick_colors():
    fig, ax, _ = _gc_fig()
    c_th = 162.5
    sec = ax.secondary_xaxis("top", functions=(lambda v: v / c_th, lambda v: v * c_th))
    sec.set_xlabel("Number of ions")
    fig._xaxis_mode = "dual"
    fig._xaxis_secondary = sec
    fig._xaxis_c_theoretical = c_th
    fig._ec_wasd_state = {
        "top": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "right": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
    }
    apply_ec_wasd_chrome(fig, ax, fig._ec_wasd_state)
    _apply_secondary_top_spine_color(fig, "#0066cc", "blue")
    fig._bp_pending_dual_top_axis = {
        "xlabel": "Number of ions",
        "xlabel_visible": True,
        "label_color": "#0066cc",
        "spine_visible": True,
        "spine_color": "#0066cc",
    }
    # Simulate swap/u recreate
    sec.remove()
    sec2 = ax.secondary_xaxis("top", functions=(lambda v: v / c_th, lambda v: v * c_th))
    fig._xaxis_secondary = sec2
    sec2.set_xlabel("Number of ions")
    _chrome_after_dual_recreate(fig, ax, first_enable=False)
    finalize_spine_colors(fig, ax)
    fig.canvas.draw()
    sec_live = ec_dual_secax(fig)
    assert sec_live is not None
    assert sec_live.xaxis.get_major_ticks()[0].tick2line.get_color() == "#0066cc"
    plt.close(fig)

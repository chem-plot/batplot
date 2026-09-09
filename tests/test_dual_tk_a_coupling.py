"""GC dual: t/k/f respect a-menu; p/i/s/b dump+style sync stay coupled."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_hex

from matplotlib.ticker import AutoMinorLocator, MultipleLocator

from batplot.plot_modes.common.spines import apply_frame_and_tick_widths, apply_wasd_tick_params
from batplot.plot_modes.electrochem.dual_axis_menu import _leave_dual_axis_chrome
from batplot.plot_modes.electrochem.spine_colors import _apply_secondary_top_spine_color
from batplot.plot_modes.electrochem.style import (
    _get_style_snapshot,
    apply_ec_wasd_chrome,
    ec_dual_secax,
    ec_dual_width_axes,
    ec_dual_x_scale_factor,
    reseal_ec_chrome,
    suppress_ec_dual_duplicate_top_title,
    sync_ec_dual_secax_x_locators,
    xaxis_dual_export_dict,
)
from batplot.plot_modes.electrochem.style_apply import apply_ec_style_config
from batplot.plot_modes.electrochem.undo_state import ec_push_state
from batplot.ui import finalize_spine_colors


def _gc_dual(*, swapped: bool = False, c_th: float = 162.5):
    fig, ax = plt.subplots()
    x = np.linspace(0.0, 200.0, 20)
    y = np.linspace(3.0, 4.0, 20)
    (ln,) = ax.plot(x, y)
    ln._orig_xdata_gc = np.asarray(x, float).copy()
    if swapped:
        ln.set_xdata(np.asarray(x, float) / c_th)
        sec = ax.secondary_xaxis("top", functions=(lambda v: v * c_th, lambda v: v / c_th))
        ax.set_xlabel("Number of ions")
        sec.set_xlabel("Specific Capacity")
    else:
        sec = ax.secondary_xaxis("top", functions=(lambda v: v / c_th, lambda v: v * c_th))
        ax.set_xlabel("Specific Capacity")
        sec.set_xlabel("Number of ions")
    fig._xaxis_mode = "dual"
    fig._xaxis_secondary = sec
    fig._xaxis_c_theoretical = c_th
    fig._xaxis_swapped = swapped
    fig._ec_wasd_state = {
        "top": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "right": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
    }
    apply_ec_wasd_chrome(fig, ax, fig._ec_wasd_state)
    return fig, ax, sec, {1: {"charge": ln, "discharge": None}}


def test_k_top_colors_secax_when_dual():
    fig, ax, sec, _ = _gc_dual()
    _apply_secondary_top_spine_color(fig, "#cc0000", "red")
    finalize_spine_colors(fig, ax)
    fig.canvas.draw()
    assert to_hex(sec.spines["top"].get_edgecolor()) == "#cc0000"
    assert to_hex(ax.spines["top"].get_edgecolor()) == "#cc0000"
    plt.close(fig)


def test_t_w1_off_hides_both_top_spines():
    fig, ax, sec, _ = _gc_dual()
    fig._ec_wasd_state["top"]["spine"] = False
    apply_ec_wasd_chrome(fig, ax, fig._ec_wasd_state)
    assert ax.spines["top"].get_visible() is False
    assert sec.spines["top"].get_visible() is False
    plt.close(fig)


def test_frame_width_applies_to_secax():
    fig, ax, sec, _ = _gc_dual()
    axes = ec_dual_width_axes(fig, ax)
    assert sec in axes
    apply_frame_and_tick_widths(axes, frame_width=2.5, major_width=1.75, minor_width=1.0)
    assert ax.spines["bottom"].get_linewidth() == 2.5
    assert sec.spines["top"].get_linewidth() == 2.5
    plt.close(fig)


def test_leave_dual_export_swapped_false():
    fig, ax, sec, _ = _gc_dual(swapped=True)
    sec.remove()
    fig._xaxis_secondary = None
    fig._xaxis_mode = "capacity"
    _leave_dual_axis_chrome(fig, ax)
    xd = xaxis_dual_export_dict(fig, ax)
    assert xd["mode"] == "capacity"
    assert xd["swapped"] is False
    snap = _get_style_snapshot(fig, ax, {}, {})
    assert snap["xaxis_dual"]["swapped"] is False
    plt.close(fig)


def test_style_sync_propagates_dual_wasd_and_top_color():
    """Batch/i path: apply_ec_style_config from dual ref → capacity panel."""
    ref_fig, ref_ax, ref_sec, ref_lines = _gc_dual()
    _apply_secondary_top_spine_color(ref_fig, "#00aa55", "green")
    ref_fig._ec_wasd_state["top"]["spine"] = True
    ref_fig._ec_wasd_state["top"]["ticks"] = False
    ref_fig._ec_wasd_state["top"]["labels"] = False
    apply_ec_wasd_chrome(ref_fig, ref_ax, ref_fig._ec_wasd_state)
    finalize_spine_colors(ref_fig, ref_ax)
    cfg = _get_style_snapshot(ref_fig, ref_ax, ref_lines, {})

    tgt_fig, tgt_ax = plt.subplots()
    x = np.linspace(0.0, 200.0, 20)
    y = np.linspace(3.0, 4.0, 20)
    (ln,) = tgt_ax.plot(x, y)
    ln._orig_xdata_gc = np.asarray(x, float).copy()
    tgt_fig._xaxis_mode = "capacity"
    tgt_fig._xaxis_secondary = None
    tgt_fig._xaxis_swapped = False
    tick_state = {
        "t_ticks": False, "b_ticks": True, "t_labels": False, "b_labels": True,
        "l_ticks": True, "l_labels": True, "r_ticks": False, "r_labels": False,
        "tx": False, "bx": True, "ly": True, "ry": False,
        "mbx": False, "mtx": False, "mly": False, "mry": False,
    }
    ok = apply_ec_style_config(
        cfg,
        fig=tgt_fig,
        ax=tgt_ax,
        cycle_lines={1: {"charge": ln, "discharge": None}},
        file_data=None,
        tick_state=tick_state,
        is_multi_file=False,
        silent=True,
    )
    assert ok is True
    assert tgt_fig._xaxis_mode == "dual"
    sec = ec_dual_secax(tgt_fig)
    assert sec is not None
    assert tgt_fig._ec_wasd_state["top"]["ticks"] is False
    assert sec.spines["top"].get_visible() is True
    assert to_hex(sec.spines["top"].get_edgecolor()) == "#00aa55"
    plt.close(ref_fig)
    plt.close(tgt_fig)


def test_undo_capture_swapped_false_outside_dual():
    fig, ax, sec, cycle_lines = _gc_dual(swapped=True)
    sec.remove()
    fig._xaxis_secondary = None
    fig._xaxis_mode = "ions"
    # sticky flag without leave helper (legacy bug path)
    fig._xaxis_swapped = True
    hist = []
    ec_push_state(
        state_history=hist,
        fig=fig,
        ax=ax,
        tick_state={},
        cycle_lines=cycle_lines,
        file_data=None,
        is_multi_file=False,
        note="leave",
    )
    # export helper used by undo must not dump swapped outside dual
    assert hist[-1]["xaxis_dual"]["mode"] == "ions"
    assert hist[-1]["xaxis_dual"]["swapped"] is False
    plt.close(fig)


def test_k_tick_marks_survive_bare_tick_params_and_draw():
    """P0: k→w must color ions tick marks even after tick_params+draw (no finalize)."""
    fig, ax, sec, _ = _gc_dual()
    _apply_secondary_top_spine_color(fig, "#cc0000", "red")
    # Hostile: visibility-only tick_params (what apply_ec_dual_top_wasd does)
    sec.tick_params(axis="x", which="major", top=True, labeltop=True)
    fig.canvas.draw()
    # Force path must have written kw so rebuild keeps color
    maj = sec.xaxis.get_major_ticks()[0]
    assert maj.tick2line.get_color() == "#cc0000"
    assert (sec.xaxis._major_tick_kw or {}).get("color") == "#cc0000"
    plt.close(fig)


def test_k_then_wasd_chrome_keeps_tick_mark_color():
    fig, ax, sec, _ = _gc_dual()
    _apply_secondary_top_spine_color(fig, "#0033aa", "blue")
    apply_ec_wasd_chrome(fig, ax, fig._ec_wasd_state)
    fig.canvas.draw()
    assert sec.xaxis.get_major_ticks()[0].tick2line.get_color() == "#0033aa"
    plt.close(fig)


def test_dual_n_syncs_secax_major_unswapped_and_swapped():
    fig, ax, sec, _ = _gc_dual(swapped=False, c_th=162.5)
    ax.xaxis.set_major_locator(MultipleLocator(50.0))
    sync_ec_dual_secax_x_locators(fig, ax, fig._ec_wasd_state)
    maj = sec.xaxis.get_major_locator()
    assert isinstance(maj, MultipleLocator)
    assert abs(float(maj._edge.step) - 50.0 / 162.5) < 1e-9
    assert abs(ec_dual_x_scale_factor(fig) - 1.0 / 162.5) < 1e-12
    plt.close(fig)

    fig2, ax2, sec2, _ = _gc_dual(swapped=True, c_th=162.5)
    ax2.xaxis.set_major_locator(MultipleLocator(0.5))
    sync_ec_dual_secax_x_locators(fig2, ax2, fig2._ec_wasd_state)
    maj2 = sec2.xaxis.get_major_locator()
    assert isinstance(maj2, MultipleLocator)
    assert abs(float(maj2._edge.step) - 0.5 * 162.5) < 1e-9
    plt.close(fig2)


def _autominor_ndivs(loc) -> int:
    return int(getattr(loc, "ndivs", None) or getattr(loc, "_ndivs", None) or 0)


def test_dual_m_preserves_autominor_after_reseal():
    fig, ax, sec, _ = _gc_dual()
    fig._ec_wasd_state["top"]["minor"] = True
    fig._ec_wasd_state["bottom"]["minor"] = True
    ax.xaxis.set_minor_locator(AutoMinorLocator(5))  # 4 minors / interval
    apply_wasd_tick_params(ax, fig._ec_wasd_state, x_sides=("bottom",))
    # Must preserve custom ndivs (not wipe to default AutoMinorLocator())
    loc = ax.xaxis.get_minor_locator()
    assert isinstance(loc, AutoMinorLocator)
    assert _autominor_ndivs(loc) == 5
    reseal_ec_chrome(fig, ax, wasd=fig._ec_wasd_state)
    loc2 = ax.xaxis.get_minor_locator()
    assert isinstance(loc2, AutoMinorLocator)
    assert _autominor_ndivs(loc2) == 5
    sec_loc = sec.xaxis.get_minor_locator()
    assert isinstance(sec_loc, AutoMinorLocator)
    assert _autominor_ndivs(sec_loc) == 5
    plt.close(fig)


def test_swap_multiplelocator_minor_uses_multiply_not_divide():
    fig, ax, sec, _ = _gc_dual(swapped=True, c_th=100.0)
    fig._ec_wasd_state["top"]["minor"] = True
    ax.xaxis.set_major_locator(MultipleLocator(0.25))
    ax.xaxis.set_minor_locator(MultipleLocator(0.05))  # ions step
    sync_ec_dual_secax_x_locators(fig, ax, fig._ec_wasd_state)
    loc = sec.xaxis.get_minor_locator()
    assert isinstance(loc, MultipleLocator)
    # swapped: top=capacity → step * C_th
    assert abs(float(loc._edge.step) - 0.05 * 100.0) < 1e-9
    plt.close(fig)


def test_reseal_after_nice_ticks_keeps_primary_top_off():
    fig, ax, sec, _ = _gc_dual()
    ax.tick_params(axis="x", which="major", top=True, labeltop=True)
    ax._top_xlabel_on = True
    reseal_ec_chrome(fig, ax, wasd=fig._ec_wasd_state)
    suppress_ec_dual_duplicate_top_title(ax, fig)
    assert ax._top_xlabel_on is False
    kw = ax.xaxis._major_tick_kw or {}
    assert bool(kw.get("top", kw.get("tick2On", False))) is False
    art = getattr(ax, "_top_xlabel_artist", None)
    if art is not None:
        assert art.get_visible() is False
    plt.close(fig)

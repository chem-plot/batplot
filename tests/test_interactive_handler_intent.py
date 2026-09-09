"""Behavioral intent tests for interactive menu handlers (not quit-only smoke)."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.colors import to_hex

from batplot.plot_modes.cpc.panel_menus import (
    _cpc_efficiency_globally_on,
    apply_cpc_file_artist_visibility,
    run_cpc_spine_color_menu,
)
from batplot.plot_modes.electrochem.colors import set_ec_file_visibility
from batplot.plot_modes.electrochem.menu import build_electrochem_menu_columns
from batplot.plot_modes.electrochem.overview import _line_capacity, build_gc_overview_datasets
from batplot.plot_modes.xy.line_style import run_line_style_menu
from batplot.plot_modes.xy.spines import apply_xy_spine_color, ensure_xy_tick_state
from batplot.ui import finalize_spine_colors


def _feed(*vals: str):
    it = iter(vals)

    def _in(*_a, **_k):
        try:
            return next(it)
        except StopIteration:
            return "q"

    return _in


def test_ec_v_reshow_respects_display_mode():
    fig, ax = plt.subplots()
    (chg,) = ax.plot([0, 1], [3, 4], label="c")
    (dch,) = ax.plot([0, 1], [4, 3], label="d")
    fig._ec_display_mode = "charge"
    f = {
        "visible": True,
        "cycle_lines": {1: {"charge": chg, "discharge": dch}},
        "selected_cycles": [1],
    }
    set_ec_file_visibility(f, False, display_mode="charge")
    assert chg.get_visible() is False and dch.get_visible() is False
    set_ec_file_visibility(f, True, display_mode="charge")
    assert chg.get_visible() is True
    assert dch.get_visible() is False
    plt.close(fig)


def test_ec_menu_hides_a_on_cv_and_relabels_xy():
    fig = plt.figure()
    fig._ec_is_gc = False
    fig._ec_overview_enabled = False
    cols = build_electrochem_menu_columns(1, is_dqdv=False, fig=fig)
    flat = " | ".join(sum(cols, []))
    assert "a: capacity/ion" not in flat
    assert "x: x range" in flat and "y: y range" in flat
    assert "x-scale" not in flat
    fig._ec_is_gc = True
    cols_gc = build_electrochem_menu_columns(1, is_dqdv=False, fig=fig)
    flat_gc = " | ".join(sum(cols_gc, []))
    assert "a: capacity/ion" in flat_gc
    plt.close(fig)


def test_ec_overview_prefers_orig_xdata_gc_under_ions():
    fig, ax = plt.subplots()
    (ln,) = ax.plot([0.1, 0.2], [3.0, 4.0])  # ions on X
    ln._orig_xdata_gc = np.array([0.0, 150.0], dtype=float)
    fig._xaxis_mode = "ions"
    q = _line_capacity(ln, capacity_on_x=True)
    assert q == pytest.approx(150.0)
    ds = build_gc_overview_datasets(
        cycle_lines={1: {"charge": ln, "discharge": None}},
        fig=fig,
    )
    assert ds and float(ds[0]["q_chg"][0]) == pytest.approx(150.0)
    plt.close(fig)


def test_cpc_bare_a_is_not_auto_toggle():
    from batplot.plot_modes.common.menu_rendering import colorize_menu
    from batplot.plot_modes.common.terminal import colorize_inline_commands, colorize_prompt

    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc_c = ax.scatter([1], [1])
    sc_e = ax2.scatter([1], [90])
    fig._cpc_spine_auto = False
    called = {"n": 0}

    def _set_spine(_side, _color):
        called["n"] += 1

    # bare a must not flip auto; a:red should color left
    run_cpc_spine_color_menu(
        fig=fig,
        file_data=None,
        current_file_idx=0,
        is_multi_file=False,
        sc_charge=sc_c,
        sc_eff=sc_e,
        push_state=lambda *_a, **_k: None,
        set_spine_color=_set_spine,
        print_menu=lambda *_a, **_k: None,
        print_file_list=lambda *_a, **_k: None,
        safe_input=_feed("a", "a:red", "q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
        colorize_inline_commands=colorize_inline_commands,
    )
    assert fig._cpc_spine_auto is False
    assert called["n"] >= 1
    plt.close(fig)


def test_cpc_ry_toggle_works_when_all_files_hidden():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    files = []
    for i in range(2):
        files.append(
            {
                "visible": False,
                "sc_charge": ax.scatter([i], [1]),
                "sc_discharge": ax.scatter([i], [2]),
                "sc_eff": ax2.scatter([i], [90]),
            }
        )
    fig._cpc_wasd_state = {
        "right": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True}
    }
    apply_cpc_file_artist_visibility(fig, files, eff_on=True)
    assert all(not f["sc_eff"].get_visible() for f in files)
    assert _cpc_efficiency_globally_on(fig, files) is True
    # Simulate ry toggle intent
    new_vis = not _cpc_efficiency_globally_on(fig, files)
    assert new_vis is False
    fig._cpc_wasd_state["right"]["title"] = False
    apply_cpc_file_artist_visibility(fig, files, eff_on=False)
    assert _cpc_efficiency_globally_on(fig, files) is False
    plt.close(fig)


def test_xy_color_menu_gets_tick_state_for_right_spine():
    from batplot.plot_modes.xy.colors import run_xy_color_menu
    from batplot.plot_modes.common.terminal import colorize_prompt

    fig, ax = plt.subplots()
    (ln,) = ax.plot([0, 1], [0, 1], label="c1")
    ax.tick_params(right=True, labelright=True, left=True, labelleft=True)
    ts = ensure_xy_tick_state(
        ax,
        {k: True for k in (
            "b_ticks", "t_ticks", "l_ticks", "r_ticks",
            "b_labels", "t_labels", "l_labels", "r_labels",
            "bx", "tx", "ly", "ry",
        )},
    )
    run_xy_color_menu(
        ax=ax,
        fig=fig,
        labels=["c1"],
        y_data_list=[np.array([0.0, 1.0])],
        label_text_objects=[],
        stack=False,
        args_files=["a.xy"],
        line_getter=lambda i: ln,
        bp=None,
        get_cif_series=lambda: None,
        sync_fig_cif_tick_series=lambda: None,
        position_top_xlabel=lambda: None,
        position_right_ylabel=lambda: None,
        push_state=lambda *_a, **_k: None,
        safe_input=_feed("d:red", "q"),
        colorize_prompt=colorize_prompt,
        tick_state=ts,
    )
    finalize_spine_colors(fig, ax, tick_state=ts, draw=True)
    assert to_hex(ax.spines["right"].get_edgecolor()) == "#ff0000"
    plt.close(fig)


def test_xy_line_style_selects_twin_curves():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    fig._xy_ax2 = ax2
    (ln0,) = ax.plot([0, 1], [0, 1])
    (ln1,) = ax2.plot([0, 1], [10, 20])
    lines = [ln0, ln1]
    run_line_style_menu(
        ax=ax,
        fig=fig,
        lines_by_curve=None,
        line_getter=lambda i: lines[i],
        line_count=lambda: 2,
        push_state=lambda *_a, **_k: None,
        safe_input=_feed("l", "all", "q"),
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
    )
    assert ln0.get_linestyle() == "-"
    assert ln1.get_linestyle() == "-"
    assert ln1.get_marker() in ("None", "none", "")
    plt.close(fig)


def test_xy_frame_width_applies_to_twin():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    fig._xy_ax2 = ax2
    (ln,) = ax.plot([0, 1], [0, 1])
    run_line_style_menu(
        ax=ax,
        fig=fig,
        lines_by_curve=None,
        line_getter=lambda i: ln,
        line_count=lambda: 1,
        push_state=lambda *_a, **_k: None,
        safe_input=_feed("f", "2.5", "q", "q"),
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
    )
    assert ax.spines["left"].get_linewidth() == pytest.approx(2.5)
    assert ax2.spines["right"].get_linewidth() == pytest.approx(2.5)
    plt.close(fig)


def test_operando_t_direction_axes_is_pane_scoped():
    src = open("batplot/plot_modes/operando/interactive.py").read()
    assert "direction_axes=[target]" in src
    assert "length_axes=[target]" in src
    assert "direction_axes=[ax] + ([ec_ax]" not in src


def test_batch_operando_wasd_pane_scope_flag():
    from batplot.plot_modes.batch_session.operando_batch_helpers import (
        apply_operando_wasd_chrome_only,
    )
    import inspect

    src = inspect.getsource(apply_operando_wasd_chrome_only)
    assert "_batch_edited_pane" in src
    assert "touch_op" in src and "touch_ec" in src

"""Hard-check regressions: twin autoscale / rearrange master / batch parity."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot.plot_modes.batch_session.menu_cpc import _toggle_efficiency_all
from batplot.plot_modes.batch_session.menu_xy import (
    _iter_panel_curve_lines,
    _line_count,
    _line_getter,
)
from batplot.plot_modes.cpc.panel_menus import _cpc_efficiency_globally_on
from batplot.plot_modes.xy.axis_range import _sync_xy_twin_xlim, relim_xy_twins
from batplot.plot_modes.xy.full_data import get_master_full, install_master_full


def test_relim_xy_twins_updates_right_ylim():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    fig._xy_ax2 = ax2
    ax.plot([0, 1], [0, 1])
    (ln2,) = ax2.plot([0, 1], [0, 10])
    ax2.set_ylim(0, 2)
    ln2.set_data([0, 1], [0, 50])
    # Force stale so relim sees new data (mirrors interactive set_data path).
    try:
        ax2._stale = True
        ln2.stale = True
    except Exception:
        pass
    relim_xy_twins(fig, ax, scaley=True)
    lo, hi = ax2.get_ylim()
    assert hi >= 45, (lo, hi)
    plt.close(fig)


def test_sync_xy_twin_xlim_txaxis():
    fig, ax = plt.subplots()
    ax2 = ax.twinx().twiny()
    fig._xy_ax2 = ax2
    fig._xy_use_top_x = True
    ax.set_xlim(10, 60)
    ax2.set_xlim(10, 60)
    ax.set_xlim(0.7, 4.0)
    _sync_xy_twin_xlim(fig, ax)
    assert ax2.get_xlim() == pytest.approx(ax.get_xlim())
    plt.close(fig)


def test_arrange_reorders_master_full_buffers():
    from batplot.plot_modes.xy.arrange import run_rearrange_menu
    import types

    fig, ax = plt.subplots()
    x1 = np.array([1.0, 2.0])
    x2 = np.array([10.0, 20.0])
    y1 = np.array([1.0, 2.0])
    y2 = np.array([3.0, 4.0])
    ax.plot(x1, y1)
    ax.plot(x2, y2)
    x_data = [x1.copy(), x2.copy()]
    y_data = [y1.copy(), y2.copy()]
    orig = [y1.copy(), y2.copy()]
    labels = ["a", "b"]
    label_txt = [ax.text(0, 0, "1"), ax.text(0, 0, "2")]
    x_full = [x1.copy(), x2.copy()]
    y_full = [y1.copy(), y2.copy()]
    install_master_full(fig, x_full, y_full, force=True)
    args = types.SimpleNamespace(stack=False, autoscale=False)
    answers = iter(["2 1", "q"])
    run_rearrange_menu(
        args=args,
        ax=ax,
        fig=fig,
        labels=labels,
        label_text_objects=label_txt,
        x_data_list=x_data,
        y_data_list=y_data,
        orig_y=orig,
        offsets_list=[0.0, 0.0],
        x_full_list=x_full,
        raw_y_full_list=y_full,
        delta=1.0,
        push_state=lambda *_a, **_k: None,
        _safe_input=lambda *_a, **_k: next(answers, "q"),
        _line=lambda i: ax.lines[i],
        _lines_by_curve=None,
    )
    mx, my = get_master_full(fig)
    assert mx is not None and float(mx[0][0]) == pytest.approx(10.0)
    assert float(x_full[0][0]) == pytest.approx(10.0)
    plt.close(fig)


def test_batch_cpc_ry_uses_global_helper_when_files_hidden():
    from batplot.plot_modes.batch_session.load import CpcPanel

    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc_c = ax.scatter([1], [1])
    sc_d = ax.scatter([1], [2])
    sc_e = ax2.scatter([1], [90])
    fig._cpc_wasd_state = {
        "right": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True}
    }
    # Simulate multi-file bookkeeping on panel
    panel = CpcPanel(
        path="a.pkl",
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
    )
    # Hide file visibility via wasd-on but artists off
    sc_e.set_visible(False)
    assert _cpc_efficiency_globally_on(fig, []) is True  # wasd title
    new = _toggle_efficiency_all([panel])
    assert new is False
    assert fig._cpc_wasd_state["right"]["title"] is False
    plt.close(fig)


def test_batch_xy_line_helpers_include_twin():
    from batplot.plot_modes.batch_session.load import XyPanel

    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    (ln0,) = ax.plot([0, 1], [0, 1])
    (ln1,) = ax2.plot([0, 1], [10, 20])
    fig._xy_ax2 = ax2
    fig._xy_lines_by_curve = [ln0, ln1]
    panel = XyPanel(path="a.pkl", fig=fig, ax=ax, menu_kwargs={})
    assert _line_count(panel) == 2
    assert _line_getter(panel)(1) is ln1
    assert ln1 in _iter_panel_curve_lines(panel)
    plt.close(fig)


def test_batch_dqdv_menu_lists_and_handles_k():
    src = open("batplot/plot_modes/batch_session/menu_dqdv_2d.py").read()
    assert '"k: spine colors"' in src or "'k: spine colors'" in src
    assert 'cmd == "k"' in src
    assert "run_operando_batch_spine_color_menu" in src

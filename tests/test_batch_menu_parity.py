"""Tests for EC/CPC/XY batch Tier A/B menu surfaces and helpers."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
import pytest

from batplot.plot_modes.batch_session.load import CpcPanel, EcPanel, XyPanel
from batplot.plot_modes.batch_session.menu_cpc import (
    _apply_cpc_style,
    _capture_panel as cpc_capture,
    _print_cpc_batch_menu,
    _set_marker_sizes_all,
    _apply_display_mode_all,
)
from batplot.plot_modes.batch_session.menu_ec import (
    _apply_cfg as ec_apply,
    _capture_panel as ec_capture,
    _print_ec_batch_menu,
)
from batplot.plot_modes.batch_session.menu_xy import _print_xy_batch_menu


def _strip_ansi(text: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_ec_batch_menu_lists_tier_ab_keys(capsys):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    p = EcPanel(path="a.pkl", fig=fig, ax=ax, cycle_lines={}, file_data=None)
    _print_ec_batch_menu([p])
    out = _strip_ansi(capsys.readouterr().out)
    for token in (
        "font", "line style", "spines/ticks", "spine colors", "legend",
        "display chg/dch", "cycles/colors", "show/hide files",
        "size",
        "rename", "x range", "y range",
        "export style", "import style", "save session", "undo",
    ):
        assert token in out, f"missing {token!r}"
    assert "rearrange legend" not in out
    assert "(ref)" not in out
    plt.close(fig)


def test_ec_batch_menu_shows_rearrange_legend_for_multi_file(capsys):
    fig, ax = plt.subplots()
    (c1,) = ax.plot([0, 1], [0, 1])
    (d1,) = ax.plot([0, 1], [1, 0])
    (c2,) = ax.plot([0, 1], [0.5, 1.5])
    file_data = [
        {"filename": "a", "visible": True, "cycle_lines": {1: {"charge": c1, "discharge": d1}}},
        {"filename": "b", "visible": True, "cycle_lines": {1: {"charge": c2, "discharge": d1}}},
    ]
    p = EcPanel(path="a.pkl", fig=fig, ax=ax, cycle_lines={1: {"charge": c1, "discharge": d1}}, file_data=file_data)
    _print_ec_batch_menu([p])
    out = _strip_ansi(capsys.readouterr().out)
    assert "rearrange legend" in out


def test_ec_batch_range_and_style_roundtrip():
    fig, ax = plt.subplots()
    (c,) = ax.plot([0.0, 1.0], [0.0, 1.0])
    (d,) = ax.plot([0.0, 1.0], [1.0, 0.0])
    p = EcPanel(
        path="a.pkl",
        fig=fig,
        ax=ax,
        cycle_lines={1: {"charge": c, "discharge": d}},
        file_data=None,
    )
    ax.set_xlim(0.2, 0.8)
    ax.set_ylim(0.1, 0.9)
    cfg = ec_capture(p)
    assert cfg.get("kind") == "ec_style_geom"
    ax.set_xlim(0.0, 1.0)
    ax.set_ylim(0.0, 1.0)
    assert ec_apply(p, cfg)
    assert ax.get_xlim() == pytest.approx((0.2, 0.8))
    assert ax.get_ylim() == pytest.approx((0.1, 0.9))
    plt.close(fig)


def test_cpc_batch_menu_lists_tier_ab_keys(capsys):
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc_c = ax.scatter([1, 2], [3, 4])
    sc_d = ax.scatter([1, 2], [2.5, 3.5])
    sc_e = ax2.scatter([1, 2], [90, 95])
    p = CpcPanel(
        path="a.pkl",
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
    )
    _print_cpc_batch_menu([p])
    out = _strip_ansi(capsys.readouterr().out)
    for token in (
        "font", "line widths", "marker sizes", "colors", "display chg/dch",
        "show/hide efficiency", "spines/ticks", "legend", "show/hide files",
        "size",
        "rename labels", "x range", "y ranges", "invert efficiency",
    ):
        assert token in out, f"missing {token!r}"
    plt.close(fig)


def test_cpc_batch_markers_display_and_style_roundtrip():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc_c = ax.scatter([1, 2], [3, 4])
    sc_d = ax.scatter([1, 2], [2.5, 3.5])
    sc_e = ax2.scatter([1, 2], [90, 95])
    p = CpcPanel(
        path="a.pkl",
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
    )
    panels = [p]
    _set_marker_sizes_all(panels, 64.0)
    assert float(sc_c.get_sizes()[0]) == pytest.approx(64.0)
    _apply_display_mode_all(panels, "charge")
    assert sc_c.get_visible() is True
    assert sc_d.get_visible() is False
    ax.set_xlim(1.5, 2.5)
    cfg = cpc_capture(p)
    assert cfg.get("kind") == "cpc_style_geom"
    ax.set_xlim(0.0, 10.0)
    assert _apply_cpc_style(p, cfg)
    assert ax.get_xlim() == pytest.approx((1.5, 2.5))
    plt.close(fig)


def test_xy_batch_menu_lists_tier_b_keys(capsys):
    fig, ax = plt.subplots()
    ax.plot([1, 2], [3, 4])
    p = XyPanel(path="a.pkl", fig=fig, ax=ax, menu_kwargs={})
    _print_xy_batch_menu([p])
    out = _strip_ansi(capsys.readouterr().out)
    for token in (
        "colors", "font", "line style", "spines/ticks", "curve labels",
        "size", "rename labels", "x range", "y range", "peak finder",
    ):
        assert token in out, f"missing {token!r}"
    plt.close(fig)


def test_ec_batch_figure_exporter_not_shadowed_by_style_export(tmp_path):
    """Regression: nested style exporter must not shadow figure ``e``/``oe`` saver."""
    import inspect

    from batplot.plot_modes.batch_session import menu_ec as ME

    src = inspect.getsource(ME.run_ec_batch_menu)
    assert "def _export_ec_style_panel" in src
    # Nested style writer must not reuse the figure-export name.
    assert "def _export_ec_panel(" not in src
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    p = EcPanel(path="a.pkl", fig=fig, ax=ax, cycle_lines={}, file_data=None)
    out = tmp_path / "ec.svg"
    ME._export_ec_panel(p, str(out))
    assert out.is_file() and out.stat().st_size > 0
    plt.close(fig)


def test_xy_batch_spine_menu_builds_wasd_without_crash():
    """Regression: batch ``t`` must not call ``build_wasd_state(ax)`` positionally."""
    from batplot.plot_modes.batch_session.common import SyncUndoStacks
    from batplot.plot_modes.batch_session.xy_batch_helpers import run_xy_batch_spine_menu
    from batplot.plot_modes.common.terminal import safe_input as real_safe_input
    import batplot.plot_modes.batch_session.xy_batch_helpers as XB

    fig, ax = plt.subplots()
    ax.plot([1, 2], [3, 4])
    p = XyPanel(path="a.pkl", fig=fig, ax=ax, menu_kwargs={"labels": ["c1"], "y_data_list": [[3, 4]]})
    # Quit pane/spine menu immediately.
    answers = iter(["q"])

    def _fake_input(prompt="", **_k):
        try:
            return next(answers)
        except StopIteration:
            return "q"

    XB.safe_input = _fake_input  # type: ignore[attr-defined]
    try:
        run_xy_batch_spine_menu(
            p,
            [p],
            push_undo=lambda: None,
            draw_all=lambda: None,
        )
    finally:
        XB.safe_input = real_safe_input  # type: ignore[attr-defined]
    assert isinstance(getattr(fig, "_bp_wasd_state", None), dict)
    plt.close(fig)


def test_operando_sync_strips_ions_abs():
    """Regression: cross-panel sync must not copy absolute ions curves."""
    from batplot.plot_modes.batch_session.operando_batch_helpers import sync_style_from_ref
    from batplot.plot_modes.batch_session.load import OperandoPanel

    captured = []

    def _capture(panel):
        return {
            "kind": "operando_ec_style_geom",
            "ec": {"y_mode": "ions", "ion_params": {"mass_mg": 1.0}, "ions_abs": [1.0, 2.0, 3.0]},
        }

    def _apply(panel, cfg):
        captured.append(cfg)
        assert "ions_abs" not in (cfg.get("ec") or {})
        return True

    fig, ax = plt.subplots()
    Z = np.zeros((5, 5))
    im = ax.imshow(Z)
    cbar = fig.colorbar(im, ax=ax)
    ec = fig.add_axes((0.8, 0.1, 0.15, 0.8))
    p1 = OperandoPanel("a.pkl", fig, ax, im, cbar, ec)
    p2 = OperandoPanel("b.pkl", fig, ax, im, cbar, ec)
    sync_style_from_ref(p1, [p1, p2], capture_panel=_capture, apply_cfg=_apply)
    assert len(captured) == 1
    plt.close(fig)


def test_cpc_style_apply_keeps_independent_ticks_and_labels():
    """Regression: WASD ticks-on/labels-off must survive style apply / batch sync."""
    from batplot.plot_modes.cpc.interactive import _apply_style, _style_snapshot
    from batplot.plot_modes.common.spines import apply_wasd_spines, apply_wasd_tick_params

    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc_c = ax.scatter([1], [1])
    sc_d = ax.scatter([1], [0.9])
    sc_e = ax2.scatter([1], [95])
    wasd = {
        "top": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": False, "title": True},
        "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "right": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
    }
    fig._cpc_wasd_state = wasd
    apply_wasd_spines(ax, wasd, sides=("top", "bottom", "left"))
    apply_wasd_tick_params(ax, wasd, y_sides=("left",), y_mode="left")
    cfg = _style_snapshot(fig, ax, ax2, sc_c, sc_d, sc_e, None)

    fig2, axb = plt.subplots()
    ax2b = axb.twinx()
    sc_c2 = axb.scatter([1], [1])
    sc_d2 = axb.scatter([1], [0.9])
    sc_e2 = ax2b.scatter([1], [95])
    _apply_style(fig2, axb, ax2b, sc_c2, sc_d2, sc_e2, cfg, None)
    fig2.canvas.draw()
    xt = axb.xaxis.get_major_ticks()
    assert xt, "expected x ticks"
    assert xt[0].tick1line.get_visible() is True
    assert xt[0].label1.get_visible() is False
    plt.close(fig)
    plt.close(fig2)


def test_xy_batch_range_sets_limits_without_cropping_peer_data():
    """Regression: batch x/y must sync limits on all panels, not crop only ref data."""
    from batplot.plot_modes.batch_session.menu_xy import _run_ref_range_menu
    from batplot.plot_modes.batch_session.common import SyncUndoStacks
    import batplot.plot_modes.batch_session.batch_menu_helpers as BMH
    from batplot.plot_modes.batch_session.batch_menu_helpers import prompt_axis_limits as real_prompt

    x = np.linspace(0.0, 10.0, 101)
    y = np.sin(x)
    fig1, ax1 = plt.subplots()
    fig2, ax2 = plt.subplots()
    ax1.plot(x, y)
    ax2.plot(x.copy(), y.copy())
    p1 = XyPanel("a.pkl", fig1, ax1, {"x_data_list": [x], "y_data_list": [y], "labels": ["c1"]})
    p2 = XyPanel("b.pkl", fig2, ax2, {"x_data_list": [x.copy()], "y_data_list": [y.copy()], "labels": ["c1"]})
    panels = [p1, p2]
    undo = SyncUndoStacks(2)
    undo.push_all([{"k": 0}, {"k": 0}])

    calls = {"n": 0}

    def _fake_prompt(*, label, get_current=None, panels=None, get_panel_limits=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return (2.0, 8.0)
        return None

    BMH.prompt_axis_limits = _fake_prompt  # type: ignore[assignment]
    try:
        _run_ref_range_menu(p1, panels, undo, "x")
    finally:
        BMH.prompt_axis_limits = real_prompt  # type: ignore[assignment]

    assert ax1.get_xlim() == pytest.approx((2.0, 8.0))
    assert ax2.get_xlim() == pytest.approx((2.0, 8.0))
    assert len(ax1.lines[0].get_xdata()) == 101
    assert len(ax2.lines[0].get_xdata()) == 101
    plt.close(fig1)
    plt.close(fig2)


def test_ec_file_visibility_reshow_survives_style_apply():
    """Regression: hide then show must not leave peer lines stuck invisible."""
    from batplot.plot_modes.electrochem.style import _get_style_snapshot
    from batplot.plot_modes.electrochem.style_apply import apply_ec_style_config

    fig, ax = plt.subplots()
    (c1,) = ax.plot([0, 1], [0, 1])
    (d1,) = ax.plot([0, 1], [1, 0])
    (c2,) = ax.plot([0, 1], [0.5, 1.5])
    (d2,) = ax.plot([0, 1], [1.5, 0.5])
    file_data = [
        {"filename": "f1", "visible": True, "cycle_lines": {1: {"charge": c1, "discharge": d1}}},
        {"filename": "f2", "visible": True, "cycle_lines": {1: {"charge": c2, "discharge": d2}}},
    ]
    # Hide file 2, capture, apply to "stuck hidden" peer state, then re-show.
    file_data[1]["visible"] = False
    c2.set_visible(False)
    d2.set_visible(False)
    cfg_hidden = _get_style_snapshot(fig, ax, file_data[0]["cycle_lines"], {}, file_data)

    file_data[1]["visible"] = True
    c2.set_visible(True)
    d2.set_visible(True)
    cfg_shown = _get_style_snapshot(fig, ax, file_data[0]["cycle_lines"], {}, file_data)

    # Simulate peer that was previously synced to hidden.
    file_data[1]["visible"] = False
    c2.set_visible(False)
    d2.set_visible(False)
    assert apply_ec_style_config(
        cfg_shown,
        fig=fig,
        ax=ax,
        cycle_lines=file_data[0]["cycle_lines"],
        file_data=file_data,
        tick_state={},
        is_multi_file=True,
        silent=True,
    )
    assert file_data[1]["visible"] is True
    assert c2.get_visible() is True
    assert d2.get_visible() is True

    assert apply_ec_style_config(
        cfg_hidden,
        fig=fig,
        ax=ax,
        cycle_lines=file_data[0]["cycle_lines"],
        file_data=file_data,
        tick_state={},
        is_multi_file=True,
        silent=True,
    )
    assert file_data[1]["visible"] is False
    assert c2.get_visible() is False
    assert d2.get_visible() is False
    plt.close(fig)


def test_ec_batch_visibility_menu_toggles_and_quits():
    from batplot.plot_modes.batch_session.ec_batch_helpers import (
        ec_print_file_list_factory,
        ec_run_file_visibility_menu,
    )

    fig, ax = plt.subplots()
    (c,) = ax.plot([0, 1], [0, 1])
    (d,) = ax.plot([0, 1], [1, 0])
    file_data = [
        {"filename": "a", "visible": True, "cycle_lines": {1: {"charge": c, "discharge": d}}},
        {"filename": "b", "visible": True, "cycle_lines": {1: {"charge": c, "discharge": d}}},
    ]
    answers = iter(["2", "q"])
    ec_run_file_visibility_menu(
        file_data=file_data,
        is_multi_file=True,
        print_file_list=ec_print_file_list_factory(True),
        rebuild_legend=lambda *_a, **_k: None,
        fig=fig,
        ax=ax,
        push_state=lambda *_a, **_k: None,
        safe_input=lambda _p="": next(answers),
        colorize_prompt=lambda s: s,
    )
    assert file_data[1]["visible"] is False
    plt.close(fig)


def test_cpc_batch_visibility_menu_toggles_range():
    from batplot.plot_modes.batch_session.cpc_batch_helpers import (
        cpc_print_file_list_factory,
        cpc_run_file_visibility_menu,
    )

    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    files = []
    for name in ("a", "b", "c"):
        files.append(
            {
                "filename": name,
                "visible": True,
                "sc_charge": ax.scatter([1], [1]),
                "sc_discharge": ax.scatter([1], [0.9]),
                "sc_eff": ax2.scatter([1], [95]),
            }
        )
    answers = iter(["1-2", "q"])
    cpc_run_file_visibility_menu(
        file_data=files,
        is_multi_file=True,
        print_file_list=cpc_print_file_list_factory(True),
        rebuild_legend=lambda *_a, **_k: None,
        fig=fig,
        ax=ax,
        ax2=ax2,
        push_state=lambda *_a, **_k: None,
        safe_input=lambda _p="": next(answers),
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
    )
    assert files[0]["visible"] is False
    assert files[1]["visible"] is False
    assert files[2]["visible"] is True
    plt.close(fig)

"""Batch dQ/dV key isolation: line (ec_gc subtype) + 2D contour.

Contour ``oc``/``or``/``t`` peer-clim locks live in
``test_batch_scoped_sync_modes.py`` (same operando helpers).
"""

from __future__ import annotations

import inspect

import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.colors import to_hex

from batplot.plot_modes.batch_session.common import SyncUndoStacks
from batplot.plot_modes.batch_session.dqdv_2d_batch_helpers import (
    first_panel_with_dqdv_source,
)
from batplot.plot_modes.batch_session.ec_batch_helpers import (
    apply_ec_cycles_colors_only,
    apply_ec_line_chrome_only,
    apply_ec_smooth_only,
    ec_panel_is_dqdv,
    ensure_ec_fig_state,
)
from batplot.plot_modes.batch_session.load import EcPanel, OperandoPanel
from batplot.plot_modes.batch_session.menu_dqdv_2d import (
    _print_dqdv_2d_batch_menu,
    _run_batch_ox_potential_window,
)
from batplot.plot_modes.batch_session.menu_ec import (
    _capture_panel as ec_capture,
    _print_ec_batch_menu,
)
from batplot.plot_modes.batch_session.operando_batch_helpers import sync_style_from_ref
import batplot.plot_modes.batch_session.menu_dqdv_2d as menu_dqdv_2d
import batplot.plot_modes.batch_session.menu_ec as menu_ec


def _strip_ansi(text: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _two_dqdv_line_panels():
    fig1, ax1 = plt.subplots()
    fig2, ax2 = plt.subplots()
    c1 = ax1.plot([0, 1], [0, 1], color="#111111", lw=1.0)[0]
    d1 = ax1.plot([0, 1], [1, 0], color="#222222", lw=1.0)[0]
    c2 = ax2.plot([0, 1], [0, 1], color="#333333", lw=3.0)[0]
    d2 = ax2.plot([0, 1], [1, 0], color="#444444", lw=3.0)[0]
    for ax in (ax1, ax2):
        ax._is_dqdv_mode = True
        ax.set_xlabel("Potential (V)")
        ax._stored_xlabel = "Potential (V)"
        ax.set_ylabel("dQ/dV")
        ax._stored_ylabel = "dQ/dV"
    ax1.set_xlim(0, 10)
    ax2.set_xlim(0, 100)
    fig1._ec_curve_linewidth = 1.0
    fig2._ec_curve_linewidth = 3.0
    fig1._dqdv_smooth_settings = {"method": "diffcap", "window": 9, "poly": 3}
    fig2._dqdv_smooth_settings = {"method": "diffcap", "window": 5, "poly": 2}
    p1 = EcPanel(
        path="dqdv_a.pkl",
        fig=fig1,
        ax=ax1,
        cycle_lines={1: {"charge": c1, "discharge": d1}},
        file_data=None,
    )
    p2 = EcPanel(
        path="dqdv_b.pkl",
        fig=fig2,
        ax=ax2,
        cycle_lines={1: {"charge": c2, "discharge": d2}},
        file_data=None,
    )
    return p1, p2


def _two_contour_panels():
    panels = []
    for i, (cmap, clim) in enumerate((("viridis", (0.0, 1.0)), ("plasma", (2.0, 4.0)))):
        fig, ax = plt.subplots()
        data = np.linspace(0, 1, 16).reshape(4, 4) * (i + 1)
        im = ax.imshow(data, origin="lower", cmap=cmap)
        im.set_clim(*clim)
        im._operando_cmap_name = cmap
        cbar = fig.colorbar(im, ax=ax)
        fig._is_dqdv_2d_contour = True
        fig._dqdv_2d_v_lo = 2.0 + i
        fig._dqdv_2d_v_hi = 3.5 + i
        ax.set_xlabel(f"X{i}")
        ax.set_ylabel(f"Y{i}")
        ax.set_ylim(0, 10 + i)
        panels.append(
            OperandoPanel(
                path=f"c{i}.pkl",
                fig=fig,
                ax=ax,
                im=im,
                cbar=cbar,
                ec_ax=None,
            )
        )
    return panels


def test_batch_dqdv_line_menu_lists_sm_hides_overview(capsys):
    p1, p2 = _two_dqdv_line_panels()
    try:
        assert ec_panel_is_dqdv(p1)
        _print_ec_batch_menu([p1, p2])
        out = _strip_ansi(capsys.readouterr().out)
        assert "smooth" in out.lower()
        assert "overview" not in out.lower()
        assert "dQ/dV" in out
        for token in (
            "font",
            "line style",
            "cycles/colors",
            "x range",
            "y range",
            "export style",
            "undo",
        ):
            assert token in out, f"missing {token!r}"
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_dqdv_ensure_fig_state_disables_overview():
    p1, _p2 = _two_dqdv_line_panels()
    try:
        fd, _cl, multi = ([{"cycle_lines": p1.cycle_lines, "visible": True}], p1.cycle_lines, False)
        ensure_ec_fig_state(p1, fd, multi, is_dqdv=True)
        assert getattr(p1.fig, "_ec_overview_enabled", True) is False
    finally:
        plt.close(p1.fig)
        plt.close(_p2.fig)


def test_batch_dqdv_c_keeps_peer_smooth_and_linewidth():
    p1, p2 = _two_dqdv_line_panels()
    try:
        p1.cycle_lines[1]["charge"].set_color("#ff0000")
        p2.cycle_lines[1]["charge"].set_color("#00aa00")
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=ec_capture, apply_cfg=apply_ec_cycles_colors_only
        )
        assert to_hex(p2.cycle_lines[1]["charge"].get_color()) == "#ff0000"
        assert p2.cycle_lines[1]["charge"].get_linewidth() == pytest.approx(3.0)
        assert getattr(p2.fig, "_dqdv_smooth_settings", {}) == {
            "method": "diffcap",
            "window": 5,
            "poly": 2,
        }
        assert p2.ax.get_xlim() == pytest.approx((0, 100))
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_dqdv_l_keeps_peer_smooth_and_colors():
    p1, p2 = _two_dqdv_line_panels()
    try:
        p1.cycle_lines[1]["charge"].set_linewidth(2.5)
        p1.fig._ec_curve_linewidth = 2.5
        p2.cycle_lines[1]["charge"].set_color("#00aa00")
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=ec_capture, apply_cfg=apply_ec_line_chrome_only
        )
        assert p2.cycle_lines[1]["charge"].get_linewidth() == pytest.approx(2.5)
        assert to_hex(p2.cycle_lines[1]["charge"].get_color()) == "#00aa00"
        assert getattr(p2.fig, "_dqdv_smooth_settings", {})["window"] == 5
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_dqdv_sm_syncs_settings_not_colors_or_limits():
    p1, p2 = _two_dqdv_line_panels()
    try:
        p1.fig._dqdv_smooth_settings = {"method": "diffcap", "window": 15, "poly": 3}
        p2.cycle_lines[1]["charge"].set_color("#00aa00")
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=ec_capture, apply_cfg=apply_ec_smooth_only
        )
        assert getattr(p2.fig, "_dqdv_smooth_settings", {})["window"] == 15
        assert to_hex(p2.cycle_lines[1]["charge"].get_color()) == "#00aa00"
        assert p2.cycle_lines[1]["charge"].get_linewidth() == pytest.approx(3.0)
        assert p2.ax.get_xlim() == pytest.approx((0, 100))
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_dqdv_line_menu_wiring_uses_is_dqdv_and_smooth():
    src = inspect.getsource(menu_ec.run_ec_batch_menu)
    assert "is_dqdv=is_dqdv" in src
    assert "_apply_stored_smooth_settings" in src
    assert "apply_ec_smooth_only" in src
    assert "run_dqdv_smoothing_menu" in src
    # GC overview must be gated for dQdV.
    assert 'if is_dqdv:' in src
    assert "overview is GC-only" in src


def test_batch_contour_menu_lists_keys(capsys):
    panels = _two_contour_panels()
    try:
        _print_dqdv_2d_batch_menu(panels)
        out = _strip_ansi(capsys.readouterr().out)
        for token in (
            "colormap",
            "colorbar",
            "spines/ticks",
            "spine colors",
            "line widths",
            "font",
            "size",
            "reverse Y",
            "potential window",
            "Y range",
            "intensity",
            "rename",
            "export style",
            "undo",
        ):
            assert token in out, f"missing {token!r}"
    finally:
        for p in panels:
            plt.close(p.fig)


def test_batch_contour_ox_uses_first_panel_with_source(monkeypatch):
    p1, p2 = _two_contour_panels()
    # Ref has no source; peer does.
    p1.fig._dqdv_2d_file_data = None
    p2.fig._dqdv_2d_file_data = [{"ok": True}]
    assert first_panel_with_dqdv_source([p1, p2]) is p2

    edited = {"panel": None}

    def _fake_menu(fig, ax, im, cbar, snapshot):
        edited["panel"] = fig
        fig._dqdv_2d_v_lo = 1.1
        fig._dqdv_2d_v_hi = 2.2

    monkeypatch.setattr(
        "batplot.plot_modes.operando.interactive._dqdv_2d_potential_window_menu",
        _fake_menu,
    )
    monkeypatch.setattr(
        menu_dqdv_2d,
        "sync_potential_window_all",
        lambda panels, v_lo, v_hi: 1,
    )
    undo = SyncUndoStacks(2)
    try:
        _run_batch_ox_potential_window(p1, [p1, p2], undo)
        assert edited["panel"] is p2.fig
        assert (p2.fig._dqdv_2d_v_lo, p2.fig._dqdv_2d_v_hi) == pytest.approx((1.1, 2.2))
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_contour_ox_wiring_avoids_full_style_sync():
    src = inspect.getsource(menu_dqdv_2d._run_batch_ox_potential_window)
    assert "first_panel_with_dqdv_source" in src
    assert "sync_potential_window_all" in src
    assert "edit_ref_then_sync" not in src
    assert "do not full-style-sync" in src.lower() or "hitchhike" in src.lower()


def test_batch_gc_menu_still_lists_overview_not_smooth(capsys):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax._is_dqdv_mode = False
    ax.set_ylabel("Capacity")
    p = EcPanel(path="gc.pkl", fig=fig, ax=ax, cycle_lines={}, file_data=None)
    try:
        _print_ec_batch_menu([p])
        out = _strip_ansi(capsys.readouterr().out)
        assert "overview" in out.lower()
        assert "smooth" not in out.lower()
    finally:
        plt.close(fig)

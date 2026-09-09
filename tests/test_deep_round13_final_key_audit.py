"""Round 13 final key audit gates: operando store sync, EC ps strip, batch t widths."""

from __future__ import annotations

import os

import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot.plot_modes.batch_session.ec_batch_helpers import (
    apply_ec_line_chrome_only,
    apply_ec_wasd_chrome_only,
)
from batplot.plot_modes.batch_session.load import EcPanel, OperandoPanel
from batplot.plot_modes.batch_session.operando_batch_helpers import (
    apply_operando_ec_labels_only,
    apply_operando_labels_only,
)
from batplot.plot_modes.electrochem.actions import _build_ec_style_export_config
from batplot.plot_modes.electrochem.style import _get_style_snapshot
from batplot.utils import get_organized_path


def test_operando_batch_or_syncs_stored_titles():
    fig, ax = plt.subplots()
    ax._stored_xlabel = "StaleX"
    ax._stored_ylabel = "StaleY"
    panel = OperandoPanel(
        path="a.pkl",
        fig=fig,
        ax=ax,
        im=None,
        cbar=None,
        ec_ax=None,
    )
    ok = apply_operando_labels_only(
        panel,
        {"operando": {"custom_labels": {"x": "NewX", "y": "NewY"}}},
    )
    assert ok is True
    assert ax.get_xlabel() == "NewX"
    assert ax._stored_xlabel == "NewX"
    assert ax.get_ylabel() == "NewY"
    assert ax._stored_ylabel == "NewY"
    plt.close(fig)


def test_operando_batch_er_syncs_ec_stored_titles():
    fig, ax = plt.subplots()
    ec_ax = fig.add_axes([0.1, 0.1, 0.3, 0.8])
    ec_ax._stored_xlabel = "OldPot"
    ec_ax._stored_ylabel = "OldTime"
    panel = OperandoPanel(
        path="a.pkl",
        fig=fig,
        ax=ax,
        im=None,
        cbar=None,
        ec_ax=ec_ax,
    )
    ok = apply_operando_ec_labels_only(
        panel,
        {"ec": {"custom_labels": {"x": "Potential", "y_time": "Time (h)"}}},
    )
    assert ok is True
    assert ec_ax.get_xlabel() == "Potential"
    assert ec_ax._stored_xlabel == "Potential"
    assert ec_ax.get_ylabel() == "Time (h)"
    assert ec_ax._stored_ylabel == "Time (h)"
    plt.close(fig)


def test_ec_style_only_export_strips_xaxis_dual():
    from types import SimpleNamespace

    fig, ax = plt.subplots()
    (ln,) = ax.plot([0, 1], [3, 4])
    ln._orig_xdata_gc = np.asarray([0.0, 1.0], float)
    fig._xaxis_mode = "dual"
    fig._xaxis_c_theoretical = 100.0
    cycle_lines = {1: {"charge": ln, "discharge": None}}
    snap = _get_style_snapshot(fig, ax, cycle_lines, {})
    assert "xaxis_dual" in snap

    ctx = SimpleNamespace(
        fig=fig,
        ax=ax,
        cycle_lines=cycle_lines,
        tick_state={},
        file_data=None,
        is_multi_file=False,
        get_style_snapshot=lambda *a, **k: dict(snap),
        get_geometry_snapshot=lambda *a, **k: {"xlim": [0, 1], "ylim": [3, 4]},
    )

    cfg_ps, ext = _build_ec_style_export_config(ctx, "ps")
    assert ext == ".bps"
    assert cfg_ps["kind"] == "ec_style"
    assert "xaxis_dual" not in cfg_ps

    cfg_psg, extg = _build_ec_style_export_config(ctx, "psg")
    assert extg == ".bpsg"
    assert cfg_psg["kind"] == "ec_style_geom"
    assert "xaxis_dual" in cfg_psg
    plt.close(fig)


def test_ec_batch_t_does_not_hitchhike_l_widths():
    fig1, ax1 = plt.subplots()
    fig2, ax2 = plt.subplots()
    ln1 = ax1.plot([0, 1], [0, 1])[0]
    ln2 = ax2.plot([0, 1], [0, 1])[0]
    ax1.spines["bottom"].set_linewidth(3.5)
    ax2.spines["bottom"].set_linewidth(0.8)
    p1 = EcPanel(path="a.pkl", fig=fig1, ax=ax1, cycle_lines={1: {"charge": ln1, "discharge": None}}, file_data=None)
    p2 = EcPanel(path="b.pkl", fig=fig2, ax=ax2, cycle_lines={1: {"charge": ln2, "discharge": None}}, file_data=None)
    from batplot.plot_modes.batch_session.menu_ec import _capture_panel

    ref_cfg = _capture_panel(p1)
    apply_ec_wasd_chrome_only(p2, ref_cfg)
    assert ax2.spines["bottom"].get_linewidth() == pytest.approx(0.8)
    # ``l`` still syncs widths.
    apply_ec_line_chrome_only(p2, ref_cfg)
    assert ax2.spines["bottom"].get_linewidth() == pytest.approx(3.5)
    plt.close(fig1)
    plt.close(fig2)


def test_get_organized_path_expanduser(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    out = get_organized_path("~/out.svg", "figure")
    assert "~" not in out
    assert out.endswith("out.svg")
    assert str(home) in out or os.path.expanduser("~") in out

"""Hard gates for batch-mode geometry keys across p / i / s / b."""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot.plot_modes.batch_session.batch_panel_state import (
    _export_cpc_style,
    _export_ec_style,
)
from batplot.plot_modes.batch_session.common import SyncUndoStacks
from batplot.plot_modes.batch_session.load import CpcPanel, EcPanel, OperandoPanel
from batplot.plot_modes.batch_session.menu_dqdv_2d import _run_batch_ox_potential_window
from batplot.plot_modes.operando import style as OS
from batplot.plot_modes.operando.style_apply import apply_operando_ec_style_config


def _make_ec_panel(path="a.pkl"):
    fig, ax = plt.subplots(figsize=(8.0, 6.0))
    (ln,) = ax.plot([0, 1], [3.0, 3.5], color="C0")
    ax.set_position([0.15, 0.15, 0.7, 0.7])
    return EcPanel(
        path=path,
        fig=fig,
        ax=ax,
        cycle_lines={1: {"charge": ln, "discharge": None}},
        file_data=None,
    )


def _make_cpc_panel(path="a.pkl"):
    fig, ax = plt.subplots(figsize=(8.0, 6.0))
    ax2 = ax.twinx()
    sc_c = ax.scatter([1, 2], [100, 110])
    sc_d = ax.scatter([1, 2], [90, 95])
    sc_e = ax2.scatter([1, 2], [90, 92])
    ax.set_position([0.15, 0.15, 0.65, 0.7])
    return CpcPanel(
        path=path,
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
        file_data=None,
    )


def test_batch_panel_state_ec_ps_strips_figure_geometry_keys(tmp_path):
    panel = _make_ec_panel()
    try:
        out = tmp_path / "ec_ps.bps"
        _export_ec_style(panel, str(out), "ps")
        cfg = json.loads(out.read_text(encoding="utf-8"))
        assert cfg["kind"] == "ec_style"
        assert "geometry" not in cfg
        fig_block = cfg.get("figure") or {}
        for key in ("canvas_size", "frame_size", "axes_fraction", "size"):
            assert key not in fig_block
    finally:
        plt.close(panel.fig)


def test_batch_panel_state_cpc_ps_strips_figure_geometry_keys(tmp_path):
    panel = _make_cpc_panel()
    try:
        out = tmp_path / "cpc_ps.bps"
        _export_cpc_style(panel, str(out), "ps")
        cfg = json.loads(out.read_text(encoding="utf-8"))
        assert cfg["kind"] == "cpc_style"
        assert "geometry" not in cfg
        fig_block = cfg.get("figure") or {}
        for key in ("canvas_size", "frame_size", "axes_fraction", "size"):
            assert key not in fig_block
    finally:
        plt.close(panel.fig)


def test_dqdv_ps_omits_potential_window_attrs():
    fig, ax = plt.subplots()
    im = ax.imshow(np.zeros((4, 4)), origin="lower")
    cbar = fig.colorbar(im, ax=ax)
    fig._is_dqdv_2d_contour = True
    fig._dqdv_2d_v_lo = 2.0
    fig._dqdv_2d_v_hi = 4.0
    fig._dqdv_2d_row_labels = ["a", "b"]
    fig._dqdv_2d_zlabel = "dQ/dV"
    try:
        cfg_ps, _ = OS.build_operando_ec_style_config_v2(fig, ax, im, cbar, None, "ps")
        assert "dqdv_2d" in cfg_ps
        assert "v_lo" not in cfg_ps["dqdv_2d"]
        assert "v_hi" not in cfg_ps["dqdv_2d"]
        assert cfg_ps["dqdv_2d"]["zlabel"] == "dQ/dV"

        cfg_psg, _ = OS.build_operando_ec_style_config_v2(fig, ax, im, cbar, None, "psg")
        assert cfg_psg["dqdv_2d"]["v_lo"] == pytest.approx(2.0)
        assert cfg_psg["dqdv_2d"]["v_hi"] == pytest.approx(4.0)
    finally:
        plt.close(fig)


def test_dqdv_style_only_import_does_not_overwrite_live_window():
    fig, ax = plt.subplots()
    im = ax.imshow(np.zeros((4, 4)), origin="lower")
    cbar = fig.colorbar(im, ax=ax)
    fig._is_dqdv_2d_contour = True
    fig._dqdv_2d_v_lo = 1.0
    fig._dqdv_2d_v_hi = 2.0
    fig._dqdv_2d_row_labels = ["x"]
    fig._dqdv_2d_zlabel = "old"
    cfg = {
        "kind": "operando_ec_style",
        "version": 2,
        "operando": {"cmap": "viridis"},
        "dqdv_2d": {
            "v_lo": 9.0,
            "v_hi": 10.0,
            "row_labels": ["a", "b"],
            "zlabel": "newZ",
            "axis_mapping_version": 2,
        },
    }
    try:
        assert apply_operando_ec_style_config(
            cfg, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=None, silent=True
        )
        # Style-only must keep live window (map geometry).
        assert float(fig._dqdv_2d_v_lo) == pytest.approx(1.0)
        assert float(fig._dqdv_2d_v_hi) == pytest.approx(2.0)
        # Labels still sync.
        assert fig._dqdv_2d_zlabel == "newZ"
        assert fig._dqdv_2d_row_labels == ["a", "b"]
    finally:
        plt.close(fig)


def test_dqdv_batch_ox_noop_does_not_push_undo(monkeypatch):
    fig, ax = plt.subplots()
    im = ax.imshow(np.zeros((4, 4)), origin="lower")
    cbar = fig.colorbar(im, ax=ax)
    fig._is_dqdv_2d_contour = True
    fig._dqdv_2d_v_lo = 2.0
    fig._dqdv_2d_v_hi = 3.5
    fig._dqdv_2d_file_data = [{"ok": True}]
    panel = OperandoPanel(path="a.pkl", fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=None)
    undo = SyncUndoStacks(1)
    undo.push_all([{"baseline": True}])
    depth_before = len(undo._stacks[0])

    def _noop_menu(*_a, **_k):
        return None

    monkeypatch.setattr(
        "batplot.plot_modes.operando.interactive._dqdv_2d_potential_window_menu",
        _noop_menu,
    )
    try:
        _run_batch_ox_potential_window(panel, [panel], undo)
        assert len(undo._stacks[0]) == depth_before
    finally:
        plt.close(fig)


def test_ec_batch_psg_export_keeps_geometry_and_canvas(tmp_path):
    panel = _make_ec_panel()
    try:
        out = tmp_path / "ec_psg.bpsg"
        _export_ec_style(panel, str(out), "psg")
        cfg = json.loads(out.read_text(encoding="utf-8"))
        assert cfg["kind"] == "ec_style_geom"
        assert "geometry" in cfg
        assert "canvas_size" in (cfg.get("figure") or {})
    finally:
        plt.close(panel.fig)

"""Batch-wide sync and p/i/s/b contract tests across EC/CPC and style sync."""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest
from matplotlib.ticker import MultipleLocator

from batplot.plot_modes.batch_session.batch_panel_state import verify_panel_pisb_roundtrip
from batplot.plot_modes.batch_session.load import CpcPanel, EcPanel
from batplot.plot_modes.batch_session.menu_cpc import (
    _apply_cpc_style,
    _capture_panel as cpc_capture,
    _restore_panel as cpc_restore,
    _toggle_efficiency_all,
)
from batplot.plot_modes.batch_session.menu_ec import _apply_cfg, _capture_panel as ec_capture
from batplot.plot_modes.batch_session.operando_batch_helpers import sync_style_from_ref


def test_ec_pisb_roundtrip():
    fig, ax = plt.subplots()
    (c,) = ax.plot([0.0, 1.0], [0.0, 1.0])
    p = EcPanel(
        path="a.pkl",
        fig=fig,
        ax=ax,
        cycle_lines={1: {"charge": c, "discharge": None}},
        file_data=None,
    )
    try:
        verify_panel_pisb_roundtrip(p, "ec_gc", sub="ps")
        verify_panel_pisb_roundtrip(p, "ec_gc", sub="psg")
    finally:
        plt.close(fig)


def test_cpc_pisb_roundtrip():
    from test_cpc_roundtrip import _build_cpc_figure

    fig, ax, ax2, sc_c, sc_d, sc_e, _cyc = _build_cpc_figure()
    p = CpcPanel(
        path="cpc.pkl",
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
    )
    try:
        verify_panel_pisb_roundtrip(p, "cpc", sub="ps")
        verify_panel_pisb_roundtrip(p, "cpc", sub="psg")
    finally:
        plt.close(fig)


def test_cpc_efficiency_toggle_undo_restores_ax2_visibility():
    from test_cpc_roundtrip import _build_cpc_figure

    fig1, ax1, ax2_1, sc_c1, sc_d1, sc_e1, _ = _build_cpc_figure()
    fig2, ax2, ax2_2, sc_c2, sc_d2, sc_e2, _ = _build_cpc_figure()
    p1 = CpcPanel(
        path="a.pkl", fig=fig1, ax=ax1, ax2=ax2_1,
        sc_charge=sc_c1, sc_discharge=sc_d1, sc_eff=sc_e1,
    )
    p2 = CpcPanel(
        path="b.pkl", fig=fig2, ax=ax2, ax2=ax2_2,
        sc_charge=sc_c2, sc_discharge=sc_d2, sc_eff=sc_e2,
    )
    panels = [p1, p2]
    snap = [cpc_capture(p) for p in panels]
    assert ax2_1.get_visible() is True
    assert ax2_2.get_visible() is True
    _toggle_efficiency_all(panels)
    assert ax2_1.get_visible() is False
    assert ax2_2.get_visible() is False
    cpc_restore(panels[0], snap[0])
    cpc_restore(panels[1], snap[1])
    assert ax2_1.get_visible() is True
    assert ax2_2.get_visible() is True
    plt.close(fig1)
    plt.close(fig2)


def test_style_sync_default_preserves_peer_axis_limits():
    fig1, ax1 = plt.subplots()
    fig2, ax2 = plt.subplots()
    ln1 = ax1.plot([0, 10], [0, 1], color="C0")[0]
    ln2 = ax2.plot([0, 100], [0, 1], color="C0")[0]
    ax1.set_xlim(0, 10)
    ax2.set_xlim(0, 100)
    p1 = EcPanel(
        path="a.pkl", fig=fig1, ax=ax1,
        cycle_lines={1: {"charge": ln1, "discharge": None}}, file_data=None,
    )
    p2 = EcPanel(
        path="b.pkl", fig=fig2, ax=ax2,
        cycle_lines={1: {"charge": ln2, "discharge": None}}, file_data=None,
    )
    ax1.yaxis.set_major_locator(MultipleLocator(2.0))
    try:
        sync_style_from_ref(p1, [p1, p2], capture_panel=ec_capture, apply_cfg=_apply_cfg)
        assert isinstance(ax2.yaxis.get_major_locator(), MultipleLocator)
        assert float(ax2.yaxis.get_major_locator()._edge.step) == pytest.approx(2.0)
        assert ax2.get_xlim() == pytest.approx((0, 100))
    finally:
        plt.close(fig1)
        plt.close(fig2)


def test_cpc_style_sync_preserves_peer_xlim():
    from test_cpc_roundtrip import _build_cpc_figure

    fig1, ax1, ax2a, sc_c1, sc_d1, sc_e1, _ = _build_cpc_figure()
    fig2, ax2, ax2b, sc_c2, sc_d2, sc_e2, _ = _build_cpc_figure()
    ax1.set_xlim(1, 5)
    ax2.set_xlim(10, 50)
    p1 = CpcPanel(
        path="a.pkl", fig=fig1, ax=ax1, ax2=ax2a,
        sc_charge=sc_c1, sc_discharge=sc_d1, sc_eff=sc_e1,
    )
    p2 = CpcPanel(
        path="b.pkl", fig=fig2, ax=ax2, ax2=ax2b,
        sc_charge=sc_c2, sc_discharge=sc_d2, sc_eff=sc_e2,
    )
    try:
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=cpc_capture, apply_cfg=_apply_cpc_style
        )
        assert ax2.get_xlim() == pytest.approx((10, 50))
    finally:
        plt.close(fig1)
        plt.close(fig2)

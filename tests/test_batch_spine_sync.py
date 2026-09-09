"""Tests for batch spine/tick sync applying to all panels."""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest
from matplotlib.ticker import MultipleLocator

from batplot.plot_modes.batch_session.ec_batch_helpers import (
    apply_ec_wasd_chrome_only,
    ec_tick_state_from_fig,
)
from batplot.plot_modes.batch_session.load import EcPanel
from batplot.plot_modes.batch_session.menu_ec import _capture_panel
from batplot.plot_modes.batch_session.operando_batch_helpers import sync_style_from_ref
from matplotlib.colors import to_hex


def test_ec_batch_spine_tick_spacing_syncs_without_overwriting_limits():
    fig1, ax1 = plt.subplots()
    fig2, ax2 = plt.subplots()
    ln1 = ax1.plot([0, 10], [0, 1], color="#ff0000")[0]
    ln2 = ax2.plot([0, 100], [0, 1], color="#00aa00")[0]
    ax1.set_xlim(0, 10)
    ax1.set_ylim(0, 1)
    ax2.set_xlim(0, 100)
    ax2.set_ylim(0, 10)
    p1 = EcPanel(
        path="a.pkl",
        fig=fig1,
        ax=ax1,
        cycle_lines={1: {"charge": ln1, "discharge": None}},
        file_data=None,
    )
    p2 = EcPanel(
        path="b.pkl",
        fig=fig2,
        ax=ax2,
        cycle_lines={1: {"charge": ln2, "discharge": None}},
        file_data=None,
    )
    ax1.yaxis.set_major_locator(MultipleLocator(1.0))
    p1.fig._dqdv_smooth_settings = {"window": 11, "polyorder": 3}
    p2.fig._dqdv_smooth_settings = {"window": 5, "polyorder": 2}
    try:
        sync_style_from_ref(
            p1,
            [p1, p2],
            capture_panel=_capture_panel,
            apply_cfg=apply_ec_wasd_chrome_only,
            include_geometry=False,
        )
        assert isinstance(ax2.yaxis.get_major_locator(), MultipleLocator)
        assert float(ax2.yaxis.get_major_locator()._edge.step) == pytest.approx(1.0)
        assert ax2.get_xlim() == pytest.approx((0, 100))
        assert ax2.get_ylim() == pytest.approx((0, 10))
        # WASD sync must not clobber peer colors / dQ/dV smooth.
        assert to_hex(ln2.get_color()) == "#00aa00"
        assert getattr(p2.fig, "_dqdv_smooth_settings", {}) == {"window": 5, "polyorder": 2}
    finally:
        plt.close(fig1)
        plt.close(fig2)


def test_ec_capture_includes_tick_spacing_for_pisb():
    fig, ax = plt.subplots()
    ln = ax.plot([0, 1], [0, 1])[0]
    ax.yaxis.set_major_locator(MultipleLocator(2.5))
    p = EcPanel(
        path="a.pkl",
        fig=fig,
        ax=ax,
        cycle_lines={1: {"charge": ln, "discharge": None}},
        file_data=None,
    )
    try:
        cfg = _capture_panel(p)
        spacing = cfg.get("ticks", {}).get("spacing", {})
        assert spacing.get("y_major_step") == pytest.approx(2.5)
        assert ec_tick_state_from_fig(fig) is not None
    finally:
        plt.close(fig)

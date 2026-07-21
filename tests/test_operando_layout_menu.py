"""Tests for operando unified g: size submenu."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
import pytest

from batplot.plot_modes.common.size_spec import parse_size_spec
from batplot.plot_modes.operando.layout_menu import (
    OperandoLayoutInches,
    apply_canvas_preserving_panels,
    apply_shared_panel_height,
    panel_heights_inches,
)


def _build_fig(with_ec: bool = True):
    fig, ax = plt.subplots(figsize=(11, 6))
    z = np.random.default_rng(0).random((20, 30))
    im = ax.imshow(z, aspect="auto", origin="lower", extent=(10.0, 40.0, 0.0, 20.0))
    cbar = fig.colorbar(im, ax=ax)
    ec_ax = None
    if with_ec:
        ec_ax = fig.add_axes((0.78, 0.1, 0.18, 0.8))
        ec_ax.plot(np.linspace(3.0, 4.2, 30), np.linspace(0.0, 20.0, 30))
    from batplot.plot_modes.operando.layout import _apply_group_layout_inches, _ensure_fixed_params

    cb_w, cb_gap, ec_gap, ec_w, op_w, op_h = _ensure_fixed_params(fig, ax, cbar.ax, ec_ax)
    _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, op_w, op_h, cb_w, cb_gap, ec_gap, ec_w)
    return fig, ax, cbar, ec_ax


def test_parse_size_spec_accepts_two_numbers():
    parsed = parse_size_spec("5 5", 11.0, 6.0)
    assert parsed == pytest.approx((5.0, 5.0))


def test_canvas_resize_preserves_panel_inches():
    fig, ax, cbar, ec_ax = _build_fig()
    try:
        before = OperandoLayoutInches.read(fig, ax, cbar.ax, ec_ax)
        apply_canvas_preserving_panels(fig, ax, cbar.ax, ec_ax, 8.0, 5.0)
        after = OperandoLayoutInches.read(fig, ax, cbar.ax, ec_ax)
        assert fig.get_size_inches() == pytest.approx((8.0, 5.0))
        assert after.op_w_in == pytest.approx(before.op_w_in, rel=0.02)
        assert after.op_h_in == pytest.approx(before.op_h_in, rel=0.02)
        assert after.ec_w_in == pytest.approx(before.ec_w_in, rel=0.02)
    finally:
        plt.close(fig)


def test_shared_height_updates_contour_colorbar_and_ec():
    fig, ax, cbar, ec_ax = _build_fig(with_ec=True)
    try:
        apply_shared_panel_height(fig, ax, cbar.ax, ec_ax, 3.5)
        op_h, cb_h, ec_h = panel_heights_inches(fig, ax, cbar.ax, ec_ax)
        assert op_h == pytest.approx(3.5, abs=0.08)
        assert cb_h == pytest.approx(3.5, abs=0.08)
        assert ec_h == pytest.approx(3.5, abs=0.08)
    finally:
        plt.close(fig)


def test_operando_batch_menu_lists_size_not_scattered_widths(capsys):
    from batplot.plot_modes.batch_session.menu_operando import _print_operando_batch_menu
    from tests.test_operando_batch_menu import _build_panel

    p = _build_panel()
    _print_operando_batch_menu([p])
    out = capsys.readouterr().out
    assert "size" in out
    assert "ow: op width" not in out
    assert "h: height" not in out
    plt.close(p.fig)

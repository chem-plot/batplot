"""Tests for batch multi-panel current-value display helpers."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
import pytest

from batplot.plot_modes.batch_session.batch_menu_helpers import (
    print_batch_pair_status,
    print_batch_scalar_status,
    prompt_batch_clim,
    summarize_limit_pairs,
)
from batplot.plot_modes.batch_session.load import OperandoPanel


def _panel(clim: tuple[float, float], path: str = "a.pkl") -> OperandoPanel:
    fig, ax = plt.subplots()
    z = np.random.default_rng(0).random((10, 10))
    im = ax.imshow(z, aspect="auto")
    im.set_clim(*clim)
    cbar = fig.colorbar(im, ax=ax)
    ec_ax = fig.add_axes((0.78, 0.1, 0.18, 0.8))
    return OperandoPanel(path=path, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax)


def test_summarize_limit_pairs_differing():
    pairs = [(11.0, 18.0), (0.0, 558.5), (11.0, 18.0)]
    text = summarize_limit_pairs(pairs)
    assert "11 18" in text
    assert "558" in text
    assert " / " in text


def test_print_batch_pair_status_numbered(capsys):
    panels = [_panel((11, 18), "a.pkl"), _panel((0, 558.5), "b.pkl")]
    try:
        print_batch_pair_status(panels, label="intensity", get_pair=lambda p: p.im.get_clim())
        out = capsys.readouterr().out
        assert "[1]" in out
        assert "[2]" in out
        assert "11" in out
        assert "558" in out
    finally:
        for p in panels:
            plt.close(p.fig)


def test_print_batch_pair_status_all_same(capsys):
    panels = [_panel((1, 2), "a.pkl"), _panel((1, 2), "b.pkl")]
    try:
        print_batch_pair_status(panels, label="intensity", get_pair=lambda p: p.im.get_clim())
        out = capsys.readouterr().out
        assert "all plots" in out
        assert "[1]" not in out
    finally:
        for p in panels:
            plt.close(p.fig)


def test_print_batch_scalar_status(capsys):
    panels = [_panel((1, 2), "a.pkl"), _panel((1, 2), "b.pkl")]
    try:
        print_batch_scalar_status(
            panels,
            label="operando width",
            get_value=lambda _p: 4.5,
            fmt="{:.2f}",
            unit="in",
        )
        out = capsys.readouterr().out
        assert "all plots" in out
        assert "4.50" in out
    finally:
        for p in panels:
            plt.close(p.fig)

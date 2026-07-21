"""Tests for batch EC cycles/colors multi-panel status display."""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest

from batplot.plot_modes.batch_session.ec_batch_helpers import print_batch_ec_cycles_status
from batplot.plot_modes.batch_session.load import EcPanel


def test_print_batch_ec_cycles_status_shows_all_panels(capsys):
    fig1, ax1 = plt.subplots()
    fig2, ax2 = plt.subplots()
    c1 = ax1.plot([0, 1], color="#ff0000", visible=True)[0]
    c2 = ax2.plot([0, 1], color="#0000ff", visible=True)[0]
    p1 = EcPanel(
        path="B443.pkl",
        fig=fig1,
        ax=ax1,
        cycle_lines={1: {"charge": c1, "discharge": None}},
        file_data=None,
    )
    p2 = EcPanel(
        path="B444.pkl",
        fig=fig2,
        ax=ax2,
        cycle_lines={5: {"charge": c2, "discharge": None}},
        file_data=None,
    )
    try:
        print_batch_ec_cycles_status([p1, p2])
        out = capsys.readouterr().out
        assert "[1]" in out
        assert "[2]" in out
        assert "B443.pkl" in out
        assert "B444.pkl" in out
        assert "1:" in out
        assert "5:" in out
    finally:
        plt.close(fig1)
        plt.close(fig2)

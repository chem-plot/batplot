"""Tests for shared batch geometry (plot frame + canvas) size menu."""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest

from batplot.plot_modes.batch_session.batch_geom_helpers import (
    apply_canvas_to_all,
    apply_plot_frame_to_all,
    frame_inches,
)
from batplot.plot_modes.batch_session.load import EcPanel


def test_apply_plot_frame_and_canvas_all_panels():
    fig1, ax1 = plt.subplots(figsize=(10, 6))
    fig2, ax2 = plt.subplots(figsize=(10, 6))
    p1 = EcPanel(path="a.pkl", fig=fig1, ax=ax1, cycle_lines={}, file_data=None)
    p2 = EcPanel(path="b.pkl", fig=fig2, ax=ax2, cycle_lines={}, file_data=None)
    panels = [p1, p2]
    try:
        apply_plot_frame_to_all(panels, 5.0, 3.0)
        for p in panels:
            fw, fh = frame_inches(p.fig, p.ax)
            assert fw == pytest.approx(5.0, rel=0.02)
            assert fh == pytest.approx(3.0, rel=0.02)
        apply_canvas_to_all(panels, 12.0, 8.0)
        for p in panels:
            cw, ch = p.fig.get_size_inches()
            assert cw == pytest.approx(12.0)
            assert ch == pytest.approx(8.0)
            fw, fh = frame_inches(p.fig, p.ax)
            assert fw == pytest.approx(5.0, rel=0.02)
            assert fh == pytest.approx(3.0, rel=0.02)
    finally:
        plt.close(fig1)
        plt.close(fig2)

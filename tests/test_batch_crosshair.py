"""Batch crosshair toggle + export suppression."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from batplot.plot_modes.batch_session.batch_crosshair import (
    panel_crosshair_active,
    toggle_batch_crosshair,
)
from batplot.plot_modes.batch_session.batch_figure_io import save_standard_panel_figure
from batplot.plot_modes.batch_session.batch_menu_helpers import batch_options_menu_column
from batplot.plot_modes.common.crosshair_export import savefig_without_crosshair


class _Panel:
    def __init__(self, fig, ax):
        self.fig = fig
        self.ax = ax
        self.path = "a.pkl"


def test_batch_options_column_lists_crosshair():
    col = batch_options_menu_column([])
    assert col[0] == "n: crosshair"
    assert "e: export figures" in col


def test_toggle_batch_crosshair_all_panels_and_export_hides(tmp_path):
    panels = []
    for _ in range(2):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1])
        panels.append(_Panel(fig, ax))

    assert toggle_batch_crosshair(panels) is True
    for p in panels:
        assert panel_crosshair_active(p.fig) is True
        st = p.fig._bp_crosshair
        assert st["hline"] is not None and st["vline"] is not None

    # Export must hide overlays (same path as batch e / oe)
    out = tmp_path / "p0.png"
    saved_vis = {}

    def _fake_savefig(path, **kwargs):
        st = panels[0].fig._bp_crosshair
        saved_vis["hline"] = st["hline"].get_visible()
        saved_vis["vline"] = st["vline"].get_visible()
        saved_vis["text"] = st["text"].get_visible()

    panels[0].fig.savefig = _fake_savefig  # type: ignore[method-assign]
    savefig_without_crosshair(panels[0].fig, str(out), dpi=72)
    assert saved_vis == {"hline": False, "vline": False, "text": False}
    assert panels[0].fig._bp_crosshair["hline"].get_visible() is True

    out2 = tmp_path / "p0b.png"
    # save_standard_panel_figure also uses savefig_without_crosshair
    save_standard_panel_figure(panels[1].fig, panels[1].ax, str(out2))
    assert out2.stat().st_size > 0

    assert toggle_batch_crosshair(panels) is False
    for p in panels:
        assert panel_crosshair_active(p.fig) is False
        plt.close(p.fig)

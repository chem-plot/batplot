"""Crosshair must not appear in exported figures."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from batplot.plot_modes.common.crosshair_export import (
    register_crosshair,
    savefig_without_crosshair,
)


def test_savefig_hides_active_crosshair_artists(tmp_path):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [1, 2])
    hline = ax.axhline(1.5, color="red", zorder=9999)
    vline = ax.axvline(0.5, color="red", zorder=9999)
    txt = ax.text(0.5, 0.5, "x=0.5", transform=ax.transAxes)
    state = {
        "active": True,
        "hline": hline,
        "vline": vline,
        "text": txt,
    }
    register_crosshair(fig, state)

    saved = {"visible": []}

    def _fake_savefig(path, **kwargs):
        saved["visible"] = [
            hline.get_visible(),
            vline.get_visible(),
            txt.get_visible(),
        ]

    fig.savefig = _fake_savefig  # type: ignore[method-assign]

    out = tmp_path / "plot.png"
    savefig_without_crosshair(fig, str(out), dpi=100)

    assert saved["visible"] == [False, False, False]
    assert hline.get_visible() is True
    assert vline.get_visible() is True
    assert txt.get_visible() is True

    plt.close(fig)

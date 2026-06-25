"""Tests for shared colormap resolution helpers."""

from __future__ import annotations

import matplotlib.pyplot as plt

from batplot.color_utils import ensure_colormap, get_colormap


def test_get_colormap_resolves_viridis():
    cmap = get_colormap("viridis")
    assert cmap is not None
    assert callable(cmap)


def test_get_colormap_resolves_reversed_builtin():
    cmap = get_colormap("viridis_r")
    assert cmap is not None


def test_get_colormap_without_deprecated_cm_get_cmap(monkeypatch):
    """Regression: palette menus must work when matplotlib.cm.get_cmap is gone."""

    import matplotlib.cm as cm

    monkeypatch.delattr(cm, "get_cmap", raising=False)

    assert ensure_colormap("viridis")
    cmap = get_colormap("viridis")
    assert cmap is not None
    assert "viridis" in plt.colormaps()

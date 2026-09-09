"""Dual-axis secondary top spine color must update spine + ticks + title together."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

from batplot.plot_modes.electrochem.spine_colors import _apply_secondary_top_spine_color
from batplot.ui import _apply_side_color_once, finalize_spine_colors, set_spine_side_color


def _hex_rgb(c) -> tuple:
    from matplotlib.colors import to_rgb

    return tuple(round(v, 5) for v in to_rgb(c))


def test_secondary_top_spine_colors_title_and_spine():
    fig, ax = plt.subplots()
    ax.plot([0.0, 100.0], [3.0, 4.0])
    ax.set_xlabel("Specific Capacity")
    sec = ax.secondary_xaxis("top", functions=(lambda x: x / 162.5, lambda x: x * 162.5))
    sec.set_xlabel("Number of ions (C / 162.5 mAh g$^{-1}$)")
    fig._xaxis_secondary = sec
    fig._xaxis_mode = "dual"

    _apply_secondary_top_spine_color(fig, "green", "green")
    fig.canvas.draw()
    finalize_spine_colors(fig, ax, draw=True)

    green = _hex_rgb("green")
    assert _hex_rgb(sec.spines["top"].get_edgecolor()) == green
    assert _hex_rgb(sec.xaxis.label.get_color()) == green
    assert _hex_rgb(ax.spines["top"].get_edgecolor()) == green
    ticks = sec.xaxis.get_major_ticks()
    assert ticks
    assert _hex_rgb(ticks[0].tick2line.get_color()) == green
    assert _hex_rgb(ticks[0].label2.get_color()) == green
    plt.close(fig)


def test_apply_side_color_once_colors_secondary_xaxis_label():
    fig, ax = plt.subplots()
    sec = ax.secondary_xaxis("top", functions=(lambda x: x, lambda x: x))
    sec.set_xlabel("ions")
    _apply_side_color_once(sec, "top", "#008000")
    assert _hex_rgb(sec.xaxis.label.get_color()) == _hex_rgb("#008000")
    plt.close(fig)


def test_set_spine_side_color_bottom_still_ok():
    fig, ax = plt.subplots()
    ax.set_xlabel("bottom")
    set_spine_side_color(ax, "bottom", "red", fig=fig)
    assert _hex_rgb(ax.xaxis.label.get_color()) == _hex_rgb("red")
    assert _hex_rgb(ax.spines["bottom"].get_edgecolor()) == _hex_rgb("red")
    plt.close(fig)

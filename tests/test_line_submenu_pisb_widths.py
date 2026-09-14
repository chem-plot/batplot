"""Line-submenu frame/tick widths round-trip via p/i/s/b (twin / dual / cbar)."""

from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.common.spines import apply_frame_and_tick_widths, current_tick_width
from batplot.plot_modes.electrochem.style import sync_ec_dual_frame_linewidths
from batplot.plot_modes.operando.style import (
    apply_cbar_line_widths,
    capture_cbar_line_widths,
    reapply_stashed_cbar_line_widths,
    stash_cbar_line_widths,
)
from batplot.plot_modes.xy.spines import (
    apply_xy_spine_specs,
    apply_xy_tick_widths,
    sync_xy_twin_spine_linewidth,
)
from batplot.plot_modes.xy.style import apply_style_config


def test_xy_twin_tick_and_spine_widths_via_apply_helpers():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    fig._xy_ax2 = ax2
    fig._xy_use_top_x = False
    apply_frame_and_tick_widths([ax, ax2], frame_width=2.5, major_width=1.8, minor_width=1.1)
    # Style/session path: primary spines + twin sync + tick widths helper
    apply_xy_spine_specs(
        fig,
        ax,
        {},
        {
            "right": {"linewidth": 2.5},
            "left": {"linewidth": 2.5},
            "top": {"linewidth": 2.5},
            "bottom": {"linewidth": 2.5},
        },
    )
    apply_frame_and_tick_widths([ax2], frame_width=0.5, major_width=0.5, minor_width=0.5)
    apply_xy_tick_widths(
        fig,
        ax,
        {"x_major": 1.8, "y_major": 1.8, "x_minor": 1.1, "y_minor": 1.1},
    )
    sync_xy_twin_spine_linewidth(fig, "right", 2.5)
    assert abs(float(ax2.spines["right"].get_linewidth()) - 2.5) < 1e-6
    assert abs(float(current_tick_width(ax2.yaxis, "major") or 0) - 1.8) < 1e-6
    plt.close(fig)


def test_xy_style_apply_mirrors_tick_widths_to_twin(tmp_path):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax2 = ax.twinx()
    fig._xy_ax2 = ax2
    cfg = {
        "kind": "xy_style",
        "version": 2,
        "ticks": {
            "x_major_width": 2.0,
            "x_minor_width": 1.0,
            "y_major_width": 3.0,
            "y_minor_width": 1.5,
        },
        "spines": {
            "right": {"linewidth": 2.4},
            "left": {"linewidth": 2.4},
            "top": {"linewidth": 2.4},
            "bottom": {"linewidth": 2.4},
        },
        "lines": [],
    }
    path = tmp_path / "xy_line_widths.bps"
    path.write_text(json.dumps(cfg), encoding="utf-8")

    class _Args:
        pass

    apply_style_config(
        str(path),
        fig,
        ax,
        [np.array([0.0, 1.0])],
        [np.array([0.0, 1.0])],
        [np.array([0.0, 1.0])],
        [0.0],
        [],
        _Args(),
        {},
        ["c1"],
        update_labels_func=lambda *_a, **_k: None,
    )
    assert abs(float(current_tick_width(ax2.yaxis, "major") or 0) - 3.0) < 1e-6
    assert abs(float(ax2.spines["right"].get_linewidth()) - 2.4) < 1e-6
    plt.close(fig)


def test_ec_dual_frame_linewidth_sync():
    fig, ax = plt.subplots()
    sec = fig.add_axes([0.1, 0.1, 0.8, 0.8])
    fig._xaxis_mode = "dual"
    fig._xaxis_secondary = sec
    for name in ("bottom", "top", "left", "right"):
        ax.spines[name].set_linewidth(2.25)
        sec.spines[name].set_linewidth(0.4)
    sync_ec_dual_frame_linewidths(fig, ax)
    for name in ("bottom", "top", "left", "right"):
        assert abs(float(sec.spines[name].get_linewidth()) - 2.25) < 1e-6
    # BC: non-dual no-op
    fig._xaxis_mode = "capacity"
    sec.spines["left"].set_linewidth(0.4)
    sync_ec_dual_frame_linewidths(fig, ax)
    assert abs(float(sec.spines["left"].get_linewidth()) - 0.4) < 1e-6
    plt.close(fig)


def test_operando_cbar_line_widths_capture_apply_and_stash():
    fig, ax = plt.subplots()
    im = ax.imshow(np.arange(9).reshape(3, 3))
    cbar = fig.colorbar(im)
    apply_frame_and_tick_widths([cbar.ax], frame_width=2.2, major_width=1.7, minor_width=1.2)
    payload = capture_cbar_line_widths(cbar)
    assert abs(float(payload["spines"]["left"]["linewidth"]) - 2.2) < 1e-6

    apply_frame_and_tick_widths([cbar.ax], frame_width=0.5, major_width=0.5, minor_width=0.5)
    apply_cbar_line_widths(cbar, payload)
    assert abs(float(cbar.ax.spines["left"].get_linewidth()) - 2.2) < 1e-6
    assert getattr(fig, "_operando_cbar_line_widths", None)

    apply_frame_and_tick_widths([cbar.ax], frame_width=0.3, major_width=0.3, minor_width=0.3)
    reapply_stashed_cbar_line_widths(cbar.ax)
    assert abs(float(cbar.ax.spines["left"].get_linewidth()) - 2.2) < 1e-6

    # Old / empty payload must no-op (BC)
    apply_cbar_line_widths(cbar, None)
    apply_cbar_line_widths(cbar, {})
    plt.close(fig)


def test_operando_style_cfg_includes_cbar_widths():
    from batplot.plot_modes.operando.style import build_operando_ec_style_config_v2

    fig, ax = plt.subplots()
    im = ax.imshow(np.arange(4).reshape(2, 2))
    cbar = fig.colorbar(im)
    apply_frame_and_tick_widths([cbar.ax], frame_width=1.9, major_width=1.4, minor_width=1.0)
    stash_cbar_line_widths(fig, cbar)
    cfg, _ext = build_operando_ec_style_config_v2(fig, ax, im, cbar, None, "ps")
    assert "spines" in cfg["colorbar"]
    assert abs(float(cfg["colorbar"]["spines"]["left"]["linewidth"]) - 1.9) < 1e-6
    plt.close(fig)

"""CPC/EC/XY: undo after canvas resize must restore figsize + frame."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.cpc import style as CS
from batplot.plot_modes.cpc.snapshots import push_cpc_state, restore_cpc_state
from batplot.ui import sync_figure_geometry_caches


def _minimal_cpc_figure():
    fig, ax = plt.subplots(figsize=(10.0, 6.0))
    ax2 = ax.twinx()
    x = np.arange(1, 6)
    sc_c = ax.scatter(x, x * 10, color="C0")
    sc_d = ax.scatter(x, x * 9, color="C1")
    sc_e = ax2.scatter(x, np.full_like(x, 98.0, dtype=float), color="C2")
    ax.set_position([0.12, 0.14, 0.76, 0.72])
    ax2.set_position(ax.get_position())
    sync_figure_geometry_caches(fig, ax)
    return fig, ax, ax2, sc_c, sc_d, sc_e


def test_cpc_undo_restores_canvas_size_and_frame_after_resize():
    fig, ax, ax2, sc_c, sc_d, sc_e = _minimal_cpc_figure()
    history: list = []
    tick_state = {"bx": True, "tx": False, "ly": True, "ry": False}
    try:
        before_size = tuple(float(v) for v in fig.get_size_inches())
        before_pos = ax.get_position().bounds

        push_cpc_state(
            history,
            fig=fig,
            ax=ax,
            ax2=ax2,
            sc_charge=sc_c,
            sc_discharge=sc_d,
            sc_eff=sc_e,
            tick_state=tick_state,
            file_data=None,
            note="resize-canvas",
        )
        assert history

        # Simulate g→c resize (frame clamped to fit smaller canvas)
        fig.set_size_inches(7.5, 4.38, forward=True)
        ax.set_position([0.05, 0.05, 0.90, 0.90])
        ax2.set_position(ax.get_position())
        fig._last_canvas_size = (7.5, 4.38)

        ok = restore_cpc_state(
            state_history=history,
            fig=fig,
            ax=ax,
            ax2=ax2,
            sc_charge=sc_c,
            sc_discharge=sc_d,
            sc_eff=sc_e,
            tick_state=tick_state,
            file_data=None,
            update_ticks_func=lambda: None,
        )
        assert ok is True
        after_size = tuple(float(v) for v in fig.get_size_inches())
        after_pos = ax.get_position().bounds
        assert abs(after_size[0] - before_size[0]) < 1e-6
        assert abs(after_size[1] - before_size[1]) < 1e-6
        for a, b in zip(after_pos, before_pos):
            assert abs(float(a) - float(b)) < 1e-6
        # g-menu caches must match restored geometry
        assert abs(fig._last_canvas_size[0] - before_size[0]) < 1e-6
        assert abs(fig._last_canvas_size[1] - before_size[1]) < 1e-6
    finally:
        plt.close(fig)


def test_cpc_style_geom_apply_uses_forward_true(monkeypatch):
    fig, ax, ax2, sc_c, sc_d, sc_e = _minimal_cpc_figure()
    seen = {}

    def _spy(w, h, *a, **k):
        seen["forward"] = k.get("forward")
        seen["size"] = (float(w), float(h))
        return plt.Figure.set_size_inches(fig, w, h, *a, **k)

    monkeypatch.setattr(fig, "set_size_inches", _spy)
    try:
        cfg = CS._style_snapshot(fig, ax, ax2, sc_c, sc_d, sc_e)
        cfg["kind"] = "cpc_style_geom"
        cfg["figure"]["canvas_size"] = [8.0, 5.0]
        cfg["figure"]["axes_fraction"] = [0.1, 0.1, 0.8, 0.8]
        CS._apply_style(fig, ax, ax2, sc_c, sc_d, sc_e, cfg, None)
        assert seen.get("forward") is True
        assert seen.get("size") == (8.0, 5.0)
    finally:
        plt.close(fig)


def test_style_only_still_does_not_resize_cpc():
    fig, ax, ax2, sc_c, sc_d, sc_e = _minimal_cpc_figure()
    try:
        before = tuple(float(v) for v in fig.get_size_inches())
        cfg = CS._style_snapshot(fig, ax, ax2, sc_c, sc_d, sc_e)
        cfg["kind"] = "cpc_style"  # style-only
        cfg["figure"]["canvas_size"] = [3.0, 2.0]
        CS._apply_style(fig, ax, ax2, sc_c, sc_d, sc_e, cfg, None)
        after = tuple(float(v) for v in fig.get_size_inches())
        assert abs(after[0] - before[0]) < 1e-9
        assert abs(after[1] - before[1]) < 1e-9
    finally:
        plt.close(fig)

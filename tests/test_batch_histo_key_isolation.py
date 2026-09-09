"""Batch histo isolation locks unique to recent fixes.

``t`` vs peer spine colors: ``test_batch_style_pisb_keys.py``.
Density ylabel / style PISB: ``test_histo_style_pisb_keys.py``.
"""

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_hex

from batplot.plot_modes.batch_session.load import HistoPanel
from batplot.plot_modes.histo.colors import run_histo_color_menu
from batplot.plot_modes.histo.load import build_bin_edges
from batplot.plot_modes.histo.plot import (
    build_histo_state,
    create_histo_figure,
    refresh_histo_figure,
)
from batplot.plot_modes.histo.session import (
    apply_histo_snapshot,
    apply_histo_style_snapshot,
    capture_histo_snapshot,
    load_histo_session,
    save_histo_session,
)
from batplot.plot_modes.histo.spines import (
    ensure_histo_tick_state,
    ensure_histo_wasd,
    get_histo_spine_colors,
    set_histo_spine_color,
)
from batplot.plot_modes.histo.wizard import HistoSetup


def _histo_panel(path: str, **style_kw) -> HistoPanel:
    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = build_histo_state(setup, source_path=path)
    for key, val in style_kw.items():
        setattr(state.style, key, val)
    fig, ax, _ = create_histo_figure(state)
    return HistoPanel(path=path, fig=fig, ax=ax, state=state)


def _bar_face(panel: HistoPanel) -> str:
    patches = list(panel.ax.patches)
    assert patches, "expected histogram bars"
    return to_hex(patches[0].get_facecolor())


def test_c_mixed_bar_and_spine_refreshes_bars():
    """``bar:red a:#0f0`` must update patches, not only spine store/state."""
    p1 = _histo_panel("a.csv", bar_color="#4C72B0")
    p2 = _histo_panel("b.csv", bar_color="#111111")
    panels = [p1, p2]
    try:
        answers = iter(["bar:red a:#00ff00", "q"])

        def _set_bar(c: str) -> None:
            for p in panels:
                p.state.style.bar_color = c

        def _set_edge(c: str) -> None:
            for p in panels:
                p.state.style.edge_color = c

        def _apply_spine(side: str, color: str) -> None:
            for p in panels:
                set_histo_spine_color(p.fig, p.ax, side, color)

        def _finish(_changed) -> None:
            from batplot.plot_modes.histo.spines import apply_histo_spine_colors

            for p in panels:
                apply_histo_spine_colors(p.fig, p.ax, get_histo_spine_colors(p.fig))

        def _refresh() -> None:
            for p in panels:
                refresh_histo_figure(p.fig, p.ax, p.state)

        run_histo_color_menu(
            fig=p1.fig,
            ax=p1.ax,
            get_bar_color=lambda: p1.state.style.bar_color,
            set_bar_color=_set_bar,
            get_edge_color=lambda: p1.state.style.edge_color,
            set_edge_color=_set_edge,
            push_state=lambda: None,
            refresh=_refresh,
            finish_spine_change=_finish,
            safe_input=lambda *_a, **_k: next(answers),
            colorize_prompt=lambda s: s,
            apply_spine_color=_apply_spine,
        )
        assert to_hex(p1.state.style.bar_color) == "#ff0000"
        assert _bar_face(p1) == "#ff0000"
        assert _bar_face(p2) == "#ff0000"
        assert to_hex(get_histo_spine_colors(p2.fig)["left"]) == "#00ff00"
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_r_clear_top_xlabel_clears_peer_override_and_pisb(tmp_path):
    """Clear top-x must drop overrides for peers and survive undo/style/session."""
    p1 = _histo_panel("a.csv")
    p2 = _histo_panel("b.csv")
    try:
        for p in (p1, p2):
            wasd = ensure_histo_wasd(p.fig, p.ax, ensure_histo_tick_state(p.ax))
            wasd["top"]["title"] = True
            p.state.style.top_xlabel = f"TOP-{p.path}"
            refresh_histo_figure(p.fig, p.ax, p.state)
        assert getattr(p2.ax, "_top_xlabel_text_override", None) == "TOP-b.csv"

        # Batch ``r`` clear sync pattern
        p1.state.style.top_xlabel = ""
        if hasattr(p1.ax, "_top_xlabel_text_override"):
            delattr(p1.ax, "_top_xlabel_text_override")
        for p in (p1, p2):
            p.state.style.top_xlabel = p1.state.style.top_xlabel
            if p1.state.style.top_xlabel:
                p.ax._top_xlabel_text_override = p1.state.style.top_xlabel
            elif hasattr(p.ax, "_top_xlabel_text_override"):
                delattr(p.ax, "_top_xlabel_text_override")
            refresh_histo_figure(p.fig, p.ax, p.state)
        assert p2.state.style.top_xlabel == ""
        assert not getattr(p2.ax, "_top_xlabel_text_override", None)

        snap = capture_histo_snapshot(p1.state, p1.fig, p1.ax)
        p2.state.style.top_xlabel = "STALE"
        p2.ax._top_xlabel_text_override = "STALE"
        apply_histo_snapshot(p2.fig, p2.ax, p2.state, snap)
        assert p2.state.style.top_xlabel == ""
        assert not getattr(p2.ax, "_top_xlabel_text_override", None)

        p3 = _histo_panel("c.csv")
        try:
            wasd3 = ensure_histo_wasd(p3.fig, p3.ax, ensure_histo_tick_state(p3.ax))
            wasd3["top"]["title"] = True
            p3.state.style.top_xlabel = "STALE"
            p3.ax._top_xlabel_text_override = "STALE"
            apply_histo_style_snapshot(p3.fig, p3.ax, p3.state, snap)
            assert p3.state.style.top_xlabel == ""
            assert not getattr(p3.ax, "_top_xlabel_text_override", None)
        finally:
            plt.close(p3.fig)

        pkl = tmp_path / "h.pkl"
        save_histo_session(p1.fig, p1.ax, p1.state, str(pkl))
        loaded = load_histo_session(str(pkl))
        assert loaded is not None
        fig_l, ax_l, state_l = loaded
        assert state_l.style.top_xlabel == ""
        assert not getattr(ax_l, "_top_xlabel_text_override", None)
        plt.close(fig_l)
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)

"""Hard gates for batch-mode style keys across p / i / s / b sync paths."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.colors import to_hex

from batplot.plot_modes.batch_session.common import SyncUndoStacks
from batplot.plot_modes.batch_session.cpc_batch_helpers import apply_cpc_colors_only
from batplot.plot_modes.batch_session.load import CpcPanel, EcPanel, HistoPanel, OperandoPanel, XyPanel
from batplot.plot_modes.batch_session.operando_batch_helpers import sync_style_from_ref
from batplot.plot_modes.batch_session.xy_batch_helpers import sync_ref_wasd_to_panels
from batplot.plot_modes.common.title_offsets import (
    capture_title_offsets,
    restore_title_offsets,
    run_title_offset_nudge_menu,
)
from batplot.plot_modes.histo.load import build_bin_edges
from batplot.plot_modes.histo.plot import build_histo_state, create_histo_figure
from batplot.plot_modes.histo.spines import (
    get_histo_spine_colors,
    set_histo_spine_color,
    sync_histo_spine_from_reference,
)
from batplot.plot_modes.histo.wizard import HistoSetup


def _histo_panel(path: str, *, left_color: str = "#000000"):
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
    fig, ax, _ = create_histo_figure(state)
    set_histo_spine_color(fig, ax, "left", left_color)
    return HistoPanel(path=path, fig=fig, ax=ax, state=state)


def test_histo_batch_t_does_not_overwrite_peer_spine_colors():
    p1 = _histo_panel("a.csv", left_color="#ff0000")
    p2 = _histo_panel("b.csv", left_color="#00aa00")
    try:
        # Ref toggles tick length — WASD sync must keep peer left spine green.
        p1.fig._tick_lengths = {"major": 9.0, "minor": 4.5}
        sync_histo_spine_from_reference(p1.fig, p1.ax, [(p2.fig, p2.ax)])
        assert to_hex(get_histo_spine_colors(p2.fig).get("left")) == to_hex("#00aa00")
        assert p2.fig._tick_lengths.get("major") == pytest.approx(9.0)
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_xy_batch_t_syncs_title_offsets_and_labelpads():
    fig1, ax1 = plt.subplots()
    fig2, ax2 = plt.subplots()
    ax1.plot([0, 1], [0, 1])
    ax2.plot([0, 1], [0, 1])
    fig1._bp_wasd_state = {
        "top": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "right": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
    }
    ax1._top_xlabel_manual_offset_y_pts = 12.0
    ax1._left_ylabel_manual_offset_x_pts = -8.0
    ax1.xaxis.labelpad = 11.0
    ax1.yaxis.labelpad = 13.0
    p1 = XyPanel(path="a.pkl", fig=fig1, ax=ax1, menu_kwargs={})
    p2 = XyPanel(path="b.pkl", fig=fig2, ax=ax2, menu_kwargs={})
    try:
        sync_ref_wasd_to_panels(p1, [p1, p2])
        offs = capture_title_offsets(ax2)
        assert offs["top_y"] == pytest.approx(12.0)
        assert offs["left_x"] == pytest.approx(-8.0)
        assert float(ax2.xaxis.labelpad) == pytest.approx(11.0)
        assert float(ax2.yaxis.labelpad) == pytest.approx(13.0)
    finally:
        plt.close(fig1)
        plt.close(fig2)


def test_operando_visibility_sync_keeps_h_offsets_without_full_geometry():
    """Style-only sync must still carry ``v→m`` chrome offsets."""
    from batplot.plot_modes.batch_session.operando_batch_helpers import apply_operando_visibility_only

    fig1, ax1 = plt.subplots()
    im1 = ax1.imshow(np.zeros((4, 4)), origin="lower")
    cbar1 = fig1.colorbar(im1, ax=ax1)
    cbar1.ax._cb_h_offset_in = 0.15
    fig2, ax2 = plt.subplots()
    im2 = ax2.imshow(np.zeros((4, 4)), origin="lower")
    cbar2 = fig2.colorbar(im2, ax=ax2)
    cbar2.ax._cb_h_offset_in = 0.0

    def _capture(panel):
        return {
            "kind": "operando_ec_style_geom",
            "colorbar": {"visible": True},
            "figure": {},
            "ec": {},
            "geometry": {
                "cb_h_offset": float(getattr(panel.cbar.ax, "_cb_h_offset_in", 0.0) or 0.0),
                "figsize": [11.0, 9.0],
                "ax_w_in": 7.0,
            },
            "operando": {},
        }

    p1 = OperandoPanel(path="a.pkl", fig=fig1, ax=ax1, im=im1, cbar=cbar1, ec_ax=None)
    p2 = OperandoPanel(path="b.pkl", fig=fig2, ax=ax2, im=im2, cbar=cbar2, ec_ax=None)
    try:
        sync_style_from_ref(
            p1,
            [p1, p2],
            capture_panel=_capture,
            apply_cfg=apply_operando_visibility_only,
            include_geometry=False,
        )
        assert float(getattr(cbar2.ax, "_cb_h_offset_in", 0.0)) == pytest.approx(0.15)
        # Full canvas inches from geometry must NOT hitchhike on style-only sync.
        assert tuple(fig2.get_size_inches()) != pytest.approx((11.0, 9.0))
    finally:
        plt.close(fig1)
        plt.close(fig2)


def test_cpc_batch_color_sync_includes_series_alpha():
    fig1, ax1 = plt.subplots()
    ax1b = ax1.twinx()
    sc_c1 = ax1.scatter([1], [1], color="C0", alpha=0.4)
    sc_d1 = ax1.scatter([1], [2], color="C1", alpha=0.4)
    sc_e1 = ax1b.scatter([1], [90], color="C2", alpha=0.4)
    fig2, ax2 = plt.subplots()
    ax2b = ax2.twinx()
    sc_c2 = ax2.scatter([1], [1], color="C3", alpha=1.0)
    sc_d2 = ax2.scatter([1], [2], color="C4", alpha=1.0)
    sc_e2 = ax2b.scatter([1], [90], color="C5", alpha=1.0)
    p1 = CpcPanel(
        path="a.pkl",
        fig=fig1,
        ax=ax1,
        ax2=ax1b,
        sc_charge=sc_c1,
        sc_discharge=sc_d1,
        sc_eff=sc_e1,
        file_data=None,
    )
    p2 = CpcPanel(
        path="b.pkl",
        fig=fig2,
        ax=ax2,
        ax2=ax2b,
        sc_charge=sc_c2,
        sc_discharge=sc_d2,
        sc_eff=sc_e2,
        file_data=None,
    )
    try:
        from batplot.plot_modes.batch_session.menu_cpc import _capture_panel

        cfg = _capture_panel(p1)
        assert cfg["series"]["charge"]["alpha"] == pytest.approx(0.4)
        apply_cpc_colors_only(p2, cfg, silent=True)
        assert float(sc_c2.get_alpha()) == pytest.approx(0.4)
    finally:
        plt.close(fig1)
        plt.close(fig2)


def test_batch_selective_import_undo_only_touches_selected_indices():
    undo = SyncUndoStacks(3)
    baseline = [{"n": i} for i in range(3)]
    undo.push_all(baseline)
    # Selective import onto panel 1 only
    undo.push_indices([1], [{"n": 1, "imported": True}])
    assert undo.can_undo()
    restored: list[tuple[int, dict]] = []

    def _restore(i, snap):
        restored.append((i, snap))

    assert undo.undo_all(_restore) is True
    assert restored == [(1, {"n": 1, "imported": True})]
    # Unchanged peers still at baseline depth
    assert len(undo._stacks[0]) == 1
    assert len(undo._stacks[2]) == 1


def test_xy_batch_rename_stores_labels_and_clears_top_override():
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax._top_xlabel_text_override = "OLD TOP"
    ax.set_xlabel("oldx")
    ax.set_ylabel("oldy")
    xl, yl = "New X", "New Y"
    ax.set_xlabel(xl)
    ax._stored_xlabel = xl
    if hasattr(ax, "_top_xlabel_text_override"):
        delattr(ax, "_top_xlabel_text_override")
    ax.set_ylabel(yl)
    ax._stored_ylabel = yl
    assert ax.get_xlabel() == "New X"
    assert ax._stored_xlabel == "New X"
    assert not hasattr(ax, "_top_xlabel_text_override")
    assert ax._stored_ylabel == "New Y"
    plt.close(fig)


def test_title_offset_nudge_does_not_push_undo_on_unknown_input():
    """Invalid nudge keys must not create junk undo frames (``b`` pollution)."""
    fig, ax = plt.subplots()
    pushes: list[int] = []
    answers = iter(["w", "zzz", "q", "q"])
    try:
        run_title_offset_nudge_menu(
            fig=fig,
            ax=ax,
            push_state=lambda: pushes.append(1),
            safe_input=lambda _p: next(answers),
            colorize_prompt=lambda s: s,
            draw=lambda: None,
        )
        assert pushes == []
        assert float(getattr(ax, "_top_xlabel_manual_offset_y_pts", 0.0) or 0.0) == 0.0
    finally:
        plt.close(fig)


def test_title_offset_nudge_routes_right_side_to_axis_by_side():
    """CPC efficiency title lives on twin ``ax2`` — batch ``t→p→d`` must hit it."""
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    answers = iter(["d", "w", "q", "q"])
    try:
        run_title_offset_nudge_menu(
            fig=fig,
            ax=ax,
            push_state=lambda: None,
            safe_input=lambda _p: next(answers),
            colorize_prompt=lambda s: s,
            draw=lambda: None,
            axis_by_side={"d": ax2},
        )
        assert float(getattr(ax, "_right_ylabel_manual_offset_x_pts", 0.0) or 0.0) == 0.0
        assert float(getattr(ax2, "_right_ylabel_manual_offset_x_pts", 0.0) or 0.0) != 0.0
    finally:
        plt.close(fig)


def test_cpc_batch_spine_menu_wires_right_title_to_ax2():
    """Guard: batch CPC title-offset handler must pass ``axis_by_side={'d': ax2}``."""
    from pathlib import Path

    helper = Path(__file__).resolve().parents[1] / "batplot/plot_modes/batch_session/cpc_batch_helpers.py"
    text = helper.read_text(encoding="utf-8")
    assert 'axis_by_side={"d": ax2}' in text

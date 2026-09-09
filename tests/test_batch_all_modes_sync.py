"""Batch-wide sync and p/i/s/b contract tests across EC/CPC and style sync."""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest
from matplotlib.ticker import MultipleLocator

from batplot.plot_modes.batch_session.batch_panel_state import verify_panel_pisb_roundtrip
from batplot.plot_modes.batch_session.common import SyncUndoStacks
from batplot.plot_modes.batch_session.load import CpcPanel, EcPanel
from batplot.plot_modes.batch_session.menu_cpc import (
    _apply_cpc_style,
    _capture_panel as cpc_capture,
    _restore_panel as cpc_restore,
    _toggle_efficiency_all,
)
from matplotlib.colors import to_hex

from batplot.plot_modes.batch_session.cpc_batch_helpers import apply_cpc_labels_only
from batplot.plot_modes.batch_session.ec_batch_helpers import (
    apply_ec_cycles_colors_only,
    apply_ec_labels_only,
    apply_ec_legend_only,
    apply_ec_line_chrome_only,
    apply_ec_spine_colors_only,
)
from batplot.plot_modes.batch_session.menu_ec import _apply_cfg, _capture_panel as ec_capture
from batplot.plot_modes.batch_session.operando_batch_helpers import (
    edit_ref_then_sync,
    sync_style_from_ref,
)


def test_ec_pisb_roundtrip():
    fig, ax = plt.subplots()
    (c,) = ax.plot([0.0, 1.0], [0.0, 1.0])
    p = EcPanel(
        path="a.pkl",
        fig=fig,
        ax=ax,
        cycle_lines={1: {"charge": c, "discharge": None}},
        file_data=None,
    )
    try:
        verify_panel_pisb_roundtrip(p, "ec_gc", sub="ps")
        verify_panel_pisb_roundtrip(p, "ec_gc", sub="psg")
    finally:
        plt.close(fig)


def test_cpc_pisb_roundtrip():
    from test_cpc_roundtrip import _build_cpc_figure

    fig, ax, ax2, sc_c, sc_d, sc_e, _cyc = _build_cpc_figure()
    p = CpcPanel(
        path="cpc.pkl",
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
    )
    try:
        verify_panel_pisb_roundtrip(p, "cpc", sub="ps")
        verify_panel_pisb_roundtrip(p, "cpc", sub="psg")
    finally:
        plt.close(fig)


def test_cpc_efficiency_toggle_undo_restores_ax2_visibility():
    """Batch ``ry`` hides efficiency chrome/artists, never ``ax2`` (right spine)."""
    from test_cpc_roundtrip import _build_cpc_figure

    fig1, ax1, ax2_1, sc_c1, sc_d1, sc_e1, _ = _build_cpc_figure()
    fig2, ax2, ax2_2, sc_c2, sc_d2, sc_e2, _ = _build_cpc_figure()
    p1 = CpcPanel(
        path="a.pkl", fig=fig1, ax=ax1, ax2=ax2_1,
        sc_charge=sc_c1, sc_discharge=sc_d1, sc_eff=sc_e1,
    )
    p2 = CpcPanel(
        path="b.pkl", fig=fig2, ax=ax2, ax2=ax2_2,
        sc_charge=sc_c2, sc_discharge=sc_d2, sc_eff=sc_e2,
    )
    panels = [p1, p2]
    snap = [cpc_capture(p) for p in panels]
    assert ax2_1.get_visible() is True
    assert ax2_2.get_visible() is True
    assert sc_e1.get_visible() is True
    _toggle_efficiency_all(panels)
    # Twin axes stay visible so the right spine/frame remains; series hide.
    assert ax2_1.get_visible() is True
    assert ax2_2.get_visible() is True
    assert sc_e1.get_visible() is False
    assert sc_e2.get_visible() is False
    cpc_restore(panels[0], snap[0])
    cpc_restore(panels[1], snap[1])
    assert ax2_1.get_visible() is True
    assert ax2_2.get_visible() is True
    assert sc_e1.get_visible() is True
    assert sc_e2.get_visible() is True
    plt.close(fig1)
    plt.close(fig2)


def test_style_sync_default_preserves_peer_axis_limits():
    fig1, ax1 = plt.subplots()
    fig2, ax2 = plt.subplots()
    ln1 = ax1.plot([0, 10], [0, 1], color="C0")[0]
    ln2 = ax2.plot([0, 100], [0, 1], color="C0")[0]
    ax1.set_xlim(0, 10)
    ax2.set_xlim(0, 100)
    p1 = EcPanel(
        path="a.pkl", fig=fig1, ax=ax1,
        cycle_lines={1: {"charge": ln1, "discharge": None}}, file_data=None,
    )
    p2 = EcPanel(
        path="b.pkl", fig=fig2, ax=ax2,
        cycle_lines={1: {"charge": ln2, "discharge": None}}, file_data=None,
    )
    ax1.yaxis.set_major_locator(MultipleLocator(2.0))
    try:
        sync_style_from_ref(p1, [p1, p2], capture_panel=ec_capture, apply_cfg=_apply_cfg)
        assert isinstance(ax2.yaxis.get_major_locator(), MultipleLocator)
        assert float(ax2.yaxis.get_major_locator()._edge.step) == pytest.approx(2.0)
        assert ax2.get_xlim() == pytest.approx((0, 100))
    finally:
        plt.close(fig1)
        plt.close(fig2)


def test_cpc_style_sync_preserves_peer_xlim():
    from test_cpc_roundtrip import _build_cpc_figure

    fig1, ax1, ax2a, sc_c1, sc_d1, sc_e1, _ = _build_cpc_figure()
    fig2, ax2, ax2b, sc_c2, sc_d2, sc_e2, _ = _build_cpc_figure()
    ax1.set_xlim(1, 5)
    ax2.set_xlim(10, 50)
    p1 = CpcPanel(
        path="a.pkl", fig=fig1, ax=ax1, ax2=ax2a,
        sc_charge=sc_c1, sc_discharge=sc_d1, sc_eff=sc_e1,
    )
    p2 = CpcPanel(
        path="b.pkl", fig=fig2, ax=ax2, ax2=ax2b,
        sc_charge=sc_c2, sc_discharge=sc_d2, sc_eff=sc_e2,
    )
    try:
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=cpc_capture, apply_cfg=_apply_cpc_style
        )
        assert ax2.get_xlim() == pytest.approx((10, 50))
    finally:
        plt.close(fig1)
        plt.close(fig2)


def _two_ec_panels():
    fig1, ax1 = plt.subplots()
    fig2, ax2 = plt.subplots()
    ln1 = ax1.plot([0, 1], [0, 1], color="C0")[0]
    ln2 = ax2.plot([0, 1], [0, 1], color="C0")[0]
    ax1.set_xlabel("Potential (V)")
    ax2.set_xlabel("Potential (V)")
    ax1._stored_xlabel = "Potential (V)"
    ax2._stored_xlabel = "Potential (V)"
    ax1.set_xlim(0, 10)
    ax2.set_xlim(0, 100)
    p1 = EcPanel(
        path="a.pkl",
        fig=fig1,
        ax=ax1,
        cycle_lines={1: {"charge": ln1, "discharge": None}},
        file_data=None,
    )
    p2 = EcPanel(
        path="b.pkl",
        fig=fig2,
        ax=ax2,
        cycle_lines={1: {"charge": ln2, "discharge": None}},
        file_data=None,
    )
    return p1, p2


def test_ec_batch_rename_syncs_xlabel_to_all_panels():
    """Rename sync must copy axis titles only (not colors / smooth / limits)."""
    p1, p2 = _two_ec_panels()
    try:
        p1.ax.set_xlabel(r"Potential vs Li/Li$^{\mathrm{+}}$")
        p1.ax._stored_xlabel = r"Potential vs Li/Li$^{\mathrm{+}}$"
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=ec_capture, apply_cfg=apply_ec_labels_only
        )
        assert p2.ax.get_xlabel() == r"Potential vs Li/Li$^{\mathrm{+}}$"
        assert getattr(p2.ax, "_stored_xlabel", None) == r"Potential vs Li/Li$^{\mathrm{+}}$"
        # Peer axis limits must stay local under style-only sync.
        assert p2.ax.get_xlim() == pytest.approx((0, 100))
        # Capture/export must keep the new label for p/i/s/b.
        cfg2 = ec_capture(p2)
        assert (cfg2.get("axis_labels") or {}).get("xlabel") == r"Potential vs Li/Li$^{\mathrm{+}}$"
        assert (cfg2.get("geometry") or {}).get("xlabel") == r"Potential vs Li/Li$^{\mathrm{+}}$"
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_ec_batch_rename_keeps_peer_colors_smooth_and_limits():
    """Full style apply on rename used to clobber dQ/dV peer colors/smooth."""
    p1, p2 = _two_ec_panels()
    try:
        p1.cycle_lines[1]["charge"].set_color("#ff0000")
        p2.cycle_lines[1]["charge"].set_color("#00aa00")
        p1.fig._dqdv_smooth_settings = {"window": 11, "polyorder": 3}
        p2.fig._dqdv_smooth_settings = {"window": 5, "polyorder": 2}
        p1.ax.set_xlabel("123")
        p1.ax._stored_xlabel = "123"
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=ec_capture, apply_cfg=apply_ec_labels_only
        )
        assert p2.ax.get_xlabel() == "123"
        assert p2.ax.get_xlim() == pytest.approx((0, 100))
        assert to_hex(p2.cycle_lines[1]["charge"].get_color()) == "#00aa00"
        assert getattr(p2.fig, "_dqdv_smooth_settings", {}) == {"window": 5, "polyorder": 2}
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_ec_batch_line_sync_keeps_peer_colors_and_smooth():
    p1, p2 = _two_ec_panels()
    try:
        p1.cycle_lines[1]["charge"].set_color("#ff0000")
        p2.cycle_lines[1]["charge"].set_color("#00aa00")
        p1.cycle_lines[1]["charge"].set_linewidth(3.0)
        p2.cycle_lines[1]["charge"].set_linewidth(1.0)
        p1.fig._ec_curve_linewidth = 3.0
        p2.fig._ec_curve_linewidth = 1.0
        p1.fig._dqdv_smooth_settings = {"window": 11, "polyorder": 3}
        p2.fig._dqdv_smooth_settings = {"window": 5, "polyorder": 2}
        p1.ax.set_xlabel("Ref Label")
        p1.ax._stored_xlabel = "Ref Label"
        p2.ax.set_xlabel("Peer Label")
        p2.ax._stored_xlabel = "Peer Label"
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=ec_capture, apply_cfg=apply_ec_line_chrome_only
        )
        assert p2.cycle_lines[1]["charge"].get_linewidth() == pytest.approx(3.0)
        assert to_hex(p2.cycle_lines[1]["charge"].get_color()) == "#00aa00"
        assert getattr(p2.fig, "_dqdv_smooth_settings", {}) == {"window": 5, "polyorder": 2}
        assert p2.ax.get_xlabel() == "Peer Label"
        assert p2.ax.get_xlim() == pytest.approx((0, 100))
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_ec_batch_cycles_sync_colors_not_wasd_or_smooth():
    p1, p2 = _two_ec_panels()
    try:
        p1.cycle_lines[1]["charge"].set_color("#ff0000")
        p1.cycle_lines[1]["charge"].set_linewidth(1.0)
        p1.fig._ec_curve_linewidth = 1.0
        p2.cycle_lines[1]["charge"].set_color("#00aa00")
        p2.cycle_lines[1]["charge"].set_linewidth(3.0)
        p2.fig._ec_curve_linewidth = 3.0
        p1.fig._ec_wasd_state = {
            "top": {"spine": True, "ticks": True, "labels": True, "title": False, "minor": False},
            "bottom": {"spine": True, "ticks": True, "labels": True, "title": True, "minor": False},
            "left": {"spine": True, "ticks": True, "labels": True, "title": True, "minor": False},
            "right": {"spine": True, "ticks": False, "labels": False, "title": False, "minor": False},
        }
        p2.fig._ec_wasd_state = {
            "top": {"spine": False, "ticks": False, "labels": False, "title": False, "minor": False},
            "bottom": {"spine": True, "ticks": True, "labels": True, "title": True, "minor": False},
            "left": {"spine": True, "ticks": True, "labels": True, "title": True, "minor": False},
            "right": {"spine": False, "ticks": False, "labels": False, "title": False, "minor": False},
        }
        p1.fig._dqdv_smooth_settings = {"window": 11, "polyorder": 3}
        p2.fig._dqdv_smooth_settings = {"window": 5, "polyorder": 2}
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=ec_capture, apply_cfg=apply_ec_cycles_colors_only
        )
        assert to_hex(p2.cycle_lines[1]["charge"].get_color()) == "#ff0000"
        # ``c`` must not hitchhike ``l`` linewidth onto peers.
        assert p2.cycle_lines[1]["charge"].get_linewidth() == pytest.approx(3.0)
        assert getattr(p2.fig, "_ec_curve_linewidth", None) == pytest.approx(3.0)
        assert getattr(p2.fig, "_dqdv_smooth_settings", {}) == {"window": 5, "polyorder": 2}
        assert p2.fig._ec_wasd_state["top"]["ticks"] is False
        assert p2.ax.get_xlim() == pytest.approx((0, 100))
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_ec_batch_legend_sync_keeps_peer_colors():
    p1, p2 = _two_ec_panels()
    try:
        p1.cycle_lines[1]["charge"].set_color("#ff0000")
        p2.cycle_lines[1]["charge"].set_color("#00aa00")
        p1.fig._ec_legend_xy_in = (0.5, 0.5)
        p2.fig._ec_legend_xy_in = (0.1, 0.1)
        p1.fig._ec_legend_user_visible = True
        p2.fig._ec_legend_user_visible = True
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=ec_capture, apply_cfg=apply_ec_legend_only
        )
        assert getattr(p2.fig, "_ec_legend_xy_in", None) == pytest.approx((0.5, 0.5))
        assert to_hex(p2.cycle_lines[1]["charge"].get_color()) == "#00aa00"
        # p/i capture must keep the synced legend offset.
        cfg2 = ec_capture(p2)
        assert (cfg2.get("legend") or {}).get("position_inches") == pytest.approx((0.5, 0.5))
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_ec_batch_spine_color_sync_keeps_curve_colors():
    p1, p2 = _two_ec_panels()
    try:
        p1.cycle_lines[1]["charge"].set_color("#ff0000")
        p2.cycle_lines[1]["charge"].set_color("#00aa00")
        p1.ax.spines["bottom"].set_color("#0000ff")
        p2.ax.spines["bottom"].set_color("#111111")
        p1.ax._stored_xlabel_color = "#0000ff"
        p2.ax._stored_xlabel_color = "#111111"
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=ec_capture, apply_cfg=apply_ec_spine_colors_only
        )
        assert to_hex(p2.cycle_lines[1]["charge"].get_color()) == "#00aa00"
        assert to_hex(p2.ax.spines["bottom"].get_edgecolor()) == "#0000ff"
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_ec_batch_full_apply_still_used_for_import_undo_path():
    """p/i/s/b and undo keep full apply_ec_style_config via _apply_cfg."""
    p1, p2 = _two_ec_panels()
    try:
        p1.cycle_lines[1]["charge"].set_color("#ff0000")
        p2.cycle_lines[1]["charge"].set_color("#00aa00")
        p1.ax.set_xlabel("Imported")
        p1.ax._stored_xlabel = "Imported"
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=ec_capture, apply_cfg=_apply_cfg
        )
        # Full apply intentionally syncs labels + colors (import/undo contract).
        assert p2.ax.get_xlabel() == "Imported"
        assert to_hex(p2.cycle_lines[1]["charge"].get_color()) == "#ff0000"
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_ec_batch_edit_ref_then_sync_live_on_draw():
    """Nested batch editors must sync peers as soon as the ref canvas redraws."""
    p1, p2 = _two_ec_panels()
    panels = [p1, p2]
    undo = SyncUndoStacks(2)
    undo.push_all([ec_capture(p) for p in panels])

    def _edit() -> None:
        p1.ax.set_xlabel("Live Synced X")
        p1.ax._stored_xlabel = "Live Synced X"
        # Nested menus call draw/draw_idle after mutations; live hook syncs peers.
        p1.fig.canvas.draw()
        assert p2.ax.get_xlabel() == "Live Synced X"

    try:
        edit_ref_then_sync(
            p1,
            panels,
            undo=undo,
            capture_panel=ec_capture,
            apply_cfg=apply_ec_labels_only,
            draw_all=lambda: None,
            edit_fn=_edit,
        )
        assert p2.ax.get_xlabel() == "Live Synced X"
        assert p2.ax.get_xlim() == pytest.approx((0, 100))
        # One undo level restores peers (full snapshot restore).
        undo.undo_all(lambda i, snap: _apply_cfg(panels[i], snap))
        assert p1.ax.get_xlabel() == "Potential (V)"
        assert p2.ax.get_xlabel() == "Potential (V)"
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_cpc_batch_rename_syncs_axis_labels():
    from test_cpc_roundtrip import _build_cpc_figure

    fig1, ax1, ax2a, sc_c1, sc_d1, sc_e1, _ = _build_cpc_figure()
    fig2, ax2, ax2b, sc_c2, sc_d2, sc_e2, _ = _build_cpc_figure()
    ax1.set_xlabel("Cycle number")
    ax2.set_xlabel("Cycle number")
    ax1.set_ylabel("Capacity")
    ax2.set_ylabel("Capacity")
    p1 = CpcPanel(
        path="a.pkl", fig=fig1, ax=ax1, ax2=ax2a,
        sc_charge=sc_c1, sc_discharge=sc_d1, sc_eff=sc_e1,
    )
    p2 = CpcPanel(
        path="b.pkl", fig=fig2, ax=ax2, ax2=ax2b,
        sc_charge=sc_c2, sc_discharge=sc_d2, sc_eff=sc_e2,
    )
    try:
        ax1.set_xlabel("Cycle #")
        ax1._stored_xlabel = "Cycle #"
        ax1.set_ylabel("Specific capacity")
        ax1._stored_ylabel = "Specific capacity"
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=cpc_capture, apply_cfg=apply_cpc_labels_only
        )
        assert ax2.get_xlabel() == "Cycle #"
        assert ax2.get_ylabel() == "Specific capacity"
        cfg2 = cpc_capture(p2)
        assert (cfg2.get("axis_labels") or {}).get("xlabel") == "Cycle #"
        assert (cfg2.get("axis_labels") or {}).get("ylabel_left") == "Specific capacity"
    finally:
        plt.close(fig1)
        plt.close(fig2)

"""Batch CPC key isolation: each sync key must not hitchhike peers.

Also locks single-file ``ie`` through p/i/s/b (+ old pkl BC).
"""

from __future__ import annotations

import inspect
import pickle

import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.colors import to_hex

from batplot.plot_modes.batch_session.cpc_batch_helpers import (
    apply_cpc_colors_only,
    apply_cpc_labels_only,
    apply_cpc_legend_only,
    apply_cpc_wasd_chrome_only,
)
from batplot.plot_modes.batch_session.load import CpcPanel
from batplot.plot_modes.batch_session.menu_cpc import (
    _apply_cpc_style,
    _capture_panel as cpc_capture,
    _invert_efficiency_all,
    _print_cpc_batch_menu,
    _restore_panel,
    _save_cpc_panel,
)
from batplot.plot_modes.batch_session.operando_batch_helpers import sync_style_from_ref
from batplot.plot_modes.cpc.session import load_cpc_session
import batplot.plot_modes.batch_session.menu_cpc as menu_cpc


def _strip_ansi(text: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _scatter_hex(sc) -> str:
    fc = np.asarray(sc.get_facecolor()).reshape(-1, 4)[0][:3]
    return to_hex(fc)


def _cpc_panel(path: str = "a.pkl") -> CpcPanel:
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc_c = ax.scatter([1, 2], [10, 20], color="C0")
    sc_d = ax.scatter([1, 2], [8, 18], color="C1")
    sc_e = ax2.scatter([1, 2], [90, 95], color="C2")
    return CpcPanel(
        path=path,
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
        file_data=None,
        tick_state={},
    )


def _two_cpc_panels():
    panels = []
    for i, (c_col, d_col, e_col, lw) in enumerate(
        (
            ("#111111", "#222222", "#333333", 1.0),
            ("#00aa00", "#00bb00", "#00cc00", 2.5),
        )
    ):
        fig, ax = plt.subplots()
        ax2 = ax.twinx()
        sc_c = ax.scatter([1, 2], [10, 20], color=c_col, s=36)
        sc_d = ax.scatter([1, 2], [8, 18], color=d_col, s=36)
        sc_e = ax2.scatter([1, 2], [90, 95], color=e_col, s=36)
        ax.set_xlabel(f"Cycle-{i}")
        ax._stored_xlabel = f"Cycle-{i}"
        ax.set_ylabel("Capacity")
        ax._stored_ylabel = "Capacity"
        ax2.set_ylabel("CE (%)")
        ax2._stored_ylabel = "CE (%)"
        ax.set_xlim(0, 10 + 10 * i)
        ax.spines["bottom"].set_linewidth(lw)
        fig._cpc_display_mode = "both"
        panels.append(
            CpcPanel(
                path=f"cpc_{i}.pkl",
                fig=fig,
                ax=ax,
                ax2=ax2,
                sc_charge=sc_c,
                sc_discharge=sc_d,
                sc_eff=sc_e,
                file_data=None,
                tick_state={},
            )
        )
    return panels


def test_batch_cpc_menu_lists_keys(capsys):
    p1, p2 = _two_cpc_panels()
    try:
        _print_cpc_batch_menu([p1, p2])
        out = _strip_ansi(capsys.readouterr().out)
        for token in (
            "font",
            "line widths",
            "marker sizes",
            "display (Chg/Dch)",
            "efficiency",
            "spines/ticks",
            "legend",
            "size",
            "colors",
            "rename",
            "x range",
            "y ranges",
            "invert efficiency",
            "overview",
            "export style",
            "undo",
        ):
            assert token in out, f"missing {token!r}"
        assert "Not in batch" not in out
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_cpc_l_menu_includes_grid():
    src = inspect.getsource(menu_cpc.run_cpc_batch_menu)
    assert 'sub == "g"' in src
    assert "toggle grid" in src.lower() or "grid lines" in src.lower()


def test_batch_cpc_c_keeps_peer_labels_widths_limits():
    p1, p2 = _two_cpc_panels()
    try:
        p1.sc_charge.set_facecolor("#ff0000")
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=cpc_capture, apply_cfg=apply_cpc_colors_only
        )
        assert _scatter_hex(p2.sc_charge) == "#ff0000"
        assert p2.ax.get_xlabel() == "Cycle-1"
        assert p2.ax.spines["bottom"].get_linewidth() == pytest.approx(2.5)
        assert p2.ax.get_xlim() == pytest.approx((0, 20))
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_cpc_t_keeps_peer_colors():
    p1, p2 = _two_cpc_panels()
    try:
        p1.fig._cpc_wasd_state = {
            "top": {"spine": True, "ticks": True, "labels": True, "title": False, "minor": False},
            "bottom": {"spine": True, "ticks": True, "labels": True, "title": True, "minor": False},
            "left": {"spine": True, "ticks": True, "labels": True, "title": True, "minor": False},
            "right": {"spine": True, "ticks": True, "labels": True, "title": True, "minor": False},
        }
        peer_color = _scatter_hex(p2.sc_charge)
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=cpc_capture, apply_cfg=apply_cpc_wasd_chrome_only
        )
        assert _scatter_hex(p2.sc_charge) == peer_color
        assert p2.ax.get_xlim() == pytest.approx((0, 20))
        assert p2.ax.spines["bottom"].get_linewidth() == pytest.approx(2.5)
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_cpc_r_syncs_top_xlabel_keeps_colors():
    p1, p2 = _two_cpc_panels()
    try:
        p1.ax.set_xlabel("New X")
        p1.ax._stored_xlabel = "New X"
        p1.ax._stored_top_xlabel = "New X"
        # Peer has visible top title with stale text.
        p2.ax._stored_top_xlabel = "Cycle-1"
        p2.ax._top_xlabel_on = True
        p2.ax._top_xlabel_text = p2.ax.text(
            0.5, 1.02, "Cycle-1", transform=p2.ax.transAxes, visible=True
        )
        peer_color = _scatter_hex(p2.sc_charge)
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=cpc_capture, apply_cfg=apply_cpc_labels_only
        )
        assert p2.ax.get_xlabel() == "New X"
        assert getattr(p2.ax, "_stored_top_xlabel", None) == "New X"
        assert p2.ax._top_xlabel_text.get_text() == "New X"
        assert _scatter_hex(p2.sc_charge) == peer_color
        assert p2.ax.get_xlim() == pytest.approx((0, 20))
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_cpc_h_keeps_peer_colors():
    p1, p2 = _two_cpc_panels()
    try:
        p1.fig._cpc_legend_xy_in = (0.4, 0.4)
        p2.fig._cpc_legend_xy_in = (0.1, 0.1)
        peer_color = _scatter_hex(p2.sc_charge)
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=cpc_capture, apply_cfg=apply_cpc_legend_only
        )
        assert _scatter_hex(p2.sc_charge) == peer_color
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_cpc_ie_converges_to_ref_target():
    """Panels with mismatched invert flags must converge, not stay mirrored."""
    p1, p2 = _two_cpc_panels()
    try:
        # Seed: ref normal, peer already inverted (desynced).
        p1.fig._cpc_eff_inverted = False
        p2.fig._cpc_eff_inverted = True
        ys2_before = np.asarray(p2.sc_eff.get_offsets())[:, 1].copy()
        # Flip peer offsets to match "inverted" geometry.
        off = p2.sc_eff.get_offsets()
        p2.sc_eff.set_offsets(list(zip(off[:, 0], 200.0 - off[:, 1])))
        ys2_inverted = np.asarray(p2.sc_eff.get_offsets())[:, 1].copy()

        new_inv = _invert_efficiency_all([p1, p2])
        assert new_inv is True
        assert getattr(p1.fig, "_cpc_eff_inverted", False) is True
        assert getattr(p2.fig, "_cpc_eff_inverted", False) is True
        # Peer was already inverted → must NOT flip again (stay at inverted ys).
        assert np.asarray(p2.sc_eff.get_offsets())[:, 1] == pytest.approx(ys2_inverted)
        # Ref was normal → must flip to inverted.
        ys1 = np.asarray(p1.sc_eff.get_offsets())[:, 1]
        assert ys1 == pytest.approx(200.0 - np.array([90.0, 95.0]))

        # Second call restores both.
        new_inv2 = _invert_efficiency_all([p1, p2])
        assert new_inv2 is False
        assert getattr(p1.fig, "_cpc_eff_inverted", True) is False
        assert getattr(p2.fig, "_cpc_eff_inverted", True) is False
        assert np.asarray(p2.sc_eff.get_offsets())[:, 1] == pytest.approx(ys2_before)
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_cpc_style_apply_xlabel_updates_top_title():
    from batplot.plot_modes.cpc.style import _apply_style

    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc_c = ax.scatter([1], [1])
    sc_d = ax.scatter([1], [2])
    sc_e = ax2.scatter([1], [90])
    ax._stored_top_xlabel = "Old"
    ax._top_xlabel_text = ax.text(0.5, 1.02, "Old", transform=ax.transAxes, visible=True)
    cfg = {
        "kind": "cpc_style",
        "axis_labels": {"xlabel": "Synced", "ylabel_left": "Cap", "ylabel_right": "CE"},
        "grid": False,
        "display_mode": "both",
        "series": {
            "charge": {"color": "#111111", "alpha": 1.0, "hollow": False, "markersize": 36},
            "discharge": {"color": "#222222", "alpha": 1.0, "hollow": False, "markersize": 36},
            "efficiency": {"color": "#333333", "alpha": 1.0, "hollow": False, "markersize": 36},
        },
    }
    try:
        _apply_style(fig, ax, ax2, sc_c, sc_d, sc_e, cfg, None)
        assert ax.get_xlabel() == "Synced"
        assert getattr(ax, "_stored_top_xlabel", None) == "Synced"
        assert ax._top_xlabel_text.get_text() == "Synced"
    finally:
        plt.close(fig)


def test_cpc_single_file_ie_undo_export_import_session(tmp_path):
    p = _cpc_panel("a.pkl")
    try:
        ys0 = p.sc_eff.get_offsets()[:, 1].copy()
        snap0 = cpc_capture(p)
        assert snap0.get("eff_inverted") is False

        _invert_efficiency_all([p])
        ys1 = p.sc_eff.get_offsets()[:, 1].copy()
        assert np.allclose(ys1, 200.0 - ys0)
        assert getattr(p.fig, "_cpc_eff_inverted") is True
        snap1 = cpc_capture(p)
        assert snap1.get("eff_inverted") is True

        _restore_panel(p, snap0)
        assert np.allclose(p.sc_eff.get_offsets()[:, 1], ys0)
        assert getattr(p.fig, "_cpc_eff_inverted") is False

        _invert_efficiency_all([p])
        cfg = cpc_capture(p)
        cfg["kind"] = "cpc_style"
        p2 = _cpc_panel("b.pkl")
        try:
            assert _apply_cpc_style(p2, cfg, apply_geometry=False) is True
            assert np.allclose(p2.sc_eff.get_offsets()[:, 1], 200.0 - ys0)
            assert getattr(p2.fig, "_cpc_eff_inverted") is True
        finally:
            plt.close(p2.fig)

        pkl = tmp_path / "cpc.pkl"
        _save_cpc_panel(p, str(pkl))
        loaded = load_cpc_session(str(pkl))
        assert loaded is not None
        fig_l, _ax_l, _ax2_l, _sc_c, _sc_d, sc_e, _file_data = loaded
        assert getattr(fig_l, "_cpc_eff_inverted", False) is True
        assert np.allclose(sc_e.get_offsets()[:, 1], 200.0 - ys0)
        plt.close(fig_l)
    finally:
        plt.close(p.fig)


def test_cpc_old_pkl_without_eff_inverted_still_loads(tmp_path):
    """Backward compatible: missing top-level eff_inverted defaults False."""
    p = _cpc_panel("a.pkl")
    try:
        pkl = tmp_path / "old.pkl"
        _save_cpc_panel(p, str(pkl))
        with open(pkl, "rb") as fh:
            meta = pickle.load(fh)
        meta.pop("eff_inverted", None)
        with open(pkl, "wb") as fh:
            pickle.dump(meta, fh)
        loaded = load_cpc_session(str(pkl))
        assert loaded is not None
        fig_l = loaded[0]
        assert getattr(fig_l, "_cpc_eff_inverted", False) is False
        plt.close(fig_l)
    finally:
        plt.close(p.fig)

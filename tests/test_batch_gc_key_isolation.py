"""Batch GC (ec_gc) key/subkey isolation: each sync key must not hitchhike peers.

Covers confirmed regressions for ``c``→``l``, ``t``→``r`` (dual xlabel), and
``x``/``y`` nice-ticks / dual reseal parity with interactive GC.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import matplotlib.pyplot as plt
import pytest
from matplotlib.colors import to_hex

from batplot.plot_modes.batch_session.ec_batch_helpers import (
    apply_ec_cycles_colors_only,
    apply_ec_labels_only,
    apply_ec_legend_only,
    apply_ec_line_chrome_only,
    apply_ec_spine_colors_only,
    apply_ec_wasd_chrome_only,
    ec_apply_display_mode,
)
from batplot.plot_modes.batch_session.load import EcPanel
from batplot.plot_modes.batch_session.menu_ec import (
    _capture_panel as ec_capture,
    _print_ec_batch_menu,
)
from batplot.plot_modes.batch_session.operando_batch_helpers import sync_style_from_ref
import batplot.plot_modes.batch_session.menu_ec as menu_ec


def _strip_ansi(text: str) -> str:
    import re

    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _two_gc_panels(*, dual: bool = False):
    fig1, ax1 = plt.subplots()
    fig2, ax2 = plt.subplots()
    c1 = ax1.plot([0, 1], [0, 1], color="#111111", lw=1.0)[0]
    d1 = ax1.plot([0, 1], [1, 0], color="#222222", lw=1.0)[0]
    c2 = ax2.plot([0, 1], [0, 1], color="#333333", lw=3.0)[0]
    d2 = ax2.plot([0, 1], [1, 0], color="#444444", lw=3.0)[0]
    ax1.set_xlabel("Potential (V)")
    ax2.set_xlabel("Potential (V)")
    ax1._stored_xlabel = "Potential (V)"
    ax2._stored_xlabel = "Potential (V)"
    ax1.set_ylabel("Capacity")
    ax2.set_ylabel("Capacity")
    ax1._stored_ylabel = "Capacity"
    ax2._stored_ylabel = "Capacity"
    ax1.set_xlim(0, 10)
    ax2.set_xlim(0, 100)
    fig1._ec_curve_linewidth = 1.0
    fig2._ec_curve_linewidth = 3.0
    fig1._ec_display_mode = "both"
    fig2._ec_display_mode = "both"
    if dual:
        fig1._ec_xaxis_mode = "dual"
        fig2._ec_xaxis_mode = "dual"
        fig1._ec_c_theoretical = 100.0
        fig2._ec_c_theoretical = 150.0
    p1 = EcPanel(
        path="gc_a.pkl",
        fig=fig1,
        ax=ax1,
        cycle_lines={1: {"charge": c1, "discharge": d1}},
        file_data=None,
    )
    p2 = EcPanel(
        path="gc_b.pkl",
        fig=fig2,
        ax=ax2,
        cycle_lines={1: {"charge": c2, "discharge": d2}},
        file_data=None,
    )
    return p1, p2


def test_batch_gc_menu_lists_gc_keys_and_rejects_dqdv_only(capsys):
    p1, p2 = _two_gc_panels()
    try:
        _print_ec_batch_menu([p1, p2])
        out = _strip_ansi(capsys.readouterr().out)
        for token in (
            "font",
            "line style",
            "spines/ticks",
            "spine colors",
            "legend",
            "display (Chg/Dch)",
            "size",
            "cycles/colors",
            "rename",
            "x range",
            "y range",
            "overview",
            "export style",
            "import style",
            "undo",
        ):
            assert token in out, f"missing {token!r}"
        assert "Not in batch" not in out
        assert "smooth" not in out.lower()
        src = inspect.getsource(menu_ec.run_ec_batch_menu)
        assert 'if cmd == "a":' in src
        assert 'if cmd == "2d":' in src
        assert "apply_ec_smooth_only" in src  # dQdV-only path exists
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_gc_c_does_not_hitchhike_peer_linewidth():
    """``c`` syncs colors; peer ``l`` linewidth must stay local."""
    p1, p2 = _two_gc_panels()
    try:
        p1.cycle_lines[1]["charge"].set_color("#ff0000")
        p1.cycle_lines[1]["charge"].set_linewidth(1.0)
        p2.cycle_lines[1]["charge"].set_color("#00aa00")
        p2.cycle_lines[1]["charge"].set_linewidth(3.0)
        p2.cycle_lines[1]["discharge"].set_linewidth(3.0)
        p1.ax.set_xlabel("Ref X")
        p1.ax._stored_xlabel = "Ref X"
        p2.ax.set_xlabel("Peer X")
        p2.ax._stored_xlabel = "Peer X"
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=ec_capture, apply_cfg=apply_ec_cycles_colors_only
        )
        assert to_hex(p2.cycle_lines[1]["charge"].get_color()) == "#ff0000"
        assert p2.cycle_lines[1]["charge"].get_linewidth() == pytest.approx(3.0)
        assert p2.cycle_lines[1]["discharge"].get_linewidth() == pytest.approx(3.0)
        assert getattr(p2.fig, "_ec_curve_linewidth", None) == pytest.approx(3.0)
        assert p2.ax.get_xlabel() == "Peer X"
        assert p2.ax.get_xlim() == pytest.approx((0, 100))
        assert getattr(p2.fig, "_ec_display_mode", "both") == "both"
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_gc_l_does_not_hitchhike_peer_colors():
    p1, p2 = _two_gc_panels()
    try:
        p1.cycle_lines[1]["charge"].set_color("#ff0000")
        p1.cycle_lines[1]["charge"].set_linewidth(2.5)
        p1.fig._ec_curve_linewidth = 2.5
        p2.cycle_lines[1]["charge"].set_color("#00aa00")
        p2.cycle_lines[1]["charge"].set_linewidth(1.0)
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=ec_capture, apply_cfg=apply_ec_line_chrome_only
        )
        assert p2.cycle_lines[1]["charge"].get_linewidth() == pytest.approx(2.5)
        assert to_hex(p2.cycle_lines[1]["charge"].get_color()) == "#00aa00"
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_gc_t_does_not_hitchhike_dual_top_xlabel():
    """``t`` may sync dual top chrome, but not ``r``-owned top xlabel text."""
    import copy

    from batplot.plot_modes.batch_session import ec_batch_helpers as eh

    p1, p2 = _two_gc_panels(dual=True)
    try:
        ref_cfg = ec_capture(p1)
        ref_cfg["xaxis_dual"] = {
            "mode": "dual",
            "c_theoretical": 100.0,
            "swapped": False,
            "top_axis": {
                "xlabel": "ions_ref",
                "labelpad": 12.0,
                "visible": True,
                "spine_visible": True,
                "ticks": True,
                "labels": True,
            },
        }
        peer_xd = {
            "mode": "dual",
            "c_theoretical": 150.0,
            "swapped": False,
            "top_axis": {
                "xlabel": "Li+",
                "labelpad": 4.0,
                "visible": True,
                "spine_visible": True,
                "ticks": False,
                "labels": False,
            },
        }
        original = eh._peer_ec_style_snapshot

        def _seeded(panel):
            out = original(panel)
            if panel is p2:
                out["xaxis_dual"] = copy.deepcopy(peer_xd)
            return out

        seen = {}

        def _capture_apply(cfg, **kwargs):
            seen["xaxis_dual"] = copy.deepcopy(cfg.get("xaxis_dual"))
            return True

        eh._peer_ec_style_snapshot = _seeded  # type: ignore[assignment]
        real_apply = eh.apply_ec_style_config
        eh.apply_ec_style_config = _capture_apply  # type: ignore[assignment]
        try:
            apply_ec_wasd_chrome_only(p2, ref_cfg)
        finally:
            eh._peer_ec_style_snapshot = original  # type: ignore[assignment]
            eh.apply_ec_style_config = real_apply  # type: ignore[assignment]

        xd = seen.get("xaxis_dual") or {}
        top = xd.get("top_axis") or {}
        assert top.get("xlabel") == "Li+"
        assert top.get("labelpad") == pytest.approx(12.0)
        assert top.get("ticks") is True
        assert xd.get("c_theoretical") == pytest.approx(150.0)
        assert p2.ax.get_xlabel() == "Potential (V)"
        assert p2.cycle_lines[1]["charge"].get_linewidth() == pytest.approx(3.0)
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_gc_t_xaxis_dual_merge_skips_xlabel():
    """Direct contract: WASD dual merge field list excludes xlabel."""
    src = Path(menu_ec.__file__).resolve().parents[0] / "ec_batch_helpers.py"
    text = src.read_text(encoding="utf-8")
    # The dual-top chrome loop must not include xlabel (owned by r).
    start = text.index('if key == "xaxis_dual":')
    chunk = text[start : start + 1600]
    assert '"labelpad"' in chunk
    assert '"spine_visible"' in chunk
    # xlabel must not appear in the for-fld tuple of that block.
    fld_start = chunk.index("for fld in (")
    fld_end = chunk.index("):", fld_start)
    fld_block = chunk[fld_start:fld_end]
    assert '"xlabel"' not in fld_block
    assert '"labelpad"' in fld_block


def test_batch_gc_r_keeps_peer_colors_and_limits():
    p1, p2 = _two_gc_panels()
    try:
        p1.ax.set_xlabel("New X")
        p1.ax._stored_xlabel = "New X"
        p2.cycle_lines[1]["charge"].set_color("#00aa00")
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=ec_capture, apply_cfg=apply_ec_labels_only
        )
        assert p2.ax.get_xlabel() == "New X"
        assert to_hex(p2.cycle_lines[1]["charge"].get_color()) == "#00aa00"
        assert p2.ax.get_xlim() == pytest.approx((0, 100))
        assert p2.cycle_lines[1]["charge"].get_linewidth() == pytest.approx(3.0)
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_gc_k_keeps_curve_colors_and_linewidth():
    p1, p2 = _two_gc_panels()
    try:
        p1.ax.spines["bottom"].set_color("#0000ff")
        p2.ax.spines["bottom"].set_color("#111111")
        p2.cycle_lines[1]["charge"].set_color("#00aa00")
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=ec_capture, apply_cfg=apply_ec_spine_colors_only
        )
        assert to_hex(p2.ax.spines["bottom"].get_edgecolor()) == "#0000ff"
        assert to_hex(p2.cycle_lines[1]["charge"].get_color()) == "#00aa00"
        assert p2.cycle_lines[1]["charge"].get_linewidth() == pytest.approx(3.0)
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_gc_h_keeps_peer_colors():
    p1, p2 = _two_gc_panels()
    try:
        p1.fig._ec_legend_xy_in = (0.4, 0.4)
        p2.fig._ec_legend_xy_in = (0.1, 0.1)
        p1.fig._ec_legend_user_visible = True
        p2.fig._ec_legend_user_visible = True
        p2.cycle_lines[1]["charge"].set_color("#00aa00")
        sync_style_from_ref(
            p1, [p1, p2], capture_panel=ec_capture, apply_cfg=apply_ec_legend_only
        )
        assert getattr(p2.fig, "_ec_legend_xy_in", None) == pytest.approx((0.4, 0.4))
        assert to_hex(p2.cycle_lines[1]["charge"].get_color()) == "#00aa00"
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_gc_d_display_all_panels_keeps_colors():
    p1, p2 = _two_gc_panels()
    try:
        p2.cycle_lines[1]["charge"].set_color("#00aa00")
        for p in (p1, p2):
            ec_apply_display_mode(
                "charge",
                cycle_lines=p.cycle_lines,
                file_data=p.file_data,
                is_multi_file=False,
            )
            p.fig._ec_display_mode = "charge"
        assert p1.cycle_lines[1]["charge"].get_visible() is True
        assert p1.cycle_lines[1]["discharge"].get_visible() is False
        assert p2.cycle_lines[1]["discharge"].get_visible() is False
        assert to_hex(p2.cycle_lines[1]["charge"].get_color()) == "#00aa00"
        assert p2.cycle_lines[1]["charge"].get_linewidth() == pytest.approx(3.0)
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_batch_gc_xy_range_calls_nice_ticks_and_reseal():
    """Interactive parity: batch x/y must reseal after set_lim (dual locators)."""
    src = inspect.getsource(menu_ec.run_ec_batch_menu)
    # Both branches must call nice ticks + reseal (not only g).
    assert src.count("ec_apply_nice_ticks(p.ax)") >= 3  # g + x + y
    assert "reseal_ec_chrome" in src
    assert 'if cmd == "x":' in src
    assert 'if cmd == "y":' in src
    # x/y blocks must include reseal (not only g).
    x_idx = src.index('if cmd == "x":')
    y_idx = src.index('if cmd == "y":')
    o_idx = src.index('if cmd == "o":')
    assert "reseal_ec_chrome" in src[x_idx:y_idx]
    assert "reseal_ec_chrome" in src[y_idx:o_idx]
    assert "ec_apply_nice_ticks" in src[x_idx:y_idx]
    assert "ec_apply_nice_ticks" in src[y_idx:o_idx]


def test_batch_gc_overlay_cycle_styles_keeps_line_chrome():
    from batplot.plot_modes.batch_session.ec_batch_helpers import (
        _overlay_cycle_styles_colors,
    )

    peer = {
        1: {
            "charge": {
                "color": "#00aa00",
                "linewidth": 3.0,
                "linestyle": "--",
                "marker": "o",
                "markersize": 6,
            }
        }
    }
    ref = {
        1: {
            "charge": {
                "color": "#ff0000",
                "linewidth": 1.0,
                "linestyle": "-",
                "marker": None,
                "markersize": 0,
            }
        }
    }
    out = _overlay_cycle_styles_colors(peer, ref)
    assert out[1]["charge"]["color"] == "#ff0000"
    assert out[1]["charge"]["linewidth"] == pytest.approx(3.0)
    assert out[1]["charge"]["linestyle"] == "--"
    assert out[1]["charge"]["marker"] == "o"
    assert out[1]["charge"]["markersize"] == 6

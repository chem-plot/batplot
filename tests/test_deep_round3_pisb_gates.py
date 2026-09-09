"""Hard gates for Round-3 deep dig: session / PISB / WASD / empty-title fidelity."""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot import session as S
from batplot.plot_modes.xy import style as ST


class _Args:
    stack = False
    xaxis = "2theta"
    norm = False
    autoscale = False


def test_ec_legend_title_empty_roundtrip():
    from batplot.plot_modes.electrochem.legend import _get_legend_title, _store_legend_title

    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1], label="1")
    leg = ax.legend()
    leg.set_title("")
    try:
        _store_legend_title(fig, ax)
        assert fig._ec_legend_title == ""
        assert _get_legend_title(fig) == ""
    finally:
        plt.close(fig)


def test_ec_curve_markers_session_load_applies(tmp_path):
    fig, ax = plt.subplots()
    (chg,) = ax.plot([0.0, 1.0], [3.0, 4.0], label="1 charge")
    (dch,) = ax.plot([1.0, 0.0], [4.0, 3.0], label="1 discharge")
    cycle_lines = {1: {"charge": chg, "discharge": dch}}
    chg.set_marker("s")
    chg.set_markersize(9.0)
    chg.set_linestyle("--")
    dch.set_marker("s")
    dch.set_markersize(9.0)
    dch.set_linestyle("--")
    path = tmp_path / "ec.pkl"
    try:
        S.dump_ec_session(str(path), fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)
        result = S.load_ec_session(str(path))
        assert result is not None
        fig2, ax2, _meta = result
        # Template restored on fig; per-line markers restored from lines_state.
        assert getattr(fig2, "_ec_curve_markers", {}).get("marker") == "s"
        assert getattr(fig2, "_ec_curve_markers", {}).get("markersize") == pytest.approx(9.0)
        assert any((ln2.get_marker() or "None") == "s" for ln2 in ax2.lines)
        plt.close(fig2)
    finally:
        plt.close(fig)


def test_dqdv_snapshot_includes_wasd_and_custom_labels():
    from batplot.plot_modes.electrochem.dqdv_2d import (
        build_dqdv_2d_snapshot,
        restore_dqdv_2d_companion_figure,
    )

    fig, ax = plt.subplots()
    Z = np.linspace(0, 1, 20).reshape(4, 5)
    im = ax.imshow(Z, origin="lower", extent=(0, 2, -0.5, 3.5), aspect="auto")
    ax.set_xlabel("Potential")
    ax.set_ylabel("Cycle")
    ax.xaxis.label.set_visible(False)
    ax._custom_labels = {"x": "", "y": "Rows"}
    ax._saved_tick_state = {"bx": True, "ly": True, "tx": False, "ry": False}
    cbar_ax = fig.add_axes((0.9, 0.1, 0.02, 0.8))

    class _CB:
        def __init__(self, cax):
            self.ax = cax

    try:
        snap = build_dqdv_2d_snapshot(
            fig, ax, im, 2.0, 4.0, ["1", "2", "3", "4"], "dQ/dV", cbar=_CB(cbar_ax)
        )
        assert snap is not None
        assert "wasd_state" in snap
        assert snap["wasd_state"]["bottom"]["title"] is False
        assert snap.get("custom_labels", {}).get("x") == ""
        assert snap.get("custom_labels", {}).get("y") == "Rows"

        restored = restore_dqdv_2d_companion_figure(snap)
        assert restored is not None
        cfig, cax, _im, _cbar = restored
        assert cax.get_ylabel() == "Rows"
        assert cax.get_xlabel() == ""
        assert cax.xaxis.label.get_visible() is False
        assert getattr(cax, "_custom_labels", {}).get("x") == ""
        plt.close(cfig)
    finally:
        plt.close(fig)


def test_operando_style_wasd_title_uses_visibility():
    from batplot.plot_modes.operando.style import build_operando_ec_style_config_v2

    fig, ax = plt.subplots()
    ax.set_xlabel("2theta")
    ax.set_ylabel("Intensity")
    ax.xaxis.label.set_visible(False)
    ax.yaxis.label.set_visible(False)
    im = ax.imshow([[0, 1], [1, 0]])
    cbar = fig.colorbar(im, ax=ax)
    try:
        cfg, _ext = build_operando_ec_style_config_v2(fig, ax, im, cbar, None, "ps")
        wasd = (cfg.get("operando") or {}).get("wasd_state") or {}
        assert wasd["bottom"]["title"] is False
        assert wasd["left"]["title"] is False
    finally:
        plt.close(fig)


def test_axis_state_title_prefers_visibility_not_text():
    from batplot.plot_modes.common.axis_state import capture_axis_wasd_state

    fig, ax = plt.subplots()
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.xaxis.label.set_visible(False)
    ax.yaxis.label.set_visible(False)
    try:
        wasd = capture_axis_wasd_state(ax, use_actual_major_visibility=True)
        assert wasd["bottom"]["title"] is False
        assert wasd["left"]["title"] is False
        wasd2 = capture_axis_wasd_state(
            ax, use_actual_major_visibility=True, use_right_ylabel_position=True
        )
        assert wasd2["bottom"]["title"] is False
        assert wasd2["left"]["title"] is False
    finally:
        plt.close(fig)


def test_xy_style_preserves_empty_twin_ylabel_and_ylim_right(tmp_path):
    fig, ax = plt.subplots()
    (ln0,) = ax.plot([0, 1], [1, 2])
    (ln1,) = ax.plot([0, 1], [3, 4])
    fig._xy_lines_by_curve = [ln0, ln1]
    ST._apply_xy_dual_y_layout(fig, ax, frozenset({1}), use_top_x=False)
    ax2 = getattr(fig, "_xy_ax2")
    assert ax2 is not None
    ax2.set_ylabel("")
    ax2.set_ylim(3.0, 7.0)
    style_path = tmp_path / "ry.bpsg"
    try:
        ST.export_style_config(
            str(style_path),
            fig,
            ax,
            [np.array([1, 2]), np.array([3, 4])],
            ["a", "b"],
            0.0,
            _Args(),
            {},
            [0.0, 0.0],
            overwrite_path=str(style_path),
            force_kind="psg",
        )
        payload = json.loads(style_path.read_text(encoding="utf-8"))
        assert payload["axis_title_texts"]["right_y"] == ""
        assert payload["geometry"]["ylim_right"][0] == pytest.approx(3.0)
        assert payload["geometry"]["ylim_right"][1] == pytest.approx(7.0)

        ax2.set_ylabel("TEMP")
        ax2.set_ylim(0.0, 1.0)
        ok = ST.apply_style_config(
            str(style_path),
            fig,
            ax,
            [np.array([0.0, 1.0]), np.array([0.0, 1.0])],
            [np.array([1.0, 2.0]), np.array([3.0, 4.0])],
            [np.array([1.0, 2.0]), np.array([3.0, 4.0])],
            [0.0, 0.0],
            [],
            _Args(),
            {},
            ["a", "b"],
            update_labels_func=lambda *a, **k: None,
        )
        assert ok is True
        assert fig._xy_ax2.get_ylabel() == ""
        y0, y1 = fig._xy_ax2.get_ylim()
        assert y0 == pytest.approx(3.0)
        assert y1 == pytest.approx(7.0)
    finally:
        plt.close(fig)


def test_cpc_efficiency_right_spine_checks_ax2():
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "batplot/plot_modes/cpc/panel_menus.py"
    text = src.read_text(encoding="utf-8")
    assert "bool(ax2.spines.get('right').get_visible()) if ax2.spines.get('right')" in text


def test_line_style_menus_validate_before_push():
    from pathlib import Path

    texts = {
        Path("batplot/plot_modes/xy/line_style.py"): 'push_state("framewidth")',
        Path("batplot/plot_modes/electrochem/line_style.py"): 'push_state("framewidth")',
        Path("batplot/plot_modes/cpc/panel_menus.py"): 'push_state("framewidth")',
        Path("batplot/plot_modes/histo/line_style.py"): "push_state()",
    }
    for path, push_token in texts.items():
        text = path.read_text(encoding="utf-8")
        parse_idx = text.find("parse_frame_tick_widths")
        push_idx = text.find(push_token, parse_idx)
        assert parse_idx >= 0, path
        assert push_idx > parse_idx, f"{path}: push must follow parse"

"""Hard gates for Round-6 session fidelity: spines/WASD/geometry round-trip."""

from __future__ import annotations

import copy
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.common.spines import wasd_to_tick_state
from batplot.plot_modes.electrochem.dqdv_2d import build_dqdv_2d_snapshot, restore_dqdv_2d_companion_figure


def test_wasd_legacy_keys_use_ticks_and_labels():
    wasd = {
        "bottom": {"ticks": True, "labels": False, "minor": False, "spine": True, "title": True},
        "top": {"ticks": False, "labels": False, "minor": False, "spine": False, "title": False},
        "left": {"ticks": True, "labels": True, "minor": False, "spine": True, "title": True},
        "right": {"ticks": False, "labels": False, "minor": False, "spine": False, "title": False},
    }
    ts = wasd_to_tick_state(
        wasd,
        tick_defaults={"top": False, "bottom": True, "left": True, "right": False},
        label_defaults={"top": False, "bottom": True, "left": True, "right": False},
    )
    assert ts["b_ticks"] is True
    assert ts["b_labels"] is False
    assert ts["bx"] is False  # AND, not OR / ticks-only


def test_xy_load_seeds_bp_wasd_state():
    src = Path("batplot/plot_modes/xy/session.py").read_text(encoding="utf-8")
    assert "fig._bp_wasd_state = copy.deepcopy(wasd_loaded)" in src
    assert "fig._bp_wasd_state = copy.deepcopy(wasd)" in src
    assert "wasd_to_tick_state" in src


def test_ec_load_tick_state_uses_side_defaults():
    src = Path("batplot/plot_modes/electrochem/session.py").read_text(encoding="utf-8")
    idx = src.find("# Store WASD state")
    assert idx >= 0
    region = src[idx : idx + 900]
    assert "wasd_to_tick_state" in region
    assert "s.get('ticks', False)" not in region
    assert "'bottom': True" in region


def test_ec_style_apply_legacy_not_or():
    src = Path("batplot/plot_modes/electrochem/style_apply.py").read_text(encoding="utf-8")
    assert "bot_s.get('labels', True) or bot_s.get('ticks', True)" not in src
    assert "wasd_to_tick_state" in src


def test_operando_tick_widths_is_not_none():
    for path in (
        "batplot/plot_modes/operando/session.py",
        "batplot/plot_modes/operando/style_apply.py",
    ):
        src = Path(path).read_text(encoding="utf-8")
        assert "if op_tick_widths.get('x_major'):" not in src
        assert "if op_tick_widths.get('x_major') is not None" in src


def test_cpc_marker_size_zero_preserved_on_load():
    src = Path("batplot/plot_modes/cpc/session.py").read_text(encoding="utf-8")
    assert "rec.get('size', 32.0) or 32.0" not in src
    assert "32.0 if _sz is None else _sz" in src


def test_cpc_top_title_dump_uses_flag():
    for path in (
        "batplot/plot_modes/cpc/session.py",
        "batplot/plot_modes/cpc/style.py",
    ):
        src = Path(path).read_text(encoding="utf-8")
        assert "getattr(ax, '_top_xlabel_on', False)" in src
    wasd = Path("batplot/plot_modes/cpc/wasd_menu.py").read_text(encoding="utf-8")
    assert "ax._top_xlabel_on = bool(wasd['top']['title'])" in wasd


def test_xy_tick_lengths_use_session_helper():
    src = Path("batplot/plot_modes/xy/session.py").read_text(encoding="utf-8")
    assert "tl.get('x_major') or tl.get('y_major')" not in src
    assert "_apply_session_tick_lengths(fig, [ax], sess.get('tick_lengths'" in src


def test_cpc_load_tick_state_uses_wasd_to_tick_state():
    src = Path("batplot/plot_modes/cpc/session.py").read_text(encoding="utf-8")
    idx = src.find("Store tick_state on axes")
    assert idx >= 0
    region = src[idx : idx + 700]
    assert "wasd_to_tick_state" in region
    assert "tick_state['bx'] = tick_state.get('b_ticks'" not in region


def test_operando_title_hide_sets_label_visibility():
    sess = Path("batplot/plot_modes/operando/session.py").read_text(encoding="utf-8")
    assert "ax.xaxis.label.set_visible(False)" in sess
    assert "ax.yaxis.label.set_visible(False)" in sess
    assert "keep_yaxis_label_on_side(ec_ax, 'right', visible=False)" in sess
    inter = Path("batplot/plot_modes/operando/interactive.py").read_text(encoding="utf-8")
    # Interactive titles go through the shared store/clear+visibility helper.
    assert "set_primary_axis_title(" in inter
    apply = Path("batplot/plot_modes/operando/style_apply.py").read_text(encoding="utf-8")
    assert "set_primary_axis_title(" in apply


def test_dqdv_snapshot_includes_and_restores_axes_bbox():
    fig, ax = plt.subplots(figsize=(7.0, 5.0))
    try:
        ax.set_position([0.2, 0.15, 0.65, 0.7])
        Z = np.random.rand(4, 8)
        im = ax.imshow(Z, aspect="auto", origin="lower")
        cbar = type("C", (), {"ax": fig.add_axes([0, 0, 0.01, 0.01])})()
        snap = build_dqdv_2d_snapshot(
            fig, ax, im, 2.0, 4.0, ["1", "2", "3", "4"], "dQ/dV", cbar=cbar
        )
        assert snap is not None
        assert isinstance(snap.get("axes_bbox"), dict)
        assert abs(snap["axes_bbox"]["left"] - 0.2) < 1e-6
        # Mutate bbox in snap and restore
        snap = copy.deepcopy(snap)
        snap["axes_bbox"] = {"left": 0.11, "right": 0.88, "bottom": 0.12, "top": 0.91}
        out = restore_dqdv_2d_companion_figure(snap)
        assert out is not None
        cfig, cax, _im, _cbar = out
        bb = cax.get_position()
        assert abs(bb.x0 - 0.11) < 1e-6
        assert abs(bb.x1 - 0.88) < 1e-6
        plt.close(cfig)
    finally:
        plt.close(fig)

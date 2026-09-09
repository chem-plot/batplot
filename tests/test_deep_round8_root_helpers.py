"""Hard gates for Round-8 root-cause sweeps (tick length 0, WASD helpers, undo)."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from batplot.plot_modes.common.session_helpers import _current_tick_length, _first_defined
from batplot.plot_modes.common.spines import wasd_to_tick_state
from batplot.plot_modes.xy.spines import ensure_xy_tick_state
from batplot.ui import _resolve_tick_state


def test_current_tick_length_preserves_zero():
    fig, ax = plt.subplots()
    try:
        ax.tick_params(axis="both", which="major", length=0.0)
        assert _current_tick_length(ax.xaxis, "major") == 0.0
        assert _current_tick_length(ax.yaxis, "major") == 0.0
    finally:
        plt.close(fig)


def test_first_defined_keeps_zero():
    assert _first_defined(0.0, 5.0) == 0.0
    assert _first_defined(None, 0.0, 5.0) == 0.0
    assert _first_defined(None, None) is None


def test_operando_style_uses_shared_tick_length_helper():
    src = Path("batplot/plot_modes/operando/style.py").read_text(encoding="utf-8")
    assert "from ..common.session_helpers import _current_tick_length" in src
    assert 'tick_kw.get("size") or tick_kw.get("length")' not in src


def test_operando_interactive_and_batch_use_wasd_to_tick_state():
    interactive = Path("batplot/plot_modes/operando/interactive.py").read_text(
        encoding="utf-8"
    )
    assert "current_tick_state = wasd_to_tick_state(wasd_state)" in interactive
    assert "set_primary_axis_title(" in interactive
    batch = Path("batplot/plot_modes/batch_session/operando_batch_helpers.py").read_text(
        encoding="utf-8"
    )
    assert "_ax._saved_tick_state = wasd_to_tick_state(_wasd)" in batch
    assert '"tx": bool(_wasd["top"]["ticks"] and _wasd["top"]["labels"])' not in batch


def test_operando_style_apply_titles_use_set_primary_axis_title():
    src = Path("batplot/plot_modes/operando/style_apply.py").read_text(encoding="utf-8")
    assert "set_primary_axis_title(" in src
    assert "ax.xaxis.label.set_visible(bool(op_wasd.get('bottom'" not in src
    assert "op_tick_state = _resolve_tick_state(ax)" in src


def test_ensure_xy_tick_state_matches_resolve_empty_dict():
    class _Ax:
        _saved_tick_state = {"b_ticks": True}

    assert ensure_xy_tick_state(_Ax(), {}) == {}
    assert ensure_xy_tick_state(_Ax(), {}) == _resolve_tick_state(_Ax(), {})


def test_batch_cpc_load_empty_tick_state_authoritative():
    src = Path("batplot/plot_modes/batch_session/load.py").read_text(encoding="utf-8")
    assert 'isinstance(saved, dict) and saved' not in src
    assert "isinstance(saved_ax, dict)" in src


def test_cpc_efficiency_syncs_split_tick_keys():
    src = Path("batplot/plot_modes/cpc/panel_menus.py").read_text(encoding="utf-8")
    assert "sync_tick_state_from_wasd" in src
    idx = src.find("wasd['right']['ticks'] = bool(new_vis)")
    assert idx >= 0
    assert "sync_tick_state_from_wasd" in src[idx : idx + 800]


def test_cif_font_and_intensity_validate_then_push():
    cif = Path("batplot/plot_modes/operando/cif_menu.py").read_text(encoding="utf-8")
    font = cif[cif.find("elif sub == 'f':") : cif.find("elif sub == 'r':")]
    assert font.find("if not font_pushed:") < font.find('snapshot("cif-font")')
    assert font.find('snapshot("cif-font")') > font.find("while True:")
    intensity = Path("batplot/plot_modes/operando/intensity_menu.py").read_text(
        encoding="utf-8"
    )
    assert "pop_undo" in intensity
    assert "unchanged and pushed and pop_undo" in intensity


def test_wasd_to_tick_state_legacy_and():
    wasd = {
        "bottom": {"ticks": True, "labels": False, "minor": False},
        "top": {"ticks": False, "labels": False, "minor": False},
        "left": {"ticks": True, "labels": True, "minor": False},
        "right": {"ticks": True, "labels": False, "minor": True},
    }
    flat = wasd_to_tick_state(wasd)
    assert flat["bx"] is False
    assert flat["ry"] is False
    assert flat["mry"] is True

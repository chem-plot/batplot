"""Hard gates for Round-7 root-cause helper unification."""

from __future__ import annotations

from pathlib import Path

from batplot.plot_modes.common.interactive_state import build_saved_tick_state
from batplot.plot_modes.common.spines import (
    set_primary_axis_title,
    sync_legacy_tick_keys,
    wasd_to_tick_state,
)
from batplot.ui import _resolve_tick_state


def test_sync_legacy_tick_keys_uses_and_not_ticks_only():
    ts = {
        "b_ticks": True,
        "b_labels": False,
        "t_ticks": False,
        "t_labels": True,
        "l_ticks": True,
        "l_labels": True,
        "r_ticks": True,
        "r_labels": False,
    }
    sync_legacy_tick_keys(ts)
    assert ts["bx"] is False
    assert ts["tx"] is False
    assert ts["ly"] is True
    assert ts["ry"] is False


def test_build_saved_tick_state_matches_wasd_to_tick_state():
    wasd = {
        "bottom": {"ticks": True, "labels": False, "minor": False},
        "top": {"ticks": False, "labels": False, "minor": False},
        "left": {"ticks": True, "labels": True, "minor": True},
        "right": {"ticks": False, "labels": False, "minor": False},
    }
    defaults = {"top": False, "bottom": True, "left": True, "right": False}
    a = wasd_to_tick_state(wasd, tick_defaults=defaults, label_defaults=defaults)
    b = build_saved_tick_state(wasd, tick_defaults=defaults, label_defaults=defaults)
    assert a == b
    assert a["bx"] is False
    assert a["mly"] is True


def test_resolve_tick_state_accepts_empty_dict():
    class _Ax:
        _saved_tick_state = {"b_ticks": True, "bx": True}

    out = _resolve_tick_state(_Ax(), {})
    assert out == {}


def test_set_primary_axis_title_sets_visibility():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    try:
        ax.set_xlabel("Potential (V)")
        set_primary_axis_title(ax, "x", on=False, stored_attr="_stored_xlabel")
        assert ax.get_xlabel() == ""
        assert ax.xaxis.label.get_visible() is False
        assert getattr(ax, "_stored_xlabel") == "Potential (V)"
        set_primary_axis_title(ax, "x", on=True, stored_attr="_stored_xlabel")
        assert ax.get_xlabel() == "Potential (V)"
        assert ax.xaxis.label.get_visible() is True
    finally:
        plt.close(fig)


def test_batch_tick_helpers_use_wasd_to_tick_state():
    xy = Path("batplot/plot_modes/batch_session/xy_batch_helpers.py").read_text(
        encoding="utf-8"
    )
    assert "return wasd_to_tick_state(" in xy
    assert 'out["bx"] = out.get("b_ticks"' not in xy
    ec = Path("batplot/plot_modes/batch_session/ec_batch_helpers.py").read_text(
        encoding="utf-8"
    )
    assert "return wasd_to_tick_state(" in ec
    assert '"bx": bool(bot.get("ticks"' not in ec


def test_cpc_wasd_uses_set_primary_axis_title():
    src = Path("batplot/plot_modes/cpc/wasd_menu.py").read_text(encoding="utf-8")
    assert "set_primary_axis_title(" in src
    batch = Path("batplot/plot_modes/batch_session/cpc_batch_helpers.py").read_text(
        encoding="utf-8"
    )
    assert "set_primary_axis_title(" in batch


def test_legend_position_validates_before_push():
    src = Path("batplot/plot_modes/common/menus.py").read_text(encoding="utf-8")
    idx = src.find("def _push_then_apply")
    assert idx >= 0
    region = src[idx : idx + 400]
    assert "sanitize_offset(pos) is None" in region
    assert region.find("sanitize_offset(pos) is None") < region.find(
        'push_state("legend-position")'
    )


def test_session_font_early_blocks_use_shared_helper():
    for path in (
        "batplot/plot_modes/xy/session.py",
        "batplot/plot_modes/electrochem/session.py",
        "batplot/plot_modes/cpc/session.py",
        "batplot/plot_modes/operando/session.py",
    ):
        src = Path(path).read_text(encoding="utf-8")
        assert "sync_font_rcparams_from_cfg" in src
        assert "if f.get('size'):" not in src
        assert "if font_cfg.get('size'):" not in src

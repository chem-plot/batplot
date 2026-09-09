"""Hard gates: GC dual must not regenerate ghost spine / vanished ions title."""

from __future__ import annotations

import pickle
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.electrochem.dual_axis_menu import (
    _chrome_after_dual_recreate,
    _clear_dual_wasd_top_on_leave,
    _ensure_dual_wasd_top_defaults,
    _leave_dual_axis_chrome,
)
from batplot.plot_modes.electrochem.labels import _rename_bottom_x
from batplot.plot_modes.electrochem.session import dump_ec_session, load_ec_session
from batplot.plot_modes.electrochem.style import (
    _get_style_snapshot,
    apply_ec_dual_top_wasd,
    ec_dual_secax,
    suppress_ec_dual_duplicate_top_title,
)
from batplot.plot_modes.electrochem.style_apply import apply_ec_style_config
from batplot.ui import set_spine_side_color


def _base_dual(*, wasd_top_off: bool = False):
    fig, ax = plt.subplots()
    x = np.linspace(0.0, 100.0, 16)
    y = np.linspace(3.0, 4.0, 16)
    (c,) = ax.plot(x, y, label="1")
    (d,) = ax.plot(x[::-1], y, label="_nolegend_")
    for ln in (c, d):
        ln._orig_xdata_gc = np.asarray(ln.get_xdata(), float).copy()
    c_th = 162.5
    sec = ax.secondary_xaxis("top", functions=(lambda v: v / c_th, lambda v: v * c_th))
    sec.set_xlabel(f"Number of ions (C / {c_th:g} mAh g$^{{-1}}$)")
    ax.set_xlabel("Specific Capacity (mAh g$^{-1}$)")
    ax.set_ylabel("Potential (V)")
    fig._xaxis_mode = "dual"
    fig._xaxis_c_theoretical = c_th
    fig._xaxis_swapped = False
    fig._xaxis_secondary = sec
    fig._gc_capacity_mode = "per_cycle"
    off = wasd_top_off
    fig._ec_wasd_state = {
        "top": {
            "spine": not off,
            "ticks": False,
            "minor": False,
            "labels": False,
            "title": not off,
        },
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "right": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
    }
    apply_ec_dual_top_wasd(fig, ax, fig._ec_wasd_state)
    return fig, ax, sec, {1: {"charge": c, "discharge": d}}


def test_first_dual_enable_forces_spine_and_ions_title_on():
    """Pre-dual t-menu left top.title=False — entering dual must not wipe ions title."""
    fig, ax = plt.subplots()
    ax.plot([0, 1], [3, 4])
    fig._ec_wasd_state = {
        "top": {"spine": False, "ticks": False, "minor": False, "labels": False, "title": False},
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "right": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
    }
    c_th = 150.0
    sec = ax.secondary_xaxis("top", functions=(lambda v: v / c_th, lambda v: v * c_th))
    sec.set_xlabel("Number of ions")
    ax.set_xlabel("Capacity")
    fig._xaxis_mode = "dual"
    fig._xaxis_secondary = sec
    _chrome_after_dual_recreate(fig, ax, first_enable=True)
    assert fig._ec_wasd_state["top"]["spine"] is True
    assert fig._ec_wasd_state["top"]["title"] is True
    assert ax.spines["top"].get_visible() is True
    assert sec.spines["top"].get_visible() is True
    assert sec.xaxis.label.get_visible() is True
    assert ax._top_xlabel_on is False
    plt.close(fig)


def test_leave_dual_clears_top_title_flag():
    fig, ax, sec, _ = _base_dual()
    fig._xaxis_secondary.remove()
    fig._xaxis_secondary = None
    fig._xaxis_mode = "capacity"
    _clear_dual_wasd_top_on_leave(fig, ax)
    assert fig._ec_wasd_state["top"]["title"] is False
    assert ax._top_xlabel_on is False
    plt.close(fig)


def test_sanitize_fig_xaxis_swapped_clears_outside_dual():
    from batplot.plot_modes.electrochem.style import sanitize_fig_xaxis_swapped

    fig, ax = plt.subplots()
    fig._xaxis_mode = "capacity"
    fig._xaxis_swapped = True
    assert sanitize_fig_xaxis_swapped(fig, mode="capacity", swapped=True) is False
    assert fig._xaxis_swapped is False
    fig._xaxis_mode = "dual"
    assert sanitize_fig_xaxis_swapped(fig, mode="dual", swapped=True) is True
    assert fig._xaxis_swapped is True
    plt.close(fig)


def test_leave_dual_clears_swapped_and_reseals_wasd():
    """After a→s then a→c, swapped must clear and primary chrome must reseal."""
    fig, ax, sec, _ = _base_dual()
    fig._xaxis_swapped = True
    fig._ec_wasd_state["top"]["spine"] = False
    fig._ec_wasd_state["top"]["title"] = True
    fig._ec_wasd_state["top"]["ticks"] = True
    ax.spines["top"].set_visible(True)
    sec.remove()
    fig._xaxis_secondary = None
    fig._xaxis_mode = "capacity"
    _leave_dual_axis_chrome(fig, ax)
    assert fig._xaxis_swapped is False
    assert fig._ec_wasd_state["top"]["title"] is False
    assert fig._ec_wasd_state["top"]["ticks"] is False
    assert fig._ec_wasd_state["top"]["labels"] is False
    # Spine preference kept; artist must match WASD after reseal
    assert fig._ec_wasd_state["top"]["spine"] is False
    assert ax.spines["top"].get_visible() is False
    assert ax._top_xlabel_on is False
    plt.close(fig)


def test_session_dump_prefers_live_wasd_top_title(tmp_path: Path):
    fig, ax, sec, cycle_lines = _base_dual()
    # Desync: bookkeeping says on, artist lag says off
    fig._ec_wasd_state["top"]["title"] = True
    fig._ec_wasd_state["top"]["spine"] = True
    sec.xaxis.label.set_visible(False)
    path = tmp_path / "prefer_live.pkl"
    dump_ec_session(str(path), fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)
    with path.open("rb") as fh:
        sess = pickle.load(fh)
    assert sess["wasd_state"]["top"]["title"] is True
    assert sess["xaxis_dual"]["top_axis"]["xlabel_visible"] is True
    loaded = load_ec_session(str(path))
    assert loaded is not None
    fig2, ax2, _ = loaded[:3]
    sec2 = ec_dual_secax(fig2)
    assert sec2 is not None
    assert bool(sec2.xaxis.label.get_visible()) is True
    plt.close(fig)
    plt.close(fig2)


def test_style_import_roundtrip_hides_both_spines(tmp_path: Path):
    fig, ax, sec, cycle_lines = _base_dual()
    set_spine_side_color(sec, "top", "#008000", fig=fig, title_color="#123456")
    fig._ec_wasd_state["top"]["spine"] = False
    fig._ec_wasd_state["top"]["ticks"] = False
    fig._ec_wasd_state["top"]["labels"] = False
    fig._ec_wasd_state["top"]["title"] = True  # title on, spine off
    apply_ec_dual_top_wasd(fig, ax, fig._ec_wasd_state)
    cfg = _get_style_snapshot(fig, ax, cycle_lines, tick_state={})
    assert cfg["wasd_state"]["top"]["spine"] is False
    assert cfg["wasd_state"]["top"]["title"] is True

    fig2, ax2, sec2, cl2 = _base_dual()
    ok = apply_ec_style_config(
        cfg, fig=fig2, ax=ax2, cycle_lines=cl2, file_data=None, tick_state={}, silent=True,
    )
    assert ok is True
    sec2b = ec_dual_secax(fig2)
    assert sec2b is not None
    assert ax2.spines["top"].get_visible() is False
    assert sec2b.spines["top"].get_visible() is False
    assert sec2b.xaxis.label.get_visible() is True
    plt.close(fig)
    plt.close(fig2)


def test_rename_bottom_x_does_not_create_dual_duplicate():
    fig, ax, sec, _ = _base_dual()
    inputs = iter(["Renamed capacity", "q"])
    calls = {"top": 0}

    def fake_top(*_a, **_k):
        calls["top"] += 1

    _rename_bottom_x(
        fig=fig,
        ax=ax,
        tick_state={},
        push_state=lambda *_a, **_k: None,
        safe_input=lambda _p: next(inputs),
        ui_position_top_xlabel=fake_top,
        ui_position_bottom_xlabel=lambda *_a, **_k: None,
    )
    assert calls["top"] == 0
    assert ax.get_xlabel() == "Renamed capacity"
    assert ax._top_xlabel_on is False
    art = getattr(ax, "_top_xlabel_artist", None)
    if art is not None:
        assert art.get_visible() is False
    assert sec.get_xlabel().startswith("Number of ions")
    plt.close(fig)


def test_w1_then_style_then_session_both_layers(tmp_path: Path):
    """End-to-end p→i→s gate for dual top hide-both."""
    fig, ax, sec, cycle_lines = _base_dual()
    fig._ec_wasd_state["top"]["spine"] = False
    fig._ec_wasd_state["top"]["ticks"] = False
    fig._ec_wasd_state["top"]["labels"] = False
    apply_ec_dual_top_wasd(fig, ax, fig._ec_wasd_state)
    cfg = _get_style_snapshot(fig, ax, cycle_lines, tick_state={})
    pkl = tmp_path / "both.pkl"
    dump_ec_session(str(pkl), fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)

    fig2, ax2, _, cl2 = _base_dual()
    apply_ec_style_config(
        cfg, fig=fig2, ax=ax2, cycle_lines=cl2, file_data=None, tick_state={}, silent=True,
    )
    sec2 = ec_dual_secax(fig2)
    assert ax2.spines["top"].get_visible() is False
    assert sec2.spines["top"].get_visible() is False

    loaded = load_ec_session(str(pkl))
    fig3, ax3, _ = loaded[:3]
    sec3 = ec_dual_secax(fig3)
    assert ax3.spines["top"].get_visible() is False
    assert sec3.spines["top"].get_visible() is False
    plt.close(fig)
    plt.close(fig2)
    plt.close(fig3)


def test_dual_recreate_keeps_custom_bottom_xlabel():
    fig, ax, sec, _ = _base_dual()
    ax._stored_xlabel = "My custom capacity"
    ax.set_xlabel("Specific Capacity (mAh g$^{-1}$)")  # simulate recreate default
    from batplot.plot_modes.electrochem.dual_axis_menu import _chrome_after_dual_recreate

    _chrome_after_dual_recreate(
        fig, ax, keep_top_xlabel=True, keep_bottom_xlabel=True, first_enable=False,
    )
    assert ax.get_xlabel() == "My custom capacity"
    assert ax.xaxis.label.get_visible() is True
    plt.close(fig)


def test_dual_recreate_honors_bottom_title_hide():
    fig, ax, sec, _ = _base_dual()
    fig._ec_wasd_state["bottom"]["title"] = False
    ax._stored_xlabel = "capacity"
    ax.set_xlabel("Specific Capacity (mAh g$^{-1}$)")
    from batplot.plot_modes.electrochem.dual_axis_menu import _chrome_after_dual_recreate

    _chrome_after_dual_recreate(fig, ax, keep_bottom_xlabel=True, first_enable=False)
    assert ax.xaxis.label.get_visible() is False
    plt.close(fig)


def test_no_axes_by_side_top_secax_only_in_ec_apply_paths():
    """Contract: EC apply paths must not orphan primary top via axes_by_side."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1] / "batplot" / "plot_modes"
    offenders = []
    pat = re.compile(r"axes_by_side\s*=\s*\{[^}]*['\"]top['\"]\s*:")
    for path in root.rglob("*.py"):
        if path.name == "spines.py":
            continue  # definition only
        text = path.read_text(encoding="utf-8")
        if pat.search(text):
            offenders.append(str(path.relative_to(root.parent.parent)))
    assert offenders == [], f"orphan dual top paths: {offenders}"

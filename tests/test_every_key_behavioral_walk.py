"""Behavioral walk of every critical menu key/subkey — asserts real state change.

Unlike quit-only smoke, this file mutates state and checks spines/ticks/colors/
visibility/fonts/labels survive apply. Parametrized platform names exercise
OS-sensitive helpers (darwin / win32 / linux) under Agg (CI-safe).
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest
from matplotlib.colors import to_hex

from batplot.plot_modes.common.spines import (
    apply_wasd_spines,
    apply_wasd_tick_params,
    run_spine_tick_menu,
    sync_tick_state_from_wasd,
    wasd_to_tick_state,
)
from batplot.plot_modes.cpc.panel_menus import apply_cpc_file_artist_visibility
from batplot.plot_modes.electrochem.interactive import _apply_spine_color
from batplot.plot_modes.histo.spines import set_histo_spine_color
from batplot.plot_modes.operando.spine_colors import (
    apply_operando_spine_color,
    _ensure_ec_tick_state,
)
from batplot.plot_modes.xy.spines import (
    apply_xy_spine_color,
    capture_xy_wasd_state,
    ensure_xy_tick_state,
    set_xy_spine_visible,
    sync_xy_twin_wasd,
)
from batplot.ui import (
    _collect_visible_tick_line_colors,
    finalize_spine_colors,
    finalize_spine_colors_cpc,
    finalize_spine_colors_for_axes,
    resolve_spine_dump_color,
    set_spine_side_color,
)

SIDES = ("top", "bottom", "left", "right")
SIDE_KEY = {"top": "w", "left": "a", "bottom": "s", "right": "d"}
PROP_NUM = {"spine": "1", "ticks": "2", "minor": "3", "labels": "4", "title": "5"}
COLORS = {
    "top": "#cc0000",
    "bottom": "#0033aa",
    "left": "#00aa00",
    "right": "#aa00aa",
}


def _feed(*vals: str):
    it = iter(vals)

    def _in(*_a, **_k):
        try:
            return next(it)
        except StopIteration:
            return "q"

    return _in


def _identity(s: str) -> str:
    return s


# ---------------------------------------------------------------------------
# WASD: every side × every prop (1–5) with real apply
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("side", SIDES)
@pytest.mark.parametrize("prop", list(PROP_NUM))
def test_wasd_every_side_every_prop_toggles(side, prop):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    wasd = {
        s: {
            "spine": True,
            "ticks": True,
            "minor": False,
            "labels": True,
            "title": s in ("bottom", "left"),
        }
        for s in SIDES
    }
    before = bool(wasd[side][prop])
    token = f"{SIDE_KEY[side]}{PROP_NUM[prop]}"
    applied = []

    def _apply(changed=None):
        applied.append(tuple(changed) if changed else None)
        apply_wasd_spines(ax, wasd)
        apply_wasd_tick_params(ax, wasd)

    run_spine_tick_menu(
        fig=fig,
        wasd=wasd,
        safe_input=_feed(token, "q"),
        colorize_prompt=_identity,
        colorize_inline_commands=_identity,
        push_state=lambda *_a, **_k: None,
        sync_tick_state=lambda: None,
        apply_wasd=_apply,
    )
    assert wasd[side][prop] is (not before), (side, prop, wasd[side])
    assert applied, "apply_wasd must run after toggle"
    # Spine visibility must match wasd after apply
    if prop == "spine":
        assert ax.spines[side].get_visible() is wasd[side]["spine"]
    plt.close(fig)


@pytest.mark.parametrize("side", SIDES)
def test_spine_color_every_side_xy_ec_histo(side):
    # XY
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax.tick_params(
        top=True, bottom=True, left=True, right=True,
        labeltop=True, labelbottom=True, labelleft=True, labelright=True,
    )
    ts = ensure_xy_tick_state(
        ax,
        {k: True for k in (
            "b_ticks", "t_ticks", "l_ticks", "r_ticks",
            "b_labels", "t_labels", "l_labels", "r_labels",
            "bx", "tx", "ly", "ry",
        )},
    )
    col = COLORS[side]
    apply_xy_spine_color(fig, ax, ts, side, col)
    finalize_spine_colors(fig, ax, tick_state=ts, draw=True)
    assert to_hex(ax.spines[side].get_edgecolor()) == col
    lines = _collect_visible_tick_line_colors(ax, side)
    if lines:
        assert all(c == col for c in lines)
    plt.close(fig)

    # EC
    fig2, ax2 = plt.subplots()
    ax2.plot([0, 1], [3, 4])
    ax2.tick_params(
        top=True, bottom=True, left=True, right=True,
        labeltop=True, labelbottom=True, labelleft=True, labelright=True,
    )
    ts2 = dict(ts)
    ax2._saved_tick_state = dict(ts2)
    _apply_spine_color(ax2, fig2, ts2, side, col)
    finalize_spine_colors(fig2, ax2, tick_state=ts2, draw=True)
    assert to_hex(ax2.spines[side].get_edgecolor()) == col
    plt.close(fig2)

    # Histo (no top ticks usually — still color spine)
    fig3, ax3 = plt.subplots()
    ax3.hist([1, 2, 2, 3])
    set_histo_spine_color(fig3, ax3, side, col)
    finalize_spine_colors(
        fig3, ax3, tick_state=getattr(ax3, "_saved_tick_state", None), draw=True
    )
    assert to_hex(ax3.spines[side].get_edgecolor()) == col
    plt.close(fig3)


# ---------------------------------------------------------------------------
# CPC / XY dual / operando / EC dual — behavioral
# ---------------------------------------------------------------------------


def test_cpc_all_wasd_sides_color_and_visibility():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    ax.plot([0, 1], [0, 1])
    ax2.plot([0, 1], [1, 0])
    ts = wasd_to_tick_state(
        {
            "top": {"ticks": False, "labels": False, "minor": False},
            "bottom": {"ticks": True, "labels": True, "minor": False},
            "left": {"ticks": True, "labels": True, "minor": False},
            "right": {"ticks": True, "labels": True, "minor": False},
        },
        tick_defaults={"top": False, "bottom": True, "left": True, "right": True},
        label_defaults={"top": False, "bottom": True, "left": True, "right": True},
    )
    ax._saved_tick_state = dict(ts)
    for side, color in (("left", COLORS["left"]), ("right", COLORS["right"]),
                        ("bottom", COLORS["bottom"]), ("top", COLORS["top"])):
        target = ax2 if side == "right" else ax
        if side in ("top", "bottom"):
            set_spine_side_color(ax, side, color, fig=fig, tick_state=ts)
            set_spine_side_color(ax2, side, color, fig=fig, tick_state=ts)
        else:
            set_spine_side_color(target, side, color, fig=fig, tick_state=ts)
    finalize_spine_colors_cpc(fig, ax, ax2, tick_state=ts, draw=True)
    assert to_hex(ax.spines["left"].get_edgecolor()) == COLORS["left"]
    assert to_hex(ax2.spines["right"].get_edgecolor()) == COLORS["right"]
    # Hide left spine via wasd
    wasd = {
        "top": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "left": {"spine": False, "ticks": True, "minor": False, "labels": True, "title": True},
        "right": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
    }
    apply_wasd_spines(ax, wasd, sides=("top", "bottom", "left"))
    apply_wasd_spines(ax2, wasd, sides=("top", "bottom", "right"))
    assert ax.spines["left"].get_visible() is False
    assert ax2.spines["right"].get_visible() is True
    plt.close(fig)


def test_cpc_multifile_d_v_ry_full_matrix():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    files = []
    for i in range(2):
        files.append(
            {
                "visible": True,
                "sc_charge": ax.scatter([i], [1]),
                "sc_discharge": ax.scatter([i], [2]),
                "sc_eff": ax2.scatter([i], [90]),
                "filename": f"f{i}.csv",
            }
        )
    fig._cpc_wasd_state = {
        "right": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True}
    }
    # Hide file 0
    files[0]["visible"] = False
    fig._cpc_display_mode = "both"
    apply_cpc_file_artist_visibility(fig, files)
    assert files[0]["sc_charge"].get_visible() is False
    assert files[1]["sc_charge"].get_visible() is True
    # d=charge must not resurrect file 0
    fig._cpc_display_mode = "charge"
    apply_cpc_file_artist_visibility(fig, files)
    assert files[0]["sc_charge"].get_visible() is False
    assert files[1]["sc_charge"].get_visible() is True
    assert files[1]["sc_discharge"].get_visible() is False
    # ry off
    apply_cpc_file_artist_visibility(fig, files, eff_on=False)
    assert files[1]["sc_eff"].get_visible() is False
    assert ax2.get_visible() is True  # twin axes stay
    # show file 0 again under charge + ry off
    files[0]["visible"] = True
    apply_cpc_file_artist_visibility(fig, files, eff_on=False)
    assert files[0]["sc_charge"].get_visible() is True
    assert files[0]["sc_discharge"].get_visible() is False
    assert files[0]["sc_eff"].get_visible() is False
    plt.close(fig)


def test_xy_dual_y_every_wasd_side_on_twin():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    fig._xy_ax2 = ax2
    fig._xy_use_top_x = True
    ax.plot([0, 1], [0, 1])
    ax2.plot([0, 1], [2, 1])
    for side in SIDES:
        set_xy_spine_visible(fig, ax, side, False)
        if side == "right" or side in ("top", "bottom"):
            assert ax2.spines[side].get_visible() is False
        assert ax.spines[side].get_visible() is False
        set_xy_spine_visible(fig, ax, side, True)
    wasd = capture_xy_wasd_state(ax, fig, None)
    for side in SIDES:
        assert wasd[side]["spine"] is True
    wasd["right"]["spine"] = False
    sync_xy_twin_wasd(ax, fig, wasd)
    assert ax2.spines["right"].get_visible() is False
    # Colors on twin
    ts = ensure_xy_tick_state(ax, {k: True for k in (
        "b_ticks", "t_ticks", "l_ticks", "r_ticks",
        "b_labels", "t_labels", "l_labels", "r_labels",
        "bx", "tx", "ly", "ry",
    )})
    apply_xy_spine_color(fig, ax, ts, "right", COLORS["right"])
    assert to_hex(ax2.spines["right"].get_edgecolor()) == COLORS["right"]
    plt.close(fig)


def test_operando_k_all_sides_both_panes_no_hitchhike():
    fig = plt.figure()
    ax = fig.add_subplot(121)
    ec = fig.add_subplot(122)
    ax.imshow([[0.0, 1.0], [1.0, 0.0]])
    ec.plot([1.0, 2.0], [1.0, 2.0])
    ec.yaxis.tick_right()
    ts = _ensure_ec_tick_state(ec)
    for side, color in COLORS.items():
        apply_operando_spine_color(fig, ax, side, color, peer_ax=ec)
    apply_operando_spine_color(
        fig, ec, "right", "#ff00ff", tick_state=ts, peer_ax=ax
    )
    finalize_spine_colors_for_axes(
        fig, [(ax, None), (ec, ts)], draw=True
    )
    assert to_hex(ax.spines["left"].get_edgecolor()) == COLORS["left"]
    assert to_hex(ec.spines["right"].get_edgecolor()) == "#ff00ff"
    # Contour right must not pick up EC magenta
    assert to_hex(ax.spines["right"].get_edgecolor()) != "#ff00ff"
    ticks = _collect_visible_tick_line_colors(ec, "right")
    assert ticks and all(c == "#ff00ff" for c in ticks)
    # Dump prefers store
    ax.spines["left"].set_edgecolor("black")
    assert resolve_spine_dump_color(ax, "left", fig) == COLORS["left"]
    plt.close(fig)


def test_ec_dual_top_and_bottom_colors_independent():
    from batplot.plot_modes.electrochem.spine_colors import _apply_secondary_top_spine_color

    fig, ax = plt.subplots()
    ax.plot([0.0, 100.0], [3.0, 4.0])
    # np.asarray keeps basedpyright happy (mpl stubs type these as ArrayLike).
    sec = ax.secondary_xaxis(
        "top",
        functions=(
            lambda x: np.asarray(x, dtype=float) / 100.0,
            lambda x: np.asarray(x, dtype=float) * 100.0,
        ),
    )
    fig._xaxis_secondary = sec
    fig._xaxis_mode = "dual"
    _apply_secondary_top_spine_color(fig, COLORS["top"], "red")
    set_spine_side_color(ax, "bottom", COLORS["bottom"], fig=fig)
    finalize_spine_colors(fig, ax, draw=True)
    assert to_hex(sec.spines["top"].get_edgecolor()) == COLORS["top"]
    assert to_hex(ax.spines["bottom"].get_edgecolor()) == COLORS["bottom"]
    plt.close(fig)


# ---------------------------------------------------------------------------
# Line / legend / rename / font — mutate + dump preference
# ---------------------------------------------------------------------------


def test_xy_line_font_label_roundtrip_fields():
    from batplot.plot_modes.common.font_extras import (
        apply_fig_font_weight,
        font_extras_export_dict,
        get_fig_font_weight,
    )
    from batplot.ui import resolve_spine_dump_color

    fig, ax = plt.subplots()
    (ln,) = ax.plot([0, 1], [0, 1], lw=1.0)
    ln.set_linewidth(3.5)
    ax.set_xlabel("X-title")
    ax.set_ylabel("Y-title")
    apply_fig_font_weight(fig, [ax.xaxis.label, ax.yaxis.label], "bold")
    assert get_fig_font_weight(fig) == "bold"
    extras = font_extras_export_dict(fig)
    assert extras.get("weight") == "bold"
    set_spine_side_color(ax, "bottom", COLORS["bottom"], fig=fig)
    ax.spines["bottom"].set_edgecolor("black")
    assert resolve_spine_dump_color(ax, "bottom", fig) == COLORS["bottom"]
    assert ln.get_linewidth() == pytest.approx(3.5)
    assert ax.get_xlabel() == "X-title"
    plt.close(fig)


# ---------------------------------------------------------------------------
# OS platform simulation (darwin / win32 / linux)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("platform_name", ["darwin", "win32", "linux"])
def test_os_path_session_resolve_and_temp(monkeypatch, platform_name, tmp_path):
    """Session path helpers must work the same on all OS names."""
    monkeypatch.setattr(sys, "platform", platform_name)
    from batplot.plot_modes.common import terminal as T
    from batplot.plot_modes.common.session_helpers import resolve_session_save_path

    # stderr guard must not break nested use
    err = sys.stderr
    with T.imk_stderr_guard():
        with T.imk_stderr_guard():
            # On darwin the outer guard may wrap stderr; nested must still restore.
            pass
    assert sys.stderr is err

    # Temp pickle roundtrip (path separators / nested dirs)
    target = tmp_path / "nested" / "sess.pkl"
    target.parent.mkdir(parents=True, exist_ok=True)
    data = {"kind": "xy", "version": 2, "platform": platform_name}
    import pickle

    with target.open("wb") as f:
        pickle.dump(data, f)
    with target.open("rb") as f:
        loaded = pickle.load(f)
    assert loaded["platform"] == platform_name

    saved = resolve_session_save_path("probe_sess", folder=str(tmp_path))
    assert saved
    assert str(tmp_path) in saved or Path(saved).name
    expanded = os.path.expanduser("~/batplot_os_probe.pkl")
    assert expanded
    assert not expanded.startswith("~")

@pytest.mark.parametrize("platform_name", ["darwin", "win32", "linux"])
def test_gui_backend_order_per_platform(monkeypatch, platform_name):
    monkeypatch.setattr(sys, "platform", platform_name)
    from batplot._mpl_backend import _gui_backend_order

    order = _gui_backend_order()
    assert order
    if platform_name == "darwin":
        assert order[0] == "MacOSX"
    else:
        assert order[0] == "TkAgg"


@pytest.mark.parametrize("platform_name", ["darwin", "win32", "linux"])
def test_spine_finalize_identical_across_platform_flags(monkeypatch, platform_name):
    """Spine apply must not depend on sys.platform."""
    monkeypatch.setattr(sys, "platform", platform_name)
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    set_spine_side_color(ax, "left", "#123456", fig=fig)
    finalize_spine_colors(fig, ax, draw=True)
    assert to_hex(ax.spines["left"].get_edgecolor()) == "#123456"
    plt.close(fig)


# ---------------------------------------------------------------------------
# Live interactive loops — mutate then assert (not quit-only smoke)
# ---------------------------------------------------------------------------


def test_ec_interactive_k_colors_all_sides(monkeypatch):
    from tests.test_interactive_menu_smoke import drive_ec
    from batplot.ui import resolve_spine_dump_color
    from batplot.plot_modes.electrochem.spine_colors import run_ec_spine_color_menu
    from batplot.plot_modes.common.terminal import colorize_prompt
    from batplot.plot_modes.common.menu_rendering import colorize_menu

    fig, ax = plt.subplots()
    ax.plot([0, 1], [3, 4])
    ax.tick_params(
        top=True, bottom=True, left=True, right=True,
        labeltop=True, labelbottom=True, labelleft=True, labelright=True,
    )
    tick_state = {
        "b_ticks": True, "t_ticks": True, "l_ticks": True, "r_ticks": True,
        "b_labels": True, "t_labels": True, "l_labels": True, "r_labels": True,
        "bx": True, "tx": True, "ly": True, "ry": True,
    }
    ax._saved_tick_state = dict(tick_state)
    run_ec_spine_color_menu(
        fig=fig,
        ax=ax,
        tick_state=tick_state,
        apply_spine_color=_apply_spine_color,
        push_state=lambda *_a, **_k: None,
        safe_input=_feed("d:red", "a:blue", "w:green", "s:#0033aa", "q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    finalize_spine_colors(fig, ax, tick_state=tick_state, draw=True)
    assert to_hex(ax.spines["right"].get_edgecolor()) == "#ff0000"
    assert to_hex(ax.spines["left"].get_edgecolor()) == "#0000ff"
    assert to_hex(ax.spines["top"].get_edgecolor()) == "#008000"
    assert to_hex(ax.spines["bottom"].get_edgecolor()) == "#0033aa"
    ax.spines["right"].set_edgecolor("black")
    assert resolve_spine_dump_color(ax, "right", fig) == "#ff0000"
    plt.close(fig)
    drive_ec(monkeypatch, ["k", "d:red", "a:blue", "q"])


def test_operando_interactive_k_ec_pane_no_hitchhike(monkeypatch):
    from batplot.plot_modes.operando.spine_colors import run_operando_spine_color_menu
    from batplot.plot_modes.common.terminal import colorize_prompt
    from batplot.plot_modes.common.menu_rendering import colorize_menu
    from batplot.ui import finalize_spine_colors_for_axes

    fig = plt.figure()
    ax = fig.add_subplot(121)
    ec = fig.add_subplot(122)
    ax.imshow([[0.0, 1.0], [1.0, 0.0]])
    ec.plot([1.0, 2.0], [1.0, 2.0])
    ec.yaxis.tick_right()
    run_operando_spine_color_menu(
        fig=fig,
        ax=ax,
        ec_ax=ec,
        push_state=lambda *_a, **_k: None,
        safe_input=_feed("o", "a:blue", "q", "e", "d:magenta", "q", "q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    ts = getattr(ec, "_saved_tick_state", None)
    finalize_spine_colors_for_axes(fig, [(ax, None), (ec, ts)], draw=True)
    assert to_hex(ax.spines["left"].get_edgecolor()) == "#0000ff"
    assert to_hex(ec.spines["right"].get_edgecolor()) == "#ff00ff"
    assert to_hex(ax.spines["right"].get_edgecolor()) != "#ff00ff"
    plt.close(fig)
    from tests.test_interactive_menu_smoke import drive_op

    drive_op(monkeypatch, ["k", "o", "d:red", "q", "e", "d:blue", "q", "q"])


def test_xy_interactive_spine_tokens_and_wasd(monkeypatch):
    from batplot.plot_modes.xy.colors import run_xy_color_menu
    from batplot.plot_modes.common.terminal import colorize_prompt
    from batplot.plot_modes.xy.spines import ensure_xy_tick_state

    fig, ax = plt.subplots()
    (ln,) = ax.plot([0, 1], [0, 1], label="c1")
    ax.tick_params(
        top=True, bottom=True, left=True, right=True,
        labeltop=True, labelbottom=True, labelleft=True, labelright=True,
    )
    ts = ensure_xy_tick_state(
        ax,
        {k: True for k in (
            "b_ticks", "t_ticks", "l_ticks", "r_ticks",
            "b_labels", "t_labels", "l_labels", "r_labels",
            "bx", "tx", "ly", "ry",
        )},
    )
    run_xy_color_menu(
        ax=ax,
        fig=fig,
        labels=["c1"],
        y_data_list=[np.array([0.0, 1.0])],
        label_text_objects=[],
        stack=False,
        args_files=["a.xy"],
        line_getter=lambda i: ln,
        bp=None,
        get_cif_series=lambda: None,
        sync_fig_cif_tick_series=lambda: None,
        position_top_xlabel=lambda: None,
        position_right_ylabel=lambda: None,
        push_state=lambda *_a, **_k: None,
        safe_input=_feed("d:red", "a:blue", "q"),
        colorize_prompt=colorize_prompt,
        tick_state=ts,
    )
    finalize_spine_colors(fig, ax, tick_state=ts, draw=True)
    assert to_hex(ax.spines["right"].get_edgecolor()) == "#ff0000"
    assert to_hex(ax.spines["left"].get_edgecolor()) == "#0000ff"
    plt.close(fig)
    from tests.test_interactive_menu_smoke import drive_xy

    drive_xy(monkeypatch, ["c", "d:red", "a:blue", "q", "t", "list", "s2", "q"])

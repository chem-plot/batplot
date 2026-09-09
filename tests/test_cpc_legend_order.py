"""CPC multi-file legend rearrange (h→ra / ra) and p/i/s/b persistence."""

from __future__ import annotations

import pickle
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

from batplot.plot_modes.cpc import session as CS
from batplot.plot_modes.cpc.legend import _build_compact_cpc_legend
from batplot.plot_modes.cpc.legend_order import (
    ensure_cpc_legend_file_order,
    run_cpc_legend_order_menu,
)
from batplot.plot_modes.cpc.menu import build_cpc_menu_columns
from batplot.plot_modes.cpc.snapshots import push_cpc_state, restore_cpc_state
from batplot.plot_modes.cpc.style import _apply_style, _style_snapshot
from batplot.plot_modes.common.menus import run_legend_position_menu


def _two_file_cpc():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc_c1 = ax.scatter([1, 2], [100, 99], c="C0", marker="s", s=40, label="a (Chg)")
    sc_d1 = ax.scatter(
        [1, 2], [98, 97], facecolors="none", edgecolors="C0", marker="s", s=40, label="a (Dch)"
    )
    sc_e1 = ax2.scatter([1, 2], [98, 98], c="C1", marker="^", s=50, label="a (Eff)")
    sc_c2 = ax.scatter([1, 2], [90, 89], c="C2", marker="s", s=40, label="b (Chg)")
    sc_d2 = ax.scatter(
        [1, 2], [88, 87], facecolors="none", edgecolors="C2", marker="s", s=40, label="b (Dch)"
    )
    sc_e2 = ax2.scatter([1, 2], [97, 97], c="C3", marker="^", s=50, label="b (Eff)")
    file_data = [
        {
            "filename": "a.csv",
            "display_name": "cell_a",
            "visible": True,
            "sc_charge": sc_c1,
            "sc_discharge": sc_d1,
            "sc_eff": sc_e1,
            "color": "C0",
            "eff_color": "C1",
            "cyc_nums": [1.0, 2.0],
            "cap_charge": [100.0, 99.0],
            "cap_discharge": [98.0, 97.0],
            "eff": [98.0, 98.0],
        },
        {
            "filename": "b.csv",
            "display_name": "cell_b",
            "visible": True,
            "sc_charge": sc_c2,
            "sc_discharge": sc_d2,
            "sc_eff": sc_e2,
            "color": "C2",
            "eff_color": "C3",
            "cyc_nums": [1.0, 2.0],
            "cap_charge": [90.0, 89.0],
            "cap_discharge": [88.0, 87.0],
            "eff": [97.0, 97.0],
        },
    ]
    fig._cpc_is_multi_file = True  # type: ignore[attr-defined]
    ensure_cpc_legend_file_order(fig, file_data)
    return fig, ax, ax2, file_data


def test_cpc_legend_order_helper_reorders():
    fig, ax, ax2, file_data = _two_file_cpc()
    states = []
    inputs = iter(["2 1", "q"])

    run_cpc_legend_order_menu(
        fig=fig,
        ax=ax,
        ax2=ax2,
        file_data=file_data,
        is_multi_file=True,
        print_file_list=lambda *_a, **_k: None,
        rebuild_legend=lambda *_a, **_k: None,
        push_state=states.append,
        safe_input=lambda _p: next(inputs),
    )
    assert states == ["rearrange-legend"]
    assert getattr(fig, "_cpc_legend_file_order") == [1, 0]
    plt.close(fig)


def test_cpc_legend_order_skips_unchanged_permutation():
    fig, ax, ax2, file_data = _two_file_cpc()
    fig._cpc_legend_file_order = [1, 0]  # type: ignore[attr-defined]
    states = []
    inputs = iter(["2 1", "q"])  # same as current
    run_cpc_legend_order_menu(
        fig=fig,
        ax=ax,
        ax2=ax2,
        file_data=file_data,
        is_multi_file=True,
        print_file_list=lambda *_a, **_k: None,
        rebuild_legend=lambda *_a, **_k: None,
        push_state=states.append,
        safe_input=lambda _p: next(inputs),
    )
    assert states == []
    assert getattr(fig, "_cpc_legend_file_order") == [1, 0]
    plt.close(fig)


def test_compact_legend_respects_file_order():
    fig, ax, ax2, file_data = _two_file_cpc()
    fig._cpc_legend_file_order = [1, 0]  # type: ignore[attr-defined]
    _build_compact_cpc_legend(ax, ax2, file_data)
    leg = ax.get_legend() or ax2.get_legend()
    texts = [t.get_text() for t in leg.get_texts()] if leg else []
    # File rows come after Charge/Discharge[/Eff] + blank separator.
    file_labels = [t for t in texts if t in ("cell_a", "cell_b")]
    assert file_labels == ["cell_b", "cell_a"]
    plt.close(fig)


def test_style_and_undo_persist_legend_order():
    fig, ax, ax2, file_data = _two_file_cpc()
    fig._cpc_legend_file_order = [1, 0]  # type: ignore[attr-defined]
    hist = []
    tick_state = {"bx": True, "ly": True, "ry": True, "tx": False}
    push_cpc_state(
        hist,
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=file_data[0]["sc_charge"],
        sc_discharge=file_data[0]["sc_discharge"],
        sc_eff=file_data[0]["sc_eff"],
        file_data=file_data,
        tick_state=tick_state,
        note="ordered",
    )
    assert hist[-1].get("legend_file_order") == [1, 0]

    fig._cpc_legend_file_order = [0, 1]  # type: ignore[attr-defined]
    snap = _style_snapshot(
        fig, ax, ax2,
        file_data[0]["sc_charge"],
        file_data[0]["sc_discharge"],
        file_data[0]["sc_eff"],
        file_data,
    )
    assert snap.get("legend_file_order") == [0, 1]

    # Import style with reversed order
    snap["legend_file_order"] = [1, 0]
    _apply_style(
        fig, ax, ax2,
        file_data[0]["sc_charge"],
        file_data[0]["sc_discharge"],
        file_data[0]["sc_eff"],
        snap,
        file_data,
    )
    assert getattr(fig, "_cpc_legend_file_order") == [1, 0]

    # Undo restores the pushed order
    fig._cpc_legend_file_order = [0, 1]  # type: ignore[attr-defined]
    ok = restore_cpc_state(
        hist,
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=file_data[0]["sc_charge"],
        sc_discharge=file_data[0]["sc_discharge"],
        sc_eff=file_data[0]["sc_eff"],
        file_data=file_data,
        tick_state=tick_state,
        update_ticks_func=lambda: None,
    )
    assert ok
    assert getattr(fig, "_cpc_legend_file_order") == [1, 0]
    plt.close(fig)


def test_session_persists_legend_order(tmp_path: Path):
    fig, ax, ax2, file_data = _two_file_cpc()
    fig._cpc_legend_file_order = [1, 0]  # type: ignore[attr-defined]
    pkl = tmp_path / "cpc_order.pkl"
    CS.dump_cpc_session(
        str(pkl),
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=file_data[0]["sc_charge"],
        sc_discharge=file_data[0]["sc_discharge"],
        sc_eff=file_data[0]["sc_eff"],
        file_data=file_data,
        skip_confirm=True,
    )
    with open(pkl, "rb") as f:
        sess = pickle.load(f)
    assert sess.get("legend_file_order") == [1, 0]

    loaded = CS.load_cpc_session(str(pkl))
    assert loaded is not None
    fig2, *_rest = loaded
    assert getattr(fig2, "_cpc_legend_file_order") == [1, 0]
    plt.close(fig)
    plt.close(fig2)


def test_legend_menu_offers_ra_when_callback_provided():
    fig, ax = plt.subplots()
    calls = []
    inputs = iter(["ra", "q"])
    run_legend_position_menu(
        fig=fig,
        get_legend=lambda: None,
        get_position=lambda: (0.0, 0.0),
        set_position=lambda xy: None,
        sanitize_offset=lambda p: (0.0, 0.0),
        toggle_legend=lambda: None,
        apply_position=lambda: None,
        push_state=lambda _n: None,
        safe_input=lambda _p: next(inputs),
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
        rearrange_legend=lambda: calls.append(True),
    )
    assert calls == [True]
    plt.close(fig)


def test_cpc_menu_does_not_print_top_level_ra():
    fig, _ax = plt.subplots()
    fig._cpc_is_multi_file = True  # type: ignore[attr-defined]
    cols = build_cpc_menu_columns(fig)
    all_items = cols[0] + cols[1] + cols[2]
    assert not any(item.startswith("ra:") for item in all_items)
    plt.close(fig)


def test_reorder_uses_ax_figure_even_if_fig_arg_differs():
    fig, ax, ax2, file_data = _two_file_cpc()
    decoy, _ = plt.subplots()
    inputs = iter(["2 1", "q"])
    run_cpc_legend_order_menu(
        fig=decoy,
        ax=ax,
        ax2=ax2,
        file_data=file_data,
        is_multi_file=True,
        print_file_list=lambda *_a, **_k: None,
        rebuild_legend=lambda *_a, **_k: None,
        push_state=lambda _n: None,
        safe_input=lambda _p: next(inputs),
    )
    assert getattr(ax.figure, "_cpc_legend_file_order") == [1, 0]
    plt.close(fig)
    plt.close(decoy)

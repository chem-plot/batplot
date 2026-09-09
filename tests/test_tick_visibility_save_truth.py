"""Session saves must reflect the tick/label visibility actually on screen.

Guards against the "hidden labels reappear after save+reload" class of bug:
the WASD (``t``) menu used to update only a dispatcher-local ``tick_state``
dict, so ``ax._saved_tick_state`` (what the session dump trusted) went stale
and the saved ``.pkl`` re-enabled labels the user had hidden.

Two independent layers are tested here:
1. The WASD menu now writes ``ax._saved_tick_state`` through on every toggle.
2. Session dumps capture major tick/label visibility from the on-screen
   artists, so even a stale ``_saved_tick_state`` cannot corrupt a save.
"""

import pickle

import numpy as np
import matplotlib.pyplot as plt

from batplot import session as S
from conftest import loaded


def _build_ec_figure():
    fig, ax = plt.subplots()
    cap = np.linspace(0.0, 150.0, 40)
    volt = np.linspace(3.0, 4.2, 40)
    charge, = ax.plot(cap, volt, color="#ff0000", lw=2.0, label="cycle 1 charge")
    discharge, = ax.plot(cap[::-1], volt, color="#0000ff", lw=1.5,
                         label="cycle 1 discharge")
    ax.set_xlabel("Capacity (mAh/g)")
    ax.set_ylabel("Voltage (V)")
    cycle_lines = {1: {"charge": charge, "discharge": discharge}}
    return fig, ax, cycle_lines


def _first_left_label_visible(ax) -> bool:
    ticks = ax.yaxis.get_major_ticks()
    assert ticks, "no y major ticks"
    return bool(ticks[0].label1.get_visible())


def test_ec_session_save_reflects_screen_when_bookkeeping_stale(session_path):
    """Exact reported bug: left labels hidden on screen, stale saved state says
    visible -> the saved session must still hide them."""
    fig, ax, cycle_lines = _build_ec_figure()
    fig.canvas.draw()
    ax.tick_params(axis="y", which="major", labelleft=False)
    # Simulate the stale bookkeeping that caused the original bug.
    ax._saved_tick_state = {
        "b_ticks": True, "b_labels": True, "t_ticks": False, "t_labels": False,
        "l_ticks": True, "l_labels": True, "r_ticks": False, "r_labels": False,
        "mbx": False, "mtx": False, "mly": False, "mry": False,
        "bx": True, "tx": False, "ly": True, "ry": False,
    }
    p = session_path("ec_stale_labels.pkl")
    S.dump_ec_session(p, fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)

    with open(p, "rb") as fh:
        sess = pickle.load(fh)
    assert sess["wasd_state"]["left"]["labels"] is False
    assert sess["tick_state"]["l_labels"] is False
    assert sess["tick_state"]["ly"] is False  # legacy key for old loaders
    # Ticks themselves were left visible and must stay visible.
    assert sess["wasd_state"]["left"]["ticks"] is True
    assert sess["tick_state"]["l_ticks"] is True

    fig2, ax2, _meta = loaded(S.load_ec_session(p))
    fig2.canvas.draw()
    assert _first_left_label_visible(ax2) is False
    assert ax2._saved_tick_state["l_labels"] is False
    plt.close(fig)
    plt.close(fig2)


def test_ec_session_save_reflects_screen_without_saved_state(session_path):
    """Fresh plot with no ``_saved_tick_state`` at all: dump must still record
    what is displayed instead of falling back to defaults."""
    fig, ax, cycle_lines = _build_ec_figure()
    fig.canvas.draw()
    ax.tick_params(axis="y", which="major", labelleft=False)
    ax.tick_params(axis="x", which="major", top=True, labeltop=True)
    assert not hasattr(ax, "_saved_tick_state")
    p = session_path("ec_no_saved_state.pkl")
    S.dump_ec_session(p, fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)

    with open(p, "rb") as fh:
        sess = pickle.load(fh)
    assert sess["wasd_state"]["left"]["labels"] is False
    assert sess["wasd_state"]["top"]["ticks"] is True
    assert sess["wasd_state"]["top"]["labels"] is True
    assert sess["tick_state"]["l_labels"] is False
    assert sess["tick_state"]["t_ticks"] is True

    fig2, ax2, _meta = loaded(S.load_ec_session(p))
    fig2.canvas.draw()
    assert _first_left_label_visible(ax2) is False
    plt.close(fig)
    plt.close(fig2)


def test_ec_wasd_menu_persists_tick_state_on_axes(monkeypatch):
    """Toggling left labels via the ``t`` menu must land in
    ``ax._saved_tick_state`` (write-through + on_quit), not just a local dict."""
    from test_interactive_menu_smoke import (
        ScriptedInput,
        _patch_dialogs,
        _patch_menu_input,
        _patch_screen_color,
    )
    from batplot.plot_modes.electrochem import actions as EA
    from batplot.plot_modes.electrochem import interactive as EI

    scripter = ScriptedInput(["t", "a4", "q", "q"])
    _patch_menu_input(monkeypatch, scripter, EI)
    _patch_dialogs(monkeypatch, EA, EI)
    _patch_screen_color(monkeypatch)
    fig, ax, cycle_lines = _build_ec_figure()
    file_data = [{
        "filename": "a.mpt", "display_name": "a", "visible": True,
        "cycle_lines": cycle_lines, "all_cycles": [1],
    }]
    EI.electrochem_interactive_menu(
        fig, ax, cycle_lines=cycle_lines, file_data=file_data, canvas_mode=True
    )
    saved = getattr(ax, "_saved_tick_state", None)
    assert isinstance(saved, dict)
    assert saved["l_labels"] is False
    assert saved["l_ticks"] is True
    assert _first_left_label_visible(ax) is False
    plt.close(fig)


def test_xy_session_save_reflects_screen_when_bookkeeping_stale(session_path, fake_args):
    """XY dump must also capture the on-screen truth for major tick labels."""
    x = np.linspace(0.0, 100.0, 200)
    y = np.sin(x)
    fig, ax = plt.subplots()
    ax.plot(x, y, label="c1")
    ax.set_xlabel("Two theta")
    ax.set_ylabel("Intensity")
    fig.canvas.draw()
    ax.tick_params(axis="y", which="major", labelleft=False)
    stale = {
        "b_ticks": True, "b_labels": True, "t_ticks": False, "t_labels": False,
        "l_ticks": True, "l_labels": True, "r_ticks": False, "r_labels": False,
        "mbx": False, "mtx": False, "mly": False, "mry": False,
    }
    ax._saved_tick_state = dict(stale)
    p = session_path("xy_stale_labels.pkl")
    S.dump_session(
        p, fig=fig, ax=ax,
        x_data_list=[x], y_data_list=[y], orig_y=[y],
        offsets_list=[0.0], labels=["c1"], delta=0.0, args=fake_args,
        tick_state=dict(stale), skip_confirm=True,
    )

    with open(p, "rb") as fh:
        sess = pickle.load(fh)
    assert sess["wasd_state"]["left"]["labels"] is False
    assert sess["wasd_state"]["left"]["ticks"] is True

    fig2, ax2, _mk = loaded(S.load_xy_session(p))
    fig2.canvas.draw()
    assert _first_left_label_visible(ax2) is False
    plt.close(fig)
    plt.close(fig2)

"""Session / style restore parity: ticks, labels, pads, cycles, CPC, operando.

Guards the "hidden labels / custom locators / cycle selection / ion params
disappear after s or p/i" class of bugs found in the 2026-08-03 audit.
"""

import pickle

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

from batplot import session as S
from batplot.plot_modes.electrochem import colors as ECY
from batplot.plot_modes.electrochem.style import _get_style_snapshot
from batplot.plot_modes.electrochem.style_apply import apply_ec_style_config
from conftest import loaded


def _first_left_label_visible(ax) -> bool:
    ticks = ax.yaxis.get_major_ticks()
    assert ticks
    return bool(ticks[0].label1.get_visible())


def test_ec_session_restores_labelpads(session_path):
    fig, ax = plt.subplots()
    (ln,) = ax.plot([0, 1], [3, 4], label="1")
    ax.set_xlabel("Capacity")
    ax.set_ylabel("Voltage")
    ax.xaxis.labelpad = 12.0
    ax.yaxis.labelpad = 18.0
    cl = {1: {"charge": ln, "discharge": None}}
    p = session_path("ec_labelpads.pkl")
    S.dump_ec_session(p, fig=fig, ax=ax, cycle_lines=cl, skip_confirm=True)
    fig2, ax2, _ = loaded(S.load_ec_session(p))
    assert abs(float(ax2.xaxis.labelpad) - 12.0) < 1e-6
    assert abs(float(ax2.yaxis.labelpad) - 18.0) < 1e-6
    plt.close(fig)
    plt.close(fig2)


def test_ec_session_keeps_multiple_locator_through_menu_entry(session_path, monkeypatch):
    """Custom t>n MultipleLocator must survive interactive menu entry nice-ticks."""
    from batplot.plot_modes.electrochem import interactive as EI
    from test_interactive_menu_smoke import ScriptedInput, _patch_dialogs, _patch_menu_input, _patch_screen_color

    fig, ax = plt.subplots()
    (ln,) = ax.plot([0, 50, 100], [3, 3.5, 4], label="1")
    ax.xaxis.set_major_locator(MultipleLocator(25.0))
    ax.yaxis.set_major_locator(MultipleLocator(0.5))
    cl = {1: {"charge": ln, "discharge": None}}
    p = session_path("ec_locator.pkl")
    S.dump_ec_session(p, fig=fig, ax=ax, cycle_lines=cl, skip_confirm=True)
    fig2, ax2, cl2 = loaded(S.load_ec_session(p))
    assert isinstance(ax2.xaxis.get_major_locator(), MultipleLocator)
    assert abs(float(ax2.xaxis.get_major_locator()._edge.step) - 25.0) < 1e-9

    scripter = ScriptedInput(["q"])
    _patch_menu_input(monkeypatch, scripter, EI)
    _patch_dialogs(monkeypatch, EI, EI)
    _patch_screen_color(monkeypatch)
    file_data = [{
        "filename": "a.mpt", "display_name": "a", "visible": True,
        "cycle_lines": cl2, "all_cycles": [1],
    }]
    EI.electrochem_interactive_menu(
        fig2, ax2, cycle_lines=cl2, file_data=file_data, canvas_mode=True,
    )
    assert isinstance(ax2.xaxis.get_major_locator(), MultipleLocator)
    assert abs(float(ax2.xaxis.get_major_locator()._edge.step) - 25.0) < 1e-9
    plt.close(fig)
    plt.close(fig2)


def test_ec_hidden_file_keeps_selected_cycles_on_save(session_path):
    fig, ax = plt.subplots()
    file_data = []
    for name in ("A", "B"):
        cl = {}
        for cyc in (1, 2, 31):
            ch, = ax.plot([0, 1], [0, float(cyc)], label=f"{name}:{cyc}")
            cl[cyc] = {"charge": ch, "discharge": None}
        ECY._set_visible_cycles(cl, [1, 31])
        file_data.append({
            "filename": f"{name}.csv",
            "display_name": name,
            "filepath": f"{name}.csv",
            "visible": True,
            "cycle_lines": cl,
            "selected_cycles": [1, 31],
        })
    # Hide file B the same way the interactive menu does
    f_b = file_data[1]
    f_b["selected_cycles"] = ECY._visible_cycle_numbers(f_b["cycle_lines"])
    f_b["visible"] = False
    for parts in f_b["cycle_lines"].values():
        parts["charge"].set_visible(False)

    p = session_path("ec_hidden_cycles.pkl")
    S.dump_ec_session(p, fig=fig, ax=ax, cycle_lines={}, file_data=file_data, skip_confirm=True)
    with open(p, "rb") as fh:
        sess = pickle.load(fh)
    assert sess["file_data"][1]["visible"] is False
    assert sess["file_data"][1]["visible_cycles"] == [1, 31]

    _fig2, _ax2, _cl, fd2 = loaded(S.load_ec_session(p))
    assert fd2[1]["visible"] is False
    assert fd2[1].get("selected_cycles") == [1, 31]
    # All lines hidden while file is hidden
    assert all(not parts["charge"].get_visible() for parts in fd2[1]["cycle_lines"].values())
    plt.close(fig)


def test_ec_style_export_uses_screen_tick_truth():
    fig, ax = plt.subplots()
    (ln,) = ax.plot([0, 1], [3, 4], label="1")
    fig.canvas.draw()
    ax.tick_params(axis="y", which="major", labelleft=False)
    stale = {
        "b_ticks": True, "b_labels": True, "t_ticks": False, "t_labels": False,
        "l_ticks": True, "l_labels": True, "r_ticks": False, "r_labels": False,
        "mbx": False, "mtx": False, "mly": False, "mry": False,
    }
    cfg = _get_style_snapshot(fig, ax, {1: {"charge": ln, "discharge": None}}, stale)
    assert cfg["wasd_state"]["left"]["labels"] is False
    plt.close(fig)


def test_xy_session_tick_state_synced_with_wasd(session_path, fake_args):
    x = np.linspace(0.0, 10.0, 50)
    y = np.sin(x)
    fig, ax = plt.subplots()
    ax.plot(x, y, label="c1")
    fig.canvas.draw()
    ax.tick_params(axis="y", which="major", labelleft=False)
    stale = {
        "b_ticks": True, "b_labels": True, "t_ticks": False, "t_labels": False,
        "l_ticks": True, "l_labels": True, "r_ticks": False, "r_labels": False,
        "mbx": False, "mtx": False, "mly": False, "mry": False,
    }
    p = session_path("xy_tick_sync.pkl")
    S.dump_session(
        p, fig=fig, ax=ax,
        x_data_list=[x], y_data_list=[y], orig_y=[y],
        offsets_list=[0.0], labels=["c1"], delta=0.0, args=fake_args,
        tick_state=dict(stale), skip_confirm=True,
    )
    with open(p, "rb") as fh:
        sess = pickle.load(fh)
    assert sess["wasd_state"]["left"]["labels"] is False
    assert sess["tick_state"]["l_labels"] is False
    plt.close(fig)


def test_cpc_session_save_reflects_screen_when_bookkeeping_stale(session_path):
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc_c = ax.scatter([1, 2], [100, 110], marker="s", label="ch")
    sc_d = ax.scatter([1, 2], [90, 95], marker="s", label="dch")
    sc_e = ax2.scatter([1, 2], [95, 98], marker="^", label="eff")
    fig.canvas.draw()
    ax.tick_params(axis="y", which="major", labelleft=False)
    ax._saved_tick_state = {
        "b_ticks": True, "b_labels": True, "t_ticks": False, "t_labels": False,
        "l_ticks": True, "l_labels": True, "r_ticks": True, "r_labels": True,
        "mbx": False, "mtx": False, "mly": False, "mry": False,
    }
    fig._cpc_wasd_state = {
        "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "top": {"spine": False, "ticks": False, "minor": False, "labels": False, "title": False},
        "right": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
    }
    p = session_path("cpc_stale_labels.pkl")
    S.dump_cpc_session(
        p, fig=fig, ax=ax, ax2=ax2,
        sc_charge=sc_c, sc_discharge=sc_d, sc_eff=sc_e,
        skip_confirm=True,
    )
    with open(p, "rb") as fh:
        sess = pickle.load(fh)
    assert sess["wasd_state"]["left"]["labels"] is False
    plt.close(fig)


def test_operando_session_restores_ion_params_in_time_mode(session_path):
    """Time-mode sessions must still restore ``_ion_params`` for ey."""
    from test_operando_roundtrip import _build_operando_figure

    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    ec_ax._ec_y_mode = "time"
    ec_ax._ion_params = {"mass_mg": 7.5, "cap_per_ion_mAh_g": 120.0, "start_ions": 0.5}
    p = session_path("op_ion_params_time.pkl")
    S.dump_operando_session(
        p, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax, skip_confirm=True,
    )
    _fig2, _ax2, _im2, _cbar2, ec_ax2 = loaded(S.load_operando_session(p))
    assert getattr(ec_ax2, "_ion_params", None) == {
        "mass_mg": 7.5, "cap_per_ion_mAh_g": 120.0, "start_ions": 0.5,
    }
    plt.close(fig)
    plt.close(_fig2)


def test_batch_ec_file_hide_preserves_selected_cycles():
    """Batch ``v`` must stash cycle ids like interactive (shared helper)."""
    from batplot.plot_modes.batch_session.ec_batch_helpers import ec_set_file_visibility

    fig, ax = plt.subplots()
    cl = {}
    for cyc in (1, 2, 31):
        ch, = ax.plot([0, 1], [0, float(cyc)])
        cl[cyc] = {"charge": ch, "discharge": None}
    ECY._set_visible_cycles(cl, [1, 31])
    f_entry = {"filename": "A.csv", "visible": True, "cycle_lines": cl}
    ec_set_file_visibility(f_entry, False)
    assert f_entry["visible"] is False
    assert f_entry["selected_cycles"] == [1, 31]
    assert all(not parts["charge"].get_visible() for parts in cl.values())
    ec_set_file_visibility(f_entry, True)
    assert f_entry["visible"] is True
    assert cl[1]["charge"].get_visible() is True
    assert cl[2]["charge"].get_visible() is False
    assert cl[31]["charge"].get_visible() is True
    plt.close(fig)


def test_ec_hide_all_does_not_wipe_already_hidden_selection():
    """``v`` → ``a`` re-hides every file; must not stash ``[]`` over a prior selection."""
    fig, ax = plt.subplots()
    files = []
    for name in ("A", "B"):
        cl = {}
        for cyc in (1, 2, 31):
            ch, = ax.plot([0, 1], [0, float(cyc)])
            cl[cyc] = {"charge": ch, "discharge": None}
        ECY._set_visible_cycles(cl, [1, 31])
        files.append({"filename": f"{name}.csv", "visible": True, "cycle_lines": cl})
    # Hide B first (stashes 1+31), then hide-all including B again.
    ECY.set_ec_file_visibility(files[1], False)
    assert files[1]["selected_cycles"] == [1, 31]
    for f in files:
        ECY.set_ec_file_visibility(f, False)
    assert files[1]["selected_cycles"] == [1, 31]
    ECY.set_ec_file_visibility(files[1], True)
    assert files[1]["cycle_lines"][1]["charge"].get_visible() is True
    assert files[1]["cycle_lines"][2]["charge"].get_visible() is False
    assert files[1]["cycle_lines"][31]["charge"].get_visible() is True
    plt.close(fig)


def test_batch_ec_nice_ticks_preserves_multiple_locator():
    from batplot.plot_modes.batch_session.ec_batch_helpers import ec_apply_nice_ticks

    fig, ax = plt.subplots()
    ax.plot([0, 100], [0, 1])
    ax.xaxis.set_major_locator(MultipleLocator(25.0))
    ax.yaxis.set_major_locator(MultipleLocator(0.2))
    ec_apply_nice_ticks(ax)
    assert isinstance(ax.xaxis.get_major_locator(), MultipleLocator)
    assert abs(float(ax.xaxis.get_major_locator()._edge.step) - 25.0) < 1e-9
    assert isinstance(ax.yaxis.get_major_locator(), MultipleLocator)
    plt.close(fig)


def test_operando_style_restores_ion_params_in_time_mode(monkeypatch):
    """Style import (p/i) must stash ``_ion_params`` even when y_mode is time."""
    from test_operando_roundtrip import _build_operando_figure
    from batplot.plot_modes.operando import style as OS
    from batplot.plot_modes.operando.style_apply import apply_operando_ec_style_config

    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    ec_ax._ec_y_mode = "time"
    ec_ax._ion_params = {"mass_mg": 7.5, "cap_per_ion_mAh_g": 120.0, "start_ions": 0.5}
    cfg, _ = OS.build_operando_ec_style_config_v2(fig, ax, im, cbar, ec_ax, "ps")
    assert cfg["ec"].get("y_mode") == "time"
    assert cfg["ec"].get("ion_params") == {
        "mass_mg": 7.5, "cap_per_ion_mAh_g": 120.0, "start_ions": 0.5,
    }

    fig2, ax2, im2, cbar2, ec_ax2 = _build_operando_figure()
    assert not getattr(ec_ax2, "_ion_params", None)
    monkeypatch.setattr("builtins.input", lambda *a, **k: "")
    apply_operando_ec_style_config(
        cfg, fig=fig2, ax=ax2, im=im2, cbar=cbar2, ec_ax=ec_ax2, silent=True,
    )
    assert getattr(ec_ax2, "_ion_params", None) == {
        "mass_mg": 7.5, "cap_per_ion_mAh_g": 120.0, "start_ions": 0.5,
    }
    plt.close(fig)
    plt.close(fig2)


def test_ec_style_dual_keeps_custom_xlabel(monkeypatch):
    """Dual-axis style apply must not clobber a renamed bottom xlabel."""
    from batplot.plot_modes.electrochem.style_apply import apply_ec_style_config

    fig, ax = plt.subplots()
    (ln,) = ax.plot([0.0, 50.0], [3.0, 4.0])
    ln._orig_xdata_gc = np.asarray([0.0, 50.0], dtype=float)  # type: ignore[attr-defined]
    tick_state = {
        "bx": True, "tx": False, "ly": True, "ry": False,
        "mbx": False, "mtx": False, "mly": False, "mry": False,
    }
    cfg = {
        "kind": "ec_style",
        "axis_labels": {"xlabel": "Custom Cap", "ylabel": "E / V"},
        "xaxis_dual": {
            "mode": "dual",
            "c_theoretical": 100.0,
            "swapped": False,
            "top_axis": {"xlabel": "ions", "xlabel_visible": True},
        },
        "wasd_state": {
            "top": {"ticks": True, "labels": False, "title": True, "spine": True, "minor": False},
            "bottom": {"ticks": True, "labels": True, "title": True, "spine": True, "minor": False},
            "left": {"ticks": True, "labels": True, "title": True, "spine": True, "minor": False},
            "right": {"ticks": False, "labels": False, "title": False, "spine": False, "minor": False},
        },
    }
    monkeypatch.setattr(
        "batplot.plot_modes.electrochem.style_apply.safe_input",
        lambda *a, **k: "",
    )
    apply_ec_style_config(
        cfg, fig=fig, ax=ax, cycle_lines={1: {"charge": ln, "discharge": None}},
        file_data=None, tick_state=tick_state, silent=True,
    )
    assert ax.get_xlabel() == "Custom Cap"
    plt.close(fig)

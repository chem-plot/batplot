"""Keystroke-driven smoke tests for ALL interactive menu dispatch loops.

Covers every top-level key (and nested subkey walks) for:
  XY, electrochem, CPC, histo, operando — single-session interactive menus.

Design notes
------------
* ``canvas_mode=True`` makes top-level ``q`` quit immediately (no y/n), except
  histo which has no canvas_mode and needs ``q`` then ``y``.
* ``ScriptedInput`` returns scripted answers, then ``"q"`` forever so nested
  menus unwind. A hard call cap turns a hang into a failure.
* File dialogs are patched to ``None`` so ``e/p/i/s/oe/os/...`` cannot block.
* Screen color picker (``e`` inside color menus) is patched so it never opens
  a magnifier / blocks on terminal ``Picker>`` during keystroke smoke runs.
"""

from __future__ import annotations

import types

import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot.plot_modes.cpc import interactive as CI
from batplot.plot_modes.common import menu_rendering as MR
from batplot.plot_modes.common import terminal as T
from batplot.plot_modes.electrochem import actions as EA
from batplot.plot_modes.electrochem import interactive as EI
from batplot.plot_modes.histo import actions as HA
from batplot.plot_modes.histo import interactive as HI
from batplot.plot_modes.histo.load import TableData, build_bin_edges
from batplot.plot_modes.histo.plot import HistoState, HistoStyle
from batplot.plot_modes.histo.wizard import HistoSetup
from batplot.plot_modes.operando import actions as OA
from batplot.plot_modes.operando import interactive as OI
from batplot.plot_modes.xy import actions as XA
from batplot.plot_modes.xy import interactive as XI
from batplot.plot_modes.xy import peaks as XP


class ScriptedInput:
    """Replay answers, then return ``q`` forever. Cap calls to catch hangs.

    After the script is exhausted, prompts that look like a quit confirmation
    get ``y`` (needed for histo, which has no ``canvas_mode``).
    """

    def __init__(self, answers, max_calls=800, quit_confirm_y: bool = False):
        self._answers = list(answers)
        self._i = 0
        self._calls = 0
        self.max_calls = max_calls
        self.quit_confirm_y = quit_confirm_y

    def __call__(self, *args, **_kwargs):
        self._calls += 1
        assert self._calls <= self.max_calls, (
            "interactive menu asked for input more than "
            f"{self.max_calls} times - possible infinite loop"
        )
        if self._i < len(self._answers):
            ans = self._answers[self._i]
            self._i += 1
            return ans
        prompt = str(args[0]) if args else ""
        if self.quit_confirm_y and "quit" in prompt.lower():
            return "y"
        return "q"


def _patch_menu_input(monkeypatch, scripter, *modules):
    """Patch all menu input entry points used by interactive loops."""
    monkeypatch.setattr(T, "safe_input", scripter)
    monkeypatch.setattr("builtins.input", scripter)

    def _prompt_menu_key(*_args, **_kwargs):
        return scripter().strip().lower()

    monkeypatch.setattr(T, "prompt_menu_key", _prompt_menu_key)
    monkeypatch.setattr(MR, "prompt_menu_key", _prompt_menu_key)
    for mod in modules:
        if hasattr(mod, "_safe_input"):
            monkeypatch.setattr(mod, "_safe_input", scripter)
        if hasattr(mod, "safe_input"):
            monkeypatch.setattr(mod, "safe_input", scripter)
        if hasattr(mod, "prompt_menu_key"):
            monkeypatch.setattr(mod, "prompt_menu_key", _prompt_menu_key)

    # Screen eyedropper opens a GUI subprocess + blocks on real stdin — never
    # allow it in keystroke smoke tests (top-level ``e`` is export; color ``e``
    # would otherwise hang the suite).
    def _no_screen_pick(*_a, **_k):
        return None

    monkeypatch.setattr(
        "batplot.color_utils.prompt_screen_color", _no_screen_pick, raising=False
    )
    monkeypatch.setattr(
        "batplot.screen_color.pick_screen_colors", lambda **_k: [], raising=False
    )


def _noop_dialog(*_a, **_k):
    return None


def _patch_dialogs(monkeypatch, *modules):
    for mod in modules:
        for name in ("choose_save_path", "choose_style_file"):
            if hasattr(mod, name):
                monkeypatch.setattr(mod, name, _noop_dialog)
    # CIF add file picker (operando / XY)
    try:
        import batplot.utils as U

        monkeypatch.setattr(U, "_ask_file_dialog", _noop_dialog, raising=False)
    except Exception:
        pass


def _patch_screen_color(monkeypatch):
    """Never launch the real eyedropper during menu keystroke smoke tests."""
    import batplot.color_utils as CU
    import batplot.screen_color as SC

    def _noop_prompt(*_a, **_k):
        return None

    monkeypatch.setattr(CU, "prompt_screen_color", _noop_prompt)
    monkeypatch.setattr(SC, "pick_screen_colors", lambda *a, **k: [])
    monkeypatch.setattr(SC, "pick_screen_color", lambda *a, **k: None)
    # Modules that did ``from ...color_utils import prompt_screen_color``
    for mod_name in (
        "batplot.plot_modes.xy.colors",
        "batplot.plot_modes.xy.cif",
        "batplot.plot_modes.histo.colors",
        "batplot.plot_modes.electrochem.colors",
        "batplot.plot_modes.electrochem.spine_colors",
        "batplot.plot_modes.cpc.colors",
        "batplot.plot_modes.cpc.interactive",
        "batplot.plot_modes.operando.colors",
        "batplot.plot_modes.operando.line_style",
        "batplot.plot_modes.operando.grid",
        "batplot.plot_modes.batch_session.menu_xy",
        "batplot.plot_modes.common.menus",
    ):
        try:
            mod = __import__(mod_name, fromlist=["*"])
        except Exception:
            continue
        if hasattr(mod, "prompt_screen_color"):
            monkeypatch.setattr(mod, "prompt_screen_color", _noop_prompt, raising=False)
        if hasattr(mod, "run_color_token_input_loop"):
            # common.menus imports the loop; patching CU is enough if it calls CU.prompt
            pass


# ---------------------------------------------------------------------------
# Fixtures / drivers
# ---------------------------------------------------------------------------


def _build_ec_figure(*, overview: bool = False, dqdv: bool = False):
    fig, ax = plt.subplots()
    cap = np.linspace(0.0, 150.0, 40)
    volt = np.linspace(3.0, 4.2, 40)
    charge, = ax.plot(cap, volt, color="#ff0000", lw=2.0, label="cycle 1 charge")
    discharge, = ax.plot(cap[::-1], volt, color="#0000ff", lw=1.5, label="cycle 1 discharge")
    ax.set_xlabel("Capacity (mAh/g)")
    ax.set_ylabel("dQ/dV (arb)" if dqdv else "Voltage (V)")
    if dqdv:
        ax._is_dqdv_mode = True  # type: ignore[attr-defined]
    if overview:
        fig._ec_overview_enabled = True  # type: ignore[attr-defined]
    cycle_lines = {1: {"charge": charge, "discharge": discharge}}
    file_data = [
        {
            "filename": "a.mpt",
            "display_name": "a",
            "visible": True,
            "cycle_lines": cycle_lines,
            "all_cycles": [1],
        }
    ]
    return fig, ax, cycle_lines, file_data


def drive_ec(monkeypatch, keys, *, overview=False, dqdv=False, max_calls=800):
    scripter = ScriptedInput(keys, max_calls=max_calls)
    _patch_menu_input(monkeypatch, scripter, EI)
    _patch_dialogs(monkeypatch, EA, EI)
    _patch_screen_color(monkeypatch)
    fig, ax, cycle_lines, file_data = _build_ec_figure(overview=overview, dqdv=dqdv)
    EI.electrochem_interactive_menu(
        fig, ax, cycle_lines=cycle_lines, file_data=file_data, canvas_mode=True
    )
    plt.close(fig)
    return scripter


def _build_operando_figure():
    fig, ax = plt.subplots()
    Z = np.random.default_rng(0).random((50, 80))
    im = ax.imshow(
        Z, aspect="auto", origin="lower", extent=(10.0, 40.0, 0.0, 20.0), cmap="viridis"
    )
    cbar = fig.colorbar(im, ax=ax)
    im._operando_cmap_name = "viridis"  # type: ignore[attr-defined]
    ax._operando_cif_tick_series = [  # type: ignore[attr-defined]
        ("phase1", "/tmp/a.cif", [1.0, 2.0], 0.709, 5.0, "#1f77b4"),
    ]
    ax._operando_cif_hkl_label_map = {}  # type: ignore[attr-defined]
    fig._operando_cif_y_positions = [0.1]  # type: ignore[attr-defined]
    fig._operando_axis_mode = "Q"  # type: ignore[attr-defined]
    fig._operando_wl = 0.709  # type: ignore[attr-defined]
    ec_ax = fig.add_axes((0.78, 0.1, 0.18, 0.8))
    t = np.linspace(0.0, 20.0, 30)
    (line,) = ec_ax.plot(np.linspace(3.0, 4.2, 30), t)
    ec_ax._ec_line = line  # type: ignore[attr-defined]
    ec_ax._ec_time_h = t  # type: ignore[attr-defined]
    ec_ax._ec_current_mA = np.ones_like(t)  # type: ignore[attr-defined]
    ec_ax.set_xlabel("Voltage (V)")
    ec_ax.set_ylabel("Time (h)")
    return fig, ax, im, cbar, ec_ax


def drive_op(monkeypatch, keys, max_calls=800):
    scripter = ScriptedInput(keys, max_calls=max_calls)
    _patch_menu_input(monkeypatch, scripter, OI)
    _patch_dialogs(monkeypatch, OA, OI)
    _patch_screen_color(monkeypatch)
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    OI.operando_ec_interactive_menu(fig, ax, im, cbar, ec_ax, canvas_mode=True)
    # operando q in canvas_mode closes fig
    try:
        plt.close(fig)
    except Exception:
        pass
    return scripter


def _build_cpc_figure():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    cyc = np.arange(1, 6, dtype=float)
    sc_charge = ax.scatter(cyc, np.linspace(150.0, 120.0, 5), c="red")
    sc_discharge = ax.scatter(cyc, np.linspace(148.0, 118.0, 5), c="blue")
    sc_eff = ax2.scatter(cyc, np.linspace(95.0, 99.0, 5), c="green")
    ax.set_xlabel("Cycle number")
    ax.set_ylabel("Capacity (mAh/g)")
    fig._cpc_overview_enabled = True  # type: ignore[attr-defined]
    return fig, ax, ax2, sc_charge, sc_discharge, sc_eff


def drive_cpc(monkeypatch, keys, max_calls=800):
    scripter = ScriptedInput(keys, max_calls=max_calls)
    _patch_menu_input(monkeypatch, scripter, CI)
    _patch_dialogs(monkeypatch, CI)
    _patch_screen_color(monkeypatch)
    fig, ax, ax2, sc_c, sc_d, sc_e = _build_cpc_figure()
    CI.cpc_interactive_menu(fig, ax, ax2, sc_c, sc_d, sc_e, canvas_mode=True)
    plt.close(fig)
    return scripter


def _build_xy_figure():
    x = np.linspace(20.0, 40.0, 101)
    y = np.sin(x)
    fig, ax = plt.subplots()
    ax.plot(x, y, label="c1")
    ax.set_xlabel("Two theta")
    ax.set_ylabel("Intensity")
    return fig, ax, [y.copy()], [x.copy()], ["c1"], [y.copy()]


def drive_xy(monkeypatch, keys, max_calls=800):
    scripter = ScriptedInput(keys, max_calls=max_calls)
    _patch_menu_input(monkeypatch, scripter, XI)
    _patch_dialogs(monkeypatch, XA, XP, XI)
    _patch_screen_color(monkeypatch)
    fig, ax, y_list, x_list, labels, orig_y = _build_xy_figure()
    args = types.SimpleNamespace(
        stack=False,
        norm=False,
        ro=False,
        xrange=None,
        files=["a.xy"],
        autoscale=False,
    )
    XI.interactive_menu(
        fig,
        ax,
        y_list,
        x_list,
        labels,
        orig_y,
        [],
        0.0,
        "Two theta",
        args,
        [x.copy() for x in x_list],
        [y.copy() for y in orig_y],
        [0.0],
        False,
        False,
        False,
        False,
        False,
        canvas_mode=True,
    )
    plt.close(fig)
    return scripter


def _build_histo_state():
    fig, ax = plt.subplots()
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 2.5, 3.5])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = HistoState(setup=setup, style=HistoStyle(), source_path="/tmp/histo.csv")
    return fig, ax, state


def drive_histo(monkeypatch, keys, max_calls=800):
    # histo has no canvas_mode — after nested menus unwind, top-level q then y
    scripter = ScriptedInput(list(keys), max_calls=max_calls, quit_confirm_y=True)
    _patch_menu_input(monkeypatch, scripter, HI)
    _patch_dialogs(monkeypatch, HA, HI)
    _patch_screen_color(monkeypatch)
    fig, ax, state = _build_histo_state()

    def _loader(*_a, **_k):
        return TableData(
            path=state.source_path or "/tmp/histo.csv",
            headers=["Length"],
            rows=[[f"{v:g}"] for v in state.setup.values],
        )

    HI.histo_interactive_menu(fig, ax, state, table_loader=_loader)
    plt.close(fig)
    return scripter


# ---------------------------------------------------------------------------
# Baseline reachability
# ---------------------------------------------------------------------------


def test_ec_menu_enters_and_quits(monkeypatch):
    drive_ec(monkeypatch, ["q"])


def test_op_menu_enters_and_quits(monkeypatch):
    drive_op(monkeypatch, ["q"])


def test_cpc_menu_enters_and_quits(monkeypatch):
    drive_cpc(monkeypatch, ["q"])


def test_xy_menu_enters_and_quits(monkeypatch):
    drive_xy(monkeypatch, ["q"])


def test_histo_menu_enters_and_quits(monkeypatch):
    drive_histo(monkeypatch, [])


@pytest.mark.parametrize("mod_drive", ["ec", "op", "cpc", "xy"])
def test_unknown_key_then_quit(monkeypatch, mod_drive):
    drivers = {
        "ec": drive_ec,
        "op": drive_op,
        "cpc": drive_cpc,
        "xy": drive_xy,
    }
    drivers[mod_drive](monkeypatch, ["zzz", "q"])


# ---------------------------------------------------------------------------
# EVERY top-level key — all modes
# ---------------------------------------------------------------------------

# XY: all dispatched keys except hidden jump game ``w`` (interactive loop).
XY_TOP_KEYS = [
    "c", "f", "l", "t", "g", "h", "sm", "a", "o", "r", "x", "y", "d",
    "cif", "z", "j", "v", "n", "p", "i", "e", "s", "b",
    "os", "ops", "opsg", "oe",
]

# EC GC path (not dQdV): include overview ``o``.
EC_TOP_KEYS = [
    "f", "l", "k", "t", "h", "d", "v", "g", "c", "r", "a", "x", "y", "ra",
    "n", "o", "p", "i", "e", "s", "b", "oe", "os", "ops", "opsg",
]

# EC dQdV-only keys
EC_DQDV_KEYS = ["sm", "2d"]

# CPC
CPC_TOP_KEYS = [
    "f", "l", "m", "c", "k", "d", "ry", "t", "h", "g", "v", "r", "x", "y",
    "ie", "o", "n", "p", "i", "e", "s", "b", "oe", "os", "ops", "opsg",
]

# Histo (quit appended by driver)
HISTO_TOP_KEYS = [
    "c", "f", "a", "l", "t", "g", "w", "r", "x", "y",
    "e", "p", "i", "s", "b", "oe", "os", "ops", "opsg",
]

# Operando (includes ``k`` spine colors — previously missing from this list)
OP_TOP_KEYS = [
    "oc", "el", "v", "t", "k", "l", "f", "g", "h", "ow", "ew", "r",
    "ox", "oy", "oz", "or", "c", "pk", "et", "ex", "ey", "er", "eg",
    "n", "p", "i", "e", "s", "b", "oe", "os", "ops", "opsg",
]


@pytest.mark.parametrize("branch_key", XY_TOP_KEYS)
def test_xy_every_toplevel_key(monkeypatch, branch_key):
    drive_xy(monkeypatch, [branch_key])


@pytest.mark.parametrize("branch_key", EC_TOP_KEYS)
def test_ec_every_toplevel_key(monkeypatch, branch_key):
    drive_ec(monkeypatch, [branch_key], overview=True)


@pytest.mark.parametrize("branch_key", EC_DQDV_KEYS)
def test_ec_dqdv_toplevel_keys(monkeypatch, branch_key):
    drive_ec(monkeypatch, [branch_key], dqdv=True, max_calls=1200)


@pytest.mark.parametrize("branch_key", CPC_TOP_KEYS)
def test_cpc_every_toplevel_key(monkeypatch, branch_key):
    drive_cpc(monkeypatch, [branch_key])


@pytest.mark.parametrize("branch_key", HISTO_TOP_KEYS)
def test_histo_every_toplevel_key(monkeypatch, branch_key):
    drive_histo(monkeypatch, [branch_key])


@pytest.mark.parametrize("branch_key", OP_TOP_KEYS)
def test_op_every_toplevel_key(monkeypatch, branch_key):
    drive_op(monkeypatch, [branch_key])


# ---------------------------------------------------------------------------
# Nested subkey walks through the live interactive loops
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "script",
    [
        # color → user colors back
        ["c", "u", "q", "q"],
        # color → spine colors every side (spine tokens at Colors> prompt)
        ["c", "d:red", "a:blue", "w:green", "s:#0033aa", "q"],
        # font family/size/weight/highlight
        ["f", "f", "q", "s", "q", "b", "q", "h", "q", "q"],
        # line style branches
        ["l", "c", "q", "f", "q", "g", "l", "ld", "d", "da", "dd", "q"],
        # spines list + every side×prop token
        ["t", "list", "w1", "a2", "s3", "d4", "w5", "i", "l", "q", "n", "q", "m", "q", "p", "q", "q"],
        # size
        ["g", "p", "q", "c", "q", "q"],
        # legend
        ["h", "v", "s", "q", "q"],
        # smoothing reduce/smooth
        ["sm", "r", "q", "s", "q", "q"],
        # rename
        ["r", "c", "q", "x", "q", "y", "q", "q"],
        # ranges
        ["x", "a", "q"],
        ["y", "a", "q"],
        # derivative open+quit
        ["d", "q"],
        # cif submenu keys
        ["cif", "z", "q", "t", "q", "v", "q", "c", "q", "q"],
        # peaks
        ["v", "q"],
        # offset
        ["o", "q"],
        # arrange
        ["a", "q"],
    ],
)
def test_xy_nested_subkey_scripts(monkeypatch, script):
    drive_xy(monkeypatch, script)


@pytest.mark.parametrize(
    "script",
    [
        ["f", "f", "q", "s", "q", "b", "q", "h", "q", "q"],
        ["l", "c", "q", "f", "q", "g", "l", "q"],
        ["k", "u", "q", "q"],
        # spine colors — every side
        ["k", "d:red", "a:blue", "w:green", "s:#0033aa", "q"],
        ["t", "list", "w1", "a2", "s3", "d4", "q"],
        ["h", "t", "p", "q", "q"],
        ["d", "c", "d", "b", "q"],
        ["c", "u", "q", "q"],
        ["r", "x", "q", "y", "q", "q"],
        ["x", "a", "q"],
        ["y", "a", "q"],
        ["o", "c", "q", "r", "q", "s", "q", "q"],
        ["a", "q"],  # dual-axis menu open+quit
    ],
)
def test_ec_nested_subkey_scripts(monkeypatch, script):
    drive_ec(monkeypatch, script, overview=True)


@pytest.mark.parametrize(
    "script",
    [
        ["f", "f", "q", "s", "q", "q"],
        ["l", "f", "q", "g", "q"],
        ["c", "ly", "q", "ry", "q", "u", "q", "s", "q", "q"],
        ["d", "c", "d", "b", "q"],
        ["ry", "t", "q"],
        ["t", "list", "q"],
        ["h", "t", "p", "q", "q"],
        ["g", "p", "q", "c", "q", "q"],
        ["r", "x", "q", "ly", "q", "ry", "q", "q"],
        ["y", "ly", "q", "ry", "q", "q"],
        ["o", "c", "q", "r", "q", "s", "q", "q"],
    ],
)
def test_cpc_nested_subkey_scripts(monkeypatch, script):
    drive_cpc(monkeypatch, script)


@pytest.mark.parametrize(
    "script",
    [
        ["c", "u", "q", "q"],
        ["f", "f", "q", "s", "q", "q"],
        ["a", "t", "c", "q", "w", "q", "l", "q", "q"],
        ["l", "f", "q", "g", "w", "q", "q"],
        ["t", "h", "d", "n", "m", "q", "list", "q"],
        ["g", "p", "q", "c", "q", "q"],
        ["r", "x", "q", "y", "q", "t", "q", "q"],
        ["y", "a", "q"],
    ],
)
def test_histo_nested_subkey_scripts(monkeypatch, script):
    drive_histo(monkeypatch, script)


@pytest.mark.parametrize(
    "script",
    [
        ["oc", "plasma", "q"],
        ["el", "c", "q", "l", "q", "q"],
        ["v", "1", "2", "3", "m", "q", "q"],
        ["t", "o", "q", "q"],  # pane pick then spine quit
        # spine colors — both panes, every side token, then quit
        ["k", "o", "d:red", "a:blue", "w:green", "s:#cc00cc", "q", "q"],
        ["k", "e", "d:magenta", "a:orange", "q", "q"],
        ["f", "f", "q", "s", "q", "q"],
        ["g", "c", "q", "o", "q", "e", "q", "h", "q", "s", "q", "q"],
        ["or", "x", "q", "y", "q", "q"],
        ["c", "z", "q", "t", "q", "c", "q", "f", "q", "r", "q", "n", "x", "q", "q"],
        ["pk", "e", "q"],
        ["eg", "t", "a", "q", "s", "q", "c", "q", "w", "q", "q"],
        ["er", "x", "q", "y", "q", "q"],
        ["ey", "q"],
        ["ex", "a", "q"],
        ["et", "q"],
        ["ox", "a", "q"],
        ["oy", "a", "q"],
        ["oz", "q"],
    ],
)
def test_op_nested_subkey_scripts(monkeypatch, script):
    drive_op(monkeypatch, script)


# ---------------------------------------------------------------------------
# One-shot: fire ALL top-level keys in a single session per mode
# ---------------------------------------------------------------------------


def _script_each_key(keys, *, menu_keys, backout=("q",), quit_tail=("q",)):
    """Open each key and back out of submenus so later keys are not swallowed.

    Without this, the first submenu key (e.g. operando ``oc``) consumes the
    rest of the script as nested answers — a false-green one-session walk.
    Instant toggles are NOT given a cushion ``q`` (that would quit the session).
    Exactly one ``q`` returns to main for most menus; a second would quit.
    """
    out: list[str] = []
    for k in keys:
        out.append(k)
        if k in menu_keys:
            if k == "oc":
                out.extend(["plasma", "q"])
            else:
                out.extend(list(backout))
    out.extend(list(quit_tail))
    return out


# Menu keys need a single backout ``q``. Instant toggles/dialogs must not —
# an extra ``q`` quits the whole session (false-green one-session walks).
_XY_MENU = {
    "c", "f", "l", "t", "g", "h", "sm", "a", "o", "r", "x", "y", "d",
    "cif", "z", "v", "p",
}
_EC_MENU = {
    "f", "l", "k", "t", "h", "d", "c", "r", "a", "x", "y", "o", "p",
}
_CPC_MENU = {
    "f", "l", "m", "c", "k", "d", "ry", "t", "h", "g", "r", "x", "y", "o", "p",
}
_HISTO_MENU = {
    "c", "f", "a", "l", "t", "g", "w", "r", "x", "y", "p",
}
_OP_MENU = {
    "oc", "el", "v", "t", "k", "l", "f", "g", "h", "ow", "ew",
    "ox", "oy", "oz", "or", "c", "pk", "et", "ex", "ey", "er", "eg", "p",
}


def test_xy_all_keys_one_session(monkeypatch):
    drive_xy(
        monkeypatch,
        _script_each_key(XY_TOP_KEYS, menu_keys=_XY_MENU),
        max_calls=4000,
    )


def test_ec_all_keys_one_session(monkeypatch):
    drive_ec(
        monkeypatch,
        _script_each_key(EC_TOP_KEYS, menu_keys=_EC_MENU),
        overview=True,
        max_calls=4000,
    )


def test_cpc_all_keys_one_session(monkeypatch):
    drive_cpc(
        monkeypatch,
        _script_each_key(CPC_TOP_KEYS, menu_keys=_CPC_MENU),
        max_calls=4000,
    )


def test_histo_all_keys_one_session(monkeypatch):
    drive_histo(
        monkeypatch,
        _script_each_key(HISTO_TOP_KEYS, menu_keys=_HISTO_MENU, quit_tail=()),
        max_calls=4000,
    )


def test_op_all_keys_one_session(monkeypatch):
    drive_op(
        monkeypatch,
        _script_each_key(OP_TOP_KEYS, menu_keys=_OP_MENU),
        max_calls=5000,
    )

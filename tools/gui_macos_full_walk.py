#!/usr/bin/env python3
"""Standalone macOS MacOSX-backend interactive menu walk.

Runs OUTSIDE pytest (conftest forces Agg). Opens real FigureCanvasMac windows
and drives every top-level key + critical nested submenus via scripted input.

Usage (from repo root)::

    MPLBACKEND=MacOSX python tools/gui_macos_full_walk.py

Exit 0 = all modes walked without crash. Keys are fed through the same
``safe_input`` / ``prompt_menu_key`` paths the GUI menus use (not mouse clicks).
"""

from __future__ import annotations

import os
import sys
import traceback
import types

# Force GUI backend BEFORE batplot._mpl_backend import (it honors MPLBACKEND).
os.environ["MPLBACKEND"] = "MacOSX"

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

import matplotlib

matplotlib.use("MacOSX", force=True)

import matplotlib.pyplot as plt
import numpy as np

from batplot._mpl_backend import ensure_gui_backend, is_interactive_backend
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

# Re-assert after batplot imports (some paths may touch pyplot).
ensure_gui_backend()
matplotlib.use("MacOSX", force=True)


class ScriptedInput:
    def __init__(self, answers, max_calls=4000, quit_confirm_y: bool = False):
        self._answers = list(answers)
        self._i = 0
        self._calls = 0
        self.max_calls = max_calls
        self.quit_confirm_y = quit_confirm_y

    def __call__(self, *args, **_kwargs):
        self._calls += 1
        if self._calls > self.max_calls:
            raise RuntimeError(f"input call cap {self.max_calls} exceeded")
        if self._i < len(self._answers):
            ans = self._answers[self._i]
            self._i += 1
            return ans
        prompt = str(args[0]) if args else ""
        if self.quit_confirm_y and "quit" in prompt.lower():
            return "y"
        return "q"


def _patch(scripter, *modules):
    T.safe_input = scripter
    import builtins

    builtins.input = scripter

    def _prompt_menu_key(*_a, **_k):
        return scripter().strip().lower()

    T.prompt_menu_key = _prompt_menu_key
    MR.prompt_menu_key = _prompt_menu_key
    for mod in modules:
        if hasattr(mod, "_safe_input"):
            mod._safe_input = scripter
        if hasattr(mod, "safe_input"):
            mod.safe_input = scripter
        if hasattr(mod, "prompt_menu_key"):
            mod.prompt_menu_key = _prompt_menu_key
        for name in ("choose_save_path", "choose_style_file"):
            if hasattr(mod, name):
                setattr(mod, name, lambda *a, **k: None)
    import batplot.color_utils as CU
    import batplot.screen_color as SC

    CU.prompt_screen_color = lambda *a, **k: None
    SC.pick_screen_colors = lambda *a, **k: []
    SC.pick_screen_color = lambda *a, **k: None
    try:
        import batplot.utils as U

        U._ask_file_dialog = lambda *a, **k: None
    except Exception:
        pass


def _pulse(fig):
    fig.canvas.draw_idle()
    plt.pause(0.05)


# Per-key backout: open key, then enough ``q`` to return to main without quitting
# early. Instant toggles get no cushion (a cushion ``q`` would quit the session).
def _script_each_key(keys, *, menu_keys, backout=("q",), quit_tail=("q",)):
    """One ``q`` returns to main for most menus; a second ``q`` would quit."""
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


XY_TOP = [
    "c", "f", "l", "t", "g", "h", "sm", "a", "o", "r", "x", "y", "d",
    "cif", "z", "j", "v", "n", "p", "i", "e", "s", "b",
    "os", "ops", "opsg", "oe",
]
# Menu keys = alone-key walk needed ≥3 inputs (key + submenu q + main q).
# Instant toggles/dialogs (2 inputs) must NOT get a cushion q or the session quits.
XY_MENU = {
    "c", "f", "l", "t", "g", "h", "sm", "a", "o", "r", "x", "y", "d",
    "cif", "z", "v", "p",
}

EC_TOP = [
    "f", "l", "k", "t", "h", "d", "v", "g", "c", "r", "a", "x", "y", "ra",
    "n", "o", "p", "i", "e", "s", "b", "oe", "os", "ops", "opsg",
]
EC_MENU = {
    "f", "l", "k", "t", "h", "d", "c", "r", "a", "x", "y", "o", "p",
}

CPC_TOP = [
    "f", "l", "m", "c", "k", "d", "ry", "t", "h", "g", "v", "r", "x", "y",
    "ie", "o", "n", "p", "i", "e", "s", "b", "oe", "os", "ops", "opsg",
]
CPC_MENU = {
    "f", "l", "m", "c", "k", "d", "ry", "t", "h", "g", "r", "x", "y", "o", "p",
}

HISTO_TOP = [
    "c", "f", "a", "l", "t", "g", "w", "r", "x", "y",
    "e", "p", "i", "s", "b", "oe", "os", "ops", "opsg",
]
HISTO_MENU = {
    "c", "f", "a", "l", "t", "g", "w", "r", "x", "y", "p",
}

OP_TOP = [
    "oc", "el", "v", "t", "k", "l", "f", "g", "h", "ow", "ew", "r",
    "ox", "oy", "oz", "or", "c", "pk", "et", "ex", "ey", "er", "eg",
    "n", "p", "i", "e", "s", "b", "oe", "os", "ops", "opsg",
]
OP_MENU = {
    "oc", "el", "v", "t", "k", "l", "f", "g", "h", "ow", "ew",
    "ox", "oy", "oz", "or", "c", "pk", "et", "ex", "ey", "er", "eg", "p",
}

NESTED = {
    "xy": [
        ["c", "d:red", "a:blue", "w:green", "s:#0033aa", "q"],
        ["t", "list", "w1", "a2", "s3", "d4", "q"],
        ["l", "c", "q", "f", "q", "g", "l", "q"],
        ["f", "f", "q", "s", "q", "b", "q", "q"],
        ["h", "v", "s", "q", "q"],
        ["r", "x", "NewX", "y", "NewY", "q"],
    ],
    "ec": [
        ["k", "d:red", "a:blue", "w:green", "s:#0033aa", "q"],
        ["t", "list", "w1", "a2", "s3", "d4", "q"],
        ["l", "c", "q", "f", "q", "g", "l", "q"],
        ["a", "q"],
        ["o", "c", "q", "q"],
    ],
    "cpc": [
        ["k", "d:red", "a:blue", "q"],
        ["d", "c", "d", "b", "q"],
        ["ry", "t", "q"],
        ["t", "list", "q"],
        ["c", "ly", "q", "ry", "q", "q"],
    ],
    "histo": [
        ["c", "u", "q", "q"],
        ["t", "list", "q"],
        ["l", "f", "q", "g", "w", "q", "q"],
        ["a", "t", "q", "q"],
    ],
    "op": [
        ["k", "o", "d:red", "a:blue", "q", "e", "d:magenta", "q", "q"],
        ["t", "o", "list", "q", "e", "list", "q", "q"],
        ["oc", "plasma", "q"],
        ["el", "c", "q", "q"],
        ["v", "1", "2", "q"],
        ["eg", "t", "q", "q"],
    ],
}


def walk_xy(keys):
    scripter = ScriptedInput(keys)
    _patch(scripter, XI, XA, XP)
    x = np.linspace(20.0, 40.0, 101)
    y = np.sin(x)
    fig, ax = plt.subplots()
    ax.plot(x, y, label="c1")
    assert "Mac" in type(fig.canvas).__name__ or is_interactive_backend(), type(fig.canvas).__name__
    _pulse(fig)
    args = types.SimpleNamespace(
        stack=False, norm=False, ro=False, xrange=None, files=["a.xy"], autoscale=False
    )
    XI.interactive_menu(
        fig, ax, [y.copy()], [x.copy()], ["c1"], [y.copy()], [], 0.0, "Two theta",
        args, [x.copy()], [y.copy()], [0.0], False, False, False, False, False,
        canvas_mode=True,
    )
    try:
        plt.close(fig)
    except Exception:
        pass
    return scripter._calls


def walk_ec(keys):
    scripter = ScriptedInput(keys)
    _patch(scripter, EI, EA)
    fig, ax = plt.subplots()
    cap = np.linspace(0.0, 150.0, 40)
    volt = np.linspace(3.0, 4.2, 40)
    charge, = ax.plot(cap, volt, color="#ff0000", lw=2.0, label="cycle 1 charge")
    discharge, = ax.plot(cap[::-1], volt, color="#0000ff", lw=1.5, label="cycle 1 discharge")
    fig._ec_overview_enabled = True  # type: ignore[attr-defined]
    cycle_lines = {1: {"charge": charge, "discharge": discharge}}
    file_data = [{
        "filename": "a.mpt", "display_name": "a", "visible": True,
        "cycle_lines": cycle_lines, "all_cycles": [1],
    }]
    _pulse(fig)
    EI.electrochem_interactive_menu(
        fig, ax, cycle_lines=cycle_lines, file_data=file_data, canvas_mode=True
    )
    try:
        plt.close(fig)
    except Exception:
        pass
    return scripter._calls


def walk_cpc(keys):
    scripter = ScriptedInput(keys)
    _patch(scripter, CI)
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    cyc = np.arange(1, 6, dtype=float)
    sc_c = ax.scatter(cyc, np.linspace(150.0, 120.0, 5), c="red")
    sc_d = ax.scatter(cyc, np.linspace(148.0, 118.0, 5), c="blue")
    sc_e = ax2.scatter(cyc, np.linspace(95.0, 99.0, 5), c="green")
    fig._cpc_overview_enabled = True  # type: ignore[attr-defined]
    _pulse(fig)
    CI.cpc_interactive_menu(fig, ax, ax2, sc_c, sc_d, sc_e, canvas_mode=True)
    try:
        plt.close(fig)
    except Exception:
        pass
    return scripter._calls


def walk_histo(keys):
    scripter = ScriptedInput(list(keys), quit_confirm_y=True)
    _patch(scripter, HI, HA)
    fig, ax = plt.subplots()
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 2.5, 3.5])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1, column_name="Length", values=values,
        xmin=float(edges[0]), xmax=float(edges[-1]), bin_edges=edges,
    )
    state = HistoState(setup=setup, style=HistoStyle(), source_path="/tmp/histo.csv")
    _pulse(fig)

    def _loader(*_a, **_k):
        return TableData(
            path=state.source_path or "/tmp/histo.csv",
            headers=["Length"],
            rows=[[f"{v:g}"] for v in state.setup.values],
        )

    HI.histo_interactive_menu(fig, ax, state, table_loader=_loader)
    try:
        plt.close(fig)
    except Exception:
        pass
    return scripter._calls


def walk_op(keys):
    scripter = ScriptedInput(keys)
    _patch(scripter, OI, OA)
    fig, ax = plt.subplots()
    Z = np.random.default_rng(0).random((50, 80))
    im = ax.imshow(Z, aspect="auto", origin="lower", extent=(10.0, 40.0, 0.0, 20.0), cmap="viridis")
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
    _pulse(fig)
    OI.operando_ec_interactive_menu(fig, ax, im, cbar, ec_ax, canvas_mode=True)
    try:
        plt.close(fig)
    except Exception:
        pass
    return scripter._calls


def main() -> int:
    if sys.platform != "darwin":
        print(f"SKIP: macOS GUI walk requires darwin (got {sys.platform})")
        return 0
    be = matplotlib.get_backend()
    print(f"backend={be} interactive={is_interactive_backend()}")
    if be.lower() != "macosx":
        print(f"FAIL: expected MacOSX backend, got {be}")
        return 1
    failures = []

    steps = [
        ("xy-all-keys", lambda: walk_xy(_script_each_key(XY_TOP, menu_keys=XY_MENU))),
        ("ec-all-keys", lambda: walk_ec(_script_each_key(EC_TOP, menu_keys=EC_MENU))),
        ("cpc-all-keys", lambda: walk_cpc(_script_each_key(CPC_TOP, menu_keys=CPC_MENU))),
        ("histo-all-keys", lambda: walk_histo(_script_each_key(HISTO_TOP, menu_keys=HISTO_MENU, quit_tail=()))),
        ("op-all-keys", lambda: walk_op(_script_each_key(OP_TOP, menu_keys=OP_MENU))),
    ]
    for mode, scripts in NESTED.items():
        walker = {
            "xy": walk_xy, "ec": walk_ec, "cpc": walk_cpc,
            "histo": walk_histo, "op": walk_op,
        }[mode]
        for i, script in enumerate(scripts):
            steps.append((f"{mode}-nested-{i}", lambda w=walker, s=script: w(s)))

    # Also: every top-level key alone (true isolation, like pytest parametrize)
    for k in OP_TOP:
        steps.append((f"op-alone-{k}", lambda key=k: walk_op([key])))
    for k in XY_TOP:
        steps.append((f"xy-alone-{k}", lambda key=k: walk_xy([key])))
    for k in EC_TOP:
        steps.append((f"ec-alone-{k}", lambda key=k: walk_ec([key])))
    for k in CPC_TOP:
        steps.append((f"cpc-alone-{k}", lambda key=k: walk_cpc([key])))
    for k in HISTO_TOP:
        steps.append((f"histo-alone-{k}", lambda key=k: walk_histo([key])))

    for name, fn in steps:
        try:
            calls = fn()
            print(f"  OK  {name}  (input calls={calls})")
        except Exception as e:
            failures.append((name, e))
            print(f"  FAIL {name}: {e}")
            traceback.print_exc()
        finally:
            plt.close("all")

    if failures:
        print(f"\nFAILED {len(failures)}/{len(steps)}")
        for name, e in failures:
            print(f"  - {name}: {e}")
        return 1
    print(f"\nALL {len(steps)} MacOSX GUI walks passed (backend={matplotlib.get_backend()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

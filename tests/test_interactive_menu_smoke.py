"""Keystroke-driven smoke tests for the interactive menu dispatch loops.

These act as a behavioural safety net for the large
``electrochem_interactive_menu`` / ``operando_ec_interactive_menu`` dispatch
loops, which otherwise have no behavioural coverage. They feed a scripted
sequence of keys through the menu's input function and assert the loop runs
the selected branches and terminates cleanly (no exception, no hang).

Design notes
------------
* ``canvas_mode=True`` makes the top-level ``q`` quit immediately (no y/n
  confirmation), so every script terminates as soon as a ``q`` reaches the
  top-level prompt.
* ``ScriptedInput`` returns the scripted answers in order, then returns ``q``
  forever. ``q`` is the universal "quit / go back" key, so any sub-menu the
  script leaves open unwinds to the top level and the menu exits. A hard call
  cap turns a runaway loop into a test failure instead of a hang.
* The menu input helper is the module-level ``_safe_input`` name; helper
  sub-menus receive it via ``safe_input=_safe_input`` at call time, so patching
  the module attribute covers them too.
"""

import types

import pytest
import numpy as np
import matplotlib.pyplot as plt

from batplot.plot_modes.cpc import interactive as CI
from batplot.plot_modes.electrochem import actions as EA
from batplot.plot_modes.electrochem import interactive as EI
from batplot.plot_modes.operando import interactive as OI
from batplot.plot_modes.xy import actions as XA
from batplot.plot_modes.xy import interactive as XI


class ScriptedInput:
    """Callable stand-in for ``safe_input`` that replays a scripted answer list.

    After the script is exhausted it returns ``"q"`` (quit/back) so the menu
    always unwinds and terminates. ``max_calls`` guards against infinite loops:
    exceeding it raises ``AssertionError`` (a test failure) rather than hanging.
    """

    def __init__(self, answers, max_calls=500):
        self._answers = list(answers)
        self._i = 0
        self._calls = 0
        self.max_calls = max_calls

    def __call__(self, *_args, **_kwargs):
        self._calls += 1
        assert self._calls <= self.max_calls, (
            "interactive menu asked for input more than "
            f"{self.max_calls} times - possible infinite loop"
        )
        if self._i < len(self._answers):
            ans = self._answers[self._i]
            self._i += 1
            return ans
        return "q"

    @property
    def exhausted(self):
        return self._i >= len(self._answers)


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


def _build_operando_figure():
    fig, ax = plt.subplots()
    Z = np.random.default_rng(0).random((50, 80))
    im = ax.imshow(Z, aspect="auto", origin="lower", extent=[10.0, 40.0, 0.0, 20.0],
                   cmap="viridis")
    cbar = fig.colorbar(im, ax=ax)
    ec_ax = fig.add_axes((0.78, 0.1, 0.18, 0.8))
    ec_ax.plot(np.linspace(3.0, 4.2, 30), np.linspace(0.0, 20.0, 30))
    ec_ax.set_xlabel("Voltage (V)")
    ec_ax.set_ylabel("Time (h)")
    ec_ax.yaxis.tick_right()
    ec_ax.yaxis.set_label_position("right")
    return fig, ax, im, cbar, ec_ax


def drive_ec(monkeypatch, keys, max_calls=500):
    """Run the EC menu with the scripted ``keys`` and return the input scripter."""
    scripter = ScriptedInput(keys, max_calls=max_calls)
    monkeypatch.setattr(EI, "_safe_input", scripter)
    monkeypatch.setattr(EA, "choose_save_path", lambda *_a, **_k: None)
    fig, ax, cycle_lines = _build_ec_figure()
    EI.electrochem_interactive_menu(fig, ax, cycle_lines=cycle_lines, canvas_mode=True)
    return scripter


def drive_op(monkeypatch, keys, max_calls=500):
    """Run the operando menu with the scripted ``keys`` and return the scripter."""
    scripter = ScriptedInput(keys, max_calls=max_calls)
    monkeypatch.setattr(OI, "_safe_input", scripter)
    monkeypatch.setattr(OI, "choose_save_path", lambda *_a, **_k: None)
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    OI.operando_ec_interactive_menu(fig, ax, im, cbar, ec_ax, canvas_mode=True)
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
    return fig, ax, ax2, sc_charge, sc_discharge, sc_eff


def drive_cpc(monkeypatch, keys, max_calls=500):
    scripter = ScriptedInput(keys, max_calls=max_calls)
    monkeypatch.setattr(CI, "_safe_input", scripter)
    monkeypatch.setattr(CI, "choose_save_path", lambda *_a, **_k: None)
    fig, ax, ax2, sc_c, sc_d, sc_e = _build_cpc_figure()
    CI.cpc_interactive_menu(fig, ax, ax2, sc_c, sc_d, sc_e, canvas_mode=True)
    return scripter


def _build_xy_figure():
    x = np.linspace(20.0, 40.0, 101)
    y = np.sin(x)
    fig, ax = plt.subplots()
    ax.plot(x, y, label="c1")
    ax.set_xlabel("Two theta")
    ax.set_ylabel("Intensity")
    return fig, ax, [y], [x], ["c1"], [y]


def drive_xy(monkeypatch, keys, max_calls=500):
    scripter = ScriptedInput(keys, max_calls=max_calls)
    monkeypatch.setattr(XI, "_safe_input", scripter)
    monkeypatch.setattr(XA, "choose_save_path", lambda *_a, **_k: None)
    fig, ax, y_list, x_list, labels, orig_y = _build_xy_figure()
    args = types.SimpleNamespace(stack=False, norm=False, ro=False, xrange=None)
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
        x_list,
        orig_y,
        [0.0],
        False,
        False,
        False,
        False,
        False,
        canvas_mode=True,
    )
    return scripter


# --- Baseline: the loops are reachable and quit cleanly --------------------

def test_ec_menu_enters_and_quits(monkeypatch):
    drive_ec(monkeypatch, ["q"])


def test_op_menu_enters_and_quits(monkeypatch):
    drive_op(monkeypatch, ["q"])


def test_ec_menu_empty_input_then_quit(monkeypatch):
    drive_ec(monkeypatch, ["", "q"])


def test_op_menu_empty_input_then_quit(monkeypatch):
    drive_op(monkeypatch, ["", "q"])


def test_ec_menu_unknown_key_then_quit(monkeypatch):
    drive_ec(monkeypatch, ["zzz", "q"])


def test_op_menu_unknown_key_then_quit(monkeypatch):
    drive_op(monkeypatch, ["zzz", "q"])


# --- Enter each large EC branch and back out (regression net for extraction) -
# The scripter auto-returns "q" once the explicit script is exhausted, so each
# branch is entered, its sub-menu (if any) receives "q" to go back, and the top
# level then receives "q" to quit. We assert only that no exception escapes.


@pytest.mark.parametrize("branch_key", [
    "n", "b", "p", "i", "s", "d", "h", "l", "k", "r", "ra", "t", "c",
    "a", "f", "x", "y", "g", "sm", "2d",
])
def test_ec_menu_enter_branch_and_back_out(monkeypatch, branch_key):
    drive_ec(monkeypatch, [branch_key])


@pytest.mark.parametrize("branch_key", [
    "n", "b", "p", "i", "s", "pk", "h", "r", "f", "l", "t", "c",
    "ox", "oy", "oz", "ew", "oc", "or", "er", "eg", "el",
    "et", "ey", "ex", "g",
])
def test_op_menu_enter_branch_and_back_out(monkeypatch, branch_key):
    drive_op(monkeypatch, [branch_key])


@pytest.mark.parametrize("branch_key", [
    "n", "b", "p", "i", "s", "e", "d", "h", "l", "k", "r", "t", "c",
    "v", "ry", "f", "m", "x", "y", "g", "ie", "oe", "os", "ops", "opsg",
])
def test_cpc_menu_enter_branch_and_back_out(monkeypatch, branch_key):
    drive_cpc(monkeypatch, [branch_key])


@pytest.mark.parametrize("branch_key", ["b", "p", "i", "s"])
def test_xy_menu_pisb_commands(monkeypatch, branch_key):
    drive_xy(monkeypatch, [branch_key])

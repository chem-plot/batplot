"""Menu must appear fully before the Press a key prompt."""

from __future__ import annotations

import io
import sys

import matplotlib
import matplotlib.pyplot as plt
import pytest

matplotlib.use("Agg")

from batplot.plot_modes.batch_session.load import EcPanel
from batplot.plot_modes.batch_session.menu_ec import _print_ec_batch_menu
from batplot.plot_modes.common.menu_rendering import print_menu_columns, prompt_menu_key


def test_print_menu_columns_flushes_before_prompt(monkeypatch):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    panel = EcPanel(path="a.pkl", fig=fig, ax=ax, cycle_lines={}, file_data=None)

    buf = io.StringIO()
    monkeypatch.setattr(sys, "stdout", buf)
    _print_ec_batch_menu([panel])
    menu_pos = buf.tell()

    inputs = iter(["q"])

    def fake_input(prompt: str = "") -> str:
        buf.write(prompt)
        return next(inputs)

    monkeypatch.setattr("builtins.input", fake_input)
    from batplot.plot_modes.common import terminal as T

    monkeypatch.setattr(T.sys, "platform", "linux")
    prompt_menu_key()
    full = buf.getvalue()
    assert "Batch EC Menu" in full
    assert full.index("Batch EC Menu") < full.index("Press a key:")
    assert menu_pos > 0
    plt.close(fig)


def test_print_menu_columns_helper_flushes():
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        print_menu_columns(
            title="Test Menu",
            columns=[("Styles", ["f: font"]), ("Options", ["q: quit"])],
        )
        assert "Test Menu" in buf.getvalue()
    finally:
        sys.stdout = old

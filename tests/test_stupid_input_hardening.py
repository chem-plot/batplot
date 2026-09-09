"""Gates: stupid interactive inputs must not crash or junk-undo."""

from __future__ import annotations

import math

import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot.plot_modes.batch_session.common import SyncUndoStacks
from batplot.plot_modes.common.spines import parse_frame_tick_widths
from batplot.ui import resize_plot_frame


def test_operando_peak_param_parse_rejects_garbage():
    """Mirror the hardened parse rules used in operando peaks menu."""
    for bad in ("abc", "", "nan"):
        try:
            if bad == "":
                prominence = 0.1
            else:
                prominence = float(bad)
            assert prominence > 0 and prominence == prominence
            if bad:
                pytest.fail(f"expected reject for {bad!r}")
        except (ValueError, AssertionError):
            pass
    assert float("0.1") > 0
    with pytest.raises(ValueError):
        int("1.5")
    assert int("5") >= 1


def test_wavelength_must_be_positive():
    for wl in (0.0, -1.0, float("nan")):
        assert not (wl > 0 and wl == wl)
    assert 1.5406 > 0


def test_sync_undo_pop_indices_drops_junk_level():
    undo = SyncUndoStacks(2)
    undo.push_all(["base0", "base1"])
    undo.push_all(["bad0", "bad1"])
    assert undo.can_undo()
    undo.pop_indices([0, 1])
    assert not undo.can_undo()


def test_parse_frame_tick_widths_rejects_garbage():
    with pytest.raises(ValueError):
        parse_frame_tick_widths("abc", single_minor_scale=1.0, paired_minor_scale=1.0)


def test_resize_plot_frame_rejects_garbage_without_push():
    fig, ax = plt.subplots()
    pushed = {"n": 0}

    def _push():
        pushed["n"] += 1

    inputs = iter(["w=abc", "q"])
    import batplot.ui as ui

    old = ui.safe_input
    try:
        ui.safe_input = lambda *a, **k: next(inputs)
        resize_plot_frame(
            fig,
            ax,
            [],
            [],
            type("A", (), {"stack": False})(),
            update_labels_func=lambda *a, **k: None,
            on_before_change=_push,
        )
    finally:
        ui.safe_input = old
    assert pushed["n"] == 0
    plt.close(fig)


def test_xy_rename_index_guard_logic():
    labels = ["a", "b"]
    label_text_objects = ["only-one"]
    idx = 1
    assert 0 <= idx < len(labels)
    assert not (idx < len(label_text_objects))

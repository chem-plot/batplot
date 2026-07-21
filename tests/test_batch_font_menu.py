"""Regression tests for batch-session font menu (f → family/size/bold/highlight)."""

from __future__ import annotations

import matplotlib
import matplotlib.pyplot as plt
import pytest

matplotlib.use("Agg")

from batplot.plot_modes.common.batch_font import run_batch_font_menu
from batplot.plot_modes.common.font_extras import get_fig_font_weight, get_fig_text_highlight
from batplot.plot_modes.batch_session.common import SyncUndoStacks


@pytest.fixture
def xy_panels(tmp_path):
    from batplot.plot_modes.batch_session.load import load_batch_panels

    paths = []
    for i in range(2):
        p = tmp_path / f"xy{i}.pkl"
        _write_min_xy_pkl(p, label=f"curve{i}")
        paths.append(str(p))
    result = load_batch_panels(paths)
    assert result.kind == "xy"
    yield result.panels
    for panel in result.panels:
        plt.close(panel.fig)


def _write_min_xy_pkl(path, *, label: str) -> None:
    import pickle
    import numpy as np

    fig, ax = plt.subplots()
    x = np.linspace(0, 10, 20)
    ax.plot(x, np.sin(x), label=label)
    ax.set_xlabel("2theta")
    ax.set_ylabel("Intensity")
    sess = {
        "kind": "xy",
        "version": 3,
        "x_data": [x],
        "y_data": [np.sin(x)],
        "orig_y": [np.sin(x)],
        "offsets": [0.0],
        "labels": [label],
        "args_subset": {"stack": False, "autoscale": True, "norm": False, "files": []},
        "wasd_state": {
            "bottom": {"ticks": True, "labels": True, "minor": False, "spine": True, "title": True},
            "top": {"ticks": False, "labels": False, "minor": False, "spine": False, "title": False},
            "left": {"ticks": True, "labels": True, "minor": False, "spine": True, "title": True},
            "right": {"ticks": False, "labels": False, "minor": False, "spine": False, "title": False},
        },
        "figure": {"size": [8.0, 6.0]},
        "axis": {"xlabel": "2theta", "ylabel": "Intensity", "xlim": (0, 10), "ylim": (-1, 1)},
    }
    with open(path, "wb") as fh:
        pickle.dump(sess, fh)
    plt.close(fig)


def test_batch_xy_font_weight_and_highlight(xy_panels):
    from batplot.plot_modes.batch_session.menu_xy import _capture_panel, _xy_batch_font_artists

    panels = xy_panels
    undo = SyncUndoStacks(len(panels))
    undo.push_all([_capture_panel(p) for p in panels])
    inputs = iter(["b", "bold", "q", "h", "t", "q", "q"])

    run_batch_font_menu(
        panels=panels,
        undo=undo,
        capture_panel=_capture_panel,
        draw_panels=lambda: None,
        collect_artists=_xy_batch_font_artists,
        safe_input=lambda _p: next(inputs),
        colorize_menu=lambda t: t,
        colorize_prompt=lambda t: t,
    )

    for panel in panels:
        assert get_fig_font_weight(panel.fig) == "bold"
        assert get_fig_text_highlight(panel.fig) is True

    snap = _capture_panel(panels[0])
    font = snap.get("font") or {}
    assert font.get("weight") == "bold"
    assert font.get("highlight") is True


def test_batch_xy_font_menu_quit_without_edit(xy_panels):
    from batplot.plot_modes.batch_session.menu_xy import _capture_panel, _xy_batch_font_artists

    undo = SyncUndoStacks(len(xy_panels))
    undo.push_all([_capture_panel(p) for p in xy_panels])
    run_batch_font_menu(
        panels=xy_panels,
        undo=undo,
        capture_panel=_capture_panel,
        draw_panels=lambda: None,
        collect_artists=_xy_batch_font_artists,
        safe_input=lambda _p: "q",
        colorize_menu=lambda t: t,
        colorize_prompt=lambda t: t,
    )
    assert undo.can_undo() is False

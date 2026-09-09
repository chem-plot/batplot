"""Geom size prompt highlighting and soft quit (q/qq)."""

from __future__ import annotations

import matplotlib.pyplot as plt

from batplot.plot_modes.common.size_spec import (
    current_canvas_status,
    current_plot_frame_status,
    is_size_quit_token,
    parse_size_spec,
    plot_frame_size_prompt,
)
from batplot.ui import resize_plot_frame


def test_is_size_quit_token_accepts_q_and_qq():
    assert is_size_quit_token("")
    assert is_size_quit_token("q")
    assert is_size_quit_token("Q")
    assert is_size_quit_token("qq")
    assert is_size_quit_token("qqq")
    assert not is_size_quit_token("6 4")
    assert not is_size_quit_token("qp")


def test_parse_size_spec_qq_silent(capsys):
    assert parse_size_spec("qq", 6.0, 4.0) is None
    assert "Invalid" not in capsys.readouterr().out


def test_size_status_highlights_when_ansi_forced(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    monkeypatch.setattr(
        "batplot.plot_modes.common.menu_rendering.sys.stdout.isatty",
        lambda: True,
    )
    status = current_canvas_status(10.0, 6.0)
    frame = current_plot_frame_status(7.5, 4.38)
    prompt = plot_frame_size_prompt()
    assert "\033[96m" in status
    assert "canvas" in status
    assert "\033[96m7.50\033[0m" in frame or "7.50" in frame
    assert "plot frame" in prompt
    assert "6 4" in prompt


def test_size_status_plain_under_no_color(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    status = current_canvas_status(10.0, 6.0)
    assert "\033[" not in status
    assert status == "Current canvas: 10.00 x 6.00 in"


def test_resize_plot_frame_qq_exits_without_push():
    fig, ax = plt.subplots()
    pushed = {"n": 0}

    def _push():
        pushed["n"] += 1

    inputs = iter(["qq"])
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

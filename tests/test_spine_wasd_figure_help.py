"""Help layout for shared WASD side figure (``t`` and color ``c``/``k`` menus)."""

from __future__ import annotations

import re

from batplot.plot_modes.common.color_menu_help import print_spine_tick_keys_note
from batplot.plot_modes.common.spines import (
    print_wasd_color_side_figure,
    print_wasd_side_figure,
)


def _strip_ansi(text: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", text)


def test_wasd_side_figure_puts_toggle_legend_on_the_right(capsys, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    print_wasd_side_figure(use_ansi=False)
    lines = [ln.rstrip() for ln in _strip_ansi(capsys.readouterr().out).splitlines() if ln.strip()]

    assert any("Plot sides (WASD):" in ln and "What to toggle:" in ln for ln in lines)
    assert any("w = top" in ln and "1 = spine line" in ln for ln in lines)
    assert any("2 = major ticks" in ln for ln in lines)
    assert any("3 = minor ticks" in ln for ln in lines)
    assert any("a=left" in ln and "d=right" in ln and "4 = labels" in ln for ln in lines)
    assert any("5 = axis title" in ln for ln in lines)
    assert any("s = bottom" in ln for ln in lines)
    # Legend must not appear as a separate under-figure one-liner.
    assert not any(ln.lstrip().startswith("What to toggle  :") for ln in lines)


def test_wasd_color_side_figure_shows_rectangle_without_toggle_digits(capsys, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    print_wasd_color_side_figure(use_ansi=False)
    lines = [ln.rstrip() for ln in _strip_ansi(capsys.readouterr().out).splitlines() if ln.strip()]

    assert any("Spine color sides (WASD):" in ln and "Type side:color:" in ln for ln in lines)
    assert any("w = top" in ln and "w:red" in ln for ln in lines)
    assert any("a=left" in ln and "d=right" in ln for ln in lines)
    assert any("s = bottom" in ln for ln in lines)
    assert any("a:#4561F7" in ln for ln in lines)
    assert any("d:green" in ln for ln in lines)
    # Color figure must not reuse the t-menu 1–5 toggle legend.
    assert not any("What to toggle:" in ln for ln in lines)
    assert not any("1 = spine line" in ln for ln in lines)


def test_print_spine_tick_keys_note_uses_color_rectangle(capsys, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    print_spine_tick_keys_note()
    out = _strip_ansi(capsys.readouterr().out)
    assert "Spine color sides (WASD):" in out
    assert "a=left" in out and "d=right" in out
    assert "Spine keys:" not in out

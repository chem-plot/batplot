"""Menu rendering presentation helpers (print-only; no PISB/dispatch)."""

from __future__ import annotations

import os

from batplot.plot_modes.common import menu_rendering as MR


def test_normalize_menu_heading_strips_parens():
    assert MR.normalize_menu_heading("(Styles)") == "Styles"
    assert MR.normalize_menu_heading("Styles") == "Styles"
    assert MR.normalize_menu_heading("(Side Panel)") == "Side Panel"


def test_no_color_disables_ansi(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert MR.ansi_menu_enabled() is False
    assert MR.colorize_menu_item("t: spines/ticks") == "t: spines/ticks"
    assert "\033[" not in MR.colorize_menu_item("f: font")


def test_ansi_on_tty_without_no_color(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")

    class _TTY:
        def isatty(self):
            return True

    monkeypatch.setattr(MR.sys, "stdout", _TTY())
    assert MR.ansi_menu_enabled() is True
    out = MR.colorize_menu_item("t: spines/ticks")
    assert out.startswith("\033[96m")
    assert "spines/ticks" in out


def test_format_batch_key_unavailable_tone():
    msg = MR.format_batch_key_unavailable("sm", "smoothing is a per-dataset data transform")
    assert "not available in batch" in msg
    assert "single-session --i" in msg
    assert "sm" in msg


def test_print_menu_columns_strips_operando_padding(capsys, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    MR.print_menu_columns(
        title="T",
        columns=[("(Styles)", [" v: toggle", " t: spines/ticks"])],
        min_widths=(12,),
    )
    out = capsys.readouterr().out
    assert "Styles" in out
    assert "(Styles)" not in out
    assert "v: toggle" in out
    assert "t: spines/ticks" in out
    # Keys extracted from the same cleaning path have no leading spaces.
    keys = MR.command_keys_from_columns([[" v: toggle", " t: spines/ticks"]])
    assert keys == {"v", "t"}

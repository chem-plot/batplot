"""Illustrated curve-look help for line menus (display-only)."""

from __future__ import annotations

from batplot.plot_modes.common.curve_look_help import (
    print_curve_line_chrome_rows,
    print_curve_look_legend,
    print_density_linestyle_legend,
    strip_ansi_for_tests,
)
from batplot.plot_modes.xy.line_style import run_line_style_menu


def test_curve_look_legend_lists_all_five_modes(capsys, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    print_curve_look_legend(use_ansi=False, ascii_safe=True, scope="selected curves")
    out = strip_ansi_for_tests(capsys.readouterr().out)
    assert "Curve look (selected curves):" in out
    for token in (
        "l ",
        "ld",
        "d ",
        "da",
        "dd",
        "line only",
        "line + dots",
        "dots only",
        "dashed",
        "dash-dot",
        "----------",
        "o---o---o---o",
    ):
        assert token in out, f"missing {token!r}"


def test_curve_look_chrome_rows_separate(capsys, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    print_curve_look_legend(use_ansi=False, ascii_safe=True)
    print_curve_line_chrome_rows(
        ["c: change curve line widths", "q: return"],
        colorize=lambda s, **_k: s,
        heading="Widths / grid",
    )
    out = strip_ansi_for_tests(capsys.readouterr().out)
    assert "Widths / grid:" in out
    assert "c: change curve line widths" in out
    assert "q: return" in out


def test_density_linestyle_legend_sdt(capsys, monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    print_density_linestyle_legend(use_ansi=False, ascii_safe=True)
    out = strip_ansi_for_tests(capsys.readouterr().out)
    assert "solid" in out and "dashed" in out and "dotted" in out
    assert "s " in out or "\ns  " in out or "  s  " in out


def test_xy_line_menu_shows_curve_look_and_still_applies_da(capsys, monkeypatch):
    """Help is illustrated; da still tags dash_pattern (p/i/s/b path unchanged)."""
    import matplotlib.pyplot as plt

    monkeypatch.setenv("NO_COLOR", "1")
    fig, ax = plt.subplots()
    ln, = ax.plot([0, 1], [0, 1])
    lines = [ln]
    pushes = []

    def _feed(*vals):
        it = iter(vals)

        def _in(*_a, **_k):
            try:
                return next(it)
            except StopIteration:
                return "q"

        return _in

    run_line_style_menu(
        ax=ax,
        fig=fig,
        lines_by_curve=lines,
        line_getter=lambda i: lines[i],
        line_count=lambda: len(lines),
        push_state=lambda note: pushes.append(note),
        safe_input=_feed("da", "all", "", "q"),
        colorize_menu=lambda s, **_k: s,
        colorize_prompt=lambda s: s,
    )
    out = strip_ansi_for_tests(capsys.readouterr().out)
    assert "Curve look" in out
    assert "Widths / grid:" in out or "c: change curve line widths" in out
    assert pushes == ["dashed-line"]
    assert getattr(ln, "_bp_dash_pattern") == (0.0, (6.0, 3.0))
    plt.close(fig)

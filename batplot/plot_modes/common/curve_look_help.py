"""Illustrated curve-look help for interactive line menus (display-only).

Prints the five shared presets (``l`` / ``ld`` / ``d`` / ``da`` / ``dd``) with
ASCII or UTF-8 glyphs so the submenu matches what the plot will look like.
Does not change dispatch, dash persistence, or p/i/s/b.
"""

from __future__ import annotations

import re
from typing import Any, Sequence

from .menu_rendering import ansi_menu_enabled, menu_block_begin, print_menu_key_rows
from .terminal import stream_needs_console_safe

# Shared choose-prompt token used by XY / EC / operando curve menus.
CURVE_LOOK_CHOICES = "l/ld/d/da/dd"


def _curve_look_glyphs(*, ascii_safe: bool) -> list[tuple[str, str, str]]:
    """Return ``(key, glyph, short description)`` for the five curve looks."""
    if ascii_safe:
        return [
            ("l", "----------", "line only"),
            ("ld", "o---o---o---o", "line + dots"),
            ("d", "o  o  o  o  o", "dots only"),
            ("da", "----  ----  ----", "dashed (length gap)"),
            ("dd", "---- . ---- . ----", "dash-dot (4 numbers)"),
        ]
    return [
        ("l", "────────────", "line only"),
        ("ld", "●───●───●───●", "line + dots"),
        ("d", "●  ●  ●  ●  ●", "dots only"),
        ("da", "────  ────  ────", "dashed (length gap)"),
        ("dd", "──── · ──── · ────", "dash-dot (4 numbers)"),
    ]


def print_curve_look_legend(
    *,
    use_ansi: bool | None = None,
    ascii_safe: bool | None = None,
    scope: str | None = None,
    indent: str = "  ",
) -> None:
    """Print the illustrated ``l/ld/d/da/dd`` block for curve line menus.

    ``scope`` is an optional trailing note (e.g. ``\"selected curves\"`` /
    ``\"all curves\"`` / ``\"EC curve\"``) shown on the section header.
    """
    if use_ansi is None:
        use_ansi = ansi_menu_enabled()
    if ascii_safe is None:
        ascii_safe = stream_needs_console_safe()
    cyan = "\033[96m" if use_ansi else ""
    reset = "\033[0m" if use_ansi else ""

    header = "Curve look"
    if scope:
        header = f"{header} ({scope})"
    menu_block_begin()
    if use_ansi:
        print(f"{indent}\033[1m{header}:\033[0m")
    else:
        print(f"{indent}{header}:")

    rows = _curve_look_glyphs(ascii_safe=bool(ascii_safe))
    key_w = max(len(k) for k, _, _ in rows)
    glyph_w = max(len(g) for _, g, _ in rows)
    for key, glyph, desc in rows:
        key_part = f"{cyan}{key:<{key_w}}{reset}" if use_ansi else f"{key:<{key_w}}"
        print(f"{indent}  {key_part}  {glyph:<{glyph_w}}  {desc}")


def print_curve_line_chrome_rows(
    rows: Sequence[str],
    *,
    colorize: Any = None,
    heading: str = "Also",
    indent: str = "  ",
) -> None:
    """Print chrome / width / quit keys under the curve-look legend."""
    menu_block_begin()
    use_ansi = ansi_menu_enabled()
    if use_ansi:
        print(f"{indent}\033[1m{heading}:\033[0m")
    else:
        print(f"{indent}{heading}:")
    print_menu_key_rows(rows, indent=indent, colorize=colorize)


def print_density_linestyle_legend(
    *,
    use_ansi: bool | None = None,
    ascii_safe: bool | None = None,
    indent: str = "  ",
) -> None:
    """Illustrated ``s/d/t`` named linestyles for histo density curve."""
    if use_ansi is None:
        use_ansi = ansi_menu_enabled()
    if ascii_safe is None:
        ascii_safe = stream_needs_console_safe()
    cyan = "\033[96m" if use_ansi else ""
    reset = "\033[0m" if use_ansi else ""

    menu_block_begin()
    if use_ansi:
        print(f"{indent}\033[1mLinestyle:\033[0m")
    else:
        print(f"{indent}Linestyle:")
    if ascii_safe:
        rows = [
            ("s", "----------", "solid"),
            ("d", "----  ----", "dashed"),
            ("t", "..........", "dotted"),
        ]
    else:
        rows = [
            ("s", "────────────", "solid"),
            ("d", "────  ────", "dashed"),
            ("t", "············", "dotted"),
        ]
    glyph_w = max(len(g) for _, g, _ in rows)
    for key, glyph, desc in rows:
        key_part = f"{cyan}{key}{reset}" if use_ansi else key
        print(f"{indent}  {key_part}  {glyph:<{glyph_w}}  {desc}")


def strip_ansi_for_tests(text: str) -> str:
    """Strip CSI sequences (tests / width checks)."""
    return re.sub(r"\033\[[0-9;]*m", "", text)


__all__ = [
    "CURVE_LOOK_CHOICES",
    "print_curve_look_legend",
    "print_curve_line_chrome_rows",
    "print_density_linestyle_legend",
    "strip_ansi_for_tests",
]

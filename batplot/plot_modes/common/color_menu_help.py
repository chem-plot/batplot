"""Shared color-menu help layout (EC classic template).

Reference layout (matches EC ``c``):
  [optional status line]
  How to set color:
    1) <method title>:
         e.g. <cyan examples>
    2) ...
  Recommended palettes for scientific publications:
    1: name - desc
        <preview bar>
  Palette digits: 1=...  2=...   (optional)
  Saved colors (use with colon form as number):
    1: <swatch> #hex
    u: edit saved colors
  v: show current colors
  e: pick color from screen
  q: back
  Selection:

Modes keep their own method rows / palettes / extras but share wording,
cyan examples, section order, and the ``Selection:`` prompt convention.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Optional, Sequence

from ...color_utils import format_color_listing, get_user_color_list, palette_preview
from .menu_rendering import ansi_menu_enabled


def _c() -> tuple[str, str]:
    if ansi_menu_enabled():
        return "\033[96m", "\033[0m"
    return "", ""


def cyan_sample(sample: str) -> str:
    """Highlight one typed example (cyan when ANSI menus are enabled)."""
    c, r = _c()
    return f"{c}{sample}{r}"


def join_cyan_samples(*samples: str, sep: str = "   |   ") -> str:
    """Join examples with EC-style `` | `` separators by default."""
    return sep.join(cyan_sample(s) for s in samples)


def join_cyan_samples_spaced(*samples: str) -> str:
    """Join examples with spaces (colon-form rows)."""
    return " ".join(cyan_sample(s) for s in samples)


def _colorize(text: str, colorize_menu: Optional[Callable[[str], str]] = None) -> str:
    if colorize_menu is not None:
        return colorize_menu(text)
    return text


def print_how_to_set_color_methods(
    methods: Sequence[tuple[str, str]],
    *,
    leading_blank: bool = True,
) -> None:
    """Print EC-style numbered ``How to set color:`` methods.

    ``methods`` is ``(title, examples_line)`` where ``examples_line`` is already
    formatted (use :func:`join_cyan_samples` / :func:`join_cyan_samples_spaced`).
    Titles should not include the leading number.
    """
    if leading_blank:
        print()
    print("How to set color:")
    for idx, (title, examples) in enumerate(methods, 1):
        print(f"  {idx}) {title}:")
        print(f"       e.g. {examples}")


def print_recommended_palettes(
    palette_options: Sequence[str],
    *,
    descriptions: Optional[dict[str, str]] = None,
    colorize_menu: Optional[Callable[[str], str]] = None,
    heading: str = "Recommended palettes for scientific publications:",
    current: Optional[str] = None,
    show_digits_line: bool = True,
    max_digits: Optional[int] = None,
) -> None:
    """Print EC-style numbered palette list with preview bars."""
    if current:
        print(f"Current palette: {current}")
    print(heading)
    desc_map = descriptions or {}
    for idx, name in enumerate(palette_options, 1):
        desc = desc_map.get(name, "")
        line = f"{idx}: {name}" + (f" - {desc}" if desc else "")
        print("  " + _colorize(line, colorize_menu))
        bar = palette_preview(name)
        if bar:
            print(f"      {bar}")
    if show_digits_line and palette_options:
        n = len(palette_options) if max_digits is None else min(max_digits, len(palette_options))
        parts = [f"{i}={palette_options[i - 1]}" for i in range(1, n + 1)]
        print("  " + _colorize("Palette digits: " + "  ".join(parts), colorize_menu))


def print_saved_colors_block(
    fig: Any,
    *,
    colorize_menu: Optional[Callable[[str], str]] = None,
    heading: str = "Saved colors (use with colon form as number):",
    always_print_heading: bool = False,
) -> bool:
    """Print saved-user-color list (EC wording). Returns True when any were shown."""
    user_colors = get_user_color_list(fig)
    if not user_colors:
        if always_print_heading:
            print()
            print(heading)
        return False
    print()
    print(heading)
    for idx, col in enumerate(user_colors, 1):
        line = f"{idx}: {format_color_listing(col)}"
        print("  " + _colorize(line, colorize_menu))
    return True


def print_color_action_keys(
    *,
    colorize_menu: Optional[Callable[[str], str]] = None,
    include_v: bool = True,
    include_u: bool = True,
    include_e: bool = True,
    extras: Optional[Iterable[tuple[str, str]]] = None,
) -> None:
    """Print EC-style action keys as separate indented lines."""
    if include_u:
        print("  " + _colorize("u: edit saved colors", colorize_menu))
    if include_v:
        print("  " + _colorize("v: show current colors", colorize_menu))
    if include_e:
        print("  " + _colorize("e: pick color from screen", colorize_menu))
    if extras:
        for key, desc in extras:
            print("  " + _colorize(f"{key}: {desc}", colorize_menu))
    print("  " + _colorize("q: back", colorize_menu))


def print_spine_tick_keys_note(
    *,
    colorize_menu: Optional[Callable[[str], str]] = None,
) -> None:
    """WASD rectangle for spine colors (``c`` / ``k``) — same box as ``t``.

    ``colorize_menu`` is accepted for call-site compatibility; the shared figure
    applies its own cyan keys (ANSI when menus allow it).
    """
    del colorize_menu  # figure owns cyan highlighting
    from .spines import print_wasd_color_side_figure

    print_wasd_color_side_figure()


def print_colors_header(title: str = "Colors>") -> None:
    if ansi_menu_enabled():
        print(f"\033[1m{title}\033[0m")
    else:
        print(title)


def print_palettes_block(
    palette_options: Sequence[str],
    *,
    descriptions: Optional[dict[str, str]] = None,
    heading: str = "Recommended palettes for scientific publications:",
    current: Optional[str] = None,
) -> None:
    print_recommended_palettes(
        palette_options,
        descriptions=descriptions,
        heading=heading,
        current=current,
        show_digits_line=False,
    )


def print_spine_tick_keys_line() -> None:
    print_spine_tick_keys_note()


def print_how_to_set_color(rows: Sequence[tuple[str, str]]) -> None:
    """Legacy target:example rows → numbered EC-style methods."""
    methods = [(str(label), examples) for label, examples in rows]
    print_how_to_set_color_methods(methods)


def print_colors_other_line(
    *,
    extras: Optional[Iterable[tuple[str, str]]] = None,
    include_v: bool = True,
    include_u: bool = True,
    include_e: bool = True,
) -> None:
    print_color_action_keys(
        include_v=include_v,
        include_u=include_u,
        include_e=include_e,
        extras=extras,
    )


__all__ = [
    "cyan_sample",
    "join_cyan_samples",
    "join_cyan_samples_spaced",
    "print_color_action_keys",
    "print_colors_header",
    "print_colors_other_line",
    "print_how_to_set_color",
    "print_how_to_set_color_methods",
    "print_palettes_block",
    "print_recommended_palettes",
    "print_saved_colors_block",
    "print_spine_tick_keys_line",
    "print_spine_tick_keys_note",
]

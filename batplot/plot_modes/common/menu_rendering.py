"""Shared rendering helpers for interactive terminal menus."""

from __future__ import annotations

import os
import sys
import threading
from collections.abc import MutableSequence, Sequence
from typing import Any

# Visual frame around key-description blocks (before/after), so the input
# prompt row is easier to separate from the listed keys.
MENU_SEPARATOR_LINE = "-" * 60
_tls = threading.local()

# ANSI escape overhead for cyan command + reset (used for column padding).
_ANSI_CYAN_PAD = len("\033[96m") + len("\033[0m")


def ansi_menu_enabled() -> bool:
    """True when menu cyan/yellow escapes should be emitted.

    Honors ``NO_COLOR`` (https://no-color.org/), ``TERM=dumb``, and non-TTY
    stdout. Print-only — never affects keys, dispatch, or p/i/s/b.
    """
    if os.environ.get("NO_COLOR", "").strip():
        return False
    if os.environ.get("TERM", "").strip().lower() == "dumb":
        return False
    try:
        return bool(sys.stdout.isatty())
    except Exception:
        return False


def normalize_menu_heading(heading: str) -> str:
    """``(Styles)`` and ``Styles`` both display as ``Styles``."""
    h = str(heading).strip()
    if len(h) >= 2 and h.startswith("(") and h.endswith(")"):
        inner = h[1:-1].strip()
        if inner:
            return inner
    return h


def print_menu_separator() -> None:
    """Print the dashed line used to frame menu key descriptions."""
    print(MENU_SEPARATOR_LINE)


def menu_block_is_open() -> bool:
    return bool(getattr(_tls, "open", False))


def menu_block_begin(*, force_new: bool = False) -> None:
    """Open a menu description block (prints the leading dashed line once).

    ``force_new=True`` closes any leftover open block first (used by main menus
    and shared submenu runners that own the full description block).
    """
    if force_new and getattr(_tls, "open", False):
        menu_block_end()
    if not getattr(_tls, "open", False):
        print_menu_separator()
        _tls.open = True


def menu_block_end() -> None:
    """Close a menu description block (prints the trailing dashed line once)."""
    if getattr(_tls, "open", False):
        print_menu_separator()
        _tls.open = False


def colorize_menu_item(text: str) -> str:
    """Colorize ``command: description`` menu rows consistently (pure, no I/O)."""
    raw = str(text).strip()
    if ":" not in raw:
        return raw
    command, description = raw.split(":", 1)
    cmd = command.strip()
    desc = description.strip()
    if not ansi_menu_enabled():
        return f"{cmd}: {desc}"
    return f"\033[96m{cmd}\033[0m: {desc}"


def colorize_menu(text: str) -> str:
    """Colorize a key row and open the description block on first use.

    Prefer this (or a thin wrapper around it) when printing interactive key
    lists so the block is automatically closed by :func:`colorize_prompt`.
    """
    menu_block_begin()
    return colorize_menu_item(text)


def append_last_action_shortcuts(options: MutableSequence[str], fig: Any) -> None:
    """Append overwrite shortcuts based on the figure's last saved/exported paths."""
    if fig is None:
        return
    if getattr(fig, "_last_session_save_path", None):
        options.append("os: overwrite session")
    if getattr(fig, "_last_style_export_path", None):
        options.append("ops: overwrite style")
        options.append("opsg: overwrite style+geom")
    if getattr(fig, "_last_figure_export_path", None):
        options.append("oe: overwrite figure")


def command_keys_from_columns(columns: Sequence[Sequence[str]]) -> set[str]:
    """Return the command keys displayed in menu column item strings."""
    keys: set[str] = set()
    for items in columns:
        for item in items:
            text = str(item).strip()
            if ":" not in text:
                continue
            key = text.split(":", 1)[0].strip()
            if key:
                keys.add(key)
    return keys


def format_batch_key_unavailable(cmd: str, reason: str) -> str:
    """Consistent reject text when a single-session-only key is typed in batch."""
    c = str(cmd).strip()
    r = str(reason).strip().rstrip(".")
    return f"{c!r} is not available in batch — {r}. Use single-session --i."


def print_menu_columns(
    *,
    title: str,
    columns: Sequence[tuple[str, Sequence[str]]],
    min_widths: Sequence[int] | None = None,
    colorize_item=colorize_menu_item,
    trailing_blank: bool = False,
) -> None:
    """Print aligned menu columns with yellow headings and cyan commands."""
    min_widths = min_widths or ()
    use_ansi = ansi_menu_enabled()
    pad = _ANSI_CYAN_PAD if use_ansi else 0
    widths = []
    norm_cols: list[tuple[str, Sequence[str]]] = []
    for idx, (heading, items) in enumerate(columns):
        h = normalize_menu_heading(heading)
        # Strip leading pad spaces from items (operando alignment hacks).
        clean_items = [str(it).strip() for it in items]
        floor = min_widths[idx] if idx < len(min_widths) else 12
        widths.append(max(len(h), *(len(item) for item in clean_items), floor))
        norm_cols.append((h, clean_items))

    rows = max((len(items) for _heading, items in norm_cols), default=0)
    print()  # space before framed menu (replaces former leading newline on title)
    menu_block_begin(force_new=True)
    if use_ansi:
        print(f"\033[1m{title}:\033[0m")
    else:
        print(f"{title}:")
    if use_ansi:
        header = " ".join(
            f"\033[93m{heading:<{width}}\033[0m"
            for (heading, _items), width in zip(norm_cols, widths)
        )
    else:
        header = " ".join(
            f"{heading:<{width}}"
            for (heading, _items), width in zip(norm_cols, widths)
        )
    print(f"  {header}")
    for row_idx in range(rows):
        rendered = []
        for (_heading, items), width in zip(norm_cols, widths):
            if row_idx < len(items):
                item = colorize_item(items[row_idx])
                rendered.append(f"{item:<{width + pad}}")
            else:
                rendered.append(f"{'':<{width}}")
        print("  " + " ".join(rendered))
    menu_block_end()
    if trailing_blank:
        print()
    sys.stdout.flush()


from .terminal import prompt_menu_key


__all__ = [
    "MENU_SEPARATOR_LINE",
    "ansi_menu_enabled",
    "append_last_action_shortcuts",
    "command_keys_from_columns",
    "colorize_menu",
    "colorize_menu_item",
    "format_batch_key_unavailable",
    "menu_block_begin",
    "menu_block_end",
    "menu_block_is_open",
    "normalize_menu_heading",
    "print_menu_columns",
    "print_menu_separator",
    "prompt_menu_key",
]

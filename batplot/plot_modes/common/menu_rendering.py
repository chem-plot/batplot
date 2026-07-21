"""Shared rendering helpers for interactive terminal menus."""

from __future__ import annotations

from collections.abc import MutableSequence, Sequence
from typing import Any


def colorize_menu_item(text: str) -> str:
    """Colorize ``command: description`` menu rows consistently."""
    if ":" not in text:
        return text
    command, description = text.split(":", 1)
    return f"\033[96m{command.strip()}\033[0m: {description.strip()}"


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


def print_menu_columns(
    *,
    title: str,
    columns: Sequence[tuple[str, Sequence[str]]],
    min_widths: Sequence[int] | None = None,
    colorize_item=colorize_menu_item,
    trailing_blank: bool = False,
) -> None:
    """Print aligned menu columns with yellow headings and cyan commands."""
    import sys

    min_widths = min_widths or ()
    widths = []
    for idx, (heading, items) in enumerate(columns):
        floor = min_widths[idx] if idx < len(min_widths) else 12
        widths.append(max(len(heading), *(len(item) for item in items), floor))

    rows = max((len(items) for _heading, items in columns), default=0)
    print(f"\n\033[1m{title}:\033[0m")
    header = " ".join(
        f"\033[93m{heading:<{width}}\033[0m"
        for (heading, _items), width in zip(columns, widths)
    )
    print(f"  {header}")
    for row_idx in range(rows):
        rendered = []
        for (_heading, items), width in zip(columns, widths):
            if row_idx < len(items):
                item = colorize_item(items[row_idx])
                rendered.append(f"{item:<{width + 9}}")
            else:
                rendered.append(f"{'':<{width}}")
        print("  " + " ".join(rendered))
    if trailing_blank:
        print()
    sys.stdout.flush()


from .terminal import prompt_menu_key


__all__ = [
    "append_last_action_shortcuts",
    "command_keys_from_columns",
    "colorize_menu_item",
    "print_menu_columns",
    "prompt_menu_key",
]

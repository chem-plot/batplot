"""Menu rendering helpers for CPC interactive mode."""

from __future__ import annotations

from ..common.menu_rendering import (
    append_last_action_shortcuts,
    command_keys_from_columns,
    colorize_menu_item,
    print_menu_columns,
)


def _colorize_menu(text: str) -> str:
    return colorize_menu_item(text)


def build_cpc_menu_columns(fig=None):
    """Build CPC interactive menu columns without printing them."""
    col1 = [
        "f: font",
        "l: line",
        "m: marker sizes",
        "c: colors",
        "d: display (Chg/Dch)",
        "ry: show/hide efficiency",
        "t: toggle spines",
        "h: legend",
        "g: size",
        "v: show/hide files",
    ]
    col2 = [
        "r: rename",
        "x: x range",
        "y: y ranges",
        "ie: invert efficiency",
    ]
    col3 = [
        "n: crosshair",
        "p: print(export) style/geom",
        "i: import style/geom",
        "e: export figure",
        "s: save project",
        "b: undo",
        "q: quit",
    ]

    if fig is not None:
        try:
            is_multi = bool(getattr(fig, '_cpc_is_multi_file', False))
        except Exception:
            is_multi = True
        if not is_multi:
            col1 = [item for item in col1 if not item.strip().startswith("v:")]

    append_last_action_shortcuts(col3, fig)
    return col1, col2, col3


def cpc_menu_command_keys(fig=None) -> set[str]:
    return command_keys_from_columns(build_cpc_menu_columns(fig))


def print_cpc_menu(fig=None) -> None:
    """Print CPC interactive menu with Styles, Geometries, Options columns."""
    col1, col2, col3 = build_cpc_menu_columns(fig)
    print_menu_columns(
        title="CPC Interactive Menu",
        columns=[
            ("(Styles)", col1),
            ("(Geometries)", col2),
            ("(Options)", col3),
        ],
        min_widths=(18, 18, 12),
    )

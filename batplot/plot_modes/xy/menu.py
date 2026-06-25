"""Top-level menu rendering for the XY interactive menu.

Mirrors the ``menu.py`` module that the other plot modes use: it owns the
column layout and printing, delegating the actual terminal formatting to
``common.menu_rendering`` so a presentation fix applies to every mode.
"""

from __future__ import annotations

from typing import Any, Callable

from ..common.menu_rendering import append_last_action_shortcuts, print_menu_columns


def print_xy_menu(
    *,
    fig: Any,
    stack: bool,
    is_diffraction: bool,
    colorize_menu: Callable[[str], str],
) -> None:
    """Print 1D/XY interactive menu. Hides o/y in --stack, n in non-diffraction."""
    col1 = ["c: colors", "f: font", "l: line", "t: toggle spines", "g: size", "h: legend", "sm: smooth"]
    # Place CIF submenu entry under Geometries; always show it so users
    # discover CIF support even before adding CIF files.
    col2 = ["a: rearrange", "o: offset", "r: rename", "x: change X", "y: change Y", "d: derivative", "cif: CIF ticks"]
    col3 = ["v: find peaks", "n: crosshair", "p: print(export) style/geom", "i: import style/geom", "e: export figure", "s: save project", "b: undo", "q: quit"]

    append_last_action_shortcuts(col3, fig)

    # Hide offset/y-range in stack mode
    if stack:
        col2 = [item for item in col2 if not item.startswith("o:") and not item.startswith("y:")]

    if not is_diffraction:
        col3 = [item for item in col3 if not item.startswith("n:")]
    print_menu_columns(
        title="1D Interactive Menu",
        columns=[
            ("(Styles)", col1),
            ("(Geometries)", col2),
            ("(Options)", col3),
        ],
        min_widths=(16, 16, 16),
        colorize_item=colorize_menu,
    )


__all__ = ["print_xy_menu"]

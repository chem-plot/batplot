"""Menu rendering helpers for electrochemistry interactive modes."""

from __future__ import annotations

from ..common.menu_rendering import (
    append_last_action_shortcuts,
    command_keys_from_columns,
    colorize_menu,
    print_menu_columns,
)


def _colorize_menu(text: str) -> str:
    return colorize_menu(text)


def build_electrochem_menu_columns(
    _n_cycles: int,
    is_dqdv: bool = False,
    fig=None,
    is_multi_file: bool = False,
    canvas_mode: bool = False,
):
    """Build EC interactive menu columns without printing them."""
    col1 = [
        "f: font",
        "l: line style",
        "k: spine colors",
        "t: spines/ticks",
        "h: legend",
        "d: display (Chg/Dch)",
    ]
    if not canvas_mode:
        col1.insert(5, "g: size")
    if is_dqdv:
        col1.insert(2, "sm: smooth")
    if is_multi_file:
        col1.append("v: show/hide files")

    col2 = [
        "c: cycles/colors",
        "r: rename",
        "x: x range",
        "y: y range",
    ]
    # Capacity/ion axis tools are GC-only (CV has no capacity X to convert).
    is_gc_session = True
    if fig is not None and hasattr(fig, "_ec_is_gc"):
        is_gc_session = bool(getattr(fig, "_ec_is_gc"))
    elif fig is not None and hasattr(fig, "_ec_overview_enabled"):
        is_gc_session = bool(getattr(fig, "_ec_overview_enabled"))
    if not is_dqdv and is_gc_session:
        col2.insert(2, "a: capacity/ion")

    col3 = [
        "n: crosshair",
        "p: print(export) style/geom",
        "i: import style/geom",
        "e: export figure",
        "s: save project",
        "b: undo",
        "q: quit",
    ]
    # Overview is GC-only (charge/discharge capacity curves). CV/dQdV omit it.
    show_overview = False
    if not is_dqdv:
        if fig is not None and hasattr(fig, "_ec_overview_enabled"):
            show_overview = bool(getattr(fig, "_ec_overview_enabled"))
        else:
            show_overview = True  # GC sessions / callers that omit the flag
    if show_overview:
        col3.insert(1, "o: overview")
    if is_dqdv:
        col3.insert(-1, "2d: dQ/dV contour")

    append_last_action_shortcuts(col3, fig)
    return col1, col2, col3


def electrochem_menu_command_keys(
    n_cycles: int,
    is_dqdv: bool = False,
    fig=None,
    is_multi_file: bool = False,
    canvas_mode: bool = False,
) -> set[str]:
    return command_keys_from_columns(
        build_electrochem_menu_columns(n_cycles, is_dqdv, fig, is_multi_file, canvas_mode)
    )


def print_electrochem_menu(
    n_cycles: int,
    is_dqdv: bool = False,
    fig=None,
    is_multi_file: bool = False,
    menu_title: str = "Interactive menu",
    canvas_mode: bool = False,
) -> None:
    """Print EC interactive menu (GC/CV/dQ/dV) in three aligned columns."""
    col1, col2, col3 = build_electrochem_menu_columns(
        n_cycles,
        is_dqdv=is_dqdv,
        fig=fig,
        is_multi_file=is_multi_file,
        canvas_mode=canvas_mode,
    )
    print_menu_columns(
        title=menu_title,
        columns=[
            ("Styles", col1),
            ("Geometries", col2),
            ("Options", col3),
        ],
        min_widths=(18, 12, 12),
    )


__all__ = [
    "_colorize_menu",
    "build_electrochem_menu_columns",
    "electrochem_menu_command_keys",
    "print_electrochem_menu",
]

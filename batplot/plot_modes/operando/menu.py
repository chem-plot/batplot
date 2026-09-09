"""Menu rendering helpers for operando interactive mode."""

from __future__ import annotations

from ..common.menu_rendering import (
    append_last_action_shortcuts,
    command_keys_from_columns,
    colorize_menu,
    print_menu_columns,
)


def _colorize_menu(text: str) -> str:
    return colorize_menu(text)


def build_operando_ec_menu_columns(fig, ec_ax=None):
    """Build operando contour menu columns without printing them."""
    if ec_ax is not None:
        col1 = [
            "oc: op colormap",
            "el: ec curve",
            "v: toggle colorbar/ec",
            "t: spines/ticks",
            "k: spine colors",
            "l: line style",
            "f: font",
            "g: size",
            "r: reverse plot",
        ]
        col2 = [
            "ox: X range",
            "oy: Y range",
            "oz: intensity range",
            "or: rename",
            "c: CIF ticks",
            "pk: peak search",
        ]
        col3 = [
            "et: time range",
            "ex: x range",
            "ey: ion labels (time Y)",
            "er: rename",
            "eg: grid",
        ]
        col4 = [
            "n: crosshair",
            "u: axis units (XRD only)",
            "p: print(export) style/geom",
            "i: import style/geom",
            "e: export figure",
            "s: save project",
            "b: undo",
            "q: quit",
        ]
        # Hide XRD-only axis convert for non-XRD / dQdV contours
        try:
            from .axis_units import is_operando_xrd_axis
            if not is_operando_xrd_axis(fig):
                col4 = [item for item in col4 if not item.startswith("u:")]
        except Exception:
            pass
        append_last_action_shortcuts(col4, fig)
        return [
            ("Styles", col1),
            ("Operando", col2),
            ("Side Panel", col3),
            ("Options", col4),
        ], (12, 14, 14, 16)
    else:
        col1 = [
            "oc: op colormap",
            "v: toggle colorbar",
            "t: spines/ticks",
            "k: spine colors",
            "l: line style",
            "f: font",
            "g: size",
            "r: reverse plot",
        ]
        col2 = [
            "ox: X range",
            "oy: Y range",
            "oz: intensity range",
            "or: rename",
            "c: CIF ticks",
            "pk: peak search",
        ]
        col3 = [
            "n: crosshair",
            "u: axis units (XRD only)",
            "p: print(export) style/geom",
            "i: import style/geom",
            "e: export figure",
            "s: save project",
            "b: undo",
            "q: quit",
        ]
        try:
            from .axis_units import is_operando_xrd_axis
            if not is_operando_xrd_axis(fig):
                col3 = [item for item in col3 if not item.startswith("u:")]
        except Exception:
            pass
        append_last_action_shortcuts(col3, fig)
        return [
            ("Styles", col1),
            ("Operando", col2),
            ("Options", col3),
        ], (12, 14, 16)


def operando_ec_menu_command_keys(fig, ec_ax=None) -> set[str]:
    columns, _min_widths = build_operando_ec_menu_columns(fig, ec_ax)
    return command_keys_from_columns([items for _heading, items in columns])


def print_operando_ec_menu(fig, ec_ax=None) -> None:
    """Print operando contour interactive menu."""
    columns, min_widths = build_operando_ec_menu_columns(fig, ec_ax)
    print_menu_columns(
        title="Contourplot Interactive Menu",
        columns=columns,
        min_widths=min_widths,
    )
    print()

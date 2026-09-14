"""Spine color menu helpers for EC interactive mode."""

from __future__ import annotations

from typing import Any, Callable

from ...color_utils import (
    format_color_listing,
    manage_user_colors,
    prompt_screen_color,
    blank_means_back,
    resolve_color_token,
)
from ...ui import set_spine_side_color
from ..common.color_menu_help import (
    join_cyan_samples,
    print_color_action_keys,
    print_how_to_set_color_methods,
    print_saved_colors_block,
    print_spine_tick_keys_note,
)

def run_ec_spine_color_menu(
    *,
    fig: Any,
    ax: Any,
    tick_state: dict,
    apply_spine_color: Callable[..., Any],
    push_state: Callable[[str], Any],
    safe_input: Callable[[str], str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
) -> None:
    """Run the EC spine-color submenu.

    Keys are always WASD (same as the spine/tick menu): ``w`` top, ``a`` left,
    ``s`` bottom, ``d`` right — including GC dual capacity/ions mode.
    """
    try:
        is_dual_xaxis = getattr(fig, "_xaxis_mode", "capacity") == "dual"
        key_to_spine = {"w": "top", "a": "left", "s": "bottom", "d": "right"}
        while True:
            print_how_to_set_color_methods(
                [
                    (
                        "Spine color (w/a/s/d)",
                        join_cyan_samples("w:red", "a:#4561F7", "s:blue", "d:green"),
                    ),
                ]
            )
            print_spine_tick_keys_note(colorize_menu=colorize_menu)
            if is_dual_xaxis and getattr(fig, "_xaxis_secondary", None) is not None:
                swapped = bool(getattr(fig, "_xaxis_swapped", False))
                top_role = "capacity" if swapped else "ions"
                bot_role = "ions" if swapped else "capacity"
                print(
                    f"  Dual x-axis: w=top ({top_role}), s=bottom ({bot_role}) "
                    "(follows a-menu / swap)"
                )
            print_saved_colors_block(fig, colorize_menu=colorize_menu)
            print_color_action_keys(colorize_menu=colorize_menu, include_v=False)
            line = safe_input(colorize_prompt("Selection: ")).strip()
            if line.lower() == "q" or blank_means_back(line):
                break
            if line.lower() == "u":
                manage_user_colors(fig)
                continue
            if line.lower() == "e":
                prompt_screen_color(fig)
                continue
            pairs = list(_parse_spine_color_pairs(line))
            planned = []
            for key_part, color in pairs:
                if key_part not in key_to_spine:
                    print(f"Unknown key: {key_part} (use w/a/s/d)")
                    continue
                spine_name = key_to_spine[key_part]
                if spine_name not in ax.spines:
                    print(f"Spine '{spine_name}' not found.")
                    continue
                try:
                    resolved = resolve_color_token(color, fig)
                except Exception as exc:
                    print(f"Error setting {spine_name} color: {exc}")
                    continue
                planned.append((spine_name, resolved, color))
            if not planned:
                continue
            push_state("color-spine")
            for spine_name, resolved, color in planned:
                try:
                    if is_dual_xaxis and spine_name == "top" and hasattr(fig, "_xaxis_secondary"):
                        _apply_secondary_top_spine_color(fig, resolved, color)
                    else:
                        apply_spine_color(ax, fig, tick_state, spine_name, resolved)
                        print(f"Set {spine_name} spine to {format_color_listing(resolved)}")
                except Exception as exc:
                    print(f"Error setting {spine_name} color: {exc}")
            try:
                from .style import reseal_ec_chrome

                reseal_ec_chrome(fig, ax, tick_state=tick_state)
            except Exception:
                pass
            fig.canvas.draw()
    except Exception as exc:
        print(f"Error in spine color menu: {exc}")


def _parse_spine_color_pairs(line: str) -> list[tuple[str, str]]:
    tokens = line.split()
    pairs = []
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if ":" in token:
            key_part, color = token.split(":", 1)
        else:
            if idx + 1 >= len(tokens):
                print(f"Skip incomplete entry: {token}")
                break
            key_part = token
            color = tokens[idx + 1]
            idx += 1
        pairs.append((key_part.lower(), color))
        idx += 1
    return pairs


def _apply_secondary_top_spine_color(fig: Any, resolved, original_color: str) -> None:
    """Color dual-mode top: SecondaryAxis spine+ticks+title AND primary top spine."""
    from ...ui import _force_ec_dual_secax_tick_colors, register_spine_color_axis

    secax = getattr(fig, "_xaxis_secondary", None)
    if secax is None:
        print("Secondary axis not found.")
        return
    try:
        fig._bp_spine_secondary_ax = secax
    except Exception:
        pass
    try:
        parent = getattr(secax, "_parent", None)
        parent_ts = (
            getattr(parent, "_saved_tick_state", None) if parent is not None else None
        )
        # Secondary: spine, tick lines/labels, and xaxis.label title
        set_spine_side_color(
            secax, "top", resolved, fig=fig, tick_state=parent_ts
        )
        # Explicit force — do not rely on set_spine_side_color skip_ax path alone.
        _force_ec_dual_secax_tick_colors(secax, resolved)
        register_spine_color_axis(fig, secax)
        # Primary top spine remains visible under dual mode — match via store path.
        if parent is not None and parent.spines.get("top") is not None:
            try:
                set_spine_side_color(
                    parent, "top", resolved, fig=fig, tick_state=parent_ts
                )
            except Exception:
                try:
                    parent.spines["top"].set_edgecolor(resolved)
                except Exception:
                    pass
            try:
                parent._stored_top_xlabel_color = resolved
            except Exception:
                pass
            register_spine_color_axis(fig, parent)
        print(f"Set top x-spine (secondary) to {format_color_listing(resolved)}")
    except Exception as exc:
        print(f"Error setting secondary top spine color: {exc}")


__all__ = ["run_ec_spine_color_menu"]

"""Spine color menu helpers for EC interactive mode."""

from __future__ import annotations

from typing import Any, Callable

from ...color_utils import color_block, format_color_listing, get_user_color_list, manage_user_colors, resolve_color_token
from ...ui import set_spine_side_color
from ..common.terminal import colorize_inline_commands


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
    """Run the EC spine-color submenu."""
    try:
        is_dual_xaxis = getattr(fig, "_xaxis_mode", "capacity") == "dual"
        while True:
            print("\nSet spine colors (with matching tick and label colors):")
            print(colorize_inline_commands("  a : left y-spine   | d : right y-spine"))
            if is_dual_xaxis:
                print(colorize_inline_commands("  t : top x-spine    | b : bottom x-spine"))
                print(colorize_inline_commands("Example: a:red d:blue t:green b:orange"))
            else:
                print(colorize_inline_commands("  w : top spine      | s : bottom spine"))
                print(colorize_inline_commands("Example: w:red a:#4561F7 s:blue d:green"))
            user_colors = get_user_color_list(fig)
            if user_colors:
                print("\nSaved colors (enter number or u# to reuse):")
                for idx, color in enumerate(user_colors, 1):
                    print("  " + colorize_menu(f"{idx}: {format_color_listing(color)}"))
                print("  " + colorize_menu("u: edit saved colors"))
            print("  " + colorize_menu("q: back to main menu"))
            line = safe_input(colorize_prompt("Enter mappings (e.g., a:red d:blue, q=back): ")).strip()
            if not line or line.lower() == "q":
                break
            if line.lower() == "u":
                manage_user_colors(fig)
                continue
            push_state("color-spine")
            key_to_spine = {"a": "left", "d": "right", "t": "top", "b": "bottom"} if is_dual_xaxis else {"w": "top", "a": "left", "s": "bottom", "d": "right"}
            for key_part, color in _parse_spine_color_pairs(line):
                if key_part not in key_to_spine:
                    if is_dual_xaxis:
                        print(f"Unknown key: {key_part} (use a/d for y-spines, t/b for x-spines)")
                    else:
                        print(f"Unknown key: {key_part} (use w/a/s/d)")
                    continue
                spine_name = key_to_spine[key_part]
                if spine_name not in ax.spines:
                    print(f"Spine '{spine_name}' not found.")
                    continue
                try:
                    resolved = resolve_color_token(color, fig)
                    if is_dual_xaxis and spine_name == "top" and hasattr(fig, "_xaxis_secondary"):
                        _apply_secondary_top_spine_color(fig, resolved, color)
                    else:
                        apply_spine_color(ax, fig, tick_state, spine_name, resolved)
                        descriptor = "bottom x-spine" if is_dual_xaxis and spine_name == "bottom" else spine_name
                        print(f"Set {descriptor} spine to {format_color_listing(resolved)}")
                except Exception as exc:
                    print(f"Error setting {spine_name} color: {exc}")
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
    secax = fig._xaxis_secondary
    if secax is not None:
        try:
            set_spine_side_color(secax, "top", resolved, fig=fig)
            print(f"Set top x-spine (secondary) to {format_color_listing(resolved)}")
        except Exception as exc:
            print(f"Error setting secondary top spine color: {exc}")
    else:
        print("Secondary axis not found.")


__all__ = ["run_ec_spine_color_menu"]

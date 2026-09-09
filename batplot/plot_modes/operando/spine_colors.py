"""Spine color menu for operando (+ optional EC side panel)."""

from __future__ import annotations

from typing import Any, Callable, Optional

from ...color_utils import (
    blank_means_back,
    format_color_listing,
    get_user_color_list,
    manage_user_colors,
    prompt_screen_color,
    resolve_color_token,
)
from ...ui import (
    finalize_spine_colors_for_axes,
    register_spine_color_axis,
    set_spine_side_color,
)
from ..common.terminal import colorize_inline_commands
from ..electrochem.spine_colors import _parse_spine_color_pairs


def _ensure_ec_tick_state(ax: Any) -> dict:
    """Seed/reconcile EC right-side bookkeeping (fresh ``tick_right()`` panels).

    Wrong left-on/right-off bookkeeping makes ``k``→``d`` skip tick coloring.
    """
    from ...ui import _tick_state_from_live_artists

    saved = getattr(ax, "_saved_tick_state", None)
    if isinstance(saved, dict):
        ts = dict(saved)
    else:
        ts = _tick_state_from_live_artists(ax)
    # Reconcile with live Y tick position (operando EC defaults to right).
    y_pos = ""
    try:
        y_pos = str(ax.yaxis.get_ticks_position() or "")
    except Exception:
        y_pos = ""
    if y_pos == "right" or (
        not ts.get("r_ticks") and not ts.get("l_ticks")
    ):
        # Prefer right when ticks live on the right, or neither side is recorded.
        if y_pos == "right" or not (ts.get("r_ticks") or ts.get("l_ticks")):
            ts["r_ticks"] = True
            ts["r_labels"] = True
            ts["l_ticks"] = False
            ts["l_labels"] = False
            ts["ry"] = True
            ts["ly"] = False
    try:
        ax._saved_tick_state = dict(ts)
    except Exception:
        pass
    return ts


def apply_operando_spine_color(
    fig: Any,
    ax: Any,
    side: str,
    color,
    *,
    tick_state: Optional[dict] = None,
    peer_ax: Optional[Any] = None,
) -> None:
    """Apply one spine color on an operando/EC axis and keep stores in sync."""
    if ax is None or side not in ("top", "bottom", "left", "right"):
        return
    if ax.spines.get(side) is None:
        return
    # Register both panes BEFORE coloring so fig-store soft-write is suppressed.
    if fig is not None:
        register_spine_color_axis(fig, ax)
        if peer_ax is not None:
            register_spine_color_axis(fig, peer_ax)
    if isinstance(tick_state, dict):
        ts = tick_state
    else:
        ts = getattr(ax, "_saved_tick_state", None)
        if not isinstance(ts, dict):
            ts = _ensure_ec_tick_state(ax)
    # Per-axis store is authoritative for dual-pane.
    set_spine_side_color(ax, side, color, fig=fig, tick_state=ts)


def run_operando_spine_color_menu(
    *,
    fig: Any,
    ax: Any,
    ec_ax: Optional[Any],
    push_state: Callable[[str], Any],
    safe_input: Callable[[str], str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
    fixed_pane: Optional[str] = None,
) -> None:
    """Pane-scoped ``k`` menu: ``w/a/s/d:color`` for operando and/or EC axes.

    ``fixed_pane`` (``'o'``/``'e'``) skips the outer pane picker — used by batch
    ``k`` so each pane visit can sync independently (like batch ``t``).
    """
    key_to_spine = {"w": "top", "a": "left", "s": "bottom", "d": "right"}
    try:
        while True:
            if fixed_pane is not None:
                pane = str(fixed_pane).strip().lower()
                if pane not in ("o", "e"):
                    print("Unknown pane.")
                    break
                if pane == "e" and ec_ax is None:
                    print("EC panel not available (no .mpt file in folder).")
                    break
            elif ec_ax is not None:
                print(
                    colorize_inline_commands(
                        "Spine colors — choose pane: o=operando (contour), e=EC side panel, q=back"
                    )
                )
                pane = safe_input(
                    colorize_prompt("Pane (o=operando, e=ec, q=back): ")
                ).strip().lower()
            else:
                print(
                    colorize_inline_commands(
                        "Spine colors apply to the contour plot. q=back"
                    )
                )
                pane = safe_input(
                    colorize_prompt("Pane (o=operando contour, q=back): ")
                ).strip().lower()
            if not pane or pane == "q" or blank_means_back(pane):
                break
            if pane == "e" and ec_ax is None:
                print("EC panel not available (no .mpt file in folder).")
                if fixed_pane is not None:
                    break
                continue
            if pane not in ("o", "e"):
                print("Unknown pane.")
                if fixed_pane is not None:
                    break
                continue
            target = ax if pane == "o" else ec_ax
            if target is None:
                print("Unknown pane.")
                if fixed_pane is not None:
                    break
                continue
            try:
                # Batch sync reads this to avoid clobbering the other pane.
                fig._bp_last_spine_color_pane = pane  # type: ignore[attr-defined]
            except Exception:
                pass
            pane_label = "operando" if pane == "o" else "EC"
            while True:
                print(f"\nSet {pane_label} spine colors (ticks/labels match):")
                print(colorize_inline_commands("  w : top spine      | s : bottom spine"))
                print(colorize_inline_commands("  a : left y-spine   | d : right y-spine"))
                print(colorize_inline_commands("Example: w:red a:#4561F7 s:blue d:green"))
                user_colors = get_user_color_list(fig)
                if user_colors:
                    print("\nSaved colors (enter number or u# to reuse):")
                    for idx, color in enumerate(user_colors, 1):
                        print("  " + colorize_menu(f"{idx}: {format_color_listing(color)}"))
                    print("  " + colorize_menu("u: edit saved colors"))
                print("  " + colorize_menu("e: pick color from screen"))
                print(
                    "  "
                    + colorize_menu(
                        "q: back"
                        if fixed_pane is not None
                        else "q: back to pane choice"
                    )
                )
                line = safe_input(
                    colorize_prompt("Enter mappings (e.g., w:red a:blue, q=back): ")
                ).strip()
                if line.lower() == "q" or blank_means_back(line):
                    break
                if line.lower() == "u":
                    manage_user_colors(fig)
                    continue
                if line.lower() == "e":
                    prompt_screen_color(fig)
                    continue
                # Plan then push — reject unknown tokens before junk undo.
                planned: list[tuple[str, object]] = []
                for key_part, color in _parse_spine_color_pairs(line):
                    if key_part not in key_to_spine:
                        print(f"Unknown key: {key_part} (use w/a/s/d)")
                        continue
                    spine_name = key_to_spine[key_part]
                    if spine_name not in target.spines:
                        print(f"Spine '{spine_name}' not found.")
                        continue
                    try:
                        planned.append((spine_name, resolve_color_token(color, fig)))
                    except Exception as exc:
                        print(f"Error resolving {spine_name} color: {exc}")
                if not planned:
                    continue
                push_state(f"color-spine-{pane_label}")
                # Dual-pane isolation: register both before any color write.
                try:
                    register_spine_color_axis(fig, ax)
                    if ec_ax is not None:
                        register_spine_color_axis(fig, ec_ax)
                except Exception:
                    pass
                if pane == "e":
                    ts = _ensure_ec_tick_state(target)
                else:
                    ts = getattr(target, "_saved_tick_state", None)
                peer = ec_ax if pane == "o" else ax
                for spine_name, resolved in planned:
                    try:
                        apply_operando_spine_color(
                            fig,
                            target,
                            spine_name,
                            resolved,
                            tick_state=ts,
                            peer_ax=peer if peer is not target else None,
                        )
                        print(
                            f"Set {pane_label} {spine_name} spine to "
                            f"{format_color_listing(resolved)}"
                        )
                    except Exception as exc:
                        print(f"Error setting {spine_name} color: {exc}")
                try:
                    entries = [(ax, getattr(ax, "_saved_tick_state", None))]
                    if ec_ax is not None:
                        entries.append(
                            (ec_ax, getattr(ec_ax, "_saved_tick_state", None))
                        )
                    finalize_spine_colors_for_axes(fig, entries, draw=True)
                except Exception:
                    try:
                        fig.canvas.draw()
                    except Exception:
                        pass
            # Batch / single-pane visit: one pane then return to caller.
            if fixed_pane is not None:
                break
    except Exception as exc:
        print(f"Error in operando spine color menu: {exc}")


__all__ = [
    "apply_operando_spine_color",
    "run_operando_spine_color_menu",
]

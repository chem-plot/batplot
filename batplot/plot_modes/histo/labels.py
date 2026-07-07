"""Rename submenu (``r``) for the histogram interactive menu."""

from __future__ import annotations

from typing import Callable

from ...ui import position_bottom_xlabel, position_left_ylabel, position_top_xlabel
from ...utils import (
    convert_label_shortcuts,
    normalize_label_text,
    print_label_latex_tips,
    print_recent_axis_names,
    remember_axis_name,
)
from .plot import HistoState
from .spines import ensure_histo_tick_state, reapply_histo_spine_layout


def _apply_histo_label_change(fig, ax, state: HistoState) -> None:
    reapply_histo_spine_layout(fig, ax, state)
    tick_state = ensure_histo_tick_state(ax)
    if getattr(ax, "_top_xlabel_on", False):
        position_top_xlabel(ax, fig, tick_state)
    position_bottom_xlabel(ax, fig, tick_state)
    position_left_ylabel(ax, fig, tick_state)
    try:
        fig.canvas.draw_idle()
    except Exception:
        pass


def run_histo_rename_menu(
    *,
    fig,
    ax,
    state: HistoState,
    push_state: Callable[[], None],
    refresh: Callable[[], None],
    safe_input: Callable[..., str],
    colorize_prompt: Callable[[str], str],
) -> None:
    """Rename bottom x, left y, and top plot title (XY-style submenu)."""

    def _top_x_display() -> str:
        if state.style.top_xlabel:
            return state.style.top_xlabel
        return state.style.xlabel or "(same as x)"

    while True:
        print("\n\033[1mRename labels>\033[0m  Current:")
        print(f"  bottom x:  {state.style.xlabel or '(empty)'}")
        print(f"  y-axis:    {state.style.ylabel or state.y_label_default()}")
        print(f"  top title: {state.style.title or '(empty)'}")
        print(f"  top x:     {_top_x_display()}")
        choice = safe_input(
            colorize_prompt(
                "Rename (x=bottom x, y=y-axis, t=top title, o=top x-axis, s=recent, q=return): "
            ),
            cancel_on_interrupt=True,
        ).strip().lower()
        if not choice or choice == "q":
            break
        if choice == "s":
            print_recent_axis_names()
            continue
        if choice not in ("x", "y", "t", "o"):
            print("Unknown option.")
            continue

        print_label_latex_tips()
        if choice == "x":
            prompt = f"New bottom x-axis label [{state.style.xlabel}] (q=cancel): "
        elif choice == "y":
            prompt = f"New y-axis label [{state.style.ylabel}] (q=cancel): "
        elif choice == "t":
            prompt = f"New top plot title [{state.style.title}] (q=cancel): "
        else:
            prompt = f"New top x-axis label [{_top_x_display()}] (q=cancel): "

        raw = safe_input(colorize_prompt(prompt), cancel_on_interrupt=True).strip()
        if not raw or raw.lower() == "q":
            continue

        text = normalize_label_text(convert_label_shortcuts(raw))
        remember_axis_name(text)
        push_state()
        if choice == "x":
            state.style.xlabel = text
        elif choice == "y":
            state.style.ylabel = text
        elif choice == "t":
            state.style.title = text
        else:
            state.style.top_xlabel = text
            ax._top_xlabel_text_override = text  # type: ignore[attr-defined]
        refresh()
        _apply_histo_label_change(fig, ax, state)
        print("Label updated.")


__all__ = ["run_histo_rename_menu"]

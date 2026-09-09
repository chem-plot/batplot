"""Rename submenu (``r``) for the histogram interactive menu."""

from __future__ import annotations

from typing import Callable

from ...ui import position_bottom_xlabel, position_left_ylabel, position_top_xlabel
from ...utils import (
    finalize_axis_label_text,
    print_label_math_help,
    print_recent_axis_names,
    remember_axis_name,
    resolve_recent_axis_name,
)

_RECENT_MODE = "histo"
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
        print(f"  y-axis:    {state.style.ylabel if state.style.ylabel else '(empty)'}")
        print(f"  top title: {state.style.title or '(empty)'}")
        print(f"  top x:     {_top_x_display()}")
        choice = safe_input(
            colorize_prompt(
                "Rename (x=bottom x, y=y-axis, t=title, o=top x, s=recent, m=math help, q=return): "
            ),
            cancel_on_interrupt=True,
        ).strip().lower()
        if not choice or choice == "q":
            break
        if choice == "s":
            print_recent_axis_names(mode=_RECENT_MODE)
            continue
        if choice == "m":
            print_label_math_help()
            continue
        if choice not in ("x", "y", "t", "o"):
            print("Unknown option.")
            continue

        label_kind = choice
        while True:
            if label_kind == "x":
                prompt = (
                    f"New bottom x-axis label [{state.style.xlabel}] "
                    f"(-=clear, number=recent, s=list, m=math help, q=back): "
                )
            elif label_kind == "y":
                prompt = (
                    f"New y-axis label [{state.style.ylabel}] "
                    f"(-=clear, number=recent, s=list, m=math help, q=back): "
                )
            elif label_kind == "t":
                prompt = (
                    f"New top plot title [{state.style.title}] "
                    f"(-=clear, number=recent, s=list, m=math help, q=back): "
                )
            else:
                prompt = (
                    f"New top x-axis label [{_top_x_display()}] "
                    f"(-=clear, number=recent, s=list, m=math help, q=back): "
                )

            raw = safe_input(colorize_prompt(prompt), cancel_on_interrupt=True).strip()
            if not raw or raw.lower() == "q":
                break
            if raw.lower() == "s":
                print_recent_axis_names(mode=_RECENT_MODE)
                continue
            if raw.lower() == "m":
                print_label_math_help()
                continue

            if raw == "-":
                text = ""
            else:
                text = resolve_recent_axis_name(raw, mode=_RECENT_MODE)
                text = finalize_axis_label_text(text)
                remember_axis_name(text, mode=_RECENT_MODE)
            push_state()
            if label_kind == "x":
                state.style.xlabel = text
            elif label_kind == "y":
                state.style.ylabel = text
            elif label_kind == "t":
                state.style.title = text
            else:
                state.style.top_xlabel = text
                if text:
                    ax._top_xlabel_text_override = text  # type: ignore[attr-defined]
                elif hasattr(ax, "_top_xlabel_text_override"):
                    try:
                        delattr(ax, "_top_xlabel_text_override")
                    except Exception:
                        ax._top_xlabel_text_override = ""  # type: ignore[attr-defined]
            refresh()
            _apply_histo_label_change(fig, ax, state)
            print("Label updated." if text else "Label cleared.")


__all__ = ["run_histo_rename_menu"]

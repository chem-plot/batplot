"""Toggle submenu (``t``) for the histogram interactive menu."""

from __future__ import annotations

from typing import Callable, Optional

from ..common.spines import print_wasd_state, run_spine_tick_menu, sync_tick_state_from_wasd
from ..common.terminal import colorize_inline_commands
from .plot import HistoState
from .spines import (
    ensure_histo_tick_state,
    ensure_histo_wasd,
    histo_title_offset_menu,
    persist_histo_spine_before_redraw,
    reapply_histo_spine_layout,
    sync_histo_spine_from_reference,
)

_TICK_DEFAULTS = {"top": False, "bottom": True, "left": True, "right": False}
_LABEL_DEFAULTS = {"top": False, "bottom": True, "left": True, "right": False}


def _flag_text(flag: bool) -> str:
    return "\033[92mON\033[0m" if flag else "off"


def _run_histo_display_submenu(
    *,
    state: HistoState,
    toggle: Callable[[str], None],
    push_state: Callable[[], None],
    refresh: Callable[[], None],
    safe_input: Callable[..., str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
) -> None:
    options = {
        "d": "density vs count (y-axis)",
        "n": "bar value labels",
        "m": "mean and median lines",
    }
    while True:
        y_mode = "density" if state.style.density else "count"
        mean_med = []
        if state.style.show_mean_line:
            mean_med.append("mean")
        if state.style.show_median_line:
            mean_med.append("median")
        stats = ", ".join(mean_med) if mean_med else "off"
        print("\n\033[1mHistogram display>\033[0m  Current:")
        print(f"  y-axis:        {y_mode}")
        print(f"  bar labels:    {_flag_text(state.style.show_bar_labels)}")
        print(f"  mean/median:   {stats}")
        for key, description in options.items():
            print("  " + colorize_menu(f"{key}: {description}"))
        print("  " + colorize_menu("q: back"))
        choice = safe_input(colorize_prompt("Histogram (d/n/m/q): "), cancel_on_interrupt=True).strip().lower()
        if not choice or choice == "q":
            break
        if choice not in options:
            print("Unknown option.")
            continue
        push_state()
        toggle(choice)
        refresh()
        print(f"Toggled {options[choice]}.")


def run_histo_toggle_menu(
    *,
    fig,
    ax,
    state: HistoState,
    push_state: Callable[[], None],
    refresh: Callable[[], None],
    safe_input: Callable[..., str],
    colorize_prompt: Callable[[str], str],
    toggle_display: Callable[[str], None],
    colorize_menu: Callable[[str], str],
    sync_targets: Optional[list[tuple]] = None,
) -> None:
    """Run XY-style spine/tick menu plus histogram display toggles (``h``)."""
    tick_state = ensure_histo_tick_state(ax)
    wasd = ensure_histo_wasd(fig, ax, tick_state)

    def _push_labeled(_label: str) -> None:
        push_state()

    def _sync_tick_state() -> None:
        from ..common.spines import sync_legacy_tick_keys

        sync_tick_state_from_wasd(
            tick_state,
            wasd,
            tick_defaults=_TICK_DEFAULTS,
            label_defaults=_LABEL_DEFAULTS,
        )
        sync_legacy_tick_keys(tick_state)
        ax._saved_tick_state = dict(tick_state)
        if sync_targets:
            sync_histo_spine_from_reference(fig, ax, sync_targets)

    def _apply_wasd(changed_sides=None) -> None:
        reapply_histo_spine_layout(fig, ax, state, changed_sides=changed_sides)
        if sync_targets:
            sync_histo_spine_from_reference(fig, ax, sync_targets)

    def _draw() -> None:
        persist_histo_spine_before_redraw(fig, ax, sync_targets=sync_targets)
        refresh()
        try:
            fig.canvas.draw()
        except Exception:
            fig.canvas.draw_idle()

    def _print_state() -> None:
        print_wasd_state(wasd, axis_map={"x": ax.xaxis, "y": ax.yaxis}, fig=fig)
        y_mode = "density" if state.style.density else "count"
        print("\033[1mHistogram display:\033[0m")
        print(f"  y-axis={y_mode}  bar labels={_flag_text(state.style.show_bar_labels)}  "
              f"mean={_flag_text(state.style.show_mean_line)}  "
              f"median={_flag_text(state.style.show_median_line)}")

    cyan, reset = "\033[96m", "\033[0m"
    extra_help = [
        f"  Histogram       : {cyan}h{reset}=density, bar labels, mean/median",
    ]

    def _extra_command(cmd: str) -> bool:
        if cmd != "h":
            return False
        _run_histo_display_submenu(
            state=state,
            toggle=toggle_display,
            push_state=push_state,
            refresh=_draw,
            safe_input=safe_input,
            colorize_menu=colorize_menu,
            colorize_prompt=colorize_prompt,
        )
        return True

    def _title_offsets() -> None:
        histo_title_offset_menu(
            fig=fig,
            ax=ax,
            tick_state=tick_state,
            push_state=push_state,
            safe_input=safe_input,
            colorize_prompt=colorize_prompt,
        )
        persist_histo_spine_before_redraw(fig, ax, sync_targets=sync_targets)
        refresh()
        try:
            fig.canvas.draw()
        except Exception:
            fig.canvas.draw_idle()

    run_spine_tick_menu(
        fig=fig,
        wasd=wasd,
        safe_input=safe_input,
        colorize_prompt=colorize_prompt,
        colorize_inline_commands=colorize_inline_commands,
        push_state=_push_labeled,
        sync_tick_state=_sync_tick_state,
        apply_wasd=_apply_wasd,
        draw=_draw,
        mode_label="histogram axes",
        back_label="histogram menu",
        axis_map={"x": ax.xaxis, "y": ax.yaxis},
        direction_axes=[ax],
        length_axes=[ax],
        title_offset_handler=_title_offsets,
        on_quit=lambda: setattr(ax, "_saved_tick_state", dict(tick_state)),
        print_state=_print_state,
        extra_help_lines=extra_help,
        extra_command_handler=_extra_command,
    )


__all__ = ["run_histo_toggle_menu"]

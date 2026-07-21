"""Y-axis range menu for histogram mode."""

from __future__ import annotations

from typing import Callable

from .plot import HistoState, histo_auto_ylim, histo_current_ylim


def _set_ylim(state: HistoState, ymin: float, ymax: float) -> None:
    if ymin == ymax:
        eps = abs(ymin) * 1e-6 if ymin != 0 else 1e-6
        ymin -= eps
        ymax += eps
    state.style.ylim = (float(ymin), float(ymax))


def run_histo_y_range_menu(
    *,
    state: HistoState,
    push_state: Callable[[], None],
    refresh: Callable[[], None],
    safe_input: Callable[..., str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
    extra_status: Callable[[], None] | None = None,
) -> None:
    """Interactive submenu to adjust histogram y-axis limits."""

    while True:
        if extra_status is not None:
            extra_status()
        current = histo_current_ylim(state)
        mode = "fixed" if state.style.ylim is not None else "auto"
        if extra_status is None:
            print(f"Current Y range ({mode}): {current[0]:.6g} to {current[1]:.6g}")
        print("  " + colorize_menu("limit1 limit2: set both limits (either order)"))
        print("  " + colorize_menu("w: upper only"))
        print("  " + colorize_menu("s: lower only"))
        print("  " + colorize_menu("a: auto (from data)"))
        print("  " + colorize_menu("q: back"))
        rng = safe_input(colorize_prompt("Y (w/s/a/q): "), cancel_on_interrupt=True).strip().lower()
        if not rng or rng == "q":
            break
        if rng == "w":
            while True:
                current = histo_current_ylim(state)
                val = safe_input(
                    colorize_prompt(
                        f"Enter upper limit (current lower: {current[0]:.6g}, q=back): "
                    ),
                    cancel_on_interrupt=True,
                ).strip()
                if not val or val.lower() == "q":
                    break
                try:
                    new_upper = float(val)
                except ValueError:
                    print("Invalid value, ignored.")
                    continue
                push_state()
                _set_ylim(state, current[0], new_upper)
                refresh()
                updated = histo_current_ylim(state)
                print(f"Y range updated: {updated[0]:.6g} to {updated[1]:.6g}")
            continue
        if rng == "s":
            while True:
                current = histo_current_ylim(state)
                val = safe_input(
                    colorize_prompt(
                        f"Enter lower limit (current upper: {current[1]:.6g}, q=back): "
                    ),
                    cancel_on_interrupt=True,
                ).strip()
                if not val or val.lower() == "q":
                    break
                try:
                    new_lower = float(val)
                except ValueError:
                    print("Invalid value, ignored.")
                    continue
                push_state()
                _set_ylim(state, new_lower, current[1])
                refresh()
                updated = histo_current_ylim(state)
                print(f"Y range updated: {updated[0]:.6g} to {updated[1]:.6g}")
            continue
        if rng == "a":
            push_state()
            state.style.ylim = None
            refresh()
            auto = histo_auto_ylim(state)
            print(f"Y range restored to auto: {auto[0]:.6g} to {auto[1]:.6g}")
            continue
        parts = rng.split()
        if len(parts) != 2:
            print("Need exactly two numbers for Y range.")
            continue
        try:
            y_min, y_max = map(float, parts)
        except ValueError:
            print("Invalid Y range.")
            continue
        push_state()
        _set_ylim(state, y_min, y_max)
        refresh()
        updated = histo_current_ylim(state)
        print(f"Y range set to ({updated[0]:.6g}, {updated[1]:.6g})")


__all__ = ["run_histo_y_range_menu"]

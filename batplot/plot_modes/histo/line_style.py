"""Line/grid submenu (``l``) for histogram interactive mode."""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..common.spines import (
    apply_frame_and_tick_widths,
    current_tick_width,
    parse_frame_tick_widths,
)
from ..common.terminal import prompt_float as _common_prompt_float
from .plot import HistoState, apply_histo_grid


def capture_histo_line_style_from_ax(ax) -> dict[str, Any]:
    """Capture spine and tick widths from a live axes (for snapshots / batch sync)."""
    spine_linewidths: dict[str, float] = {}
    for name, sp in ax.spines.items():
        try:
            spine_linewidths[str(name)] = float(sp.get_linewidth())
        except Exception:
            pass
    tick_widths = {
        "x_major": current_tick_width(ax.xaxis, "major"),
        "x_minor": current_tick_width(ax.xaxis, "minor"),
        "y_major": current_tick_width(ax.yaxis, "major"),
        "y_minor": current_tick_width(ax.yaxis, "minor"),
    }
    return {
        "spine_linewidths": spine_linewidths,
        "tick_widths": tick_widths,
    }


def apply_histo_line_style_to_ax(ax, line_style: dict[str, Any] | None) -> None:
    """Restore spine/tick widths captured by ``capture_histo_line_style_from_ax``."""
    if not line_style:
        return
    spine_lw = line_style.get("spine_linewidths") or {}
    for name, lw in spine_lw.items():
        sp = ax.spines.get(name)
        if sp is None or lw is None:
            continue
        try:
            sp.set_linewidth(float(lw))
        except Exception:
            pass
    tw = line_style.get("tick_widths") or {}
    try:
        if tw.get("x_major") is not None:
            ax.tick_params(axis="x", which="major", width=float(tw["x_major"]))
        if tw.get("x_minor") is not None:
            ax.tick_params(axis="x", which="minor", width=float(tw["x_minor"]))
        if tw.get("y_major") is not None:
            ax.tick_params(axis="y", which="major", width=float(tw["y_major"]))
        if tw.get("y_minor") is not None:
            ax.tick_params(axis="y", which="minor", width=float(tw["y_minor"]))
    except Exception:
        pass


def sync_histo_line_style_from_reference(
    ref_ax,
    ref_state: HistoState,
    targets: list[tuple[Any, Any, HistoState]],
) -> None:
    """Copy grid + spine/tick widths from reference panel to batch targets."""
    captured = capture_histo_line_style_from_ax(ref_ax)
    for _fig, tax, tstate in targets:
        tstate.style.show_grid = bool(ref_state.style.show_grid)
        tstate.style.grid_linewidth = float(ref_state.style.grid_linewidth)
        apply_histo_line_style_to_ax(tax, captured)
        apply_histo_grid(tax, tstate)


def run_histo_line_style_menu(
    *,
    fig,
    ax,
    state: HistoState,
    push_state: Callable[[], None],
    refresh: Callable[[], None],
    safe_input: Callable[..., str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
    on_change: Callable[[], None] | None = None,
) -> None:
    """Run histo line submenu: spine/tick widths, grid toggle, grid width."""

    def _prompt_float(prompt_text: str) -> float | None:
        return _common_prompt_float(safe_input, prompt_text)

    def _after_change() -> None:
        if on_change is not None:
            on_change()
        else:
            refresh()

    def _grid_status() -> str:
        return "on" if state.style.show_grid else "off"

    try:
        while True:
            bottom_lw = ax.spines.get("bottom")
            frame_hint = f"{float(bottom_lw.get_linewidth()):g}" if bottom_lw else "?"
            print("\033[1mLine submenu:\033[0m")
            print(f"  {colorize_menu('f  : frame (spine) and tick widths')}")
            print(f"  {colorize_menu(f'g  : toggle grid lines (currently {_grid_status()})')}")
            print(
                f"  {colorize_menu(f'w  : grid line width (current {state.style.grid_linewidth:g})')}"
            )
            print(f"  {colorize_menu('q  : return')}")
            sub = safe_input(colorize_prompt("Choose (f/g/w/q): ")).strip().lower()
            if sub in ("q", ""):
                break
            if sub == "f":
                while True:
                    fw_in = safe_input(
                        "Enter frame/tick width (e.g., 1.5) or 'm M' (major minor) or q=back: "
                    ).strip()
                    if not fw_in or fw_in.lower() == "q":
                        break
                    push_state()
                    try:
                        frame_w, tick_major, tick_minor = parse_frame_tick_widths(fw_in)
                        apply_frame_and_tick_widths(
                            [ax],
                            frame_width=frame_w,
                            major_width=tick_major,
                            minor_width=tick_minor,
                        )
                        _after_change()
                        print(
                            f"Set frame width={frame_w}, major tick width={tick_major}, "
                            f"minor tick width={tick_minor}"
                        )
                    except ValueError:
                        print("Invalid numeric value(s).")
                continue
            if sub == "g":
                push_state()
                state.style.show_grid = not bool(state.style.show_grid)
                apply_histo_grid(ax, state)
                _after_change()
                print(f"Grid {'enabled' if state.style.show_grid else 'disabled'}.")
                continue
            if sub == "w":
                while True:
                    cur = float(state.style.grid_linewidth)
                    val = _prompt_float(
                        f"Grid line width [{cur:g}] (q=back): "
                    )
                    if val is None:
                        break
                    if val <= 0:
                        print("Grid line width must be positive.")
                        continue
                    push_state()
                    state.style.grid_linewidth = float(val)
                    if state.style.show_grid:
                        apply_histo_grid(ax, state)
                    _after_change()
                    print(f"Grid line width set to {val:g}.")
                continue
            print("Unknown submenu option.")
    except Exception as exc:
        print(f"Error in line submenu: {exc}")


__all__ = [
    "apply_histo_line_style_to_ax",
    "capture_histo_line_style_from_ax",
    "run_histo_line_style_menu",
    "sync_histo_line_style_from_reference",
]

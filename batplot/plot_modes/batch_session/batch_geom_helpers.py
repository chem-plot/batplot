"""Shared batch geometry helpers: plot frame and canvas sizing for fig+ax panels."""

from __future__ import annotations

import os
from typing import Any, Callable, Sequence, Tuple

from ..common.size_spec import parse_size_spec
from ..common.terminal import colorize_prompt, safe_input


def frame_inches(fig, ax) -> Tuple[float, float]:
    fw, fh = fig.get_size_inches()
    bb = ax.get_position()
    return float(bb.width * fw), float(bb.height * fh)


def set_frame_inches(fig, ax, w_in: float, h_in: float) -> None:
    """Set plot frame to absolute width/height in inches inside the current canvas."""
    fig_w, fig_h = fig.get_size_inches()
    w_frac = w_in / fig_w if fig_w > 0 else 0.5
    h_frac = h_in / fig_h if fig_h > 0 else 0.5
    left = (1 - w_frac) / 2
    bottom = (1 - h_frac) / 2
    ax.set_position([left, bottom, w_frac, h_frac])
    fig._last_user_axes_inches = (w_in, h_in)  # type: ignore[attr-defined]
    fig._last_user_margins = (left, bottom, w_frac, h_frac)  # type: ignore[attr-defined]


def set_canvas_inches_preserving_frame(fig, ax, canvas_w: float, canvas_h: float) -> None:
    """Resize canvas while keeping the plot frame size in inches (per panel)."""
    bb = ax.get_position()
    fw_old, fh_old = fig.get_size_inches()
    frame_w = bb.width * fw_old
    frame_h = bb.height * fh_old
    fig.set_size_inches(canvas_w, canvas_h, forward=True)
    w_frac = frame_w / canvas_w if canvas_w > 0 else bb.width
    h_frac = frame_h / canvas_h if canvas_h > 0 else bb.height
    min_margin = 0.05
    max_w_frac = 1 - 2 * min_margin
    max_h_frac = 1 - 2 * min_margin
    if w_frac > max_w_frac:
        w_frac = max_w_frac
    if h_frac > max_h_frac:
        h_frac = max_h_frac
    left = (1 - w_frac) / 2
    bottom = (1 - h_frac) / 2
    if w_frac > 0.05 and h_frac > 0.05:
        ax.set_position([left, bottom, w_frac, h_frac])
    fig._last_canvas_size = (canvas_w, canvas_h)  # type: ignore[attr-defined]


def _panel_ax(panel: Any):
    return getattr(panel, "ax", panel)


def _panel_fig(panel: Any):
    return getattr(panel, "fig", panel)


def _print_frame_status(panels: Sequence, *, item_name: str = "plot") -> None:
    frames = [frame_inches(_panel_fig(p), _panel_ax(p)) for p in panels]
    canvases = [_panel_fig(p).get_size_inches() for p in panels]
    same = (
        len({(round(w, 3), round(h, 3)) for w, h in frames}) == 1
        and len({(round(c[0], 3), round(c[1], 3)) for c in canvases}) == 1
    )
    if same and panels:
        cw, ch = canvases[0]
        fw, fh = frames[0]
        print(f"Current canvas (all plots): {cw:.2f} x {ch:.2f} in")
        print(f"Current plot frame (all plots): {fw:.2f} x {fh:.2f} in (W x H)")
        return
    print(f"Current {item_name} sizes (new values apply to ALL plots):")
    for i, panel in enumerate(panels, 1):
        cw, ch = _panel_fig(panel).get_size_inches()
        fw, fh = frame_inches(_panel_fig(panel), _panel_ax(panel))
        label = os.path.basename(getattr(panel, "path", "") or "") or f"plot {i}"
        print(f"  [{i}] canvas {cw:.2f}×{ch:.2f} in, frame {fw:.2f}×{fh:.2f} in  ({label})")


def _print_canvas_status(panels: Sequence) -> None:
    canvases = [_panel_fig(p).get_size_inches() for p in panels]
    frames = [frame_inches(_panel_fig(p), _panel_ax(p)) for p in panels]
    same = len({(round(c[0], 3), round(c[1], 3)) for c in canvases}) == 1
    if same and panels:
        cw, ch = canvases[0]
        fw, fh = frames[0]
        print(f"Current canvas (all plots): {cw:.2f} x {ch:.2f} in (frame {fw:.2f} x {fh:.2f} in)")
        return
    print("Current canvas sizes (new values apply to ALL plots):")
    for i, panel in enumerate(panels, 1):
        cw, ch = _panel_fig(panel).get_size_inches()
        fw, fh = frame_inches(_panel_fig(panel), _panel_ax(panel))
        label = os.path.basename(getattr(panel, "path", "") or "") or f"plot {i}"
        print(f"  [{i}] canvas {cw:.2f}×{ch:.2f} in (frame {fw:.2f}×{fh:.2f} in)  ({label})")


def apply_plot_frame_to_all(panels: Sequence, w_in: float, h_in: float) -> None:
    for panel in panels:
        set_frame_inches(_panel_fig(panel), _panel_ax(panel), w_in, h_in)


def apply_canvas_to_all(panels: Sequence, canvas_w: float, canvas_h: float) -> None:
    for panel in panels:
        set_canvas_inches_preserving_frame(
            _panel_fig(panel), _panel_ax(panel), canvas_w, canvas_h
        )


def run_batch_plot_frame_menu(
    panels: Sequence,
    *,
    push_undo: Callable[[], None],
    draw_all: Callable[[], None],
    on_applied: Callable[[], None] | None = None,
) -> None:
    """Prompt repeatedly; set the same absolute plot-frame inches on every panel."""
    ref = panels[0]
    while True:
        cur_w, cur_h = frame_inches(_panel_fig(ref), _panel_ax(ref))
        _print_frame_status(panels)
        try:
            spec = safe_input(
                colorize_prompt(
                    "Enter new plot frame size for ALL plots "
                    "(e.g. '6 4', '3x3', 'w=6 h=4', 'scale=1.2', single width, q=back): "
                ),
                cancel_on_interrupt=True,
            ).strip()
        except (KeyboardInterrupt, EOFError):
            print("Canceled.")
            return
        if not spec or spec.lower() == "q":
            return
        parsed = parse_size_spec(spec, cur_w, cur_h)
        if parsed is None:
            continue
        new_w, new_h = parsed
        push_undo()
        apply_plot_frame_to_all(panels, new_w, new_h)
        if on_applied:
            on_applied()
        draw_all()
        print(f"Plot frame set to {new_w:.2f} x {new_h:.2f} in on all {len(panels)} plots.")


def run_batch_canvas_menu(
    panels: Sequence,
    *,
    push_undo: Callable[[], None],
    draw_all: Callable[[], None],
    on_applied: Callable[[], None] | None = None,
) -> None:
    """Prompt repeatedly; set the same canvas size on every panel (frame inches preserved)."""
    ref = panels[0]
    while True:
        cur_w, cur_h = _panel_fig(ref).get_size_inches()
        _print_canvas_status(panels)
        try:
            spec = safe_input(
                colorize_prompt(
                    "Enter new canvas size for ALL plots "
                    "(e.g. '8 6', '6x4', 'w=6 h=5', 'scale=1.2', q=back): "
                ),
                cancel_on_interrupt=True,
            ).strip()
        except (KeyboardInterrupt, EOFError):
            print("Canceled.")
            return
        if not spec or spec.lower() == "q":
            return
        parsed = parse_size_spec(spec, cur_w, cur_h)
        if parsed is None:
            continue
        new_w, new_h = max(1.0, parsed[0]), max(1.0, parsed[1])
        push_undo()
        apply_canvas_to_all(panels, new_w, new_h)
        if on_applied:
            on_applied()
        draw_all()
        print(f"Canvas set to {new_w:.2f} x {new_h:.2f} in on all {len(panels)} plots.")


def run_batch_geom_size_menu(
    panels: Sequence,
    *,
    push_undo: Callable[[], None],
    draw_all: Callable[[], None],
    colorize_menu: Callable[[str], str],
    on_applied: Callable[[], None] | None = None,
) -> None:
    """``g: size`` submenu: plot frame (p) and canvas (c), matching normal EC/XY/CPC mode."""
    while True:
        print("  " + colorize_menu("p: plot frame size"))
        print("  " + colorize_menu("c: canvas size"))
        print("  " + colorize_menu("q: back"))
        choice = safe_input(colorize_prompt("Size (p/c/q): ")).strip().lower()
        if not choice or choice == "q":
            break
        if choice == "p":
            run_batch_plot_frame_menu(
                panels,
                push_undo=push_undo,
                draw_all=draw_all,
                on_applied=on_applied,
            )
            continue
        if choice == "c":
            run_batch_canvas_menu(
                panels,
                push_undo=push_undo,
                draw_all=draw_all,
                on_applied=on_applied,
            )
            continue
        print("Unknown option.")


__all__ = [
    "apply_canvas_to_all",
    "apply_plot_frame_to_all",
    "frame_inches",
    "run_batch_canvas_menu",
    "run_batch_geom_size_menu",
    "run_batch_plot_frame_menu",
    "set_canvas_inches_preserving_frame",
    "set_frame_inches",
]

"""Histogram batch session helpers (sync geometry/styles across panels)."""

from __future__ import annotations

from typing import Callable, List, Sequence, Tuple

from ..common.terminal import colorize_prompt, safe_input
from ..histo.plot import HistoState, sync_histo_geometry
from .batch_menu_helpers import summarize_values
from .load import HistoPanel


def summarize_figsize(panels: Sequence[HistoPanel]) -> str:
    pairs = [p.state.style.figsize for p in panels]
    labels = [f"{float(a):g}×{float(b):g}" for a, b in pairs]
    return summarize_values(labels, fmt="{}")


def frame_inches(fig, ax) -> Tuple[float, float]:
    fw, fh = fig.get_size_inches()
    bb = ax.get_position()
    return float(bb.width * fw), float(bb.height * fh)


def summarize_frame_inches(panels: Sequence[HistoPanel]) -> str:
    labels = [f"{w:g}×{h:g}" for w, h in (frame_inches(p.fig, p.ax) for p in panels)]
    return summarize_values(labels, fmt="{}")


from ..common.size_spec import parse_size_spec
def set_frame_inches(fig, ax, w_in: float, h_in: float) -> None:
    """Set plot frame to absolute width/height in inches inside the current canvas."""
    fig_w, fig_h = fig.get_size_inches()
    w_frac = w_in / fig_w
    h_frac = h_in / fig_h
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
    w_frac = frame_w / canvas_w
    h_frac = frame_h / canvas_h
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


def apply_plot_frame_to_all(panels: Sequence[HistoPanel], w_in: float, h_in: float) -> None:
    for panel in panels:
        set_frame_inches(panel.fig, panel.ax, w_in, h_in)
        sync_histo_geometry(panel.fig, panel.ax, panel.state)


def apply_canvas_to_all(panels: Sequence[HistoPanel], canvas_w: float, canvas_h: float) -> None:
    for panel in panels:
        set_canvas_inches_preserving_frame(panel.fig, panel.ax, canvas_w, canvas_h)
        sync_histo_geometry(panel.fig, panel.ax, panel.state)


def _print_frame_status(panels: Sequence[HistoPanel]) -> None:
    frames = [frame_inches(p.fig, p.ax) for p in panels]
    canvases = [p.fig.get_size_inches() for p in panels]
    same = len({(round(w, 3), round(h, 3)) for w, h in frames}) == 1 and len(
        {(round(c[0], 3), round(c[1], 3)) for c in canvases}
    ) == 1
    if same and panels:
        p = panels[0]
        cw, ch = p.fig.get_size_inches()
        fw, fh = frame_inches(p.fig, p.ax)
        print(f"Current canvas: {cw:.2f} x {ch:.2f} in")
        print(f"Current plot frame: {fw:.2f} x {fh:.2f} in (W x H)")
        return
    print("Current sizes (new values apply to ALL plots):")
    for i, panel in enumerate(panels, 1):
        cw, ch = panel.fig.get_size_inches()
        fw, fh = frame_inches(panel.fig, panel.ax)
        print(f"  [{i}] canvas {cw:.2f}×{ch:.2f} in, frame {fw:.2f}×{fh:.2f} in")


def _print_canvas_status(panels: Sequence[HistoPanel]) -> None:
    canvases = [p.fig.get_size_inches() for p in panels]
    same = len({(round(c[0], 3), round(c[1], 3)) for c in canvases}) == 1
    if same and panels:
        cw, ch = panels[0].fig.get_size_inches()
        fw, fh = frame_inches(panels[0].fig, panels[0].ax)
        print(f"Current canvas size: {cw:.2f} x {ch:.2f} in (frame {fw:.2f} x {fh:.2f} in)")
        return
    print("Current canvas sizes (new values apply to ALL plots):")
    for i, panel in enumerate(panels, 1):
        cw, ch = panel.fig.get_size_inches()
        fw, fh = frame_inches(panel.fig, panel.ax)
        print(f"  [{i}] canvas {cw:.2f}×{ch:.2f} in (frame {fw:.2f}×{fh:.2f} in)")


def run_batch_plot_frame_menu(
    panels: List[HistoPanel],
    *,
    push_all: Callable[[], None],
    draw_all: Callable[[], None],
) -> None:
    """Prompt repeatedly; set the same absolute plot-frame inches on every panel."""
    while True:
        ref = panels[0]
        cur_w, cur_h = frame_inches(ref.fig, ref.ax)
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
        push_all()
        apply_plot_frame_to_all(panels, new_w, new_h)
        draw_all()
        print(f"Plot frame set to {new_w:.2f} x {new_h:.2f} in on all {len(panels)} plots.")


def run_batch_canvas_menu(
    panels: List[HistoPanel],
    *,
    push_all: Callable[[], None],
    draw_all: Callable[[], None],
) -> None:
    """Prompt repeatedly; set the same canvas size on every panel (frame inches preserved)."""
    while True:
        ref = panels[0]
        cur_w, cur_h = ref.fig.get_size_inches()
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
        new_w, new_h = parsed
        min_size = 1.0
        new_w = max(min_size, new_w)
        new_h = max(min_size, new_h)
        push_all()
        apply_canvas_to_all(panels, new_w, new_h)
        draw_all()
        print(f"Canvas set to {new_w:.2f} x {new_h:.2f} in on all {len(panels)} plots.")


def run_batch_histo_geom_menu(
    panels: List[HistoPanel],
    *,
    push_all: Callable[[], None],
    draw_all: Callable[[], None],
    colorize_menu: Callable[[str], str],
) -> None:
    """Geometry submenu: plot frame, canvas, or direct size entry at the top prompt."""
    while True:
        for key, desc in (("p", "plot frame"), ("c", "canvas")):
            print("  " + colorize_menu(f"{key}: {desc}"))
        print("  " + colorize_menu("q: back"))
        choice = safe_input(colorize_prompt("Geom (p/c/q): ")).strip().lower()
        if not choice or choice == "q":
            break
        if choice == "p":
            run_batch_plot_frame_menu(panels, push_all=push_all, draw_all=draw_all)
            continue
        if choice == "c":
            run_batch_canvas_menu(panels, push_all=push_all, draw_all=draw_all)
            continue
        ref = panels[0]
        cur_w, cur_h = frame_inches(ref.fig, ref.ax)
        parsed = parse_size_spec(choice, cur_w, cur_h)
        if parsed is None:
            print("Unknown option.")
            continue
        new_w, new_h = parsed
        push_all()
        apply_plot_frame_to_all(panels, new_w, new_h)
        draw_all()
        print(f"Plot frame set to {new_w:.2f} x {new_h:.2f} in on all {len(panels)} plots.")


__all__ = [
    "apply_canvas_to_all",
    "apply_plot_frame_to_all",
    "frame_inches",
    "parse_size_spec",
    "run_batch_canvas_menu",
    "run_batch_histo_geom_menu",
    "run_batch_plot_frame_menu",
    "summarize_figsize",
    "summarize_frame_inches",
]

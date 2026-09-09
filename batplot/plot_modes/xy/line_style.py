"""Line-style submenu (``l``) for the XY interactive menu.

Handles curve line widths, frame/tick widths, grid toggling, and line/marker/
dash style presets for selected curves. Mutating actions go through the
injected ``push_state`` so undo keeps working exactly as before. Shared frame/
tick-width logic is reused from ``common.spines`` so a fix there applies to all
modes.
"""

from __future__ import annotations

import re
from typing import Any, Callable, List, Optional, Sequence

from ...plotting import apply_curve_color
from ..common.line_dash import clear_dash_pattern, prompt_dash_pattern, set_dash_pattern
from ..common.session_helpers import _artist_linewidth
from ..common.spines import apply_frame_and_tick_widths, parse_frame_tick_widths
from ..common.terminal import prompt_float as _common_prompt_float


def run_line_style_menu(
    *,
    ax: Any,
    fig: Any,
    lines_by_curve: Optional[Sequence[Any]],
    line_getter: Callable[[int], Any],
    line_count: Callable[[], int],
    push_state: Callable[[str], Any],
    safe_input: Callable[[str], str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
) -> None:
    """Run the line/marker/width/grid submenu."""
    try:
        def _select_lines(_ax_obj, prompt_text):
            # Use line_count()/line_getter — ax.lines misses --ry twin curves.
            total = int(line_count())
            if total == 0:
                print("No curves to modify.")
                return []
            print(f"Total curves available: {total}")
            raw = safe_input(prompt_text + " ").strip().lower()
            if not raw or raw in ('all', '*'):
                return list(range(total))
            tokens = [tok for tok in re.split(r'[,\s]+', raw) if tok]
            selected = []
            for tok in tokens:
                try:
                    idx = int(tok) - 1
                    if 0 <= idx < total:
                        if idx not in selected:
                            selected.append(idx)
                    else:
                        print(f"Index out of range: {tok}")
                except ValueError:
                    print(f"Skipping invalid token: {tok}")
            return selected

        def _frame_axes():
            axes = [ax]
            twin = getattr(fig, "_xy_ax2", None)
            if twin is not None and twin is not ax:
                axes.append(twin)
            return axes

        def _prompt_float(prompt_text):
            return _common_prompt_float(safe_input, prompt_text)

        def _prompt_dash_pattern(kind='dash'):
            return prompt_dash_pattern(safe_input, kind=kind)

        while True:
            print("\033[1mLine submenu:\033[0m")
            print(f"  {colorize_menu('c  : change curve line widths')}")
            print(f"  {colorize_menu('f  : change frame (axes spines) and tick widths')}")
            print(f"  {colorize_menu('g  : toggle grid lines')}")
            print(f"  {colorize_menu('l  : show only lines (no markers) for selected curves')}")
            print(f"  {colorize_menu('ld : show line and dots for selected curves')}")
            print(f"  {colorize_menu('d  : show only dots for selected curves')}")
            print(f"  {colorize_menu('da : dashed line for selected curves')}")
            print(f"  {colorize_menu('dd : dashed line + dots for selected curves')}")
            print(f"  {colorize_menu('q  : return')}")
            sub = safe_input(colorize_prompt("Choose (c/f/g/l/ld/d/da/dd/q): ")).strip().lower()
            if sub == 'q':
                break
            if sub == '':
                continue
            if sub == 'c':
                while True:
                    spec = safe_input("Curve widths (single value OR mappings like '1:1.2 3:2', q=back): ").strip()
                    if not spec or spec.lower() == 'q':
                        break
                    if ":" in spec:
                        parsed = []
                        parts = spec.split()
                        for p in parts:
                            if ":" not in p:
                                print(f"Skip malformed token: {p}")
                                continue
                            idx_str, lw_str = p.split(":", 1)
                            try:
                                idx = int(idx_str) - 1
                                lw = float(lw_str)
                                if 0 <= idx < line_count():
                                    parsed.append((idx, lw))
                                else:
                                    print(f"Index out of range: {idx+1}")
                            except ValueError:
                                print(f"Bad token: {p}")
                        if not parsed:
                            continue
                        push_state("linewidth")
                        for idx, lw in parsed:
                            line_getter(idx).set_linewidth(lw)
                    else:
                        try:
                            lw = float(spec)
                        except ValueError:
                            print("Invalid width value.")
                            continue
                        push_state("linewidth")
                        if lines_by_curve:
                            for ln in lines_by_curve:
                                ln.set_linewidth(lw)
                        else:
                            for i in range(line_count()):
                                line_getter(i).set_linewidth(lw)
                    fig.canvas.draw()
            elif sub == 'f':
                while True:
                    fw_in = safe_input("Enter frame/tick width (e.g., 1.5) or 'm M' (major minor) or q=back: ").strip()
                    if not fw_in or fw_in.lower() == 'q':
                        break
                    try:
                        frame_w, tick_major, tick_minor = parse_frame_tick_widths(fw_in)
                    except ValueError:
                        print("Invalid numeric value(s).")
                        continue
                    push_state("framewidth")
                    apply_frame_and_tick_widths(
                        _frame_axes(),
                        frame_width=frame_w,
                        major_width=tick_major,
                        minor_width=tick_minor,
                    )
                    fig.canvas.draw()
                    print(f"Set frame width={frame_w}, major tick width={tick_major}, minor tick width={tick_minor}")
            elif sub == 'g':
                push_state("grid")
                # Toggle grid state - check if any gridlines are visible
                current_grid = False
                try:
                    # Check if grid is currently on by looking at gridline visibility
                    for line in ax.get_xgridlines() + ax.get_ygridlines():
                        if line.get_visible():
                            current_grid = True
                            break
                except Exception:
                    current_grid = ax.xaxis._gridOnMajor if hasattr(ax.xaxis, '_gridOnMajor') else False

                new_grid_state = not current_grid
                if new_grid_state:
                    # Enable grid with light styling
                    ax.grid(True, color='0.85', linestyle='-', linewidth=0.5, alpha=0.7)
                else:
                    # Disable grid (no style parameters when disabling)
                    ax.grid(False)
                fig.canvas.draw()
                print(f"Grid {'enabled' if new_grid_state else 'disabled'}.")
            elif sub == 'l':
                targets = _select_lines(ax, "line-only targets (numbers or 'all'):")
                if not targets:
                    continue
                push_state("line-only")
                for idx in targets:
                    ln = line_getter(idx)
                    ln.set_linestyle('-')
                    clear_dash_pattern(ln)
                    ln.set_marker('None')
                fig.canvas.draw()
                print(f"Applied line-only style to curves: {', '.join(str(i+1) for i in targets)}")
            elif sub == 'ld':
                targets = _select_lines(ax, "line+dots targets (numbers or 'all'):")
                if not targets:
                    continue
                while True:
                    raw = safe_input("Marker size (blank=auto ~3*lw, q=back): ").strip().lower()
                    if raw == 'q':
                        break
                    custom_msize = None
                    if raw:
                        try:
                            custom_msize = float(raw)
                        except ValueError:
                            print("Invalid marker size.")
                            continue
                    push_state("line+dots")
                    for idx in targets:
                        ln = line_getter(idx)
                        lw = _artist_linewidth(ln)
                        ln.set_linestyle('-')
                        clear_dash_pattern(ln)
                        ln.set_marker('o')
                        msize = custom_msize if custom_msize is not None else max(3.0, lw * 3.0)
                        ln.set_markersize(msize)
                        apply_curve_color(ln, ln.get_color())
                    fig.canvas.draw()
                    print(f"Applied line+dots style to curves: {', '.join(str(i+1) for i in targets)}")
                    break
            elif sub == 'd':
                targets = _select_lines(ax, "dots-only targets (numbers or 'all'):")
                if not targets:
                    continue
                while True:
                    raw = safe_input("Marker size (blank=auto ~3*lw, q=back): ").strip().lower()
                    if raw == 'q':
                        break
                    custom_msize = None
                    if raw:
                        try:
                            custom_msize = float(raw)
                        except ValueError:
                            print("Invalid marker size.")
                            continue
                    push_state("dots-only")
                    for idx in targets:
                        ln = line_getter(idx)
                        lw = _artist_linewidth(ln)
                        ln.set_linestyle('None')
                        clear_dash_pattern(ln)
                        ln.set_marker('o')
                        msize = custom_msize if custom_msize is not None else max(3.0, lw * 3.0)
                        ln.set_markersize(msize)
                        apply_curve_color(ln, ln.get_color())
                    fig.canvas.draw()
                    print(f"Applied dots-only style to curves: {', '.join(str(i+1) for i in targets)}")
                    break
            elif sub == 'da':
                targets = _select_lines(ax, "dashed-line targets (numbers or 'all'):")
                if not targets:
                    continue
                while True:
                    dash_vals = _prompt_dash_pattern()
                    if dash_vals is None:
                        break
                    dash_len, gap_len = dash_vals[0], dash_vals[1]
                    push_state("dashed-line")
                    for idx in targets:
                        ln = line_getter(idx)
                        ln.set_marker('None')
                        set_dash_pattern(ln, (dash_len, gap_len))
                    fig.canvas.draw()
                    print(f"Applied dashed lines to curves: {', '.join(str(i+1) for i in targets)}")
                    break
            elif sub == 'dd':
                targets = _select_lines(ax, "dash-dot targets (numbers or 'all'):")
                if not targets:
                    continue
                while True:
                    dash_vals = _prompt_dash_pattern(kind='dashdot')
                    if dash_vals is None:
                        break
                    push_state("dash-dot")
                    for idx in targets:
                        ln = line_getter(idx)
                        ln.set_marker('None')
                        set_dash_pattern(ln, dash_vals)
                    fig.canvas.draw()
                    print(f"Applied dash-dot style to curves: {', '.join(str(i+1) for i in targets)}")
                    break
            else:
                print("Unknown submenu option.")
    except Exception as e:
        print(f"Error setting widths: {e}")


__all__ = ["run_line_style_menu"]

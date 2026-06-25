"""Curve rearrange submenu (``a``) for the XY interactive menu.

Reorders all parallel per-curve lists in place (so undo/save see the change)
and restacks offsets. The dispatcher injects the lists, ``delta``, and the
line-access helpers; mutations go through ``push_state``.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence

from ...plotting import update_labels


def run_rearrange_menu(
    *,
    args: Any,
    ax: Any,
    fig: Any,
    labels: List[str],
    label_text_objects: List[Any],
    x_data_list: List[Any],
    y_data_list: List[Any],
    orig_y: List[Any],
    offsets_list: List[float],
    x_full_list: List[Any],
    raw_y_full_list: List[Any],
    delta: float,
    push_state: Callable[[str], Any],
    _safe_input: Callable[[str], str],
    _line: Callable[[int], Any],
    _lines_by_curve: Optional[Sequence[Any]],
) -> None:
        try:
            if not args.stack:
                print('Be careful, changing the arrangement may lead to a mess! If you want to rearrange the curves, use "--stack".')
            while True:
                print("Current curve order:")
                for idx, label in enumerate(labels):
                    print(f"{idx+1}: {label}")
                new_order_str = _safe_input("Enter new order (space-separated indices, q=back): ").strip()
                if not new_order_str or new_order_str.lower() == 'q':
                    break
                try:
                    new_order = [int(i)-1 for i in new_order_str.strip().split()]
                except (ValueError, TypeError):
                    print("Invalid input. Use space-separated numbers (e.g., 3 1 2 4).")
                    continue
                if len(new_order) != len(labels):
                    print("Error: Number of indices does not match number of curves.")
                    continue
                if any(i < 0 or i >= len(labels) for i in new_order):
                    print("Error: Invalid index in order list.")
                    continue
    
                push_state("rearrange")
    
                original_styles = []
                for ln in (_lines_by_curve if _lines_by_curve else ax.lines):
                    original_styles.append({
                        "color": ln.get_color(),
                        "linewidth": ln.get_linewidth(),
                        "linestyle": ln.get_linestyle(),
                        "alpha": ln.get_alpha(),
                        "marker": ln.get_marker(),
                        "markersize": ln.get_markersize(),
                        "markerfacecolor": ln.get_markerfacecolor(),
                        "markeredgecolor": ln.get_markeredgecolor()
                    })
                reordered_styles = [original_styles[i] for i in new_order]
                xlim_current = ax.get_xlim()
    
                x_data_list[:]      = [x_data_list[i] for i in new_order]
                orig_y[:]           = [orig_y[i] for i in new_order]
                y_data_list[:]      = [y_data_list[i] for i in new_order]
                labels[:]           = [labels[i] for i in new_order]
                label_text_objects[:] = [label_text_objects[i] for i in new_order]
                x_full_list[:]      = [x_full_list[i] for i in new_order]
                raw_y_full_list[:]  = [raw_y_full_list[i] for i in new_order]
                offsets_list[:]     = [offsets_list[i] for i in new_order]
    
                if args.stack:
                    offset_local = 0.0
                    for i, (x_plot, y_norm, style) in enumerate(zip(x_data_list, orig_y, reordered_styles)):
                        y_plot_offset = y_norm + offset_local
                        y_data_list[i] = y_plot_offset
                        offsets_list[i] = offset_local
                        ln = _line(i)
                        ln.set_data(x_plot, y_plot_offset)
                        ln.set_color(style["color"]) 
                        ln.set_linewidth(style["linewidth"]) 
                        ln.set_linestyle(style["linestyle"]) 
                        ln.set_alpha(style["alpha"]) 
                        ln.set_marker(style["marker"]) 
                        ln.set_markersize(style["markersize"]) 
                        ln.set_markerfacecolor(style["markerfacecolor"]) 
                        ln.set_markeredgecolor(style["markeredgecolor"]) 
                        y_range = (y_norm.max() - y_norm.min()) if y_norm.size else 0.0
                        gap = y_range + (delta * (y_range if args.autoscale else 1.0))
                        offset_local -= gap
                else:
                    offset_local = 0.0
                    for i, (x_plot, y_norm, style) in enumerate(zip(x_data_list, orig_y, reordered_styles)):
                        y_plot_offset = y_norm + offset_local
                        y_data_list[i] = y_plot_offset
                        offsets_list[i] = offset_local
                        ln = _line(i)
                        ln.set_data(x_plot, y_plot_offset)
                        ln.set_color(style["color"]) 
                        ln.set_linewidth(style["linewidth"]) 
                        ln.set_linestyle(style["linestyle"]) 
                        ln.set_alpha(style["alpha"]) 
                        ln.set_marker(style["marker"]) 
                        ln.set_markersize(style["markersize"]) 
                        ln.set_markerfacecolor(style["markerfacecolor"]) 
                        ln.set_markeredgecolor(style["markeredgecolor"]) 
                        increment = (y_norm.max() - y_norm.min()) * delta if (args.autoscale and y_norm.size) else delta
                        offset_local += increment
    
                for i, (txt, lab) in enumerate(zip(label_text_objects, labels)):
                    txt.set_text(f"{i+1}: {lab}")
                # Preserve current axis titles (respect 't' menu toggles like bt/lt)
                ax.set_xlim(xlim_current)
                # Do not reset xlabel/ylabel here; rearrange should not change title visibility
                update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                fig.canvas.draw()
        except Exception as e:
            print(f"Error rearranging curves: {e}")


__all__ = ["run_rearrange_menu"]

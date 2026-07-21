"""Derivative submenu (``d``) for the XY interactive menu.

Computes 1st/2nd (optionally reversed) derivatives of the curves and updates the
y-axis label, with reset support. Numeric kernels come from ``data_ops``; the
data-lifecycle callbacks and label updater are injected by the dispatcher so
undo and processed-data tracking are unchanged.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional

from ...plotting import update_labels
from .data_ops import _calculate_derivative, _calculate_reversed_derivative



def update_ylabel_for_derivative(
    order: int,
    current_label: Optional[str] = None,
    *,
    is_reversed: bool = False,
    x_label: Optional[str] = None,
    fallback_ylabel: str = "Y",
) -> str:
    """Generate an appropriate y-axis label for a derivative plot.

    Extracted from the interactive menu so style import (``i``) can update the
    ylabel without importing nested menu closures.
    """
    if current_label is None:
        current_label = fallback_ylabel or "Y"

    current_lower = current_label.lower()

    if is_reversed:
        y_label = (
            current_label
            if current_label and current_label != "Y"
            else (fallback_ylabel or "Y")
        )
        if order == 1:
            if x_label:
                return f"d({x_label})/d({y_label})"
            return f"dx/d({y_label})"
        if x_label:
            return f"d²({x_label})/d({y_label})²"
        return f"d²x/d({y_label})²"

    if order == 1:
        if "/" in current_label:
            if "d²" in current_label or "d2" in current_lower:
                return current_label.replace("d²", "d").replace("d2", "d")
            if "d" in current_label.lower() and "/" in current_label:
                return current_label
        if x_label:
            return f"d({current_label})/d({x_label})"
        return f"d({current_label})/dx"

    # order == 2
    if "/" in current_label:
        if "d²" in current_label or "d2" in current_lower:
            return current_label
        if "d" in current_label.lower() and "/" in current_label:
            return (
                current_label.replace("d(", "d²(")
                .replace("d2(", "d²(")
                .replace("d/", "d²/")
                .replace("/d(", "²/d(")
            )
    if x_label:
        return f"d²({current_label})/d({x_label})²"
    return f"d²({current_label})/dx²"


def run_derivative_menu(
    *,
    args: Any,
    ax: Any,
    fig: Any,
    label_text_objects: List[Any],
    x_data_list: List[Any],
    y_data_list: List[Any],
    offsets_list: List[float],
    push_state: Callable[[str], Any],
    _safe_input: Callable[[str], str],
    _apply_data_changes: Callable[[], Any],
    _ensure_pre_derivative_data: Callable[[], Any],
    _reset_from_derivative: Callable[[], Any],
    _update_full_processed_data: Callable[[], Any],
    _update_ylabel_for_derivative: Callable[..., Any],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
) -> None:
        while True:
            try:
                print("\n\033[1mDerivative Menu\033[0m")
                print("Commands:")
                print("  " + colorize_menu("1: Calculate 1st derivative (dy/dx)"))
                print("  " + colorize_menu("2: Calculate 2nd derivative (d²y/dx²)"))
                print("  " + colorize_menu("3: Calculate reversed 1st derivative (dx/dy)"))
                print("  " + colorize_menu("4: Calculate reversed 2nd derivative (d²x/dy²)"))
                print("  " + colorize_menu("reset: Reset to data before derivative"))
                print("  " + colorize_menu("q: back to main menu"))
                sub = _safe_input(colorize_prompt("d> ")).strip().lower()
                if not sub or sub == 'q':
                    break
                if sub == 'reset':
                    push_state("derivative-reset")
                    success, reset_count, total_points = _reset_from_derivative()
                    if success:
                        print(f"Reset {reset_count} curve(s) from derivative to original data ({total_points} total points restored).")
                        ax.relim()
                        ax.autoscale_view(scalex=False, scaley=True)
                        update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                        _apply_data_changes()
                    else:
                        print("No derivative data to reset.")
                    continue
                if sub in ('1', '2', '3', '4'):
                    try:
                        option = int(sub)
                        is_reversed = (option == 3 or option == 4)
                        order = 1 if option in (1, 3) else 2
                        push_state(f"derivative-{option}")
                        _ensure_pre_derivative_data()
                        processed = 0
                        total_points = 0
                        for i in range(len(x_data_list)):
                            try:
                                # Use current data (may already be processed)
                                current_x = x_data_list[i].copy()
                                current_y = y_data_list[i].copy()
                                # Remove offset for processing
                                if i < len(offsets_list):
                                    current_y_no_offset = current_y - offsets_list[i]
                                else:
                                    current_y_no_offset = current_y.copy()
                                n_points = len(current_y_no_offset)
                                if n_points < 2:
                                    print(f"Curve {i+1} has too few points (<2) for derivative calculation.")
                                    continue
                                # Calculate derivative
                                if is_reversed:
                                    derivative_y = _calculate_reversed_derivative(current_x, current_y_no_offset, order)
                                else:
                                    derivative_y = _calculate_derivative(current_x, current_y_no_offset, order)
                                if len(derivative_y) > 0:
                                    # Restore offset
                                    if i < len(offsets_list):
                                        derivative_y = derivative_y + offsets_list[i]
                                    # Update data (keep same x, replace y with derivative)
                                    x_data_list[i] = current_x.copy()
                                    y_data_list[i] = derivative_y
                                    processed += 1
                                    total_points += n_points
                            except Exception as e:
                                print(f"Error processing curve {i+1}: {e}")
                        if processed > 0:
                            # Update y-axis label
                            current_ylabel = ax.get_ylabel() or ""
                            new_ylabel = _update_ylabel_for_derivative(order, current_ylabel, is_reversed=is_reversed)
                            ax.set_ylabel(new_ylabel)
                            # Store derivative order and reversed flag
                            fig._derivative_order = order
                            fig._derivative_reversed = is_reversed
                            # Update plot
                            _apply_data_changes()
                            ax.relim()
                            ax.autoscale_view(scalex=False, scaley=True)
                            update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                            fig.canvas.draw_idle()
                            order_name = "1st" if order == 1 else "2nd"
                            direction = "reversed " if is_reversed else ""
                            print(f"Applied {direction}{order_name} derivative to {processed} curve(s) with {total_points} total points.")
                            print(f"Y-axis label updated to: {new_ylabel}")
                            _update_full_processed_data()  # Store full processed data for X-range filtering
                        else:
                            print("No curves were processed.")
                    except ValueError:
                        print("Invalid input.")
                    continue
            except Exception as e:
                print(f"Error in derivative menu: {e}")


__all__ = ["run_derivative_menu", "update_ylabel_for_derivative"]

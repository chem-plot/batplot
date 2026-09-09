"""Curve offset adjustment submenu for the XY interactive menu.

Extracted verbatim from interactive.py (the former inline ``o`` key handler);
the dispatcher keeps a thin call that rebinds ``delta`` from the return value,
so prompts, messages, and undo semantics are unchanged.
"""
from __future__ import annotations

import numpy as np  # type: ignore[import]

from ...plotting import update_labels


def run_offset_menu(
    *,
    ax,
    fig,
    args,
    labels,
    orig_y,
    x_data_list,
    y_data_list,
    offsets_list,
    delta,
    line,
    nlines,
    push_state,
    safe_input,
    colorize_menu,
    label_text_objects=None,
):
    """Offset adjustment menu (1-N/a/r/d/q). Returns the (possibly new) delta."""
    if label_text_objects is None:
        label_text_objects = []
    print("\n\033[1mOffset adjustment menu:\033[0m")
    print(f"  {colorize_menu('1-{}: adjust individual curve offset'.format(len(labels)))}")
    print(f"  {colorize_menu('a: set spacing between curves')}")
    print(f"  {colorize_menu('r: reset all offsets to 0')}")
    print(f"  {colorize_menu('d: change delta spacing (original behavior)')}")
    print(f"  {colorize_menu('q: back to main menu')}")

    while True:
        offset_cmd = safe_input("Offset> ").strip().lower()

        if offset_cmd == 'q' or offset_cmd == '':
            break

        elif offset_cmd == 'r':
            # Reset all offsets to 0
            try:
                push_state("reset-offsets")
                for i in range(len(labels)):
                    if i >= nlines():
                        continue
                    # Get current x-data from the line
                    current_x = np.asarray(line(i).get_xdata(), dtype=float)
                    # Reset to normalized data without any offset
                    y_norm = orig_y[i]
                    y_data_list[i] = y_norm.copy()
                    offsets_list[i] = 0.0
                    # Update x_data_list to match current line data
                    x_data_list[i] = current_x.copy()
                    line(i).set_data(current_x, y_norm)

                ax.relim()
                ax.autoscale_view(scalex=False, scaley=True)
                from .axis_range import _autoscale_xy_right_y
                _autoscale_xy_right_y(fig)
                update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                fig.canvas.draw()
                print("All offsets reset to 0")
            except Exception as e:
                print(f"Error resetting offsets: {e}")

        elif offset_cmd == 'a':
            # Set spacing between curves (separates all curves)
            try:
                if len(labels) <= 1:
                    print("Warning: Only one curve loaded; spacing cannot be applied.")
                    continue

                # Calculate current spacing (average difference between consecutive offsets)
                current_spacing = 0.0
                if len(offsets_list) > 1:
                    spacing_diffs = []
                    sorted_indices = sorted(range(len(offsets_list)), key=lambda i: offsets_list[i] if i < len(offsets_list) else 0.0)
                    for j in range(len(sorted_indices) - 1):
                        idx1, idx2 = sorted_indices[j], sorted_indices[j + 1]
                        off1 = offsets_list[idx1] if idx1 < len(offsets_list) else 0.0
                        off2 = offsets_list[idx2] if idx2 < len(offsets_list) else 0.0
                        spacing_diffs.append(abs(off2 - off1))
                    if spacing_diffs:
                        current_spacing = sum(spacing_diffs) / len(spacing_diffs)

                spacing_input = safe_input("Enter spacing value between curves (current avg: {:.4g}): ".format(current_spacing)).strip()
                if not spacing_input:
                    print("Canceled.")
                    continue

                spacing_value = float(spacing_input)
                push_state("curve-spacing")

                # Apply spacing to separate all curves
                # Find the minimum current offset to use as baseline
                min_offset = min(offsets_list) if offsets_list else 0.0

                # Sort curves by their current offset to maintain order
                curve_order = sorted(range(len(labels)), key=lambda i: offsets_list[i] if i < len(offsets_list) else 0.0)

                # Apply cumulative spacing starting from the minimum offset
                current_offset = min_offset
                for i, curve_idx in enumerate(curve_order):
                    if curve_idx >= nlines():
                        continue
                    # Get current x-data from the line
                    current_x = np.asarray(line(curve_idx).get_xdata(), dtype=float)
                    y_norm = orig_y[curve_idx]

                    # Set new offset with spacing
                    offsets_list[curve_idx] = current_offset
                    y_with_offset = y_norm + current_offset
                    y_data_list[curve_idx] = y_with_offset
                    x_data_list[curve_idx] = current_x.copy()
                    line(curve_idx).set_data(current_x, y_with_offset)

                    # Calculate spacing for next curve based on current curve's range
                    if i < len(curve_order) - 1:  # Not the last curve
                        y_range = (y_norm.max() - y_norm.min()) if y_norm.size else 0.0
                        if args.stack:
                            # In stack mode, spacing is relative to curve range
                            gap = y_range + (spacing_value * (y_range if args.autoscale else 1.0))
                            current_offset -= gap
                        else:
                            # In normal mode, spacing is absolute or relative
                            increment = (y_range * spacing_value) if (args.autoscale and y_norm.size) else spacing_value
                            current_offset += increment

                ax.relim()
                ax.autoscale_view(scalex=False, scaley=True)
                from .axis_range import _autoscale_xy_right_y
                _autoscale_xy_right_y(fig)
                update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                fig.canvas.draw()
                print("Spacing of {:.4g} applied to separate all curves".format(spacing_value))

            except ValueError:
                print("Invalid spacing value")
            except Exception as e:
                print(f"Error applying spacing: {e}")

        elif offset_cmd == 'd':
            # Original delta spacing behavior
            if len(labels) <= 1:
                print("Warning: Only one curve loaded; applying an offset is not recommended.")
            try:
                new_delta_str = safe_input(f"Enter new offset spacing (current={delta}): ").strip()
                if not new_delta_str:
                    print("Canceled.")
                    continue
                new_delta = float(new_delta_str)
                push_state("delta-spacing")
                delta = new_delta
                offsets_list[:] = []
                if args.stack:
                    current_offset = 0.0
                    for i, y_norm in enumerate(orig_y):
                        if i >= nlines():
                            continue
                        # Get current x-data from the line
                        current_x = np.asarray(line(i).get_xdata(), dtype=float)
                        y_with_offset = y_norm + current_offset
                        y_data_list[i] = y_with_offset
                        offsets_list.append(current_offset)
                        # Update x_data_list to match current line data
                        x_data_list[i] = current_x.copy()
                        line(i).set_data(current_x, y_with_offset)
                        y_range = (y_norm.max() - y_norm.min()) if y_norm.size else 0.0
                        gap = y_range + (delta * (y_range if args.autoscale else 1.0))
                        current_offset -= gap
                else:
                    current_offset = 0.0
                    for i, y_norm in enumerate(orig_y):
                        if i >= nlines():
                            continue
                        # Get current x-data from the line
                        current_x = np.asarray(line(i).get_xdata(), dtype=float)
                        y_with_offset = y_norm + current_offset
                        y_data_list[i] = y_with_offset
                        offsets_list.append(current_offset)
                        # Update x_data_list to match current line data
                        x_data_list[i] = current_x.copy()
                        line(i).set_data(current_x, y_with_offset)
                        increment = (y_norm.max() - y_norm.min()) * delta if (args.autoscale and y_norm.size) else delta
                        current_offset += increment
                update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                ax.relim(); ax.autoscale_view(scalex=False, scaley=True)
                from .axis_range import _autoscale_xy_right_y
                _autoscale_xy_right_y(fig)
                fig.canvas.draw()
                print(f"Offsets updated with delta={delta}")
            except ValueError:
                print("Invalid delta value")
            except Exception as e:
                print(f"Error updating offsets: {e}")

        elif offset_cmd.isdigit():
            # Adjust individual curve offset
            try:
                curve_num = int(offset_cmd)
                if curve_num < 1 or curve_num > len(labels):
                    print("Invalid curve number (1-{})".format(len(labels)))
                    continue

                idx = curve_num - 1
                if idx >= nlines():
                    print("Invalid curve number.")
                    continue

                current_offset = offsets_list[idx] if idx < len(offsets_list) else 0.0

                individual_offset_input = safe_input("Enter offset for curve {} (current: {:.4g}): ".format(
                    curve_num, current_offset)).strip()
                if not individual_offset_input:
                    print("Canceled.")
                    continue

                individual_offset = float(individual_offset_input)
                push_state("curve-{}-offset".format(curve_num))

                # Get current x-data from the line to ensure we're working with actual displayed data
                current_x = np.asarray(line(idx).get_xdata(), dtype=float)
                # Apply individual offset to this curve
                y_norm = orig_y[idx]
                offsets_list[idx] = individual_offset
                y_with_offset = y_norm + individual_offset
                y_data_list[idx] = y_with_offset
                # Update x_data_list to match current line data
                x_data_list[idx] = current_x.copy()
                line(idx).set_data(current_x, y_with_offset)

                ax.relim()
                ax.autoscale_view(scalex=False, scaley=True)
                from .axis_range import _autoscale_xy_right_y
                _autoscale_xy_right_y(fig)
                update_labels(ax, y_data_list, label_text_objects, args.stack, getattr(fig, '_stack_label_at_bottom', False))
                fig.canvas.draw()
                print("Curve {} offset set to: {:.4g}".format(curve_num, individual_offset))

            except ValueError:
                print("Invalid offset value")
            except Exception as e:
                print(f"Error setting curve offset: {e}")
        else:
            print("Unknown command. Use 1-{}, a, r, d, or q".format(len(labels)))
    return delta

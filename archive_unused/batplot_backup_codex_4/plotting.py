"""Plotting helpers for batplot."""

from __future__ import annotations

from typing import List
import numpy as np


def update_labels(ax, y_data_list: List, label_text_objects: List, stack_mode: bool, stack_label_at_bottom: bool = False):
    """
    stack_mode True:
        Each label at (xmax, curve_ymax or curve_ymin) in data coordinates.
        If stack_label_at_bottom is True, labels are placed at curve minimum.
        If stack_label_at_bottom is False (default), labels are placed at curve maximum.
    stack_mode False:
        Labels form a fixed vertical list at top-right or bottom-right in axes coordinates.
        If stack_label_at_bottom is True, labels are positioned at bottom-right.
        If stack_label_at_bottom is False (default), labels are positioned at top-right.
    
    Sets label text color to match the corresponding curve color.
    """
    if not label_text_objects:
        return

    if stack_mode:
        x_max = ax.get_xlim()[1]
        for i, txt in enumerate(label_text_objects):
            if i < len(y_data_list) and len(y_data_list[i]) > 0:
                if stack_label_at_bottom:
                    # Place at bottom but add a small offset upward (10% of curve range)
                    y_min = float(np.min(y_data_list[i]))
                    y_max = float(np.max(y_data_list[i]))
                    y_range = y_max - y_min
                    y_pos_curve = y_min + (0.1 * y_range)  # 10% above the minimum
                else:
                    y_pos_curve = float(np.max(y_data_list[i]))
            else:
                if stack_label_at_bottom:
                    y_lim_min = ax.get_ylim()[0]
                    y_lim_max = ax.get_ylim()[1]
                    y_lim_range = y_lim_max - y_lim_min
                    y_pos_curve = y_lim_min + (0.1 * y_lim_range)
                else:
                    y_pos_curve = ax.get_ylim()[1]
            txt.set_transform(ax.transData)
            txt.set_position((x_max, y_pos_curve))
            # Set label color to match curve color
            try:
                if i < len(ax.lines):
                    txt.set_color(ax.lines[i].get_color())
            except Exception:
                pass
    else:
        n = len(label_text_objects)
        top_pad = 0.02
        bottom_pad = 0.05  # More padding at bottom to avoid x-axis labels
        spacing = min(0.08, max(0.025, 0.90 / max(n, 1)))
        
        if stack_label_at_bottom:
            # Position labels from bottom up (bottom-right)
            # Calculate available space and adjust starting position
            available_space = 1.0 - bottom_pad - top_pad
            total_height = (n - 1) * spacing if n > 1 else 0
            
            # If labels would extend beyond top, compress spacing
            if total_height > available_space:
                spacing = available_space / max(n - 1, 1)
            
            start_y = bottom_pad
            for i, txt in enumerate(label_text_objects):
                y_pos = start_y + i * spacing
                # Ensure we stay within bounds
                if y_pos > 1.0 - top_pad:
                    y_pos = 1.0 - top_pad
                txt.set_transform(ax.transAxes)
                txt.set_position((1.0, y_pos))
                # Set label color to match curve color
                try:
                    if i < len(ax.lines):
                        txt.set_color(ax.lines[i].get_color())
                except Exception:
                    pass
        else:
            # Position labels from top down (top-right)
            start_y = 1.0 - top_pad
            for i, txt in enumerate(label_text_objects):
                y_pos = start_y - i * spacing
                if y_pos < top_pad:
                    y_pos = top_pad
                txt.set_transform(ax.transAxes)
                txt.set_position((1.0, y_pos))
                # Set label color to match curve color
                try:
                    if i < len(ax.lines):
                        txt.set_color(ax.lines[i].get_color())
                except Exception:
                    pass
    ax.figure.canvas.draw_idle()

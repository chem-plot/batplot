"""Plotting helpers for batplot.

This module contains utility functions for positioning and styling plot labels.
Labels are the text annotations that identify each curve (e.g., file names).
"""

from __future__ import annotations

from typing import List
import numpy as np


def update_labels(ax, y_data_list: List, label_text_objects: List, stack_mode: bool, stack_label_at_bottom: bool = False):
    """
    Update positions and colors of curve labels on a plot.
    
    HOW LABEL POSITIONING WORKS:
    ---------------------------
    Labels identify which curve is which (e.g., "file1.xy", "file2.xy").
    This function positions them intelligently based on the plot mode:
    
    STACK MODE (stack_mode=True):
    -----------------------------
    When curves are stacked vertically (--stack flag), each label is placed
    next to its corresponding curve at the right edge of the plot.
    
    Positioning:
    - X position: Right edge of plot (x_max in data coordinates)
    - Y position: 
      * If stack_label_at_bottom=False: At curve maximum (top of curve)
      * If stack_label_at_bottom=True: At curve minimum + 10% offset (bottom of curve)
    
    Coordinate system: Data coordinates (matches curve data)
    Example: If curve goes from y=0 to y=100, label is at (x_max, 100) or (x_max, 10)
    
    NORMAL MODE (stack_mode=False):
    --------------------------------
    When curves are overlaid (not stacked), labels form a vertical list
    at the right edge of the plot.
    
    Positioning:
    - X position: Right edge (1.0 in axes coordinates = 100% of plot width)
    - Y position: Evenly spaced vertical list
      * If stack_label_at_bottom=False: Top-right, spacing downward
      * If stack_label_at_bottom=True: Bottom-right, spacing upward
    
    Coordinate system: Axes coordinates (0.0 to 1.0, independent of data range)
    Example: First label at (1.0, 0.98), second at (1.0, 0.90), etc.
    
    COLOR MATCHING:
    --------------
    Each label's text color is set to match its corresponding curve color.
    This makes it easy to identify which label belongs to which curve.
    
    Args:
        ax: Matplotlib axes object containing the plot
        y_data_list: List of y-data arrays, one per curve
                     Used to find curve min/max for stack mode positioning
        label_text_objects: List of matplotlib Text objects (the labels)
        stack_mode: True if curves are stacked, False if overlaid
        stack_label_at_bottom: If True, place labels at bottom (for stack mode)
                               or bottom-right (for normal mode)
    """
    # Early return if no labels to update
    if not label_text_objects:
        return

    # ====================================================================
    # STACK MODE: Labels positioned next to each curve
    # ====================================================================
    # In stack mode, curves are separated vertically. Each label is placed
    # at the right edge of the plot, aligned with its corresponding curve.
    fig = getattr(ax, 'figure', None)
    label_anchor_left = bool(getattr(fig, '_label_anchor_left', False)) if fig is not None else False

    # ====================================================================
    if stack_mode:
        # Get plot edges in data coordinates
        x_min, x_max = ax.get_xlim()
        x_pos = x_min if label_anchor_left else x_max
        ha = 'left' if label_anchor_left else 'right'
        
        # Position each label next to its curve
        for i, txt in enumerate(label_text_objects):
            # Check if we have data for this curve
            if i < len(y_data_list) and len(y_data_list[i]) > 0:
                # We have actual data, use curve min/max
                if stack_label_at_bottom:
                    # Place label at bottom of curve with small upward offset
                    # This prevents label from being hidden at the very bottom
                    y_min = float(np.min(y_data_list[i]))  # Bottom of curve
                    y_max = float(np.max(y_data_list[i]))  # Top of curve
                    y_range = y_max - y_min
                    # Position 10% above minimum (small offset for visibility)
                    y_pos_curve = y_min + (0.1 * y_range)
                else:
                    # Place label at top of curve (default)
                    y_pos_curve = float(np.max(y_data_list[i]))
            else:
                # No data available, use plot limits as fallback
                if stack_label_at_bottom:
                    y_lim_min = ax.get_ylim()[0]  # Bottom of plot
                    y_lim_max = ax.get_ylim()[1]  # Top of plot
                    y_lim_range = y_lim_max - y_lim_min
                    # Position 10% above bottom of plot
                    y_pos_curve = y_lim_min + (0.1 * y_lim_range)
                else:
                    y_pos_curve = ax.get_ylim()[1]  # Top of plot
            
            # Set coordinate system to data coordinates (matches curve positions)
            # transData means positions are in the same units as the plot data
            txt.set_transform(ax.transData)
            
            # Set label position (right edge, aligned with curve)
            txt.set_position((x_pos, y_pos_curve))
            txt.set_ha(ha)
            txt.set_va('bottom' if stack_label_at_bottom else 'top')
            
            # Set label color to match curve color (makes identification easier)
            try:
                if i < len(ax.lines):
                    # Get color from corresponding line object
                    txt.set_color(ax.lines[i].get_color())
            except Exception:
                # If color matching fails, keep default color
                pass
    # ====================================================================
    # NORMAL MODE: Labels form vertical list at right edge
    # ====================================================================
    # In normal mode (overlaid curves), labels are stacked vertically
    # at the right edge of the plot. They use axes coordinates (0.0 to 1.0)
    # so they stay in the same position even if data range changes.
    # ====================================================================
    else:
        n = len(label_text_objects)
        
        # Padding from edges (in axes coordinates, where 0.0 = bottom, 1.0 = top)
        top_pad = 0.02      # 2% padding from top
        bottom_pad = 0.05   # 5% padding from bottom (more to avoid x-axis labels)
        
        # Calculate spacing between labels
        # Formula: Distribute 90% of vertical space evenly among labels
        # Clamp between 0.025 (minimum) and 0.08 (maximum) for readability
        spacing = min(0.08, max(0.025, 0.90 / max(n, 1)))
        
        if stack_label_at_bottom:
            # ============================================================
            # BOTTOM-RIGHT POSITIONING
            # ============================================================
            # Labels start at bottom and stack upward.
            # Useful when top of plot is crowded or you want labels near data.
            # ============================================================
            
            # Calculate available vertical space
            available_space = 1.0 - bottom_pad - top_pad
            
            # Calculate total height needed for all labels
            total_height = (n - 1) * spacing if n > 1 else 0
            
            # If labels would extend beyond top, compress spacing
            # This ensures all labels fit even with many curves
            if total_height > available_space:
                spacing = available_space / max(n - 1, 1)
            
            # Start from bottom and stack upward
            start_y = bottom_pad
            for i, txt in enumerate(label_text_objects):
                y_pos = start_y + i * spacing  # Each label higher than previous
                
                # Ensure we stay within bounds (safety check)
                if y_pos > 1.0 - top_pad:
                    y_pos = 1.0 - top_pad
                
                # Use axes coordinates (0.0 to 1.0, independent of data)
                # This keeps labels in same position even if data range changes
                txt.set_transform(ax.transAxes)
                
                # Position at right edge (1.0 = 100% of plot width)
                txt.set_position((0.0 if label_anchor_left else 1.0, y_pos))
                txt.set_ha('left' if label_anchor_left else 'right')
                txt.set_va('bottom')
                
                # Match label color to curve color
                try:
                    if i < len(ax.lines):
                        txt.set_color(ax.lines[i].get_color())
                except Exception:
                    pass
        else:
            # ============================================================
            # TOP-RIGHT POSITIONING (DEFAULT)
            # ============================================================
            # Labels start at top and stack downward.
            # This is the default behavior and works well for most plots.
            # ============================================================
            
            # Start from top and stack downward
            start_y = 1.0 - top_pad  # Start just below top edge
            for i, txt in enumerate(label_text_objects):
                y_pos = start_y - i * spacing  # Each label lower than previous
                
                # Ensure we stay within bounds (safety check)
                if y_pos < top_pad:
                    y_pos = top_pad
                
                # Use axes coordinates (0.0 to 1.0, independent of data)
                txt.set_transform(ax.transAxes)
                
                # Position at right edge (1.0 = 100% of plot width)
                txt.set_position((0.0 if label_anchor_left else 1.0, y_pos))
                txt.set_ha('left' if label_anchor_left else 'right')
                txt.set_va('top')
                
                # Match label color to curve color
                try:
                    if i < len(ax.lines):
                        txt.set_color(ax.lines[i].get_color())
                except Exception:
                    pass
    
    # ====================================================================
    # REDRAW PLOT
    # ====================================================================
    # After updating label positions, tell matplotlib to redraw the plot.
    # draw_idle() schedules a redraw when the GUI is ready (more efficient
    # than immediate draw()).
    # ====================================================================
    ax.figure.canvas.draw_idle()

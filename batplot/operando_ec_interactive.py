"""Interactive menu for operando contour plots with optional electrochemical (EC) side panel.

This module provides an interactive command-line interface for manipulating operando
contour plots that correlate in-situ characterization data (XRD/PDF/XAS) with 
electrochemical measurements. Users can adjust:
- Visual styling (colormap, line widths, fonts)
- Axis ranges and labels
- Plot geometry (widths, gaps, heights)
- EC panel settings (time vs ions mode, curve visibility)
- Export and session management

The menu supports both dual-panel mode (with .mpt file) and operando-only mode.
"""

from __future__ import annotations

from typing import Tuple, Dict, Optional, Any
import json
import os

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, MaxNLocator, AutoMinorLocator, NullFormatter
import numpy as np

# Import UI positioning functions
from .ui import position_top_xlabel as _ui_position_top_xlabel
from .ui import position_right_ylabel as _ui_position_right_ylabel
from .ui import position_bottom_xlabel as _ui_position_bottom_xlabel
from .ui import position_left_ylabel as _ui_position_left_ylabel


def _colorize_menu(text):
    """Colorize menu items: command in cyan, colon in white, description in default."""
    if ':' not in text:
        return text
    parts = text.split(':', 1)
    cmd = parts[0].strip()
    desc = parts[1].strip() if len(parts) > 1 else ''
    return f"\033[96m{cmd}\033[0m: {desc}"  # Cyan for command, default for description


def _colorize_prompt(text):
    """Colorize commands within input prompts. Handles formats like (s=size, f=family, q=return) or (y/n)."""
    import re
    pattern = r'\(([a-z]+=[^,)]+(?:,\s*[a-z]+=[^,)]+)*|[a-z]+(?:/[a-z]+)+)\)'
    
    def colorize_match(match):
        content = match.group(1)
        if '/' in content:
            parts = content.split('/')
            colored_parts = [f"\033[96m{p.strip()}\033[0m" for p in parts]
            return f"({'/'.join(colored_parts)})"
        else:
            parts = content.split(',')
            colored_parts = []
            for part in parts:
                part = part.strip()
                if '=' in part:
                    cmd, desc = part.split('=', 1)
                    colored_parts.append(f"\033[96m{cmd.strip()}\033[0m={desc.strip()}")
                else:
                    colored_parts.append(part)
            return f"({', '.join(colored_parts)})"
    
    return re.sub(pattern, colorize_match, text)


def _colorize_inline_commands(text):
    """Colorize inline command examples in help text. Colors quoted examples and specific known commands."""
    import re
    # Color quoted command examples (like 's2 w5 a4', 'w2 w5')
    text = re.sub(r"'([a-z0-9\s_-]+)'", lambda m: f"'\033[96m{m.group(1)}\033[0m'", text)
    # Color specific known commands: q, i, l, list, help, all
    text = re.sub(r'\b(q|i|l|list|help|all)\b(?=\s*[=,]|\s*$)', lambda m: f"\033[96m{m.group(1)}\033[0m", text)
    return text


# ============================================================================
# Constants
# ============================================================================

# Default geometry adjustments (in inches)
DEFAULT_EC_GAP_MULTIPLIER = 0.35  # Multiplier to reduce gap between operando and EC panels
MIN_EC_GAP_INCHES = 0.05  # Minimum allowed gap between panels
MIN_EC_WIDTH_INCHES = 0.8  # Minimum width for EC panel

# Width transfer from EC to operando panel
WIDTH_TRANSFER_FROM_EC_FRACTION = 0.18  # Fraction of EC width to transfer to operando
MAX_WIDTH_TRANSFER_FRACTION = 0.12  # Maximum transfer as fraction of combined width

# Default voltage axis margin (fraction of range)
DEFAULT_VOLTAGE_MARGIN = 0.02  # 2% margin on voltage axis

# History management
MAX_UNDO_HISTORY_SIZE = 40  # Maximum number of undo states to keep

# Intensity mapping
INTENSITY_CALCULATION_BUFFER = 1  # Buffer for intensity calculation indices


# ============================================================================
# Geometry and State Management Helper Functions
# ============================================================================

def _get_fig_size(fig) -> Tuple[float, float]:
    """Get the figure size in inches.
    
    Args:
        fig: Matplotlib Figure object
        
    Returns:
        Tuple of (width, height) in inches
    """
    width, height = fig.get_size_inches()
    return float(width), float(height)


def _get_geometry_snapshot(ax, ec_ax) -> Dict:
    """Collect a snapshot of current axes geometry settings.
    
    Captures axis limits and labels for both operando and EC (if present) axes.
    Used for undo/redo functionality and session persistence.
    
    Args:
        ax: Main operando axes object
        ec_ax: Optional EC (electrochemistry) axes object
        
    Returns:
        Dictionary containing:
            - 'operando': dict with xlim, ylim, xlabel, ylabel
            - 'ec': dict with xlim, ylim, xlabel, ylabel (if ec_ax exists)
    """
    snapshot = {
        'operando': {
            'xlim': list(ax.get_xlim()),
            'ylim': list(ax.get_ylim()),
            'xlabel': ax.get_xlabel() or '',
            'ylabel': ax.get_ylabel() or '',
        }
    }
    if ec_ax is not None:
        snapshot['ec'] = {
            'xlim': list(ec_ax.get_xlim()),
            'ylim': list(ec_ax.get_ylim()),
            'xlabel': ec_ax.get_xlabel() or '',
            'ylabel': ec_ax.get_ylabel() or '',
        }
    return snapshot


def _ensure_fixed_params(fig, ax, cbar_ax, ec_ax):
    """Initialize and return fixed geometry parameters in inches.
    
    Retrieves or calculates the fixed dimensions for all plot elements (colorbar,
    operando axes, EC axes) and the gaps between them. These values are stored
    as attributes on the axes objects and used to maintain consistent sizing
    when resizing the figure.
    
    Args:
        fig: Matplotlib Figure object
        ax: Main operando axes
        cbar_ax: Colorbar axes
        ec_ax: Optional EC axes (can be None)
        
    Returns:
        Tuple of (colorbar_width, colorbar_gap, ec_gap, ec_width, 
                  axes_width, axes_height) all in inches
    """
    fig_width_in, fig_height_in = _get_fig_size(fig)
    
    # Get current axes positions (fractions of figure size)
    ax_x0, ax_y0, ax_width_frac, ax_height_frac = ax.get_position().bounds
    cb_x0, cb_y0, cb_width_frac, cb_height_frac = cbar_ax.get_position().bounds
    
    # Retrieve or calculate fixed parameters in inches
    colorbar_width_in = getattr(cbar_ax, '_fixed_cb_w_in', cb_width_frac * fig_width_in)
    colorbar_gap_in = getattr(cbar_ax, '_fixed_cb_gap_in', 
                              (ax_x0 - (cb_x0 + cb_width_frac)) * fig_width_in)
    axes_width_in = getattr(ax, '_fixed_ax_w_in', ax_width_frac * fig_width_in)
    axes_height_in = getattr(ax, '_fixed_ax_h_in', ax_height_frac * fig_height_in)
    
    if ec_ax is not None:
        ec_x0, ec_y0, ec_width_frac, ec_height_frac = ec_ax.get_position().bounds
        ec_gap_in = getattr(ec_ax, '_fixed_ec_gap_in', 
                           (ec_x0 - (ax_x0 + ax_width_frac)) * fig_width_in)
        ec_width_in = getattr(ec_ax, '_fixed_ec_w_in', ec_width_frac * fig_width_in)
    else:
        ec_gap_in = 0.0
        ec_width_in = 0.0
    
    return (colorbar_width_in, colorbar_gap_in, ec_gap_in, ec_width_in, 
            axes_width_in, axes_height_in)


def _apply_group_layout_inches(fig, ax, cbar_ax, ec_ax,
                               ax_width_in: float, ax_height_in: float,
                               colorbar_width_in: float, colorbar_gap_in: float,
                               ec_gap_in: float, ec_width_in: float):
    """Position all plot elements (colorbar, operando, EC) centered horizontally.
    
    This function calculates and applies the layout for all plot elements using
    absolute inch measurements for widths and gaps, which allows consistent sizing
    when the figure is resized. All elements are vertically centered and the group
    is horizontally centered in the figure.
    
    Args:
        fig: Matplotlib Figure object
        ax: Main operando axes
        cbar_ax: Colorbar axes
        ec_ax: Optional EC axes (can be None)
        ax_width_in: Operando axes width in inches
        ax_height_in: Operando axes height in inches
        colorbar_width_in: Colorbar width in inches
        colorbar_gap_in: Gap between colorbar and operando axes in inches
        ec_gap_in: Gap between operando and EC axes in inches
        ec_width_in: EC axes width in inches (0 if ec_ax is None)
    """
    fig_width_in, fig_height_in = _get_fig_size(fig)
    
    # Convert inches to figure fractions (0-1 scale)
    ax_width_frac = max(0.0, ax_width_in / fig_width_in)
    ax_height_frac = max(0.0, ax_height_in / fig_height_in)
    colorbar_width_frac = max(0.0, colorbar_width_in / fig_width_in)
    colorbar_gap_frac = max(0.0, colorbar_gap_in / fig_width_in)
    
    if ec_ax is not None:
        ec_gap_frac = max(0.0, ec_gap_in / fig_width_in)
        ec_width_frac = max(0.0, ec_width_in / fig_width_in)
        # Calculate total width for all elements
        total_width_frac = (colorbar_width_frac + colorbar_gap_frac + 
                           ax_width_frac + ec_gap_frac + ec_width_frac)
    else:
        ec_gap_frac = 0.0
        ec_width_frac = 0.0
        # Calculate total width without EC panel
        total_width_frac = colorbar_width_frac + colorbar_gap_frac + ax_width_frac
    
    # Center the group horizontally and vertically
    group_left_edge = 0.5 - total_width_frac / 2.0
    vertical_center = 0.5 - ax_height_frac / 2.0

    # Calculate positions for each element: [x0, y0, width, height]
    colorbar_x0 = group_left_edge
    operando_x0 = colorbar_x0 + colorbar_width_frac + colorbar_gap_frac
    colorbar_height_frac = ax_height_frac  # Match colorbar height to axes

    # Apply positions
    ax.set_position([operando_x0, vertical_center, ax_width_frac, ax_height_frac])
    cbar_ax.set_position([colorbar_x0, vertical_center, colorbar_width_frac, 
                          colorbar_height_frac])
    
    if ec_ax is not None:
        ec_x0 = operando_x0 + ax_width_frac + ec_gap_frac
        ec_ax.set_position([ec_x0, vertical_center, ec_width_frac, ax_height_frac])
        setattr(ec_ax, '_fixed_ec_gap_in', ec_gap_in)
        setattr(ec_ax, '_fixed_ec_w_in', ec_width_in)

    # Store fixed inch measurements for future use
    setattr(cbar_ax, '_fixed_cb_w_in', colorbar_width_in)
    setattr(cbar_ax, '_fixed_cb_gap_in', colorbar_gap_in)
    setattr(ec_ax, '_fixed_ec_gap_in', ec_gap_in)
    setattr(ec_ax, '_fixed_ec_w_in', ec_width_in)
    setattr(ax, '_fixed_ax_w_in', ax_width_in)
    setattr(ax, '_fixed_ax_h_in', ax_height_in)

    # Redraw the canvas
    try:
        fig.canvas.draw()
    except Exception:
        fig.canvas.draw_idle()


def operando_ec_interactive_menu(fig, ax, im, cbar, ec_ax):
    """Launch the interactive menu for operando contour plots.
    
    This is the main entry point for the interactive mode. It sets up the initial
    layout, initializes state management, and enters a command loop that allows
    users to interactively modify the plot appearance, adjust axis ranges, toggle
    elements, and export results.
    
    Supported modes:
    - Dual-panel mode: Operando contour with EC side panel (when .mpt file present)
    - Operando-only mode: Just the contour plot (no .mpt file)
    
    Available commands:
    - Styling: colormap (oc), line widths (l), fonts (f), colors
    - Geometry: width (ow/ew), height (h), gaps, canvas size (g)
    - Axes: ranges (ox/oy/oz/et/ey), labels (or/er), toggle visibility (t)
    - EC: curve selection (el), y-axis mode (ey: time ↔ ions)
    - Utilities: crosshair (n), reverse (r), visibility toggle (v)
    - Export: figure (e), style (p), session (s), undo (b), quit (q)
    
    Args:
        fig: Matplotlib Figure containing the plot
        ax: Main axes for operando contour
        im: AxesImage object (the contour/heatmap)
        cbar: Colorbar object
        ec_ax: Optional axes for EC curves (None in operando-only mode)
    """

    def _renormalize_to_visible():
        """Adjust color scale to match the intensity range of the currently visible region.
        
        This function recalculates the colorbar limits based on only the portion of the
        contour map that is currently visible (within the current x/y axis limits). This
        is useful after zooming to enhance contrast in a specific region.
        
        The function:
        1. Gets the visible x/y range from current axis limits
        2. Maps these to pixel indices in the image array
        3. Extracts the visible sub-array
        4. Finds min/max of finite values (ignoring NaN/Inf)
        5. Updates the color scale (clim) and colorbar
        """
        try:
            # Get the image data array
            data_array = np.asarray(im.get_array(), dtype=float)
            if data_array.ndim != 2 or data_array.size == 0:
                return
                
            height, width = data_array.shape
            
            # Get image extent (data coordinates)
            x0, x1, y0, y1 = im.get_extent()
            
            # Normalize coordinate orientation (handle reversed axes)
            x_min, x_max = (x0, x1) if x0 <= x1 else (x1, x0)
            y_min, y_max = (y0, y1) if y0 <= y1 else (y1, y0)
            
            # Get current visible limits
            x_limits = ax.get_xlim()
            y_limits = ax.get_ylim()
            x_visible_min, x_visible_max = (min(x_limits), max(x_limits))
            y_visible_min, y_visible_max = (min(y_limits), max(y_limits))
            
            # Map data coordinates to pixel indices
            if x_max > x_min:
                col_start = int(np.floor((x_visible_min - x_min) / (x_max - x_min) * (width - 1)))
                col_end = int(np.ceil((x_visible_max - x_min) / (x_max - x_min) * (width - 1)))
            else:
                col_start, col_end = 0, width - 1
                
            if y_max > y_min:
                row_start = int(np.floor((y_visible_min - y_min) / (y_max - y_min) * (height - 1)))
                row_end = int(np.ceil((y_visible_max - y_min) / (y_max - y_min) * (height - 1)))
            else:
                row_start, row_end = 0, height - 1
            
            # Clip indices to array bounds and ensure valid slice
            col_start = max(0, min(width - 1, col_start))
            col_end = max(0, min(width - 1, col_end))
            row_start = max(0, min(height - 1, row_start))
            row_end = max(0, min(height - 1, row_end))
            
            # Swap if reversed
            if col_end < col_start:
                col_start, col_end = col_end, col_start
            if row_end < row_start:
                row_start, row_end = row_end, row_start
            
            # Extract visible region
            visible_data = data_array[row_start:row_end + 1, col_start:col_end + 1]
            
            # Get finite values only (exclude NaN and Inf)
            finite_values = visible_data[np.isfinite(visible_data)]
            
            if finite_values.size > 0:
                intensity_min = float(np.min(finite_values))
                intensity_max = float(np.max(finite_values))
                
                if intensity_max > intensity_min:
                    # Update color limits
                    im.set_clim(intensity_min, intensity_max)
                    
                    # Update colorbar if available
                    try:
                        if cbar is not None:
                            cbar.update_normal(im)
                    except Exception:
                        pass
        except Exception:
            pass
    def print_menu():
        # Adjust menu based on whether EC panel is available
        if ec_ax is not None:
            col1 = [
                "oc: op colormap",
                "ow: op width",
                "el: ec curve",
                "ew: ec width",
                " v: toggle colorbar/ec",
                " t: toggle axes",
                " l: line",
                " h: height",
                " f: fonts",
                " g: size",
                " r: reverse plot"
            ]
            col2 = [
                "ox: X range",
                "oy: Y range",
                "oz: intensity range",
                "or: rename"
            ]
            col3 = [
                "et: time range",
                "ey: y axis type",
                "er: rename"
            ]
            col4 = [
                "n: crosshair",
                "p: print(export) style/geom",
                "i: import style/geom",
                "e: export figure",
                "s: save project",
                "b: undo",
                "q: quit",
            ]
            # Dynamic column widths
            w1 = max(len("(Styles)"), *(len(s) for s in col1), 12)
            w2 = max(len("(Operando)"), *(len(s) for s in col2), 14)
            w3 = max(len("(EC)"), *(len(s) for s in col3), 14)
            w4 = max(len("(Options)"), *(len(s) for s in col4), 16)
            rows = max(len(col1), len(col2), len(col3), len(col4))
            print("\n\033[1mInteractive menu:\033[0m")  # Bold title
            print(f"  \033[93m{'(Styles)':<{w1}}\033[0m \033[93m{'(Operando)':<{w2}}\033[0m \033[93m{'(EC)':<{w3}}\033[0m \033[93m{'(Options)':<{w4}}\033[0m")  # Yellow headers
            for i in range(rows):
                p1 = _colorize_menu(col1[i]) if i < len(col1) else ""
                p2 = _colorize_menu(col2[i]) if i < len(col2) else ""
                p3 = _colorize_menu(col3[i]) if i < len(col3) else ""
                p4 = _colorize_menu(col4[i]) if i < len(col4) else ""
                # Add padding to account for ANSI escape codes
                pad1 = w1 + (9 if i < len(col1) else 0)
                pad2 = w2 + (9 if i < len(col2) else 0)
                pad3 = w3 + (9 if i < len(col3) else 0)
                pad4 = w4 + (9 if i < len(col4) else 0)
                print(f"  {p1:<{pad1}} {p2:<{pad2}} {p3:<{pad3}} {p4:<{pad4}}")
        else:
            # Operando-only menu (no EC panel)
            col1 = [
                "oc: op colormap",
                "ow: op width",
                " v: toggle colorbar",
                " t: toggle axes",
                " l: line",
                " h: height",
                " f: fonts",
                " g: size",
                " r: reverse plot"
            ]
            col2 = [
                "ox: X range",
                "oy: Y range",
                "oz: intensity range",
                "or: rename"
            ]
            col3 = [
                "n: crosshair",
                "p: print(export) style/geom",
                "i: import style/geom",
                "e: export figure",
                "s: save project",
                "b: undo",
                "q: quit",
            ]
            w1 = max(len("(Styles)"), *(len(s) for s in col1), 12)
            w2 = max(len("(Operando)"), *(len(s) for s in col2), 14)
            w3 = max(len("(Options)"), *(len(s) for s in col3), 16)
            rows = max(len(col1), len(col2), len(col3))
            print("\n\033[1mInteractive menu:\033[0m")  # Bold title
            print(f"  \033[93m{'(Styles)':<{w1}}\033[0m \033[93m{'(Operando)':<{w2}}\033[0m \033[93m{'(Options)':<{w3}}\033[0m")  # Yellow headers
            for i in range(rows):
                p1 = _colorize_menu(col1[i]) if i < len(col1) else ""
                p2 = _colorize_menu(col2[i]) if i < len(col2) else ""
                p3 = _colorize_menu(col3[i]) if i < len(col3) else ""
                # Add padding to account for ANSI escape codes
                pad1 = w1 + (9 if i < len(col1) else 0)
                pad2 = w2 + (9 if i < len(col2) else 0)
                pad3 = w3 + (9 if i < len(col3) else 0)
                print(f"  {p1:<{pad1}} {p2:<{pad2}} {p3:<{pad3}}")
        print()
    def print_menu_old():
        col1 = [
            "oc: op colormap",
            "ow: op width",
            "el: ec curve",
            "ew: ec width",
            " k: spine colors",
            " t: toggle axes",
            " l: line",
            " h: height",
            " f: fonts",
            " g: size",
            " r: reverse plot"
        ]
        col2 = [
            "ox: X range",
            "oy: Y range",
            "oz: intensity range",
            "or: rename"
        ]
        col3 = [
            "et: time range",
            "ey: y axis type",
            "er: rename",
            
        ]
        col4 = [
            "n: crosshair",
            "p: print(export) style/geom",
            "i: import style/geom",
            "e: export figure",
            "s: save project",
            "b: undo",
            "q: quit",
        ]
        # Dynamic column widths
        w1 = max(len("(Styles)"), *(len(s) for s in col1), 12)
        w2 = max(len("(Operando)"), *(len(s) for s in col2), 14)
        w3 = max(len("(EC)"), *(len(s) for s in col3), 14)
        w4 = max(len("(Options)"), *(len(s) for s in col4), 16)
        rows = max(len(col1), len(col2), len(col3), len(col4))
        print("\nInteractive menu:")
        print(f"  {'(Styles)':<{w1}} {'(Operando)':<{w2}} {'(EC)':<{w3}} {'(Options)':<{w4}}")
        for i in range(rows):
            p1 = col1[i] if i < len(col1) else ""
            p2 = col2[i] if i < len(col2) else ""
            p3 = col3[i] if i < len(col3) else ""
            p4 = col4[i] if i < len(col4) else ""
            print(f"  {p1:<{w1}} {p2:<{w2}} {p3:<{w3}} {p4:<{w4}}")

    def set_fonts(family=None, size=None):
        import matplotlib as mpl
        if family:
            mpl.rcParams['font.family'] = 'sans-serif'
            mpl.rcParams['font.sans-serif'] = [family, 'DejaVu Sans', 'Arial', 'Liberation Sans']
        if size is not None:
            mpl.rcParams['font.size'] = size
        axes = [ax, ec_ax]
        for a in axes:
            if a is None:
                continue
            if family:
                try: a.xaxis.label.set_family(family)
                except Exception: pass
                try: a.yaxis.label.set_family(family)
                except Exception: pass
                for t in a.get_xticklabels() + a.get_yticklabels():
                    try: t.set_family(family)
                    except Exception: pass
                # Also update top/right tick labels (label2)
                try:
                    for tick in a.xaxis.get_major_ticks():
                        if hasattr(tick, 'label2'):
                            tick.label2.set_family(family)
                except Exception: pass
                try:
                    for tick in a.yaxis.get_major_ticks():
                        if hasattr(tick, 'label2'):
                            tick.label2.set_family(family)
                except Exception: pass
                for t in getattr(a, 'texts', []):
                    try: t.set_family(family)
                    except Exception: pass
                # Update top xlabel and right ylabel artists
                try:
                    top_artist = getattr(a, '_top_xlabel_artist', None)
                    if top_artist is not None:
                        top_artist.set_family(family)
                except Exception: pass
                try:
                    right_artist = getattr(a, '_right_ylabel_artist', None)
                    if right_artist is not None:
                        right_artist.set_family(family)
                except Exception: pass
            if size is not None:
                try: a.xaxis.label.set_size(size)
                except Exception: pass
                try: a.yaxis.label.set_size(size)
                except Exception: pass
                for t in a.get_xticklabels() + a.get_yticklabels():
                    try: t.set_size(size)
                    except Exception: pass
                # Also update top/right tick labels (label2)
                try:
                    for tick in a.xaxis.get_major_ticks():
                        if hasattr(tick, 'label2'):
                            tick.label2.set_size(size)
                except Exception: pass
                try:
                    for tick in a.yaxis.get_major_ticks():
                        if hasattr(tick, 'label2'):
                            tick.label2.set_size(size)
                except Exception: pass
                for t in getattr(a, 'texts', []):
                    try: t.set_size(size)
                    except Exception: pass
                # Update top xlabel and right ylabel artists
                try:
                    top_artist = getattr(a, '_top_xlabel_artist', None)
                    if top_artist is not None:
                        top_artist.set_size(size)
                except Exception: pass
                try:
                    right_artist = getattr(a, '_right_ylabel_artist', None)
                    if right_artist is not None:
                        right_artist.set_size(size)
                except Exception: pass
        # colorbar
        if cbar is not None:
            if family:
                for t in cbar.ax.get_yticklabels():
                    try: t.set_family(family)
                    except Exception: pass
                try: 
                    # Update the ylabel object directly for consistent sizing
                    cbar.ax.yaxis.label.set_family(family)
                except Exception: pass
                # Update High/Low labels if they exist
                if hasattr(fig, '_cbar_high_text'):
                    try: fig._cbar_high_text.set_family(family)
                    except Exception: pass
                if hasattr(fig, '_cbar_low_text'):
                    try: fig._cbar_low_text.set_family(family)
                    except Exception: pass
            if size is not None:
                for t in cbar.ax.get_yticklabels():
                    try: t.set_size(size)
                    except Exception: pass
                try: 
                    # Update the ylabel object directly to match axis label sizes exactly
                    cbar.ax.yaxis.label.set_size(size)
                except Exception: pass
                # Update High/Low labels if they exist
                if hasattr(fig, '_cbar_high_text'):
                    try: fig._cbar_high_text.set_size(size)
                    except Exception: pass
                if hasattr(fig, '_cbar_low_text'):
                    try: fig._cbar_low_text.set_size(size)
                    except Exception: pass
        
        # Update title distances after font size changes (unified UI positioning functions)
        for a in axes:
            if a is None:
                continue
            try:
                # Get current tick state for this axis
                tick_state = getattr(a, '_saved_tick_state', {
                    'b_labels': True, 'bx': True,
                    't_labels': False, 'tx': False,
                    'l_labels': True, 'ly': True,
                    'r_labels': False, 'ry': False,
                })
                # Call all four UI positioning functions to update distances
                _ui_position_bottom_xlabel(a, fig, tick_state)
                _ui_position_top_xlabel(a, fig, tick_state)
                _ui_position_left_ylabel(a, fig, tick_state)
                _ui_position_right_ylabel(a, fig, tick_state)
            except Exception:
                pass
        
        try:
            fig.canvas.draw()
        except Exception:
            fig.canvas.draw_idle()

    # Initialize fixed params
    cb_w_in, cb_gap_in, ec_gap_in, ec_w_in, ax_w_in, ax_h_in = _ensure_fixed_params(fig, ax, cbar.ax, ec_ax)
    # Decrease distance between operando and EC plots once per session
    if not getattr(ec_ax, '_ec_gap_adjusted', False):
        try:
            # Decrease gap more aggressively and allow a smaller minimum
            # Increase the multiplier from 0.2 to 0.35 for more spacing
            ec_gap_in = max(0.05, ec_gap_in * 0.35)
            setattr(ec_ax, '_fixed_ec_gap_in', ec_gap_in)
            setattr(ec_ax, '_ec_gap_adjusted', True)
            _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)
        except Exception:
            pass
    # Rebalance default widths once per session: increase operando, decrease EC
    if not getattr(ec_ax, '_ec_op_width_adjusted', False):
        try:
            # Transfer a fraction of width from EC to operando while keeping total similar
            combined = ax_w_in + ec_w_in
            if combined > 0 and ec_w_in > 0.5:
                transfer = min(ec_w_in * 0.18, combined * 0.12)
                # Enforce sensible minimum EC width
                min_ec = 0.8
                if ec_w_in - transfer < min_ec:
                    transfer = max(0.0, ec_w_in - min_ec)
                ax_w_in = ax_w_in + transfer
                ec_w_in = ec_w_in - transfer
                _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)
            setattr(ec_ax, '_ec_op_width_adjusted', True)
        except Exception:
            pass
    # Default: put EC y-axis ticks/label on the right
    try:
        ec_ax.yaxis.tick_right()
        ec_ax.yaxis.set_label_position('right')
        # If a title exists, move it to the right as well
        _title = ec_ax.get_title()
        if isinstance(_title, str) and _title.strip():
            ec_ax.set_title(_title, loc='right')
    except Exception:
        pass
    # Give a tiny default right margin on EC x-limits (voltage) so curves aren't glued to the edge
    if not getattr(ec_ax, '_xlim_expanded_default', False):
        try:
            x0, x1 = ec_ax.get_xlim()
            xr = (x1 - x0) if x1 > x0 else 0.0
            if xr > 0:
                ec_ax.set_xlim(x0, x1 + 0.02 * xr)
                setattr(ec_ax, '_xlim_expanded_default', True)
        except Exception:
            pass

    print_menu()
    # Crosshair state for both axes
    # Undo history
    state_history = []
    
    def _get_spine_visible(axis, which: str) -> bool:
        """Helper to get spine visibility status"""
        sp = axis.spines.get(which)
        try:
            return bool(sp.get_visible()) if sp is not None else False
        except Exception:
            return False
    
    def _snapshot(note: str = ""):
        try:
            fig_w, fig_h = _get_fig_size(fig)
            # Geometry inches
            cb_w_in_s, cb_gap_in_s, ec_gap_in_s, ec_w_in_s, ax_w_in_s, ax_h_in_s = _ensure_fixed_params(fig, ax, cbar.ax, ec_ax)
            # Axes & image
            op_xlim = ax.get_xlim(); op_ylim = ax.get_ylim()
            # EC axes (only if ec_ax exists)
            if ec_ax is not None:
                ec_xlim = ec_ax.get_xlim(); ec_ylim = ec_ax.get_ylim()
            else:
                ec_xlim = None; ec_ylim = None
            try:
                clim = im.get_clim()
            except Exception:
                clim = None
            cmap_name = getattr(im.get_cmap(), 'name', None)
            # EC mode and caches (only if ec_ax exists)
            if ec_ax is not None:
                mode = getattr(ec_ax, '_ec_y_mode', 'time')
                ions_abs = getattr(ec_ax, '_ions_abs', None)
                prev_xlim = getattr(ec_ax, '_prev_ec_xlim', None)
                ions_expanded = getattr(ec_ax, '_ions_xlim_expanded', False)
                saved_time_ylim = getattr(ec_ax, '_saved_time_ylim', None)
                ec_labels = getattr(ec_ax, '_custom_labels', {'x': ec_ax.get_xlabel(), 'y_time': None, 'y_ions': None})
            else:
                mode = 'time'
                ions_abs = None
                prev_xlim = None
                ions_expanded = False
                saved_time_ylim = None
                ec_labels = None
            # Labels & fonts
            op_labels = getattr(ax, '_custom_labels', {'x': ax.get_xlabel(), 'y': ax.get_ylabel()})
            fam = plt.rcParams.get('font.sans-serif', [])
            fsize = plt.rcParams.get('font.size', None)
            # WASD state for both panes
            op_wasd = {
                'top':    {'spine': _get_spine_visible(ax, 'top'), 'ticks': ax.xaxis._major_tick_kw.get('tick1On', True), 
                           'minor': bool(ax.xaxis._minor_tick_kw.get('tick1On', False)), 
                           'labels': ax.xaxis._major_tick_kw.get('label1On', True), 
                           'title': bool(getattr(ax, '_top_xlabel_on', False))},
                'bottom': {'spine': _get_spine_visible(ax, 'bottom'), 'ticks': ax.xaxis._major_tick_kw.get('tick2On', True), 
                           'minor': bool(ax.xaxis._minor_tick_kw.get('tick2On', False)), 
                           'labels': ax.xaxis._major_tick_kw.get('label2On', True), 
                           'title': bool(ax.get_xlabel())},
                'left':   {'spine': _get_spine_visible(ax, 'left'), 'ticks': ax.yaxis._major_tick_kw.get('tick1On', True), 
                           'minor': bool(ax.yaxis._minor_tick_kw.get('tick1On', False)), 
                           'labels': ax.yaxis._major_tick_kw.get('label1On', True), 
                           'title': bool(ax.get_ylabel())},
                'right':  {'spine': _get_spine_visible(ax, 'right'), 'ticks': ax.yaxis._major_tick_kw.get('tick2On', False), 
                           'minor': bool(ax.yaxis._minor_tick_kw.get('tick2On', False)), 
                           'labels': ax.yaxis._major_tick_kw.get('label2On', False), 
                           'title': bool(getattr(ax, '_right_ylabel_on', False))},
            }
            # EC WASD state (only if ec_ax exists)
            if ec_ax is not None:
                ec_wasd = {
                    'top':    {'spine': _get_spine_visible(ec_ax, 'top'), 'ticks': ec_ax.xaxis._major_tick_kw.get('tick1On', True), 
                               'minor': bool(ec_ax.xaxis._minor_tick_kw.get('tick1On', False)), 
                               'labels': ec_ax.xaxis._major_tick_kw.get('label1On', True), 
                               'title': bool(getattr(ec_ax, '_top_xlabel_on', False))},
                    'bottom': {'spine': _get_spine_visible(ec_ax, 'bottom'), 'ticks': ec_ax.xaxis._major_tick_kw.get('tick2On', True), 
                               'minor': bool(ec_ax.xaxis._minor_tick_kw.get('tick2On', False)), 
                               'labels': ec_ax.xaxis._major_tick_kw.get('label2On', True), 
                               'title': bool(ec_ax.get_xlabel())},
                    'left':   {'spine': _get_spine_visible(ec_ax, 'left'), 'ticks': ec_ax.yaxis._major_tick_kw.get('tick1On', False), 
                               'minor': bool(ec_ax.yaxis._minor_tick_kw.get('tick1On', False)), 
                               'labels': ec_ax.yaxis._major_tick_kw.get('label1On', False), 
                               'title': bool(ec_ax.get_ylabel())},
                    'right':  {'spine': _get_spine_visible(ec_ax, 'right'), 'ticks': ec_ax.yaxis._major_tick_kw.get('tick2On', True), 
                               'minor': bool(ec_ax.yaxis._minor_tick_kw.get('tick2On', False)), 
                               'labels': ec_ax.yaxis._major_tick_kw.get('label2On', True), 
                               'title': bool(ec_ax.get_ylabel())},
                }
            else:
                ec_wasd = None
            # Visibility states
            cb_visible = bool(cbar.ax.get_visible())
            ec_visible = bool(ec_ax.get_visible()) if ec_ax is not None else None
            # Label pads (save current labelpad values to restore later)
            op_labelpads = {
                'x': getattr(ax.xaxis, 'labelpad', None),
                'y': getattr(ax.yaxis, 'labelpad', None),
            }
            ec_labelpads = None
            if ec_ax is not None:
                ec_labelpads = {
                    'x': getattr(ec_ax.xaxis, 'labelpad', None),
                    'y': getattr(ec_ax.yaxis, 'labelpad', None),
                }
            state_history.append({
                'note': note,
                'fig_size': (fig_w, fig_h),
                'geom': (cb_w_in_s, cb_gap_in_s, ec_gap_in_s, ec_w_in_s, ax_w_in_s, ax_h_in_s),
                'op_xlim': op_xlim, 'op_ylim': op_ylim,
                'ec_xlim': ec_xlim, 'ec_ylim': ec_ylim,
                'clim': clim, 'cmap': cmap_name,
                'ec_mode': mode,
                'ions_abs': (np.array(ions_abs, float) if ions_abs is not None else None),
                'prev_ec_xlim': prev_xlim,
                'ions_expanded': bool(ions_expanded),
                'saved_time_ylim': saved_time_ylim,
                'op_labels': dict(op_labels) if isinstance(op_labels, dict) else {'x': ax.get_xlabel(), 'y': ax.get_ylabel()},
                'ec_labels': dict(ec_labels) if ec_labels is not None and isinstance(ec_labels, dict) else None,
                'font': {'family': list(fam), 'size': fsize},
                'op_wasd': dict(op_wasd),
                'ec_wasd': dict(ec_wasd) if ec_wasd is not None else None,
                'tick_lengths': getattr(fig, '_tick_lengths', None),
                'tick_direction': getattr(fig, '_tick_direction', 'out'),
                'cb_visible': cb_visible,
                'ec_visible': ec_visible,
                'op_labelpads': dict(op_labelpads),
                'ec_labelpads': dict(ec_labelpads) if ec_labelpads is not None else None,
            })
            if len(state_history) > 40:
                state_history.pop(0)
        except Exception as e:
            print(f"Warning: snapshot failed: {e}")
    def _restore():
        if not state_history:
            print("No undo history."); return
        snap = state_history.pop()
        try:
            # Canvas size
            try:
                W, H = snap['fig_size']
                fig.set_size_inches(max(1.0, float(W)), max(1.0, float(H)), forward=True)
            except Exception:
                pass
            # Geometry inches
            try:
                cb_w_i, cb_gap_i, ec_gap_i, ec_w_i, ax_w_i, ax_h_i = snap['geom']
                _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, float(ax_w_i), float(ax_h_i), float(cb_w_i), float(cb_gap_i), float(ec_gap_i), float(ec_w_i))
            except Exception:
                pass
            # Labels
            try:
                op_l = snap.get('op_labels', {})
                ax.set_xlabel(op_l.get('x') or ax.get_xlabel() or '')
                ax.set_ylabel(op_l.get('y') or ax.get_ylabel() or '')
            except Exception:
                pass
            try:
                ec_l = snap.get('ec_labels', {})
                if ec_ax is not None and ec_l:
                    ec_ax.set_xlabel(ec_l.get('x') or ec_ax.get_xlabel() or '')
            except Exception:
                pass
            # Fonts - use set_fonts to properly update all labels including label2
            try:
                font = snap.get('font', {})
                fam = font.get('family')
                size = font.get('size')
                if fam or size is not None:
                    # Convert family list back to string
                    if isinstance(fam, list) and fam:
                        fam = fam[0]
                    set_fonts(family=fam if fam else None, size=size if size is not None else None)
            except Exception:
                pass
            # Operando axes and image
            try:
                ax.set_xlim(*snap['op_xlim']); ax.set_ylim(*snap['op_ylim'])
            except Exception:
                pass
            try:
                if snap.get('clim') is not None:
                    lo, hi = snap['clim']; im.set_clim(float(lo), float(hi))
            except Exception:
                pass
            try:
                if snap.get('cmap'):
                    im.set_cmap(snap['cmap'])
                    if cbar is not None:
                        cbar.update_normal(im)
            except Exception:
                pass
            # EC axes
            try:
                if ec_ax is not None:
                    ec_ax.set_xlim(*snap['ec_xlim']); ec_ax.set_ylim(*snap['ec_ylim'])
            except Exception:
                pass
            # EC y-mode
            try:
                if ec_ax is None:
                    pass  # Skip EC mode restoration when no EC panel
                else:
                    mode = snap.get('ec_mode', 'time')
                    if mode == 'ions':
                        setattr(ec_ax, '_ec_y_mode', 'ions')
                        ions_abs = snap.get('ions_abs')
                        if ions_abs is not None:
                            setattr(ec_ax, '_ions_abs', np.asarray(ions_abs, float))
                        # Minimal re-install of ions formatter similar to ey handler
                        t = np.asarray(getattr(ec_ax, '_ec_time_h', []), float)
                        def _fmt_ions(y, pos):
                            try:
                                arr = getattr(ec_ax, '_ions_abs', None)
                                if arr is None or t.size == 0:
                                    return f"{y:.6g}"
                                val = float(np.interp(y, t, arr, left=arr[0], right=arr[-1]))
                                s = ("%f" % val).rstrip('0').rstrip('.')
                                return s
                            except Exception:
                                return ""
                        ec_ax.yaxis.set_major_formatter(FuncFormatter(_fmt_ions))
                        try:
                            ec_ax.set_ylabel(snap.get('ec_labels',{}).get('y_ions') or 'Number of ions')
                        except Exception:
                            pass
                        # Restore label positions and right ticks
                        try:
                            ec_ax.yaxis.tick_right(); ec_ax.yaxis.set_label_position('right')
                        except Exception:
                            pass
                        # Restore xlim adjustments used in ions mode if present
                        prev_xlim = snap.get('prev_ec_xlim')
                        ions_exp = bool(snap.get('ions_expanded', False))
                        if prev_xlim and not ions_exp:
                            try:
                                ec_ax.set_xlim(*prev_xlim)
                            except Exception:
                                pass
                        elif ions_exp and prev_xlim:
                            try:
                                ec_ax.set_xlim(*prev_xlim)
                            except Exception:
                                pass
                    else:
                        setattr(ec_ax, '_ec_y_mode', 'time')
                        from matplotlib.ticker import ScalarFormatter
                        ec_ax.yaxis.set_major_formatter(ScalarFormatter())
                        try:
                            ec_ax.set_ylabel(snap.get('ec_labels',{}).get('y_time') or 'Time (h)')
                        except Exception:
                            pass
                        try:
                            ec_ax.yaxis.tick_right(); ec_ax.yaxis.set_label_position('right')
                        except Exception:
                            pass
                        st_ylim = snap.get('saved_time_ylim')
                        if st_ylim and isinstance(st_ylim,(list,tuple)) and len(st_ylim)==2:
                            try:
                                ec_ax.set_ylim(*st_ylim)
                            except Exception:
                                pass
            except Exception:
                pass
            # Restore WASD state for both panes
            try:
                op_wasd = snap.get('op_wasd')
                ec_wasd = snap.get('ec_wasd')
                if op_wasd:
                    for side in ['top', 'bottom', 'left', 'right']:
                        st = op_wasd.get(side, {})
                        # Spine
                        sp = ax.spines.get(side)
                        if sp and 'spine' in st:
                            sp.set_visible(bool(st['spine']))
                        # Ticks, minor, labels - only for available sides (aws for operando)
                        if side in ['top', 'bottom']:  # w/s - both panes control
                            tick_key = 'tick1On' if side == 'top' else 'tick2On'
                            label_key = 'label1On' if side == 'top' else 'label2On'
                            if 'ticks' in st:
                                ax.tick_params(axis='x', which='major', **{tick_key: bool(st['ticks'])})
                            if 'minor' in st:
                                ax.tick_params(axis='x', which='minor', **{tick_key: bool(st['minor'])})
                            if 'labels' in st:
                                ax.tick_params(axis='x', which='major', **{label_key: bool(st['labels'])})
                        elif side == 'left':  # a - only operando controls
                            if 'ticks' in st:
                                ax.tick_params(axis='y', which='major', left=bool(st['ticks']), right=False)
                            if 'minor' in st:
                                ax.tick_params(axis='y', which='minor', left=bool(st['minor']), right=False)
                            if 'labels' in st:
                                ax.tick_params(axis='y', which='major', labelleft=bool(st['labels']), labelright=False)
                        # Title restoration
                        if side == 'top' and 'title' in st:
                            setattr(ax, '_top_xlabel_on', bool(st['title']))
                        elif side == 'right' and 'title' in st:
                            setattr(ax, '_right_ylabel_on', bool(st['title']))
                if ec_wasd and ec_ax is not None:
                    for side in ['top', 'bottom', 'left', 'right']:
                        st = ec_wasd.get(side, {})
                        # Spine
                        sp = ec_ax.spines.get(side)
                        if sp and 'spine' in st:
                            sp.set_visible(bool(st['spine']))
                        # Ticks, minor, labels - only for available sides (wsd for EC)
                        if side in ['top', 'bottom']:  # w/s - both panes control
                            tick_key = 'tick1On' if side == 'top' else 'tick2On'
                            label_key = 'label1On' if side == 'top' else 'label2On'
                            if 'ticks' in st:
                                ec_ax.tick_params(axis='x', which='major', **{tick_key: bool(st['ticks'])})
                            if 'minor' in st:
                                ec_ax.tick_params(axis='x', which='minor', **{tick_key: bool(st['minor'])})
                            if 'labels' in st:
                                ec_ax.tick_params(axis='x', which='major', **{label_key: bool(st['labels'])})
                        elif side == 'right':  # d - only EC controls
                            if 'ticks' in st:
                                ec_ax.tick_params(axis='y', which='major', left=False, right=bool(st['ticks']))
                            if 'minor' in st:
                                ec_ax.tick_params(axis='y', which='minor', left=False, right=bool(st['minor']))
                            if 'labels' in st:
                                ec_ax.tick_params(axis='y', which='major', labelleft=False, labelright=bool(st['labels']))
                        # Title restoration
                        if side == 'top' and 'title' in st:
                            setattr(ec_ax, '_top_xlabel_on', bool(st['title']))
                        elif side == 'right' and 'title' in st:
                            # EC right title is actual ylabel, not duplicate
                            if bool(st['title']):
                                # Keep existing ylabel or restore from ec_labels
                                pass  # ylabel already restored above
                            else:
                                # Hide ylabel
                                ec_ax.set_ylabel('')
                # Re-position titles using UI module functions
                try:
                    # Build current tick state dict for UI functions
                    op_tick_state = {}
                    ec_tick_state = {}
                    if op_wasd:
                        for side in ['top', 'bottom', 'left', 'right']:
                            st = op_wasd.get(side, {})
                            # Map to tick_state dict format
                            if side == 'top':
                                op_tick_state['t_ticks'] = st.get('ticks', False)
                                op_tick_state['t_labels'] = st.get('labels', False)
                            elif side == 'bottom':
                                op_tick_state['b_ticks'] = st.get('ticks', True)
                                op_tick_state['b_labels'] = st.get('labels', True)
                            elif side == 'left':
                                op_tick_state['l_ticks'] = st.get('ticks', True)
                                op_tick_state['l_labels'] = st.get('labels', True)
                            elif side == 'right':
                                op_tick_state['r_ticks'] = st.get('ticks', False)
                                op_tick_state['r_labels'] = st.get('labels', False)
                    if ec_wasd:
                        for side in ['top', 'bottom', 'left', 'right']:
                            st = ec_wasd.get(side, {})
                            if side == 'top':
                                ec_tick_state['t_ticks'] = st.get('ticks', False)
                                ec_tick_state['t_labels'] = st.get('labels', False)
                            elif side == 'bottom':
                                ec_tick_state['b_ticks'] = st.get('ticks', True)
                                ec_tick_state['b_labels'] = st.get('labels', True)
                            elif side == 'left':
                                ec_tick_state['l_ticks'] = st.get('ticks', False)
                                ec_tick_state['l_labels'] = st.get('labels', False)
                            elif side == 'right':
                                ec_tick_state['r_ticks'] = st.get('ticks', True)
                                ec_tick_state['r_labels'] = st.get('labels', True)
                    # Position titles
                    _ui_position_top_xlabel(ax, fig, op_tick_state)
                    _ui_position_top_xlabel(ec_ax, fig, ec_tick_state)
                    _ui_position_right_ylabel(ax, fig, op_tick_state)
                    # EC right ylabel uses actual ylabel, not duplicate artist
                    # Hide duplicate artist if present
                    if hasattr(ec_ax, '_right_ylabel_artist') and ec_ax._right_ylabel_artist:
                        ec_ax._right_ylabel_artist.set_visible(False)
                except Exception:
                    pass
            except Exception:
                pass
            # Restore tick lengths
            try:
                tick_lengths = snap.get('tick_lengths')
                if tick_lengths and isinstance(tick_lengths, dict):
                    major = tick_lengths.get('major')
                    minor = tick_lengths.get('minor')
                    if major is not None:
                        ax.tick_params(axis='both', which='major', length=major)
                        ec_ax.tick_params(axis='both', which='major', length=major)
                    if minor is not None:
                        ax.tick_params(axis='both', which='minor', length=minor)
                        ec_ax.tick_params(axis='both', which='minor', length=minor)
                    fig._tick_lengths = tick_lengths
            except Exception:
                pass
            # Restore tick direction
            try:
                tick_dir = snap.get('tick_direction', 'out')
                ax.tick_params(axis='both', which='both', direction=tick_dir)
                ec_ax.tick_params(axis='both', which='both', direction=tick_dir)
                fig._tick_direction = tick_dir
            except Exception:
                pass
            # Restore visibility states
            try:
                cb_vis = snap.get('cb_visible')
                if cb_vis is not None:
                    cbar.ax.set_visible(bool(cb_vis))
            except Exception:
                pass
            try:
                ec_vis = snap.get('ec_visible')
                if ec_vis is not None and ec_ax is not None:
                    ec_ax.set_visible(bool(ec_vis))
            except Exception:
                pass
            # Restore label pads (critical for maintaining title positions)
            try:
                op_pads = snap.get('op_labelpads', {})
                if op_pads:
                    if op_pads.get('x') is not None:
                        ax.xaxis.labelpad = op_pads['x']
                    if op_pads.get('y') is not None:
                        ax.yaxis.labelpad = op_pads['y']
            except Exception:
                pass
            try:
                ec_pads = snap.get('ec_labelpads', {})
                if ec_pads and ec_ax is not None:
                    if ec_pads.get('x') is not None:
                        ec_ax.xaxis.labelpad = ec_pads['x']
                    if ec_pads.get('y') is not None:
                        ec_ax.yaxis.labelpad = ec_pads['y']
            except Exception:
                pass
            try:
                fig.canvas.draw()
            except Exception:
                fig.canvas.draw_idle()
            print("Undo: restored previous state.")
        except Exception as e:
            print(f"Undo failed: {e}")
    cross = {
        'active': False,
        'vline': None, 'hline': None,
        'cid': None,
    }
    def _intensity_at(x: float, y: float):
        try:
            arr = np.asarray(im.get_array(), dtype=float)
            if arr.ndim != 2 or arr.size == 0:
                return None
            H, W = arr.shape
            x0, x1, y0, y1 = im.get_extent()
            xmin, xmax = (x0, x1) if x0 <= x1 else (x1, x0)
            ymin, ymax = (y0, y1) if y0 <= y1 else (y1, y0)
            if not (xmin <= x <= xmax and ymin <= y <= ymax):
                return None
            c = int(round((x - xmin) / (xmax - xmin) * (W - 1))) if xmax > xmin else 0
            r = int(round((y - ymin) / (ymax - ymin) * (H - 1))) if ymax > ymin else 0
            r = max(0, min(H - 1, r)); c = max(0, min(W - 1, c))
            val = arr[r, c]
            return float(val) if np.isfinite(val) else None
        except Exception:
            return None
    def _toggle_crosshair():
        if not cross['active']:
            try:
                # Create unified crosshair lines spanning the entire figure (same style as XY mode)
                import matplotlib.lines
                import matplotlib.pyplot as mpl_plt
                vline = fig.add_artist(matplotlib.lines.Line2D([0.5, 0.5], [0, 1], transform=fig.transFigure,
                                                   color='0.35', ls='--', lw=0.8, alpha=0.85, zorder=9999))
                hline = fig.add_artist(matplotlib.lines.Line2D([0, 1], [0.5, 0.5], transform=fig.transFigure,
                                                   color='0.35', ls='--', lw=0.8, alpha=0.85, zorder=9999))
                # Create text annotations for coordinates
                coord_text = fig.text(0.02, 0.98, '', transform=fig.transFigure, 
                                     verticalalignment='top', 
                                     fontsize=max(9, int(0.6 * mpl_plt.rcParams.get('font.size', 12))),
                                     color='0.15',
                                     bbox=dict(boxstyle='round,pad=0.25', fc='white', ec='0.7', alpha=0.8))
            except Exception as e:
                print(f"Failed to create crosshair: {e}")
                import traceback
                traceback.print_exc()
                return
            def on_move(ev):
                if ev.inaxes not in (ax, ec_ax):
                    return
                try:
                    # Update crosshair position based on mouse in figure coordinates
                    if ev.x is not None and ev.y is not None:
                        # Convert mouse position to figure coordinates (0-1)
                        fig_x = ev.x / fig.bbox.width
                        fig_y = ev.y / fig.bbox.height
                        vline.set_xdata([fig_x, fig_x])
                        hline.set_ydata([fig_y, fig_y])
                        
                        # ALWAYS get data coordinates for BOTH axes regardless of where mouse is
                        texts = []
                        
                        # Get operando coordinates with intensity (z)
                        try:
                            op_point = ax.transData.inverted().transform((ev.x, ev.y))
                            xlim = ax.get_xlim()
                            ylim = ax.get_ylim()
                            
                            # Get intensity value at this position from the image
                            z_val = None
                            try:
                                # Get the array from the image
                                arr = im.get_array()
                                extent = im.get_extent()  # (left, right, bottom, top)
                                
                                # Map data coordinates to array indices
                                if extent is not None and arr is not None:
                                    x_data, y_data = op_point[0], op_point[1]
                                    left, right, bottom, top = extent
                                    
                                    # Calculate normalized position (0-1)
                                    x_norm = (x_data - left) / (right - left) if right != left else 0.5
                                    y_norm = (y_data - bottom) / (top - bottom) if top != bottom else 0.5
                                    
                                    # Convert to array indices
                                    rows, cols = arr.shape
                                    col_idx = int(x_norm * cols)
                                    row_idx = int((1 - y_norm) * rows)  # Flip y because image origin is top-left
                                    
                                    # Check bounds and get value
                                    if 0 <= row_idx < rows and 0 <= col_idx < cols:
                                        z_val = arr[row_idx, col_idx]
                            except Exception:
                                pass
                            
                            if xlim[0] <= op_point[0] <= xlim[1] and ylim[0] <= op_point[1] <= ylim[1]:
                                if z_val is not None:
                                    texts.append(f"Operando: x={op_point[0]:.4f}, y={op_point[1]:.4f}, z={z_val:.4f}")
                                else:
                                    texts.append(f"Operando: x={op_point[0]:.4f}, y={op_point[1]:.4f}")
                            else:
                                if z_val is not None:
                                    texts.append(f"Operando: x={op_point[0]:.4f}, y={op_point[1]:.4f}, z={z_val:.4f} (out of range)")
                                else:
                                    texts.append(f"Operando: x={op_point[0]:.4f}, y={op_point[1]:.4f} (out of range)")
                        except Exception:
                            texts.append("Operando: N/A")
                        
                        # Get EC coordinates (if EC panel exists)
                        if ec_ax is not None:
                            try:
                                ec_point = ec_ax.transData.inverted().transform((ev.x, ev.y))
                                xlim = ec_ax.get_xlim()
                                ylim = ec_ax.get_ylim()
                                if xlim[0] <= ec_point[0] <= xlim[1] and ylim[0] <= ec_point[1] <= ylim[1]:
                                    texts.append(f"EC: x={ec_point[0]:.4f}, y={ec_point[1]:.4f}")
                                else:
                                    texts.append(f"EC: x={ec_point[0]:.4f}, y={ec_point[1]:.4f} (out of range)")
                            except Exception:
                                texts.append("EC: N/A")
                        
                        coord_text.set_text('\n'.join(texts))
                    
                    fig.canvas.draw_idle()
                except Exception:
                    pass
            cid = fig.canvas.mpl_connect('motion_notify_event', on_move)
            cross.update({'active': True, 'vline': vline, 'hline': hline, 'coord_text': coord_text, 'cid': cid})
            # Force immediate drawing so crosshair is visible
            try:
                fig.canvas.draw_idle()
            except Exception:
                pass
            print("Crosshair ON. Move mouse over either pane. Press 'n' again to turn off.")
        else:
            try:
                if cross['cid'] is not None:
                    fig.canvas.mpl_disconnect(cross['cid'])
            except Exception:
                pass
            for k in ('vline', 'hline', 'coord_text'):
                art = cross.get(k)
                if art is not None:
                    try: art.remove()
                    except Exception: pass
            cross.update({'active': False, 'vline': None, 'hline': None, 'coord_text': None, 'cid': None})
            try:
                fig.canvas.draw_idle()
            except Exception:
                pass
            print("Crosshair OFF.")
    while True:
        cmd = input("Press a key: ").strip().lower()
        if not cmd:
            continue
        if cmd == 'q':
            try:
                ans = input("Quit interactive? Remember to save (e=export, s=save). Quit now? (y/n): ").strip().lower()
            except Exception:
                ans = 'y'
            if ans == 'y':
                try:
                    import matplotlib.pyplot as _plt
                    _plt.close(fig)
                except Exception:
                    pass
                break
            else:
                print_menu()
                continue
        if cmd == 'e':
            try:
                import os
                from .utils import list_files_in_subdirectory, get_organized_path, _confirm_overwrite as _co
                # List existing figure files in Figures/ subdirectory
                fig_extensions = ('.svg', '.png', '.jpg', '.jpeg', '.pdf', '.eps', '.tif', '.tiff')
                file_list = list_files_in_subdirectory(fig_extensions, 'figure')
                files = [f[0] for f in file_list]
                if files:
                    print("Existing figure files in Figures/:")
                    for i, f in enumerate(files, 1):
                        print(f"  {i}: {f}")
                
                fname = input("Export filename (default .svg if no extension) or number to overwrite (q=cancel): ").strip()
                if not fname or fname.lower() == 'q':
                    print_menu(); continue
                
                # Check if user selected a number
                already_confirmed = False
                if fname.isdigit() and files:
                    idx = int(fname)
                    if 1 <= idx <= len(files):
                        name = files[idx-1]
                        yn = input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                        if yn != 'y':
                            print_menu(); continue
                        target = file_list[idx-1][1]  # Full path from list
                        already_confirmed = True
                    else:
                        print("Invalid number.")
                        print_menu(); continue
                else:
                    if not os.path.splitext(fname)[1]:
                        fname += '.svg'
                    # Use organized path unless it's an absolute path
                    if os.path.isabs(fname):
                        target = fname
                    else:
                        target = get_organized_path(fname, 'figure')
                
                if not already_confirmed and os.path.exists(target):
                    target = _co(target)
                if not target:
                    print_menu(); continue
                _, ext = os.path.splitext(target)
                if ext.lower() == '.svg':
                    try:
                        _fig_fc = fig.get_facecolor()
                    except Exception:
                        _fig_fc = None
                    try:
                        _ax_fc = ax.get_facecolor()
                    except Exception:
                        _ax_fc = None
                    try:
                        if getattr(fig, 'patch', None) is not None:
                            fig.patch.set_alpha(0.0); fig.patch.set_facecolor('none')
                        if getattr(ax, 'patch', None) is not None:
                            ax.patch.set_alpha(0.0); ax.patch.set_facecolor('none')
                        if getattr(ec_ax, 'patch', None) is not None:
                            ec_ax.patch.set_alpha(0.0); ec_ax.patch.set_facecolor('none')
                    except Exception:
                        pass
                    try:
                        fig.savefig(target, dpi=300, transparent=True, facecolor='none', edgecolor='none')
                    finally:
                        try:
                            if _fig_fc is not None and getattr(fig, 'patch', None) is not None:
                                fig.patch.set_alpha(1.0); fig.patch.set_facecolor(_fig_fc)
                        except Exception:
                            pass
                        try:
                            if _ax_fc is not None and getattr(ax, 'patch', None) is not None:
                                ax.patch.set_alpha(1.0); ax.patch.set_facecolor(_ax_fc)
                        except Exception:
                            pass
                else:
                    fig.savefig(target, dpi=300)
                print(f"Exported figure to {target}")
            except Exception as e:
                print(f"Export failed: {e}")
            print_menu(); continue
        if cmd == 'n':
            try:
                _toggle_crosshair()
            except Exception as e:
                print(f"Error toggling crosshair: {e}")
            print_menu(); continue
        if cmd == 'v':
            # Toggle colorbar and/or EC panel visibility, or change colorbar label mode
            _snapshot("toggle-visibility")
            try:
                if ec_ax is not None:
                    # Dual-panel mode: toggle both colorbar and EC, or change colorbar labels
                    print("Toggle: 1=colorbar, 2=EC panel, 3=both, 4=colorbar labels, q=cancel")
                    choice = input("v> ").strip().lower()
                    if choice == '1':
                        # Toggle colorbar
                        cb_vis = cbar.ax.get_visible()
                        cbar.ax.set_visible(not cb_vis)
                        print(f"Colorbar: {'hidden' if cb_vis else 'shown'}")
                    elif choice == '2':
                        # Toggle EC panel
                        ec_vis = ec_ax.get_visible()
                        ec_ax.set_visible(not ec_vis)
                        print(f"EC panel: {'hidden' if ec_vis else 'shown'}")
                    elif choice == '3':
                        # Toggle both
                        cb_vis = cbar.ax.get_visible()
                        ec_vis = ec_ax.get_visible()
                        new_vis = not (cb_vis and ec_vis)  # Show if either is hidden
                        cbar.ax.set_visible(new_vis)
                        ec_ax.set_visible(new_vis)
                        print(f"Colorbar & EC panel: {'shown' if new_vis else 'hidden'}")
                    elif choice == '4':
                        # Toggle colorbar label mode: normal ticks vs High/Low
                        current_mode = getattr(fig, '_colorbar_label_mode', 'normal')
                        if current_mode == 'normal':
                            # Switch to High/Low mode
                            # Hide tick labels
                            cbar.ax.yaxis.set_ticklabels([])
                            # Add High and Low text labels
                            # Remove existing High/Low labels if any
                            if hasattr(fig, '_cbar_high_text'):
                                try: fig._cbar_high_text.remove()
                                except: pass
                            if hasattr(fig, '_cbar_low_text'):
                                try: fig._cbar_low_text.remove()
                                except: pass
                            # Get current font settings
                            font_size = plt.rcParams.get('font.size', 10)
                            font_family = plt.rcParams.get('font.family', ['sans-serif'])
                            # Add new labels outside the colorbar (above and below)
                            fig._cbar_high_text = cbar.ax.text(0.5, 1.02, 'High', ha='center', va='bottom',
                                                                transform=cbar.ax.transAxes,
                                                                fontsize=font_size, fontfamily=font_family)
                            fig._cbar_low_text = cbar.ax.text(0.5, -0.02, 'Low', ha='center', va='top',
                                                               transform=cbar.ax.transAxes,
                                                               fontsize=font_size, fontfamily=font_family)
                            fig._colorbar_label_mode = 'highlow'
                            print("Colorbar labels: High/Low mode")
                        else:
                            # Switch back to normal tick labels
                            cbar.ax.yaxis.set_ticklabels([])  # Reset to auto
                            cbar.ax.yaxis.set_major_formatter(plt.ScalarFormatter())
                            # Remove High/Low labels
                            if hasattr(fig, '_cbar_high_text'):
                                try: fig._cbar_high_text.remove()
                                except: pass
                                delattr(fig, '_cbar_high_text')
                            if hasattr(fig, '_cbar_low_text'):
                                try: fig._cbar_low_text.remove()
                                except: pass
                                delattr(fig, '_cbar_low_text')
                            fig._colorbar_label_mode = 'normal'
                            print("Colorbar labels: Normal mode")
                    elif choice != 'q':
                        print("Invalid choice")
                else:
                    # Operando-only mode: toggle colorbar or change label mode
                    print("Toggle: 1=colorbar visibility, 2=colorbar labels, q=cancel")
                    choice = input("v> ").strip().lower()
                    if choice == '1':
                        cb_vis = cbar.ax.get_visible()
                        cbar.ax.set_visible(not cb_vis)
                        print(f"Colorbar: {'hidden' if cb_vis else 'shown'}")
                    elif choice == '2':
                        # Toggle colorbar label mode
                        current_mode = getattr(fig, '_colorbar_label_mode', 'normal')
                        if current_mode == 'normal':
                            # Switch to High/Low mode
                            cbar.ax.yaxis.set_ticklabels([])
                            # Remove existing High/Low labels if any
                            if hasattr(fig, '_cbar_high_text'):
                                try: fig._cbar_high_text.remove()
                                except: pass
                            if hasattr(fig, '_cbar_low_text'):
                                try: fig._cbar_low_text.remove()
                                except: pass
                            # Get current font settings
                            font_size = plt.rcParams.get('font.size', 10)
                            font_family = plt.rcParams.get('font.family', ['sans-serif'])
                            # Add new labels outside the colorbar (above and below)
                            fig._cbar_high_text = cbar.ax.text(0.5, 1.02, 'High', ha='center', va='bottom',
                                                                transform=cbar.ax.transAxes,
                                                                fontsize=font_size, fontfamily=font_family)
                            fig._cbar_low_text = cbar.ax.text(0.5, -0.02, 'Low', ha='center', va='top',
                                                               transform=cbar.ax.transAxes,
                                                               fontsize=font_size, fontfamily=font_family)
                            fig._colorbar_label_mode = 'highlow'
                            print("Colorbar labels: High/Low mode")
                        else:
                            # Switch back to normal
                            cbar.ax.yaxis.set_ticklabels([])
                            cbar.ax.yaxis.set_major_formatter(plt.ScalarFormatter())
                            if hasattr(fig, '_cbar_high_text'):
                                try: fig._cbar_high_text.remove()
                                except: pass
                                delattr(fig, '_cbar_high_text')
                            if hasattr(fig, '_cbar_low_text'):
                                try: fig._cbar_low_text.remove()
                                except: pass
                                delattr(fig, '_cbar_low_text')
                            fig._colorbar_label_mode = 'normal'
                            print("Colorbar labels: Normal mode")
                    elif choice != 'q':
                        print("Invalid choice")
                fig.canvas.draw_idle()
            except Exception as e:
                print(f"Error toggling visibility: {e}")
            print_menu(); continue
        if cmd == 'b':
            _restore(); print_menu(); continue
        if cmd == 's':
            try:
                from .session import dump_operando_session
                import os
                folder = os.getcwd()
                try:
                    files = sorted([f for f in os.listdir(folder) if f.lower().endswith('.pkl')])
                except Exception:
                    files = []
                if files:
                    print("Existing .pkl files:")
                    for i, f in enumerate(files, 1):
                        print(f"  {i}: {f}")
                choice = input("Enter new filename or number to overwrite (q=cancel): ").strip()
                if not choice or choice.lower() == 'q':
                    print_menu(); continue
                if choice.isdigit() and files:
                    idx = int(choice)
                    if 1 <= idx <= len(files):
                        name = files[idx-1]
                        yn = input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                        if yn != 'y':
                            print_menu(); continue
                        target = os.path.join(folder, name)
                    else:
                        print("Invalid number.")
                        print_menu(); continue
                else:
                    name = choice
                    root, ext = os.path.splitext(name)
                    if ext == '':
                        name = name + '.pkl'
                    target = name if os.path.isabs(name) else os.path.join(folder, name)
                    if os.path.exists(target):
                        yn = input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
                        if yn != 'y':
                            print_menu(); continue
                dump_operando_session(target, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax, skip_confirm=True)
            except Exception as e:
                print(f"Save failed: {e}")
            print_menu(); continue
        if cmd == 'h':
            # Always read fresh value from attribute to avoid stale cached value
            ax_h_in = getattr(ax, '_fixed_ax_h_in', ax_h_in)
            print(f"Current height: {ax_h_in:.2f} in")
            val = input("New height (inches): ").strip()
            if val:
                _snapshot("height")
                try:
                    new_h = max(0.25, float(val))
                    ax_h_in = new_h
                    _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)
                except Exception as e:
                    print(f"Invalid height: {e}")
            print_menu()
        elif cmd == 'r':
            _snapshot("reverse")
            # Reverse vertical orientation for both operando and EC plots
            try:
                y0, y1 = ax.get_ylim()
                ax.set_ylim(y1, y0)
            except Exception as e:
                print(f"Operando reverse failed: {e}")
            try:
                ey0, ey1 = ec_ax.get_ylim()
                ec_ax.set_ylim(ey1, ey0)
                # If we have a stored time ylim for restoration later, invert it too
                if hasattr(ec_ax, '_saved_time_ylim') and isinstance(ec_ax._saved_time_ylim, (tuple, list)) and len(ec_ax._saved_time_ylim)==2:
                    lo, hi = ec_ax._saved_time_ylim
                    try:
                        ec_ax._saved_time_ylim = (hi, lo)
                    except Exception:
                        pass
                fig.canvas.draw_idle()
            except Exception as e:
                print(f"EC reverse failed: {e}")
            print_menu()
        elif cmd == 'f':
            # Font submenu with numbered options
            cur_family = plt.rcParams.get('font.sans-serif', [''])[0]
            cur_size = plt.rcParams.get('font.size', None)
            print(f"\nFont submenu (current: family='{cur_family}', size={cur_size})")
            print("  f: change family  |  s: change size  |  q: back")
            while True:
                sub = input("Font> ").strip().lower()
                if not sub:
                    continue
                if sub == 'q':
                    break
                if sub == 'f':
                    # Common font families with numbered options
                    fonts = ['Arial', 'DejaVu Sans', 'Helvetica', 'Liberation Sans', 
                             'Times New Roman', 'Courier New', 'Verdana', 'Tahoma']
                    print("\nCommon font families:")
                    for i, font in enumerate(fonts, 1):
                        print(f"  {i}: {font}")
                    print("Or enter custom font name directly.")
                    choice = input("Font family (number or name): ").strip()
                    if not choice:
                        continue
                    _snapshot("font-family")
                    # Check if it's a number
                    if choice.isdigit():
                        idx = int(choice)
                        if 1 <= idx <= len(fonts):
                            fam = fonts[idx-1]
                            set_fonts(family=fam)
                            print(f"Applied font family: {fam}")
                        else:
                            print("Invalid number.")
                    else:
                        # Use as custom font name
                        set_fonts(family=choice)
                        print(f"Applied font family: {choice}")
                elif sub == 's':
                    # Show current size and accept direct input
                    cur_size = plt.rcParams.get('font.size', None)
                    choice = input(f"Font size (current: {cur_size}): ").strip()
                    if not choice:
                        continue
                    _snapshot("font-size")
                    try:
                        sz = float(choice)
                        if sz > 0:
                            set_fonts(size=sz)
                            print(f"Applied font size: {sz}")
                        else:
                            print("Size must be positive.")
                    except Exception:
                        print("Invalid size.")
            print_menu()
        elif cmd == 'l':
            # Line widths submenu for both operando and EC panes
            print("Line widths: set frame (spines) and tick widths for both operando and EC")
            print(_colorize_inline_commands("Enter frame/tick width (e.g., '1.5' or 'f t' for frame/tick separately)"))
            print("Format examples:")
            print(_colorize_inline_commands("  1.5      - set both frame and ticks to 1.5"))
            print(_colorize_inline_commands("  1.5 2.5  - set frame=1.5, ticks=2.5"))
            print(_colorize_inline_commands("  q        - cancel"))
            
            inp = input("Line widths> ").strip().lower()
            if not inp or inp == 'q':
                print_menu()
                continue
            
            _snapshot("line-widths")
            try:
                parts = inp.split()
                if len(parts) == 1:
                    # Single value: apply to both frame and ticks
                    val = float(parts[0])
                    frame_w = tick_w = max(0.1, val)
                elif len(parts) == 2:
                    # Two values: frame and tick
                    frame_w = max(0.1, float(parts[0]))
                    tick_w = max(0.1, float(parts[1]))
                else:
                    print("Invalid format. Use 1 or 2 numbers.")
                    print_menu()
                    continue
                
                # Apply to operando pane (ax)
                for spine in ax.spines.values():
                    spine.set_linewidth(frame_w)
                ax.tick_params(axis='both', which='major', width=tick_w)
                ax.tick_params(axis='both', which='minor', width=tick_w)
                
                # Apply to EC pane (ec_ax)
                for spine in ec_ax.spines.values():
                    spine.set_linewidth(frame_w)
                ec_ax.tick_params(axis='both', which='major', width=tick_w)
                ec_ax.tick_params(axis='both', which='minor', width=tick_w)
                
                # Also apply to colorbar if present
                if cbar is not None:
                    try:
                        for spine in cbar.ax.spines.values():
                            spine.set_linewidth(frame_w)
                        cbar.ax.tick_params(axis='both', which='major', width=tick_w)
                        cbar.ax.tick_params(axis='both', which='minor', width=tick_w)
                    except Exception:
                        pass
                
                try:
                    fig.canvas.draw()
                except Exception:
                    fig.canvas.draw_idle()
                
                print(f"Applied: frame={frame_w:.2f}, ticks={tick_w:.2f} to operando, EC, and colorbar")
            except ValueError:
                print("Invalid number format.")
            except Exception as e:
                print(f"Error: {e}")
            
            print_menu()
        elif cmd == 't':
            # Unified WASD ticks/labels/spines submenu for either pane
            # Import here to avoid scoping issues with nested functions
            from matplotlib.ticker import AutoMinorLocator, NullFormatter, MaxNLocator
            
            def _get_tick_state(a):
                # Unified keys with fallbacks for legacy combined flags
                base = getattr(a, '_saved_tick_state', None)
                if isinstance(base, dict):
                    return base
                return {
                    'bx': True, 'tx': False,
                    'ly': True, 'ry': False,
                    'mbx': False, 'mtx': False,
                    'mly': False, 'mry': False,
                    'b_ticks': True, 'b_labels': True,
                    't_ticks': False, 't_labels': False,
                    'l_ticks': True, 'l_labels': True,
                    'r_ticks': False, 'r_labels': False,
                }
            def _set_spine_visible(axis, which: str, visible: bool):
                sp = axis.spines.get(which)
                if sp is not None:
                    try:
                        sp.set_visible(bool(visible))
                    except Exception:
                        pass
            def _get_spine_visible(axis, which: str) -> bool:
                sp = axis.spines.get(which)
                try:
                    return bool(sp.get_visible()) if sp is not None else False
                except Exception:
                    return False
            def _update_tick_visibility(axis, ts: dict):
                axis.tick_params(axis='x',
                                 bottom=ts['bx'], labelbottom=ts['bx'],
                                 top=ts['tx'],    labeltop=ts['tx'])
                axis.tick_params(axis='y',
                                 left=ts['ly'],  labelleft=ts['ly'],
                                 right=ts['ry'], labelright=ts['ry'])
                # Minor ticks X
                if ts.get('mbx') or ts.get('mtx'):
                    try:
                        axis.xaxis.set_minor_locator(AutoMinorLocator())
                        axis.xaxis.set_minor_formatter(NullFormatter())
                        axis.tick_params(axis='x', which='minor',
                                         bottom=ts.get('mbx', False),
                                         top=ts.get('mtx', False),
                                         labelbottom=False, labeltop=False)
                    except Exception:
                        pass
                else:
                    axis.tick_params(axis='x', which='minor', bottom=False, top=False, labelbottom=False, labeltop=False)
                # Minor ticks Y
                if ts.get('mly') or ts.get('mry'):
                    try:
                        axis.yaxis.set_minor_locator(AutoMinorLocator())
                        axis.yaxis.set_minor_formatter(NullFormatter())
                        axis.tick_params(axis='y', which='minor',
                                         left=ts.get('mly', False),
                                         right=ts.get('mry', False),
                                         labelleft=False, labelright=False)
                    except Exception:
                        pass
                else:
                    axis.tick_params(axis='y', which='minor', left=False, right=False, labelleft=False, labelright=False)
                try:
                    axis._saved_tick_state = dict(ts)
                except Exception:
                    pass
            def _apply_nice_ticks_axis(axis):
                try:
                    if (getattr(axis, 'get_xscale', None) and axis.get_xscale() == 'linear'):
                        axis.xaxis.set_major_locator(MaxNLocator(nbins='auto', steps=[1, 2, 5], min_n_ticks=4))
                    if (getattr(axis, 'get_yscale', None) and axis.get_yscale() == 'linear'):
                        axis.yaxis.set_major_locator(MaxNLocator(nbins='auto', steps=[1, 2, 5], min_n_ticks=4))
                except Exception:
                    pass
            while True:
                if ec_ax is not None:
                    print(_colorize_inline_commands("Choose pane: o=operando, e=ec, q=back"))
                else:
                    print(_colorize_inline_commands("Choose pane: o=operando, q=back"))
                pane = input("ot> ").strip().lower()
                if not pane:
                    continue
                if pane == 'q':
                    break
                if ec_ax is None and pane == 'e':
                    print("EC panel not available (no .mpt file in folder).")
                    continue
                target = ax if pane == 'o' else (ec_ax if pane == 'e' else None)
                if target is None:
                    print("Unknown pane."); continue
                base_xlabel = target.get_xlabel() or ''
                base_ylabel = target.get_ylabel() or ''
                ts = _get_tick_state(target)
                
                # Read actual current tick visibility from matplotlib (more reliable than saved state)
                def _get_actual_tick_visibility(axis):
                    try:
                        # Get a sample tick to check visibility
                        xticks = axis.xaxis.get_major_ticks()
                        yticks = axis.yaxis.get_major_ticks()
                        return {
                            'bottom': bool(xticks[0].tick1line.get_visible()) if xticks else True,
                            'top': bool(xticks[0].tick2line.get_visible()) if xticks else False,
                            'left': bool(yticks[0].tick1line.get_visible()) if yticks else True,
                            'right': bool(yticks[0].tick2line.get_visible()) if yticks else False,
                            'bottom_labels': bool(xticks[0].label1.get_visible()) if xticks else True,
                            'top_labels': bool(xticks[0].label2.get_visible()) if xticks else False,
                            'left_labels': bool(yticks[0].label1.get_visible()) if yticks else True,
                            'right_labels': bool(yticks[0].label2.get_visible()) if yticks else False,
                        }
                    except Exception:
                        return None
                
                actual = _get_actual_tick_visibility(target)
                
                # Build WASD state based on actual current state (not just saved state)
                wasd = {
                    'top':    {'spine': _get_spine_visible(target, 'top'),    
                               'ticks': bool(actual['top']) if actual else bool(ts.get('t_ticks', ts.get('tx', False))), 
                               'minor': bool(ts.get('mtx', False)), 
                               'labels': bool(actual['top_labels']) if actual else bool(ts.get('t_labels', ts.get('tx', False))), 
                               'title': bool(getattr(target, '_top_xlabel_on', False))},
                    'bottom': {'spine': _get_spine_visible(target, 'bottom'), 
                               'ticks': bool(actual['bottom']) if actual else bool(ts.get('b_ticks', ts.get('bx', True))),  
                               'minor': bool(ts.get('mbx', False)), 
                               'labels': bool(actual['bottom_labels']) if actual else bool(ts.get('b_labels', ts.get('bx', True))),  
                               'title': bool(target.get_xlabel())},
                    'left':   {'spine': _get_spine_visible(target, 'left'),   
                               'ticks': bool(actual['left']) if actual else bool(ts.get('l_ticks', ts.get('ly', True))),  
                               'minor': bool(ts.get('mly', False)), 
                               'labels': bool(actual['left_labels']) if actual else bool(ts.get('l_labels', ts.get('ly', True))),  
                               'title': bool(target.get_ylabel())},
                    'right':  {'spine': _get_spine_visible(target, 'right'),  
                               'ticks': bool(actual['right']) if actual else bool(ts.get('r_ticks', ts.get('ry', False))), 
                               'minor': bool(ts.get('mry', False)), 
                               'labels': bool(actual['right_labels']) if actual else bool(ts.get('r_labels', ts.get('ry', False))), 
                               'title': bool(target.get_ylabel()) if target is ec_ax else bool(getattr(target, '_right_ylabel_on', False))},
                }
                def _apply_wasd_axis(axis, wasd_state, changed_sides=None):
                    # Determine which sides are available for this pane
                    is_ec = (axis is ec_ax)
                    is_operando = (axis is ax)
                    
                    # If changed_sides is None, reposition all sides (for load style, etc.)
                    # If changed_sides is an empty set, don't reposition anything (e.g., spine/tick toggles)
                    if changed_sides is None:
                        changed_sides = {'bottom', 'top', 'left', 'right'}
                    
                    # Spines - only apply available sides
                    for name in ('top','bottom','left','right'):
                        if is_ec and name == 'left':
                            continue  # Don't touch left spine for EC panel
                        if is_operando and name == 'right' and ec_ax is not None:
                            continue  # Don't touch right spine for operando panel ONLY if EC panel exists
                        _set_spine_visible(axis, name, bool(wasd_state[name]['spine']))
                    
                    # Major ticks & labels for X axis (top/bottom)
                    axis.tick_params(axis='x', top=bool(wasd_state['top']['ticks']), bottom=bool(wasd_state['bottom']['ticks']),
                                     labeltop=bool(wasd_state['top']['labels']), labelbottom=bool(wasd_state['bottom']['labels']))
                    
                    # Major ticks & labels for Y axis - only apply available sides
                    if is_ec:
                        # EC panel: only control right side, leave left alone
                        axis.tick_params(axis='y', right=bool(wasd_state['right']['ticks']),
                                         labelright=bool(wasd_state['right']['labels']))
                    elif is_operando and ec_ax is not None:
                        # Operando panel with EC: only control left side, leave right alone
                        axis.tick_params(axis='y', left=bool(wasd_state['left']['ticks']),
                                         labelleft=bool(wasd_state['left']['labels']))
                    elif is_operando and ec_ax is None:
                        # Operando-only mode: control both left and right sides
                        axis.tick_params(axis='y', left=bool(wasd_state['left']['ticks']), right=bool(wasd_state['right']['ticks']),
                                         labelleft=bool(wasd_state['left']['labels']), labelright=bool(wasd_state['right']['labels']))
                    else:
                        # Fallback: control both sides
                        axis.tick_params(axis='y', left=bool(wasd_state['left']['ticks']), right=bool(wasd_state['right']['ticks']),
                                         labelleft=bool(wasd_state['left']['labels']), labelright=bool(wasd_state['right']['labels']))
                    
                    # Minor ticks X
                    if wasd_state['top']['minor'] or wasd_state['bottom']['minor']:
                        axis.xaxis.set_minor_locator(AutoMinorLocator()); axis.xaxis.set_minor_formatter(NullFormatter())
                    axis.tick_params(axis='x', which='minor', top=bool(wasd_state['top']['minor']), bottom=bool(wasd_state['bottom']['minor']), labeltop=False, labelbottom=False)
                    
                    # Minor ticks Y - only apply available sides
                    if wasd_state['left']['minor'] or wasd_state['right']['minor']:
                        axis.yaxis.set_minor_locator(AutoMinorLocator()); axis.yaxis.set_minor_formatter(NullFormatter())
                    if is_ec:
                        # EC panel: only control right side minor ticks
                        axis.tick_params(axis='y', which='minor', right=bool(wasd_state['right']['minor']), labelright=False)
                    elif is_operando and ec_ax is not None:
                        # Operando panel with EC: only control left side minor ticks
                        axis.tick_params(axis='y', which='minor', left=bool(wasd_state['left']['minor']), labelleft=False)
                    elif is_operando and ec_ax is None:
                        # Operando-only mode: control both left and right side minor ticks
                        axis.tick_params(axis='y', which='minor', left=bool(wasd_state['left']['minor']), right=bool(wasd_state['right']['minor']), labelleft=False, labelright=False)
                    else:
                        # Fallback: control both sides
                        axis.tick_params(axis='y', which='minor', left=bool(wasd_state['left']['minor']), right=bool(wasd_state['right']['minor']), labelleft=False, labelright=False)
                    
                    # Build tick_state dict from current wasd_state for UI functions
                    current_tick_state = {
                        't_labels': bool(wasd_state['top']['labels']),
                        'tx': bool(wasd_state['top']['labels']),
                        'b_labels': bool(wasd_state['bottom']['labels']),
                        'bx': bool(wasd_state['bottom']['labels']),
                        'l_labels': bool(wasd_state['left']['labels']),
                        'ly': bool(wasd_state['left']['labels']),
                        'r_labels': bool(wasd_state['right']['labels']),
                        'ry': bool(wasd_state['right']['labels']),
                    }
                    
                    # Store tick state for future reference
                    axis._saved_tick_state = current_tick_state
                    
                    # X-axis titles (bottom and top)
                    if bool(wasd_state['bottom']['title']):
                        if hasattr(axis,'_stored_xlabel') and isinstance(axis._stored_xlabel,str) and axis._stored_xlabel:
                            axis.set_xlabel(axis._stored_xlabel)
                    else:
                        if not hasattr(axis,'_stored_xlabel'):
                            try: axis._stored_xlabel = axis.get_xlabel()
                            except Exception: axis._stored_xlabel = ''
                        axis.set_xlabel("")
                    
                    axis._top_xlabel_on = bool(wasd_state['top']['title'])
                    
                    # Y-axis titles - only apply for available sides
                    if is_operando and ec_ax is not None:
                        # Operando panel WITH EC: only control left ylabel
                        if bool(wasd_state['left']['title']):
                            if hasattr(axis,'_stored_ylabel') and isinstance(axis._stored_ylabel,str) and axis._stored_ylabel:
                                axis.set_ylabel(axis._stored_ylabel)
                        else:
                            if not hasattr(axis,'_stored_ylabel'):
                                try: axis._stored_ylabel = axis.get_ylabel()
                                except Exception: axis._stored_ylabel = ''
                            axis.set_ylabel("")
                        # Right ylabel is disabled for operando when EC exists
                        axis._right_ylabel_on = False
                    elif is_operando and ec_ax is None:
                        # Operando-only mode: control both left and right ylabels
                        if bool(wasd_state['left']['title']):
                            if hasattr(axis,'_stored_ylabel') and isinstance(axis._stored_ylabel,str) and axis._stored_ylabel:
                                axis.set_ylabel(axis._stored_ylabel)
                        else:
                            if not hasattr(axis,'_stored_ylabel'):
                                try: axis._stored_ylabel = axis.get_ylabel()
                                except Exception: axis._stored_ylabel = ''
                            axis.set_ylabel("")
                        axis._right_ylabel_on = bool(wasd_state['right']['title'])
                    elif is_ec:
                        # EC panel: control the actual ylabel (already positioned right)
                        if bool(wasd_state['right']['title']):
                            if hasattr(axis,'_stored_ylabel') and isinstance(axis._stored_ylabel,str) and axis._stored_ylabel:
                                axis.set_ylabel(axis._stored_ylabel)
                        else:
                            if not hasattr(axis,'_stored_ylabel'):
                                try: axis._stored_ylabel = axis.get_ylabel()
                                except Exception: axis._stored_ylabel = ''
                            axis.set_ylabel("")
                        # Left ylabel is disabled for EC (hide any duplicate artist)
                        # Note: EC uses the actual ylabel which is already on the right side
                    else:
                        # Fallback: control both
                        if bool(wasd_state['left']['title']):
                            if hasattr(axis,'_stored_ylabel') and isinstance(axis._stored_ylabel,str) and axis._stored_ylabel:
                                axis.set_ylabel(axis._stored_ylabel)
                        else:
                            if not hasattr(axis,'_stored_ylabel'):
                                try: axis._stored_ylabel = axis.get_ylabel()
                                except Exception: axis._stored_ylabel = ''
                            axis.set_ylabel("")
                        axis._right_ylabel_on = bool(wasd_state['right']['title'])
                    
                    # Only reposition sides that were actually changed
                    # This prevents unnecessary title movement when toggling unrelated elements
                    if 'bottom' in changed_sides:
                        _ui_position_bottom_xlabel(axis, fig, current_tick_state)
                    if 'top' in changed_sides:
                        _ui_position_top_xlabel(axis, fig, current_tick_state)
                    if 'left' in changed_sides:
                        _ui_position_left_ylabel(axis, fig, current_tick_state)
                    if 'right' in changed_sides:
                        _ui_position_right_ylabel(axis, fig, current_tick_state)
                
                print("WASD toggles: direction (w/a/s/d) x action (1..5)")
                print("  1=spine   2=ticks   3=minor ticks   4=tick labels   5=axis title")
                print("Type 'i' to invert tick direction, 'l' to change tick length, 'list' for state, 'q' to return.")
                while True:
                    cmd2 = input("Toggle> ").strip().lower()
                    if not cmd2:
                        continue
                    if cmd2 == 'q':
                        break
                    if cmd2 == 'i':
                        # Invert tick direction (toggle between 'out' and 'in')
                        push_state("tick-direction")
                        current_dir = getattr(fig, '_tick_direction', 'out')
                        new_dir = 'in' if current_dir == 'out' else 'out'
                        setattr(fig, '_tick_direction', new_dir)
                        ax.tick_params(axis='both', which='both', direction=new_dir)
                        ec_ax.tick_params(axis='both', which='both', direction=new_dir)
                        print(f"Tick direction: {new_dir}")
                        try:
                            fig.canvas.draw()
                        except Exception:
                            fig.canvas.draw_idle()
                        continue
                    if cmd2 == 'l':
                        # Change tick length (major and minor automatically set to 70%)
                        try:
                            # Get current major tick length from axes
                            current_major = ax.xaxis.get_major_ticks()[0].tick1line.get_markersize() if ax.xaxis.get_major_ticks() else 4.0
                            print(f"Current major tick length: {current_major}")
                            new_length_str = input("Enter new major tick length (e.g., 6.0): ").strip()
                            if not new_length_str:
                                continue
                            new_major = float(new_length_str)
                            if new_major <= 0:
                                print("Length must be positive.")
                                continue
                            new_minor = new_major * 0.7  # Auto-set minor to 70%
                            push_state("tick-length")
                            # Apply to all four axes on both ax and ec_ax
                            ax.tick_params(axis='both', which='major', length=new_major)
                            ax.tick_params(axis='both', which='minor', length=new_minor)
                            ec_ax.tick_params(axis='both', which='major', length=new_major)
                            ec_ax.tick_params(axis='both', which='minor', length=new_minor)
                            # Store for persistence
                            if not hasattr(fig, '_tick_lengths'):
                                fig._tick_lengths = {}
                            fig._tick_lengths.update({'major': new_major, 'minor': new_minor})
                            print(f"Set major tick length: {new_major}, minor: {new_minor:.2f}")
                            try:
                                fig.canvas.draw()
                            except Exception:
                                fig.canvas.draw_idle()
                        except ValueError:
                            print("Invalid number.")
                        except Exception as e:
                            print(f"Error setting tick length: {e}")
                        continue
                    if cmd2 == 'list':
                        def b(v): return 'ON ' if bool(v) else 'off'
                        # Show which sides are available for this pane
                        if target is ec_ax:
                            print(f"top    w1:{b(wasd['top']['spine'])} w2:{b(wasd['top']['ticks'])} w3:{b(wasd['top']['minor'])} w4:{b(wasd['top']['labels'])} w5:{b(wasd['top']['title'])}")
                            print(f"bottom s1:{b(wasd['bottom']['spine'])} s2:{b(wasd['bottom']['ticks'])} s3:{b(wasd['bottom']['minor'])} s4:{b(wasd['bottom']['labels'])} s5:{b(wasd['bottom']['title'])}")
                            print(f"right  d1:{b(wasd['right']['spine'])} d2:{b(wasd['right']['ticks'])} d3:{b(wasd['right']['minor'])} d4:{b(wasd['right']['labels'])} d5:{b(wasd['right']['title'])}")
                            print("(left spine 'a' not available for EC panel)")
                        else:
                            print(f"top    w1:{b(wasd['top']['spine'])} w2:{b(wasd['top']['ticks'])} w3:{b(wasd['top']['minor'])} w4:{b(wasd['top']['labels'])} w5:{b(wasd['top']['title'])}")
                            print(f"bottom s1:{b(wasd['bottom']['spine'])} s2:{b(wasd['bottom']['ticks'])} s3:{b(wasd['bottom']['minor'])} s4:{b(wasd['bottom']['labels'])} s5:{b(wasd['bottom']['title'])}")
                            print(f"left   a1:{b(wasd['left']['spine'])} a2:{b(wasd['left']['ticks'])} a3:{b(wasd['left']['minor'])} a4:{b(wasd['left']['labels'])} a5:{b(wasd['left']['title'])}")
                            print("(right spine 'd' not available for operando panel)")
                        continue
                    changed = False
                    changed_sides = set()  # Track which sides were affected
                    for p in cmd2.split():
                        if len(p) != 2:
                            print("Unknown code."); continue
                        side = {'w':'top','a':'left','s':'bottom','d':'right'}.get(p[0])
                        if side is None or p[1] not in '12345':
                            print("Unknown code."); continue
                        # Disable a12345 for EC panel (no left spine in dual-pane mode)
                        if target is ec_ax and side == 'left':
                            print("Left spine 'a' not available for EC panel (use operando panel for left side)"); continue
                        # Disable d12345 for operando panel ONLY in dual-pane mode (when EC panel exists)
                        # In operando-only mode (no EC panel), d12345 should work for right spine
                        if target is ax and side == 'right' and ec_ax is not None:
                            print("Right spine 'd' not available for operando panel (use EC panel for right side)")
                            continue
                        key = {'1':'spine','2':'ticks','3':'minor','4':'labels','5':'title'}[p[1]]
                        wasd[side][key] = not bool(wasd[side][key])
                        changed = True
                        # Track which side was changed to only reposition affected sides
                        # Labels and titles affect positioning, but spine/tick toggles don't necessarily
                        if key in ('labels', 'title'):
                            changed_sides.add(side)
                        # Sync new separate keys + legacy tick state for compatibility
                        if side == 'top' and key == 'ticks':
                            ts['t_ticks'] = bool(wasd['top']['ticks'])
                            ts['tx'] = bool(wasd['top']['ticks'] and wasd['top']['labels'])
                        if side == 'top' and key == 'labels':
                            ts['t_labels'] = bool(wasd['top']['labels'])
                            ts['tx'] = bool(wasd['top']['ticks'] and wasd['top']['labels'])
                        if side == 'top' and key == 'minor':
                            ts['mtx'] = bool(wasd['top']['minor'])
                        if side == 'bottom' and key == 'ticks':
                            ts['b_ticks'] = bool(wasd['bottom']['ticks'])
                            ts['bx'] = bool(wasd['bottom']['ticks'] and wasd['bottom']['labels'])
                        if side == 'bottom' and key == 'labels':
                            ts['b_labels'] = bool(wasd['bottom']['labels'])
                            ts['bx'] = bool(wasd['bottom']['ticks'] and wasd['bottom']['labels'])
                        if side == 'bottom' and key == 'minor':
                            ts['mbx'] = bool(wasd['bottom']['minor'])
                        if side == 'left' and key == 'ticks':
                            ts['l_ticks'] = bool(wasd['left']['ticks'])
                            ts['ly'] = bool(wasd['left']['ticks'] and wasd['left']['labels'])
                        if side == 'left' and key == 'labels':
                            ts['l_labels'] = bool(wasd['left']['labels'])
                            ts['ly'] = bool(wasd['left']['ticks'] and wasd['left']['labels'])
                        if side == 'left' and key == 'minor':
                            ts['mly'] = bool(wasd['left']['minor'])
                        if side == 'right' and key == 'ticks':
                            ts['r_ticks'] = bool(wasd['right']['ticks'])
                            ts['ry'] = bool(wasd['right']['ticks'] and wasd['right']['labels'])
                        if side == 'right' and key == 'labels':
                            ts['r_labels'] = bool(wasd['right']['labels'])
                            ts['ry'] = bool(wasd['right']['ticks'] and wasd['right']['labels'])
                        if side == 'right' and key == 'minor':
                            ts['mry'] = bool(wasd['right']['minor'])
                    if changed:
                        _snapshot("toggle-ticks")
                        # Pass changed_sides (even if empty) to avoid repositioning all sides unnecessarily
                        _apply_wasd_axis(target, wasd, changed_sides)
                        # Single draw at the end after all positioning is complete
                        try:
                            fig.canvas.draw()
                        except Exception:
                            fig.canvas.draw_idle()
                        try:
                            target._saved_tick_state = dict(ts)
                        except Exception:
                            pass
                        try:
                            fig.canvas.draw()
                        except Exception:
                            fig.canvas.draw_idle()
            print_menu()
        elif cmd == 'ox':
            while True:
                cur = ax.get_xlim(); print(f"Current operando X: {cur[0]:.4g} {cur[1]:.4g}")
                line = input("New X range (min max, q=back): ").strip()
                if not line or line.lower() == 'q':
                    break
                _snapshot("operando-xrange")
                try:
                    lo, hi = map(float, line.split())
                    ax.set_xlim(lo, hi)
                    # Re-normalize intensity to visible region
                    _renormalize_to_visible()
                    fig.canvas.draw_idle()
                except Exception as e:
                    print(f"Invalid range: {e}")
            print_menu()
        elif cmd == 'oy':
            while True:
                cur = ax.get_ylim(); print(f"Current operando Y: {cur[0]:.4g} {cur[1]:.4g}")
                line = input("New Y range (min max, q=back): ").strip()
                if not line or line.lower() == 'q':
                    break
                _snapshot("operando-yrange")
                try:
                    lo, hi = map(float, line.split())
                    ax.set_ylim(lo, hi)
                    # Re-normalize intensity to visible region
                    _renormalize_to_visible()
                    fig.canvas.draw_idle()
                except Exception as e:
                    print(f"Invalid range: {e}")
            print_menu()
        elif cmd == 'oz':
            while True:
                try:
                    cur = im.get_clim()
                    print(f"Current color scale range: {cur[0]:.4g} to {cur[1]:.4g}")
                except Exception:
                    print("Could not retrieve current color scale range")
                
                # Initialize variables for auto-fit
                auto_available = False
                auto_lo = 0.0
                auto_hi = 1.0
                
                # Calculate actual intensity range in the visible (current X/Y) area
                try:
                    import numpy as _np  # Local import to ensure availability
                    arr = _np.asarray(im.get_array(), dtype=float)
                    if arr.ndim == 2 and arr.size > 0:
                        H, W = arr.shape
                        x0, x1, y0, y1 = im.get_extent()
                        xmin, xmax = (x0, x1) if x0 <= x1 else (x1, x0)
                        ymin, ymax = (y0, y1) if y0 <= y1 else (y1, y0)
                        xl = ax.get_xlim(); yl = ax.get_ylim()
                        xlo, xhi = (min(xl), max(xl))
                        ylo, yhi = (min(yl), max(yl))
                        
                        # Map to pixel indices
                        if xmax > xmin:
                            c0 = int(_np.floor((xlo - xmin) / (xmax - xmin) * (W - 1)))
                            c1 = int(_np.ceil((xhi - xmin) / (xmax - xmin) * (W - 1)))
                        else:
                            c0, c1 = 0, W - 1
                        if ymax > ymin:
                            r0 = int(_np.floor((ylo - ymin) / (ymax - ymin) * (H - 1)))
                            r1 = int(_np.ceil((yhi - ymin) / (ymax - ymin) * (H - 1)))
                        else:
                            r0, r1 = 0, H - 1
                        
                        c0 = max(0, min(W - 1, c0)); c1 = max(0, min(W - 1, c1))
                        r0 = max(0, min(H - 1, r0)); r1 = max(0, min(H - 1, r1))
                        if c1 < c0: c0, c1 = c1, c0
                        if r1 < r0: r0, r1 = r1, r0
                        view = arr[r0:r1+1, c0:c1+1]
                        finite = view[_np.isfinite(view)]
                        if finite.size:
                            auto_lo = float(_np.min(finite))
                            auto_hi = float(_np.max(finite))
                            print(f"Actual intensity range in visible area: {auto_lo:.4g} to {auto_hi:.4g}")
                            auto_available = True
                        else:
                            print("No finite intensity data in visible area")
                            auto_available = False
                    else:
                        print("No intensity data available")
                        auto_available = False
                except Exception as e:
                    print(f"Could not compute intensity range in visible area: {e}")
                    auto_available = False
                
                if auto_available:
                    line = input("New intensity range (min max, a=auto-fit to visible, q=back): ").strip()
                else:
                    line = input("New intensity range (min max, q=back): ").strip()
                
                if not line or line.lower() == 'q':
                    break
                
                _snapshot("operando-intensity-range")
                try:
                    if line.lower() == 'a':
                        # Apply auto-normalization to visible data
                        if auto_available:
                            im.set_clim(auto_lo, auto_hi)
                            try:
                                if cbar is not None:
                                    cbar.update_normal(im)
                            except Exception:
                                pass
                            fig.canvas.draw_idle()
                            print(f"Applied auto-fit range: {auto_lo:.4g} to {auto_hi:.4g}")
                        else:
                            print("Auto-fit unavailable: no finite data in visible area")
                    else:
                        lo, hi = map(float, line.split())
                        im.set_clim(lo, hi)
                        try:
                            if cbar is not None:
                                cbar.update_normal(im)
                        except Exception:
                            pass
                        fig.canvas.draw_idle()
                        print(f"Applied intensity range: {lo:.4g} to {hi:.4g}")
                except Exception as e:
                    print(f"Invalid range: {e}")
            print_menu()
        elif cmd in ('ow'):
            # Always read fresh value from attribute to avoid stale cached value
            while True:
                ax_w_in = getattr(ax, '_fixed_ax_w_in', ax_w_in)
                print(f"Current operando width: {ax_w_in:.2f} in")
                val = input("New width (inches, q=back): ").strip()
                if not val or val.lower() == 'q':
                    break
                _snapshot("operando-width")
                try:
                    new_w = max(0.25, float(val))
                    ax_w_in = new_w
                    _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)
                except Exception as e:
                    print(f"Invalid width: {e}")
            print_menu()
        elif cmd == 'ew':
            # Always read fresh value from attribute to avoid stale cached value
            if ec_ax is None:
                print("EC panel not available (no .mpt file in folder).")
                print_menu()
                continue
            while True:
                ec_w_in = getattr(ec_ax, '_fixed_ec_w_in', ec_w_in)
                print(f"Current EC width: {ec_w_in:.2f} in")
                val = input("New EC width (inches, q=back): ").strip()
                if not val or val.lower() == 'q':
                    break
                _snapshot("ec-width")
                try:
                    new_w = max(0.25, float(val))
                    ec_w_in = new_w
                    _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)
                except Exception as e:
                    print(f"Invalid EC width: {e}")
            print_menu()
        elif cmd == 'oc':
            # Change operando colormap (perceptually uniform suggestions)
            available = list(plt.colormaps())
            base = ['viridis', 'plasma', 'inferno', 'magma', 'cividis']
            extras = []
            for name in ('turbo', 'batlow', 'batlowK'):
                if name in available:
                    extras.append(name)
            print("Recommended colormaps for scientific publications:")
            print("  1. viridis    - Perceptually uniform (blue→yellow), colorblind-friendly")
            print("  2. plasma     - Perceptually uniform (purple→yellow), high contrast")
            print("  3. inferno    - Perceptually uniform (black→yellow), good for dark backgrounds")
            print("  4. cividis    - Perceptually uniform, optimized for color vision deficiency")
            print("  5. magma      - Perceptually uniform (black→white), excellent for grayscale")
            print("\nOther available: " + ", ".join(base + extras))
            print(_colorize_inline_commands("Append _r to reverse (e.g., viridis_r or 1_r). Blank to cancel."))
            choice = input("Palette name or number (1-5): ").strip()
            if not choice:
                print_menu(); continue
            try:
                _snapshot("operando-colormap")
                
                # Map numeric selections to palette names
                palette_map = {
                    '1': 'viridis',
                    '2': 'plasma',
                    '3': 'inferno',
                    '4': 'cividis',
                    '5': 'magma'
                }
                
                # Check for reversed palette (number_r or name_r)
                if choice.endswith('_r'):
                    base_choice = choice[:-2]
                    if base_choice in palette_map:
                        choice = palette_map[base_choice] + '_r'
                    # else keep original choice (e.g., "viridis_r")
                elif choice in palette_map:
                    choice = palette_map[choice]
                
                if choice not in available:
                    raise ValueError(f"Unknown colormap '{choice}'")
                im.set_cmap(choice)
                try:
                    # Sync colorbar if linked to same mappable
                    if cbar is not None:
                        cbar.update_normal(im)
                except Exception:
                    pass
                try:
                    fig.canvas.draw()
                except Exception:
                    fig.canvas.draw_idle()
                print(f"Applied colormap: {choice}")
            except Exception as e:
                print(f"Error applying colormap: {e}")
            print_menu()
        elif cmd == 'p':
            # Print current style and offer export
            # Style commands (Styles column - col1):
            #   oc: operando colormap
            #   ow: operando width
            #   ew: EC width
            #   h:  height
            #   el: EC curve (color, linewidth)
            #   t:  toggle axes (WASD states for both panes)
            #   l:  line widths (frame and tick widths for both panes)
            #   f:  fonts (family, size)
            #   g:  canvas size
            #   r:  reverse Y-axis orientation
            try:
                # Export functionality only available in dual-pane mode
                if ec_ax is not None:
                    print("Print & Export: ps=style only (.bps), psg=style+geometry (.bpsg), q=cancel")
                    choice = input("p> ").strip().lower()
                    if not choice or choice == 'q':
                        print_menu()
                        continue
                    
                    if choice not in ('ps', 'psg'):
                        print(f"Unknown option: {choice}")
                        print_menu()
                        continue
                else:
                    # Operando-only mode: no export, just return to menu
                    print("\nNote: Style export (.bps/.bpsg) is only available in dual-pane mode (with EC file).")
                    print_menu()
                    continue
                
                # Gather style
                fig_w, fig_h = _get_fig_size(fig)
                cb_w_in, cb_gap_in, ec_gap_in, ec_w_in, ax_w_in, ax_h_in = _ensure_fixed_params(fig, ax, cbar.ax, ec_ax)
                fam = plt.rcParams.get('font.sans-serif', [''])[0]
                fsize = plt.rcParams.get('font.size', None)
                cmap_name = getattr(im.get_cmap(), 'name', None)
                
                # Print header based on mode
                if ec_ax is not None:
                    print("\n--- Operando+EC Style ---")
                    print("Commands (Styles): oc(colormap), ow(op width), ew(ec width), h(height), el(EC curve), v(toggle colorbar/ec), t(toggle axes), l(line widths), f(fonts), g(canvas), r(reverse)")
                    print("Commands (Operando): ox(X range), oy(Y range), oz(intensity range), or(rename)")
                    print("Commands (EC): et(time range), ey(Y-axis type), er(rename)")
                    print(f"Canvas size (g): {fig_w:.3f} x {fig_h:.3f}")
                    print(f"Geometry: operando width (ow)={ax_w_in:.3f}\", height (h)={ax_h_in:.3f}\", EC width (ew)={ec_w_in:.3f}\"")
                else:
                    print("\n--- Operando-Only Style ---")
                    print("Commands (Styles): oc(colormap), ow(op width), v(toggle colorbar), t(toggle axes), l(line widths), h(height), f(fonts), g(canvas), r(reverse)")
                    print("Commands (Operando): ox(X range), oy(Y range), oz(intensity range), or(rename)")
                    print(f"Canvas size (g): {fig_w:.3f} x {fig_h:.3f}")
                    print(f"Geometry: operando width (ow)={ax_w_in:.3f}\", height (h)={ax_h_in:.3f}\"")
                
                # Visibility state
                cb_vis = bool(cbar.ax.get_visible())
                ec_vis = bool(ec_ax.get_visible()) if ec_ax is not None else None
                if ec_ax is not None:
                    print(f"Visibility (v): colorbar={'shown' if cb_vis else 'hidden'}, EC panel={'shown' if ec_vis else 'hidden'}")
                else:
                    print(f"Visibility (v): colorbar={'shown' if cb_vis else 'hidden'}")
                
                # Check if Y-axes are reversed (ylim[0] > ylim[1])
                op_ylim = ax.get_ylim()
                op_reversed = bool(op_ylim[0] > op_ylim[1])
                if ec_ax is not None:
                    ec_ylim = ec_ax.get_ylim()
                    ec_reversed = bool(ec_ylim[0] > ec_ylim[1])
                    print(f"Reverse (r): operando={'YES' if op_reversed else 'no'}, EC={'YES' if ec_reversed else 'no'}")
                else:
                    print(f"Reverse (r): operando={'YES' if op_reversed else 'no'}")
                
                print(f"Font (f): family='{fam}', size={fsize}")
                print(f"Operando colormap (oc): {cmap_name}")
                
                # Display intensity range (oz command)
                try:
                    clim = im.get_clim()
                    print(f"Operando intensity range (oz): {clim[0]:.4g} to {clim[1]:.4g}")
                except Exception:
                    print("Operando intensity range (oz): N/A")
                
                # Display EC Y-axis mode (ey command) - only if EC panel exists
                if ec_ax is not None:
                    ec_y_mode = getattr(ec_ax, '_ec_y_mode', 'time')
                    print(f"EC Y-axis mode (ey): {ec_y_mode}")
                    if ec_y_mode == 'ions':
                        ion_params = getattr(ec_ax, '_ion_params', {})
                        if ion_params:
                            mass_mg = ion_params.get('mass_mg', 'N/A')
                            cap_per_ion = ion_params.get('cap_per_ion_mAh_g', 'N/A')
                            start_ions = ion_params.get('start_ions', 'N/A')
                            print(f"  Ion params: mass={mass_mg} mg, cap/ion={cap_per_ion} mAh/g, start={start_ions}")
                
                # Display operando pane tick visibility
                def _onoff(v): return 'ON ' if bool(v) else 'off'
                op_ts = getattr(ax, '_saved_tick_state', {})
                op_wasd = {
                    'left':   {'spine': bool(ax.spines.get('left').get_visible() if ax.spines.get('left') else False), 
                               'ticks': bool(op_ts.get('l_ticks', op_ts.get('ly', True))), 
                               'minor': bool(op_ts.get('mly', False)), 
                               'labels': bool(op_ts.get('l_labels', op_ts.get('ly', True))), 
                               'title': bool(ax.get_ylabel())},
                    'top':    {'spine': bool(ax.spines.get('top').get_visible() if ax.spines.get('top') else False),
                               'ticks': bool(op_ts.get('t_ticks', op_ts.get('tx', False))), 
                               'minor': bool(op_ts.get('mtx', False)), 
                               'labels': bool(op_ts.get('t_labels', op_ts.get('tx', False))), 
                               'title': bool(getattr(ax, '_top_xlabel_on', False))},
                    'bottom': {'spine': bool(ax.spines.get('bottom').get_visible() if ax.spines.get('bottom') else False),
                               'ticks': bool(op_ts.get('b_ticks', op_ts.get('bx', True))), 
                               'minor': bool(op_ts.get('mbx', False)), 
                               'labels': bool(op_ts.get('b_labels', op_ts.get('bx', True))), 
                               'title': bool(ax.get_xlabel())},
                    'right':  {'spine': bool(ax.spines.get('right').get_visible() if ax.spines.get('right') else False),
                               'ticks': bool(op_ts.get('r_ticks', op_ts.get('ry', False))), 
                               'minor': bool(op_ts.get('mry', False)), 
                               'labels': bool(op_ts.get('r_labels', op_ts.get('ry', False))), 
                               'title': bool(getattr(ax, '_right_ylabel_on', False))},
                }
                if ec_ax is not None:
                    # Dual pane mode: operando has a/w/s, EC has w/s/d
                    print("Operando pane (t>o: a=left, w=top, s=bottom; 'd' not available):")
                    for side_key, side_name in [('left', 'a'), ('top', 'w'), ('bottom', 's')]:
                        s = op_wasd[side_key]
                        print(f"  {side_name}1:{_onoff(s['spine'])} {side_name}2:{_onoff(s['ticks'])} {side_name}3:{_onoff(s['minor'])} {side_name}4:{_onoff(s['labels'])} {side_name}5:{_onoff(s['title'])}")
                else:
                    # Operando-only mode: all four sides available
                    print("Operando pane (t>o: a=left, w=top, s=bottom, d=right):")
                    for side_key, side_name in [('left', 'a'), ('top', 'w'), ('bottom', 's'), ('right', 'd')]:
                        s = op_wasd[side_key]
                        print(f"  {side_name}1:{_onoff(s['spine'])} {side_name}2:{_onoff(s['ticks'])} {side_name}3:{_onoff(s['minor'])} {side_name}4:{_onoff(s['labels'])} {side_name}5:{_onoff(s['title'])}")
                
                # Display EC pane tick visibility (only if EC panel exists)
                if ec_ax is not None:
                    ec_ts = getattr(ec_ax, '_saved_tick_state', {})
                    ec_wasd = {
                        'top':    {'spine': bool(ec_ax.spines.get('top').get_visible() if ec_ax.spines.get('top') else False),
                                   'ticks': bool(ec_ts.get('t_ticks', ec_ts.get('tx', False))), 
                                   'minor': bool(ec_ts.get('mtx', False)), 
                                   'labels': bool(ec_ts.get('t_labels', ec_ts.get('tx', False))), 
                                   'title': bool(getattr(ec_ax, '_top_xlabel_on', False))},
                        'bottom': {'spine': bool(ec_ax.spines.get('bottom').get_visible() if ec_ax.spines.get('bottom') else False),
                                   'ticks': bool(ec_ts.get('b_ticks', ec_ts.get('bx', True))), 
                                   'minor': bool(ec_ts.get('mbx', False)), 
                                   'labels': bool(ec_ts.get('b_labels', ec_ts.get('bx', True))), 
                                   'title': bool(ec_ax.get_xlabel())},
                        'right':  {'spine': bool(ec_ax.spines.get('right').get_visible() if ec_ax.spines.get('right') else False),
                                   'ticks': bool(ec_ts.get('r_ticks', ec_ts.get('ry', False))), 
                                   'minor': bool(ec_ts.get('mry', False)), 
                                   'labels': bool(ec_ts.get('r_labels', ec_ts.get('ry', False))), 
                                   'title': bool(ec_ax.get_ylabel())},  # Use actual ylabel for EC
                    }
                    print("EC pane (t>e: w=top, s=bottom, d=right; 'a' not available):")
                    for side_key, side_name in [('top', 'w'), ('bottom', 's'), ('right', 'd')]:
                        s = ec_wasd[side_key]
                        print(f"  {side_name}1:{_onoff(s['spine'])} {side_name}2:{_onoff(s['ticks'])} {side_name}3:{_onoff(s['minor'])} {side_name}4:{_onoff(s['labels'])} {side_name}5:{_onoff(s['title'])}")
                else:
                    ec_wasd = None
                
                # Line widths (l command: frame and tick widths)
                print("\nLine widths (l command):")
                op_frame_lw = ax.spines.get('bottom').get_linewidth() if ax.spines.get('bottom') else 1.0
                try:
                    op_tick_lw = ax.xaxis.get_major_ticks()[0].tick1line.get_markersize() if ax.xaxis.get_major_ticks() else 1.0
                except:
                    op_tick_lw = 1.0
                print(f"  Operando: frame={op_frame_lw:.2f}, ticks={op_tick_lw:.2f}")
                
                if ec_ax is not None:
                    ec_frame_lw = ec_ax.spines.get('bottom').get_linewidth() if ec_ax.spines.get('bottom') else 1.0
                    try:
                        ec_tick_lw = ec_ax.xaxis.get_major_ticks()[0].tick1line.get_markersize() if ec_ax.xaxis.get_major_ticks() else 1.0
                    except:
                        ec_tick_lw = 1.0
                    print(f"  EC: frame={ec_frame_lw:.2f}, ticks={ec_tick_lw:.2f}")
                
                # EC curve properties (el command, only if EC panel exists)
                if ec_ax is not None:
                    print("\nEC curve (el command):")
                    ln = getattr(ec_ax, '_ec_line', None)
                    if ln is None and ec_ax.lines:
                        ln = ec_ax.lines[0]
                    if ln is not None:
                        try:
                            ec_color = ln.get_color()
                            ec_lw = ln.get_linewidth()
                            print(f"  Color: {ec_color}, Linewidth: {ec_lw:.2f}")
                        except Exception:
                            print("  (unable to read EC line properties)")
                    else:
                        print("  (no EC line found)")
                
                print("-------------------------\n")
                # List style files (.bps, .bpsg, .bpcfg) for convenience
                try:
                    _bpcfg_files = sorted([f for f in os.listdir(os.getcwd()) if f.lower().endswith(('.bps', '.bpsg', '.bpcfg'))])
                except Exception:
                    _bpcfg_files = []
                if _bpcfg_files:
                    print("Existing style files (.bps/.bpsg):")
                    for _i, _f in enumerate(_bpcfg_files, 1):
                        print(f"  {_i}: {_f}")
                sub = input("Style: (e=export, q=return): ").strip().lower()
                if sub == 'e':
                    choice = input("Enter new filename or number to overwrite (q=cancel): ").strip()
                    if not choice or choice.lower() == 'q':
                        print_menu(); continue
                    target = None
                    if choice.isdigit() and _bpcfg_files:
                        _idx = int(choice)
                        if 1 <= _idx <= len(_bpcfg_files):
                            name = _bpcfg_files[_idx-1]
                            yn = input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                            if yn == 'y':
                                target = os.path.join(os.getcwd(), name)
                        else:
                            print("Invalid number."); print_menu(); continue
                    else:
                        name = choice
                        root, ext = os.path.splitext(name)
                        if ext == '':
                            name = name + '.bpcfg'
                        target = name if os.path.isabs(name) else os.path.join(os.getcwd(), name)
                        if os.path.exists(target):
                            yn = input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
                            if yn != 'y':
                                target = None
                    # Build WASD states for both panes
                    op_wasd_state = {
                        'left':   op_wasd['left'],
                        'top':    op_wasd['top'],
                        'bottom': op_wasd['bottom'],
                        'right':  {'spine': bool(ax.spines.get('right').get_visible() if ax.spines.get('right') else False),
                                   'ticks': bool(op_ts.get('r_ticks', op_ts.get('ry', False))), 
                                   'minor': bool(op_ts.get('mry', False)), 
                                   'labels': bool(op_ts.get('r_labels', op_ts.get('ry', False))), 
                                   'title': bool(getattr(ax, '_right_ylabel_on', False))},
                    }
                    ec_wasd_state = {
                        'left':   {'spine': bool(ec_ax.spines.get('left').get_visible() if ec_ax.spines.get('left') else False),
                                   'ticks': bool(ec_ts.get('l_ticks', ec_ts.get('ly', True))), 
                                   'minor': bool(ec_ts.get('mly', False)), 
                                   'labels': bool(ec_ts.get('l_labels', ec_ts.get('ly', True))), 
                                   'title': bool(ec_ax.get_ylabel())},
                        'top':    ec_wasd['top'],
                        'bottom': ec_wasd['bottom'],
                        'right':  ec_wasd['right'],
                    }
                    
                    # Gather spine and tick widths for both panes
                    op_spines = {}
                    for name in ('bottom', 'top', 'left', 'right'):
                        sp = ax.spines.get(name)
                        if sp:
                            op_spines[name] = {'linewidth': float(sp.get_linewidth()), 'visible': bool(sp.get_visible())}
                    ec_spines = {}
                    for name in ('bottom', 'top', 'left', 'right'):
                        sp = ec_ax.spines.get(name)
                        if sp:
                            ec_spines[name] = {'linewidth': float(sp.get_linewidth()), 'visible': bool(sp.get_visible())}
                    
                    # Tick widths
                    def _get_tick_width(axis_obj, which_axis='x', which_tick='major'):
                        try:
                            ticks = axis_obj.xaxis.get_major_ticks() if which_axis == 'x' and which_tick == 'major' else \
                                    axis_obj.xaxis.get_minor_ticks() if which_axis == 'x' and which_tick == 'minor' else \
                                    axis_obj.yaxis.get_major_ticks() if which_axis == 'y' and which_tick == 'major' else \
                                    axis_obj.yaxis.get_minor_ticks()
                            if ticks:
                                return float(ticks[0].tick1line.get_markersize())
                        except:
                            pass
                        return None
                    
                    op_ticks = {
                        'x_major': _get_tick_width(ax, 'x', 'major'),
                        'x_minor': _get_tick_width(ax, 'x', 'minor'),
                        'y_major': _get_tick_width(ax, 'y', 'major'),
                        'y_minor': _get_tick_width(ax, 'y', 'minor'),
                    }
                    ec_ticks = {
                        'x_major': _get_tick_width(ec_ax, 'x', 'major'),
                        'x_minor': _get_tick_width(ec_ax, 'x', 'minor'),
                        'y_major': _get_tick_width(ec_ax, 'y', 'major'),
                        'y_minor': _get_tick_width(ec_ax, 'y', 'minor'),
                    }
                    
                    # EC curve properties (el command)
                    ec_curve = {}
                    ln = getattr(ec_ax, '_ec_line', None)
                    if ln is None and ec_ax.lines:
                        ln = ec_ax.lines[0]
                    if ln is not None:
                        try:
                            ec_curve = {
                                'color': ln.get_color(),
                                'linewidth': float(ln.get_linewidth())
                            }
                        except Exception:
                            pass
                    
                    # Check if Y-axes are reversed
                    op_ylim_cur = ax.get_ylim()
                    ec_ylim_cur = ec_ax.get_ylim()
                    op_reversed = bool(op_ylim_cur[0] > op_ylim_cur[1])
                    ec_reversed = bool(ec_ylim_cur[0] > ec_ylim_cur[1])
                    
                    # Capture intensity range (oz command)
                    try:
                        clim = im.get_clim()
                        intensity_range = [float(clim[0]), float(clim[1])]
                    except Exception:
                        intensity_range = None
                    
                    # Capture ions mode state (ey command)
                    ec_y_mode = getattr(ec_ax, '_ec_y_mode', 'time')
                    ion_params = getattr(ec_ax, '_ion_params', None)
                    
                    # Build config based on choice
                    # Get visibility states
                    cb_visible = bool(cbar.ax.get_visible())
                    ec_visible = bool(ec_ax.get_visible()) if ec_ax is not None else None
                    
                    # Get colorbar label mode
                    cb_label_mode = getattr(fig, '_colorbar_label_mode', 'normal')
                    
                    # Capture labelpad values (for title positioning)
                    op_labelpads = {
                        'x': getattr(ax.xaxis, 'labelpad', None),
                        'y': getattr(ax.yaxis, 'labelpad', None),
                    }
                    ec_labelpads = {
                        'x': getattr(ec_ax.xaxis, 'labelpad', None),
                        'y': getattr(ec_ax.yaxis, 'labelpad', None),
                    }
                    
                    if choice == 'ps':
                        cfg = {
                            'kind': 'operando_ec_style',
                            'version': 2,
                            'figure': {'canvas_size': [fig_w, fig_h], 'cb_visible': cb_visible, 'cb_label_mode': cb_label_mode},
                            'geometry': {'op_w_in': ax_w_in, 'op_h_in': ax_h_in, 'ec_w_in': ec_w_in},
                            'operando': {'cmap': cmap_name, 'wasd_state': op_wasd_state, 'spines': op_spines, 'ticks': {'widths': op_ticks}, 'y_reversed': op_reversed, 'intensity_range': intensity_range, 'labelpads': op_labelpads},
                            'ec': {'wasd_state': ec_wasd_state, 'spines': ec_spines, 'ticks': {'widths': ec_ticks}, 'curve': ec_curve, 'y_reversed': ec_reversed, 'y_mode': ec_y_mode, 'ion_params': ion_params, 'visible': ec_visible, 'labelpads': ec_labelpads},
                            'font': {'family': fam, 'size': fsize},
                        }
                        default_ext = '.bps'
                    else:  # psg
                        cfg = {
                            'kind': 'operando_ec_style_geom',
                            'version': 2,
                            'figure': {'canvas_size': [fig_w, fig_h], 'cb_visible': cb_visible, 'cb_label_mode': cb_label_mode},
                            'geometry': {'op_w_in': ax_w_in, 'op_h_in': ax_h_in, 'ec_w_in': ec_w_in},
                            'operando': {'cmap': cmap_name, 'wasd_state': op_wasd_state, 'spines': op_spines, 'ticks': {'widths': op_ticks}, 'y_reversed': op_reversed, 'intensity_range': intensity_range, 'labelpads': op_labelpads},
                            'ec': {'wasd_state': ec_wasd_state, 'spines': ec_spines, 'ticks': {'widths': ec_ticks}, 'curve': ec_curve, 'y_reversed': ec_reversed, 'y_mode': ec_y_mode, 'ion_params': ion_params, 'visible': ec_visible, 'labelpads': ec_labelpads},
                            'font': {'family': fam, 'size': fsize},
                            'axes_geometry': _get_geometry_snapshot(ax, ec_ax),
                        }
                        default_ext = '.bpsg'
                        # Print geometry info
                        geom = cfg['axes_geometry']
                        print("\n--- Geometry ---")
                        print(f"Operando X label: {geom['operando']['xlabel']}")
                        print(f"Operando Y label: {geom['operando']['ylabel']}")
                        print(f"Operando X limits: {geom['operando']['xlim'][0]:.4g} to {geom['operando']['xlim'][1]:.4g}")
                        print(f"Operando Y limits: {geom['operando']['ylim'][0]:.4g} to {geom['operando']['ylim'][1]:.4g}")
                        print(f"EC X label: {geom['ec']['xlabel']}")
                        print(f"EC Y label: {geom['ec']['ylabel']}")
                        print(f"EC X limits: {geom['ec']['xlim'][0]:.4g} to {geom['ec']['xlim'][1]:.4g}")
                        print(f"EC Y limits: {geom['ec']['ylim'][0]:.4g} to {geom['ec']['ylim'][1]:.4g}")
                    
                    # List existing files
                    try:
                        _style_files = sorted([f for f in os.listdir(os.getcwd()) if f.lower().endswith(default_ext) or f.lower().endswith('.bpcfg')])
                    except Exception:
                        _style_files = []
                    if _style_files:
                        print(f"\nExisting {default_ext} files:")
                        for _i, _f in enumerate(_style_files, 1):
                            print(f"  {_i}: {_f}")
                    
                    try:
                        sub = input("Style: (e=export, q=return): ").strip().lower()
                        if sub == 'e':
                            choice_name = input("Enter new filename or number to overwrite (q=cancel): ").strip()
                            if not choice_name or choice_name.lower() == 'q':
                                print_menu(); continue
                            target = None
                            if choice_name.isdigit() and _style_files:
                                _idx = int(choice_name)
                                if 1 <= _idx <= len(_style_files):
                                    name = _style_files[_idx-1]
                                    yn = input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                                    if yn == 'y':
                                        target = os.path.join(os.getcwd(), name)
                                else:
                                    print("Invalid number."); print_menu(); continue
                            else:
                                name = choice_name
                                # Add default extension if no extension provided
                                if not any(name.lower().endswith(ext) for ext in ['.bps', '.bpsg', '.bpcfg']):
                                    name = name + default_ext
                                target = name if os.path.isabs(name) else os.path.join(os.getcwd(), name)
                                if os.path.exists(target):
                                    yn = input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
                                    if yn != 'y':
                                        target = None
                            if target:
                                with open(target, 'w', encoding='utf-8') as f:
                                    json.dump(cfg, f, indent=2)
                                print(f"Exported style to {target}")
                    except Exception as e:
                        print(f"Export failed: {e}")
            except Exception as e:
                print(f"Error while printing/exporting style: {e}")
            print_menu()
        elif cmd == 'i':
            # Load a .bps/.bpsg/.bpcfg style and apply
            # Applies style properties from commands: oc, ow, ew, h, el, t, l, f, g, r
            try:
                try:
                    _style_files = sorted([f for f in os.listdir(os.getcwd()) if f.lower().endswith(('.bps', '.bpsg', '.bpcfg'))])
                except Exception:
                    _style_files = []
                if _style_files:
                    print("Available style files:")
                    for _i, _f in enumerate(_style_files, 1):
                        print(f"  {_i}: {_f}")
                inp = input("Enter number or filename (.bps/.bpsg, q=cancel): ").strip()
                if not inp or inp.lower() == 'q':
                    print_menu(); continue
                _snapshot("import-style")
                if inp.isdigit() and _style_files:
                    _idx = int(inp)
                    if 1 <= _idx <= len(_style_files):
                        path = os.path.join(os.getcwd(), _style_files[_idx-1])
                    else:
                        print("Invalid number."); print_menu(); continue
                else:
                    path = inp
                    if not os.path.isfile(path):
                        # Try adding extensions
                        found = False
                        for ext in ['.bps', '.bpsg', '.bpcfg']:
                            alt = path if path.lower().endswith(ext) else path + ext
                            if os.path.isfile(alt):
                                path = alt
                                found = True
                                break
                        if not found:
                            print("File not found."); print_menu(); continue
                
                with open(path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                
                # Check file type
                kind = cfg.get('kind', '')
                if kind not in ('operando_ec_style', 'operando_ec_style_geom'):
                    print("Not an operando+EC style file.")
                    print_menu(); continue
                
                has_geometry = (kind == 'operando_ec_style_geom' and 'axes_geometry' in cfg)
                # Version check (support both v1 and v2)
                version = cfg.get('version', 1)
                
                # Fonts
                font = cfg.get('font', {})
                fam = font.get('family')
                size = font.get('size')
                if fam or size is not None:
                    try:
                        set_fonts(family=fam if fam else None, size=size if size is not None else None)
                    except Exception:
                        pass
                
                # Canvas - support both 'size' (v1) and 'canvas_size' (v2)
                fig_cfg = cfg.get('figure', {})
                fig_sz = fig_cfg.get('canvas_size') or fig_cfg.get('size')
                if isinstance(fig_sz, (list, tuple)) and len(fig_sz) == 2:
                    try:
                        W = max(1.0, float(fig_sz[0])); H = max(1.0, float(fig_sz[1]))
                        fig.set_size_inches(W, H, forward=True)
                    except Exception:
                        pass
                
                # Geometry inches
                # v1: stored in operando/ec/gaps sub-dicts
                # v2: stored in geometry dict
                if version >= 2:
                    geom = cfg.get('geometry', {})
                    if geom:
                        try:
                            new_op_w = geom.get('op_w_in')
                            new_op_h = geom.get('op_h_in')
                            new_ec_w = geom.get('ec_w_in')
                            if new_op_w is not None:
                                ax_w_in = max(0.25, float(new_op_w))
                            if new_op_h is not None:
                                ax_h_in = max(0.25, float(new_op_h))
                            if new_ec_w is not None:
                                ec_w_in = max(0.25, float(new_ec_w))
                            _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)
                        except Exception as e:
                            print(f"Warning: Could not apply geometry: {e}")
                elif version == 1:
                    cb_w_in, cb_gap_in, ec_gap_in_cur, ec_w_in_cur, ax_w_in_cur, ax_h_in_cur = _ensure_fixed_params(fig, ax, cbar.ax, ec_ax)
                    op = cfg.get('operando', {})
                    ec_cfg = cfg.get('ec', {})
                    gaps = cfg.get('gaps', {})
                    ax_w_in = float(op.get('ax_w_in', ax_w_in_cur))
                    ax_h_in = float(op.get('ax_h_in', ax_h_in_cur))
                    ec_w_in = float(ec_cfg.get('ec_w_in', ec_w_in_cur))
                    cb_w_in = float(gaps.get('cb_w_in', cb_w_in))
                    cb_gap_in = float(gaps.get('cb_gap_in', cb_gap_in))
                    ec_gap_in = float(gaps.get('ec_gap_in', ec_gap_in_cur))
                    _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)
                
                # Colormap
                op = cfg.get('operando', {})
                cmap = op.get('cmap')
                if cmap:
                    try:
                        im.set_cmap(cmap)
                        if cbar is not None:
                            cbar.update_normal(im)
                    except Exception:
                        pass
                
                # Apply operando WASD state (v2)
                if version >= 2:
                    op_wasd = op.get('wasd_state')
                    if op_wasd and isinstance(op_wasd, dict):
                        try:
                            # Apply spines
                            for side in ('top', 'bottom', 'left', 'right'):
                                if side in op_wasd and 'spine' in op_wasd[side]:
                                    sp = ax.spines.get(side)
                                    if sp:
                                        sp.set_visible(bool(op_wasd[side]['spine']))
                            # Apply ticks
                            ax.tick_params(axis='x', 
                                          top=bool(op_wasd.get('top', {}).get('ticks', False)),
                                          bottom=bool(op_wasd.get('bottom', {}).get('ticks', True)),
                                          labeltop=bool(op_wasd.get('top', {}).get('labels', False)),
                                          labelbottom=bool(op_wasd.get('bottom', {}).get('labels', True)))
                            ax.tick_params(axis='y',
                                          left=bool(op_wasd.get('left', {}).get('ticks', True)),
                                          right=bool(op_wasd.get('right', {}).get('ticks', False)),
                                          labelleft=bool(op_wasd.get('left', {}).get('labels', True)),
                                          labelright=bool(op_wasd.get('right', {}).get('labels', False)))
                            # Apply minor ticks
                            if op_wasd.get('top', {}).get('minor') or op_wasd.get('bottom', {}).get('minor'):
                                from matplotlib.ticker import AutoMinorLocator, NullFormatter
                                ax.xaxis.set_minor_locator(AutoMinorLocator())
                                ax.xaxis.set_minor_formatter(NullFormatter())
                            ax.tick_params(axis='x', which='minor',
                                          top=bool(op_wasd.get('top', {}).get('minor', False)),
                                          bottom=bool(op_wasd.get('bottom', {}).get('minor', False)))
                            if op_wasd.get('left', {}).get('minor') or op_wasd.get('right', {}).get('minor'):
                                from matplotlib.ticker import AutoMinorLocator, NullFormatter
                                ax.yaxis.set_minor_locator(AutoMinorLocator())
                                ax.yaxis.set_minor_formatter(NullFormatter())
                            ax.tick_params(axis='y', which='minor',
                                          left=bool(op_wasd.get('left', {}).get('minor', False)),
                                          right=bool(op_wasd.get('right', {}).get('minor', False)))
                            # Store WASD state
                            op_ts = {}
                            for side_key, prefix in [('top', 't'), ('bottom', 'b'), ('left', 'l'), ('right', 'r')]:
                                s = op_wasd.get(side_key, {})
                                op_ts[f'{prefix}_ticks'] = bool(s.get('ticks', False))
                                op_ts[f'{prefix}_labels'] = bool(s.get('labels', False))
                                op_ts[f'm{prefix}x' if prefix in 'tb' else f'm{prefix}y'] = bool(s.get('minor', False))
                            ax._saved_tick_state = op_ts
                            # Apply titles
                            ax._top_xlabel_on = bool(op_wasd.get('top', {}).get('title', False))
                            ax._right_ylabel_on = bool(op_wasd.get('right', {}).get('title', False))
                        except Exception as e:
                            print(f"Warning: Could not apply operando WASD state: {e}")
                    
                    # Apply operando spines
                    op_spines = op.get('spines', {})
                    if op_spines:
                        try:
                            for name, props in op_spines.items():
                                sp = ax.spines.get(name)
                                if sp and 'linewidth' in props:
                                    sp.set_linewidth(float(props['linewidth']))
                        except Exception:
                            pass
                    
                    # Apply operando tick widths
                    op_tick_widths = op.get('ticks', {}).get('widths', {})
                    if op_tick_widths:
                        try:
                            if op_tick_widths.get('x_major'): ax.tick_params(axis='x', which='major', width=op_tick_widths['x_major'])
                            if op_tick_widths.get('x_minor'): ax.tick_params(axis='x', which='minor', width=op_tick_widths['x_minor'])
                            if op_tick_widths.get('y_major'): ax.tick_params(axis='y', which='major', width=op_tick_widths['y_major'])
                            if op_tick_widths.get('y_minor'): ax.tick_params(axis='y', which='minor', width=op_tick_widths['y_minor'])
                        except Exception:
                            pass
                
                # Apply EC WASD state (v2, only if EC panel exists)
                if version >= 2 and ec_ax is not None:
                    ec_cfg = cfg.get('ec', {})
                    ec_wasd = ec_cfg.get('wasd_state')
                    if ec_wasd and isinstance(ec_wasd, dict):
                        try:
                            # Apply spines
                            for side in ('top', 'bottom', 'left', 'right'):
                                if side in ec_wasd and 'spine' in ec_wasd[side]:
                                    sp = ec_ax.spines.get(side)
                                    if sp:
                                        sp.set_visible(bool(ec_wasd[side]['spine']))
                            # Apply ticks
                            ec_ax.tick_params(axis='x',
                                             top=bool(ec_wasd.get('top', {}).get('ticks', False)),
                                             bottom=bool(ec_wasd.get('bottom', {}).get('ticks', True)),
                                             labeltop=bool(ec_wasd.get('top', {}).get('labels', False)),
                                             labelbottom=bool(ec_wasd.get('bottom', {}).get('labels', True)))
                            ec_ax.tick_params(axis='y',
                                             left=bool(ec_wasd.get('left', {}).get('ticks', True)),
                                             right=bool(ec_wasd.get('right', {}).get('ticks', False)),
                                             labelleft=bool(ec_wasd.get('left', {}).get('labels', True)),
                                             labelright=bool(ec_wasd.get('right', {}).get('labels', False)))
                            # Apply minor ticks
                            if ec_wasd.get('top', {}).get('minor') or ec_wasd.get('bottom', {}).get('minor'):
                                from matplotlib.ticker import AutoMinorLocator, NullFormatter
                                ec_ax.xaxis.set_minor_locator(AutoMinorLocator())
                                ec_ax.xaxis.set_minor_formatter(NullFormatter())
                            ec_ax.tick_params(axis='x', which='minor',
                                             top=bool(ec_wasd.get('top', {}).get('minor', False)),
                                             bottom=bool(ec_wasd.get('bottom', {}).get('minor', False)))
                            if ec_wasd.get('left', {}).get('minor') or ec_wasd.get('right', {}).get('minor'):
                                from matplotlib.ticker import AutoMinorLocator, NullFormatter
                                ec_ax.yaxis.set_minor_locator(AutoMinorLocator())
                                ec_ax.yaxis.set_minor_formatter(NullFormatter())
                            ec_ax.tick_params(axis='y', which='minor',
                                             left=bool(ec_wasd.get('left', {}).get('minor', False)),
                                             right=bool(ec_wasd.get('right', {}).get('minor', False)))
                            # Store WASD state
                            ec_ts = {}
                            for side_key, prefix in [('top', 't'), ('bottom', 'b'), ('left', 'l'), ('right', 'r')]:
                                s = ec_wasd.get(side_key, {})
                                ec_ts[f'{prefix}_ticks'] = bool(s.get('ticks', False))
                                ec_ts[f'{prefix}_labels'] = bool(s.get('labels', False))
                                ec_ts[f'm{prefix}x' if prefix in 'tb' else f'm{prefix}y'] = bool(s.get('minor', False))
                            ec_ax._saved_tick_state = ec_ts
                            # Apply titles
                            ec_ax._top_xlabel_on = bool(ec_wasd.get('top', {}).get('title', False))
                            ec_ax._right_ylabel_on = bool(ec_wasd.get('right', {}).get('title', False))
                        except Exception as e:
                            print(f"Warning: Could not apply EC WASD state: {e}")
                    
                    # Apply EC spines
                    ec_spines = ec_cfg.get('spines', {})
                    if ec_spines:
                        try:
                            for name, props in ec_spines.items():
                                sp = ec_ax.spines.get(name)
                                if sp and 'linewidth' in props:
                                    sp.set_linewidth(float(props['linewidth']))
                        except Exception:
                            pass
                    
                    # Apply EC tick widths
                    ec_tick_widths = ec_cfg.get('ticks', {}).get('widths', {})
                    if ec_tick_widths:
                        try:
                            if ec_tick_widths.get('x_major'): ec_ax.tick_params(axis='x', which='major', width=ec_tick_widths['x_major'])
                            if ec_tick_widths.get('x_minor'): ec_ax.tick_params(axis='x', which='minor', width=ec_tick_widths['x_minor'])
                            if ec_tick_widths.get('y_major'): ec_ax.tick_params(axis='y', which='major', width=ec_tick_widths['y_major'])
                            if ec_tick_widths.get('y_minor'): ec_ax.tick_params(axis='y', which='minor', width=ec_tick_widths['y_minor'])
                        except Exception:
                            pass
                    
                    # Apply EC curve properties (el command)
                    ec_curve = ec_cfg.get('curve', {})
                    if ec_curve:
                        ln = getattr(ec_ax, '_ec_line', None)
                        if ln is None and ec_ax.lines:
                            ln = ec_ax.lines[0]
                        if ln is not None:
                            try:
                                if 'color' in ec_curve:
                                    ln.set_color(ec_curve['color'])
                                if 'linewidth' in ec_curve:
                                    ln.set_linewidth(float(ec_curve['linewidth']))
                            except Exception as e:
                                print(f"Warning: Could not apply EC curve properties: {e}")
                
                # Apply reverse state (r command)
                if version >= 2:
                    try:
                        # Operando Y-axis reverse
                        op_y_reversed = op.get('y_reversed', False)
                        if op_y_reversed:
                            y0, y1 = ax.get_ylim()
                            if y0 < y1:  # Only reverse if not already reversed
                                ax.set_ylim(y1, y0)
                        else:
                            y0, y1 = ax.get_ylim()
                            if y0 > y1:  # Un-reverse if currently reversed
                                ax.set_ylim(y1, y0)
                    except Exception as e:
                        print(f"Warning: Could not apply operando reverse: {e}")
                    
                    try:
                        # EC Y-axis reverse
                        ec_cfg = cfg.get('ec', {})
                        ec_y_reversed = ec_cfg.get('y_reversed', False)
                        if ec_y_reversed:
                            ey0, ey1 = ec_ax.get_ylim()
                            if ey0 < ey1:  # Only reverse if not already reversed
                                ec_ax.set_ylim(ey1, ey0)
                                # Also update stored time ylim if present
                                if hasattr(ec_ax, '_saved_time_ylim') and isinstance(ec_ax._saved_time_ylim, (tuple, list)) and len(ec_ax._saved_time_ylim)==2:
                                    lo, hi = ec_ax._saved_time_ylim
                                    ec_ax._saved_time_ylim = (hi, lo)
                        else:
                            ey0, ey1 = ec_ax.get_ylim()
                            if ey0 > ey1:  # Un-reverse if currently reversed
                                ec_ax.set_ylim(ey1, ey0)
                                # Also update stored time ylim if present
                                if hasattr(ec_ax, '_saved_time_ylim') and isinstance(ec_ax._saved_time_ylim, (tuple, list)) and len(ec_ax._saved_time_ylim)==2:
                                    lo, hi = ec_ax._saved_time_ylim
                                    ec_ax._saved_time_ylim = (hi, lo)
                    except Exception as e:
                        print(f"Warning: Could not apply EC reverse: {e}")
                    
                    # Apply intensity range (oz command)
                    try:
                        intensity_range = op.get('intensity_range')
                        if intensity_range and isinstance(intensity_range, (list, tuple)) and len(intensity_range) == 2:
                            im.set_clim(float(intensity_range[0]), float(intensity_range[1]))
                            print(f"Applied intensity range: {intensity_range[0]:.4g} to {intensity_range[1]:.4g}")
                    except Exception as e:
                        print(f"Warning: Could not apply intensity range: {e}")
                    
                    # Apply ions mode (ey command)
                    try:
                        ec_cfg = cfg.get('ec', {})
                        ec_y_mode = ec_cfg.get('y_mode', 'time')
                        ion_params = ec_cfg.get('ion_params')
                        
                        if ec_y_mode == 'ions' and ion_params:
                            # Store parameters
                            ec_ax._ion_params = ion_params
                            ec_ax._ec_y_mode = 'ions'
                            
                            # Compute and apply ions formatter
                            import numpy as np
                            
                            time_h = getattr(ec_ax, '_ec_time_h', None)
                            current_mA = getattr(ec_ax, '_ec_current_mA', None)
                            voltage_v = getattr(ec_ax, '_ec_voltage_v', None)
                            
                            if current_mA is None:
                                print("Error: Current data is required for ion counting but is not available in the .mpt file.")
                                print("The .mpt file must contain the '<I>/mA' column to use this feature.")
                                print_menu()
                                continue
                            
                            if time_h is not None and current_mA is not None:
                                t = np.asarray(time_h, float)
                                i_mA = np.asarray(current_mA, float)
                                v = np.asarray(voltage_v, float)
                                
                                # Cumulative trapezoidal integration for capacity (mAh)
                                dt = np.diff(t)
                                cap_increments = np.empty_like(t)
                                cap_increments[0] = 0.0
                                if t.size > 1:
                                    cap_increments[1:] = 0.5 * (i_mA[:-1] + i_mA[1:]) * dt
                                cap_mAh = np.cumsum(cap_increments)
                                
                                # Convert to specific capacity
                                mass_g = float(ion_params.get('mass_mg', 0.0)) / 1000.0
                                with np.errstate(divide='ignore', invalid='ignore'):
                                    cap_mAh_g = np.where(mass_g > 0, cap_mAh / mass_g, np.nan)
                                    ions_delta = np.where(
                                        ion_params.get('cap_per_ion_mAh_g', 0.0) > 0,
                                        cap_mAh_g / float(ion_params['cap_per_ion_mAh_g']),
                                        np.nan
                                    )
                                
                                ions_abs = float(ion_params.get('start_ions', 0.0)) + ions_delta
                                ec_ax._ions_abs = ions_abs
                                
                                # Install formatter
                                y0, y1 = ec_ax.get_ylim()
                                ions_y0 = float(np.interp(y0, t, ions_abs, left=ions_abs[0], right=ions_abs[-1]))
                                ions_y1 = float(np.interp(y1, t, ions_abs, left=ions_abs[0], right=ions_abs[-1]))
                                rng = abs(ions_y1 - ions_y0)
                                
                                def _nice_step(r, approx=6):
                                    if not np.isfinite(r) or r <= 0:
                                        return 1.0
                                    raw = r / max(1, approx)
                                    exp = np.floor(np.log10(raw))
                                    base = raw / (10**exp)
                                    if base < 1.5:
                                        step = 1.0
                                    elif base < 3.5:
                                        step = 2.0
                                    elif base < 7.5:
                                        step = 5.0
                                    else:
                                        step = 10.0
                                    return step * (10**exp)
                                
                                step = _nice_step(rng)
                                
                                def _fmt(y, pos):
                                    try:
                                        val = float(np.interp(y, t, ions_abs, left=ions_abs[0], right=ions_abs[-1]))
                                        if step > 0:
                                            val = round(val / step) * step
                                        s = ("%f" % val).rstrip('0').rstrip('.')
                                        return s
                                    except Exception:
                                        return ""
                                
                                ec_ax.yaxis.set_major_formatter(FuncFormatter(_fmt))
                                ec_ax.yaxis.set_major_locator(MaxNLocator(nbins='auto', steps=[1,2,5], min_n_ticks=4))
                                
                                # Update label if not custom
                                if not getattr(ec_ax, '_custom_labels', {}).get('y_ions'):
                                    ec_ax.set_ylabel('Number of ions')
                                
                                print("Applied ions mode")
                    except Exception as e:
                        print(f"Warning: Could not apply ions mode: {e}")
                
                # Apply visibility states (n command)
                if version >= 2:
                    try:
                        fig_cfg = cfg.get('figure', {})
                        cb_visible = fig_cfg.get('cb_visible')
                        if cb_visible is not None:
                            cbar.ax.set_visible(bool(cb_visible))
                        
                        # Restore colorbar label mode
                        cb_label_mode = fig_cfg.get('cb_label_mode', 'normal')
                        if cb_label_mode == 'highlow':
                            # Switch to High/Low mode
                            cbar.ax.yaxis.set_ticklabels([])
                            # Remove existing High/Low labels if any
                            if hasattr(fig, '_cbar_high_text'):
                                try: fig._cbar_high_text.remove()
                                except: pass
                            if hasattr(fig, '_cbar_low_text'):
                                try: fig._cbar_low_text.remove()
                                except: pass
                            # Get current font settings
                            font_size = plt.rcParams.get('font.size', 10)
                            font_family = plt.rcParams.get('font.family', ['sans-serif'])
                            # Add new labels outside the colorbar (above and below)
                            fig._cbar_high_text = cbar.ax.text(0.5, 1.02, 'High', ha='center', va='bottom',
                                                                transform=cbar.ax.transAxes,
                                                                fontsize=font_size, fontfamily=font_family)
                            fig._cbar_low_text = cbar.ax.text(0.5, -0.02, 'Low', ha='center', va='top',
                                                               transform=cbar.ax.transAxes,
                                                               fontsize=font_size, fontfamily=font_family)
                            fig._colorbar_label_mode = 'highlow'
                        else:
                            # Ensure normal mode
                            fig._colorbar_label_mode = 'normal'
                            # Remove High/Low labels if they exist
                            if hasattr(fig, '_cbar_high_text'):
                                try: fig._cbar_high_text.remove()
                                except: pass
                                try: delattr(fig, '_cbar_high_text')
                                except: pass
                            if hasattr(fig, '_cbar_low_text'):
                                try: fig._cbar_low_text.remove()
                                except: pass
                                try: delattr(fig, '_cbar_low_text')
                                except: pass
                    except Exception:
                        pass
                    try:
                        ec_cfg = cfg.get('ec', {})
                        ec_visible = ec_cfg.get('visible')
                        if ec_visible is not None and ec_ax is not None:
                            ec_ax.set_visible(bool(ec_visible))
                    except Exception:
                        pass
                
                # Apply labelpads (title positioning)
                if version >= 2:
                    try:
                        op_pads = op.get('labelpads', {})
                        if op_pads:
                            if op_pads.get('x') is not None:
                                ax.xaxis.labelpad = op_pads['x']
                            if op_pads.get('y') is not None:
                                ax.yaxis.labelpad = op_pads['y']
                    except Exception as e:
                        print(f"Warning: Could not apply operando labelpads: {e}")
                    
                    try:
                        ec_cfg = cfg.get('ec', {})
                        ec_pads = ec_cfg.get('labelpads', {})
                        if ec_pads:
                            if ec_pads.get('x') is not None:
                                ec_ax.xaxis.labelpad = ec_pads['x']
                            if ec_pads.get('y') is not None:
                                ec_ax.yaxis.labelpad = ec_pads['y']
                    except Exception as e:
                        print(f"Warning: Could not apply EC labelpads: {e}")
                
                # Final redraw
                try:
                    fig.canvas.draw()
                except Exception:
                    fig.canvas.draw_idle()
                
                # Apply geometry if present
                if has_geometry:
                    try:
                        geom = cfg.get('axes_geometry', {})
                        op_geom = geom.get('operando', {})
                        ec_geom = geom.get('ec', {})
                        
                        if op_geom.get('xlabel'):
                            ax.set_xlabel(op_geom['xlabel'])
                        if op_geom.get('ylabel'):
                            ax.set_ylabel(op_geom['ylabel'])
                        if 'xlim' in op_geom and isinstance(op_geom['xlim'], list) and len(op_geom['xlim']) == 2:
                            ax.set_xlim(op_geom['xlim'][0], op_geom['xlim'][1])
                        if 'ylim' in op_geom and isinstance(op_geom['ylim'], list) and len(op_geom['ylim']) == 2:
                            ax.set_ylim(op_geom['ylim'][0], op_geom['ylim'][1])
                        
                        if ec_geom.get('xlabel'):
                            ec_ax.set_xlabel(ec_geom['xlabel'])
                        if ec_geom.get('ylabel'):
                            ec_ax.set_ylabel(ec_geom['ylabel'])
                        if 'xlim' in ec_geom and isinstance(ec_geom['xlim'], list) and len(ec_geom['xlim']) == 2:
                            ec_ax.set_xlim(ec_geom['xlim'][0], ec_geom['xlim'][1])
                        if 'ylim' in ec_geom and isinstance(ec_geom['ylim'], list) and len(ec_geom['ylim']) == 2:
                            ec_ax.set_ylim(ec_geom['ylim'][0], ec_geom['ylim'][1])
                        
                        print("Applied geometry (labels and limits)")
                        fig.canvas.draw_idle()
                    except Exception as e:
                        print(f"Warning: Could not apply geometry: {e}")
                
                print(f"Applied style from {path}")
            except Exception as e:
                print(f"Load style failed: {e}")
            print_menu()
        elif cmd == 'or':
            # Operando rename submenu
            try:
                if not hasattr(ax, '_custom_labels'):
                    ax._custom_labels = {'x': None, 'y': None}
                print("Rename Operando Axes: x=rename X label, y=rename Y label, q=back")
                print("Tip: Use LaTeX/mathtext for special characters:")
                print("  Subscript: H$_2$O → H₂O  |  Superscript: m$^2$ → m²")
                print("  Greek: $\\alpha$, $\\beta$  |  Angstrom: $\\AA$ → Å")
                while True:
                    sub = input("or> ").strip().lower()
                    if not sub:
                        continue
                    if sub == 'q':
                        break
                    if sub == 'x':
                        cur = ax.get_xlabel() or ''
                        lab = input(f"New operando X label (blank=cancel, current='{cur}'): ")
                        if lab:
                            _snapshot("rename-op-x")
                            try:
                                ax.set_xlabel(lab)
                                ax._custom_labels['x'] = lab
                                # Update top duplicate label if shown
                                base_xlabel = lab
                                _position_top_xlabel(ax, base_xlabel)
                            except Exception:
                                pass
                    elif sub == 'y':
                        cur = ax.get_ylabel() or ''
                        lab = input(f"New operando Y label (blank=cancel, current='{cur}'): ")
                        if lab:
                            _snapshot("rename-op-y")
                            try:
                                ax.set_ylabel(lab)
                                ax._custom_labels['y'] = lab
                                # Update right duplicate label if shown
                                base_ylabel = lab
                                _position_right_ylabel(ax, base_ylabel)
                            except Exception:
                                pass
                    try:
                        fig.canvas.draw()
                    except Exception:
                        fig.canvas.draw_idle()
            except Exception as e:
                print(f"Rename failed: {e}")
            print_menu()
        elif cmd == 'er':
            # EC rename submenu (tracks separate labels for time vs ions modes)
            if ec_ax is None:
                print("EC panel not available (no .mpt file in folder).")
                print_menu()
                continue
            try:
                if not hasattr(ec_ax, '_custom_labels'):
                    ec_ax._custom_labels = {'x': None, 'y_time': None, 'y_ions': None}
                print("Rename EC Axes: x=rename X label, y=rename Y label (mode-aware), q=back")
                print("Tip: Use LaTeX/mathtext for special characters:")
                print("  Subscript: H$_2$O → H₂O  |  Superscript: m$^2$ → m²")
                print("  Greek: $\\alpha$, $\\beta$  |  Angstrom: $\\AA$ → Å")
                while True:
                    sub = input("er> ").strip().lower()
                    if not sub:
                        continue
                    if sub == 'q':
                        break
                    if sub == 'x':
                        cur = ec_ax.get_xlabel() or ''
                        lab = input(f"New EC X label (blank=cancel, current='{cur}'): ")
                        if lab:
                            _snapshot("rename-ec-x")
                            try:
                                ec_ax.set_xlabel(lab)
                                ec_ax._custom_labels['x'] = lab
                                # Update top duplicate label if shown
                                _position_top_xlabel(ec_ax, lab)
                            except Exception:
                                pass
                    elif sub == 'y':
                        cur = ec_ax.get_ylabel() or ''
                        lab = input(f"New EC Y label (blank=cancel, current='{cur}'): ")
                        if lab:
                            _snapshot("rename-ec-y")
                            try:
                                ec_ax.set_ylabel(lab)
                                # Store against current mode
                                mode = getattr(ec_ax, '_ec_y_mode', 'time')
                                if mode == 'ions':
                                    ec_ax._custom_labels['y_ions'] = lab
                                else:
                                    ec_ax._custom_labels['y_time'] = lab
                                # Update right duplicate label if shown
                                _position_right_ylabel(ec_ax, lab)
                            except Exception:
                                pass
                    try:
                        fig.canvas.draw()
                    except Exception:
                        fig.canvas.draw_idle()
            except Exception as e:
                print(f"Rename failed: {e}")
            print_menu()
        elif cmd == 'el':
            # EC line style submenu: color and linewidth
            if ec_ax is None:
                print("EC panel not available (no .mpt file in folder).")
                print_menu()
                continue
            try:
                # Resolve EC line handle
                ln = getattr(ec_ax, '_ec_line', None)
                if ln is None and ec_ax.lines:
                    ln = ec_ax.lines[0]
                if ln is None:
                    print("No EC line found to style.")
                    print_menu(); continue
                print("EC line submenu: c=color, l=linewidth, q=back")
                while True:
                    sub = input("el> ").strip().lower()
                    if not sub:
                        continue
                    if sub == 'q':
                        break
                    if sub == 'c':
                        cur = ln.get_color()
                        val = input(f"Color (name or hex, current={cur}, blank=cancel): ").strip()
                        if not val:
                            continue
                        _snapshot("ec-line-color")
                        try:
                            ln.set_color(val)
                            fig.canvas.draw_idle()
                        except Exception as e:
                            print(f"Invalid color: {e}")
                    elif sub == 'l':
                        cur = ln.get_linewidth()
                        val = input(f"Line width (current={cur}, blank=cancel): ").strip()
                        if not val:
                            continue
                        _snapshot("ec-line-width")
                        try:
                            lw = float(val)
                            if lw > 0:
                                ln.set_linewidth(lw)
                                fig.canvas.draw_idle()
                            else:
                                print("Width must be > 0.")
                        except Exception as e:
                            print(f"Invalid width: {e}")
                    else:
                        print("Unknown option.")
            except Exception as e:
                print(f"EC line styling failed: {e}")
            print_menu()
        elif cmd == 'et':
            if ec_ax is None:
                print("EC panel not available (no .mpt file in folder).")
                print_menu()
                continue
            while True:
                cur = ec_ax.get_ylim(); print(f"Current EC time range (Y): {cur[0]:.4g} {cur[1]:.4g}")
                line = input("New time range (min max, q=back): ").strip()
                if not line or line.lower() == 'q':
                    break
                _snapshot("ec-time-range")
                try:
                    lo, hi = map(float, line.split())
                    ec_ax.set_ylim(lo, hi)
                    # Persist chosen time-mode limits so ey toggles won't override
                    try:
                        ec_ax._saved_time_ylim = (lo, hi)
                    except Exception:
                        pass
                    # If in ions mode, refresh formatter/locator for nice ticks
                    if getattr(ec_ax, '_ec_y_mode', 'time') == 'ions':
                        try:
                            import numpy as np
                            t = np.asarray(getattr(ec_ax, '_ec_time_h'))
                            ions_abs = getattr(ec_ax, '_ions_abs', None)
                            if ions_abs is not None:
                                y0, y1 = ec_ax.get_ylim()
                                ions_y0 = float(np.interp(y0, t, ions_abs, left=ions_abs[0], right=ions_abs[-1]))
                                ions_y1 = float(np.interp(y1, t, ions_abs, left=ions_abs[0], right=ions_abs[-1]))
                                rng = abs(ions_y1 - ions_y0)
                                def _nice_step(r, approx=6):
                                    if not np.isfinite(r) or r <= 0:
                                        return 1.0
                                    raw = r / max(1, approx)
                                    exp = np.floor(np.log10(raw))
                                    base = raw / (10**exp)
                                    if base < 1.5:
                                        step = 1.0
                                    elif base < 3.5:
                                        step = 2.0
                                    elif base < 7.5:
                                        step = 5.0
                                    else:
                                        step = 10.0
                                    return step * (10**exp)
                                step = _nice_step(rng)
                                def _ions_format(y, pos):
                                    try:
                                        val = float(np.interp(y, t, ions_abs, left=ions_abs[0], right=ions_abs[-1]))
                                        if step > 0:
                                            val = round(val / step) * step
                                        s = ("%f" % val).rstrip('0').rstrip('.')
                                        return s
                                    except Exception:
                                        return ""
                                ec_ax.yaxis.set_major_formatter(FuncFormatter(_ions_format))
                                # Use 1-2-5 locator for pleasant spacing
                                if not hasattr(ec_ax, '_prev_ylocator'):
                                    try:
                                        ec_ax._prev_ylocator = ec_ax.yaxis.get_major_locator()
                                    except Exception:
                                        ec_ax._prev_ylocator = None
                                ec_ax.yaxis.set_major_locator(MaxNLocator(nbins='auto', steps=[1,2,5], min_n_ticks=4))
                        except Exception:
                            pass
                    fig.canvas.draw_idle()
                except Exception as e:
                    print(f"Invalid range: {e}")
            print_menu()
        elif cmd == 'ey':
            # Submenu: n = show number of ions, t = back to time
            if ec_ax is None:
                print("EC panel not available (no .mpt file in folder).")
                print_menu()
                continue
            try:
                time_h = getattr(ec_ax, '_ec_time_h', None)
                voltage_v = getattr(ec_ax, '_ec_voltage_v', None)
                current_mA = getattr(ec_ax, '_ec_current_mA', None)
                ln = getattr(ec_ax, '_ec_line', None)
                if time_h is None or ln is None:
                    print("EC data not available for ion calculation.")
                    print_menu(); continue
                if current_mA is None:
                    print("Error: Current data is required for ion counting but is not available in the .mpt file.")
                    print("The .mpt file must contain the '<I>/mA' column to use this feature.")
                    print_menu(); continue
                while True:
                    sub = input("ey submenu: n=ions, t=time, q=back: ").strip().lower()
                    if not sub:
                        continue
                    if sub == 'q':
                        break
                    if sub == 'n':
                        # Get or update parameters; allow reuse of previous values
                        params = getattr(ec_ax, '_ion_params', {"mass_mg": None, "cap_per_ion_mAh_g": None, "start_ions": None, "material": "cathode"})
                        mass_mg = params.get('mass_mg')
                        cap_per_ion = params.get('cap_per_ion_mAh_g')
                        start_ions = params.get('start_ions')
                        material = params.get('material', 'cathode')
                        need_input = (mass_mg is None or cap_per_ion is None or start_ions is None)
                        if need_input:
                            prompt = "Enter mass(mg), capacity-per-ion(mAh g⁻¹), start-ions (e.g. 4.5 26.8 0), q=cancel: "
                        else:
                            prompt = f"Enter mass,cap-per-ion,start-ions (blank=reuse {mass_mg} {cap_per_ion} {start_ions}; q=cancel): "
                        s = input(prompt).strip()
                        if not s:
                            if need_input:
                                continue
                            # reuse previous values
                        elif s.lower() == 'q':
                            continue
                        else:
                            try:
                                vals = list(map(float, s.split()))
                                if len(vals) != 3:
                                    raise ValueError()
                                mass_mg, cap_per_ion, start_ions = vals
                            except Exception:
                                print("Bad input. Expect three numbers: mass, capacity-per-ion, start-ions.")
                                continue
                            if material is None:
                                material = 'cathode'
                            ec_ax._ion_params = {"mass_mg": mass_mg, "cap_per_ion_mAh_g": cap_per_ion, "start_ions": start_ions, "material": material}
                        _snapshot("ey->ions")
                        import numpy as np
                        t = np.asarray(time_h, float)
                        i_mA = np.asarray(current_mA, float)
                        v = np.asarray(voltage_v, float)
                        # Cumulative trapezoidal integration for capacity (mAh)
                        dt = np.diff(t)
                        cap_increments = np.empty_like(t)
                        cap_increments[0] = 0.0
                        if t.size > 1:
                            cap_increments[1:] = 0.5 * (i_mA[:-1] + i_mA[1:]) * dt
                        cap_mAh = np.cumsum(cap_increments)
                        mass_g = float(mass_mg) / 1000.0
                        with np.errstate(divide='ignore', invalid='ignore'):
                            cap_mAh_g = np.where(mass_g>0, cap_mAh / mass_g, np.nan)
                            ions_delta = np.where(cap_per_ion>0, cap_mAh_g / float(cap_per_ion), np.nan)
                        ions_abs = float(start_ions) + ions_delta
                        # Segment by charge/discharge: boundaries where sign changes (ignore tiny currents)
                        sgn = np.sign(i_mA)
                        eps = 1e-9
                        sgn[np.isclose(i_mA, 0.0, atol=eps)] = 0.0
                        # propagate zeros to last nonzero for segmentation logic
                        last = 0.0
                        seg_bounds = [0]
                        for k in range(1, len(sgn)):
                            cur = sgn[k] if sgn[k] != 0 else last
                            prev = sgn[k-1] if sgn[k-1] != 0 else last
                            if k == 1:
                                last = prev
                            if cur != prev:
                                seg_bounds.append(k)
                            last = cur
                        seg_bounds.append(len(sgn)-1)
                        # For cathode materials, ions should decrease during charge (voltage rising)
                        try:
                            if material and str(material).lower().startswith('cat') and len(seg_bounds) > 1:
                                a0 = seg_bounds[0]
                                b0 = seg_bounds[1]
                                if b0 > a0:
                                    dv = float(v[b0]) - float(v[a0])
                                    dt_seg = float(t[b0]) - float(t[a0])
                                    if dt_seg > 0 and np.isfinite(dv):
                                        slope = dv / dt_seg  # dV/dt
                                        # Expected ions change sign for cathode: -sign(dV/dt)
                                        expected = -np.sign(slope) if slope != 0 else 0.0
                                        actual = np.sign(float(ions_abs[b0]) - float(ions_abs[a0]))
                                        if expected != 0 and actual != 0 and actual != expected:
                                            # Flip ions direction globally
                                            ions_abs = float(start_ions) - ions_delta
                                            setattr(ec_ax, '_ion_inverted', True)
                                            # Quietly invert without verbose console output
                                        else:
                                            setattr(ec_ax, '_ion_inverted', False)
                        except Exception:
                            pass
                        # Keep curve unchanged; only change y-axis labeling to ions(t)
                        # Clear previous annotations and guides
                        for a in getattr(ec_ax, '_ion_annots', []):
                            try: a.remove()
                            except Exception: pass
                        ec_ax._ion_annots = []
                        for gl in getattr(ec_ax, '_ion_guides', []):
                            try: gl.remove()
                            except Exception: pass
                        ec_ax._ion_guides = []
                        # Persist ions for later reuse (e.g., when Y-range changes)
                        try:
                            setattr(ec_ax, '_ions_abs', np.asarray(ions_abs, float))
                        except Exception:
                            pass
                        # Save current time-mode ylim once, to restore on exit
                        try:
                            if getattr(ec_ax, '_ec_y_mode', 'time') != 'ions' and not hasattr(ec_ax, '_saved_time_ylim'):
                                ec_ax._saved_time_ylim = ec_ax.get_ylim()
                        except Exception:
                            pass
                        # Install ions formatter for Y axis (time -> ions)
                        # Determine a "nice" rounding step based on visible ions range
                        try:
                            y0, y1 = ec_ax.get_ylim()
                        except Exception:
                            y0, y1 = (t[0], t[-1])
                        ions_y0 = float(np.interp(y0, t, ions_abs, left=ions_abs[0], right=ions_abs[-1]))
                        ions_y1 = float(np.interp(y1, t, ions_abs, left=ions_abs[0], right=ions_abs[-1]))
                        rng = abs(ions_y1 - ions_y0) if np.isfinite(ions_y0) and np.isfinite(ions_y1) else (float(np.nanmax(ions_abs)) - float(np.nanmin(ions_abs)))
                        def _nice_step(r, approx=6):
                            if not np.isfinite(r) or r <= 0:
                                return 1.0
                            raw = r / max(1, approx)
                            exp = np.floor(np.log10(raw))
                            base = raw / (10**exp)
                            if base < 1.5:
                                step = 1.0
                            elif base < 3.5:
                                step = 2.0
                            elif base < 7.5:
                                step = 5.0
                            else:
                                step = 10.0
                            return step * (10**exp)
                        step = _nice_step(rng)
                        def _ions_format(y, pos):
                            try:
                                val = float(np.interp(y, t, ions_abs, left=ions_abs[0], right=ions_abs[-1]))
                                if step > 0:
                                    val = round(val / step) * step
                                # Trim trailing zeros nicely
                                s = ("%f" % val).rstrip('0').rstrip('.')
                                return s
                            except Exception:
                                return ""
                        # Save previous formatter once
                        if not hasattr(ec_ax, '_prev_yformatter'):
                            try:
                                ec_ax._prev_yformatter = ec_ax.yaxis.get_major_formatter()
                            except Exception:
                                ec_ax._prev_yformatter = None
                        ec_ax.yaxis.set_major_formatter(FuncFormatter(_ions_format))
                        # Save previous locator once
                        if not hasattr(ec_ax, '_prev_ylocator'):
                            try:
                                ec_ax._prev_ylocator = ec_ax.yaxis.get_major_locator()
                            except Exception:
                                ec_ax._prev_ylocator = None
                        # Apply 1-2-5 major locator for pleasant tick spacing
                        try:
                            ec_ax.yaxis.set_major_locator(MaxNLocator(nbins='auto', steps=[1,2,5], min_n_ticks=4))
                        except Exception:
                            pass
                        # Set default ions label or custom override
                        try:
                            label = 'Number of ions'
                            if hasattr(ec_ax, '_custom_labels') and ec_ax._custom_labels.get('y_ions'):
                                label = ec_ax._custom_labels['y_ions']
                            ec_ax.set_ylabel(label)
                        except Exception:
                            pass
                        try:
                            ec_ax.yaxis.tick_right(); ec_ax.yaxis.set_label_position('right')
                        except Exception:
                            pass
                        # Annotate and mark end of each non-empty segment
                        def _fmt2(x: float) -> str:
                            s = ("%0.2f" % float(x)).rstrip('0').rstrip('.')
                            return s if s else "0"
                        # Expand EC x-range to the right to make room for right-side labels
                        try:
                            x0, x1 = ec_ax.get_xlim()
                            xr = (x1 - x0) if x1 > x0 else 0.0
                            if xr > 0 and not getattr(ec_ax, '_ions_xlim_expanded', False):
                                # Save previous once per ions session and expand once
                                setattr(ec_ax, '_prev_ec_xlim', (x0, x1))
                                ec_ax.set_xlim(x0, x1 + 0.08 * xr)
                                setattr(ec_ax, '_ions_xlim_expanded', True)
                        except Exception:
                            pass
                        # Recompute after potential xlim expansion
                        try:
                            x0, x1 = ec_ax.get_xlim()
                            xr = (x1 - x0) if x1 > x0 else 0.0
                            x_right_inset = x1 - 0.02 * xr if xr > 0 else x1
                        except Exception:
                            x_right_inset = None
                        for si in range(len(seg_bounds)-1):
                            a = seg_bounds[si]
                            b = seg_bounds[si+1]
                            if b >= a:
                                end_i = float(ions_abs[b])
                                end_t = float(t[b])
                                end_v = float(v[b])
                                # Light dashed guide line at segment end (horizontal at time coordinate)
                                try:
                                    guide = ec_ax.axhline(y=end_t, color='0.7', linestyle='--', linewidth=0.8, alpha=0.5, zorder=0)
                                    ec_ax._ion_guides.append(guide)
                                except Exception:
                                    pass
                                # Text annotation slightly offset from the curve, with at most 2 decimals
                                try:
                                    # Place all tags at the right edge inside the frame and above the dashed line
                                    xi = x_right_inset if x_right_inset is not None else end_v
                                    txt = ec_ax.annotate(_fmt2(end_i), xy=(xi, end_t), xytext=(0, 4), textcoords='offset points',
                                                         ha='right', va='bottom', fontsize=9,
                                                         bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='0.7', alpha=0.8))
                                    ec_ax._ion_annots.append(txt)
                                except Exception:
                                    pass
                                # No marker plotted to avoid creating new line artists
                        # Do not alter existing EC Y-limits here; keep user choice intact
                        ec_ax._ec_y_mode = 'ions'
                    elif sub == 't':
                        _snapshot("ey->time")
                        # Revert to time view
                        for a in getattr(ec_ax, '_ion_annots', []):
                            try: a.remove()
                            except Exception: pass
                        ec_ax._ion_annots = []
                        for gl in getattr(ec_ax, '_ion_guides', []):
                            try: gl.remove()
                            except Exception: pass
                        ec_ax._ion_guides = []
                        # Clear cached ions data
                        try:
                            setattr(ec_ax, '_ions_abs', None)
                        except Exception:
                            pass
                        # No extra markers to clear
                        # Restore previous y-axis formatter and label
                        prev_fmt = getattr(ec_ax, '_prev_yformatter', None)
                        try:
                            if prev_fmt is not None:
                                ec_ax.yaxis.set_major_formatter(prev_fmt)
                            else:
                                from matplotlib.ticker import ScalarFormatter
                                ec_ax.yaxis.set_major_formatter(ScalarFormatter())
                            # Restore previous locator if available
                            prev_loc = getattr(ec_ax, '_prev_ylocator', None)
                            if prev_loc is not None:
                                ec_ax.yaxis.set_major_locator(prev_loc)
                        except Exception:
                            pass
                        # Set default time label or custom override
                        try:
                            label = 'Time (h)'
                            if hasattr(ec_ax, '_custom_labels') and ec_ax._custom_labels.get('y_time'):
                                label = ec_ax._custom_labels['y_time']
                            ec_ax.set_ylabel(label)
                        except Exception:
                            pass
                        try:
                            ec_ax.yaxis.tick_right(); ec_ax.yaxis.set_label_position('right')
                        except Exception:
                            pass
                        # Restore EC x-limits if previously expanded for ions labels
                        prev_xlim = getattr(ec_ax, '_prev_ec_xlim', None)
                        if prev_xlim and isinstance(prev_xlim, tuple) and len(prev_xlim) == 2:
                            try:
                                ec_ax.set_xlim(*prev_xlim)
                            except Exception:
                                pass
                        try:
                            setattr(ec_ax, '_prev_ec_xlim', None)
                            setattr(ec_ax, '_ions_xlim_expanded', False)
                        except Exception:
                            pass
                        # Restore prior time-mode ylim if saved; else leave as-is
                        prev_time_ylim = getattr(ec_ax, '_saved_time_ylim', None)
                        if prev_time_ylim and isinstance(prev_time_ylim, (list, tuple)) and len(prev_time_ylim)==2:
                            try:
                                ec_ax.set_ylim(*prev_time_ylim)
                            except Exception:
                                pass
                        ec_ax._ec_y_mode = 'time'
                    # Draw after any submenu action
                    try:
                        fig.canvas.draw()
                    except Exception:
                        fig.canvas.draw_idle()
            except Exception as e:
                print(f"Error in ey submenu: {e}")
            print_menu()
        elif cmd == 'g':
            # Preserve legacy size submenu
            cur_w, cur_h = _get_fig_size(fig)
            print(f"Current canvas size: {cur_w:.2f} x {cur_h:.2f} in (W x H)")
            print("Canvas: only figure size will change; panel widths/gaps are not altered.")
            line = input("New canvas size 'W H' (blank=cancel): ").strip()
            if line:
                _snapshot("canvas-size")
                try:
                    parts = line.split()
                    if len(parts) == 2:
                        W = max(1.0, float(parts[0])); H = max(1.0, float(parts[1]))
                        
                        # Capture current panel dimensions in inches before resize
                        old_w, old_h = cur_w, cur_h
                        cb_pos = cbar.ax.get_position()
                        ax_pos = ax.get_position()
                        ec_pos = ec_ax.get_position() if ec_ax else None
                        
                        cb_w_in = cb_pos.width * old_w
                        cb_h_in = cb_pos.height * old_h
                        cb_gap_in = (ax_pos.x0 - (cb_pos.x0 + cb_pos.width)) * old_w
                        ax_w_in = ax_pos.width * old_w
                        ax_h_in = ax_pos.height * old_h
                        if ec_ax:
                            ec_gap_in = (ec_pos.x0 - (ax_pos.x0 + ax_pos.width)) * old_w
                            ec_w_in = ec_pos.width * old_w
                        
                        # Resize figure
                        fig.set_size_inches(W, H, forward=True)
                        
                        # Recalculate fractional positions to maintain inch-based dimensions
                        total_w_in = cb_w_in + cb_gap_in + ax_w_in
                        if ec_ax:
                            total_w_in += ec_gap_in + ec_w_in
                        
                        # Center the group horizontally
                        group_left = max(0.0, (W - total_w_in) / (2.0 * W))
                        y0 = max(0.0, (H - ax_h_in) / (2.0 * H))
                        
                        # Set new fractional positions
                        cb_x0 = group_left
                        cb_wf = cb_w_in / W
                        cb_hf = ax_h_in / H
                        cbar.ax.set_position([cb_x0, y0, cb_wf, cb_hf])
                        
                        ax_x0 = cb_x0 + cb_wf + (cb_gap_in / W)
                        ax_wf = ax_w_in / W
                        ax_hf = ax_h_in / H
                        ax.set_position([ax_x0, y0, ax_wf, ax_hf])
                        
                        if ec_ax:
                            ec_x0 = ax_x0 + ax_wf + (ec_gap_in / W)
                            ec_wf = ec_w_in / W
                            ec_hf = ax_h_in / H
                            ec_ax.set_position([ec_x0, y0, ec_wf, ec_hf])
                        
                        fig.canvas.draw_idle()
                except Exception as e:
                    print(f"Canvas resize failed: {e}")
            print_menu()
        else:
            print("Unknown command.")
            print_menu()

__all__ = ["operando_ec_interactive_menu"]

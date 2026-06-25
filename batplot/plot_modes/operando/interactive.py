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
import sys

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
from matplotlib.ticker import FuncFormatter, MaxNLocator, AutoMinorLocator, NullFormatter, NullLocator, MultipleLocator, AutoLocator  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]

# Import UI positioning functions
from ...ui import position_top_xlabel as _ui_position_top_xlabel
from ...ui import position_right_ylabel as _ui_position_right_ylabel
from ...ui import position_bottom_xlabel as _ui_position_bottom_xlabel
from ...ui import position_left_ylabel as _ui_position_left_ylabel
from ...ui import (
    capture_axes_tick_locators,
    restore_axes_tick_locators,
    capture_axis_tick_locators,
    restore_axis_tick_locators,
    apply_wasd_minor_ticks,
)
from ..common.interactive_state import right_y_major_visibility
from ..common.files import format_file_timestamp as _format_file_timestamp
from ..common.sources import normalize_source_paths
from ..common.terminal import (
    FilterIMKWarning as _FilterIMKWarning,
    colorize_prompt as _colorize_prompt,
    colorize_single_key_inline_commands as _colorize_inline_commands,
    safe_input as _safe_input,
)
from ..common.spines import (
    apply_changed_side_title_positions,
    apply_frame_and_tick_widths,
    apply_wasd_spines,
    apply_wasd_tick_params,
    keep_yaxis_label_on_side,
    parse_frame_tick_widths,
    run_spine_tick_menu,
    wasd_to_tick_state,
)
from ..common.menus import run_font_menu
from ..common.palettes import TAB10_HEX, palette_items
from ..common.title_offsets import capture_title_offsets, restore_title_offsets
from .layout import (
    _apply_group_layout_inches,
    _detach_mpl_colorbar_callbacks,
    _draw_custom_colorbar,
    _ensure_fixed_params,
    _get_fig_size,
    _get_geometry_snapshot,
    _redraw_operando_cif_if_present,
    _safe_set_clim,
    _update_custom_colorbar,
)
from .menu import print_operando_ec_menu
from .actions import (
    OperandoActionContext,
    handle_export_figure,
    handle_export_style,
    handle_import_style,
    handle_quick_overwrite_figure,
    handle_quick_overwrite_session,
    handle_quick_overwrite_style,
    handle_save_session,
    handle_undo,
)
from .colors import _ensure_operando_colormap, run_operando_colormap_menu
from .line_style import run_ec_line_style_menu
from .grid import run_ec_grid_menu
from .labels import run_operando_ec_rename_menu, run_operando_rename_menu
from .peaks import run_peak_search_menu
from .visibility import run_visibility_menu
from .ions_axis import (
    format_ions_value,
    install_ec_ions_y_display,
    ions_value_at_time,
    restore_ec_time_y_display,
)

# Import color utilities for palette preview and user colors
from ...color_utils import (
    palette_preview,
    resolve_color_token,
    ensure_colormap,
    get_colormap,
)
from matplotlib import colors as mcolors  # type: ignore[import-untyped]
import re
import traceback
from io import StringIO

import matplotlib as mpl  # type: ignore[import-untyped]
import matplotlib.lines  # type: ignore[import-untyped]
from matplotlib.ticker import ScalarFormatter  # type: ignore[import-untyped]
try:
    from matplotlib.widgets import RangeSlider, Button  # type: ignore[import-untyped]
except ImportError:
    RangeSlider = None  # type: ignore[misc, assignment]
    Button = None  # type: ignore[misc, assignment]

from .plot import _draw_operando_cif_ticks
from .session import dump_operando_session
from ...utils import (
    choose_style_file, convert_label_shortcuts, natural_sort_key, print_label_latex_tips,
    print_recent_axis_names, remember_axis_name,
    choose_save_path, list_files_in_subdirectory, get_organized_path,
    ensure_exact_case_filename, _confirm_overwrite, normalize_label_text,
)

def _axis_tick_width(axis_obj, which: str = 'major'):
    """Return tick line width from axis tick params or rc defaults."""
    try:
        tick_kw = axis_obj._major_tick_kw if which == 'major' else axis_obj._minor_tick_kw
        width = tick_kw.get('width')
        if width is None:
            axis_name = getattr(axis_obj, 'axis_name', 'x')
            rc_key = f"{axis_name}tick.{which}.width"
            width = plt.rcParams.get(rc_key)
        if width is not None:
            return float(width)
    except (AttributeError, TypeError, ValueError, KeyError):
        pass
    return None


def _colorize_menu(text):
    """Colorize menu items: command in cyan, colon in white, description in default."""
    if ':' not in text:
        return text
    parts = text.split(':', 1)
    cmd = parts[0].strip()
    desc = parts[1].strip() if len(parts) > 1 else ''
    return f"\033[96m{cmd}\033[0m: {desc}"  # Cyan for command, default for description


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

def _maybe_reapply_dqdv_2d_contour(fig, ax, im, cbar=None) -> None:
    """Re-apply butterfly voltage formatter only (does not reset labels, limits, or WASD)."""
    if not getattr(fig, "_is_dqdv_2d_contour", False):
        return
    try:
        from ..electrochem.interactive import reapply_dqdv_2d_contour_axes
        reapply_dqdv_2d_contour_axes(fig, ax, im, cbar, style_mode="minimal")
    except Exception:
        pass


def _restore_dqdv_2d_operando_labels(ax, op_labels: dict) -> None:
    """Restore operando axis titles after undo / style import in 2D dQ/dV mode."""
    if not isinstance(op_labels, dict):
        return
    try:
        if op_labels.get("x") is not None:
            ax.set_xlabel(str(op_labels.get("x") or ""))
            if not hasattr(ax, "_custom_labels"):
                ax._custom_labels = {"x": None, "y": None}
            ax._custom_labels["x"] = op_labels.get("x")
        if op_labels.get("y") is not None:
            ax.set_ylabel(str(op_labels.get("y") or ""))
            if not hasattr(ax, "_custom_labels"):
                ax._custom_labels = {"x": None, "y": None}
            ax._custom_labels["y"] = op_labels.get("y")
    except Exception:
        pass


def _dqdv_2d_print_potential_window(fig) -> None:
    """Print current butterfly potential limits for the 2D dQ/dV contour."""
    try:
        v_lo = float(fig._dqdv_2d_v_lo)
        v_hi = float(fig._dqdv_2d_v_hi)
    except Exception:
        print("Potential window (V): unknown")
        return
    print(
        f"Current potential window (V): {v_lo:.4g} {v_hi:.4g}  "
        f"(left discharge: {v_hi:.4g}→{v_lo:.4g}, right charge: {v_lo:.4g}→{v_hi:.4g})"
    )


def _dqdv_2d_potential_window_menu(fig, ax, im, cbar, snapshot_fn) -> None:
    """ox submenu for 2D dQ/dV contour: set V_lo/V_hi and rebuild butterfly map."""
    from ..electrochem.interactive import update_dqdv_2d_potential_window

    def _apply(v_lo: float, v_hi: float, note: str) -> None:
        snapshot_fn(note)
        if update_dqdv_2d_potential_window(fig, ax, im, v_lo, v_hi):
            if cbar is not None:
                try:
                    _update_custom_colorbar(
                        cbar.ax, im,
                        label=getattr(cbar.ax, "_colorbar_label", None),
                        label_mode=getattr(fig, "_colorbar_label_mode", "highlow"),
                    )
                except Exception:
                    pass
            try:
                fig.canvas.draw_idle()
            except Exception:
                pass
            _dqdv_2d_print_potential_window(fig)

    while True:
        _dqdv_2d_print_potential_window(fig)
        print("  " + _colorize_menu("limit1 limit2: set both limits (either order, e.g. 2 3)"))
        print("  " + _colorize_menu("w: upper voltage only (V_hi)"))
        print("  " + _colorize_menu("s: lower voltage only (V_lo)"))
        print("  " + _colorize_menu("a: auto (restore initial window)"))
        print("  " + _colorize_menu("q: back"))
        line = _safe_input(_colorize_prompt("Potential window V (w/s/a/q): ")).strip()
        if not line or line.lower() == "q":
            break
        if line.lower() == "a":
            try:
                v_lo = float(fig._dqdv_2d_v_lo_orig)
                v_hi = float(fig._dqdv_2d_v_hi_orig)
            except Exception:
                print("No initial potential window stored.")
                continue
            _apply(v_lo, v_hi, "dqdv2d-potential-auto")
            continue
        if line.lower() == "w":
            try:
                v_lo = float(fig._dqdv_2d_v_lo)
                v_hi = float(fig._dqdv_2d_v_hi)
            except Exception:
                continue
            val = _safe_input(_colorize_inline_commands(
                f"New upper voltage V_hi (current V_lo={v_lo:.4g}, q=back): "
            )).strip()
            if not val or val.lower() == "q":
                continue
            try:
                new_hi = float(val)
            except ValueError:
                print("Invalid value.")
                continue
            if new_hi <= v_lo:
                print(f"V_hi must be greater than V_lo ({v_lo:.4g}).")
                continue
            _apply(v_lo, new_hi, "dqdv2d-potential-w")
            continue
        if line.lower() == "s":
            try:
                v_lo = float(fig._dqdv_2d_v_lo)
                v_hi = float(fig._dqdv_2d_v_hi)
            except Exception:
                continue
            val = _safe_input(_colorize_inline_commands(
                f"New lower voltage V_lo (current V_hi={v_hi:.4g}, q=back): "
            )).strip()
            if not val or val.lower() == "q":
                continue
            try:
                new_lo = float(val)
            except ValueError:
                print("Invalid value.")
                continue
            if new_lo >= v_hi:
                print(f"V_lo must be less than V_hi ({v_hi:.4g}).")
                continue
            _apply(new_lo, v_hi, "dqdv2d-potential-s")
            continue
        try:
            parts = line.replace(",", " ").split()
            if len(parts) < 2:
                print("Enter two voltages: V_lo V_hi (e.g. 2 3).")
                continue
            v_a, v_b = float(parts[0]), float(parts[1])
            v_lo, v_hi = min(v_a, v_b), max(v_a, v_b)
            if v_hi <= v_lo:
                print("Upper voltage must be greater than lower.")
                continue
            _apply(v_lo, v_hi, "dqdv2d-potential-range")
        except ValueError:
            print("Invalid numbers.")


def operando_ec_interactive_menu(fig, ax, im, cbar, ec_ax, file_paths=None, canvas_mode: bool = False):
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
        file_paths: Optional list of source data file paths; used to suggest
            reasonable default save locations when exporting figures/session files
    """
    # Normalize file path list for downstream helpers
    file_paths = normalize_source_paths(file_paths or [], require_exists=False)

    # If we were given a real Matplotlib Colorbar (e.g. from session load),
    # detach it from `im` immediately. This must happen before any function
    # that may clear/redraw `cbar.ax` (custom colorbar) is called.
    _detach_mpl_colorbar_callbacks(cbar, im)

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
                    _safe_set_clim(im, intensity_min, intensity_max)
                    
                    # Update colorbar if available
                    try:
                        if cbar is not None:
                            _update_custom_colorbar(cbar.ax, im)
                    except Exception:
                        pass
        except Exception:
            pass
    def print_menu():
        print_operando_ec_menu(fig, ec_ax)

    def set_fonts(family=None, size=None):
        if family:
            mpl.rcParams['font.family'] = 'sans-serif'
            mpl.rcParams['font.sans-serif'] = [family, 'DejaVu Sans', 'Arial', 'Liberation Sans']
            # Set mathtext.fontset to match font family
            lf = family.lower()
            if any(k in lf for k in ('stix', 'times', 'roman')):
                mpl.rcParams['mathtext.fontset'] = 'stix'
            else:
                mpl.rcParams['mathtext.fontset'] = 'dejavusans'
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
        # colorbar - redraw with new font settings
        if cbar is not None:
            # Redraw the colorbar to apply font changes
            try:
                _update_custom_colorbar(cbar.ax, im)
            except Exception:
                pass
        
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
    
    # Adjust colorbar gap once per session (move colorbar to desired position)
    if not getattr(cbar.ax, '_cb_gap_adjusted', False):
        try:
            if ec_ax is not None:
                # When EC panel exists, apply gap adjustment (multiply by 0.75 to move colorbar closer)
                cb_gap_in = cb_gap_in * 0.75
            else:
                # When no EC panel, increase gap to move colorbar further left (multiply by 1.3)
                cb_gap_in = cb_gap_in * 1.1
            setattr(cbar.ax, '_fixed_cb_gap_in', cb_gap_in)
            setattr(cbar.ax, '_cb_gap_adjusted', True)
            _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)
        except Exception:
            pass
    
    # Initialize custom colorbar (replaces matplotlib's colorbar)
    cbar_label = getattr(cbar.ax, '_colorbar_label', 'Intensity')
    cbar_label_mode = getattr(fig, '_colorbar_label_mode', 'highlow')
    # If we were given a real Matplotlib Colorbar (e.g. from session load),
    # detach it from `im` before we clear/redraw the axes for the custom colorbar.
    _detach_mpl_colorbar_callbacks(cbar, im)
    _draw_custom_colorbar(cbar.ax, im, cbar_label, cbar_label_mode)
    if getattr(fig, '_operando_session_loaded', False):
        try:
            from .layout import _finalize_operando_session_axes
            _finalize_operando_session_axes(fig, ax, ec_ax)
        except Exception:
            pass
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
        if ec_ax is not None:
            ec_ax.yaxis.tick_right()
            ec_ax.yaxis.set_label_position('right')
            # If a title exists, move it to the right as well
            _title = ec_ax.get_title()
            if isinstance(_title, str) and _title.strip():
                ec_ax.set_title(_title, loc='right')
    except Exception:
        pass
    # Give a tiny default right margin on EC x-limits (voltage) so curves aren't glued to the edge
    if ec_ax is not None and not getattr(ec_ax, '_xlim_expanded_default', False):
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
    
    def _op_locator_step(locator):
        try:
            if isinstance(locator, MultipleLocator):
                return float(locator._edge.step)
        except Exception:
            pass
        return None
    def _op_locator_ndivs(locator):
        try:
            if isinstance(locator, AutoMinorLocator):
                return int(locator._ndivs)
        except Exception:
            pass
        return None

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
            # Get colormap name: first check if we stored it explicitly, otherwise try to get from colormap object
            cmap_name = getattr(im, '_operando_cmap_name', None)
            if cmap_name is None:
                cmap_name = getattr(im.get_cmap(), 'name', None)
            # EC mode and caches (only if ec_ax exists)
            if ec_ax is not None:
                mode = getattr(ec_ax, '_ec_y_mode', 'time')
                ions_abs = getattr(ec_ax, '_ions_abs', None)
                prev_xlim = getattr(ec_ax, '_prev_ec_xlim', None)
                ions_expanded = getattr(ec_ax, '_ions_xlim_expanded', False)
                saved_time_ylim = getattr(ec_ax, '_saved_time_ylim', None)
                ec_labels = getattr(ec_ax, '_custom_labels', {'x': ec_ax.get_xlabel(), 'y_time': None, 'y_ions': None})
                ion_guides = []
                for gl in getattr(ec_ax, '_ion_guides', []) or []:
                    try:
                        ydata = np.asarray(gl.get_ydata(), float)
                        if ydata.size:
                            ion_guides.append(float(ydata[0]))
                    except Exception:
                        pass
                ion_annots = []
                for ann in getattr(ec_ax, '_ion_annots', []) or []:
                    try:
                        ion_annots.append({
                            'text': ann.get_text(),
                            'xy': tuple(float(v) for v in ann.xy),
                        })
                    except Exception:
                        pass
            else:
                mode = 'time'
                ions_abs = None
                prev_xlim = None
                ions_expanded = False
                saved_time_ylim = None
                ec_labels = None
                ion_guides = []
                ion_annots = []
            # Labels & fonts
            op_labels = getattr(ax, '_custom_labels', {'x': ax.get_xlabel(), 'y': ax.get_ylabel()})
            fam = plt.rcParams.get('font.sans-serif', [])
            fsize = plt.rcParams.get('font.size', None)
            mathtext_fs = plt.rcParams.get('mathtext.fontset', 'dejavusans')
            # WASD state for both panes (minor flags from _saved_tick_state, not tick_params alone)
            op_ts_snap = getattr(ax, '_saved_tick_state', {}) or {}
            op_wasd = {
                'top':    {'spine': _get_spine_visible(ax, 'top'),
                           'ticks': bool(op_ts_snap.get('t_ticks', op_ts_snap.get('tx', False))),
                           'minor': bool(op_ts_snap.get('mtx', False)),
                           'labels': bool(op_ts_snap.get('t_labels', op_ts_snap.get('tx', False))),
                           'title': bool(getattr(ax, '_top_xlabel_on', False))},
                'bottom': {'spine': _get_spine_visible(ax, 'bottom'),
                           'ticks': bool(op_ts_snap.get('b_ticks', op_ts_snap.get('bx', True))),
                           'minor': bool(op_ts_snap.get('mbx', False)),
                           'labels': bool(op_ts_snap.get('b_labels', op_ts_snap.get('bx', True))),
                           'title': bool(ax.get_xlabel())},
                'left':   {'spine': _get_spine_visible(ax, 'left'),
                           'ticks': bool(op_ts_snap.get('l_ticks', op_ts_snap.get('ly', True))),
                           'minor': bool(op_ts_snap.get('mly', False)),
                           'labels': bool(op_ts_snap.get('l_labels', op_ts_snap.get('ly', True))),
                           'title': bool(ax.get_ylabel())},
                'right':  {'spine': _get_spine_visible(ax, 'right'),
                           'ticks': bool(op_ts_snap.get('r_ticks', op_ts_snap.get('ry', False))),
                           'minor': bool(op_ts_snap.get('mry', False)),
                           'labels': bool(op_ts_snap.get('r_labels', op_ts_snap.get('ry', False))),
                           'title': bool(getattr(ax, '_right_ylabel_on', False))},
            }
            # EC WASD state (only if ec_ax exists)
            if ec_ax is not None:
                # For EC, check if ylabel is currently visible (not hidden by user via d5)
                # EC uses the actual ylabel positioned on right, not a duplicate artist
                ec_ylabel_visible = bool(ec_ax.get_ylabel())  # Empty string = hidden
                ec_ts_snap = getattr(ec_ax, '_saved_tick_state', {}) or {}
                # The EC y-axis lives on the right and is the panel's primary axis. Capture its
                # ACTUAL displayed tick/label visibility rather than trusting _saved_tick_state,
                # which can drift out of sync (e.g. after a session load stores r_ticks=False while
                # the ticks are actually shown). Using the stale state made undo (b) wrongly hide
                # the EC right ticks/labels after commands like oy.
                ec_right_ticks_vis, ec_right_labels_vis = right_y_major_visibility(ec_ax)
                ec_wasd = {
                    'top':    {'spine': _get_spine_visible(ec_ax, 'top'),
                               'ticks': bool(ec_ts_snap.get('t_ticks', ec_ts_snap.get('tx', False))),
                               'minor': bool(ec_ts_snap.get('mtx', False)),
                               'labels': bool(ec_ts_snap.get('t_labels', ec_ts_snap.get('tx', False))),
                               'title': bool(getattr(ec_ax, '_top_xlabel_on', False))},
                    'bottom': {'spine': _get_spine_visible(ec_ax, 'bottom'),
                               'ticks': bool(ec_ts_snap.get('b_ticks', ec_ts_snap.get('bx', True))),
                               'minor': bool(ec_ts_snap.get('mbx', False)),
                               'labels': bool(ec_ts_snap.get('b_labels', ec_ts_snap.get('bx', True))),
                               'title': bool(ec_ax.get_xlabel())},
                    'left':   {'spine': _get_spine_visible(ec_ax, 'left'),
                               'ticks': bool(ec_ts_snap.get('l_ticks', False)),
                               'minor': bool(ec_ts_snap.get('mly', False)),
                               'labels': bool(ec_ts_snap.get('l_labels', False)),
                               'title': False},
                    'right':  {'spine': _get_spine_visible(ec_ax, 'right'),
                               'ticks': ec_right_ticks_vis,
                               'minor': bool(ec_ts_snap.get('mry', False)),
                               'labels': ec_right_labels_vis,
                               'title': ec_ylabel_visible},
                }
            else:
                ec_wasd = None
            # Visibility states
            cb_visible = bool(cbar.ax.get_visible())
            ec_visible = bool(ec_ax.get_visible()) if ec_ax is not None else None
            cb_label = getattr(cbar.ax, '_colorbar_label', cbar.ax.get_ylabel() or 'Intensity')
            cb_label_mode = getattr(fig, '_colorbar_label_mode', 'highlow')
            # Horizontal offsets (relative to canvas center, in inches)
            cb_h_offset = getattr(cbar.ax, '_cb_h_offset_in', 0.0)
            ec_h_offset = getattr(ec_ax, '_ec_h_offset_in', 0.0) if ec_ax is not None else None
            # Colorbar tick/label positions (left/right)
            cb_ticks_left = True
            cb_label_left = True
            try:
                cb_ticks_left = any(getattr(tick, 'tick1line', None) and tick.tick1line.get_visible() for tick in cbar.ax.yaxis.get_major_ticks())
                # label position is stored on axis; capture current setting
                cb_label_left = (cbar.ax.yaxis.get_label_position() == 'left')
            except Exception:
                pass
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
            # Spine and tick widths (l command) for undo
            op_spines_snap = {}
            for name in ('bottom', 'top', 'left', 'right'):
                sp = ax.spines.get(name)
                if sp:
                    op_spines_snap[name] = {
                        'linewidth': float(sp.get_linewidth()),
                        'color': sp.get_edgecolor(),
                        'visible': bool(sp.get_visible()),
                    }
            op_ticks_snap = {
                'x_major': _axis_tick_width(ax.xaxis, 'major'),
                'x_minor': _axis_tick_width(ax.xaxis, 'minor'),
                'y_major': _axis_tick_width(ax.yaxis, 'major'),
                'y_minor': _axis_tick_width(ax.yaxis, 'minor'),
            }
            ec_spines_snap = None
            ec_ticks_snap = None
            ec_line_style = None
            if ec_ax is not None:
                ec_spines_snap = {}
                for name in ('bottom', 'top', 'left', 'right'):
                    sp = ec_ax.spines.get(name)
                    if sp:
                        ec_spines_snap[name] = {
                            'linewidth': float(sp.get_linewidth()),
                            'color': sp.get_edgecolor(),
                            'visible': bool(sp.get_visible()),
                        }
                ec_ticks_snap = {
                    'x_major': _axis_tick_width(ec_ax.xaxis, 'major'),
                    'x_minor': _axis_tick_width(ec_ax.xaxis, 'minor'),
                    'y_major': _axis_tick_width(ec_ax.yaxis, 'major'),
                    'y_minor': _axis_tick_width(ec_ax.yaxis, 'minor'),
                }
                ln = getattr(ec_ax, '_ec_line', None)
                if ln is None and ec_ax.lines:
                    try:
                        ln = ec_ax.lines[0]
                    except Exception:
                        ln = None
                if ln is not None:
                    try:
                        ec_line_style = {
                            'color': ln.get_color(),
                            'linewidth': float(ln.get_linewidth() or 1.0),
                        }
                    except Exception:
                        pass
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
                'ion_guides': ion_guides,
                'ion_annots': ion_annots,
                'op_labels': dict(op_labels) if isinstance(op_labels, dict) else {'x': ax.get_xlabel(), 'y': ax.get_ylabel()},
                'ec_labels': dict(ec_labels) if ec_labels is not None and isinstance(ec_labels, dict) else None,
                'font': {'family': list(fam), 'size': fsize, 'mathtext_fontset': mathtext_fs},
                'op_wasd': dict(op_wasd),
                'ec_wasd': dict(ec_wasd) if ec_wasd is not None else None,
                'tick_lengths': getattr(fig, '_tick_lengths', None),
                'tick_direction': getattr(fig, '_tick_direction', 'out'),
                'tick_spacing_op': capture_axes_tick_locators(ax, ('x', 'y')),
                'tick_spacing_ec': capture_axes_tick_locators(ec_ax, ('x', 'y')) if ec_ax is not None else None,
                'cb_visible': cb_visible,
                'cb_label': str(cb_label),
                'cb_label_mode': cb_label_mode,
                'ec_visible': ec_visible,
                'cb_h_offset': float(cb_h_offset),
                'ec_h_offset': float(ec_h_offset) if ec_h_offset is not None else None,
                'cb_ticks_left': cb_ticks_left,
                'cb_label_left': cb_label_left,
                'op_labelpads': dict(op_labelpads),
                'ec_labelpads': dict(ec_labelpads) if ec_labelpads is not None else None,
                'op_title_offsets': capture_title_offsets(ax),
                'ec_title_offsets': capture_title_offsets(ec_ax) if ec_ax is not None else None,
                'op_spines': op_spines_snap,
                'op_ticks': op_ticks_snap,
                'ec_spines': ec_spines_snap,
                'ec_ticks': ec_ticks_snap,
                'ec_line_style': ec_line_style,
                'ec_grid': dict(getattr(ec_ax, '_ec_grid', None) or {}) if ec_ax is not None else None,
                'operando_cif': {
                    'tick_series': list(getattr(ax, '_operando_cif_tick_series', [])),
                    'show_hkl': bool(getattr(fig, '_operando_cif_show_hkl', False)),
                    'show_titles': bool(getattr(fig, '_operando_cif_show_titles', True)),
                    'placement': str(getattr(fig, '_operando_cif_placement', 'below')),
                    'y_positions': list(getattr(fig, '_operando_cif_y_positions', [])),
                    'colormap': getattr(fig, '_operando_cif_colormap', None),
                    'highlight': bool(getattr(fig, '_operando_cif_highlight', False)),
                    'title_font': dict(getattr(fig, '_operando_cif_title_font', None) or {}),
                    'title_visible': list(getattr(fig, '_operando_cif_title_visible', None) or []),
                    'set_visible': list(getattr(fig, '_operando_cif_set_visible', None) or []),
                } if getattr(ax, '_operando_cif_tick_series', None) else None,
                'dqdv_2d': {
                    'v_lo': float(getattr(fig, '_dqdv_2d_v_lo', 0.0)),
                    'v_hi': float(getattr(fig, '_dqdv_2d_v_hi', 0.0)),
                    'row_labels': [str(s) for s in (getattr(fig, '_dqdv_2d_row_labels', None) or [])],
                    'zlabel': str(getattr(fig, '_dqdv_2d_zlabel', 'dQ/dV')),
                } if getattr(fig, '_is_dqdv_2d_contour', False) else None,
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
            # Horizontal offsets
            try:
                cb_h_offset = snap.get('cb_h_offset', 0.0)
                setattr(cbar.ax, '_cb_h_offset_in', float(cb_h_offset))
                ec_h_offset = snap.get('ec_h_offset')
                if ec_ax is not None and ec_h_offset is not None:
                    setattr(ec_ax, '_ec_h_offset_in', float(ec_h_offset))
                elif ec_ax is not None:
                    setattr(ec_ax, '_ec_h_offset_in', 0.0)
                # Reapply layout with restored offsets
                cb_w_i, cb_gap_i, ec_gap_i, ec_w_i, ax_w_i, ax_h_i = _ensure_fixed_params(fig, ax, cbar.ax, ec_ax)
                _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, ax_w_i, ax_h_i, cb_w_i, cb_gap_i, ec_gap_i, ec_w_i)
            except Exception:
                pass
            # Colorbar tick/label side
            try:
                cb_ticks_left = snap.get('cb_ticks_left', True)
                cb_label_left = snap.get('cb_label_left', True)
                cbar.ax.yaxis.set_ticks_position('left' if cb_ticks_left else 'right')
                cbar.ax.yaxis.set_label_position('left' if cb_label_left else 'right')
            except Exception:
                pass
            # Labels (2D dQ/dV: restored again after potential-window rebuild below)
            try:
                op_l = snap.get('op_labels', {})
                if getattr(fig, '_is_dqdv_2d_contour', False):
                    _restore_dqdv_2d_operando_labels(ax, op_l)
                else:
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
                mathtext_fs = font.get('mathtext_fontset')
                # Restore mathtext.fontset first
                if mathtext_fs:
                    try:
                        plt.rcParams['mathtext.fontset'] = mathtext_fs
                    except Exception:
                        pass
                if fam or size is not None:
                    # Convert family list back to string
                    if isinstance(fam, list) and fam:
                        fam = fam[0]
                    set_fonts(family=fam if fam else None, size=size if size is not None else None)
            except Exception:
                pass
            # Operando axes and image
            try:
                if getattr(fig, '_is_dqdv_2d_contour', False):
                    ax.set_ylim(*snap['op_ylim'])
                else:
                    ax.set_xlim(*snap['op_xlim'])
                    ax.set_ylim(*snap['op_ylim'])
            except Exception:
                pass
            try:
                if snap.get('clim') is not None:
                    # Detach built-in colorbar update to avoid artist removal errors; we redraw custom below.
                    try:
                        if hasattr(cbar, 'mappable'):
                            cbar.mappable = None
                        if hasattr(cbar, 'solids'):
                            cbar.solids = None
                    except Exception:
                        pass
                    lo, hi = snap['clim']; _safe_set_clim(im, float(lo), float(hi))
            except Exception:
                pass
            try:
                if snap.get('cmap'):
                    cmap_name = snap['cmap']
                    im.set_cmap(cmap_name)
                    # Store the colormap name explicitly so it can be retrieved reliably when saving
                    setattr(im, '_operando_cmap_name', cmap_name)
                    if cbar is not None:
                        _update_custom_colorbar(cbar.ax, im)
            except Exception:
                pass
            # Restore colorbar side (ticks/label) and redraw custom colorbar to keep position
            try:
                if cbar is not None:
                    cb_ticks_left = snap.get('cb_ticks_left', True)
                    cb_label_left = snap.get('cb_label_left', True)
                    cbar.ax.yaxis.set_ticks_position('left' if cb_ticks_left else 'right')
                    cbar.ax.yaxis.set_label_position('left' if cb_label_left else 'right')
                    cb_label = snap.get('cb_label', getattr(cbar.ax, '_colorbar_label', None))
                    cb_label_mode = snap.get('cb_label_mode', getattr(fig, '_colorbar_label_mode', 'highlow'))
                    if cb_label is not None:
                        cbar.ax._colorbar_label = cb_label
                    fig._colorbar_label_mode = cb_label_mode
                    _update_custom_colorbar(cbar.ax, im, label=cb_label, label_mode=cb_label_mode)
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
                        if snap.get('prev_ec_xlim') is not None:
                            setattr(ec_ax, '_prev_ec_xlim', tuple(snap.get('prev_ec_xlim')))
                        setattr(ec_ax, '_ions_xlim_expanded', bool(snap.get('ions_expanded', False)))
                        if snap.get('saved_time_ylim') is not None:
                            setattr(ec_ax, '_saved_time_ylim', tuple(snap.get('saved_time_ylim')))
                        # Re-install ions formatter and high-precision status bar
                        t = np.asarray(getattr(ec_ax, "_ec_time_h", []), float)
                        arr = getattr(ec_ax, "_ions_abs", None)
                        if arr is not None and t.size:
                            install_ec_ions_y_display(ec_ax, t, arr, save_prev=False)
                        try:
                            ec_ax.set_ylabel(snap.get('ec_labels',{}).get('y_ions') or 'Number of ions')
                        except Exception:
                            pass
                        # Restore label positions and right ticks
                        try:
                            keep_yaxis_label_on_side(ec_ax, 'right')
                        except Exception:
                            pass
                        for a in getattr(ec_ax, '_ion_annots', []):
                            try: a.remove()
                            except Exception: pass
                        ec_ax._ion_annots = []
                        for gl in getattr(ec_ax, '_ion_guides', []):
                            try: gl.remove()
                            except Exception: pass
                        ec_ax._ion_guides = []
                        for y_guide in snap.get('ion_guides', []) or []:
                            try:
                                ec_ax._ion_guides.append(ec_ax.axhline(y=float(y_guide), color='0.7', linestyle='--', linewidth=0.8, alpha=0.5, zorder=0))
                            except Exception:
                                pass
                        for ann in snap.get('ion_annots', []) or []:
                            try:
                                txt = ec_ax.annotate(str(ann.get('text', '')), xy=tuple(ann.get('xy', (0.0, 0.0))), xytext=(0, 4), textcoords='offset points',
                                                     ha='right', va='bottom', fontsize=9,
                                                     bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='0.7', alpha=0.8))
                                ec_ax._ion_annots.append(txt)
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
                    else:
                        setattr(ec_ax, '_ec_y_mode', 'time')
                        # Remove ion guides and annotations when restoring to time mode
                        for a in getattr(ec_ax, '_ion_annots', []):
                            try: a.remove()
                            except Exception: pass
                        ec_ax._ion_annots = []
                        for gl in getattr(ec_ax, '_ion_guides', []):
                            try: gl.remove()
                            except Exception: pass
                        ec_ax._ion_guides = []
                        restore_ec_time_y_display(ec_ax)
                        try:
                            ec_ax.set_ylabel(snap.get('ec_labels',{}).get('y_time') or 'Time (h)')
                        except Exception:
                            pass
                        try:
                            keep_yaxis_label_on_side(ec_ax, 'right')
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
                    apply_wasd_spines(ax, op_wasd)
                    apply_wasd_tick_params(
                        ax,
                        op_wasd,
                        y_sides=('left',),
                        y_mode='left',
                    )
                    for side in ['top', 'right']:
                        st = op_wasd.get(side, {})
                        # Title restoration
                        if side == 'top' and 'title' in st:
                            setattr(ax, '_top_xlabel_on', bool(st['title']))
                        elif side == 'right' and 'title' in st:
                            setattr(ax, '_right_ylabel_on', bool(st['title']))
                if ec_wasd and ec_ax is not None:
                    apply_wasd_spines(ec_ax, ec_wasd)
                    apply_wasd_tick_params(
                        ec_ax,
                        ec_wasd,
                        y_sides=('right',),
                        y_mode='right',
                    )
                    for side in ['top', 'right']:
                        st = ec_wasd.get(side, {})
                        # Title restoration
                        if side == 'top' and 'title' in st:
                            setattr(ec_ax, '_top_xlabel_on', bool(st['title']))
                        elif side == 'right' and 'title' in st:
                            # EC right title is actual ylabel, not duplicate
                            if bool(st['title']):
                                if not ec_ax.get_ylabel() and hasattr(ec_ax, '_stored_ylabel'):
                                    ec_ax.set_ylabel(ec_ax._stored_ylabel)
                            else:
                                if not hasattr(ec_ax, '_stored_ylabel'):
                                    ec_ax._stored_ylabel = ec_ax.get_ylabel()
                                ec_ax.set_ylabel('')
                # Re-position titles using UI module functions
                try:
                    # Build current tick state dict for UI functions
                    op_tick_state = {}
                    ec_tick_state = {}
                    if op_wasd:
                        op_tick_state = wasd_to_tick_state(
                            op_wasd,
                            tick_defaults={'top': False, 'bottom': True, 'left': True, 'right': False},
                            label_defaults={'top': False, 'bottom': True, 'left': True, 'right': False},
                        )
                    if ec_wasd:
                        ec_tick_state = wasd_to_tick_state(
                            ec_wasd,
                            tick_defaults={'top': False, 'bottom': True, 'left': False, 'right': True},
                            label_defaults={'top': False, 'bottom': True, 'left': False, 'right': True},
                        )
                    try:
                        ax._saved_tick_state = dict(op_tick_state)
                        if ec_ax is not None:
                            ec_ax._saved_tick_state = dict(ec_tick_state)
                    except Exception:
                        pass
                    # Position titles
                    _ui_position_top_xlabel(ax, fig, op_tick_state)
                    _ui_position_bottom_xlabel(ax, fig, op_tick_state)
                    _ui_position_left_ylabel(ax, fig, op_tick_state)
                    _ui_position_right_ylabel(ax, fig, op_tick_state)
                    if ec_ax is not None:
                        _ui_position_top_xlabel(ec_ax, fig, ec_tick_state)
                        _ui_position_bottom_xlabel(ec_ax, fig, ec_tick_state)
                        try:
                            keep_yaxis_label_on_side(ec_ax, 'right', visible=bool(ec_ax.get_ylabel()))
                        except Exception:
                            pass
                        # EC right title is the actual ylabel (already on the right); never build a duplicate artist
                        if hasattr(ec_ax, '_right_ylabel_artist') and ec_ax._right_ylabel_artist is not None:
                            try:
                                ec_ax._right_ylabel_artist.set_visible(False)
                            except Exception:
                                pass
                except Exception:
                    pass
                # Restore title offsets
                try:
                    op_offsets = snap.get('op_title_offsets', {})
                    if op_offsets:
                        restore_title_offsets(ax, op_offsets)
                        # Reposition titles to apply offsets
                        _ui_position_top_xlabel(ax, fig, op_tick_state)
                        _ui_position_bottom_xlabel(ax, fig, op_tick_state)
                        _ui_position_left_ylabel(ax, fig, op_tick_state)
                        _ui_position_right_ylabel(ax, fig, op_tick_state)
                    ec_offsets = snap.get('ec_title_offsets')
                    if ec_offsets and ec_ax is not None:
                        restore_title_offsets(ec_ax, ec_offsets)
                        # Reposition titles to apply offsets
                        _ui_position_top_xlabel(ec_ax, fig, ec_tick_state)
                        _ui_position_bottom_xlabel(ec_ax, fig, ec_tick_state)
                        try:
                            keep_yaxis_label_on_side(ec_ax, 'right', visible=bool(ec_ax.get_ylabel()))
                        except Exception:
                            pass
                        # EC right title is the actual ylabel (already on the right); never build a duplicate artist
                        if hasattr(ec_ax, '_right_ylabel_artist') and ec_ax._right_ylabel_artist is not None:
                            try:
                                ec_ax._right_ylabel_artist.set_visible(False)
                            except Exception:
                                pass
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
                        if ec_ax is not None:
                            ec_ax.tick_params(axis='both', which='major', length=major)
                    if minor is not None:
                        ax.tick_params(axis='both', which='minor', length=minor)
                        if ec_ax is not None:
                            ec_ax.tick_params(axis='both', which='minor', length=minor)
                    fig._tick_lengths = tick_lengths
            except Exception:
                pass
            # Restore tick direction
            try:
                tick_dir = snap.get('tick_direction', 'out')
                ax.tick_params(axis='both', which='both', direction=tick_dir)
                if ec_ax is not None:
                    ec_ax.tick_params(axis='both', which='both', direction=tick_dir)
                fig._tick_direction = tick_dir
            except Exception:
                pass
            # Restore tick spacing / minor locators (after WASD tick_params above)
            try:
                restore_axes_tick_locators(ax, snap.get('tick_spacing_op'), ('x', 'y'))
                if ec_ax is not None:
                    restore_axes_tick_locators(ec_ax, snap.get('tick_spacing_ec'), ('x', 'y'))
            except Exception:
                pass
            _maybe_reapply_dqdv_2d_contour(fig, ax, im, cbar)
            # Re-apply WASD minor locators after spacing restore (undo order)
            try:
                op_wasd = snap.get('op_wasd')
                ec_wasd = snap.get('ec_wasd')
                if op_wasd:
                    apply_wasd_minor_ticks(
                        ax, op_wasd,
                        y_minor_mode='left' if ec_ax is not None else 'both',
                    )
                if ec_wasd and ec_ax is not None:
                    apply_wasd_minor_ticks(ec_ax, ec_wasd, y_minor_mode='right')
            except Exception:
                pass
            # Restore spine linewidths and tick widths (l command)
            try:
                op_sp = snap.get('op_spines', {})
                if op_sp:
                    for name, spec in op_sp.items():
                        sp = ax.spines.get(name)
                        if sp is not None and spec is not None:
                            if isinstance(spec, dict):
                                if spec.get('linewidth') is not None:
                                    sp.set_linewidth(float(spec['linewidth']))
                                if spec.get('color') is not None:
                                    sp.set_edgecolor(spec['color'])
                                if spec.get('visible') is not None:
                                    sp.set_visible(bool(spec['visible']))
                            else:
                                sp.set_linewidth(float(spec))
                op_tw = snap.get('op_ticks', {})
                if op_tw:
                    if op_tw.get('x_major') is not None:
                        ax.tick_params(axis='x', which='major', width=op_tw['x_major'])
                    if op_tw.get('x_minor') is not None:
                        ax.tick_params(axis='x', which='minor', width=op_tw['x_minor'])
                    if op_tw.get('y_major') is not None:
                        ax.tick_params(axis='y', which='major', width=op_tw['y_major'])
                    if op_tw.get('y_minor') is not None:
                        ax.tick_params(axis='y', which='minor', width=op_tw['y_minor'])
            except Exception:
                pass
            try:
                if ec_ax is not None:
                    ec_sp = snap.get('ec_spines', {})
                    if ec_sp:
                        for name, spec in ec_sp.items():
                            sp = ec_ax.spines.get(name)
                            if sp is not None and spec is not None:
                                if isinstance(spec, dict):
                                    if spec.get('linewidth') is not None:
                                        sp.set_linewidth(float(spec['linewidth']))
                                    if spec.get('color') is not None:
                                        sp.set_edgecolor(spec['color'])
                                    if spec.get('visible') is not None:
                                        sp.set_visible(bool(spec['visible']))
                                else:
                                    sp.set_linewidth(float(spec))
                    ec_tw = snap.get('ec_ticks', {})
                    if ec_tw:
                        if ec_tw.get('x_major') is not None:
                            ec_ax.tick_params(axis='x', which='major', width=ec_tw['x_major'])
                        if ec_tw.get('x_minor') is not None:
                            ec_ax.tick_params(axis='x', which='minor', width=ec_tw['x_minor'])
                        if ec_tw.get('y_major') is not None:
                            ec_ax.tick_params(axis='y', which='major', width=ec_tw['y_major'])
                        if ec_tw.get('y_minor') is not None:
                            ec_ax.tick_params(axis='y', which='minor', width=ec_tw['y_minor'])
            except Exception:
                pass
            # Restore EC line style (el command)
            try:
                ec_line_style = snap.get('ec_line_style')
                if ec_line_style and ec_ax is not None:
                    ln = getattr(ec_ax, '_ec_line', None)
                    if ln is None and ec_ax.lines:
                        try:
                            ln = ec_ax.lines[0]
                        except Exception:
                            ln = None
                    if ln is not None:
                        if ec_line_style.get('color') is not None:
                            ln.set_color(ec_line_style['color'])
                        if ec_line_style.get('linewidth') is not None:
                            ln.set_linewidth(float(ec_line_style['linewidth']))
            except Exception:
                pass
            # Restore EC grid
            try:
                ec_grid_snap = snap.get('ec_grid')
                if ec_grid_snap and ec_ax is not None:
                    g = dict(ec_grid_snap)
                    g.setdefault('visible', False)
                    g.setdefault('alpha', 0.3)
                    g.setdefault('linestyle', '--')
                    g.setdefault('color', '0.6')
                    g.setdefault('which', 'major')
                    ec_ax._ec_grid = g
                    ec_ax.grid(
                        g['visible'],
                        which=g['which'],
                        axis='both',
                        alpha=float(g['alpha']),
                        color=str(g['color']),
                        linestyle=str(g['linestyle']),
                    )
            except Exception:
                pass
            # Restore visibility states
            try:
                cb_vis = snap.get('cb_visible')
                if cb_vis is not None and cbar is not None:
                    cbar.ax.set_visible(bool(cb_vis))
            except Exception:
                pass
            try:
                ec_vis = snap.get('ec_visible')
                if ec_vis is not None and ec_ax is not None:
                    ec_ax.set_visible(bool(ec_vis))
            except Exception:
                pass
            # Restore operando CIF tick state
            try:
                cif_snap = snap.get('operando_cif')
                if cif_snap and getattr(ax, '_operando_cif_tick_series', None):
                    fig._operando_cif_show_hkl = bool(cif_snap.get('show_hkl', False))
                    fig._operando_cif_show_titles = bool(cif_snap.get('show_titles', True))
                    fig._operando_cif_placement = str(cif_snap.get('placement', 'below'))
                    y_pos = cif_snap.get('y_positions', [])
                    fig._operando_cif_y_positions = list(y_pos) if y_pos else []
                    fig._operando_cif_colormap = cif_snap.get('colormap')
                    fig._operando_cif_highlight = bool(cif_snap.get('highlight', False))
                    fig._operando_cif_title_font = dict(cif_snap.get('title_font') or {})
                    fig._operando_cif_title_visible = list(cif_snap.get('title_visible') or [])
                    fig._operando_cif_set_visible = list(cif_snap.get('set_visible') or [])
                    # Restore tick_series (includes colors)
                    tick_series_restore = cif_snap.get('tick_series')
                    if tick_series_restore is not None:
                        ax._operando_cif_tick_series = list(tick_series_restore)
                    axis_mode = getattr(fig, '_operando_axis_mode', '2theta')
                    wl = getattr(fig, '_operando_wl', None)
                    cif_series = getattr(ax, '_operando_cif_tick_series', [])
                    cif_hkl_map = getattr(ax, '_operando_cif_hkl_label_map', {})
                    ax_pos = ax.get_position()
                    y_base = ax_pos.ymin - 0.02 if fig._operando_cif_placement == 'below' else ax_pos.ymax + 0.02
                    dy = -0.025 if fig._operando_cif_placement == 'below' else 0.025
                    while len(fig._operando_cif_y_positions) < len(cif_series):
                        fig._operando_cif_y_positions.append(y_base + len(fig._operando_cif_y_positions) * dy)
                    _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl,
                                             show_hkl=fig._operando_cif_show_hkl, show_titles=fig._operando_cif_show_titles,
                                             placement=fig._operando_cif_placement, y_positions=fig._operando_cif_y_positions)
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
                d2 = snap.get('dqdv_2d')
                if d2 and isinstance(d2, dict) and getattr(fig, '_is_dqdv_2d_contour', False):
                    try:
                        fig._dqdv_2d_v_lo = float(d2['v_lo'])
                        fig._dqdv_2d_v_hi = float(d2['v_hi'])
                        fig._dqdv_2d_row_labels = [str(s) for s in (d2.get('row_labels') or [])]
                        if d2.get('zlabel') is not None:
                            fig._dqdv_2d_zlabel = str(d2['zlabel'])
                    except Exception:
                        pass
                    try:
                        from ..electrochem.interactive import update_dqdv_2d_potential_window
                        update_dqdv_2d_potential_window(
                            fig, ax, im,
                            float(fig._dqdv_2d_v_lo), float(fig._dqdv_2d_v_hi),
                        )
                    except Exception:
                        pass
                _maybe_reapply_dqdv_2d_contour(fig, ax, im, cbar)
                if getattr(fig, '_is_dqdv_2d_contour', False):
                    _restore_dqdv_2d_operando_labels(ax, snap.get('op_labels', {}))
            except Exception:
                pass
            try:
                fig.canvas.draw()
            except Exception:
                fig.canvas.draw_idle()
            print("Undo: restored previous state.")
        except Exception as e:
            print(f"Undo failed: {e}")

    def _run_save_dqdv_2d_contour_session():
        """Save dQ/dV 2D contour state (.pkl) with butterfly axis metadata."""
        import pickle
        from ..electrochem.interactive import build_dqdv_2d_snapshot
        folder = choose_save_path(file_paths, purpose="dQ/dV 2D session save")
        if not folder:
            return
        print(f"\nChosen path: {folder}")
        if not os.path.isdir(folder):
            print(f"Error: path is not a directory or does not exist: {folder}")
            return
        try:
            v_lo = float(fig._dqdv_2d_v_lo)
            v_hi = float(fig._dqdv_2d_v_hi)
            row_labels = [str(s) for s in (fig._dqdv_2d_row_labels or [])]
            zlab = str(getattr(fig, "_dqdv_2d_zlabel", "dQ/dV"))
        except Exception:
            print("Error: missing dQ/dV 2D axis metadata on this figure.")
            return
        snap = build_dqdv_2d_snapshot(fig, ax, im, v_lo, v_hi, row_labels, zlab, cbar)
        if snap is None:
            print("Error: could not build dQ/dV 2D session snapshot.")
            return
        try:
            all_names = os.listdir(folder)
            files = sorted([f for f in all_names if f.lower().endswith('.pkl')], key=natural_sort_key)
        except OSError as e:
            print(f"Cannot list directory: {e}")
            return
        if files:
            print("Existing .pkl files:")
            for i, f in enumerate(files, 1):
                filepath = os.path.join(folder, f)
                timestamp = _format_file_timestamp(filepath)
                if timestamp:
                    print(f"  {i}: {f}  ({timestamp})")
                else:
                    print(f"  {i}: {f}")
        choice = _safe_input(_colorize_prompt(
            "Enter new filename (no ext needed) or number to overwrite (q=cancel): "
        )).strip()
        if not choice or choice.lower() == 'q':
            return
        target = None
        if choice.isdigit() and files:
            idx = int(choice)
            if 1 <= idx <= len(files):
                name = files[idx - 1]
                yn = _safe_input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                if yn == 'y':
                    target = os.path.join(folder, name)
            else:
                print("Invalid number.")
                return
        else:
            name = choice
            root, ext = os.path.splitext(name)
            if ext == '':
                name = name + '.pkl'
            target = name if os.path.isabs(name) else os.path.join(folder, name)
            if os.path.exists(target):
                yn = _safe_input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
                if yn != 'y':
                    return
        if not target:
            return
        target = ensure_exact_case_filename(target)
        try:
            with open(target, 'wb') as f:
                pickle.dump(snap, f)
            fig._last_session_save_path = target
            print(f"dQ/dV 2D session saved to {target}")
        except Exception as e:
            print(f"Error saving dQ/dV 2D session: {e}")

    def _run_save_operando_session():
        """Run the operando session save flow. Returns without printing menus."""
        if getattr(fig, '_is_dqdv_2d_contour', False):
            _run_save_dqdv_2d_contour_session()
            return
        folder = choose_save_path(file_paths, purpose="operando session save")
        if not folder:
            return
        print(f"\nChosen path: {folder}")
        if not os.path.isdir(folder):
            print(f"Error: path is not a directory or does not exist: {folder}")
            return
        try:
            all_names = os.listdir(folder)
            files = sorted([f for f in all_names if f.lower().endswith('.pkl')], key=natural_sort_key)
        except OSError as e:
            print(f"Cannot list directory (check permissions or path): {e}")
            return
        except Exception as e:
            print(f"Error listing directory: {e}")
            return
        if files:
            print("Existing .pkl files:")
            for i, f in enumerate(files, 1):
                filepath = os.path.join(folder, f)
                timestamp = _format_file_timestamp(filepath)
                if timestamp:
                    print(f"  {i}: {f}  ({timestamp})")
                else:
                    print(f"  {i}: {f}")
            print("Enter a number above to overwrite, or a new filename to create.")
        else:
            print("No .pkl files in this directory. Enter a new filename to create.")
        last_session_path = getattr(fig, '_last_session_save_path', None)
        if last_session_path:
            prompt = _colorize_inline_commands("Enter new filename (no ext needed), number to overwrite, or o to overwrite last (q=cancel): ")
        else:
            prompt = _colorize_inline_commands("Enter new filename (no ext needed) or number to overwrite (q=cancel): ")
        choice = _safe_input(prompt).strip()
        if not choice or choice.lower() == 'q':
            return
        if choice.lower() == 'o':
            if not last_session_path:
                print("No previous save found.")
                return
            if not os.path.exists(last_session_path):
                print(f"Previous save file not found: {last_session_path}")
                return
            yn = _safe_input(f"Overwrite '{os.path.basename(last_session_path)}'? (y/n): ").strip().lower()
            if yn != 'y':
                return
            dump_operando_session(last_session_path, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax, skip_confirm=True)
            print(f"Overwritten session to {last_session_path}")
            return
        if choice.isdigit() and files:
            idx = int(choice)
            if 1 <= idx <= len(files):
                name = files[idx - 1]
                yn = _safe_input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                if yn != 'y':
                    return
                target = os.path.join(folder, name)
                dump_operando_session(target, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax, skip_confirm=True)
                fig._last_session_save_path = target
                print(f"Operando session saved to {target}")
                return
            else:
                print("Invalid number.")
                return
        name = choice
        root, ext = os.path.splitext(name)
        if ext == '':
            name = name + '.pkl'
        target = name if os.path.isabs(name) else os.path.join(folder, name)
        if os.path.exists(target):
            yn = _safe_input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
            if yn != 'y':
                return
        dump_operando_session(target, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax, skip_confirm=True)
        fig._last_session_save_path = target
        actual_name = os.path.basename(target)
        if os.path.exists(target):
            try:
                dir_files = os.listdir(folder)
                for f in dir_files:
                    if f.lower() == actual_name.lower():
                        actual_name = f
                        break
            except Exception:
                pass
        print(f"Operando session saved to {os.path.join(folder, actual_name)}")

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
                vline = fig.add_artist(matplotlib.lines.Line2D([0.5, 0.5], [0, 1], transform=fig.transFigure,
                                                   color='0.35', ls='--', lw=0.8, alpha=0.85, zorder=9999))
                hline = fig.add_artist(matplotlib.lines.Line2D([0, 1], [0.5, 0.5], transform=fig.transFigure,
                                                   color='0.35', ls='--', lw=0.8, alpha=0.85, zorder=9999))
                # Create text annotations for coordinates
                coord_text = fig.text(0.02, 0.98, '', transform=fig.transFigure, 
                                     verticalalignment='top', 
                                     fontsize=max(9, int(0.6 * mpl.rcParams.get('font.size', 16))),
                                     color='0.15',
                                     bbox=dict(boxstyle='round,pad=0.25', fc='white', ec='0.7', alpha=0.8))
            except Exception as e:
                print(f"Failed to create crosshair: {e}")
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
                                in_range = (
                                    xlim[0] <= ec_point[0] <= xlim[1]
                                    and ylim[0] <= ec_point[1] <= ylim[1]
                                )
                                suffix = "" if in_range else " (out of range)"
                                if getattr(ec_ax, "_ec_y_mode", "time") == "ions":
                                    t_ec = np.asarray(getattr(ec_ax, "_ec_time_h", []), float)
                                    ions_arr = getattr(ec_ax, "_ions_abs", None)
                                    if ions_arr is not None and t_ec.size:
                                        ions_y = ions_value_at_time(t_ec, ions_arr, ec_point[1])
                                        texts.append(
                                            f"EC: x={ec_point[0]:.4f}, "
                                            f"y={format_ions_value(ions_y)}{suffix}"
                                        )
                                    else:
                                        texts.append(
                                            f"EC: x={ec_point[0]:.4f}, y={ec_point[1]:.4f}{suffix}"
                                        )
                                else:
                                    texts.append(
                                        f"EC: x={ec_point[0]:.4f}, y={ec_point[1]:.4f}{suffix}"
                                    )
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

    def _make_action_context():
        return OperandoActionContext(
            fig=fig,
            ax=ax,
            im=im,
            cbar=cbar,
            ec_ax=ec_ax,
            file_paths=file_paths,
            print_menu=print_menu,
            snapshot=_snapshot,
            restore=_restore,
            run_save_operando_session=_run_save_operando_session,
            set_fonts=set_fonts,
            axis_tick_width=_axis_tick_width,
            format_file_timestamp=_format_file_timestamp,
            maybe_reapply_dqdv_2d_contour=_maybe_reapply_dqdv_2d_contour,
            restore_dqdv_2d_operando_labels=_restore_dqdv_2d_operando_labels,
            ax_w_in=ax_w_in,
            ax_h_in=ax_h_in,
            cb_w_in=cb_w_in,
            cb_gap_in=cb_gap_in,
            ec_gap_in=ec_gap_in,
            ec_w_in=ec_w_in,
        )

    def _handle_op_c():
            nonlocal ax_pos, cur, sub, v, val
            cif_series = getattr(ax, '_operando_cif_tick_series', None)
            if not cif_series:
                print("No CIF tick labels. Add CIF files when launching: batplot folder phase.cif:1.54 --operando --interactive")
                print_menu()
                return
            axis_mode = getattr(fig, '_operando_axis_mode', '2theta')
            wl = getattr(fig, '_operando_wl', None)
            cif_hkl_map = getattr(ax, '_operando_cif_hkl_label_map', {})
            show_hkl = getattr(fig, '_operando_cif_show_hkl', False)
            show_titles = getattr(fig, '_operando_cif_show_titles', True)
            placement = getattr(fig, '_operando_cif_placement', 'below')
            y_positions = list(getattr(fig, '_operando_cif_y_positions', []))
            n_sets = len(cif_series)
            ax_pos = ax.get_position()
            y_base = ax_pos.ymin - 0.02 if placement == 'below' else ax_pos.ymax + 0.02
            dy = -0.025 if placement == 'below' else 0.025
            while len(y_positions) < n_sets:
                y_positions.append(y_base + len(y_positions) * dy)
            while True:
                print(_colorize_inline_commands("CIF tick labels:"))
                print("  " + _colorize_menu(f"z: toggle hkl labels (currently {'on' if show_hkl else 'off'})"))
                print("  " + _colorize_menu(f"t: toggle CIF titles (currently {'on' if show_titles else 'off'})"))
                show_highlight = getattr(fig, '_operando_cif_highlight', False)
                print("  " + _colorize_menu(f"h: highlight for overlay (currently {'on' if show_highlight else 'off'})"))
                print("  " + _colorize_menu(f"p: placement (currently {placement})"))
                print("  " + _colorize_menu("v: vertical position (per CIF set)"))
                print("  " + _colorize_inline_commands("o: color (per CIF set)  m: colormap (all sets)"))
                cif_font = getattr(fig, '_operando_cif_title_font', None) or {}
                rc_fam = plt.rcParams.get('font.family', ['sans-serif'])
                if isinstance(rc_fam, list):
                    rc_fam = rc_fam[0] if rc_fam else 'sans-serif'
                rc_sz = max(8, int(0.55 * plt.rcParams.get('font.size', 12)))
                fam_disp = cif_font.get('family') or rc_fam
                sz_disp = cif_font.get('size') if cif_font.get('size') is not None else rc_sz
                font_desc = f"family={fam_disp}, size={sz_disp}"
                print("  " + _colorize_inline_commands(f"f: font (currently {font_desc})"))
                print("  " + _colorize_inline_commands("r: rename (per set)  n: hide/show name (per set)"))
                print("  " + _colorize_menu("x: show/hide CIF set (per set)"))
                print("  " + _colorize_menu("b: undo"))
                print("  " + _colorize_menu("q: back"))
                sub = _safe_input(_colorize_prompt(
                    "CIF tick labels (key letter from list above, q=back): "
                )).strip().lower()
                if not sub or sub == 'q':
                    break
                if sub == 'z':
                    _snapshot("cif-hkl")
                    fig._operando_cif_show_hkl = not show_hkl
                    show_hkl = fig._operando_cif_show_hkl
                    _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
                    fig.canvas.draw_idle()
                    print(f"CIF hkl labels: {'on' if show_hkl else 'off'}")
                elif sub == 't':
                    _snapshot("cif-titles")
                    fig._operando_cif_show_titles = not show_titles
                    show_titles = fig._operando_cif_show_titles
                    _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
                    fig.canvas.draw_idle()
                    print(f"CIF titles: {'on' if show_titles else 'off'}")
                elif sub == 'h':
                    _snapshot("cif-highlight")
                    fig._operando_cif_highlight = not getattr(fig, '_operando_cif_highlight', False)
                    _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
                    fig.canvas.draw_idle()
                    print(f"CIF highlight: {'on' if fig._operando_cif_highlight else 'off'} (visible when overlaid on contour)")
                elif sub == 'p':
                    _snapshot("cif-placement")
                    placement = 'above' if placement == 'below' else 'below'
                    fig._operando_cif_placement = placement
                    ax_pos = ax.get_position()
                    y_base = ax_pos.ymin - 0.02 if placement == 'below' else ax_pos.ymax + 0.02
                    dy = -0.025 if placement == 'below' else 0.025
                    y_positions = [y_base + i * dy for i in range(len(cif_series))]
                    fig._operando_cif_y_positions = y_positions
                    _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
                    fig.canvas.draw_idle()
                    print(f"CIF placement: {placement}")
                elif sub == 'v':
                    print(f"CIF sets: {list(range(1, len(cif_series) + 1))}")
                    for i, (lab, *_ ) in enumerate(cif_series):
                        print(f"  {i+1}: {lab}  y={y_positions[i]:.2f}" if i < len(y_positions) else f"  {i+1}: {lab}")
                    idx_s = _safe_input(_colorize_inline_commands("Set index to adjust (q=back): ")).strip().lower()
                    if idx_s == 'q':
                        continue
                    try:
                        idx = int(idx_s) - 1
                        if 0 <= idx < len(cif_series):
                            while True:
                                cur_y = y_positions[idx] if idx < len(y_positions) else 0
                                val_s = _safe_input(_colorize_inline_commands(f"New y for set {idx+1} (current {cur_y:.3f}, w=up s=down, q=back): ")).strip().lower()
                                if not val_s or val_s == 'q':
                                    break
                                delta = None
                                target_y = None
                                if val_s == 'w':
                                    delta = 0.02
                                elif val_s == 's':
                                    delta = -0.02
                                elif val_s:
                                    try:
                                        target_y = float(val_s)
                                    except ValueError:
                                        print("Invalid value.")
                                        continue
                                if delta is None and target_y is None:
                                    continue
                                _snapshot("cif-y-position")
                                y_positions = list(getattr(fig, '_operando_cif_y_positions', []))
                                ax_pos = ax.get_position()
                                y_base = ax_pos.ymin - 0.02 if placement == 'below' else ax_pos.ymax + 0.02
                                dy = -0.025 if placement == 'below' else 0.025
                                while len(y_positions) < len(cif_series):
                                    y_positions.append(y_base + len(y_positions) * dy)
                                if delta is not None:
                                    y_positions[idx] = (y_positions[idx] if idx < len(y_positions) else 0) + delta
                                else:
                                    y_positions[idx] = target_y
                                fig._operando_cif_y_positions = y_positions
                                _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
                                fig.canvas.draw_idle()
                                print(f"Set {idx+1} y = {y_positions[idx]:.2f}")
                        else:
                            print("Invalid index.")
                    except ValueError:
                        print("Invalid index.")
                elif sub == 'o':
                    while True:
                        print("CIF color (per set). Use color name or hex, e.g. red, #FF0000")
                        for i, (lab, fname, *rest) in enumerate(cif_series):
                            col = rest[-1] if rest else 'k'
                            print(f"  {i+1}: {lab}  color={col}")
                        idx_s = _safe_input(_colorize_inline_commands("Set index (q=back): ")).strip().lower()
                        if not idx_s or idx_s == 'q':
                            break
                        try:
                            idx = int(idx_s) - 1
                            if 0 <= idx < len(cif_series):
                                new_col = _safe_input(f"New color for set {idx+1}: ").strip()
                                if new_col:
                                    _snapshot("cif-color")
                                    try:
                                        resolved = resolve_color_token(new_col) if resolve_color_token else new_col
                                    except Exception:
                                        resolved = new_col
                                    lab, fname, peaksQ, wl_e, qmax, _ = cif_series[idx]
                                    cif_series = list(cif_series)
                                    cif_series[idx] = (lab, fname, peaksQ, wl_e, qmax, resolved)
                                    fig._operando_cif_colormap = None  # custom per-set colors
                                    ax._operando_cif_tick_series = cif_series
                                    _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
                                    fig.canvas.draw_idle()
                                    print(f"Set {idx+1} color: {resolved}")
                            else:
                                print("Invalid index.")
                        except ValueError:
                            print("Invalid index.")
                elif sub == 'f':
                    _snapshot("cif-font")
                    cur = getattr(fig, '_operando_cif_title_font', None) or {}
                    rc_family = plt.rcParams.get('font.family', ['sans-serif'])
                    if isinstance(rc_family, list):
                        rc_family = rc_family[0] if rc_family else 'sans-serif'
                    rc_size = max(8, int(0.55 * plt.rcParams.get('font.size', 12)))
                    fam_display = cur.get('family') or rc_family
                    sz_display = cur.get('size') if cur.get('size') is not None else rc_size
                    while True:
                        print(f"\nCIF title font (current: family={fam_display}, size={sz_display})")
                        print("  " + _colorize_menu("f: family"))
                        print("  " + _colorize_menu("s: size"))
                        print("  " + _colorize_menu("q: back"))
                        font_sub = _safe_input(_colorize_prompt("CIF font (f/s/q): ")).strip().lower()
                        if not font_sub or font_sub == 'q':
                            break
                        if font_sub == 'f':
                            print(_colorize_inline_commands("Common: Arial, DejaVu Sans, Times New Roman, Courier New"))
                            new_fam = _safe_input(_colorize_prompt(f"Font family (current: {fam_display}, Enter=keep, q=back): ")).strip()
                            if new_fam and new_fam.lower() != 'q':
                                font_dict = dict(cur)
                                font_dict['family'] = new_fam
                                fig._operando_cif_title_font = font_dict
                                cur = font_dict
                                fam_display = new_fam
                                _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
                                fig.canvas.draw_idle()
                                print(f"CIF title font family: {fam_display}")
                        elif font_sub == 's':
                            new_sz = _safe_input(_colorize_prompt(f"Font size (current: {sz_display}, Enter=keep, q=back): ")).strip()
                            if new_sz and new_sz.lower() != 'q':
                                try:
                                    val = max(6, int(float(new_sz)))
                                    font_dict = dict(cur)
                                    font_dict['size'] = val
                                    fig._operando_cif_title_font = font_dict
                                    cur = font_dict
                                    sz_display = val
                                    _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
                                    fig.canvas.draw_idle()
                                    print(f"CIF title font size: {sz_display}")
                                except (ValueError, TypeError):
                                    print("Invalid font size.")
                elif sub == 'r':
                    while True:
                        print(_colorize_inline_commands("CIF sets (q=back)"))
                        for i, (lab, *_ ) in enumerate(cif_series):
                            print(f"  {i+1}: {lab}")
                        print_label_latex_tips(colorize=_colorize_inline_commands)
                        idx_s = _safe_input(_colorize_inline_commands("Set index to rename (q=back): ")).strip().lower()
                        if not idx_s or idx_s == 'q':
                            break
                        try:
                            idx = int(idx_s) - 1
                            if 0 <= idx < len(cif_series):
                                lab, fname, peaksQ, wl_e, qmax, col = cif_series[idx]
                                new_lab = _safe_input(f"New label for set {idx+1} (current: {lab}, blank=cancel): ").strip()
                                if new_lab:
                                    new_lab = convert_label_shortcuts(new_lab)
                                    _snapshot("cif-rename")
                                    cif_series = list(cif_series)
                                    cif_series[idx] = (new_lab, fname, peaksQ, wl_e, qmax, col)
                                    ax._operando_cif_tick_series = cif_series
                                    _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
                                    fig.canvas.draw_idle()
                                    print(f"Set {idx+1} renamed to: {new_lab}")
                            else:
                                print("Invalid index.")
                        except ValueError:
                            print("Invalid index.")
                elif sub == 'n':
                    title_visible = list(getattr(fig, '_operando_cif_title_visible', None) or [True] * len(cif_series))
                    while len(title_visible) < len(cif_series):
                        title_visible.append(True)
                    while True:
                        print("CIF sets - hide/show name (per set):")
                        for i, (lab, *_ ) in enumerate(cif_series):
                            vis = "show" if (i < len(title_visible) and title_visible[i]) else "hide"
                            lab_s = str(lab)
                            print(f"  {i+1}: {lab_s[:40]}... ({vis})" if len(lab_s) > 40 else f"  {i+1}: {lab_s} ({vis})")
                        idx_s = _safe_input(_colorize_inline_commands("Set index to toggle (q=back): ")).strip().lower()
                        if not idx_s or idx_s == 'q':
                            break
                        try:
                            idx = int(idx_s) - 1
                            if 0 <= idx < len(cif_series):
                                _snapshot("cif-hide-name")
                                if idx < len(title_visible):
                                    title_visible[idx] = not title_visible[idx]
                                else:
                                    title_visible.extend([True] * (idx - len(title_visible) + 1))
                                    title_visible[idx] = False
                                fig._operando_cif_title_visible = title_visible
                                _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
                                fig.canvas.draw_idle()
                                v = "shown" if title_visible[idx] else "hidden"
                                print(f"Set {idx+1} name: {v}")
                            else:
                                print("Invalid index.")
                        except ValueError:
                            print("Invalid index.")
                elif sub == 'x':
                    set_visible = list(getattr(fig, '_operando_cif_set_visible', None) or [True] * len(cif_series))
                    while len(set_visible) < len(cif_series):
                        set_visible.append(True)
                    while True:
                        print("CIF sets - show/hide entire set (ticks + labels):")
                        for i, (lab, *_ ) in enumerate(cif_series):
                            lab_s = str(lab)
                            vis = "show" if (i < len(set_visible) and set_visible[i]) else "hide"
                            print(f"  {i+1}: {lab_s[:40]}... ({vis})" if len(lab_s) > 40 else f"  {i+1}: {lab_s} ({vis})")
                        idx_s = _safe_input(_colorize_inline_commands("Set index to toggle (q=back): ")).strip().lower()
                        if not idx_s or idx_s == 'q':
                            break
                        try:
                            idx = int(idx_s) - 1
                            if 0 <= idx < len(cif_series):
                                _snapshot("cif-set-visibility")
                                if idx < len(set_visible):
                                    set_visible[idx] = not set_visible[idx]
                                else:
                                    set_visible.extend([True] * (idx - len(set_visible) + 1))
                                    set_visible[idx] = False
                                fig._operando_cif_set_visible = set_visible
                                _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
                                fig.canvas.draw_idle()
                                v = "shown" if set_visible[idx] else "hidden"
                                print(f"Set {idx+1}: {v}")
                            else:
                                print("Invalid index.")
                        except ValueError:
                            print("Invalid index.")
                elif sub == 'm':
                    # Apply colormap to all CIF sets
                    try:
                        _ensure_operando_colormap('tab10')
                        _ensure_operando_colormap('viridis')
                        _ensure_operando_colormap('plasma')
                    except Exception:
                        pass
                    rec_palettes = palette_items(["tab10", "viridis", "plasma", "Set2", "Dark2", "rainbow"])
                    print("Apply colormap to all CIF sets:")
                    for idx, (name, desc) in enumerate(rec_palettes, 1):
                        bar = palette_preview(name, steps=max(1, min(8, len(cif_series)))) if palette_preview else ""
                        print(f"  {idx}. {name} - {desc}" + (f"  {bar}" if bar else ""))
                    choice = _safe_input(_colorize_inline_commands("Palette name or number (1-6), q=back: ")).strip().lower()
                    if not choice or choice == 'q':
                        continue
                    palette_map = {str(i): name for i, (name, _) in enumerate(rec_palettes, 1)}
                    pal_name = palette_map.get(choice, choice)
                    if not ensure_colormap(pal_name.split('_r')[0] if pal_name.lower().endswith('_r') else pal_name):
                        print(f"Unknown colormap '{pal_name}'.")
                        continue
                    _snapshot("cif-colormap")
                    n = len(cif_series)
                    try:
                        base = pal_name[:-2] if pal_name.lower().endswith('_r') else pal_name
                        if base.lower() == 'tab10':
                            colors = [TAB10_HEX[i % len(TAB10_HEX)] for i in range(n)]
                        else:
                            cmap = get_colormap(pal_name)
                            if cmap is None:
                                raise ValueError(f"Unknown colormap '{pal_name}'")
                            colors = [mcolors.to_hex(cmap(i / max(n - 1, 1))) for i in range(n)]
                    except Exception as e:
                        print(f"Could not apply colormap: {e}")
                        continue
                    cif_series = list(cif_series)
                    for i, (lab, fname, peaksQ, wl_e, qmax, _) in enumerate(cif_series):
                        cif_series[i] = (lab, fname, peaksQ, wl_e, qmax, colors[i] if i < len(colors) else 'k')
                    ax._operando_cif_tick_series = cif_series
                    fig._operando_cif_colormap = pal_name
                    _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
                    fig.canvas.draw_idle()
                    print(f"Applied '{pal_name}' to all {n} CIF sets.")
                elif sub == 'b':
                    _restore()
                    show_hkl = getattr(fig, '_operando_cif_show_hkl', False)
                    show_titles = getattr(fig, '_operando_cif_show_titles', True)
                    placement = getattr(fig, '_operando_cif_placement', 'below')
                    y_positions = list(getattr(fig, '_operando_cif_y_positions', []))
                    cif_series = getattr(ax, '_operando_cif_tick_series', cif_series)
                    ax_pos = ax.get_position()
                    y_base = ax_pos.ymin - 0.02 if placement == 'below' else ax_pos.ymax + 0.02
                    dy = -0.025 if placement == 'below' else 0.025
                    while len(y_positions) < len(cif_series):
                        y_positions.append(y_base + len(y_positions) * dy)
                    fig._operando_cif_y_positions = y_positions
                    _draw_operando_cif_ticks(ax, fig, cif_series, cif_hkl_map, axis_mode=axis_mode, wl=wl, show_hkl=show_hkl, show_titles=show_titles, placement=placement, y_positions=y_positions)
                    fig.canvas.draw_idle()
                else:
                    print("Unknown choice.")
            print_menu()

    def _handle_op_t():
            nonlocal _get_spine_visible, actual
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
                    # Clear minor locator if no minor ticks are enabled
                    axis.xaxis.set_minor_locator(NullLocator())
                    axis.xaxis.set_minor_formatter(NullFormatter())
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
                    # Clear minor locator if no minor ticks are enabled
                    axis.yaxis.set_minor_locator(NullLocator())
                    axis.yaxis.set_minor_formatter(NullFormatter())
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
                    print(_colorize_inline_commands(
                        "Choose which plot to edit: o=operando (contour), e=EC side panel, q=return to contour menu"
                    ))
                    pane = _safe_input(_colorize_prompt(
                        "Pane (o=operando, e=ec side panel, q=back to contour menu): "
                    )).strip().lower()
                else:
                    print(_colorize_inline_commands(
                        "Spines/ticks apply to the contour plot only. q=return to contour menu"
                    ))
                    pane = _safe_input(_colorize_prompt(
                        "Pane (o=operando contour, q=back to contour menu): "
                    )).strip().lower()
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
                    
                    if is_ec:
                        apply_wasd_spines(axis, wasd_state, sides=('top', 'bottom', 'right'))
                        apply_wasd_tick_params(axis, wasd_state, y_sides=('right',), y_mode='right')
                    elif is_operando and ec_ax is not None:
                        apply_wasd_spines(axis, wasd_state, sides=('top', 'bottom', 'left'))
                        apply_wasd_tick_params(axis, wasd_state, y_sides=('left',), y_mode='left')
                    else:
                        apply_wasd_spines(axis, wasd_state)
                        apply_wasd_tick_params(axis, wasd_state)
                    
                    # Build tick_state dict from current wasd_state for UI functions
                    current_tick_state = {
                        't_ticks': bool(wasd_state['top']['ticks']),
                        't_labels': bool(wasd_state['top']['labels']),
                        'tx': bool(wasd_state['top']['ticks'] and wasd_state['top']['labels']),
                        'b_ticks': bool(wasd_state['bottom']['ticks']),
                        'b_labels': bool(wasd_state['bottom']['labels']),
                        'bx': bool(wasd_state['bottom']['ticks'] and wasd_state['bottom']['labels']),
                        'l_ticks': bool(wasd_state['left']['ticks']),
                        'l_labels': bool(wasd_state['left']['labels']),
                        'ly': bool(wasd_state['left']['ticks'] and wasd_state['left']['labels']),
                        'r_ticks': bool(wasd_state['right']['ticks']),
                        'r_labels': bool(wasd_state['right']['labels']),
                        'ry': bool(wasd_state['right']['ticks'] and wasd_state['right']['labels']),
                        'mtx': bool(wasd_state['top']['minor']),
                        'mbx': bool(wasd_state['bottom']['minor']),
                        'mly': bool(wasd_state['left']['minor']),
                        'mry': bool(wasd_state['right']['minor']),
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
                        # Set flag for right title state (used by save/export)
                        axis._right_ylabel_on = bool(wasd_state['right']['title'])
                        try:
                            keep_yaxis_label_on_side(axis, 'right', visible=bool(axis.get_ylabel()))
                        except Exception:
                            pass
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
                    apply_changed_side_title_positions(
                        changed_sides,
                        bottom=lambda: _ui_position_bottom_xlabel(axis, fig, current_tick_state),
                        top=lambda: _ui_position_top_xlabel(axis, fig, current_tick_state),
                        left=None if is_ec else lambda: _ui_position_left_ylabel(axis, fig, current_tick_state),
                        # EC axes use actual ylabel on right, not duplicate artists.
                        right=None if is_ec else lambda: _ui_position_right_ylabel(axis, fig, current_tick_state),
                    )
                
                def _sync_operando_pane_tick_state():
                    ts_current = wasd_to_tick_state(
                        wasd,
                        tick_defaults={
                            'top': False,
                            'bottom': True,
                            'left': not (target is ec_ax),
                            'right': bool(target is ec_ax or (target is ax and ec_ax is None)),
                        },
                        label_defaults={
                            'top': False,
                            'bottom': True,
                            'left': not (target is ec_ax),
                            'right': bool(target is ec_ax or (target is ax and ec_ax is None)),
                        },
                    )
                    try:
                        if target is not None:
                            target._saved_tick_state = dict(ts_current)
                    except Exception:
                        pass
                def _apply_operando_pane_wasd(changed_sides=None):
                    _apply_wasd_axis(target, wasd, changed_sides)
                def _draw_operando_spine_menu():
                    try:
                        fig.canvas.draw()
                    except Exception:
                        fig.canvas.draw_idle()
                run_spine_tick_menu(
                    fig=fig,
                    wasd=wasd,
                    safe_input=_safe_input,
                    colorize_prompt=_colorize_prompt,
                    colorize_inline_commands=_colorize_inline_commands,
                    push_state=_snapshot,
                    sync_tick_state=_sync_operando_pane_tick_state,
                    apply_wasd=_apply_operando_pane_wasd,
                    draw=_draw_operando_spine_menu,
                    mode_label='EC pane' if target is ec_ax else 'operando pane',
                    back_label='pane chooser',
                    axis_map={'x': target.xaxis, 'y': target.yaxis},
                    direction_axes=[ax] + ([ec_ax] if ec_ax is not None else []),
                    length_axes=[ax] + ([ec_ax] if ec_ax is not None else []),
                    side_aliases={'left': 'right'} if target is ec_ax else None,
                )
                continue
            print_menu()

    def _handle_op_et():
            nonlocal cur, hi, ions_abs, line, lo, new_lower, new_upper, orig_max, orig_min, t, val
            if ec_ax is None:
                print("EC panel not available (no .mpt file in folder).")
                print_menu()
                return
            while True:
                cur = ec_ax.get_ylim(); print(f"Current EC time range (Y): {cur[0]:.4g} {cur[1]:.4g}")
                print("  " + _colorize_menu("limit1 limit2: set both limits (either order)"))
                print("  " + _colorize_menu("w: upper only"))
                print("  " + _colorize_menu("s: lower only"))
                print("  " + _colorize_menu("a: auto (restore original)"))
                print("  " + _colorize_menu("q: back"))
                line = _safe_input(_colorize_prompt("EC time (w/s/a/q): ")).strip()
                if not line or line.lower() == 'q':
                    break
                if line.lower() == 'w':
                    # Upper only: change upper limit, fix lower - stay in loop
                    while True:
                        cur = ec_ax.get_ylim()
                        print(f"Current EC time range (Y): {cur[0]:.4g} {cur[1]:.4g}")
                        val = _safe_input(_colorize_inline_commands(f"Enter new upper time limit (current lower: {cur[0]:.4g}, q=back): ")).strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_upper = float(val)
                        except (ValueError, KeyboardInterrupt):
                            print("Invalid value, ignored.")
                            continue
                        _snapshot("ec-time-range")
                        ec_ax.set_ylim(cur[0], new_upper)
                        ec_ax._saved_time_ylim = (cur[0], new_upper)
                        fig.canvas.draw_idle()
                        print(f"EC time range updated: {ec_ax.get_ylim()[0]:.4g} {ec_ax.get_ylim()[1]:.4g}")
                if line.lower() == 's':
                    # Lower only: change lower limit, fix upper - stay in loop
                    while True:
                        cur = ec_ax.get_ylim()
                        print(f"Current EC time range (Y): {cur[0]:.4g} {cur[1]:.4g}")
                        val = _safe_input(_colorize_inline_commands(f"Enter new lower time limit (current upper: {cur[1]:.4g}, q=back): ")).strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_lower = float(val)
                        except (ValueError, KeyboardInterrupt):
                            print("Invalid value, ignored.")
                            continue
                        _snapshot("ec-time-range")
                        ec_ax.set_ylim(new_lower, cur[1])
                        ec_ax._saved_time_ylim = (new_lower, cur[1])
                        fig.canvas.draw_idle()
                        print(f"EC time range updated: {ec_ax.get_ylim()[0]:.4g} {ec_ax.get_ylim()[1]:.4g}")
                if line.lower() == 'a':
                    # Auto: restore original range from EC lines
                    _snapshot("ec-time-range-auto")
                    try:
                        all_y = []
                        for ln in ec_ax.lines:
                            try:
                                yd = np.asarray(ln.get_ydata(), dtype=float)
                                if yd.size > 0:
                                    all_y.extend([yd.min(), yd.max()])
                            except Exception:
                                pass
                        if all_y:
                            orig_min = min(all_y)
                            orig_max = max(all_y)
                            ec_ax.set_ylim(orig_min, orig_max)
                            ec_ax._saved_time_ylim = (orig_min, orig_max)
                            fig.canvas.draw_idle()
                            print(f"EC time range restored to original: {ec_ax.get_ylim()[0]:.4g} {ec_ax.get_ylim()[1]:.4g}")
                        else:
                            print("No original data available.")
                    except Exception as e:
                        print(f"Error restoring original time range: {e}")
                    continue
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
                            t = np.asarray(getattr(ec_ax, '_ec_time_h'))
                            ions_abs = getattr(ec_ax, '_ions_abs', None)
                            if ions_abs is not None:
                                install_ec_ions_y_display(ec_ax, t, ions_abs, save_prev=False)
                        except Exception:
                            pass
                    fig.canvas.draw_idle()
                except Exception as e:
                    print(f"Invalid range: {e}")
            print_menu()

    def _handle_op_ex():
            nonlocal cur, hi, line, ln, lo, new_lower, new_upper, orig_max, orig_min, val
            if ec_ax is None:
                print("EC panel not available (no .mpt file in folder).")
                print_menu()
                return
            while True:
                cur = ec_ax.get_xlim()
                print(f"Current EC X range: {cur[0]:.4g} {cur[1]:.4g}")
                print("  " + _colorize_menu("limit1 limit2: set both limits (either order)"))
                print("  " + _colorize_menu("w: upper only"))
                print("  " + _colorize_menu("s: lower only"))
                print("  " + _colorize_menu("a: auto (restore original)"))
                print("  " + _colorize_menu("q: back"))
                line = _safe_input(_colorize_prompt("EC X (w/s/a/q): ")).strip()
                if not line or line.lower() == 'q':
                    break
                if line.lower() == 'w':
                    # Upper only: change upper limit, fix lower - stay in loop
                    while True:
                        cur = ec_ax.get_xlim()
                        print(f"Current EC X range: {cur[0]:.4g} {cur[1]:.4g}")
                        val = _safe_input(_colorize_inline_commands(f"Enter new upper EC X limit (current lower: {cur[0]:.4g}, q=back): ")).strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_upper = float(val)
                        except (ValueError, KeyboardInterrupt):
                            print("Invalid value, ignored.")
                            continue
                        _snapshot("ec-x-range")
                        ec_ax.set_xlim(cur[0], new_upper)
                        ec_ax._prev_ec_xlim = (cur[0], new_upper)
                        ec_ax._ions_xlim_expanded = False
                        fig.canvas.draw_idle()
                        print(f"EC X range updated: {ec_ax.get_xlim()[0]:.4g} {ec_ax.get_xlim()[1]:.4g}")
                if line.lower() == 's':
                    # Lower only: change lower limit, fix upper - stay in loop
                    while True:
                        cur = ec_ax.get_xlim()
                        print(f"Current EC X range: {cur[0]:.4g} {cur[1]:.4g}")
                        val = _safe_input(_colorize_inline_commands(f"Enter new lower EC X limit (current upper: {cur[1]:.4g}, q=back): ")).strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_lower = float(val)
                        except (ValueError, KeyboardInterrupt):
                            print("Invalid value, ignored.")
                            continue
                        _snapshot("ec-x-range")
                        ec_ax.set_xlim(new_lower, cur[1])
                        ec_ax._prev_ec_xlim = (new_lower, cur[1])
                        ec_ax._ions_xlim_expanded = False
                        fig.canvas.draw_idle()
                        print(f"EC X range updated: {ec_ax.get_xlim()[0]:.4g} {ec_ax.get_xlim()[1]:.4g}")
                if line.lower() == 'a':
                    # Auto: restore original range from EC lines
                    _snapshot("ec-x-range-auto")
                    try:
                        all_x = []
                        for ln in ec_ax.lines:
                            try:
                                xd = np.asarray(ln.get_xdata(), dtype=float)
                                if xd.size > 0:
                                    all_x.extend([xd.min(), xd.max()])
                            except Exception:
                                pass
                        if all_x:
                            orig_min = min(all_x)
                            orig_max = max(all_x)
                            ec_ax.set_xlim(orig_min, orig_max)
                            ec_ax._prev_ec_xlim = (orig_min, orig_max)
                            ec_ax._ions_xlim_expanded = False
                            fig.canvas.draw_idle()
                            print(f"EC X range restored to original: {ec_ax.get_xlim()[0]:.4g} {ec_ax.get_xlim()[1]:.4g}")
                        else:
                            print("No original data available.")
                    except Exception as e:
                        print(f"Error restoring original EC X range: {e}")
                    continue
                _snapshot("ec-x-range")
                try:
                    lo, hi = map(float, line.split())
                    if lo == hi:
                        raise ValueError("limits must differ")
                    ec_ax.set_xlim(lo, hi)
                    try:
                        ec_ax._prev_ec_xlim = (lo, hi)
                        ec_ax._ions_xlim_expanded = False
                    except Exception:
                        pass
                    try:
                        fig.canvas.draw()
                    except Exception:
                        fig.canvas.draw_idle()
                except Exception as e:
                    print(f"Invalid range: {e}")
            print_menu()

    def _handle_op_ox():
            nonlocal cur, data_array, extent, hi, line, lo, new_lower, new_upper, orig_max, orig_min, val
            if getattr(fig, '_is_dqdv_2d_contour', False):
                try:
                    _dqdv_2d_potential_window_menu(fig, ax, im, cbar, _snapshot)
                except Exception as e:
                    print(f"Potential window change failed: {e}")
                print_menu()
                return
            while True:
                cur = ax.get_xlim(); print(f"Current operando X: {cur[0]:.4g} {cur[1]:.4g}")
                print("  " + _colorize_menu("limit1 limit2: set both limits (either order)"))
                print("  " + _colorize_menu("w: upper only"))
                print("  " + _colorize_menu("s: lower only"))
                print("  " + _colorize_menu("a: auto (restore original)"))
                print("  " + _colorize_menu("q: back"))
                line = _safe_input(_colorize_prompt("Operando X (w/s/a/q): ")).strip()
                if not line or line.lower() == 'q':
                    break
                if line.lower() == 'w':
                    # Upper only: change upper limit, fix lower - stay in loop
                    while True:
                        cur = ax.get_xlim()
                        print(f"Current operando X: {cur[0]:.4g} {cur[1]:.4g}")
                        val = _safe_input(_colorize_inline_commands(f"Enter new upper X limit (current lower: {cur[0]:.4g}, q=back): ")).strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_upper = float(val)
                        except (ValueError, KeyboardInterrupt):
                            print("Invalid value, ignored.")
                            continue
                        _snapshot("operando-xrange")
                        ax.set_xlim(cur[0], new_upper)
                        _redraw_operando_cif_if_present(fig, ax)
                        fig.canvas.draw_idle()
                        print(f"Operando X range updated: {ax.get_xlim()[0]:.4g} {ax.get_xlim()[1]:.4g}")
                if line.lower() == 'w':
                    continue
                if line.lower() == 's':
                    # Lower only: change lower limit, fix upper - stay in loop
                    while True:
                        cur = ax.get_xlim()
                        print(f"Current operando X: {cur[0]:.4g} {cur[1]:.4g}")
                        val = _safe_input(_colorize_inline_commands(f"Enter new lower X limit (current upper: {cur[1]:.4g}, q=back): ")).strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_lower = float(val)
                        except (ValueError, KeyboardInterrupt):
                            print("Invalid value, ignored.")
                            continue
                        _snapshot("operando-xrange")
                        ax.set_xlim(new_lower, cur[1])
                        _redraw_operando_cif_if_present(fig, ax)
                        fig.canvas.draw_idle()
                        print(f"Operando X range updated: {ax.get_xlim()[0]:.4g} {ax.get_xlim()[1]:.4g}")
                if line.lower() == 's':
                    continue
                if line.lower() == 'a':
                    # Auto: restore original range from image data
                    _snapshot("operando-xrange-auto")
                    try:
                        data_array = np.asarray(im.get_array(), dtype=float)
                        if data_array.size > 0:
                            # Get original extent from image
                            extent = im.get_extent()
                            if extent and len(extent) == 4:
                                orig_min = min(extent[0], extent[1])
                                orig_max = max(extent[0], extent[1])
                                ax.set_xlim(orig_min, orig_max)
                                _redraw_operando_cif_if_present(fig, ax)
                                fig.canvas.draw_idle()
                                print(f"Operando X range restored to original: {ax.get_xlim()[0]:.4g} {ax.get_xlim()[1]:.4g}")
                            else:
                                print("No original data available.")
                        else:
                            print("No original data available.")
                    except Exception as e:
                        print(f"Error restoring original X range: {e}")
                    continue
                _snapshot("operando-xrange")
                try:
                    lo, hi = map(float, line.split())
                    ax.set_xlim(lo, hi)
                    _redraw_operando_cif_if_present(fig, ax)
                    fig.canvas.draw_idle()
                except Exception as e:
                    print(f"Invalid range: {e}")
            print_menu()

    while True:
        try:
            cmd = _safe_input(_colorize_prompt("Press a key: ")).strip().lower()
        except (KeyboardInterrupt, EOFError):
            print("\n\nExiting interactive menu...")
            break
        if not cmd:
            continue
        if cmd == 'q':
            if canvas_mode:
                try:
                    plt.close(fig)
                except Exception:
                    pass
                break
            try:
                ans = _safe_input(_colorize_inline_commands("Quit interactive? Remember to save (e=export, s=save). Quit now? (y/n): ")).strip().lower()
            except Exception:
                ans = 'y'
            if ans == 'y':
                try:
                    plt.close(fig)
                except Exception:
                    pass
                break
            elif ans in ('e', 's'):
                cmd = ans  # Fall through to export/save handler
            else:
                print_menu()
                continue
        if cmd == 'e':
            handle_export_figure(_make_action_context())
            continue
        if cmd == 'n':
            try:
                _toggle_crosshair()
            except Exception as e:
                print(f"Error toggling crosshair: {e}")
            print_menu(); continue
        if cmd == 'v':
            run_visibility_menu(
                fig=fig,
                ax=ax,
                im=im,
                cbar=cbar,
                ec_ax=ec_ax,
                snapshot=_snapshot,
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
                colorize_inline_commands=_colorize_inline_commands,
            )
            print_menu(); continue
        if cmd == 'b':
            handle_undo(_make_action_context())
            continue
        if cmd == 's':
            handle_save_session(_make_action_context())
            continue
        if cmd == 'pk':
            run_peak_search_menu(
                im=im,
                file_paths=file_paths,
                print_menu=print_menu,
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
            )
            continue
        if cmd == 'h':
            # Always read fresh value from attribute to avoid stale cached value
            ax_h_in = getattr(ax, '_fixed_ax_h_in', ax_h_in)
            print(f"Current height: {ax_h_in:.2f} in")
            print("  " + _colorize_menu("inches: new height (inches)"))
            print("  " + _colorize_menu("q: back"))
            val = _safe_input(_colorize_prompt("Height (inches, q=back): ")).strip()
            if val:
                _snapshot("height")
                try:
                    new_h = max(0.25, float(val))
                    ax_h_in = new_h
                    _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)  # pyright: ignore[reportOptionalMemberAccess]
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
            if ec_ax is not None:
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
            def _apply_operando_font_family(family):
                _snapshot("font-family")
                set_fonts(family=family)
            def _apply_operando_font_size(size):
                _snapshot("font-size")
                set_fonts(size=size)
            run_font_menu(
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
                get_current_family=lambda: plt.rcParams.get('font.sans-serif', [''])[0],
                get_current_size=lambda: plt.rcParams.get('font.size', None),
                apply_family=_apply_operando_font_family,
                apply_size=_apply_operando_font_size,
            )
            print_menu()
        elif cmd == 'l':
            # Line widths submenu for both operando and EC panes
            while True:
                print("Line widths: set frame (spines) and tick widths for both operando and EC")
                print(_colorize_inline_commands("Enter frame/tick width (e.g., '1.5' or 'f t' for frame/tick separately)"))
                print("Format examples:")
                print(_colorize_inline_commands("  1.5      - set both frame and ticks to 1.5"))
                print(_colorize_inline_commands("  1.5 2.5  - set frame=1.5, ticks=2.5"))
                print(_colorize_inline_commands("  q        - back"))
                
                inp = _safe_input(_colorize_prompt("Line widths (value or 'f t', q=back): ")).strip().lower()
                if not inp or inp == 'q':
                    break
                
                _snapshot("line-widths")
                try:
                    frame_w, tick_w, tick_minor = parse_frame_tick_widths(
                        inp,
                        single_minor_scale=1.0,
                        paired_minor_scale=1.0,
                    )
                    frame_w = max(0.1, frame_w)
                    tick_w = max(0.1, tick_w)
                    tick_minor = max(0.1, tick_minor)
                    axes_for_widths = [ax]
                    if ec_ax is not None:
                        axes_for_widths.append(ec_ax)
                    if cbar is not None:
                        axes_for_widths.append(cbar.ax)
                    apply_frame_and_tick_widths(
                        axes_for_widths,
                        frame_width=frame_w,
                        major_width=tick_w,
                        minor_width=tick_minor,
                    )
                    
                    try:
                        fig.canvas.draw()
                    except Exception:
                        fig.canvas.draw_idle()
                    
                    if ec_ax is not None:
                        print(f"Applied: frame={frame_w:.2f}, ticks={tick_w:.2f} to operando, EC, and colorbar")
                    else:
                        print(f"Applied: frame={frame_w:.2f}, ticks={tick_w:.2f} to operando and colorbar")
                except ValueError:
                    print("Invalid number format.")
                except Exception as e:
                    print(f"Error: {e}")
            print_menu()
        elif cmd == 't':
            # Unified WASD ticks/labels/spines submenu for either pane
            # Import here to avoid scoping issues with nested functions
            # Import UI positioning functions locally to ensure they're accessible in nested functions
            
            _handle_op_t()
            continue
        elif cmd == 'c':
            # CIF tick labels submenu (only when CIF data is present)
            _handle_op_c()
            continue
        elif cmd == 'ox':
            _handle_op_ox()
            continue
        elif cmd == 'oy':
            while True:
                cur = ax.get_ylim(); print(f"Current operando Y: {cur[0]:.4g} {cur[1]:.4g}")
                print("  " + _colorize_menu("limit1 limit2: set both limits (either order)"))
                print("  " + _colorize_menu("w: upper only"))
                print("  " + _colorize_menu("s: lower only"))
                print("  " + _colorize_menu("a: auto (restore original)"))
                print("  " + _colorize_menu("q: back"))
                line = _safe_input(_colorize_prompt("Operando Y (w/s/a/q): ")).strip()
                if not line or line.lower() == 'q':
                    break
                if line.lower() == 'w':
                    # Upper only: change upper limit, fix lower - stay in loop
                    while True:
                        cur = ax.get_ylim()
                        print(f"Current operando Y: {cur[0]:.4g} {cur[1]:.4g}")
                        val = _safe_input(_colorize_inline_commands(f"Enter new upper Y limit (current lower: {cur[0]:.4g}, q=back): ")).strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_upper = float(val)
                        except (ValueError, KeyboardInterrupt):
                            print("Invalid value, ignored.")
                            continue
                        _snapshot("operando-yrange")
                        ax.set_ylim(cur[0], new_upper)
                        fig.canvas.draw_idle()
                        print(f"Operando Y range updated: {ax.get_ylim()[0]:.4g} {ax.get_ylim()[1]:.4g}")
                if line.lower() == 'w':
                    continue
                if line.lower() == 's':
                    # Lower only: change lower limit, fix upper - stay in loop
                    while True:
                        cur = ax.get_ylim()
                        print(f"Current operando Y: {cur[0]:.4g} {cur[1]:.4g}")
                        val = _safe_input(_colorize_inline_commands(f"Enter new lower Y limit (current upper: {cur[1]:.4g}, q=back): ")).strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_lower = float(val)
                        except (ValueError, KeyboardInterrupt):
                            print("Invalid value, ignored.")
                            continue
                        _snapshot("operando-yrange")
                        ax.set_ylim(new_lower, cur[1])
                        fig.canvas.draw_idle()
                        print(f"Operando Y range updated: {ax.get_ylim()[0]:.4g} {ax.get_ylim()[1]:.4g}")
                if line.lower() == 's':
                    continue
                if line.lower() == 'a':
                    # Auto: restore original range from image data
                    _snapshot("operando-yrange-auto")
                    try:
                        data_array = np.asarray(im.get_array(), dtype=float)
                        if data_array.size > 0:
                            # Get original extent from image
                            extent = im.get_extent()
                            if extent and len(extent) == 4:
                                orig_min = min(extent[2], extent[3])
                                orig_max = max(extent[2], extent[3])
                                ax.set_ylim(orig_min, orig_max)
                                fig.canvas.draw_idle()
                                print(f"Operando Y range restored to original: {ax.get_ylim()[0]:.4g} {ax.get_ylim()[1]:.4g}")
                            else:
                                print("No original data available.")
                        else:
                            print("No original data available.")
                    except Exception as e:
                        print(f"Error restoring original Y range: {e}")
                    continue
                _snapshot("operando-yrange")
                try:
                    lo, hi = map(float, line.split())
                    ax.set_ylim(lo, hi)
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
                    arr = np.asarray(im.get_array(), dtype=float)
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
                            c0 = int(np.floor((xlo - xmin) / (xmax - xmin) * (W - 1)))
                            c1 = int(np.ceil((xhi - xmin) / (xmax - xmin) * (W - 1)))
                        else:
                            c0, c1 = 0, W - 1
                        if ymax > ymin:
                            r0 = int(np.floor((ylo - ymin) / (ymax - ymin) * (H - 1)))
                            r1 = int(np.ceil((yhi - ymin) / (ymax - ymin) * (H - 1)))
                        else:
                            r0, r1 = 0, H - 1
                        
                        c0 = max(0, min(W - 1, c0)); c1 = max(0, min(W - 1, c1))
                        r0 = max(0, min(H - 1, r0)); r1 = max(0, min(H - 1, r1))
                        if c1 < c0: c0, c1 = c1, c0
                        if r1 < r0: r0, r1 = r1, r0
                        view = arr[r0:r1+1, c0:c1+1]
                        finite = view[np.isfinite(view)]
                        if finite.size:
                            auto_lo = float(np.min(finite))
                            auto_hi = float(np.max(finite))
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
                
                print("  " + _colorize_menu("limit1 limit2: set both limits (either order)"))
                print("  " + _colorize_menu("w: upper only"))
                print("  " + _colorize_menu("s: lower only"))
                print("  " + _colorize_menu("b: bar (drag to adjust range)"))
                if auto_available:
                    print("  " + _colorize_menu("a: auto-fit to visible"))
                print("  " + _colorize_menu("q: back"))
                if auto_available:
                    line = _safe_input(_colorize_prompt("Intensity (w/s/b/a/q): ")).strip()
                else:
                    line = _safe_input(_colorize_prompt("Intensity (w/s/b/q): ")).strip()
                
                if not line or line.lower() == 'q':
                    break
                
                if line.lower() == 'b':
                    # Interactive bar: drag to adjust intensity range
                    if RangeSlider is None or Button is None:
                        print("Intensity bar requires matplotlib 3.4+ (RangeSlider). Use limit1 limit2 or w/s instead.")
                        continue
                    _snapshot("operando-intensity-range")
                    # Suppress macOS IMKCFRunLoopWakeUpReliable warning during slider (closing window triggers it)
                    _orig_stderr = sys.stderr
                    try:
                        sys.stderr = _FilterIMKWarning(_orig_stderr)
                    except Exception:
                        pass
                    try:
                        cur = im.get_clim()
                        vmin_cur, vmax_cur = float(cur[0]), float(cur[1])
                        # Get full data range for slider bounds
                        arr = np.asarray(im.get_array(), dtype=float)
                        if arr.ndim == 2 and arr.size > 0:
                            finite = arr[np.isfinite(arr)]
                            vmin_data = float(np.min(finite)) if finite.size else vmin_cur
                            vmax_data = float(np.max(finite)) if finite.size else vmax_cur
                        else:
                            vmin_data = vmin_cur
                            vmax_data = vmax_cur
                        # Ensure slider range spans current values
                        vmin_slider = min(vmin_data, vmin_cur)
                        vmax_slider = max(vmax_data, vmax_cur)
                        if vmax_slider <= vmin_slider:
                            vmax_slider = vmin_slider + 1.0
                        # Create slider figure
                        fig_slider = plt.figure(figsize=(8, 1.8), facecolor='0.95')
                        try:
                            fig_slider.canvas.manager.set_window_title("Intensity range")
                        except Exception:
                            pass
                        ax_slider = fig_slider.add_axes([0.15, 0.35, 0.7, 0.25])
                        slider = RangeSlider(ax_slider, "Intensity", vmin_slider, vmax_slider, valinit=(vmin_cur, vmax_cur))
                        ax_btn = fig_slider.add_axes([0.8, 0.05, 0.15, 0.2])
                        btn_done = Button(ax_btn, "Done", color="0.85", hovercolor="0.95")
                        def _on_slider_change(val):
                            lo, hi = val
                            _safe_set_clim(im, lo, hi)
                            try:
                                if cbar is not None:
                                    _update_custom_colorbar(cbar.ax, im)
                            except Exception:
                                pass
                            fig.canvas.draw_idle()
                        def _on_done_clicked(event):
                            fig_slider.canvas.stop_event_loop()
                        def _on_slider_closed(event):
                            try:
                                fig_slider.canvas.stop_event_loop()
                            except Exception:
                                pass
                        slider.on_changed(_on_slider_change)
                        btn_done.on_clicked(_on_done_clicked)
                        fig_slider.canvas.mpl_connect("close_event", _on_slider_closed)
                        fig_slider.canvas.draw_idle()
                        plt.show(block=False)
                        try:
                            fig_slider.canvas.start_event_loop(timeout=-1)
                        except Exception:
                            pass
                        # Capture final values from slider before closing (callback already updated im)
                        try:
                            final_lo, final_hi = slider.val
                        except Exception:
                            final_lo, final_hi = im.get_clim()
                        plt.close(fig_slider)
                        try:
                            _safe_set_clim(im, final_lo, final_hi)
                            if cbar is not None:
                                _update_custom_colorbar(cbar.ax, im)
                            fig.canvas.draw_idle()
                            print(f"Intensity range: {final_lo:.4g} to {final_hi:.4g}")
                        except Exception:
                            pass
                    except Exception as e:
                        print(f"Slider failed: {e}")
                    finally:
                        try:
                            sys.stderr = _orig_stderr
                        except Exception:
                            pass
                    continue
                
                if line.lower() == 'w':
                    # Upper only: change upper limit, fix lower - stay in loop
                    while True:
                        try:
                            cur = im.get_clim()
                            print(f"Current color scale range: {cur[0]:.4g} to {cur[1]:.4g}")
                        except Exception:
                            print("Could not retrieve current color scale range")
                            break
                        val = _safe_input(_colorize_inline_commands(f"Enter new upper intensity limit (current lower: {cur[0]:.4g}, q=back): ")).strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_upper = float(val)
                        except (ValueError, KeyboardInterrupt):
                            print("Invalid value, ignored.")
                            continue
                        _snapshot("operando-intensity-range")
                        _safe_set_clim(im, cur[0], new_upper)
                        try:
                            if cbar is not None:
                                _update_custom_colorbar(cbar.ax, im)
                        except Exception:
                            pass
                        fig.canvas.draw_idle()
                        print(f"Intensity range updated: {im.get_clim()[0]:.4g} to {im.get_clim()[1]:.4g}")
                if line.lower() == 's':
                    # Lower only: change lower limit, fix upper - stay in loop
                    while True:
                        try:
                            cur = im.get_clim()
                            print(f"Current color scale range: {cur[0]:.4g} to {cur[1]:.4g}")
                        except Exception:
                            print("Could not retrieve current color scale range")
                            break
                        val = _safe_input(_colorize_inline_commands(f"Enter new lower intensity limit (current upper: {cur[1]:.4g}, q=back): ")).strip()
                        if not val or val.lower() == 'q':
                            break
                        try:
                            new_lower = float(val)
                        except (ValueError, KeyboardInterrupt):
                            print("Invalid value, ignored.")
                            continue
                        _snapshot("operando-intensity-range")
                        _safe_set_clim(im, new_lower, cur[1])
                        try:
                            if cbar is not None:
                                _update_custom_colorbar(cbar.ax, im)
                        except Exception:
                            pass
                        fig.canvas.draw_idle()
                        print(f"Intensity range updated: {im.get_clim()[0]:.4g} to {im.get_clim()[1]:.4g}")
                
                _snapshot("operando-intensity-range")
                try:
                    if line.lower() == 'a':
                        # Apply auto-normalization to visible data
                        if auto_available:
                            _safe_set_clim(im, auto_lo, auto_hi)
                            try:
                                if cbar is not None:
                                    _update_custom_colorbar(cbar.ax, im)
                            except Exception:
                                pass
                            fig.canvas.draw_idle()
                            print(f"Applied auto-fit range: {auto_lo:.4g} to {auto_hi:.4g}")
                        else:
                            print("Auto-fit unavailable: no finite data in visible area")
                    else:
                        lo, hi = map(float, line.split())
                        _safe_set_clim(im, lo, hi)
                        try:
                            if cbar is not None:
                                _update_custom_colorbar(cbar.ax, im)
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
                print("  " + _colorize_menu("inches: new width (inches)"))
                print("  " + _colorize_menu("q: back"))
                val = _safe_input(_colorize_prompt("Operando width (inches, q=back): ")).strip()
                if not val or val.lower() == 'q':
                    break
                _snapshot("operando-width")
                try:
                    new_w = max(0.25, float(val))
                    ax_w_in = new_w
                    _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)  # pyright: ignore[reportOptionalMemberAccess]
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
                print("  " + _colorize_menu("inches: new width (inches)"))
                print("  " + _colorize_menu("q: back"))
                val = _safe_input(_colorize_prompt("EC width (inches, q=back): ")).strip()
                if not val or val.lower() == 'q':
                    break
                _snapshot("ec-width")
                try:
                    new_w = max(0.25, float(val))
                    ec_w_in = new_w
                    _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)  # pyright: ignore[reportOptionalMemberAccess]
                except Exception as e:
                    print(f"Invalid EC width: {e}")
            print_menu()
        elif cmd == 'oc':
            run_operando_colormap_menu(
                fig=fig,
                im=im,
                cbar=cbar,
                snapshot=_snapshot,
                update_custom_colorbar=_update_custom_colorbar,
                safe_input=_safe_input,
                colorize_inline_commands=_colorize_inline_commands,
            )
            print_menu()
        elif cmd == 'p':
            handle_export_style(_make_action_context())
            continue
        elif cmd == 'i':
            action_ctx = _make_action_context()
            handle_import_style(action_ctx)
            ax_w_in = action_ctx.ax_w_in
            ax_h_in = action_ctx.ax_h_in
            cb_w_in = action_ctx.cb_w_in
            cb_gap_in = action_ctx.cb_gap_in
            ec_gap_in = action_ctx.ec_gap_in
            ec_w_in = action_ctx.ec_w_in
            continue
        elif cmd == 'or':
            run_operando_rename_menu(
                fig=fig,
                ax=ax,
                snapshot=_snapshot,
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
            )
            print_menu()
        elif cmd == 'er':
            run_operando_ec_rename_menu(
                fig=fig,
                ec_ax=ec_ax,
                snapshot=_snapshot,
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
            )
            print_menu()
        elif cmd == 'eg':
            run_ec_grid_menu(
                fig=fig,
                ec_ax=ec_ax,
                snapshot=_snapshot,
                safe_input=_safe_input,
                colorize_prompt=_colorize_prompt,
                colorize_inline_commands=_colorize_inline_commands,
            )
            print_menu()
        elif cmd == 'el':
            run_ec_line_style_menu(
                fig=fig,
                ec_ax=ec_ax,
                snapshot=_snapshot,
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
            )
            print_menu()
        elif cmd == 'et':
            _handle_op_et()
            continue
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
                    sub = _safe_input(_colorize_inline_commands("ey submenu: n=ions, t=time, q=back: ")).strip().lower()
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
                            prompt = _colorize_inline_commands("Enter mass(mg), capacity-per-ion(mAh g^-1), start-ions (e.g. 4.5 26.8 0), q=cancel: ")
                        else:
                            prompt = _colorize_inline_commands(f"Enter mass,cap-per-ion,start-ions (blank=reuse {mass_mg} {cap_per_ion} {start_ions}; q=cancel): ")
                        s = _safe_input(prompt).strip()
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
                        if mass_mg is None or cap_per_ion is None or start_ions is None:
                            print("Bad input. Expect three numbers: mass, capacity-per-ion, start-ions.")
                            continue
                        _snapshot("ey->ions")
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
                        # Install ions formatter + high-precision status bar (time -> ions)
                        install_ec_ions_y_display(ec_ax, t, ions_abs)
                        # Set default ions label or custom override
                        try:
                            label = 'Number of ions'
                            if hasattr(ec_ax, '_custom_labels') and ec_ax._custom_labels.get('y_ions'):
                                label = ec_ax._custom_labels['y_ions']
                            ec_ax.set_ylabel(label)
                        except Exception:
                            pass
                        try:
                            keep_yaxis_label_on_side(ec_ax, 'right')
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
                        # Restore previous y-axis formatter, locator, and status bar
                        restore_ec_time_y_display(ec_ax)
                        # Set default time label or custom override
                        try:
                            label = 'Time (h)'
                            if hasattr(ec_ax, '_custom_labels') and ec_ax._custom_labels.get('y_time'):
                                label = ec_ax._custom_labels['y_time']
                            ec_ax.set_ylabel(label)
                        except Exception:
                            pass
                        try:
                            keep_yaxis_label_on_side(ec_ax, 'right')
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
        elif cmd == 'ex':
            _handle_op_ex()
            continue
        elif cmd == 'g':
            # Preserve legacy size submenu
            while True:
                cur_w, cur_h = _get_fig_size(fig)
                print(f"Current canvas size: {cur_w:.2f} x {cur_h:.2f} in (W x H)")
                print("  " + _colorize_menu("W H: new width and height (inches)"))
                print("  " + _colorize_menu("q: back"))
                print("(Panel widths/gaps are not altered)")
                line = _safe_input(_colorize_prompt("Canvas (W H, q=back): ")).strip()
                if not line or line.lower() == 'q':
                    break
                if line:
                    _snapshot("canvas-size")
                    try:
                        parts = line.split()
                        if len(parts) == 2:
                            W = max(1.0, float(parts[0])); H = max(1.0, float(parts[1]))
                            
                            # Capture current panel dimensions in inches before resize
                            old_w, old_h = cur_w, cur_h
                            cb_pos = cbar.ax.get_position()  # pyright: ignore[reportOptionalMemberAccess]
                            ax_pos = ax.get_position()
                            ec_pos = ec_ax.get_position() if ec_ax else None
                            
                            cb_w_in = cb_pos.width * old_w
                            cb_h_in = cb_pos.height * old_h
                            cb_gap_in = (ax_pos.x0 - (cb_pos.x0 + cb_pos.width)) * old_w
                            ax_w_in = ax_pos.width * old_w
                            ax_h_in = ax_pos.height * old_h
                            if ec_pos is not None:
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
                            cbar.ax.set_position([cb_x0, y0, cb_wf, cb_hf])  # pyright: ignore[reportOptionalMemberAccess]
                            
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
        elif cmd == 'oe':
            handle_quick_overwrite_figure(_make_action_context())
            continue
        elif cmd == 'os':
            handle_quick_overwrite_session(_make_action_context())
            continue
        elif cmd in ('ops', 'opsg'):
            handle_quick_overwrite_style(_make_action_context(), include_geometry=(cmd == 'opsg'))
            continue
        else:
            print("Unknown command.")
            print_menu()

__all__ = ["operando_ec_interactive_menu"]

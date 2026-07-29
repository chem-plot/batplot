"""Interactive menu for Capacity-Per-Cycle (CPC) plots.

This module provides the interactive menu for CPC (Capacity Per Cycle) mode.
CPC plots show how battery capacity changes over multiple cycles, displaying:
- Charge capacity vs cycle number
- Discharge capacity vs cycle number  
- Coulombic efficiency vs cycle number

HOW CPC MODE WORKS:
------------------
CPC mode reads battery cycling data and extracts:
1. Maximum charge capacity for each cycle
2. Maximum discharge capacity for each cycle
3. Coulombic efficiency = (discharge_capacity / charge_capacity) × 100%

These values are plotted as scatter points (one point per cycle), allowing you
to see capacity fade and efficiency trends over the battery's lifetime.

INTERACTIVE FEATURES:
--------------------
The interactive menu allows you to:
- Customize colors for each file (charge, discharge, efficiency)
- Adjust line/marker styles and sizes
- Show/hide individual files
- Modify axis ranges and labels
- Export style files (.bpcfg) for reuse
- Save/load sessions

MULTI-FILE SUPPORT:
-----------------
CPC mode can plot multiple files simultaneously, each with its own color scheme.
This is useful for comparing different battery cells, materials, or conditions.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, cast
import json
import os
import sys
import contextlib
from io import StringIO
import random as _random
import re
import traceback

import matplotlib.pyplot as plt  # type: ignore[import]
from matplotlib.ticker import AutoMinorLocator, NullFormatter, NullLocator, MultipleLocator, AutoLocator  # type: ignore[import]
from matplotlib.colors import to_hex  # type: ignore[import]
import numpy as np  # type: ignore[import]

from ...ui import (
    set_spine_side_color as _ui_set_spine_side_color,
    finalize_spine_colors_cpc,
    resize_plot_frame, resize_canvas,
    update_tick_visibility as _ui_update_tick_visibility,
    position_top_xlabel as _ui_position_top_xlabel,
    position_right_ylabel as _ui_position_right_ylabel,
    position_bottom_xlabel as _ui_position_bottom_xlabel,
    position_left_ylabel as _ui_position_left_ylabel,
    capture_axis_tick_locators,
    restore_axis_tick_locators,
)
from .menu import _colorize_menu, build_cpc_menu_columns, print_cpc_menu as _print_menu
from ...utils import (
    choose_save_path,
    choose_style_file,
    list_files_in_subdirectory,
    get_organized_path,
    natural_sort_key,
    ensure_exact_case_filename,
)
from ...color_utils import resolve_color_token
from .session import dump_cpc_session
from .colors import _generate_similar_color, run_cpc_color_menu
from .labels import run_cpc_rename_menu
from ..common.crosshair_export import register_crosshair
from ..common.menu_rendering import prompt_menu_key
from ..common.terminal import (
    colorize_inline_commands as _colorize_inline_commands,
    colorize_prompt as _colorize_prompt,
    safe_input as _safe_input,
)
from ..common.files import format_file_timestamp as _format_file_timestamp
from ..common.fonts import (
    apply_font_family_to_artists,
    apply_font_size_to_artists,
    axis_text_artists,
    collect_fig_font_artists,
    legend_text_artists,
    set_font_family_defaults,
    set_font_size_default,
)
from ..common.font_extras import (
    apply_fig_font_weight,
    apply_fig_text_highlight,
    apply_font_extras_from_cfg,
    apply_session_font_cfg,
    font_extras_export_dict,
    get_fig_font_weight,
    get_fig_text_highlight,
    get_fig_text_highlight_style,
)
from ..common.menus import run_axis_limit_menu, run_dispatch_menu, run_font_menu, run_legend_position_menu, run_option_menu
from ..common.sources import file_data_source_paths
from ..common.spines import (
    apply_changed_side_title_positions,
    apply_frame_and_tick_widths,
    apply_wasd_spines,
    apply_wasd_tick_params,
    current_tick_width,
    parse_frame_tick_widths,
    run_spine_tick_menu,
    sync_tick_state_from_wasd,
)
from .legend import (
    _build_compact_cpc_legend,
    _color_of,
    _coerce_legend_color,
    _get_legend_title,
    _legend_no_frame,
    _normalize_spine_color,
    _reapply_cpc_legend_text_colors,
    _rebuild_legend,
    _sanitize_legend_offset,
    _visible_handles_labels,
)
from .snapshots import (
    _apply_cpc_geometry_snapshot,
    _get_geometry_snapshot,
    push_cpc_state,
    restore_cpc_state,
)
from .actions import (
    CpcActionContext,
    handle_figure_export,
    handle_quick_overwrite_figure,
    handle_quick_overwrite_session,
    handle_quick_overwrite_style,
    handle_save_session,
    handle_style_export,
    handle_style_import,
    handle_undo,
)


def _collect_file_paths(file_data) -> list:
    """Extract absolute file paths from file_data structures."""
    return file_data_source_paths(file_data)


def _get_current_file_artists(file_data, current_idx):
    """Get the scatter artists for the currently selected file."""
    if not file_data or current_idx >= len(file_data):
        return None, None, None
    file_info = file_data[current_idx]
    return file_info['sc_charge'], file_info['sc_discharge'], file_info['sc_eff']


def _print_file_list(file_data, current_idx):
    """Print list of files with current selection highlighted."""
    print("\n=== Files ===")
    for i, f in enumerate(file_data):
        marker = "→" if i == current_idx else " "
        vis = "✓" if f.get('visible', True) else "✗"
        print(f"{marker} {i+1}. [{vis}] {f['filename']}")
    print()


from .style import (  # noqa: F401  — re-export for tests / older imports
    _apply_style,
    _cpc_font_artists,
    _is_hollow_marker,
    _style_snapshot,
)


def cpc_interactive_menu(fig, ax, ax2: Any, sc_charge, sc_discharge, sc_eff, file_data: Optional[List[Dict]] = None, canvas_mode: bool = False):
    """
    Interactive menu for Capacity-Per-Cycle (CPC) plots.
    
    HOW CPC INTERACTIVE MENU WORKS:
    ------------------------------
    This function provides an interactive command-line menu for customizing CPC plots.
    CPC plots show battery capacity and efficiency over multiple cycles.
    
    PLOT STRUCTURE:
    --------------
    CPC plots have two Y-axes (twin axes):
    - Left Y-axis: Capacity (mAh/g or mAh) - shows charge and discharge capacity
    - Right Y-axis: Efficiency (%) - shows coulombic efficiency
    
    X-axis: Cycle number (1, 2, 3, ...)
    
    Each cycle is represented by scatter points:
    - Charge capacity point (left axis)
    - Discharge capacity point (left axis)
    - Efficiency point (right axis)
    
    MULTI-FILE MODE:
    --------------
    CPC mode supports plotting multiple files simultaneously:
    - Each file gets its own set of scatter points (charge, discharge, efficiency)
    - Each file can have different colors
    - Files can be shown/hidden individually
    - You can switch between files to edit their properties
    
    MENU COMMANDS:
    -------------
    The menu is organized into three categories:
    
    **Styles** (visual appearance):
    - f: font (size and family)
    - l: line (width and style)
    - m: marker sizes
    - c: colors (for charge, discharge, efficiency)
    - k: spine colors (plot border colors)
    - ry: show/hide efficiency (right Y-axis)
    - t: toggle spines (show/hide tick labels)
    - h: legend (show/hide)
    - g: size (figure and axes size)
    - v: show/hide files (multi-file mode)
    
    **Geometries** (axis ranges and labels):
    - r: rename titles (axis labels)
    - x: x range (cycle number range)
    - y: y ranges (capacity and efficiency ranges)
    
    **Options** (file operations):
    - p: print/export style/geometry (save .bpcfg file)
    - i: import style/geometry (load .bpcfg file)
    - e: export figure (save plot as image)
    - s: save project (save session as .pkl)
    - b: undo (revert last change)
    - q: quit (exit menu)
    
    Args:
        fig: Matplotlib figure object
        ax: Primary axes (left Y-axis, shows capacity)
        ax2: Twin axes (right Y-axis, shows efficiency)
        sc_charge: Scatter plot artist for charge capacity (primary file)
        sc_discharge: Scatter plot artist for discharge capacity (primary file)
        sc_eff: Scatter plot artist for efficiency (primary file)
        file_data: Optional list of dictionaries, one per file:
            - 'filename': File name (for display)
            - 'sc_charge': Scatter artist for charge capacity
            - 'sc_discharge': Scatter artist for discharge capacity
            - 'sc_eff': Scatter artist for efficiency
            - 'visible': Whether file is currently visible
            - 'filepath': Path to source file (optional)
    """
    # ====================================================================
    # MULTI-FILE MODE SETUP
    # ====================================================================
    # CPC mode can handle multiple files simultaneously. Each file gets its
    # own set of scatter points (charge, discharge, efficiency) with its
    # own colors. This allows comparing multiple battery cells or conditions.
    #
    # If file_data is provided, we're in multi-file mode.
    # If not provided, we create a single-file structure for backward compatibility.
    # ====================================================================
    if file_data is None:
        # Backward compatibility: create file_data structure from single file
        # This allows the function to work with old code that passes individual artists
        # Try to get filename from label if available
        filename = 'Data'
        try:
            if hasattr(sc_charge, 'get_label') and sc_charge.get_label():
                label = sc_charge.get_label()
                # Extract filename from label like "filename (Chg)" or use label as-is
                if ' (Chg)' in label:
                    filename = label.replace(' (Chg)', '')
                elif ' (Dch)' in label:
                    filename = label.replace(' (Dch)', '')
                elif label and label != 'Charge capacity':
                    filename = label
        except Exception:
            pass
        file_data = [{
            'filename': filename,
            'sc_charge': sc_charge,      # Charge capacity scatter artist
            'sc_discharge': sc_discharge,  # Discharge capacity scatter artist
            'sc_eff': sc_eff,            # Efficiency scatter artist
            'visible': True               # File is visible by default
        }]
    # Track which file is currently selected for editing (in multi-file mode)
    current_file_idx = 0  # Index of currently selected file (0 = first file)
    
    # Collect file paths for session saving (if available)
    file_paths = _collect_file_paths(file_data)

    # Multi-file flag: now that file_data is finalized
    is_multi_file = file_data is not None and len(file_data) > 1
    try:
        fig._cpc_is_multi_file = bool(is_multi_file)
    except Exception:
        pass
    
    # ====================================================================
    # TICK STATE MANAGEMENT
    # ====================================================================
    # CPC plots have two axes (primary + twin), so we need to track tick
    # visibility for both. The tick_state dictionary tracks:
    #
    # Primary axes (ax):
    #   - bx: bottom x-axis ticks and labels
    #   - tx: top x-axis ticks and labels
    #   - ly: left y-axis ticks and labels (capacity)
    #   - mbx: minor bottom x-axis ticks
    #   - mtx: minor top x-axis ticks
    #   - mly: minor left y-axis ticks
    #
    # Twin axes (ax2):
    #   - ry: right y-axis ticks and labels (efficiency)
    #   - mry: minor right y-axis ticks
    #
    # Users can toggle these with 't' command to customize plot appearance.
    # ====================================================================
    tick_state = {
        'bx': True,   # bottom x-axis (cycle numbers) - shown by default
        'tx': False,  # top x-axis - hidden by default
        'ly': True,   # left y-axis (capacity) - shown by default
        'ry': True,   # right y-axis (efficiency) - shown by default
        'mbx': False, # minor bottom x-axis ticks - hidden by default
        'mtx': False, # minor top x-axis ticks - hidden by default
        'mly': False, # minor left y-axis ticks - hidden by default
        'mry': False, # minor right y-axis ticks - hidden by default
    }
    try:
        saved_wasd = getattr(fig, '_cpc_wasd_state', None)
        if isinstance(saved_wasd, dict) and saved_wasd:
            sync_tick_state_from_wasd(
                tick_state,
                saved_wasd,
                tick_defaults={'top': False, 'bottom': True, 'left': True, 'right': True},
                label_defaults={'top': False, 'bottom': True, 'left': True, 'right': True},
            )
            # Keep axis-level cache in sync so any save path persists the current state.
            try:
                ax._saved_tick_state = dict(tick_state)
            except Exception:
                pass
    except Exception:
        pass

    # --- Undo stack using style snapshots ---
    state_history = []  # list of cfg dicts

    if not hasattr(fig, '_cpc_spine_colors') or not isinstance(getattr(fig, '_cpc_spine_colors'), dict):
        fig._cpc_spine_colors = {}

    def _set_spine_color(spine_name: str, color):
        if not hasattr(fig, '_cpc_spine_colors') or not isinstance(fig._cpc_spine_colors, dict):
            fig._cpc_spine_colors = {}
        color = _normalize_spine_color(color)
        if color is None:
            return
        fig._cpc_spine_colors[spine_name] = color
        axes_map = {
            'top': [ax, ax2],
            'bottom': [ax, ax2],
            'left': [ax],
            'right': [ax2],
        }
        target_axes = axes_map.get(spine_name, [ax, ax2])
        for curr_ax in target_axes:
            if curr_ax is None or spine_name not in curr_ax.spines:
                continue
            try:
                _ui_set_spine_side_color(curr_ax, spine_name, color, fig=fig)
            except Exception:
                pass

    def push_state(note: str = ""):
        push_cpc_state(
            state_history,
            fig=fig,
            ax=ax,
            ax2=ax2,
            sc_charge=sc_charge,
            sc_discharge=sc_discharge,
            sc_eff=sc_eff,
            file_data=file_data,
            tick_state=tick_state,
            note=note,
        )

    def pop_undo() -> None:
        if state_history:
            state_history.pop()

    def restore_state():
        restore_cpc_state(
            state_history,
            fig=fig,
            ax=ax,
            ax2=ax2,
            sc_charge=sc_charge,
            sc_discharge=sc_discharge,
            sc_eff=sc_eff,
            file_data=file_data,
            tick_state=tick_state,
            update_ticks_func=_update_ticks,
        )

    def _update_ticks():
        try:
            # Apply shared visibility to primary ax; then adjust twin for right side
            _ui_update_tick_visibility(ax, tick_state)
            # Ensure left axis ticks/labels don't appear on right axis
            ax.tick_params(axis='y', right=False, labelright=False)
            # Right axis tick params follow r_* keys
            ax2.tick_params(axis='y',
                            right=tick_state.get('r_ticks', tick_state.get('ry', False)),
                            labelright=tick_state.get('r_labels', tick_state.get('ry', False)))
            # Minor right-y consistency
            if tick_state.get('mry'):
                ax2.yaxis.set_minor_locator(AutoMinorLocator()); ax2.yaxis.set_minor_formatter(NullFormatter())
                ax2.tick_params(axis='y', which='minor', right=True, labelright=False)
            else:
                ax2.tick_params(axis='y', which='minor', right=False, labelright=False)
            # Note: Do NOT call position functions during undo restore as it causes title drift
            # Title offsets are already restored from snapshot in restore_state()
            # Draw before re-applying spine colors so tick objects exist (even when right was hidden)
            try:
                fig.canvas.draw_idle()
            except Exception:
                pass
            try:
                finalize_spine_colors_cpc(
                    fig, ax, ax2,
                    tick_state=tick_state,
                    colors=getattr(fig, '_cpc_spine_colors', None),
                )
            except Exception:
                pass
            fig.canvas.draw_idle()
        except Exception:
            pass

    def _toggle_spine(code: str):
        # Map bl/tl/ll to ax; rl to ax2
        try:
            if code == 'bl':
                sp = ax.spines.get('bottom'); sp.set_visible(not sp.get_visible())
            elif code == 'tl':
                sp = ax.spines.get('top'); sp.set_visible(not sp.get_visible())
            elif code == 'll':
                sp = ax.spines.get('left'); sp.set_visible(not sp.get_visible())
            elif code == 'rl':
                sp = ax2.spines.get('right'); sp.set_visible(not sp.get_visible())
            fig.canvas.draw_idle()
        except Exception:
            pass

    def _sanitize_legend_offset(xy: object) -> Optional[tuple[float, float]]:
        if xy is None or not isinstance(xy, tuple) or len(xy) != 2:
            return None
        x_in, y_in = xy
        try:
            x_val = float(x_in)
            y_val = float(y_in)
        except Exception:
            return None
        fw, fh = fig.get_size_inches()
        if fw <= 0 or fh <= 0:
            return None
        max_offset = max(fw, fh) * 2.0
        if abs(x_val) > max_offset or abs(y_val) > max_offset:
            return None
        return (x_val, y_val)

    def _apply_legend_position():
        """Reapply legend position using stored inches offset. Uses _rebuild_legend so
        compact multi-file format (header row + per-file names) is preserved."""
        try:
            _rebuild_legend(ax, ax2, file_data, preserve_position=True)
        except Exception:
            pass

    # Ensure resize re-applies legend position in inches
    try:
        if not hasattr(fig, '_cpc_legpos_cid') or getattr(fig, '_cpc_legpos_cid') is None:
            def _on_resize(event):
                _apply_legend_position()
                try:
                    fig.canvas.draw_idle()
                except Exception:
                    pass
            fig._cpc_legpos_cid = fig.canvas.mpl_connect('resize_event', _on_resize)
    except Exception:
        pass

    # Crosshair state for CPC
    crosshair_cpc = {'active': False, 'hline': None, 'vline': None, 'text': None, 'cid_motion': None}
    register_crosshair(fig, crosshair_cpc)

    def _toggle_crosshair_cpc():
        if not crosshair_cpc['active']:
            vline = ax.axvline(x=ax.get_xlim()[0], color='0.35', ls='--', lw=0.8, alpha=0.85, zorder=9999)
            hline = ax.axhline(y=ax.get_ylim()[0], color='0.35', ls='--', lw=0.8, alpha=0.85, zorder=9999)
            txt = ax.text(1.0, 1.0, "", ha='right', va='bottom', transform=ax.transAxes,
                          fontsize=max(9, int(0.6 * plt.rcParams.get('font.size', 16))),
                          color='0.15', bbox=dict(boxstyle='round,pad=0.25', fc='white', ec='0.7', alpha=0.8))

            def on_move(event):
                if event.inaxes not in (ax, ax2):
                    return
                if event.x is None or event.y is None:
                    return
                try:
                    pt_ax = ax.transData.inverted().transform((event.x, event.y))
                    pt_ax2 = ax2.transData.inverted().transform((event.x, event.y))
                    cycle = pt_ax[0]
                    cap = pt_ax[1]
                    eff = pt_ax2[1]
                    vline.set_xdata([cycle, cycle])
                    hline.set_ydata([cap, cap])
                    txt.set_text(f"Cycle={cycle:.2g}\nCapacity={cap:.4g}\nEfficiency={eff:.2%}")
                except Exception:
                    if event.xdata is not None and event.ydata is not None:
                        vline.set_xdata([event.xdata, event.xdata])
                        hline.set_ydata([event.ydata, event.ydata])
                        txt.set_text(f"x={event.xdata:.4g}\ny={event.ydata:.4g}")
                fig.canvas.draw_idle()

            cid = fig.canvas.mpl_connect('motion_notify_event', on_move)
            crosshair_cpc.update({'active': True, 'hline': hline, 'vline': vline, 'text': txt, 'cid_motion': cid})
            print("Crosshair ON. Move mouse over axes. Press 'n' again to turn off.")
        else:
            if crosshair_cpc['cid_motion'] is not None:
                fig.canvas.mpl_disconnect(crosshair_cpc['cid_motion'])
            for k in ('hline', 'vline', 'text'):
                art = crosshair_cpc.get(k)
                if art is not None:
                    try:
                        art.remove()
                    except Exception:
                        pass
            crosshair_cpc.update({'active': False, 'hline': None, 'vline': None, 'text': None, 'cid_motion': None})
            fig.canvas.draw_idle()
            print("Crosshair OFF.")

    def _handle_key_t():
        assert sc_eff is not None
        # Unified WASD toggles for spines/ticks/minor/labels/title per side
        # Import UI positioning functions locally to ensure they're accessible in nested functions
        
        try:
            # Local WASD state stored on figure to persist across openings
            wasd = getattr(fig, '_cpc_wasd_state', None)
            if not isinstance(wasd, dict):
                wasd = {
                    'top':    {'spine': bool(ax.spines.get('top').get_visible()) if ax.spines.get('top') else False,
                               'ticks': bool(tick_state.get('t_ticks', tick_state.get('tx', False))),
                               'minor': bool(tick_state.get('mtx', False)),
                               'labels': bool(tick_state.get('t_labels', tick_state.get('tx', False))),
                               'title': bool(getattr(ax, '_top_xlabel_on', False))},
                    'bottom': {'spine': bool(ax.spines.get('bottom').get_visible()) if ax.spines.get('bottom') else True,
                               'ticks': bool(tick_state.get('b_ticks', tick_state.get('bx', True))),
                               'minor': bool(tick_state.get('mbx', False)),
                               'labels': bool(tick_state.get('b_labels', tick_state.get('bx', True))),
                               'title': bool(ax.get_xlabel())},
                    'left':   {'spine': bool(ax.spines.get('left').get_visible()) if ax.spines.get('left') else True,
                               'ticks': bool(tick_state.get('l_ticks', tick_state.get('ly', True))),
                               'minor': bool(tick_state.get('mly', False)),
                               'labels': bool(tick_state.get('l_labels', tick_state.get('ly', True))),
                               'title': bool(ax.get_ylabel())},
                    'right':  {'spine': bool(ax2.spines.get('right').get_visible()) if ax2.spines.get('right') else True,
                               'ticks': bool(tick_state.get('r_ticks', tick_state.get('ry', True))),
                               'minor': bool(tick_state.get('mry', False)),
                               'labels': bool(tick_state.get('r_labels', tick_state.get('ry', True))),
                               'title': bool(ax2.yaxis.get_label().get_text()) and bool(sc_eff.get_visible())},
                }
                setattr(fig, '_cpc_wasd_state', wasd)

            def _apply_wasd(changed_sides=None):
                assert sc_eff is not None
                # If no changed_sides specified, reposition all sides (for load style, etc.)
                if changed_sides is None:
                    changed_sides = {'bottom', 'top', 'left', 'right'}
                
                apply_wasd_spines(ax, wasd, sides=('top', 'bottom', 'left'))
                apply_wasd_spines(ax2, wasd, sides=('top', 'bottom', 'right'))
                apply_wasd_tick_params(ax, wasd, y_sides=('left',), y_mode='left')
                apply_wasd_tick_params(ax2, wasd, x_sides=(), y_sides=('right',), y_mode='right')

                # Titles
                try:
                    # Bottom X title
                    if bool(wasd['bottom']['title']):
                        # Restore stored xlabel if present
                        if hasattr(ax, '_stored_xlabel') and isinstance(ax._stored_xlabel, str) and ax._stored_xlabel:
                            ax.set_xlabel(ax._stored_xlabel)
                    else:
                        # Store once
                        if not hasattr(ax, '_stored_xlabel'):
                            try:
                                ax._stored_xlabel = ax.get_xlabel()
                            except Exception:
                                ax._stored_xlabel = ''
                        ax.set_xlabel("")
                except Exception:
                    pass
                try:
                    # Top X title - create a text artist positioned at the top
                    # First ensure we have the original xlabel text stored
                    if not hasattr(ax, '_stored_top_xlabel') or not ax._stored_top_xlabel:
                        # Try to get from current xlabel first
                        current_xlabel = ax.get_xlabel()
                        if current_xlabel:
                            ax._stored_top_xlabel = current_xlabel
                        # If still empty, try from stored bottom xlabel
                        elif hasattr(ax, '_stored_xlabel') and ax._stored_xlabel:
                            ax._stored_top_xlabel = ax._stored_xlabel
                        else:
                            ax._stored_top_xlabel = ''
                    
                    if bool(wasd['top']['title']) and ax._stored_top_xlabel:
                        # Get or create the top xlabel artist
                        if not hasattr(ax, '_top_xlabel_text') or ax._top_xlabel_text is None:
                            # Create a new text artist at the top center
                            ax._top_xlabel_text = ax.text(0.5, 1.0, '', transform=ax.transAxes,
                                                          ha='center', va='bottom',
                                                          fontsize=ax.xaxis.label.get_fontsize(),
                                                          fontfamily=ax.xaxis.label.get_fontfamily())
                        # Update text and make visible
                        ax._top_xlabel_text.set_text(ax._stored_top_xlabel)
                        ax._top_xlabel_text.set_visible(True)
                        
                        # Dynamic positioning based on top tick labels visibility
                        # Only reposition top if it's in changed_sides
                        if 'top' in changed_sides:
                            try:
                                # Get renderer for measurements
                                renderer = fig.canvas.get_renderer()
                                
                                # Base padding
                                labelpad = ax.xaxis.labelpad if hasattr(ax.xaxis, 'labelpad') else 4.0
                                fig_h = fig.get_size_inches()[1]
                                ax_bbox = ax.get_position()
                                ax_h_inches = ax_bbox.height * fig_h
                                base_pad_axes = (labelpad / 72.0) / ax_h_inches if ax_h_inches > 0 else 0.02
                                
                                # If top tick labels are visible, measure their height and add spacing
                                extra_offset = 0.0
                                if bool(wasd['top']['labels']) and renderer is not None:
                                    try:
                                        max_h_px = 0.0
                                        for t in ax.xaxis.get_major_ticks():
                                            lab = getattr(t, 'label2', None)  # Top labels are label2
                                            if lab is not None and lab.get_visible():
                                                bb = lab.get_window_extent(renderer=renderer)
                                                if bb is not None:
                                                    max_h_px = max(max_h_px, float(bb.height))
                                        # Convert pixels to axes coordinates
                                        if max_h_px > 0 and ax_h_inches > 0:
                                            dpi = float(fig.dpi) if hasattr(fig, 'dpi') else 100.0
                                            max_h_inches = max_h_px / dpi
                                            extra_offset = max_h_inches / ax_h_inches
                                    except Exception:
                                        # Fallback to fixed offset if labels are on
                                        extra_offset = 0.05
                                
                                total_offset = 1.0 + base_pad_axes + extra_offset
                                ax._top_xlabel_text.set_position((0.5, total_offset))
                            except Exception:
                                # Fallback positioning
                                if bool(wasd['top']['labels']):
                                    ax._top_xlabel_text.set_position((0.5, 1.07))
                                else:
                                    ax._top_xlabel_text.set_position((0.5, 1.02))
                    else:
                        # Hide top label
                        if hasattr(ax, '_top_xlabel_text') and ax._top_xlabel_text is not None:
                            ax._top_xlabel_text.set_visible(False)
                except Exception:
                    pass
                try:
                    # Left Y title
                    if bool(wasd['left']['title']):
                        if hasattr(ax, '_stored_ylabel') and isinstance(ax._stored_ylabel, str) and ax._stored_ylabel:
                            ax.set_ylabel(ax._stored_ylabel)
                    else:
                        if not hasattr(ax, '_stored_ylabel'):
                            try:
                                ax._stored_ylabel = ax.get_ylabel()
                            except Exception:
                                ax._stored_ylabel = ''
                        ax.set_ylabel("")
                except Exception:
                    pass
                try:
                    # Right Y title - simple approach like left/bottom
                    if bool(wasd['right']['title']) and bool(sc_eff.get_visible()):
                        if hasattr(ax2, '_stored_ylabel') and isinstance(ax2._stored_ylabel, str) and ax2._stored_ylabel:
                            ax2.set_ylabel(ax2._stored_ylabel)
                    else:
                        if not hasattr(ax2, '_stored_ylabel'):
                            try:
                                ax2._stored_ylabel = ax2.get_ylabel()
                            except Exception:
                                ax2._stored_ylabel = ''
                        ax2.set_ylabel("")
                except Exception:
                    pass
                
                # Only reposition sides that were actually changed
                # This prevents unnecessary title movement when toggling unrelated elements
                apply_changed_side_title_positions(
                    changed_sides,
                    bottom=lambda: _ui_position_bottom_xlabel(ax, fig, tick_state),
                    left=lambda: _ui_position_left_ylabel(ax, fig, tick_state),
                )
                try:
                    finalize_spine_colors_cpc(fig, ax, ax2, tick_state=tick_state)
                except Exception:
                    pass

            def _print_wasd():
                _Cw = '\033[96m'; _Rw = '\033[0m'
                def b(v):
                    return 'ON ' if bool(v) else 'off'
                print(f"\033[1mToggle spines state:\033[0m")
                print(f"  {'Side':<8}  spine  major  minor  labels title")
                for side_key, side_code in [('top','w'),('bottom','s'),('left','a'),('right','d')]:
                    s = wasd[side_key]
                    print(f"  {_Cw}{side_code}={side_key:<6}{_Rw} {b(s['spine'])}  {b(s['ticks'])}   {b(s['minor'])}   {b(s['labels'])}  {b(s['title'])}")
                # Tick direction
                tick_dir = getattr(fig, '_tick_direction', 'out')
                print(f"  Tick direction  : {_Cw}{tick_dir}{_Rw}")
                # Tick lengths
                tl = getattr(fig, '_tick_lengths', {}) or {}
                maj_l = tl.get('major')
                min_l = tl.get('minor')
                if maj_l is not None:
                    min_str = f"  minor={min_l:.2g}" if min_l is not None else ""
                    print(f"  Tick length     : {_Cw}major={maj_l:.2g}{_Rw}{min_str}")
                else:
                    print(f"  Tick length     : default")
                # Tick spacing
                def _sp(loc):
                    try:
                        if isinstance(loc, MultipleLocator):
                            return str(loc._edge.step)
                        return "auto"
                    except Exception:
                        return "auto"
                def _mn(loc):
                    try:
                        if isinstance(loc, AutoMinorLocator):
                            return f"{loc._ndivs-1}/interval"
                        if isinstance(loc, NullLocator):
                            return "off"
                        return "auto"
                    except Exception:
                        return "auto"
                print(f"  Tick spacing    : {_Cw}x{_Rw}={_sp(ax.xaxis.get_major_locator())}  {_Cw}y{_Rw}={_sp(ax.yaxis.get_major_locator())}  {_Cw}r{_Rw}={_sp(ax2.yaxis.get_major_locator())}")
                print(f"  Minor count     : {_Cw}x{_Rw}={_mn(ax.xaxis.get_minor_locator())}  {_Cw}y{_Rw}={_mn(ax.yaxis.get_minor_locator())}  {_Cw}r{_Rw}={_mn(ax2.yaxis.get_minor_locator())}")

            def _sync_cpc_tick_state():
                sync_tick_state_from_wasd(
                    tick_state,
                    wasd,
                    tick_defaults={'top': False, 'bottom': True, 'left': True, 'right': True},
                    label_defaults={'top': False, 'bottom': True, 'left': True, 'right': True},
                )
                try:
                    ax._saved_tick_state = dict(tick_state)
                except Exception:
                    pass
            def _draw_cpc_spine_menu():
                try:
                    finalize_spine_colors_cpc(fig, ax, ax2, tick_state=tick_state)
                except Exception:
                    pass
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
                push_state=push_state,
                sync_tick_state=_sync_cpc_tick_state,
                apply_wasd=_apply_wasd,
                draw=_draw_cpc_spine_menu,
                mode_label="CPC axes",
                back_label="CPC menu",
                axis_map={'x': ax.xaxis, 'y': ax.yaxis, 'r': ax2.yaxis},
                direction_axes=[ax, ax2],
                length_axes=[ax, ax2],
                on_quit=lambda: setattr(ax, '_saved_tick_state', dict(tick_state)),
                print_state=_print_wasd,
            )
            _print_menu(fig); return
        except Exception as e:
            print(f"Error in WASD tick menu: {e}")
        _print_menu(fig); return

    _print_menu(fig)
    pending_key = None
    while True:
        try:
            # Update current file's scatter artists for commands that need them
            sc_charge, sc_discharge, sc_eff = _get_current_file_artists(file_data, current_file_idx)
            assert sc_charge is not None
            assert sc_discharge is not None
            assert sc_eff is not None
            
            if pending_key is not None:
                key = pending_key
                pending_key = None
            else:
                key = prompt_menu_key()
        except (KeyboardInterrupt, EOFError):
            print("\n\nExiting interactive menu...")
            break
        if not key:
            continue

        action_ctx = CpcActionContext(
            fig=fig,
            ax=ax,
            ax2=ax2,
            sc_charge=sc_charge,
            sc_discharge=sc_discharge,
            sc_eff=sc_eff,
            file_data=file_data,
            file_paths=file_paths,
            is_multi_file=is_multi_file,
            tick_state=tick_state,
            safe_input=_safe_input,
            colorize_prompt=_colorize_prompt,
            colorize_inline_commands=_colorize_inline_commands,
            print_menu=_print_menu,
            choose_save_path=choose_save_path,
            choose_style_file=choose_style_file,
            list_files_in_subdirectory=list_files_in_subdirectory,
            get_organized_path=get_organized_path,
            ensure_exact_case_filename=ensure_exact_case_filename,
            natural_sort_key=natural_sort_key,
            dump_cpc_session=dump_cpc_session,
            format_file_timestamp=_format_file_timestamp,
            rebuild_legend=_rebuild_legend,
            style_snapshot=_style_snapshot,
            apply_style=_apply_style,
            get_geometry_snapshot=_get_geometry_snapshot,
            push_state=push_state,
            pop_undo=pop_undo,
            restore_state=restore_state,
        )
        
        if key == 'n':
            try:
                _toggle_crosshair_cpc()
            except Exception as e:
                print(f"Error toggling crosshair: {e}")
            _print_menu(fig)
            continue
        # File visibility toggle command (v)
        if key == 'v':
            try:
                if is_multi_file:
                    while True:
                        _print_file_list(file_data, current_file_idx)
                        print("  " + _colorize_menu("1, 1 2 3, 1-4: toggle file(s)"))
                        print("  " + _colorize_menu("a: toggle all"))
                        print("  " + _colorize_menu("q: back"))
                        choice = _safe_input(
                            _colorize_prompt(f"Select file numbers (1-{len(file_data)}), a=all, q=back: ")
                        ).strip()
                        if not choice or choice.lower() == 'q':
                            break

                        indices_to_toggle = []
                        if choice.lower() in ('a', 'all'):
                            indices_to_toggle = list(range(len(file_data)))
                        else:
                            parts = choice.replace(',', ' ').split()
                            for p in parts:
                                p = p.strip()
                                if not p:
                                    continue
                                if '-' in p and p.count('-') == 1:
                                    try:
                                        lo, hi = p.split('-')
                                        lo_i = int(lo.strip()) - 1
                                        hi_i = int(hi.strip()) - 1
                                        for i in range(lo_i, hi_i + 1):
                                            if 0 <= i < len(file_data):
                                                indices_to_toggle.append(i)
                                    except ValueError:
                                        pass
                                else:
                                    try:
                                        idx = int(p) - 1
                                        if 0 <= idx < len(file_data):
                                            indices_to_toggle.append(idx)
                                    except ValueError:
                                        pass
                            indices_to_toggle = sorted(set(indices_to_toggle))

                        if indices_to_toggle:
                            push_state("visibility")
                            for idx in indices_to_toggle:
                                f = file_data[idx]
                                new_vis = not f.get('visible', True)
                                f['visible'] = new_vis
                                f['sc_charge'].set_visible(new_vis)
                                f['sc_discharge'].set_visible(new_vis)
                                f['sc_eff'].set_visible(new_vis)
                            _rebuild_legend(ax, ax2, file_data, preserve_position=True)
                            fig.canvas.draw_idle()
                            names = [file_data[i].get('filename', f'File {i+1}') for i in indices_to_toggle]
                            print(f"Toggled: {', '.join(names)}")
                        else:
                            print("Invalid input. Use: 1, 1 2 3, 1-4, a, or q.")
                else:
                    print("File visibility (v) is only available in multi-file CPC mode.")
            except ValueError:
                print("Invalid input. Use: 1, 1 2 3, 1-4, a, or q.")
            except Exception as e:
                print(f"Visibility toggle failed: {e}")
            _print_menu(fig)
            if is_multi_file:
                _print_file_list(file_data, current_file_idx)
            continue
        
        if key == 'q':
            if canvas_mode:
                break
            try:
                confirm = _safe_input(_colorize_prompt("Quit CPC interactive? Remember to save (e=export, s=save). Quit now? (y/n): ")).strip().lower()
            except Exception:
                confirm = 'y'
            if confirm == 'y':
                break
            elif confirm in ('e', 's'):
                pending_key = confirm
                continue
            else:
                _print_menu(fig); continue
        elif key == 'b':
            handle_undo(action_ctx)
            continue
        elif key == 'c':
            try:
                run_cpc_color_menu(
                    fig=fig,
                    ax=ax,
                    ax2=ax2,
                    file_data=file_data,
                    is_multi_file=is_multi_file,
                    sc_charge=sc_charge,
                    sc_eff=sc_eff,
                    push_state=push_state,
                    set_spine_color=_set_spine_color,
                    rebuild_legend=_rebuild_legend,
                    safe_input=_safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=_colorize_prompt,
                )
            except Exception as e:
                print(f"Error in colors menu: {e}")
            _print_menu(fig)
            if is_multi_file:
                _print_file_list(file_data, current_file_idx)
            continue
        elif key == 'k':
            # Spine colors (w=top, a=left, s=bottom, d=right)
            try:
                while True:
                    print("\nSet spine colors (with matching tick and label colors):")
                    print(_colorize_inline_commands("  w : top spine    | a : left spine"))
                    print(_colorize_inline_commands("  s : bottom spine | d : right spine"))
                    print(_colorize_inline_commands("Example: w:red a:#4561F7 s:blue d:green"))
                    # Add auto function when only one file is loaded
                    if not is_multi_file:
                        auto_enabled = getattr(fig, '_cpc_spine_auto', False)
                        auto_status = "ON" if auto_enabled else "OFF"
                        print(_colorize_inline_commands(f"  auto : auto-apply capacity color to left y-axis, efficiency to right y-axis [{auto_status}]"))
                    print("  " + _colorize_menu("q: back to main menu"))
                    line = _safe_input(_colorize_prompt("Enter mappings (e.g., w:red a:#4561F7, q=back): ")).strip()
                    if not line or line.lower() == 'q':
                        break
                    # Handle auto toggle when only one file is loaded
                    if not is_multi_file and line.lower() in ('a', 'auto'):
                        auto_enabled = getattr(fig, '_cpc_spine_auto', False)
                        if auto_enabled:
                            # Turning OFF: push current (auto ON) state first so undo restores it
                            push_state("color-spine-auto")
                        fig._cpc_spine_auto = not auto_enabled
                        new_status = "ON" if fig._cpc_spine_auto else "OFF"
                        print(f"Auto mode: {new_status}")
                        if fig._cpc_spine_auto:
                            # Turning ON: push state, then apply auto colors
                            push_state("color-spine-auto")
                            try:
                                # Draw first so tick objects exist (even when right axis was hidden)
                                fig.canvas.draw_idle()
                                # Get capacity curve color (charge color)
                                charge_col = _normalize_spine_color(_color_of(sc_charge))
                                # Get efficiency curve color
                                eff_col = _normalize_spine_color(_color_of(sc_eff))
                                if charge_col and eff_col:
                                    _set_spine_color('left', charge_col)
                                    _set_spine_color('right', eff_col)
                                    print(f"Applied: left y-axis = {charge_col}, right y-axis = {eff_col}")
                                else:
                                    print("Could not get charge/efficiency colors from artists.")
                                fig.canvas.draw()
                            except Exception as e:
                                print(f"Error applying auto colors: {e}")
                        continue
                    push_state("color-spine")
                    # Draw first so tick objects exist (even when right axis was hidden)
                    try:
                        fig.canvas.draw_idle()
                    except Exception:
                        pass
                    # Map wasd to spine names
                    key_to_spine = {'w': 'top', 'a': 'left', 's': 'bottom', 'd': 'right'}
                    tokens = line.split()
                    manual_change_made = False
                    for token in tokens:
                        if ':' not in token:
                            # Skip auto keyword silently (handled above)
                            if token.lower() not in ('a', 'auto'):
                                print(f"Skip malformed token: {token}")
                            continue
                        key_part, color = token.split(':', 1)
                        key_part = key_part.lower()
                        if key_part not in key_to_spine:
                            print(f"Unknown key: {key_part} (use w/a/s/d)")
                            continue
                        spine_name = key_to_spine[key_part]
                        resolved = resolve_color_token(color, fig)
                        _set_spine_color(spine_name, resolved)
                        print(f"Set {spine_name} spine to {resolved}")
                        manual_change_made = True
                    # Disable auto mode if manual changes were made
                    if manual_change_made and not is_multi_file and getattr(fig, '_cpc_spine_auto', False):
                        fig._cpc_spine_auto = False
                        print("Auto mode disabled (manual spine color set)")
                    fig.canvas.draw()
            except Exception as e:
                print(f"Error in spine color menu: {e}")
            _print_menu(fig)
            if is_multi_file:
                _print_file_list(file_data, current_file_idx)
            continue
        elif key == 'e':
            handle_figure_export(action_ctx)
            continue
        elif key == 's':
            handle_save_session(action_ctx)
            continue
        elif key == 'p':
            handle_style_export(action_ctx)
            continue
        elif key == 'i':
            handle_style_import(action_ctx)
            continue
        elif key == 'd':
            # Display mode: charge-only / discharge-only / both
            try:
                while True:
                    print("\nDisplay mode for CPC:")
                    print("  " + _colorize_menu("c: show only charge capacity (hide discharge)"))
                    print("  " + _colorize_menu("d: show only discharge capacity (hide charge)"))
                    print("  " + _colorize_menu("b: show both charge and discharge"))
                    print("  " + _colorize_menu("q: back"))
                    sub = _safe_input(_colorize_prompt("Display (c/d/b/q): ")).strip().lower()
                    if not sub or sub == 'q':
                        break
                    if sub == 'c':
                        push_state("display-charge")
                        for f in file_data:
                            sc_c = f.get('sc_charge')
                            sc_d = f.get('sc_discharge')
                            if sc_c is not None:
                                sc_c.set_visible(True)
                            if sc_d is not None:
                                sc_d.set_visible(False)
                        try:
                            fig._cpc_display_mode = "charge"
                        except Exception:
                            pass
                    elif sub == 'd':
                        push_state("display-discharge")
                        for f in file_data:
                            sc_c = f.get('sc_charge')
                            sc_d = f.get('sc_discharge')
                            if sc_c is not None:
                                sc_c.set_visible(False)
                            if sc_d is not None:
                                sc_d.set_visible(True)
                        try:
                            fig._cpc_display_mode = "discharge"
                        except Exception:
                            pass
                    elif sub == 'b':
                        push_state("display-both")
                        for f in file_data:
                            sc_c = f.get('sc_charge')
                            sc_d = f.get('sc_discharge')
                            if sc_c is not None:
                                sc_c.set_visible(True)
                            if sc_d is not None:
                                sc_d.set_visible(True)
                        try:
                            fig._cpc_display_mode = "both"
                        except Exception:
                            pass
                    else:
                        print("Unknown choice (use c, d, b, or q).")
                    _rebuild_legend(ax, ax2, file_data, preserve_position=True)
                    fig.canvas.draw_idle()
            except Exception as e:
                print(f"Display mode change failed: {e}")
            _print_menu(fig)
            if is_multi_file:
                _print_file_list(file_data, current_file_idx)
            continue
        elif key == 'ry':
            while True:
                print("  " + _colorize_menu("t: toggle efficiency axis visibility"))
                print("  " + _colorize_menu("q: back"))
                sub = _safe_input(_colorize_prompt("Efficiency axis (t/q): ")).strip().lower()
                if not sub or sub == 'q':
                    break
                if sub != 't':
                    print("Unknown option.")
                    continue
                try:
                    push_state("toggle-eff")

                    # Capture current legend position BEFORE toggling visibility
                    try:
                        if not hasattr(fig, '_cpc_legend_xy_in') or getattr(fig, '_cpc_legend_xy_in') is None:
                            leg0 = ax.get_legend()
                            if leg0 is not None and leg0.get_visible():
                                try:
                                    try:
                                        renderer = fig.canvas.get_renderer()
                                    except Exception:
                                        fig.canvas.draw()
                                        renderer = fig.canvas.get_renderer()
                                    bb = leg0.get_window_extent(renderer=renderer)
                                    cx = 0.5 * (bb.x0 + bb.x1)
                                    cy = 0.5 * (bb.y0 + bb.y1)
                                    fx, fy = fig.transFigure.inverted().transform((cx, cy))
                                    fw, fh = fig.get_size_inches()
                                    offset = ((fx - 0.5) * fw, (fy - 0.5) * fh)
                                    offset = _sanitize_legend_offset(offset)
                                    if offset is not None:
                                        fig._cpc_legend_xy_in = offset
                                except Exception:
                                    pass
                    except Exception:
                        pass

                    if is_multi_file:
                        any_eff_visible = any(
                            f.get('sc_eff', {}).get_visible()
                            if hasattr(f.get('sc_eff'), 'get_visible') else True
                            for f in file_data if f.get('sc_eff')
                        )
                        new_vis = not any_eff_visible
                    else:
                        vis = bool(sc_eff.get_visible()) if hasattr(sc_eff, 'get_visible') else True
                        new_vis = not vis

                    if is_multi_file:
                        for f in file_data:
                            eff_sc = f.get('sc_eff')
                            if eff_sc is not None:
                                try:
                                    eff_sc.set_visible(new_vis)
                                except Exception:
                                    pass
                    else:
                        sc_eff.set_visible(new_vis)

                    try:
                        ax2.yaxis.label.set_visible(new_vis)
                    except Exception:
                        pass

                    try:
                        ax2.tick_params(axis='y', right=new_vis, labelright=new_vis)
                        tick_state['ry'] = bool(new_vis)
                    except Exception:
                        pass

                    try:
                        wasd = getattr(fig, '_cpc_wasd_state', None)
                        if not isinstance(wasd, dict):
                            wasd = {
                                'top': {'spine': bool(ax.spines.get('top').get_visible()) if ax.spines.get('top') else False,
                                        'ticks': bool(tick_state.get('t_ticks', tick_state.get('tx', False))),
                                        'minor': bool(tick_state.get('mtx', False)),
                                        'labels': bool(tick_state.get('t_labels', tick_state.get('tx', False))),
                                        'title': bool(getattr(ax, '_top_xlabel_on', False))},
                                'bottom': {'spine': bool(ax.spines.get('bottom').get_visible()) if ax.spines.get('bottom') else True,
                                           'ticks': bool(tick_state.get('b_ticks', tick_state.get('bx', True))),
                                           'minor': bool(tick_state.get('mbx', False)),
                                           'labels': bool(tick_state.get('b_labels', tick_state.get('bx', True))),
                                           'title': bool(ax.xaxis.label.get_visible()) and bool(ax.get_xlabel())},
                                'left': {'spine': bool(ax.spines.get('left').get_visible()) if ax.spines.get('left') else True,
                                         'ticks': bool(tick_state.get('l_ticks', tick_state.get('ly', True))),
                                         'minor': bool(tick_state.get('mly', False)),
                                         'labels': bool(tick_state.get('l_labels', tick_state.get('ly', True))),
                                         'title': bool(ax.yaxis.label.get_visible()) and bool(ax.get_ylabel())},
                                'right': {'spine': bool(ax2.spines.get('right').get_visible()) if ax.spines.get('right') else True,
                                          'ticks': bool(tick_state.get('r_ticks', tick_state.get('ry', True))),
                                          'minor': bool(tick_state.get('mry', False)),
                                          'labels': bool(tick_state.get('r_labels', tick_state.get('ry', True))),
                                          'title': bool(ax2.yaxis.label.get_visible()) and bool(ax2.get_ylabel())},
                            }
                        wasd.setdefault('right', {})
                        wasd['right']['ticks'] = bool(new_vis)
                        wasd['right']['labels'] = bool(new_vis)
                        wasd['right']['title'] = bool(new_vis)
                        setattr(fig, '_cpc_wasd_state', wasd)
                    except Exception:
                        pass

                    _rebuild_legend(ax, ax2, file_data, preserve_position=True)
                    fig.canvas.draw_idle()
                except Exception:
                    pass
            _print_menu(fig); continue
        elif key == 'h':
            # Legend submenu: toggle visibility and move legend in inches relative to canvas center.
            try:

                def _cpc_toggle_legend():
                    try:
                        leg = ax.get_legend()
                        if leg is not None and leg.get_visible():
                            leg.set_visible(False)
                        else:
                            handles, _labels = _visible_handles_labels(ax, ax2)
                            if handles:
                                _rebuild_legend(ax, ax2, file_data, preserve_position=True)
                            else:
                                print("No visible legend items found.")
                        fig.canvas.draw_idle()
                    except Exception as e:
                        print(f"Error toggling legend: {e}")
                        traceback.print_exc()

                def _cpc_apply_legend_pos():
                    _apply_legend_position()
                    fig.canvas.draw_idle()

                run_legend_position_menu(
                    fig=fig,
                    get_legend=ax.get_legend,
                    get_position=lambda: getattr(fig, '_cpc_legend_xy_in', (0.0, 0.0)),
                    set_position=lambda xy: setattr(fig, '_cpc_legend_xy_in', xy),
                    sanitize_offset=_sanitize_legend_offset,
                    toggle_legend=_cpc_toggle_legend,
                    apply_position=_cpc_apply_legend_pos,
                    push_state=push_state,
                    safe_input=_safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=_colorize_prompt,
                )
            except Exception:
                pass
            _print_menu(fig); continue
        elif key == 'f':
            def _cpc_font_artists_local():
                return _cpc_font_artists(ax, ax2, fig)
            def _apply_cpc_font_family(fam):
                push_state("font-family")
                set_font_family_defaults(fam, sans_serif_stack=True)
                apply_font_family_to_artists(_cpc_font_artists_local(), fam)
                fig.canvas.draw_idle()
            def _apply_cpc_font_size(size):
                push_state("font-size")
                set_font_size_default(size)
                apply_font_size_to_artists(_cpc_font_artists_local(), size)
                fig.canvas.draw_idle()
            def _apply_cpc_font_weight(weight):
                push_state("font-weight")
                apply_fig_font_weight(fig, _cpc_font_artists_local(), weight)
                fig.canvas.draw_idle()
            def _toggle_cpc_highlight():
                push_state("font-highlight")
                apply_fig_text_highlight(fig, _cpc_font_artists_local(), not get_fig_text_highlight(fig))
                fig.canvas.draw_idle()
            def _set_cpc_hl_fc(fc):
                push_state("font-highlight")
                apply_fig_text_highlight(fig, _cpc_font_artists_local(), get_fig_text_highlight(fig), fc=fc)
                fig.canvas.draw_idle()
            def _set_cpc_hl_alpha(alpha):
                push_state("font-highlight")
                apply_fig_text_highlight(fig, _cpc_font_artists_local(), get_fig_text_highlight(fig), alpha=alpha)
                fig.canvas.draw_idle()
            def _set_cpc_hl_pad(pad):
                push_state("font-highlight")
                apply_fig_text_highlight(fig, _cpc_font_artists_local(), get_fig_text_highlight(fig), pad=pad)
                fig.canvas.draw_idle()
            run_font_menu(
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
                get_current_family=lambda: plt.rcParams.get('font.sans-serif', [''])[0],
                get_current_size=lambda: plt.rcParams.get('font.size', None),
                apply_family=_apply_cpc_font_family,
                apply_size=_apply_cpc_font_size,
                get_current_weight=lambda: get_fig_font_weight(fig),
                apply_weight=_apply_cpc_font_weight,
                get_current_highlight=lambda: get_fig_text_highlight(fig),
                get_highlight_style=lambda: get_fig_text_highlight_style(fig),
                apply_highlight_toggle=_toggle_cpc_highlight,
                apply_highlight_facecolor=_set_cpc_hl_fc,
                apply_highlight_alpha=_set_cpc_hl_alpha,
                apply_highlight_pad=_set_cpc_hl_pad,
                blank_exits=True,
            )
            _print_menu(fig); continue
        elif key == 'l':
            # Line widths submenu: frame/ticks vs grid
            try:
                while True:
                    # Show current widths summary
                    try:
                        cur_sp_lw = {name: (ax.spines.get(name).get_linewidth() if ax.spines.get(name) else None)
                                      for name in ('bottom','top','left','right')}
                    except Exception:
                        cur_sp_lw = {}
                    x_maj = current_tick_width(ax.xaxis, 'major')
                    x_min = current_tick_width(ax.xaxis, 'minor')
                    ly_maj = current_tick_width(ax.yaxis, 'major')
                    ly_min = current_tick_width(ax.yaxis, 'minor')
                    ry_maj = current_tick_width(ax2.yaxis, 'major')
                    ry_min = current_tick_width(ax2.yaxis, 'minor')
                    print("Line widths:")
                    if cur_sp_lw:
                        print("  Frame spines lw:", 
                              " ".join(f"{k}={v:.3g}" if isinstance(v,(int,float)) else f"{k}=?" for k,v in cur_sp_lw.items()))
                    print(f"  Tick widths: xM={x_maj if x_maj is not None else '?'} xm={x_min if x_min is not None else '?'} lyM={ly_maj if ly_maj is not None else '?'} lym={ly_min if ly_min is not None else '?'} ryM={ry_maj if ry_maj is not None else '?'} rym={ry_min if ry_min is not None else '?'}")
                    print("\033[1mLine submenu:\033[0m")
                    print(f"  {_colorize_menu('f  : change frame (axes spines) and tick widths')}")
                    print(f"  {_colorize_menu('g  : toggle grid lines')}")
                    print(f"  {_colorize_menu('q  : return')}")
                    sub = _safe_input(_colorize_prompt("Choose (f/g/q): ")).strip().lower()
                    if not sub:
                        continue
                    if sub == 'q':
                        break
                    if sub == 'f':
                        while True:
                            fw_in = _safe_input("Enter frame/tick width (e.g., 1.5) or 'm M' (major minor) or q=back: ").strip()
                            if not fw_in or fw_in.lower() == 'q':
                                break
                            try:
                                push_state("framewidth")
                                frame_w, tick_major, tick_minor = parse_frame_tick_widths(fw_in)
                                apply_frame_and_tick_widths(
                                    [ax, ax2],
                                    frame_width=frame_w,
                                    major_width=tick_major,
                                    minor_width=tick_minor,
                                )
                                fig.canvas.draw()
                                print(f"Set frame width={frame_w}, major tick width={tick_major}, minor tick width={tick_minor}")
                            except ValueError:
                                print("Invalid numeric value(s).")
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
                            # Disable grid
                            ax.grid(False)
                        fig.canvas.draw()
                        print(f"Grid {'enabled' if new_grid_state else 'disabled'}.")
                    else:
                        print("Unknown option.")
            except Exception as e:
                print(f"Error in line submenu: {e}")
            _print_menu(fig); continue
        elif key == 'm':
            try:
                while True:
                    print("Current marker sizes:")
                    try:
                        c_ms = getattr(sc_charge, 'get_sizes', lambda: [32])()[0]
                    except Exception:
                        c_ms = 32
                    try:
                        d_ms = getattr(sc_discharge, 'get_sizes', lambda: [32])()[0]
                    except Exception:
                        d_ms = 32
                    try:
                        e_ms = getattr(sc_eff, 'get_sizes', lambda: [40])()[0]
                    except Exception:
                        e_ms = 40
                    print(f"  charge ms={c_ms}, discharge ms={d_ms}, efficiency ms={e_ms}")
                    spec = _safe_input("Set new marker size for all series (q=back): ").strip().lower()
                    if not spec or spec == 'q':
                        break
                    try:
                        num = float(spec)
                        push_state("marker-size")
                        # Apply to current file's artists
                        if hasattr(sc_charge, 'set_sizes'):
                            sc_charge.set_sizes([num])
                        if hasattr(sc_discharge, 'set_sizes'):
                            sc_discharge.set_sizes([num])
                        if hasattr(sc_eff, 'set_sizes'):
                            sc_eff.set_sizes([num])
                        # In multi-file mode, also apply to all files' capacity/efficiency
                        if is_multi_file and file_data:
                            for f in file_data:
                                ch = f.get('sc_charge')
                                dh = f.get('sc_discharge')
                                ef = f.get('sc_eff')
                                try:
                                    if ch is not None and hasattr(ch, 'set_sizes'):
                                        ch.set_sizes([num])
                                except Exception:
                                    pass
                                try:
                                    if dh is not None and hasattr(dh, 'set_sizes'):
                                        dh.set_sizes([num])
                                except Exception:
                                    pass
                                try:
                                    if ef is not None and hasattr(ef, 'set_sizes'):
                                        ef.set_sizes([num])
                                except Exception:
                                    pass
                        fig.canvas.draw_idle()
                    except Exception:
                        print("Invalid value.")
            except Exception as e:
                print(f"Error: {e}")
            _print_menu(fig); continue
        elif key == 't':
            _handle_key_t()
            continue
        elif key == 'g':
            def _resize_cpc_frame():
                try:
                    push_state("resize-frame")
                    resize_plot_frame(fig, ax, [], [], type('Args', (), {'stack': False})(), lambda *_: None)
                except Exception as e:
                    print(f"Resize failed: {e}")
            def _resize_cpc_canvas():
                try:
                    push_state("resize-canvas")
                    resize_canvas(fig, ax)
                except Exception as e:
                    print(f"Resize failed: {e}")
            run_option_menu(
                prompt="Geom (p/c/q): ",
                options={
                    "p": ("plot frame", _resize_cpc_frame),
                    "c": ("canvas", _resize_cpc_canvas),
                },
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
            )
            _print_menu(fig); continue
        elif key == 'r':
            run_cpc_rename_menu(
                fig=fig,
                ax=ax,
                ax2=ax2,
                file_data=file_data,
                current_file_idx=current_file_idx,
                is_multi_file=is_multi_file,
                push_state=push_state,
                rebuild_legend=_rebuild_legend,
                print_file_list=_print_file_list,
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
            )
            _print_menu(fig); continue
        elif key == 'x':
            def _draw_cpc_x_range():
                try:
                    ax.relim()
                    ax.autoscale_view(scalex=True, scaley=False)
                except Exception:
                    pass
                try:
                    leg = ax.get_legend()
                    if leg is not None and leg.get_visible():
                        _apply_legend_position()
                except Exception:
                    pass
                fig.canvas.draw_idle()
            def _auto_cpc_x_range():
                try:
                    all_x = []
                    for sc in [sc_charge, sc_discharge]:
                        if sc is not None and hasattr(sc, 'get_offsets'):
                            offsets = sc.get_offsets()
                            if offsets.size > 0:
                                all_x.extend([offsets[:, 0].min(), offsets[:, 0].max()])
                    if all_x:
                        ax.set_xlim(min(all_x), max(all_x))
                    else:
                        print("No original data available.")
                except Exception as e:
                    print(f"Error restoring original X range: {e}")
            run_axis_limit_menu(
                axis_name="X",
                prompt_name="X",
                get_limits=ax.get_xlim,
                set_limits=lambda lo, hi: ax.set_xlim(lo, hi),
                auto_limits=_auto_cpc_x_range,
                push_state=push_state,
                state_label="x-range",
                draw=_draw_cpc_x_range,
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
                invalid_message="Invalid numbers.",
            )
            _print_menu(fig); continue
        elif key == 'y':
            def _redraw_cpc_left_y():
                try:
                    ax.relim()
                    ax.autoscale_view(scalex=False, scaley=True)
                except Exception:
                    pass
                try:
                    leg = ax.get_legend()
                    if leg is not None and leg.get_visible():
                        _apply_legend_position()
                except Exception:
                    pass
                fig.canvas.draw_idle()
            def _redraw_cpc_right_y():
                try:
                    ax2.relim()
                    ax2.autoscale_view(scalex=False, scaley=True)
                except Exception:
                    pass
                try:
                    leg = ax.get_legend()
                    if leg is not None and leg.get_visible():
                        _apply_legend_position()
                except Exception:
                    pass
                fig.canvas.draw_idle()
            def _auto_cpc_left_y():
                try:
                    all_y = []
                    for sc in [sc_charge, sc_discharge]:
                        if sc is not None and hasattr(sc, 'get_offsets'):
                            offsets = sc.get_offsets()
                            if offsets.size > 0:
                                all_y.extend([offsets[:, 1].min(), offsets[:, 1].max()])
                    if all_y:
                        ax.set_ylim(min(all_y), max(all_y))
                    else:
                        print("No original data available.")
                except Exception as e:
                    print(f"Error restoring original left Y range: {e}")
            def _auto_cpc_right_y():
                try:
                    if sc_eff is not None and hasattr(sc_eff, 'get_offsets'):
                        offsets = sc_eff.get_offsets()
                        if offsets.size > 0:
                            ax2.set_ylim(float(offsets[:, 1].min()), float(offsets[:, 1].max()))
                        else:
                            print("No original data available.")
                    else:
                        print("No original data available.")
                except Exception as e:
                    print(f"Error restoring original right Y range: {e}")
            def _run_cpc_left_y_menu():
                run_axis_limit_menu(
                    axis_name="left Y",
                    prompt_name="Left Y",
                    get_limits=ax.get_ylim,
                    set_limits=lambda lo, hi: ax.set_ylim(lo, hi),
                    auto_limits=_auto_cpc_left_y,
                    push_state=push_state,
                    state_label="y-left-range",
                    draw=_redraw_cpc_left_y,
                    safe_input=_safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=_colorize_prompt,
                    invalid_message="Invalid numbers.",
                )
            def _run_cpc_right_y_menu():
                assert sc_eff is not None
                try:
                    eff_on = bool(sc_eff.get_visible())
                except Exception:
                    eff_on = True
                if not eff_on:
                    print("Right Y is not shown; enable efficiency with 'ry' first.")
                    return
                run_axis_limit_menu(
                    axis_name="right Y",
                    prompt_name="Right Y",
                    get_limits=ax2.get_ylim,
                    set_limits=lambda lo, hi: ax2.set_ylim(lo, hi),
                    auto_limits=_auto_cpc_right_y,
                    push_state=push_state,
                    state_label="y-right-range",
                    draw=_redraw_cpc_right_y,
                    safe_input=_safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=_colorize_prompt,
                    invalid_message="Invalid numbers.",
                )
            run_dispatch_menu(
                prompt="Y-axis target (ly=left capacity, ry=right efficiency, q=back): ",
                options={
                    "ly": "left Y-axis (capacity)",
                    "ry": "right Y-axis (efficiency)",
                },
                handle_choice=lambda choice: _run_cpc_left_y_menu() if choice == 'ly' else (_run_cpc_right_y_menu() if choice == 'ry' else print("Unknown Y target.")),
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
            )
            _print_menu(fig); continue
        elif key == 'ie':
            # Invert coulombic efficiency values around 100% for the current file(s)
            try:
                if sc_eff is None or not hasattr(sc_eff, 'get_offsets'):
                    print("No efficiency data to invert.")
                    _print_menu(fig); continue
                if is_multi_file:
                    _print_file_list(file_data, current_file_idx)
                    choice = _safe_input(
                        f"Select file numbers (1-{len(file_data)}) to invert efficiency, a for all, or q=cancel: "
                    ).strip().lower()
                    if not choice or choice == 'q':
                        _print_menu(fig); continue
                    targets = []
                    if choice in ('a', 'all'):
                        targets = list(range(len(file_data)))
                    else:
                        try:
                            idx = int(choice) - 1
                            if 0 <= idx < len(file_data):
                                targets = [idx]
                            else:
                                print("Invalid file number.")
                                _print_menu(fig); continue
                        except ValueError:
                            print("Invalid choice.")
                            _print_menu(fig); continue
                    push_state("invert-efficiency")
                    for idx in targets:
                        f = file_data[idx]
                        eff_sc = f.get('sc_eff')
                        if eff_sc is None or not hasattr(eff_sc, 'get_offsets'):
                            continue
                        offsets = eff_sc.get_offsets()
                        if offsets.size == 0:
                            continue
                        xs = offsets[:, 0]
                        ys = offsets[:, 1]
                        # Invert around 100% (y -> 100 - y + 100 = 200 - y)
                        new_ys = 200.0 - ys
                        eff_sc.set_offsets(list(zip(xs, new_ys)))
                    fig.canvas.draw_idle()
                    print("Inverted efficiency for selected file(s).")
                else:
                    offsets = sc_eff.get_offsets()
                    if offsets.size == 0:
                        print("No efficiency data to invert.")
                        _print_menu(fig); continue
                    xs = offsets[:, 0]
                    ys = offsets[:, 1]
                    push_state("invert-efficiency")
                    new_ys = 200.0 - ys
                    sc_eff.set_offsets(list(zip(xs, new_ys)))
                    fig.canvas.draw_idle()
                    print("Inverted efficiency for current dataset.")
            except Exception as e:
                print(f"Error in efficiency inversion: {e}")
            _print_menu(fig); continue
        elif key == 'oe':
            handle_quick_overwrite_figure(action_ctx)
            continue
        elif key == 'os':
            handle_quick_overwrite_session(action_ctx)
            continue
        elif key in ('ops', 'opsg'):
            handle_quick_overwrite_style(action_ctx, include_geometry=(key == 'opsg'))
            continue
        else:
            print("Unknown key.")
            _print_menu(fig); continue


__all__ = ["cpc_interactive_menu"]

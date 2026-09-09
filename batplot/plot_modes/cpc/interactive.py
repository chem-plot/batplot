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
from ...color_utils import prompt_screen_color, blank_means_back, resolve_color_token
from .session import dump_cpc_session
from .colors import _generate_similar_color, run_cpc_color_menu
from .labels import run_cpc_rename_menu
from .overview import run_cpc_overview
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
    default_flat_tick_state,
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

from .panel_menus import (
    run_cpc_display_menu,
    run_cpc_efficiency_axis_menu,
    run_cpc_invert_efficiency_menu,
    run_cpc_line_width_menu,
    run_cpc_marker_size_menu,
    run_cpc_spine_color_menu,
    run_cpc_visibility_menu,
)
from .wasd_menu import run_cpc_wasd_menu

def _collect_file_paths(file_data) -> list:
    """Extract absolute file paths from file_data structures."""
    return file_data_source_paths(file_data)


def _get_current_file_artists(file_data, current_idx):
    """Get the scatter artists for the currently selected file."""
    if not file_data or current_idx >= len(file_data):
        return None, None, None
    file_info = file_data[current_idx]
    return file_info['sc_charge'], file_info['sc_discharge'], file_info['sc_eff']


def _print_file_list(file_data, current_idx=0):
    """Print list of files with current selection highlighted."""
    print("\n=== Files ===")
    for i, f in enumerate(file_data):
        marker = "→" if i == current_idx else " "
        vis = "✓" if f.get('visible', True) else "✗"
        name = f.get('display_name') or f.get('filename', f'File {i+1}')
        print(f"{marker} {i+1}. [{vis}] {name}")
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

    # Multi-file flag (recomputed each loop after add-file).
    is_multi_file = file_data is not None and len(file_data) > 1
    try:
        fig._cpc_is_multi_file = bool(is_multi_file)
    except Exception:
        pass
    if is_multi_file:
        try:
            from .legend_order import ensure_cpc_legend_file_order

            ensure_cpc_legend_file_order(fig, file_data)
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
    # Full flat schema (split + legacy) so p/s/b match batch before first ``t``.
    tick_state = default_flat_tick_state(
        tick_defaults={'top': False, 'bottom': True, 'left': True, 'right': True},
        label_defaults={'top': False, 'bottom': True, 'left': True, 'right': True},
    )
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
                _ui_set_spine_side_color(
                    curr_ax, spine_name, color, fig=fig, tick_state=tick_state
                )
            except Exception:
                pass

    def push_state(note: str = ""):
        return push_cpc_state(
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
        run_cpc_wasd_menu(
            fig=fig, ax=ax, ax2=ax2, sc_eff=sc_eff, tick_state=tick_state,
            push_state=push_state, print_menu=_print_menu,
            safe_input=_safe_input, colorize_prompt=_colorize_prompt,
            colorize_inline_commands=_colorize_inline_commands,
        )

    _print_menu(fig)
    pending_key = None
    while True:
        try:
            # Refresh multi-file / paths after add-file (or undo trim).
            is_multi_file = len(file_data) > 1
            try:
                fig._cpc_is_multi_file = bool(is_multi_file)
            except Exception:
                pass
            file_paths = _collect_file_paths(file_data)
            if current_file_idx >= len(file_data):
                current_file_idx = max(0, len(file_data) - 1)

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
            run_cpc_visibility_menu(
                fig=fig, ax=ax, ax2=ax2, file_data=file_data,
                current_file_idx=current_file_idx, is_multi_file=is_multi_file,
                push_state=push_state, print_menu=_print_menu,
                print_file_list=_print_file_list, safe_input=_safe_input,
                colorize_menu=_colorize_menu, colorize_prompt=_colorize_prompt,
            )
            continue

        if key == 'a':
            from .add_file import run_cpc_add_files_menu

            run_cpc_add_files_menu(
                fig=fig,
                ax=ax,
                ax2=ax2,
                file_data=file_data,
                push_state=push_state,
                pop_undo=pop_undo,
                safe_input=_safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
                print_menu=_print_menu,
            )
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
            run_cpc_spine_color_menu(
                fig=fig, file_data=file_data, current_file_idx=current_file_idx,
                is_multi_file=is_multi_file, sc_charge=sc_charge, sc_eff=sc_eff,
                push_state=push_state, set_spine_color=_set_spine_color,
                print_menu=_print_menu, print_file_list=_print_file_list,
                safe_input=_safe_input, colorize_menu=_colorize_menu,
                colorize_prompt=_colorize_prompt,
                colorize_inline_commands=_colorize_inline_commands,
            )
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
            run_cpc_display_menu(
                fig=fig, ax=ax, ax2=ax2, file_data=file_data,
                current_file_idx=current_file_idx, is_multi_file=is_multi_file,
                push_state=push_state, print_menu=_print_menu,
                print_file_list=_print_file_list, safe_input=_safe_input,
                colorize_menu=_colorize_menu, colorize_prompt=_colorize_prompt,
            )
            continue
        elif key == 'ry':
            run_cpc_efficiency_axis_menu(
                fig=fig, ax=ax, ax2=ax2, sc_eff=sc_eff, file_data=file_data,
                is_multi_file=is_multi_file, tick_state=tick_state,
                push_state=push_state, sanitize_legend_offset=_sanitize_legend_offset,
                print_menu=_print_menu, safe_input=_safe_input,
                colorize_menu=_colorize_menu, colorize_prompt=_colorize_prompt,
            )
            continue
        elif key == 'h':
            # Legend submenu: toggle, position, and (multi-file) rearrange display order.
            try:
                from .legend_order import run_cpc_legend_order_menu

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

                def _cpc_rearrange_legend():
                    run_cpc_legend_order_menu(
                        fig=fig,
                        ax=ax,
                        ax2=ax2,
                        file_data=file_data,
                        is_multi_file=is_multi_file,
                        print_file_list=_print_file_list,
                        rebuild_legend=_rebuild_legend,
                        push_state=push_state,
                        safe_input=_safe_input,
                    )

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
                    rearrange_legend=_cpc_rearrange_legend if is_multi_file else None,
                )
            except Exception as e:
                print(f"Error in CPC legend menu: {e}")
                traceback.print_exc()
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
                highlight_fig=fig,
                blank_exits=True,
            )
            _print_menu(fig); continue
        elif key == 'l':
            # Line widths submenu: frame/ticks vs grid
            run_cpc_line_width_menu(
                fig=fig, ax=ax, ax2=ax2, push_state=push_state,
                print_menu=_print_menu, safe_input=_safe_input,
                colorize_menu=_colorize_menu, colorize_prompt=_colorize_prompt,
            )
            continue
        elif key == 'm':
            run_cpc_marker_size_menu(
                fig=fig, sc_charge=sc_charge, sc_discharge=sc_discharge,
                sc_eff=sc_eff, file_data=file_data, is_multi_file=is_multi_file,
                push_state=push_state, print_menu=_print_menu,
                safe_input=_safe_input,
            )
            continue
        elif key == 't':
            _handle_key_t()
            continue
        elif key == 'g':
            def _sync_cpc_twin_frame():
                # resize_* only moves primary ax; keep efficiency twin locked.
                try:
                    if ax2 is not None:
                        ax2.set_position(ax.get_position())
                except Exception:
                    pass
            def _resize_cpc_frame():
                try:
                    resize_plot_frame(
                        fig, ax, [], [], type('Args', (), {'stack': False})(), lambda *_: None,
                        on_before_change=lambda: push_state("resize-frame"),
                    )
                    _sync_cpc_twin_frame()
                except Exception as e:
                    print(f"Resize failed: {e}")
            def _resize_cpc_canvas():
                try:
                    resize_canvas(
                        fig, ax,
                        on_before_change=lambda: push_state("resize-canvas"),
                    )
                    _sync_cpc_twin_frame()
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
                restore_state=restore_state,
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
            run_cpc_invert_efficiency_menu(
                fig=fig, sc_eff=sc_eff, file_data=file_data,
                current_file_idx=current_file_idx, is_multi_file=is_multi_file,
                push_state=push_state, print_menu=_print_menu,
                print_file_list=_print_file_list, safe_input=_safe_input,
            )
            continue
        elif key == 'o':
            try:
                run_cpc_overview(
                    file_data,
                    ax=ax,
                    safe_input=_safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=_colorize_prompt,
                    print_file_list=_print_file_list if is_multi_file else None,
                    include_hidden=False,
                )
            except Exception as e:
                print(f"Error in overview: {e}")
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

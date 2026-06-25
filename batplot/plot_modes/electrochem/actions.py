"""Command actions for the electrochemistry interactive menu."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List
import json
import os

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
from matplotlib.ticker import (  # type: ignore[import-untyped]
    AutoLocator,
    AutoMinorLocator,
    MultipleLocator,
    NullFormatter,
    NullLocator,
)

from .session import dump_ec_session
from ...utils import (
    _confirm_overwrite,
    choose_save_path,
    choose_style_file,
    ensure_exact_case_filename,
    get_organized_path,
    list_files_in_subdirectory,
    natural_sort_key,
)
from ..common.terminal import (
    colorize_inline_commands as _colorize_inline_commands,
    colorize_prompt as _colorize_prompt,
    safe_input as _safe_input,
)
from ..common.files import confirm_previous_path


@dataclass
class ElectrochemActionContext:
    fig: Any
    ax: Any
    cycle_lines: Dict[Any, Any]
    file_data: List[Dict[Any, Any]]
    tick_state: Dict[str, Any]
    source_paths: List[str]
    all_cycles: List[Any]
    is_dqdv: bool
    is_multi_file: bool
    menu_title: str
    canvas_mode: bool
    print_menu: Callable[..., Any]
    push_state: Callable[[str], Any]
    restore_state: Callable[[], Any]
    format_file_timestamp: Callable[[str], str]
    savefig_plot_window: Callable[..., Any]
    rebuild_legend: Callable[[Any], Any]
    get_style_snapshot: Callable[..., Dict[Any, Any]]
    get_geometry_snapshot: Callable[..., Dict[Any, Any]]
    print_style_snapshot: Callable[[Dict[Any, Any]], Any]
    export_style_dialog: Callable[..., Any]
    apply_font_family: Callable[..., Any]
    apply_font_size: Callable[..., Any]
    apply_spine_color: Callable[..., Any]
    iter_cycle_lines: Callable[..., Any]
    apply_cycle_styles: Callable[..., Any]
    apply_stored_smooth_settings: Callable[..., Any]
    sanitize_legend_offset: Callable[..., Any]
    apply_file_display_names_to_legend: Callable[..., Any]
    apply_display_mode: Callable[[str], Any]
    ui_position_top_xlabel: Callable[..., Any]
    ui_position_bottom_xlabel: Callable[..., Any]
    ui_position_left_ylabel: Callable[..., Any]
    ui_position_right_ylabel: Callable[..., Any]
    apply_legend_position: Callable[..., Any]
    set_legend_user_pref: Callable[..., Any]


def _redraw_menu(ctx: ElectrochemActionContext) -> None:
    ctx.print_menu(
        len(ctx.all_cycles),
        ctx.is_dqdv,
        ctx.fig,
        ctx.is_multi_file,
        ctx.menu_title,
        ctx.canvas_mode,
    )


def _build_ec_style_export_config(ctx: ElectrochemActionContext, exp_choice: str) -> tuple[dict, str]:
    """Build the canonical EC style payload for normal export and overwrite."""
    cfg = ctx.get_style_snapshot(
        ctx.fig,
        ctx.ax,
        ctx.cycle_lines,
        ctx.tick_state,
        file_data=ctx.file_data if ctx.is_multi_file else None,
    )
    if exp_choice == "psg":
        cfg["kind"] = "ec_style_geom"
        cfg["geometry"] = ctx.get_geometry_snapshot(ctx.fig, ctx.ax)
        return cfg, ".bpsg"
    cfg["kind"] = "ec_style"
    return cfg, ".bps"


def handle_undo_command(ctx: ElectrochemActionContext) -> None:
    ctx.restore_state()
    _redraw_menu(ctx)


def handle_export_figure_command(ctx: ElectrochemActionContext) -> None:
    fig = ctx.fig
    ax = ctx.ax
    source_paths = ctx.source_paths
    all_cycles = ctx.all_cycles
    is_dqdv = ctx.is_dqdv
    is_multi_file = ctx.is_multi_file
    menu_title = ctx.menu_title
    canvas_mode = ctx.canvas_mode
    _print_menu = ctx.print_menu
    _format_file_timestamp = ctx.format_file_timestamp
    _ec_savefig_plot_window = ctx.savefig_plot_window
    _rebuild_legend = ctx.rebuild_legend

    for _action_once in range(1):
        # Export current figure to a file; default extension .svg if missing
        try:
            base_path = choose_save_path(source_paths, purpose="figure export")
            if not base_path:
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                continue
            # List existing figure files in Figures/ subdirectory
            fig_extensions = ('.svg', '.png', '.jpg', '.jpeg', '.pdf', '.eps', '.tif', '.tiff')
            file_list = list_files_in_subdirectory(fig_extensions, 'figure', base_path=base_path)
            files = [f[0] for f in file_list]
            if files:
                figures_dir = os.path.join(base_path, 'Figures')
                print(f"Existing figure files in {figures_dir}:")
                for i, (fname, fpath) in enumerate(file_list, 1):
                    timestamp = _format_file_timestamp(fpath)
                    if timestamp:
                        print(f"  {i}: {fname}  ({timestamp})")
                    else:
                        print(f"  {i}: {fname}")

            last_figure_path = getattr(fig, '_last_figure_export_path', None)
            if last_figure_path:
                fname = _safe_input("Export filename (default .svg if no extension), number to overwrite, or o to overwrite last (q=cancel): ").strip()
            else:
                fname = _safe_input("Export filename (default .svg if no extension) or number to overwrite (q=cancel): ").strip()
            if not fname or fname.lower() == 'q':
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                continue

            already_confirmed = False  # Initialize for new filename case
            # Check for 'o' option
            if fname.lower() == 'o':
                if not last_figure_path:
                    print("No previous export found.")
                    _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                    continue
                if not os.path.exists(last_figure_path):
                    print(f"Previous export file not found: {last_figure_path}")
                    _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                    continue
                yn = _safe_input(f"Overwrite '{os.path.basename(last_figure_path)}'? (y/n): ").strip().lower()
                if yn != 'y':
                    _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                    continue
                target = last_figure_path
                already_confirmed = True
            # Check if user selected a number
            elif fname.isdigit() and files:
                already_confirmed = False
                idx = int(fname)
                if 1 <= idx <= len(files):
                    name = files[idx-1]
                    yn = _safe_input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                    if yn != 'y':
                        _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                        continue
                    target = file_list[idx-1][1]  # Full path from list
                    already_confirmed = True
                else:
                    print("Invalid number.")
                    _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                    continue
            else:
                root, ext = os.path.splitext(fname)
                if ext == '':
                    fname = fname + '.svg'
                # Use organized path unless it's an absolute path
                if os.path.isabs(fname):
                    target = fname
                else:
                    target = get_organized_path(fname, 'figure', base_path=base_path)

            try:
                if not already_confirmed and os.path.exists(target):
                    target = _confirm_overwrite(target)
                if target:
                    # Ensure exact case is preserved (important for macOS case-insensitive filesystem)
                    target = ensure_exact_case_filename(target)

                    # Save current legend position before export (savefig can change layout)
                    saved_legend_pos = None
                    try:
                        saved_legend_pos = getattr(fig, '_ec_legend_xy_in', None)
                    except Exception:
                        pass

                    # If exporting SVG, make background transparent for PowerPoint
                    _, ext2 = os.path.splitext(target)
                    ext2 = ext2.lower()
                    if ext2 == '.svg':
                        # Save original patch states
                        try:
                            fig_fc = fig.get_facecolor()
                        except Exception:
                            fig_fc = None
                        try:
                            ax_fc = ax.get_facecolor()
                        except Exception:
                            ax_fc = None
                        try:
                            # Set transparent patches
                            if getattr(fig, 'patch', None) is not None:
                                fig.patch.set_alpha(0.0)
                                fig.patch.set_facecolor('none')
                            if getattr(ax, 'patch', None) is not None:
                                ax.patch.set_alpha(0.0)
                                ax.patch.set_facecolor('none')
                        except Exception:
                            pass
                        try:
                            _ec_savefig_plot_window(fig, ax, target, transparent=True)
                        finally:
                            # Restore original patches if available
                            try:
                                if fig_fc is not None and getattr(fig, 'patch', None) is not None:
                                    fig.patch.set_alpha(1.0)
                                    fig.patch.set_facecolor(fig_fc)
                            except Exception:
                                pass
                            try:
                                if ax_fc is not None and getattr(ax, 'patch', None) is not None:
                                    ax.patch.set_alpha(1.0)
                                    ax.patch.set_facecolor(ax_fc)
                            except Exception:
                                pass
                    else:
                        _ec_savefig_plot_window(fig, ax, target, transparent=False)
                    print(f"Exported figure to {target}")
                    fig._last_figure_export_path = target

                    # Restore legend position after savefig (which may have changed layout)
                    if saved_legend_pos is not None:
                        try:
                            fig._ec_legend_xy_in = saved_legend_pos
                            _rebuild_legend(ax)
                            fig.canvas.draw_idle()
                        except Exception:
                            pass
            except Exception as e:
                print(f"Export failed: {e}")
        except Exception as e:
            print(f"Export failed: {e}")
        _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)


def handle_style_command(ctx: ElectrochemActionContext) -> None:
    fig = ctx.fig
    ax = ctx.ax
    cycle_lines = ctx.cycle_lines
    file_data = ctx.file_data
    tick_state = ctx.tick_state
    source_paths = ctx.source_paths
    all_cycles = ctx.all_cycles
    is_dqdv = ctx.is_dqdv
    is_multi_file = ctx.is_multi_file
    menu_title = ctx.menu_title
    canvas_mode = ctx.canvas_mode
    _print_menu = ctx.print_menu
    _get_style_snapshot = ctx.get_style_snapshot
    _get_geometry_snapshot = ctx.get_geometry_snapshot
    _print_style_snapshot = ctx.print_style_snapshot
    _export_style_dialog = ctx.export_style_dialog
    _format_file_timestamp = ctx.format_file_timestamp

    for _action_once in range(1):
        # Print/export style or style+geometry
        try:
            style_menu_active = True
            while style_menu_active:
                # Print style info first
                cfg = _get_style_snapshot(fig, ax, cycle_lines, tick_state, file_data=file_data if is_multi_file else None)
                cfg['kind'] = 'ec_style'  # Default, will be updated if psg is chosen
                _print_style_snapshot(cfg)

                # List available style files (.bps, .bpsg, .bpcfg) in Styles/ subdirectory
                style_file_list = list_files_in_subdirectory(('.bps', '.bpsg', '.bpcfg'), 'style')
                _bpcfg_files = [f[0] for f in style_file_list]
                if _bpcfg_files:
                    print("Existing style files in Styles/ (.bps/.bpsg):")
                    for _i, (fname, fpath) in enumerate(style_file_list, 1):
                        timestamp = _format_file_timestamp(fpath)
                        if timestamp:
                            print(f"  {_i}: {fname}  ({timestamp})")
                        else:
                            print(f"  {_i}: {fname}")

                last_style_path = getattr(fig, '_last_style_export_path', None)
                if last_style_path:
                    sub = _safe_input(_colorize_prompt("Style submenu: (e=export, o=overwrite last, q=return, r=refresh): ")).strip().lower()
                else:
                    sub = _safe_input(_colorize_prompt("Style submenu: (e=export, q=return, r=refresh): ")).strip().lower()
                if sub == 'q':
                    break
                if sub == 'r' or sub == '':
                    continue
                if sub == 'o':
                    # Overwrite last exported style file
                    if not last_style_path:
                        print("No previous export found.")
                        continue
                    if not os.path.exists(last_style_path):
                        print(f"Previous export file not found: {last_style_path}")
                        continue
                    yn = _safe_input(f"Overwrite '{os.path.basename(last_style_path)}'? (y/n): ").strip().lower()
                    if yn != 'y':
                        continue
                    # Determine if last export was style-only or style+geometry
                    try:
                        with open(last_style_path, 'r', encoding='utf-8') as f:
                            old_cfg = json.load(f)
                        if old_cfg.get('kind') == 'ec_style_geom':
                            cfg, _default_ext = _build_ec_style_export_config(ctx, 'psg')
                        else:
                            cfg, _default_ext = _build_ec_style_export_config(ctx, 'ps')
                    except Exception:
                        cfg, _default_ext = _build_ec_style_export_config(ctx, 'ps')
                    with open(last_style_path, 'w', encoding='utf-8') as f:
                        json.dump(cfg, f, indent=2)
                    print(f"Overwritten style to {last_style_path}")
                    style_menu_active = False
                    break
                if sub == 'e':
                    # Ask for ps or psg
                    print("Export options:")
                    print("  " + _colorize_inline_commands("ps  = style only (.bps)"))
                    print("  " + _colorize_inline_commands("psg = style + geometry (.bpsg)"))
                    exp_choice = _safe_input(_colorize_prompt("Export choice (ps/psg, q=cancel): ")).strip().lower()
                    if not exp_choice or exp_choice == 'q':
                        print("Style export canceled.")
                        continue

                    if exp_choice == 'ps':
                        # Style only
                        cfg, default_ext = _build_ec_style_export_config(ctx, 'ps')
                    elif exp_choice == 'psg':
                        # Style + Geometry
                        cfg, default_ext = _build_ec_style_export_config(ctx, 'psg')
                        geom = cfg['geometry']
                        print("\n--- Geometry ---")
                        print(f"X-axis label: {geom['xlabel']}")
                        print(f"Y-axis label: {geom['ylabel']}")
                        print(f"X limits: {geom['xlim'][0]:.4g} to {geom['xlim'][1]:.4g}")
                        print(f"Y limits: {geom['ylim'][0]:.4g} to {geom['ylim'][1]:.4g}")
                    else:
                        print(f"Unknown option: {exp_choice}")
                        continue

                    save_base = choose_save_path(source_paths, purpose="style export")
                    if not save_base:
                        print("Style export canceled.")
                        continue
                    print(f"\nChosen path: {save_base}")
                    exported_path = _export_style_dialog(cfg, default_ext=default_ext, base_path=save_base)
                    if exported_path:
                        fig._last_style_export_path = exported_path
                    style_menu_active = False  # Exit style submenu and return to main menu
                    break
                else:
                    print("Unknown choice.")
        except Exception as e:
            print(f"Error in style submenu: {e}")
        _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)


def handle_import_style_command(ctx: ElectrochemActionContext) -> None:  # pyright: ignore[reportGeneralTypeIssues] - too complex for full analysis
    fig = ctx.fig
    ax = ctx.ax
    cycle_lines = ctx.cycle_lines
    file_data = ctx.file_data
    tick_state = ctx.tick_state
    source_paths = ctx.source_paths
    all_cycles = ctx.all_cycles
    is_dqdv = ctx.is_dqdv
    is_multi_file = ctx.is_multi_file
    menu_title = ctx.menu_title
    canvas_mode = ctx.canvas_mode
    _print_menu = ctx.print_menu
    push_state = ctx.push_state
    _apply_font_family = ctx.apply_font_family
    _apply_font_size = ctx.apply_font_size
    _apply_spine_color = ctx.apply_spine_color
    _iter_cycle_lines = ctx.iter_cycle_lines
    _apply_cycle_styles = ctx.apply_cycle_styles
    _apply_stored_smooth_settings = ctx.apply_stored_smooth_settings
    _sanitize_legend_offset = ctx.sanitize_legend_offset
    _apply_file_display_names_to_legend = ctx.apply_file_display_names_to_legend
    _rebuild_legend = ctx.rebuild_legend
    _apply_display_mode = ctx.apply_display_mode
    _ui_position_top_xlabel = ctx.ui_position_top_xlabel
    _ui_position_bottom_xlabel = ctx.ui_position_bottom_xlabel
    _ui_position_left_ylabel = ctx.ui_position_left_ylabel
    _ui_position_right_ylabel = ctx.ui_position_right_ylabel
    _apply_legend_position = ctx.apply_legend_position
    _set_legend_user_pref = ctx.set_legend_user_pref

    for _action_once in range(1):
        # Import style from ...bps/.bpsg/.bpcfg
        try:
            path = choose_style_file(source_paths, purpose="style import")
            if not path:
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                continue
            push_state("import-style")
            with open(path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)

            # Check file type
            kind = cfg.get('kind', '')
            if kind not in ('ec_style', 'ec_style_geom'):
                print("Not an EC style file.")
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                continue

            # Enforce compatibility between style/geom ro state and current figure ro state
            file_ro = bool(cfg.get('ro_active', False))
            current_ro = bool(getattr(fig, '_ro_active', False))
            if file_ro != current_ro:
                if file_ro:
                    print("Warning: EC style/geometry file was saved with --ro (swapped x/y axes); current plot is not using --ro.")
                else:
                    print("Warning: EC style/geometry file was saved without --ro; current plot was created with --ro.")
                print("Not applying EC style/geometry to avoid corrupting axis orientation.")
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                continue

            geometry_cfg = cfg.get('geometry')
            if geometry_cfg is None:
                geometry_cfg = cfg.get('axes_geometry')
            has_geometry = (kind == 'ec_style_geom' and isinstance(geometry_cfg, dict))

            # Save current labelpad values and axes position BEFORE any style changes
            saved_xlabelpad = None
            saved_ylabelpad = None
            saved_axes_position = None
            try:
                saved_xlabelpad = getattr(ax.xaxis, 'labelpad', None)
            except Exception:
                pass
            try:
                saved_ylabelpad = getattr(ax.yaxis, 'labelpad', None)
            except Exception:
                pass
            try:
                # Save current axes position to detect if it actually changes
                saved_axes_position = ax.get_position()
            except Exception:
                pass

            # --- Apply comprehensive style (no curve data) ---
            # Figure and font
            try:
                fig_cfg = cfg.get('figure', {})
                # Get axes_fraction BEFORE changing canvas size (to preserve exact position)
                axes_frac = fig_cfg.get('axes_fraction')
                frame_size = fig_cfg.get('frame_size')

                canvas_size = fig_cfg.get('canvas_size')
                if canvas_size and isinstance(canvas_size, list) and len(canvas_size) == 2:
                    # Use forward=False to prevent automatic subplot adjustment that can shift the plot
                    # We'll restore axes_fraction immediately after to set exact position
                    fig.set_size_inches(canvas_size[0], canvas_size[1], forward=False)

                # Frame position: prefer axes_fraction (exact position), fall back to centering based on frame_size
                axes_position_changed = False
                if axes_frac and isinstance(axes_frac, (list, tuple)) and len(axes_frac) == 4:
                    # Restore exact position from axes_fraction (this overrides any automatic adjustments)
                    x0, y0, w, h = axes_frac
                    left = float(x0)
                    bottom = float(y0)
                    right = left + float(w)
                    top = bottom + float(h)
                    if 0 < left < right <= 1 and 0 < bottom < top <= 1:
                        w_frac = right - left
                        h_frac = top - bottom
                        if saved_axes_position is not None:
                            tol = 1e-6
                            if (abs(saved_axes_position.x0 - left) > tol or
                                abs(saved_axes_position.y0 - bottom) > tol or
                                abs(saved_axes_position.width - w_frac) > tol or
                                abs(saved_axes_position.height - h_frac) > tol):
                                axes_position_changed = True
                                ax.set_position([left, bottom, w_frac, h_frac])
                        else:
                            axes_position_changed = True
                            ax.set_position([left, bottom, w_frac, h_frac])
                elif frame_size and isinstance(frame_size, (list, tuple)) and len(frame_size) == 2:
                    # Fall back to centering based on frame_size (for backward compatibility)
                    fw_in, fh_in = frame_size
                    canvas_w, canvas_h = fig.get_size_inches()
                    if canvas_w > 0 and canvas_h > 0:
                        min_margin = 0.05
                        w_frac = min(fw_in / canvas_w, 1 - 2 * min_margin)
                        h_frac = min(fh_in / canvas_h, 1 - 2 * min_margin)
                        left = (1 - w_frac) / 2
                        bottom = (1 - h_frac) / 2
                        if saved_axes_position is not None:
                            tol = 1e-6
                            new_pos = (left, bottom, w_frac, h_frac)
                            if (abs(saved_axes_position.x0 - new_pos[0]) > tol or
                                abs(saved_axes_position.y0 - new_pos[1]) > tol or
                                abs(saved_axes_position.width - new_pos[2]) > tol or
                                abs(saved_axes_position.height - new_pos[3]) > tol):
                                axes_position_changed = True
                                ax.set_position([left, bottom, w_frac, h_frac])
                        else:
                            axes_position_changed = True
                            ax.set_position([left, bottom, w_frac, h_frac])

                font_cfg = cfg.get('font', {})
                if font_cfg.get('family'):
                    _apply_font_family(ax, font_cfg['family'])
                if font_cfg.get('size') is not None:
                    _apply_font_size(ax, float(font_cfg['size']))
                if font_cfg.get('mathtext_fontset'):
                    try:
                        plt.rcParams['mathtext.fontset'] = font_cfg['mathtext_fontset']
                    except Exception:
                        pass
                axis_label_colors = cfg.get('axis_label_colors') or {}
                try:
                    if axis_label_colors.get('x'):
                        ax.xaxis.label.set_color(axis_label_colors['x'])
                        ax._stored_xlabel_color = axis_label_colors['x']
                    if axis_label_colors.get('y'):
                        ax.yaxis.label.set_color(axis_label_colors['y'])
                        ax._stored_ylabel_color = axis_label_colors['y']
                except Exception:
                    pass
            except Exception as e:
                print(f"Warning: Could not apply figure/font settings: {e}")

            # WASD state and dependent components
            try:
                wasd_state = cfg.get('wasd_state')
                if wasd_state and isinstance(wasd_state, dict):
                    # Apply spines
                    for name in ('top','bottom','left','right'):
                        side = wasd_state.get(name, {})
                        if name in ax.spines and 'spine' in side:
                            ax.spines[name].set_visible(bool(side['spine']))

                    # Apply major ticks & labels
                    top_s = wasd_state.get('top', {})
                    bot_s = wasd_state.get('bottom', {})
                    left_s = wasd_state.get('left', {})
                    right_s = wasd_state.get('right', {})

                    ax.tick_params(axis='x',
                                  top=bool(top_s.get('ticks', False)),
                                  bottom=bool(bot_s.get('ticks', True)),
                                  labeltop=bool(top_s.get('labels', False)),
                                  labelbottom=bool(bot_s.get('labels', True)))
                    ax.tick_params(axis='y',
                                  left=bool(left_s.get('ticks', True)),
                                  right=bool(right_s.get('ticks', False)),
                                  labelleft=bool(left_s.get('labels', True)),
                                  labelright=bool(right_s.get('labels', False)))

                    # Apply minor ticks - only set locator if minor ticks are enabled, otherwise clear it
                    if top_s.get('minor') or bot_s.get('minor'):
                        ax.xaxis.set_minor_locator(AutoMinorLocator())
                        ax.xaxis.set_minor_formatter(NullFormatter())
                    else:
                        # Clear minor locator if no minor ticks are enabled
                        ax.xaxis.set_minor_locator(NullLocator())
                        ax.xaxis.set_minor_formatter(NullFormatter())
                    ax.tick_params(axis='x', which='minor',
                                  top=bool(top_s.get('minor', False)),
                                  bottom=bool(bot_s.get('minor', False)),
                                  labeltop=False, labelbottom=False)

                    if left_s.get('minor') or right_s.get('minor'):
                        ax.yaxis.set_minor_locator(AutoMinorLocator())
                        ax.yaxis.set_minor_formatter(NullFormatter())
                    else:
                        # Clear minor locator if no minor ticks are enabled
                        ax.yaxis.set_minor_locator(NullLocator())
                        ax.yaxis.set_minor_formatter(NullFormatter())
                    ax.tick_params(axis='y', which='minor',
                                  left=bool(left_s.get('minor', False)),
                                  right=bool(right_s.get('minor', False)),
                                  labelleft=False, labelright=False)

                    # Apply axis titles
                    ax._top_xlabel_on = bool(top_s.get('title', False))
                    ax._right_ylabel_on = bool(right_s.get('title', False))

                    # Update tick_state for consistency
                    tick_state['t_ticks'] = bool(top_s.get('ticks', False))
                    tick_state['t_labels'] = bool(top_s.get('labels', False))
                    tick_state['b_ticks'] = bool(bot_s.get('ticks', True))
                    tick_state['b_labels'] = bool(bot_s.get('labels', True))
                    tick_state['l_ticks'] = bool(left_s.get('ticks', True))
                    tick_state['l_labels'] = bool(left_s.get('labels', True))
                    tick_state['r_ticks'] = bool(right_s.get('ticks', False))
                    tick_state['r_labels'] = bool(right_s.get('labels', False))
                    tick_state['mtx'] = bool(top_s.get('minor', False))
                    tick_state['mbx'] = bool(bot_s.get('minor', False))
                    tick_state['mly'] = bool(left_s.get('minor', False))
                    tick_state['mry'] = bool(right_s.get('minor', False))
                    try:
                        setattr(fig, '_ec_wasd_state', {
                            'top': dict(top_s),
                            'bottom': dict(bot_s),
                            'left': dict(left_s),
                            'right': dict(right_s),
                        })
                        ax._saved_tick_state = dict(tick_state)
                    except Exception:
                        pass

                    # Don't reposition labels here - do it at the end after all style changes
                    # This prevents font changes and other operations from triggering unnecessary recalculations

            except Exception as e:
                print(f"Warning: Could not apply tick visibility: {e}")

            # Spines and Ticks (widths)
            try:
                spines_cfg = cfg.get('spines', {})
                for name, props in spines_cfg.items():
                    if name in ax.spines:
                        if props.get('linewidth') is not None:
                            ax.spines[name].set_linewidth(props['linewidth'])
                        if props.get('color') is not None:
                            _apply_spine_color(ax, fig, tick_state, name, props['color'])

                tick_widths = cfg.get('ticks', {}).get('widths', {})
                if tick_widths.get('x_major') is not None: ax.tick_params(axis='x', which='major', width=tick_widths['x_major'])
                if tick_widths.get('x_minor') is not None: ax.tick_params(axis='x', which='minor', width=tick_widths['x_minor'])
                if tick_widths.get('y_major') is not None: ax.tick_params(axis='y', which='major', width=tick_widths['y_major'])
                if tick_widths.get('y_minor') is not None: ax.tick_params(axis='y', which='minor', width=tick_widths['y_minor'])

                tick_lengths = cfg.get('ticks', {}).get('lengths', {})
                major_len = tick_lengths.get('major')
                minor_len = tick_lengths.get('minor')
                if major_len is not None:
                    ax.tick_params(axis='both', which='major', length=float(major_len))
                if minor_len is not None:
                    ax.tick_params(axis='both', which='minor', length=float(minor_len))
                if major_len is not None or minor_len is not None:
                    fig._tick_lengths = dict(tick_lengths)

                # Apply tick direction
                tick_direction = cfg.get('ticks', {}).get('direction', 'out')
                if tick_direction:
                    setattr(fig, '_tick_direction', tick_direction)
                    ax.tick_params(axis='both', which='both', direction=tick_direction)
                # Apply tick spacing and minor count
                ec_spacing = cfg.get('ticks', {}).get('spacing', {})
                if ec_spacing:
                    for axis_obj, maj_key, min_key, ndivs_key in [
                        (ax.xaxis, 'x_major_step', 'x_minor_step', 'x_minor_ndivs'),
                        (ax.yaxis, 'y_major_step', 'y_minor_step', 'y_minor_ndivs'),
                    ]:
                        try:
                            maj_step = ec_spacing.get(maj_key)
                            if maj_step is not None:
                                axis_obj.set_major_locator(MultipleLocator(float(maj_step)))
                            else:
                                axis_obj.set_major_locator(AutoLocator())
                        except Exception:
                            pass
                        try:
                            min_step = ec_spacing.get(min_key)
                            ndivs = ec_spacing.get(ndivs_key)
                            if min_step is not None:
                                axis_obj.set_minor_locator(MultipleLocator(float(min_step)))
                            elif ndivs is not None:
                                axis_obj.set_minor_locator(AutoMinorLocator(int(ndivs)))
                            else:
                                axis_obj.set_minor_locator(AutoMinorLocator())
                        except Exception:
                            pass
            except Exception: pass

            # Grid state
            try:
                grid_enabled = cfg.get('grid', False)
                if grid_enabled:
                    ax.grid(True, color='0.85', linestyle='-', linewidth=0.5, alpha=0.7)
                else:
                    ax.grid(False)
            except Exception: pass

            # Rotation angle
            try:
                rotation_angle = cfg.get('rotation_angle', 0)
                setattr(fig, '_ec_rotation_angle', rotation_angle)
            except Exception: pass

            # Curve linewidth (single value for all curves)
            try:
                curve_linewidth = cfg.get('curve_linewidth')
                if curve_linewidth is not None:
                    # Store globally on fig so it persists
                    setattr(fig, '_ec_curve_linewidth', float(curve_linewidth))
                    # Apply to all curves
                    for cyc, role, ln in _iter_cycle_lines(cycle_lines):
                        try:
                            ln.set_linewidth(float(curve_linewidth))
                        except Exception:
                            pass
            except Exception: pass

            # Curve marker properties (linestyle, marker, markersize, colors)
            try:
                curve_markers = cfg.get('curve_markers', {})
                if curve_markers:
                    for cyc, role, ln in _iter_cycle_lines(cycle_lines):
                        try:
                            if 'linestyle' in curve_markers:
                                ln.set_linestyle(curve_markers['linestyle'])
                            if 'marker' in curve_markers:
                                ln.set_marker(curve_markers['marker'])
                            if 'markersize' in curve_markers:
                                ln.set_markersize(curve_markers['markersize'])
                            if 'markerfacecolor' in curve_markers:
                                ln.set_markerfacecolor(curve_markers['markerfacecolor'])
                            if 'markeredgecolor' in curve_markers:
                                ln.set_markeredgecolor(curve_markers['markeredgecolor'])
                        except Exception:
                            pass
            except Exception: pass

            # Legend visibility/position
            legend_cfg = cfg.get('legend', {}) or {}
            legend_visible = None
            try:
                if legend_cfg:
                    legend_visible = bool(legend_cfg.get('visible', True))
                    xy = legend_cfg.get('position_inches')
                    if xy is not None:
                        fig._ec_legend_xy_in = _sanitize_legend_offset(fig, xy)
                    else:
                        fig._ec_legend_xy_in = None
                    if 'title' in legend_cfg and legend_cfg['title']:
                        fig._ec_legend_title = legend_cfg['title']
                    fig._ec_legend_user_visible = bool(legend_visible)
            except Exception:
                legend_visible = None

            cycle_styles_per_file_cfg = cfg.get('cycle_styles_per_file')
            cycle_styles_cfg = cfg.get('cycle_styles')
            if cycle_styles_per_file_cfg and is_multi_file and file_data and len(cycle_styles_per_file_cfg) == len(file_data):
                for i, f in enumerate(file_data):
                    cl = f.get('cycle_lines')
                    if cl and i < len(cycle_styles_per_file_cfg):
                        _apply_cycle_styles(cl, cycle_styles_per_file_cfg[i])
            elif cycle_styles_cfg:
                if is_multi_file and file_data:
                    for f in file_data:
                        cl = f.get('cycle_lines')
                        if cl:
                            _apply_cycle_styles(cl, cycle_styles_cfg)
                else:
                    _apply_cycle_styles(cycle_lines, cycle_styles_cfg)

            # Restore per-file visibility before display-mode filtering.
            try:
                file_visibility = cfg.get('file_visibility')
                if file_visibility and file_data and len(file_visibility) == len(file_data):
                    for f, visible in zip(file_data, file_visibility):
                        file_visible = bool(visible)
                        f['visible'] = file_visible
                        for _cyc, _role, ln in _iter_cycle_lines(f.get('cycle_lines') or {}):
                            try:
                                ln.set_visible(file_visible and bool(ln.get_visible()))
                            except Exception:
                                pass
            except Exception:
                pass

            # Restore display mode (d command) from style-only exports too.
            try:
                display_mode = cfg.get('display_mode')
                if display_mode in ('charge', 'discharge', 'both'):
                    _apply_display_mode(display_mode)
                    fig._ec_display_mode = display_mode
            except Exception:
                pass

            # Restore file display names (multi-file) from style
            try:
                names = cfg.get('file_display_names')
                if names and file_data and len(file_data) == len(names):
                    for i, f in enumerate(file_data):
                        if i < len(names):
                            f['display_name'] = names[i]
                    _apply_file_display_names_to_legend(file_data)
                    _rebuild_legend(ax)
            except Exception:
                pass

            # Restore legend file order (ra command)
            try:
                order = cfg.get('legend_file_order')
                if order and file_data and isinstance(order, (list, tuple)) and len(order) == len(file_data):
                    fig._ec_legend_file_order = list(order)
                    _rebuild_legend(ax)
            except Exception:
                pass

            # Restore dQ/dV smooth settings (sm command)
            try:
                smooth_cfg = cfg.get('_dqdv_smooth_settings')
                if isinstance(smooth_cfg, dict) and smooth_cfg:
                    fig._dqdv_smooth_settings = dict(smooth_cfg)
                    if is_multi_file and file_data:
                        for f in file_data:
                            cl = f.get('cycle_lines')
                            if cl:
                                _apply_stored_smooth_settings(cl, fig)
                    else:
                        _apply_stored_smooth_settings(cycle_lines, fig)
            except Exception:
                pass

            # Restore dual x-axis state
            try:
                xaxis_dual_cfg = cfg.get('xaxis_dual')
                if xaxis_dual_cfg and isinstance(xaxis_dual_cfg, dict):
                    mode = xaxis_dual_cfg.get('mode', 'capacity')
                    c_th = xaxis_dual_cfg.get('c_theoretical')
                    swapped = xaxis_dual_cfg.get('swapped', False)

                    # When ions/dual mode: prompt to use saved capacity or enter new
                    if mode in ('ions', 'dual') and c_th is not None:
                        try:
                            c_th_val = float(c_th)
                            prompt = f"Imported style uses ions display (capacity {c_th_val:g} mAh/g). Use this [Enter] or enter new value: "
                            raw = input(prompt).strip()
                            if raw:
                                new_c = float(raw)
                                if new_c > 0:
                                    c_th = new_c
                        except (ValueError, EOFError):
                            pass

                    # Store state on fig
                    fig._xaxis_mode = mode
                    fig._xaxis_c_theoretical = c_th
                    fig._xaxis_swapped = swapped

                    # Remove existing secondary axis if any
                    if hasattr(fig, '_xaxis_secondary') and fig._xaxis_secondary is not None:
                        try:
                            fig._xaxis_secondary.remove()
                        except Exception:
                            pass
                        fig._xaxis_secondary = None

                    # Recreate dual axis if needed
                    if mode == 'dual' and c_th is not None:
                        # Transform data based on swap state
                        for ln in ax.lines:
                            try:
                                if not hasattr(ln, "_orig_xdata_gc"):
                                    x0 = np.asarray(ln.get_xdata(), dtype=float)
                                    setattr(ln, "_orig_xdata_gc", x0.copy())
                                x_orig = getattr(ln, "_orig_xdata_gc")
                                if swapped:
                                    # Ions on bottom
                                    ln.set_xdata(x_orig / c_th)
                                else:
                                    # Capacity on bottom
                                    ln.set_xdata(x_orig)
                            except Exception:
                                continue

                        # Define conversion functions
                        if swapped:
                            def _bottom_to_top_ions(ions):
                                return ions * c_th

                            def _top_to_bottom_capacity(capacity):
                                return capacity / c_th

                            bottom_to_top = _bottom_to_top_ions
                            top_to_bottom = _top_to_bottom_capacity
                        else:
                            def _bottom_to_top_capacity(capacity):
                                return capacity / c_th

                            def _top_to_bottom_ions(ions):
                                return ions * c_th

                            bottom_to_top = _bottom_to_top_capacity
                            top_to_bottom = _top_to_bottom_ions

                        # Create secondary axis
                        try:
                            secax = ax.secondary_xaxis('top', functions=(bottom_to_top, top_to_bottom))
                            fig._xaxis_secondary = secax

                            # Set labels based on swap state
                            capacity_label = "Specific Capacity (mAh g$^{{-1}}$)"
                            ions_label = f"Number of ions (C / {c_th:g} mAh g$^{{-1}}$)"

                            if swapped:
                                ax.set_xlabel(ions_label)
                                secax.set_xlabel(capacity_label)
                            else:
                                ax.set_xlabel(capacity_label)
                                secax.set_xlabel(ions_label)
                            top_axis_cfg = xaxis_dual_cfg.get('top_axis') if isinstance(xaxis_dual_cfg, dict) else None
                            if isinstance(top_axis_cfg, dict):
                                try:
                                    if top_axis_cfg.get('xlabel') is not None:
                                        secax.set_xlabel(str(top_axis_cfg.get('xlabel') or ''))
                                    secax.xaxis.label.set_visible(bool(top_axis_cfg.get('xlabel_visible', True)))
                                    if top_axis_cfg.get('label_color'):
                                        secax.xaxis.label.set_color(top_axis_cfg['label_color'])
                                    sp = secax.spines.get('top')
                                    if sp is not None:
                                        if top_axis_cfg.get('spine_visible') is not None:
                                            sp.set_visible(bool(top_axis_cfg.get('spine_visible')))
                                        if top_axis_cfg.get('spine_color'):
                                            sp.set_edgecolor(top_axis_cfg['spine_color'])
                                    tick_color = top_axis_cfg.get('major_tick_color') or top_axis_cfg.get('spine_color')
                                    if tick_color:
                                        secax.tick_params(axis='x', which='both', colors=tick_color)
                                except Exception:
                                    pass

                            # Apply font settings
                            try:
                                font_fam = plt.rcParams.get('font.sans-serif', [''])
                                font_fam_str = font_fam[0] if isinstance(font_fam, list) and font_fam else ''
                                font_size = plt.rcParams.get('font.size', None)
                                if font_fam_str:
                                    secax.xaxis.label.set_family(font_fam_str)
                                if font_size is not None:
                                    secax.xaxis.label.set_size(font_size)
                            except Exception:
                                pass
                        except Exception as e:
                            print(f"Warning: Could not recreate dual x-axis: {e}")
                    elif mode == 'ions' and c_th is not None:
                        # Single ions mode
                        for ln in ax.lines:
                            try:
                                if not hasattr(ln, "_orig_xdata_gc"):
                                    x0 = np.asarray(ln.get_xdata(), dtype=float)
                                    setattr(ln, "_orig_xdata_gc", x0.copy())
                                x_orig = getattr(ln, "_orig_xdata_gc")
                                ln.set_xdata(x_orig / c_th)
                            except Exception:
                                continue
            except Exception as e:
                print(f"Warning: Could not restore dual x-axis state: {e}")

            # Apply geometry if present (before final repositioning)
            if has_geometry:
                try:
                    geom = geometry_cfg or {}
                    if 'xlabel' in geom and geom['xlabel']:
                        ax.set_xlabel(geom['xlabel'])
                    if 'ylabel' in geom and geom['ylabel']:
                        ax.set_ylabel(geom['ylabel'])
                    if 'xlim' in geom and isinstance(geom['xlim'], list) and len(geom['xlim']) == 2:
                        ax.set_xlim(geom['xlim'][0], geom['xlim'][1])
                    if 'ylim' in geom and isinstance(geom['ylim'], list) and len(geom['ylim']) == 2:
                        ax.set_ylim(geom['ylim'][0], geom['ylim'][1])
                    dm = geom.get('display_mode')
                    if dm in ('charge', 'discharge', 'both'):
                        _apply_display_mode(dm)
                        try:
                            fig._ec_display_mode = dm
                        except Exception:
                            pass
                    print("Applied geometry (labels and limits)")
                except Exception as e:
                    print(f"Warning: Could not apply geometry: {e}")

            # Restore title offsets
            try:
                offsets = cfg.get('title_offsets', {})
                if offsets:
                    ax._top_xlabel_manual_offset_y_pts = float(offsets.get('top_y', 0.0) or 0.0)
                    ax._top_xlabel_manual_offset_x_pts = float(offsets.get('top_x', 0.0) or 0.0)
                    ax._bottom_xlabel_manual_offset_y_pts = float(offsets.get('bottom_y', 0.0) or 0.0)
                    ax._left_ylabel_manual_offset_x_pts = float(offsets.get('left_x', 0.0) or 0.0)
                    ax._right_ylabel_manual_offset_x_pts = float(offsets.get('right_x', 0.0) or 0.0)
                    ax._right_ylabel_manual_offset_y_pts = float(offsets.get('right_y', 0.0) or 0.0)
            except Exception:
                pass

            # Final label positioning - do this AFTER all style changes to prevent drift
            # Set pending labelpad before repositioning to preserve original values
            try:
                if saved_xlabelpad is not None:
                    ax._pending_xlabelpad = saved_xlabelpad
                if saved_ylabelpad is not None:
                    ax._pending_ylabelpad = saved_ylabelpad

                # Only reposition if axes position actually changed OR if fonts changed
                # This prevents unnecessary movement when nothing actually changed
                font_cfg = cfg.get('font', {})
                font_changed = (font_cfg.get('family') is not None or font_cfg.get('size') is not None)

                # Always reposition titles to apply offsets (even if nothing else changed)
                _ui_position_top_xlabel(ax, fig, tick_state)
                _ui_position_bottom_xlabel(ax, fig, tick_state)
                _ui_position_left_ylabel(ax, fig, tick_state)
                _ui_position_right_ylabel(ax, fig, tick_state)

                # Always ensure labelpad is exactly as it was before style import
                # This is a final safeguard against any drift
                if saved_xlabelpad is not None:
                    ax.xaxis.labelpad = saved_xlabelpad
                if saved_ylabelpad is not None:
                    ax.yaxis.labelpad = saved_ylabelpad
            except Exception:
                pass

            # Rebuild and reposition legend after all changes (including figure size changes)
            _rebuild_legend(ax)
            if legend_cfg:
                try:
                    if legend_visible:
                        _apply_legend_position(fig, ax)
                    leg = ax.get_legend()
                    if leg is not None:
                        leg.set_visible(bool(legend_visible))
                    _set_legend_user_pref(fig, bool(legend_visible))
                except Exception:
                    pass

            fig.canvas.draw_idle()
            print(f"Applied style from {path}")

        except Exception as e:
            print(f"Error importing style: {e}")
        _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)


def handle_save_session_command(ctx: ElectrochemActionContext) -> None:
    fig = ctx.fig
    ax = ctx.ax
    cycle_lines = ctx.cycle_lines
    file_data = ctx.file_data
    source_paths = ctx.source_paths
    all_cycles = ctx.all_cycles
    is_dqdv = ctx.is_dqdv
    is_multi_file = ctx.is_multi_file
    menu_title = ctx.menu_title
    canvas_mode = ctx.canvas_mode
    _print_menu = ctx.print_menu
    _format_file_timestamp = ctx.format_file_timestamp

    for _action_once in range(1):
        try:
            last_session_path = getattr(fig, '_last_session_save_path', None)
            folder = choose_save_path(source_paths, purpose="EC session save")
            if not folder:
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode); continue
            print(f"\nChosen path: {folder}")
            try:
                files = sorted([f for f in os.listdir(folder) if f.lower().endswith('.pkl')], key=natural_sort_key)
            except Exception:
                files = []
            if files:
                print("Existing .pkl files:")
                for i, f in enumerate(files, 1):
                    filepath = os.path.join(folder, f)
                    timestamp = _format_file_timestamp(filepath)
                    if timestamp:
                        print(f"  {i}: {f}  ({timestamp})")
                    else:
                        print(f"  {i}: {f}")
            if last_session_path:
                prompt = "Enter new filename (no ext needed), number to overwrite, or o to overwrite last (q=cancel): "
            else:
                prompt = "Enter new filename (no ext needed) or number to overwrite (q=cancel): "
            choice = _safe_input(prompt).strip()
            if not choice or choice.lower() == 'q':
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode); continue
            if choice.lower() == 'o':
                # Overwrite last saved session
                if not last_session_path:
                    print("No previous save found.")
                    _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode); continue
                if not os.path.exists(last_session_path):
                    print(f"Previous save file not found: {last_session_path}")
                    _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode); continue
                yn = _safe_input(f"Overwrite '{os.path.basename(last_session_path)}'? (y/n): ").strip().lower()
                if yn != 'y':
                    _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode); continue
                dump_ec_session(last_session_path, fig=fig, ax=ax, cycle_lines=cycle_lines, file_data=file_data if is_multi_file else None, skip_confirm=True)
                print(f"Overwritten session to {last_session_path}")
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode); continue
            if choice.isdigit() and files:
                idx = int(choice)
                if 1 <= idx <= len(files):
                    name = files[idx-1]
                    yn = _safe_input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                    if yn != 'y':
                        _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode); continue
                    target = os.path.join(folder, name)
                    dump_ec_session(target, fig=fig, ax=ax, cycle_lines=cycle_lines, file_data=file_data if is_multi_file else None, skip_confirm=True)
                    fig._last_session_save_path = target
                    _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode); continue
                else:
                    print("Invalid number.")
                    _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode); continue
            if choice.lower() != 'o':
                name = choice
                root, ext = os.path.splitext(name)
                if ext == '':
                    name = name + '.pkl'
                target = name if os.path.isabs(name) else os.path.join(folder, name)
                if os.path.exists(target):
                    yn = _safe_input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
                    if yn != 'y':
                        _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode); continue
            dump_ec_session(target, fig=fig, ax=ax, cycle_lines=cycle_lines, file_data=file_data if is_multi_file else None, skip_confirm=True)
            fig._last_session_save_path = target
        except Exception as e:
            print(f"Save failed: {e}")
        _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)


def handle_quick_overwrite_figure_command(ctx: ElectrochemActionContext) -> None:
    fig = ctx.fig
    ax = ctx.ax
    try:
        last_figure_path = confirm_previous_path(
            fig,
            '_last_figure_export_path',
            safe_input=_safe_input,
            missing_message="No previous figure export found.",
            missing_file_message="Previous export file not found: {path}",
            confirm_prompt="Overwrite '{basename}'? (y/n): ",
        )
        if not last_figure_path:
            _redraw_menu(ctx)
            return

        _, ext = os.path.splitext(last_figure_path)
        if ext.lower() == '.svg':
            try:
                fig_fc = fig.get_facecolor()
            except Exception:
                fig_fc = None
            try:
                ax_fc = ax.get_facecolor()
            except Exception:
                ax_fc = None
            try:
                if getattr(fig, 'patch', None) is not None:
                    fig.patch.set_alpha(0.0)
                    fig.patch.set_facecolor('none')
                if getattr(ax, 'patch', None) is not None:
                    ax.patch.set_alpha(0.0)
                    ax.patch.set_facecolor('none')
            except Exception:
                pass
            try:
                ctx.savefig_plot_window(fig, ax, last_figure_path, transparent=True)
            finally:
                try:
                    if fig_fc is not None and getattr(fig, 'patch', None) is not None:
                        fig.patch.set_alpha(1.0)
                        fig.patch.set_facecolor(fig_fc)
                except Exception:
                    pass
                try:
                    if ax_fc is not None and getattr(ax, 'patch', None) is not None:
                        ax.patch.set_alpha(1.0)
                        ax.patch.set_facecolor(ax_fc)
                except Exception:
                    pass
        else:
            ctx.savefig_plot_window(fig, ax, last_figure_path, transparent=False)
        print(f"Overwritten figure to {last_figure_path}")
    except Exception as e:
        print(f"Overwrite failed: {e}")
    _redraw_menu(ctx)


def handle_quick_overwrite_session_command(ctx: ElectrochemActionContext) -> None:
    fig = ctx.fig
    try:
        last_session_path = confirm_previous_path(
            fig,
            '_last_session_save_path',
            safe_input=_safe_input,
            missing_message="No previous session save found.",
            missing_file_message="Previous save file not found: {path}",
            confirm_prompt="Overwrite '{basename}'? (y/n): ",
        )
        if not last_session_path:
            _redraw_menu(ctx)
            return
        dump_ec_session(
            last_session_path,
            fig=fig,
            ax=ctx.ax,
            cycle_lines=ctx.cycle_lines,
            file_data=ctx.file_data if ctx.is_multi_file else None,
            skip_confirm=True,
        )
        print(f"Overwritten session to {last_session_path}")
    except Exception as e:
        print(f"Overwrite failed: {e}")
    _redraw_menu(ctx)


def handle_quick_overwrite_style_command(ctx: ElectrochemActionContext, *, include_geometry: bool) -> None:
    fig = ctx.fig
    try:
        exp_choice = 'psg' if include_geometry else 'ps'
        label = "style+geometry" if include_geometry else "style-only"
        last_style_path = confirm_previous_path(
            fig,
            '_last_style_export_path',
            safe_input=_safe_input,
            missing_message="No previous style export found.",
            missing_file_message="Previous export file not found: {path}",
            confirm_prompt=f"Overwrite {label} file '{{basename}}'? (y/n): ",
        )
        if not last_style_path:
            _redraw_menu(ctx)
            return
        cfg, _ = _build_ec_style_export_config(ctx, exp_choice)
        with open(last_style_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2)
        print(f"Overwritten {label} style to {last_style_path}")
    except Exception as e:
        print(f"Overwrite failed: {e}")
    _redraw_menu(ctx)

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
from ...ui import set_spine_side_color, finalize_spine_colors
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
from ..common.font_extras import apply_font_extras_from_cfg
from ..common.fonts import collect_fig_font_artists


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
    pop_undo: Callable[[], Any]
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
    from ..common.state_capture import as_style_geom_export

    cfg = ctx.get_style_snapshot(
        ctx.fig,
        ctx.ax,
        ctx.cycle_lines,
        ctx.tick_state,
        file_data=ctx.file_data if ctx.is_multi_file else None,
    )
    if exp_choice == "psg":
        return (
            as_style_geom_export(
                cfg,
                kind="ec_style_geom",
                geometry=ctx.get_geometry_snapshot(ctx.fig, ctx.ax),
            ),
            ".bpsg",
        )
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


def handle_import_style_command(ctx: ElectrochemActionContext) -> None:
    """Import EC style/geometry via the canonical style applier."""
    from .style_apply import apply_ec_style_config

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
    pop_undo = ctx.pop_undo

    for _action_once in range(1):
        try:
            path = choose_style_file(source_paths, purpose="style import")
            if not path:
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                continue
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)

            kind = cfg.get("kind", "")
            if kind not in ("ec_style", "ec_style_geom"):
                print("Not an EC style file.")
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                continue

            file_ro = bool(cfg.get("ro_active", False))
            current_ro = bool(getattr(fig, "_ro_active", False))
            if file_ro != current_ro:
                if file_ro:
                    print(
                        "Warning: EC style/geometry file was saved with --ro (swapped x/y axes); "
                        "current plot is not using --ro."
                    )
                else:
                    print(
                        "Warning: EC style/geometry file was saved without --ro; "
                        "current plot was created with --ro."
                    )
                print("Not applying EC style/geometry to avoid corrupting axis orientation.")
                _print_menu(len(all_cycles), is_dqdv, fig, is_multi_file, menu_title, canvas_mode)
                continue

            push_state("import-style")
            ok = apply_ec_style_config(
                cfg,
                fig=fig,
                ax=ax,
                cycle_lines=cycle_lines,
                file_data=file_data if is_multi_file else None,
                tick_state=tick_state,
                is_multi_file=is_multi_file,
                silent=False,
            )
            if ok:
                print(f"Applied style from {path}")
            else:
                try:
                    pop_undo()
                except Exception:
                    pass
        except Exception as e:
            try:
                pop_undo()
            except Exception:
                pass
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

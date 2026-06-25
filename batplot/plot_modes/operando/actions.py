"""Command action handlers for the operando interactive menu.

This module keeps the p/i/e/s/b command bodies out of ``interactive.py`` while
preserving the operando-only and operando+EC behavior through an explicit context
object supplied by the menu loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
import json
import os

import matplotlib.pyplot as plt  # type: ignore[import-untyped]
from matplotlib.ticker import FuncFormatter, MaxNLocator, AutoMinorLocator, NullFormatter, NullLocator  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]

from .plot import _draw_operando_cif_ticks
from .ions_axis import install_ec_ions_y_display
from ...ui import position_top_xlabel as _ui_position_top_xlabel
from ...ui import position_right_ylabel as _ui_position_right_ylabel
from ...ui import position_bottom_xlabel as _ui_position_bottom_xlabel
from ...ui import position_left_ylabel as _ui_position_left_ylabel
from ...ui import restore_axes_tick_locators
from ..common.spines import keep_yaxis_label_on_side
from ...utils import (
    choose_style_file,
    choose_save_path,
    list_files_in_subdirectory,
    get_organized_path,
    ensure_exact_case_filename,
    _confirm_overwrite,
)
from ..common.terminal import (
    colorize_single_key_inline_commands as _colorize_inline_commands,
    safe_input as _safe_input,
)
from ..common.files import confirm_previous_path
from ..common.title_offsets import restore_title_offsets
from .session import dump_operando_session
from .layout import (
    _apply_group_layout_inches,
    _ensure_fixed_params,
    _get_fig_size,
    _safe_set_clim,
    _update_custom_colorbar,
)
from .style import build_operando_ec_style_config_v2 as _build_operando_ec_style_config_v2


@dataclass
class OperandoActionContext:
    fig: Any
    ax: Any
    im: Any
    cbar: Any
    ec_ax: Any
    file_paths: list[str]
    print_menu: Callable[[], None]
    snapshot: Callable[[str], None]
    restore: Callable[[], None]
    run_save_operando_session: Callable[[], None]
    set_fonts: Callable[..., None]
    axis_tick_width: Callable[[Any, str], Any]
    format_file_timestamp: Callable[[str], str]
    maybe_reapply_dqdv_2d_contour: Callable[[Any, Any, Any, Any], None]
    restore_dqdv_2d_operando_labels: Callable[[Any, dict], None]
    ax_w_in: float
    ax_h_in: float
    cb_w_in: float
    cb_gap_in: float
    ec_gap_in: float
    ec_w_in: float


def _sync_geometry(ctx: OperandoActionContext, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in) -> None:
    ctx.ax_w_in = ax_w_in
    ctx.ax_h_in = ax_h_in
    ctx.cb_w_in = cb_w_in
    ctx.cb_gap_in = cb_gap_in
    ctx.ec_gap_in = ec_gap_in
    ctx.ec_w_in = ec_w_in


def _apply_tick_lengths(fig, axis, lengths) -> None:
    if not lengths:
        return
    major = lengths.get('major', lengths.get('x_major', lengths.get('y_major')))
    minor = lengths.get('minor', lengths.get('x_minor', lengths.get('y_minor')))
    try:
        if major is not None:
            axis.tick_params(axis='both', which='major', length=float(major))
        if minor is not None:
            axis.tick_params(axis='both', which='minor', length=float(minor))
        if major is not None or minor is not None:
            if not hasattr(fig, '_tick_lengths') or not isinstance(getattr(fig, '_tick_lengths', None), dict):
                fig._tick_lengths = {}
            if major is not None:
                fig._tick_lengths['major'] = float(major)
            if minor is not None:
                fig._tick_lengths['minor'] = float(minor)
    except Exception:
        pass


def _apply_tick_style(fig, axis, tick_cfg) -> None:
    if not axis or not isinstance(tick_cfg, dict):
        return
    try:
        direction = tick_cfg.get("direction")
        if direction:
            axis.tick_params(axis="both", which="both", direction=direction)
            setattr(fig, "_tick_direction", direction)
    except Exception:
        pass
    try:
        restore_axes_tick_locators(axis, tick_cfg.get("locator_state"), ("x", "y"))
    except Exception:
        pass


def handle_export_figure(ctx: OperandoActionContext) -> None:
    fig = ctx.fig
    ax = ctx.ax
    im = ctx.im
    cbar = ctx.cbar
    ec_ax = ctx.ec_ax
    file_paths = ctx.file_paths
    print_menu = ctx.print_menu
    _format_file_timestamp = ctx.format_file_timestamp
    try:
        # Choose base path (terminal cwd vs file directories)
        base_path = choose_save_path(file_paths, purpose="figure export")
        if not base_path:
            print_menu(); return
        print(f"\nChosen path: {base_path}")
        # List existing figure files in Figures/ subdirectory
        fig_extensions = ('.svg', '.png', '.jpg', '.jpeg', '.pdf', '.eps', '.tif', '.tiff')
        file_list = list_files_in_subdirectory(fig_extensions, 'figure', base_path=base_path)
        files = [f[0] for f in file_list]
        if files:
            print("Existing figure files in Figures/:")
            for i, (fname, fpath) in enumerate(file_list, 1):
                timestamp = _format_file_timestamp(fpath)
                if timestamp:
                    print(f"  {i}: {fname}  ({timestamp})")
                else:
                    print(f"  {i}: {fname}")

        last_figure_path = getattr(fig, '_last_figure_export_path', None)
        if last_figure_path:
            fname = _safe_input(_colorize_inline_commands("Export filename (default .svg if no extension), number to overwrite, or o to overwrite last (q=cancel): ")).strip()
        else:
            fname = _safe_input(_colorize_inline_commands("Export filename (default .svg if no extension) or number to overwrite (q=cancel): ")).strip()
        if not fname or fname.lower() == 'q':
            print_menu(); return

        already_confirmed = False  # Initialize for new filename case
        # Check for 'o' option
        if fname.lower() == 'o':
            if not last_figure_path:
                print("No previous export found.")
                print_menu(); return
            if not os.path.exists(last_figure_path):
                print(f"Previous export file not found: {last_figure_path}")
                print_menu(); return
            yn = _safe_input(f"Overwrite '{os.path.basename(last_figure_path)}'? (y/n): ").strip().lower()
            if yn != 'y':
                print_menu(); return
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
                    print_menu(); return
                target = file_list[idx-1][1]  # Full path from list
                already_confirmed = True
            else:
                print("Invalid number.")
                print_menu(); return
        else:
            if not os.path.splitext(fname)[1]:
                fname += '.svg'
            # Use organized path unless it's an absolute path
            if os.path.isabs(fname):
                target = fname
            else:
                target = get_organized_path(fname, 'figure', base_path=base_path)

        if not already_confirmed and os.path.exists(target):
            target = _confirm_overwrite(target)
        if not target:
            print_menu(); return
        # Ensure exact case is preserved (important for macOS case-insensitive filesystem)
        target = ensure_exact_case_filename(target)

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
        fig._last_figure_export_path = target
    except Exception as e:
        print(f"Export failed: {e}")
    print_menu(); return



def handle_undo(ctx: OperandoActionContext) -> None:
    ctx.restore()
    ctx.print_menu()


def handle_save_session(ctx: OperandoActionContext) -> None:
    try:
        ctx.run_save_operando_session()
    except Exception as e:
        print(f"Save failed: {e}")
    ctx.print_menu()


def handle_quick_overwrite_figure(ctx: OperandoActionContext) -> None:
    fig = ctx.fig
    ax = ctx.ax
    print_menu = ctx.print_menu
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
            print_menu()
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
                ec_fc = ctx.ec_ax.get_facecolor() if ctx.ec_ax is not None else None
            except Exception:
                ec_fc = None
            try:
                if getattr(fig, 'patch', None) is not None:
                    fig.patch.set_alpha(0.0)
                    fig.patch.set_facecolor('none')
                if getattr(ax, 'patch', None) is not None:
                    ax.patch.set_alpha(0.0)
                    ax.patch.set_facecolor('none')
                if ctx.ec_ax is not None and getattr(ctx.ec_ax, 'patch', None) is not None:
                    ctx.ec_ax.patch.set_alpha(0.0)
                    ctx.ec_ax.patch.set_facecolor('none')
            except Exception:
                pass
            try:
                fig.savefig(last_figure_path, dpi=300, transparent=True, facecolor='none', edgecolor='none')
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
                try:
                    if ec_fc is not None and ctx.ec_ax is not None and getattr(ctx.ec_ax, 'patch', None) is not None:
                        ctx.ec_ax.patch.set_alpha(1.0)
                        ctx.ec_ax.patch.set_facecolor(ec_fc)
                except Exception:
                    pass
        else:
            fig.savefig(last_figure_path, dpi=300)
        print(f"Overwritten figure to {last_figure_path}")
    except Exception as e:
        print(f"Overwrite failed: {e}")
    print_menu()


def handle_quick_overwrite_session(ctx: OperandoActionContext) -> None:
    fig = ctx.fig
    print_menu = ctx.print_menu
    try:
        last_session_path = confirm_previous_path(
            fig,
            '_last_session_save_path',
            safe_input=_safe_input,
            missing_message="No previous session save found.",
            missing_file_message="Previous save file not found: {path}",
            confirm_prompt="Overwrite '{basename}'? (y/n): ",
            canceled_message=None,
        )
        if not last_session_path:
            print_menu()
            return
        dump_operando_session(
            last_session_path,
            fig=fig,
            ax=ctx.ax,
            im=ctx.im,
            cbar=ctx.cbar,
            ec_ax=ctx.ec_ax,
            skip_confirm=True,
        )
        print(f"Overwritten session to {last_session_path}")
    except Exception as e:
        print(f"Overwrite failed: {e}")
    print_menu()


def handle_quick_overwrite_style(ctx: OperandoActionContext, *, include_geometry: bool) -> None:
    fig = ctx.fig
    print_menu = ctx.print_menu
    try:
        exp_choice = 'psg' if include_geometry else 'ps'
        last_style_path = confirm_previous_path(
            fig,
            '_last_style_export_path',
            safe_input=_safe_input,
            missing_message="No previous style export found.",
            missing_file_message="Previous export file not found: {path}",
            confirm_prompt=f"Overwrite '{{basename}}' with current {exp_choice.upper()} style? (y/n): ",
            canceled_message=None,
        )
        if not last_style_path:
            print_menu()
            return
        cfg, _ = _build_operando_ec_style_config_v2(ctx.fig, ctx.ax, ctx.im, ctx.cbar, ctx.ec_ax, exp_choice)
        with open(last_style_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2)
        print(f"Overwritten style to {last_style_path}")
    except Exception as e:
        print(f"Overwrite failed: {e}")
    print_menu()


def handle_export_style(ctx: OperandoActionContext) -> None:
    fig = ctx.fig
    ax = ctx.ax
    im = ctx.im
    cbar = ctx.cbar
    ec_ax = ctx.ec_ax
    file_paths = ctx.file_paths
    print_menu = ctx.print_menu
    _axis_tick_width = ctx.axis_tick_width
    _format_file_timestamp = ctx.format_file_timestamp
    # Print current style and offer export
    # Style commands (Styles column - col1):
    #   oc: operando colormap
    #   ow: operando width
    #   ew: EC width
    #   h:  height
    #   el: EC curve (color, linewidth)
    #   t:  toggle spines (WASD states for both panes)
    #   l:  line widths (frame and tick widths for both panes)
    #   f:  fonts (family, size)
    #   g:  canvas size
    #   r:  reverse Y-axis orientation
    try:
        style_menu_active = True
        while style_menu_active:
            # Print style info first
            # Gather style
            fig_w, fig_h = _get_fig_size(fig)
            cb_w_in, cb_gap_in, ec_gap_in, ec_w_in, ax_w_in, ax_h_in = _ensure_fixed_params(fig, ax, cbar.ax, ec_ax)
            fam = plt.rcParams.get('font.sans-serif', [''])[0]
            fsize = plt.rcParams.get('font.size', None)
            # Get colormap name: first check if we stored it explicitly, otherwise try to get from colormap object
            cmap_name = getattr(im, '_operando_cmap_name', None)
            if cmap_name is None:
                cmap_name = getattr(im.get_cmap(), 'name', None)
            cb_vis = bool(cbar.ax.get_visible())
            ec_vis = bool(ec_ax.get_visible()) if ec_ax is not None else None
            cb_label_text = str(getattr(cbar.ax, '_colorbar_label', cbar.ax.get_ylabel() or 'Intensity'))
            cb_label_mode = getattr(fig, '_colorbar_label_mode', 'highlow')

            # Print header based on mode
            if ec_ax is not None:
                print("\n" + "=" * 60)
                print("  OPERANDO+EC STYLE SUMMARY")
                print("=" * 60)
                print("Commands: oc ow ew h el v t l f g r | ox oy oz or c | et ex ey er eg")
                print()
            else:
                print("\n" + "=" * 60)
                print("  OPERANDO-ONLY STYLE SUMMARY")
                print("=" * 60)
                print("Commands: oc ow v t l h f g r | ox oy oz or c")
                print()

            # ---- Canvas & Geometry ----
            print("--- Canvas & Geometry ---")
            print(f"Canvas size (g): {fig_w:.3f} x {fig_h:.3f} in")
            print(f"Geometry: ow={ax_w_in:.3f}\", h={ax_h_in:.3f}\", colorbar={cb_w_in:.3f}\"", end="")
            if ec_ax is not None:
                print(f", ew={ec_w_in:.3f}\"")
            else:
                print()
            cb_off = getattr(cbar.ax, '_cb_h_offset_in', 0.0)
            if abs(cb_off) > 0.001:
                print(f"  Colorbar horizontal offset: {cb_off:+.3f}\"")
            if ec_ax is not None:
                ec_off = getattr(ec_ax, '_ec_h_offset_in', 0.0)
                if abs(ec_off) > 0.001:
                    print(f"  EC panel horizontal offset: {ec_off:+.3f}\"")

            # ---- Visibility & Colorbar ----
            print("\n--- Visibility & Colorbar ---")
            if ec_ax is not None:
                print(f"Visibility (v): colorbar={'shown' if cb_vis else 'hidden'}, EC={'shown' if ec_vis else 'hidden'}")
            else:
                print(f"Visibility (v): colorbar={'shown' if cb_vis else 'hidden'}")
            mode_label = "High/Low" if cb_label_mode == 'highlow' else 'Normal'
            print(f"Colorbar: label=\"{cb_label_text}\", mode={mode_label}")
            cb_ticks_pos = cbar.ax.yaxis.get_ticks_position()
            cb_label_pos = cbar.ax.yaxis.get_label_position()
            print(f"  Ticks: {cb_ticks_pos}, label: {cb_label_pos}")

            # ---- Font ----
            mathtext = plt.rcParams.get('mathtext.fontset', 'dejavusans')
            print(f"\n--- Font (f) ---")
            print(f"Family='{fam}', size={fsize}, mathtext={mathtext}")

            # ---- Operando ----
            print("\n--- Operando ---")
            print(f"Colormap (oc): {cmap_name}")
            try:
                clim = im.get_clim()
                print(f"Intensity range (oz): {clim[0]:.4g} to {clim[1]:.4g}")
            except Exception:
                print("Intensity range (oz): N/A")
            op_xlim = ax.get_xlim()
            op_ylim = ax.get_ylim()
            print(f"X range (ox): {op_xlim[0]:.4g} to {op_xlim[1]:.4g}")
            print(f"Y range (oy): {op_ylim[0]:.4g} to {op_ylim[1]:.4g}")
            op_reversed = bool(op_ylim[0] > op_ylim[1])
            print(f"Labels (or): x='{ax.get_xlabel() or ''}', y='{ax.get_ylabel() or ''}'")
            print(f"Reverse Y (r): {'YES' if op_reversed else 'no'}")

            # CIF ticks (c)
            cif_series = getattr(ax, '_operando_cif_tick_series', None)
            if cif_series:
                n_sets = len(cif_series)
                show_hkl = bool(getattr(fig, '_operando_cif_show_hkl', False))
                show_titles = bool(getattr(fig, '_operando_cif_show_titles', True))
                placement = str(getattr(fig, '_operando_cif_placement', 'below'))
                highlight = bool(getattr(fig, '_operando_cif_highlight', False))
                print(f"CIF ticks (c): {n_sets} set(s), hkl={'on' if show_hkl else 'off'}, titles={'on' if show_titles else 'off'}, placement={placement}, highlight={'on' if highlight else 'off'}")
            else:
                print("CIF ticks (c): none")

            # ---- EC Panel (Side Panel) ----
            if ec_ax is not None:
                print("\n--- EC Panel ---")
                ec_y_mode = getattr(ec_ax, '_ec_y_mode', 'time')
                print(f"Y-axis mode (ey): {ec_y_mode}")
                if ec_y_mode == 'ions':
                    ion_params = getattr(ec_ax, '_ion_params', {})
                    if ion_params:
                        mass_mg = ion_params.get('mass_mg', 'N/A')
                        cap_per_ion = ion_params.get('cap_per_ion_mAh_g', 'N/A')
                        start_ions = ion_params.get('start_ions', 'N/A')
                        print(f"  Ion params: mass={mass_mg} mg, cap/ion={cap_per_ion} mAh/g, start={start_ions}")
                ec_xlim = ec_ax.get_xlim()
                ec_ylim = ec_ax.get_ylim()
                print(f"X range (et/ex): {ec_xlim[0]:.4g} to {ec_xlim[1]:.4g}")
                print(f"Y range: {ec_ylim[0]:.4g} to {ec_ylim[1]:.4g}")
                ec_reversed = bool(ec_ylim[0] > ec_ylim[1])
                ec_ylabel = ec_ax.get_ylabel() or getattr(ec_ax, '_stored_ylabel', '') or ''
                print(f"Labels (er): x='{ec_ax.get_xlabel() or ''}', y='{ec_ylabel}'")
                print(f"Reverse Y (r): {'YES' if ec_reversed else 'no'}")
                ec_grid = getattr(ec_ax, '_ec_grid', None) or {}
                grid_visible = ec_grid.get('visible', False)
                print(f"Grid (eg): {'on' if grid_visible else 'off'}", end="")
                if grid_visible:
                    print(f" (alpha={ec_grid.get('alpha', 0.3):.2f}, ls='{ec_grid.get('linestyle', '--')}', which={ec_grid.get('which', 'major')})")
                else:
                    print()
                ln = getattr(ec_ax, '_ec_line', None)
                if ln is None and ec_ax.lines:
                    ln = ec_ax.lines[0]
                if ln is not None:
                    try:
                        print(f"Curve (el): color={ln.get_color()}, linewidth={ln.get_linewidth():.2f}")
                    except Exception:
                        print("Curve (el): (unable to read)")
                else:
                    print("Curve (el): (no line)")

            # ---- Line widths & Ticks (l, t) ----
            print("\n--- Line widths (l) ---")
            op_frame_lw = ax.spines.get('bottom').get_linewidth() if ax.spines.get('bottom') else 1.0
            op_tick_lw = _axis_tick_width(ax.xaxis, 'major') or 1.0
            print(f"Operando: frame={op_frame_lw:.2f}, ticks={op_tick_lw:.2f}")
            if ec_ax is not None:
                ec_frame_lw = ec_ax.spines.get('bottom').get_linewidth() if ec_ax.spines.get('bottom') else 1.0
                ec_tick_lw = _axis_tick_width(ec_ax.xaxis, 'major') or 1.0
                print(f"EC: frame={ec_frame_lw:.2f}, ticks={ec_tick_lw:.2f}")
            tick_dir = getattr(fig, '_tick_direction', 'out')
            print(f"Tick direction (t>i): {tick_dir}")
            tick_len = getattr(fig, '_tick_lengths', None)
            if tick_len and isinstance(tick_len, dict):
                maj = tick_len.get('major')
                minor = tick_len.get('minor')
                if maj is not None:
                    mn_str = str(minor) if minor is not None else 'auto'
                    print(f"Tick length (t>l): major={maj}, minor={mn_str}")

            # Toggle spines (t) - WASD visibility
            print("\n--- Toggle spines (t) ---")
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
                print(_colorize_inline_commands("Operando pane (t>o: a=left, w=top, s=bottom; 'd' not available):"))
                for side_key, side_name in [('left', 'a'), ('top', 'w'), ('bottom', 's')]:
                    s = op_wasd[side_key]
                    print(f"  {side_name}1:{_onoff(s['spine'])} {side_name}2:{_onoff(s['ticks'])} {side_name}3:{_onoff(s['minor'])} {side_name}4:{_onoff(s['labels'])} {side_name}5:{_onoff(s['title'])}")
            else:
                # Operando-only mode: all four sides available
                print(_colorize_inline_commands("Operando pane (t>o: a=left, w=top, s=bottom, d=right):"))
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
                print(_colorize_inline_commands("EC pane (t>e: w=top, s=bottom, d=right; 'a' not available):"))
                for side_key, side_name in [('top', 'w'), ('bottom', 's'), ('right', 'd')]:
                    s = ec_wasd[side_key]
                    print(f"  {side_name}1:{_onoff(s['spine'])} {side_name}2:{_onoff(s['ticks'])} {side_name}3:{_onoff(s['minor'])} {side_name}4:{_onoff(s['labels'])} {side_name}5:{_onoff(s['title'])}")
            else:
                ec_wasd = None

            print("=" * 60 + "\n")

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
            if ec_ax is None:
                _sm_parts = ["e=export", "q=return", "r=refresh"]
                if last_style_path:
                    _sm_parts.append("o=overwrite last")
                sub = _safe_input(_colorize_inline_commands(
                    "Style submenu: (" + ", ".join(_sm_parts) + "): "
                )).strip().lower()
            else:
                if last_style_path:
                    sub = _safe_input(_colorize_inline_commands(
                        "Style submenu: (e=export, o=overwrite last, q=return, r=refresh): "
                    )).strip().lower()
                else:
                    sub = _safe_input(_colorize_inline_commands(
                        "Style submenu: (e=export, q=return, r=refresh): "
                    )).strip().lower()
            if sub == 'q':
                break
            if sub == 'r' or sub == '':
                continue
            if sub == 'o':
                if not last_style_path:
                    print("No previous export found.")
                    continue
                if not os.path.exists(last_style_path):
                    print(f"Previous export file not found: {last_style_path}")
                    continue
                yn = _safe_input(f"Overwrite '{os.path.basename(last_style_path)}'? (y/n): ").strip().lower()
                if yn != 'y':
                    continue
                try:
                    with open(last_style_path, 'r', encoding='utf-8') as f:
                        old_cfg = json.load(f)
                    _ok = old_cfg.get('kind', '')
                    if _ok == 'operando_ec_style_geom':
                        _exp_reload = 'psg'
                    elif _ok == 'operando_ec_style':
                        _exp_reload = 'ps'
                    else:
                        print("Previous file is not a recognized operando style export.")
                        continue
                    _cfg_o, _ = _build_operando_ec_style_config_v2(fig, ax, im, cbar, ec_ax, _exp_reload)
                    with open(last_style_path, 'w', encoding='utf-8') as f:
                        json.dump(_cfg_o, f, indent=2)
                    print(f"Overwritten style to {last_style_path}")
                except Exception as e:
                    print(f"Overwrite failed: {e}")
                style_menu_active = False
                break
            if sub == 'e':
                print("Export options:")
                print("  " + _colorize_inline_commands("ps  = style only (.bps)"))
                print("  " + _colorize_inline_commands("psg = style + geometry (.bpsg)"))
                exp_choice = _safe_input(_colorize_inline_commands("Export choice (ps/psg, q=cancel): ")).strip().lower()
                if not exp_choice or exp_choice == 'q':
                    print("Style export canceled.")
                    continue
                if exp_choice not in ('ps', 'psg'):
                    print(f"Unknown option: {exp_choice}")
                    continue
                try:
                    cfg, default_ext = _build_operando_ec_style_config_v2(fig, ax, im, cbar, ec_ax, exp_choice)
                except Exception as e:
                    print(f"Could not build style config: {e}")
                    continue
                if exp_choice == 'psg':
                    geom = cfg['axes_geometry']
                    print("\n--- Geometry ---")
                    print(f"Operando X label: {geom['operando']['xlabel']}")
                    print(f"Operando Y label: {geom['operando']['ylabel']}")
                    print(f"Operando X limits: {geom['operando']['xlim'][0]:.4g} to {geom['operando']['xlim'][1]:.4g}")
                    print(f"Operando Y limits: {geom['operando']['ylim'][0]:.4g} to {geom['operando']['ylim'][1]:.4g}")
                    ec_geom = geom.get('ec')
                    if ec_geom:
                        print(f"EC X label: {ec_geom['xlabel']}")
                        print(f"EC Y label: {ec_geom['ylabel']}")
                        print(f"EC X limits: {ec_geom['xlim'][0]:.4g} to {ec_geom['xlim'][1]:.4g}")
                        print(f"EC Y limits: {ec_geom['ylim'][0]:.4g} to {ec_geom['ylim'][1]:.4g}")
                save_base = choose_save_path(file_paths, purpose="style export")
                if not save_base:
                    print("Style export canceled.")
                    continue
                print(f"\nChosen path: {save_base}")
                style_extensions = ('.bps', '.bpsg', '.bpcfg')
                file_list = list_files_in_subdirectory(style_extensions, 'style', base_path=save_base)
                _style_files = [f[0] for f in file_list]
                if _style_files:
                    styles_dir = os.path.join(save_base, 'Styles')
                    print(f"\nExisting {default_ext} files in {styles_dir}:")
                    for _i, (fname, fpath) in enumerate(file_list, 1):
                        timestamp = _format_file_timestamp(fpath)
                        if timestamp:
                            print(f"  {_i}: {fname}  ({timestamp})")
                        else:
                            print(f"  {_i}: {fname}")
                choice_name = _safe_input(_colorize_inline_commands("Enter new filename or number to overwrite (q=cancel): ")).strip()
                if not choice_name or choice_name.lower() == 'q':
                    print("Style export canceled.")
                    continue
                target = None
                if choice_name.isdigit() and _style_files:
                    _idx = int(choice_name)
                    if 1 <= _idx <= len(_style_files):
                        name = _style_files[_idx-1]
                        yn = _safe_input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                        if yn == 'y':
                            target = file_list[_idx-1][1]
                    else:
                        print("Invalid number.")
                        continue
                else:
                    name = choice_name
                    if not any(name.lower().endswith(ext) for ext in ['.bps', '.bpsg', '.bpcfg']):
                        name = name + default_ext
                    if os.path.isabs(name):
                        target = name
                    else:
                        target = get_organized_path(name, 'style', base_path=save_base)
                    if os.path.exists(target):
                        yn = _safe_input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
                        if yn != 'y':
                            target = None
                if target:
                    target = ensure_exact_case_filename(target)
                    with open(target, 'w', encoding='utf-8') as f:
                        json.dump(cfg, f, indent=2)
                    print(f"Exported style to {target}")
                    fig._last_style_export_path = target
                style_menu_active = False
                break
            print("Unknown choice.")
            continue
    except Exception as e:
        print(f"Error while printing/exporting style: {e}")
    print_menu()



def handle_import_style(ctx: OperandoActionContext) -> None:  # pyright: ignore[reportGeneralTypeIssues] - too complex for full analysis
    fig = ctx.fig
    ax = ctx.ax
    im = ctx.im
    cbar = ctx.cbar
    ec_ax = ctx.ec_ax
    file_paths = ctx.file_paths
    print_menu = ctx.print_menu
    _snapshot = ctx.snapshot
    set_fonts = ctx.set_fonts
    _maybe_reapply_dqdv_2d_contour = ctx.maybe_reapply_dqdv_2d_contour
    _restore_dqdv_2d_operando_labels = ctx.restore_dqdv_2d_operando_labels
    ax_w_in = ctx.ax_w_in
    ax_h_in = ctx.ax_h_in
    cb_w_in = ctx.cb_w_in
    cb_gap_in = ctx.cb_gap_in
    ec_gap_in = ctx.ec_gap_in
    ec_w_in = ctx.ec_w_in
    # Load a .bps/.bpsg/.bpcfg style and apply
    # Applies: oc, ow, ew, h, el, t, l, f, g, r, v; .bpsg also applies ox, oy, oz, or, et, ex, ey, er (axes_geometry + ec y_mode)
    try:
        path = choose_style_file(file_paths, purpose="style import")
        if not path:
            _sync_geometry(ctx, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)
            print_menu(); return
        _snapshot("import-style")
        with open(path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)

        # Check file type
        kind = cfg.get('kind', '')
        if kind not in ('operando_ec_style', 'operando_ec_style_geom'):
            print("Not a recognized operando style file (expected kind operando_ec_style or operando_ec_style_geom).")
            _sync_geometry(ctx, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)
            print_menu(); return

        d2_cfg = cfg.get('dqdv_2d')
        if d2_cfg and isinstance(d2_cfg, dict) and getattr(fig, '_is_dqdv_2d_contour', False):
            try:
                fig._dqdv_2d_v_lo = float(d2_cfg['v_lo'])
                fig._dqdv_2d_v_hi = float(d2_cfg['v_hi'])
                fig._dqdv_2d_row_labels = [str(s) for s in (d2_cfg.get('row_labels') or [])]
                if d2_cfg.get('zlabel') is not None:
                    fig._dqdv_2d_zlabel = str(d2_cfg['zlabel'])
                fig._dqdv_2d_axis_mapping_version = int(d2_cfg.get('axis_mapping_version', 2))
            except Exception:
                pass

        has_geometry = (kind == 'operando_ec_style_geom' and 'axes_geometry' in cfg)

        # Save current labelpad values BEFORE any style changes
        saved_op_xlabelpad = None
        saved_op_ylabelpad = None
        saved_ec_xlabelpad = None
        saved_ec_ylabelpad = None
        try:
            saved_op_xlabelpad = getattr(ax.xaxis, 'labelpad', None)
        except Exception:
            pass
        try:
            saved_op_ylabelpad = getattr(ax.yaxis, 'labelpad', None)
        except Exception:
            pass
        if ec_ax is not None:
            try:
                saved_ec_xlabelpad = getattr(ec_ax.xaxis, 'labelpad', None)
            except Exception:
                pass
            try:
                saved_ec_ylabelpad = getattr(ec_ax.yaxis, 'labelpad', None)
            except Exception:
                pass

        # Version check (support both v1 and v2)
        version = cfg.get('version', 1)

        # Fonts
        font = cfg.get('font', {})
        fam = font.get('family')
        size = font.get('size')
        mathtext_fs = font.get('mathtext_fontset')
        if mathtext_fs:
            try:
                plt.rcParams['mathtext.fontset'] = mathtext_fs
            except Exception:
                pass
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
                    # Restore horizontal offsets
                    cb_h_offset = geom.get('cb_h_offset', 0.0)
                    ec_h_offset = geom.get('ec_h_offset')
                    setattr(cbar.ax, '_cb_h_offset_in', float(cb_h_offset))
                    if ec_ax is not None:
                        if ec_h_offset is not None:
                            setattr(ec_ax, '_ec_h_offset_in', float(ec_h_offset))
                        else:
                            setattr(ec_ax, '_ec_h_offset_in', 0.0)
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
                # Store the colormap name explicitly so it can be retrieved reliably when saving
                setattr(im, '_operando_cmap_name', cmap)
                if cbar is not None:
                    _update_custom_colorbar(cbar.ax, im)
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
                        ax.xaxis.set_minor_locator(AutoMinorLocator())
                        ax.xaxis.set_minor_formatter(NullFormatter())
                    else:
                        # Clear minor locator if no minor ticks are enabled
                        ax.xaxis.set_minor_locator(NullLocator())
                        ax.xaxis.set_minor_formatter(NullFormatter())
                    ax.tick_params(axis='x', which='minor',
                                  top=bool(op_wasd.get('top', {}).get('minor', False)),
                                  bottom=bool(op_wasd.get('bottom', {}).get('minor', False)))
                    if op_wasd.get('left', {}).get('minor') or op_wasd.get('right', {}).get('minor'):
                        ax.yaxis.set_minor_locator(AutoMinorLocator())
                        ax.yaxis.set_minor_formatter(NullFormatter())
                    else:
                        # Clear minor locator if no minor ticks are enabled
                        ax.yaxis.set_minor_locator(NullLocator())
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
                    ax.xaxis.label.set_visible(bool(op_wasd.get('bottom', {}).get('title', True)))
                    ax.yaxis.label.set_visible(bool(op_wasd.get('left', {}).get('title', True)))
                except Exception as e:
                    print(f"Warning: Could not apply operando WASD state: {e}")

            # Apply operando spines
            op_spines = op.get('spines', {})
            if op_spines:
                try:
                    for name, props in op_spines.items():
                        sp = ax.spines.get(name)
                        if not sp:
                            continue
                        if 'linewidth' in props and props['linewidth'] is not None:
                            try:
                                sp.set_linewidth(float(props['linewidth']))
                            except Exception:
                                pass
                        if 'visible' in props and props['visible'] is not None:
                            try:
                                sp.set_visible(bool(props['visible']))
                            except Exception:
                                pass
                        if 'color' in props and props['color'] is not None:
                            try:
                                sp.set_edgecolor(props['color'])
                                if name in ('top', 'bottom'):
                                    ax.tick_params(axis='x', which='both', colors=props['color'])
                                    ax.xaxis.label.set_color(props['color'])
                                else:
                                    ax.tick_params(axis='y', which='both', colors=props['color'])
                                    ax.yaxis.label.set_color(props['color'])
                            except Exception:
                                pass
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
            _apply_tick_lengths(fig, ax, op.get('ticks', {}).get('lengths'))
            _apply_tick_style(fig, ax, op.get('ticks', {}))

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
                                     left=False,
                                     right=bool(ec_wasd.get('right', {}).get('ticks', True)),
                                     labelleft=False,
                                     labelright=bool(ec_wasd.get('right', {}).get('labels', True)))
                    # Apply minor ticks
                    if ec_wasd.get('top', {}).get('minor') or ec_wasd.get('bottom', {}).get('minor'):
                        ec_ax.xaxis.set_minor_locator(AutoMinorLocator())
                        ec_ax.xaxis.set_minor_formatter(NullFormatter())
                    else:
                        # Clear minor locator if no minor ticks are enabled
                        ec_ax.xaxis.set_minor_locator(NullLocator())
                        ec_ax.xaxis.set_minor_formatter(NullFormatter())
                    ec_ax.tick_params(axis='x', which='minor',
                                     top=bool(ec_wasd.get('top', {}).get('minor', False)),
                                     bottom=bool(ec_wasd.get('bottom', {}).get('minor', False)))
                    if ec_wasd.get('left', {}).get('minor') or ec_wasd.get('right', {}).get('minor'):
                        ec_ax.yaxis.set_minor_locator(AutoMinorLocator())
                        ec_ax.yaxis.set_minor_formatter(NullFormatter())
                    else:
                        # Clear minor locator if no minor ticks are enabled
                        ec_ax.yaxis.set_minor_locator(NullLocator())
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
                    ec_ax.xaxis.label.set_visible(bool(ec_wasd.get('bottom', {}).get('title', True)))
                    ec_right_title = bool(ec_wasd.get('right', {}).get('title', True))
                    if ec_right_title:
                        if not ec_ax.get_ylabel() and hasattr(ec_ax, '_stored_ylabel'):
                            ec_ax.set_ylabel(ec_ax._stored_ylabel)
                    else:
                        if not hasattr(ec_ax, '_stored_ylabel'):
                            ec_ax._stored_ylabel = ec_ax.get_ylabel()
                        ec_ax.set_ylabel('')
                except Exception as e:
                    print(f"Warning: Could not apply EC WASD state: {e}")

            # Apply EC spines
            ec_spines = ec_cfg.get('spines', {})
            if ec_spines:
                try:
                    for name, props in ec_spines.items():
                        sp = ec_ax.spines.get(name)
                        if not sp:
                            continue
                        if 'linewidth' in props and props['linewidth'] is not None:
                            try:
                                sp.set_linewidth(float(props['linewidth']))
                            except Exception:
                                pass
                        if 'visible' in props and props['visible'] is not None:
                            try:
                                sp.set_visible(bool(props['visible']))
                            except Exception:
                                pass
                        if 'color' in props and props['color'] is not None:
                            try:
                                sp.set_edgecolor(props['color'])
                                if name in ('top', 'bottom'):
                                    ec_ax.tick_params(axis='x', which='both', colors=props['color'])
                                    ec_ax.xaxis.label.set_color(props['color'])
                                else:
                                    ec_ax.tick_params(axis='y', which='both', colors=props['color'])
                                    ec_ax.yaxis.label.set_color(props['color'])
                            except Exception:
                                pass
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
            _apply_tick_lengths(fig, ec_ax, ec_cfg.get('ticks', {}).get('lengths'))
            _apply_tick_style(fig, ec_ax, ec_cfg.get('ticks', {}))

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

            if ec_ax is not None:
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
                    _safe_set_clim(im, float(intensity_range[0]), float(intensity_range[1]))
                    print(f"Applied intensity range: {intensity_range[0]:.4g} to {intensity_range[1]:.4g}")
            except Exception as e:
                print(f"Warning: Could not apply intensity range: {e}")

            # Apply CIF tick config (c command) if present and CIF data exists
            try:
                cif_cfg = cfg.get('cif', {})
                if cif_cfg and getattr(ax, '_operando_cif_tick_series', None):
                    fig._operando_cif_show_hkl = bool(cif_cfg.get('show_hkl', False))
                    fig._operando_cif_show_titles = bool(cif_cfg.get('show_titles', True))
                    fig._operando_cif_placement = str(cif_cfg.get('placement', 'below'))
                    y_pos = cif_cfg.get('y_positions', [])
                    fig._operando_cif_y_positions = list(y_pos) if y_pos else []
                    fig._operando_cif_colormap = cif_cfg.get('colormap')
                    fig._operando_cif_highlight = bool(cif_cfg.get('highlight', False))
                    fig._operando_cif_title_font = dict(cif_cfg.get('title_font') or {})
                    fig._operando_cif_title_visible = list(cif_cfg.get('title_visible') or [])
                    fig._operando_cif_set_visible = list(cif_cfg.get('set_visible') or [])
                    labels = cif_cfg.get('labels', [])
                    colors = cif_cfg.get('colors', [])
                    if labels or colors:
                        cif_series = list(ax._operando_cif_tick_series)
                        n_updates = max(len(labels), len(colors))
                        for idx in range(n_updates):
                            if idx < len(cif_series):
                                lab, fname, peaksQ, wl_e, qmax, _ = cif_series[idx]
                                if idx < len(labels) and labels[idx] is not None:
                                    lab = str(labels[idx])
                                col = colors[idx] if idx < len(colors) else cif_series[idx][-1]
                                cif_series[idx] = (lab, fname, peaksQ, wl_e, qmax, col)
                        ax._operando_cif_tick_series = cif_series
                    axis_mode = getattr(fig, '_operando_axis_mode', '2theta')
                    wl = getattr(fig, '_operando_wl', None)
                    cif_hkl_map = getattr(ax, '_operando_cif_hkl_label_map', {})
                    ax_pos = ax.get_position()
                    y_base = ax_pos.ymin - 0.02 if fig._operando_cif_placement == 'below' else ax_pos.ymax + 0.02
                    dy = -0.025 if fig._operando_cif_placement == 'below' else 0.025
                    while len(fig._operando_cif_y_positions) < len(ax._operando_cif_tick_series):
                        fig._operando_cif_y_positions.append(y_base + len(fig._operando_cif_y_positions) * dy)
                    _draw_operando_cif_ticks(ax, fig, ax._operando_cif_tick_series, cif_hkl_map, axis_mode=axis_mode, wl=wl,
                                             show_hkl=fig._operando_cif_show_hkl, show_titles=fig._operando_cif_show_titles,
                                             placement=fig._operando_cif_placement, y_positions=fig._operando_cif_y_positions)
                    print("Applied CIF tick config.")
            except Exception as e:
                print(f"Warning: Could not apply CIF config: {e}")

            # Apply ions mode (ey command)
            try:
                ec_cfg = cfg.get('ec', {})
                ec_y_mode = ec_cfg.get('y_mode', 'time')
                ion_params = ec_cfg.get('ion_params')

                if ec_y_mode == 'ions' and ion_params:
                    # Store parameters
                    ec_ax._ion_params = ion_params
                    ec_ax._ec_y_mode = 'ions'
                    if ec_cfg.get('prev_ec_xlim') is not None:
                        try:
                            ec_ax._prev_ec_xlim = tuple(ec_cfg.get('prev_ec_xlim'))
                        except Exception:
                            pass
                    ec_ax._ions_xlim_expanded = bool(ec_cfg.get('ions_xlim_expanded', False))

                    # Compute and apply ions formatter

                    time_h = getattr(ec_ax, '_ec_time_h', None)
                    current_mA = getattr(ec_ax, '_ec_current_mA', None)
                    voltage_v = getattr(ec_ax, '_ec_voltage_v', None)

                    if current_mA is None:
                        print("Error: Current data is required for ion counting but is not available in the .mpt file.")
                        print("The .mpt file must contain the '<I>/mA' column to use this feature.")
                        _sync_geometry(ctx, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)
                        print_menu()
                        return

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

                        ions_payload = ec_cfg.get('ions_abs')
                        if ions_payload is not None and len(ions_payload) == len(t):
                            ions_abs = np.asarray(ions_payload, float)
                        else:
                            ions_abs = float(ion_params.get('start_ions', 0.0)) + ions_delta
                        ec_ax._ions_abs = ions_abs

                        install_ec_ions_y_display(ec_ax, t, ions_abs)

                        # Update label if not custom
                        if not getattr(ec_ax, '_custom_labels', {}).get('y_ions'):
                            ec_ax.set_ylabel('Number of ions')
                        for a in getattr(ec_ax, '_ion_annots', []):
                            try:
                                a.remove()
                            except Exception:
                                pass
                        ec_ax._ion_annots = []
                        for gl in getattr(ec_ax, '_ion_guides', []):
                            try:
                                gl.remove()
                            except Exception:
                                pass
                        ec_ax._ion_guides = []
                        for y_guide in ec_cfg.get('ion_guides', []) or []:
                            try:
                                ec_ax._ion_guides.append(ec_ax.axhline(y=float(y_guide), color='0.7', linestyle='--', linewidth=0.8, alpha=0.5, zorder=0))
                            except Exception:
                                pass
                        for ann in ec_cfg.get('ion_annots', []) or []:
                            try:
                                txt = ec_ax.annotate(str(ann.get('text', '')), xy=tuple(ann.get('xy', (0.0, 0.0))), xytext=(0, 4), textcoords='offset points',
                                                     ha='right', va='bottom', fontsize=9,
                                                     bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='0.7', alpha=0.8))
                                ec_ax._ion_annots.append(txt)
                            except Exception:
                                pass

                        print("Applied ions mode")
            except Exception as e:
                print(f"Warning: Could not apply ions mode: {e}")

        # Apply visibility states (n command)
        if version >= 2:
            try:
                fig_cfg = cfg.get('figure', {})
                colorbar_cfg = cfg.get('colorbar', {})
                cb_visible = colorbar_cfg.get('visible')
                if cb_visible is None:
                    cb_visible = fig_cfg.get('cb_visible')
                if cb_visible is not None:
                    cbar.ax.set_visible(bool(cb_visible))

                # Restore colorbar label text and mode
                cb_label_mode = colorbar_cfg.get('mode', fig_cfg.get('cb_label_mode', 'highlow'))
                if cb_label_mode not in ('normal', 'highlow'):
                    cb_label_mode = 'highlow'
                fig._colorbar_label_mode = cb_label_mode
                cb_label_text = colorbar_cfg.get('label')
                if cb_label_text is not None:
                    cbar.ax._colorbar_label = cb_label_text
                try:
                    _update_custom_colorbar(
                        cbar.ax,
                        im,
                        label=cb_label_text if cb_label_text is not None else None,
                        label_mode=cb_label_mode,
                    )
                except Exception:
                    pass
            except Exception:
                pass
            try:
                ec_cfg = cfg.get('ec', {})
                ec_visible = ec_cfg.get('visible')
                if ec_visible is not None and ec_ax is not None:
                    ec_ax.set_visible(bool(ec_visible))
                ec_grid = ec_cfg.get('grid') or {}
                if ec_grid and ec_ax is not None:
                    g = dict(ec_grid)
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

        # Restore title offsets BEFORE applying labelpads
        if version >= 2:
            try:
                op_offsets = op.get('title_offsets', {})
                if op_offsets:
                    restore_title_offsets(ax, op_offsets)
            except Exception as e:
                print(f"Warning: Could not apply operando title offsets: {e}")

            try:
                ec_cfg = cfg.get('ec', {})
                ec_offsets = ec_cfg.get('title_offsets', {})
                if ec_offsets and ec_ax is not None:
                    restore_title_offsets(ec_ax, ec_offsets)
            except Exception as e:
                print(f"Warning: Could not apply EC title offsets: {e}")

        # Apply labelpads (title positioning) - preserve current if not in config
        if version >= 2:
            try:
                op_pads = op.get('labelpads', {})
                if op_pads:
                    if op_pads.get('x') is not None:
                        ax.xaxis.labelpad = op_pads['x']
                    elif saved_op_xlabelpad is not None:
                        ax.xaxis.labelpad = saved_op_xlabelpad
                    if op_pads.get('y') is not None:
                        ax.yaxis.labelpad = op_pads['y']
                    elif saved_op_ylabelpad is not None:
                        ax.yaxis.labelpad = saved_op_ylabelpad
                else:
                    # No labelpads in config, preserve current values
                    if saved_op_xlabelpad is not None:
                        ax.xaxis.labelpad = saved_op_xlabelpad
                    if saved_op_ylabelpad is not None:
                        ax.yaxis.labelpad = saved_op_ylabelpad
            except Exception as e:
                print(f"Warning: Could not apply operando labelpads: {e}")

            try:
                ec_cfg = cfg.get('ec', {})
                ec_pads = ec_cfg.get('labelpads', {})
                if ec_pads and ec_ax is not None:
                    if ec_pads.get('x') is not None:
                        ec_ax.xaxis.labelpad = ec_pads['x']
                    elif saved_ec_xlabelpad is not None:
                        ec_ax.xaxis.labelpad = saved_ec_xlabelpad
                    if ec_pads.get('y') is not None:
                        ec_ax.yaxis.labelpad = ec_pads['y']
                    elif saved_ec_ylabelpad is not None:
                        ec_ax.yaxis.labelpad = saved_ec_ylabelpad
                elif ec_ax is not None:
                    # No labelpads in config, preserve current values
                    if saved_ec_xlabelpad is not None:
                        ec_ax.xaxis.labelpad = saved_ec_xlabelpad
                    if saved_ec_ylabelpad is not None:
                        ec_ax.yaxis.labelpad = saved_ec_ylabelpad
            except Exception as e:
                print(f"Warning: Could not apply EC labelpads: {e}")

        # Reposition titles to apply offsets (after labelpads are set)
        try:
            # Build tick_state for operando pane
            op_ts = getattr(ax, '_saved_tick_state', {})
            op_tick_state = {
                't_ticks': bool(op_ts.get('t_ticks', op_ts.get('tx', False))),
                't_labels': bool(op_ts.get('t_labels', op_ts.get('tx', False))),
                'b_ticks': bool(op_ts.get('b_ticks', op_ts.get('bx', True))),
                'b_labels': bool(op_ts.get('b_labels', op_ts.get('bx', True))),
                'l_ticks': bool(op_ts.get('l_ticks', op_ts.get('ly', True))),
                'l_labels': bool(op_ts.get('l_labels', op_ts.get('ly', True))),
                'r_ticks': bool(op_ts.get('r_ticks', op_ts.get('ry', False))),
                'r_labels': bool(op_ts.get('r_labels', op_ts.get('ry', False))),
            }
            _ui_position_top_xlabel(ax, fig, op_tick_state)
            _ui_position_bottom_xlabel(ax, fig, op_tick_state)
            _ui_position_left_ylabel(ax, fig, op_tick_state)
            _ui_position_right_ylabel(ax, fig, op_tick_state)
            if ec_ax is not None:
                ec_ts = getattr(ec_ax, '_saved_tick_state', {})
                ec_tick_state = {
                    't_ticks': bool(ec_ts.get('t_ticks', ec_ts.get('tx', False))),
                    't_labels': bool(ec_ts.get('t_labels', ec_ts.get('tx', False))),
                    'b_ticks': bool(ec_ts.get('b_ticks', ec_ts.get('bx', True))),
                    'b_labels': bool(ec_ts.get('b_labels', ec_ts.get('bx', True))),
                    'l_ticks': bool(ec_ts.get('l_ticks', ec_ts.get('ly', True))),
                    'l_labels': bool(ec_ts.get('l_labels', ec_ts.get('ly', True))),
                    'r_ticks': bool(ec_ts.get('r_ticks', ec_ts.get('ry', False))),
                    'r_labels': bool(ec_ts.get('r_labels', ec_ts.get('ry', False))),
                }
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
        except Exception as e:
            print(f"Warning: Could not reposition titles: {e}")

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
                _is_d2 = bool(getattr(fig, '_is_dqdv_2d_contour', False))

                if not _is_d2:
                    if op_geom.get('xlabel'):
                        ax.set_xlabel(op_geom['xlabel'])
                    if op_geom.get('ylabel'):
                        ax.set_ylabel(op_geom['ylabel'])
                if 'xlim' in op_geom and isinstance(op_geom['xlim'], list) and len(op_geom['xlim']) == 2:
                    if not _is_d2:
                        ax.set_xlim(op_geom['xlim'][0], op_geom['xlim'][1])
                if 'ylim' in op_geom and isinstance(op_geom['ylim'], list) and len(op_geom['ylim']) == 2:
                    ax.set_ylim(op_geom['ylim'][0], op_geom['ylim'][1])

                if ec_ax is not None and ec_geom:
                    if ec_geom.get('xlabel'):
                        ec_ax.set_xlabel(ec_geom['xlabel'])
                    if ec_geom.get('ylabel'):
                        ec_ax.set_ylabel(ec_geom['ylabel'])
                    if 'xlim' in ec_geom and isinstance(ec_geom['xlim'], list) and len(ec_geom['xlim']) == 2:
                        ec_ax.set_xlim(ec_geom['xlim'][0], ec_geom['xlim'][1])
                    if 'ylim' in ec_geom and isinstance(ec_geom['ylim'], list) and len(ec_geom['ylim']) == 2:
                        ec_ax.set_ylim(ec_geom['ylim'][0], ec_geom['ylim'][1])
                        if getattr(ec_ax, '_ec_y_mode', 'time') == 'time':
                            try:
                                ec_ax._saved_time_ylim = tuple(ec_geom['ylim'])
                            except Exception:
                                pass

                print("Applied geometry (labels and limits)")
                fig.canvas.draw_idle()
            except Exception as e:
                print(f"Warning: Could not apply geometry: {e}")

        _maybe_reapply_dqdv_2d_contour(fig, ax, im, cbar)
        if getattr(fig, '_is_dqdv_2d_contour', False):
            geom = cfg.get('axes_geometry', {}) if has_geometry else {}
            op_geom = geom.get('operando', {}) if isinstance(geom, dict) else {}
            op_l = {
                'x': op_geom.get('xlabel') if op_geom.get('xlabel') else ax.get_xlabel(),
                'y': op_geom.get('ylabel') if op_geom.get('ylabel') else ax.get_ylabel(),
            }
            _restore_dqdv_2d_operando_labels(ax, op_l)

        print(f"Applied style from {path}")
    except Exception as e:
        print(f"Load style failed: {e}")
    _sync_geometry(ctx, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)
    print_menu()


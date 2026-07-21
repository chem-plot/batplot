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
from ..common.crosshair_export import savefig_without_crosshair
from ...ui import position_top_xlabel as _ui_position_top_xlabel
from ...ui import position_right_ylabel as _ui_position_right_ylabel
from ...ui import position_bottom_xlabel as _ui_position_bottom_xlabel
from ...ui import position_left_ylabel as _ui_position_left_ylabel
from ...ui import restore_axes_tick_locators
from ...ui import set_spine_side_color as _ui_set_spine_side_color
from ...ui import finalize_spine_colors_for_axes
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
from ..common.font_extras import apply_font_extras_from_cfg, refresh_font_extras_on_artists
from ..common.fonts import collect_operando_font_artists
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
    pop_undo: Callable[[], None]
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
                savefig_without_crosshair(fig, target, dpi=300, transparent=True, facecolor='none', edgecolor='none')
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
            savefig_without_crosshair(fig, target, dpi=300)
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
                savefig_without_crosshair(fig, last_figure_path, dpi=300, transparent=True, facecolor='none', edgecolor='none')
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
            savefig_without_crosshair(fig, last_figure_path, dpi=300)
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
        if getattr(fig, "_is_dqdv_2d_contour", False):
            # Must match ``s`` → build_dqdv_2d_snapshot (kind=dqdv_2d_contour).
            # dump_operando_session would write operando_ec and break reload.
            import pickle

            from ..electrochem.dqdv_2d import build_dqdv_2d_snapshot

            try:
                v_lo = float(fig._dqdv_2d_v_lo)
                v_hi = float(fig._dqdv_2d_v_hi)
                row_labels = [str(s) for s in (fig._dqdv_2d_row_labels or [])]
                zlab = str(getattr(fig, "_dqdv_2d_zlabel", "dQ/dV"))
            except Exception:
                print("Error: missing dQ/dV 2D axis metadata on this figure.")
                print_menu()
                return
            snap = build_dqdv_2d_snapshot(
                fig, ctx.ax, ctx.im, v_lo, v_hi, row_labels, zlab, ctx.cbar
            )
            if snap is None:
                print("Error: could not build dQ/dV 2D session snapshot.")
                print_menu()
                return
            with open(last_session_path, "wb") as fh:
                pickle.dump(snap, fh)
            print(f"Overwritten dQ/dV 2D session to {last_session_path}")
        else:
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



def handle_import_style(ctx: OperandoActionContext) -> None:
    """Import operando/dQdV style via the shared ``apply_operando_ec_style_config`` path."""
    fig = ctx.fig
    ax = ctx.ax
    im = ctx.im
    cbar = ctx.cbar
    ec_ax = ctx.ec_ax
    file_paths = ctx.file_paths
    print_menu = ctx.print_menu
    _snapshot = ctx.snapshot
    _pop_undo = ctx.pop_undo
    ax_w_in = ctx.ax_w_in
    ax_h_in = ctx.ax_h_in
    cb_w_in = ctx.cb_w_in
    cb_gap_in = ctx.cb_gap_in
    ec_gap_in = ctx.ec_gap_in
    ec_w_in = ctx.ec_w_in
    try:
        path = choose_style_file(file_paths, purpose="style import")
        if not path:
            _sync_geometry(ctx, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)
            print_menu()
            return
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        kind = cfg.get("kind", "")
        if kind not in ("operando_ec_style", "operando_ec_style_geom"):
            print("Not a recognized operando style file (expected kind operando_ec_style or operando_ec_style_geom).")
            _sync_geometry(ctx, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)
            print_menu()
            return
        _snapshot("import-style")
        # Lazy import avoids circular import at module load (style_apply imports actions helpers).
        from .style_apply import apply_operando_ec_style_config
        from .layout import _ensure_fixed_params

        ok = apply_operando_ec_style_config(
            cfg, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax, silent=False
        )
        if not ok:
            try:
                _pop_undo()
            except Exception:
                pass
        else:
            print(f"Applied style from {path}")
        try:
            cb_w_in, cb_gap_in, ec_gap_in, ec_w_in, ax_w_in, ax_h_in = _ensure_fixed_params(
                fig, ax, cbar.ax, ec_ax
            )
        except Exception:
            pass
    except Exception as e:
        try:
            _pop_undo()
        except Exception:
            pass
        print(f"Load style failed: {e}")
    _sync_geometry(ctx, ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in)
    print_menu()



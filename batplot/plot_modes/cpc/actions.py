"""Action handlers for the CPC interactive menu."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
import json
import os

from ..common.crosshair_export import savefig_without_crosshair
from ..common.files import confirm_previous_path


@dataclass
class CpcActionContext:
    """Runtime objects and callbacks shared by CPC command handlers."""

    fig: Any
    ax: Any
    ax2: Any
    sc_charge: Any
    sc_discharge: Any
    sc_eff: Any
    file_data: Any
    file_paths: Any
    is_multi_file: bool
    tick_state: dict
    safe_input: Callable[..., str]
    colorize_prompt: Callable[[str], str]
    colorize_inline_commands: Callable[[str], str]
    print_menu: Callable[..., None]
    choose_save_path: Callable[..., Any]
    choose_style_file: Callable[..., Any]
    list_files_in_subdirectory: Callable[..., Any]
    get_organized_path: Callable[..., str]
    ensure_exact_case_filename: Callable[[str], str]
    natural_sort_key: Callable[..., Any]
    dump_cpc_session: Callable[..., Any]
    format_file_timestamp: Callable[[str], str]
    rebuild_legend: Callable[..., Any]
    style_snapshot: Callable[..., dict]
    apply_style: Callable[..., Any]
    get_geometry_snapshot: Callable[..., dict]
    push_state: Callable[[str], Any]
    pop_undo: Callable[[], Any]
    restore_state: Callable[[], Any]


def _build_cpc_style_export_config(ctx: CpcActionContext, exp_choice: str) -> tuple[dict, str]:
    """Build the canonical CPC style payload for normal export and overwrite."""
    snap = ctx.style_snapshot(
        ctx.fig,
        ctx.ax,
        ctx.ax2,
        ctx.sc_charge,
        ctx.sc_discharge,
        ctx.sc_eff,
        ctx.file_data,
    )
    if exp_choice == "psg":
        snap["kind"] = "cpc_style_geom"
        snap["geometry"] = ctx.get_geometry_snapshot(ctx.ax, ctx.ax2)
        return snap, ".bpsg"
    snap["kind"] = "cpc_style"
    return snap, ".bps"


def handle_undo(ctx: CpcActionContext) -> None:
    """Revert the last CPC interactive change and redraw the menu."""
    ctx.restore_state()
    ctx.print_menu(ctx.fig)


def handle_figure_export(ctx: CpcActionContext) -> None:
    """Handle CPC figure export."""
    fig = ctx.fig
    ax = ctx.ax
    ax2 = ctx.ax2
    file_data = ctx.file_data
    is_multi_file = ctx.is_multi_file
    _safe_input = ctx.safe_input
    _print_menu = ctx.print_menu

    try:
        base_path = ctx.choose_save_path(ctx.file_paths, purpose="figure export")
        if not base_path:
            _print_menu(fig)
            return
        print(f"\nChosen path: {base_path}")
        # List existing figure files from Figures/ subdirectory
        fig_extensions = ('.svg', '.png', '.jpg', '.jpeg', '.pdf', '.eps', '.tif', '.tiff')
        file_list = ctx.list_files_in_subdirectory(fig_extensions, 'figure', base_path=base_path)
        files = [f[0] for f in file_list]
        if files:
            figures_dir = os.path.join(base_path, 'Figures')
            print(f"Existing figure files in {figures_dir}:")
            for i, (fname, fpath) in enumerate(file_list, 1):
                timestamp = ctx.format_file_timestamp(fpath)
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
            _print_menu(fig)
            return

        target = None
        # Check for 'o' option
        if fname.lower() == 'o':
            if not last_figure_path:
                print("No previous export found.")
                _print_menu(fig)
                return
            if not os.path.exists(last_figure_path):
                print(f"Previous export file not found: {last_figure_path}")
                _print_menu(fig)
                return
            yn = _safe_input(f"Overwrite '{os.path.basename(last_figure_path)}'? (y/n): ").strip().lower()
            if yn != 'y':
                _print_menu(fig)
                return
            target = last_figure_path
        # Check if user selected a number
        elif fname.isdigit() and files:
            idx = int(fname)
            if 1 <= idx <= len(files):
                name = files[idx-1]
                yn = _safe_input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                if yn != 'y':
                    _print_menu(fig)
                    return
                target = file_list[idx-1][1]  # Full path from list
            else:
                print("Invalid number.")
                _print_menu(fig)
                return
        else:
            root, ext = os.path.splitext(fname)
            if ext == '':
                fname = fname + '.svg'
            # Use organized path unless it's an absolute path
            if os.path.isabs(fname):
                target = fname
            else:
                target = ctx.get_organized_path(fname, 'figure', base_path=base_path)
            if os.path.exists(target):
                yn = _safe_input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
                if yn != 'y':
                    _print_menu(fig)
                    return
        if target:
            # Ensure exact case is preserved (important for macOS case-insensitive filesystem)
            target = ctx.ensure_exact_case_filename(target)

            # Save current legend position before export (savefig can change layout)
            saved_legend_pos = None
            try:
                saved_legend_pos = getattr(fig, '_cpc_legend_xy_in', None)
            except Exception:
                pass

            # Remove numbering from legend labels before export
            original_labels = {}
            if is_multi_file:
                try:
                    for i, f in enumerate(file_data, 1):
                        # Store original labels
                        original_labels[f['sc_charge']] = f['sc_charge'].get_label()
                        original_labels[f['sc_discharge']] = f['sc_discharge'].get_label()
                        original_labels[f['sc_eff']] = f['sc_eff'].get_label()

                        # Remove "N. " prefix from labels
                        base_label = f['filename']
                        f['sc_charge'].set_label(f'{base_label} charge')
                        f['sc_discharge'].set_label(f'{base_label} discharge')
                        f['sc_eff'].set_label(f'{base_label} efficiency')

                    # Rebuild legend without numbers
                    ctx.rebuild_legend(ax, ax2, file_data)
                except Exception:
                    pass

            # Export the figure
            _, _ext = os.path.splitext(target)
            if _ext.lower() == '.svg':
                # Temporarily force transparent patches so SVG background stays transparent
                try:
                    _fig_fc = fig.get_facecolor()
                except Exception:
                    _fig_fc = None
                try:
                    _ax_fc = ax.get_facecolor()
                except Exception:
                    _ax_fc = None
                try:
                    _ax2_fc = ax2.get_facecolor()
                except Exception:
                    _ax2_fc = None
                try:
                    if getattr(fig, 'patch', None) is not None:
                        fig.patch.set_alpha(0.0)
                        fig.patch.set_facecolor('none')
                    if getattr(ax, 'patch', None) is not None:
                        ax.patch.set_alpha(0.0)
                        ax.patch.set_facecolor('none')
                    if getattr(ax2, 'patch', None) is not None:
                        ax2.patch.set_alpha(0.0)
                        ax2.patch.set_facecolor('none')
                except Exception:
                    pass
                try:
                    savefig_without_crosshair(fig, target, bbox_inches='tight', transparent=True, facecolor='none', edgecolor='none', dpi=fig.dpi)
                finally:
                    try:
                        if _fig_fc is not None and getattr(fig, 'patch', None) is not None:
                            fig.patch.set_alpha(1.0)
                            fig.patch.set_facecolor(_fig_fc)
                    except Exception:
                        pass
                    try:
                        if _ax_fc is not None and getattr(ax, 'patch', None) is not None:
                            ax.patch.set_alpha(1.0)
                            ax.patch.set_facecolor(_ax_fc)
                    except Exception:
                        pass
                    try:
                        if _ax2_fc is not None and getattr(ax2, 'patch', None) is not None:
                            ax2.patch.set_alpha(1.0)
                            ax2.patch.set_facecolor(_ax2_fc)
                    except Exception:
                        pass
                print(f"Exported figure to {target}")
                fig._last_figure_export_path = target

                # Restore original labels and legend position
                if is_multi_file and original_labels:
                    try:
                        for artist, label in original_labels.items():
                            artist.set_label(label)
                        ctx.rebuild_legend(ax, ax2, file_data)
                    except Exception:
                        pass
                # Restore legend position after savefig (which may have changed layout)
                if saved_legend_pos is not None:
                    try:
                        fig._cpc_legend_xy_in = saved_legend_pos
                        ctx.rebuild_legend(ax, ax2, file_data)
                        fig.canvas.draw_idle()
                    except Exception:
                        pass
            else:
                savefig_without_crosshair(fig, target, bbox_inches='tight', dpi=fig.dpi)
                print(f"Exported figure to {target}")
                fig._last_figure_export_path = target

                # Restore original labels and legend position
                if is_multi_file and original_labels:
                    try:
                        for artist, label in original_labels.items():
                            artist.set_label(label)
                        ctx.rebuild_legend(ax, ax2, file_data)
                    except Exception:
                        pass
                # Restore legend position after savefig (which may have changed layout)
                if saved_legend_pos is not None:
                    try:
                        fig._cpc_legend_xy_in = saved_legend_pos
                        ctx.rebuild_legend(ax, ax2, file_data)
                        fig.canvas.draw_idle()
                    except Exception:
                        pass
    except Exception as e:
        print(f"Export failed: {e}")
    _print_menu(fig)


def handle_save_session(ctx: CpcActionContext) -> None:
    """Save CPC session data and style to a project pickle."""
    fig = ctx.fig
    ax = ctx.ax
    ax2 = ctx.ax2
    sc_charge = ctx.sc_charge
    sc_discharge = ctx.sc_discharge
    sc_eff = ctx.sc_eff
    file_data = ctx.file_data
    tick_state = ctx.tick_state
    _safe_input = ctx.safe_input
    _print_menu = ctx.print_menu

    try:
        # Sync current tick/title visibility (including minors) into stored WASD state before save
        try:
            wasd = getattr(fig, '_cpc_wasd_state', {})
            if not isinstance(wasd, dict):
                wasd = {}
            # bottom
            w = wasd.setdefault('bottom', {})
            w['ticks'] = bool(tick_state.get('b_ticks', tick_state.get('bx', True)))
            w['labels'] = bool(tick_state.get('b_labels', tick_state.get('bx', True)))
            w['minor'] = bool(tick_state.get('mbx', False))
            w['title'] = bool(ax.xaxis.label.get_visible())
            try:
                sp = ax.spines.get('bottom')
                w['spine'] = bool(sp.get_visible()) if sp else w.get('spine', True)
            except Exception:
                pass
            # top
            w = wasd.setdefault('top', {})
            w['ticks'] = bool(tick_state.get('t_ticks', tick_state.get('tx', False)))
            w['labels'] = bool(tick_state.get('t_labels', tick_state.get('tx', False)))
            w['minor'] = bool(tick_state.get('mtx', False))
            w['title'] = bool(getattr(ax, '_top_xlabel_on', False))
            try:
                sp = ax.spines.get('top')
                w['spine'] = bool(sp.get_visible()) if sp else w.get('spine', False)
            except Exception:
                pass
            # left
            w = wasd.setdefault('left', {})
            w['ticks'] = bool(tick_state.get('l_ticks', tick_state.get('ly', True)))
            w['labels'] = bool(tick_state.get('l_labels', tick_state.get('ly', True)))
            w['minor'] = bool(tick_state.get('mly', False))
            w['title'] = bool(ax.yaxis.label.get_visible())
            try:
                sp = ax.spines.get('left')
                w['spine'] = bool(sp.get_visible()) if sp else w.get('spine', True)
            except Exception:
                pass
            # right
            w = wasd.setdefault('right', {})
            w['ticks'] = bool(tick_state.get('r_ticks', tick_state.get('ry', True)))
            w['labels'] = bool(tick_state.get('r_labels', tick_state.get('ry', True)))
            w['minor'] = bool(tick_state.get('mry', False))
            w['title'] = bool(ax2.yaxis.label.get_visible() if ax2 is not None else False)
            try:
                sp = ax2.spines.get('right') if ax2 is not None else None
                w['spine'] = bool(sp.get_visible()) if sp else w.get('spine', True)
            except Exception:
                pass
            setattr(fig, '_cpc_wasd_state', wasd)
        except Exception:
            pass
        folder = ctx.choose_save_path(ctx.file_paths, purpose="CPC session save")
        if not folder:
            _print_menu(fig)
            return
        print(f"\nChosen path: {folder}")
        try:
            files = sorted([f for f in os.listdir(folder) if f.lower().endswith('.pkl')], key=ctx.natural_sort_key)
        except Exception:
            files = []
        if files:
            print("Existing .pkl files:")
            for i, f in enumerate(files, 1):
                filepath = os.path.join(folder, f)
                timestamp = ctx.format_file_timestamp(filepath)
                if timestamp:
                    print(f"  {i}: {f}  ({timestamp})")
                else:
                    print(f"  {i}: {f}")
        last_session_path = getattr(fig, '_last_session_save_path', None)
        if last_session_path:
            prompt = "Enter new filename (no ext needed), number to overwrite, or o to overwrite last (q=cancel): "
        else:
            prompt = "Enter new filename (no ext needed) or number to overwrite (q=cancel): "
        choice = _safe_input(prompt).strip()
        if not choice or choice.lower() == 'q':
            _print_menu(fig)
            return
        if choice.lower() == 'o':
            # Overwrite last saved session
            if not last_session_path:
                print("No previous save found.")
                _print_menu(fig)
                return
            if not os.path.exists(last_session_path):
                print(f"Previous save file not found: {last_session_path}")
                _print_menu(fig)
                return
            yn = _safe_input(f"Overwrite '{os.path.basename(last_session_path)}'? (y/n): ").strip().lower()
            if yn != 'y':
                _print_menu(fig)
                return
            ctx.dump_cpc_session(
                last_session_path,
                fig=fig,
                ax=ax,
                ax2=ax2,
                sc_charge=sc_charge,
                sc_discharge=sc_discharge,
                sc_eff=sc_eff,
                file_data=file_data,
                skip_confirm=True,
            )
            print(f"Overwritten session to {last_session_path}")
            _print_menu(fig)
            return
        if choice.isdigit() and files:
            idx = int(choice)
            if 1 <= idx <= len(files):
                name = files[idx-1]
                yn = _safe_input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                if yn != 'y':
                    _print_menu(fig)
                    return
                target = os.path.join(folder, name)
                ctx.dump_cpc_session(
                    target,
                    fig=fig,
                    ax=ax,
                    ax2=ax2,
                    sc_charge=sc_charge,
                    sc_discharge=sc_discharge,
                    sc_eff=sc_eff,
                    file_data=file_data,
                    skip_confirm=True,
                )
                fig._last_session_save_path = target
                _print_menu(fig)
                return
            else:
                print("Invalid number.")
                _print_menu(fig)
                return
        if choice.lower() != 'o':
            name = choice
            root, ext = os.path.splitext(name)
            if ext == '':
                name = name + '.pkl'
            target = name if os.path.isabs(name) else os.path.join(folder, name)
            if os.path.exists(target):
                yn = _safe_input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
                if yn != 'y':
                    _print_menu(fig)
                    return
            ctx.dump_cpc_session(
                target,
                fig=fig,
                ax=ax,
                ax2=ax2,
                sc_charge=sc_charge,
                sc_discharge=sc_discharge,
                sc_eff=sc_eff,
                file_data=file_data,
                skip_confirm=True,
            )
            fig._last_session_save_path = target
    except Exception as e:
        print(f"Save failed: {e}")
    _print_menu(fig)


def handle_style_export(ctx: CpcActionContext) -> None:
    """Handle CPC style/geometry summary and export."""
    fig = ctx.fig
    ax = ctx.ax
    ax2 = ctx.ax2
    sc_charge = ctx.sc_charge
    sc_discharge = ctx.sc_discharge
    sc_eff = ctx.sc_eff
    file_data = ctx.file_data
    _safe_input = ctx.safe_input
    _print_menu = ctx.print_menu
    _colorize_prompt = ctx.colorize_prompt
    _colorize_inline_commands = ctx.colorize_inline_commands

    try:
        style_menu_active = True
        while style_menu_active:
            # Print style info first
            snap = ctx.style_snapshot(fig, ax, ax2, sc_charge, sc_discharge, sc_eff, file_data)
            snap['kind'] = 'cpc_style'  # Default, will be updated if psg is chosen

            def _onoff(v):
                return 'ON ' if bool(v) else 'off'

            print("\n" + "=" * 60)
            print("  CPC STYLE SUMMARY")
            print("=" * 60)
            print("Commands (Styles): f, l, m, c, d, ry, t, h, g, v | Geometries: r, x, y, ie")
            print()

            # ---- Canvas & Geometry (g) ----
            fig_cfg = snap.get('figure', {})
            canvas = fig_cfg.get('canvas_size')
            frame = fig_cfg.get('frame_size')
            print("--- Canvas & Geometry ---")
            if canvas and all(v is not None for v in canvas):
                print(f"Canvas size (g): {canvas[0]:.3f} x {canvas[1]:.3f} in")
            if frame and all(v is not None for v in frame):
                print(f"Plot frame: {frame[0]:.3f} x {frame[1]:.3f} in")

            # ---- Font (f) ----
            ft = snap.get('font', {})
            print(f"\n--- Font (f) ---")
            print(f"Family='{ft.get('family', '')}', size={ft.get('size', '')}")

            # ---- Toggle spines (t) ----
            wasd = snap.get('wasd_state', {})
            if wasd:
                print(f"\n--- Toggle spines (t) ---")
                print("WASD (w=top, a=left, s=bottom, d=right): 1=spine 2=ticks 3=minor 4=labels 5=title")
                for side_key, side_label in [('top', 'w'), ('left', 'a'), ('bottom', 's'), ('right', 'd')]:
                    s = wasd.get(side_key, {})
                    print(f"  {side_label}1:{_onoff(s.get('spine', False))} {side_label}2:{_onoff(s.get('ticks', False))} {side_label}3:{_onoff(s.get('minor', False))} {side_label}4:{_onoff(s.get('labels', False))} {side_label}5:{_onoff(s.get('title', False))}")

            # ---- Line widths (l) ----
            spines = snap.get('spines', {})
            ticks = snap.get('ticks', {})
            frame_lw = spines.get('bottom', {}).get('linewidth', '?') if spines else '?'
            print(f"\n--- Line widths (l) ---")
            print(f"Frame: {frame_lw}")
            print(f"Ticks: x=({ticks.get('x_major_width')}, {ticks.get('x_minor_width')})  ly=({ticks.get('ly_major_width')}, {ticks.get('ly_minor_width')})  ry=({ticks.get('ry_major_width')}, {ticks.get('ry_minor_width')})")
            print(f"Tick direction: {ticks.get('direction', 'out')}")

            # ---- Spines (k) ----
            if spines:
                print("\n--- Spines (k) ---")
                for name in ('bottom', 'top', 'left', 'right'):
                    props = spines.get(name, {})
                    lw = props.get('linewidth', '?')
                    vis = props.get('visible', False)
                    col = props.get('color')
                    print(f"  {name:<6} lw={lw} visible={vis} color={col}")
            spine_colors = snap.get('spine_colors', {})
            if spine_colors:
                print("Spine colors (k):")
                for name, color in spine_colors.items():
                    print(f"  {name}: {color}")
            spine_auto = snap.get('spine_colors_auto', False)
            if spine_auto:
                print(f"  Auto: ON (capacity→left, efficiency→right)")

            # ---- Grid ----
            grid_enabled = snap.get('grid', False)
            print(f"\n--- Grid ---")
            print(f"Grid: {'on' if grid_enabled else 'off'}")

            # ---- Multi-file (v) ----
            multi_files = snap.get('multi_files', [])
            if multi_files:
                print("\n--- Multi-file visibility (v) ---")
                for i, finfo in enumerate(multi_files, 1):
                    vis_mark = "●" if finfo.get('visible', True) else "○"
                    fname = finfo.get('filename', 'unknown')
                    ch_col = finfo.get('charge_color', 'N/A')
                    dh_col = finfo.get('discharge_color', 'N/A')
                    ef_col = finfo.get('efficiency_color', 'N/A')
                    print(f"  {i}. {vis_mark} {fname}")
                    print(f"     charge={ch_col}, discharge={dh_col}, efficiency={ef_col}")

            # ---- Series (c, m, ry) ----
            s = snap.get('series', {})
            ch = s.get('charge', {})
            dh = s.get('discharge', {})
            ef = s.get('efficiency', {})
            print(f"\n--- Series (c, m, ry) ---")
            if not multi_files:
                print(f"Charge: color={ch.get('color')}, markersize={ch.get('markersize')}, alpha={ch.get('alpha')}")
                print(f"Discharge: color={dh.get('color')}, markersize={dh.get('markersize')}, alpha={dh.get('alpha')}")
                print(f"Efficiency: color={ef.get('color')}, markersize={ef.get('markersize')}, alpha={ef.get('alpha')}, visible={ef.get('visible')}")
            else:
                print(f"Marker sizes (m): charge={ch.get('markersize')}, discharge={dh.get('markersize')}, efficiency={ef.get('markersize')}")
                print(f"Alpha: charge={ch.get('alpha')}, discharge={dh.get('alpha')}, efficiency={ef.get('alpha')}")
                print(f"Efficiency visible (ry): {ef.get('visible')}")

            # ---- Legend (h) ----
            leg_cfg = snap.get('legend', {})
            leg_vis = leg_cfg.get('visible', False)
            leg_pos = leg_cfg.get('position_inches')
            leg_single = leg_cfg.get('single_file_effective', False)
            print(f"\n--- Legend (h) ---")
            if leg_pos:
                print(f"Visible: {leg_vis}, position=({leg_pos[0]:.3f}, {leg_pos[1]:.3f}) in (rel. center)")
            else:
                print(f"Visible: {leg_vis}, position=auto")
            if multi_files:
                print(f"Legend mode: {'single-file (1 visible)' if leg_single else 'multi-file'}")

            print("=" * 60 + "\n")

            # List available style files (.bps, .bpsg, .bpcfg) in Styles/ subdirectory
            style_file_list = ctx.list_files_in_subdirectory(('.bps', '.bpsg', '.bpcfg'), 'style')
            _bpcfg_files = [f[0] for f in style_file_list]
            if _bpcfg_files:
                print("Existing style files in Styles/ (.bps/.bpsg):")
                for _i, (fname, fpath) in enumerate(style_file_list, 1):
                    timestamp = ctx.format_file_timestamp(fpath)
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
                    if old_cfg.get('kind') == 'cpc_style_geom':
                        snap, _default_ext = _build_cpc_style_export_config(ctx, 'psg')
                    else:
                        snap, _default_ext = _build_cpc_style_export_config(ctx, 'ps')
                except Exception:
                    snap, _default_ext = _build_cpc_style_export_config(ctx, 'ps')
                with open(last_style_path, 'w', encoding='utf-8') as f:
                    json.dump(snap, f, indent=2)
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
                    snap, default_ext = _build_cpc_style_export_config(ctx, 'ps')
                elif exp_choice == 'psg':
                    # Style + Geometry
                    snap, default_ext = _build_cpc_style_export_config(ctx, 'psg')
                    geom = snap.get('geometry', {})
                    print("\n--- Geometry ---")
                    print(f"X-axis label: {geom.get('xlabel', '')}")
                    print(f"Y-axis label (left): {geom.get('ylabel_left', '')}")
                    if 'ylabel_right' in geom:
                        print(f"Y-axis label (right): {geom.get('ylabel_right', '')}")
                    xlim = geom.get('xlim', [])
                    if xlim and len(xlim) == 2:
                        print(f"X limits: {xlim[0]:.4g} to {xlim[1]:.4g}")
                    ylim_l = geom.get('ylim_left', [])
                    if ylim_l and len(ylim_l) == 2:
                        print(f"Y limits (left): {ylim_l[0]:.4g} to {ylim_l[1]:.4g}")
                    ylim_r = geom.get('ylim_right', [])
                    if ylim_r and len(ylim_r) == 2:
                        print(f"Y limits (right): {ylim_r[0]:.4g} to {ylim_r[1]:.4g}")
                else:
                    print(f"Unknown option: {exp_choice}")
                    continue

                save_base = ctx.choose_save_path(ctx.file_paths, purpose="style export")
                if not save_base:
                    print("Style export canceled.")
                    continue
                print(f"\nChosen path: {save_base}")
                style_extensions = ('.bps', '.bpsg', '.bpcfg')
                file_list = ctx.list_files_in_subdirectory(style_extensions, 'style', base_path=save_base)
                files = [f[0] for f in file_list]
                if files:
                    styles_dir = os.path.join(save_base, 'Styles')
                    print(f"Existing {default_ext} files in {styles_dir}:")
                    for i, (fname, fpath) in enumerate(file_list, 1):
                        timestamp = ctx.format_file_timestamp(fpath)
                        if timestamp:
                            print(f"  {i}: {fname}  ({timestamp})")
                        else:
                            print(f"  {i}: {fname}")
                if last_style_path:
                    choice = _safe_input("Enter new filename, number to overwrite, or o to overwrite last (q=cancel): ").strip()
                else:
                    choice = _safe_input("Enter new filename or number to overwrite (q=cancel): ").strip()
                if not choice or choice.lower() == 'q':
                    print("Style export canceled.")
                    continue
                if choice.lower() == 'o':
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
                        if old_cfg.get('kind') == 'cpc_style_geom':
                            snap, _default_ext = _build_cpc_style_export_config(ctx, 'psg')
                        else:
                            snap, _default_ext = _build_cpc_style_export_config(ctx, 'ps')
                    except Exception:
                        snap, _default_ext = _build_cpc_style_export_config(ctx, 'ps')
                    with open(last_style_path, 'w', encoding='utf-8') as f:
                        json.dump(snap, f, indent=2)
                    print(f"Overwritten style to {last_style_path}")
                    style_menu_active = False
                    break
                target = None
                if choice.isdigit() and files:
                    idx = int(choice)
                    if 1 <= idx <= len(files):
                        name = files[idx-1]
                        yn = _safe_input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                        if yn == 'y':
                            target = file_list[idx-1][1]  # Full path from list
                    else:
                        print("Invalid number.")
                        continue
                else:
                    name = choice
                    # Add default extension if no extension provided
                    if not any(name.lower().endswith(ext) for ext in ['.bps', '.bpsg', '.bpcfg']):
                        name = name + default_ext
                    # Use organized path unless it's an absolute path
                    if os.path.isabs(name):
                        target = name
                    else:
                        target = ctx.get_organized_path(name, 'style', base_path=save_base)
                    if os.path.exists(target):
                        yn = _safe_input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
                        if yn != 'y':
                            target = None
                if target:
                    with open(target, 'w', encoding='utf-8') as f:
                        json.dump(snap, f, indent=2)
                    print(f"Exported CPC style to {target}")
                    fig._last_style_export_path = target
                style_menu_active = False  # Exit style submenu and return to main menu
                break
            else:
                print("Unknown choice.")
    except Exception as e:
        print(f"Error in style submenu: {e}")
    _print_menu(fig)


def handle_style_import(ctx: CpcActionContext) -> None:
    """Import CPC style and optional geometry from a style file."""
    fig = ctx.fig
    ax = ctx.ax
    ax2 = ctx.ax2
    sc_charge = ctx.sc_charge
    sc_discharge = ctx.sc_discharge
    sc_eff = ctx.sc_eff
    file_data = ctx.file_data
    _print_menu = ctx.print_menu

    try:
        path = ctx.choose_style_file(ctx.file_paths, purpose="style import")
        if not path:
            _print_menu(fig)
            return
        with open(path, 'r', encoding='utf-8') as f:
            cfg = json.load(f)

        # Check file type
        kind = cfg.get('kind', '')
        if kind not in ('cpc_style', 'cpc_style_geom'):
            print("Not a CPC style file.")
            _print_menu(fig)
            return

        # Enforce compatibility between style/geom ro state and current figure ro state
        file_ro = bool(cfg.get('ro_active', False))
        current_ro = bool(getattr(fig, '_ro_active', False))
        if file_ro != current_ro:
            if file_ro:
                print("Warning: Style/geometry file was saved with --ro (swapped x/y axes); current plot is not using --ro.")
            else:
                print("Warning: Style/geometry file was saved without --ro; current plot was created with --ro.")
            print("Not applying CPC style/geometry to avoid corrupting axis orientation.")
            _print_menu(fig)
            return

        ctx.push_state("import-style")

        geometry_cfg = cfg.get('geometry')
        if geometry_cfg is None:
            geometry_cfg = cfg.get('axes_geometry')
        has_geometry = (kind == 'cpc_style_geom' and isinstance(geometry_cfg, dict))

        # Apply style
        ctx.apply_style(fig, ax, ax2, sc_charge, sc_discharge, sc_eff, cfg, file_data)

        # Apply geometry if present
        if has_geometry:
            try:
                geom = geometry_cfg or {}
                if 'xlabel' in geom and geom['xlabel']:
                    ax.set_xlabel(geom['xlabel'])
                if 'ylabel_left' in geom and geom['ylabel_left']:
                    ax.set_ylabel(geom['ylabel_left'])
                if ax2 is not None and 'ylabel_right' in geom and geom['ylabel_right']:
                    ax2.set_ylabel(geom['ylabel_right'])
                if 'xlim' in geom and isinstance(geom['xlim'], list) and len(geom['xlim']) == 2:
                    ax.set_xlim(geom['xlim'][0], geom['xlim'][1])
                if 'ylim_left' in geom and isinstance(geom['ylim_left'], list) and len(geom['ylim_left']) == 2:
                    ax.set_ylim(geom['ylim_left'][0], geom['ylim_left'][1])
                if ax2 is not None and 'ylim_right' in geom and isinstance(geom['ylim_right'], list) and len(geom['ylim_right']) == 2:
                    ax2.set_ylim(geom['ylim_right'][0], geom['ylim_right'][1])
                print("Applied geometry (labels and limits)")
                fig.canvas.draw_idle()
            except Exception as e:
                print(f"Warning: Could not apply geometry: {e}")

    except Exception as e:
        try:
            ctx.pop_undo()
        except Exception:
            pass
        print(f"Error importing style: {e}")
    _print_menu(fig)


def handle_quick_overwrite_figure(ctx: CpcActionContext) -> None:
    """Overwrite the last CPC figure export."""
    fig = ctx.fig
    ax = ctx.ax
    _safe_input = ctx.safe_input
    _print_menu = ctx.print_menu
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
            _print_menu(fig)
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
                savefig_without_crosshair(fig, last_figure_path, bbox_inches='tight', transparent=True, facecolor='none', edgecolor='none', dpi=fig.dpi)
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
            savefig_without_crosshair(fig, last_figure_path, bbox_inches='tight', dpi=fig.dpi)
        print(f"Overwritten figure to {last_figure_path}")
    except Exception as e:
        print(f"Overwrite failed: {e}")
    _print_menu(fig)


def handle_quick_overwrite_session(ctx: CpcActionContext) -> None:
    """Overwrite the last CPC session save."""
    fig = ctx.fig
    _safe_input = ctx.safe_input
    _print_menu = ctx.print_menu
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
            _print_menu(fig)
            return
        ctx.dump_cpc_session(
            last_session_path,
            fig=fig,
            ax=ctx.ax,
            ax2=ctx.ax2,
            sc_charge=ctx.sc_charge,
            sc_discharge=ctx.sc_discharge,
            sc_eff=ctx.sc_eff,
            file_data=ctx.file_data,
            skip_confirm=True,
        )
        print(f"Overwritten session to {last_session_path}")
    except Exception as e:
        print(f"Overwrite failed: {e}")
    _print_menu(fig)


def handle_quick_overwrite_style(ctx: CpcActionContext, *, include_geometry: bool) -> None:
    """Overwrite the last CPC style export."""
    fig = ctx.fig
    _safe_input = ctx.safe_input
    _print_menu = ctx.print_menu
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
            _print_menu(fig)
            return

        cfg, _ = _build_cpc_style_export_config(ctx, exp_choice)
        with open(last_style_path, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, indent=2)
        print(f"Overwritten {label} style to {last_style_path}")
    except Exception as e:
        print(f"Overwrite failed: {e}")
    _print_menu(fig)


__all__ = [
    "CpcActionContext",
    "handle_figure_export",
    "handle_quick_overwrite_figure",
    "handle_quick_overwrite_session",
    "handle_quick_overwrite_style",
    "handle_save_session",
    "handle_style_export",
    "handle_style_import",
    "handle_undo",
]

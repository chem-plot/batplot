"""Action handlers for the XY interactive menu.

The functions in this module hold command bodies that need access to the
current interactive plot state.  The menu loop in ``interactive.py`` owns the
flow control and passes that state through ``XyActionContext``.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Any, Callable

from .session import dump_session as _bp_dump_session
from ..common.crosshair_export import savefig_without_crosshair
from ..common.files import confirm_previous_path
from ...utils import (
    _confirm_overwrite,
    choose_save_path,
    choose_style_file,
    ensure_exact_case_filename,
    get_organized_path,
    list_files_in_subdirectory,
    natural_sort_key,
)


@dataclass
class XyActionContext:
    fig: Any
    ax: Any
    x_data_list: Any
    y_data_list: Any
    orig_y: Any
    x_full_list: Any
    raw_y_full_list: Any
    offsets_list: Any
    labels: Any
    label_text_objects: Any
    delta: Any
    args: Any
    tick_state: Any
    source_file_paths: Any
    bp: Any
    safe_input: Callable[..., str]
    colorize_prompt: Callable[[str], str]
    format_file_timestamp: Callable[[str], str]
    cif_series_for_session: Callable[[], Any]
    print_style_info: Callable[[], Any]
    export_style_config: Callable[..., Any]
    apply_style_config: Callable[[str], Any]
    push_state: Callable[[str], Any]
    restore_state: Callable[[], Any]
    pop_undo: Callable[[], Any]


def _dump_session(ctx: XyActionContext, target_path: str, *, skip_confirm: bool) -> None:
    bp = ctx.bp
    _bp_dump_session(
        target_path,
        fig=ctx.fig,
        ax=ctx.ax,
        x_data_list=ctx.x_data_list,
        y_data_list=ctx.y_data_list,
        orig_y=ctx.orig_y,
        x_full_list=ctx.x_full_list,
        raw_y_full_list=ctx.raw_y_full_list,
        offsets_list=ctx.offsets_list,
        labels=ctx.labels,
        delta=ctx.delta,
        args=ctx.args,
        tick_state=ctx.tick_state,
        cif_tick_series=ctx.cif_series_for_session(),
        cif_hkl_map=(getattr(bp, 'cif_hkl_map', None) if bp is not None else None),
        cif_hkl_label_map=(getattr(bp, 'cif_hkl_label_map', None) if bp is not None else None),
        show_cif_hkl=(bool(getattr(bp, 'show_cif_hkl', False)) if bp is not None else False),
        show_cif_titles=(bool(getattr(bp, 'show_cif_titles', True)) if bp is not None else True),
        skip_confirm=skip_confirm,
    )


def _save_figure_to_target(ctx: XyActionContext, export_target: str) -> None:
    export_target = ensure_exact_case_filename(export_target)

    # Temporarily remove numbering for export.
    for i, txt in enumerate(ctx.label_text_objects):
        txt.set_text(ctx.labels[i])

    _, ext = os.path.splitext(export_target)
    if ext.lower() == '.svg':
        try:
            fig_fc = ctx.fig.get_facecolor()
        except Exception:
            fig_fc = None
        try:
            ax_fc = ctx.ax.get_facecolor()
        except Exception:
            ax_fc = None
        try:
            if getattr(ctx.fig, 'patch', None) is not None:
                ctx.fig.patch.set_alpha(0.0)
                ctx.fig.patch.set_facecolor('none')
            if getattr(ctx.ax, 'patch', None) is not None:
                ctx.ax.patch.set_alpha(0.0)
                ctx.ax.patch.set_facecolor('none')
        except Exception:
            pass
        try:
            savefig_without_crosshair(
                ctx.fig,
                export_target,
                dpi=300,
                transparent=True,
                facecolor='none',
                edgecolor='none',
            )
        finally:
            try:
                if fig_fc is not None and getattr(ctx.fig, 'patch', None) is not None:
                    ctx.fig.patch.set_alpha(1.0)
                    ctx.fig.patch.set_facecolor(fig_fc)
            except Exception:
                pass
            try:
                if ax_fc is not None and getattr(ctx.ax, 'patch', None) is not None:
                    ctx.ax.patch.set_alpha(1.0)
                    ctx.ax.patch.set_facecolor(ax_fc)
            except Exception:
                pass
    else:
        savefig_without_crosshair(ctx.fig, export_target, dpi=300)

    print(f"Figure saved to {export_target}")
    ctx.fig._last_figure_export_path = export_target

    for i, txt in enumerate(ctx.label_text_objects):
        txt.set_text(f"{i+1}: {ctx.labels[i]}")
    ctx.fig.canvas.draw()


def handle_undo(ctx: XyActionContext) -> None:
    ctx.restore_state()


def handle_quick_overwrite_session(ctx: XyActionContext) -> None:
    try:
        last_session_path = confirm_previous_path(
            ctx.fig,
            '_last_session_save_path',
            safe_input=ctx.safe_input,
            missing_message="No previous session save found.",
            missing_file_message="Previous save file not found: {path}",
            confirm_prompt="Overwrite session '{basename}'? (y/n): ",
        )
        if not last_session_path:
            return
        _dump_session(ctx, last_session_path, skip_confirm=True)
        ctx.fig._last_session_save_path = last_session_path
        print(f"Overwritten session to {last_session_path}")
    except Exception as exc:
        print(f"Error overwriting session: {exc}")


def handle_quick_overwrite_style(ctx: XyActionContext, key: str) -> None:
    try:
        if key == 'ops':
            mode = 'ps'
            label = "style-only"
        else:
            mode = 'psg'
            label = "style+geometry"
        last_style_path = confirm_previous_path(
            ctx.fig,
            '_last_style_export_path',
            safe_input=ctx.safe_input,
            missing_message="No previous style export found.",
            missing_file_message="Previous style file not found: {path}",
            confirm_prompt=f"Overwrite {label} file '{{basename}}'? (y/n): ",
        )
        if not last_style_path:
            return
        exported = ctx.export_style_config(
            None,
            base_path=None,
            overwrite_path=last_style_path,
            force_kind=mode,
        )
        if exported:
            ctx.fig._last_style_export_path = exported
            print(f"Overwritten {label} style to {exported}")
    except Exception as exc:
        print(f"Error overwriting style: {exc}")


def handle_quick_overwrite_figure(ctx: XyActionContext) -> None:
    try:
        last_figure_path = confirm_previous_path(
            ctx.fig,
            '_last_figure_export_path',
            safe_input=ctx.safe_input,
            missing_message="No previous figure export found.",
            missing_file_message="Previous export file not found: {path}",
            confirm_prompt="Overwrite figure '{basename}'? (y/n): ",
        )
        if not last_figure_path:
            return
        _save_figure_to_target(ctx, last_figure_path)
    except Exception as exc:
        print(f"Error overwriting figure: {exc}")


def handle_save_session(ctx: XyActionContext) -> None:
    try:
        folder = choose_save_path(ctx.source_file_paths, purpose="project save")
        if not folder:
            print("Save canceled.")
            return
        print(f"\nChosen path: {folder}")
        files = []
        try:
            files = sorted(
                [f for f in os.listdir(folder) if f.lower().endswith('.pkl')],
                key=natural_sort_key,
            )
        except Exception:
            files = []
        if files:
            print("Existing .pkl files:")
            for i, filename in enumerate(files, 1):
                filepath = os.path.join(folder, filename)
                timestamp = ctx.format_file_timestamp(filepath)
                if timestamp:
                    print(f"  {i}: {filename}  ({timestamp})")
                else:
                    print(f"  {i}: {filename}")
        last_session_path = getattr(ctx.fig, '_last_session_save_path', None)
        if last_session_path:
            prompt = (
                "Enter new filename (no ext needed), number to overwrite, "
                "or o to overwrite last (q=cancel): "
            )
        else:
            prompt = "Enter new filename (no ext needed) or number to overwrite (q=cancel): "
        choice = ctx.safe_input(prompt).strip()
        if not choice or choice.lower() == 'q':
            print("Canceled.")
            return
        if choice.lower() == 'o':
            if not last_session_path:
                print("No previous save found.")
                return
            if not os.path.exists(last_session_path):
                print(f"Previous save file not found: {last_session_path}")
                return
            yn = ctx.safe_input(f"Overwrite '{os.path.basename(last_session_path)}'? (y/n): ")
            if yn.strip().lower() != 'y':
                return
            _dump_session(ctx, last_session_path, skip_confirm=True)
            print(f"Overwritten session to {last_session_path}")
            return

        target_path = None
        if choice.isdigit() and files:
            idx = int(choice)
            if 1 <= idx <= len(files):
                name = files[idx - 1]
                yn = ctx.safe_input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                if yn != 'y':
                    print("Canceled.")
                    return
                target_path = os.path.join(folder, name)
                _dump_session(ctx, target_path, skip_confirm=True)
                ctx.fig._last_session_save_path = target_path
                return
            print("Invalid number.")
            return

        if choice.lower() != 'o':
            name = choice
            _root, ext = os.path.splitext(name)
            if ext == '':
                name = name + '.pkl'
            target_path = name if os.path.isabs(name) else os.path.join(folder, name)
            skip_confirm = False
            if os.path.exists(target_path):
                yn = ctx.safe_input(
                    f"'{os.path.basename(target_path)}' exists. Overwrite? (y/n): "
                ).strip().lower()
                if yn != 'y':
                    print("Canceled.")
                    return
                skip_confirm = True
            _dump_session(ctx, target_path, skip_confirm=skip_confirm)
            ctx.fig._last_session_save_path = target_path
    except Exception as exc:
        print(f"Error saving session: {exc}")


def handle_style_export(ctx: XyActionContext) -> None:
    try:
        while True:
            ctx.print_style_info()
            style_file_list = list_files_in_subdirectory(('.bps', '.bpsg', '.bpcfg'), 'style')
            bpcfg_files = [f[0] for f in style_file_list]
            if bpcfg_files:
                print("Existing style files in Styles/ (.bps/.bpsg):")
                for i, (fname, fpath) in enumerate(style_file_list, 1):
                    timestamp = ctx.format_file_timestamp(fpath)
                    if timestamp:
                        print(f"  {i}: {fname}  ({timestamp})")
                    else:
                        print(f"  {i}: {fname}")
            last_style_path = getattr(ctx.fig, '_last_style_export_path', None)
            n_style = len(style_file_list) if style_file_list else 0
            if last_style_path and n_style:
                sub = ctx.safe_input(ctx.colorize_prompt(
                    "Style submenu: (e=export, o=overwrite last, q=return, r=refresh). "
                    "Press number to overwrite: "
                )).strip().lower()
            elif last_style_path:
                sub = ctx.safe_input(ctx.colorize_prompt(
                    "Style submenu: (e=export, o=overwrite last, q=return, r=refresh): "
                )).strip().lower()
            elif n_style:
                sub = ctx.safe_input(ctx.colorize_prompt(
                    "Style submenu: (e=export, q=return, r=refresh). "
                    "Press number to overwrite: "
                )).strip().lower()
            else:
                sub = ctx.safe_input(ctx.colorize_prompt(
                    "Style submenu: (e=export, q=return, r=refresh): "
                )).strip().lower()
            if sub == 'q':
                return
            if sub == 'r' or sub == '':
                continue
            if sub == 'o':
                if not last_style_path:
                    print("No previous export found.")
                    continue
                if not os.path.exists(last_style_path):
                    print(f"Previous export file not found: {last_style_path}")
                    continue
                yn = ctx.safe_input(
                    f"Overwrite '{os.path.basename(last_style_path)}'? (y/n): "
                ).strip().lower()
                if yn != 'y':
                    continue
                exported_path = ctx.export_style_config(
                    None,
                    base_path=None,
                    overwrite_path=last_style_path,
                )
                if exported_path:
                    ctx.fig._last_style_export_path = exported_path
                return
            if sub.isdigit() and n_style and 1 <= int(sub) <= n_style:
                idx = int(sub) - 1
                target_path = style_file_list[idx][1]
                fname = style_file_list[idx][0]
                yn = ctx.safe_input(f"Overwrite '{fname}'? (y/n): ").strip().lower()
                if yn != 'y':
                    continue
                exported_path = ctx.export_style_config(
                    None,
                    base_path=None,
                    overwrite_path=target_path,
                )
                if exported_path:
                    ctx.fig._last_style_export_path = exported_path
                return
            if sub == 'e':
                save_base = choose_save_path(ctx.source_file_paths, purpose="style export")
                if not save_base:
                    print("Style export canceled.")
                    continue
                print(f"\nChosen path: {save_base}")
                exported_path = ctx.export_style_config(None, base_path=save_base)
                if exported_path:
                    ctx.fig._last_style_export_path = exported_path
                return
            print("Unknown choice.")
    except Exception as exc:
        print(f"Error in style submenu: {exc}")


def handle_style_import(ctx: XyActionContext) -> None:
    try:
        fname = choose_style_file(ctx.source_file_paths, purpose="style import")
        if not fname:
            print("Style import canceled.")
            return
        bname = os.path.basename(fname)
        yn = ctx.safe_input(
            ctx.colorize_prompt(f"Apply style '{bname}'? (y/n): ")
        ).strip().lower()
        if yn != 'y':
            print("Style import canceled.")
            return
        ctx.push_state("style-import")
        try:
            ctx.apply_style_config(fname)
        except Exception:
            ctx.pop_undo()
            raise
    except Exception as exc:
        print(f"Error importing style: {exc}")


def handle_figure_export(ctx: XyActionContext) -> None:
    try:
        base_path = choose_save_path(ctx.source_file_paths, purpose="figure export")
        if not base_path:
            print("Export canceled.")
            return
        print(f"\nChosen path: {base_path}")
        fig_extensions = ('.svg', '.png', '.jpg', '.jpeg', '.pdf', '.eps', '.tif', '.tiff')
        file_list = list_files_in_subdirectory(fig_extensions, 'figure', base_path=base_path)
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

        last_figure_path = getattr(ctx.fig, '_last_figure_export_path', None)
        if last_figure_path:
            filename = ctx.safe_input(
                "Enter filename (default SVG if no extension), number to overwrite, "
                "or o to overwrite last (q=cancel): "
            ).strip()
        else:
            filename = ctx.safe_input(
                "Enter filename (default SVG if no extension) or number to overwrite (q=cancel): "
            ).strip()
        if not filename or filename.lower() == 'q':
            print("Canceled.")
            return

        already_confirmed = False
        if filename.lower() == 'o':
            if not last_figure_path:
                print("No previous export found.")
                return
            if not os.path.exists(last_figure_path):
                print(f"Previous export file not found: {last_figure_path}")
                return
            yn = ctx.safe_input(
                f"Overwrite '{os.path.basename(last_figure_path)}'? (y/n): "
            ).strip().lower()
            if yn != 'y':
                print("Canceled.")
                return
            export_target = last_figure_path
            already_confirmed = True
        elif filename.isdigit() and files:
            idx = int(filename)
            if 1 <= idx <= len(files):
                name = files[idx - 1]
                yn = ctx.safe_input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                if yn != 'y':
                    print("Canceled.")
                    return
                export_target = file_list[idx - 1][1]
                already_confirmed = True
            else:
                print("Invalid number.")
                return
        else:
            if not os.path.splitext(filename)[1]:
                filename += ".svg"
            if os.path.isabs(filename):
                export_target = filename
            else:
                export_target = get_organized_path(filename, 'figure', base_path=base_path)

        if not already_confirmed and os.path.exists(export_target):
            export_target = _confirm_overwrite(export_target)

        if not export_target:
            print("Export canceled.")
            return

        _save_figure_to_target(ctx, export_target)
    except Exception as exc:
        print(f"Error saving figure: {exc}")

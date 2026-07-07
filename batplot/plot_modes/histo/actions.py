"""Save/export/import action handlers for the histogram interactive menu."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Callable

from ...utils import (
    choose_save_path,
    choose_style_file,
    ensure_exact_case_filename,
    get_organized_path,
    list_files_in_subdirectory,
    natural_sort_key,
)

HISTO_STYLE_EXTENSIONS = (".bpsh",)


@dataclass
class HistoActionContext:
    fig: Any
    ax: Any
    state: Any
    source_file_paths: list[str]
    safe_input: Callable[..., str]
    colorize_prompt: Callable[[str], str]
    format_file_timestamp: Callable[[str], str]
    push_state: Callable[[], None]
    pop_undo: Callable[[], None]
    save_session: Callable[[str], None]
    export_style: Callable[[str], None]
    export_figure: Callable[[str], None]
    apply_style_file: Callable[[str], None]


def handle_quick_overwrite_session(ctx: HistoActionContext) -> None:
    try:
        last_session_path = getattr(ctx.fig, "_last_session_save_path", None)
        if not last_session_path:
            print("No previous session save found.")
            return
        if not os.path.exists(last_session_path):
            print(f"Previous save file not found: {last_session_path}")
            return
        yn = ctx.safe_input(
            f"Overwrite session '{os.path.basename(last_session_path)}'? (y/n): "
        ).strip().lower()
        if yn != "y":
            return
        target = ensure_exact_case_filename(last_session_path)
        ctx.save_session(target)
        print(f"Overwritten session to {target}")
    except Exception as exc:
        print(f"Error overwriting session: {exc}")


def handle_quick_overwrite_style(ctx: HistoActionContext) -> None:
    try:
        last_style_path = getattr(ctx.fig, "_last_style_export_path", None)
        if not last_style_path:
            print("No previous style export found.")
            return
        if not os.path.exists(last_style_path):
            print(f"Previous export file not found: {last_style_path}")
            return
        yn = ctx.safe_input(
            f"Overwrite style '{os.path.basename(last_style_path)}'? (y/n): "
        ).strip().lower()
        if yn != "y":
            return
        target = ensure_exact_case_filename(last_style_path)
        ctx.export_style(target)
        print(f"Overwritten style to {target}")
    except Exception as exc:
        print(f"Error overwriting style: {exc}")


def handle_quick_overwrite_figure(ctx: HistoActionContext) -> None:
    try:
        last_figure_path = getattr(ctx.fig, "_last_figure_export_path", None)
        if not last_figure_path:
            print("No previous figure export found.")
            return
        if not os.path.exists(last_figure_path):
            print(f"Previous export file not found: {last_figure_path}")
            return
        yn = ctx.safe_input(
            f"Overwrite figure '{os.path.basename(last_figure_path)}'? (y/n): "
        ).strip().lower()
        if yn != "y":
            return
        target = ensure_exact_case_filename(last_figure_path)
        ctx.export_figure(target)
        print(f"Overwritten figure to {target}")
    except Exception as exc:
        print(f"Error overwriting figure: {exc}")


def handle_save_session(ctx: HistoActionContext) -> None:
    try:
        folder = choose_save_path(ctx.source_file_paths, purpose="histogram session save")
        if not folder:
            print("Save canceled.")
            return
        print(f"\nChosen path: {folder}")
        files: list[str] = []
        try:
            files = sorted(
                [name for name in os.listdir(folder) if name.lower().endswith(".pkl")],
                key=natural_sort_key,
            )
        except Exception:
            files = []
        if files:
            print("Existing .pkl files:")
            for i, name in enumerate(files, 1):
                filepath = os.path.join(folder, name)
                timestamp = ctx.format_file_timestamp(filepath)
                if timestamp:
                    print(f"  {i}: {name}  ({timestamp})")
                else:
                    print(f"  {i}: {name}")
        last_session_path = getattr(ctx.fig, "_last_session_save_path", None)
        if last_session_path:
            prompt = (
                "Enter new filename (no ext needed), number to overwrite, "
                "or o to overwrite last (q=cancel): "
            )
        else:
            prompt = "Enter new filename (no ext needed) or number to overwrite (q=cancel): "
        choice = ctx.safe_input(prompt).strip()
        if not choice or choice.lower() == "q":
            print("Canceled.")
            return
        if choice.lower() == "o":
            if not last_session_path:
                print("No previous save found.")
                return
            if not os.path.exists(last_session_path):
                print(f"Previous save file not found: {last_session_path}")
                return
            yn = ctx.safe_input(f"Overwrite '{os.path.basename(last_session_path)}'? (y/n): ").strip().lower()
            if yn != "y":
                return
            ctx.save_session(ensure_exact_case_filename(last_session_path))
            print(f"Overwritten session to {last_session_path}")
            return
        if choice.isdigit() and files:
            idx = int(choice)
            if 1 <= idx <= len(files):
                name = files[idx - 1]
                yn = ctx.safe_input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                if yn != "y":
                    print("Canceled.")
                    return
                target = ensure_exact_case_filename(os.path.join(folder, name))
                ctx.save_session(target)
                print(f"Saved session to {target}")
                return
            print("Invalid number.")
            return
        name = choice
        root, ext = os.path.splitext(name)
        if ext == "":
            name = name + ".pkl"
        target = name if os.path.isabs(name) else os.path.join(folder, name)
        target = ensure_exact_case_filename(target)
        if os.path.exists(target):
            yn = ctx.safe_input(f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ").strip().lower()
            if yn != "y":
                print("Canceled.")
                return
        ctx.save_session(target)
        print(f"Saved session to {target}")
    except Exception as exc:
        print(f"Error saving session: {exc}")


def handle_figure_export(ctx: HistoActionContext) -> None:
    try:
        base_path = choose_save_path(ctx.source_file_paths, purpose="figure export")
        if not base_path:
            print("Export canceled.")
            return
        print(f"\nChosen path: {base_path}")
        fig_extensions = (".svg", ".png", ".jpg", ".jpeg", ".pdf", ".eps", ".tif", ".tiff")
        file_list = list_files_in_subdirectory(fig_extensions, "figure", base_path=base_path)
        files = [fname for fname, _fpath in file_list]
        if files:
            figures_dir = os.path.join(base_path, "Figures")
            print(f"Existing figure files in {figures_dir}:")
            for i, (fname, fpath) in enumerate(file_list, 1):
                timestamp = ctx.format_file_timestamp(fpath)
                if timestamp:
                    print(f"  {i}: {fname}  ({timestamp})")
                else:
                    print(f"  {i}: {fname}")
        last_figure_path = getattr(ctx.fig, "_last_figure_export_path", None)
        if last_figure_path:
            filename = ctx.safe_input(
                "Enter filename (default SVG if no extension), number to overwrite, "
                "or o to overwrite last (q=cancel): "
            ).strip()
        else:
            filename = ctx.safe_input(
                "Enter filename (default SVG if no extension) or number to overwrite (q=cancel): "
            ).strip()
        if not filename or filename.lower() == "q":
            print("Canceled.")
            return
        if filename.lower() == "o":
            if not last_figure_path:
                print("No previous export found.")
                return
            if not os.path.exists(last_figure_path):
                print(f"Previous export file not found: {last_figure_path}")
                return
            yn = ctx.safe_input(f"Overwrite '{os.path.basename(last_figure_path)}'? (y/n): ").strip().lower()
            if yn != "y":
                print("Canceled.")
                return
            ctx.export_figure(ensure_exact_case_filename(last_figure_path))
            print(f"Figure saved to {last_figure_path}")
            return
        if filename.isdigit() and files:
            idx = int(filename)
            if 1 <= idx <= len(files):
                name = files[idx - 1]
                yn = ctx.safe_input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                if yn != "y":
                    print("Canceled.")
                    return
                target = ensure_exact_case_filename(file_list[idx - 1][1])
                ctx.export_figure(target)
                print(f"Figure saved to {target}")
                return
            print("Invalid number.")
            return
        if not os.path.splitext(filename)[1]:
            filename += ".svg"
        if os.path.isabs(filename):
            export_target = filename
        else:
            export_target = get_organized_path(filename, "figure", base_path=base_path)
        export_target = ensure_exact_case_filename(export_target)
        if os.path.exists(export_target):
            yn = ctx.safe_input(f"'{os.path.basename(export_target)}' exists. Overwrite? (y/n): ").strip().lower()
            if yn != "y":
                print("Canceled.")
                return
        ctx.export_figure(export_target)
        print(f"Figure saved to {export_target}")
    except Exception as exc:
        print(f"Error saving figure: {exc}")


def handle_style_export(ctx: HistoActionContext) -> None:
    try:
        while True:
            style_file_list = list_files_in_subdirectory(HISTO_STYLE_EXTENSIONS, "style")
            if style_file_list:
                print("Existing style files in Styles/ (.bpsh):")
                for i, (fname, fpath) in enumerate(style_file_list, 1):
                    timestamp = ctx.format_file_timestamp(fpath)
                    if timestamp:
                        print(f"  {i}: {fname}  ({timestamp})")
                    else:
                        print(f"  {i}: {fname}")
            last_style_path = getattr(ctx.fig, "_last_style_export_path", None)
            n_style = len(style_file_list)
            if last_style_path and n_style:
                sub = ctx.safe_input(
                    ctx.colorize_prompt(
                        "Style submenu: (e=export, o=overwrite last, q=return, r=refresh). "
                        "Press number to overwrite: "
                    )
                ).strip().lower()
            elif last_style_path:
                sub = ctx.safe_input(
                    ctx.colorize_prompt("Style submenu: (e=export, o=overwrite last, q=return, r=refresh): ")
                ).strip().lower()
            elif n_style:
                sub = ctx.safe_input(
                    ctx.colorize_prompt(
                        "Style submenu: (e=export, q=return, r=refresh). Press number to overwrite: "
                    )
                ).strip().lower()
            else:
                sub = ctx.safe_input(
                    ctx.colorize_prompt("Style submenu: (e=export, q=return, r=refresh): ")
                ).strip().lower()
            if sub == "q":
                return
            if sub in ("r", ""):
                continue
            if sub == "o":
                if not last_style_path:
                    print("No previous export found.")
                    continue
                if not os.path.exists(last_style_path):
                    print(f"Previous export file not found: {last_style_path}")
                    continue
                yn = ctx.safe_input(f"Overwrite '{os.path.basename(last_style_path)}'? (y/n): ").strip().lower()
                if yn != "y":
                    continue
                ctx.export_style(ensure_exact_case_filename(last_style_path))
                print(f"Overwritten style to {last_style_path}")
                return
            if sub.isdigit() and n_style and 1 <= int(sub) <= n_style:
                idx = int(sub) - 1
                target_path = style_file_list[idx][1]
                fname = style_file_list[idx][0]
                yn = ctx.safe_input(f"Overwrite '{fname}'? (y/n): ").strip().lower()
                if yn != "y":
                    continue
                ctx.export_style(ensure_exact_case_filename(target_path))
                print(f"Overwritten style to {target_path}")
                return
            if sub == "e":
                save_base = choose_save_path(ctx.source_file_paths, purpose="style export")
                if not save_base:
                    print("Style export canceled.")
                    continue
                print(f"\nChosen path: {save_base}")
                file_list = list_files_in_subdirectory(HISTO_STYLE_EXTENSIONS, "style", base_path=save_base)
                files = [fname for fname, _fpath in file_list]
                if files:
                    styles_dir = os.path.join(save_base, "Styles")
                    print(f"Existing .bpsh files in {styles_dir}:")
                    for i, (fname, fpath) in enumerate(file_list, 1):
                        timestamp = ctx.format_file_timestamp(fpath)
                        if timestamp:
                            print(f"  {i}: {fname}  ({timestamp})")
                        else:
                            print(f"  {i}: {fname}")
                if last_style_path:
                    choice = ctx.safe_input(
                        "Enter new filename, number to overwrite, or o to overwrite last (q=cancel): "
                    ).strip()
                else:
                    choice = ctx.safe_input("Enter new filename or number to overwrite (q=cancel): ").strip()
                if not choice or choice.lower() == "q":
                    print("Style export canceled.")
                    continue
                if choice.lower() == "o":
                    if not last_style_path:
                        print("No previous export found.")
                        continue
                    if not os.path.exists(last_style_path):
                        print(f"Previous export file not found: {last_style_path}")
                        continue
                    yn = ctx.safe_input(f"Overwrite '{os.path.basename(last_style_path)}'? (y/n): ").strip().lower()
                    if yn != "y":
                        continue
                    ctx.export_style(ensure_exact_case_filename(last_style_path))
                    print(f"Overwritten style to {last_style_path}")
                    return
                target: str | None = None
                if choice.isdigit() and files:
                    idx = int(choice)
                    if 1 <= idx <= len(files):
                        name = files[idx - 1]
                        yn = ctx.safe_input(f"Overwrite '{name}'? (y/n): ").strip().lower()
                        if yn != "y":
                            continue
                        target = file_list[idx - 1][1]
                    else:
                        print("Invalid number.")
                        continue
                else:
                    name = choice
                    if not name.lower().endswith(".bpsh"):
                        name = name + ".bpsh"
                    if os.path.isabs(name):
                        target = name
                    else:
                        target = get_organized_path(name, "style", base_path=save_base)
                    target = ensure_exact_case_filename(target)
                    if os.path.exists(target):
                        yn = ctx.safe_input(
                            f"'{os.path.basename(target)}' exists. Overwrite? (y/n): "
                        ).strip().lower()
                        if yn != "y":
                            continue
                if target:
                    ctx.export_style(target)
                    print(f"Saved style to {target}")
                return
            print("Unknown choice.")
    except Exception as exc:
        print(f"Error in style submenu: {exc}")


def handle_style_import(ctx: HistoActionContext) -> None:
    try:
        fname = choose_style_file(
            ctx.source_file_paths,
            purpose="histogram style import",
            extensions=HISTO_STYLE_EXTENSIONS,
        )
        if not fname:
            print("Style import canceled.")
            return
        bname = os.path.basename(fname)
        yn = ctx.safe_input(ctx.colorize_prompt(f"Apply style '{bname}'? (y/n): ")).strip().lower()
        if yn != "y":
            print("Style import canceled.")
            return
        ctx.push_state()
        try:
            ctx.apply_style_file(fname)
            print("Imported style.")
        except Exception:
            ctx.pop_undo()
            raise
    except json.JSONDecodeError:
        print("Import failed: invalid JSON.")
        ctx.pop_undo()
    except Exception as exc:
        print(f"Import failed: {exc}")


__all__ = [
    "HISTO_STYLE_EXTENSIONS",
    "HistoActionContext",
    "handle_figure_export",
    "handle_quick_overwrite_figure",
    "handle_quick_overwrite_session",
    "handle_quick_overwrite_style",
    "handle_save_session",
    "handle_style_export",
    "handle_style_import",
]

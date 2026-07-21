"""Shared save / style import / export prompts for batch session menus."""

from __future__ import annotations

import os
from typing import Any, Callable, Sequence

from ..common.palettes import parse_index_ranges
from ..common.terminal import colorize_prompt, safe_input
from ...utils import choose_save_path, ensure_exact_case_filename, natural_sort_key
from .common import panel_basenames


def print_numbered_panels(panels: Sequence[Any]) -> None:
    for i, name in enumerate(panel_basenames(panels), 1):
        print(f"  [{i}] {name}")


def parse_panel_selection(spec: str, total: int) -> list[int] | None:
    """Parse plot selection into sorted 0-based indices, or None if canceled/invalid."""
    spec = (spec or "").strip().lower()
    if spec == "q":
        return None
    if spec in ("a", "all"):
        return list(range(total))
    normalized = spec.replace(" ", ",")
    indices = parse_index_ranges(normalized, total, warn_out_of_range=True)
    if not indices:
        print("No valid plot numbers.")
        return None
    return indices


def prompt_panel_indices(
    panels: Sequence[Any],
    *,
    verb: str,
    allow_all: bool = True,
) -> list[int] | None:
    """Ask which batch panels to target. Enter = all plots; single-panel batches skip."""
    total = len(panels)
    if total <= 0:
        return None
    if total == 1:
        return [0]
    print(f"\n{verb}:")
    print_numbered_panels(panels)
    all_hint = ", all" if allow_all else ""
    spec = safe_input(
        colorize_prompt(
            f"Which plots? (Enter=all, 1-{total}, e.g. 2 or 1 3 or 1-4{all_hint}, q=cancel): "
        ),
        cancel_on_interrupt=True,
    ).strip()
    if not spec:
        return list(range(total))
    return parse_panel_selection(spec, total)


def _panel_export_basename(panel: Any) -> str:
    path = getattr(panel, "path", "") or "plot"
    return os.path.splitext(os.path.basename(path))[0]


def _resolve_multi_export_path(folder: str, panel: Any, default_ext: str) -> str:
    ext = default_ext if default_ext.startswith(".") else f".{default_ext}"
    return os.path.join(folder, _panel_export_basename(panel) + ext)


def _list_pkl_files(folder: str) -> list[tuple[str, str]]:
    try:
        names = sorted(
            [name for name in os.listdir(folder) if name.lower().endswith(".pkl")],
            key=natural_sort_key,
        )
    except Exception:
        names = []
    return [(name, os.path.join(folder, name)) for name in names]


def _default_session_name(panel: Any) -> str:
    path = getattr(panel, "path", "") or "plot"
    base = os.path.basename(path)
    if base.lower().endswith(".pkl"):
        return base
    return base + ".pkl" if base else "plot.pkl"


def _panel_fig(panel: Any) -> Any:
    return getattr(panel, "fig", panel)


def _prompt_one_session_path(
    panel: Any,
    panel_index: int,
    *,
    base_path: str,
    file_list: list[tuple[str, str]],
) -> str | None:
    """Prompt save path for one panel session; returns None if skipped/canceled."""
    fig = _panel_fig(panel)
    panel_label = panel_basenames([panel])[0]
    last_path = getattr(fig, "_last_session_save_path", None)
    default_name = _default_session_name(panel)

    print(f"\nSave session for [{panel_index + 1}] {panel_label}")
    if last_path:
        prompt = (
            f"Filename [{default_name}], number to overwrite listed file, "
            "o=overwrite last (q=skip): "
        )
    else:
        prompt = f"Filename [{default_name}], number to overwrite listed file (q=skip): "
    choice = safe_input(colorize_prompt(prompt), cancel_on_interrupt=True).strip()
    if choice.lower() == "q":
        return None
    if not choice:
        choice = default_name

    files = [name for name, _ in file_list]
    already_confirmed = False
    target: str | None = None

    if choice.lower() == "o":
        if not last_path:
            print("No previous save for this plot.")
            return None
        if not os.path.isfile(last_path):
            print(f"Previous save file not found: {last_path}")
            return None
        yn = safe_input(
            f"Overwrite '{os.path.basename(last_path)}'? (y/n): ",
            cancel_on_interrupt=True,
        ).strip().lower()
        if yn != "y":
            return None
        target = last_path
        already_confirmed = True
    elif choice.isdigit() and files:
        idx = int(choice)
        if 1 <= idx <= len(files):
            name = files[idx - 1]
            yn = safe_input(f"Overwrite '{name}'? (y/n): ", cancel_on_interrupt=True).strip().lower()
            if yn != "y":
                return None
            target = file_list[idx - 1][1]
            already_confirmed = True
        else:
            print("Invalid number.")
            return None
    else:
        fname = choice
        if not os.path.splitext(fname)[1]:
            fname += ".pkl"
        if os.path.isabs(fname):
            target = fname
        else:
            target = os.path.join(base_path, fname)

    if not target:
        return None
    target = ensure_exact_case_filename(target)
    if not already_confirmed and os.path.exists(target):
        yn = safe_input(
            f"'{os.path.basename(target)}' exists. Overwrite? (y/n): ",
            cancel_on_interrupt=True,
        ).strip().lower()
        if yn != "y":
            return None
    return target


def _save_sessions_to_original_paths(
    panels: Sequence[Any],
    indices: list[int],
    save_panel: Callable[[Any, str], None],
) -> None:
    targets: list[tuple[int, str]] = []
    for i in indices:
        path = getattr(panels[i], "path", "") or ""
        if not path:
            print(f"Skip [{i + 1}]: no loaded session path.")
            continue
        targets.append((i, path))
    if not targets:
        print("No sessions to save.")
        return

    print("Save to original path(s):")
    for i, path in targets:
        print(f"  [{i + 1}] {os.path.basename(path)}")
    yn = safe_input(colorize_prompt("Overwrite? (y/n): "), cancel_on_interrupt=True).strip().lower()
    if yn != "y":
        print("Save canceled.")
        return

    for i, path in targets:
        try:
            save_panel(panels[i], path)
            fig = _panel_fig(panels[i])
            fig._last_session_save_path = os.path.abspath(path)  # type: ignore[attr-defined]
            print(f"Saved [{i + 1}] {os.path.basename(path)}")
        except Exception as exc:
            print(f"Save failed for [{i + 1}] {path}: {exc}")


def _save_sessions_as_new(
    panels: Sequence[Any],
    indices: list[int],
    save_panel: Callable[[Any, str], None],
) -> None:
    source_paths = [getattr(panels[i], "path", "") for i in indices]
    base_path = choose_save_path([p for p in source_paths if p], purpose="session save")
    if not base_path:
        print("Save canceled.")
        return
    print(f"\nChosen path: {base_path}")

    file_list = _list_pkl_files(base_path)
    if file_list:
        print("Existing .pkl files:")
        for i, (fname, _fpath) in enumerate(file_list, 1):
            print(f"  {i}: {fname}")

    saved = 0
    for i in indices:
        target = _prompt_one_session_path(
            panels[i],
            i,
            base_path=base_path,
            file_list=file_list,
        )
        if not target:
            print(f"Skipped [{i + 1}].")
            continue
        try:
            save_panel(panels[i], target)
            fig = _panel_fig(panels[i])
            fig._last_session_save_path = os.path.abspath(target)  # type: ignore[attr-defined]
            print(f"Saved [{i + 1}] to {target}")
            saved += 1
        except Exception as exc:
            print(f"Save failed for [{i + 1}]: {exc}")

    if saved:
        print(f"Saved {saved} session(s).")
    else:
        print("No sessions saved.")


def run_batch_save_sessions(
    panels: Sequence[Any],
    save_panel: Callable[[Any, str], None],
) -> None:
    """Save selected panel session(s) to original paths or new filenames."""
    indices = prompt_panel_indices(
        panels,
        verb="Save session(s)",
    )
    if indices is None:
        print("Save canceled.")
        return

    mode = safe_input(
        colorize_prompt(
            "Save to original .pkl path(s)? (Enter/y=yes, n=save as new file(s), q=cancel): "
        ),
        cancel_on_interrupt=True,
    ).strip().lower()
    if mode == "q":
        print("Save canceled.")
        return
    if mode in ("", "y", "yes"):
        _save_sessions_to_original_paths(panels, indices, save_panel)
        return
    if mode in ("n", "no"):
        _save_sessions_as_new(panels, indices, save_panel)
        return
    print("Save canceled.")


def run_batch_import_style(
    panels: Sequence[Any],
    *,
    path_prompt: str,
    load_style: Callable[[str], Any],
    apply_style: Callable[[Any, Any], bool | None],
    prepare: Callable[[list[int]], None] | None = None,
    on_applied: Callable[[list[int], str], None] | None = None,
) -> list[int] | None:
    """Import one style file onto selected panels. Returns indices changed."""
    indices = prompt_panel_indices(
        panels,
        verb="Import style onto plot(s)",
    )
    if indices is None:
        print("Import canceled.")
        return None
    path = safe_input(colorize_prompt(path_prompt), cancel_on_interrupt=True).strip()
    if not path or path.lower() == "q":
        print("Import canceled.")
        return None
    payload = load_style(path)
    if payload is None:
        return None
    if prepare:
        prepare(indices)
    succeeded: list[int] = []
    skipped: list[int] = []
    for i in indices:
        try:
            result = apply_style(panels[i], payload)
            if result is False:
                skipped.append(i)
            else:
                succeeded.append(i)
        except Exception as exc:
            print(f"Import failed for [{i + 1}]: {exc}")
            return None
    if skipped:
        names = ", ".join(str(i + 1) for i in skipped)
        print(f"Skipped plot(s) {names} (incompatible or rejected).")
    if not succeeded:
        print("Style import did not apply to any panels.")
        return None
    if on_applied:
        on_applied(succeeded, path)
    else:
        names = ", ".join(str(i + 1) for i in succeeded)
        print(f"Applied style to plot(s) {names}.")
    return succeeded


def run_batch_export_style(
    panels: Sequence[Any],
    export_panel: Callable[[Any, str], None],
    *,
    default_ext: str,
    path_prompt_single: str = "Export style path (q=cancel): ",
    purpose: str = "style export",
) -> None:
    """Export style from one or more panels (one file or one file per plot in a folder)."""
    indices = prompt_panel_indices(
        panels,
        verb="Export style from plot(s)",
    )
    if indices is None:
        print("Export canceled.")
        return
    ext = default_ext if default_ext.startswith(".") else f".{default_ext}"

    if len(indices) == 1:
        i = indices[0]
        out = safe_input(colorize_prompt(path_prompt_single), cancel_on_interrupt=True).strip()
        if not out or out.lower() == "q":
            print("Export canceled.")
            return
        if not os.path.splitext(out)[1]:
            out += ext
        try:
            export_panel(panels[i], out)
            print(f"Exported style from [{i + 1}] to {out}")
        except Exception as exc:
            print(f"Export failed: {exc}")
        return

    paths = [getattr(panels[i], "path", "") for i in indices]
    folder = choose_save_path(list(paths), purpose=purpose)
    if not folder:
        print("Export canceled.")
        return
    print(f"\nChosen folder: {folder}")
    for i in indices:
        out = _resolve_multi_export_path(folder, panels[i], ext)
        try:
            export_panel(panels[i], out)
            print(f"Exported [{i + 1}] to {out}")
        except Exception as exc:
            print(f"Export failed for [{i + 1}]: {exc}")


__all__ = [
    "parse_panel_selection",
    "print_numbered_panels",
    "prompt_panel_indices",
    "run_batch_export_style",
    "run_batch_import_style",
    "run_batch_save_sessions",
]

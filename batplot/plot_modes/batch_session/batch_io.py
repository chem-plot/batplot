"""Shared save / style import / export prompts for batch session menus."""

from __future__ import annotations

import os
from typing import Any, Callable, List, Optional, Sequence

from ..common.palettes import parse_index_ranges
from ..common.terminal import colorize_prompt, safe_input
from ...utils import choose_save_path
from .common import panel_basenames


def print_numbered_panels(panels: Sequence[Any]) -> None:
    for i, name in enumerate(panel_basenames(panels), 1):
        print(f"  [{i}] {name}")


def parse_panel_selection(spec: str, total: int) -> list[int] | None:
    """Parse plot selection into sorted 0-based indices, or None if canceled/invalid."""
    spec = (spec or "").strip().lower()
    if not spec or spec == "q":
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
    """Ask which batch panels to target. Single-panel batches skip the prompt."""
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
            f"Which plots? (1-{total}, e.g. 2 or 1 3 or 1-4{all_hint}, q=cancel): "
        ),
        cancel_on_interrupt=True,
    ).strip()
    return parse_panel_selection(spec, total)


def _panel_export_basename(panel: Any) -> str:
    path = getattr(panel, "path", "") or "plot"
    return os.path.splitext(os.path.basename(path))[0]


def _resolve_multi_export_path(folder: str, panel: Any, default_ext: str) -> str:
    ext = default_ext if default_ext.startswith(".") else f".{default_ext}"
    return os.path.join(folder, _panel_export_basename(panel) + ext)


def run_batch_save_sessions(
    panels: Sequence[Any],
    save_panel: Callable[[Any], None],
    *,
    source_paths: Sequence[str] | None = None,
) -> None:
    """Save selected panel session(s) back to their original ``.pkl`` paths."""
    indices = prompt_panel_indices(panels, verb="Save sessions to original .pkl paths")
    if indices is None:
        print("Save canceled.")
        return
    for i in indices:
        panel = panels[i]
        path = (source_paths[i] if source_paths else None) or getattr(panel, "path", "")
        try:
            save_panel(panel)
            print(f"Saved [{i + 1}] {os.path.basename(path)}")
        except Exception as exc:
            print(f"Save failed for [{i + 1}] {path}: {exc}")


def run_batch_import_style(
    panels: Sequence[Any],
    *,
    path_prompt: str,
    load_style: Callable[[str], Any],
    apply_style: Callable[[Any, Any], None],
    prepare: Callable[[list[int]], None] | None = None,
    on_applied: Callable[[list[int], str], None] | None = None,
) -> list[int] | None:
    """Import one style file onto selected panels. Returns indices changed."""
    indices = prompt_panel_indices(panels, verb="Import style onto plots")
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
    for i in indices:
        try:
            apply_style(panels[i], payload)
        except Exception as exc:
            print(f"Import failed for [{i + 1}]: {exc}")
            return None
    if on_applied:
        on_applied(indices, path)
    else:
        names = ", ".join(str(i + 1) for i in indices)
        print(f"Applied style to plot(s) {names}.")
    return indices


def run_batch_export_style(
    panels: Sequence[Any],
    export_panel: Callable[[Any, str], None],
    *,
    default_ext: str,
    path_prompt_single: str = "Export style path (q=cancel): ",
    purpose: str = "style export",
) -> None:
    """Export style from one or more panels (one file or one file per plot in a folder)."""
    indices = prompt_panel_indices(panels, verb="Export style from plot(s)")
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

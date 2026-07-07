"""Shared save / overwrite / quit helpers for batch session menus."""

from __future__ import annotations

import os
from typing import Any, Callable, List, Sequence

from ..common.files import confirm_previous_path
from ..common.terminal import colorize_prompt, safe_input
from .batch_io import parse_panel_selection, print_numbered_panels, prompt_panel_indices


def panel_fig(panel: Any) -> Any:
    return getattr(panel, "fig", panel)


def append_batch_io_shortcuts(options: List[str], panels: Sequence[Any]) -> None:
    """Append overwrite shortcuts when any panel has a prior save/export path."""
    figs = [panel_fig(p) for p in panels]
    if any(getattr(f, "_last_session_save_path", None) for f in figs):
        options.append("os: overwrite session(s)")
    if any(getattr(f, "_last_style_export_path", None) for f in figs):
        options.append("ops: overwrite style")
        options.append("opsg: overwrite style+geom")
    # Figure overwrite (oe) is not wired in batch menus yet — omit from shortcuts.


def batch_quit_confirm(*, allow_export: bool = True) -> str | None:
    """Return ``y`` to quit, ``s`` / ``s all`` to save first, or ``None`` to stay."""
    try:
        if allow_export:
            prompt = (
                "Quit batch interactive? "
                "(s=save selected, s all=save every plot, y/n): "
            )
        else:
            prompt = "Quit batch interactive? Quit now? (y/n): "
        confirm = safe_input(colorize_prompt(prompt), cancel_on_interrupt=True).strip().lower()
    except (KeyboardInterrupt, EOFError):
        return "y"
    if confirm == "y":
        return "y"
    if allow_export and confirm in ("s all", "all"):
        return "s all"
    if allow_export and confirm == "s":
        return "s"
    return None


def run_batch_save_all(panels: Sequence[Any], save_panel: Callable[[Any], None]) -> None:
    """Save every panel without a selection prompt."""
    for i, panel in enumerate(panels):
        path = getattr(panel, "path", "") or "?"
        try:
            save_panel(panel)
            print(f"Saved [{i + 1}] {os.path.basename(path)}")
        except Exception as exc:
            print(f"Save failed for [{i + 1}] {path}: {exc}")


def run_batch_overwrite_sessions(
    panels: Sequence[Any],
    save_panel: Callable[[Any, str], None],
) -> None:
    """Overwrite each panel's last (or loaded) session path, with per-panel confirm."""
    for i, panel in enumerate(panels):
        fig = panel_fig(panel)
        fallback = getattr(panel, "path", None)
        path = confirm_previous_path(
            fig,
            "_last_session_save_path",
            safe_input=safe_input,
            missing_message=(
                f"No previous save for [{i + 1}] {os.path.basename(fallback or '?')}."
            ),
            missing_file_message="Previous save file not found: {path}",
            confirm_prompt="Overwrite '{basename}'? (y/n): ",
            canceled_message=None,
        )
        if not path and fallback:
            yn = safe_input(
                colorize_prompt(
                    f"Overwrite loaded session [{i + 1}] '{os.path.basename(fallback)}'? (y/n): "
                ),
                cancel_on_interrupt=True,
            ).strip().lower()
            if yn == "y":
                path = fallback
        if not path:
            continue
        try:
            save_panel(panel, path)
            fig._last_session_save_path = os.path.abspath(path)  # type: ignore[attr-defined]
            print(f"Overwritten [{i + 1}] {os.path.basename(path)}")
        except Exception as exc:
            print(f"Overwrite failed for [{i + 1}]: {exc}")


def prompt_style_source_index(panels: Sequence[Any]) -> int | None:
    """Pick one panel whose style snapshot is used for ``ops`` / ``opsg``."""
    total = len(panels)
    if total <= 0:
        return None
    if total == 1:
        return 0
    print("\nStyle overwrite uses one plot as the source snapshot:")
    print_numbered_panels(panels)
    spec = safe_input(
        colorize_prompt(f"Which plot? (1-{total}, q=cancel): "),
        cancel_on_interrupt=True,
    ).strip()
    if not spec or spec.lower() == "q":
        return None
    indices = parse_panel_selection(spec, total)
    if indices is None or len(indices) != 1:
        print("Pick exactly one plot number.")
        return None
    return indices[0]


__all__ = [
    "append_batch_io_shortcuts",
    "batch_quit_confirm",
    "panel_fig",
    "prompt_style_source_index",
    "run_batch_overwrite_sessions",
    "run_batch_save_all",
]

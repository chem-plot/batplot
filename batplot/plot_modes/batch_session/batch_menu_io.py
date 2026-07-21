"""Shared batch interactive I/O handlers (identical across XY, EC, CPC, operando, histo)."""

from __future__ import annotations

from typing import Any, Callable, Sequence

from .batch_commands import batch_quit_confirm, run_batch_overwrite_sessions, run_batch_save_all
from .batch_figure_io import run_batch_export_figures, run_batch_overwrite_figures
from .batch_io import run_batch_export_style, run_batch_import_style, run_batch_save_sessions


def batch_quit_or_save_all(
    panels: Sequence[Any],
    save_panel: Callable[[Any, str], None],
) -> bool:
    """Handle ``q`` quit prompt. Returns True when the menu loop should exit."""
    action = batch_quit_confirm(allow_export=True)
    if action == "y":
        return True
    if action == "s":
        run_batch_save_all(panels, save_panel)
    return False


def batch_save_sessions(
    panels: Sequence[Any],
    save_panel: Callable[[Any, str], None],
) -> None:
    run_batch_save_sessions(panels, save_panel)


def batch_overwrite_sessions(
    panels: Sequence[Any],
    save_panel: Callable[[Any, str], None],
) -> None:
    run_batch_overwrite_sessions(panels, save_panel)


def batch_export_figures(
    panels: Sequence[Any],
    export_panel: Callable[[Any, str], None],
    *,
    format_timestamp: Callable[[str], str] | None = None,
) -> None:
    run_batch_export_figures(
        panels,
        export_panel,
        format_timestamp=format_timestamp,
    )


def batch_overwrite_figures(
    panels: Sequence[Any],
    export_panel: Callable[[Any, str], None],
) -> None:
    run_batch_overwrite_figures(panels, export_panel)


def batch_import_style(
    panels: Sequence[Any],
    *,
    path_prompt: str,
    load_style: Callable[[str], Any],
    apply_style: Callable[[Any, Any], None],
    prepare: Callable[[list[int]], None] | None = None,
    on_applied: Callable[[list[int], str], None] | None = None,
) -> list[int] | None:
    return run_batch_import_style(
        panels,
        path_prompt=path_prompt,
        load_style=load_style,
        apply_style=apply_style,
        prepare=prepare,
        on_applied=on_applied,
    )


def batch_export_style(
    panels: Sequence[Any],
    export_panel: Callable[[Any, str], None],
    *,
    default_ext: str,
    path_prompt_single: str = "Export style path (q=cancel): ",
    purpose: str = "style export",
) -> None:
    run_batch_export_style(
        panels,
        export_panel,
        default_ext=default_ext,
        path_prompt_single=path_prompt_single,
        purpose=purpose,
    )


__all__ = [
    "batch_export_figures",
    "batch_export_style",
    "batch_import_style",
    "batch_overwrite_figures",
    "batch_overwrite_sessions",
    "batch_quit_or_save_all",
    "batch_save_sessions",
]

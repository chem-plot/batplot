"""Batch figure export (``e`` / ``oe``) for session interactive menus."""

from __future__ import annotations

import os
from typing import Any, Callable, Sequence

from ..common.crosshair_export import savefig_without_crosshair
from ..common.files import confirm_previous_path
from ..common.terminal import colorize_prompt, safe_input
from ...utils import choose_save_path, ensure_exact_case_filename, get_organized_path, list_files_in_subdirectory
from .batch_commands import panel_fig
from .batch_io import panel_basenames

FIG_EXTENSIONS = (".svg", ".png", ".jpg", ".jpeg", ".pdf", ".eps", ".tif", ".tiff")


def save_standard_panel_figure(
    fig,
    ax,
    path: str,
    *,
    extra_axes: Sequence[Any] = (),
    dpi: int = 300,
) -> None:
    """Save a panel figure with SVG transparency handling (shared by batch export)."""
    path = ensure_exact_case_filename(path)
    _, ext = os.path.splitext(path)
    # Collect only real patches so restore never sees Optional patch/owner.
    patch_owners: list[tuple[Any, Any]] = []
    for owner in (fig, ax, *extra_axes):
        if owner is None:
            continue
        patch = getattr(owner, "patch", None)
        if patch is None:
            continue
        patch_owners.append((owner, patch))

    if ext.lower() == ".svg":
        saved: list[tuple[Any, Any, Any]] = []
        try:
            for owner, patch in patch_owners:
                try:
                    fc = owner.get_facecolor() if owner is fig else patch.get_facecolor()
                except Exception:
                    fc = None
                saved.append((owner, patch, fc))
                patch.set_alpha(0.0)
                patch.set_facecolor("none")
            savefig_without_crosshair(
                fig,
                path,
                dpi=dpi,
                bbox_inches="tight",
                transparent=True,
                facecolor="none",
                edgecolor="none",
            )
        finally:
            for owner, patch, fc in saved:
                try:
                    patch.set_alpha(1.0)
                    if fc is not None:
                        if owner is fig:
                            owner.set_facecolor(fc)
                        else:
                            patch.set_facecolor(fc)
                except Exception:
                    pass
    else:
        savefig_without_crosshair(fig, path, dpi=dpi, bbox_inches="tight")
    fig._last_figure_export_path = os.path.abspath(path)  # type: ignore[attr-defined]


def _panel_default_figure_name(panel: Any, ext: str = ".svg") -> str:
    path = getattr(panel, "path", "") or "plot"
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem + ext


def _prompt_one_figure_path(
    panel: Any,
    panel_index: int,
    *,
    base_path: str,
    file_list: list[tuple[str, str]],
    format_timestamp: Callable[[str], str] | None = None,
) -> str | None:
    """Prompt export path for one panel; returns None if skipped/canceled."""
    fig = panel_fig(panel)
    panel_label = panel_basenames([panel])[0]
    last_path = getattr(fig, "_last_figure_export_path", None)
    default_name = _panel_default_figure_name(panel)

    print(f"\nExport figure for [{panel_index + 1}] {panel_label}")
    if last_path:
        prompt = (
            f"Filename [{default_name}], number to overwrite listed file, "
            "o=overwrite last, Enter=default name (q=cancel): "
        )
    else:
        prompt = (
            f"Filename [{default_name}], number to overwrite listed file, "
            "Enter=default name (q=cancel): "
        )
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
            print("No previous export for this plot.")
            return None
        if not os.path.isfile(last_path):
            print(f"Previous export file not found: {last_path}")
            return None
        yn = safe_input(f"Overwrite '{os.path.basename(last_path)}'? (y/n): ", cancel_on_interrupt=True).strip().lower()
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
            fname += ".svg"
        if os.path.isabs(fname):
            target = fname
        else:
            target = get_organized_path(fname, "figure", base_path=base_path)

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


def run_batch_export_figures(
    panels: Sequence[Any],
    export_panel: Callable[[Any, str], None],
    *,
    format_timestamp: Callable[[str], str] | None = None,
) -> None:
    """Export figure image(s) from selected batch panels (one prompt per plot)."""
    from .batch_io import prompt_panel_indices

    indices = prompt_panel_indices(
        panels,
        verb="Export figure(s)",
    )
    if indices is None:
        print("Export canceled.")
        return

    source_paths = [getattr(panels[i], "path", "") for i in indices]
    base_path = choose_save_path([p for p in source_paths if p], purpose="figure export")
    if not base_path:
        print("Export canceled.")
        return
    print(f"\nChosen path: {base_path}")

    file_list = list_files_in_subdirectory(FIG_EXTENSIONS, "figure", base_path=base_path)
    if file_list:
        figures_dir = os.path.join(base_path, "Figures")
        print(f"Existing figure files in {figures_dir}:")
        ts_fn = format_timestamp or (lambda _p: "")
        for i, (fname, fpath) in enumerate(file_list, 1):
            timestamp = ts_fn(fpath)
            if timestamp:
                print(f"  {i}: {fname}  ({timestamp})")
            else:
                print(f"  {i}: {fname}")

    exported = 0
    for i in indices:
        target = _prompt_one_figure_path(
            panels[i],
            i,
            base_path=base_path,
            file_list=file_list,
            format_timestamp=format_timestamp,
        )
        if not target:
            print(f"Skipped [{i + 1}].")
            continue
        try:
            export_panel(panels[i], target)
            fig = panel_fig(panels[i])
            fig._last_figure_export_path = os.path.abspath(target)  # type: ignore[attr-defined]
            print(f"Saved [{i + 1}] to {target}")
            exported += 1
        except Exception as exc:
            print(f"Export failed for [{i + 1}]: {exc}")

    if exported:
        print(f"Exported {exported} figure(s).")
    else:
        print("No figures exported.")


def run_batch_overwrite_figures(
    panels: Sequence[Any],
    export_panel: Callable[[Any, str], None],
) -> None:
    """Overwrite each panel's last exported figure path (``oe``), with confirm."""
    restored = 0
    for i, panel in enumerate(panels):
        fig = panel_fig(panel)
        fallback = getattr(panel, "path", None)
        path = confirm_previous_path(
            fig,
            "_last_figure_export_path",
            safe_input=safe_input,
            missing_message=f"No previous figure export for [{i + 1}] {os.path.basename(fallback or '?')}.",
            missing_file_message="Previous export file not found: {path}",
            confirm_prompt="Overwrite '{basename}'? (y/n): ",
            canceled_message=None,
        )
        if not path:
            continue
        try:
            export_panel(panel, path)
            fig._last_figure_export_path = os.path.abspath(path)  # type: ignore[attr-defined]
            print(f"Overwritten [{i + 1}] {os.path.basename(path)}")
            restored += 1
        except Exception as exc:
            print(f"Overwrite failed for [{i + 1}]: {exc}")
    if not restored:
        print("No figures overwritten.")


__all__ = [
    "FIG_EXTENSIONS",
    "run_batch_export_figures",
    "run_batch_overwrite_figures",
    "save_standard_panel_figure",
]

"""Batch interactive menu for XY / 1D sessions."""

from __future__ import annotations

import json
import os
from typing import List

from ..common.batch_font import run_batch_font_menu
from ..common.files import confirm_previous_path
from ..common.fonts import collect_fig_font_artists
from ..common.menu_rendering import colorize_menu_item as _colorize_menu, print_menu_columns, prompt_menu_key
from ..common.terminal import colorize_prompt, safe_input
from ..xy.interactive import normalize_xy_menu_kwargs
from ..xy.line_style import run_line_style_menu
from ..xy.style import apply_style_config, export_style_config
from ...plotting import update_labels
from ...color_utils import format_color_listing
from .operando_batch_helpers import edit_ref_then_sync, noop_snapshot
from .batch_commands import (
    prompt_style_source_index,
)
from .batch_crosshair import toggle_batch_crosshair
from .batch_menu_io import (
    batch_export_figures,
    batch_export_style,
    batch_import_style,
    batch_overwrite_figures,
    batch_overwrite_sessions,
    batch_quit_or_save_all,
    batch_save_sessions,
)
from .common import (
    SyncUndoStacks,
    draw_panels,
    print_batch_header,
    remove_temp_file,
    set_all_panel_figure_titles,
    write_temp_style_json,
)
from .batch_geom_helpers import run_batch_geom_size_menu
from .batch_menu_helpers import (
    batch_options_menu_column,
)
from .load import XyPanel
from .xy_batch_helpers import (
    dump_xy_panel,
    export_xy_panel_figure,
    run_xy_batch_spine_menu,
    tick_state_for,
)


def _print_xy_batch_menu(panels: List[XyPanel]) -> None:
    col1 = [
        "c: colors",
        "f: font",
        "l: line style",
        "t: spines/ticks",
        "h: curve labels",
        "g: size",
    ]
    col2 = [
        "r: rename labels",
        "x: x range",
        "y: y range",
        "v: peak finder",
    ]
    col3 = batch_options_menu_column(panels)
    print_menu_columns(
        title=f"Batch XY Menu ({len(panels)} plots)",
        columns=[("Styles", col1), ("Geometries", col2), ("Options", col3)],
        min_widths=(20, 18, 18),
        colorize_item=_colorize_menu,
    )


def _tick_state_for(panel: XyPanel) -> dict:
    return tick_state_for(panel)


def _line_getter(panel: XyPanel):
    def _line(idx: int):
        return panel.ax.lines[idx]

    return _line


def _run_ref_range_menu(ref: XyPanel, panels: List[XyPanel], undo: SyncUndoStacks, axis: str) -> None:
    """Apply shared axis limits to every panel.

    Batch mode intentionally sets limits only (no per-panel data cropping).
    Using the normal XY ``x`` submenu would crop the reference curves while
    only syncing ``xlim`` to peers — leave cropping to single-session mode.
    """
    from .batch_menu_helpers import prompt_axis_limits

    def _draw_all() -> None:
        draw_panels(panels)

    label = "X" if axis == "x" else "Y"
    get_limits = (lambda p: p.ax.get_xlim()) if axis == "x" else (lambda p: p.ax.get_ylim())
    while True:
        lims = prompt_axis_limits(
            label=f"XY {label}",
            panels=panels,
            get_panel_limits=get_limits,
        )
        if lims is None:
            break
        undo.push_all([_capture_panel(p) for p in panels])
        for p in panels:
            try:
                if axis == "x":
                    p.ax.set_xlim(lims[0], lims[1])
                else:
                    p.ax.set_ylim(lims[0], lims[1])
            except Exception as exc:
                print(f"{label} range failed: {exc}")
        _draw_all()
        print(f"{label} set to {lims[0]:.4g} … {lims[1]:.4g} on all plots.")


def _print_batch_xy_current_curves(ref: XyPanel) -> None:
    kw = normalize_xy_menu_kwargs(ref.menu_kwargs)
    labels = kw.get("labels") or []
    print("\nCurrent curves (reference plot; visible only; applied to all panels):")
    any_curve = False
    for idx, label in enumerate(labels):
        ln = ref.ax.lines[idx] if idx < len(ref.ax.lines) else None
        try:
            if ln is not None and not ln.get_visible():
                continue
        except Exception:
            pass
        col = ln.get_color() if ln is not None else None
        any_curve = True
        print(f"  {idx + 1}: {format_color_listing(col)} {label}")
    if not any_curve:
        print("  (none visible)")


def _apply_style_path(panel: XyPanel, path: str, *, keep_canvas_fixed: bool = False) -> None:
    kw = normalize_xy_menu_kwargs(panel.menu_kwargs)
    tick_state = _tick_state_for(panel)
    cif_globals = kw.get("cif_globals") or {}
    if not keep_canvas_fixed:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            kind = str(cfg.get("kind", "")).lower()
            keep_canvas_fixed = "geom" not in kind and "geometry" not in cfg
        except Exception:
            keep_canvas_fixed = True
    apply_style_config(
        path,
        panel.fig,
        panel.ax,
        kw.get("x_data_list"),
        kw.get("y_data_list") or [],
        kw.get("orig_y"),
        kw.get("offsets_list") or [],
        kw.get("label_text_objects") or [],
        kw.get("args"),
        tick_state,
        kw.get("labels") or [],
        update_labels,
        cif_tick_series=cif_globals.get("cif_tick_series"),
        cif_hkl_label_map=cif_globals.get("cif_hkl_label_map"),
        adjust_margins_cb=lambda: None,
        keep_canvas_fixed=keep_canvas_fixed,
    )


def _xy_batch_font_artists(panel: XyPanel) -> list:
    kw = normalize_xy_menu_kwargs(panel.menu_kwargs)
    extra = kw.get("label_text_objects") or []
    ax2 = getattr(panel.fig, "_xy_ax2", None)
    return collect_fig_font_artists(
        panel.ax,
        panel.fig,
        include_title=True,
        include_axes_texts=True,
        extra_axes=[ax2] if ax2 is not None else None,
        extra_artists=list(extra),
    )


def _capture_panel(panel: XyPanel) -> dict:
    import tempfile

    fd, tmp = tempfile.mkstemp(suffix=".bpsg")
    os.close(fd)
    kw = normalize_xy_menu_kwargs(panel.menu_kwargs)
    tick_state = _tick_state_for(panel)
    cif_globals = kw.get("cif_globals") or {}
    try:
        export_style_config(
            tmp,
            panel.fig,
            panel.ax,
            kw.get("y_data_list") or [],
            kw.get("labels") or [],
            kw.get("delta", 0.0),
            kw.get("args"),
            tick_state,
            kw.get("offsets_list") or [],
            cif_tick_series=cif_globals.get("cif_tick_series"),
            label_text_objects=kw.get("label_text_objects"),
            overwrite_path=tmp,
            force_kind="psg",
        )
        with open(tmp, "r", encoding="utf-8") as fh:
            return json.load(fh)
    finally:
        remove_temp_file(tmp)


def _restore_panel(panel: XyPanel, cfg: dict) -> None:
    path = write_temp_style_json(cfg)
    try:
        _apply_style_path(panel, path)
    finally:
        remove_temp_file(path)


def run_xy_batch_menu(panels: List[XyPanel]) -> None:
    set_all_panel_figure_titles(panels)
    print_batch_header("xy", panels)
    undo = SyncUndoStacks(len(panels))
    undo.push_all([_capture_panel(p) for p in panels])
    pending: str | None = None
    ref = panels[0]

    while True:
        _print_xy_batch_menu(panels)
        try:
            if pending:
                cmd = pending
                pending = None
            else:
                cmd = prompt_menu_key()
        except (KeyboardInterrupt, EOFError):
            break
        if not cmd:
            continue

        if cmd == "q":
            if batch_quit_or_save_all(panels, dump_xy_panel):
                break
            continue

        if cmd == "b":
            undo.undo_all(lambda i, snap: _restore_panel(panels[i], snap))
            draw_panels(panels)
            continue

        if cmd == "n":
            toggle_batch_crosshair(panels)
            continue

        if cmd == "g":
            run_batch_geom_size_menu(
                panels,
                push_undo=lambda: undo.push_all([_capture_panel(p) for p in panels]),
                draw_all=lambda: draw_panels(panels),
                colorize_menu=_colorize_menu,
            )
            continue

        if cmd == "f":
            run_batch_font_menu(
                panels=panels,
                undo=undo,
                capture_panel=_capture_panel,
                draw_panels=lambda: draw_panels(panels),
                collect_artists=_xy_batch_font_artists,
                safe_input=safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=colorize_prompt,
            )
            continue

        if cmd == "l":
            def _edit_lines() -> None:
                run_line_style_menu(
                    ax=ref.ax,
                    fig=ref.fig,
                    lines_by_curve=None,
                    line_getter=_line_getter(ref),
                    line_count=lambda: len(ref.ax.lines),
                    push_state=noop_snapshot,
                    safe_input=safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=colorize_prompt,
                )

            def _apply_xy_cfg(panel: XyPanel, cfg: dict) -> bool:
                try:
                    _restore_panel(panel, cfg)
                    return True
                except Exception as exc:
                    print(f"Style sync failed: {exc}")
                    return False

            edit_ref_then_sync(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=_apply_xy_cfg,
                draw_all=lambda: draw_panels(panels),
                edit_fn=_edit_lines,
            )
            continue

        if cmd == "c":
            while True:
                _print_batch_xy_current_curves(ref)
                color = safe_input(
                    colorize_prompt("Curve color for ALL curves/plots (name/#hex, q=back): "),
                    cancel_on_interrupt=True,
                ).strip()
                if not color or color.lower() == "q":
                    break
                undo.push_all([_capture_panel(p) for p in panels])
                for p in panels:
                    for ln in p.ax.lines:
                        try:
                            ln.set_color(color)
                        except Exception:
                            pass
                draw_panels(panels)
                print(f"Color set to {color!r} on all curves.")
            continue

        if cmd == "h":
            # Toggle curve-name label visibility on every panel (batch legend).
            undo.push_all([_capture_panel(p) for p in panels])
            for p in panels:
                kw = normalize_xy_menu_kwargs(p.menu_kwargs)
                label_objs = kw.get("label_text_objects") or []
                if not label_objs:
                    continue
                try:
                    first_vis = bool(label_objs[0].get_visible())
                except Exception:
                    first_vis = True
                new_state = not first_vis
                for lbl in label_objs:
                    try:
                        lbl.set_visible(new_state)
                    except Exception:
                        pass
                try:
                    p.fig._curve_names_visible = new_state  # type: ignore[attr-defined]
                except Exception:
                    pass
                try:
                    args = kw.get("args")
                    stack = bool(getattr(args, "stack", False)) if args is not None else False
                    update_labels(
                        p.ax,
                        kw.get("y_data_list") or [],
                        label_objs,
                        stack,
                        getattr(p.fig, "_stack_label_at_bottom", False),
                    )
                except Exception:
                    pass
            draw_panels(panels)
            print("Toggled curve-name labels on all plots.")
            continue

        if cmd == "t":
            run_xy_batch_spine_menu(
                ref,
                panels,
                push_undo=lambda: undo.push_all([_capture_panel(p) for p in panels]),
                draw_all=lambda: draw_panels(panels),
            )
            continue

        if cmd == "x":
            _run_ref_range_menu(ref, panels, undo, "x")
            continue

        if cmd == "y":
            _run_ref_range_menu(ref, panels, undo, "y")
            continue

        if cmd == "r":
            while True:
                xl = safe_input(
                    colorize_prompt("X-axis label (blank=skip, q=back): "),
                    cancel_on_interrupt=True,
                ).strip()
                if xl.lower() == "q":
                    break
                yl = safe_input(
                    colorize_prompt("Y-axis label (blank=skip, q=back): "),
                    cancel_on_interrupt=True,
                ).strip()
                if yl.lower() == "q":
                    break
                if not xl and not yl:
                    break
                undo.push_all([_capture_panel(p) for p in panels])
                for p in panels:
                    if xl:
                        p.ax.set_xlabel(xl)
                    if yl:
                        p.ax.set_ylabel(yl)
                draw_panels(panels)
            continue

        if cmd == "i":
            def _load_xy_style(path: str):
                if not os.path.isfile(path):
                    print("File not found.")
                    return None
                return path

            def _on_xy_imported(indices: list[int], path: str) -> None:
                ref.fig._last_style_import_path = os.path.abspath(path)  # type: ignore[attr-defined]
                draw_panels(panels)
                names = ", ".join(str(i + 1) for i in indices)
                print(f"Applied style to plot(s) {names}.")

            batch_import_style(
                panels,
                path_prompt="Import style path (.bps/.bpsg, q=cancel): ",
                load_style=_load_xy_style,
                apply_style=lambda panel, style_path: _apply_style_path(panel, style_path),
                prepare=lambda _indices: undo.push_all([_capture_panel(p) for p in panels]),
                on_applied=_on_xy_imported,
            )
            continue

        if cmd == "e":
            batch_export_figures(
                panels,
                export_xy_panel_figure,
            )
            continue

        if cmd == "p":
            sub = safe_input("Export style: ps=style only, psg=style+geometry, q=cancel: ", cancel_on_interrupt=True).strip().lower()
            if sub not in ("ps", "psg"):
                continue
            ext = ".bpsg" if sub == "psg" else ".bps"

            def _export_xy_style_panel(panel: XyPanel, out: str) -> None:
                kw = normalize_xy_menu_kwargs(panel.menu_kwargs)
                tick_state = _tick_state_for(panel)
                cif_globals = kw.get("cif_globals") or {}
                export_style_config(
                    out,
                    panel.fig,
                    panel.ax,
                    kw.get("y_data_list") or [],
                    kw.get("labels") or [],
                    kw.get("delta", 0.0),
                    kw.get("args"),
                    tick_state,
                    kw.get("offsets_list") or [],
                    cif_tick_series=cif_globals.get("cif_tick_series"),
                    label_text_objects=kw.get("label_text_objects") or [],
                    overwrite_path=out,
                    force_kind=sub,
                )
                panel.fig._last_style_export_path = os.path.abspath(out)  # type: ignore[attr-defined]

            batch_export_style(
                panels,
                _export_xy_style_panel,
                default_ext=ext,
                path_prompt_single=f"Export {sub} path [.bps/.bpsg, q=cancel]: ",
                purpose=f"batch {sub} export",
            )
            continue

        if cmd in ("ops", "opsg"):
            src = prompt_style_source_index(panels)
            if src is None:
                continue
            source = panels[src]
            path = confirm_previous_path(
                source.fig,
                "_last_style_export_path",
                safe_input=safe_input,
                missing_message="No previous style export found.",
                missing_file_message="Previous export file not found: {path}",
                confirm_prompt="Overwrite '{basename}'? (y/n): ",
            )
            if path:
                kw = normalize_xy_menu_kwargs(source.menu_kwargs)
                tick_state = _tick_state_for(source)
                cif_globals = kw.get("cif_globals") or {}
                try:
                    export_style_config(
                        path,
                        source.fig,
                        source.ax,
                        kw.get("y_data_list") or [],
                        kw.get("labels") or [],
                        kw.get("delta", 0.0),
                        kw.get("args"),
                        tick_state,
                        kw.get("offsets_list") or [],
                        cif_tick_series=cif_globals.get("cif_tick_series"),
                        label_text_objects=kw.get("label_text_objects") or [],
                        overwrite_path=path,
                        force_kind="psg" if cmd == "opsg" else "ps",
                    )
                    print(f"Overwritten style to {path}")
                except Exception as exc:
                    print(f"Overwrite failed: {exc}")
            continue

        if cmd == "s":
            batch_save_sessions(panels, dump_xy_panel)
            continue

        if cmd == "os":
            batch_overwrite_sessions(panels, dump_xy_panel)
            continue

        if cmd == "oe":
            batch_overwrite_figures(panels, export_xy_panel_figure)
            continue

        if cmd == "v":
            from ..xy.peaks import run_peak_finder_menu

            kw = normalize_xy_menu_kwargs(ref.menu_kwargs)
            print("Peak finder runs on the reference plot [1] (read-only / export).")
            try:
                run_peak_finder_menu(
                    ax=ref.ax,
                    x_data_list=kw.get("x_data_list") or [],
                    y_data_list=kw.get("y_data_list") or [],
                    offsets_list=kw.get("offsets_list") or [],
                    labels=kw.get("labels") or [],
                    source_file_paths=kw.get("source_file_paths") or [],
                    safe_input=safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=colorize_prompt,
                )
            except Exception as exc:
                print(f"Peak finder failed: {exc}")
            continue

        if cmd in ("sm", "a", "o", "d", "cif"):
            reasons = {
                "sm": "smoothing is a per-dataset data transform",
                "a": "curve rearrange is data-local to each session",
                "o": "offsets are data-local to each session",
                "d": "derivative is a per-dataset data transform",
                "cif": "CIF overlays require matching phase data on every panel",
            }
            print(f"{cmd!r} is not enabled in batch ({reasons.get(cmd, 'advanced')}).")
            continue

        print(f"Unknown command: {cmd!r}")


__all__ = ["run_xy_batch_menu"]

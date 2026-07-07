"""Batch interactive menu for XY / 1D sessions."""

from __future__ import annotations

import json
import os
from typing import List

import matplotlib.pyplot as plt  # type: ignore[import-untyped]

from ..common.files import confirm_previous_path
from ..common.menu_rendering import print_menu_columns
from ..common.terminal import colorize_prompt, prompt_float, safe_input
from ..xy.axis_range import run_x_range_menu, run_y_range_menu
from ..xy.interactive import normalize_xy_menu_kwargs
from ..xy.style import apply_style_config, export_style_config
from ...plotting import update_labels
from .batch_commands import (
    append_batch_io_shortcuts,
    batch_quit_confirm,
    prompt_style_source_index,
    run_batch_overwrite_sessions,
    run_batch_save_all,
)
from .batch_io import (
    run_batch_export_style,
    run_batch_import_style,
    run_batch_save_sessions,
)
from .common import (
    SyncUndoStacks,
    draw_panels,
    print_batch_header,
    remove_temp_file,
    write_temp_style_json,
)
from .load import XyPanel
from .xy_batch_helpers import (
    dump_xy_panel,
    run_xy_batch_spine_menu,
    sync_axis_limits_from_ref,
    tick_state_for,
)


def _colorize_menu(text: str) -> str:
    if ":" not in text:
        return text
    cmd, desc = text.split(":", 1)
    return f"\033[96m{cmd.strip()}\033[0m: {desc.strip()}"


def _print_xy_batch_menu(panels: List[XyPanel]) -> None:
    col1 = ["c: colors", "f: font", "l: line widths", "t: spines/ticks", "g: figure size"]
    col2 = ["r: rename axis labels", "x: x range", "y: y range"]
    col3 = ["p: export style", "i: import style", "s: save sessions", "s all: save all", "b: undo", "q: quit"]
    append_batch_io_shortcuts(col3, panels)
    print_menu_columns(
        title=f"Batch XY Menu ({len(panels)} plots)",
        columns=[("(Styles)", col1), ("(Geometries)", col2), ("(I/O)", col3)],
        min_widths=(18, 18, 18),
        colorize_item=_colorize_menu,
    )


def _tick_state_for(panel: XyPanel) -> dict:
    return tick_state_for(panel)


def _line_getter(panel: XyPanel):
    def _line(idx: int):
        return panel.ax.lines[idx]

    return _line


def _run_ref_range_menu(ref: XyPanel, panels: List[XyPanel], undo: SyncUndoStacks, axis: str) -> None:
    kw = normalize_xy_menu_kwargs(ref.menu_kwargs)
    args = kw.get("args")
    labels = kw.get("labels") or []
    label_text_objects = kw.get("label_text_objects") or []
    x_data_list = kw.get("x_data_list") or []
    y_data_list = kw.get("y_data_list") or []
    orig_y = kw.get("orig_y") or []
    offsets_list = kw.get("offsets_list") or []
    x_full_list = kw.get("x_full_list") or []
    raw_y_full_list = kw.get("raw_y_full_list") or []

    def _push(_label: str) -> None:
        undo.push_all([_capture_panel(p) for p in panels])

    def _draw_all() -> None:
        draw_panels(panels)

    if axis == "x":
        run_x_range_menu(
            args=args,
            ax=ref.ax,
            fig=ref.fig,
            labels=labels,
            label_text_objects=label_text_objects,
            x_data_list=x_data_list,
            y_data_list=y_data_list,
            orig_y=orig_y,
            offsets_list=offsets_list,
            x_full_list=x_full_list,
            raw_y_full_list=raw_y_full_list,
            push_state=_push,
            _safe_input=safe_input,
            _line=_line_getter(ref),
            colorize_menu=_colorize_menu,
            colorize_prompt=colorize_prompt,
        )
        sync_axis_limits_from_ref(ref, panels, axis="x", draw_all=_draw_all)
    else:
        run_y_range_menu(
            args=args,
            ax=ref.ax,
            fig=ref.fig,
            label_text_objects=label_text_objects,
            y_data_list=y_data_list,
            push_state=_push,
            _safe_input=safe_input,
            colorize_menu=_colorize_menu,
            colorize_prompt=colorize_prompt,
        )
        sync_axis_limits_from_ref(ref, panels, axis="y", draw_all=_draw_all)


def _apply_style_path(panel: XyPanel, path: str) -> None:
    kw = normalize_xy_menu_kwargs(panel.menu_kwargs)
    tick_state = _tick_state_for(panel)
    cif_globals = kw.get("cif_globals") or {}
    apply_style_config(
        path,
        panel.fig,
        panel.ax,
        kw.get("x_data_list"),
        kw.get("y_data_list"),
        kw.get("orig_y"),
        kw.get("offsets_list"),
        kw.get("label_text_objects"),
        kw.get("args"),
        tick_state,
        kw.get("labels"),
        update_labels,
        cif_tick_series=cif_globals.get("cif_tick_series"),
        cif_hkl_label_map=cif_globals.get("cif_hkl_label_map"),
        adjust_margins_cb=lambda: None,
        keep_canvas_fixed=True,
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
            kw.get("y_data_list"),
            kw.get("labels"),
            kw.get("delta", 0.0),
            kw.get("args"),
            tick_state,
            kw.get("offsets_list"),
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
                cmd = safe_input(colorize_prompt("Press a key: "), cancel_on_interrupt=True).strip().lower()
        except (KeyboardInterrupt, EOFError):
            break
        if not cmd:
            continue

        if cmd == "q":
            action = batch_quit_confirm(allow_export=True)
            if action == "y":
                break
            if action == "s":
                pending = "s"
            elif action == "s all":
                pending = "s all"
            continue

        if cmd == "b":
            undo.undo_all(lambda i, snap: _restore_panel(panels[i], snap))
            draw_panels(panels)
            continue

        if cmd == "g":
            w = prompt_float(safe_input, "Figure width (inches): ", on_error="Invalid width.")
            h = prompt_float(safe_input, "Figure height (inches): ", on_error="Invalid height.")
            if w is None or h is None or w <= 0 or h <= 0:
                continue
            undo.push_all([_capture_panel(p) for p in panels])
            for p in panels:
                p.fig.set_size_inches(w, h, forward=True)
            draw_panels(panels)
            continue

        if cmd == "f":
            fs = prompt_float(safe_input, "Font size (blank=keep): ", on_error="Invalid font size.")
            if fs is None:
                continue
            undo.push_all([_capture_panel(p) for p in panels])
            if fs > 0:
                plt.rcParams["font.size"] = fs
            for p in panels:
                for lbl in (p.ax.xaxis.label, p.ax.yaxis.label, p.ax.title):
                    try:
                        if fs > 0:
                            lbl.set_fontsize(fs)
                    except Exception:
                        pass
            draw_panels(panels)
            continue

        if cmd == "l":
            lw = prompt_float(safe_input, "Line width for all curves: ", on_error="Invalid line width.")
            if lw is None or lw <= 0:
                continue
            undo.push_all([_capture_panel(p) for p in panels])
            for p in panels:
                for ln in p.ax.lines:
                    try:
                        ln.set_linewidth(lw)
                    except Exception:
                        pass
            draw_panels(panels)
            continue

        if cmd == "c":
            color = safe_input("Curve color (matplotlib name or #hex, q=cancel): ", cancel_on_interrupt=True).strip()
            if not color or color.lower() == "q":
                continue
            undo.push_all([_capture_panel(p) for p in panels])
            for p in panels:
                for ln in p.ax.lines:
                    try:
                        ln.set_color(color)
                    except Exception:
                        pass
            draw_panels(panels)
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
            xl = safe_input("X-axis label (blank=keep, q=cancel): ", cancel_on_interrupt=True).strip()
            if xl.lower() == "q":
                continue
            yl = safe_input("Y-axis label (blank=keep, q=cancel): ", cancel_on_interrupt=True).strip()
            if yl.lower() == "q":
                continue
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

            run_batch_import_style(
                panels,
                path_prompt="Import style path (.bps/.bpsg, q=cancel): ",
                load_style=_load_xy_style,
                apply_style=lambda panel, style_path: _apply_style_path(panel, style_path),
                prepare=lambda indices: undo.push_indices(
                    indices, [_capture_panel(panels[i]) for i in indices]
                ),
                on_applied=_on_xy_imported,
            )
            continue

        if cmd == "p":
            sub = safe_input("Export style: ps=style only, psg=style+geometry, q=cancel: ", cancel_on_interrupt=True).strip().lower()
            if sub not in ("ps", "psg"):
                continue
            ext = ".bpsg" if sub == "psg" else ".bps"

            def _export_xy_panel(panel: XyPanel, out: str) -> None:
                kw = normalize_xy_menu_kwargs(panel.menu_kwargs)
                tick_state = _tick_state_for(panel)
                cif_globals = kw.get("cif_globals") or {}
                export_style_config(
                    out,
                    panel.fig,
                    panel.ax,
                    kw.get("y_data_list"),
                    kw.get("labels"),
                    kw.get("delta", 0.0),
                    kw.get("args"),
                    tick_state,
                    kw.get("offsets_list"),
                    cif_tick_series=cif_globals.get("cif_tick_series"),
                    label_text_objects=kw.get("label_text_objects"),
                    force_kind=sub,
                )
                panel.fig._last_style_export_path = os.path.abspath(out)  # type: ignore[attr-defined]

            run_batch_export_style(
                panels,
                _export_xy_panel,
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
                        kw.get("y_data_list"),
                        kw.get("labels"),
                        kw.get("delta", 0.0),
                        kw.get("args"),
                        tick_state,
                        kw.get("offsets_list"),
                        cif_tick_series=cif_globals.get("cif_tick_series"),
                        label_text_objects=kw.get("label_text_objects"),
                        overwrite_path=path,
                        force_kind="psg" if cmd == "opsg" else "ps",
                    )
                    print(f"Overwritten style to {path}")
                except Exception as exc:
                    print(f"Overwrite failed: {exc}")
            continue

        if cmd == "s all":
            run_batch_save_all(panels, lambda p: dump_xy_panel(p, p.path))
            continue

        if cmd == "s":
            run_batch_save_sessions(panels, lambda p: dump_xy_panel(p, p.path))
            continue

        if cmd == "os":
            run_batch_overwrite_sessions(panels, dump_xy_panel)
            continue

        print(f"Unknown command: {cmd!r}")


__all__ = ["run_xy_batch_menu"]

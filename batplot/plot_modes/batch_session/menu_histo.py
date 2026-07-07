"""Batch interactive menu for histogram sessions."""

from __future__ import annotations

import json
import os
from typing import List

from ..common.files import confirm_previous_path
from ..common.menu_rendering import print_menu_columns
from ..common.menus import run_option_menu
from ..common.terminal import colorize_prompt, safe_input
from ..histo.labels import run_histo_rename_menu
from ..histo.density_curve import run_histo_density_curve_menu
from ..histo.colors import run_histo_color_menu
from ..histo.fonts import run_histo_font_menu, sync_histo_font_rcparams
from ..histo.interactive import _export_style, _noop_update_labels
from ..histo.load import load_table
from ..histo.plot import apply_histo_geometry, refresh_histo_figure, sync_histo_geometry
from ..histo.session import apply_histo_snapshot, capture_histo_snapshot, save_histo_session
from ..histo.toggles import run_histo_toggle_menu
from ..histo.wizard import HistoSetup, run_histo_wizard
from ...ui import resize_canvas, resize_plot_frame
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
from .common import SyncUndoStacks, draw_panels, print_batch_header
from .load import HistoPanel


def _colorize_menu(text: str) -> str:
    if ":" not in text:
        return text
    cmd, desc = text.split(":", 1)
    return f"\033[96m{cmd.strip()}\033[0m: {desc.strip()}"


def _print_histo_batch_menu(panels: List[HistoPanel]) -> None:
    bw = 0.95
    if panels:
        bw = max(0.01, min(float(panels[0].state.style.bar_width_frac), 1.0))
    col1 = ["c: colors", "f: font", "a: density curve", "t: toggle spines", "g: size"]
    col2 = [f"w: bar width ({bw:g})", "r: rename labels", "x: range/bins"]
    col3 = ["p: export style", "i: import style", "s: save sessions", "s all: save all", "b: undo", "q: quit"]
    append_batch_io_shortcuts(col3, panels)
    print_menu_columns(
        title=f"Batch Histogram Menu ({len(panels)} plots)",
        columns=[("(Styles)", col1), ("(Geometries)", col2), ("(Options)", col3)],
        min_widths=(18, 18, 18),
        colorize_item=_colorize_menu,
    )


def _save_histo_panel(panel: HistoPanel, path: str) -> None:
    save_histo_session(panel.fig, panel.ax, panel.state, path)


def run_histo_batch_menu(panels: List[HistoPanel]) -> None:
    print_batch_header("histo", panels)
    undo = SyncUndoStacks(len(panels))
    undo.push_all([capture_histo_snapshot(p.state, p.fig, p.ax) for p in panels])
    pending: str | None = None
    ref = panels[0]

    def _push_all() -> None:
        undo.push_all([capture_histo_snapshot(p.state, p.fig, p.ax) for p in panels])

    def _refresh_all() -> None:
        for p in panels:
            refresh_histo_figure(p.fig, p.ax, p.state)
        draw_panels(panels)

    def _apply_ref_font_to_all() -> None:
        fam = ref.state.style.font_family
        label_sz = ref.state.style.label_fontsize
        title_sz = ref.state.style.title_fontsize
        for p in panels:
            p.state.style.font_family = fam
            p.state.style.label_fontsize = label_sz
            p.state.style.title_fontsize = title_sz
            sync_histo_font_rcparams(p.state)
        _refresh_all()

    def _batch_toggle(key: str) -> None:
        for p in panels:
            if key == "g":
                p.state.style.show_grid = not p.state.style.show_grid
            elif key == "d":
                p.state.style.density = not p.state.style.density
                p.state.style.ylabel = p.state.y_label_default()
            elif key == "n":
                p.state.style.show_bar_labels = not p.state.style.show_bar_labels
            elif key == "m":
                p.state.style.show_mean_line = not p.state.style.show_mean_line
                p.state.style.show_median_line = not p.state.style.show_median_line

    while True:
        _print_histo_batch_menu(panels)
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
            undo.undo_all(lambda i, snap: apply_histo_snapshot(panels[i].fig, panels[i].ax, panels[i].state, snap))
            draw_panels(panels)
            continue

        if cmd == "c":
            run_histo_color_menu(
                fig=ref.fig,
                ax=ref.ax,
                get_bar_color=lambda: ref.state.style.bar_color,
                set_bar_color=lambda c: [setattr(p.state.style, "bar_color", c) for p in panels],
                get_edge_color=lambda: ref.state.style.edge_color,
                set_edge_color=lambda c: [setattr(p.state.style, "edge_color", c) for p in panels],
                push_state=_push_all,
                refresh=_refresh_all,
                safe_input=safe_input,
                colorize_prompt=colorize_prompt,
            )
            continue

        if cmd == "f":
            run_histo_font_menu(
                state=ref.state,
                push_state=_push_all,
                refresh=_apply_ref_font_to_all,
                safe_input=safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=colorize_prompt,
            )
            continue

        if cmd == "a":
            def _apply_ref_density_to_all() -> None:
                rs = ref.state.style
                for p in panels:
                    ps = p.state.style
                    ps.show_density_curve = rs.show_density_curve
                    ps.density_curve_color = rs.density_curve_color
                    ps.density_curve_lw = rs.density_curve_lw
                    ps.density_curve_ls = rs.density_curve_ls
                    ps.density_curve_alpha = rs.density_curve_alpha
                _refresh_all()

            run_histo_density_curve_menu(
                state=ref.state,
                push_state=_push_all,
                refresh=_apply_ref_density_to_all,
                safe_input=safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=colorize_prompt,
            )
            draw_panels(panels)
            continue

        if cmd == "w":
            cur = max(0.01, min(float(ref.state.style.bar_width_frac), 1.0))
            raw = safe_input(
                colorize_prompt(
                    f"Bar width fraction [{cur:g}] (0–1, fraction of bin width, blank=keep, q=cancel): "
                ),
                cancel_on_interrupt=True,
            ).strip()
            if raw.lower() == "q" or not raw:
                continue
            try:
                val = float(raw)
            except ValueError:
                print("Invalid bar width.")
                continue
            if val <= 0 or val > 1:
                print("Bar width must be between 0 and 1.")
                continue
            undo.push_all([capture_histo_snapshot(p.state, p.fig, p.ax) for p in panels])
            for p in panels:
                p.state.style.bar_width_frac = val
                refresh_histo_figure(p.fig, p.ax, p.state)
            draw_panels(panels)
            print(f"Bar width set to {val:g} on all plots.")
            continue

        if cmd == "g":

            def _apply_ref_geometry_to_all() -> None:
                fw, fh = ref.state.style.figsize
                frac = ref.state.style.axes_fraction
                for p in panels:
                    p.state.style.figsize = (fw, fh)
                    p.state.style.axes_fraction = frac
                    apply_histo_geometry(p.fig, p.ax, p.state)
                    p.fig.canvas.draw_idle()

            def _resize_frame() -> None:
                undo.push_all([capture_histo_snapshot(p.state, p.fig, p.ax) for p in panels])
                try:
                    resize_plot_frame(
                        ref.fig, ref.ax, [], [], type("Args", (), {"stack": False})(), _noop_update_labels
                    )
                    sync_histo_geometry(ref.fig, ref.ax, ref.state)
                    _apply_ref_geometry_to_all()
                except Exception as exc:
                    print(f"Resize failed: {exc}")

            def _resize_canvas_cmd() -> None:
                undo.push_all([capture_histo_snapshot(p.state, p.fig, p.ax) for p in panels])
                try:
                    resize_canvas(ref.fig, ref.ax)
                    sync_histo_geometry(ref.fig, ref.ax, ref.state)
                    _apply_ref_geometry_to_all()
                except Exception as exc:
                    print(f"Resize failed: {exc}")

            run_option_menu(
                prompt="Geom (p/c/q): ",
                options={
                    "p": ("plot frame", _resize_frame),
                    "c": ("canvas", _resize_canvas_cmd),
                },
                safe_input=safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=colorize_prompt,
            )
            draw_panels(panels)
            continue

        if cmd == "r":
            def _apply_ref_labels_to_all() -> None:
                rs = ref.state.style
                for p in panels:
                    ps = p.state.style
                    ps.xlabel = rs.xlabel
                    ps.ylabel = rs.ylabel
                    ps.title = rs.title
                    ps.top_xlabel = rs.top_xlabel
                    refresh_histo_figure(p.fig, p.ax, p.state)
                _refresh_all()

            run_histo_rename_menu(
                fig=ref.fig,
                ax=ref.ax,
                state=ref.state,
                push_state=_push_all,
                refresh=_apply_ref_labels_to_all,
                safe_input=safe_input,
                colorize_prompt=colorize_prompt,
            )
            draw_panels(panels)
            continue

        if cmd == "t":
            sync_targets = [(p.fig, p.ax) for p in panels[1:]]

            def _batch_toggle_display(key: str) -> None:
                _batch_toggle(key)

            try:
                run_histo_toggle_menu(
                    fig=ref.fig,
                    ax=ref.ax,
                    state=ref.state,
                    push_state=_push_all,
                    refresh=_refresh_all,
                    safe_input=safe_input,
                    colorize_prompt=colorize_prompt,
                    colorize_menu=_colorize_menu,
                    toggle_display=_batch_toggle_display,
                    sync_targets=sync_targets or None,
                )
            except Exception as exc:
                print(f"Error in toggle menu: {exc}")
            draw_panels(panels)
            continue

        if cmd == "p":
            run_batch_export_style(
                panels,
                lambda panel, out: _export_style(panel.fig, panel.ax, panel.state, out),
                default_ext=".bpsh",
                path_prompt_single="Export style JSON [.bpsh, q=cancel]: ",
                purpose="batch histogram style export",
            )
            continue

        if cmd == "x":
            src_path = ref.state.source_path
            if not src_path or not os.path.isfile(src_path):
                print("Range/bin editor needs the source data file stored in the session.")
                continue
            try:
                table = load_table(src_path)
            except Exception as exc:
                print(f"Could not load source table: {exc}")
                continue
            new_setup = run_histo_wizard(
                table,
                fixed_col=ref.state.setup.column_index,
            )
            if new_setup is None:
                continue
            _push_all()
            for p in panels:
                old = p.state.setup
                p.state.setup = HistoSetup(
                    column_index=old.column_index,
                    column_name=old.column_name,
                    values=old.values,
                    xmin=new_setup.xmin,
                    xmax=new_setup.xmax,
                    bin_edges=new_setup.bin_edges.copy(),
                )
                refresh_histo_figure(p.fig, p.ax, p.state)
            draw_panels(panels)
            print("Range/bin settings applied to all plots.")
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
                try:
                    _export_style(source.fig, source.ax, source.state, path)
                    print(f"Overwritten style to {path}")
                except Exception as exc:
                    print(f"Overwrite failed: {exc}")
            continue

        if cmd == "i":
            def _load_histo_style(path: str):
                if not os.path.isfile(path):
                    print("File not found.")
                    return None
                with open(path, "r", encoding="utf-8") as fh:
                    return json.load(fh)

            def _on_histo_imported(indices: list[int], _path: str) -> None:
                draw_panels(panels)
                names = ", ".join(str(i + 1) for i in indices)
                print(f"Applied style to plot(s) {names}.")

            run_batch_import_style(
                panels,
                path_prompt="Import style JSON path (q=cancel): ",
                load_style=_load_histo_style,
                apply_style=lambda panel, payload: apply_histo_snapshot(
                    panel.fig, panel.ax, panel.state, payload
                ),
                prepare=lambda indices: undo.push_indices(
                    indices,
                    [capture_histo_snapshot(panels[i].state, panels[i].fig, panels[i].ax) for i in indices],
                ),
                on_applied=_on_histo_imported,
            )
            continue

        if cmd == "s all":
            run_batch_save_all(panels, lambda p: _save_histo_panel(p, p.path))
            continue

        if cmd == "s":
            run_batch_save_sessions(panels, lambda p: _save_histo_panel(p, p.path))
            continue

        if cmd == "os":
            run_batch_overwrite_sessions(panels, _save_histo_panel)
            continue

        print(f"Unknown command: {cmd!r}")


__all__ = ["run_histo_batch_menu"]

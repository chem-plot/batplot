"""Batch interactive menu for histogram sessions."""

from __future__ import annotations

import json
import os
from typing import Any, List

from ..common.files import confirm_previous_path
from ..common.menu_rendering import colorize_menu_item as _colorize_menu, print_menu_columns, prompt_menu_key
from ..common.terminal import colorize_prompt, safe_input
from ..histo.labels import run_histo_rename_menu
from ..histo.density_curve import run_histo_density_curve_menu
from ..histo.colors import run_histo_color_menu
from ..histo.fonts import run_histo_font_menu, sync_histo_font_rcparams
from ..histo.interactive import _export_style, _export_figure
from ..histo.load import load_table
from ..histo.plot import HistoState, normalize_histo_title, refresh_histo_figure
from ..histo.session import apply_histo_snapshot, apply_histo_style_snapshot, capture_histo_snapshot, save_histo_session
from ..histo.toggles import run_histo_toggle_menu
from ..histo.wizard import HistoSetup, run_histo_wizard
from ..histo.line_style import run_histo_line_style_menu, sync_histo_line_style_from_reference
from ..histo.spines import set_histo_spine_color
from ..histo.y_range import run_histo_y_range_menu
from .batch_commands import (
    prompt_style_source_index,
)
from .batch_crosshair import (
    clear_panel_crosshair,
    restore_batch_crosshair_if_was_on,
    snapshot_batch_crosshair_on,
    toggle_batch_crosshair,
)
from .batch_menu_io import (
    batch_export_figures,
    batch_export_style,
    batch_import_style,
    batch_overwrite_figures,
    batch_overwrite_sessions,
    batch_quit_or_save_all,
    batch_save_sessions,
)
from .common import SyncUndoStacks, draw_panels, print_batch_header, set_all_panel_figure_titles
from .batch_menu_helpers import (
    batch_options_menu_column,
    print_batch_pair_status,
    print_batch_scalar_status,
)
from .histo_batch_helpers import (
    run_batch_histo_geom_menu,
)
from .load import HistoPanel


def _print_histo_batch_menu(panels: List[HistoPanel]) -> None:
    col1 = ["c: colors", "f: font", "a: density curve", "l: lines/grid", "t: spines/ticks", "g: size"]
    col2 = ["w: bar width", "r: rename labels", "x: range/bins", "y: y range"]
    col3 = batch_options_menu_column(panels)
    print_menu_columns(
        title=f"Batch Histogram Menu ({len(panels)} plots)",
        columns=[("Styles", col1), ("Geometries", col2), ("Options", col3)],
        min_widths=(18, 18, 18),
        colorize_item=_colorize_menu,
    )


def _save_histo_panel(panel: HistoPanel, path: str) -> None:
    save_histo_session(panel.fig, panel.ax, panel.state, path)


def run_histo_batch_menu(panels: List[HistoPanel]) -> None:
    for p in panels:
        normalize_histo_title(p.state)
        refresh_histo_figure(p.fig, p.ax, p.state)
    set_all_panel_figure_titles(panels)
    print_batch_header("histo", panels)
    undo = SyncUndoStacks(len(panels))
    undo.push_all([capture_histo_snapshot(p.state, p.fig, p.ax) for p in panels])
    pending: str | None = None
    ref = panels[0]

    def _push_all() -> None:
        undo.push_all([capture_histo_snapshot(p.state, p.fig, p.ax) for p in panels])

    def _refresh_all() -> None:
        was_cross = snapshot_batch_crosshair_on(panels)
        for p in panels:
            if was_cross:
                clear_panel_crosshair(p.fig)
            refresh_histo_figure(p.fig, p.ax, p.state)
        draw_panels(panels)
        restore_batch_crosshair_if_was_on(panels, was_cross)

    def _apply_ref_font_to_all() -> None:
        rs = ref.state.style
        for p in panels:
            ps = p.state.style
            ps.font_family = rs.font_family
            ps.label_fontsize = rs.label_fontsize
            ps.title_fontsize = rs.title_fontsize
            ps.font_weight = rs.font_weight
            ps.text_highlight = rs.text_highlight
            ps.text_highlight_fc = rs.text_highlight_fc
            ps.text_highlight_alpha = rs.text_highlight_alpha
            ps.text_highlight_pad = rs.text_highlight_pad
            sync_histo_font_rcparams(p.state)
        _refresh_all()

    def _batch_toggle(key: str) -> None:
        rs = ref.state.style
        if key == "d":
            rs.density = not rs.density
            rs.ylabel = rs.y_label_default()
        elif key == "n":
            rs.show_bar_labels = not rs.show_bar_labels
        elif key == "m":
            rs.show_mean_line = not rs.show_mean_line
            rs.show_median_line = not rs.show_median_line
        for p in panels:
            ps = p.state.style
            ps.density = rs.density
            ps.ylabel = ps.y_label_default()
            ps.show_bar_labels = rs.show_bar_labels
            ps.show_mean_line = rs.show_mean_line
            ps.show_median_line = rs.show_median_line
        _refresh_all()

    while True:
        _print_histo_batch_menu(panels)
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
            if batch_quit_or_save_all(panels, _save_histo_panel):
                break
            continue

        if cmd == "b":
            undo.undo_all(lambda i, snap: apply_histo_snapshot(panels[i].fig, panels[i].ax, panels[i].state, snap))
            draw_panels(panels)
            continue

        if cmd == "n":
            toggle_batch_crosshair(panels)
            continue

        if cmd == "c":
            def _set_bar_color(c: str) -> None:
                for p in panels:
                    setattr(p.state.style, "bar_color", c)

            def _set_edge_color(c: str) -> None:
                for p in panels:
                    setattr(p.state.style, "edge_color", c)

            def _apply_spine_color(side: str, color: str) -> None:
                for p in panels:
                    set_histo_spine_color(p.fig, p.ax, side, color)

            def _finish_spine_colors_only(changed: list[tuple[str, str]]) -> None:
                from batplot.plot_modes.histo.spines import apply_histo_spine_colors, get_histo_spine_colors

                try:
                    ref.fig.canvas.draw()
                except Exception:
                    ref.fig.canvas.draw_idle()
                for p in panels:
                    try:
                        apply_histo_spine_colors(p.fig, p.ax, get_histo_spine_colors(p.fig))
                    except Exception:
                        pass
                draw_panels(panels, full_draw=True)

            run_histo_color_menu(
                fig=ref.fig,
                ax=ref.ax,
                get_bar_color=lambda: ref.state.style.bar_color,
                set_bar_color=_set_bar_color,
                get_edge_color=lambda: ref.state.style.edge_color,
                set_edge_color=_set_edge_color,
                push_state=_push_all,
                refresh=_refresh_all,
                finish_spine_change=_finish_spine_colors_only,
                safe_input=safe_input,
                colorize_prompt=colorize_prompt,
                apply_spine_color=_apply_spine_color,
            )
            continue

        if cmd == "l":
            line_sync_targets: list[tuple[Any, Any, HistoState]] = [
                (p.fig, p.ax, p.state) for p in panels[1:]
            ]

            def _apply_ref_line_style_to_all() -> None:
                if line_sync_targets:
                    sync_histo_line_style_from_reference(ref.ax, ref.state, line_sync_targets)
                _refresh_all()

            run_histo_line_style_menu(
                fig=ref.fig,
                ax=ref.ax,
                state=ref.state,
                push_state=_push_all,
                refresh=_refresh_all,
                safe_input=safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=colorize_prompt,
                on_change=_apply_ref_line_style_to_all,
            )
            draw_panels(panels)
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
            while True:
                print_batch_scalar_status(
                    panels,
                    label="bar width fraction",
                    get_value=lambda p: max(0.01, min(float(p.state.style.bar_width_frac), 1.0)),
                    fmt="{:.4g}",
                )
                raw = safe_input(
                    colorize_prompt(
                        "Bar width fraction (0–1, fraction of bin width, q=back): "
                    ),
                    cancel_on_interrupt=True,
                ).strip()
                if not raw or raw.lower() == "q":
                    break
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
            run_batch_histo_geom_menu(
                panels,
                push_all=_push_all,
                draw_all=_refresh_all,
                colorize_menu=_colorize_menu,
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

        if cmd == "e":
            batch_export_figures(
                panels,
                lambda p, path: _export_figure(p.fig, p.ax, path),
            )
            continue

        if cmd == "p":
            sub = safe_input(
                "Export ps=style only, psg=style+geometry, q=cancel: ",
                cancel_on_interrupt=True,
            ).strip().lower()
            if sub not in ("ps", "psg"):
                continue
            batch_export_style(
                panels,
                lambda panel, out: _export_style(
                    panel.fig,
                    panel.ax,
                    panel.state,
                    out,
                    include_geometry=(sub == "psg"),
                ),
                default_ext=".bpsh",
                path_prompt_single=f"Export {sub} JSON [.bpsh, q=cancel]: ",
                purpose=f"batch histogram {sub} export",
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
            while True:
                new_setup = run_histo_wizard(
                    table,
                    fixed_col=ref.state.setup.column_index,
                )
                if new_setup is None:
                    break
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

        if cmd == "y":
            from ..histo.plot import histo_current_ylim

            def _apply_ref_ylim_to_all() -> None:
                ylim = ref.state.style.ylim
                for p in panels:
                    p.state.style.ylim = ylim
                    refresh_histo_figure(p.fig, p.ax, p.state)
                draw_panels(panels)

            def _batch_histo_ylim_status() -> None:
                print_batch_pair_status(
                    panels,
                    label="histogram Y",
                    get_pair=lambda p: histo_current_ylim(p.state),
                    fmt="{:.6g}",
                )

            run_histo_y_range_menu(
                state=ref.state,
                push_state=_push_all,
                refresh=_apply_ref_ylim_to_all,
                safe_input=safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=colorize_prompt,
                extra_status=_batch_histo_ylim_status,
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
                try:
                    _export_style(
                        source.fig,
                        source.ax,
                        source.state,
                        path,
                        include_geometry=(cmd == "opsg"),
                    )
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
                    payload = json.load(fh)
                kind = payload.get("kind", "")
                if kind and kind != "histo_style":
                    print(f"Not a histogram style file (kind={kind!r}).")
                    return None
                return payload

            def _on_histo_imported(indices: list[int], _path: str) -> None:
                draw_panels(panels)
                names = ", ".join(str(i + 1) for i in indices)
                print(f"Applied style to plot(s) {names}.")

            batch_import_style(
                panels,
                path_prompt="Import style JSON path (q=cancel): ",
                load_style=_load_histo_style,
                apply_style=lambda panel, payload: apply_histo_style_snapshot(
                    panel.fig, panel.ax, panel.state, payload
                ),
                prepare=lambda _indices: _push_all(),
                on_applied=_on_histo_imported,
            )
            continue

        if cmd == "s":
            batch_save_sessions(panels, _save_histo_panel)
            continue

        if cmd == "os":
            batch_overwrite_sessions(panels, _save_histo_panel)
            continue

        if cmd == "oe":
            batch_overwrite_figures(
                panels,
                lambda p, path: _export_figure(p.fig, p.ax, path),
            )
            continue

        print(f"Unknown command: {cmd!r}")


__all__ = ["run_histo_batch_menu"]

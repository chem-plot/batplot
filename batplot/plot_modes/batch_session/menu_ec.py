"""Batch interactive menu for EC sessions."""

from __future__ import annotations

import json
import os
from typing import List

import matplotlib.pyplot as plt  # type: ignore[import-untyped]

from ...batch import _load_style_file
from ..electrochem.colors import (
    _apply_colors,
    _apply_curve_linewidth,
    _iter_cycle_lines,
    _parse_cycle_tokens,
    _parse_fall_cycles_tokens,
    _parse_file_palette_tokens,
    _parse_per_file_cycle_tokens,
    _set_visible_cycles,
    run_ec_cycles_menu,
)
from ..electrochem.labels import run_ec_rename_menu
from ..electrochem.legend import (
    _apply_legend_position,
    _get_legend_title,
    _legend_handles_labels_ncol,
    _legend_no_frame,
    _rebuild_legend,
    _sanitize_legend_offset,
    _set_legend_user_pref,
    _store_legend_title,
)
from ..electrochem.line_style import run_ec_line_style_menu
from ..electrochem.spine_colors import run_ec_spine_color_menu
from ..electrochem.style_apply import apply_ec_style_config
from ..common.batch_font import run_batch_font_menu
from ..common.files import confirm_previous_path
from ..common.fonts import collect_fig_font_artists
from ..common.menu_rendering import colorize_menu_item as _colorize_menu, print_menu_columns, prompt_menu_key
from ..common.menus import run_legend_position_menu
from ..common.terminal import colorize_inline_commands, colorize_prompt, safe_input
from ..electrochem.export import _ec_savefig_plot_window
from ..electrochem.session import dump_ec_session
from ..electrochem.style import _get_geometry_snapshot, _get_style_snapshot
from ...ui import (
    position_bottom_xlabel,
    position_left_ylabel,
    position_right_ylabel,
    position_top_xlabel,
)
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
from .batch_geom_helpers import run_batch_geom_size_menu
from .batch_menu_helpers import (
    batch_options_menu_column,
    prompt_axis_limits,
)
from .common import SyncUndoStacks, draw_panels, print_batch_header, set_all_panel_figure_titles
from .ec_batch_helpers import (
    ec_all_cycles,
    ec_apply_display_mode,
    ec_apply_nice_ticks,
    ec_apply_spine_color,
    ec_normalize_file_data,
    ec_print_file_list_factory,
    ec_run_file_visibility_menu,
    edit_ref_then_sync,
    ensure_ec_fig_state,
    noop_snapshot,
    print_batch_ec_cycles_status,
    run_ec_batch_spine_menu,
)
from ..electrochem.legend_order import run_ec_legend_order_menu
from .load import EcPanel


def _default_tick_state() -> dict:
    return {
        "bx": True,
        "tx": False,
        "ly": True,
        "ry": False,
        "mbx": False,
        "mtx": False,
        "mly": False,
        "mry": False,
    }


def _tick_state_from_fig(fig) -> dict:
    wasd = getattr(fig, "_ec_wasd_state", None)
    if isinstance(wasd, dict):
        top = wasd.get("top", {})
        bot = wasd.get("bottom", {})
        left = wasd.get("left", {})
        right = wasd.get("right", {})
        return {
            "bx": bool(bot.get("ticks", True)),
            "tx": bool(top.get("ticks", False)),
            "ly": bool(left.get("ticks", True)),
            "ry": bool(right.get("ticks", False)),
            "mbx": bool(bot.get("minor", False)),
            "mtx": bool(top.get("minor", False)),
            "mly": bool(left.get("minor", False)),
            "mry": bool(right.get("minor", False)),
            "b_ticks": bool(bot.get("ticks", True)),
            "t_ticks": bool(top.get("ticks", False)),
            "l_ticks": bool(left.get("ticks", True)),
            "r_ticks": bool(right.get("ticks", False)),
            "b_labels": bool(bot.get("labels", True)),
            "t_labels": bool(top.get("labels", False)),
            "l_labels": bool(left.get("labels", True)),
            "r_labels": bool(right.get("labels", False)),
        }
    return _default_tick_state()


def _ec_batch_has_multi_file(panels: List[EcPanel]) -> bool:
    for panel in panels:
        fd = panel.file_data
        if fd and len(fd) > 1:
            return True
    return False


def _print_ec_batch_menu(panels: List[EcPanel]) -> None:
    col1 = [
        "f: font",
        "l: line style",
        "t: spines/ticks",
        "k: spine colors",
        "h: legend",
        "d: display chg/dch",
        "v: show/hide files",
        "g: size",
    ]
    col2 = [
        "c: cycles/colors",
        "r: rename labels/files",
        "x: x range",
        "y: y range",
    ]
    if _ec_batch_has_multi_file(panels):
        col2.append("ra: rearrange legend")
    col3 = batch_options_menu_column(panels)
    print_menu_columns(
        title=f"Batch EC Menu ({len(panels)} plots)",
        columns=[("Styles", col1), ("Geometries", col2), ("Options", col3)],
        min_widths=(20, 22, 18),
        colorize_item=_colorize_menu,
    )


def _ec_batch_font_artists(panel: EcPanel) -> list:
    return collect_fig_font_artists(
        panel.ax,
        panel.fig,
        include_title=True,
        include_axes_texts=True,
    )


def _capture_panel(panel: EcPanel) -> dict:
    from ..common.state_capture import as_style_geom_export

    tick_state = _tick_state_from_fig(panel.fig)
    snap = _get_style_snapshot(
        panel.fig,
        panel.ax,
        panel.cycle_lines or {},
        tick_state,
        panel.file_data,
    )
    return as_style_geom_export(
        snap,
        kind="ec_style_geom",
        geometry=_get_geometry_snapshot(panel.fig, panel.ax),
    )


def _apply_cfg(panel: EcPanel, cfg: dict) -> bool:
    tick_state = _tick_state_from_fig(panel.fig)
    is_multi = bool(panel.file_data and len(panel.file_data) > 1)
    return apply_ec_style_config(
        cfg,
        fig=panel.fig,
        ax=panel.ax,
        cycle_lines=panel.cycle_lines or {},
        file_data=panel.file_data,
        tick_state=tick_state,
        is_multi_file=is_multi,
        silent=False,
    )


def _restore_panel(panel: EcPanel, cfg: dict) -> None:
    _apply_cfg(panel, cfg)
    try:
        panel.fig.canvas.draw_idle()
    except Exception:
        pass


def _push_all(undo: SyncUndoStacks, panels: List[EcPanel]) -> None:
    undo.push_all([_capture_panel(p) for p in panels])


def _ref_menu_context(ref: EcPanel):
    """Return (file_data, cycle_lines, is_multi_file, print_file_list) for the
    reference panel, seeding the fig-level attrs normal-mode legend helpers
    expect (``_ec_file_data``/``_ec_is_multi_file``/``_ec_legend_file_order``)."""
    file_data, cycle_lines, is_multi_file = ec_normalize_file_data(ref)
    ensure_ec_fig_state(ref, file_data, is_multi_file)
    return file_data, cycle_lines, is_multi_file, ec_print_file_list_factory(is_multi_file)


def _save_ec_panel(panel: EcPanel, path: str) -> None:
    dump_ec_session(
        path,
        fig=panel.fig,
        ax=panel.ax,
        cycle_lines=panel.cycle_lines or {},
        file_data=panel.file_data,
        skip_confirm=True,
    )


def _export_ec_panel(panel: EcPanel, path: str) -> None:
    _, ext = os.path.splitext(path)
    _ec_savefig_plot_window(
        panel.fig,
        panel.ax,
        path,
        transparent=ext.lower() == ".svg",
    )
    panel.fig._last_figure_export_path = os.path.abspath(path)  # type: ignore[attr-defined]


def run_ec_batch_menu(panels: List[EcPanel]) -> None:
    set_all_panel_figure_titles(panels)
    print_batch_header("ec_gc", panels)
    # Seed fig-level _ec_file_data/_ec_is_multi_file on every panel so reused
    # normal-mode helpers (_rebuild_legend, apply_ec_style_config sync, etc.)
    # see correct multi-file legend behavior for ALL panels, not just the
    # reference one used for nested submenus.
    for _p in panels:
        _fd, _cl, _multi = ec_normalize_file_data(_p)
        ensure_ec_fig_state(_p, _fd, _multi)
    undo = SyncUndoStacks(len(panels))
    undo.push_all([_capture_panel(p) for p in panels])
    pending: str | None = None
    ref = panels[0]

    while True:
        _print_ec_batch_menu(panels)
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
            if batch_quit_or_save_all(panels, _save_ec_panel):
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
            def _after_ec_geom() -> None:
                for p in panels:
                    ec_apply_nice_ticks(p.ax)

            run_batch_geom_size_menu(
                panels,
                push_undo=lambda: undo.push_all([_capture_panel(p) for p in panels]),
                draw_all=lambda: draw_panels(panels),
                colorize_menu=_colorize_menu,
                on_applied=_after_ec_geom,
            )
            continue

        if cmd == "f":
            run_batch_font_menu(
                panels=panels,
                undo=undo,
                capture_panel=_capture_panel,
                draw_panels=lambda: draw_panels(panels),
                collect_artists=_ec_batch_font_artists,
                safe_input=safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=colorize_prompt,
            )
            continue

        if cmd == "l":
            file_data, cycle_lines, is_multi_file, print_file_list = _ref_menu_context(ref)
            edit_ref_then_sync(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=_apply_cfg,
                draw_all=lambda: draw_panels(panels),
                edit_fn=lambda: run_ec_line_style_menu(
                    fig=ref.fig,
                    ax=ref.ax,
                    cycle_lines=cycle_lines,
                    file_data=file_data,
                    current_file_idx=0,
                    is_multi_file=is_multi_file,
                    is_dqdv=False,
                    print_file_list=print_file_list,
                    iter_cycle_lines=_iter_cycle_lines,
                    rebuild_legend=_rebuild_legend,
                    apply_stored_smooth_settings=lambda *_a, **_k: None,
                    push_state=noop_snapshot,
                    safe_input=safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=colorize_prompt,
                ),
            )
            continue

        if cmd == "t":
            run_ec_batch_spine_menu(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=_apply_cfg,
                draw_all=lambda: draw_panels(panels),
            )
            continue

        if cmd == "k":
            tick_state = _tick_state_from_fig(ref.fig)
            edit_ref_then_sync(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=_apply_cfg,
                draw_all=lambda: draw_panels(panels),
                edit_fn=lambda: run_ec_spine_color_menu(
                    fig=ref.fig,
                    ax=ref.ax,
                    tick_state=tick_state,
                    apply_spine_color=ec_apply_spine_color,
                    push_state=noop_snapshot,
                    safe_input=safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=colorize_prompt,
                ),
            )
            continue

        if cmd == "h":
            def _ec_toggle_legend_ref() -> None:
                leg = ref.ax.get_legend()
                if leg is not None and leg.get_visible():
                    leg.set_visible(False)
                    _set_legend_user_pref(ref.fig, False)
                else:
                    _set_legend_user_pref(ref.fig, True)
                _rebuild_legend(ref.ax)
                try:
                    ref.fig.canvas.draw_idle()
                except Exception:
                    pass

            def _ec_apply_legend_pos_ref() -> None:
                _store_legend_title(ref.fig, ref.ax)
                if not _apply_legend_position(ref.fig, ref.ax):
                    handles, labels, ncol = _legend_handles_labels_ncol(ref.ax)
                    if handles:
                        _legend_no_frame(
                            ref.ax, handles, labels, loc="best", borderaxespad=1.0,
                            title=_get_legend_title(ref.fig), ncol=ncol,
                        )
                try:
                    ref.fig.canvas.draw_idle()
                except Exception:
                    pass

            edit_ref_then_sync(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=_apply_cfg,
                draw_all=lambda: draw_panels(panels),
                edit_fn=lambda: run_legend_position_menu(
                    fig=ref.fig,
                    get_legend=ref.ax.get_legend,
                    get_position=lambda: getattr(ref.fig, "_ec_legend_xy_in", (0.0, 0.0)),
                    set_position=lambda xy: setattr(ref.fig, "_ec_legend_xy_in", xy),
                    sanitize_offset=lambda xy: _sanitize_legend_offset(ref.fig, xy),
                    toggle_legend=_ec_toggle_legend_ref,
                    apply_position=_ec_apply_legend_pos_ref,
                    push_state=noop_snapshot,
                    safe_input=safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=colorize_prompt,
                ),
            )
            continue

        if cmd == "d":
            while True:
                print("\nDisplay mode for ALL plots:")
                print("  " + _colorize_menu("c: show only charge curves (hide discharge)"))
                print("  " + _colorize_menu("d: show only discharge curves (hide charge)"))
                print("  " + _colorize_menu("b: show both charge and discharge"))
                print("  " + _colorize_menu("q: back"))
                sub = safe_input(colorize_prompt("Display (c/d/b/q): "), cancel_on_interrupt=True).strip().lower()
                if not sub or sub == "q":
                    break
                mode = {"c": "charge", "d": "discharge", "b": "both"}.get(sub)
                if mode is None:
                    print("Unknown option.")
                    continue
                _push_all(undo, panels)
                for p in panels:
                    p_file_data, p_cycle_lines, p_is_multi = ec_normalize_file_data(p)
                    ec_apply_display_mode(
                        mode,
                        cycle_lines=p_cycle_lines,
                        file_data=p_file_data,
                        is_multi_file=p_is_multi,
                    )
                    try:
                        p.fig._ec_display_mode = mode
                    except Exception:
                        pass
                draw_panels(panels)
                print(f"Display mode set to '{mode}' on all plots.")
            continue

        if cmd == "c":
            file_data, cycle_lines, is_multi_file, print_file_list = _ref_menu_context(ref)
            edit_ref_then_sync(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=_apply_cfg,
                draw_all=lambda: draw_panels(panels),
                edit_fn=lambda: run_ec_cycles_menu(
                    fig=ref.fig,
                    ax=ref.ax,
                    cycle_lines=cycle_lines,
                    file_data=file_data,
                    current_file_idx=0,
                    all_cycles=ec_all_cycles(cycle_lines, file_data),
                    is_multi_file=is_multi_file,
                    is_dqdv=False,
                    menu_title="",
                    canvas_mode=False,
                    print_file_list=print_file_list,
                    print_menu=lambda *_a, **_k: None,
                    colorize_menu=_colorize_menu,
                    colorize_inline_commands=colorize_inline_commands,
                    colorize_prompt=colorize_prompt,
                    safe_input=safe_input,
                    push_state=noop_snapshot,
                    parse_fall_cycles_tokens=_parse_fall_cycles_tokens,
                    parse_per_file_cycle_tokens=_parse_per_file_cycle_tokens,
                    parse_file_palette_tokens=_parse_file_palette_tokens,
                    parse_cycle_tokens=_parse_cycle_tokens,
                    set_visible_cycles=_set_visible_cycles,
                    apply_colors=_apply_colors,
                    apply_curve_linewidth=_apply_curve_linewidth,
                    apply_stored_smooth_settings=lambda *_a, **_k: None,
                    apply_display_mode=lambda mode: ec_apply_display_mode(
                        mode, cycle_lines=cycle_lines, file_data=file_data, is_multi_file=is_multi_file,
                    ),
                    rebuild_legend=_rebuild_legend,
                    apply_nice_ticks=lambda: ec_apply_nice_ticks(ref.ax),
                    curves_status_fn=lambda: print_batch_ec_cycles_status(panels),
                ),
            )
            continue

        if cmd == "r":
            file_data, _cycle_lines, _is_multi_file, print_file_list = _ref_menu_context(ref)
            tick_state = _tick_state_from_fig(ref.fig)
            edit_ref_then_sync(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=_apply_cfg,
                draw_all=lambda: draw_panels(panels),
                edit_fn=lambda: run_ec_rename_menu(
                    fig=ref.fig,
                    ax=ref.ax,
                    file_data=file_data,
                    tick_state=tick_state,
                    push_state=noop_snapshot,
                    rebuild_legend=_rebuild_legend,
                    print_file_list=print_file_list,
                    safe_input=safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=colorize_prompt,
                    ui_position_top_xlabel=position_top_xlabel,
                    ui_position_bottom_xlabel=position_bottom_xlabel,
                    ui_position_left_ylabel=position_left_ylabel,
                    ui_position_right_ylabel=position_right_ylabel,
                ),
            )
            continue

        if cmd == "x":
            while True:
                lims = prompt_axis_limits(label="EC X", panels=panels, get_panel_limits=lambda p: p.ax.get_xlim())
                if lims is None:
                    break
                _push_all(undo, panels)
                for p in panels:
                    try:
                        p.ax.set_xlim(lims[0], lims[1])
                    except Exception as exc:
                        print(f"X range failed: {exc}")
                draw_panels(panels)
                print(f"EC X set to {lims[0]:.4g} … {lims[1]:.4g} on all plots.")
            continue

        if cmd == "y":
            while True:
                lims = prompt_axis_limits(label="EC Y", panels=panels, get_panel_limits=lambda p: p.ax.get_ylim())
                if lims is None:
                    break
                _push_all(undo, panels)
                for p in panels:
                    try:
                        p.ax.set_ylim(lims[0], lims[1])
                    except Exception as exc:
                        print(f"Y range failed: {exc}")
                draw_panels(panels)
                print(f"EC Y set to {lims[0]:.4g} … {lims[1]:.4g} on all plots.")
            continue

        if cmd == "i":
            def _on_style_imported(indices: list[int], _path: str) -> None:
                draw_panels(panels)
                print(
                    f"Applied style to plot(s) {', '.join(str(i + 1) for i in indices)}."
                )

            batch_import_style(
                panels,
                path_prompt="Import style path (.bps/.bpsg, q=cancel): ",
                load_style=lambda path: _load_style_file(path) or None,
                apply_style=lambda panel, cfg: _apply_cfg(panel, cfg),
                prepare=lambda _indices: undo.push_all([_capture_panel(p) for p in panels]),
                on_applied=_on_style_imported,
            )
            continue

        if cmd == "e":
            batch_export_figures(
                panels,
                _export_ec_panel,
            )
            continue

        if cmd == "p":
            sub = safe_input("Export ps=style, psg=style+geometry, q=cancel: ", cancel_on_interrupt=True).strip().lower()
            if sub not in ("ps", "psg"):
                continue
            ext = ".bpsg" if sub == "psg" else ".bps"

            def _export_ec_style_panel(panel: EcPanel, out: str) -> None:
                cfg = _capture_panel(panel)
                cfg["kind"] = "ec_style_geom" if sub == "psg" else "ec_style"
                if sub == "ps":
                    cfg.pop("geometry", None)
                with open(out, "w", encoding="utf-8") as fh:
                    json.dump(cfg, fh, indent=2)
                panel.fig._last_style_export_path = os.path.abspath(out)  # type: ignore[attr-defined]

            batch_export_style(
                panels,
                _export_ec_style_panel,
                default_ext=ext,
                path_prompt_single="Export path (q=cancel): ",
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
                cfg = _capture_panel(source)
                cfg["kind"] = "ec_style_geom" if cmd == "opsg" else "ec_style"
                if cmd == "ops":
                    cfg.pop("geometry", None)
                try:
                    with open(path, "w", encoding="utf-8") as fh:
                        json.dump(cfg, fh, indent=2)
                    print(f"Overwritten style to {path}")
                except Exception as exc:
                    print(f"Overwrite failed: {exc}")
            continue

        if cmd == "s":
            batch_save_sessions(panels, _save_ec_panel)
            continue

        if cmd == "os":
            batch_overwrite_sessions(panels, _save_ec_panel)
            continue

        if cmd == "oe":
            batch_overwrite_figures(panels, _export_ec_panel)
            continue

        if cmd == "v":
            file_data, _cycle_lines, is_multi_file, print_file_list = _ref_menu_context(ref)
            edit_ref_then_sync(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=_apply_cfg,
                draw_all=lambda: draw_panels(panels),
                edit_fn=lambda: ec_run_file_visibility_menu(
                    file_data=file_data,
                    is_multi_file=is_multi_file,
                    print_file_list=print_file_list,
                    rebuild_legend=_rebuild_legend,
                    fig=ref.fig,
                    ax=ref.ax,
                    push_state=noop_snapshot,
                    safe_input=safe_input,
                    colorize_prompt=colorize_prompt,
                ),
            )
            continue

        if cmd == "ra":
            file_data, _cycle_lines, is_multi_file, print_file_list = _ref_menu_context(ref)
            edit_ref_then_sync(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=_apply_cfg,
                draw_all=lambda: draw_panels(panels),
                edit_fn=lambda: run_ec_legend_order_menu(
                    fig=ref.fig,
                    ax=ref.ax,
                    file_data=file_data,
                    is_multi_file=is_multi_file,
                    print_file_list=print_file_list,
                    rebuild_legend=_rebuild_legend,
                    push_state=noop_snapshot,
                    safe_input=safe_input,
                ),
            )
            continue

        if cmd in ("a", "sm", "2d"):
            reasons = {
                "a": "X-axis ions/capacity mode needs per-dataset capacity constants",
                "sm": "dQ/dV smoothing is a per-dataset data transform",
                "2d": "dQ/dV 2D opens a separate companion figure",
            }
            print(f"{cmd!r} is not enabled in batch ({reasons.get(cmd, 'advanced')}).")
            continue

        print(f"Unknown command: {cmd!r}")


__all__ = ["run_ec_batch_menu"]

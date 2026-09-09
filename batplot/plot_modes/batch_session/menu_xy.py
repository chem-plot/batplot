"""Batch interactive menu for XY / 1D sessions."""

from __future__ import annotations

import json
import os
from typing import List

from ..common.batch_font import run_batch_font_menu
from ..common.files import confirm_previous_path
from ..common.fonts import collect_fig_font_artists
from ..common.menu_rendering import colorize_menu as _colorize_menu, print_menu_columns, prompt_menu_key
from ..common.terminal import colorize_prompt, safe_input
from ..xy.interactive import normalize_xy_menu_kwargs
from ..xy.line_style import run_line_style_menu
from ..xy.style import apply_style_config, export_style_config
from ...plotting import apply_curve_color, update_labels
from ...color_utils import (
    format_color_listing,
    get_user_color_list,
    manage_user_colors,
    prompt_screen_color,
    blank_means_back,
    last_screen_pick_count,
    resolve_color_token,
)

from .operando_batch_helpers import edit_ref_then_sync, noop_snapshot
from .xy_batch_helpers import apply_xy_line_chrome_only
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
    make_style_import_prepare,
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
        "h: legend",
        "g: size",
    ]
    col2 = [
        "r: rename labels",
        "x: x range",
        "y: y range",
        "v: peak finder",
        "cif: CIF ticks (add)",
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
    """Include ``--ry`` twin curves via ``fig._xy_lines_by_curve`` (interactive parity)."""

    def _line(idx: int):
        by_curve = getattr(panel.fig, "_xy_lines_by_curve", None)
        if by_curve is not None and 0 <= idx < len(by_curve):
            return by_curve[idx]
        return panel.ax.lines[idx]

    return _line


def _line_count(panel: XyPanel) -> int:
    by_curve = getattr(panel.fig, "_xy_lines_by_curve", None)
    if by_curve is not None:
        return len(by_curve)
    return len(panel.ax.lines)


def _iter_panel_curve_lines(panel: XyPanel):
    by_curve = getattr(panel.fig, "_xy_lines_by_curve", None)
    if by_curve is not None:
        return list(by_curve)
    lines = list(panel.ax.lines)
    ax2 = getattr(panel.fig, "_xy_ax2", None)
    if ax2 is not None:
        lines.extend(list(ax2.lines))
    return lines


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
                    # ``--txaxis`` twin must track primary xlim (interactive parity).
                    try:
                        from ..xy.axis_range import _sync_xy_twin_xlim

                        _sync_xy_twin_xlim(p.fig, p.ax)
                    except Exception:
                        pass
                    # Match single-session XY: grow CIF peak lists then redraw
                    # so stems outside the previous window appear after expand.
                    try:
                        if hasattr(p.ax, "_cif_extend_func") and callable(p.ax._cif_extend_func):
                            p.ax._cif_extend_func(float(p.ax.get_xlim()[1]))
                    except Exception as _cif_ext_exc:
                        print(f"Warning: CIF tick extend failed: {_cif_ext_exc}")
                    try:
                        if hasattr(p.ax, "_cif_draw_func") and callable(p.ax._cif_draw_func):
                            p.ax._cif_draw_func()
                    except Exception as _cif_draw_exc:
                        print(f"Warning: CIF tick redraw failed: {_cif_draw_exc}")
                else:
                    p.ax.set_ylim(lims[0], lims[1])
                    # ``--ry`` twin Y: autoscale after left-axis edits (interactive).
                    try:
                        from ..xy.axis_range import _autoscale_xy_right_y

                        _autoscale_xy_right_y(p.fig)
                    except Exception:
                        pass
            except Exception as exc:
                print(f"{label} range failed: {exc}")
        _draw_all()
        print(f"{label} set to {lims[0]:.4g} … {lims[1]:.4g} on all plots.")


def _print_batch_xy_current_curves(ref: XyPanel) -> None:
    kw = normalize_xy_menu_kwargs(ref.menu_kwargs)
    labels = kw.get("labels") or []
    get_line = _line_getter(ref)
    print("\nCurrent curves (reference plot; visible only; applied to all panels):")
    any_curve = False
    for idx, label in enumerate(labels):
        try:
            ln = get_line(idx)
        except Exception:
            ln = None
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


def _sync_panel_cif_globals_from_fig(panel: XyPanel) -> None:
    """Keep ``menu_kwargs['cif_globals']`` aligned after style import / undo."""
    kw = normalize_xy_menu_kwargs(panel.menu_kwargs)
    cg = kw.get("cif_globals")
    if not isinstance(cg, dict):
        cg = {}
        panel.menu_kwargs["cif_globals"] = cg
    fig = panel.fig
    try:
        if hasattr(fig, "_bp_show_cif_titles"):
            cg["show_cif_titles"] = bool(fig._bp_show_cif_titles)
        if hasattr(fig, "_bp_show_cif_hkl"):
            cg["show_cif_hkl"] = bool(fig._bp_show_cif_hkl)
        if hasattr(fig, "_bp_cif_set_visible"):
            cg["cif_set_visible"] = list(fig._bp_cif_set_visible)
    except Exception:
        pass


def _seed_fig_cif_flags_from_globals(panel: XyPanel) -> None:
    """Push panel CIF flags onto fig attrs so style export can see them without ``__main__``."""
    kw = normalize_xy_menu_kwargs(panel.menu_kwargs)
    cg = kw.get("cif_globals") or {}
    fig = panel.fig
    try:
        if "show_cif_titles" in cg and cg["show_cif_titles"] is not None:
            fig._bp_show_cif_titles = bool(cg["show_cif_titles"])  # type: ignore[attr-defined]
        if "show_cif_hkl" in cg and cg["show_cif_hkl"] is not None:
            fig._bp_show_cif_hkl = bool(cg["show_cif_hkl"])  # type: ignore[attr-defined]
        if isinstance(cg.get("cif_set_visible"), (list, tuple)):
            fig._bp_cif_set_visible = [bool(v) for v in cg["cif_set_visible"]]  # type: ignore[attr-defined]
    except Exception:
        pass


def _apply_style_path(panel: XyPanel, path: str, *, keep_canvas_fixed: bool = False) -> bool:
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
    ok = apply_style_config(
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
    if ok:
        _sync_panel_cif_globals_from_fig(panel)
    return bool(ok)


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
    _seed_fig_cif_flags_from_globals(panel)
    # Always pass a list (possibly empty) so .bpsg capture embeds
    # cif.tick_series=[] and batch undo can clear a first interactive add.
    cts = cif_globals.get("cif_tick_series")
    if cts is None:
        cts = []
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
            cif_tick_series=cts,
            label_text_objects=kw.get("label_text_objects"),
            overwrite_path=tmp,
            force_kind="psg",
            cif_hkl_label_map=cif_globals.get("cif_hkl_label_map"),
            show_cif_titles=cif_globals.get("show_cif_titles"),
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
                    line_count=lambda: _line_count(ref),
                    push_state=noop_snapshot,
                    safe_input=safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=colorize_prompt,
                )

            def _apply_xy_line_cfg(panel: XyPanel, cfg: dict) -> bool:
                return apply_xy_line_chrome_only(
                    panel,
                    cfg,
                    capture_panel=_capture_panel,
                    restore_panel=_restore_panel,
                )

            edit_ref_then_sync(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=_apply_xy_line_cfg,
                draw_all=lambda: draw_panels(panels),
                edit_fn=_edit_lines,
            )
            continue

        if cmd == "c":
            from ..xy.spines import apply_xy_spine_color

            _spine_keys = {"w": "top", "a": "left", "s": "bottom", "d": "right"}
            while True:
                fig_ref = getattr(ref, "fig", None)
                user_colors = get_user_color_list(fig_ref)
                if user_colors:
                    print("Saved colors (refer as number or u#):")
                    for idx, col in enumerate(user_colors, 1):
                        print(f"  {idx}: {format_color_listing(col)}")
                print("  " + _colorize_menu("Spine colors: w:red a:#4561F7 (syncs to all plots)"))
                print("  " + _colorize_menu("v: show current colors"))
                print("  " + _colorize_menu("u: edit saved colors"))
                print("  " + _colorize_menu("e: pick color from screen"))
                color = safe_input(
                    colorize_prompt(
                        "Curve or spine color for ALL plots (name/#hex, w:red…, v/e/u, q=back): "
                    ),
                    cancel_on_interrupt=True,
                ).strip()
                if color.lower() == "q" or blank_means_back(color):
                    break
                if color.lower() == "v":
                    _print_batch_xy_current_curves(ref)
                    continue
                if color.lower() == "u":
                    manage_user_colors(fig_ref)
                    continue
                tokens = color.split()
                is_spine = bool(tokens) and all(
                    ":" in t and t.split(":", 1)[0].lower() in _spine_keys for t in tokens
                )
                if is_spine:
                    undo.push_all([_capture_panel(p) for p in panels])
                    for tok in tokens:
                        key_part, color_spec = tok.split(":", 1)
                        spine_name = _spine_keys[key_part.lower()]
                        try:
                            resolved = resolve_color_token(color_spec, fig_ref)
                        except Exception:
                            resolved = color_spec
                        for p in panels:
                            try:
                                apply_xy_spine_color(
                                    p.fig, p.ax, tick_state_for(p), spine_name, resolved
                                )
                            except Exception:
                                pass
                        print(f"Set {spine_name} spine to {format_color_listing(resolved)} on all plots.")
                    draw_panels(panels)
                    continue
                if color.lower() == "e":
                    picked = prompt_screen_color(fig_ref)
                    if not picked:
                        continue
                    if last_screen_pick_count() > 1:
                        # Palette grab — saved as u#; do not recolor all curves
                        # with only the last pick.
                        continue
                    color = picked
                else:
                    try:
                        color = resolve_color_token(color, fig_ref)
                    except Exception:
                        print(f"Invalid color: {color!r}")
                        continue
                    try:
                        from matplotlib.colors import to_rgba

                        to_rgba(color)
                    except Exception:
                        print(f"Invalid color: {color!r}")
                        continue
                undo.push_all([_capture_panel(p) for p in panels])
                for p in panels:
                    for ln in _iter_panel_curve_lines(p):
                        try:
                            apply_curve_color(ln, color)
                        except Exception:
                            try:
                                ln.set_color(color)
                            except Exception:
                                pass
                    # Keep on-plot curve name labels in sync with line color.
                    try:
                        kw = normalize_xy_menu_kwargs(p.menu_kwargs)
                        for lbl in (kw.get("label_text_objects") or []):
                            try:
                                lbl.set_color(color)
                            except Exception:
                                pass
                    except Exception:
                        pass
                draw_panels(panels)
                print(f"Color set to {color!r} on all curves.")
            continue

        if cmd == "h":
            # Legend submenu (visibility + corner position), matching single-session ``h``.
            while True:
                print("\n\033[1mLegend submenu (all plots):\033[0m")
                print("  " + _colorize_menu("v: show/hide curve names"))
                try:
                    bot = bool(getattr(ref.fig, "_stack_label_at_bottom", False))
                    left = bool(getattr(ref.fig, "_label_anchor_left", False))
                    cur = f"{'bottom' if bot else 'top'}-{'left' if left else 'right'}"
                except Exception:
                    cur = "top-right"
                print(f"  {_colorize_menu(f's: legend position (current: {cur})')}")
                print(f"  {_colorize_menu('q: back')}")
                sub = safe_input(colorize_prompt("Choose (v/s/q): ")).strip().lower()
                if not sub or sub == "q":
                    break
                if sub == "v":
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
                if sub == "s":
                    print("\nChoose legend position:")
                    print("  " + _colorize_menu("1: top-right"))
                    print("  " + _colorize_menu("2: top-left"))
                    print("  " + _colorize_menu("3: bottom-right"))
                    print("  " + _colorize_menu("4: bottom-left"))
                    choice = safe_input(colorize_prompt("Position (1-4, q=cancel): ")).strip().lower()
                    options = {
                        "1": (False, False),
                        "2": (False, True),
                        "3": (True, False),
                        "4": (True, True),
                    }
                    if not choice or choice == "q":
                        continue
                    if choice not in options:
                        print("Unknown option.")
                        continue
                    bottom, left = options[choice]
                    undo.push_all([_capture_panel(p) for p in panels])
                    for p in panels:
                        try:
                            p.fig._stack_label_at_bottom = bottom  # type: ignore[attr-defined]
                            p.fig._label_anchor_left = left  # type: ignore[attr-defined]
                        except Exception:
                            pass
                        kw = normalize_xy_menu_kwargs(p.menu_kwargs)
                        label_objs = kw.get("label_text_objects") or []
                        try:
                            args = kw.get("args")
                            stack = bool(getattr(args, "stack", False)) if args is not None else False
                            update_labels(
                                p.ax,
                                kw.get("y_data_list") or [],
                                label_objs,
                                stack,
                                bottom,
                            )
                        except Exception:
                            pass
                    draw_panels(panels)
                    print(
                        f"Legend position set to "
                        f"{'bottom' if bottom else 'top'}-{'left' if left else 'right'} "
                        f"on all plots."
                    )
                    continue
                print("Unknown option.")
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
            from ...utils import (
                finalize_axis_label_text,
                print_label_math_help,
                print_recent_axis_names,
                remember_axis_name,
                resolve_recent_axis_name,
            )

            while True:
                xl = safe_input(
                    colorize_prompt(
                        "X-axis label (blank=skip, number=recent, s=show recent, m=math help, q=back): "
                    ),
                    cancel_on_interrupt=True,
                ).strip()
                if xl.lower() == "q":
                    break
                if xl.lower() == "s":
                    print_recent_axis_names(mode="xy")
                    continue
                if xl.lower() == "m":
                    print_label_math_help()
                    continue
                yl = safe_input(
                    colorize_prompt(
                        "Y-axis label (blank=skip, number=recent, s=show recent, m=math help, q=back): "
                    ),
                    cancel_on_interrupt=True,
                ).strip()
                if yl.lower() == "q":
                    break
                if yl.lower() == "s":
                    print_recent_axis_names(mode="xy")
                    continue
                if yl.lower() == "m":
                    print_label_math_help()
                    continue
                if not xl and not yl:
                    break
                if xl:
                    xl = finalize_axis_label_text(resolve_recent_axis_name(xl, mode="xy"))
                    remember_axis_name(xl, mode="xy")
                if yl:
                    yl = finalize_axis_label_text(resolve_recent_axis_name(yl, mode="xy"))
                    remember_axis_name(yl, mode="xy")
                undo.push_all([_capture_panel(p) for p in panels])
                for p in panels:
                    if xl:
                        p.ax.set_xlabel(xl)
                        p.ax._stored_xlabel = xl  # type: ignore[attr-defined]
                        # Match single-panel rename: top duplicate follows bottom x.
                        if hasattr(p.ax, "_top_xlabel_text_override"):
                            try:
                                delattr(p.ax, "_top_xlabel_text_override")
                            except Exception:
                                pass
                    if yl:
                        p.ax.set_ylabel(yl)
                        p.ax._stored_ylabel = yl  # type: ignore[attr-defined]
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
                prepare=make_style_import_prepare(
                    undo, panels, _capture_panel, _restore_panel
                ),
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
                _seed_fig_cif_flags_from_globals(panel)
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
                    cif_hkl_label_map=cif_globals.get("cif_hkl_label_map"),
                    show_cif_titles=cif_globals.get("show_cif_titles"),
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
                _seed_fig_cif_flags_from_globals(source)
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
                        cif_hkl_label_map=cif_globals.get("cif_hkl_label_map"),
                        show_cif_titles=cif_globals.get("show_cif_titles"),
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

        if cmd == "cif":
            # Minimal CIF submenu: add-only (full CIF editor stays single-session).
            while True:
                print("\nCIF (batch — add only):")
                print("  " + _colorize_menu("a: add CIF file(s) to all plots"))
                print("  " + _colorize_menu("q: back"))
                sub = safe_input(
                    colorize_prompt("CIF (a/q): "), cancel_on_interrupt=True
                ).strip().lower()
                if not sub or sub == "q":
                    break
                if sub != "a":
                    print("Only 'a' (add) is available in batch CIF; use single-session for z/t/v/…")
                    continue
                from ...utils import _ask_files_dialog, _parse_typed_path_list
                from ..xy.cif import append_xy_cif_file
                from ..xy.axis_units import get_xy_axis_mode

                print("Select CIF file(s)… (cancel to return)")
                try:
                    picked = _ask_files_dialog(
                        filetypes=(".cif", ".CIF"),
                        title="Select CIF file(s)",
                        multiple=True,
                    )
                except Exception:
                    picked = []
                if not picked:
                    line = safe_input(
                        colorize_prompt(
                            "No file selected. Type CIF path(s) (quote if spaces), q=back: "
                        ),
                        cancel_on_interrupt=True,
                    ).strip()
                    if not line or line.lower() == "q":
                        continue
                    picked = _parse_typed_path_list(line)
                    if not picked:
                        print("No file selected.")
                        continue
                # Optional wavelength when any panel is in 2θ mode (not Q / d).
                needs_wl = False
                for p in panels:
                    kw = normalize_xy_menu_kwargs(p.menu_kwargs)
                    mode = get_xy_axis_mode(
                        p.fig, use_Q=bool(kw.get("use_Q")),
                    )
                    if mode == "2theta":
                        needs_wl = True
                        break
                wl_suffix = ""
                if needs_wl:
                    wl_hint = safe_input(
                        colorize_prompt(
                            "Wavelength Å for 2θ (Enter=session default, q=cancel): "
                        ),
                        cancel_on_interrupt=True,
                    ).strip()
                    if wl_hint.lower() == "q":
                        continue
                    if wl_hint:
                        try:
                            wl_val = float(wl_hint)
                        except ValueError:
                            print("Invalid wavelength; using session default.")
                        else:
                            if wl_val > 0 and wl_val == wl_val:
                                wl_suffix = f":{wl_hint}"
                            else:
                                print("Wavelength must be > 0; using session default.")
                undo.push_all([_capture_panel(p) for p in panels])
                n_ok = 0
                n_adds = 0
                for token_base in picked:
                    token = f"{token_base}{wl_suffix}"
                    for p in panels:
                        kw = normalize_xy_menu_kwargs(p.menu_kwargs)
                        cg = kw.get("cif_globals")
                        if cg is None:
                            cg = {
                                "cif_tick_series": [],
                                "cif_hkl_label_map": {},
                                "cif_hkl_map": {},
                                "show_cif_hkl": False,
                                "show_cif_titles": True,
                            }
                            kw["cif_globals"] = cg
                            p.menu_kwargs["cif_globals"] = cg
                        if cg.get("cif_tick_series") is None:
                            cg["cif_tick_series"] = []
                        bp = type("CIFState", (), cg)()
                        mode = get_xy_axis_mode(p.fig, use_Q=bool(kw.get("use_Q")))
                        use_2th = mode == "2theta"
                        default_wl = getattr(kw.get("args"), "wl", None) or getattr(p.fig, "_xy_wavelength", None)
                        try:
                            append_xy_cif_file(
                                p.fig,
                                p.ax,
                                token,
                                _bp=bp,
                                use_2th=use_2th,
                                default_wl=default_wl,
                                redraw=True,
                                y_data_list=kw.get("y_data_list"),
                            )
                            # Keep dict in sync with CIFState mutations
                            cg["cif_tick_series"] = getattr(bp, "cif_tick_series", cg.get("cif_tick_series"))
                            cg["cif_hkl_label_map"] = getattr(bp, "cif_hkl_label_map", cg.get("cif_hkl_label_map"))
                            n_ok += 1
                            n_adds += 1
                        except Exception as exc:
                            print(f"  Plot {os.path.basename(p.path)}: {exc}")
                if n_ok == 0:
                    # Restore pre-add snaps (discard-only would leave partial mutates).
                    undo.undo_all(lambda i, snap: _restore_panel(panels[i], snap))
                    print("CIF add failed on all plots.")
                else:
                    draw_panels(panels)
                    print(
                        f"Added {len(picked)} CIF file(s) "
                        f"({n_adds} panel-add(s) across {len(panels)} plot(s))."
                    )
            continue

        if cmd in ("sm", "a", "o", "d"):
            from ..common.menu_rendering import format_batch_key_unavailable

            reasons = {
                "sm": "smoothing is a per-dataset data transform",
                "a": "curve rearrange is data-local to each session",
                "o": "offsets are data-local to each session",
                "d": "derivative is a per-dataset data transform",
            }
            print(format_batch_key_unavailable(cmd, reasons.get(cmd, "advanced")))
            continue

        print(f"Unknown command: {cmd!r}")


__all__ = ["run_xy_batch_menu"]

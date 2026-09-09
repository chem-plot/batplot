"""Batch interactive menu for standalone dQ/dV 2D contour sessions.

Reuses the operando (no-EC) style / geometry / p-i-s-b machinery, but:
- saves with ``build_dqdv_2d_snapshot`` (kind=dqdv_2d_contour)
- ``ox`` edits the butterfly potential window and syncs it across panels
- omits CIF / peak / EC side-panel keys that do not apply to contour maps
"""

from __future__ import annotations

import json
import os
from typing import List

from ...batch import _load_style_file
from ..common.batch_font import run_batch_font_menu
from ..common.files import confirm_previous_path
from ..common.menu_rendering import colorize_menu as _colorize_menu, print_menu_columns, prompt_menu_key
from ..common.terminal import (
    colorize_inline_commands,
    colorize_prompt,
    colorize_single_key_inline_commands,
    safe_input,
)
from ..operando.colors import apply_operando_colormap, run_operando_colormap_menu
from ..operando.labels import run_operando_rename_menu
from ..operando.layout import _update_custom_colorbar
from ..operando.layout_menu import run_operando_batch_size_menu
from ..operando.style import build_operando_ec_style_config_v2
from ..operando.visibility import run_visibility_menu
from .batch_commands import prompt_style_source_index
from .batch_crosshair import toggle_batch_crosshair
from .batch_menu_helpers import batch_options_menu_column, prompt_axis_limits, prompt_batch_clim
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
    set_all_panel_figure_titles,
)
from .dqdv_2d_batch_helpers import (
    first_panel_with_dqdv_source,
    panel_potential_window,
    save_dqdv_2d_panel,
    sync_potential_window_all,
)
from .load import OperandoPanel
from .menu_operando import (
    _apply_operando_cfg,
    _capture_panel,
    _export_operando_panel,
    _operando_batch_font_artists,
    _push_all,
    _restore_panel,
)
from .operando_batch_helpers import (
    apply_frame_tick_widths_all,
    apply_operando_colormap_only,
    apply_operando_labels_only,
    apply_operando_visibility_only,
    apply_operando_spine_colors_only,
    apply_operando_wasd_chrome_only,
    edit_ref_then_sync,
    noop_snapshot,
    reverse_y_all,
    run_operando_batch_spine_color_menu,
    run_operando_batch_spine_menu,
    set_clim_all,
    set_operando_ylim_all,
)


def _print_dqdv_2d_batch_menu(panels: List[OperandoPanel]) -> None:
    col1 = [
        "oc: colormap",
        "v: toggle colorbar",
        "t: spines/ticks",
        "k: spine colors",
        "l: line widths",
        "f: font",
        "g: size",
        "r: reverse Y",
    ]
    col2 = [
        "ox: potential window",
        "oy: Y range",
        "oz: intensity range",
        "or: rename labels",
    ]
    col4 = batch_options_menu_column(panels)
    print_menu_columns(
        title=f"Batch dQ/dV 2D Contour Menu ({len(panels)} plots)",
        columns=[
            ("Styles", col1),
            ("Contour", col2),
            ("Options", col4),
        ],
        min_widths=(14, 18, 16),
        colorize_item=_colorize_menu,
    )


def _run_batch_ox_potential_window(
    ref: OperandoPanel,
    panels: List[OperandoPanel],
    undo: SyncUndoStacks,
) -> None:
    """Edit butterfly V_lo/V_hi on a panel with source data, then sync peers."""
    from ..operando.interactive import _dqdv_2d_potential_window_menu

    edit = first_panel_with_dqdv_source(panels)
    if edit is None:
        print(
            "Potential window rebuild needs source dQ/dV line data.\n"
            "These standalone contour .pkl files only store the rendered map — "
            "re-open 2D from a live --dqdv session (2d) to change V_lo/V_hi, "
            "or use oy/oz for view/intensity edits."
        )
        return
    if edit is not ref:
        print(
            f"Reference plot has no rebuild source; editing "
            f"{os.path.basename(edit.path)} (first panel with source data)."
        )

    before = panel_potential_window(edit)
    # Capture pre-edit state so ``b`` can undo even though the submenu already
    # rebuilt the edited map (nested snapshot is a no-op in batch).
    pre_snaps = [_capture_panel(p) for p in panels]
    _dqdv_2d_potential_window_menu(
        edit.fig, edit.ax, edit.im, edit.cbar, noop_snapshot,
    )
    after = panel_potential_window(edit)
    if before is None or after is None or after == before:
        # Cancel / no-op: do not push a junk undo level.
        draw_panels(panels)
        return
    undo.push_all(pre_snaps)
    v_lo, v_hi = after
    n_ok = sync_potential_window_all(panels, v_lo, v_hi)
    # Refresh colorbar chrome after rebuild (clim is preserved; ticks may move).
    for p in panels:
        try:
            _update_custom_colorbar(p.cbar.ax, p.im)
        except Exception:
            pass
    # Window rebuild already updates each panel's map; do not full-style-sync
    # (that would hitchhike cmap/WASD/labels/clim from the reference).
    draw_panels(panels)
    print(
        f"Potential window set to {v_lo:.4g} … {v_hi:.4g} "
        f"(rebuilt map on {n_ok}/{len(panels)} plot(s))."
    )


def run_dqdv_2d_batch_menu(panels: List[OperandoPanel]) -> None:
    """Batch menu for ``kind=dqdv_2d_contour`` panels (OperandoPanel, ec_ax=None)."""
    set_all_panel_figure_titles(panels)
    print_batch_header("dqdv_2d_contour", panels)
    undo = SyncUndoStacks(len(panels))
    undo.push_all([_capture_panel(p) for p in panels])
    pending: str | None = None
    ref = panels[0]

    while True:
        _print_dqdv_2d_batch_menu(panels)
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
            if batch_quit_or_save_all(panels, save_dqdv_2d_panel):
                break
            continue

        if cmd == "b":
            undo.undo_all(lambda i, snap: _restore_panel(panels[i], snap))
            draw_panels(panels)
            continue

        if cmd == "n":
            toggle_batch_crosshair(panels)
            continue

        if cmd in ("g", "ow", "ew", "h"):
            run_operando_batch_size_menu(
                panels,
                push_undo=lambda: _push_all(undo, panels),
                draw_all=lambda: draw_panels(panels),
                safe_input_fn=safe_input,
                colorize_menu_fn=_colorize_menu,
                colorize_prompt_fn=colorize_prompt,
                initial_focus=None if cmd == "g" else cmd,
            )
            continue

        if cmd == "f":
            run_batch_font_menu(
                panels=panels,
                undo=undo,
                capture_panel=_capture_panel,
                draw_panels=lambda: draw_panels(panels),
                collect_artists=_operando_batch_font_artists,
                safe_input=safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=colorize_prompt,
            )
            continue

        if cmd == "oc":
            def _edit_cmap() -> None:
                run_operando_colormap_menu(
                    fig=ref.fig,
                    im=ref.im,
                    cbar=ref.cbar,
                    snapshot=noop_snapshot,
                    update_custom_colorbar=_update_custom_colorbar,
                    safe_input=safe_input,
                    colorize_inline_commands=colorize_inline_commands,
                )

            edit_ref_then_sync(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=apply_operando_colormap_only,
                draw_all=lambda: draw_panels(panels),
                edit_fn=_edit_cmap,
            )
            name = getattr(ref.im, "_operando_cmap_name", None)
            if name:
                for p in panels:
                    try:
                        apply_operando_colormap(p.im, str(name))
                        _update_custom_colorbar(p.cbar.ax, p.im)
                    except Exception:
                        pass
                draw_panels(panels)
            continue

        if cmd == "v":
            edit_ref_then_sync(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=apply_operando_visibility_only,
                draw_all=lambda: draw_panels(panels),
                edit_fn=lambda: run_visibility_menu(
                    fig=ref.fig,
                    ax=ref.ax,
                    im=ref.im,
                    cbar=ref.cbar,
                    ec_ax=None,
                    snapshot=noop_snapshot,
                    safe_input=safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=colorize_prompt,
                    colorize_inline_commands=colorize_single_key_inline_commands,
                ),
            )
            continue

        if cmd == "t":
            run_operando_batch_spine_menu(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=apply_operando_wasd_chrome_only,
                draw_all=lambda: draw_panels(panels),
            )
            continue

        if cmd == "k":
            run_operando_batch_spine_color_menu(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=apply_operando_spine_colors_only,
                draw_all=lambda: draw_panels(panels),
            )
            continue

        if cmd == "l":
            while True:
                print(colorize_inline_commands("Line widths for ALL: '1.5' or 'f t' (frame tick), q=back"))
                inp = safe_input(
                    colorize_prompt("Line widths (q=back): "),
                    cancel_on_interrupt=True,
                ).strip().lower()
                if not inp or inp == "q":
                    break
                try:
                    # Dry-parse first so invalid input does not create a junk undo level.
                    from ..common.spines import parse_frame_tick_widths

                    parse_frame_tick_widths(
                        inp, single_minor_scale=1.0, paired_minor_scale=1.0
                    )
                    _push_all(undo, panels)
                    fw, tw, _mw = apply_frame_tick_widths_all(panels, inp)
                    draw_panels(panels)
                    print(f"Applied frame={fw:.2f}, ticks={tw:.2f} to all plots.")
                except ValueError:
                    print("Invalid number format.")
                except Exception as exc:
                    print(f"Error: {exc}")
            continue

        if cmd == "r":
            _push_all(undo, panels)
            reverse_y_all(panels)
            draw_panels(panels)
            print("Reversed Y orientation on all plots.")
            continue

        if cmd == "ox":
            _run_batch_ox_potential_window(ref, panels, undo)
            continue

        if cmd == "oy":
            while True:
                lims = prompt_axis_limits(
                    label="contour Y",
                    panels=panels,
                    get_panel_limits=lambda p: p.ax.get_ylim(),
                )
                if lims is None:
                    break
                _push_all(undo, panels)
                set_operando_ylim_all(panels, lims[0], lims[1])
                draw_panels(panels)
                print(f"Y range set to {lims[0]:.4g} … {lims[1]:.4g} on all plots.")
            continue

        if cmd == "oz":
            while True:
                clim = prompt_batch_clim(panels, label="intensity")
                if clim is None:
                    break
                vmin, vmax = clim
                _push_all(undo, panels)
                set_clim_all(panels, vmin, vmax)
                draw_panels(panels)
                print(f"Intensity set to {vmin:.4g} … {vmax:.4g} on all plots.")
            continue

        if cmd == "or":
            edit_ref_then_sync(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=apply_operando_labels_only,
                draw_all=lambda: draw_panels(panels),
                edit_fn=lambda: run_operando_rename_menu(
                    fig=ref.fig,
                    ax=ref.ax,
                    snapshot=noop_snapshot,
                    safe_input=safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=colorize_prompt,
                ),
            )
            continue

        if cmd == "i":
            def _on_style_imported(indices: list[int], _path: str) -> None:
                draw_panels(panels)
                print(
                    f"Applied style to plot(s) {', '.join(str(i + 1) for i in indices)}."
                )

            batch_import_style(
                panels,
                path_prompt="Import contour/operando style path (.bps/.bpsg, q=cancel): ",
                load_style=lambda path: _load_style_file(path) or None,
                apply_style=lambda panel, cfg: _apply_operando_cfg(panel, cfg),
                prepare=make_style_import_prepare(
                    undo, panels, _capture_panel, _restore_panel
                ),
                on_applied=_on_style_imported,
            )
            continue

        if cmd == "e":
            batch_export_figures(panels, _export_operando_panel)
            continue

        if cmd == "p":
            sub = safe_input(
                "Export ps=style, psg=style+geometry, q=cancel: ",
                cancel_on_interrupt=True,
            ).strip().lower()
            if sub not in ("ps", "psg"):
                continue
            ext = ".bpsg" if sub == "psg" else ".bps"

            def _export_style_panel(panel: OperandoPanel, out: str) -> None:
                cfg, _ = build_operando_ec_style_config_v2(
                    panel.fig, panel.ax, panel.im, panel.cbar, panel.ec_ax, sub
                )
                with open(out, "w", encoding="utf-8") as fh:
                    json.dump(cfg, fh, indent=2)
                panel.fig._last_style_export_path = os.path.abspath(out)  # type: ignore[attr-defined]

            batch_export_style(
                panels,
                _export_style_panel,
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
                try:
                    cfg, _kind = build_operando_ec_style_config_v2(
                        source.fig,
                        source.ax,
                        source.im,
                        source.cbar,
                        source.ec_ax,
                        "psg" if cmd == "opsg" else "ps",
                    )
                    with open(path, "w", encoding="utf-8") as fh:
                        json.dump(cfg, fh, indent=2)
                    print(f"Overwritten style to {path}")
                except Exception as exc:
                    print(f"Overwrite failed: {exc}")
            continue

        if cmd == "s":
            batch_save_sessions(panels, save_dqdv_2d_panel)
            continue

        if cmd == "os":
            batch_overwrite_sessions(panels, save_dqdv_2d_panel)
            continue

        if cmd == "oe":
            batch_overwrite_figures(panels, _export_operando_panel)
            continue

        print(f"Unknown command: {cmd!r}")


__all__ = ["run_dqdv_2d_batch_menu"]

"""Batch interactive menu for operando+EC sessions."""

from __future__ import annotations

import json
import os
from typing import List

from ...batch import _load_style_file
from ...session import dump_operando_session
from ..common.batch_font import run_batch_font_menu
from ..common.files import confirm_previous_path
from ..common.fonts import collect_operando_font_artists
from ..common.menu_rendering import colorize_menu as _colorize_menu, print_menu_columns, prompt_menu_key
from ..common.terminal import (
    colorize_inline_commands,
    colorize_prompt,
    colorize_single_key_inline_commands,
    safe_input,
)
from ..operando.colors import apply_operando_colormap, run_operando_cif_color_menu, run_operando_colormap_menu
from ..operando.grid import run_ec_grid_menu
from ..operando.ions_axis import (
    clear_ec_ion_overlays,
    install_ec_ions_y_display,
    place_ec_ion_segment_labels,
    restore_ec_time_y_display,
)
from ..operando.labels import run_operando_ec_rename_menu, run_operando_rename_menu
from ..operando.layout import _update_custom_colorbar
from ..operando.layout_menu import run_operando_batch_size_menu
from ..operando.line_style import run_ec_line_style_menu
from ..operando.style import build_operando_ec_style_config_v2
from ..operando.style_apply import apply_operando_ec_style_config
from ..operando.visibility import run_visibility_menu
from .batch_commands import prompt_style_source_index
from .batch_crosshair import toggle_batch_crosshair
from .batch_figure_io import save_standard_panel_figure
from .batch_menu_helpers import (
    batch_options_menu_column,
    prompt_axis_limits,
    prompt_batch_clim,
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
from .common import (
    SyncUndoStacks,
    draw_panels,
    make_style_import_prepare,
    print_batch_header,
    set_all_panel_figure_titles,
)
from .load import OperandoPanel
from .operando_batch_helpers import (
    apply_frame_tick_widths_all,
    apply_operando_cif_colors_only,
    apply_operando_colormap_only,
    apply_operando_ec_curve_only,
    apply_operando_ec_grid_only,
    apply_operando_ec_labels_only,
    apply_operando_ions_only,
    apply_operando_labels_only,
    apply_operando_spine_colors_only,
    apply_operando_visibility_only,
    apply_operando_wasd_chrome_only,
    edit_ref_then_sync,
    noop_snapshot,
    reverse_y_all,
    run_operando_batch_spine_color_menu,
    run_operando_batch_spine_menu,
    set_clim_all,
    set_ec_xlim_all,
    set_ec_ylim_all,
    set_operando_xlim_all,
    set_operando_ylim_all,
)


def _print_operando_batch_menu(panels: List[OperandoPanel]) -> None:
    has_ec = any(p.ec_ax is not None for p in panels)
    col1 = [
        "oc: op colormap",
        "el: EC curve style" if has_ec else None,
        "v: toggle colorbar/ec" if has_ec else "v: toggle colorbar",
        "t: spines/ticks",
        "k: spine colors",
        "l: line widths",
        "f: font",
        "g: size",
        "r: reverse Y",
    ]
    col2 = [
        "ox: X range",
        "oy: Y range",
        "oz: intensity range",
        "or: rename",
        "c: CIF ticks",
        "pk: peak search",
    ]
    col3 = []
    if has_ec:
        col3 = [
            "et: time range",
            "ex: x range",
            "ey: ion labels (time Y)",
            "er: rename",
            "eg: grid",
        ]
    col4 = batch_options_menu_column(panels)
    columns = [
        ("Styles", [x for x in col1 if x]),
        ("Operando", col2),
    ]
    if col3:
        columns.append(("Side Panel", col3))
    columns.append(("Options", col4))
    widths = (14, 14, 14, 16) if col3 else (14, 14, 16)
    print_menu_columns(
        title=f"Batch Operando Menu ({len(panels)} plots)",
        columns=columns,
        min_widths=widths,
        colorize_item=_colorize_menu,
    )


def _operando_batch_font_artists(panel: OperandoPanel) -> list:
    return collect_operando_font_artists(panel.fig, panel.ax, panel.ec_ax, panel.cbar)


def _capture_panel(panel: OperandoPanel) -> dict:
    cfg, _ext = build_operando_ec_style_config_v2(
        panel.fig, panel.ax, panel.im, panel.cbar, panel.ec_ax, "psg"
    )
    return cfg


def _apply_operando_cfg(panel: OperandoPanel, cfg: dict) -> bool:
    return apply_operando_ec_style_config(
        cfg,
        fig=panel.fig,
        ax=panel.ax,
        im=panel.im,
        cbar=panel.cbar,
        ec_ax=panel.ec_ax,
        silent=False,
    )


def _restore_panel(panel: OperandoPanel, cfg: dict) -> None:
    _apply_operando_cfg(panel, cfg)
    try:
        panel.fig.canvas.draw_idle()
    except Exception:
        pass


def _save_operando_panel(panel: OperandoPanel, path: str) -> None:
    ok = dump_operando_session(
        path,
        fig=panel.fig,
        ax=panel.ax,
        im=panel.im,
        cbar=panel.cbar,
        ec_ax=panel.ec_ax,
        skip_confirm=True,
    )
    if not ok:
        raise RuntimeError(f"Failed to save operando session to {path}")


def _export_operando_panel(panel: OperandoPanel, path: str) -> None:
    save_standard_panel_figure(
        panel.fig,
        panel.ax,
        path,
        extra_axes=(panel.ec_ax,),
    )


def _push_all(undo: SyncUndoStacks, panels: List[OperandoPanel]) -> None:
    undo.push_all([_capture_panel(p) for p in panels])


def _run_batch_ey_menu(ref: OperandoPanel, panels: List[OperandoPanel], undo: SyncUndoStacks) -> None:
    """Apply EC y-mode (time/ions) on ref, then sync style (recomputes ions per panel)."""
    if ref.ec_ax is None:
        print("EC panel not available.")
        return

    def _edit() -> None:
        ec_ax = ref.ec_ax
        assert ec_ax is not None
        time_h = getattr(ec_ax, "_ec_time_h", None)
        current_mA = getattr(ec_ax, "_ec_current_mA", None)
        ln = getattr(ec_ax, "_ec_line", None)
        if time_h is None or ln is None:
            print("EC data not available for ion calculation on reference plot.")
            return
        while True:
            sub = safe_input(
                colorize_inline_commands("ey submenu: n=ions, t=time, q=back: "),
                cancel_on_interrupt=True,
            ).strip().lower()
            if not sub:
                continue
            if sub == "q":
                break
            if sub == "t":
                clear_ec_ion_overlays(ec_ax)
                restore_ec_time_y_display(ec_ax)
                try:
                    setattr(ec_ax, "_ions_abs", None)
                except Exception:
                    pass
                ec_ax._ec_y_mode = "time"
                print("EC Y axis: time (ion labels cleared)")
                try:
                    ref.fig.canvas.draw_idle()
                except Exception:
                    pass
                continue
            if sub != "n":
                print("Unknown option.")
                continue
            if current_mA is None:
                print("Current data (_ec_current_mA) required for ions mode.")
                continue
            params = getattr(
                ec_ax,
                "_ion_params",
                {"mass_mg": None, "cap_per_ion_mAh_g": None, "start_ions": None, "material": "cathode"},
            )
            while True:
                mass_mg = params.get("mass_mg")
                cap_per_ion = params.get("cap_per_ion_mAh_g")
                start_ions = params.get("start_ions")
                need = mass_mg is None or cap_per_ion is None or start_ions is None
                if need:
                    prompt = "Enter mass(mg), capacity-per-ion(mAh g^-1), start-ions (e.g. 4.5 26.8 0), q=back: "
                else:
                    prompt = (
                        f"Enter mass,cap-per-ion,start-ions "
                        f"(blank=reuse {mass_mg} {cap_per_ion} {start_ions}; q=back): "
                    )
                s = safe_input(colorize_prompt(prompt), cancel_on_interrupt=True).strip()
                if s.lower() == "q":
                    break
                if s:
                    parts = s.replace(",", " ").split()
                    if len(parts) < 3:
                        print("Need three numbers.")
                        continue
                    try:
                        params = {
                            "mass_mg": float(parts[0]),
                            "cap_per_ion_mAh_g": float(parts[1]),
                            "start_ions": float(parts[2]),
                            "material": params.get("material", "cathode"),
                        }
                    except ValueError:
                        print("Invalid numbers.")
                        continue
                mat = safe_input(
                    colorize_prompt("Material cathode/anode [cathode]: "),
                    cancel_on_interrupt=True,
                ).strip().lower()
                if mat in ("cathode", "anode"):
                    params["material"] = mat
                try:
                    import numpy as np

                    mass_g = float(params["mass_mg"]) / 1000.0
                    t = np.asarray(time_h, dtype=float)
                    i_mA = np.asarray(current_mA, dtype=float)
                    v = np.asarray(getattr(ec_ax, "_ec_voltage_v", None), dtype=float)
                    if t.size < 2 or i_mA.size != t.size:
                        print("EC time/current arrays invalid.")
                        break
                    dt = np.diff(t)
                    cap_increments = np.empty_like(t)
                    cap_increments[0] = 0.0
                    if t.size > 1:
                        cap_increments[1:] = 0.5 * (i_mA[:-1] + i_mA[1:]) * dt
                    cap_mAh = np.cumsum(cap_increments)
                    with np.errstate(divide="ignore", invalid="ignore"):
                        cap_mAh_g = np.where(mass_g > 0, cap_mAh / mass_g, np.nan)
                        ions_delta = np.where(
                            float(params["cap_per_ion_mAh_g"]) > 0,
                            cap_mAh_g / float(params["cap_per_ion_mAh_g"]),
                            np.nan,
                        )
                    if params.get("material") == "anode":
                        ions_delta = -ions_delta
                    ions_abs = float(params["start_ions"]) + ions_delta
                    ec_ax._ion_params = dict(params)
                    ec_ax._ions_abs = ions_abs
                    ec_ax._ec_y_mode = "ions"
                    # Keep time spine; only add ion count labels (same as interactive).
                    install_ec_ions_y_display(ec_ax, t, ions_abs, save_prev=True)
                    place_ec_ion_segment_labels(
                        ec_ax, t, ions_abs,
                        voltage=v if v.size == t.size else None,
                        current_mA=i_mA,
                    )
                    print("Ion labels added (Y spine stays time; syncs to all panels).")
                    try:
                        ref.fig.canvas.draw_idle()
                    except Exception:
                        pass
                    break
                except Exception as exc:
                    print(f"Ions mode failed: {exc}")
                    break

    edit_ref_then_sync(
        ref,
        panels,
        undo=undo,
        capture_panel=_capture_panel,
        apply_cfg=apply_operando_ions_only,
        draw_all=lambda: draw_panels(panels),
        edit_fn=_edit,
    )


def run_operando_batch_menu(panels: List[OperandoPanel]) -> None:
    set_all_panel_figure_titles(panels)
    print_batch_header("operando_ec", panels)
    undo = SyncUndoStacks(len(panels))
    undo.push_all([_capture_panel(p) for p in panels])
    pending: str | None = None
    ref = panels[0]

    while True:
        _print_operando_batch_menu(panels)
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
            if batch_quit_or_save_all(panels, _save_operando_panel):
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
            # Ensure colormap name attribute is present after sync
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

        if cmd == "el":
            edit_ref_then_sync(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=apply_operando_ec_curve_only,
                draw_all=lambda: draw_panels(panels),
                edit_fn=lambda: run_ec_line_style_menu(
                    fig=ref.fig,
                    ec_ax=ref.ec_ax,
                    snapshot=noop_snapshot,
                    safe_input=safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=colorize_prompt,
                ),
            )
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
                    ec_ax=ref.ec_ax,
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
                    try:
                        fw, tw, _mw = apply_frame_tick_widths_all(panels, inp)
                    except Exception:
                        # Restore then drop tip (discard-only leaves cracked panels).
                        undo.undo_all(lambda i, snap: _restore_panel(panels[i], snap))
                        raise
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
            while True:
                lims = prompt_axis_limits(
                    label="operando X",
                    panels=panels,
                    get_panel_limits=lambda p: p.ax.get_xlim(),
                )
                if lims is None:
                    break
                _push_all(undo, panels)
                set_operando_xlim_all(panels, lims[0], lims[1])
                draw_panels(panels)
                print(f"Operando X set to {lims[0]:.4g} … {lims[1]:.4g} on all plots.")
            continue

        if cmd == "oy":
            while True:
                lims = prompt_axis_limits(
                    label="operando Y",
                    panels=panels,
                    get_panel_limits=lambda p: p.ax.get_ylim(),
                )
                if lims is None:
                    break
                _push_all(undo, panels)
                set_operando_ylim_all(panels, lims[0], lims[1])
                draw_panels(panels)
                print(f"Operando Y set to {lims[0]:.4g} … {lims[1]:.4g} on all plots.")
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

        if cmd == "et":
            if ref.ec_ax is None:
                print("EC panel not available.")
                continue
            while True:
                lims = prompt_axis_limits(
                    label="EC time (Y)",
                    panels=panels,
                    get_panel_limits=lambda p: p.ec_ax.get_ylim() if p.ec_ax is not None else (0.0, 1.0),
                )
                if lims is None:
                    break
                _push_all(undo, panels)
                set_ec_ylim_all(panels, lims[0], lims[1])
                draw_panels(panels)
                print(f"EC time range set to {lims[0]:.4g} … {lims[1]:.4g} on all plots.")
            continue

        if cmd == "ex":
            if ref.ec_ax is None:
                print("EC panel not available.")
                continue
            while True:
                lims = prompt_axis_limits(
                    label="EC X",
                    panels=panels,
                    get_panel_limits=lambda p: p.ec_ax.get_xlim() if p.ec_ax is not None else (0.0, 1.0),
                )
                if lims is None:
                    break
                _push_all(undo, panels)
                set_ec_xlim_all(panels, lims[0], lims[1])
                draw_panels(panels)
                print(f"EC X set to {lims[0]:.4g} … {lims[1]:.4g} on all plots.")
            continue

        if cmd == "ey":
            _run_batch_ey_menu(ref, panels, undo)
            continue

        if cmd == "er":
            edit_ref_then_sync(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=apply_operando_ec_labels_only,
                draw_all=lambda: draw_panels(panels),
                edit_fn=lambda: run_operando_ec_rename_menu(
                    fig=ref.fig,
                    ec_ax=ref.ec_ax,
                    snapshot=noop_snapshot,
                    safe_input=safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=colorize_prompt,
                ),
            )
            continue

        if cmd == "eg":
            edit_ref_then_sync(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=apply_operando_ec_grid_only,
                draw_all=lambda: draw_panels(panels),
                edit_fn=lambda: run_ec_grid_menu(
                    fig=ref.fig,
                    ec_ax=ref.ec_ax,
                    snapshot=noop_snapshot,
                    safe_input=safe_input,
                    colorize_prompt=colorize_prompt,
                    colorize_inline_commands=colorize_inline_commands,
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
                path_prompt="Import operando style path (.bps/.bpsg, q=cancel): ",
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
            batch_save_sessions(panels, _save_operando_panel)
            continue

        if cmd == "os":
            batch_overwrite_sessions(panels, _save_operando_panel)
            continue

        if cmd == "oe":
            batch_overwrite_figures(panels, _export_operando_panel)
            continue

        # Tier C: peaks (per-plot; run on reference — data-local, no cross-panel sync)
        if cmd == "pk":
            from ..operando.peaks import run_peak_search_menu

            print("Peak search runs on the reference plot [1] (peaks are data-local).")
            try:
                run_peak_search_menu(
                    im=ref.im,
                    file_paths=None,
                    print_menu=lambda: None,
                    safe_input=safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=colorize_prompt,
                    fig=getattr(ref, "fig", None),
                    ax=getattr(ref, "ax", None),
                )
            except Exception as exc:
                print(f"Peak search failed: {exc}")
            draw_panels(panels)
            continue

        # Tier C: CIF ticks — add sets / sync display flags across panels
        if cmd == "c":
            print("CIF (applied to ALL plots):")
            print("  " + _colorize_menu("a: add CIF file(s)"))
            print("  " + _colorize_menu("c: CIF colors (per set / palette, e=screen pick)"))
            print("  " + _colorize_menu("h: toggle HKL labels"))
            print("  " + _colorize_menu("t: toggle CIF titles"))
            print("  " + _colorize_menu("q: back"))
            sub = safe_input(colorize_prompt("CIF (a/c/h/t/q): "), cancel_on_interrupt=True).strip().lower()
            if not sub or sub == "q":
                continue
            if sub == "a":
                from ...utils import _ask_files_dialog, _parse_typed_path_list
                from ..operando.plot import append_operando_cif_file

                # One multi-select picker; typed path only if dialog empty.
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
                wl_suffix = ""
                # Optional wavelength when any panel uses 2θ axes (once for all picks).
                if any(getattr(p.fig, "_operando_axis_mode", None) == "2theta" for p in panels):
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
                _push_all(undo, panels)
                n_ok = 0
                for token_base in picked:
                    token = f"{token_base}{wl_suffix}"
                    for p in panels:
                        try:
                            append_operando_cif_file(p.fig, p.ax, token, redraw=True)
                            n_ok += 1
                        except Exception as exc:
                            print(f"  Plot {os.path.basename(p.path)}: {exc}")
                expected = len(picked) * len(panels)
                if n_ok < expected:
                    # All-or-nothing: partial success left divergent panels.
                    undo.undo_all(lambda i, snap: _restore_panel(panels[i], snap))
                    if n_ok == 0:
                        print("CIF add failed on all plots.")
                    else:
                        print(
                            f"CIF add incomplete ({n_ok}/{expected}); "
                            "restored all plots."
                        )
                else:
                    draw_panels(panels)
                    print(
                        f"Added {len(picked)} CIF file(s) "
                        f"({n_ok} panel-add(s) across {len(panels)} plot(s))."
                    )
                continue
            has_cif = any(
                bool(getattr(p.ax, "_operando_cif_tick_series", None)) for p in panels
            )
            if not has_cif:
                print("No CIF tick data on these sessions; use a to add.")
                continue
            if sub == "c":
                ref_series = list(getattr(ref.ax, "_operando_cif_tick_series", None) or [])
                if not ref_series:
                    print("Reference plot has no CIF sets; add CIF on all plots first.")
                    continue

                def _edit_cif_colors() -> None:
                    def _redraw(series):
                        ref.ax._operando_cif_tick_series = list(series)
                        from ..operando.layout import _redraw_operando_cif_if_present

                        _redraw_operando_cif_if_present(ref.fig, ref.ax)

                    run_operando_cif_color_menu(
                        fig=ref.fig,
                        ax=ref.ax,
                        cif_series=ref_series,
                        safe_input=safe_input,
                        push_state=noop_snapshot,
                        redraw=_redraw,
                        colorize_prompt=colorize_prompt,
                    )

                edit_ref_then_sync(
                    ref,
                    panels,
                    undo=undo,
                    capture_panel=_capture_panel,
                    apply_cfg=apply_operando_cif_colors_only,
                    draw_all=lambda: draw_panels(panels),
                    edit_fn=_edit_cif_colors,
                )
                continue
            if sub not in ("h", "t"):
                print("Unknown option.")
                continue
            _push_all(undo, panels)
            # Broadcast ref's toggled target to all CIF panels (do not flip each
            # independently — that keeps disagreeing panels forever diverged).
            if sub == "h":
                target = not bool(getattr(ref.fig, "_operando_cif_show_hkl", False))
            else:
                target = not bool(getattr(ref.fig, "_operando_cif_show_titles", True))
            for p in panels:
                if not getattr(p.ax, "_operando_cif_tick_series", None):
                    continue
                if sub == "h":
                    p.fig._operando_cif_show_hkl = target  # type: ignore[attr-defined]
                else:
                    p.fig._operando_cif_show_titles = target  # type: ignore[attr-defined]
                try:
                    from ..operando.layout import _redraw_operando_cif_if_present

                    _redraw_operando_cif_if_present(p.fig, p.ax)
                except Exception:
                    pass
            draw_panels(panels)
            print("CIF display flags updated on panels that have CIF data.")
            continue

        if cmd == "u":
            # Interactive XRD axis-units remesh; batch has no safe all-panel sync.
            from ..common.menu_rendering import format_batch_key_unavailable

            print(
                format_batch_key_unavailable(
                    "u",
                    "axis-unit remesh is per-plot (no safe all-panel sync); use ox/oy for ranges",
                )
            )
            continue

        print(f"Unknown command: {cmd!r}")


__all__ = ["run_operando_batch_menu"]

"""Batch interactive menu for CPC sessions (Tier A/B layout parity)."""

from __future__ import annotations

import json
import os
from typing import List

from ...batch import _load_style_file
from ...ui import finalize_spine_colors_cpc
from ..common.batch_font import run_batch_font_menu
from ..common.files import confirm_previous_path
from ..common.fonts import collect_fig_font_artists
from ..common.menu_rendering import colorize_menu as _colorize_menu, print_menu_columns, prompt_menu_key
from ..common.menus import run_legend_position_menu
from ..common.spines import apply_frame_and_tick_widths, parse_frame_tick_widths
from ..common.terminal import colorize_prompt, safe_input
from ..cpc.colors import run_cpc_color_menu
from ..cpc.style import _apply_style, _style_snapshot
from ..cpc.labels import run_cpc_rename_menu
from ..cpc.overview import run_cpc_overview
from ..cpc.legend import (
    _rebuild_legend,
    _sanitize_legend_offset,
    _visible_handles_labels,
)
from ..cpc.legend_order import run_cpc_legend_order_menu
from ..cpc.session import dump_cpc_session
from ..cpc.snapshots import _apply_cpc_geometry_snapshot, _get_geometry_snapshot
from .batch_commands import prompt_style_source_index
from .batch_crosshair import toggle_batch_crosshair
from .batch_figure_io import save_standard_panel_figure
from .batch_geom_helpers import run_batch_geom_size_menu
from .batch_menu_helpers import batch_options_menu_column, prompt_axis_limits
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
from .cpc_batch_helpers import (
    apply_cpc_colors_only,
    apply_cpc_file_visibility_only,
    apply_cpc_labels_only,
    apply_cpc_legend_only,
    apply_cpc_wasd_chrome_only,
    cpc_normalize_file_data,
    cpc_print_file_list_factory,
    cpc_run_file_visibility_menu,
    cpc_set_spine_color,
    edit_ref_then_sync,
    noop_snapshot,
    run_cpc_batch_spine_menu,
)
from .load import CpcPanel


def _cpc_batch_has_multi_file(panels: List[CpcPanel]) -> bool:
    for panel in panels:
        _fd, is_multi = cpc_normalize_file_data(panel)
        if is_multi:
            return True
        raw = getattr(panel, "file_data", None)
        if raw and len(raw) > 1:
            return True
    return False


def _print_cpc_batch_menu(panels: List[CpcPanel]) -> None:
    col1 = [
        "f: font",
        "l: line widths",
        "m: marker sizes",
        "d: display (Chg/Dch)",
        "ry: show/hide efficiency",
        "t: spines/ticks",
        "h: legend",
        "g: size",
    ]
    if _cpc_batch_has_multi_file(panels):
        col1.insert(-1, "v: show/hide files")
    col2 = [
        "c: colors",
        "r: rename labels",
        "x: x range",
        "y: y ranges",
        "ie: invert efficiency",
    ]
    col3 = batch_options_menu_column(panels)
    col3.insert(1, "o: overview")
    print_menu_columns(
        title=f"Batch CPC Menu ({len(panels)} plots)",
        columns=[("Styles", col1), ("Geometries", col2), ("Options", col3)],
        min_widths=(20, 22, 18),
        colorize_item=_colorize_menu,
    )


def _cpc_batch_font_artists(panel: CpcPanel) -> list:
    return collect_fig_font_artists(
        panel.ax,
        panel.fig,
        include_title=True,
        extra_axes=[panel.ax2],
    )


def _capture_panel(panel: CpcPanel) -> dict:
    from ..common.state_capture import as_style_geom_export

    snap = _style_snapshot(
        panel.fig,
        panel.ax,
        panel.ax2,
        panel.sc_charge,
        panel.sc_discharge,
        panel.sc_eff,
        panel.file_data,
    )
    return as_style_geom_export(
        snap,
        kind="cpc_style_geom",
        geometry=_get_geometry_snapshot(panel.ax, panel.ax2),
    )


def _restore_panel(panel: CpcPanel, cfg: dict) -> None:
    _apply_cpc_style(panel, cfg, apply_geometry=True)


def _apply_cpc_style(panel: CpcPanel, cfg: dict, *, apply_geometry: bool = True) -> bool:
    kind = cfg.get("kind", "")
    if kind and kind not in ("cpc_style", "cpc_style_geom"):
        print(f"Not a CPC style file (kind={kind!r}).")
        return False
    file_ro = bool(cfg.get("ro_active", False))
    current_ro = bool(getattr(panel.fig, "_ro_active", False))
    if file_ro != current_ro:
        if file_ro:
            print("Warning: CPC style was saved with --ro; current plot is not using --ro.")
        else:
            print("Warning: CPC style was saved without --ro; current plot was created with --ro.")
        print("Not applying CPC style/geometry to avoid corrupting axis orientation.")
        return False
    _apply_style(
        panel.fig,
        panel.ax,
        panel.ax2,
        panel.sc_charge,
        panel.sc_discharge,
        panel.sc_eff,
        cfg,
        panel.file_data,
    )
    geometry_cfg = cfg.get("geometry")
    if geometry_cfg is None:
        geometry_cfg = cfg.get("axes_geometry")
    has_geometry = apply_geometry and kind == "cpc_style_geom" and isinstance(geometry_cfg, dict)
    if has_geometry:
        _apply_cpc_geometry_snapshot(panel.ax, panel.ax2, geometry_cfg)
    try:
        panel.fig.canvas.draw_idle()
    except Exception:
        pass
    return True


def _save_cpc_panel(panel: CpcPanel, path: str) -> None:
    ok = dump_cpc_session(
        path,
        fig=panel.fig,
        ax=panel.ax,
        ax2=panel.ax2,
        sc_charge=panel.sc_charge,
        sc_discharge=panel.sc_discharge,
        sc_eff=panel.sc_eff,
        file_data=panel.file_data,
        skip_confirm=True,
    )
    if not ok:
        raise RuntimeError(f"Failed to save CPC session to {path}")


def _export_cpc_panel(panel: CpcPanel, path: str) -> None:
    save_standard_panel_figure(
        panel.fig,
        panel.ax,
        path,
        extra_axes=(panel.ax2,),
        dpi=int(getattr(panel.fig, "dpi", 300) or 300),
    )


def _push_all(undo: SyncUndoStacks, panels: List[CpcPanel]) -> None:
    undo.push_all([_capture_panel(p) for p in panels])


def _apply_display_mode_all(panels: List[CpcPanel], mode: str) -> None:
    from ..cpc.panel_menus import apply_cpc_file_artist_visibility

    for p in panels:
        file_data, _ = cpc_normalize_file_data(p)
        try:
            p.fig._cpc_display_mode = mode
        except Exception:
            pass
        apply_cpc_file_artist_visibility(p.fig, file_data)
        try:
            _rebuild_legend(p.ax, p.ax2, file_data, preserve_position=True)
        except Exception:
            pass


def _set_marker_sizes_all(panels: List[CpcPanel], size: float) -> None:
    for p in panels:
        file_data, _ = cpc_normalize_file_data(p)
        artists = []
        for f in file_data:
            for key in ("sc_charge", "sc_discharge", "sc_eff"):
                sc = f.get(key)
                if sc is not None:
                    artists.append(sc)
        for sc in (p.sc_charge, p.sc_discharge, p.sc_eff):
            if sc is not None and sc not in artists:
                artists.append(sc)
        for sc in artists:
            try:
                if hasattr(sc, "set_sizes"):
                    sc.set_sizes([size])
            except Exception:
                pass


def _toggle_efficiency_all(panels: List[CpcPanel]) -> bool:
    """Toggle efficiency visibility using reference state; return new visible flag.

    Mirrors interactive ``ry``: series + tick/label/title chrome only (never
    ``ax2.set_visible``, which would hide the right spine).
    """
    from ..cpc.panel_menus import (
        _cpc_efficiency_globally_on,
        apply_cpc_file_artist_visibility,
    )
    from ..common.spines import sync_tick_state_from_wasd

    ref = panels[0]
    file_data0, _ = cpc_normalize_file_data(ref)
    # Same global ry intent as interactive (wasd / visible-file fallback).
    new_vis = not _cpc_efficiency_globally_on(ref.fig, file_data0)
    for p in panels:
        file_data, _ = cpc_normalize_file_data(p)
        try:
            p.ax2.yaxis.label.set_visible(new_vis)
            p.ax2.tick_params(axis="y", right=new_vis, labelright=new_vis)
        except Exception:
            pass
        try:
            wasd = getattr(p.fig, "_cpc_wasd_state", None)
            if not isinstance(wasd, dict):
                wasd = {}
            wasd.setdefault("right", {})
            wasd["right"]["ticks"] = bool(new_vis)
            wasd["right"]["labels"] = bool(new_vis)
            wasd["right"]["title"] = bool(new_vis)
            p.fig._cpc_wasd_state = wasd
            ts = getattr(p.ax, "_saved_tick_state", None)
            if isinstance(ts, dict):
                sync_tick_state_from_wasd(
                    ts,
                    wasd,
                    tick_defaults={
                        "top": False,
                        "bottom": True,
                        "left": True,
                        "right": True,
                    },
                    label_defaults={
                        "top": False,
                        "bottom": True,
                        "left": True,
                        "right": True,
                    },
                )
                p.ax._saved_tick_state = dict(ts)
                if getattr(p, "tick_state", None) is not None:
                    p.tick_state.clear()
                    p.tick_state.update(ts)
        except Exception:
            pass
        apply_cpc_file_artist_visibility(p.fig, file_data, eff_on=bool(new_vis))
        try:
            if p.sc_eff is not None and not file_data:
                p.sc_eff.set_visible(new_vis)
        except Exception:
            pass
        try:
            _rebuild_legend(p.ax, p.ax2, file_data, preserve_position=True)
        except Exception:
            pass
    return new_vis


def _cpc_eff_inverted_flag(panel: CpcPanel) -> bool:
    """Return whether efficiency is currently inverted on *panel* (first file).

    Single-file panels use an ephemeral ``file_data`` stub, so the flag is also
    mirrored on ``fig._cpc_eff_inverted`` for round-trips within a batch session.
    """
    if panel.file_data:
        for f in panel.file_data:
            if f.get("sc_eff") is not None:
                return bool(f.get("eff_inverted", False))
    return bool(getattr(panel.fig, "_cpc_eff_inverted", False))


def _invert_efficiency_all(panels: List[CpcPanel]) -> bool:
    """Invert efficiency around 100% to a shared target from the reference panel.

    Mirrors ``ry``/``d``: compute desired state from ref, then bring every panel
    to that state (do not blindly toggle peers that already differ).
    Returns the new inverted flag.
    """
    ref = panels[0]
    new_inv = not _cpc_eff_inverted_flag(ref)
    for p in panels:
        file_data, _ = cpc_normalize_file_data(p)
        seen: set[int] = set()
        cur_panel = _cpc_eff_inverted_flag(p)
        for f in file_data:
            sc = f.get("sc_eff")
            if sc is None or id(sc) in seen:
                continue
            seen.add(id(sc))
            try:
                cur = (
                    bool(f.get("eff_inverted", False))
                    if p.file_data
                    else cur_panel
                )
                if cur != new_inv:
                    offsets = sc.get_offsets()
                    if offsets is not None and len(offsets) > 0:
                        xs = offsets[:, 0]
                        ys = offsets[:, 1]
                        sc.set_offsets(list(zip(xs, 200.0 - ys)))
                f["eff_inverted"] = new_inv
            except Exception as exc:
                print(f"Invert efficiency failed: {exc}")
        try:
            p.fig._cpc_eff_inverted = new_inv
        except Exception:
            pass
    return new_inv


def run_cpc_batch_menu(panels: List[CpcPanel]) -> None:
    set_all_panel_figure_titles(panels)
    print_batch_header("cpc", panels)
    undo = SyncUndoStacks(len(panels))
    undo.push_all([_capture_panel(p) for p in panels])
    pending: str | None = None
    ref = panels[0]

    while True:
        _print_cpc_batch_menu(panels)
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
            if batch_quit_or_save_all(panels, _save_cpc_panel):
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
            def _after_cpc_geom() -> None:
                # batch_geom helpers only move primary ax; keep twin locked.
                for p in panels:
                    try:
                        if getattr(p, "ax2", None) is not None:
                            p.ax2.set_position(p.ax.get_position())
                    except Exception:
                        pass

            run_batch_geom_size_menu(
                panels,
                push_undo=lambda: _push_all(undo, panels),
                draw_all=lambda: draw_panels(panels),
                colorize_menu=_colorize_menu,
                on_applied=_after_cpc_geom,
            )
            continue

        if cmd == "f":
            run_batch_font_menu(
                panels=panels,
                undo=undo,
                capture_panel=_capture_panel,
                draw_panels=lambda: draw_panels(panels),
                collect_artists=_cpc_batch_font_artists,
                safe_input=safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=colorize_prompt,
            )
            continue

        if cmd == "l":
            while True:
                print("Line widths for ALL plots:")
                print("  " + _colorize_menu("f: frame/tick widths"))
                print("  " + _colorize_menu("g: toggle grid lines"))
                print("  " + _colorize_menu("q: back"))
                sub = safe_input(colorize_prompt("Choose (f/g/q): "), cancel_on_interrupt=True).strip().lower()
                if not sub or sub == "q":
                    break
                if sub == "g":
                    # Converge all panels to the toggled ref grid state (ry/d pattern).
                    def _grid_on(ax) -> bool:
                        try:
                            for line in ax.get_xgridlines() + ax.get_ygridlines():
                                if line.get_visible():
                                    return True
                        except Exception:
                            pass
                        return False

                    new_grid = not _grid_on(ref.ax)
                    _push_all(undo, panels)
                    for p in panels:
                        try:
                            if new_grid:
                                p.ax.grid(
                                    True,
                                    color="0.85",
                                    linestyle="-",
                                    linewidth=0.5,
                                    alpha=0.7,
                                )
                            else:
                                p.ax.grid(False)
                        except Exception as exc:
                            print(f"Grid toggle failed: {exc}")
                    draw_panels(panels)
                    print(f"Grid {'enabled' if new_grid else 'disabled'} on all plots.")
                    continue
                if sub != "f":
                    print("Unknown option.")
                    continue
                while True:
                    fw_in = safe_input(
                        colorize_prompt("Frame/tick width (e.g. 1.5 or '1.5 2', q=back): "),
                        cancel_on_interrupt=True,
                    ).strip()
                    if not fw_in or fw_in.lower() == "q":
                        break
                    try:
                        frame_w, tick_w, tick_minor = parse_frame_tick_widths(
                            fw_in, single_minor_scale=1.0, paired_minor_scale=1.0
                        )
                        # Allow 0 (parity with interactive ``l``); reject negatives only.
                        frame_w = max(0.0, frame_w)
                        tick_w = max(0.0, tick_w)
                        tick_minor = max(0.0, tick_minor)
                        _push_all(undo, panels)
                        for p in panels:
                            apply_frame_and_tick_widths(
                                [p.ax, p.ax2],
                                frame_width=frame_w,
                                major_width=tick_w,
                                minor_width=tick_minor,
                            )
                            try:
                                finalize_spine_colors_cpc(
                                    p.fig, p.ax, p.ax2, tick_state=p.tick_state or None
                                )
                            except Exception:
                                pass
                        draw_panels(panels)
                        print(f"Applied frame={frame_w:.2f}, ticks={tick_w:.2f} to all plots.")
                    except ValueError:
                        print("Invalid number format.")
                    except Exception as exc:
                        print(f"Error: {exc}")
            continue

        if cmd == "m":
            while True:
                spec = safe_input(
                    colorize_prompt("Marker size for ALL series/plots (q=back): "),
                    cancel_on_interrupt=True,
                ).strip().lower()
                if not spec or spec == "q":
                    break
                try:
                    num = float(spec)
                    # Size 0 hides markers (interactive ``m`` / style parity).
                    if num < 0:
                        print("Size must be >= 0.")
                        continue
                except ValueError:
                    print("Invalid value.")
                    continue
                _push_all(undo, panels)
                _set_marker_sizes_all(panels, num)
                draw_panels(panels)
                print(f"Marker size set to {num:g} on all plots.")
            continue

        if cmd == "c":
            file_data, is_multi = cpc_normalize_file_data(ref)
            print_file_list = cpc_print_file_list_factory(is_multi)

            def _set_spine(side: str, color) -> None:
                cpc_set_spine_color(
                    ref.fig,
                    ref.ax,
                    ref.ax2,
                    side,
                    color,
                    tick_state=getattr(ref, "tick_state", None),
                )

            edit_ref_then_sync(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=apply_cpc_colors_only,
                draw_all=lambda: draw_panels(panels),
                edit_fn=lambda: run_cpc_color_menu(
                    fig=ref.fig,
                    ax=ref.ax,
                    ax2=ref.ax2,
                    file_data=file_data,
                    is_multi_file=is_multi,
                    sc_charge=ref.sc_charge,
                    sc_eff=ref.sc_eff,
                    push_state=noop_snapshot,
                    set_spine_color=_set_spine,
                    rebuild_legend=lambda: _rebuild_legend(
                        ref.ax, ref.ax2, file_data, preserve_position=True
                    ),
                    safe_input=safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=colorize_prompt,
                ),
            )
            continue

        if cmd == "d":
            while True:
                print("\nDisplay mode for ALL plots:")
                print("  " + _colorize_menu("c: show only charge"))
                print("  " + _colorize_menu("d: show only discharge"))
                print("  " + _colorize_menu("b: show both"))
                print("  " + _colorize_menu("q: back"))
                sub = safe_input(colorize_prompt("Display (c/d/b/q): "), cancel_on_interrupt=True).strip().lower()
                if not sub or sub == "q":
                    break
                mode = {"c": "charge", "d": "discharge", "b": "both"}.get(sub)
                if mode is None:
                    print("Unknown option.")
                    continue
                _push_all(undo, panels)
                _apply_display_mode_all(panels, mode)
                draw_panels(panels)
                print(f"Display mode set to '{mode}' on all plots.")
            continue

        if cmd == "ry":
            _push_all(undo, panels)
            vis = _toggle_efficiency_all(panels)
            draw_panels(panels)
            print(f"Efficiency axis {'shown' if vis else 'hidden'} on all plots.")
            continue

        if cmd == "t":
            run_cpc_batch_spine_menu(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=apply_cpc_wasd_chrome_only,
                draw_all=lambda: draw_panels(panels),
            )
            continue

        if cmd == "h":
            file_data, is_multi = cpc_normalize_file_data(ref)
            print_file_list = cpc_print_file_list_factory(is_multi)

            def _toggle_legend() -> None:
                try:
                    leg = ref.ax.get_legend()
                    if leg is not None and leg.get_visible():
                        leg.set_visible(False)
                    else:
                        handles, _labels = _visible_handles_labels(ref.ax, ref.ax2)
                        if handles:
                            _rebuild_legend(ref.ax, ref.ax2, file_data, preserve_position=True)
                        else:
                            print("No visible legend items found.")
                    ref.fig.canvas.draw_idle()
                except Exception as exc:
                    print(f"Error toggling legend: {exc}")

            def _apply_pos() -> None:
                try:
                    _rebuild_legend(ref.ax, ref.ax2, file_data, preserve_position=True)
                    ref.fig.canvas.draw_idle()
                except Exception as exc:
                    print(f"Error applying legend position: {exc}")

            def _rearrange_legend() -> None:
                run_cpc_legend_order_menu(
                    fig=ref.fig,
                    ax=ref.ax,
                    ax2=ref.ax2,
                    file_data=file_data,
                    is_multi_file=is_multi,
                    print_file_list=print_file_list,
                    rebuild_legend=_rebuild_legend,
                    push_state=noop_snapshot,
                    safe_input=safe_input,
                )

            edit_ref_then_sync(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=apply_cpc_legend_only,
                draw_all=lambda: draw_panels(panels),
                edit_fn=lambda: run_legend_position_menu(
                    fig=ref.fig,
                    get_legend=ref.ax.get_legend,
                    get_position=lambda: getattr(ref.fig, "_cpc_legend_xy_in", (0.0, 0.0)),
                    set_position=lambda xy: setattr(ref.fig, "_cpc_legend_xy_in", xy),
                    sanitize_offset=_sanitize_legend_offset,
                    toggle_legend=_toggle_legend,
                    apply_position=_apply_pos,
                    push_state=noop_snapshot,
                    safe_input=safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=colorize_prompt,
                    rearrange_legend=_rearrange_legend if is_multi else None,
                ),
            )
            continue

        if cmd == "r":
            file_data, is_multi = cpc_normalize_file_data(ref)
            print_file_list = cpc_print_file_list_factory(is_multi)
            # Labels-only: full style apply would overwrite peer series colors.
            edit_ref_then_sync(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=apply_cpc_labels_only,
                draw_all=lambda: draw_panels(panels),
                edit_fn=lambda: run_cpc_rename_menu(
                    fig=ref.fig,
                    ax=ref.ax,
                    ax2=ref.ax2,
                    file_data=file_data,
                    current_file_idx=0,
                    is_multi_file=is_multi,
                    push_state=noop_snapshot,
                    rebuild_legend=lambda: _rebuild_legend(
                        ref.ax, ref.ax2, file_data, preserve_position=True
                    ),
                    print_file_list=print_file_list,
                    safe_input=safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=colorize_prompt,
                ),
            )
            continue

        if cmd == "x":
            while True:
                lims = prompt_axis_limits(label="CPC X", panels=panels, get_panel_limits=lambda p: p.ax.get_xlim())
                if lims is None:
                    break
                _push_all(undo, panels)
                for p in panels:
                    try:
                        p.ax.set_xlim(lims[0], lims[1])
                    except Exception as exc:
                        print(f"X range failed: {exc}")
                draw_panels(panels)
                print(f"X set to {lims[0]:.4g} … {lims[1]:.4g} on all plots.")
            continue

        if cmd == "y":
            while True:
                print("Y ranges for ALL plots:")
                print("  " + _colorize_menu("ly: left Y (capacity)"))
                print("  " + _colorize_menu("ry: right Y (efficiency)"))
                print("  " + _colorize_menu("q: back"))
                sub = safe_input(colorize_prompt("Y target (ly/ry/q): "), cancel_on_interrupt=True).strip().lower()
                if not sub or sub == "q":
                    break
                if sub == "ly":
                    lims = prompt_axis_limits(
                        label="CPC left Y",
                        panels=panels,
                        get_panel_limits=lambda p: p.ax.get_ylim(),
                    )
                    if lims is None:
                        continue
                    _push_all(undo, panels)
                    for p in panels:
                        try:
                            p.ax.set_ylim(lims[0], lims[1])
                        except Exception as exc:
                            print(f"Left Y failed: {exc}")
                    draw_panels(panels)
                    print(f"Left Y set to {lims[0]:.4g} … {lims[1]:.4g} on all plots.")
                elif sub == "ry":
                    lims = prompt_axis_limits(
                        label="CPC right Y",
                        panels=panels,
                        get_panel_limits=lambda p: p.ax2.get_ylim(),
                    )
                    if lims is None:
                        continue
                    _push_all(undo, panels)
                    for p in panels:
                        try:
                            p.ax2.set_ylim(lims[0], lims[1])
                        except Exception as exc:
                            print(f"Right Y failed: {exc}")
                    draw_panels(panels)
                    print(f"Right Y set to {lims[0]:.4g} … {lims[1]:.4g} on all plots.")
                else:
                    print("Unknown option.")
            continue

        if cmd == "ie":
            _push_all(undo, panels)
            new_inv = _invert_efficiency_all(panels)
            draw_panels(panels)
            print(
                f"Efficiency {'inverted' if new_inv else 'restored'} around 100% "
                f"on all plots."
            )
            continue

        if cmd == "o":
            # Overview for each batch panel (reference first, then remaining)
            for i, p in enumerate(panels):
                file_data, _ = cpc_normalize_file_data(p)
                print(f"\n--- Plot {i + 1}: {os.path.basename(p.path)} ---")
                try:
                    run_cpc_overview(
                        file_data,
                        ax=p.ax,
                        safe_input=safe_input,
                        colorize_menu=_colorize_menu,
                        colorize_prompt=colorize_prompt,
                        print_file_list=None,
                        include_hidden=False,
                    )
                except Exception as exc:
                    print(f"Error in overview: {exc}")
            continue

        if cmd == "i":
            def _on_style_imported(indices: list[int], _path: str) -> None:
                draw_panels(panels)
                print(f"Applied style to plot(s) {', '.join(str(i + 1) for i in indices)}.")

            batch_import_style(
                panels,
                path_prompt="Import style path (.bps/.bpsg, q=cancel): ",
                load_style=lambda path: _load_style_file(path) or None,
                apply_style=lambda panel, cfg: _apply_cpc_style(panel, cfg, apply_geometry=True),
                prepare=make_style_import_prepare(
                    undo, panels, _capture_panel, _restore_panel
                ),
                on_applied=_on_style_imported,
            )
            continue

        if cmd == "e":
            batch_export_figures(panels, _export_cpc_panel)
            continue

        if cmd == "p":
            sub = safe_input(
                "Export ps=style, psg=style+geometry, q=cancel: ",
                cancel_on_interrupt=True,
            ).strip().lower()
            if sub not in ("ps", "psg"):
                continue
            ext = ".bpsg" if sub == "psg" else ".bps"

            def _export_style_panel(panel: CpcPanel, out: str) -> None:
                cfg = _capture_panel(panel)
                cfg["kind"] = "cpc_style_geom" if sub == "psg" else "cpc_style"
                if sub == "ps":
                    cfg.pop("geometry", None)
                    fig_block = cfg.get("figure")
                    if isinstance(fig_block, dict):
                        for key in ("canvas_size", "frame_size", "axes_fraction", "size"):
                            fig_block.pop(key, None)
                        if not fig_block:
                            cfg.pop("figure", None)
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
                cfg = _capture_panel(source)
                cfg["kind"] = "cpc_style_geom" if cmd == "opsg" else "cpc_style"
                if cmd == "ops":
                    cfg.pop("geometry", None)
                    fig_block = cfg.get("figure")
                    if isinstance(fig_block, dict):
                        for key in ("canvas_size", "frame_size", "axes_fraction", "size"):
                            fig_block.pop(key, None)
                        if not fig_block:
                            cfg.pop("figure", None)
                try:
                    with open(path, "w", encoding="utf-8") as fh:
                        json.dump(cfg, fh, indent=2)
                    print(f"Overwritten style to {path}")
                except Exception as exc:
                    print(f"Overwrite failed: {exc}")
            continue

        if cmd == "s":
            batch_save_sessions(panels, _save_cpc_panel)
            continue

        if cmd == "os":
            batch_overwrite_sessions(panels, _save_cpc_panel)
            continue

        if cmd == "oe":
            batch_overwrite_figures(panels, _export_cpc_panel)
            continue

        if cmd == "v":
            file_data, is_multi = cpc_normalize_file_data(ref)
            print_file_list = cpc_print_file_list_factory(is_multi)
            edit_ref_then_sync(
                ref,
                panels,
                undo=undo,
                capture_panel=_capture_panel,
                apply_cfg=apply_cpc_file_visibility_only,
                draw_all=lambda: draw_panels(panels),
                edit_fn=lambda: cpc_run_file_visibility_menu(
                    file_data=file_data,
                    is_multi_file=is_multi,
                    print_file_list=print_file_list,
                    rebuild_legend=_rebuild_legend,
                    fig=ref.fig,
                    ax=ref.ax,
                    ax2=ref.ax2,
                    push_state=noop_snapshot,
                    safe_input=safe_input,
                    colorize_menu=_colorize_menu,
                    colorize_prompt=colorize_prompt,
                ),
            )
            continue

        print(f"Unknown command: {cmd!r}")


__all__ = ["run_cpc_batch_menu"]

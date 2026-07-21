"""XY-specific helpers for batch session editing."""

from __future__ import annotations

import copy
import os
from typing import Any, Callable, List

from ..common.spines import (
    apply_flat_tick_params,
    build_wasd_state,
    legacy_tick_state_to_flat,
    run_spine_tick_menu,
    sync_legacy_tick_keys,
    sync_tick_state_from_wasd,
)
from ...ui import capture_axes_tick_locators, restore_axes_tick_locators, finalize_spine_colors
from ..xy.spines import apply_xy_spine_color
from ..common.terminal import colorize_inline_commands, colorize_prompt, safe_input
from ..xy.interactive import normalize_xy_menu_kwargs
from ..xy.session import dump_session
from .batch_figure_io import save_standard_panel_figure
from .load import XyPanel


def tick_state_for(panel: XyPanel) -> dict:
    fig = panel.fig
    wasd = getattr(fig, "_bp_wasd_state", None)
    if isinstance(wasd, dict):
        out: dict = {}
        for side_key, prefix in [("top", "t"), ("bottom", "b"), ("left", "l"), ("right", "r")]:
            s = wasd.get(side_key, {})
            out[f"{prefix}_ticks"] = bool(s.get("ticks", side_key in ("bottom", "left")))
            out[f"{prefix}_labels"] = bool(s.get("labels", side_key in ("bottom", "left")))
            out[f"m{prefix}x" if prefix in "tb" else f"m{prefix}y"] = bool(s.get("minor", False))
        out["bx"] = out.get("b_ticks", True)
        out["tx"] = out.get("t_ticks", False)
        out["ly"] = out.get("l_ticks", True)
        out["ry"] = out.get("r_ticks", False)
        return out
    saved = getattr(panel.ax, "_saved_tick_state", None)
    if isinstance(saved, dict):
        if any(k in saved for k in ("b_ticks", "t_ticks", "l_ticks", "r_ticks")):
            return dict(saved)
        return legacy_tick_state_to_flat(saved)
    return legacy_tick_state_to_flat({})


def dump_xy_panel(panel: XyPanel, path: str) -> None:
    """Save one XY panel session (keyword args — matches ``dump_session`` API)."""
    kw = normalize_xy_menu_kwargs(panel.menu_kwargs)
    cif_globals = kw.get("cif_globals") or {}
    dump_session(
        path,
        fig=panel.fig,
        ax=panel.ax,
        x_data_list=kw.get("x_data_list") or [],
        y_data_list=kw.get("y_data_list") or [],
        orig_y=kw.get("orig_y") or [],
        x_full_list=kw.get("x_full_list"),
        raw_y_full_list=kw.get("raw_y_full_list"),
        offsets_list=kw.get("offsets_list") or [],
        labels=kw.get("labels") or [],
        delta=float(kw.get("delta") or 0.0),
        args=kw.get("args"),
        tick_state=tick_state_for(panel),
        cif_tick_series=cif_globals.get("cif_tick_series"),
        cif_hkl_map=cif_globals.get("cif_hkl_map"),
        cif_hkl_label_map=cif_globals.get("cif_hkl_label_map"),
        show_cif_hkl=cif_globals.get("show_cif_hkl"),
        show_cif_titles=cif_globals.get("show_cif_titles"),
        skip_confirm=True,
    )
    panel.fig._last_session_save_path = os.path.abspath(path)  # type: ignore[attr-defined]


def export_xy_panel_figure(panel: XyPanel, path: str) -> None:
    """Export one XY panel figure (strip stack numbering from labels during save)."""
    kw = normalize_xy_menu_kwargs(panel.menu_kwargs)
    labels = kw.get("labels") or []
    label_objs = kw.get("label_text_objects") or []
    for i, txt in enumerate(label_objs):
        if i < len(labels):
            txt.set_text(labels[i])
    try:
        save_standard_panel_figure(panel.fig, panel.ax, path)
    finally:
        for i, txt in enumerate(label_objs):
            if i < len(labels):
                txt.set_text(f"{i + 1}: {labels[i]}")
        try:
            panel.fig.canvas.draw_idle()
        except Exception:
            pass


def sync_ref_wasd_to_panels(ref: XyPanel, panels: List[XyPanel]) -> None:
    """Copy spine/tick style from the reference panel to all others."""
    wasd = getattr(ref.fig, "_bp_wasd_state", None)
    if not isinstance(wasd, dict):
        return
    ref_ax = ref.ax
    ref_fig = ref.fig
    tick_lengths = getattr(ref_fig, "_tick_lengths", None)
    tick_direction = getattr(ref_fig, "_tick_direction", None)
    tick_spacing = capture_axes_tick_locators(ref_ax, ("x", "y"))
    for panel in panels:
        if panel is ref:
            continue
        panel.fig._bp_wasd_state = copy.deepcopy(wasd)  # type: ignore[attr-defined]
        tick_state = tick_state_for(panel)
        sync_tick_state_from_wasd(
            tick_state,
            panel.fig._bp_wasd_state,  # type: ignore[attr-defined]
        )
        sync_legacy_tick_keys(tick_state)
        apply_flat_tick_params(panel.ax, tick_state)
        try:
            panel.ax._saved_tick_state = dict(tick_state)  # type: ignore[attr-defined]
        except Exception:
            pass
        ax = panel.ax
        fig = panel.fig
        if tick_lengths:
            fig._tick_lengths = dict(tick_lengths)  # type: ignore[attr-defined]
            if tick_lengths.get("major") is not None:
                ax.tick_params(axis="both", which="major", length=float(tick_lengths["major"]))
            if tick_lengths.get("minor") is not None:
                ax.tick_params(axis="both", which="minor", length=float(tick_lengths["minor"]))
        if tick_direction:
            fig._tick_direction = tick_direction  # type: ignore[attr-defined]
            ax.tick_params(axis="both", which="both", direction=tick_direction)
        tick_state = tick_state_for(panel)
        for name in ("bottom", "top", "left", "right"):
            ref_sp = ref_ax.spines.get(name)
            if ref_sp is None:
                continue
            try:
                color = ref_sp.get_edgecolor()
                sp = ax.spines.get(name)
                if sp is not None:
                    sp.set_visible(ref_sp.get_visible())
                    sp.set_linewidth(ref_sp.get_linewidth())
                apply_xy_spine_color(fig, ax, tick_state, name, color)
            except Exception:
                pass
        for axis_name, ref_axis in (("x", ref_ax.xaxis), ("y", ref_ax.yaxis)):
            axis = ax.xaxis if axis_name == "x" else ax.yaxis
            for which in ("major", "minor"):
                try:
                    ref_kw = ref_axis._major_tick_kw if which == "major" else ref_axis._minor_tick_kw
                    width = ref_kw.get("width")
                    if width is not None:
                        ax.tick_params(axis=axis_name, which=which, width=width)
                except Exception:
                    pass
        restore_axes_tick_locators(ax, tick_spacing, ("x", "y"))
        try:
            finalize_spine_colors(fig, ax, tick_state=tick_state)
        except Exception:
            pass


def run_xy_batch_spine_menu(
    ref: XyPanel,
    panels: List[XyPanel],
    *,
    push_undo: Callable[[], None],
    draw_all: Callable[[], None],
) -> None:
    """Full spine/tick submenu on panel [1], then sync WASD to all panels."""
    ax = ref.ax
    fig = ref.fig
    tick_state = tick_state_for(ref)
    wasd = getattr(fig, "_bp_wasd_state", None)
    if not isinstance(wasd, dict):
        def _spine_visible(side: str) -> bool:
            sp = ax.spines.get(side)
            try:
                return bool(sp.get_visible()) if sp is not None else False
            except Exception:
                return False

        wasd = build_wasd_state(
            get_spine_visible=_spine_visible,
            tick_state=tick_state,
            title_visible={
                "top": bool(getattr(ax, "_top_xlabel_on", False)),
                "bottom": bool(ax.xaxis.label.get_visible()) if ax.xaxis.label is not None else bool(ax.get_xlabel()),
                "left": bool(ax.yaxis.label.get_visible()) if ax.yaxis.label is not None else bool(ax.get_ylabel()),
                "right": bool(getattr(ax, "_right_ylabel_on", False)),
            },
            tick_defaults={"top": False, "bottom": True, "left": True, "right": False},
            label_defaults={"top": False, "bottom": True, "left": True, "right": False},
        )
        fig._bp_wasd_state = wasd  # type: ignore[attr-defined]

    def _sync_ref_tick_state() -> None:
        sync_tick_state_from_wasd(tick_state, wasd)
        sync_legacy_tick_keys(tick_state)

    def _apply_ref_wasd(changed_sides=None) -> None:
        _sync_ref_tick_state()
        apply_flat_tick_params(ax, tick_state)
        try:
            ax._saved_tick_state = dict(tick_state)
        except Exception:
            pass
        try:
            finalize_spine_colors(fig, ax, tick_state=tick_state)
        except Exception:
            pass

    def _draw_ref_spine_menu() -> None:
        try:
            finalize_spine_colors(fig, ax, tick_state=tick_state)
        except Exception:
            pass
        try:
            fig.canvas.draw_idle()
        except Exception:
            pass
        sync_ref_wasd_to_panels(ref, panels)
        draw_all()

    push_undo()
    run_spine_tick_menu(
        fig=fig,
        wasd=wasd,
        safe_input=safe_input,
        colorize_prompt=colorize_prompt,
        colorize_inline_commands=colorize_inline_commands,
        push_state=lambda _label: push_undo(),
        sync_tick_state=_sync_ref_tick_state,
        apply_wasd=_apply_ref_wasd,
        draw=_draw_ref_spine_menu,
        mode_label="batch XY",
        back_label="batch menu",
        axis_map={"x": ax.xaxis, "y": ax.yaxis},
        direction_axes=[ax],
        length_axes=[ax],
        on_quit=lambda: setattr(ax, "_saved_tick_state", dict(tick_state)),
    )
    sync_ref_wasd_to_panels(ref, panels)
    draw_all()


def sync_axis_limits_from_ref(
    ref: XyPanel,
    panels: List[XyPanel],
    *,
    axis: str,
    draw_all: Callable[[], None],
) -> None:
    """Apply reference panel x or y limits to every panel."""
    if axis == "x":
        lim = ref.ax.get_xlim()
        for p in panels:
            p.ax.set_xlim(lim)
    elif axis == "y":
        lim = ref.ax.get_ylim()
        for p in panels:
            p.ax.set_ylim(lim)
    draw_all()


__all__ = [
    "dump_xy_panel",
    "run_xy_batch_spine_menu",
    "sync_axis_limits_from_ref",
    "sync_ref_wasd_to_panels",
    "tick_state_for",
]

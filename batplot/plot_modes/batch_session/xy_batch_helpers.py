"""XY-specific helpers for batch session editing."""

from __future__ import annotations

import copy
import os
from typing import Any, Callable, List

from ..common.spines import (
    apply_changed_side_title_positions,
    apply_flat_tick_params,
    build_wasd_state,
    legacy_tick_state_to_flat,
    run_spine_tick_menu,
    set_primary_axis_title,
    sync_legacy_tick_keys,
    sync_tick_state_from_wasd,
    wasd_to_tick_state,
)
from ...ui import (
    capture_axes_tick_locators,
    finalize_spine_colors,
    position_bottom_xlabel,
    position_left_ylabel,
    position_right_ylabel,
    position_top_xlabel,
    restore_axes_tick_locators,
)
from ..common.terminal import colorize_inline_commands, colorize_prompt, safe_input
from ..common.title_offsets import (
    capture_title_offsets,
    restore_title_offsets,
    run_title_offset_nudge_menu,
)
from ..xy.interactive import normalize_xy_menu_kwargs
from ..xy.session import dump_session
from ..xy.spines import set_xy_spine_visible, sync_xy_twin_wasd
from .batch_figure_io import save_standard_panel_figure
from .load import XyPanel


def _apply_xy_batch_wasd_chrome(
    fig: Any,
    ax: Any,
    wasd: dict,
    tick_state: dict,
    *,
    changed_sides: set[str] | None = None,
) -> None:
    """Apply WASD spine/title/twin chrome (interactive ``t`` parity for batch).

    Spine **colors** stay panel-local (batch ``c``); this only toggles visibility,
    tick params, twin chrome, and axis-title on/off.
    """
    if changed_sides is None:
        changed_sides = {"bottom", "top", "left", "right"}
    for side in ("top", "bottom", "left", "right"):
        side_cfg = wasd.get(side) if isinstance(wasd.get(side), dict) else {}
        set_xy_spine_visible(fig, ax, side, bool(side_cfg.get("spine", False)))
    apply_flat_tick_params(ax, tick_state)
    sync_xy_twin_wasd(ax, fig, wasd)
    set_primary_axis_title(
        ax,
        "x",
        on=bool((wasd.get("bottom") or {}).get("title", True)),
        stored_attr="_stored_xlabel",
    )
    ax._top_xlabel_on = bool((wasd.get("top") or {}).get("title", False))
    top_art = getattr(ax, "_top_xlabel_artist", None)
    if not ax._top_xlabel_on and top_art is not None:
        try:
            top_art.set_visible(False)
        except Exception:
            pass
    set_primary_axis_title(
        ax,
        "y",
        on=bool((wasd.get("left") or {}).get("title", True)),
        stored_attr="_stored_ylabel",
    )
    ax._right_ylabel_on = bool((wasd.get("right") or {}).get("title", False))
    right_art = getattr(ax, "_right_ylabel_artist", None)
    if not ax._right_ylabel_on and right_art is not None:
        try:
            right_art.set_visible(False)
        except Exception:
            pass
    apply_changed_side_title_positions(
        changed_sides,
        bottom=lambda: position_bottom_xlabel(ax, fig, tick_state),
        top=lambda: position_top_xlabel(ax, fig, tick_state),
        left=lambda: position_left_ylabel(ax, fig, tick_state),
        right=lambda: position_right_ylabel(ax, fig, tick_state),
    )
    try:
        finalize_spine_colors(fig, ax, tick_state=tick_state)
    except Exception:
        pass


def tick_state_for(panel: XyPanel) -> dict:
    fig = panel.fig
    wasd = getattr(fig, "_bp_wasd_state", None)
    if isinstance(wasd, dict):
        # One rule with dump/session: legacy bx = ticks AND labels.
        return wasd_to_tick_state(
            wasd,
            tick_defaults={"top": False, "bottom": True, "left": True, "right": False},
            label_defaults={"top": False, "bottom": True, "left": True, "right": False},
        )
    saved = getattr(panel.ax, "_saved_tick_state", None)
    if isinstance(saved, dict):
        if any(k in saved for k in ("b_ticks", "t_ticks", "l_ticks", "r_ticks")):
            out = dict(saved)
            sync_legacy_tick_keys(out)
            return out
        return legacy_tick_state_to_flat(saved)
    return legacy_tick_state_to_flat({})


def dump_xy_panel(panel: XyPanel, path: str) -> None:
    """Save one XY panel session (keyword args — matches ``dump_session`` API)."""
    kw = normalize_xy_menu_kwargs(panel.menu_kwargs)
    cif_globals = kw.get("cif_globals") or {}
    show_hkl = cif_globals.get("show_cif_hkl")
    if show_hkl is None and hasattr(panel.fig, "_bp_show_cif_hkl"):
        show_hkl = bool(panel.fig._bp_show_cif_hkl)
    ok = dump_session(
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
        show_cif_hkl=show_hkl,
        show_cif_titles=cif_globals.get("show_cif_titles"),
        skip_confirm=True,
    )
    if not ok:
        raise RuntimeError(f"Failed to save XY session to {path}")


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
    """Copy spine/tick WASD chrome from the reference panel to all others.

    Spine **colors** stay panel-local (batch ``c``). Twin ``--ry`` / ``--txaxis``
    chrome is updated via ``sync_xy_twin_wasd`` (interactive parity).
    """
    wasd = getattr(ref.fig, "_bp_wasd_state", None)
    if not isinstance(wasd, dict):
        return
    ref_ax = ref.ax
    ref_fig = ref.fig
    tick_lengths = getattr(ref_fig, "_tick_lengths", None)
    tick_direction = getattr(ref_fig, "_tick_direction", None)
    tick_spacing = capture_axes_tick_locators(ref_ax, ("x", "y"))
    ref_offsets = capture_title_offsets(ref_ax)
    try:
        ref_xpad = float(ref_ax.xaxis.labelpad)
    except Exception:
        ref_xpad = None
    try:
        ref_ypad = float(ref_ax.yaxis.labelpad)
    except Exception:
        ref_ypad = None
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
        try:
            panel.ax._saved_tick_state = dict(tick_state)  # type: ignore[attr-defined]
        except Exception:
            pass
        ax = panel.ax
        fig = panel.fig
        ax2 = getattr(fig, "_xy_ax2", None)
        length_targets = [ax] + ([ax2] if ax2 is not None else [])
        if tick_lengths:
            fig._tick_lengths = dict(tick_lengths)  # type: ignore[attr-defined]
            for target in length_targets:
                if tick_lengths.get("major") is not None:
                    target.tick_params(
                        axis="both", which="major", length=float(tick_lengths["major"])
                    )
                if tick_lengths.get("minor") is not None:
                    target.tick_params(
                        axis="both", which="minor", length=float(tick_lengths["minor"])
                    )
        if tick_direction:
            fig._tick_direction = tick_direction  # type: ignore[attr-defined]
            for target in length_targets:
                target.tick_params(axis="both", which="both", direction=tick_direction)
        restore_axes_tick_locators(ax, tick_spacing, ("x", "y"))
        restore_title_offsets(ax, ref_offsets)
        try:
            if ref_xpad is not None:
                ax.xaxis.labelpad = ref_xpad
            if ref_ypad is not None:
                ax.yaxis.labelpad = ref_ypad
        except Exception:
            pass
        # Full WASD body (spine visibility / titles / twin) — not artist-copy.
        _apply_xy_batch_wasd_chrome(fig, ax, wasd, tick_state)


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
        try:
            ax._saved_tick_state = dict(tick_state)
        except Exception:
            pass
        sides = changed_sides
        if sides is not None and not isinstance(sides, set):
            try:
                sides = set(sides)
            except Exception:
                sides = None
        _apply_xy_batch_wasd_chrome(fig, ax, wasd, tick_state, changed_sides=sides)

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

    def _title_offsets() -> None:
        run_title_offset_nudge_menu(
            fig=fig,
            ax=ax,
            push_state=push_undo,
            safe_input=safe_input,
            colorize_prompt=colorize_prompt,
            draw=_draw_ref_spine_menu,
        )

    ax2 = getattr(fig, "_xy_ax2", None)
    twin_axes = [ax, ax2] if ax2 is not None else [ax]

    # Push only on real spine edits (via push_state); open→q must not junk undo.
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
        direction_axes=twin_axes,
        length_axes=twin_axes,
        title_offset_handler=_title_offsets,
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


_XY_LINE_CHROME_KEYS = (
    "linewidth",
    "linestyle",
    "dash_pattern",
    "marker",
    "markersize",
    "alpha",
)


def merge_xy_line_chrome_cfg(peer_cfg: dict, ref_cfg: dict) -> dict:
    """Peer-merge for batch ``l``: line chrome / grid / frame widths (not colors)."""
    from .batch_scoped_sync import deep_merge_keys, merge_spines_props

    merged = deep_merge_keys(
        peer_cfg,
        ref_cfg,
        top_keys=frozenset({"grid"}),
        force_kind="xy_style",
        drop_geometry=True,
    )
    # Spines: widths/visible only (colors stay peer-local; ``c``/``t`` own those).
    merged["spines"] = merge_spines_props(
        peer_cfg.get("spines"), ref_cfg.get("spines"), mode="linewidth"
    )
    # Tick widths only (spacing/WASD stay peer-local under ``l``).
    peer_ticks = peer_cfg.get("ticks") if isinstance(peer_cfg.get("ticks"), dict) else {}
    ref_ticks = ref_cfg.get("ticks") if isinstance(ref_cfg.get("ticks"), dict) else {}
    out_ticks = copy.deepcopy(peer_ticks) if peer_ticks else {}
    for key in (
        "x_major_width",
        "x_minor_width",
        "y_major_width",
        "y_minor_width",
    ):
        if key in ref_ticks:
            out_ticks[key] = ref_ticks[key]
    merged["ticks"] = out_ticks

    peer_lines = peer_cfg.get("lines") if isinstance(peer_cfg.get("lines"), list) else []
    ref_lines = ref_cfg.get("lines") if isinstance(ref_cfg.get("lines"), list) else []
    out_lines = copy.deepcopy(peer_lines)
    for i, ref_entry in enumerate(ref_lines):
        if i >= len(out_lines) or not isinstance(ref_entry, dict):
            break
        pe = dict(out_lines[i] or {})
        for key in _XY_LINE_CHROME_KEYS:
            if key in ref_entry:
                pe[key] = copy.deepcopy(ref_entry[key])
        out_lines[i] = pe
    merged["lines"] = out_lines
    return merged


def apply_xy_line_chrome_only(
    panel: XyPanel,
    ref_cfg: dict,
    *,
    capture_panel: Callable[[XyPanel], dict],
    restore_panel: Callable[[XyPanel, dict], None],
    silent: bool = True,
) -> bool:
    """Batch XY ``l`` scoped sync via peer-merge + full restore of merged cfg."""
    try:
        peer = capture_panel(panel)
        merged = merge_xy_line_chrome_cfg(peer, ref_cfg if isinstance(ref_cfg, dict) else {})
        restore_panel(panel, merged)
        return True
    except Exception as exc:
        if not silent:
            print(f"XY line sync failed for {getattr(panel, 'path', '?')}: {exc}")
        return False


__all__ = [
    "apply_xy_line_chrome_only",
    "dump_xy_panel",
    "merge_xy_line_chrome_cfg",
    "run_xy_batch_spine_menu",
    "sync_axis_limits_from_ref",
    "sync_ref_wasd_to_panels",
    "tick_state_for",
]

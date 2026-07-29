"""Operando-specific helpers for batch session editing (Tier A/B layout sync)."""

from __future__ import annotations

import json
from typing import Callable, List, Sequence, TypeVar

from ..common.spines import (
    apply_frame_and_tick_widths,
    apply_wasd_spines,
    apply_wasd_tick_params,
    build_wasd_state,
    parse_frame_tick_widths,
    run_spine_tick_menu,
)
from ..common.terminal import (
    colorize_inline_commands,
    colorize_prompt,
    colorize_single_key_inline_commands,
    safe_input,
)
from ..operando.layout import (
    _apply_group_layout_inches,
    _ensure_fixed_params,
    _redraw_operando_cif_if_present,
    _safe_set_clim,
    _update_custom_colorbar,
)
from ...ui import finalize_spine_colors_for_axes
from .batch_menu_helpers import prompt_axis_limits
from .common import SyncUndoStacks
from .load import OperandoPanel

PanelT = TypeVar("PanelT")


def _cfg_signature(cfg: dict) -> str:
    try:
        return json.dumps(cfg, sort_keys=True, default=str)
    except Exception:
        return repr(cfg)


def panel_layout_inches(panel: OperandoPanel) -> tuple[float, float, float, float, float, float]:
    """Return ``(cb_w, cb_gap, ec_gap, ec_w, op_w, op_h)`` inches for a panel."""
    return _ensure_fixed_params(panel.fig, panel.ax, panel.cbar.ax, panel.ec_ax)


def apply_layout_inches_to_panel(
    panel: OperandoPanel,
    *,
    op_w: float | None = None,
    op_h: float | None = None,
    ec_w: float | None = None,
) -> None:
    """Apply selected inch layout values to one panel, keeping other dims."""
    cb_w, cb_gap, ec_gap, cur_ec_w, cur_op_w, cur_op_h = panel_layout_inches(panel)
    ax_w = float(op_w) if op_w is not None else float(cur_op_w)
    ax_h = float(op_h) if op_h is not None else float(cur_op_h)
    ec_width = float(ec_w) if ec_w is not None else float(cur_ec_w)
    _apply_group_layout_inches(
        panel.fig,
        panel.ax,
        panel.cbar.ax,
        panel.ec_ax,
        ax_w,
        ax_h,
        cb_w,
        cb_gap,
        ec_gap,
        ec_width,
    )


def apply_layout_inches_to_all(
    panels: Sequence[OperandoPanel],
    *,
    op_w: float | None = None,
    op_h: float | None = None,
    ec_w: float | None = None,
) -> None:
    for panel in panels:
        apply_layout_inches_to_panel(panel, op_w=op_w, op_h=op_h, ec_w=ec_w)


def _label_only_axes_geometry(axes_geom: dict | None) -> dict | None:
    """Keep axis titles from ``axes_geometry`` without limits/clim."""
    if not isinstance(axes_geom, dict):
        return None
    labels_only: dict = {}
    for section, data in axes_geom.items():
        if not isinstance(data, dict):
            continue
        part = {k: v for k, v in data.items() if k in ("xlabel", "ylabel")}
        if part:
            labels_only[section] = part
    return labels_only or None


def sync_style_from_ref(
    ref: PanelT,
    panels: Sequence[PanelT],
    *,
    capture_panel: Callable[[PanelT], dict],
    apply_cfg: Callable[..., bool | None],
    include_geometry: bool = False,
) -> None:
    """Copy style (+ optional geometry) from the reference panel onto every other panel.

    Strip data-local ``ec.ions_abs`` so each panel recomputes ions from its own
    ``_ec_time_h`` / ``_ec_current_mA`` + shared ``ion_params``.

    When ``include_geometry=False`` (default), axis limits/clim/layout inches are
    not copied; axis titles in ``axes_geometry`` still sync (rename/or/er menus).
    """
    import copy

    cfg = copy.deepcopy(capture_panel(ref))
    if not include_geometry:
        cfg.pop("geometry", None)
        axes_geom = cfg.pop("axes_geometry", None)
        kind = str(cfg.get("kind", ""))
        if kind.endswith("_style_geom"):
            cfg["kind"] = kind.replace("_style_geom", "_style")
        labels_only = _label_only_axes_geometry(axes_geom)
        if labels_only:
            cfg["axes_geometry"] = labels_only
            if str(cfg.get("kind", "")).startswith("operando"):
                cfg["kind"] = "operando_ec_style_geom"
    ec_cfg = cfg.get("ec")
    if isinstance(ec_cfg, dict):
        ec_cfg.pop("ions_abs", None)
    for panel in panels:
        if panel is ref:
            continue
        try:
            apply_cfg(panel, cfg)
        except Exception as exc:
            print(f"Sync failed for {getattr(panel, 'path', '?')}: {exc}")


def edit_ref_then_sync(
    ref: PanelT,
    panels: List[PanelT],
    *,
    undo: SyncUndoStacks,
    capture_panel: Callable[[PanelT], dict],
    apply_cfg: Callable[..., bool | None],
    draw_all: Callable[[], None],
    edit_fn: Callable[..., object],
    include_geometry: bool = False,
) -> None:
    """Run a ref-only editor, then push one undo point and sync style to all panels.

    Nested menus should pass ``snapshot=noop_snapshot`` so undo stays one level
    per submenu visit (histo-style batch sync).

    By default ``include_geometry=False`` so style edits on the reference panel
    do not overwrite axis limits/clim on peers (use explicit ``x``/``y``/``ox`` keys
    for shared limits).
    """
    pre = [capture_panel(p) for p in panels]
    edit_fn()
    post_ref = capture_panel(ref)
    if _cfg_signature(post_ref) == _cfg_signature(pre[0]):
        draw_all()
        return
    undo.push_all(pre)
    sync_style_from_ref(
        ref,
        panels,
        capture_panel=capture_panel,
        apply_cfg=apply_cfg,
        include_geometry=include_geometry,
    )
    draw_all()


def noop_snapshot(*_args, **_kwargs) -> None:
    """Disable per-keystroke undo inside nested operando menus during batch sync."""
    return None


def apply_frame_tick_widths_all(
    panels: Sequence[OperandoPanel],
    raw: str,
) -> tuple[float, float, float]:
    """Parse and apply frame/tick widths to every panel's op/ec/colorbar axes."""
    frame_w, tick_w, tick_minor = parse_frame_tick_widths(
        raw,
        single_minor_scale=1.0,
        paired_minor_scale=1.0,
    )
    frame_w = max(0.1, frame_w)
    tick_w = max(0.1, tick_w)
    tick_minor = max(0.1, tick_minor)
    for panel in panels:
        axes = [panel.ax]
        if panel.ec_ax is not None:
            axes.append(panel.ec_ax)
        if panel.cbar is not None:
            axes.append(panel.cbar.ax)
        apply_frame_and_tick_widths(
            axes,
            frame_width=frame_w,
            major_width=tick_w,
            minor_width=tick_minor,
        )
        try:
            entries = [(panel.ax, getattr(panel.ax, "_saved_tick_state", None))]
            if panel.ec_ax is not None:
                entries.append((panel.ec_ax, getattr(panel.ec_ax, "_saved_tick_state", None)))
            finalize_spine_colors_for_axes(panel.fig, entries)
        except Exception:
            pass
    return frame_w, tick_w, tick_minor


def reverse_y_all(panels: Sequence[OperandoPanel]) -> None:
    """Flip operando and EC y-limits on every panel (same as normal ``r``)."""
    for panel in panels:
        try:
            y0, y1 = panel.ax.get_ylim()
            panel.ax.set_ylim(y1, y0)
        except Exception as exc:
            print(f"Operando reverse failed: {exc}")
        ec_ax = panel.ec_ax
        if ec_ax is None:
            continue
        try:
            ey0, ey1 = ec_ax.get_ylim()
            ec_ax.set_ylim(ey1, ey0)
            saved = getattr(ec_ax, "_saved_time_ylim", None)
            if isinstance(saved, (tuple, list)) and len(saved) == 2:
                lo, hi = saved
                ec_ax._saved_time_ylim = (hi, lo)
        except Exception as exc:
            print(f"EC reverse failed: {exc}")


def set_operando_xlim_all(panels: Sequence[OperandoPanel], lo: float, hi: float) -> None:
    for panel in panels:
        try:
            panel.ax.set_xlim(lo, hi)
            _redraw_operando_cif_if_present(panel.fig, panel.ax)
        except Exception as exc:
            print(f"X range failed: {exc}")


def set_operando_ylim_all(panels: Sequence[OperandoPanel], lo: float, hi: float) -> None:
    for panel in panels:
        try:
            panel.ax.set_ylim(lo, hi)
        except Exception as exc:
            print(f"Y range failed: {exc}")


def set_clim_all(panels: Sequence[OperandoPanel], vmin: float, vmax: float) -> None:
    for panel in panels:
        try:
            _safe_set_clim(panel.im, vmin, vmax)
            _update_custom_colorbar(panel.cbar.ax, panel.im)
        except Exception as exc:
            print(f"Intensity range failed: {exc}")


def set_ec_ylim_all(panels: Sequence[OperandoPanel], lo: float, hi: float) -> None:
    for panel in panels:
        ec_ax = panel.ec_ax
        if ec_ax is None:
            continue
        try:
            ec_ax.set_ylim(lo, hi)
            ec_ax._saved_time_ylim = (lo, hi)
        except Exception as exc:
            print(f"EC time range failed: {exc}")


def set_ec_xlim_all(panels: Sequence[OperandoPanel], lo: float, hi: float) -> None:
    for panel in panels:
        ec_ax = panel.ec_ax
        if ec_ax is None:
            continue
        try:
            ec_ax.set_xlim(lo, hi)
            ec_ax._prev_ec_xlim = (lo, hi)
            ec_ax._ions_xlim_expanded = False
        except Exception as exc:
            print(f"EC x range failed: {exc}")


def run_operando_batch_spine_menu(
    ref: OperandoPanel,
    panels: List[OperandoPanel],
    *,
    undo: SyncUndoStacks,
    capture_panel: Callable[[OperandoPanel], dict],
    apply_cfg: Callable[[OperandoPanel, dict], bool],
    draw_all: Callable[[], None],
) -> None:
    """WASD spine/tick editor on the reference pane, then sync style to all panels."""
    while True:
        if ref.ec_ax is not None:
            print(
                colorize_single_key_inline_commands(
                    "Choose which plot to edit: o=operando (contour), e=EC side panel, q=return"
                )
            )
            pane = safe_input(
                colorize_prompt("Pane (o=operando, e=ec, q=back): "),
                cancel_on_interrupt=True,
            ).strip().lower()
        else:
            pane = safe_input(
                colorize_prompt("Pane (o=operando contour, q=back): "),
                cancel_on_interrupt=True,
            ).strip().lower()
        if not pane or pane == "q":
            break
        if pane == "e" and ref.ec_ax is None:
            print("EC panel not available.")
            continue
        if pane not in ("o", "e"):
            print("Unknown pane.")
            continue
        target = ref.ax if pane == "o" else ref.ec_ax
        assert target is not None

        def _spine_visible(side: str, _ax=target) -> bool:
            sp = _ax.spines.get(side)
            try:
                return bool(sp.get_visible()) if sp is not None else False
            except Exception:
                return False

        ts = getattr(target, "_saved_tick_state", None)
        if not isinstance(ts, dict):
            ts = {
                "bx": True,
                "tx": False,
                "ly": True,
                "ry": False,
                "mbx": False,
                "mtx": False,
                "mly": False,
                "mry": False,
                "b_ticks": True,
                "b_labels": True,
                "t_ticks": False,
                "t_labels": False,
                "l_ticks": True,
                "l_labels": True,
                "r_ticks": False,
                "r_labels": False,
            }

        wasd = build_wasd_state(
            get_spine_visible=_spine_visible,
            tick_state=ts,
            title_visible={
                "top": bool(getattr(target, "_top_xlabel_on", False)),
                "bottom": bool(target.get_xlabel()),
                "left": bool(target.get_ylabel()),
                "right": bool(getattr(target, "_right_ylabel_on", False))
                if target is ref.ax
                else bool(target.get_ylabel()),
            },
        )

        is_ec = target is ref.ec_ax
        has_ec = ref.ec_ax is not None

        def _apply_wasd(changed_sides=None, _ax=target, _wasd=wasd) -> None:
            if is_ec:
                apply_wasd_spines(_ax, _wasd, sides=("top", "bottom", "right"))
                apply_wasd_tick_params(_ax, _wasd, y_sides=("right",), y_mode="right")
            elif has_ec:
                apply_wasd_spines(_ax, _wasd, sides=("top", "bottom", "left"))
                apply_wasd_tick_params(_ax, _wasd, y_sides=("left",), y_mode="left")
            else:
                apply_wasd_spines(_ax, _wasd)
                apply_wasd_tick_params(_ax, _wasd)
            flat = {
                "t_ticks": bool(_wasd["top"]["ticks"]),
                "t_labels": bool(_wasd["top"]["labels"]),
                "tx": bool(_wasd["top"]["ticks"] and _wasd["top"]["labels"]),
                "b_ticks": bool(_wasd["bottom"]["ticks"]),
                "b_labels": bool(_wasd["bottom"]["labels"]),
                "bx": bool(_wasd["bottom"]["ticks"] and _wasd["bottom"]["labels"]),
                "l_ticks": bool(_wasd["left"]["ticks"]),
                "l_labels": bool(_wasd["left"]["labels"]),
                "ly": bool(_wasd["left"]["ticks"] and _wasd["left"]["labels"]),
                "r_ticks": bool(_wasd["right"]["ticks"]),
                "r_labels": bool(_wasd["right"]["labels"]),
                "ry": bool(_wasd["right"]["ticks"] and _wasd["right"]["labels"]),
                "mtx": bool(_wasd["top"]["minor"]),
                "mbx": bool(_wasd["bottom"]["minor"]),
                "mly": bool(_wasd["left"]["minor"]),
                "mry": bool(_wasd["right"]["minor"]),
            }
            try:
                _ax._saved_tick_state = dict(flat)
            except Exception:
                pass
            try:
                finalize_spine_colors_for_axes(
                    ref.fig, [(_ax, getattr(_ax, "_saved_tick_state", None))]
                )
            except Exception:
                pass

        def _draw() -> None:
            try:
                ref.fig.canvas.draw_idle()
            except Exception:
                pass
            sync_style_from_ref(
                ref,
                panels,
                capture_panel=capture_panel,
                apply_cfg=apply_cfg,
                include_geometry=False,
            )
            draw_all()

        def _edit() -> None:
            run_spine_tick_menu(
                fig=ref.fig,
                wasd=wasd,
                safe_input=safe_input,
                colorize_prompt=colorize_prompt,
                colorize_inline_commands=colorize_inline_commands,
                push_state=lambda _label: None,
                sync_tick_state=lambda: None,
                apply_wasd=_apply_wasd,
                draw=_draw,
                mode_label="batch operando",
                back_label="batch menu",
                axis_map={"x": target.xaxis, "y": target.yaxis},
                direction_axes=[target],
                length_axes=[target],
            )

        edit_ref_then_sync(
            ref,
            panels,
            undo=undo,
            capture_panel=capture_panel,
            apply_cfg=apply_cfg,
            draw_all=draw_all,
            edit_fn=_edit,
            include_geometry=False,
        )


__all__ = [
    "apply_frame_tick_widths_all",
    "apply_layout_inches_to_all",
    "apply_layout_inches_to_panel",
    "edit_ref_then_sync",
    "noop_snapshot",
    "panel_layout_inches",
    "prompt_axis_limits",
    "reverse_y_all",
    "run_operando_batch_spine_menu",
    "set_clim_all",
    "set_ec_xlim_all",
    "set_ec_ylim_all",
    "set_operando_xlim_all",
    "set_operando_ylim_all",
    "sync_style_from_ref",
]

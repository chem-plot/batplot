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
    wasd_to_tick_state,
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


_LABEL_KEYS = (
    "xlabel",
    "ylabel",
    "ylabel_left",
    "ylabel_right",
    "top_xlabel",
    "right_ylabel",
)


def _label_only_axes_geometry(axes_geom: dict | None) -> dict | None:
    """Keep axis titles from ``axes_geometry`` without limits/clim."""
    if not isinstance(axes_geom, dict):
        return None
    labels_only: dict = {}
    for section, data in axes_geom.items():
        if not isinstance(data, dict):
            continue
        part = {k: v for k, v in data.items() if k in _LABEL_KEYS}
        if part:
            labels_only[section] = part
    return labels_only or None


def _label_only_flat_geometry(geometry: dict | None) -> dict | None:
    """Keep EC/CPC flat ``geometry`` axis titles without limits/figsize."""
    if not isinstance(geometry, dict):
        return None
    part = {k: geometry[k] for k in _LABEL_KEYS if k in geometry and geometry[k] is not None}
    return part or None


def _fold_flat_labels_into_axis_labels(cfg: dict, labels_flat: dict | None) -> None:
    """Merge label-only flat geometry into ``cfg['axis_labels']`` (EC + CPC keys)."""
    if not labels_flat:
        return
    axis_labels = dict(cfg.get("axis_labels") or {})
    for key in _LABEL_KEYS:
        if key in labels_flat and labels_flat[key] is not None:
            axis_labels[key] = labels_flat[key]
    cfg["axis_labels"] = axis_labels


def _panel_ref_index(ref: PanelT, panels: Sequence[PanelT]) -> int:
    for i, panel in enumerate(panels):
        if panel is ref:
            return i
    return 0


def sync_style_from_ref(
    ref: PanelT,
    panels: Sequence[PanelT],
    *,
    capture_panel: Callable[[PanelT], dict],
    apply_cfg: Callable[..., bool | None],
    include_geometry: bool = False,
) -> int:
    """Copy style (+ optional geometry) from the reference panel onto every other panel.

    Strip data-local ``ec.ions_abs`` so each panel recomputes ions from its own
    ``_ec_time_h`` / ``_ec_current_mA`` + shared ``ion_params``.

    When ``include_geometry=False`` (default), axis limits/clim/layout inches are
    not copied; axis titles from ``axes_geometry`` **and** flat ``geometry``
    (EC/CPC ``xlabel``/``ylabel``/``ylabel_left``/``ylabel_right``) still sync
    so rename reaches every panel.

    Returns the number of peer panels sync was attempted on.
    """
    import copy

    cfg = copy.deepcopy(capture_panel(ref))
    if not include_geometry:
        flat_geom = cfg.pop("geometry", None)
        axes_geom = cfg.pop("axes_geometry", None)
        kind = str(cfg.get("kind", ""))
        # Never keep *_style_geom here — that would resize peer canvases / apply
        # inch layout. Labels sync via axis_labels / custom_labels instead.
        if kind.endswith("_style_geom"):
            cfg["kind"] = kind.replace("_style_geom", "_style")
        # View-geometry hitchhikers (oz / r) must not ride style-only sync.
        op_strip = cfg.get("operando")
        if isinstance(op_strip, dict):
            op_strip.pop("intensity_range", None)
            op_strip.pop("y_reversed", None)
        ec_strip = cfg.get("ec")
        if isinstance(ec_strip, dict):
            ec_strip.pop("y_reversed", None)
            # Limit bookkeeping owned by geometry / panel-local state.
            ec_strip.pop("saved_time_ylim", None)
            ec_strip.pop("prev_ec_xlim", None)
            ec_strip.pop("ions_xlim_expanded", None)
        # EC/CPC put titles in flat geometry; fold them into axis_labels so
        # style-only apply still renames peers (and p/i/s/b stay consistent).
        _fold_flat_labels_into_axis_labels(cfg, _label_only_flat_geometry(flat_geom))
        # Operando nested axes_geometry titles → custom_labels (style-only path).
        labels_nested = _label_only_axes_geometry(axes_geom)
        if labels_nested:
            op = cfg.setdefault("operando", {})
            if isinstance(op, dict):
                custom = dict(op.get("custom_labels") or {})
                op_ax = labels_nested.get("operando") or labels_nested.get("op") or {}
                if isinstance(op_ax, dict):
                    if op_ax.get("xlabel") is not None:
                        custom["x"] = op_ax["xlabel"]
                    if op_ax.get("ylabel") is not None:
                        custom["y"] = op_ax["ylabel"]
                ec_ax_lbl = labels_nested.get("ec") or {}
                if isinstance(ec_ax_lbl, dict):
                    ec_cfg = cfg.setdefault("ec", {})
                    if isinstance(ec_cfg, dict):
                        ec_custom = dict(ec_cfg.get("custom_labels") or {})
                        if ec_ax_lbl.get("xlabel") is not None:
                            ec_custom["x"] = ec_ax_lbl["xlabel"]
                        if ec_ax_lbl.get("ylabel") is not None:
                            # EC side panel uses y_time / y_ions; keep generic y too.
                            ec_custom["y_time"] = ec_ax_lbl["ylabel"]
                        if ec_custom:
                            ec_cfg["custom_labels"] = ec_custom
                if custom:
                    op["custom_labels"] = custom
        # Batch ``v`` → ``m`` owns these chrome offsets; keep them without
        # hitchhiking canvas/frame inches (apply_operando_visibility_only).
        if isinstance(flat_geom, dict):
            slim = {
                k: flat_geom[k]
                for k in ("cb_h_offset", "ec_h_offset")
                if k in flat_geom
            }
            if slim:
                cfg["geometry"] = slim
    ec_cfg = cfg.get("ec")
    if isinstance(ec_cfg, dict):
        ec_cfg.pop("ions_abs", None)
    n_peers = 0
    for panel in panels:
        if panel is ref:
            continue
        n_peers += 1
        try:
            ok = apply_cfg(panel, cfg)
            if ok is False:
                print(f"Sync skipped for {getattr(panel, 'path', '?')} (apply returned False).")
        except Exception as exc:
            print(f"Sync failed for {getattr(panel, 'path', '?')}: {exc}")
    return n_peers


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
    live_sync: bool = True,
) -> None:
    """Run a ref-only editor, then push one undo point and sync style to all panels.

    Nested menus should pass ``snapshot=noop_snapshot`` so undo stays one level
    per submenu visit (batch owns undo via :func:`make_batch_live_sync`).

    By default ``include_geometry=False`` so style edits on the reference panel
    do not overwrite axis limits/clim on peers (use explicit ``x``/``y``/``ox`` keys
    for shared limits).

    When ``live_sync=True`` (default), wrapping the reference canvas ``draw`` /
    ``draw_idle`` syncs peers after each nested-menu redraw (rename, line style,
    spines, …) so users do not see only the reference plot update. A final sync
    still runs when the submenu returns if anything changed without a draw.
    """
    _push_state, on_change, finalize = make_batch_live_sync(
        ref,
        panels,
        undo=undo,
        capture_panel=capture_panel,
        apply_cfg=apply_cfg,
        draw_all=draw_all,
        include_geometry=include_geometry,
    )
    canvas = None
    orig_draw = None
    orig_idle = None
    if live_sync:
        fig = getattr(ref, "fig", None)
        canvas = getattr(fig, "canvas", None) if fig is not None else None
        if canvas is not None:
            orig_draw = canvas.draw
            orig_idle = canvas.draw_idle

            def _draw(*args, **kwargs):
                out = orig_draw(*args, **kwargs)
                on_change()
                return out

            def _draw_idle(*args, **kwargs):
                out = orig_idle(*args, **kwargs)
                on_change()
                return out

            canvas.draw = _draw  # type: ignore[method-assign]
            canvas.draw_idle = _draw_idle  # type: ignore[method-assign]
    try:
        edit_fn()
    finally:
        if canvas is not None and orig_draw is not None and orig_idle is not None:
            canvas.draw = orig_draw  # type: ignore[method-assign]
            canvas.draw_idle = orig_idle  # type: ignore[method-assign]
        finalize()


def make_batch_live_sync(
    ref: PanelT,
    panels: List[PanelT],
    *,
    undo: SyncUndoStacks,
    capture_panel: Callable[[PanelT], dict],
    apply_cfg: Callable[..., bool | None],
    draw_all: Callable[[], None],
    include_geometry: bool = False,
) -> tuple[Callable[..., None], Callable[[], None], Callable[[], bool]]:
    """Hooks for live peer sync during a nested batch submenu (e.g. rename).

    Returns ``(push_state, on_change, finalize)``:
    - ``push_state``: no-op for nested undo (batch owns one undo level)
    - ``on_change``: call **after** a successful mutation to sync peers now
    - ``finalize``: call when the submenu returns; pushes undo once if needed
      and syncs if live sync never ran. Returns True if anything changed.
    """
    pre = [capture_panel(p) for p in panels]
    ref_idx = _panel_ref_index(ref, panels)
    pre_sig = _cfg_signature(pre[ref_idx])
    last_sig = {"v": pre_sig}
    state = {"pushed": False, "synced": False, "busy": False, "announced": False}

    def push_state(_note: str = "") -> None:
        return None

    def on_change() -> None:
        if state["busy"]:
            return
        try:
            sig = _cfg_signature(capture_panel(ref))
        except Exception:
            return
        if sig == last_sig["v"]:
            return
        state["busy"] = True
        try:
            if not state["pushed"]:
                undo.push_all(pre)
                state["pushed"] = True
            n = sync_style_from_ref(
                ref,
                panels,
                capture_panel=capture_panel,
                apply_cfg=apply_cfg,
                include_geometry=include_geometry,
            )
            try:
                last_sig["v"] = _cfg_signature(capture_panel(ref))
            except Exception:
                last_sig["v"] = sig
            state["synced"] = True
            draw_all()
            if n and not state["announced"]:
                print(f"Synced to {n} other plot(s).")
                state["announced"] = True
        finally:
            state["busy"] = False

    def finalize() -> bool:
        if state["busy"]:
            return bool(state["synced"] or state["pushed"])
        try:
            changed = _cfg_signature(capture_panel(ref)) != pre_sig
        except Exception:
            changed = bool(state["synced"])
        if not changed:
            draw_all()
            return False
        if not state["pushed"]:
            undo.push_all(pre)
            state["pushed"] = True
        if not state["synced"]:
            n = sync_style_from_ref(
                ref,
                panels,
                capture_panel=capture_panel,
                apply_cfg=apply_cfg,
                include_geometry=include_geometry,
            )
            draw_all()
            if n and not state["announced"]:
                print(f"Synced to {n} other plot(s).")
                state["announced"] = True
            state["synced"] = True
            return True
        draw_all()
        return True

    return push_state, on_change, finalize


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
    # Allow 0 (parity with interactive operando ``l``); reject negatives only.
    frame_w = max(0.0, frame_w)
    tick_w = max(0.0, tick_w)
    tick_minor = max(0.0, tick_minor)
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
                "bottom": (
                    bool(target.xaxis.label.get_visible())
                    if getattr(target, "xaxis", None) is not None and target.xaxis.label is not None
                    else bool(target.get_xlabel())
                ),
                "left": (
                    bool(target.yaxis.label.get_visible())
                    if getattr(target, "yaxis", None) is not None and target.yaxis.label is not None
                    else bool(target.get_ylabel())
                ),
                "right": bool(getattr(target, "_right_ylabel_on", False))
                if target is ref.ax
                else (
                    bool(target.yaxis.label.get_visible())
                    if getattr(target, "yaxis", None) is not None and target.yaxis.label is not None
                    else bool(target.get_ylabel())
                ),
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
            try:
                _ax._saved_tick_state = wasd_to_tick_state(_wasd)
            except Exception:
                pass
            try:
                finalize_spine_colors_for_axes(
                    ref.fig, [(_ax, getattr(_ax, "_saved_tick_state", None))]
                )
            except Exception:
                pass

        def _draw() -> None:
            # Do not sync peers here — that bypasses undo.push_all. Peer sync
            # happens in edit_ref_then_sync after a real ref change.
            try:
                ref.fig.canvas.draw_idle()
            except Exception:
                pass

        def _title_offsets(_target=target) -> None:
            from ..common.title_offsets import run_title_offset_nudge_menu

            run_title_offset_nudge_menu(
                fig=ref.fig,
                ax=_target,
                push_state=lambda: None,
                safe_input=safe_input,
                colorize_prompt=colorize_prompt,
                draw=_draw,
            )

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
                title_offset_handler=_title_offsets,
            )

        edited_pane = "ec" if pane == "e" else "operando"

        def _apply_scoped(panel, cfg, _pane=edited_pane):
            scoped = dict(cfg) if isinstance(cfg, dict) else {}
            scoped["_batch_edited_pane"] = _pane
            return apply_cfg(panel, scoped)

        edit_ref_then_sync(
            ref,
            panels,
            undo=undo,
            capture_panel=capture_panel,
            apply_cfg=_apply_scoped,
            draw_all=draw_all,
            edit_fn=_edit,
            include_geometry=False,
        )


def run_operando_batch_spine_color_menu(
    ref: OperandoPanel,
    panels: List[OperandoPanel],
    *,
    undo: SyncUndoStacks,
    capture_panel: Callable[[OperandoPanel], dict],
    apply_cfg: Callable[[OperandoPanel, dict], bool],
    draw_all: Callable[[], None],
) -> None:
    """Pane-scoped spine colors on reference, then sync that pane to all panels.

    Matches batch ``t``: each ``o``/``e`` visit gets its own ``edit_ref_then_sync``
    so an earlier pane is not dropped when the later pane is the last tag.
    """
    from ..common.menu_rendering import colorize_menu as _colorize_menu
    from ..operando.spine_colors import run_operando_spine_color_menu

    while True:
        if ref.ec_ax is not None:
            print(
                colorize_single_key_inline_commands(
                    "Spine colors — choose pane: o=operando (contour), e=EC side panel, q=back"
                )
            )
            pane = safe_input(
                colorize_prompt("Pane (o=operando, e=ec, q=back): "),
                cancel_on_interrupt=True,
            ).strip().lower()
        else:
            print(
                colorize_single_key_inline_commands(
                    "Spine colors apply to the contour plot. q=back"
                )
            )
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

        try:
            ref.fig._bp_last_spine_color_pane = pane  # type: ignore[attr-defined]
        except Exception:
            pass
        edited_pane = "ec" if pane == "e" else "operando"

        def _edit(_pane=pane) -> None:
            run_operando_spine_color_menu(
                fig=ref.fig,
                ax=ref.ax,
                ec_ax=ref.ec_ax,
                push_state=noop_snapshot,
                safe_input=safe_input,
                colorize_menu=_colorize_menu,
                colorize_prompt=colorize_prompt,
                fixed_pane=_pane,
            )

        def _apply_scoped(panel, cfg, _pane=edited_pane):
            scoped = dict(cfg) if isinstance(cfg, dict) else {}
            scoped["_batch_edited_pane"] = _pane
            return apply_cfg(panel, scoped)

        edit_ref_then_sync(
            ref,
            panels,
            undo=undo,
            capture_panel=capture_panel,
            apply_cfg=_apply_scoped,
            draw_all=draw_all,
            edit_fn=_edit,
            include_geometry=False,
        )


def _peer_operando_style(panel: OperandoPanel) -> dict:
    from ..operando.style import build_operando_ec_style_config_v2

    # Style-only capture: no canvas/geometry hitchhiking on scoped sync.
    cfg, _ext = build_operando_ec_style_config_v2(
        panel.fig, panel.ax, panel.im, panel.cbar, panel.ec_ax, "ps"
    )
    return cfg


def _apply_operando_merged(panel: OperandoPanel, cfg: dict) -> bool:
    """Full style-only apply (used by legacy ``apply_operando_scoped_sync``)."""
    from ..operando.style_apply import apply_operando_ec_style_config

    merged = dict(cfg)
    merged["kind"] = "operando_ec_style"
    merged.pop("geometry", None)
    merged.pop("axes_geometry", None)
    return bool(
        apply_operando_ec_style_config(
            merged,
            fig=panel.fig,
            ax=panel.ax,
            im=panel.im,
            cbar=panel.cbar,
            ec_ax=panel.ec_ax,
            silent=True,
        )
    )


def apply_operando_scoped_sync(
    panel: OperandoPanel,
    ref_cfg: dict,
    *,
    top_keys: frozenset[str] = frozenset(),
    nested_keys: dict[str, frozenset[str]] | None = None,
    op_spine_mode: str | None = None,
    ec_spine_mode: str | None = None,
    silent: bool = True,
) -> bool:
    """Merge selected keys onto peer style, then full style-apply (legacy).

    Prefer the direct ``apply_operando_*_only`` helpers for batch menus — full
    apply re-enters intensity/CIF/reverse even when those keys were not merged.
    """
    from .batch_scoped_sync import deep_merge_keys, merge_spines_props

    try:
        peer = _peer_operando_style(panel)
        merged = deep_merge_keys(
            peer,
            ref_cfg,
            top_keys=top_keys,
            nested_keys=nested_keys,
            force_kind="operando_ec_style",
            drop_geometry=True,
        )
        if op_spine_mode:
            op = dict(merged.get("operando") or {})
            ref_op = ref_cfg.get("operando") if isinstance(ref_cfg.get("operando"), dict) else {}
            op["spines"] = merge_spines_props(
                (peer.get("operando") or {}).get("spines"),
                ref_op.get("spines"),
                mode=op_spine_mode,
            )
            merged["operando"] = op
        if ec_spine_mode and panel.ec_ax is not None:
            ec = dict(merged.get("ec") or {})
            ref_ec = ref_cfg.get("ec") if isinstance(ref_cfg.get("ec"), dict) else {}
            ec["spines"] = merge_spines_props(
                (peer.get("ec") or {}).get("spines"),
                ref_ec.get("spines"),
                mode=ec_spine_mode,
            )
            merged["ec"] = ec
        ec = merged.get("ec")
        if isinstance(ec, dict):
            ec = dict(ec)
            ec.pop("ions_abs", None)
            merged["ec"] = ec
        return _apply_operando_merged(panel, merged)
    except Exception as exc:
        if not silent:
            print(f"Operando scoped sync failed for {getattr(panel, 'path', '?')}: {exc}")
        return False


def _draw_idle(panel: OperandoPanel) -> None:
    try:
        panel.fig.canvas.draw_idle()
    except Exception:
        pass


def apply_operando_colormap_only(panel: OperandoPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch ``oc``: colormap only (preserves clim / CIF / labels / reverse)."""
    from ..operando.colors import apply_operando_colormap

    try:
        op = cfg.get("operando") if isinstance(cfg.get("operando"), dict) else {}
        cmap = op.get("cmap")
        if not cmap:
            return False
        clim = None
        try:
            clim = panel.im.get_clim()
        except Exception:
            pass
        apply_operando_colormap(panel.im, str(cmap))
        if clim is not None:
            try:
                panel.im.set_clim(*clim)
            except Exception:
                pass
        try:
            _update_custom_colorbar(panel.cbar.ax, panel.im)
        except Exception:
            pass
        _draw_idle(panel)
        return True
    except Exception as exc:
        if not silent:
            print(f"Operando colormap sync failed for {getattr(panel, 'path', '?')}: {exc}")
        return False


def apply_operando_ec_curve_only(panel: OperandoPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch ``el``: EC curve chrome only."""
    from ..operando.style_apply import _apply_ec_wasd_spines_ticks_curve

    try:
        if panel.ec_ax is None:
            return False
        ref_ec = cfg.get("ec") if isinstance(cfg.get("ec"), dict) else {}
        curve = ref_ec.get("curve")
        if not isinstance(curve, dict) or not curve:
            return False
        version = int(cfg.get("version") or 2)
        _apply_ec_wasd_spines_ticks_curve(
            panel.fig, panel.ec_ax, {"ec": {"curve": dict(curve)}}, version
        )
        _draw_idle(panel)
        return True
    except Exception as exc:
        if not silent:
            print(f"Operando EC curve sync failed for {getattr(panel, 'path', '?')}: {exc}")
        return False


def apply_operando_visibility_only(panel: OperandoPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch ``v``: colorbar / EC visibility + colorbar label mode/text + h-offsets."""
    try:
        colorbar_cfg = cfg.get("colorbar") if isinstance(cfg.get("colorbar"), dict) else {}
        fig_cfg = cfg.get("figure") if isinstance(cfg.get("figure"), dict) else {}
        ec_cfg = cfg.get("ec") if isinstance(cfg.get("ec"), dict) else {}
        geom = cfg.get("geometry") if isinstance(cfg.get("geometry"), dict) else {}

        cb_visible = colorbar_cfg.get("visible")
        if cb_visible is None:
            cb_visible = fig_cfg.get("cb_visible")
        if cb_visible is not None:
            panel.cbar.ax.set_visible(bool(cb_visible))

        cb_label_mode = colorbar_cfg.get("mode", fig_cfg.get("cb_label_mode"))
        if cb_label_mode in ("normal", "highlow"):
            panel.fig._colorbar_label_mode = cb_label_mode
        cb_label_text = colorbar_cfg.get("label")
        if cb_label_text is not None:
            from ...utils import finalize_axis_label_text

            cb_label_text = finalize_axis_label_text(str(cb_label_text))
            panel.cbar.ax._colorbar_label = cb_label_text
        try:
            mode = getattr(panel.fig, "_colorbar_label_mode", "highlow")
            _update_custom_colorbar(
                panel.cbar.ax,
                panel.im,
                label=cb_label_text if cb_label_text is not None else None,
                label_mode=mode if mode in ("normal", "highlow") else "highlow",
            )
        except Exception:
            pass
        if colorbar_cfg.get("ticks_left") is not None:
            ticks_left = bool(colorbar_cfg["ticks_left"])
            panel.cbar.ax._colorbar_ticks_left = ticks_left
            panel.cbar.ax.yaxis.set_ticks_position(
                "left" if ticks_left else "right"
            )
        if colorbar_cfg.get("label_left") is not None:
            label_left = bool(colorbar_cfg["label_left"])
            panel.cbar.ax._colorbar_label_left = label_left
            panel.cbar.ax.yaxis.set_label_position(
                "left" if label_left else "right"
            )

        if panel.ec_ax is not None and ec_cfg.get("visible") is not None:
            panel.ec_ax.set_visible(bool(ec_cfg["visible"]))

        # ``v`` → ``m`` horizontal offsets (psg capture carries geometry).
        layout_dirty = False
        if "cb_h_offset" in geom:
            try:
                panel.cbar.ax._cb_h_offset_in = float(geom.get("cb_h_offset") or 0.0)
                layout_dirty = True
            except Exception:
                pass
        if panel.ec_ax is not None and "ec_h_offset" in geom:
            try:
                panel.ec_ax._ec_h_offset_in = float(geom.get("ec_h_offset") or 0.0)
                layout_dirty = True
            except Exception:
                pass
        if layout_dirty:
            try:
                cb_w_in, cb_gap_in, ec_gap_in, ec_w_in, ax_w_in, ax_h_in = _ensure_fixed_params(
                    panel.fig, panel.ax, panel.cbar.ax, panel.ec_ax
                )
                _apply_group_layout_inches(
                    panel.fig, panel.ax, panel.cbar.ax, panel.ec_ax,
                    ax_w_in, ax_h_in, cb_w_in, cb_gap_in, ec_gap_in, ec_w_in,
                )
            except Exception:
                pass

        _draw_idle(panel)
        return True
    except Exception as exc:
        if not silent:
            print(f"Operando visibility sync failed for {getattr(panel, 'path', '?')}: {exc}")
        return False


def apply_operando_wasd_chrome_only(panel: OperandoPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch ``t``: WASD / tick spacing / title offsets (not ``l`` widths or ``k`` colors).

    When ``cfg["_batch_edited_pane"]`` is ``operando`` or ``ec``, only that pane
    is overwritten on peers (pane chooser must not clobber the other pane).
    """
    import copy

    from ..operando.style_apply import (
        _apply_ec_wasd_spines_ticks_curve,
        _apply_operando_wasd_spines_ticks,
        _apply_title_offsets_and_labelpads,
        _finalize_spine_colors,
        _reposition_titles,
        _save_labelpads,
    )
    from .batch_scoped_sync import merge_spines_props

    try:
        edited = cfg.get("_batch_edited_pane")
        touch_op = edited in (None, "operando")
        touch_ec = edited in (None, "ec")
        ref_op = cfg.get("operando") if isinstance(cfg.get("operando"), dict) else {}
        ref_ec = cfg.get("ec") if isinstance(cfg.get("ec"), dict) else {}
        peer = {}
        try:
            peer = _peer_operando_style(panel)
        except Exception:
            peer = {}
        peer_op = peer.get("operando") if isinstance(peer.get("operando"), dict) else {}
        peer_ec = peer.get("ec") if isinstance(peer.get("ec"), dict) else {}

        op: dict = {}
        if touch_op:
            for key in ("wasd_state", "ticks", "title_offsets", "labelpads"):
                if key in ref_op:
                    op[key] = copy.deepcopy(ref_op[key])
            # Frame/tick linewidths belong to ``l`` — do not hitchhike onto ``t``.
            ticks_op = op.get("ticks")
            if isinstance(ticks_op, dict):
                ticks_op = dict(ticks_op)
                ticks_op.pop("widths", None)
                op["ticks"] = ticks_op
            op["spines"] = merge_spines_props(
                peer_op.get("spines"), ref_op.get("spines"), mode="visible"
            )

        ec_part: dict = {}
        if touch_ec:
            for key in ("wasd_state", "ticks", "title_offsets", "labelpads"):
                if key in ref_ec:
                    ec_part[key] = copy.deepcopy(ref_ec[key])
            ticks_ec = ec_part.get("ticks")
            if isinstance(ticks_ec, dict):
                ticks_ec = dict(ticks_ec)
                ticks_ec.pop("widths", None)
                ec_part["ticks"] = ticks_ec
            ec_part["spines"] = merge_spines_props(
                peer_ec.get("spines"), ref_ec.get("spines"), mode="visible"
            )
        # Intentionally omit ``curve`` — owned by ``el``.

        version = int(cfg.get("version") or 2)
        if touch_op:
            _apply_operando_wasd_spines_ticks(panel.fig, panel.ax, op, version)
        if touch_ec and panel.ec_ax is not None:
            _apply_ec_wasd_spines_ticks_curve(
                panel.fig, panel.ec_ax, {"ec": ec_part}, version
            )
        _finalize_spine_colors(panel.fig, panel.ax, panel.ec_ax)
        saved = _save_labelpads(panel.ax, panel.ec_ax)
        _apply_title_offsets_and_labelpads(
            panel.ax, panel.ec_ax,
            {"ec": ec_part} if touch_ec else {"ec": {}},
            op if touch_op else {},
            *saved,
        )
        _reposition_titles(panel.fig, panel.ax, panel.ec_ax)
        _draw_idle(panel)
        return True
    except Exception as exc:
        if not silent:
            print(f"Operando WASD sync failed for {getattr(panel, 'path', '?')}: {exc}")
        return False


def apply_operando_spine_colors_only(panel: OperandoPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch ``k``: spine colors only (linewidths owned by ``l``).

    Honors ``cfg["_batch_edited_pane"]`` so editing EC colors does not clobber
    peer contour colors (and vice versa).
    """
    from ..operando.style_apply import (
        _apply_ec_wasd_spines_ticks_curve,
        _apply_operando_wasd_spines_ticks,
        _finalize_spine_colors,
    )
    from .batch_scoped_sync import merge_spines_props

    try:
        edited = cfg.get("_batch_edited_pane")
        touch_op = edited in (None, "operando")
        touch_ec = edited in (None, "ec")
        ref_op = cfg.get("operando") if isinstance(cfg.get("operando"), dict) else {}
        ref_ec = cfg.get("ec") if isinstance(cfg.get("ec"), dict) else {}
        peer = {}
        try:
            peer = _peer_operando_style(panel)
        except Exception:
            peer = {}
        peer_op = peer.get("operando") if isinstance(peer.get("operando"), dict) else {}
        peer_ec = peer.get("ec") if isinstance(peer.get("ec"), dict) else {}

        version = int(cfg.get("version") or 2)
        if touch_op:
            op = {
                "spines": merge_spines_props(
                    peer_op.get("spines"), ref_op.get("spines"), mode="color"
                )
            }
            _apply_operando_wasd_spines_ticks(panel.fig, panel.ax, op, version)
        if touch_ec and panel.ec_ax is not None:
            ec_part = {
                "spines": merge_spines_props(
                    peer_ec.get("spines"), ref_ec.get("spines"), mode="color"
                )
            }
            _apply_ec_wasd_spines_ticks_curve(
                panel.fig, panel.ec_ax, {"ec": ec_part}, version
            )
        _finalize_spine_colors(panel.fig, panel.ax, panel.ec_ax)
        _draw_idle(panel)
        return True
    except Exception as exc:
        if not silent:
            print(f"Operando spine-color sync failed for {getattr(panel, 'path', '?')}: {exc}")
        return False


def apply_operando_labels_only(panel: OperandoPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch ``or``: operando axis title text only."""
    try:
        from ...utils import finalize_axis_label_text

        op = cfg.get("operando") if isinstance(cfg.get("operando"), dict) else {}
        labels = op.get("custom_labels")
        if not isinstance(labels, dict):
            return False
        custom = dict(getattr(panel.ax, "_custom_labels", None) or {})
        for k, v in labels.items():
            custom[k] = None if v is None else finalize_axis_label_text(str(v))
        panel.ax._custom_labels = custom
        # Use key presence so empty-string clears sync (truthy check would skip).
        # Keep _stored_* in sync so hide→t title-on / dump cannot revive stale text.
        if "x" in labels and labels["x"] is not None:
            text = str(custom["x"])
            panel.ax.set_xlabel(text)
            panel.ax._stored_xlabel = text
        if "y" in labels and labels["y"] is not None:
            text = str(custom["y"])
            panel.ax.set_ylabel(text)
            panel.ax._stored_ylabel = text
        _draw_idle(panel)
        return True
    except Exception as exc:
        if not silent:
            print(f"Operando label sync failed for {getattr(panel, 'path', '?')}: {exc}")
        return False


def apply_operando_ec_labels_only(panel: OperandoPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch ``er``: EC axis title text only."""
    try:
        from ...utils import finalize_axis_label_text

        if panel.ec_ax is None:
            return False
        ec_cfg = cfg.get("ec") if isinstance(cfg.get("ec"), dict) else {}
        ec_custom = ec_cfg.get("custom_labels")
        if not isinstance(ec_custom, dict):
            return False
        ec_ax = panel.ec_ax
        stored = dict(getattr(ec_ax, "_custom_labels", None) or {})
        for k, v in ec_custom.items():
            stored[k] = None if v is None else finalize_axis_label_text(str(v))
        ec_ax._custom_labels = stored

        # Prefer peer live title visibility so ``er`` does not invent flags from
        # a ref WASD snapshot (owned by ``t``). Ref wasd_state is only a fallback.
        ec_wasd = ec_cfg.get("wasd_state") if isinstance(ec_cfg.get("wasd_state"), dict) else {}
        try:
            bottom_on = bool(ec_ax.xaxis.label.get_visible())
        except Exception:
            bottom_on = bool(ec_wasd.get("bottom", {}).get("title", True)) if ec_wasd else True
        try:
            # WASD ``t`` owns title visibility; do not infer ON from nonempty text.
            right_on = bool(getattr(ec_ax, "_right_ylabel_on", True))
        except Exception:
            right_on = bool(ec_wasd.get("right", {}).get("title", True)) if ec_wasd else True

        if bottom_on and "x" in ec_custom and ec_custom.get("x") is not None:
            text = str(stored["x"])
            ec_ax.set_xlabel(text)
            ec_ax._stored_xlabel = text
        # Overlay ions keep a time spine title (session / style_apply parity).
        ylab = stored.get("y_time")
        if ylab is None:
            ylab = stored.get("y")
        if right_on and ylab is not None:
            text = str(ylab)
            ec_ax.set_ylabel(text)
            ec_ax._stored_ylabel = text
        _draw_idle(panel)
        return True
    except Exception as exc:
        if not silent:
            print(f"Operando EC label sync failed for {getattr(panel, 'path', '?')}: {exc}")
        return False


def apply_operando_ions_only(panel: OperandoPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch ``ey``: ions mode + params (ions_abs recomputed per panel).

    Omits ``y_reversed`` / ``intensity_range`` / ``cif`` so peer reverse and clim
    stay local (``ps`` peer snapshots omit reverse — injecting ``False`` would
    un-flip panels that used batch ``r``).
    """
    import copy

    from ..operando.style_apply import _apply_reverse_intensity_cif_ions

    try:
        if panel.ec_ax is None:
            return False
        ref_ec = cfg.get("ec") if isinstance(cfg.get("ec"), dict) else {}
        peer = {}
        try:
            peer = _peer_operando_style(panel)
        except Exception:
            peer = {}
        peer_ec = peer.get("ec") if isinstance(peer.get("ec"), dict) else {}

        # Do not include y_reversed — key presence in apply_view_geom would force
        # un-reverse when peer ``ps`` capture omitted the flag.
        op: dict = {}
        ec = {
            "y_mode": ref_ec.get("y_mode", peer_ec.get("y_mode", "time")),
        }
        if "ion_params" in ref_ec and isinstance(ref_ec.get("ion_params"), dict):
            ec["ion_params"] = copy.deepcopy(ref_ec["ion_params"])
        elif isinstance(peer_ec.get("ion_params"), dict):
            ec["ion_params"] = copy.deepcopy(peer_ec["ion_params"])
        for key in ("ion_guides", "ion_annots"):
            if key in ref_ec:
                ec[key] = copy.deepcopy(ref_ec[key])
        # Never copy panel-local absolute ions arrays.
        mini = {"version": 2, "operando": op, "ec": ec}
        result = _apply_reverse_intensity_cif_ions(
            panel.fig, panel.ax, panel.im, panel.ec_ax, mini, op, silent=True
        )
        if result is False:
            return False
        _draw_idle(panel)
        return True
    except Exception as exc:
        if not silent:
            print(f"Operando ions sync failed for {getattr(panel, 'path', '?')}: {exc}")
        return False


def apply_operando_ec_grid_only(panel: OperandoPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch ``eg``: EC grid only."""
    try:
        if panel.ec_ax is None:
            return False
        ec_cfg = cfg.get("ec") if isinstance(cfg.get("ec"), dict) else {}
        ec_grid = ec_cfg.get("grid")
        if not isinstance(ec_grid, dict):
            return False
        g = dict(ec_grid)
        g.setdefault("visible", False)
        g.setdefault("alpha", 0.3)
        g.setdefault("linestyle", "--")
        g.setdefault("color", "0.6")
        g.setdefault("which", "major")
        panel.ec_ax._ec_grid = g
        panel.ec_ax.grid(
            g["visible"],
            which=g["which"],
            axis="both",
            alpha=float(g["alpha"]),
            color=str(g["color"]),
            linestyle=str(g["linestyle"]),
        )
        _draw_idle(panel)
        return True
    except Exception as exc:
        if not silent:
            print(f"Operando EC grid sync failed for {getattr(panel, 'path', '?')}: {exc}")
        return False


def apply_operando_cif_colors_only(panel: OperandoPanel, cfg: dict, *, silent: bool = True) -> bool:
    """Batch CIF ``c``: colors / display flags (not peak tick data / clim)."""
    try:
        cif = dict(cfg.get("cif") or {}) if isinstance(cfg.get("cif"), dict) else {}
        series = list(getattr(panel.ax, "_operando_cif_tick_series", None) or [])
        n_peer = len(series)
        if not n_peer:
            return False

        for key, default in (("title_visible", True), ("set_visible", True)):
            vals = cif.get(key)
            if not isinstance(vals, list):
                continue
            if len(vals) < n_peer:
                pad = default if not vals else vals[-1]
                cif[key] = list(vals) + [pad] * (n_peer - len(vals))
            elif len(vals) > n_peer:
                cif[key] = list(vals)[:n_peer]

        fig = panel.fig
        ax = panel.ax
        if "show_hkl" in cif:
            fig._operando_cif_show_hkl = bool(cif.get("show_hkl"))
        if "show_titles" in cif:
            fig._operando_cif_show_titles = bool(cif.get("show_titles", True))
        if "colormap" in cif:
            fig._operando_cif_colormap = cif.get("colormap")
        if "highlight" in cif:
            fig._operando_cif_highlight = bool(cif.get("highlight", False))
        if "title_font" in cif and isinstance(cif.get("title_font"), dict):
            fig._operando_cif_title_font = dict(cif.get("title_font") or {})
        if isinstance(cif.get("title_visible"), list):
            fig._operando_cif_title_visible = list(cif["title_visible"])
        if isinstance(cif.get("set_visible"), list):
            fig._operando_cif_set_visible = list(cif["set_visible"])

        colors = cif.get("colors")
        labels = cif.get("labels")
        if isinstance(colors, list) or isinstance(labels, list):
            updated = list(series)
            n_updates = max(
                len(colors) if isinstance(colors, list) else 0,
                len(labels) if isinstance(labels, list) else 0,
            )
            for idx in range(min(n_updates, len(updated))):
                lab, fname, peaksQ, wl_e, qmax, col = updated[idx]
                if isinstance(labels, list) and idx < len(labels) and labels[idx] is not None:
                    lab = str(labels[idx])
                if isinstance(colors, list) and idx < len(colors) and colors[idx] is not None:
                    col = colors[idx]
                updated[idx] = (lab, fname, peaksQ, wl_e, qmax, col)
            ax._operando_cif_tick_series = updated

        _redraw_operando_cif_if_present(fig, ax)
        _draw_idle(panel)
        return True
    except Exception as exc:
        if not silent:
            print(f"Operando CIF color sync failed for {getattr(panel, 'path', '?')}: {exc}")
        return False


__all__ = [
    "apply_frame_tick_widths_all",
    "apply_layout_inches_to_all",
    "apply_layout_inches_to_panel",
    "apply_operando_cif_colors_only",
    "apply_operando_colormap_only",
    "apply_operando_ec_curve_only",
    "apply_operando_ec_grid_only",
    "apply_operando_ec_labels_only",
    "apply_operando_ions_only",
    "apply_operando_labels_only",
    "apply_operando_scoped_sync",
    "apply_operando_spine_colors_only",
    "apply_operando_visibility_only",
    "apply_operando_wasd_chrome_only",
    "edit_ref_then_sync",
    "make_batch_live_sync",
    "noop_snapshot",
    "panel_layout_inches",
    "prompt_axis_limits",
    "reverse_y_all",
    "run_operando_batch_spine_color_menu",
    "run_operando_batch_spine_menu",
    "set_clim_all",
    "set_ec_xlim_all",
    "set_ec_ylim_all",
    "set_operando_xlim_all",
    "set_operando_ylim_all",
    "sync_style_from_ref",
]

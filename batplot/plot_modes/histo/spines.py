"""Spine/tick state for histogram mode (XY-style ``t`` menu)."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Set

from ..common.spines import (
    apply_changed_side_title_positions,
    apply_wasd_spines,
    apply_wasd_tick_params,
    build_wasd_state,
    default_flat_tick_state,
    legacy_tick_state_to_flat,
    sync_legacy_tick_keys,
    sync_tick_state_from_wasd,
)
from ...ui import position_bottom_xlabel, position_left_ylabel, position_top_xlabel
from .plot import HistoState

_TICK_DEFAULTS = {"top": False, "bottom": True, "left": True, "right": False}
_LABEL_DEFAULTS = {"top": False, "bottom": True, "left": True, "right": False}


def ensure_histo_tick_state(ax) -> Dict[str, bool]:
    tick_state = getattr(ax, "_saved_tick_state", None)
    if not isinstance(tick_state, dict) or not tick_state:
        tick_state = default_flat_tick_state(
            tick_defaults=_TICK_DEFAULTS,
            label_defaults=_LABEL_DEFAULTS,
        )
        ax._saved_tick_state = tick_state
    else:
        tick_state = legacy_tick_state_to_flat(
            tick_state,
            tick_defaults=_TICK_DEFAULTS,
            label_defaults=_LABEL_DEFAULTS,
        )
        ax._saved_tick_state = tick_state
    sync_legacy_tick_keys(tick_state)
    return tick_state


def ensure_histo_wasd(fig, ax, tick_state: Dict[str, bool]) -> Dict[str, Dict[str, bool]]:
    wasd = getattr(fig, "_histo_wasd_state", None)
    if not isinstance(wasd, dict) or not wasd:
        wasd = build_wasd_state(
            get_spine_visible=lambda side: bool(ax.spines.get(side).get_visible()) if ax.spines.get(side) else False,
            tick_state=tick_state,
            title_visible={
                "top": False,
                "bottom": bool(ax.xaxis.label.get_visible()),
                "left": bool(ax.yaxis.label.get_visible()),
                "right": False,
            },
            tick_defaults=_TICK_DEFAULTS,
            label_defaults=_LABEL_DEFAULTS,
        )
        fig._histo_wasd_state = wasd
    return wasd


def capture_histo_spine_snapshot(fig, ax) -> dict:
    tick_state = ensure_histo_tick_state(ax)
    wasd = ensure_histo_wasd(fig, ax, tick_state)
    return {
        "tick_state": dict(tick_state),
        "wasd_state": {side: dict(state) for side, state in wasd.items()},
        "tick_direction": getattr(fig, "_tick_direction", "out"),
        "tick_lengths": dict(getattr(fig, "_tick_lengths", {}) or {}),
    }


def apply_histo_spine_snapshot(fig, ax, snap: dict) -> None:
    if isinstance(snap.get("tick_state"), dict):
        tick_state = legacy_tick_state_to_flat(
            snap["tick_state"],
            tick_defaults=_TICK_DEFAULTS,
            label_defaults=_LABEL_DEFAULTS,
        )
        sync_legacy_tick_keys(tick_state)
        ax._saved_tick_state = tick_state
    if isinstance(snap.get("wasd_state"), dict):
        fig._histo_wasd_state = {side: dict(state) for side, state in snap["wasd_state"].items()}
    if snap.get("tick_direction"):
        fig._tick_direction = str(snap["tick_direction"])
    if isinstance(snap.get("tick_lengths"), dict):
        fig._tick_lengths = dict(snap["tick_lengths"])


def apply_histo_wasd(
    fig,
    ax,
    wasd: Dict[str, Dict[str, bool]],
    tick_state: Dict[str, bool],
    state: HistoState,
    *,
    changed_sides: Optional[Set[str]] = None,
) -> None:
    if changed_sides is None:
        changed_sides = {"bottom", "top", "left", "right"}
    apply_wasd_spines(ax, wasd)
    apply_wasd_tick_params(ax, wasd)
    direction = getattr(fig, "_tick_direction", "out")
    ax.tick_params(axis="both", which="both", direction=direction)
    tick_lengths = getattr(fig, "_tick_lengths", {}) or {}
    major = tick_lengths.get("major")
    if major is not None:
        minor = tick_lengths.get("minor", float(major) * 0.7)
        ax.tick_params(axis="both", which="major", length=major)
        ax.tick_params(axis="both", which="minor", length=minor)

    bottom = wasd.get("bottom", {})
    if bool(bottom.get("title", True)):
        ax.set_xlabel(state.style.xlabel, fontsize=state.style.label_fontsize)
        ax.xaxis.label.set_visible(True)
    else:
        if not hasattr(ax, "_stored_xlabel"):
            ax._stored_xlabel = state.style.xlabel
        ax.xaxis.label.set_visible(False)

    top = wasd.get("top", {})
    ax._top_xlabel_on = bool(top.get("title", False))  # type: ignore[attr-defined]
    if state.style.top_xlabel:
        ax._top_xlabel_text_override = state.style.top_xlabel  # type: ignore[attr-defined]

    left = wasd.get("left", {})
    ylab = state.style.ylabel or state.y_label_default()
    if bool(left.get("title", True)):
        ax.set_ylabel(ylab, fontsize=state.style.label_fontsize)
        ax.yaxis.label.set_visible(True)
    else:
        if not hasattr(ax, "_stored_ylabel"):
            ax._stored_ylabel = ylab
        ax.yaxis.label.set_visible(False)

    apply_changed_side_title_positions(
        changed_sides,
        bottom=lambda: position_bottom_xlabel(ax, fig, tick_state),
        top=lambda: position_top_xlabel(ax, fig, tick_state),
        left=lambda: position_left_ylabel(ax, fig, tick_state),
        right=lambda: None,
    )


def reapply_histo_spine_layout(
    fig,
    ax,
    state: HistoState,
    *,
    changed_sides: Optional[Set[str]] = None,
) -> None:
    tick_state = ensure_histo_tick_state(ax)
    wasd = ensure_histo_wasd(fig, ax, tick_state)
    apply_histo_wasd(fig, ax, wasd, tick_state, state, changed_sides=changed_sides)


def sync_histo_spine_from_reference(ref_fig, ref_ax, targets: list[tuple[Any, Any]]) -> None:
    snap = capture_histo_spine_snapshot(ref_fig, ref_ax)
    for fig, ax in targets:
        apply_histo_spine_snapshot(fig, ax, snap)


def histo_title_offset_menu(
    *,
    fig,
    ax,
    tick_state: Dict[str, bool],
    push_state: Callable[[], None],
    safe_input: Callable[..., str],
    colorize_prompt: Callable[[str], str],
) -> None:
    """Nudge bottom/left axis title positions (histogram has no duplicate top/right titles)."""

    def _dpi() -> float:
        try:
            return float(fig.dpi)
        except Exception:
            return 72.0

    def _px_value(attr: str) -> float:
        try:
            pts = float(getattr(ax, attr, 0.0) or 0.0)
        except Exception:
            pts = 0.0
        return pts * _dpi() / 72.0

    def _set_attr(attr: str, pts: float) -> None:
        try:
            setattr(ax, attr, float(pts))
        except Exception:
            pass

    def _nudge(attr: str, delta_px: float) -> None:
        try:
            current_pts = float(getattr(ax, attr, 0.0) or 0.0)
        except Exception:
            current_pts = 0.0
        delta_pts = float(delta_px) * 72.0 / _dpi()
        _set_attr(attr, current_pts + delta_pts)

    snapshot_taken = False

    def _ensure_snapshot() -> None:
        nonlocal snapshot_taken
        if not snapshot_taken:
            push_state()
            snapshot_taken = True

    while True:
        print("Title offsets (bottom X / left Y):")
        print("  s: bottom X label   a: left Y label   q: back")
        choice = safe_input(colorize_prompt("Title offset (s/a/q): ")).strip().lower()
        if not choice or choice == "q":
            break
        if choice == "s":
            while True:
                y_px = _px_value("_xlabel_manual_offset_y_pts")
                x_px = _px_value("_xlabel_manual_offset_x_pts")
                print(f"Bottom title offset: Y={y_px:+.2f} px, X={x_px:+.2f} px")
                sub = safe_input(colorize_prompt("bottom (w=up, s=down, a=left, d=right, 0=reset, q=back): ")).strip().lower()
                if not sub:
                    continue
                if sub == "q":
                    break
                if sub == "0":
                    _ensure_snapshot()
                    _set_attr("_xlabel_manual_offset_y_pts", 0.0)
                    _set_attr("_xlabel_manual_offset_x_pts", 0.0)
                elif sub == "w":
                    _ensure_snapshot()
                    _nudge("_xlabel_manual_offset_y_pts", +1.0)
                elif sub == "s":
                    _ensure_snapshot()
                    _nudge("_xlabel_manual_offset_y_pts", -1.0)
                elif sub == "a":
                    _ensure_snapshot()
                    _nudge("_xlabel_manual_offset_x_pts", -1.0)
                elif sub == "d":
                    _ensure_snapshot()
                    _nudge("_xlabel_manual_offset_x_pts", +1.0)
                else:
                    print("Unknown choice.")
                    continue
                position_bottom_xlabel(ax, fig, tick_state)
                fig.canvas.draw_idle()
            continue
        if choice == "a":
            while True:
                x_px = _px_value("_ylabel_manual_offset_x_pts")
                y_px = _px_value("_ylabel_manual_offset_y_pts")
                print(f"Left title offset: X={x_px:+.2f} px, Y={y_px:+.2f} px")
                sub = safe_input(colorize_prompt("left (w=up, s=down, a=left, d=right, 0=reset, q=back): ")).strip().lower()
                if not sub:
                    continue
                if sub == "q":
                    break
                if sub == "0":
                    _ensure_snapshot()
                    _set_attr("_ylabel_manual_offset_x_pts", 0.0)
                    _set_attr("_ylabel_manual_offset_y_pts", 0.0)
                elif sub == "w":
                    _ensure_snapshot()
                    _nudge("_ylabel_manual_offset_y_pts", +1.0)
                elif sub == "s":
                    _ensure_snapshot()
                    _nudge("_ylabel_manual_offset_y_pts", -1.0)
                elif sub == "a":
                    _ensure_snapshot()
                    _nudge("_ylabel_manual_offset_x_pts", -1.0)
                elif sub == "d":
                    _ensure_snapshot()
                    _nudge("_ylabel_manual_offset_x_pts", +1.0)
                else:
                    print("Unknown choice.")
                    continue
                position_left_ylabel(ax, fig, tick_state)
                fig.canvas.draw_idle()
            continue
        print("Unknown choice.")


__all__ = [
    "apply_histo_spine_snapshot",
    "apply_histo_wasd",
    "capture_histo_spine_snapshot",
    "ensure_histo_tick_state",
    "ensure_histo_wasd",
    "histo_title_offset_menu",
    "reapply_histo_spine_layout",
    "sync_histo_spine_from_reference",
]

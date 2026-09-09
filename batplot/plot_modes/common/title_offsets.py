"""Shared helpers for manual axis-title offset attributes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any, Dict


TITLE_OFFSET_DEFAULTS = {
    "top_y": 0.0,
    "top_x": 0.0,
    "bottom_y": 0.0,
    "left_x": 0.0,
    "right_x": 0.0,
    "right_y": 0.0,
}

_ATTR_BY_KEY = {
    "top_y": "_top_xlabel_manual_offset_y_pts",
    "top_x": "_top_xlabel_manual_offset_x_pts",
    "bottom_y": "_bottom_xlabel_manual_offset_y_pts",
    "left_x": "_left_ylabel_manual_offset_x_pts",
    "right_x": "_right_ylabel_manual_offset_x_pts",
    "right_y": "_right_ylabel_manual_offset_y_pts",
}

# Side key → primary nudge attr (secondary axis on WASD ``d`` / ``w``).
_SIDE_PRIMARY_ATTR = {
    "w": "_top_xlabel_manual_offset_y_pts",
    "s": "_bottom_xlabel_manual_offset_y_pts",
    "a": "_left_ylabel_manual_offset_x_pts",
    "d": "_right_ylabel_manual_offset_x_pts",
}


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def capture_title_offsets(axis: Any) -> Dict[str, float]:
    """Capture the six manual title-offset attrs used by interactive menus."""
    return {
        key: _as_float(getattr(axis, attr, default))
        for key, default in TITLE_OFFSET_DEFAULTS.items()
        for attr in (_ATTR_BY_KEY[key],)
    }


def restore_title_offsets(axis: Any, offsets: Mapping[str, object] | None) -> None:
    """Restore manual title-offset attrs from a saved mapping."""
    offsets = offsets or {}
    if "top_y" not in offsets and "top" in offsets:
        offsets = {**offsets, "top_y": offsets.get("top")}
    if "right_x" not in offsets and "right" in offsets:
        offsets = {**offsets, "right_x": offsets.get("right")}
    for key, attr in _ATTR_BY_KEY.items():
        setattr(axis, attr, _as_float(offsets.get(key, TITLE_OFFSET_DEFAULTS[key])))


def reset_title_offsets(axis: Any) -> None:
    """Reset all manual title-offset attrs to zero."""
    restore_title_offsets(axis, TITLE_OFFSET_DEFAULTS)


def run_title_offset_nudge_menu(
    *,
    fig: Any,
    ax: Any,
    push_state: Callable[[], None],
    safe_input: Callable[..., str],
    colorize_prompt: Callable[[str], str],
    draw: Callable[[], None],
    sides: tuple[str, ...] = ("w", "a", "s", "d"),
    axis_by_side: dict[str, Any] | None = None,
    initial_side: str | None = None,
) -> None:
    """Compact WASD title-offset nudge used by batch spine menus (``t`` → ``p``).

    ``axis_by_side`` routes a side to a different axes (e.g. CPC right title on
    ``ax2``). Defaults to ``ax`` for every side.

    ``initial_side`` skips the side picker and opens that side's nudge loop
    once (then returns) — used when the caller already chose ``w/a/s/d``.
    """

    def _dpi() -> float:
        try:
            return float(fig.dpi)
        except Exception:
            return 72.0

    def _target(side: str):
        if axis_by_side and side in axis_by_side and axis_by_side[side] is not None:
            return axis_by_side[side]
        return ax

    def _px(target, attr: str) -> float:
        try:
            pts = float(getattr(target, attr, 0.0) or 0.0)
        except Exception:
            pts = 0.0
        return pts * _dpi() / 72.0

    def _nudge(target, attr: str, delta_px: float) -> None:
        try:
            current = float(getattr(target, attr, 0.0) or 0.0)
        except Exception:
            current = 0.0
        setattr(target, attr, current + float(delta_px) * 72.0 / _dpi())

    def _nudge_side(side: str) -> None:
        attr = _SIDE_PRIMARY_ATTR[side]
        target = _target(side)
        while True:
            print(f"  current: {_px(target, attr):+.2f} px")
            sub = safe_input(
                colorize_prompt("Nudge (w=+/s=- 5px, W=+/S=- 20px, 0=reset, q=back): ")
            ).strip()
            if not sub or sub.lower() == "q":
                break
            if sub == "0":
                push_state()
                setattr(target, attr, 0.0)
            elif sub == "w":
                push_state()
                _nudge(target, attr, 5.0)
            elif sub == "s":
                push_state()
                _nudge(target, attr, -5.0)
            elif sub == "W":
                push_state()
                _nudge(target, attr, 20.0)
            elif sub == "S":
                push_state()
                _nudge(target, attr, -20.0)
            else:
                print("Unknown nudge.")
                continue
            draw()

    side_set = {s.lower() for s in sides}
    if initial_side is not None:
        side = str(initial_side).strip().lower()
        if side in side_set and side in _SIDE_PRIMARY_ATTR:
            _nudge_side(side)
        else:
            print("Unknown side.")
        return

    while True:
        print("\nTitle offsets:")
        print("  w : top   | s : bottom | a : left | d : right")
        print("  q : back")
        side = safe_input(colorize_prompt("Side (w/a/s/d/q): ")).strip().lower()
        if not side or side == "q":
            break
        if side not in side_set or side not in _SIDE_PRIMARY_ATTR:
            print("Unknown side.")
            continue
        _nudge_side(side)


__all__ = [
    "TITLE_OFFSET_DEFAULTS",
    "capture_title_offsets",
    "reset_title_offsets",
    "restore_title_offsets",
    "run_title_offset_nudge_menu",
]

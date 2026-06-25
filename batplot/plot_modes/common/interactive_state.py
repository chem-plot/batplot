"""Shared helpers for interactive menu state bookkeeping.

The interactive menus still own their command loops. This module only centralizes
small, deterministic pieces that were duplicated across those loops: matplotlib's
side-to-tickparam mapping and WASD tick-state normalization.
"""

from __future__ import annotations

from typing import Dict, Mapping, Tuple


SIDES = ("top", "bottom", "left", "right")
_PREFIX_BY_SIDE = {
    "top": "t",
    "bottom": "b",
    "left": "l",
    "right": "r",
}


def x_tickparam_keys(side: str) -> Tuple[str, str]:
    """Return matplotlib tick/label keyword names for an x-axis side."""
    side = str(side).lower()
    if side == "top":
        return "tick2On", "label2On"
    if side == "bottom":
        return "tick1On", "label1On"
    raise ValueError(f"x-axis side must be 'top' or 'bottom', got {side!r}")


def y_tickparam_keys(side: str) -> Tuple[str, str]:
    """Return matplotlib tick/label keyword names for a y-axis side."""
    side = str(side).lower()
    if side == "left":
        return "tick1On", "label1On"
    if side == "right":
        return "tick2On", "label2On"
    raise ValueError(f"y-axis side must be 'left' or 'right', got {side!r}")


def _side_default(defaults: Mapping[str, bool] | None, side: str) -> bool:
    if defaults is None:
        return False
    return bool(defaults.get(side, False))


def build_saved_tick_state(
    wasd: Mapping[str, Mapping[str, object]] | None,
    *,
    tick_defaults: Mapping[str, bool] | None = None,
    label_defaults: Mapping[str, bool] | None = None,
    overrides: Mapping[str, bool] | None = None,
) -> Dict[str, bool]:
    """Build a flat ``_saved_tick_state`` dict from a WASD side-state dict.

    ``tick_defaults`` and ``label_defaults`` must match the defaults used in the
    surrounding ``tick_params`` calls. Passing those defaults explicitly keeps the
    stored state aligned with what is displayed, even when a saved session omits
    a side key.
    """
    wasd = wasd or {}
    out: Dict[str, bool] = {}
    for side in SIDES:
        prefix = _PREFIX_BY_SIDE[side]
        state = wasd.get(side, {}) or {}
        out[f"{prefix}_ticks"] = bool(
            state.get("ticks", _side_default(tick_defaults, side))
        )
        out[f"{prefix}_labels"] = bool(
            state.get("labels", _side_default(label_defaults, side))
        )
        minor_key = f"m{prefix}x" if prefix in ("t", "b") else f"m{prefix}y"
        out[minor_key] = bool(state.get("minor", False))
    if overrides:
        for key, value in overrides.items():
            out[str(key)] = bool(value)
    return out


def right_y_major_visibility(ax, *, default: Tuple[bool, bool] = (True, True)) -> Tuple[bool, bool]:
    """Return actual displayed right-side major tick and label visibility."""
    try:
        major_ticks = ax.yaxis.get_major_ticks()
        if not major_ticks:
            return bool(default[0]), bool(default[1])
        ticks_on = any(
            getattr(tick, "tick2line", None) is not None
            and tick.tick2line.get_visible()
            for tick in major_ticks
        )
        labels_on = any(
            getattr(tick, "label2", None) is not None
            and tick.label2.get_visible()
            for tick in major_ticks
        )
        return bool(ticks_on), bool(labels_on)
    except Exception:
        return bool(default[0]), bool(default[1])

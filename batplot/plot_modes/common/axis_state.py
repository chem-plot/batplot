"""Shared axis state capture helpers for styles and sessions."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


_SIDE_PREFIX = {'top': 't', 'bottom': 'b', 'left': 'l', 'right': 'r'}
_LEGACY_TICK_KEY = {'top': 'tx', 'bottom': 'bx', 'left': 'ly', 'right': 'ry'}


def _actual_major_visibility(axis: Any, side: str) -> tuple[bool | None, bool | None]:
    try:
        if side in ('top', 'bottom'):
            ticks = axis.xaxis.get_major_ticks()
            if not ticks:
                return None, None
            tick = ticks[0]
            line = tick.tick2line if side == 'top' else tick.tick1line
            label = tick.label2 if side == 'top' else tick.label1
        else:
            ticks = axis.yaxis.get_major_ticks()
            if not ticks:
                return None, None
            tick = ticks[0]
            line = tick.tick2line if side == 'right' else tick.tick1line
            label = tick.label2 if side == 'right' else tick.label1
        return bool(line.get_visible()), bool(label.get_visible())
    except Exception:
        return None, None


def _ylabel_on_right(axis: Any) -> bool:
    try:
        return axis.yaxis.get_label_position() == 'right'
    except Exception:
        return False


def _default_major_state(side: str, *, ylabel_on_right: bool) -> bool:
    return side == 'bottom' or (side == 'left' and not ylabel_on_right) or (side == 'right' and ylabel_on_right)


def _title_state(axis: Any, side: str, *, use_right_ylabel_position: bool) -> bool:
    ylabel_on_right = _ylabel_on_right(axis) if use_right_ylabel_position else False
    if side == 'left':
        if ylabel_on_right:
            return False
        if use_right_ylabel_position:
            return bool(axis.get_ylabel())
        return bool(axis.yaxis.label.get_visible())
    if side == 'bottom':
        if use_right_ylabel_position:
            return bool(axis.get_xlabel())
        return bool(axis.xaxis.label.get_visible())
    if side == 'top':
        return bool(getattr(axis, '_top_xlabel_on', False))
    if side == 'right':
        if ylabel_on_right:
            return bool(axis.get_ylabel())
        return bool(getattr(axis, '_right_ylabel_on', False))
    return False


def capture_axis_wasd_state(
    axis: Any,
    *,
    tick_state: dict[str, Any] | None = None,
    use_actual_major_visibility: bool = False,
    use_right_ylabel_position: bool = False,
) -> dict[str, dict[str, bool]]:
    """Capture WASD-style spine/tick/title state without changing schema keys."""
    state: dict[str, Any] = tick_state if tick_state is not None else (getattr(axis, '_saved_tick_state', None) or {})
    ylabel_on_right = _ylabel_on_right(axis) if use_right_ylabel_position else False
    wasd: dict[str, dict[str, bool]] = {}
    for side in ('top', 'bottom', 'left', 'right'):
        spine = axis.spines.get(side)
        prefix = _SIDE_PREFIX[side]
        default_on = _default_major_state(side, ylabel_on_right=ylabel_on_right)
        actual_ticks, actual_labels = (
            _actual_major_visibility(axis, side) if use_actual_major_visibility else (None, None)
        )
        ticks = state.get(
            f'{prefix}_ticks',
            state.get(_LEGACY_TICK_KEY[side], default_on),
        )
        labels = state.get(
            f'{prefix}_labels',
            state.get(_LEGACY_TICK_KEY[side], default_on),
        )
        wasd[side] = {
            'spine': bool(spine.get_visible() if spine else False),
            'ticks': bool(ticks if actual_ticks is None else actual_ticks),
            'minor': bool(state.get(f'm{prefix}x' if side in ('top', 'bottom') else f'm{prefix}y', False)),
            'labels': bool(labels if actual_labels is None else actual_labels),
            'title': _title_state(axis, side, use_right_ylabel_position=use_right_ylabel_position),
        }
    return wasd


def capture_axis_spines_and_tick_widths(
    axis: Any,
    tick_width: Callable[[Any, str], Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Capture existing session/style spine and tick-width dictionaries."""
    spines: dict[str, dict[str, Any]] = {}
    for name in ('bottom', 'top', 'left', 'right'):
        spine = axis.spines.get(name)
        if spine:
            spines[name] = {
                'linewidth': float(spine.get_linewidth()),
                'visible': bool(spine.get_visible()),
                'color': spine.get_edgecolor(),
            }
    ticks = {
        'x_major': tick_width(axis.xaxis, 'major'),
        'x_minor': tick_width(axis.xaxis, 'minor'),
        'y_major': tick_width(axis.yaxis, 'major'),
        'y_minor': tick_width(axis.yaxis, 'minor'),
    }
    return spines, ticks


__all__ = [
    "capture_axis_spines_and_tick_widths",
    "capture_axis_wasd_state",
]

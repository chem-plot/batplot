"""Shared helpers for manual axis-title offset attributes."""

from __future__ import annotations

from collections.abc import Mapping
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


__all__ = [
    "TITLE_OFFSET_DEFAULTS",
    "capture_title_offsets",
    "reset_title_offsets",
    "restore_title_offsets",
]

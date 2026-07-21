"""Shared state capture helpers for style export, session dump, and undo.

Phase-2 unification layer: small utilities reused across modes so p/i/s/b
paths share validation and serialization conventions without changing on-disk
pickle schemas.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any


def ro_states_compatible(cfg: dict, fig: Any, *, mode_label: str = "style/geometry") -> bool:
    """Return True when style/geometry ``ro_active`` matches the current figure."""
    file_ro = bool(cfg.get("ro_active", False))
    current_ro = bool(getattr(fig, "_ro_active", False))
    if file_ro == current_ro:
        return True
    if file_ro:
        print(
            f"Warning: {mode_label} file was saved with --ro (swapped x/y axes); "
            "current plot is not using --ro."
        )
    else:
        print(
            f"Warning: {mode_label} file was saved without --ro; "
            "current plot was created with --ro."
        )
    print(f"Not applying {mode_label} to avoid corrupting axis orientation.")
    return False


def ro_states_compatible_xy(cfg: dict, fig: Any) -> bool:
    """XY-specific ro_active guard (wording matches historical XY messages)."""
    file_ro = bool(cfg.get("ro_active", False))
    current_ro = bool(getattr(fig, "_ro_active", False))
    if file_ro == current_ro:
        return True
    if file_ro:
        print(
            "Warning: Style/geometry file was saved with --ro (swapped x/y axes); "
            "current plot is not using --ro."
        )
    else:
        print(
            "Warning: Style/geometry file was saved without --ro; "
            "current plot was created with --ro."
        )
    print("Not applying style/geometry to avoid corrupting axis orientation.")
    return False


def write_temp_json_snapshot(cfg: dict, *, suffix: str = ".json") -> str:
    """Write a style snapshot dict to a temp file; caller must delete the path."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh)
    return path


def remove_temp_snapshot(path: str | None) -> None:
    if not path:
        return
    try:
        os.unlink(path)
    except OSError:
        pass


def load_json_snapshot(path: str) -> dict | None:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return payload if isinstance(payload, dict) else None
    except Exception:
        return None


def as_style_geom_export(snap: dict, *, kind: str, geometry: dict) -> dict:
    """Attach export kind and geometry block for batch undo / style+geometry capture."""
    out = dict(snap)
    out["kind"] = kind
    out["geometry"] = geometry
    return out


__all__ = [
    "as_style_geom_export",
    "load_json_snapshot",
    "remove_temp_snapshot",
    "ro_states_compatible",
    "ro_states_compatible_xy",
    "write_temp_json_snapshot",
]

"""Cross-mode helpers: session saves must keep untrimmed source arrays.

Display crops / filters / clim / view limits must never be the only copy of
curve or image data in a ``.pkl``. Each mode dump path should call these
helpers (or equivalent) so expand-after-reload always has a backup.
"""

from __future__ import annotations

from typing import Any, Tuple

import numpy as np


def as_float1d(arr: Any) -> np.ndarray:
    return np.asarray(arr, dtype=float).reshape(-1)


def longest_xy_pair(
    *candidates: Tuple[Any, Any],
) -> Tuple[np.ndarray, np.ndarray]:
    """Return the longest finite-length (x, y) pair among candidates."""
    best_x = np.array([], dtype=float)
    best_y = np.array([], dtype=float)
    best_n = -1
    for pair in candidates:
        if not pair or len(pair) != 2:
            continue
        try:
            x = as_float1d(pair[0])
            y = as_float1d(pair[1])
        except Exception:
            continue
        n = int(min(x.size, y.size))
        if n > best_n:
            best_n = n
            best_x = np.array(x[:n], copy=True)
            best_y = np.array(y[:n], copy=True)
    return best_x, best_y


def line_display_and_full_xy(ln: Any) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Display (x,y) plus longest full backup from line attrs / current data.

    Prefers ``_original_xdata`` / ``_original_ydata`` when longer than the
    live artist arrays (spike filters, smoothing). Also bootstraps originals
    onto the line when missing so later filters cannot destroy the only copy.
    """
    try:
        x = as_float1d(ln.get_xdata())
        y = as_float1d(ln.get_ydata())
    except Exception:
        x = np.array([], dtype=float)
        y = np.array([], dtype=float)
    n = int(min(x.size, y.size))
    x_disp = np.array(x[:n], copy=True)
    y_disp = np.array(y[:n], copy=True)

    ox = getattr(ln, "_original_xdata", None)
    oy = getattr(ln, "_original_ydata", None)
    x_full, y_full = longest_xy_pair((x_disp, y_disp), (ox, oy))

    # Ensure the live artist always keeps a non-shrinking original backup.
    try:
        cur_ox = getattr(ln, "_original_xdata", None)
        cur_oy = getattr(ln, "_original_ydata", None)
        cur_n = 0
        if cur_ox is not None and cur_oy is not None:
            cur_n = int(min(as_float1d(cur_ox).size, as_float1d(cur_oy).size))
        if x_full.size > cur_n:
            ln._original_xdata = np.array(x_full, copy=True)
            ln._original_ydata = np.array(y_full, copy=True)
    except Exception:
        pass
    return x_disp, y_disp, x_full, y_full


def never_shrink_array(current: Any, incoming: Any) -> np.ndarray:
    """Keep the larger ndarray (by size) between current backup and incoming."""
    try:
        inc = np.array(incoming, copy=True)
    except Exception:
        inc = np.asarray([], dtype=float)
    try:
        cur = np.asarray(current)
    except Exception:
        cur = np.asarray([])
    if getattr(cur, "size", 0) > getattr(inc, "size", 0):
        return np.array(cur, copy=True)
    return inc


def install_operando_array_master(fig: Any, data: Any) -> np.ndarray:
    """Store / upgrade fig-level operando Z master (never shrink)."""
    master = never_shrink_array(getattr(fig, "_operando_array_master", None), data)
    try:
        fig._operando_array_master = master
    except Exception:
        pass
    return master


def install_cpc_series_master(fig: Any, role: str, x: Any, y: Any) -> Tuple[np.ndarray, np.ndarray]:
    """Store / upgrade CPC scatter master for ``role`` (never shrink)."""
    key_x = f"_cpc_master_x_{role}"
    key_y = f"_cpc_master_y_{role}"
    cur_x = getattr(fig, key_x, None)
    cur_y = getattr(fig, key_y, None)
    x_full, y_full = longest_xy_pair((cur_x, cur_y), (x, y))
    try:
        setattr(fig, key_x, x_full)
        setattr(fig, key_y, y_full)
    except Exception:
        pass
    return x_full, y_full


def install_scatter_xy_master(sc: Any, x: Any, y: Any) -> Tuple[np.ndarray, np.ndarray]:
    """Never-shrink XY master on a PathCollection (per-file CPC safe)."""
    cur_x = cur_y = None
    try:
        cur = getattr(sc, "_cpc_master_offsets", None)
        if cur is not None:
            arr = np.asarray(cur, dtype=float)
            if arr.ndim == 2 and arr.shape[1] >= 2 and arr.shape[0] > 0:
                cur_x, cur_y = arr[:, 0], arr[:, 1]
    except Exception:
        cur_x = cur_y = None
    x_full, y_full = longest_xy_pair((cur_x, cur_y), (x, y))
    try:
        if x_full.size and y_full.size:
            sc._cpc_master_offsets = np.column_stack([x_full, y_full])
    except Exception:
        pass
    return x_full, y_full


def style_payload_forbids_data_arrays(payload: Any, *, banned_keys: Tuple[str, ...] = ()) -> list:
    """Return list of forbidden data-bearing keys found in a style export.

    Used by tests / guards so ``p`` cannot smuggle session arrays.
    """
    if not isinstance(payload, dict):
        return ["<not a dict>"]
    default_banned = (
        "x_data",
        "y_data",
        "x_full_data",
        "master_x_full_data",
        "raw_y_full_data",
        "array",
        "array_master",
        "Z",
        "source_file_data",
        "values",
        "values_master",
        "ions_abs",
        "offsets",
        "efficiency_offsets",
        "x_full",
        "y_full",
        "original_xdata",
        "original_ydata",
    )
    banned = set(default_banned) | set(banned_keys)
    hits: list = []

    def _walk(obj: Any, path: str) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                p = f"{path}.{k}" if path else str(k)
                if k in banned:
                    hits.append(p)
                # Histo style must not embed setup column data
                if k == "setup" and isinstance(v, dict) and (
                    "values" in v or "values_master" in v
                ):
                    hits.append(p)
                _walk(v, p)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _walk(v, f"{path}[{i}]")

    _walk(payload, "")
    return hits


__all__ = [
    "as_float1d",
    "install_cpc_series_master",
    "install_operando_array_master",
    "install_scatter_xy_master",
    "line_display_and_full_xy",
    "longest_xy_pair",
    "never_shrink_array",
    "style_payload_forbids_data_arrays",
]

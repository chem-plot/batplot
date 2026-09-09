"""Cumulative (throughput) capacity transform for GC plots (``--gc --cum``).

Per-cycle GC resets each charge/discharge half-cycle near 0. Cumulative mode
lays those half-cycles end-to-end on the capacity axis so the curve runs
continuously from the start to the end of the experiment.
"""

from __future__ import annotations

from typing import Any, Optional, Tuple

import numpy as np

_SPEC = r"Specific Capacity (mAh g$^{-1}$)"
_CUM_SPEC = r"Cumulative Specific Capacity (mAh g$^{-1}$)"
_ABS = r"Capacity (mAh)"
_CUM_ABS = r"Cumulative Capacity (mAh)"


def make_cumulative_capacity(
    cap_x: np.ndarray,
    charge_mask: np.ndarray,
    discharge_mask: np.ndarray,
) -> np.ndarray:
    """Return capacity with half-cycle segments laid end-to-end.

    Contiguous charge and discharge runs (in time order) are shifted so each
    segment continues from the end of the previous one. Points outside both
    masks are left as NaN (they are not plotted by GC).
    """
    cap = np.asarray(cap_x, dtype=float)
    chg = np.asarray(charge_mask, dtype=bool)
    dch = np.asarray(discharge_mask, dtype=bool)
    n = int(cap.size)
    out = np.full(n, np.nan, dtype=float)
    if n == 0:
        return out
    if chg.shape != cap.shape:
        chg = np.resize(chg, cap.shape).astype(bool)
    if dch.shape != cap.shape:
        dch = np.resize(dch, cap.shape).astype(bool)

    active = chg | dch
    offset = 0.0
    i = 0
    while i < n:
        if not active[i]:
            i += 1
            continue
        is_chg = bool(chg[i])
        j = i + 1
        while j < n and active[j] and bool(chg[j]) == is_chg:
            j += 1
        seg = cap[i:j]
        finite = np.isfinite(seg)
        if np.any(finite):
            first = int(np.flatnonzero(finite)[0])
            base = float(seg[first])
            # Absolute progress so both rising (0→Q) and falling (Q→0)
            # half-cycles advance the cumulative axis forward.
            local = np.abs(seg - base)
            out[i:j] = offset + local
            loc_f = local[finite]
            step = float(np.nanmax(loc_f)) if loc_f.size else 0.0
            if not np.isfinite(step) or step < 0:
                step = 0.0
            offset += step
        i = j
    return out


def cumulative_capacity_xlabel(base_label: Optional[str]) -> str:
    """Map a per-cycle capacity xlabel to its cumulative counterpart."""
    lab = (base_label or "").strip()
    if not lab:
        return _CUM_SPEC
    if "cumulative" in lab.lower():
        return lab
    if "Specific Capacity" in lab or "mAh g" in lab:
        return _CUM_SPEC
    if lab in (_ABS, "Capacity (mAh)") or (
        "Capacity" in lab and "mAh" in lab and "g" not in lab
    ):
        return _CUM_ABS
    if lab.startswith("Cumulative "):
        return lab
    return f"Cumulative {lab}"


def apply_gc_capacity_mode(
    args: Any,
    cap_x: np.ndarray,
    charge_mask: np.ndarray,
    discharge_mask: np.ndarray,
    x_label: str,
) -> Tuple[np.ndarray, str, bool]:
    """If ``args.cum``, return cumulative capacity + xlabel; else passthrough."""
    if not bool(getattr(args, "cum", False)):
        return cap_x, x_label, False
    cum = make_cumulative_capacity(cap_x, charge_mask, discharge_mask)
    return cum, cumulative_capacity_xlabel(x_label), True


def stamp_gc_capacity_mode(fig: Any, *, cumulative: bool) -> None:
    """Store mode on the figure for session/style / overview."""
    try:
        fig._gc_capacity_mode = "cumulative" if cumulative else "per_cycle"
    except Exception:
        pass


__all__ = [
    "apply_gc_capacity_mode",
    "cumulative_capacity_xlabel",
    "make_cumulative_capacity",
    "stamp_gc_capacity_mode",
]

"""Helpers for batch editing of standalone dQ/dV 2D contour sessions."""

from __future__ import annotations

import os
import pickle
from typing import List, Optional, Sequence, Tuple

from ..electrochem.dqdv_2d import (
    build_dqdv_2d_snapshot,
    update_dqdv_2d_potential_window,
)
from .load import OperandoPanel


def save_dqdv_2d_panel(panel: OperandoPanel, path: str) -> None:
    """Persist a contour panel as ``kind=dqdv_2d_contour`` (never operando_ec)."""
    fig, ax, im, cbar = panel.fig, panel.ax, panel.im, panel.cbar
    try:
        v_lo = float(fig._dqdv_2d_v_lo)
        v_hi = float(fig._dqdv_2d_v_hi)
    except Exception as exc:
        raise RuntimeError(f"Contour panel missing potential window: {exc}") from exc
    row_labels = [str(s) for s in (getattr(fig, "_dqdv_2d_row_labels", None) or [])]
    zlab = str(getattr(fig, "_dqdv_2d_zlabel", "dQ/dV"))
    snap = build_dqdv_2d_snapshot(fig, ax, im, v_lo, v_hi, row_labels, zlab, cbar)
    if not isinstance(snap, dict):
        raise RuntimeError("Failed to build dQ/dV 2D contour snapshot")
    # Preserve overwrite-figure path when present (same as other modes' dumps).
    try:
        from ..common.session_helpers import capture_last_figure_export_path

        last = capture_last_figure_export_path(fig)
        if last:
            snap["last_figure_export_path"] = last
    except Exception:
        pass
    with open(path, "wb") as fh:
        pickle.dump(snap, fh, protocol=pickle.HIGHEST_PROTOCOL)
    try:
        fig._last_session_save_path = os.path.abspath(path)
    except Exception:
        pass


def panel_potential_window(panel: OperandoPanel) -> Optional[Tuple[float, float]]:
    try:
        return (
            float(panel.fig._dqdv_2d_v_lo),
            float(panel.fig._dqdv_2d_v_hi),
        )
    except Exception:
        return None


def sync_potential_window_all(
    panels: Sequence[OperandoPanel],
    v_lo: float,
    v_hi: float,
) -> int:
    """Rebuild butterfly maps on every panel that still has source dQ/dV data.

    Returns the number of panels successfully updated.
    """
    n_ok = 0
    for panel in panels:
        try:
            if update_dqdv_2d_potential_window(panel.fig, panel.ax, panel.im, v_lo, v_hi):
                n_ok += 1
        except Exception:
            pass
    return n_ok


def any_panel_has_dqdv_source(panels: Sequence[OperandoPanel]) -> bool:
    return any(bool(getattr(p.fig, "_dqdv_2d_file_data", None)) for p in panels)


def first_panel_with_dqdv_source(
    panels: Sequence[OperandoPanel],
) -> Optional[OperandoPanel]:
    """Prefer the first panel that can rebuild its butterfly map from source."""
    for panel in panels:
        if getattr(panel.fig, "_dqdv_2d_file_data", None):
            return panel
    return None


__all__ = [
    "any_panel_has_dqdv_source",
    "first_panel_with_dqdv_source",
    "panel_potential_window",
    "save_dqdv_2d_panel",
    "sync_potential_window_all",
]

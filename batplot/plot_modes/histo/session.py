"""Histogram session save/load."""

from __future__ import annotations

import os
import pickle
from typing import Any, Tuple

from .interactive import _apply_state, _restore_snapshot, _save_session, _snapshot_state
from .plot import HistoState, create_histo_figure
from .spines import apply_histo_spine_snapshot, reapply_histo_spine_layout


def load_histo_session(path: str) -> Tuple[Any, Any, HistoState] | None:
    """Load a histogram ``.pkl`` session. Returns ``(fig, ax, state)``."""
    try:
        with open(path, "rb") as fh:
            payload = pickle.load(fh)
    except Exception as exc:
        print(f"Failed to load histogram session: {exc}")
        return None
    if not isinstance(payload, dict) or payload.get("kind") != "histo":
        return None
    try:
        snap = payload["state"]
        state = _restore_snapshot(snap)
        fig, ax, _meta = create_histo_figure(state)
        apply_histo_spine_snapshot(fig, ax, snap)
        reapply_histo_spine_layout(fig, ax, state)
        fig._last_session_save_path = os.path.abspath(path)  # type: ignore[attr-defined]
        fig._bp_histo_state = state  # type: ignore[attr-defined]
        return fig, ax, state
    except Exception as exc:
        print(f"Histogram session restore failed: {exc}")
        return None


def save_histo_session(fig, ax, state: HistoState, path: str) -> None:
    _save_session(fig, ax, state, path)


def capture_histo_snapshot(state: HistoState, fig=None, ax=None) -> dict:
    return _snapshot_state(state, fig, ax)


def restore_histo_snapshot(state: HistoState, snap: dict) -> HistoState:
    return _restore_snapshot(snap)


def apply_histo_snapshot(fig, ax, state: HistoState, snap: dict) -> None:
    restored = _restore_snapshot(snap)
    _apply_state(fig, ax, state, restored, snap=snap)


__all__ = [
    "apply_histo_snapshot",
    "capture_histo_snapshot",
    "load_histo_session",
    "restore_histo_snapshot",
    "save_histo_session",
]

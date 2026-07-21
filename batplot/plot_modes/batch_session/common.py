"""Shared helpers for batch session interactive menus."""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Callable, List, Optional, Sequence

from ..common.terminal import imk_stderr_guard
from .kinds import kind_label


class SyncUndoStacks:
    """Synchronized per-panel undo stacks (batch edits push/pop together)."""

    def __init__(self, n_panels: int) -> None:
        self._stacks: List[List[Any]] = [[] for _ in range(n_panels)]

    def push_all(self, snapshots: List[Any]) -> None:
        for i, snap in enumerate(snapshots):
            self._stacks[i].append(snap)
            if len(self._stacks[i]) > 40:
                self._stacks[i].pop(0)

    def push_indices(self, indices: List[int], snapshots: List[Any]) -> None:
        for i, snap in zip(indices, snapshots):
            if 0 <= i < len(self._stacks):
                self._stacks[i].append(snap)
                if len(self._stacks[i]) > 40:
                    self._stacks[i].pop(0)

    def can_undo(self) -> bool:
        """True when at least one panel has more than the baseline snapshot (index 0)."""
        return any(len(s) > 1 for s in self._stacks)

    def undo_all(self, restore_fn: Callable[[int, Any], None]) -> bool:
        if not self.can_undo():
            print("No undo history.")
            return False
        restored = 0
        for i, stack in enumerate(self._stacks):
            if len(stack) <= 1:
                continue
            snap = stack.pop()
            try:
                restore_fn(i, snap)
                restored += 1
            except Exception as exc:
                print(f"Undo failed for panel {i + 1}: {exc}")
        if restored:
            print(f"Undo: restored {restored} panel(s).")
            return True
        print("Undo failed.")
        return False


def set_all_panel_figure_titles(panels: Sequence[Any]) -> None:
    for panel in panels:
        set_panel_figure_title(panel)


def draw_panels(panels: Sequence[Any], draw_attr: str = "fig", *, full_draw: bool = False) -> None:
    with imk_stderr_guard():
        for panel in panels:
            try:
                fig = getattr(panel, draw_attr, panel)
                if full_draw:
                    fig.canvas.draw()
                    try:
                        fig.canvas.flush_events()
                    except Exception:
                        pass
                else:
                    fig.canvas.draw_idle()
            except Exception:
                pass
    set_all_panel_figure_titles(panels)


def panel_basenames(panels: Sequence[Any]) -> List[str]:
    names = []
    for p in panels:
        path = getattr(p, "path", "")
        names.append(os.path.basename(path) if path else "?")
    return names


def session_figure_title(path: str) -> str:
    """Window title for a batch panel loaded from a session ``.pkl`` path."""
    return os.path.basename(path) if path else "?"


def set_panel_figure_title(panel: Any) -> None:
    """Set the matplotlib window title to the session ``.pkl`` filename (not Figure N)."""
    path = getattr(panel, "path", "")
    fig = getattr(panel, "fig", panel)
    title = session_figure_title(path)
    try:
        manager = getattr(getattr(fig, "canvas", None), "manager", None)
        if manager is not None and hasattr(manager, "set_window_title"):
            manager.set_window_title(title)
            return
    except Exception:
        pass
    try:
        fig.canvas.manager.set_window_title(title)  # type: ignore[attr-defined]
    except Exception:
        pass


def print_batch_header(kind: str, panels: Sequence[Any]) -> None:
    import sys

    label = kind_label(kind)
    names = panel_basenames(panels)
    print(f"\nBatch session mode: {label} ({len(panels)} plots)")
    for i, name in enumerate(names, 1):
        print(f"  [{i}] {name}")
    sys.stdout.flush()


def batch_quit_confirm(*, allow_export: bool = True) -> str | None:
    from .batch_commands import batch_quit_confirm as _batch_quit_confirm

    return _batch_quit_confirm(allow_export=allow_export)


def apply_style_json_to_all(
    panels: Sequence[Any],
    cfg: dict,
    apply_fn: Callable[[Any, dict], None],
) -> None:
    for panel in panels:
        apply_fn(panel, cfg)


def load_style_json(path: str) -> dict | None:
    if not os.path.isfile(path):
        print("File not found.")
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        print(f"Could not read style file: {exc}")
        return None


def write_temp_style_json(cfg: dict) -> str:
    from ..common.state_capture import write_temp_json_snapshot

    return write_temp_json_snapshot(cfg, suffix=".bpsg")


def remove_temp_file(path: str | None) -> None:
    from ..common.state_capture import remove_temp_snapshot

    remove_temp_snapshot(path)


__all__ = [
    "SyncUndoStacks",
    "apply_style_json_to_all",
    "batch_quit_confirm",
    "draw_panels",
    "load_style_json",
    "panel_basenames",
    "print_batch_header",
    "remove_temp_file",
    "session_figure_title",
    "set_all_panel_figure_titles",
    "set_panel_figure_title",
    "write_temp_style_json",
]

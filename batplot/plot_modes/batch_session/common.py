"""Shared helpers for batch session interactive menus."""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Callable, List, Optional

from ..common.terminal import colorize_prompt, safe_input
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
        return any(self._stacks)

    def undo_all(self, restore_fn: Callable[[int, Any], None]) -> bool:
        if not self.can_undo():
            print("No undo history.")
            return False
        restored = 0
        for i, stack in enumerate(self._stacks):
            if not stack:
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


def draw_panels(panels: List[Any], draw_attr: str = "fig") -> None:
    for panel in panels:
        try:
            fig = getattr(panel, draw_attr, panel)
            fig.canvas.draw_idle()
        except Exception:
            pass


def panel_basenames(panels: List[Any]) -> List[str]:
    names = []
    for p in panels:
        path = getattr(p, "path", "")
        names.append(os.path.basename(path) if path else "?")
    return names


def print_batch_header(kind: str, panels: List[Any]) -> None:
    label = kind_label(kind)
    names = panel_basenames(panels)
    print(f"\nBatch session mode: {label} ({len(panels)} plots)")
    for i, name in enumerate(names, 1):
        print(f"  [{i}] {name}")


def batch_quit_confirm(*, allow_export: bool = True) -> str | None:
    from .batch_commands import batch_quit_confirm as _batch_quit_confirm

    return _batch_quit_confirm(allow_export=allow_export)


def apply_style_json_to_all(
    panels: List[Any],
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
    fh = tempfile.NamedTemporaryFile(mode="w", suffix=".bpsg", delete=False, encoding="utf-8")
    try:
        json.dump(cfg, fh, indent=2)
        fh.close()
        return fh.name
    except Exception:
        fh.close()
        raise


def remove_temp_file(path: str | None) -> None:
    if not path:
        return
    try:
        os.unlink(path)
    except Exception:
        pass


__all__ = [
    "SyncUndoStacks",
    "apply_style_json_to_all",
    "batch_quit_confirm",
    "draw_panels",
    "load_style_json",
    "panel_basenames",
    "print_batch_header",
    "remove_temp_file",
    "write_temp_style_json",
]

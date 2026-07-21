"""Hide interactive crosshair overlays during figure export."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

_LINE_KEYS = ("hline", "vline")
_TEXT_KEYS = ("text", "coord_text", "value_text")
_PANEL_KEYS = ("panel", "value_panel", "status_panel", "coord_panel")


def register_crosshair(fig, state: dict[str, Any] | None) -> None:
    """Attach live crosshair state dict to *fig* for export-time suppression."""
    if state is None:
        try:
            delattr(fig, "_bp_crosshair")
        except Exception:
            pass
    else:
        fig._bp_crosshair = state  # type: ignore[attr-defined]


def _iter_crosshair_artists(state: dict[str, Any] | None) -> list[Any]:
    if not isinstance(state, dict) or not state.get("active"):
        return []
    artists: list[Any] = []
    for key in _LINE_KEYS + _TEXT_KEYS + _PANEL_KEYS:
        art = state.get(key)
        if art is not None:
            artists.append(art)
    extra = state.get("extra_artists")
    if extra:
        for art in extra:
            if art is not None:
                artists.append(art)
    return artists


def _toolbar_message_state(fig) -> tuple[Any | None, str | None]:
    """Return (toolbar_or_widget, previous_message) when available."""
    canvas = getattr(fig, "canvas", None)
    toolbar = getattr(canvas, "toolbar", None)
    if toolbar is None:
        return None, None
    try:
        if hasattr(toolbar, "set_message"):
            prev = str(getattr(toolbar, "_message", "") or "")
            try:
                message_label = getattr(toolbar, "message", None)
                if message_label is not None and hasattr(message_label, "get"):
                    prev = str(message_label.get() or "")
            except Exception:
                pass
            toolbar.set_message("")
            return toolbar, prev
    except Exception:
        pass
    return None, None


def _restore_toolbar_message(toolbar, previous: str | None) -> None:
    if toolbar is None or previous is None:
        return
    try:
        if hasattr(toolbar, "set_message"):
            toolbar.set_message(previous)
    except Exception:
        pass


@contextmanager
def suppress_crosshair_for_export(fig) -> Iterator[None]:
    """Temporarily hide crosshair artists (and toolbar coord readout) for savefig."""
    state = getattr(fig, "_bp_crosshair", None)
    hidden: list[tuple[Any, bool]] = []
    toolbar, toolbar_prev = _toolbar_message_state(fig)
    try:
        for art in _iter_crosshair_artists(state):
            try:
                hidden.append((art, bool(art.get_visible())))
                art.set_visible(False)
            except Exception:
                pass
        try:
            fig.canvas.draw()
        except Exception:
            try:
                fig.canvas.draw_idle()
            except Exception:
                pass
        yield
    finally:
        for art, was_visible in hidden:
            try:
                art.set_visible(was_visible)
            except Exception:
                pass
        _restore_toolbar_message(toolbar, toolbar_prev)
        try:
            fig.canvas.draw_idle()
        except Exception:
            pass


def savefig_without_crosshair(fig, path: str, **kwargs) -> None:
    """``fig.savefig`` wrapper that omits active crosshair overlays."""
    with suppress_crosshair_for_export(fig):
        fig.savefig(path, **kwargs)


__all__ = [
    "register_crosshair",
    "savefig_without_crosshair",
    "suppress_crosshair_for_export",
]

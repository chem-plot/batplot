"""Shared helpers for custom dash patterns on Line2D artists.

Matplotlib normalizes a custom dash tuple passed to ``set_linestyle`` (e.g.
``(0, (6, 3))``) into the named style ``'--'``, so ``get_linestyle()`` cannot
return the exact pattern. To keep custom dashes round-trippable through
print/import style (p/i), save/load sessions (s), and undo (b), the menus tag
the artist with a ``_bp_dash_pattern`` attribute whenever a custom dash is
applied, and the capture/restore code persists that tag alongside
``linestyle``. Old sessions/styles simply lack the field and behave as before.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Optional, Tuple

_DASH_ATTR = "_bp_dash_pattern"


def prompt_dash_pattern(safe_input: Callable[[str], str], kind: str = "dash") -> Optional[Tuple[float, ...]]:
    """Prompt for a dash (or dash-dot) on/off pattern.

    Returns the on/off sequence as a tuple of floats, or ``None`` when the
    user backs out (``q``) or enters an invalid pattern.
    """
    if kind == "dashdot":
        prompt = "Dash-dot pattern 'dash gap dot gap' (blank=6 3 1 3, q=back): "
        default: Tuple[float, ...] = (6.0, 3.0, 1.0, 3.0)
    else:
        prompt = "Dash pattern 'length gap' (blank=6 3, q=back): "
        default = (6.0, 3.0)
    raw = safe_input(prompt).strip().lower()
    if raw == "q":
        return None
    if not raw:
        return default
    tokens = [tok for tok in re.split(r"[,\s]+", raw) if tok]
    try:
        if kind == "dashdot":
            if len(tokens) == 2:
                dash = float(tokens[0])
                gap = float(tokens[1])
                dot = min(dash * 0.2, 2.0)
                return (dash, gap, dot, gap)
            if len(tokens) >= 4:
                return tuple(float(tokens[i]) for i in range(4))
        else:
            if len(tokens) == 1:
                val = float(tokens[0])
                return (val, val)
            if len(tokens) >= 2:
                return (float(tokens[0]), float(tokens[1]))
    except ValueError:
        print("Invalid dash pattern.")
        return None
    print("Invalid dash pattern.")
    return None


def set_dash_pattern(ln: Any, seq: Tuple[float, ...], offset: float = 0.0) -> None:
    """Apply a custom dash pattern to a line and tag it for persistence."""
    pattern = (float(offset), tuple(float(v) for v in seq))
    ln.set_linestyle(pattern)
    try:
        setattr(ln, _DASH_ATTR, pattern)
    except Exception:
        pass


def clear_dash_pattern(ln: Any) -> None:
    """Remove the custom-dash tag (call when applying solid/none/marker styles)."""
    try:
        if hasattr(ln, _DASH_ATTR):
            delattr(ln, _DASH_ATTR)
    except Exception:
        pass


def capture_dash_pattern(ln: Any):
    """Return the custom dash pattern in a JSON/pickle-safe list form, or None."""
    dp = getattr(ln, _DASH_ATTR, None)
    if not dp:
        return None
    try:
        return [float(dp[0]), [float(v) for v in dp[1]]]
    except Exception:
        return None


def restore_dash_pattern(ln: Any, dp: Any) -> None:
    """Re-apply a captured dash pattern (list or tuple form). No-op if falsy."""
    if not dp:
        return
    try:
        offset = float(dp[0])
        seq = tuple(float(v) for v in dp[1])
        if seq:
            ln.set_linestyle((offset, seq))
            setattr(ln, _DASH_ATTR, (offset, seq))
    except Exception:
        pass


__all__ = [
    "prompt_dash_pattern",
    "set_dash_pattern",
    "clear_dash_pattern",
    "capture_dash_pattern",
    "restore_dash_pattern",
]

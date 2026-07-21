"""Session kind detection for batch session mode."""

from __future__ import annotations

import pickle
from typing import Optional

KIND_LABELS = {
    "xy": "XY / 1D",
    "ec_gc": "EC (GC/CV/dQ/dV)",
    "cpc": "CPC / capacity per cycle",
    "operando_ec": "Operando + EC",
    "histo": "Histogram",
    "dqdv_2d_contour": "dQ/dV 2D contour",
}


def detect_session_kind(path: str) -> Optional[str]:
    """Return normalized session kind or None if unreadable."""
    try:
        with open(path, "rb") as fh:
            sess = pickle.load(fh)
        if not isinstance(sess, dict):
            return None
        kind = sess.get("kind")
        if kind == "ec_gc":
            return "ec_gc"
        if kind == "operando_ec":
            return "operando_ec"
        if kind == "cpc":
            return "cpc"
        if kind == "histo":
            return "histo"
        if kind == "dqdv_2d_contour":
            return "dqdv_2d_contour"
        if "version" in sess and "x_data" in sess:
            return "xy"
        return None
    except Exception as exc:
        print(f"  Could not read {path}: {exc}")
        return None


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, kind)


__all__ = ["KIND_LABELS", "detect_session_kind", "kind_label"]

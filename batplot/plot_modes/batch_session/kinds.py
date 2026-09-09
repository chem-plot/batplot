"""Session kind detection and batch panel compatibility profiles."""

from __future__ import annotations

import os
import pickle
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


KIND_LABELS = {
    "xy": "XY / 1D",
    "ec_gc": "EC (GC/CV/dQ/dV)",
    "cpc": "CPC / capacity per cycle",
    "operando_ec": "Operando + EC",
    "histo": "Histogram",
    "dqdv_2d_contour": "dQ/dV 2D contour",
}


@dataclass(frozen=True)
class BatchProfile:
    """Fingerprint for batch-panel compatibility (kind + layout subtype)."""

    kind: str
    subtype: Tuple[str, ...]
    label: str


def load_session_dict(path: str) -> Optional[dict]:
    """Load a session pickle header dict, or None if unreadable / not a dict."""
    try:
        with open(path, "rb") as fh:
            sess = pickle.load(fh)
        if not isinstance(sess, dict):
            return None
        return sess
    except Exception as exc:
        print(f"  Could not read {path}: {exc}")
        return None


def detect_session_kind_from_dict(sess: dict) -> Optional[str]:
    """Return normalized session kind from an already-loaded session dict."""
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


def detect_session_kind(path: str) -> Optional[str]:
    """Return normalized session kind or None if unreadable."""
    sess = load_session_dict(path)
    if sess is None:
        return None
    return detect_session_kind_from_dict(sess)


def kind_label(kind: str) -> str:
    return KIND_LABELS.get(kind, kind)


def _axis_label_text(sess: dict, which: str) -> str:
    axis = sess.get("axis") if isinstance(sess.get("axis"), dict) else {}
    labels = sess.get("axis_labels") if isinstance(sess.get("axis_labels"), dict) else {}
    raw = axis.get(which) if axis else None
    if raw is None and labels:
        raw = labels.get(which)
    return str(raw or "")


def _axis_looks_like_current(text: str) -> bool:
    """True for CV current axes — not Li/Li+ (which contains a bare ``i/``)."""
    t = (text or "").lower()
    if "current" in t:
        return True
    # I (mA), I/mA, I / mA — require word-boundary I, not the i in Li/Li+
    if re.search(r"(?<![a-z])i\s*\(\s*m?a", t):
        return True
    if re.search(r"(?<![a-z])i\s*/\s*m?a", t):
        return True
    return False


def _ec_plot_family(sess: dict) -> str:
    """Classify EC pickle as gc / cv / dqdv (all share kind=ec_gc)."""
    mode = sess.get("mode")
    if mode is True or mode == 1:
        return "dqdv"
    xlab = _axis_label_text(sess, "xlabel")
    ylab = _axis_label_text(sess, "ylabel")
    # CV: current on an axis (Potential vs Current). Do not treat Li/Li+ as current.
    if _axis_looks_like_current(xlab) or _axis_looks_like_current(ylab):
        return "cv"
    return "gc"


def _ec_file_layout(sess: dict) -> str:
    if bool(sess.get("multi_file")):
        return "multi-file"
    fd = sess.get("file_data")
    if isinstance(fd, list) and len(fd) > 1:
        return "multi-file"
    return "single-file"


def _xy_layout(sess: dict) -> str:
    args = sess.get("args_subset") if isinstance(sess.get("args_subset"), dict) else {}
    stack = bool(args.get("stack", False))
    right_y = sess.get("right_y_curve_indices") or []
    try:
        dual_y = len(list(right_y)) > 0
    except Exception:
        dual_y = False
    if dual_y and stack:
        return "stack+dual-y"
    if dual_y:
        return "dual-y"
    if stack:
        return "stack"
    return "overlay"


def _operando_layout(sess: dict) -> str:
    ec = sess.get("ec")
    if isinstance(ec, dict) and ec:
        return "with-ec-panel"
    return "operando-only"


def _cpc_layout(sess: dict) -> str:
    multi = sess.get("multi_files")
    n = len(multi) if isinstance(multi, list) else 0
    files = "multi-file" if n > 1 else "single-file"
    ro = "ro" if bool(sess.get("ro_active", False)) else "std"
    return f"{files}+{ro}"


def _histo_layout(sess: dict) -> str:
    # Histogram panels share one interactive surface; keep a stable subtype so
    # future layout forks can extend this without changing the call site.
    state = sess.get("state")
    if not isinstance(state, dict):
        return "histo"
    setup = state.get("setup")
    if isinstance(setup, dict):
        # Value column identity is data, not layout — do not fingerprint it.
        density = bool(setup.get("show_density") or setup.get("density"))
        return "histo+density" if density else "histo"
    return "histo"


_FAMILY_LABELS = {
    "gc": "GC",
    "cv": "CV",
    "dqdv": "dQ/dV",
}


def batch_profile_from_dict(sess: dict, kind: Optional[str] = None) -> Optional[BatchProfile]:
    """Build a batch compatibility profile from a session dict."""
    k = kind or detect_session_kind_from_dict(sess)
    if k is None:
        return None
    if k == "ec_gc":
        family = _ec_plot_family(sess)
        files = _ec_file_layout(sess)
        subtype = (family, files)
        label = f"EC {_FAMILY_LABELS.get(family, family)} ({files})"
        return BatchProfile(kind=k, subtype=subtype, label=label)
    if k == "xy":
        layout = _xy_layout(sess)
        return BatchProfile(kind=k, subtype=(layout,), label=f"XY ({layout})")
    if k == "operando_ec":
        layout = _operando_layout(sess)
        pretty = "operando + EC panel" if layout == "with-ec-panel" else "operando only (no EC panel)"
        return BatchProfile(kind=k, subtype=(layout,), label=pretty)
    if k == "cpc":
        layout = _cpc_layout(sess)
        files, ro = layout.split("+", 1)
        ro_txt = "rate-overlap on" if ro == "ro" else "standard"
        return BatchProfile(kind=k, subtype=(layout,), label=f"CPC ({files}, {ro_txt})")
    if k == "histo":
        layout = _histo_layout(sess)
        return BatchProfile(kind=k, subtype=(layout,), label="Histogram")
    if k == "dqdv_2d_contour":
        return BatchProfile(kind=k, subtype=("contour",), label="dQ/dV 2D contour")
    return BatchProfile(kind=k, subtype=("default",), label=kind_label(k))


def batch_profile_for_path(path: str) -> Optional[BatchProfile]:
    sess = load_session_dict(path)
    if sess is None:
        return None
    return batch_profile_from_dict(sess)


def validate_batch_profiles(
    paths: List[str],
) -> Tuple[Optional[str], Dict[str, BatchProfile], Optional[int]]:
    """Validate batch paths share the same kind **and** layout subtype.

    Returns ``(kind, path->profile, error_code)``.

    * Different top-level kinds → **Error** (exit 1), do not open.
    * Same kind, different subtype/layout → **Warning** (exit 1), do not open.
    """
    profiles: Dict[str, BatchProfile] = {}
    normalized: List[str] = []
    for path in paths:
        abspath = os.path.abspath(path)
        if not os.path.isfile(abspath):
            print(f"Session file not found: {path}")
            return None, profiles, 1
        if not abspath.lower().endswith(".pkl"):
            print("Batch session mode requires .pkl session files only.")
            return None, profiles, 1
        sess = load_session_dict(abspath)
        if sess is None:
            print(f"Not a valid batplot session: {path}")
            return None, profiles, 1
        kind = detect_session_kind_from_dict(sess)
        if kind is None:
            print(f"Not a valid batplot session: {path}")
            return None, profiles, 1
        profile = batch_profile_from_dict(sess, kind)
        if profile is None:
            print(f"Not a valid batplot session: {path}")
            return None, profiles, 1
        profiles[abspath] = profile
        normalized.append(abspath)

    kinds = {p.kind for p in profiles.values()}
    if len(kinds) != 1:
        print("\nError: All session files must be from the same plot mode.")
        for path in normalized:
            print(f"  {os.path.basename(path)}: {kind_label(profiles[path].kind)}")
        print(
            "\nBatplot cannot open a mixed batch. Edit same-mode sessions together, "
            "or use --canvas to combine different modes in one layout."
        )
        return None, profiles, 1

    kind = next(iter(kinds))
    subtypes = {p.subtype for p in profiles.values()}
    if len(subtypes) != 1:
        print(
            "\nWarning: Batch sessions must share the same data layout / subtype."
        )
        for path in normalized:
            print(f"  {os.path.basename(path)}: {profiles[path].label}")
        print(
            "\nBatplot will not open this batch. Use matching sessions "
            "(same mode and same layout — e.g. all GC multi-file, or all XY stack), "
            "open them individually, or use --canvas to combine different layouts."
        )
        return None, profiles, 1

    return kind, profiles, None


__all__ = [
    "BatchProfile",
    "KIND_LABELS",
    "batch_profile_for_path",
    "batch_profile_from_dict",
    "detect_session_kind",
    "detect_session_kind_from_dict",
    "kind_label",
    "load_session_dict",
    "validate_batch_profiles",
]

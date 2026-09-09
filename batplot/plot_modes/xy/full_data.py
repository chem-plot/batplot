"""Canonical untrimmed XY buffers so X-range crops never destroy session data.

Display arrays (``x_data`` / ``y_data``) may be sliced by the ``x`` menu.
``x_full_list`` / ``raw_y_full_list`` and ``fig._xy_master_*`` must keep the
full domain for expand / save / reload. Dump and load always prefer the
longest available backup (backward compatible with older ``.pkl`` files).
"""

from __future__ import annotations

import os
import re
from typing import Any, List, Optional, Sequence, Tuple

import numpy as np

_MASTER_X = "_xy_master_x_full"
_MASTER_Y = "_xy_master_y_full"

# "file.raw (λ=1.54000 Å)" / "file.xy (wl=0.71)" / bare "file.brml"
_LABEL_SOURCE_RE = re.compile(
    r"^(?P<path>.+?\.(?:raw|brml|xy|xye|dat|csv|txt|xrdml|rasx|qye|nor|gr))"
    r"(?:\s*\((?P<meta>[^)]*)\))?\s*$",
    re.IGNORECASE,
)
_WL_RE = re.compile(
    r"(?:λ|lambda|wl)\s*=\s*([0-9]*\.?[0-9]+)",
    re.IGNORECASE,
)


def as_float1d(arr: Any) -> np.ndarray:
    return np.asarray(arr, dtype=float).reshape(-1)


def copy_array_list(arrays: Sequence[Any] | None) -> List[np.ndarray]:
    if not arrays:
        return []
    return [np.array(as_float1d(a), copy=True) for a in arrays]


def _pair_len(x: Any, y: Any) -> int:
    try:
        nx = int(as_float1d(x).size)
        ny = int(as_float1d(y).size)
        return min(nx, ny) if nx and ny else 0
    except Exception:
        return 0


def install_master_full(
    fig: Any,
    x_full_list: Sequence[Any] | None,
    raw_y_full_list: Sequence[Any] | None,
    *,
    force: bool = False,
) -> None:
    """Store / upgrade fig-level master full buffers (never shrink unless force)."""
    if fig is None or not x_full_list or not raw_y_full_list:
        return
    n = min(len(x_full_list), len(raw_y_full_list))
    if n <= 0:
        return
    cur_x = list(getattr(fig, _MASTER_X, None) or [])
    cur_y = list(getattr(fig, _MASTER_Y, None) or [])
    out_x: List[np.ndarray] = []
    out_y: List[np.ndarray] = []
    for i in range(n):
        nx, ny = as_float1d(x_full_list[i]), as_float1d(raw_y_full_list[i])
        m = min(nx.size, ny.size)
        nx, ny = nx[:m].copy(), ny[:m].copy()
        if (not force) and i < len(cur_x) and i < len(cur_y):
            if _pair_len(cur_x[i], cur_y[i]) > m:
                out_x.append(as_float1d(cur_x[i]).copy())
                out_y.append(as_float1d(cur_y[i]).copy())
                continue
        out_x.append(nx)
        out_y.append(ny)
    # Keep any extra master curves if live list shrank (should not happen).
    if (not force) and len(cur_x) > n and len(cur_y) > n:
        out_x.extend(as_float1d(a).copy() for a in cur_x[n:])
        out_y.extend(as_float1d(a).copy() for a in cur_y[n:])
    try:
        setattr(fig, _MASTER_X, out_x)
        setattr(fig, _MASTER_Y, out_y)
    except Exception:
        pass


def get_master_full(fig: Any) -> Tuple[Optional[List[np.ndarray]], Optional[List[np.ndarray]]]:
    if fig is None:
        return None, None
    mx = getattr(fig, _MASTER_X, None)
    my = getattr(fig, _MASTER_Y, None)
    if isinstance(mx, list) and isinstance(my, list) and mx and my:
        return copy_array_list(mx), copy_array_list(my)
    return None, None


def best_full_buffers(
    fig: Any,
    x_full_list: Sequence[Any] | None,
    raw_y_full_list: Sequence[Any] | None,
    x_data_list: Sequence[Any] | None = None,
    y_fallback_list: Sequence[Any] | None = None,
) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """Return the longest available per-curve full X/Y pair."""
    candidates: List[Tuple[str, Optional[Sequence[Any]], Optional[Sequence[Any]]]] = []
    mx, my = get_master_full(fig)
    candidates.append(("master", mx, my))
    if fig is not None:
        candidates.append(
            (
                "original",
                getattr(fig, "_original_x_data_list", None),
                getattr(fig, "_original_y_data_list", None),
            )
        )
        # full_processed can be a crop after smooth — only use if longer than live full
        candidates.append(
            (
                "processed",
                getattr(fig, "_full_processed_x_data_list", None),
                getattr(fig, "_full_processed_y_data_list", None),
            )
        )
    candidates.append(("live_full", x_full_list, raw_y_full_list))
    candidates.append(("display", x_data_list, y_fallback_list))

    n = 0
    for _name, xs, ys in candidates:
        if xs and ys:
            n = max(n, min(len(xs), len(ys)))
    if n <= 0:
        return [], []

    out_x: List[np.ndarray] = []
    out_y: List[np.ndarray] = []
    for i in range(n):
        best_x = np.array([], dtype=float)
        best_y = np.array([], dtype=float)
        best_n = 0
        for _name, xs, ys in candidates:
            if not xs or not ys or i >= len(xs) or i >= len(ys):
                continue
            ln = _pair_len(xs[i], ys[i])
            if ln > best_n:
                xa, ya = as_float1d(xs[i]), as_float1d(ys[i])
                best_x, best_y = xa[:ln].copy(), ya[:ln].copy()
                best_n = ln
        out_x.append(best_x)
        out_y.append(best_y)
    return out_x, out_y


def sync_live_full_lists(
    fig: Any,
    x_full_list: list,
    raw_y_full_list: list,
    *,
    x_data_list: Sequence[Any] | None = None,
    y_fallback_list: Sequence[Any] | None = None,
) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """Upgrade live full lists + master from the best available buffers."""
    best_x, best_y = best_full_buffers(
        fig, x_full_list, raw_y_full_list, x_data_list, y_fallback_list
    )
    if not best_x:
        return list(x_full_list or []), list(raw_y_full_list or [])
    # Mutate live lists in place when possible (interactive closures share refs).
    if isinstance(x_full_list, list) and isinstance(raw_y_full_list, list):
        x_full_list[:] = best_x
        raw_y_full_list[:] = best_y
    install_master_full(fig, best_x, best_y, force=True)
    return best_x, best_y


def upgrade_originals_from_full(fig: Any, x_full_list: Sequence[Any], raw_y_full_list: Sequence[Any]) -> None:
    """If ``_original_*`` is missing or shorter than full, refresh from full."""
    if fig is None or not x_full_list or not raw_y_full_list:
        return
    ox = getattr(fig, "_original_x_data_list", None)
    oy = getattr(fig, "_original_y_data_list", None)
    n = min(len(x_full_list), len(raw_y_full_list))
    need = ox is None or oy is None or len(ox) < n or len(oy) < n
    if not need and isinstance(ox, list) and isinstance(oy, list):
        for i in range(n):
            if _pair_len(x_full_list[i], raw_y_full_list[i]) > _pair_len(ox[i], oy[i]):
                need = True
                break
    if not need:
        return
    fig._original_x_data_list = copy_array_list(x_full_list[:n])
    fig._original_y_data_list = copy_array_list(raw_y_full_list[:n])


def parse_label_source(label: Any) -> Tuple[Optional[str], Optional[float]]:
    """Return ``(basename_or_path, wavelength_A_or_None)`` from a curve label."""
    text = str(label or "").strip()
    if not text:
        return None, None
    m = _LABEL_SOURCE_RE.match(text)
    if not m:
        if _looks_like_basename(text):
            return text, None
        return None, None
    path = m.group("path").strip()
    meta = m.group("meta") or ""
    wl = None
    wm = _WL_RE.search(meta)
    if wm:
        try:
            wl = float(wm.group(1))
        except ValueError:
            wl = None
    return path, wl


def _looks_like_basename(text: str) -> bool:
    low = text.lower()
    return any(
        low.endswith(ext)
        for ext in (
            ".raw", ".brml", ".xy", ".xye", ".dat", ".csv", ".txt",
            ".xrdml", ".rasx", ".qye", ".nor", ".gr",
        )
    )


def source_candidates_from_labels(labels: Sequence[Any] | None) -> List[str]:
    out: List[str] = []
    seen = set()
    for lab in labels or []:
        path, _wl = parse_label_source(lab)
        if not path:
            continue
        key = path.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def full_matches_display(
    x_full_list: Sequence[Any] | None,
    x_data_list: Sequence[Any] | None,
) -> bool:
    """True when every full buffer is no longer than the display crop."""
    if not x_full_list or not x_data_list:
        return False
    n = min(len(x_full_list), len(x_data_list))
    if n <= 0:
        return False
    for i in range(n):
        if as_float1d(x_full_list[i]).size > as_float1d(x_data_list[i]).size:
            return False
    return True


def _find_source_file(basename: str, roots: Sequence[str]) -> Optional[str]:
    found = _find_all_source_files(basename, roots, limit=1)
    return found[0] if found else None


def _find_all_source_files(
    basename: str, roots: Sequence[str], *, limit: int = 24
) -> List[str]:
    """Locate matching source files (absolute path first, then basename walk)."""
    out: List[str] = []
    seen: set[str] = set()

    def _add(path: str) -> None:
        try:
            ap = os.path.abspath(path)
        except Exception:
            return
        if ap in seen or not os.path.isfile(ap):
            return
        seen.add(ap)
        out.append(ap)

    base = os.path.basename(basename)
    for cand in (basename, os.path.abspath(basename) if basename else ""):
        if cand:
            _add(cand)
        if len(out) >= limit:
            return out
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        direct = os.path.join(root, base)
        _add(direct)
        if len(out) >= limit:
            return out
        try:
            for dirpath, _dirnames, filenames in os.walk(root):
                rel = os.path.relpath(dirpath, root)
                depth = 0 if rel == "." else rel.count(os.sep) + 1
                if depth > 6:
                    _dirnames[:] = []
                    continue
                if base in filenames:
                    _add(os.path.join(dirpath, base))
                    if len(out) >= limit:
                        return out
        except Exception:
            continue
    return out


def _load_xy_columns(fpath: str) -> Tuple[np.ndarray, np.ndarray, Optional[float]]:
    """Return ``(x, y, vendor_wl_or_None)`` from a XRD/XY source file."""
    from ...readers_xrd import is_bruker_raw, read_xrd_vendor_file, sanitize_xrd_intensity
    from ...readers_common import robust_loadtxt_skipheader

    ext = os.path.splitext(fpath)[1].lower()
    if ext in (".raw", ".brml") or (ext == ".raw" and is_bruker_raw(fpath)):
        x2t, y, _e, wl_file = read_xrd_vendor_file(fpath)
        y = sanitize_xrd_intensity(y)
        x2t = as_float1d(x2t)
        y = as_float1d(y)
        m = min(x2t.size, y.size)
        return x2t[:m], y[:m], (float(wl_file) if wl_file is not None else None)

    data = np.asarray(robust_loadtxt_skipheader(fpath), dtype=float)
    if data.ndim == 1:
        raise ValueError(f"Need ≥2 columns in {fpath}")
    if data.shape[1] < 2:
        raise ValueError(f"Need ≥2 columns in {fpath}")
    x = as_float1d(data[:, 0])
    y = as_float1d(data[:, 1])
    m = min(x.size, y.size)
    return x[:m], y[:m], None


def _2theta_to_Q(x2t: np.ndarray, wl: float) -> np.ndarray:
    theta = np.radians(as_float1d(x2t) / 2.0)
    return (4.0 * np.pi * np.sin(theta) / float(wl)).astype(float)


def _score_heal_candidate(
    x_disp: np.ndarray,
    y_disp: np.ndarray,
    x_cand: np.ndarray,
    y_cand: np.ndarray,
) -> float:
    """Correlation of candidate vs displayed curve on the display X grid (0..1 bad→good)."""
    xd = as_float1d(x_disp)
    yd = as_float1d(y_disp)
    xc = as_float1d(x_cand)
    yc = as_float1d(y_cand)
    if xd.size < 8 or xc.size < 8:
        return -1.0
    lo, hi = float(xd.min()), float(xd.max())
    mask = (xc >= lo - 1e-9) & (xc <= hi + 1e-9)
    if int(np.count_nonzero(mask)) < 8:
        return -1.0
    xs, ys = xc[mask], yc[mask]
    span = float(ys.max() - ys.min()) if ys.size else 0.0
    yn = (ys - ys.min()) / span if span > 0 else np.zeros_like(ys)
    y_ref = yd.copy()
    rspan = float(y_ref.max() - y_ref.min()) if y_ref.size else 0.0
    if rspan > 0:
        y_ref = (y_ref - y_ref.min()) / rspan
    try:
        yi = np.interp(xd, xs, yn)
        if not np.isfinite(yi).all() or float(np.std(yi)) < 1e-15:
            return -1.0
        c = float(np.corrcoef(y_ref, yi)[0, 1])
        return c if np.isfinite(c) else -1.0
    except Exception:
        return -1.0


def _domain_variants(
    x_raw: np.ndarray,
    y_raw: np.ndarray,
    *,
    mode: str,
    wavelengths: Sequence[Optional[float]],
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Build possible (x_domain, y) pairs for the session axis mode."""
    out: List[Tuple[np.ndarray, np.ndarray]] = []
    x_raw = as_float1d(x_raw)
    y_raw = as_float1d(y_raw)
    # Always try native X (already Q / 2θ / d)
    out.append((x_raw, y_raw))
    if mode in ("q", "2theta", "d"):
        for wl in wavelengths:
            if wl is None:
                continue
            try:
                wlf = float(wl)
            except (TypeError, ValueError):
                continue
            if wlf <= 0:
                continue
            try:
                if mode == "q":
                    # Treat file X as 2θ → Q
                    out.append((_2theta_to_Q(x_raw, wlf), y_raw))
                elif mode == "d":
                    # 2θ → d = λ / (2 sinθ)
                    th = np.radians(x_raw / 2.0)
                    s = np.sin(th)
                    with np.errstate(divide="ignore", invalid="ignore"):
                        d = np.where(np.abs(s) > 1e-15, wlf / (2.0 * s), np.nan)
                    ok = np.isfinite(d)
                    if np.count_nonzero(ok) > 8:
                        out.append((d[ok].astype(float), y_raw[ok]))
                # mode == "2theta": native already covered; Q-file→2θ is rare — skip
            except Exception:
                continue
    return out


def try_heal_full_from_label_sources(
    *,
    fig: Any,
    labels: Sequence[Any] | None,
    x_full_list: list,
    raw_y_full_list: list,
    axis_mode: Any = None,
    session_path: Any = None,
    source_files: Sequence[Any] | None = None,
    x_display_list: Sequence[Any] | None = None,
    y_display_list: Sequence[Any] | None = None,
    min_corr: float = 0.92,
) -> bool:
    """Reload untrimmed arrays from original files when the session lost them.

    Used for backward-compat repair of ``.pkl`` files whose ``x_full_data`` was
    incorrectly saved as the displayed crop. Supports Bruker ``.raw``/``.brml``
    and text XY (``.xy``/``.xye``/…). When several basename matches exist, pick
    the domain/λ variant that best correlates with the displayed curve.
    Returns True if any curve healed.
    """
    if not labels or not isinstance(x_full_list, list) or not isinstance(raw_y_full_list, list):
        return False
    roots: List[str] = []
    if session_path:
        try:
            sp = os.path.abspath(str(session_path))
            d = os.path.dirname(sp)
            # Session dir + one parent only (e.g. Figures/ + NFSO data/).
            # Do NOT walk grandparent (often a huge OneDrive tree).
            roots.extend([d, os.path.dirname(d)])
            # Common sibling data folders next to Figures/
            for sub in ("XRD", "Data", "data", "XY", "xy", "raw", "RAW"):
                roots.append(os.path.join(os.path.dirname(d), sub))
        except Exception:
            pass
    roots.append(os.getcwd())
    # Also search parent dirs of known absolute source paths (when they exist)
    for sf in source_files or []:
        try:
            if not sf:
                continue
            ap = os.path.abspath(str(sf))
            if os.path.isfile(ap):
                roots.append(os.path.dirname(ap))
            else:
                # Missing absolute path: still try its directory if present
                parent = os.path.dirname(ap)
                if os.path.isdir(parent):
                    roots.append(parent)
        except Exception:
            pass
    seen_r: set[str] = set()
    uniq_roots: List[str] = []
    for r in roots:
        try:
            ar = os.path.abspath(r)
        except Exception:
            continue
        if ar in seen_r or not os.path.isdir(ar):
            continue
        seen_r.add(ar)
        uniq_roots.append(ar)

    mode = str(axis_mode or getattr(fig, "_xy_axis_mode", "") or "").strip().lower()
    if mode.startswith("q"):
        mode = "q"
    elif mode in ("2theta", "2θ", "2th"):
        mode = "2theta"
    elif mode.startswith("d"):
        mode = "d"

    # Prefer fig / label λ, then common XRD wavelengths (order matters for ties).
    common_wls: List[Optional[float]] = []
    fig_wl = getattr(fig, "_xy_wavelength", None)
    if fig_wl is not None:
        try:
            common_wls.append(float(fig_wl))
        except (TypeError, ValueError):
            pass
    for w in (0.7093, 0.709, 1.5406, 1.54, 0.25448, 0.7107):
        if w not in common_wls:
            common_wls.append(w)

    healed = 0
    load_cache: dict[str, Tuple[np.ndarray, np.ndarray, Optional[float]]] = {}
    path_cache: dict[str, List[str]] = {}
    for i, lab in enumerate(labels):
        if i >= len(x_full_list):
            break
        src_name, wl_lab = parse_label_source(lab)
        # Prefer per-curve absolute source_files entry when present
        explicit = None
        if source_files and i < len(source_files) and source_files[i]:
            explicit = str(source_files[i])
        if not src_name and not explicit:
            continue

        cache_key = f"{explicit or ''}|{src_name or ''}"
        if cache_key in path_cache:
            uniq_paths = path_cache[cache_key]
        else:
            paths: List[str] = []
            if explicit:
                paths.extend(_find_all_source_files(explicit, uniq_roots, limit=8))
            if src_name:
                paths.extend(_find_all_source_files(src_name, uniq_roots, limit=24))
            seen_p: set[str] = set()
            uniq_paths = []
            for p in paths:
                if p in seen_p:
                    continue
                seen_p.add(p)
                uniq_paths.append(p)
            # Prefer folders that look like converted / wavelength-tagged data
            def _path_rank(p: str) -> tuple:
                pl = p.lower()
                return (
                    0 if "converted_0p709" in pl or "converted_0.709" in pl else 1,
                    0 if "converted" in pl else 1,
                    0 if "sorted" in pl else 1,
                    len(p),
                )
            uniq_paths.sort(key=_path_rank)
            path_cache[cache_key] = uniq_paths
        if not uniq_paths:
            continue

        if x_display_list is not None and i < len(x_display_list):
            x_disp = as_float1d(x_display_list[i])
        else:
            x_disp = as_float1d(x_full_list[i])
        if y_display_list is not None and i < len(y_display_list):
            y_disp = as_float1d(y_display_list[i])
        else:
            y_disp = as_float1d(raw_y_full_list[i]) if i < len(raw_y_full_list) else x_disp * 0

        wls: List[Optional[float]] = []
        if wl_lab is not None:
            wls.append(float(wl_lab))
        wls.extend(common_wls)

        best_score = -1.0
        best_x: Optional[np.ndarray] = None
        best_y: Optional[np.ndarray] = None
        cur_n = int(as_float1d(x_full_list[i]).size)
        for fpath in uniq_paths:
            try:
                if fpath not in load_cache:
                    load_cache[fpath] = _load_xy_columns(fpath)
                x_raw, y_raw, wl_file = load_cache[fpath]
            except Exception:
                continue
            wls_try = list(wls)
            if wl_file is not None and float(wl_file) not in wls_try:
                wls_try.insert(0, float(wl_file))
            for x_dom, y_dom in _domain_variants(x_raw, y_raw, mode=mode, wavelengths=wls_try):
                if as_float1d(x_dom).size <= cur_n:
                    continue
                sc = _score_heal_candidate(x_disp, y_disp, x_dom, y_dom)
                if sc > best_score:
                    best_score = sc
                    best_x = as_float1d(x_dom).copy()
                    best_y = as_float1d(y_dom).copy()
                    if best_score >= 0.999:
                        break
            if best_score >= 0.999:
                break

        if best_x is None or best_y is None:
            continue
        # Require a strong match when a display curve exists; otherwise accept longer only.
        need_corr = x_disp.size >= 8 and float(np.std(y_disp)) > 1e-15
        if need_corr and best_score < float(min_corr):
            continue
        if best_x.size <= cur_n:
            continue
        x_full_list[i] = best_x
        while len(raw_y_full_list) <= i:
            raw_y_full_list.append(np.array([], dtype=float))
        raw_y_full_list[i] = best_y
        healed += 1

    if healed:
        install_master_full(fig, x_full_list, raw_y_full_list, force=True)
        upgrade_originals_from_full(fig, x_full_list, raw_y_full_list)
        print(
            f"Restored full X/Y data for {healed} curve(s) from original source files "
            f"(session had only the displayed crop)."
        )
        return True
    return False


def ensure_full_covers_x_window(
    *,
    fig: Any,
    labels: Sequence[Any] | None,
    x_full_list: list,
    raw_y_full_list: list,
    new_min: float,
    new_max: float,
    axis_mode: Any = None,
    session_path: Any = None,
    source_files: Sequence[Any] | None = None,
    x_display_list: Sequence[Any] | None = None,
    y_display_list: Sequence[Any] | None = None,
) -> bool:
    """If full buffers cannot cover ``[new_min, new_max]``, try healing from sources."""
    if not x_full_list:
        return False
    try:
        lo = min(float(as_float1d(a).min()) for a in x_full_list if as_float1d(a).size)
        hi = max(float(as_float1d(a).max()) for a in x_full_list if as_float1d(a).size)
    except ValueError:
        return False
    if lo <= float(new_min) + 1e-12 and hi >= float(new_max) - 1e-12:
        return False
    # Prefer fig-stored source list / session path when caller omits them
    if source_files is None:
        source_files = getattr(fig, "_xy_source_files", None)
    if session_path is None:
        session_path = getattr(fig, "_last_session_save_path", None)
    return try_heal_full_from_label_sources(
        fig=fig,
        labels=labels,
        x_full_list=x_full_list,
        raw_y_full_list=raw_y_full_list,
        axis_mode=axis_mode or getattr(fig, "_xy_axis_mode", None),
        session_path=session_path,
        source_files=source_files,
        x_display_list=x_display_list,
        y_display_list=y_display_list,
    )


def warn_if_full_looks_cropped(
    x_full_list: Sequence[Any] | None,
    x_data_list: Sequence[Any] | None,
    *,
    norm_xlim: Any = None,
) -> None:
    if not full_matches_display(x_full_list, x_data_list):
        return
    tip = (
        "Warning: session full-data buffers match the displayed X crop. "
        "Expanding X later cannot recover points outside this window. "
        "Re-plot from the original data files if you need the full range."
    )
    try:
        if norm_xlim is not None and len(norm_xlim) == 2 and x_full_list:
            lo = min(float(as_float1d(a).min()) for a in x_full_list if as_float1d(a).size)
            hi = max(float(as_float1d(a).max()) for a in x_full_list if as_float1d(a).size)
            n0, n1 = float(norm_xlim[0]), float(norm_xlim[1])
            if n0 < lo - 1e-9 or n1 > hi + 1e-9:
                tip += f" (norm_xlim {n0:g}–{n1:g} is wider than saved full {lo:g}–{hi:g}.)"
    except Exception:
        pass
    print(tip)


__all__ = [
    "as_float1d",
    "best_full_buffers",
    "copy_array_list",
    "ensure_full_covers_x_window",
    "full_matches_display",
    "get_master_full",
    "install_master_full",
    "parse_label_source",
    "source_candidates_from_labels",
    "sync_live_full_lists",
    "try_heal_full_from_label_sources",
    "upgrade_originals_from_full",
    "warn_if_full_looks_cropped",
]

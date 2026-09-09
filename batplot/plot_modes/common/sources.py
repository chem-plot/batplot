"""Shared source-path normalization for interactive save/export menus."""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any, List


def normalize_source_paths(
    paths: Iterable[Any] | None,
    *,
    require_exists: bool = True,
    require_file: bool = False,
) -> List[str]:
    """Return absolute, unique paths while preserving input order."""
    out: List[str] = []
    seen = set()
    for path in paths or []:
        if not path:
            continue
        try:
            # expanduser first so ``~/data.xy`` works on Windows/macOS/Linux
            # (plain abspath leaves ``~`` as a literal path segment).
            abs_path = os.path.abspath(os.path.expanduser(str(path)))
        except Exception:
            continue
        if require_exists and not os.path.exists(abs_path):
            continue
        if require_file and not os.path.isfile(abs_path):
            continue
        if abs_path in seen:
            continue
        seen.add(abs_path)
        out.append(abs_path)
    return out


def split_path_token(token: Any) -> tuple[str, list[str]]:
    """Split a path token from trailing ``:suffix`` parts (``:wl``, ``:q``, …).

    Preserves Windows drive colons for both normal and extended-length paths:

    - ``C:\\dir\\file.cif:1.54``
    - ``\\\\?\\C:\\dir\\file.cif:1.54``
    - UNC ``\\\\server\\share\\file.cif:1.54`` (no drive colon to preserve)
    - POSIX ``/tmp/file.cif:1.54``

    Returns ``(path, rest_parts)`` where ``rest_parts`` are the suffix segments
    after the path (may be empty).
    """
    s = str(token)
    parts = s.split(":")
    if len(parts) <= 1:
        return s, []

    head = parts[0]
    # Normal drive letter: C:\...
    if len(head) == 1 and head.isalpha():
        return head + ":" + parts[1], parts[2:]

    # Extended-length DOS device path: \\?\C:\... or //?/C:/...
    # After split(':'), head is '\\?\C' or '//?/C' (length 5).
    if (
        len(head) == 5
        and head[4].isalpha()
        and (head.startswith("\\\\?\\") or head.startswith("//?/"))
    ):
        return head + ":" + parts[1], parts[2:]

    return parts[0], parts[1:]


def path_token_without_suffix(token: Any) -> str:
    """Strip ``:wl`` / ``:label`` from a path token; keep Windows drive letters."""
    path, _rest = split_path_token(token)
    return path


def cif_present(args_files: Iterable[Any] | None, series_getter: Any = None) -> bool:
    """Return True if any input file is a ``.cif`` or a CIF tick series exists.

    Supports the ``path:label`` / ``path:wl`` syntax. On Windows, drive letters
    (``C:\\...``) are preserved — do not treat the drive colon as a suffix.
    ``series_getter`` is an optional zero-arg callable returning the current CIF
    tick series (truthy when overlays exist).
    """
    try:
        if any(
            path_token_without_suffix(f).lower().endswith(".cif")
            for f in (args_files or [])
        ):
            return True
        if series_getter is not None:
            return bool(series_getter())
    except Exception:
        pass
    return False


_DATA_LIKE_EXTENSIONS = (
    ".xy", ".xye", ".dat", ".csv", ".txt", ".nor", ".gr", ".qye", ".cif",
    ".raw", ".brml", ".xrdml", ".rasx", ".mpt", ".pkl",
)


def _looks_like_data_path(value: object) -> bool:
    s = str(value or "").strip()
    if not s:
        return False
    low = s.lower()
    if os.path.sep in s or "/" in s or "\\" in s:
        return True
    return any(low.endswith(ext) for ext in _DATA_LIKE_EXTENSIONS)


def cif_paths_from_tick_series(cif_tick_series: Iterable[Any] | None) -> List[str]:
    """Extract CIF file paths from stored ``cif_tick_series`` tuples."""
    paths: List[str] = []
    for entry in cif_tick_series or []:
        if not entry:
            continue
        try:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                for idx in (1, 0):
                    candidate = entry[idx]
                    if candidate and str(candidate).lower().endswith(".cif"):
                        paths.append(str(candidate))
                        break
            elif isinstance(entry, dict):
                for key in ("filepath", "filename", "file", "path"):
                    candidate = entry.get(key)
                    if candidate and str(candidate).lower().endswith(".cif"):
                        paths.append(str(candidate))
                        break
        except Exception:
            continue
    return normalize_source_paths(paths, require_exists=False)


def resolve_xy_source_files(
    args: Any = None,
    *,
    labels: Iterable[Any] | None = None,
    cif_tick_series: Iterable[Any] | None = None,
    fig: Any = None,
    args_subset: dict[str, Any] | None = None,
    session: dict[str, Any] | None = None,
) -> List[str]:
    """Resolve original data file paths for XY interactive menus after pkl reload."""
    existing = getattr(args, "files", None) if args is not None else None
    if existing:
        return normalize_source_paths(existing, require_exists=False)

    candidates: List[Any] = []
    if args_subset:
        candidates.extend(args_subset.get("files") or [])
    if session:
        candidates.extend(session.get("source_files") or [])
        subset = session.get("args_subset") or {}
        candidates.extend(subset.get("files") or [])

    for lbl in labels or []:
        if _looks_like_data_path(lbl):
            candidates.append(lbl)
            continue
        # Curve labels often look like ``file.raw (λ=1.54 Å)``.
        try:
            from ..xy.full_data import parse_label_source

            path, _wl = parse_label_source(lbl)
            if path:
                candidates.append(path)
        except Exception:
            pass

    candidates.extend(cif_paths_from_tick_series(cif_tick_series))

    if fig is not None:
        for path in getattr(fig, "_bp_source_paths", []) or []:
            if path and not str(path).lower().endswith(".pkl"):
                candidates.append(path)

    return normalize_source_paths(candidates, require_exists=False)


def ensure_xy_args_files(
    args: Any,
    *,
    labels: Iterable[Any] | None = None,
    cif_tick_series: Iterable[Any] | None = None,
    fig: Any = None,
    args_subset: dict[str, Any] | None = None,
    session: dict[str, Any] | None = None,
) -> List[str]:
    """Ensure ``args.files`` exists (minimal Args from session reload)."""
    files = resolve_xy_source_files(
        args,
        labels=labels,
        cif_tick_series=cif_tick_series,
        fig=fig,
        args_subset=args_subset,
        session=session,
    )
    try:
        args.files = files
    except Exception:
        pass
    return files


def file_data_source_paths(file_data: Any) -> List[str]:
    """Extract filepath entries from a single file_data dict or list of dicts."""
    entries = file_data if isinstance(file_data, list) else [file_data]
    paths = [
        entry.get("filepath")
        for entry in entries
        if isinstance(entry, dict) and entry.get("filepath")
    ]
    return normalize_source_paths(paths, require_exists=False)


__all__ = [
    "cif_paths_from_tick_series",
    "cif_present",
    "ensure_xy_args_files",
    "file_data_source_paths",
    "normalize_source_paths",
    "resolve_xy_source_files",
]

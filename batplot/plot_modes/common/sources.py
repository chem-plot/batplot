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
            abs_path = os.path.abspath(path)
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


def cif_present(args_files: Iterable[Any] | None, series_getter: Any = None) -> bool:
    """Return True if any input file is a ``.cif`` or a CIF tick series exists.

    Supports the ``path:label`` syntax by inspecting only the part before the
    first colon. ``series_getter`` is an optional zero-arg callable returning the
    current CIF tick series (truthy when overlays exist).
    """
    try:
        if any(
            str(f).split(":")[0].lower().endswith(".cif")
            for f in (args_files or [])
        ):
            return True
        if series_getter is not None:
            return bool(series_getter())
    except Exception:
        pass
    return False


def file_data_source_paths(file_data: Any) -> List[str]:
    """Extract filepath entries from a single file_data dict or list of dicts."""
    entries = file_data if isinstance(file_data, list) else [file_data]
    paths = [
        entry.get("filepath")
        for entry in entries
        if isinstance(entry, dict) and entry.get("filepath")
    ]
    return normalize_source_paths(paths, require_exists=False)


__all__ = ["cif_present", "file_data_source_paths", "normalize_source_paths"]

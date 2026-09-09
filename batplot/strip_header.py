"""Remove leading header lines from text files and export to a subfolder.

CLI examples
------------
    batplot data.txt --strip-header 5
    batplot /path/to/folder --strip-header 3 --ext .xy
    batplot /path/to/folder --strip-header 2 --ext .xy,.dat,.txt
"""

from __future__ import annotations

import os
from typing import Sequence

from .converters import normalize_extension
from .utils import natural_sort_key

# Default subfolder written next to each input (mirrors ``converted/`` for --convert).
DEFAULT_OUT_SUBDIR = "stripped"

# Formats that are not plain text line-oriented files — skip with a warning.
_BINARY_OR_UNSUPPORTED_EXTS = frozenset(
    {
        ".brml",
        ".raw",
        ".rasx",
        ".xrdml",
        ".xlsx",
        ".xls",
        ".pkl",
        ".bps",
        ".bpsg",
        ".bpsh",
        ".png",
        ".jpg",
        ".jpeg",
        ".svg",
        ".pdf",
        ".gif",
        ".tif",
        ".tiff",
        ".zip",
        ".gz",
        ".bz2",
        ".7z",
        ".pyc",
        ".so",
        ".dll",
        ".dylib",
        ".exe",
    }
)


def parse_ext_filters(raw: str | None) -> list[str] | None:
    """Parse ``--ext`` into a list of normalized extensions.

    Accepts a single token (``.xy`` / ``xy``) or a comma-separated list
    (``.xy,.dat,.txt``). Returns ``None`` when unset/empty.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if not parts:
        return None
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        norm = normalize_extension(p)
        if norm and norm not in seen:
            seen.add(norm)
            out.append(norm)
    return out or None


def strip_header_bytes(data: bytes, n_lines: int) -> tuple[bytes, int, int]:
    """Return ``(body, total_lines, removed)`` after dropping the first ``n_lines``.

    Uses ``bytes.splitlines(keepends=True)`` so ``\\n``, ``\\r\\n``, and ``\\r``
    line endings are preserved on Windows, macOS, and Linux.
    """
    if n_lines < 0:
        raise ValueError("n_lines must be >= 0")
    if not data:
        return b"", 0, 0
    lines = data.splitlines(keepends=True)
    total = len(lines)
    removed = min(n_lines, total)
    return b"".join(lines[removed:]), total, removed


def strip_header_file(
    path: str,
    n_lines: int,
    *,
    out_subdir: str = DEFAULT_OUT_SUBDIR,
) -> str | None:
    """Strip the first ``n_lines`` from ``path`` into ``<dir>/<out_subdir>/<name>``.

    Returns the output path on success, or ``None`` on skip/failure.
    Never modifies the original file.
    """
    if n_lines < 1:
        print(f"Error: --strip-header requires N >= 1 (got {n_lines})")
        return None
    if not os.path.isfile(path):
        print(f"Warning: Not a file: {path}")
        return None

    ext = os.path.splitext(path)[1].lower()
    if ext in _BINARY_OR_UNSUPPORTED_EXTS:
        print(f"Warning: Skipping unsupported/binary format: {path}")
        return None

    abs_path = os.path.abspath(path)
    input_dir = os.path.dirname(abs_path) or os.getcwd()
    subdir = (out_subdir or DEFAULT_OUT_SUBDIR).strip() or DEFAULT_OUT_SUBDIR
    # Avoid writing into a nested stripped/stripped/... if user points at an output file.
    if os.path.basename(os.path.normpath(input_dir)).lower() == subdir.lower():
        print(f"Warning: Skipping file already inside '{subdir}/': {path}")
        return None

    output_dir = os.path.join(input_dir, subdir)
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as exc:
        print(f"Error: Cannot create output folder {output_dir}: {exc}")
        return None

    out_path = os.path.join(output_dir, os.path.basename(abs_path))
    # Do not overwrite a different input that happens to share the output path.
    if os.path.normcase(os.path.normpath(out_path)) == os.path.normcase(os.path.normpath(abs_path)):
        print(f"Warning: Refusing to overwrite input in place: {path}")
        return None

    try:
        with open(abs_path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        print(f"Error reading {path}: {exc}")
        return None

    try:
        body, total, removed = strip_header_bytes(data, n_lines)
    except ValueError as exc:
        print(f"Error: {exc}")
        return None

    if removed < n_lines:
        print(
            f"Warning: {path} has only {total} line(s); "
            f"removed {removed} (requested {n_lines})."
        )

    try:
        with open(out_path, "wb") as fh:
            fh.write(body)
    except OSError as exc:
        print(f"Error writing {out_path}: {exc}")
        return None

    print(f"Stripped {removed} header line(s): {path} → {out_path}")
    return out_path


def collect_strip_targets(
    paths: Sequence[str],
    ext_filters: Sequence[str] | None,
) -> list[str]:
    """Expand files/folders into a flat list of text files to process.

    - Files: included as-is (optional ``ext_filters`` still applied when set).
    - Directories: non-recursive listing of immediate files matching ``ext_filters``.
      ``ext_filters`` is required for directories.
    """
    expanded: list[str] = []
    filters = [normalize_extension(e) for e in (ext_filters or []) if normalize_extension(e)]
    filter_set = set(filters) if filters else None

    for p in paths:
        if not p:
            continue
        if os.path.isfile(p):
            ext = os.path.splitext(p)[1].lower()
            if filter_set is not None and ext not in filter_set:
                print(f"Warning: Skipping file (extension filter {', '.join(sorted(filter_set))}): {p}")
                continue
            expanded.append(p)
        elif os.path.isdir(p):
            if filter_set is None:
                print(
                    f"Error: Folder requires --ext to select file types "
                    f"(e.g. --ext .xy or --ext .xy,.dat,.txt): {p}"
                )
                continue
            try:
                names = sorted(os.listdir(p), key=natural_sort_key)
            except OSError as exc:
                print(f"Error listing directory {p}: {exc}")
                continue
            for name in names:
                # Skip hidden entries and the output subfolder name if present as a file.
                if name.startswith("."):
                    continue
                fp = os.path.join(p, name)
                if not os.path.isfile(fp):
                    continue
                ext = os.path.splitext(name)[1].lower()
                if ext in filter_set:
                    expanded.append(fp)
        else:
            print(f"Warning: Not a file or directory: {p}")

    return expanded


def run_strip_header(
    paths: Sequence[str],
    n_lines: int,
    *,
    ext: str | None = None,
    out_subdir: str = DEFAULT_OUT_SUBDIR,
) -> int:
    """CLI entry: strip headers from files/folders. Returns process exit code."""
    if n_lines is None:
        print("Error: --strip-header requires the number of lines to remove (e.g. --strip-header 5).")
        return 1
    try:
        n = int(n_lines)
    except (TypeError, ValueError):
        print(f"Error: --strip-header N must be an integer (got {n_lines!r}).")
        return 1
    if n < 1:
        print(f"Error: --strip-header requires N >= 1 (got {n}).")
        return 1
    if not paths:
        print("Error: --strip-header requires file(s) or a directory.")
        return 1

    ext_filters = parse_ext_filters(ext)
    # Folder-only inputs must have --ext; collect_strip_targets enforces that.
    has_dir = any(os.path.isdir(p) for p in paths if p)
    if has_dir and ext_filters is None:
        print(
            "Error: when stripping a folder, pass --ext "
            "(e.g. batplot folder --strip-header 3 --ext .xy)."
        )
        return 1

    targets = collect_strip_targets(paths, ext_filters)
    if not targets:
        if ext_filters:
            shown = ", ".join(ext_filters)
            print(f"Error: No matching files found (looking for: {shown}).")
        else:
            print("Error: No files to process.")
        return 1

    n_ok = 0
    for path in targets:
        if strip_header_file(path, n, out_subdir=out_subdir) is not None:
            n_ok += 1

    if n_ok == 0:
        print("Error: No files were stripped successfully.")
        return 1
    print(f"Done: stripped headers from {n_ok} file(s) → '{out_subdir}/' subfolder(s).")
    return 0


__all__ = [
    "DEFAULT_OUT_SUBDIR",
    "collect_strip_targets",
    "parse_ext_filters",
    "run_strip_header",
    "strip_header_bytes",
    "strip_header_file",
]

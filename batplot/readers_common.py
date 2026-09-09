"""Low-level numeric parsing helpers shared by batplot readers.

Split out of ``readers.py`` so both the generic readers and the
electrochemistry readers (``readers_ec.py``) can use them without a
circular import. All names are re-exported from ``batplot.readers``.
"""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any, List, Optional, cast

import numpy as np  # type: ignore[import-untyped]


def _to_float_decimal(s: str | bytes) -> float:
    """Convert string/bytes to float, supporting comma as decimal separator (European locale)."""
    raw = s.decode() if isinstance(s, bytes) else str(s)
    val = raw.strip()
    try:
        return float(val)
    except ValueError:
        return float(val.replace(",", "."))


def _parse_numeric_tokens(line: str) -> Optional[List[float]]:
    """Parse a line into numeric tokens, supporting comma as decimal and comma as delimiter."""
    tokens = line.replace("\t", " ").split()
    result: List[float] = []
    for t in tokens:
        try:
            result.append(float(t.replace(",", ".")))
        except ValueError:
            parts = t.split(",")
            if len(parts) >= 2:
                try:
                    result.extend([float(p.strip()) for p in parts])
                except ValueError:
                    return None
            else:
                return None
    return result


def loadtxt_with_decimal_comma(fname: str, comments: str = "#", **kwargs: Any) -> np.ndarray:
    """Load numeric data with np.loadtxt, supporting comma as decimal separator."""
    # Infer column count from first valid line to avoid "invalid column" errors
    ncols = 2
    with open(fname, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            ls = line.strip()
            if not ls or ls.startswith(comments):
                continue
            ncols = max(ncols, len(line.split()))
            break
    conv = {i: _to_float_decimal for i in range(min(ncols, 256))}
    return np.loadtxt(fname, comments=comments, converters=cast(Any, conv), **kwargs)


def _csv_cell_to_float(cell: str) -> float:
    """Convert one CSV cell to float; non-numeric markers become NaN."""
    raw = (cell or "").strip()
    if not raw or raw == ";":
        return float("nan")
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return float("nan")


def read_csv_numeric_grid(fname: str) -> np.ndarray:
    """Read comma-separated CSV into a float grid (NaN for text or ';' cells).

    Skips a leading header row when the first column is not numeric. Handles
    UTF-8 BOMs and wide refinement exports that interleave labels with values.
    """
    with open(fname, newline="", encoding="utf-8-sig", errors="ignore") as f:
        rows = [row for row in csv.reader(f) if row and any((c or "").strip() for c in row)]
    if not rows:
        raise ValueError(f"No numeric data found in {fname}")

    start = 0
    first_col = _csv_cell_to_float(rows[0][0]) if rows[0] else float("nan")
    if not np.isfinite(first_col):
        start = 1
    data_rows = rows[start:]
    if not data_rows:
        raise ValueError(f"No numeric data found in {fname}")

    ncols = max(len(row) for row in data_rows)
    grid = np.full((len(data_rows), ncols), np.nan, dtype=float)
    for i, row in enumerate(data_rows):
        for j, cell in enumerate(row):
            if j < ncols:
                grid[i, j] = _csv_cell_to_float(cell)

    if not np.any(np.isfinite(grid)):
        raise ValueError(f"No numeric data found in {fname}")
    return grid


def robust_loadtxt_skipheader(fname: str):
    """Skip comments/non-numeric lines and load at least 2-column numeric data.
    
    Flexibly handles comma, space, tab, or mixed delimiters.
    Supports comma as decimal separator (European locale, e.g. 1,5 for 1.5).
    """
    if str(fname).lower().endswith(".csv"):
        try:
            return read_csv_numeric_grid(fname)
        except ValueError:
            pass

    data_lines: List[str] = []
    with open(fname, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            ls = line.strip()
            if not ls or ls.startswith("#"):
                continue
            parsed = _parse_numeric_tokens(ls.replace("\t", " "))
            if parsed is not None and len(parsed) >= 2:
                data_lines.append(" ".join(str(v) for v in parsed))
    if not data_lines:
        raise ValueError(f"No numeric data found in {fname}")
    return np.loadtxt(StringIO("\n".join(data_lines)))


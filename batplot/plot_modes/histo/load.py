"""Load tabular data for histogram mode."""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np  # type: ignore[import]

from ...showcol import _print_columns, _rows_to_columns, _try_float


@dataclass
class TableData:
    path: str
    headers: List[str]
    rows: List[List[str]]

    @property
    def ncols(self) -> int:
        if not self.rows:
            return len(self.headers)
        return max(len(self.headers), max(len(r) for r in self.rows))

    def padded_headers(self) -> List[str]:
        n = self.ncols
        h = list(self.headers) + [""] * max(0, n - len(self.headers))
        return h[:n]

    def preview_columns(self, n_preview: int = 5) -> None:
        ncols = self.ncols
        h = self.padded_headers()
        norm_rows: List[List[str]] = []
        for r in self.rows[:n_preview]:
            row = list(r) + [""] * max(0, ncols - len(r))
            norm_rows.append(row[:ncols])
        cols = _rows_to_columns(norm_rows, ncols, n_preview)
        print(f"\nColumns in {os.path.basename(self.path)}:")
        _print_columns(h, cols)

    def column_values(self, col_index: int) -> np.ndarray:
        """Return numeric values from a 1-based column index."""
        if col_index < 1:
            raise ValueError(f"Column index must be >= 1, got {col_index}")
        j = col_index - 1
        out: List[float] = []
        for row in self.rows:
            if j >= len(row):
                continue
            cell = str(row[j]).strip()
            if not cell:
                continue
            val = _try_float(cell)
            if val is None:
                continue
            out.append(float(val))
        if not out:
            raise ValueError(f"No numeric values in column {col_index}")
        return np.asarray(out, dtype=float)

    def last_numeric_column_index(self) -> int:
        """Return 1-based index of the rightmost column with numeric data."""
        ncols = self.ncols
        for j in range(ncols - 1, -1, -1):
            for row in self.rows:
                if j >= len(row):
                    continue
                cell = str(row[j]).strip()
                if cell and _try_float(cell) is not None:
                    return j + 1
        raise ValueError("No numeric columns found")


def _load_delimited_text(path: str) -> Tuple[List[str], List[List[str]]]:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        sample = f.read(4096)
    if not sample.strip():
        raise ValueError(f"File is empty: {path}")
    delimiter = "\t" if sample.count("\t") >= sample.count(",") else ","
    rows_raw: List[List[str]] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.reader(f, delimiter=delimiter)
        for row in reader:
            if not row or all(not str(c).strip() for c in row):
                continue
            rows_raw.append([str(c).strip() for c in row])
    if not rows_raw:
        raise ValueError(f"No data rows in {path}")
    header = rows_raw[0]
    data_rows = rows_raw[1:]
    # If first row looks numeric, treat file as headerless.
    if header and all(_try_float(c) is not None for c in header if str(c).strip()):
        data_rows = rows_raw
        header = [""] * len(header)
    return header, data_rows


def load_table(path: str) -> TableData:
    """Load a CSV or TXT table for histogram mode."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {path}")
    ext = p.suffix.lower()
    if ext == ".csv":
        from ...readers import _load_csv_header_and_rows

        try:
            header, rows, _meta = _load_csv_header_and_rows(str(p))
            return TableData(path=str(p), headers=list(header), rows=rows)
        except Exception:
            header, rows = _load_delimited_text(str(p))
            return TableData(path=str(p), headers=header, rows=rows)
    if ext in (".txt", ".tsv", ".dat"):
        header, rows = _load_delimited_text(str(p))
        return TableData(path=str(p), headers=header, rows=rows)
    raise ValueError(
        f"Histogram mode supports .csv and .txt files (got {ext!r}). "
        "Use batplot file.csv --histo --i"
    )


def column_stats(values: np.ndarray) -> dict:
    vals = np.asarray(values, dtype=float)
    finite = vals[np.isfinite(vals)]
    if finite.size == 0:
        raise ValueError("No finite numeric values to histogram")
    return {
        "n": int(finite.size),
        "min": float(np.min(finite)),
        "max": float(np.max(finite)),
        "mean": float(np.mean(finite)),
        "median": float(np.median(finite)),
        "std": float(np.std(finite)),
    }


def suggest_bin_width(xmin: float, xmax: float, n: int) -> float:
    span = max(xmax - xmin, 1e-12)
    if n <= 1:
        return max(span / 10.0, 1e-6)
    # Sturges-like default, rounded to a sensible step.
    raw = span / max(8.0, min(50.0, np.log2(n) + 1.0))
    if raw <= 0:
        return span / 10.0
    magnitude = 10 ** np.floor(np.log10(raw))
    nice = magnitude * np.array([1.0, 2.0, 2.5, 5.0, 10.0])
    pick = float(nice[np.argmin(np.abs(nice - raw))])
    return max(pick, magnitude * 0.1)


def auto_range(values: np.ndarray, *, padding_fraction: float = 0.02) -> Tuple[float, float]:
    stats = column_stats(values)
    span = stats["max"] - stats["min"]
    pad = span * padding_fraction if span > 0 else 0.1
    xmin = stats["min"] - pad
    xmax = stats["max"] + pad
    if xmin == xmax:
        xmin -= 0.5
        xmax += 0.5
    return xmin, xmax


def build_bin_edges(xmin: float, xmax: float, *, bin_width: float | None, n_bins: int | None) -> np.ndarray:
    if xmax <= xmin:
        raise ValueError(f"Invalid histogram range: xmin={xmin} xmax={xmax}")
    if bin_width is not None and bin_width <= 0:
        raise ValueError("Bin width must be positive")
    if n_bins is not None and n_bins <= 0:
        raise ValueError("Number of bins must be positive")
    if bin_width is not None and n_bins is not None:
        raise ValueError("Use either --binwidth or --bins, not both")
    if bin_width is not None:
        edges = np.arange(xmin, xmax + bin_width * 0.5, bin_width, dtype=float)
        if edges.size < 2:
            edges = np.array([xmin, xmax], dtype=float)
        if edges[-1] < xmax:
            edges = np.append(edges, edges[-1] + bin_width)
        return edges
    if n_bins is not None:
        return np.linspace(xmin, xmax, int(n_bins) + 1, dtype=float)
    width = suggest_bin_width(xmin, xmax, 10)
    return build_bin_edges(xmin, xmax, bin_width=width, n_bins=None)


def resolve_column_index(table: TableData, col_spec: str | int) -> int:
    if col_spec is None:
        raise ValueError("No column specified")
    if isinstance(col_spec, int):
        if col_spec < 1 or col_spec > table.ncols:
            raise ValueError(f"Column {col_spec} out of range (1..{table.ncols})")
        return col_spec
    text = str(col_spec).strip()
    if text.isdigit():
        return resolve_column_index(table, int(text))
    headers = table.padded_headers()
    lowered = [h.strip().lower() for h in headers]
    key = text.lower()
    if key in lowered:
        return lowered.index(key) + 1
    matches = [i + 1 for i, h in enumerate(headers) if key in h.lower() and h.strip()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise ValueError(f"Ambiguous column name {text!r}; use column number")
    raise ValueError(f"Unknown column {text!r}")

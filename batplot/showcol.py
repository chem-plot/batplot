"""CLI helper: preview column headers and first rows for many batplot input formats.

Used by ``batplot --showcol <files>`` (see ``run_showcol``).
"""

from __future__ import annotations

import csv
import os
import re
from io import StringIO
from typing import Any, List, Optional, Sequence, Tuple

# -----------------------------------------------------------------------------
# Path tokens like file.xye:1.5406 (wavelength suffix)
# -----------------------------------------------------------------------------

_WL_SUFFIX_RE = re.compile(r"^(.+\.\w+):(\d+(?:\.\d+)?)$")


def resolve_path_token(token: str) -> str:
    """Strip trailing ``:wavelength`` from a path when the base file exists."""
    if os.path.isfile(token):
        return token
    if ":" not in token:
        return token
    base, tail = token.rsplit(":", 1)
    try:
        float(tail)
    except ValueError:
        return token
    if os.path.isfile(base):
        return base
    m = _WL_SUFFIX_RE.match(token.replace("\\", "/"))
    if m and os.path.isfile(m.group(1)):
        return m.group(1)
    return token


# -----------------------------------------------------------------------------
# Formatting
# -----------------------------------------------------------------------------

N_PREVIEW_DEFAULT = 10
_MAX_CELL_STR = 18


def _try_float(s: str) -> Optional[float]:
    try:
        return float(s.replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def _fmt_cell(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        t = f"{v:.6g}"
    else:
        t = str(v).strip()
    if len(t) > _MAX_CELL_STR:
        return t[: _MAX_CELL_STR - 1] + "…"
    return t


def _print_columns(
    col_names: Sequence[str],
    columns: Sequence[Sequence[Any]],
    *,
    notes: str = "",
) -> None:
    """Print numbered columns with optional names and up to N preview values per column."""
    if notes:
        print(notes)
    ncols = len(columns)
    if ncols == 0:
        print("  (no columns to display)")
        return
    for j in range(ncols):
        name = ""
        if j < len(col_names) and str(col_names[j]).strip():
            name = str(col_names[j]).strip()
        label = f"[{j + 1}] {name}" if name else f"[{j + 1}]"
        vals = columns[j]
        vs = ", ".join(_fmt_cell(v) for v in vals)
        print(f"  {label}")
        print(f"      {vs}")


def _rows_to_columns(
    rows: Sequence[Sequence[Any]], ncols: int, n_preview: int
) -> List[List[Any]]:
    out: List[List[Any]] = [[] for _ in range(ncols)]
    for row in rows[:n_preview]:
        for j in range(ncols):
            out[j].append(row[j] if j < len(row) else "")
    return out


# -----------------------------------------------------------------------------
# CSV (uses same header logic as readers._load_csv_header_and_rows when possible)
# -----------------------------------------------------------------------------

def _showcol_csv(path: str, n_preview: int) -> None:
    from .readers import _load_csv_header_and_rows

    try:
        header, rows, _ = _load_csv_header_and_rows(path)
    except Exception as exc:
        print(f"  CSV parse fallback ({exc}); trying generic text preview.")
        _showcol_delimited_text(path, n_preview)
        return
    if not rows:
        print("  (file has header but no data rows)")
        _print_columns(header, [[] for _ in header], notes="")
        return
    ncols = max(len(header), max(len(r) for r in rows[:n_preview]))
    # Pad header
    h = list(header) + [""] * max(0, ncols - len(header))
    norm_rows: List[List[Any]] = []
    for r in rows[:n_preview]:
        row = list(r) + [""] * max(0, ncols - len(r))
        norm_rows.append(row[:ncols])
    cols = _rows_to_columns(norm_rows, ncols, n_preview)
    _print_columns(h[:ncols], cols)


# -----------------------------------------------------------------------------
# Delimited / whitespace text (.xy, .txt, .dat, non-EC-Lab .mpt, etc.)
# -----------------------------------------------------------------------------

def _tokenize_line(line: str) -> List[str]:
    ls = line.strip()
    if "\t" in ls:
        return [p.strip() for p in ls.split("\t")]
    if ";" in ls and "," not in ls:
        return [p.strip() for p in ls.split(";")]
    # Let csv handle "a,b,c" with possible quotes
    try:
        r = next(csv.reader(StringIO(ls)))
        if len(r) >= 2:
            return [x.strip() for x in r]
    except Exception:
        pass
    return ls.split()


def _is_numeric_data_row(tokens: Sequence[str]) -> bool:
    if len(tokens) < 2:
        return False
    ok = 0
    for t in tokens:
        if t == "":
            continue
        if _try_float(t) is None:
            return False
        ok += 1
    return ok >= 2


def _showcol_delimited_text(path: str, n_preview: int) -> None:
    raw_lines: List[str] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            ls = line.strip()
            if not ls or ls.startswith("#"):
                continue
            raw_lines.append(ls)

    token_rows = [_tokenize_line(ln) for ln in raw_lines]
    data_idx = None
    for i, tok in enumerate(token_rows):
        if _is_numeric_data_row(tok):
            data_idx = i
            break

    if data_idx is None:
        print("  No row found with at least two numeric columns (after # comments).")
        if token_rows:
            print(f"  First non-comment line (tokens): {token_rows[0][:12]!r}…")
        return

    preamble = token_rows[:data_idx]
    header_tokens: List[str] = []
    if data_idx > 0:
        header_tokens = list(token_rows[data_idx - 1])
        if data_idx > 1:
            print("  Leading non-data lines (not used as column names):")
            for k, pl in enumerate(preamble[:-1], start=1):
                prev = " ".join(_fmt_cell(x) for x in pl[:16])
                if len(pl) > 16:
                    prev += " …"
                print(f"    ({k}) {prev}")

    data_rows = token_rows[data_idx : data_idx + n_preview]
    if not data_rows:
        print("  (no data rows)")
        return

    ncols = max(len(r) for r in data_rows)
    names: List[str]
    if header_tokens:
        if len(header_tokens) < ncols:
            header_tokens = header_tokens + [""] * (ncols - len(header_tokens))
        names = [header_tokens[j] if j < len(header_tokens) else "" for j in range(ncols)]
    else:
        names = [""] * ncols

    norm_rows: List[List[Any]] = []
    for r in data_rows:
        row = list(r) + [""] * (ncols - len(r))
        vals: List[Any] = []
        for j in range(ncols):
            t = row[j].strip() if j < len(row) else ""
            fv = _try_float(t)
            vals.append(fv if fv is not None else t)
        norm_rows.append(vals)

    cols = _rows_to_columns(norm_rows, ncols, n_preview)
    _print_columns(names, cols)


# -----------------------------------------------------------------------------
# BioLogic EC-Lab .mpt
# -----------------------------------------------------------------------------

def _showcol_mpt(path: str, n_preview: int) -> None:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        first = f.readline()

    if not first.strip().startswith("EC-Lab ASCII FILE"):
        _showcol_delimited_text(path, n_preview)
        return

    header_lines = 0
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.startswith("Nb header lines"):
                m = re.search(r"Nb header lines\s*:\s*(\d+)", line)
                if m:
                    header_lines = int(m.group(1))
                    break

    if header_lines == 0:
        print("  Could not find EC-Lab 'Nb header lines'; using generic text preview.")
        _showcol_delimited_text(path, n_preview)
        return

    column_names: List[str] = []
    data_rows: List[List[float]] = []
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for _ in range(header_lines - 1):
            f.readline()
        header_line = f.readline().strip()
        column_names = [c.strip() for c in header_line.split("\t")]
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) != len(column_names):
                continue
            try:
                data_rows.append([float(p.replace(",", ".")) for p in parts])
            except ValueError:
                continue
            if len(data_rows) >= n_preview:
                break

    if not column_names:
        print("  (no column names in .mpt)")
        return

    cols = _rows_to_columns(data_rows, len(column_names), n_preview)
    _print_columns(column_names, cols)


# -----------------------------------------------------------------------------
# Excel
# -----------------------------------------------------------------------------

def _showcol_xlsx(path: str, n_preview: int) -> None:
    from .readers import openpyxl as _oxl  # type: ignore

    if _oxl is None:
        print("  Install openpyxl to preview .xlsx: pip install openpyxl")
        return

    wb = _oxl.load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb.active
        if ws is None:
            print("  (workbook has no active sheet)")
            return
        grid: List[List[str]] = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= 80:
                break
            grid.append(["" if v is None else str(v).strip() for v in row])
    finally:
        wb.close()

    while grid and not any(c.strip() for c in grid[-1]):
        grid.pop()
    if not grid:
        print("  (empty sheet)")
        return

    data_idx = None
    for i, row in enumerate(grid):
        while row and row[-1] == "":
            row = row[:-1]
        if _is_numeric_data_row(row):
            data_idx = i
            break

    if data_idx is None:
        print("  No row with all-numeric cells (≥2 columns) in first rows.")
        return

    if data_idx > 0:
        print("  Leading non-data rows:")
        for k in range(data_idx - 1):
            r = grid[k]
            s = " | ".join(_fmt_cell(x) for x in r[:12])
            if len(r) > 12:
                s += " | …"
            print(f"    ({k + 1}) {s}")

    header_tokens = list(grid[data_idx - 1]) if data_idx > 0 else []
    data_rows_raw = grid[data_idx : data_idx + n_preview]
    ncols = max(len(r) for r in data_rows_raw)
    names = [header_tokens[j] if j < len(header_tokens) else "" for j in range(ncols)]

    norm_rows: List[List[Any]] = []
    for r in data_rows_raw:
        row = list(r) + [""] * (ncols - len(r))
        vals = []
        for j in range(ncols):
            t = row[j] if j < len(row) else ""
            fv = _try_float(str(t))
            vals.append(fv if fv is not None else t)
        norm_rows.append(vals)

    cols = _rows_to_columns(norm_rows, ncols, n_preview)
    _print_columns(names, cols)


# -----------------------------------------------------------------------------
# Bruker .brml / .raw
# -----------------------------------------------------------------------------

def _showcol_brml(path: str, n_preview: int) -> None:
    from .readers import extract_bruker_brml_scans

    try:
        scans = extract_bruker_brml_scans(path, out_dir=None)
    except Exception as exc:
        print(f"  Could not read .brml: {exc}")
        return
    if not scans:
        print("  (no XRD scans found in .brml)")
        return
    x_arr, y_arr = scans[0]
    n = min(n_preview, len(x_arr))
    xs = [float(x_arr[i]) for i in range(n)]
    ys = [float(y_arr[i]) for i in range(n)]
    note = f"  Native XML zip: {len(scans)} scan(s); preview is first scan only, 2 columns."
    if len(scans) > 1:
        note += f" (scans 2–{len(scans)} same layout)"
    _print_columns(["2theta (deg)", "intensity"], [xs, ys], notes=note)


def _showcol_bruker_raw(path: str, n_preview: int) -> None:
    from .readers import read_bruker_raw

    try:
        x_arr, y_arr, _e, _wl = read_bruker_raw(path)
    except Exception as exc:
        print(f"  Could not read Bruker .raw: {exc}")
        return
    n = min(n_preview, len(x_arr))
    xs = [float(x_arr[i]) for i in range(n)]
    ys = [float(y_arr[i]) for i in range(n)]
    _print_columns(
        ["2theta (deg)", "intensity"],
        [xs, ys],
        notes="  Binary Bruker RAW v4: no text header; column names are descriptive labels.",
    )


# -----------------------------------------------------------------------------
# Dispatcher
# -----------------------------------------------------------------------------

_SKIP_EXT = {
    ".bps",
    ".bpsg",
    ".pkl",
    ".py",
    ".md",
    ".svg",
    ".png",
    ".pdf",
    ".cif",
}


def showcol_one(path: str, n_preview: int = N_PREVIEW_DEFAULT) -> bool:
    """Print preview for one file. Returns True on success."""
    ext = os.path.splitext(path)[1].lower()
    print(f"=== {path} ===")
    if ext in _SKIP_EXT:
        if ext == ".cif":
            print("  Skipping .cif (crystal structure; not tabular columns).")
        else:
            print(f"  Skipping (not a data preview target): {ext}")
        return True

    try:
        if ext == ".csv":
            _showcol_csv(path, n_preview)
        elif ext in (".xlsx", ".xls"):
            _showcol_xlsx(path, n_preview)
        elif ext == ".mpt":
            _showcol_mpt(path, n_preview)
        elif ext == ".brml":
            _showcol_brml(path, n_preview)
        elif ext == ".raw":
            from .readers import is_bruker_raw

            if is_bruker_raw(path):
                _showcol_bruker_raw(path, n_preview)
            else:
                print("  Not Bruker RAW v4; trying text column preview.")
                _showcol_delimited_text(path, n_preview)
        else:
            _showcol_delimited_text(path, n_preview)
    except OSError as exc:
        print(f"  Error reading file: {exc}")
        return False
    except Exception as exc:
        print(f"  Error: {exc}")
        return False

    print()
    return True


def run_showcol(paths: Sequence[str], n_preview: int = N_PREVIEW_DEFAULT) -> int:
    """Entry for CLI: preview all paths. Exit code 0 if all succeeded."""
    if not paths:
        print("batplot --showcol: provide at least one file.")
        return 1
    ok = True
    for token in paths:
        p = resolve_path_token(token)
        if os.path.isdir(p):
            print(f"=== {token} ===\n  Skipping directory (pass files, not folders).\n")
            continue
        if not os.path.isfile(p):
            print(f"=== {token} ===\n  File not found.\n")
            ok = False
            continue
        if not showcol_one(p, n_preview=n_preview):
            ok = False
    return 0 if ok else 1

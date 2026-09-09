"""Readers for various battery cycler data formats.

This module provides parsers for different battery testing equipment file formats:

Supported Formats:
    - BioLogic .mpt / .npt: EC-Lab ASCII exports (same layout; ``.npt`` is treated as an alias of ``.mpt``)
    - BioLogic .txt: Exported text format from EC-Lab software
    - Neware .csv: CSV export from Neware battery testers
    - Landt/Lanhe .xlsx: Excel files with Chinese column headers
    - Generic .csv: Generic CSV with standard battery cycling columns

Key Functions:
    - read_mpt_file(): Parse BioLogic .mpt files for CV, GC, CPC modes
    - read_biologic_txt_file(): Parse BioLogic .txt exports
    - read_ec_csv_file(): Parse Neware CSV and Excel files, handles half-cycles
    - read_ec_csv_dqdv_file(): Parse CSV for differential capacity analysis

Data Return Formats:
    CV mode: (voltage, current, cycles)
    GC mode: (capacity, voltage, cycles, charge_mask, discharge_mask)
    CPC mode: (cycle_nums, cap_charge, cap_discharge, efficiency)
    dQ/dV mode: (voltage, dqdv, cycles)

Special Features:
    - Half-cycle detection and merging (Neware compatibility)
    - Automatic column detection with fuzzy matching
    - Chinese column name support (Landt/Lanhe cyclers)
    - Specific capacity calculation for .mpt files
"""

from __future__ import annotations

import numpy as np  # type: ignore[import-untyped]
from typing import Any, cast
try:
    import openpyxl  # type: ignore[import-untyped]  # noqa: F401 (re-exported; showcol imports it from here)
except ImportError:
    openpyxl = None  # optional dependency


# Shared numeric parsing helpers live in readers_common.py (re-exported).
from .readers_common import (  # noqa: F401
    _to_float_decimal,
    _parse_numeric_tokens,
    loadtxt_with_decimal_comma,
    _csv_cell_to_float,
    read_csv_numeric_grid,
    robust_loadtxt_skipheader,
)

# Electrochemistry readers live in readers_ec.py (re-exported for compatibility).
from .readers_ec import (  # noqa: F401
    _infer_cycles_from_masks,
    read_excel_to_csv_like,
    _normalize_header_value,
    _normalize_data_value,
    _looks_like_neware_multilevel,
    _parse_neware_multilevel_rows,
    _load_csv_header_and_rows,
    read_mpt_file,
    read_biologic_txt_file,
    read_ec_csv_file,
    read_ec_csv_dqdv_file,
    _compute_dqdv_from_capacity,
    compute_dqdv_numerical,
    read_mpt_dqdv_file,
    is_cs_b_format,
    is_biologic_datalogger_csv,
    read_biologic_datalogger_csv,
    read_biologic_datalogger_time_voltage,
    read_biologic_datalogger_dqdv_file,
    read_cs_b_csv_file,
    read_csv_time_voltage,
    read_mpt_time_voltage,
    read_batx_file,
    read_indexed_voltage_time_file,
)


def read_csv_file(fname: str):
    # Try ; and \t before , so European format (semicolon + comma decimal) parses correctly
    for delim in [";", "\t", ","]:
        try:
            # Infer column count from first line to build converters (genfromtxt errors if too many)
            ncols = 2
            with open(fname, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.strip() and not line.strip().startswith("#"):
                        ncols = max(ncols, len(line.strip().split(delim)))
                        break
            _conv = {i: _to_float_decimal for i in range(min(ncols, 256))}
            data = np.genfromtxt(fname, delimiter=delim, comments="#", converters=cast(Any, _conv))
            if data.ndim == 1:
                data = data.reshape(1, -1)
            if data.shape[1] >= 2:
                # Reject if first 2 columns have excessive NaN (wrong delimiter)
                valid = np.isfinite(data[:, 0]) & np.isfinite(data[:, 1])
                if np.sum(valid) >= 1:
                    return data
        except Exception:
            continue
    raise ValueError(f"Invalid CSV format in {fname}, need at least 2 columns (x,y).")


# XRD vendor readers live in readers_xrd.py (re-exported for compatibility).
from .readers_xrd import (  # noqa: F401
    is_bruker_raw,
    sanitize_xrd_intensity,
    read_bruker_raw,
    read_bruker_brml,
    extract_bruker_brml_scans,
    read_xrd_vendor_file,
)


def read_gr_file(fname: str):
    """Read a PDF .gr file (r, G(r)). Supports comma as decimal separator."""
    r_vals = []
    g_vals = []
    with open(fname, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            ls = line.strip()
            if not ls or ls.startswith("#"):
                continue
            parsed = _parse_numeric_tokens(ls.replace("\t", " "))
            if parsed is not None and len(parsed) >= 2:
                r_vals.append(parsed[0])
                g_vals.append(parsed[1])
    if not r_vals:
        raise ValueError(f"No numeric data found in {fname}")
    return np.array(r_vals, dtype=float), np.array(g_vals, dtype=float)


def read_fullprof_rowwise(fname: str):
    with open(fname, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()[1:]
    y_rows = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        y_rows.extend([_to_float_decimal(val) for val in line.split()])
    y = np.array(y_rows)
    return y, len(lines)


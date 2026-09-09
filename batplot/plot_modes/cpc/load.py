"""Load CPC/EPC series arrays from CSV/XLS/MPT (shared by CLI and interactive add)."""

from __future__ import annotations

import os
from typing import Optional, Tuple, cast

import numpy as np  # type: ignore[import-untyped]

from ...readers import (
    _load_csv_header_and_rows,
    is_cs_b_format,
    read_cs_b_csv_file,
    read_ec_csv_file,
    read_mpt_file,
)

_SUPPORTED_EXTS = (".csv", ".xlsx", ".xls", ".mpt")


def cpc_supported_extension(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in _SUPPORTED_EXTS


def cpc_file_needs_mass(path: str) -> bool:
    """True when active mass (mg) is required before this file can be loaded."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".mpt":
        return True
    if ext not in (".csv", ".xlsx", ".xls"):
        return False
    try:
        header, _, _ = _load_csv_header_and_rows(path)
    except Exception:
        return False
    hdr = [h.strip().replace("\t", "") for h in (header or [])]
    has_spec = any("Spec. Cap.(mAh/g)" in h for h in hdr)
    has_abs = any(h == "Capacity(mAh)" for h in hdr)
    # Abs-only capacity needs mass for specific capacity / energy.
    return bool(has_abs and not has_spec)


def load_cpc_file_arrays(
    path: str,
    *,
    mass_mg: Optional[float] = None,
    is_epc: bool = False,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(cyc_nums, cap_charge, cap_discharge, eff)`` for one CPC/EPC file.

    Raises ``ValueError`` / ``FileNotFoundError`` on unsupported or incomplete input.
    ``.mpt`` always requires a positive ``mass_mg``.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"File not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    file_basename = os.path.basename(path)

    if ext in (".csv", ".xlsx", ".xls"):
        if not is_epc:
            _cpc_header = None
            try:
                _cpc_header, _, _ = _load_csv_header_and_rows(path)
            except Exception:
                pass
            if _cpc_header is not None and is_cs_b_format(_cpc_header):
                return cast(
                    Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
                    read_cs_b_csv_file(path, mode="cpc"),
                )
            cap_x, voltage, cycles, chg_mask, dchg_mask = read_ec_csv_file(
                path, prefer_specific=True
            )
            if _cpc_header is not None:
                _cpc_hdr_s = [h.strip().replace("\t", "") for h in _cpc_header]
                _has_spec = any("Spec. Cap.(mAh/g)" in h for h in _cpc_hdr_s)
                _has_abs = any(h == "Capacity(mAh)" for h in _cpc_hdr_s)
                if _has_abs and not _has_spec:
                    if mass_mg is not None and mass_mg > 0:
                        cap_x = cap_x * (1000.0 / float(mass_mg))
                    else:
                        print(
                            f"CPC mode: {file_basename!r} contains only Capacity(mAh) — "
                            "pass --mass <mg> for specific capacity."
                        )
            return _aggregate_cycle_capacity(cap_x, cycles, chg_mask, dchg_mask)

        header, rows, _ = _load_csv_header_and_rows(path)
        header_stripped = [h.strip().replace("\t", "") for h in header]
        has_chg_en = any("Chg. Spec. Energy(mWh/g)" in h for h in header_stripped)
        has_dch_en = any("DChg. Spec. Energy(mWh/g)" in h for h in header_stripped)
        has_en = any("Spec. Energy(mWh/g)" in h for h in header_stripped)
        if has_chg_en or has_dch_en or has_en:
            cap_x, voltage, cycles, chg_mask, dchg_mask = read_ec_csv_file(
                path, prefer_specific=True
            )
            name_to_idx = {h.strip().replace("\t", ""): i for i, h in enumerate(header)}

            def _idx(name: str):
                return name_to_idx.get(name, None)

            def _col(idx):
                if idx is None:
                    return None
                vals = []
                for row in rows:
                    val = row[idx] if idx < len(row) else ""
                    try:
                        vals.append(float(str(val).strip() or "nan"))
                    except Exception:
                        vals.append(float("nan"))
                return np.array(vals, dtype=float)

            en_chg = _col(_idx("Chg. Spec. Energy(mWh/g)"))
            en_dch = _col(_idx("DChg. Spec. Energy(mWh/g)"))
            en_any = _col(_idx("Spec. Energy(mWh/g)"))
            print(
                f"EPC mode: using Spec. Energy(mWh/g) columns from {file_basename!r} "
                "(no numerical integration)."
            )
            return _aggregate_cycle_energy(
                cap_x, cycles, chg_mask, dchg_mask, en_chg, en_dch, en_any
            )

        cap_x, voltage, cycles, chg_mask, dchg_mask = read_ec_csv_file(
            path, prefer_specific=True
        )
        _epc_has_spec = any("Spec. Cap.(mAh/g)" in h for h in header_stripped)
        _epc_has_abs = any(h == "Capacity(mAh)" for h in header_stripped)
        if _epc_has_abs and not _epc_has_spec:
            if mass_mg is not None and mass_mg > 0:
                cap_x = cap_x * (1000.0 / float(mass_mg))
            else:
                print(
                    f"EPC mode: {file_basename!r} contains only Capacity(mAh) — "
                    "pass --mass <mg> for specific energy (mWh/g)."
                )
        print(
            f"EPC mode: computing energy density by integrating V vs capacity "
            f"for {file_basename!r}."
        )
        return _integrate_cycle_energy(cap_x, voltage, cycles, chg_mask, dchg_mask)

    if ext == ".mpt":
        if mass_mg is None or mass_mg <= 0:
            mode_name = "EPC" if is_epc else "CPC"
            raise ValueError(
                f"{mode_name} mode (.mpt) requires a positive mass in mg "
                "(same as CLI --mass)."
            )
        if is_epc:
            cap_x, voltage, cycles, chg_mask, dchg_mask = cast(
                Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray],
                read_mpt_file(path, mode="gc", mass_mg=mass_mg),
            )
            return _integrate_cycle_energy(
                cap_x, voltage, cycles, chg_mask, dchg_mask
            )
        return cast(
            Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
            read_mpt_file(path, mode="cpc", mass_mg=mass_mg),
        )

    raise ValueError(
        f"Unsupported format for {file_basename!r} (must be .csv, .xlsx, .xls, or .mpt)"
    )


def _unique_cycles(cycles) -> list[int]:
    cyc = np.array(cycles, dtype=int)
    unique = np.unique(cyc)
    unique = unique[np.isfinite(unique)]
    return [int(x) for x in unique] or [1]


def _aggregate_cycle_capacity(cap_x, cycles, chg_mask, dchg_mask):
    cyc = np.array(cycles, dtype=int)
    cyc_nums, cap_charge, cap_discharge, eff = [], [], [], []
    for c in sorted(_unique_cycles(cycles)):
        m_c = cyc == c
        qchg = np.nanmax(cap_x[m_c & chg_mask]) if np.any(m_c & chg_mask) else np.nan
        qdch = np.nanmax(cap_x[m_c & dchg_mask]) if np.any(m_c & dchg_mask) else np.nan
        eta = (
            (qdch / qchg * 100.0)
            if (np.isfinite(qchg) and qchg > 0 and np.isfinite(qdch))
            else np.nan
        )
        cyc_nums.append(c)
        cap_charge.append(qchg)
        cap_discharge.append(qdch)
        eff.append(eta)
    return (
        np.array(cyc_nums, dtype=float),
        np.array(cap_charge, dtype=float),
        np.array(cap_discharge, dtype=float),
        np.array(eff, dtype=float),
    )


def _aggregate_cycle_energy(cap_x, cycles, chg_mask, dchg_mask, en_chg, en_dch, en_any):
    cyc = np.array(cycles, dtype=int)
    cyc_nums, cap_charge, cap_discharge, eff = [], [], [], []
    for c in sorted(_unique_cycles(cycles)):
        m_c = cyc == c
        mask_c = m_c & chg_mask
        mask_d = m_c & dchg_mask
        if en_chg is not None:
            e_c = float(np.nanmax(en_chg[mask_c])) if np.any(mask_c) else float("nan")
        elif en_any is not None:
            e_c = float(np.nanmax(en_any[mask_c])) if np.any(mask_c) else float("nan")
        else:
            e_c = float("nan")
        if en_dch is not None:
            e_d = float(np.nanmax(en_dch[mask_d])) if np.any(mask_d) else float("nan")
        elif en_any is not None:
            e_d = float(np.nanmax(en_any[mask_d])) if np.any(mask_d) else float("nan")
        else:
            e_d = float("nan")
        qchg = np.nanmax(cap_x[mask_c]) if np.any(mask_c) else np.nan
        qdch = np.nanmax(cap_x[mask_d]) if np.any(mask_d) else np.nan
        eta = (
            (qdch / qchg * 100.0)
            if (np.isfinite(qchg) and qchg > 0 and np.isfinite(qdch))
            else np.nan
        )
        cyc_nums.append(c)
        cap_charge.append(e_c)
        cap_discharge.append(e_d)
        eff.append(eta)
    return (
        np.array(cyc_nums, dtype=float),
        np.array(cap_charge, dtype=float),
        np.array(cap_discharge, dtype=float),
        np.array(eff, dtype=float),
    )


def _integrate_cycle_energy(cap_x, voltage, cycles, chg_mask, dchg_mask):
    trapz = getattr(np, "trapezoid", None) or np.trapz
    cyc = np.array(cycles, dtype=int)
    cyc_nums, cap_charge, cap_discharge, eff = [], [], [], []
    for c in sorted(_unique_cycles(cycles)):
        m_c = cyc == c
        mask_c = m_c & chg_mask
        mask_d = m_c & dchg_mask
        if np.count_nonzero(mask_c) >= 2:
            e_c = float(trapz(voltage[mask_c], cap_x[mask_c]))
        else:
            e_c = np.nan
        if np.count_nonzero(mask_d) >= 2:
            e_d = float(trapz(voltage[mask_d], cap_x[mask_d]))
        else:
            e_d = np.nan
        qchg = np.nanmax(cap_x[mask_c]) if np.any(mask_c) else np.nan
        qdch = np.nanmax(cap_x[mask_d]) if np.any(mask_d) else np.nan
        eta = (
            (qdch / qchg * 100.0)
            if (np.isfinite(qchg) and qchg > 0 and np.isfinite(qdch))
            else np.nan
        )
        cyc_nums.append(c)
        cap_charge.append(e_c)
        cap_discharge.append(e_d)
        eff.append(eta)
    return (
        np.array(cyc_nums, dtype=float),
        np.array(cap_charge, dtype=float),
        np.array(cap_discharge, dtype=float),
        np.array(eff, dtype=float),
    )


__all__ = [
    "cpc_file_needs_mass",
    "cpc_supported_extension",
    "load_cpc_file_arrays",
]

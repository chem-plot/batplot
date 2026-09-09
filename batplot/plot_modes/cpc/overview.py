"""CPC overview adapter: extract cycle metrics and run the overview submenu."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import numpy as np

from ..common.overview_metrics import (
    coulombic_efficiency,
    run_overview_submenu,
)


def _scatter_xy(sc) -> tuple[np.ndarray, np.ndarray]:
    if sc is None or not hasattr(sc, "get_offsets"):
        return np.asarray([], dtype=float), np.asarray([], dtype=float)
    try:
        offs = np.asarray(sc.get_offsets(), dtype=float)
    except Exception:
        return np.asarray([], dtype=float), np.asarray([], dtype=float)
    if offs.size == 0:
        return np.asarray([], dtype=float), np.asarray([], dtype=float)
    if offs.ndim != 2 or offs.shape[1] < 2:
        return np.asarray([], dtype=float), np.asarray([], dtype=float)
    return offs[:, 0].astype(float), offs[:, 1].astype(float)


def _qty_label_from_ax(ax) -> str:
    try:
        ylabel = (ax.get_ylabel() or "").lower()
    except Exception:
        ylabel = ""
    if "energy" in ylabel or "mwh" in ylabel:
        return "E"
    return "Q"


def extract_cpc_file_metrics(file_info: Dict[str, Any], *, qty_label: str = "Q") -> Optional[Dict[str, Any]]:
    """Build overview dataset dict from a CPC file_data entry (arrays and/or scatters)."""
    name = (
        file_info.get("display_name")
        or file_info.get("filename")
        or "Data"
    )
    inverted = bool(file_info.get("eff_inverted", False))

    sc_c = file_info.get("sc_charge")
    sc_d = file_info.get("sc_discharge")
    sc_e = file_info.get("sc_eff")
    xc, yc = _scatter_xy(sc_c)
    xd, yd = _scatter_xy(sc_d)
    xe, ye = _scatter_xy(sc_e)

    by_cycle: Dict[float, Dict[str, float]] = {}

    def _key(c: float) -> float:
        return float(round(float(c), 6))

    if xc.size:
        for c, q in zip(xc, yc):
            if not np.isfinite(c):
                continue
            by_cycle.setdefault(_key(c), {})["q_chg"] = float(q)
    if xd.size:
        for c, q in zip(xd, yd):
            if not np.isfinite(c):
                continue
            by_cycle.setdefault(_key(c), {})["q_dch"] = float(q)
    if xe.size:
        for c, e in zip(xe, ye):
            if not np.isfinite(c):
                continue
            by_cycle.setdefault(_key(c), {})["eff"] = float(e)

    # Fall back to stored arrays when scatters are empty / incomplete
    cyc_arr = file_info.get("cyc_nums")
    if cyc_arr is not None:
        cyc_arr = np.asarray(cyc_arr, dtype=float)
        q_chg_arr = np.asarray(file_info.get("cap_charge", []), dtype=float)
        q_dch_arr = np.asarray(file_info.get("cap_discharge", []), dtype=float)
        eff_arr = file_info.get("eff")
        if eff_arr is not None:
            eff_arr = np.asarray(eff_arr, dtype=float)
        else:
            eff_arr = None
        for i, c in enumerate(cyc_arr):
            if not np.isfinite(c):
                continue
            entry = by_cycle.setdefault(_key(c), {})
            if "q_chg" not in entry and i < q_chg_arr.size:
                entry["q_chg"] = float(q_chg_arr[i])
            if "q_dch" not in entry and i < q_dch_arr.size:
                entry["q_dch"] = float(q_dch_arr[i])
            if "eff" not in entry and eff_arr is not None and i < eff_arr.size:
                e_val = float(eff_arr[i])
                if inverted and np.isfinite(e_val):
                    e_val = 200.0 - e_val
                entry["eff"] = e_val

    if not by_cycle:
        return None

    cycles = np.array(sorted(by_cycle.keys()), dtype=float)
    q_chg = np.array([by_cycle[c].get("q_chg", np.nan) for c in cycles], dtype=float)
    q_dch = np.array([by_cycle[c].get("q_dch", np.nan) for c in cycles], dtype=float)
    eff = np.array([by_cycle[c].get("eff", np.nan) for c in cycles], dtype=float)

    # Fill missing CE from capacities (respect invert flag when not taken from scatter)
    missing = ~np.isfinite(eff)
    if np.any(missing):
        computed = coulombic_efficiency(q_chg, q_dch, inverted=inverted)
        eff = np.where(missing, computed, eff)

    return {
        "name": name,
        "cycles": cycles,
        "q_chg": q_chg,
        "q_dch": q_dch,
        "eff": eff,
        "inverted": inverted,
        "filepath": file_info.get("filepath"),
        "qty_label": qty_label,
    }


def build_cpc_overview_datasets(
    file_data: List[Dict[str, Any]],
    *,
    ax=None,
    include_hidden: bool = False,
) -> List[Dict[str, Any]]:
    qty = _qty_label_from_ax(ax) if ax is not None else "Q"
    out: List[Dict[str, Any]] = []
    for f in file_data or []:
        if not include_hidden and not f.get("visible", True):
            continue
        ds = extract_cpc_file_metrics(f, qty_label=qty)
        if ds is not None:
            out.append(ds)
    return out


def run_cpc_overview(
    file_data: List[Dict[str, Any]],
    *,
    ax=None,
    safe_input: Callable[..., str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
    print_file_list: Optional[Callable] = None,
    include_hidden: bool = False,
) -> None:
    datasets = build_cpc_overview_datasets(
        file_data, ax=ax, include_hidden=include_hidden
    )
    if not datasets:
        # Retry including hidden if user may want a specific file
        datasets = build_cpc_overview_datasets(
            file_data, ax=ax, include_hidden=True
        )
        if not datasets:
            print("No CPC cycle data available for overview.")
            return

    def _select() -> Optional[List[int]]:
        # Always list overview-eligible datasets (not raw file_data) so indices match.
        if len(datasets) == 1:
            return [0]
        for i, ds in enumerate(datasets):
            print(f"  {i + 1}: {ds.get('name', f'File {i + 1}')}")
        choice = safe_input(
            colorize_prompt(f"Select file (1-{len(datasets)} / a / q): ")
        ).strip().lower()
        if not choice or choice == "q":
            return None
        if choice in ("a", "all"):
            return list(range(len(datasets)))
        try:
            idx = int(choice) - 1
        except ValueError:
            print("Invalid choice.")
            return None
        if not (0 <= idx < len(datasets)):
            print("Invalid file number.")
            return None
        return [idx]

    run_overview_submenu(
        datasets,
        safe_input=safe_input,
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
        select_indices=_select if len(datasets) > 1 else None,
    )


__all__ = [
    "build_cpc_overview_datasets",
    "extract_cpc_file_metrics",
    "run_cpc_overview",
]

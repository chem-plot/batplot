"""GC overview adapter: derive cycle capacities from cycle_lines and run submenu."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import numpy as np

from ..common.overview_metrics import coulombic_efficiency, run_overview_submenu


def _line_capacity(line, *, capacity_on_x: bool) -> float:
    if line is None:
        return float("nan")
    try:
        # Prefer capacity stash so ions / swapped dual X do not poison Q metrics.
        orig = getattr(line, "_orig_xdata_gc", None)
        if orig is not None:
            arr = np.asarray(orig, dtype=float)
        else:
            data = line.get_xdata() if capacity_on_x else line.get_ydata()
            arr = np.asarray(data, dtype=float)
    except Exception:
        return float("nan")
    if arr.size == 0:
        return float("nan")
    # Use span so overview stays correct for per-cycle (0→Q) and cumulative
    # (offset→offset+Q) GC plots. Absolute max would be wrong under --cum.
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        return float("nan")
    return float(np.nanmax(finite) - np.nanmin(finite))


def extract_gc_cycle_metrics(
    cycle_lines: Dict[Any, Dict[str, Any]],
    *,
    capacity_on_x: bool = True,
    name: str = "Data",
    filepath: Optional[str] = None,
    inverted: bool = False,
    qty_label: str = "Q",
) -> Optional[Dict[str, Any]]:
    if not cycle_lines:
        return None
    cycles_list: List[float] = []
    q_chg_list: List[float] = []
    q_dch_list: List[float] = []
    for cyc in sorted(cycle_lines.keys(), key=lambda x: (float(x) if _is_num(x) else 0, str(x))):
        try:
            cyc_f = float(cyc)
        except (TypeError, ValueError):
            continue
        pair = cycle_lines.get(cyc) or {}
        q_c = _line_capacity(pair.get("charge"), capacity_on_x=capacity_on_x)
        q_d = _line_capacity(pair.get("discharge"), capacity_on_x=capacity_on_x)
        if not (np.isfinite(q_c) or np.isfinite(q_d)):
            continue
        cycles_list.append(cyc_f)
        q_chg_list.append(q_c)
        q_dch_list.append(q_d)
    if not cycles_list:
        return None
    cycles = np.asarray(cycles_list, dtype=float)
    q_chg = np.asarray(q_chg_list, dtype=float)
    q_dch = np.asarray(q_dch_list, dtype=float)
    eff = coulombic_efficiency(q_chg, q_dch, inverted=inverted)
    return {
        "name": name,
        "cycles": cycles,
        "q_chg": q_chg,
        "q_dch": q_dch,
        "eff": eff,
        "inverted": inverted,
        "filepath": filepath,
        "qty_label": qty_label,
    }


def _is_num(x: Any) -> bool:
    try:
        float(x)
        return True
    except (TypeError, ValueError):
        return False


def build_gc_overview_datasets(
    *,
    cycle_lines: Optional[Dict[Any, Dict[str, Any]]] = None,
    file_data: Optional[List[Dict[str, Any]]] = None,
    fig=None,
    include_hidden: bool = False,
) -> List[Dict[str, Any]]:
    capacity_on_x = True
    if fig is not None:
        if bool(getattr(fig, "_ro_active", False)):
            capacity_on_x = False
        else:
            mode = getattr(fig, "_xaxis_mode", "capacity")
            swapped = bool(getattr(fig, "_xaxis_swapped", False))
            if mode == "ions":
                capacity_on_x = False
            elif mode == "dual":
                # Bottom axis is capacity unless swapped (ions on bottom).
                capacity_on_x = not swapped
            else:
                capacity_on_x = True

    out: List[Dict[str, Any]] = []
    if file_data:
        for f in file_data:
            if not include_hidden and not f.get("visible", True):
                continue
            cl = f.get("cycle_lines") or {}
            ds = extract_gc_cycle_metrics(
                cl,
                capacity_on_x=capacity_on_x,
                name=f.get("display_name") or f.get("filename") or "Data",
                filepath=f.get("filepath"),
                inverted=bool(f.get("eff_inverted", False)),
            )
            if ds is not None:
                out.append(ds)
        return out

    if cycle_lines:
        ds = extract_gc_cycle_metrics(
            cycle_lines,
            capacity_on_x=capacity_on_x,
            name="Data",
        )
        if ds is not None:
            out.append(ds)
    return out


def run_gc_overview(
    *,
    cycle_lines: Optional[Dict[Any, Dict[str, Any]]] = None,
    file_data: Optional[List[Dict[str, Any]]] = None,
    fig=None,
    safe_input: Callable[..., str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
    print_file_list: Optional[Callable] = None,
    include_hidden: bool = False,
) -> None:
    datasets = build_gc_overview_datasets(
        cycle_lines=cycle_lines,
        file_data=file_data,
        fig=fig,
        include_hidden=include_hidden,
    )
    if not datasets:
        datasets = build_gc_overview_datasets(
            cycle_lines=cycle_lines,
            file_data=file_data,
            fig=fig,
            include_hidden=True,
        )
        if not datasets:
            print("No GC cycle data available for overview.")
            return

    def _select() -> Optional[List[int]]:
        # Always list overview-eligible datasets so indices match selection.
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
    "build_gc_overview_datasets",
    "extract_gc_cycle_metrics",
    "run_gc_overview",
]

"""Pure helpers for GC/CPC overview: CE, retention, tables, and export."""

from __future__ import annotations

import csv
import os
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

_NEAR_ZERO = 1e-15


def coulombic_efficiency(
    q_chg: Sequence[float],
    q_dch: Sequence[float],
    *,
    inverted: bool = False,
) -> np.ndarray:
    """Return CE% = 100 * Q_dch / Q_chg; optionally invert around 100% (y -> 200 - y)."""
    q_chg_a = np.asarray(q_chg, dtype=float)
    q_dch_a = np.asarray(q_dch, dtype=float)
    if q_chg_a.shape != q_dch_a.shape:
        raise ValueError("q_chg and q_dch must have the same shape")
    with np.errstate(divide="ignore", invalid="ignore"):
        ok = np.isfinite(q_chg_a) & np.isfinite(q_dch_a) & (np.abs(q_chg_a) > _NEAR_ZERO)
        eff = np.where(ok, 100.0 * q_dch_a / q_chg_a, np.nan)
    if inverted:
        eff = np.where(np.isfinite(eff), 200.0 - eff, np.nan)
    return eff.astype(float)


def capacity_retention(
    q: Sequence[float],
    cycles: Sequence[float],
    start: float,
    end: float,
    ref_cycle: Optional[float] = None,
) -> Dict[str, Any]:
    """Discharge (or other) capacity retention over [start, end] vs a reference cycle.

    R(n) = 100 * Q(n) / Q(n_ref). Default n_ref is the first cycle in range.
    """
    cycles_a = np.asarray(cycles, dtype=float)
    q_a = np.asarray(q, dtype=float)
    if cycles_a.size == 0 or q_a.size == 0:
        raise ValueError("No cycle data for retention")
    if cycles_a.shape != q_a.shape:
        raise ValueError("q and cycles must have the same shape")
    start_f = float(start)
    end_f = float(end)
    if end_f < start_f:
        start_f, end_f = end_f, start_f

    mask = (cycles_a >= start_f - 1e-9) & (cycles_a <= end_f + 1e-9) & np.isfinite(cycles_a)
    if not np.any(mask):
        raise ValueError(f"No cycles found in range {start_f:g}–{end_f:g}")

    cyc_r = cycles_a[mask]
    q_r = q_a[mask]
    order = np.argsort(cyc_r)
    cyc_r = cyc_r[order]
    q_r = q_r[order]

    if ref_cycle is None:
        ref_cycle_f = float(cyc_r[0])
    else:
        ref_cycle_f = float(ref_cycle)

    ref_hits = np.where(np.isclose(cyc_r, ref_cycle_f, rtol=0.0, atol=1e-6))[0]
    if ref_hits.size == 0:
        # Allow ref outside printed range but present in full series
        full_hits = np.where(np.isclose(cycles_a, ref_cycle_f, rtol=0.0, atol=1e-6))[0]
        if full_hits.size == 0:
            raise ValueError(f"Reference cycle {ref_cycle_f:g} not found")
        q_ref = float(q_a[full_hits[0]])
    else:
        q_ref = float(q_r[ref_hits[0]])

    if not np.isfinite(q_ref) or abs(q_ref) <= _NEAR_ZERO:
        raise ValueError(f"Reference capacity at cycle {ref_cycle_f:g} is missing or zero")

    with np.errstate(divide="ignore", invalid="ignore"):
        ret = np.where(np.isfinite(q_r), 100.0 * q_r / q_ref, np.nan)

    q_start = float(q_r[0]) if q_r.size else np.nan
    q_end = float(q_r[-1]) if q_r.size else np.nan
    fade_pct = np.nan
    fade_per_cycle = np.nan
    # Fade uses the same reference capacity as total retention (Q_ref), not
    # merely the first cycle in the printed range.
    if np.isfinite(q_ref) and abs(q_ref) > _NEAR_ZERO and np.isfinite(q_end):
        fade_pct = 100.0 * (q_ref - q_end) / q_ref
        n_span = float(cyc_r[-1] - cyc_r[0])
        if n_span > 0:
            fade_per_cycle = fade_pct / n_span

    return {
        "cycles": cyc_r,
        "q": q_r,
        "retention_pct": ret.astype(float),
        "ref_cycle": ref_cycle_f,
        "q_ref": q_ref,
        "q_start": q_start,
        "q_end": q_end,
        "fade_pct": float(fade_pct) if np.isfinite(fade_pct) else np.nan,
        "fade_per_cycle": float(fade_per_cycle) if np.isfinite(fade_per_cycle) else np.nan,
        "start": start_f,
        "end": end_f,
    }


def cycle_summary_stats(
    cycles: Sequence[float],
    q_chg: Sequence[float],
    q_dch: Sequence[float],
    eff: Sequence[float],
    *,
    inverted: bool = False,
) -> Dict[str, Any]:
    """Aggregate first/last capacities, mean CE, irreversible loss, best/worst CE.

    When ``inverted`` is True (CPC ``ie`` display), ``eff`` holds display values
    ``200 - CE``. Best/worst are ranked on **true** CE so labels stay meaningful.
    Reported best/worst percentages are true CE (not inverted display values).
    Mean/std still describe the provided ``eff`` series (display values).
    """
    cycles_a = np.asarray(cycles, dtype=float)
    q_chg_a = np.asarray(q_chg, dtype=float)
    q_dch_a = np.asarray(q_dch, dtype=float)
    eff_a = np.asarray(eff, dtype=float)
    n = int(cycles_a.size)
    if n == 0:
        return {
            "n_cycles": 0,
            "first_cycle": np.nan,
            "last_cycle": np.nan,
            "q_chg_first": np.nan,
            "q_dch_first": np.nan,
            "q_chg_last": np.nan,
            "q_dch_last": np.nan,
            "eff_mean": np.nan,
            "eff_std": np.nan,
            "irr_loss": np.nan,
            "irr_loss_pct": np.nan,
            "best_ce_cycle": np.nan,
            "best_ce": np.nan,
            "worst_ce_cycle": np.nan,
            "worst_ce": np.nan,
        }

    order = np.argsort(cycles_a)
    cycles_a = cycles_a[order]
    q_chg_a = q_chg_a[order]
    q_dch_a = q_dch_a[order]
    eff_a = eff_a[order]

    irr = q_chg_a[0] - q_dch_a[0]
    irr_pct = np.nan
    if np.isfinite(q_chg_a[0]) and abs(q_chg_a[0]) > _NEAR_ZERO and np.isfinite(irr):
        irr_pct = 100.0 * irr / q_chg_a[0]

    finite_eff = np.isfinite(eff_a)
    eff_mean = float(np.nanmean(eff_a)) if np.any(finite_eff) else np.nan
    eff_std = float(np.nanstd(eff_a)) if np.any(finite_eff) else np.nan
    best_ce_cycle = worst_ce_cycle = np.nan
    best_ce = worst_ce = np.nan
    if np.any(finite_eff):
        ranking = (200.0 - eff_a) if inverted else eff_a
        i_best = int(np.nanargmax(ranking))
        i_worst = int(np.nanargmin(ranking))
        best_ce_cycle = float(cycles_a[i_best])
        best_ce = float(ranking[i_best])
        worst_ce_cycle = float(cycles_a[i_worst])
        worst_ce = float(ranking[i_worst])

    return {
        "n_cycles": n,
        "first_cycle": float(cycles_a[0]),
        "last_cycle": float(cycles_a[-1]),
        "q_chg_first": float(q_chg_a[0]),
        "q_dch_first": float(q_dch_a[0]),
        "q_chg_last": float(q_chg_a[-1]),
        "q_dch_last": float(q_dch_a[-1]),
        "eff_mean": eff_mean,
        "eff_std": eff_std,
        "irr_loss": float(irr) if np.isfinite(irr) else np.nan,
        "irr_loss_pct": float(irr_pct) if np.isfinite(irr_pct) else np.nan,
        "best_ce_cycle": best_ce_cycle,
        "best_ce": best_ce,
        "worst_ce_cycle": worst_ce_cycle,
        "worst_ce": worst_ce,
    }


def _fmt_cycle(v: Any, width: int = 5) -> str:
    """Format cycle index as a plain integer (never scientific notation)."""
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return f"{'---':>{width}}"
    if not np.isfinite(fv):
        return f"{'---':>{width}}"
    return f"{int(round(fv)):{width}d}"


def _fmt_num(v: Any, width: int = 10, prec: int = 4) -> str:
    """Fixed-width decimal (never scientific notation)."""
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return f"{'---':>{width}}"
    if not np.isfinite(fv):
        return f"{'---':>{width}}"
    return f"{fv:{width}.{prec}f}"


def _fmt_plain(v: Any, prec: int = 4) -> str:
    """Unpadded number for prose lines."""
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return "---"
    if not np.isfinite(fv):
        return "---"
    if abs(fv - round(fv)) < 1e-9 and abs(fv) < 1e9:
        return str(int(round(fv)))
    text = f"{fv:.{prec}f}".rstrip("0").rstrip(".")
    return text or "0"

def cycle_availability_text(datasets: Sequence[Dict[str, Any]]) -> str:
    """Short 'N cycles (first–last)' summary for prompts."""
    parts: List[str] = []
    for ds in datasets:
        cycles = np.asarray(ds.get("cycles", []), dtype=float)
        cycles = cycles[np.isfinite(cycles)]
        name = str(ds.get("name") or "Data")
        if cycles.size == 0:
            parts.append(f"{name}: no cycles")
            continue
        n = int(cycles.size)
        lo = int(round(float(np.min(cycles))))
        hi = int(round(float(np.max(cycles))))
        if len(datasets) == 1:
            return f"{n} cycles ({lo}–{hi})"
        parts.append(f"{name}: {n} cycles ({lo}–{hi})")
    return "; ".join(parts) if parts else "no cycles"


def format_cycle_table(
    cycles: Sequence[float],
    q_chg: Sequence[float],
    q_dch: Sequence[float],
    eff: Sequence[float],
    *,
    qty_label: str = "Q",
    inverted: bool = False,
    title: Optional[str] = None,
) -> str:
    """Fixed-width per-cycle capacity/efficiency table."""
    cyc_w, q_w, e_w = 5, 12, 10
    h_chg = f"{qty_label}_chg"
    h_dch = f"{qty_label}_dch"
    lines: List[str] = []
    if title:
        lines.append(title)
    note = " (efficiency inverted around 100%)" if inverted else ""
    header = (
        f"{'Cycle':>{cyc_w}}  {h_chg:>{q_w}}  {h_dch:>{q_w}}  {'CE%':>{e_w}}"
    )
    lines.append(header + note)
    lines.append("-" * len(header))
    rows = list(zip(cycles, q_chg, q_dch, eff))
    if not rows:
        lines.append("(no cycles)")
        return "\n".join(lines)
    for c, qc, qd, e in rows:
        lines.append(
            f"{_fmt_cycle(c, cyc_w)}  {_fmt_num(qc, q_w)}  "
            f"{_fmt_num(qd, q_w)}  {_fmt_num(e, e_w)}"
        )
    return "\n".join(lines)


def format_retention_report(
    result: Dict[str, Any],
    *,
    qty_label: str = "Q",
    title: Optional[str] = None,
) -> str:
    """Human-readable retention report including per-cycle rows."""
    cyc_w, q_w, r_w = 5, 12, 12
    lines: List[str] = []
    if title:
        lines.append(title)
    ret = np.asarray(result.get("retention_pct", []), dtype=float)
    total_ret = float(ret[-1]) if ret.size and np.isfinite(ret[-1]) else np.nan
    lines.append(
        f"Reference: cycle {_fmt_plain(result['ref_cycle'])}  "
        f"({qty_label}_ref={_fmt_plain(result['q_ref'])})"
    )
    lines.append(
        f"Range: {_fmt_plain(result['start'])}–{_fmt_plain(result['end'])}  "
        f"({qty_label}_start={_fmt_plain(result['q_start'])}, "
        f"{qty_label}_end={_fmt_plain(result['q_end'])})"
    )
    lines.append(
        f"Total capacity retention: {_fmt_plain(total_ret)}%  "
        f"(= {qty_label}_end / {qty_label}_ref × 100)"
    )
    fade = result.get("fade_pct", np.nan)
    fpc = result.get("fade_per_cycle", np.nan)
    lines.append(
        f"Capacity fade: {_fmt_plain(fade)}% over range  "
        f"(= ({qty_label}_ref − {qty_label}_end) / {qty_label}_ref × 100; "
        f"{_fmt_plain(fpc)}% per cycle)"
    )
    h_q = qty_label
    header = f"{'Cycle':>{cyc_w}}  {h_q:>{q_w}}  {'Retention%':>{r_w}}"
    lines.append(header)
    lines.append("-" * len(header))
    for c, qv, r in zip(result["cycles"], result["q"], result["retention_pct"]):
        lines.append(
            f"{_fmt_cycle(c, cyc_w)}  {_fmt_num(qv, q_w)}  {_fmt_num(r, r_w)}"
        )
    return "\n".join(lines)


def format_summary_stats(
    stats: Dict[str, Any],
    *,
    qty_label: str = "Q",
    inverted: bool = False,
    title: Optional[str] = None,
) -> str:
    lines: List[str] = []
    if title:
        lines.append(title)
    if stats.get("n_cycles", 0) == 0:
        lines.append("No cycle data.")
        return "\n".join(lines)
    inv = " [CE inverted]" if inverted else ""
    lines.append(
        f"Cycles: {stats['n_cycles']}  "
        f"({_fmt_plain(stats['first_cycle'])}–{_fmt_plain(stats['last_cycle'])}){inv}"
    )
    lines.append(
        f"First: {qty_label}_chg={_fmt_plain(stats['q_chg_first'])}  "
        f"{qty_label}_dch={_fmt_plain(stats['q_dch_first'])}"
    )
    lines.append(
        f"Last:  {qty_label}_chg={_fmt_plain(stats['q_chg_last'])}  "
        f"{qty_label}_dch={_fmt_plain(stats['q_dch_last'])}"
    )
    lines.append(
        f"CE mean±std: {_fmt_plain(stats['eff_mean'])} ± "
        f"{_fmt_plain(stats['eff_std'])} %"
    )
    lines.append(
        f"1st-cycle irreversible loss: {_fmt_plain(stats['irr_loss'])} "
        f"({_fmt_plain(stats['irr_loss_pct'])}% of charge)"
    )
    lines.append(
        f"Best CE:  {_fmt_plain(stats['best_ce'])}% at cycle "
        f"{_fmt_plain(stats['best_ce_cycle'])}"
    )
    lines.append(
        f"Worst CE: {_fmt_plain(stats['worst_ce'])}% at cycle "
        f"{_fmt_plain(stats['worst_ce_cycle'])}"
    )
    return "\n".join(lines)


def export_overview_csv(
    path: str,
    cycles: Sequence[float],
    q_chg: Sequence[float],
    q_dch: Sequence[float],
    eff: Sequence[float],
    *,
    retention_pct: Optional[Sequence[float]] = None,
    qty_label: str = "Q",
) -> None:
    """Write overview rows to CSV (UTF-8)."""
    fieldnames = ["cycle", f"{qty_label}_chg", f"{qty_label}_dch", "CE_pct"]
    if retention_pct is not None:
        fieldnames.append("retention_pct")
    parent = os.path.dirname(os.path.abspath(os.path.expanduser(path)))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    path = os.path.abspath(os.path.expanduser(path))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        ret = list(retention_pct) if retention_pct is not None else None
        for i, (c, qc, qd, e) in enumerate(zip(cycles, q_chg, q_dch, eff)):
            row = {
                "cycle": _csv_num(c),
                f"{qty_label}_chg": _csv_num(qc),
                f"{qty_label}_dch": _csv_num(qd),
                "CE_pct": _csv_num(e),
            }
            if ret is not None:
                row["retention_pct"] = _csv_num(ret[i]) if i < len(ret) else ""
            writer.writerow(row)


def export_overview_txt(path: str, text: str) -> None:
    path = os.path.abspath(os.path.expanduser(path))
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
        if not text.endswith("\n"):
            fh.write("\n")


def _csv_num(v: Any) -> str:
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(fv):
        return ""
    return f"{fv:.10g}"


def parse_cycle_span(spec: str) -> Optional[Tuple[Optional[float], Optional[float]]]:
    """Parse 'all', '10', or '10-50' / '10 50'. Returns (start, end) or None if empty/q."""
    s = (spec or "").strip().lower()
    if not s or s in ("q", "cancel"):
        return None
    if s in ("a", "all", "*"):
        return (None, None)
    s = s.replace(",", " ").replace(":", "-")
    if "-" in s and " " not in s.strip("-"):
        parts = [p.strip() for p in s.split("-", 1)]
    else:
        parts = s.split()
    if len(parts) == 1:
        try:
            v = float(parts[0])
            return (v, v)
        except ValueError:
            raise ValueError(f"Invalid cycle spec: {spec!r}")
    if len(parts) >= 2:
        try:
            return (float(parts[0]), float(parts[1]))
        except ValueError as exc:
            raise ValueError(f"Invalid cycle spec: {spec!r}") from exc
    raise ValueError(f"Invalid cycle spec: {spec!r}")


def filter_cycle_slice(
    cycles: np.ndarray,
    q_chg: np.ndarray,
    q_dch: np.ndarray,
    eff: np.ndarray,
    start: Optional[float],
    end: Optional[float],
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if start is None and end is None:
        return cycles, q_chg, q_dch, eff
    lo = float("-inf") if start is None else float(start)
    hi = float("inf") if end is None else float(end)
    if hi < lo:
        lo, hi = hi, lo
    mask = (cycles >= lo - 1e-9) & (cycles <= hi + 1e-9)
    return cycles[mask], q_chg[mask], q_dch[mask], eff[mask]


def default_export_path(filepath: Optional[str], stem_hint: str = "overview") -> str:
    if filepath:
        base = os.path.splitext(os.path.basename(filepath))[0] or stem_hint
        parent = os.path.dirname(os.path.abspath(filepath)) or os.getcwd()
        return os.path.join(parent, f"overview_{base}.csv")
    return os.path.join(os.getcwd(), f"{stem_hint}.csv")


def run_overview_submenu(
    datasets: List[Dict[str, Any]],
    *,
    safe_input: Callable[..., str],
    colorize_menu: Callable[[str], str],
    colorize_prompt: Callable[[str], str],
    select_indices: Optional[Callable[[], Optional[List[int]]]] = None,
) -> None:
    """Interactive overview submenu shared by GC and CPC.

    Each dataset dict needs:
      name, cycles, q_chg, q_dch, eff, inverted (bool), filepath (optional),
      qty_label (default 'Q')
    """
    if not datasets:
        print("No overview data available.")
        return

    last_text = ""
    last_export: Optional[Dict[str, Any]] = None

    def _pick() -> List[Dict[str, Any]]:
        if len(datasets) == 1:
            return list(datasets)
        if select_indices is not None:
            idxs = select_indices()
            if idxs is None:
                return []
            return [datasets[i] for i in idxs if 0 <= i < len(datasets)]
        print("Files:")
        for i, ds in enumerate(datasets):
            print(f"  {i + 1}: {ds.get('name', f'File {i + 1}')}")
        choice = safe_input(
            colorize_prompt(f"Select file (1-{len(datasets)} / a / q): ")
        ).strip().lower()
        if not choice or choice == "q":
            return []
        if choice in ("a", "all"):
            return list(datasets)
        try:
            idx = int(choice) - 1
        except ValueError:
            print("Invalid choice.")
            return []
        if not (0 <= idx < len(datasets)):
            print("Invalid file number.")
            return []
        return [datasets[idx]]

    while True:
        print()
        print(colorize_menu("Overview"))
        print(f"Available: {cycle_availability_text(datasets)}")
        print(colorize_menu("  c: capacity & efficiency table"))
        print(colorize_menu("  r: capacity retention (cycle range)"))
        print(colorize_menu("  s: summary stats"))
        print(colorize_menu("  e: export last table/report (csv/txt)"))
        print(colorize_menu("  q: back"))
        sub = safe_input(colorize_prompt("Overview (c/r/s/e/q): ")).strip().lower()
        if not sub or sub == "q":
            return
        if sub == "c":
            chosen = _pick()
            if not chosen:
                continue
            avail = cycle_availability_text(chosen)
            print(f"Available: {avail}")
            span_in = safe_input(
                colorize_prompt(
                    f"Cycles (all or start-end, available {avail}, q=back): "
                )
            ).strip()
            if span_in.lower() in ("q", "cancel"):
                continue
            try:
                span = parse_cycle_span(span_in or "all")
            except ValueError as exc:
                print(exc)
                continue
            if span is None:
                continue
            start, end = span
            blocks: List[str] = []
            export_cycles: List[float] = []
            export_qc: List[float] = []
            export_qd: List[float] = []
            export_eff: List[float] = []
            qty = "Q"
            for ds in chosen:
                cycles = np.asarray(ds["cycles"], dtype=float)
                q_chg = np.asarray(ds["q_chg"], dtype=float)
                q_dch = np.asarray(ds["q_dch"], dtype=float)
                eff = np.asarray(ds["eff"], dtype=float)
                cycles, q_chg, q_dch, eff = filter_cycle_slice(
                    cycles, q_chg, q_dch, eff, start, end
                )
                qty = str(ds.get("qty_label") or "Q")
                block = format_cycle_table(
                    cycles,
                    q_chg,
                    q_dch,
                    eff,
                    qty_label=qty,
                    inverted=bool(ds.get("inverted")),
                    title=f"=== {ds.get('name', 'Data')} ===",
                )
                print(block)
                blocks.append(block)
                export_cycles.extend(cycles.tolist())
                export_qc.extend(q_chg.tolist())
                export_qd.extend(q_dch.tolist())
                export_eff.extend(eff.tolist())
            last_text = "\n\n".join(blocks)
            last_export = {
                "cycles": export_cycles,
                "q_chg": export_qc,
                "q_dch": export_qd,
                "eff": export_eff,
                "qty_label": qty,
                "filepath": chosen[0].get("filepath"),
                "text": last_text,
            }
            continue

        if sub == "r":
            chosen = _pick()
            if not chosen:
                continue
            avail = cycle_availability_text(chosen)
            print(f"Available: {avail}")
            span_in = safe_input(
                colorize_prompt(
                    f"Cycle range (start end, available {avail}, q=back): "
                )
            ).strip()
            if not span_in or span_in.lower() in ("q", "cancel"):
                continue
            try:
                span = parse_cycle_span(span_in)
            except ValueError as exc:
                print(exc)
                continue
            if span is None or span[0] is None or span[1] is None:
                print("Please provide start and end cycle numbers.")
                continue
            # Narrow Optional[float] for the type checker after the None guard above
            start = float(span[0])
            end = float(span[1])
            ref_in = safe_input(
                colorize_prompt("Reference cycle (Enter=first in range, q=back): ")
            ).strip()
            if ref_in.lower() in ("q", "cancel"):
                continue
            ref_cycle: Optional[float] = None
            if ref_in:
                try:
                    ref_cycle = float(ref_in)
                except ValueError:
                    print("Invalid reference cycle.")
                    continue
            blocks = []
            last_export = None  # clear stale export if all retention runs fail
            for ds in chosen:
                qty = str(ds.get("qty_label") or "Q")
                try:
                    result = capacity_retention(
                        ds["q_dch"],
                        ds["cycles"],
                        start,
                        end,
                        ref_cycle=ref_cycle,
                    )
                except ValueError as exc:
                    print(f"{ds.get('name', 'Data')}: {exc}")
                    continue
                block = format_retention_report(
                    result,
                    qty_label=qty,
                    title=f"=== {ds.get('name', 'Data')} ===",
                )
                print(block)
                blocks.append(block)
                # Build aligned CE for export
                cycles_a = np.asarray(ds["cycles"], dtype=float)
                q_chg_a = np.asarray(ds["q_chg"], dtype=float)
                eff_a = np.asarray(ds["eff"], dtype=float)
                q_chg_r = []
                eff_r = []
                for c in result["cycles"]:
                    hits = np.where(np.isclose(cycles_a, c, rtol=0.0, atol=1e-6))[0]
                    if hits.size:
                        q_chg_r.append(float(q_chg_a[hits[0]]))
                        eff_r.append(float(eff_a[hits[0]]))
                    else:
                        q_chg_r.append(np.nan)
                        eff_r.append(np.nan)
                last_export = {
                    "cycles": result["cycles"].tolist(),
                    "q_chg": q_chg_r,
                    "q_dch": result["q"].tolist(),
                    "eff": eff_r,
                    "retention_pct": result["retention_pct"].tolist(),
                    "qty_label": qty,
                    "filepath": ds.get("filepath"),
                    "text": block,
                }
            last_text = "\n\n".join(blocks)
            continue

        if sub == "s":
            chosen = _pick()
            if not chosen:
                continue
            avail = cycle_availability_text(chosen)
            print(f"Available: {avail}")
            blocks = []
            for ds in chosen:
                stats = cycle_summary_stats(
                    ds["cycles"],
                    ds["q_chg"],
                    ds["q_dch"],
                    ds["eff"],
                    inverted=bool(ds.get("inverted")),
                )
                block = format_summary_stats(
                    stats,
                    qty_label=str(ds.get("qty_label") or "Q"),
                    inverted=bool(ds.get("inverted")),
                    title=f"=== {ds.get('name', 'Data')} ===",
                )
                print(block)
                blocks.append(block)
            last_text = "\n\n".join(blocks)
            if chosen:
                ds0 = chosen[0]
                last_export = {
                    "cycles": list(ds0["cycles"]),
                    "q_chg": list(ds0["q_chg"]),
                    "q_dch": list(ds0["q_dch"]),
                    "eff": list(ds0["eff"]),
                    "qty_label": str(ds0.get("qty_label") or "Q"),
                    "filepath": ds0.get("filepath"),
                    "text": last_text,
                }
            continue

        if sub == "e":
            if not last_export and not last_text:
                print("Nothing to export yet. Run c, r, or s first.")
                continue
            default = default_export_path(
                (last_export or {}).get("filepath"), "overview"
            )
            path_in = safe_input(
                colorize_prompt(f"Export path [{default}] (q=back): ")
            ).strip()
            if path_in.lower() in ("q", "cancel"):
                continue
            path = path_in or default
            path = os.path.expanduser(path)
            ext = os.path.splitext(path)[1].lower()
            try:
                if ext == ".txt" or (ext == "" and last_text and not last_export):
                    if not path.lower().endswith(".txt"):
                        path = path + ("" if ext else ".txt")
                    export_overview_txt(path, last_text or (last_export or {}).get("text", ""))
                else:
                    if not ext:
                        path = path + ".csv"
                    le = last_export or {}
                    export_overview_csv(
                        path,
                        le.get("cycles", []),
                        le.get("q_chg", []),
                        le.get("q_dch", []),
                        le.get("eff", []),
                        retention_pct=le.get("retention_pct"),
                        qty_label=str(le.get("qty_label") or "Q"),
                    )
                print(f"Exported overview to {path}")
            except Exception as exc:
                print(f"Export failed: {exc}")
            continue

        print("Unknown overview key.")


__all__ = [
    "capacity_retention",
    "coulombic_efficiency",
    "cycle_availability_text",
    "cycle_summary_stats",
    "default_export_path",
    "export_overview_csv",
    "export_overview_txt",
    "filter_cycle_slice",
    "format_cycle_table",
    "format_retention_report",
    "format_summary_stats",
    "parse_cycle_span",
    "run_overview_submenu",
]

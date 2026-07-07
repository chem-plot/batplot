"""Interactive setup prompts for histogram mode."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np  # type: ignore[import]

from ..common.terminal import prompt_float, safe_input
from .load import (
    TableData,
    auto_range,
    build_bin_edges,
    column_stats,
    resolve_column_index,
    suggest_bin_width,
)


@dataclass
class HistoSetup:
    column_index: int
    column_name: str
    values: np.ndarray
    xmin: float
    xmax: float
    bin_edges: np.ndarray

    @property
    def bin_width(self) -> float:
        if self.bin_edges.size < 2:
            return 1.0
        return float(self.bin_edges[1] - self.bin_edges[0])

    @property
    def n_bins(self) -> int:
        return max(0, int(self.bin_edges.size) - 1)


def _parse_range_input(text: str, values: np.ndarray) -> tuple[float, float] | None:
    raw = text.strip().lower()
    if not raw or raw == "q":
        return None
    if raw in ("auto", "a", "default"):
        return auto_range(values)
    parts = raw.replace(",", " ").split()
    if len(parts) != 2:
        return None
    try:
        xmin = float(parts[0])
        xmax = float(parts[1])
    except ValueError:
        return None
    if xmax <= xmin:
        return None
    return xmin, xmax


def _parse_bin_input(text: str, xmin: float, xmax: float, n: int) -> tuple[float | None, int | None]:
    raw = text.strip().lower()
    if not raw or raw == "q":
        return None, None
    if raw.startswith("bins=") or raw.startswith("bins "):
        token = raw.split("=", 1)[-1].strip() if "=" in raw else raw.split(None, 1)[-1].strip()
        try:
            return None, int(token)
        except ValueError:
            return None, None
    try:
        width = float(raw)
        if width > 0:
            return width, None
    except ValueError:
        pass
    return suggest_bin_width(xmin, xmax, n), None


def run_histo_wizard(
    table: TableData,
    *,
    fixed_col: int | None = None,
    hint_col: int | None = None,
    allow_keep_column: bool = False,
) -> HistoSetup | None:
    """Ask which column, range, and bin width to use."""
    if fixed_col is not None:
        col_index = fixed_col
        try:
            table.column_values(col_index)
        except ValueError as exc:
            print(exc)
            return None
    else:
        table.preview_columns()
        while True:
            if hint_col is not None and allow_keep_column:
                prompt = (
                    f"\nWhich column to histogram? "
                    f"(number or name, Enter=keep [{hint_col}], q=cancel): "
                )
            else:
                prompt = "\nWhich column to histogram? (column number or name, q=cancel): "
            choice = safe_input(prompt, cancel_on_interrupt=True).strip()
            if not choice:
                if allow_keep_column and hint_col is not None:
                    col_index = hint_col
                else:
                    print("Enter a column number or name.")
                    continue
            elif choice.lower() in ("q", "quit", "cancel"):
                return None
            else:
                try:
                    col_index = resolve_column_index(table, choice)
                except ValueError as exc:
                    print(exc)
                    continue
            try:
                table.column_values(col_index)
                break
            except ValueError as exc:
                print(exc)

    values = table.column_values(col_index)
    headers = table.padded_headers()
    col_name = headers[col_index - 1].strip() or f"column {col_index}"
    stats = column_stats(values)
    print(
        f"\nColumn [{col_index}] {col_name!r}: "
        f"n={stats['n']}  min={stats['min']:.4g}  max={stats['max']:.4g}  "
        f"mean={stats['mean']:.4g}  median={stats['median']:.4g}"
    )

    auto_xmin, auto_xmax = auto_range(values)
    while True:
        range_prompt = (
            f"Histogram range xmin xmax [auto -> {auto_xmin:.4g} {auto_xmax:.4g}]: "
        )
        range_text = safe_input(range_prompt, cancel_on_interrupt=True).strip()
        if range_text.lower() in ("q", "quit", "cancel"):
            return None
        if not range_text or range_text.lower() in ("auto", "a", "default"):
            xmin, xmax = auto_xmin, auto_xmax
            break
        parsed = _parse_range_input(range_text, values)
        if parsed is None:
            print("Enter 'auto' or two numbers: xmin xmax")
            continue
        xmin, xmax = parsed
        break

    default_width = suggest_bin_width(xmin, xmax, stats["n"])
    while True:
        bin_prompt = (
            f"Bin width (segment size) [{default_width:.4g}] "
            f"or bins=N [{max(8, int(round((xmax - xmin) / default_width)))}]: "
        )
        bin_text = safe_input(bin_prompt, cancel_on_interrupt=True).strip()
        if bin_text.lower() in ("q", "quit", "cancel"):
            return None
        if not bin_text:
            bin_width, n_bins = default_width, None
        else:
            bin_width, n_bins = _parse_bin_input(bin_text, xmin, xmax, stats["n"])
            if bin_width is None and n_bins is None:
                print("Enter a positive bin width or bins=N")
                continue
        try:
            edges = build_bin_edges(xmin, xmax, bin_width=bin_width, n_bins=n_bins)
        except ValueError as exc:
            print(exc)
            continue
        print(
            f"Preview: {edges.size - 1} bins from {edges[0]:.4g} to {edges[-1]:.4g} "
            f"(width ≈ {edges[1] - edges[0]:.4g})"
        )
        confirm = safe_input("Proceed? [Y/n]: ", cancel_on_interrupt=True).strip().lower()
        if confirm in ("", "y", "yes"):
            return HistoSetup(
                column_index=col_index,
                column_name=col_name,
                values=values,
                xmin=float(edges[0]),
                xmax=float(edges[-1]),
                bin_edges=edges,
            )
        print("Adjust range or bin width.")

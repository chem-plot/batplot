"""Tests for GC --cum (cumulative / throughput capacity)."""

from __future__ import annotations

from argparse import Namespace
from pathlib import Path

import numpy as np
import pytest

from batplot.args import parse_args
from batplot.plot_modes.electrochem.capacity_cum import (
    apply_gc_capacity_mode,
    cumulative_capacity_xlabel,
    make_cumulative_capacity,
)
from batplot.plot_modes.electrochem.overview import extract_gc_cycle_metrics


def test_parse_cum_flag():
    args = parse_args(["f.csv", "--gc", "--cum"])
    assert args.gc is True
    assert args.cum is True


def test_make_cumulative_capacity_end_to_end():
    # Two half-cycles: charge 0→10, discharge 0→9
    cap = np.array([0.0, 5.0, 10.0, 0.0, 4.5, 9.0])
    chg = np.array([True, True, True, False, False, False])
    dch = np.array([False, False, False, True, True, True])
    cum = make_cumulative_capacity(cap, chg, dch)
    np.testing.assert_allclose(cum[:3], [0.0, 5.0, 10.0])
    np.testing.assert_allclose(cum[3:], [10.0, 14.5, 19.0])
    assert cum[2] == pytest.approx(cum[3])  # connected at charge→discharge


def test_apply_passthrough_without_cum():
    cap = np.array([0.0, 1.0])
    chg = np.array([True, True])
    dch = np.array([False, False])
    args = Namespace(cum=False)
    out, lab, flag = apply_gc_capacity_mode(
        args, cap, chg, dch, r"Specific Capacity (mAh g$^{-1}$)"
    )
    assert flag is False
    assert out is cap
    assert "Cumulative" not in lab


def test_xlabel_cumulative():
    assert "Cumulative" in cumulative_capacity_xlabel(
        r"Specific Capacity (mAh g$^{-1}$)"
    )


def test_overview_span_works_for_cumulative_lines():
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    # Cumulative segment for cycle 1 charge: 100→200 (span 100)
    (c,) = ax.plot([100.0, 200.0], [3.0, 4.0])
    (d,) = ax.plot([200.0, 290.0], [4.0, 3.0])
    ds = extract_gc_cycle_metrics({1: {"charge": c, "discharge": d}}, capacity_on_x=True)
    assert ds is not None
    assert ds["q_chg"][0] == pytest.approx(100.0)
    assert ds["q_dch"][0] == pytest.approx(90.0)
    plt.close(fig)


def test_gc_cum_route_saves_figure(tmp_path: Path, monkeypatch):
    """Smoke: --gc --cum on a tiny Neware-like CSV writes a figure."""
    csv = tmp_path / "tiny_gc.csv"
    csv.write_text(
        "Voltage(V),Current(mA),Step Type,Spec. Cap.(mAh/g)\n"
        "3.0,0.5,CC Chg,0\n"
        "3.2,0.5,CC Chg,50\n"
        "3.4,0.5,CC Chg,100\n"
        "3.2,-0.5,CC DChg,100\n"
        "3.0,-0.5,CC DChg,50\n"
        "2.8,-0.5,CC DChg,0\n",
        encoding="utf-8",
    )

    from batplot.cli import main

    monkeypatch.chdir(tmp_path)
    out = tmp_path / "cum.png"
    try:
        rc = main([str(csv.name), "--gc", "--cum", "--out", str(out.name)])
    except SystemExit as exc:
        rc = exc.code
    assert (rc is None) or (rc == 0)
    assert out.is_file() and out.stat().st_size > 0


def test_make_cumulative_falling_discharge():
    """Shared Spec. Cap. column that falls on discharge still advances x."""
    cap = np.array([0.0, 50.0, 100.0, 100.0, 50.0, 0.0])
    chg = np.array([True, True, True, False, False, False])
    dch = np.array([False, False, False, True, True, True])
    cum = make_cumulative_capacity(cap, chg, dch)
    np.testing.assert_allclose(cum[:3], [0.0, 50.0, 100.0])
    np.testing.assert_allclose(cum[3:], [100.0, 150.0, 200.0])

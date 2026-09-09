"""Unit tests for overview metrics (CE, retention, formatting, export)."""

from __future__ import annotations

import os

import numpy as np
import pytest

from batplot.plot_modes.common.overview_metrics import (
    capacity_retention,
    coulombic_efficiency,
    cycle_summary_stats,
    export_overview_csv,
    export_overview_txt,
    filter_cycle_slice,
    format_cycle_table,
    format_retention_report,
    parse_cycle_span,
)


def test_coulombic_efficiency_basic_and_invert():
    q_chg = [100.0, 100.0, 0.0, np.nan]
    q_dch = [95.0, 105.0, 10.0, 50.0]
    eff = coulombic_efficiency(q_chg, q_dch)
    assert eff[0] == pytest.approx(95.0)
    assert eff[1] == pytest.approx(105.0)
    assert np.isnan(eff[2])
    assert np.isnan(eff[3])
    inv = coulombic_efficiency(q_chg, q_dch, inverted=True)
    assert inv[0] == pytest.approx(105.0)
    assert inv[1] == pytest.approx(95.0)


def test_capacity_retention_default_ref_and_fade():
    cycles = [1, 2, 3, 4, 5]
    q = [100.0, 98.0, 96.0, 94.0, 90.0]
    res = capacity_retention(q, cycles, 2, 5)
    assert res["ref_cycle"] == 2.0
    assert res["q_ref"] == pytest.approx(98.0)
    assert res["retention_pct"][0] == pytest.approx(100.0)
    assert res["retention_pct"][-1] == pytest.approx(100.0 * 90.0 / 98.0)
    assert res["fade_pct"] == pytest.approx(100.0 * (98.0 - 90.0) / 98.0)
    assert res["fade_per_cycle"] == pytest.approx(res["fade_pct"] / 3.0)


def test_capacity_retention_custom_ref_and_errors():
    cycles = np.array([1.0, 2.0, 3.0])
    q = np.array([100.0, 95.0, 90.0])
    res = capacity_retention(q, cycles, 1, 3, ref_cycle=1)
    assert res["retention_pct"][-1] == pytest.approx(90.0)
    with pytest.raises(ValueError, match="not found"):
        capacity_retention(q, cycles, 1, 3, ref_cycle=99)
    with pytest.raises(ValueError, match="No cycles"):
        capacity_retention(q, cycles, 10, 20)
    with pytest.raises(ValueError, match="zero"):
        capacity_retention([0.0, 1.0], [1.0, 2.0], 1, 2, ref_cycle=1)


def test_cycle_summary_stats():
    cycles = [1, 2, 3]
    q_chg = [110.0, 100.0, 100.0]
    q_dch = [100.0, 99.0, 98.0]
    eff = coulombic_efficiency(q_chg, q_dch)
    stats = cycle_summary_stats(cycles, q_chg, q_dch, eff)
    assert stats["n_cycles"] == 3
    assert stats["irr_loss"] == pytest.approx(10.0)
    assert stats["irr_loss_pct"] == pytest.approx(100.0 * 10.0 / 110.0)
    assert stats["best_ce_cycle"] == 2.0 or stats["best_ce"] >= stats["worst_ce"]


def test_cycle_summary_stats_best_worst_with_inverted_display():
    """Best/worst must rank true CE even when eff is inverted display (200-CE)."""
    cycles = [1, 2, 3]
    # True CE: 90, 99, 95 → best cycle 2, worst cycle 1
    true_eff = np.array([90.0, 99.0, 95.0])
    inv_eff = 200.0 - true_eff
    stats = cycle_summary_stats(cycles, [100, 100, 100], [90, 99, 95], inv_eff, inverted=True)
    assert stats["best_ce_cycle"] == 2.0
    assert stats["best_ce"] == pytest.approx(99.0)
    assert stats["worst_ce_cycle"] == 1.0
    assert stats["worst_ce"] == pytest.approx(90.0)


def test_capacity_retention_fade_uses_q_ref_not_range_start():
    cycles = [1, 2, 3, 4]
    q = [100.0, 98.0, 95.0, 90.0]
    # Range 2–4 but ref cycle 1 → fade vs 100, not vs 98
    res = capacity_retention(q, cycles, 2, 4, ref_cycle=1)
    assert res["q_ref"] == pytest.approx(100.0)
    assert res["fade_pct"] == pytest.approx(100.0 * (100.0 - 90.0) / 100.0)


def test_parse_and_filter_cycle_span():
    assert parse_cycle_span("all") == (None, None)
    assert parse_cycle_span("10-20") == (10.0, 20.0)
    assert parse_cycle_span("5 15") == (5.0, 15.0)
    assert parse_cycle_span("q") is None
    cycles = np.array([1.0, 2.0, 3.0, 4.0])
    q = np.array([10.0, 20.0, 30.0, 40.0])
    c, a, b, e = filter_cycle_slice(cycles, q, q, q, 2, 3)
    assert list(c) == [2.0, 3.0]


def test_format_and_export(tmp_path):
    text = format_cycle_table([1, 2], [100, 99], [95, 94], [95, 94.95], inverted=True)
    assert "inverted" in text
    assert "95" in text
    ret = capacity_retention(
        [203.2, 184.4, 138.8], [1, 10, 30], 1, 30, ref_cycle=1
    )
    report = format_retention_report(ret, qty_label="Q")
    assert "1e+" not in report
    assert "Total capacity retention:" in report
    assert "68.3071" in report or "68.31" in report
    lines = [ln for ln in report.splitlines() if ln.strip()]
    header = next(ln for ln in lines if ln.lstrip().startswith("Cycle"))
    row10 = next(ln for ln in lines if ln.lstrip().startswith("10"))
    # Same fixed-width layout: Cycle / Q / Retention% columns line up
    assert header.find("Cycle") == row10.find("10") or header.index("C") == 0
    assert abs(header.index("Retention%") - row10.rfind(".")) < 20
    csv_path = tmp_path / "ov.csv"
    export_overview_csv(
        str(csv_path),
        [1, 2],
        [100, 99],
        [95, 94],
        [95, 94.95],
        retention_pct=[100, 98.9],
    )
    body = csv_path.read_text(encoding="utf-8")
    assert "cycle" in body and "retention_pct" in body
    txt_path = tmp_path / "ov.txt"
    export_overview_txt(str(txt_path), text)
    assert "Cycle" in txt_path.read_text(encoding="utf-8")


def test_cycle_availability_and_no_scientific_cycles():
    from batplot.plot_modes.common.overview_metrics import cycle_availability_text

    ds = {
        "name": "cell",
        "cycles": np.arange(1, 31, dtype=float),
        "q_chg": np.ones(30),
        "q_dch": np.ones(30),
        "eff": np.full(30, 99.0),
    }
    assert cycle_availability_text([ds]) == "30 cycles (1–30)"
    table = format_cycle_table(
        ds["cycles"], ds["q_chg"], ds["q_dch"], ds["eff"]
    )
    assert "1e+" not in table
    assert any(ln.strip().startswith("10 ") for ln in table.splitlines())


def test_retention_matches_p_b448_discharge_spec_cap():
    """Spot-check vs P_B448_rate.csv CC DChg Spec. Cap. (batplot cycle ≈ file Cycle Index - 1)."""
    import pandas as pd

    path = (
        "/Users/tiandai/Library/CloudStorage/OneDrive-UniversitetetiOslo/My files/"
        "Li2FeSeO_processing/EC/P_B448_rate.csv"
    )
    try:
        df = pd.read_csv(path)
    except FileNotFoundError:
        pytest.skip("user EC file not present")
    g = (
        df[df["Step Type"] == "CC DChg"]
        .groupby("Cycle Index")["Spec. Cap.(mAh/g)"]
        .max()
    )
    # First discharge in file is Cycle Index 2 → batplot cycle 1
    file_cycles = g.loc[2:31]
    q = file_cycles.to_numpy(dtype=float)
    cycles = np.arange(1, len(q) + 1, dtype=float)
    res = capacity_retention(q, cycles, 1, 30, ref_cycle=1)
    assert res["q_ref"] == pytest.approx(203.19, abs=0.02)
    assert res["retention_pct"][0] == pytest.approx(100.0)
    # File has no Retention column; total retention is Q_last/Q_ref
    assert float(res["retention_pct"][-1]) == pytest.approx(
        100.0 * q[-1] / q[0], rel=1e-6
    )

def test_gc_and_cpc_extract_adapters():
    import matplotlib.pyplot as plt

    from batplot.plot_modes.cpc.overview import extract_cpc_file_metrics
    from batplot.plot_modes.electrochem.overview import extract_gc_cycle_metrics

    fig, ax = plt.subplots()
    (c,) = ax.plot([0.0, 100.0], [3.0, 4.0])
    (d,) = ax.plot([0.0, 90.0], [4.0, 3.0])
    ds = extract_gc_cycle_metrics({1: {"charge": c, "discharge": d}}, capacity_on_x=True)
    assert ds is not None
    assert ds["q_chg"][0] == pytest.approx(100.0)
    assert ds["eff"][0] == pytest.approx(90.0)

    sc_c = ax.scatter([1, 2], [100.0, 98.0])
    sc_d = ax.scatter([1, 2], [95.0, 94.0])
    sc_e = ax.scatter([1, 2], [105.0, 104.0])
    cpc = extract_cpc_file_metrics(
        {
            "filename": "cell",
            "sc_charge": sc_c,
            "sc_discharge": sc_d,
            "sc_eff": sc_e,
            "eff_inverted": True,
            "visible": True,
        }
    )
    assert cpc is not None
    assert cpc["eff"][0] == pytest.approx(105.0)
    assert cpc["inverted"] is True
    plt.close(fig)

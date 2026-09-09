"""Operando peak search stays consistent with Options ``u`` axis units."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.operando import axis_units as AU
from batplot.plot_modes.operando import peaks as PK
from batplot.plot_modes.xy.axis_units import convert_x_array, default_xlabel


def _make_q_imshow_with_peak(q_lo=1.0, q_hi=5.0, n_cols=81, n_rows=3, q_peak=3.0):
    fig, ax = plt.subplots()
    x = np.linspace(q_lo, q_hi, n_cols)
    row = np.exp(-0.5 * ((x - q_peak) / 0.25) ** 2)
    Z = np.vstack([row * (i + 1) for i in range(n_rows)])
    im = ax.imshow(
        Z,
        aspect="auto",
        origin="lower",
        extent=(q_lo, q_hi, 0, n_rows - 1),
        cmap="viridis",
        interpolation="nearest",
    )
    AU.set_operando_axis_mode(fig, "Q", wavelength=0.709)
    ax.set_xlabel(default_xlabel("Q"))
    return fig, ax, im, q_peak


def test_extract_x_axis_matches_extent_after_u_to_d():
    fig, ax, im, q_peak = _make_q_imshow_with_peak()
    AU.apply_operando_axis_unit_conversion(
        fig=fig, ax=ax, im=im, frm="Q", to="d", wl=0.709, redraw_cif=False,
    )
    data, x_axis, x_min, x_max = PK.extract_operando_peak_data(im)
    assert getattr(fig, "_operando_axis_mode") == "d"
    d_expected = float(convert_x_array(np.array([q_peak]), frm="Q", to="d", wl=None)[0])
    # Peak column in remeshed image should land near d_expected on x_axis
    peak_col = int(np.nanargmax(data[0]))
    assert x_min <= x_axis[peak_col] <= x_max
    np.testing.assert_allclose(x_axis[peak_col], d_expected, rtol=0.08, atol=0.08)
    plt.close(fig)


def test_find_peaks_in_d_domain_after_u():
    fig, ax, im, q_peak = _make_q_imshow_with_peak()
    AU.apply_operando_axis_unit_conversion(
        fig=fig, ax=ax, im=im, frm="Q", to="d", wl=0.709, redraw_cif=False,
    )
    data, x_axis, x_min, x_max = PK.extract_operando_peak_data(im)
    d_peak = float(convert_x_array(np.array([q_peak]), frm="Q", to="d", wl=None)[0])

    def fake_find_peaks(profile, **_kwargs):
        return np.array([int(np.nanargmax(profile))]), {}

    results = PK.find_operando_peaks(
        data,
        x_axis,
        x_range_min=x_min,
        x_range_max=x_max,
        find_peaks_func=fake_find_peaks,
    )
    assert results
    found_d = float(results[0][1])
    np.testing.assert_allclose(found_d, d_peak, rtol=0.08, atol=0.08)
    plt.close(fig)


def test_export_includes_bragg_triplet_with_wl(tmp_path: Path):
    fig, ax, im, q_peak = _make_q_imshow_with_peak()
    mode, wl = PK.resolve_peak_axis_context(fig, ax)
    assert mode == "Q"
    assert wl == 0.709
    results = [(0, q_peak, 1.23)]
    out = tmp_path / "peaks.txt"
    PK.write_peak_results(
        str(out),
        results,
        include_intensity=True,
        axis_mode=mode,
        wavelength=wl,
    )
    text = out.read_text(encoding="utf-8")
    assert "axis_mode=Q" in text
    assert "2theta_deg" in text
    assert "Q_A^-1" in text
    assert "d_A" in text
    trip = PK.peak_bragg_triplet(q_peak, axis_mode="Q", wavelength=0.709)
    assert trip["Q"] is not None and abs(trip["Q"] - q_peak) < 1e-9
    assert trip["2theta"] is not None and trip["d"] is not None
    assert f"{trip['2theta']:.6f}" in text
    assert f"{trip['d']:.6f}" in text
    plt.close(fig)


def test_export_without_wl_keeps_single_position_column(tmp_path: Path):
    results = [(0, 2.5), (1, 2.6)]
    out = tmp_path / "peaks.txt"
    PK.write_peak_results(str(out), results, axis_mode="Q", wavelength=None)
    text = out.read_text(encoding="utf-8")
    assert "2theta_deg" not in text
    assert "Q (Å⁻¹)" in text or "Peak position" in text
    assert "2.500000" in text


def test_peak_bragg_triplet_roundtrip_modes():
    wl = 0.709
    q = 2.5
    from_q = PK.peak_bragg_triplet(q, axis_mode="Q", wavelength=wl)
    tth = from_q["2theta"]
    d = from_q["d"]
    assert tth is not None and d is not None
    from_tth = PK.peak_bragg_triplet(tth, axis_mode="2theta", wavelength=wl)
    from_d = PK.peak_bragg_triplet(d, axis_mode="d", wavelength=wl)
    np.testing.assert_allclose(from_tth["Q"], q, rtol=1e-6)
    np.testing.assert_allclose(from_d["Q"], q, rtol=1e-6)
    np.testing.assert_allclose(from_tth["d"], d, rtol=1e-6)
    np.testing.assert_allclose(from_d["2theta"], tth, rtol=1e-6)

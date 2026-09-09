"""CIF tick positions must match Bragg / reciprocal-space crystallography."""

from __future__ import annotations

from types import SimpleNamespace

import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.xy import axis_units as AU


def test_peaks_q_to_domain_matches_bragg_cubic():
    """Cubic a=5 Å (100): Q=2π/a, 2θ from Bragg, d=a."""
    a = 5.0
    q100 = 2.0 * np.pi / a
    wl = 1.5406
    tth = AU.peaks_Q_to_domain([q100], "2theta", wl)
    assert len(tth) == 1
    # Bragg: 2 d sinθ = λ  →  2θ = 2 arcsin(λ / (2a))
    tth_exp = 2.0 * np.degrees(np.arcsin(wl / (2.0 * a)))
    np.testing.assert_allclose(tth[0], tth_exp, rtol=1e-10, atol=1e-10)
    # Also equals Q→2θ via 4π sinθ / λ
    np.testing.assert_allclose(tth[0], AU.Q_to_twotheta(np.array([q100]), wl)[0], rtol=1e-12)
    d = AU.peaks_Q_to_domain([q100], "d")
    np.testing.assert_allclose(d[0], a, rtol=1e-12)
    q_back = AU.domain_peak_to_Q(tth[0], "2theta", wl)
    np.testing.assert_allclose(q_back, q100, rtol=1e-10)


def test_peaks_unknown_mode_no_invent_q():
    """Blank/unknown axis must not place Q peaks (would misplace on 2θ axes)."""
    assert AU.peaks_Q_to_domain([1.0, 2.0], "") == []
    assert AU.peaks_Q_to_domain([1.0, 2.0], "unknown") == []
    assert AU.peaks_Q_to_domain([1.0, 2.0], "energy") == []
    assert AU.domain_peak_to_Q(1.0, "") is None
    # Explicit Q still works
    assert AU.peaks_Q_to_domain([1.5], "Q") == [1.5]


def test_resolve_cif_draw_wavelength_prefers_fig_over_cu_ka():
    fig = plt.figure()
    AU.set_xy_axis_mode(fig, "2theta", wavelength=0.7093)
    wl = AU.resolve_cif_draw_wavelength(fig=fig, args=SimpleNamespace(wl=None), axis_mode="2theta")
    assert abs(wl - 0.7093) < 1e-12
    # No fig λ → Cu Kα last-resort BC default
    fig2 = plt.figure()
    wl2 = AU.resolve_cif_draw_wavelength(
        fig=fig2, args=SimpleNamespace(wl=None), axis_mode="2theta", warn=False,
    )
    assert abs(wl2 - AU.CU_KA_ANGSTROM) < 1e-12
    plt.close(fig)
    plt.close(fig2)


def test_resolve_cif_dual_wl_file_info_uses_original_for_q_domain_math():
    """When converting ticks via Q→2θ, λ must be the plot Bragg λ (λ1 for Q data)."""
    fig = plt.figure()
    AU.set_xy_axis_mode(fig, "Q", wavelength=1.54)  # stale λ2
    info = [{"original_wl": 0.709, "conversion_wl": 1.54, "final_wl": 1.54}]
    # For 2θ tick placement after viewing Q-built data, resolve with mode from convert
    wl = AU.resolve_wavelength(
        fig=fig, args=SimpleNamespace(wl=None),
        file_wavelength_info=info, axis_mode="Q",
    )
    assert abs(wl - 0.709) < 1e-12
    plt.close(fig)


def test_after_u_convert_ticks_stay_bragg():
    """Peaks stay in Q; domain map after Options ``u`` remains Bragg-correct."""
    a = 4.0
    q100 = 2.0 * np.pi / a
    wl = 0.7093
    peaks = [q100]
    tth = AU.peaks_Q_to_domain(peaks, "2theta", wl)
    d = AU.peaks_Q_to_domain(peaks, "d")
    q = AU.peaks_Q_to_domain(peaks, "Q")
    # Round-trip domain → Q
    np.testing.assert_allclose(AU.domain_peak_to_Q(tth[0], "2theta", wl), q100, rtol=1e-10)
    np.testing.assert_allclose(AU.domain_peak_to_Q(d[0], "d"), q100, rtol=1e-10)
    np.testing.assert_allclose(AU.domain_peak_to_Q(q[0], "Q"), q100, rtol=1e-12)

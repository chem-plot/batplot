"""Tests for operando Options ``u`` axis unit convert (XRD 2θ ↔ Q ↔ d)."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from batplot.plot_modes.operando import axis_units as AU
from batplot.plot_modes.operando.menu import build_operando_ec_menu_columns, print_operando_ec_menu
from batplot.plot_modes.xy.axis_units import convert_x_array, default_xlabel


def _make_q_imshow(q_lo=1.0, q_hi=5.0, n_cols=50, n_rows=4):
    fig, ax = plt.subplots()
    x = np.linspace(q_lo, q_hi, n_cols)
    # Fake intensity peaking near mid-Q
    row = np.exp(-0.5 * ((x - 3.0) / 0.4) ** 2)
    Z = np.vstack([row * (i + 1) for i in range(n_rows)])
    im = ax.imshow(
        Z, aspect="auto", origin="lower",
        extent=(q_lo, q_hi, 0, n_rows - 1),
        cmap="viridis", interpolation="nearest",
    )
    fig._operando_axis_mode = "Q"
    fig._operando_wl = 1.5406
    ax.set_xlabel(default_xlabel("Q"))
    return fig, ax, im


def test_remesh_q_to_d_preserves_peak_location():
    fig, ax, im = _make_q_imshow()
    Z0 = np.asarray(im.get_array(), dtype=float)
    peak_col = int(np.argmax(Z0[0]))
    x0, x1, _, _ = im.get_extent()
    q_peak = x0 + (x1 - x0) * (peak_col / (Z0.shape[1] - 1))

    AU.apply_operando_axis_unit_conversion(
        fig=fig, ax=ax, im=im, frm="Q", to="d", wl=1.5406, redraw_cif=False,
    )
    assert getattr(fig, "_operando_axis_mode") == "d"
    Z1 = np.asarray(im.get_array(), dtype=float)
    peak_col2 = int(np.nanargmax(Z1[0]))
    d0, d1, _, _ = im.get_extent()
    d_peak = d0 + (d1 - d0) * (peak_col2 / (Z1.shape[1] - 1))
    d_expected = float(convert_x_array(np.array([q_peak]), frm="Q", to="d", wl=None)[0])
    np.testing.assert_allclose(d_peak, d_expected, rtol=0.05, atol=0.05)
    assert ax.get_xlabel() == default_xlabel("d")
    plt.close(fig)


def test_remesh_roundtrip_q_d_q_close():
    fig, ax, im = _make_q_imshow()
    Z0 = np.asarray(im.get_array(), dtype=float).copy()
    ext0 = tuple(im.get_extent())
    AU.apply_operando_axis_unit_conversion(
        fig=fig, ax=ax, im=im, frm="Q", to="d", wl=1.54, redraw_cif=False,
    )
    AU.apply_operando_axis_unit_conversion(
        fig=fig, ax=ax, im=im, frm="d", to="Q", wl=1.54, redraw_cif=False,
    )
    Z2 = np.asarray(im.get_array(), dtype=float)
    # Remesh is lossy but should stay close on the interior
    mid = slice(5, -5)
    np.testing.assert_allclose(Z2[0, mid], Z0[0, mid], rtol=0.15, atol=0.05)
    ext2 = tuple(im.get_extent())
    np.testing.assert_allclose(ext2[0], ext0[0], rtol=0.05, atol=0.05)
    np.testing.assert_allclose(ext2[1], ext0[1], rtol=0.05, atol=0.05)
    assert getattr(fig, "_operando_axis_mode") == "Q"
    plt.close(fig)


def test_menu_lists_u_only_for_xrd(capsys):
    fig = plt.figure()
    fig._operando_axis_mode = "Q"
    print_operando_ec_menu(fig, None)
    out = capsys.readouterr().out
    assert "axis units (XRD only)" in out

    fig._operando_axis_mode = "r"
    print_operando_ec_menu(fig, None)
    out2 = capsys.readouterr().out
    assert "axis units (XRD only)" not in out2

    fig._is_dqdv_2d_contour = True
    fig._operando_axis_mode = "Q"
    print_operando_ec_menu(fig, None)
    out3 = capsys.readouterr().out
    assert "axis units (XRD only)" not in out3
    plt.close(fig)


def test_menu_keys_include_u_for_xrd_dispatch_contract():
    fig = plt.figure()
    fig._operando_axis_mode = "Q"
    cols, _ = build_operando_ec_menu_columns(fig, ec_ax=object())
    flat = " ".join(item for _h, items in cols for item in items)
    assert "u: axis units (XRD only)" in flat
    plt.close(fig)


def test_refuse_non_xrd_menu():
    fig, ax = plt.subplots()
    im = ax.imshow(np.ones((3, 10)), extent=(0, 1, 0, 2))
    fig._operando_axis_mode = "r"
    answers = iter(["q"])
    out = AU.run_operando_axis_units_menu(
        fig=fig, ax=ax, im=im,
        push_state=lambda n: None,
        _safe_input=lambda p: next(answers, "b"),
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
    )
    assert out is None
    plt.close(fig)


def test_cif_peaks_follow_d_domain():
    from batplot.plot_modes.operando.plot import _draw_operando_cif_ticks

    fig, ax, im = _make_q_imshow(q_lo=1.0, q_hi=4.0)
    # One peak at Q = 2π → d = 1 Å after convert
    peaksQ = [2.0 * np.pi]
    ax._operando_cif_tick_series = [("ph", "/tmp/a.cif", peaksQ, None, 10.0, "k")]
    ax._operando_cif_hkl_label_map = {}
    AU.apply_operando_axis_unit_conversion(
        fig=fig, ax=ax, im=im, frm="Q", to="d", wl=1.54, redraw_cif=True,
    )
    # After draw, artists exist; peak should map near d=1 within xlim
    arts = getattr(fig, "_operando_cif_tick_art", []) or []
    assert arts  # at least title or tick
    plt.close(fig)


def test_old_session_none_mode_infers_from_xlabel():
    """Old sessions omit axis_mode; infer from xlabel — never invent 2θ for blank."""
    fig = plt.figure()
    # No axes / blank: do not offer ``u``
    assert AU.is_operando_xrd_axis(fig) is False
    fig2, ax2 = plt.subplots()
    ax2.set_xlabel(r"Q (Å$^{-1}$)")
    assert AU.is_operando_xrd_axis(fig2, ax2) is True
    assert getattr(fig2, "_operando_axis_mode") == "Q"
    fig3, ax3 = plt.subplots()
    ax3.set_xlabel("Energy (KeV)")
    assert AU.is_operando_xrd_axis(fig3, ax3) is False
    assert getattr(fig3, "_operando_axis_mode") == "energy"
    fig4 = plt.figure()
    fig4._operando_axis_mode = "r"
    assert AU.is_operando_xrd_axis(fig4) is False
    plt.close(fig)
    plt.close(fig2)
    plt.close(fig3)
    plt.close(fig4)


def test_infer_mode_from_xlabel():
    assert AU.infer_operando_axis_mode_from_xlabel(r"Q (Å$^{-1}$)") == "Q"
    assert AU.infer_operando_axis_mode_from_xlabel("2θ (deg)") == "2theta"
    assert AU.infer_operando_axis_mode_from_xlabel("Two theta (deg)") == "2theta"
    assert AU.infer_operando_axis_mode_from_xlabel(r"d ($\mathrm{\AA}$)") == "d"
    assert AU.infer_operando_axis_mode_from_xlabel("r (Å)") == "r"
    assert AU.infer_operando_axis_mode_from_xlabel("R (Å)") == "r"
    assert AU.infer_operando_axis_mode_from_xlabel("Energy (KeV)") == "energy"
    assert AU.infer_operando_axis_mode_from_xlabel("user defined") == "user_defined"


def test_operando_q_to_2theta_bragg_clamp_keeps_columns():
    """Over-range Q → 2θ must not collapse the remesh via NaN columns."""
    fig, ax, im = _make_q_imshow(q_lo=0.5, q_hi=15.0, n_cols=80)
    n0 = np.asarray(im.get_array()).shape[1]
    AU.apply_operando_axis_unit_conversion(
        fig=fig, ax=ax, im=im, frm="Q", to="2theta", wl=1.5406, redraw_cif=False,
    )
    assert getattr(fig, "_operando_axis_mode") == "2theta"
    Z = np.asarray(im.get_array(), dtype=float)
    assert Z.shape[1] == n0
    ext = im.get_extent()
    assert ext[1] < 181.0
    plt.close(fig)


def test_ensure_mode_from_xlabel():
    fig, ax = plt.subplots()
    ax.set_xlabel(r"Q (Å$^{-1}$)")
    mode = AU.ensure_operando_axis_mode(fig, ax)
    assert mode == "Q"
    assert getattr(fig, "_operando_axis_mode") == "Q"
    plt.close(fig)
    fig2, ax2 = plt.subplots()
    assert AU.ensure_operando_axis_mode(fig2, ax2) is None
    assert getattr(fig2, "_operando_axis_mode", None) is None
    plt.close(fig2)


def test_snapshot_push_returns_bool_for_axis_units_menu():
    fig, ax, im = _make_q_imshow()
    pushes = []

    def _push(note):
        pushes.append(note)
        return True

    answers = iter(["d", ""])  # convert with Enter keeping wl
    out = AU.run_operando_axis_units_menu(
        fig=fig, ax=ax, im=im,
        push_state=_push,
        pop_undo=None,
        _safe_input=lambda p: next(answers, "b"),
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
    )
    assert out == "d"
    assert pushes == ["axis-units"]
    plt.close(fig)


def test_failed_push_does_not_convert():
    fig, ax, im = _make_q_imshow()
    Z0 = np.asarray(im.get_array(), dtype=float).copy()

    def _push(_note):
        return False

    answers = iter(["d", ""])
    out = AU.run_operando_axis_units_menu(
        fig=fig, ax=ax, im=im,
        push_state=_push,
        pop_undo=None,
        _safe_input=lambda p: next(answers, "b"),
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
    )
    assert out is None
    np.testing.assert_array_equal(np.asarray(im.get_array(), dtype=float), Z0)
    assert getattr(fig, "_operando_axis_mode") == "Q"
    plt.close(fig)


def test_dispatcher_wires_u_command():
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[1]
        / "batplot" / "plot_modes" / "operando" / "interactive.py"
    ).read_text(encoding="utf-8")
    assert "run_operando_axis_units_menu(" in src
    assert "cmd == 'u'" in src
    assert "pop_undo=_restore" in src


def test_geometry_snapshot_ensures_axis_mode():
    from batplot.plot_modes.operando.layout import _get_geometry_snapshot

    fig, ax = plt.subplots()
    ax.set_xlabel(r"Q ($\mathrm{\AA}^{-1}$)")
    # No fig attr — snapshot should still resolve via ensure/infer
    snap = _get_geometry_snapshot(ax, None)
    assert snap["operando"]["axis_mode"] == "Q"
    plt.close(fig)

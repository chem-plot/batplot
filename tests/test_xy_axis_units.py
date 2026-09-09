"""Tests for XY Options ``u`` axis unit convert (2θ ↔ Q ↔ d)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.xy import axis_units as AU
from batplot.plot_modes.xy.menu import print_xy_menu
from batplot.plot_modes.xy.style import apply_style_config
from batplot.plotting import update_labels


def test_convert_roundtrip_q_d_q():
    q = np.array([1.0, 2.0, 3.5, 5.0])
    d = AU.convert_x_array(q, frm="Q", to="d", wl=None)
    q2 = AU.convert_x_array(d, frm="d", to="Q", wl=None)
    np.testing.assert_allclose(q2, q, rtol=1e-10)


def test_format_xrd_crosshair_includes_all_bragg_with_wl():
    wl = 0.709
    q = 2.0
    lines_q = AU.format_xrd_crosshair_x_lines(q, axis_mode="Q", wavelength=wl)
    assert lines_q[0].startswith("Q=")
    assert any(s.startswith("2θ=") for s in lines_q)
    assert any(s.startswith("d=") for s in lines_q)

    tth = float(AU.Q_to_twotheta(np.array([q]), wl)[0])
    lines_tth = AU.format_xrd_crosshair_x_lines(tth, axis_mode="2theta", wavelength=wl)
    assert lines_tth[0].startswith("2θ=")
    assert any(s.startswith("Q=") for s in lines_tth)
    assert any(s.startswith("d=") for s in lines_tth)

    d = float(AU.Q_to_d(np.array([q]))[0])
    lines_d = AU.format_xrd_crosshair_x_lines(d, axis_mode="d", wavelength=wl)
    assert lines_d[0].startswith("d=")
    assert any(s.startswith("Q=") for s in lines_d)
    assert any(s.startswith("2θ=") for s in lines_d)


def test_format_xrd_crosshair_without_wl_omits_2theta_on_q():
    lines = AU.format_xrd_crosshair_x_lines(2.0, axis_mode="Q", wavelength=None)
    assert lines[0].startswith("Q=")
    assert any(s.startswith("d=") for s in lines)
    assert not any(s.startswith("2θ=") for s in lines)


def test_convert_roundtrip_2theta_q_with_wl():
    wl = 1.5406
    tth = np.array([10.0, 20.0, 30.0, 45.0])
    q = AU.convert_x_array(tth, frm="2theta", to="Q", wl=wl)
    tth2 = AU.convert_x_array(q, frm="Q", to="2theta", wl=wl)
    np.testing.assert_allclose(tth2, tth, rtol=1e-8, atol=1e-8)


def test_peaks_q_to_domain_d_and_2theta():
    peaks = [2.0 * np.pi]  # d = 1 Å
    np.testing.assert_allclose(AU.peaks_Q_to_domain(peaks, "d"), [1.0], rtol=1e-10)
    wl = 1.5406
    tth = AU.peaks_Q_to_domain(peaks, "2theta", wl)
    assert len(tth) == 1
    q_back = AU.domain_peak_to_Q(tth[0], "2theta", wl)
    np.testing.assert_allclose(q_back, peaks[0], rtol=1e-8)


def test_apply_converts_data_and_cif_display_wl():
    fig, ax = plt.subplots()
    x = [np.array([1.0, 2.0, 4.0])]
    y = [np.array([1.0, 1.0, 1.0])]
    (ln,) = ax.plot(x[0], y[0])
    fig._xy_lines_by_curve = [ln]
    ax.set_xlim(1.0, 4.0)
    AU.set_xy_axis_mode(fig, "Q", wavelength=1.54)
    cif = [("phase", "a.cif", [2.0 * np.pi], None, 10.0, "k")]
    AU.apply_xy_axis_unit_conversion(
        fig=fig,
        ax=ax,
        frm="Q",
        to="d",
        wl=1.54,
        x_data_list=x,
        x_full_list=[np.array(x[0], copy=True)],
        y_data_list=y,
        cif_series=cif,
    )
    np.testing.assert_allclose(x[0], AU.Q_to_d(np.array([1.0, 2.0, 4.0])), rtol=1e-10)
    assert getattr(fig, "_xy_axis_mode") == "d"
    assert cif[0][3] is None  # λ not stored on entries in d mode
    AU.apply_xy_axis_unit_conversion(
        fig=fig,
        ax=ax,
        frm="d",
        to="2theta",
        wl=1.54,
        x_data_list=x,
        x_full_list=x,
        y_data_list=y,
        cif_series=cif,
    )
    assert getattr(fig, "_xy_axis_mode") == "2theta"
    assert cif[0][3] == 1.54
    plt.close(fig)


def test_menu_lists_u_for_diffraction_only(capsys):
    fig = plt.figure()
    print_xy_menu(fig=fig, stack=False, is_diffraction=True, colorize_menu=lambda s: s)
    out = capsys.readouterr().out
    assert "u: axis units (XRD only)" in out
    print_xy_menu(fig=fig, stack=False, is_diffraction=False, colorize_menu=lambda s: s)
    out2 = capsys.readouterr().out
    assert "u: axis units" not in out2
    plt.close(fig)


def test_style_bpsg_skips_xlim_on_axis_mode_mismatch(tmp_path):
    fig, ax = plt.subplots()
    x = np.linspace(1.0, 3.0, 20)
    y = np.ones_like(x)
    ax.plot(x, y)
    ax.set_xlim(2.0, 6.0)
    ax.set_ylim(0.0, 2.0)
    AU.set_xy_axis_mode(fig, "d", wavelength=1.54)
    args = SimpleNamespace(wl=1.54, stack=False, files=[], ro=False)
    tick_state = {
        "bx": True, "tx": False, "ly": True, "ry": False,
        "mbx": False, "mtx": False, "mly": False, "mry": False,
        "b_ticks": True, "t_ticks": False, "l_ticks": True, "r_ticks": False,
        "b_labels": True, "t_labels": False, "l_labels": True, "r_labels": False,
    }
    path = tmp_path / "t.bpsg"
    cfg = {
        "kind": "xy_style_geom",
        "ro_active": False,
        "geometry": {
            "xlabel": "Q",
            "ylabel": "I",
            "xlim": [1.0, 3.0],
            "ylim": [0.0, 2.0],
            "axis_mode": "Q",
            "wavelength": 1.54,
        },
    }
    path.write_text(json.dumps(cfg), encoding="utf-8")
    apply_style_config(
        str(path),
        fig,
        ax,
        [x],
        [y],
        [y.copy()],
        [0.0],
        [],
        args,
        tick_state,
        ["a"],
        update_labels,
        cif_tick_series=None,
        cif_hkl_label_map=None,
    )
    xl = ax.get_xlim()
    assert abs(xl[0] - 2.0) < 1e-9 and abs(xl[1] - 6.0) < 1e-9
    # xlabel must also stay put on mode mismatch (was wrongly applying "Q")
    assert ax.get_xlabel() != "Q"
    plt.close(fig)


def test_convert_updates_stored_xlabel_for_spine_menu():
    fig, ax = plt.subplots()
    x = [np.array([1.0, 2.0, 4.0])]
    y = [np.array([1.0, 1.0, 1.0])]
    (ln,) = ax.plot(x[0], y[0])
    fig._xy_lines_by_curve = [ln]
    ax.set_xlabel(AU.default_xlabel("Q"))
    ax._stored_xlabel = AU.default_xlabel("Q")
    AU.set_xy_axis_mode(fig, "Q", wavelength=1.54)
    AU.apply_xy_axis_unit_conversion(
        fig=fig, ax=ax, frm="Q", to="d", wl=1.54,
        x_data_list=x, x_full_list=[np.array(x[0], copy=True)], y_data_list=y,
    )
    assert ax.get_xlabel() == AU.default_xlabel("d")
    assert getattr(ax, "_stored_xlabel") == AU.default_xlabel("d")
    plt.close(fig)


def test_get_xy_axis_mode_respects_xaxis_hint_for_d():
    fig = plt.figure()
    # No stored mode — hint via xaxis / fig hint
    assert AU.get_xy_axis_mode(fig, xaxis="d") == "d"
    fig._xy_xaxis_hint = "d"
    assert AU.get_xy_axis_mode(fig) == "d"
    plt.close(fig)


def test_get_xy_axis_mode_unknown_not_2theta():
    fig, ax = plt.subplots()
    ax.set_xlabel("")
    assert AU.get_xy_axis_mode(fig, ax=ax) == "unknown"
    ax.set_xlabel(r"Q ($\mathrm{\AA}^{-1}$)")
    assert AU.get_xy_axis_mode(fig, ax=ax) == "Q"
    plt.close(fig)


def test_infer_two_theta_english_xlabel():
    assert AU.infer_xy_axis_mode_from_xlabel("Two theta (deg)") == "2theta"
    assert AU.infer_xy_axis_mode_from_xlabel("Two-Theta") == "2theta"
    fig, ax = plt.subplots()
    ax.set_xlabel("Two theta (deg)")
    assert AU.get_xy_axis_mode(fig, ax=ax) == "2theta"
    plt.close(fig)


def test_resolve_wavelength_dual_wl_prefers_original_for_q():
    """file:λ1:λ2 Q data must convert with λ1, not stored final_wl=λ2."""
    fig = plt.figure()
    AU.set_xy_axis_mode(fig, "Q", wavelength=1.54)  # stale λ2 (old bug)
    info = [{"original_wl": 0.709, "conversion_wl": 1.54, "final_wl": 1.54}]
    wl = AU.resolve_wavelength(
        fig=fig,
        args=SimpleNamespace(wl=None),
        file_wavelength_info=info,
        axis_mode="Q",
    )
    assert wl == 0.709
    fig._xy_dual_wl_display = True
    AU.set_xy_axis_mode(fig, "2theta", wavelength=1.54)
    wl2 = AU.resolve_wavelength(
        fig=fig,
        args=SimpleNamespace(wl=None),
        file_wavelength_info=info,
        axis_mode="2theta",
    )
    assert wl2 == 1.54
    plt.close(fig)


def test_run_axis_units_menu_q_to_d():
    fig, ax = plt.subplots()
    x_data = [np.array([1.0, 2.0, 4.0])]
    x_full = [np.array([1.0, 2.0, 4.0])]
    y_data = [np.array([1.0, 1.0, 1.0])]
    (ln,) = ax.plot(x_data[0], y_data[0])
    fig._xy_lines_by_curve = [ln]
    AU.set_xy_axis_mode(fig, "Q", wavelength=1.54)
    args = SimpleNamespace(wl=1.54, xaxis="Q")
    answers = iter(["d"])
    pushed = []

    def _inp(_p=""):
        try:
            return next(answers)
        except StopIteration:
            return "b"

    out = AU.run_axis_units_menu(
        fig=fig,
        ax=ax,
        args=args,
        x_data_list=x_data,
        x_full_list=x_full,
        y_data_list=y_data,
        use_Q=True,
        use_r=False,
        use_E=False,
        use_k=False,
        use_rft=False,
        get_cif_series=lambda: [],
        sync_fig_cif_tick_series=lambda: None,
        file_wavelength_info=None,
        push_state=lambda note: pushed.append(note) or True,
        pop_undo=None,
        set_use_Q=lambda f: None,
        _safe_input=_inp,
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
    )
    assert out == "d"
    assert pushed == ["axis-units"]
    assert getattr(fig, "_xy_axis_mode") == "d"
    np.testing.assert_allclose(x_data[0], AU.Q_to_d(np.array([1.0, 2.0, 4.0])), rtol=1e-10)
    plt.close(fig)


def test_run_axis_units_menu_respects_2theta_launch_and_wl():
    """``--xaxis 2theta --wl`` must start convert from 2θ using that λ."""
    fig, ax = plt.subplots()
    x_data = [np.array([10.0, 20.0, 40.0])]
    x_full = [np.array([10.0, 20.0, 40.0])]
    y_data = [np.ones(3)]
    (ln,) = ax.plot(x_data[0], y_data[0])
    fig._xy_lines_by_curve = [ln]
    AU.set_xy_axis_mode(fig, "2theta", wavelength=0.25)
    args = SimpleNamespace(wl=0.25, xaxis="2theta")
    answers = iter(["q", ""])  # convert to Q, Enter keeps λ=0.25
    pushed = []

    def _inp(_p=""):
        try:
            return next(answers)
        except StopIteration:
            return "b"

    out = AU.run_axis_units_menu(
        fig=fig,
        ax=ax,
        args=args,
        x_data_list=x_data,
        x_full_list=x_full,
        y_data_list=y_data,
        use_Q=False,
        use_2th=True,
        use_r=False,
        use_E=False,
        use_k=False,
        use_rft=False,
        get_cif_series=lambda: [],
        sync_fig_cif_tick_series=lambda: None,
        file_wavelength_info=None,
        push_state=lambda note: pushed.append(note) or True,
        pop_undo=None,
        set_use_Q=lambda f: None,
        set_use_2th=lambda f: None,
        _safe_input=_inp,
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
    )
    assert out == "Q"
    assert getattr(fig, "_xy_axis_mode") == "Q"
    # 2θ=10° at λ=0.25 → Q = 4π sin(5°)/0.25
    q_exp = AU.twotheta_to_Q(np.array([10.0]), 0.25)[0]
    np.testing.assert_allclose(x_data[0][0], q_exp, rtol=1e-10)
    plt.close(fig)


def test_operando_xaxis_2theta_wins_over_wl():
    from batplot.plot_modes.operando.plot import _infer_axis_mode
    args = SimpleNamespace(xaxis="2theta", wl=0.25)
    assert _infer_axis_mode(args, any_qye=False, has_unknown_ext=False) == "2theta"
    args2 = SimpleNamespace(xaxis=None, wl=0.25)
    assert _infer_axis_mode(args2, any_qye=False, has_unknown_ext=False) == "Q"


def test_xy_cancel_when_push_fails():
    fig, ax = plt.subplots()
    x = [np.array([1.0, 2.0, 4.0])]
    y = [np.ones(3)]
    (ln,) = ax.plot(x[0], y[0])
    fig._xy_lines_by_curve = [ln]
    AU.set_xy_axis_mode(fig, "Q", wavelength=1.54)
    x0 = x[0].copy()
    answers = iter(["d"])

    def _inp(_p=""):
        try:
            return next(answers)
        except StopIteration:
            return "b"

    out = AU.run_axis_units_menu(
        fig=fig,
        ax=ax,
        args=SimpleNamespace(wl=1.54, xaxis="Q"),
        x_data_list=x,
        x_full_list=[x0.copy()],
        y_data_list=y,
        use_Q=True,
        use_r=False,
        use_E=False,
        use_k=False,
        use_rft=False,
        get_cif_series=lambda: [],
        sync_fig_cif_tick_series=lambda: None,
        file_wavelength_info=None,
        push_state=lambda note: False,
        pop_undo=None,
        set_use_Q=lambda f: None,
        _safe_input=_inp,
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
    )
    assert out is None
    np.testing.assert_array_equal(x[0], x0)
    assert getattr(fig, "_xy_axis_mode") == "Q"
    plt.close(fig)


def test_xy_atomic_convert_raises_before_mode_flip():
    fig, ax = plt.subplots()
    x = [np.array([10.0, 20.0])]
    y = [np.ones(2)]
    (ln,) = ax.plot(x[0], y[0])
    fig._xy_lines_by_curve = [ln]
    AU.set_xy_axis_mode(fig, "2theta", wavelength=None)
    x0 = x[0].copy()
    try:
        AU.apply_xy_axis_unit_conversion(
            fig=fig,
            ax=ax,
            frm="2theta",
            to="Q",
            wl=None,
            x_data_list=x,
            x_full_list=[x0.copy()],
            y_data_list=y,
        )
        assert False, "expected ValueError"
    except ValueError:
        pass
    np.testing.assert_array_equal(x[0], x0)
    assert getattr(fig, "_xy_axis_mode") == "2theta"
    plt.close(fig)


def test_dispatcher_wires_u_command():
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "batplot"
        / "plot_modes"
        / "xy"
        / "interactive.py"
    ).read_text(encoding="utf-8")
    assert "run_axis_units_menu(" in src
    assert "elif key == 'u':" in src
    assert "pop_undo=restore_state" in src


def test_q_to_2theta_clamps_overrange_xlim():
    """Q xlim beyond Bragg limit must not remain in Q after →2θ."""
    fig, ax = plt.subplots()
    wl = 1.5406
    q = np.linspace(0.5, 15.0, 200)  # 15 ≫ 4π/λ ≈ 8.1
    y = np.ones_like(q)
    (ln,) = ax.plot(q, y)
    fig._xy_lines_by_curve = [ln]
    ax.set_xlim(0.5, 15.0)
    AU.set_xy_axis_mode(fig, "Q", wavelength=wl)
    x = [q.copy()]
    AU.apply_xy_axis_unit_conversion(
        fig=fig, ax=ax, frm="Q", to="2theta", wl=wl,
        x_data_list=x, x_full_list=[q.copy()], y_data_list=[y.copy()],
    )
    assert getattr(fig, "_xy_axis_mode") == "2theta"
    lo, hi = ax.get_xlim()
    assert hi < 181.0  # degrees, not leftover Q=15
    assert lo < hi
    assert np.all(np.isfinite(x[0]))
    plt.close(fig)


def test_xmax_domain_to_q_for_d_axis():
    # Visible d window [0.5, 2.0] Å → high-Q edge from min d = 0.5 → Q = 4π
    q = AU.xmax_domain_to_Q(2.0, "d", xlim=(0.5, 2.0))
    np.testing.assert_allclose(q, (2.0 * np.pi) / 0.5, rtol=1e-10)


def test_xmax_2theta_without_wl_not_degrees_as_q():
    # 60° without λ must not become Qmax=60
    q = AU.xmax_domain_to_Q(60.0, "2theta", wl=None)
    assert q == max(60.0 * 0.1, 10.0)
    q_wl = AU.xmax_domain_to_Q(60.0, "2theta", wl=1.5406)
    assert q_wl < 10.0  # real Q for Cu Kα ~4


def test_pipeline_xaxis_d_honored_with_cif_context():
    """Regression: CIF/vendor/λ branch must not swallow ``--xaxis d``."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[1]
        / "batplot"
        / "plot_modes"
        / "xy"
        / "pipeline.py"
    ).read_text(encoding="utf-8")
    assert 'str(args.xaxis).lower() == "d"' in src
    assert 'axis_mode = "d"' in src
    assert 'axis_mode not in ("Q", "2theta", "d")' in src


def test_cif_qmax_uses_d_axis_window():
    from batplot.plot_modes.xy.cif import _xy_cif_qmax

    fig, ax = plt.subplots()
    AU.set_xy_axis_mode(fig, "d", wavelength=1.54)
    ax.set_xlim(0.8, 3.0)  # Å; high-Q from 0.8 → ~7.85
    qmax = _xy_cif_qmax(ax, [], use_2th=False, fig=fig)
    np.testing.assert_allclose(qmax, max((2.0 * np.pi) / 0.8, 10.0), rtol=1e-8)
    plt.close(fig)

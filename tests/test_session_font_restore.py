"""Cross-mode session/style font restore (family/size on axis labels, not just rcParams)."""

import matplotlib.pyplot as plt
import numpy as np

from batplot import session as S
from batplot.plot_modes.common.fonts import apply_font_size_to_artists, collect_fig_font_artists, set_font_size_default
from batplot.plot_modes.electrochem import interactive as E
from conftest import assert_allclose, loaded


def _apply_font10(ax, fig=None):
    if fig is None:
        fig = ax.get_figure()
    set_font_size_default(10.0)
    apply_font_size_to_artists(collect_fig_font_artists(ax, fig), 10.0)


def test_ec_session_font_size_on_axis_labels(session_path):
    fig, ax, cycle_lines, _cap, _volt = _build_ec_figure()
    _apply_font10(ax, fig)
    p = session_path("ec_font10.pkl")
    S.dump_ec_session(p, fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)

    plt.rcParams["font.size"] = 16.0
    fig2, ax2, _meta = loaded(S.load_ec_session(p))
    assert plt.rcParams["font.size"] == 10.0
    assert ax2.xaxis.label.get_fontsize() == 10.0
    assert ax2.get_xticklabels()[0].get_fontsize() == 10.0


def test_cpc_session_font_size_on_axis_labels(session_path):
    fig, ax, ax2, sc_ch, sc_dh, sc_ef, _cyc = _build_cpc_figure()
    _apply_font10(ax, fig)
    _apply_font10(ax2, fig)
    p = session_path("cpc_font10.pkl")
    S.dump_cpc_session(
        p, fig=fig, ax=ax, ax2=ax2,
        sc_charge=sc_ch, sc_discharge=sc_dh, sc_eff=sc_ef,
        skip_confirm=True,
    )

    plt.rcParams["font.size"] = 16.0
    fig2, ax2p, ax2s, *_rest = loaded(S.load_cpc_session(p))
    assert plt.rcParams["font.size"] == 10.0
    assert ax2p.xaxis.label.get_fontsize() == 10.0
    assert ax2s.yaxis.label.get_fontsize() == 10.0


def test_xy_session_font_size_on_axis_labels(session_path, fake_args):
    fig, ax, x_full, y_full, x_disp, y_disp = _build_xy_figure()
    _apply_font10(ax, fig)
    p = session_path("xy_font10.pkl")
    S.dump_session(
        p, fig=fig, ax=ax,
        x_data_list=[x_disp], y_data_list=[y_disp], orig_y=[y_disp],
        x_full_list=[x_full], raw_y_full_list=[y_full],
        offsets_list=[0.0], labels=["c1"], delta=0.0, args=fake_args,
        tick_state={}, skip_confirm=True,
    )

    plt.rcParams["font.size"] = 16.0
    fig2, ax2, _mk = loaded(S.load_xy_session(p))
    assert plt.rcParams["font.size"] == 10.0
    assert ax2.xaxis.label.get_fontsize() == 10.0
    assert ax2.get_xticklabels()[0].get_fontsize() == 10.0


def test_operando_session_font_size_on_axis_labels(session_path):
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    _apply_font10(ax, fig)
    _apply_font10(ec_ax, fig)
    p = session_path("op_font10.pkl")
    S.dump_operando_session(
        p, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax, skip_confirm=True,
    )

    plt.rcParams["font.size"] = 16.0
    fig2, ax2, _im2, _cb2, ec_ax2 = loaded(S.load_operando_session(p))
    assert plt.rcParams["font.size"] == 10.0
    assert ax2.xaxis.label.get_fontsize() == 10.0
    assert ec_ax2.xaxis.label.get_fontsize() == 10.0


def test_ec_style_apply_restores_font_size_on_axis_labels(session_path):
    from batplot.plot_modes.electrochem.style_apply import apply_ec_style_config

    fig, ax, cycle_lines, _cap, _volt = _build_ec_figure()
    E._apply_font_size(ax, 10.0)
    snap = E._get_style_snapshot(fig, ax, cycle_lines, tick_state={}, file_data=None)

    fig2, ax2, cycle_lines2, _c2, _v2 = _build_ec_figure()
    apply_ec_style_config(
        snap,
        fig=fig2,
        ax=ax2,
        cycle_lines=cycle_lines2,
        file_data=None,
        tick_state={},
        is_multi_file=False,
        silent=True,
    )
    assert ax2.xaxis.label.get_fontsize() == 10.0
    assert ax2.get_xticklabels()[0].get_fontsize() == 10.0


def _build_ec_figure():
    fig, ax = plt.subplots()
    cap = np.linspace(0.0, 150.0, 40)
    volt = np.linspace(3.0, 4.2, 40)
    charge, = ax.plot(cap, volt, color="#ff0000", lw=2.0, label="cycle 1 charge")
    discharge, = ax.plot(cap[::-1], volt, color="#0000ff", lw=1.5, label="cycle 1 discharge")
    ax.set_xlabel("Capacity (mAh/g)")
    ax.set_ylabel("Voltage (V)")
    cycle_lines = {1: {"charge": charge, "discharge": discharge}}
    return fig, ax, cycle_lines, cap, volt


def _build_cpc_figure():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    cyc = np.arange(1, 21, dtype=float)
    sc_charge = ax.scatter(cyc, np.linspace(150.0, 120.0, 20), c="red", label="charge")
    sc_discharge = ax.scatter(cyc, np.linspace(148.0, 118.0, 20), c="blue", label="discharge")
    sc_eff = ax2.scatter(cyc, np.linspace(95.0, 99.0, 20), c="green", label="efficiency")
    ax.set_xlabel("Cycle number")
    ax.set_ylabel("Capacity (mAh/g)")
    ax2.set_ylabel("Coulombic efficiency (%)")
    return fig, ax, ax2, sc_charge, sc_discharge, sc_eff, cyc


def _build_xy_figure():
    x_full = np.linspace(10.0, 40.0, 80)
    y_full = np.sin(x_full)
    x_disp = x_full.copy()
    y_disp = y_full.copy()
    fig, ax = plt.subplots()
    ax.plot(x_disp, y_disp, label="c1")
    ax.set_xlabel("Two theta")
    ax.set_ylabel("Intensity")
    return fig, ax, x_full, y_full, x_disp, y_disp


def _build_operando_figure():
    fig, ax = plt.subplots()
    Z = np.random.default_rng(0).random((50, 80))
    im = ax.imshow(Z, aspect="auto", origin="lower", extent=(10.0, 40.0, 0.0, 20.0), cmap="viridis")
    cbar = fig.colorbar(im, ax=ax)
    ec_ax = fig.add_axes((0.78, 0.1, 0.18, 0.8))
    ec_ax.plot(np.linspace(3.0, 4.2, 30), np.linspace(0.0, 20.0, 30))
    ec_ax.set_xlabel("Voltage (V)")
    ec_ax.set_ylabel("Time (h)")
    ax.set_xlabel("2θ (deg)")
    ax.set_ylabel("Scan index")
    return fig, ax, im, cbar, ec_ax

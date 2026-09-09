"""XY full-domain buffers must survive X crops and .pkl save/load."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
import pytest

from batplot.plot_modes.xy.full_data import (
    full_matches_display,
    install_master_full,
    parse_label_source,
    sync_live_full_lists,
    warn_if_full_looks_cropped,
)
from batplot.session import dump_session, load_xy_session
from conftest import loaded


def test_parse_label_source_strips_wavelength_suffix():
    path, wl = parse_label_source("TD_S112-121_P_1.raw (λ=1.54000 Å)")
    assert path == "TD_S112-121_P_1.raw"
    assert wl == pytest.approx(1.54)


def test_master_survives_live_full_corruption_on_save(session_path, fake_args):
    """If live x_full is wrongly cropped but master is intact, dump keeps master."""
    x_full = np.linspace(0.0, 100.0, 1001)
    y_full = np.sin(x_full)
    mask = (x_full >= 20.0) & (x_full <= 40.0)
    x_disp, y_disp = x_full[mask], y_full[mask]

    fig, ax = plt.subplots()
    ax.plot(x_disp, y_disp)
    ax.set_xlim(20, 40)
    ax._norm_xlim = (0.0, 100.0)
    install_master_full(fig, [x_full], [y_full], force=True)

    # Simulate the bad in-memory state that produced BM0_P.pkl
    x_full_list = [x_disp.copy()]
    raw_y_full_list = [y_disp.copy()]
    assert full_matches_display(x_full_list, [x_disp])

    p = session_path("xy_master_protect.pkl")
    dump_session(
        p,
        fig=fig,
        ax=ax,
        x_data_list=[x_disp],
        y_data_list=[y_disp],
        orig_y=[y_disp],
        x_full_list=x_full_list,
        raw_y_full_list=raw_y_full_list,
        offsets_list=[0.0],
        labels=["c1.raw (λ=1.54000 Å)"],
        delta=0.0,
        args=fake_args,
        tick_state={},
        skip_confirm=True,
    )
    # Live lists upgraded during dump
    assert x_full_list[0].size == x_full.size

    _fig2, _ax2, mk = loaded(load_xy_session(p))
    assert mk["x_full_list"][0].size == x_full.size
    assert abs(float(mk["x_full_list"][0].max()) - 100.0) < 1e-9
    plt.close(fig)
    plt.close(_fig2)


def test_sync_live_full_prefers_longest_backup():
    fig, ax = plt.subplots()
    try:
        install_master_full(
            fig,
            [np.linspace(0, 10, 101)],
            [np.ones(101)],
            force=True,
        )
        x_full = [np.linspace(4, 5, 11)]
        y_full = [np.ones(11)]
        sync_live_full_lists(fig, x_full, y_full, x_data_list=x_full, y_fallback_list=y_full)
        assert x_full[0].size == 101
    finally:
        plt.close(fig)


def test_warn_if_full_looks_cropped(capsys):
    fig, ax = plt.subplots()
    try:
        x = np.linspace(2.7, 2.8, 97)
        warn_if_full_looks_cropped([x], [x], norm_xlim=(0.08, 6.0))
        out = capsys.readouterr().out
        assert "full-data buffers match the displayed X crop" in out
    finally:
        plt.close(fig)


def test_expand_after_reload_still_works_with_master(session_path, fake_args):
    from batplot.plot_modes.xy.axis_range import run_x_range_menu

    x_full = np.linspace(0.0, 100.0, 1001)
    y_full = np.cos(x_full)
    mask = (x_full >= 20.0) & (x_full <= 40.0)
    x_disp, y_disp = x_full[mask], y_full[mask]
    fig, ax = plt.subplots()
    ax.plot(x_disp, y_disp)
    ax.set_xlim(20, 40)
    install_master_full(fig, [x_full], [y_full], force=True)
    p = session_path("xy_expand_master.pkl")
    dump_session(
        p, fig=fig, ax=ax,
        x_data_list=[x_disp], y_data_list=[y_disp], orig_y=[y_disp],
        x_full_list=[x_full], raw_y_full_list=[y_full],
        offsets_list=[0.0], labels=["a.raw"], delta=0.0, args=fake_args,
        tick_state={}, skip_confirm=True,
    )
    fig2, ax2, mk = loaded(load_xy_session(p))
    inputs = iter(["10 90", "q"])
    run_x_range_menu(
        args=mk["args"], ax=ax2, fig=fig2, labels=mk["labels"],
        label_text_objects=mk.get("label_text_objects") or [],
        x_data_list=mk["x_data_list"], y_data_list=mk["y_data_list"],
        orig_y=mk["orig_y"], offsets_list=mk["offsets_list"],
        x_full_list=mk["x_full_list"], raw_y_full_list=mk["raw_y_full_list"],
        push_state=lambda *_a, **_k: None,
        _safe_input=lambda _p: next(inputs),
        _line=lambda i: ax2.lines[i],
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
    )
    assert mk["x_data_list"][0].size > x_disp.size
    plt.close(fig)
    plt.close(fig2)


def test_heal_xye_q_from_2theta_source(tmp_path):
    """Cropped Q session must heal from a nearby .xye (2θ) via λ match."""
    from batplot.plot_modes.xy.full_data import try_heal_full_from_label_sources

    # Synthetic 2θ file; convert with λ=0.709 → Q used as "truth"
    x2t = np.linspace(5.0, 60.0, 2001)
    y = np.exp(-((x2t - 30.0) ** 2) / 40.0) * 1000.0 + 10.0
    src = tmp_path / "phase.xye"
    np.savetxt(src, np.column_stack([x2t, y]))

    wl = 0.709
    xq = 4.0 * np.pi * np.sin(np.radians(x2t / 2.0)) / wl
    mask = (xq >= 1.0) & (xq <= 3.0)
    x_disp, y_disp = xq[mask], y[mask]
    # stack-style normalize display (heal scores on normalized shapes)
    y_norm = (y_disp - y_disp.min()) / (y_disp.max() - y_disp.min())

    fig, ax = plt.subplots()
    ax.plot(x_disp, y_norm)
    fig._xy_axis_mode = "Q"  # type: ignore[attr-defined]
    x_full = [x_disp.copy()]
    y_full = [y_norm.copy()]
    ok = try_heal_full_from_label_sources(
        fig=fig,
        labels=[f"{src.name} (λ=0.25448 Å)"],  # wrong label λ — must still match 0.709
        x_full_list=x_full,
        raw_y_full_list=y_full,
        axis_mode="Q",
        session_path=str(tmp_path / "sess.pkl"),
        source_files=[str(src)],
        x_display_list=[x_disp],
        y_display_list=[y_norm],
    )
    assert ok
    assert x_full[0].size == x2t.size
    assert float(x_full[0].max()) > 3.0
    plt.close(fig)


EXSITU_XRD_PKL = (
    "/Users/tiandai/Library/CloudStorage/OneDrive-UniversitetetiOslo/My files/"
    "NFSO data/Figures/exsituXRD.pkl"
)


@pytest.mark.skipif(not __import__("os").path.isfile(EXSITU_XRD_PKL), reason="exsituXRD.pkl missing")
def test_exsitu_xrd_expand_recovers_points_past_saved_crop():
    from batplot.session import load_xy_session
    from batplot.plot_modes.xy.axis_range import run_x_range_menu

    loaded = load_xy_session(EXSITU_XRD_PKL)
    assert loaded is not None
    fig, ax, mk = loaded
    assert mk["x_full_list"][0].size > mk["x_data_list"][0].size
    n0 = mk["x_data_list"][0].size
    feeds = iter(["1 4", "q"])
    run_x_range_menu(
        args=mk["args"],
        ax=ax,
        fig=fig,
        labels=mk["labels"],
        label_text_objects=mk.get("label_text_objects") or [],
        x_data_list=mk["x_data_list"],
        y_data_list=mk["y_data_list"],
        orig_y=mk["orig_y"],
        offsets_list=mk["offsets_list"],
        x_full_list=mk["x_full_list"],
        raw_y_full_list=mk["raw_y_full_list"],
        push_state=lambda *_a, **_k: None,
        _safe_input=lambda _p: next(feeds),
        _line=lambda i: ax.lines[i],
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
    )
    assert mk["x_data_list"][0].size > n0
    assert float(mk["x_data_list"][0].max()) > 3.01
    plt.close(fig)

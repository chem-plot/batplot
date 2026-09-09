"""Backward-compat defaults for new Options ``u`` / dual-wl session fields."""

from __future__ import annotations

import json
from types import SimpleNamespace

import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.xy import axis_units as AU
from batplot.plot_modes.xy.style import apply_style_config
from batplot.plotting import update_labels


def _tick_state():
    return {
        "bx": True, "tx": False, "ly": True, "ry": False,
        "mbx": False, "mtx": False, "mly": False, "mry": False,
        "b_ticks": True, "t_ticks": False, "l_ticks": True, "r_ticks": False,
        "b_labels": True, "t_labels": False, "l_labels": True, "r_labels": False,
    }


def test_old_bpsg_without_dual_wl_keys_still_applies(tmp_path):
    """Pre-dual-wl .bpsg must apply xlim/λ; missing keys → False / []."""
    fig, ax = plt.subplots()
    x = np.linspace(1.0, 5.0, 20)
    y = np.ones_like(x)
    ax.plot(x, y)
    AU.set_xy_axis_mode(fig, "Q", wavelength=1.54)
    ax.set_xlabel(AU.default_xlabel("Q"))
    ax.set_xlim(1.0, 5.0)
    path = tmp_path / "legacy.bpsg"
    path.write_text(
        json.dumps(
            {
                "kind": "xy_style_geom",
                "geometry": {
                    "xlabel": AU.default_xlabel("Q"),
                    "ylabel": "I",
                    "xlim": [1.5, 4.5],
                    "ylim": [0.0, 2.0],
                    "axis_mode": "Q",
                    "wavelength": 0.709,
                    # no dual_wl_display / file_wavelength_info
                },
            }
        ),
        encoding="utf-8",
    )
    apply_style_config(
        str(path),
        fig,
        ax,
        [x],
        [y],
        [y.copy()],
        [0.0],
        [],
        SimpleNamespace(wl=1.54, stack=False, files=[], ro=False, xaxis="Q"),
        _tick_state(),
        ["a"],
        update_labels,
    )
    assert abs(float(fig._xy_wavelength) - 0.709) < 1e-12
    assert bool(getattr(fig, "_xy_dual_wl_display", False)) is False
    assert list(getattr(fig, "_xy_file_wavelength_info", None) or []) == []
    xl = ax.get_xlim()
    assert abs(xl[0] - 1.5) < 1e-9 and abs(xl[1] - 4.5) < 1e-9
    plt.close(fig)


def test_resolve_wavelength_old_session_empty_fwi():
    """Old pkls have no file_wavelength_info — resolver must use fig λ / default."""
    fig = plt.figure()
    AU.set_xy_axis_mode(fig, "2theta", wavelength=0.25)
    wl = AU.resolve_wavelength(
        fig=fig,
        args=SimpleNamespace(wl=None),
        file_wavelength_info=None,
        axis_mode="2theta",
    )
    assert abs(wl - 0.25) < 1e-12
    # Completely bare fig → CIF draw helper falls back to Cu Kα (BC)
    fig2 = plt.figure()
    wl2 = AU.resolve_cif_draw_wavelength(
        fig=fig2, args=SimpleNamespace(wl=None), warn=False,
    )
    assert abs(wl2 - AU.CU_KA_ANGSTROM) < 1e-12
    plt.close(fig)
    plt.close(fig2)


def test_get_xy_axis_mode_blank_xlabel_stays_unknown():
    """Old Fe_edge-style sessions with blank xlabel must not invent 2θ."""
    fig, ax = plt.subplots()
    ax.set_xlabel("")
    assert AU.get_xy_axis_mode(fig, ax=ax) == "unknown"
    assert AU.peaks_Q_to_domain([1.0, 2.0], "unknown") == []
    plt.close(fig)

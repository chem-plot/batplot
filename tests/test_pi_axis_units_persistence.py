"""p/i (style) and session must persist Options ``u`` / dual-wl metadata."""

from __future__ import annotations

import json
import pickle
from types import SimpleNamespace

import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.xy import axis_units as AU
from batplot.plot_modes.xy.style import apply_style_config, export_style_config
from batplot.plotting import update_labels


def _tick_state():
    return {
        "bx": True, "tx": False, "ly": True, "ry": False,
        "mbx": False, "mtx": False, "mly": False, "mry": False,
        "b_ticks": True, "t_ticks": False, "l_ticks": True, "r_ticks": False,
        "b_labels": True, "t_labels": False, "l_labels": True, "r_labels": False,
    }


def test_psg_roundtrip_dual_wl_and_axis_mode(tmp_path):
    fig, ax = plt.subplots()
    x = np.linspace(1.0, 4.0, 20)
    y = np.ones_like(x)
    ax.plot(x, y)
    ax.set_xlim(1.0, 4.0)
    ax.set_xlabel(AU.default_xlabel("Q"))
    AU.set_xy_axis_mode(fig, "Q", wavelength=0.709)
    fig._xy_dual_wl_display = False
    fig._xy_file_wavelength_info = [
        {"original_wl": 0.709, "conversion_wl": 1.54, "final_wl": 1.54},
    ]
    args = SimpleNamespace(wl=0.709, stack=False, files=[], ro=False, xaxis="Q")
    path = tmp_path / "dual.bpsg"
    # Build config the same way export does for psg geometry
    cfg = {
        "kind": "xy_style_geom",
        "ro_active": False,
        "geometry": {
            "xlabel": ax.get_xlabel(),
            "ylabel": "I",
            "xlim": list(ax.get_xlim()),
            "ylim": list(ax.get_ylim()),
            "axis_mode": "Q",
            "wavelength": 0.709,
            "dual_wl_display": False,
            "file_wavelength_info": list(fig._xy_file_wavelength_info),
        },
    }
    path.write_text(json.dumps(cfg), encoding="utf-8")

    fig2, ax2 = plt.subplots()
    ax2.plot(x, y)
    AU.set_xy_axis_mode(fig2, "Q", wavelength=1.54)  # stale
    fig2._xy_file_wavelength_info = []
    apply_style_config(
        str(path), fig2, ax2, [x], [y], [y.copy()], [0.0], [], args,
        _tick_state(), ["a"], update_labels,
    )
    assert abs(float(fig2._xy_wavelength) - 0.709) < 1e-12
    assert fig2._xy_file_wavelength_info[0]["original_wl"] == 0.709
    assert fig2._xy_file_wavelength_info[0]["conversion_wl"] == 1.54
    # resolve must prefer λ1 for Q
    wl = AU.resolve_wavelength(
        fig=fig2, args=args,
        file_wavelength_info=fig2._xy_file_wavelength_info,
        axis_mode="Q",
    )
    assert abs(wl - 0.709) < 1e-12
    plt.close(fig)
    plt.close(fig2)


def test_psg_skips_xlim_when_current_mode_is_energy(tmp_path):
    """XRD style must not overwrite xlim/xlabel on a known non-XRD figure."""
    fig, ax = plt.subplots()
    ax.plot([7000, 7200], [1, 1])
    ax.set_xlim(7000, 7200)
    ax.set_xlabel("Energy (eV)")
    args = SimpleNamespace(wl=None, stack=False, files=[], ro=False, xaxis="energy")
    path = tmp_path / "qstyle.bpsg"
    cfg = {
        "kind": "xy_style_geom",
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
        str(path), fig, ax, [np.array([7000.0, 7200.0])], [np.array([1.0, 1.0])],
        [np.array([1.0, 1.0])], [0.0], [], args, _tick_state(), ["a"], update_labels,
    )
    xl = ax.get_xlim()
    assert abs(xl[0] - 7000.0) < 1e-9 and abs(xl[1] - 7200.0) < 1e-9
    assert "energy" in (ax.get_xlabel() or "").lower()
    plt.close(fig)


def test_session_dict_includes_file_wavelength_info(tmp_path):
    """Dump path writes dual-wl pairs (load restores via sess keys)."""
    from batplot.plot_modes.xy.session import dump_session

    fig, ax = plt.subplots()
    x = [np.linspace(1.0, 3.0, 10)]
    y = [np.ones(10)]
    ax.plot(x[0], y[0])
    AU.set_xy_axis_mode(fig, "Q", wavelength=0.709)
    fig._xy_dual_wl_display = False
    fig._xy_file_wavelength_info = [
        {"original_wl": 0.709, "conversion_wl": 1.54, "final_wl": 1.54},
    ]
    args = SimpleNamespace(
        xaxis="Q", wl=0.709, stack=False, files=["a.xy"],
        autoscale=True, norm=False,
    )
    out = tmp_path / "sess.pkl"
    dump_session(
        str(out),
        fig=fig, ax=ax,
        x_data_list=x, y_data_list=y, orig_y=y,
        offsets_list=[0.0], labels=["a"], delta=0.0, args=args,
        tick_state=_tick_state(), skip_confirm=True,
    )
    with open(out, "rb") as f:
        sess = pickle.load(f)
    assert sess.get("dual_wl_display") is False
    assert sess["file_wavelength_info"][0]["original_wl"] == 0.709
    assert abs(sess["wavelength"] - 0.709) < 1e-12
    assert sess["axis_mode"] == "Q"
    plt.close(fig)

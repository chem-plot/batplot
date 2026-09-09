"""Every mode session dump must keep untrimmed data for expand-after-reload."""

from __future__ import annotations

import pickle
from types import SimpleNamespace

import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot.plot_modes.common.session_data_guarantee import (
    line_display_and_full_xy,
    longest_xy_pair,
)
from batplot.plot_modes.electrochem.dqdv_2d import (
    _DqdvArrayLine,
    build_dqdv_2d_snapshot,
    restore_dqdv_2d_companion_figure,
    update_dqdv_2d_potential_window,
)
from batplot.plot_modes.electrochem.session import _ec_line_payload
from batplot.plot_modes.xy.axis_range import _refilter_curves_from_full
from batplot.session import dump_session, load_xy_session
from conftest import loaded


class _Line:
    def __init__(self, x, y, *, orig=None):
        self._x = np.asarray(x, float)
        self._y = np.asarray(y, float)
        if orig is not None:
            self._original_xdata = np.asarray(orig[0], float)
            self._original_ydata = np.asarray(orig[1], float)

    def get_xdata(self):
        return self._x

    def get_ydata(self):
        return self._y

    def get_color(self):
        return "tab:blue"

    def get_linewidth(self):
        return 1.0

    def get_linestyle(self):
        return "-"

    def get_alpha(self):
        return None

    def get_visible(self):
        return True

    def get_label(self):
        return ""

    def get_marker(self):
        return None

    def get_markersize(self):
        return None

    def get_markerfacecolor(self):
        return None

    def get_markeredgecolor(self):
        return None


def test_longest_xy_pair_prefers_longer():
    x1, y1 = longest_xy_pair((np.arange(3), np.arange(3)), (np.arange(10), np.arange(10)))
    assert x1.size == 10


def test_line_display_and_full_prefers_originals():
    full_x = np.linspace(0, 10, 101)
    full_y = np.sin(full_x)
    disp_x = full_x[20:40]
    disp_y = full_y[20:40]
    ln = _Line(disp_x, disp_y, orig=(full_x, full_y))
    xd, yd, xf, yf = line_display_and_full_xy(ln)
    assert xd.size == 20
    assert xf.size == 101


def test_ec_line_payload_keeps_full_when_display_filtered():
    full_x = np.linspace(0, 5, 200)
    full_y = np.cos(full_x)
    ln = _Line(full_x[50:80], full_y[50:80], orig=(full_x, full_y))
    payload = _ec_line_payload(ln)
    assert payload["x"].size == 30
    assert payload["x_full"].size == 200
    assert payload["original_xdata"].size == 200


def test_xy_narrow_save_expand_keeps_master(session_path, fake_args):
    x_full = np.linspace(0.0, 100.0, 1001)
    y_full = np.sin(x_full)
    mask = (x_full >= 20.0) & (x_full <= 40.0)
    x_disp, y_disp = x_full[mask].copy(), y_full[mask].copy()

    fig, ax = plt.subplots()
    ax.plot(x_disp, y_disp)
    from batplot.plot_modes.xy.full_data import install_master_full

    install_master_full(fig, [x_full], [y_full], force=True)
    x_data_list = [x_disp.copy()]
    y_data_list = [y_disp.copy()]
    orig_y = [y_disp.copy()]
    x_full_list = [x_full.copy()]
    raw_y_full_list = [y_full.copy()]
    offsets = [0.0]
    labels = ["c1.xy"]

    class L:
        def set_data(self, x, y):
            pass

    _refilter_curves_from_full(
        args=fake_args,
        labels=labels,
        x_data_list=x_data_list,
        y_data_list=y_data_list,
        orig_y=orig_y,
        offsets_list=offsets,
        x_full_list=x_full_list,
        raw_y_full_list=raw_y_full_list,
        new_min=30.0,
        new_max=35.0,
        _line=lambda i: L(),
    )
    assert x_data_list[0].size < 100

    p = session_path("guarantee_xy.pkl")
    dump_session(
        p,
        fig=fig,
        ax=ax,
        x_data_list=x_data_list,
        y_data_list=y_data_list,
        orig_y=orig_y,
        x_full_list=x_full_list,
        raw_y_full_list=raw_y_full_list,
        offsets_list=offsets,
        labels=labels,
        delta=0.0,
        args=fake_args,
        tick_state={},
        skip_confirm=True,
    )
    with open(p, "rb") as fh:
        sess = pickle.load(fh)
    assert sess["master_x_full_data"][0].size == 1001
    assert sess["x_full_data"][0].size == 1001
    assert sess["x_data"][0].size < 100

    _fig2, _ax2, mk = loaded(load_xy_session(p))
    assert mk["x_full_list"][0].size == 1001
    _refilter_curves_from_full(
        args=mk["args"],
        labels=mk["labels"],
        x_data_list=mk["x_data_list"],
        y_data_list=mk["y_data_list"],
        orig_y=mk["orig_y"],
        offsets_list=mk["offsets_list"],
        x_full_list=mk["x_full_list"],
        raw_y_full_list=mk["raw_y_full_list"],
        new_min=0.0,
        new_max=100.0,
        _line=lambda i: L(),
    )
    assert mk["x_data_list"][0].size == 1001
    plt.close(fig)
    plt.close(_fig2)


def test_operando_dump_keeps_array_master(tmp_path):
    from batplot.plot_modes.operando.session import dump_operando_session, load_operando_session

    fig, ax = plt.subplots()
    Z = np.arange(60, dtype=float).reshape(6, 10)
    im = ax.imshow(Z, origin="lower", aspect="auto", extent=(0, 10, 0, 6))
    cbar = fig.colorbar(im, ax=ax, fraction=0.05)
    ax.set_xlim(2, 5)
    ax.set_ylim(1, 4)
    im.set_clim(10, 40)
    p = tmp_path / "op.pkl"
    dump_operando_session(str(p), fig=fig, ax=ax, im=im, cbar=cbar, skip_confirm=True)
    with open(p, "rb") as fh:
        sess = pickle.load(fh)
    assert sess["operando"]["array"].shape == (6, 10)
    assert sess["operando"]["array_master"].shape == (6, 10)
    assert np.allclose(sess["operando"]["array_master"], Z)
    # View limits are metadata only
    assert sess["operando"]["labels"]["xlim"] == pytest.approx((2, 5))
    loaded = load_operando_session(str(p))
    assert loaded is not None
    fig2 = loaded[0]
    assert getattr(fig2, "_operando_array_master", None) is not None
    assert np.asarray(fig2._operando_array_master).shape == (6, 10)
    plt.close(fig)
    plt.close(fig2)


def test_dqdv_source_uses_originals_not_filtered_display():
    fig, ax = plt.subplots()
    Z = np.linspace(0, 1, 12).reshape(3, 4)
    im = ax.imshow(Z, origin="lower", aspect="auto")
    cbar = fig.colorbar(im, ax=ax, fraction=0.05)
    fig._is_dqdv_2d_contour = True
    v = np.linspace(1.0, 4.0, 81)
    dq = np.sin(v)
    # Live line looks cropped; originals keep full domain
    ln_c = _DqdvArrayLine(v[20:40], dq[20:40])
    ln_c._original_xdata = v
    ln_c._original_ydata = dq
    ln_d = _DqdvArrayLine(v[20:40], -dq[20:40])
    ln_d._original_xdata = v
    ln_d._original_ydata = -dq
    fig._dqdv_2d_file_data = [
        {
            "filename": "cell.csv",
            "display_name": "cell",
            "visible": True,
            "cycle_lines": {1: {"charge": ln_c, "discharge": ln_d}},
        }
    ]
    snap = build_dqdv_2d_snapshot(fig, ax, im, 2.0, 3.0, ["a", "b", "c"], "dQ/dV", cbar)
    assert snap is not None
    src = snap["source_file_data"][0]["cycle_lines"][1]["charge"]
    assert np.asarray(src["x"]).size == 81
    restored = restore_dqdv_2d_companion_figure(snap)
    assert restored is not None
    cfig, cax, cim, _ = restored
    assert update_dqdv_2d_potential_window(cfig, cax, cim, 1.2, 3.8) is True
    plt.close(cfig)
    plt.close(fig)


def test_histo_snapshot_keeps_full_values_with_x_window():
    from batplot.plot_modes.histo.interactive import _snapshot_state
    from batplot.plot_modes.histo.plot import HistoState, HistoStyle
    from batplot.plot_modes.histo.wizard import HistoSetup

    values = np.linspace(0, 100, 500)
    setup = HistoSetup(
        column_index=0,
        column_name="x",
        values=values,
        xmin=20.0,
        xmax=40.0,
        bin_edges=np.linspace(20, 40, 11),
    )
    state = HistoState(setup=setup, style=HistoStyle(), source_path="")
    snap = _snapshot_state(state)
    assert np.asarray(snap["setup"]["values"]).size == 500
    assert np.asarray(snap["setup"]["values_master"]).size == 500
    assert snap["setup"]["xmin"] == 20.0


def test_cpc_dump_includes_full_series(tmp_path):
    from batplot.plot_modes.cpc.session import dump_cpc_session, load_cpc_session

    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    x = np.arange(1, 21, dtype=float)
    sc_c = ax.scatter(x, x * 10)
    sc_d = ax.scatter(x, x * 9)
    sc_e = ax2.scatter(x, np.full_like(x, 99.0))
    ax.set_xlim(5, 10)
    p = tmp_path / "cpc.pkl"
    dump_cpc_session(
        str(p),
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
        skip_confirm=True,
    )
    with open(p, "rb") as fh:
        sess = pickle.load(fh)
    assert sess["series"]["charge"]["x"].size == 20
    assert sess["series"]["charge"]["x_full"].size == 20
    assert sess["axis"]["xlim"] == pytest.approx((5, 10))
    loaded = load_cpc_session(str(p))
    assert loaded is not None
    plt.close(fig)
    plt.close(loaded[0])


def test_cpc_multifile_session_keeps_scatter_masters(tmp_path):
    from batplot.plot_modes.common.session_data_guarantee import install_scatter_xy_master
    from batplot.plot_modes.cpc.session import dump_cpc_session

    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    x1 = np.arange(1, 31, dtype=float)
    x2 = np.arange(1, 21, dtype=float)
    sc_c1 = ax.scatter(x1, x1)
    sc_d1 = ax.scatter(x1, x1 * 0.9)
    sc_e1 = ax2.scatter(x1, np.full_like(x1, 98.0))
    sc_c2 = ax.scatter(x2, x2)
    sc_d2 = ax.scatter(x2, x2 * 0.9)
    sc_e2 = ax2.scatter(x2, np.full_like(x2, 97.0))
    install_scatter_xy_master(sc_c1, x1, x1)
    install_scatter_xy_master(sc_d1, x1, x1 * 0.9)
    install_scatter_xy_master(sc_e1, x1, np.full_like(x1, 98.0))
    install_scatter_xy_master(sc_c2, x2, x2)
    install_scatter_xy_master(sc_d2, x2, x2 * 0.9)
    install_scatter_xy_master(sc_e2, x2, np.full_like(x2, 97.0))
    # Simulate a bad shrink of live offsets — masters must still dump full.
    sc_c1.set_offsets(np.column_stack([x1[:5], x1[:5]]))
    file_data = [
        {
            "filename": "a.csv",
            "display_name": "a",
            "visible": True,
            "eff_inverted": False,
            "sc_charge": sc_c1,
            "sc_discharge": sc_d1,
            "sc_eff": sc_e1,
        },
        {
            "filename": "b.csv",
            "display_name": "b",
            "visible": True,
            "eff_inverted": False,
            "sc_charge": sc_c2,
            "sc_discharge": sc_d2,
            "sc_eff": sc_e2,
        },
    ]
    p = tmp_path / "cpc_multi.pkl"
    dump_cpc_session(
        str(p),
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c1,
        sc_discharge=sc_d1,
        sc_eff=sc_e1,
        file_data=file_data,
        skip_confirm=True,
    )
    with open(p, "rb") as fh:
        sess = pickle.load(fh)
    assert sess["multi_files"][0]["charge"]["x"].size == 5
    assert sess["multi_files"][0]["charge"]["x_full"].size == 30
    assert sess["multi_files"][1]["charge"]["x_full"].size == 20
    plt.close(fig)


def test_histo_style_export_omits_column_data(tmp_path):
    from batplot.plot_modes.common.session_data_guarantee import style_payload_forbids_data_arrays
    from batplot.plot_modes.histo.interactive import _export_style
    from batplot.plot_modes.histo.plot import HistoState, HistoStyle
    from batplot.plot_modes.histo.wizard import HistoSetup
    import json

    fig, ax = plt.subplots()
    values = np.linspace(0, 10, 50)
    state = HistoState(
        setup=HistoSetup(
            column_index=0,
            column_name="x",
            values=values,
            xmin=0.0,
            xmax=10.0,
            bin_edges=np.linspace(0, 10, 6),
        ),
        style=HistoStyle(),
        source_path="data.csv",
    )
    out = tmp_path / "h.bpsh"
    _export_style(fig, ax, state, str(out), include_geometry=True)
    payload = json.loads(out.read_text(encoding="utf-8"))
    hits = style_payload_forbids_data_arrays(payload)
    assert hits == [], hits
    assert "setup" not in payload
    assert "source_path" not in payload
    plt.close(fig)


def test_cpc_style_export_omits_efficiency_offsets():
    from batplot.plot_modes.common.session_data_guarantee import style_payload_forbids_data_arrays
    from batplot.plot_modes.cpc.style import _style_snapshot

    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    x = np.arange(1, 11, dtype=float)
    sc_c = ax.scatter(x, x)
    sc_d = ax.scatter(x, x * 0.9)
    sc_e = ax2.scatter(x, np.full_like(x, 99.0))
    payload = _style_snapshot(fig, ax, ax2, sc_c, sc_d, sc_e, file_data=None)
    hits = style_payload_forbids_data_arrays(payload)
    assert hits == [], hits
    assert "offsets" not in (payload.get("series", {}).get("efficiency") or {})
    plt.close(fig)


def test_operando_style_export_omits_ions_abs():
    from batplot.plot_modes.common.session_data_guarantee import style_payload_forbids_data_arrays
    from batplot.plot_modes.operando.style import build_operando_ec_style_config_v2

    fig, ax = plt.subplots()
    Z = np.arange(40, dtype=float).reshape(4, 10)
    im = ax.imshow(Z, origin="lower", aspect="auto")
    cbar = fig.colorbar(im, ax=ax, fraction=0.05)
    ec_ax = fig.add_axes([0.7, 0.1, 0.2, 0.8])
    t = np.linspace(0, 5, 50)
    ec_ax.plot(t, np.sin(t))
    ec_ax._ec_time_h = t
    ec_ax._ec_voltage_v = np.sin(t)
    ec_ax._ec_current_mA = np.cos(t)
    ec_ax._ec_y_mode = "ions"
    ec_ax._ion_params = {
        "mass_mg": 1.0,
        "cap_per_ion_mAh_g": 100.0,
        "start_ions": 0.0,
    }
    ec_ax._ions_abs = np.linspace(0, 1, 50)
    cfg, _ext = build_operando_ec_style_config_v2(fig, ax, im, cbar, ec_ax, "ps")
    hits = style_payload_forbids_data_arrays(cfg)
    assert hits == [], hits
    assert "ions_abs" not in (cfg.get("ec") or {})
    plt.close(fig)


def test_bc_missing_new_full_keys_still_load(tmp_path):
    """Older pkls without master keys must load without crash."""
    from batplot.plot_modes.operando.session import dump_operando_session, load_operando_session

    fig, ax = plt.subplots()
    Z = np.ones((3, 4))
    im = ax.imshow(Z)
    cbar = fig.colorbar(im, ax=ax)
    p = tmp_path / "legacy_op.pkl"
    dump_operando_session(str(p), fig=fig, ax=ax, im=im, cbar=cbar, skip_confirm=True)
    with open(p, "rb") as fh:
        sess = pickle.load(fh)
    sess["operando"].pop("array_master", None)
    sess["operando"].pop("extent_master", None)
    with open(p, "wb") as fh:
        pickle.dump(sess, fh)
    loaded = load_operando_session(str(p))
    assert loaded is not None
    plt.close(fig)
    plt.close(loaded[0])

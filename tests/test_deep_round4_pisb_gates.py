"""Hard gates for Round-4 deep dig: CPC legend/session, batch import, undo fidelity."""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from batplot import session as S
from batplot.plot_modes.batch_session.load import XyPanel
from batplot.plot_modes.batch_session.menu_xy import _apply_style_path
from batplot.plot_modes.cpc.legend import _get_legend_title


def test_cpc_legend_title_empty_get_preserves():
    fig, ax = plt.subplots()
    fig._cpc_legend_title = ""
    try:
        assert _get_legend_title(fig, default="Series") == ""
        # Style apply key-presence (same assignment as style.py legend block).
        title_val = ""
        fig._cpc_legend_title = "" if title_val is None else str(title_val)
        assert fig._cpc_legend_title == ""
        assert _get_legend_title(fig) == ""
    finally:
        plt.close(fig)


def test_cpc_session_preserves_empty_series_label(tmp_path):
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc_c = ax.scatter([1, 2], [10, 20])
    sc_d = ax.scatter([1, 2], [9, 18], label="Discharge capacity")
    sc_e = ax2.scatter([1, 2], [90, 95], label="Coulombic efficiency")
    # Matplotlib ignores label="" in the ctor; rename menus use set_label("").
    sc_c.set_label("")
    path = tmp_path / "cpc.pkl"
    try:
        S.dump_cpc_session(
            str(path),
            fig=fig,
            ax=ax,
            ax2=ax2,
            sc_charge=sc_c,
            sc_discharge=sc_d,
            sc_eff=sc_e,
            skip_confirm=True,
        )
        with open(path, "rb") as fh:
            blob = pickle.load(fh)
        assert blob["series"]["charge"]["label"] == ""
    finally:
        plt.close(fig)


def test_xy_batch_apply_style_returns_false_on_reject(tmp_path):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [1, 2])
    bad = tmp_path / "ec.bps"
    bad.write_text(json.dumps({"kind": "ec_style", "version": 2}), encoding="utf-8")
    panel = XyPanel(
        path=str(tmp_path / "a.pkl"),
        fig=fig,
        ax=ax,
        menu_kwargs={
            "x_data_list": [np.array([0.0, 1.0])],
            "y_data_list": [np.array([1.0, 2.0])],
            "orig_y": [np.array([1.0, 2.0])],
            "offsets_list": [0.0],
            "label_text_objects": [],
            "args": type("A", (), {"stack": False, "xaxis": "2theta", "norm": False})(),
            "labels": ["c1"],
            "cif_globals": {},
        },
    )
    try:
        assert _apply_style_path(panel, str(bad)) is False
    finally:
        plt.close(fig)


def test_dual_axis_u_pushes_before_mutating_c_th():
    src = Path("batplot/plot_modes/electrochem/dual_axis_menu.py").read_text(encoding="utf-8")
    u_idx = src.find("elif sub == 'u':")
    assert u_idx >= 0
    region = src[u_idx : u_idx + 2500]
    push_idx = region.find('push_state("update-c-theoretical")')
    assign_idx = region.find("fig._xaxis_c_theoretical = new_c_th")
    assert 0 <= push_idx < assign_idx


def test_batch_io_expanduser_on_typed_paths():
    src = Path("batplot/plot_modes/batch_session/batch_io.py").read_text(encoding="utf-8")
    assert "os.path.expanduser(choice)" in src
    assert src.count("expanduser") >= 2


def test_operando_undo_empty_y_time_source_gate():
    src = Path("batplot/plot_modes/operando/undo_state.py").read_text(encoding="utf-8")
    assert "y_time') or 'Time (h)'" not in src
    assert "'y_time' in ec_labs" in src


def test_intensity_validate_before_snapshot():
    src = Path("batplot/plot_modes/operando/intensity_menu.py").read_text(encoding="utf-8")
    idx = src.find("lo, hi = map(float, line.split())")
    assert idx >= 0
    assert src.find('snapshot("operando-intensity-range")', idx) > idx


def test_cpc_session_load_empty_legend_title(tmp_path):
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc_c = ax.scatter([1], [1], label="Charge capacity")
    sc_d = ax.scatter([1], [1], label="Discharge capacity")
    sc_e = ax2.scatter([1], [90], label="Coulombic efficiency")
    fig._cpc_legend_title = ""
    path = tmp_path / "cpc_leg.pkl"
    try:
        S.dump_cpc_session(
            str(path),
            fig=fig,
            ax=ax,
            ax2=ax2,
            sc_charge=sc_c,
            sc_discharge=sc_d,
            sc_eff=sc_e,
            skip_confirm=True,
        )
        with open(path, "rb") as fh:
            blob = pickle.load(fh)
        assert blob.get("legend", {}).get("title") == ""
        result = S.load_cpc_session(str(path))
        assert result is not None
        fig2 = result[0]
        assert getattr(fig2, "_cpc_legend_title", None) == ""
        plt.close(fig2)
    finally:
        plt.close(fig)

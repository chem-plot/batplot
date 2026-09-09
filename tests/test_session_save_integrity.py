"""Session save (``s``/``os``) integrity: no false success, path expand, key parity."""

from __future__ import annotations

import os
import pickle
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot.plot_modes.batch_session.batch_io import _save_sessions_as_new
from batplot.plot_modes.common.session_helpers import resolve_session_save_path
from batplot.plot_modes.cpc.session import dump_cpc_session
from batplot.plot_modes.electrochem.dqdv_2d import build_dqdv_2d_snapshot
from batplot.plot_modes.electrochem.session import dump_ec_session
from batplot.plot_modes.operando.session import dump_operando_session
from batplot.plot_modes.xy.session import dump_session


def test_resolve_session_save_path_expands_user_and_ext(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()

    def _expanduser(p: str) -> str:
        s = str(p)
        if s == "~":
            return str(home)
        if s.startswith("~/") or s.startswith("~\\"):
            return str(home / s[2:])
        return s

    monkeypatch.setattr(os.path, "expanduser", _expanduser)
    out = resolve_session_save_path("~/mysess", folder=str(tmp_path / "other"))
    assert out == str((home / "mysess.pkl").resolve())
    assert "~" not in out

    rel = resolve_session_save_path("nested/foo", folder=str(tmp_path))
    assert "nested" in rel and rel.endswith("foo.pkl")
    assert os.path.isabs(rel)


def test_xy_dump_returns_false_on_io_error_no_false_stamp(tmp_path):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    args = SimpleNamespace(stack=False, autoscale=False, norm=False, files=[], xaxis="Q")
    tick_state = {"bx": True, "tx": False, "ly": True, "ry": False}
    bad = tmp_path / "missing_dir" / "x.pkl"
    fig._last_session_save_path = None  # type: ignore[attr-defined]
    ok = dump_session(
        str(bad),
        fig=fig,
        ax=ax,
        x_data_list=[np.array([0.0, 1.0])],
        y_data_list=[np.array([0.0, 1.0])],
        orig_y=[np.array([0.0, 1.0])],
        x_full_list=[np.array([0.0, 1.0])],
        raw_y_full_list=[np.array([0.0, 1.0])],
        offsets_list=[0.0],
        labels=["a"],
        delta=0.0,
        args=args,
        tick_state=tick_state,
        skip_confirm=True,
    )
    assert ok is False
    assert getattr(fig, "_last_session_save_path", None) in (None, "")
    plt.close(fig)


def test_ec_dump_returns_false_on_io_error(tmp_path):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [3.0, 3.2])
    bad = tmp_path / "nope" / "ec.pkl"
    fig._last_session_save_path = None  # type: ignore[attr-defined]
    ok = dump_ec_session(
        str(bad),
        fig=fig,
        ax=ax,
        cycle_lines={},
        skip_confirm=True,
    )
    assert ok is False
    assert getattr(fig, "_last_session_save_path", None) in (None, "")
    plt.close(fig)


def test_ec_dump_honors_legend_user_visible(tmp_path):
    fig, ax = plt.subplots()
    (ln,) = ax.plot([0, 1], [3.0, 3.2], label="c1")
    leg = ax.legend()
    leg.set_visible(True)
    fig._ec_legend_user_visible = False  # type: ignore[attr-defined]
    path = tmp_path / "ec_leg.pkl"
    assert dump_ec_session(str(path), fig=fig, ax=ax, cycle_lines={}, skip_confirm=True)
    with open(path, "rb") as fh:
        sess = pickle.load(fh)
    assert sess["legend"]["visible"] is False
    plt.close(fig)


def test_xy_dump_show_cif_hkl_from_fig_attr(tmp_path):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    fig._bp_show_cif_hkl = True  # type: ignore[attr-defined]
    args = SimpleNamespace(stack=False, autoscale=False, norm=False, files=[], xaxis="Q")
    path = tmp_path / "xy_cif.pkl"
    ok = dump_session(
        str(path),
        fig=fig,
        ax=ax,
        x_data_list=[np.array([0.0, 1.0])],
        y_data_list=[np.array([0.0, 1.0])],
        orig_y=[np.array([0.0, 1.0])],
        offsets_list=[0.0],
        labels=["a"],
        delta=0.0,
        args=args,
        tick_state={},
        show_cif_hkl=None,
        skip_confirm=True,
    )
    assert ok is True
    with open(path, "rb") as fh:
        sess = pickle.load(fh)
    assert sess["show_cif_hkl"] is True
    plt.close(fig)


def test_cpc_and_operando_dump_bool_on_failure(tmp_path):
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc = ax.scatter([1], [10])
    bad = tmp_path / "missing" / "c.pkl"
    assert (
        dump_cpc_session(
            str(bad),
            fig=fig,
            ax=ax,
            ax2=ax2,
            sc_charge=sc,
            sc_discharge=sc,
            sc_eff=sc,
            skip_confirm=True,
        )
        is False
    )

    im = ax.imshow(np.zeros((4, 4)), origin="lower")
    cbar = fig.colorbar(im, ax=ax)
    assert (
        dump_operando_session(
            str(tmp_path / "missing2" / "o.pkl"),
            fig=fig,
            ax=ax,
            im=im,
            cbar=cbar,
            skip_confirm=True,
        )
        is False
    )
    plt.close(fig)


def test_batch_save_as_new_updates_panel_path(tmp_path):
    fig, ax = plt.subplots()
    panel = SimpleNamespace(path=str(tmp_path / "old.pkl"), fig=fig, ax=ax)
    new_path = str(tmp_path / "new.pkl")

    def _save(_panel, path):
        Path(path).write_bytes(b"x")

    with patch(
        "batplot.plot_modes.batch_session.batch_io._prompt_one_session_path",
        return_value=new_path,
    ), patch(
        "batplot.plot_modes.batch_session.batch_io.choose_save_path",
        return_value=str(tmp_path),
    ), patch(
        "batplot.plot_modes.batch_session.batch_io._list_pkl_files",
        return_value=[],
    ):
        _save_sessions_as_new([panel], [0], _save)
    assert panel.path == os.path.abspath(new_path)
    assert fig._last_session_save_path == os.path.abspath(new_path)  # type: ignore[attr-defined]
    plt.close(fig)


def test_dqdv_snapshot_includes_title_offsets_and_cbar_side():
    fig, ax = plt.subplots()
    im = ax.imshow(np.ones((3, 5)), origin="lower")
    cbar = fig.colorbar(im, ax=ax)
    cbar.ax.yaxis.set_ticks_position("right")
    cbar.ax.yaxis.set_label_position("right")
    ax._top_xlabel_manual_offset_y_pts = 12.0  # type: ignore[attr-defined]
    fig._dqdv_2d_nx = 10  # type: ignore[attr-defined]
    fig._dqdv_2d_v_lo_orig = 2.0  # type: ignore[attr-defined]
    fig._dqdv_2d_v_hi_orig = 4.0  # type: ignore[attr-defined]
    snap = build_dqdv_2d_snapshot(fig, ax, im, 2.0, 4.0, ["a", "b", "c"], "dQ/dV", cbar)
    assert snap is not None
    assert snap["title_offsets"]["top_y"] == pytest.approx(12.0)
    assert snap["colorbar"].get("ticks_left") is False
    assert snap["colorbar"].get("label_left") is False
    plt.close(fig)


def test_xy_dump_cancel_before_tick_mutate(tmp_path):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    args = SimpleNamespace(stack=False, autoscale=False, norm=False, files=[], xaxis="Q")
    tick_state = {"bx": True, "tx": False, "ly": True, "ry": False, "mbx": False}
    path = tmp_path / "cancel.pkl"
    with patch(
        "batplot.plot_modes.xy.session._confirm_overwrite",
        return_value=None,
    ):
        ok = dump_session(
            str(path),
            fig=fig,
            ax=ax,
            x_data_list=[np.array([0.0, 1.0])],
            y_data_list=[np.array([0.0, 1.0])],
            orig_y=[np.array([0.0, 1.0])],
            offsets_list=[0.0],
            labels=["a"],
            delta=0.0,
            args=args,
            tick_state=tick_state,
            skip_confirm=False,
        )
    assert ok is False
    assert not path.exists()
    assert not hasattr(ax, "_saved_tick_state") or ax._saved_tick_state != {"forced": True}
    plt.close(fig)

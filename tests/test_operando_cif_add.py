"""Operando interactive CIF add (c → a) and p/i/s/b persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot.plot_modes.operando.plot import append_operando_cif_file
from batplot.plot_modes.operando.session import dump_operando_session, load_operando_session
from batplot.plot_modes.operando.style import build_operando_ec_style_config_v2
from batplot.plot_modes.operando.style_apply import apply_operando_ec_style_config


CIF_PATH = Path("/Users/tiandai/Downloads/ICSD_CollCode60433.cif")
SAMPLE_PKL = Path(
    "/Users/tiandai/Library/CloudStorage/OneDrive-UniversitetetiOslo/My files/"
    "Li2FeSeO_processing/Figures/InsituSynthesis.pkl"
)


def _minimal_operando_figure():
    fig, ax = plt.subplots(figsize=(6, 4))
    im = ax.imshow(np.random.rand(8, 12), origin="lower", aspect="auto", extent=(1, 5, 0, 7))
    cbar = fig.colorbar(im, ax=ax)
    fig._operando_axis_mode = "Q"  # type: ignore[attr-defined]
    fig._operando_wl = 0.709  # type: ignore[attr-defined]
    ax.set_xlim(1, 5)
    return fig, ax, im, cbar


def _write_minimal_cif(path: Path) -> None:
    path.write_text(
        "data_test\n"
        "_cell_length_a 3.0\n_cell_length_b 3.0\n_cell_length_c 3.0\n"
        "_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n"
        "_symmetry_space_group_name_H-M 'P 1'\n"
        "loop_\n_atom_site_label\n_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\n"
        "Li 0 0 0\n",
        encoding="utf-8",
    )


def test_operando_cif_extend_grows_qmax_on_widen(tmp_path):
    """Widening X must raise qmax_sim (parity with XY CIF extend)."""
    from batplot.plot_modes.operando.plot import (
        append_operando_cif_file,
        extend_operando_cif_series_for_xmax,
    )
    from batplot.plot_modes.operando.layout import _redraw_operando_cif_if_present

    cif = tmp_path / "tiny.cif"
    _write_minimal_cif(cif)
    fig, ax, _im, _cbar = _minimal_operando_figure()
    ax.set_xlim(1.0, 2.0)
    append_operando_cif_file(fig, ax, str(cif), redraw=False)
    series = ax._operando_cif_tick_series
    q_before = float(series[0][4])
    n_before = len(series[0][2] or [])
    ax.set_xlim(1.0, 40.0)
    assert extend_operando_cif_series_for_xmax(fig, ax, 40.0) is True
    series2 = ax._operando_cif_tick_series
    assert float(series2[0][4]) > q_before
    assert len(series2[0][2] or []) >= n_before
    # redraw path also extends (no crash)
    _redraw_operando_cif_if_present(fig, ax)
    plt.close(fig)


@pytest.mark.skipif(not CIF_PATH.is_file(), reason="sample CIF not on this machine")
def test_append_operando_cif_file_adds_series():
    fig, ax, _im, _cbar = _minimal_operando_figure()
    lab, resolved = append_operando_cif_file(fig, ax, str(CIF_PATH), redraw=True)
    series = getattr(ax, "_operando_cif_tick_series", [])
    assert len(series) == 1
    assert lab
    assert os.path.isfile(resolved)
    assert series[0][1] == resolved
    hkl = getattr(ax, "_operando_cif_hkl_label_map", {})
    assert resolved in hkl or str(CIF_PATH.resolve()) in hkl
    # duplicate path rejected
    with pytest.raises(ValueError, match="already loaded"):
        append_operando_cif_file(fig, ax, str(CIF_PATH), redraw=False)
    plt.close(fig)


@pytest.mark.skipif(not CIF_PATH.is_file(), reason="sample CIF not on this machine")
def test_operando_cif_add_survives_session_roundtrip(tmp_path):
    fig, ax, im, cbar = _minimal_operando_figure()
    append_operando_cif_file(fig, ax, str(CIF_PATH), redraw=True)
    n_before = len(ax._operando_cif_tick_series)
    out = tmp_path / "op_cif.pkl"
    dump_operando_session(
        str(out), fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=None, skip_confirm=True
    )
    plt.close(fig)

    loaded = load_operando_session(str(out))
    assert loaded is not None
    fig2, ax2, _im2, _cbar2, _ec = loaded
    series2 = getattr(ax2, "_operando_cif_tick_series", [])
    assert len(series2) == n_before
    assert any("60433" in str(e[1]) or "60433" in str(e[0]) for e in series2)
    plt.close(fig2)


@pytest.mark.skipif(not CIF_PATH.is_file(), reason="sample CIF not on this machine")
def test_operando_cif_add_in_style_psg_roundtrip(tmp_path):
    fig, ax, im, cbar = _minimal_operando_figure()
    append_operando_cif_file(fig, ax, str(CIF_PATH), redraw=True)
    cfg, ext = build_operando_ec_style_config_v2(fig, ax, im, cbar, None, "psg")
    assert ext == ".bpsg"
    assert "cif" in cfg
    assert cfg["cif"].get("files")
    assert cfg["cif"].get("tick_series")
    style_path = tmp_path / "op.bpsg"
    style_path.write_text(json.dumps(cfg), encoding="utf-8")

    fig2, ax2, im2, cbar2 = _minimal_operando_figure()
    assert not getattr(ax2, "_operando_cif_tick_series", None)
    ok = apply_operando_ec_style_config(
        cfg, fig=fig2, ax=ax2, im=im2, cbar=cbar2, ec_ax=None, silent=True
    )
    assert ok
    assert len(getattr(ax2, "_operando_cif_tick_series", []) or []) == 1
    plt.close(fig)
    plt.close(fig2)


def test_ask_file_dialog_passes_title_and_cif_filter(monkeypatch):
    """CIF add must open the OS dialog with CIF filters (no typed path prompt)."""
    from batplot import utils as U

    seen = {}

    def _fake_macos(initialdir, filetypes=None, *, title="Select a file", multiple=True):
        seen["backend"] = "macos"
        seen["filetypes"] = filetypes
        seen["title"] = title
        seen["initialdir"] = initialdir
        return []

    def _fake_tk(initialdir, filetypes=None, *, title="Select a file", multiple=True):
        seen["backend"] = "tk"
        seen["filetypes"] = filetypes
        seen["title"] = title
        return []

    # _ask_file_dialog delegates to _ask_files_dialog_* backends.
    monkeypatch.setattr(U, "_ask_files_dialog_macos", _fake_macos)
    monkeypatch.setattr(U, "_ask_files_dialog_tk", _fake_tk)
    monkeypatch.setattr(U, "_ask_files_dialog_zenity", lambda *a, **k: [])

    out = U._ask_file_dialog(filetypes=(".cif", ".CIF"), title="Select a CIF file")
    assert out is None
    assert seen["title"] == "Select a CIF file"
    assert seen["filetypes"] == (".cif", ".CIF")
    assert seen["backend"] in ("macos", "tk")


def test_add_cif_interactive_opens_dialog_immediately(monkeypatch, tmp_path):
    """``a`` must call the file picker first — never wait for typed path / ``c``."""
    from batplot.plot_modes.operando import interactive as OI
    from batplot.plot_modes.common import menu_rendering as MR
    from batplot.plot_modes.common import terminal as T
    import batplot.utils as U

    cif = tmp_path / "phase.cif"
    # Minimal CIF; append may succeed or fail — we only assert the dialog opens first.
    cif.write_text(
        "data_test\n_cell_length_a 3.0\n_cell_length_b 3.0\n_cell_length_c 3.0\n"
        "_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n"
        "loop_\n_atom_site_label\n_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\n"
        "Li 0 0 0\n",
        encoding="utf-8",
    )

    dialog_calls = []

    def _fake_dialog(*_a, **kwargs):
        dialog_calls.append(kwargs)
        return [str(cif)]

    monkeypatch.setattr(U, "_ask_files_dialog", _fake_dialog)

    # main ``c`` → CIF ``a`` → CIF ``q`` → main ``q`` (Q-mode: no wavelength prompt)
    feed_vals = ["c", "a", "q", "q"]
    it = iter(feed_vals)

    def _feed(*_a, **_k):
        try:
            return next(it)
        except StopIteration:
            return "q"

    monkeypatch.setattr(T, "safe_input", _feed)
    monkeypatch.setattr(OI, "_safe_input", _feed)
    monkeypatch.setattr(T, "prompt_menu_key", lambda *a, **k: _feed().strip().lower())
    monkeypatch.setattr(MR, "prompt_menu_key", lambda *a, **k: _feed().strip().lower())
    monkeypatch.setattr(OI, "prompt_menu_key", lambda *a, **k: _feed().strip().lower())
    monkeypatch.setattr(OI, "choose_save_path", lambda *a, **k: None)

    fig, ax = plt.subplots()
    im = ax.imshow(np.random.rand(6, 8), origin="lower", aspect="auto")
    cbar = fig.colorbar(im)
    fig._operando_axis_mode = "Q"  # type: ignore[attr-defined]
    fig._operando_wl = 0.709  # type: ignore[attr-defined]
    try:
        OI.operando_ec_interactive_menu(fig, ax, im, cbar, None, canvas_mode=True)
    finally:
        try:
            plt.close(fig)
        except Exception:
            pass

    assert dialog_calls, "file picker was never opened for CIF add"
    assert len(dialog_calls) == 1, "picker must open once (no re-prompt after select)"
    assert dialog_calls[0].get("title") == "Select CIF file(s)"
    assert dialog_calls[0].get("filetypes") == (".cif", ".CIF")
    assert dialog_calls[0].get("multiple") is True


@pytest.mark.skipif(not SAMPLE_PKL.is_file(), reason="sample operando pkl not on this machine")
@pytest.mark.skipif(not CIF_PATH.is_file(), reason="sample CIF not on this machine")
def test_add_cif_to_user_insitu_pkl(tmp_path):
    loaded = load_operando_session(str(SAMPLE_PKL))
    assert loaded is not None
    fig, ax, im, cbar, ec_ax = loaded
    n0 = len(getattr(ax, "_operando_cif_tick_series", None) or [])
    assert n0 >= 1
    append_operando_cif_file(fig, ax, str(CIF_PATH), redraw=True)
    n1 = len(ax._operando_cif_tick_series)
    assert n1 == n0 + 1
    out = tmp_path / "InsituSynthesis_with_extra_cif.pkl"
    dump_operando_session(
        str(out), fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax, skip_confirm=True
    )
    plt.close(fig)

    loaded2 = load_operando_session(str(out))
    assert loaded2 is not None
    _f, ax3, *_rest = loaded2
    assert len(getattr(ax3, "_operando_cif_tick_series", []) or []) == n1
    plt.close(_f)

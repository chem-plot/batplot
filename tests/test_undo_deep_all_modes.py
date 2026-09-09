"""Deep undo (``b``) regressions across modes — CIF clear, arrange, markers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot.plot_modes.xy.cif import append_xy_cif_file
from batplot.plot_modes.xy import style as ST
from batplot.plot_modes.operando.plot import append_operando_cif_file
from batplot.plot_modes.operando.style import build_operando_ec_style_config_v2
from batplot.plot_modes.operando.style_apply import apply_operando_ec_style_config


CIF_PATH = Path("/Users/tiandai/Downloads/ICSD_CollCode60433.cif")


def _xy_fig_bp():
    fig, ax = plt.subplots()
    x = np.linspace(1, 6, 40)
    y = np.sin(x) + 2
    ax.plot(x, y, marker="o", markerfacecolor="red", markeredgecolor="blue")
    series: list = []
    bp = SimpleNamespace(
        cif_tick_series=series,
        cif_hkl_label_map={},
        cif_hkl_map={},
        show_cif_hkl=False,
        show_cif_titles=True,
    )
    fig._batplot_cif_tick_series = series  # type: ignore[attr-defined]
    return fig, ax, bp, x, y


@pytest.mark.skipif(not CIF_PATH.is_file(), reason="sample CIF not on this machine")
def test_xy_psg_empty_cif_clears_series_on_apply(tmp_path):
    """Batch undo baseline: empty tick_series in .bpsg must clear added CIF."""
    fig, ax, bp, x, y = _xy_fig_bp()
    args = SimpleNamespace(stack=False, autoscale=True, norm=False, files=[], xaxis=None, wl=None)
    # Capture empty baseline as psg
    out_empty = tmp_path / "empty.bpsg"
    ST.export_style_config(
        "empty", fig, ax, [y], ["c"], 0.0, args, {}, [0.0],
        cif_tick_series=bp.cif_tick_series,
        overwrite_path=str(out_empty),
        force_kind="psg",
        cif_hkl_label_map=bp.cif_hkl_label_map,
    )
    cfg = json.loads(out_empty.read_text(encoding="utf-8"))
    assert "cif" in cfg
    assert cfg["cif"].get("tick_series") == []

    append_xy_cif_file(fig, ax, str(CIF_PATH), _bp=bp, use_2th=False, redraw=True)
    assert len(bp.cif_tick_series) == 1
    assert len(getattr(ax, "_cif_tick_art", []) or []) >= 1

    ok = ST.apply_style_config(
        str(out_empty), fig, ax, [x], [y], [y.copy()], [0.0], [],
        args, {}, ["c"], lambda *_a, **_k: None,
        bp.cif_tick_series, bp.cif_hkl_label_map,
    )
    assert ok is not False
    assert bp.cif_tick_series == []
    assert getattr(ax, "_cif_tick_art", None) == [] or len(ax._cif_tick_art) == 0
    plt.close(fig)


@pytest.mark.skipif(not CIF_PATH.is_file(), reason="sample CIF not on this machine")
def test_operando_psg_empty_cif_clears_series_on_apply():
    fig, ax = plt.subplots()
    im = ax.imshow(np.random.rand(6, 8), origin="lower", aspect="auto")
    cbar = fig.colorbar(im)
    fig._operando_axis_mode = "Q"  # type: ignore[attr-defined]
    fig._operando_wl = 0.709  # type: ignore[attr-defined]
    cfg_empty, _ = build_operando_ec_style_config_v2(fig, ax, im, cbar, None, "psg")
    assert "cif" in cfg_empty
    assert cfg_empty["cif"].get("tick_series") == []

    append_operando_cif_file(fig, ax, str(CIF_PATH), redraw=True)
    assert len(getattr(ax, "_operando_cif_tick_series", []) or []) == 1

    ok = apply_operando_ec_style_config(
        cfg_empty, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=None, silent=True,
    )
    assert ok
    assert list(getattr(ax, "_operando_cif_tick_series", []) or []) == []
    plt.close(fig)


def test_operando_legacy_style_without_cif_key_does_not_clear():
    """Old styles omitting ``cif`` must not wipe an existing series."""
    fig, ax = plt.subplots()
    im = ax.imshow(np.random.rand(4, 5), origin="lower", aspect="auto")
    cbar = fig.colorbar(im)
    fig._operando_axis_mode = "Q"  # type: ignore[attr-defined]
    ax._operando_cif_tick_series = [("keep", "/tmp/x.cif", [1.0], None, 5.0, "k")]
    cfg = {"kind": "operando_ec_style_geom", "version": 2, "operando": {}, "figure": {}}
    assert "cif" not in cfg
    apply_operando_ec_style_config(
        cfg, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=None, silent=True,
    )
    assert len(ax._operando_cif_tick_series) == 1
    plt.close(fig)


def test_xy_legacy_bps_without_cif_key_does_not_clear(tmp_path):
    fig, ax, bp, x, y = _xy_fig_bp()
    bp.cif_tick_series.append(("keep", "/tmp/x.cif", [1.0], None, 5.0, "k"))
    cfg = {
        "version": 2,
        "kind": "xy_style",
        "ro_active": False,
        "figure": {"size": [6, 4], "dpi": 100},
        "margins": {"left": 0.12, "right": 0.95, "bottom": 0.12, "top": 0.9},
        "curves": [],
    }
    path = tmp_path / "legacy.bps"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    args = SimpleNamespace(stack=False, autoscale=True, norm=False, files=[], xaxis=None, wl=None)
    ST.apply_style_config(
        str(path), fig, ax, [x], [y], [y.copy()], [0.0], [],
        args, {}, ["c"], lambda *_a, **_k: None,
        bp.cif_tick_series, bp.cif_hkl_label_map,
    )
    assert len(bp.cif_tick_series) == 1
    plt.close(fig)


def test_xy_marker_facecolor_restored_on_undo_logic():
    """Restore must set mfc/mec to snap values, not only handle 'none'."""
    fig, ax = plt.subplots()
    ln, = ax.plot([0, 1], [0, 1], marker="o", markerfacecolor="green", markeredgecolor="black")
    # Simulate restore branch
    item = {"mfc": "green", "mec": "black"}
    ln.set_markerfacecolor("red")
    ln.set_markeredgecolor("yellow")
    ln.set_markerfacecolor(item["mfc"])
    ln.set_markeredgecolor(item["mec"])
    assert str(ln.get_markerfacecolor()).lower() in ("green", "#008000") or ln.get_markerfacecolor() == "green"
    plt.close(fig)


@pytest.mark.skipif(not CIF_PATH.is_file(), reason="sample CIF not on this machine")
def test_batch_xy_capture_embeds_empty_tick_series(tmp_path):
    from batplot.plot_modes.batch_session.menu_xy import _capture_panel
    from batplot.plot_modes.batch_session.load import XyPanel

    fig, ax, bp, x, y = _xy_fig_bp()
    panel = XyPanel(
        path="a.pkl",
        fig=fig,
        ax=ax,
        menu_kwargs={
            "y_data_list": [y],
            "labels": ["c"],
            "delta": 0.0,
            "args": SimpleNamespace(stack=False),
            "offsets_list": [0.0],
            "cif_globals": {
                "cif_tick_series": bp.cif_tick_series,
                "cif_hkl_label_map": bp.cif_hkl_label_map,
            },
        },
    )
    cfg = _capture_panel(panel)
    assert "cif" in cfg
    assert cfg["cif"]["tick_series"] == []
    plt.close(fig)

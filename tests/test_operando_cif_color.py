"""Operando CIF unified color menu (c) and p/i/s persistence of CIF colors."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot.plot_modes.operando.colors import run_operando_cif_color_menu
from batplot.plot_modes.operando.plot import append_operando_cif_file
from batplot.plot_modes.operando.session import dump_operando_session, load_operando_session
from batplot.plot_modes.operando.style import build_operando_ec_style_config_v2
from batplot.plot_modes.operando.style_apply import apply_operando_ec_style_config


CIF_PATH = Path("/Users/tiandai/Downloads/ICSD_CollCode60433.cif")


def _minimal_operando_figure():
    fig, ax = plt.subplots(figsize=(6, 4))
    im = ax.imshow(np.random.rand(8, 12), origin="lower", aspect="auto", extent=(1, 5, 0, 7))
    cbar = fig.colorbar(im, ax=ax)
    fig._operando_axis_mode = "Q"  # type: ignore[attr-defined]
    fig._operando_wl = 0.709  # type: ignore[attr-defined]
    ax.set_xlim(1, 5)
    return fig, ax, im, cbar


def _fake_series(n=2, color="k"):
    """Minimal tick_series tuples without needing a real CIF file."""
    out = []
    for i in range(n):
        out.append((f"phase{i+1}", f"/tmp/fake_{i+1}.cif", [1.0, 2.0], 0.709, 5.0, color))
    return out


def test_cif_color_menu_per_set_mapping():
    fig, ax, _im, _cbar = _minimal_operando_figure()
    series = _fake_series(2, "k")
    ax._operando_cif_tick_series = list(series)
    feeds = iter(["1:red 2:#00ff00", "q"])
    snapshots = []

    def safe_input(_prompt=""):
        return next(feeds)

    def push_state(note):
        snapshots.append(note)

    def redraw(cts):
        ax._operando_cif_tick_series = list(cts)

    out = run_operando_cif_color_menu(
        fig=fig,
        ax=ax,
        cif_series=series,
        safe_input=safe_input,
        push_state=push_state,
        redraw=redraw,
    )
    # resolve_color_token may return name or hex
    c0 = str(out[0][-1]).lower()
    c1 = str(out[1][-1]).lower()
    assert c0 in ("red", "#ff0000", "#f00")
    assert c1 in ("#00ff00", "#0f0", "lime")
    assert "cif-color" in snapshots
    assert getattr(fig, "_operando_cif_colormap", None) is None
    plt.close(fig)


def test_cif_color_menu_all_viridis():
    fig, ax, _im, _cbar = _minimal_operando_figure()
    series = _fake_series(3, "k")
    ax._operando_cif_tick_series = list(series)
    feeds = iter(["all viridis", "q"])
    snapshots = []

    def safe_input(_prompt=""):
        return next(feeds)

    def push_state(note):
        snapshots.append(note)

    def redraw(cts):
        ax._operando_cif_tick_series = list(cts)

    out = run_operando_cif_color_menu(
        fig=fig,
        ax=ax,
        cif_series=series,
        safe_input=safe_input,
        push_state=push_state,
        redraw=redraw,
    )
    assert len(out) == 3
    cols = [str(e[-1]).lower() for e in out]
    assert all(c.startswith("#") for c in cols)
    assert len(set(cols)) >= 2  # palette yields distinct samples
    assert getattr(fig, "_operando_cif_colormap", None) == "viridis"
    assert "cif-color-palette" in snapshots
    plt.close(fig)


def test_cif_color_survives_session_roundtrip(tmp_path):
    fig, ax, im, cbar = _minimal_operando_figure()
    series = _fake_series(2, "k")
    series[0] = (series[0][0], series[0][1], series[0][2], series[0][3], series[0][4], "#ff0000")
    series[1] = (series[1][0], series[1][1], series[1][2], series[1][3], series[1][4], "#00ff00")
    ax._operando_cif_tick_series = list(series)
    fig._operando_cif_colormap = "viridis"  # type: ignore[attr-defined]
    out = tmp_path / "op_cif_color.pkl"
    dump_operando_session(
        str(out), fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=None, skip_confirm=True
    )
    plt.close(fig)

    loaded = load_operando_session(str(out))
    assert loaded is not None
    fig2, ax2, *_rest = loaded
    series2 = list(getattr(ax2, "_operando_cif_tick_series", []) or [])
    assert len(series2) == 2
    assert str(series2[0][-1]).lower() in ("#ff0000", "red")
    assert str(series2[1][-1]).lower() in ("#00ff00", "lime")
    assert getattr(fig2, "_operando_cif_colormap", None) == "viridis"
    plt.close(fig2)


def test_cif_color_in_style_ps_and_psg(tmp_path):
    fig, ax, im, cbar = _minimal_operando_figure()
    series = _fake_series(2, "#112233")
    series[1] = (series[1][0], series[1][1], series[1][2], series[1][3], series[1][4], "#aabbcc")
    ax._operando_cif_tick_series = list(series)
    fig._operando_cif_colormap = "plasma"  # type: ignore[attr-defined]

    cfg_ps, _ = build_operando_ec_style_config_v2(fig, ax, im, cbar, None, "ps")
    assert cfg_ps["cif"]["colors"][0] == "#112233"
    assert cfg_ps["cif"]["colors"][1] == "#aabbcc"
    assert cfg_ps["cif"]["colormap"] == "plasma"

    cfg_psg, _ = build_operando_ec_style_config_v2(fig, ax, im, cbar, None, "psg")
    assert cfg_psg["cif"]["tick_series"][0][-1] == "#112233"
    assert cfg_psg["cif"]["colormap"] == "plasma"

    fig2, ax2, im2, cbar2 = _minimal_operando_figure()
    # Seed a series so color list length matches on apply (ps without tick_series)
    ax2._operando_cif_tick_series = _fake_series(2, "k")
    ok = apply_operando_ec_style_config(
        cfg_ps, fig=fig2, ax=ax2, im=im2, cbar=cbar2, ec_ax=None, silent=True
    )
    assert ok
    s2 = ax2._operando_cif_tick_series
    assert str(s2[0][-1]).lower() == "#112233"
    assert str(s2[1][-1]).lower() == "#aabbcc"
    assert getattr(fig2, "_operando_cif_colormap", None) == "plasma"
    plt.close(fig)
    plt.close(fig2)


@pytest.mark.skipif(not CIF_PATH.is_file(), reason="sample CIF not on this machine")
def test_cif_color_menu_with_real_cif_file():
    fig, ax, _im, _cbar = _minimal_operando_figure()
    append_operando_cif_file(fig, ax, str(CIF_PATH), redraw=False)
    feeds = iter(["1:blue", "q"])

    def safe_input(_prompt=""):
        return next(feeds)

    out = run_operando_cif_color_menu(
        fig=fig,
        ax=ax,
        cif_series=list(ax._operando_cif_tick_series),
        safe_input=safe_input,
        push_state=lambda _n: None,
        redraw=lambda cts: setattr(ax, "_operando_cif_tick_series", list(cts)),
    )
    c0 = str(out[0][-1]).lower()
    assert c0 in ("blue", "#0000ff", "#00f")
    plt.close(fig)

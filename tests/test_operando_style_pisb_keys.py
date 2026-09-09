"""Hard gates for operando style keys across p / i / s / b."""

from __future__ import annotations

import pickle

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.operando import style as OS
from batplot.plot_modes.operando.session import dump_operando_session, load_operando_session
from batplot.plot_modes.operando.style_apply import apply_operando_ec_style_config
from batplot.plot_modes.operando.undo_state import op_restore, op_snapshot


def _noop(*_a, **_k):
    return None


def _get_spine_visible(axis, which: str) -> bool:
    sp = axis.spines.get(which)
    try:
        return bool(sp.get_visible()) if sp is not None else False
    except Exception:
        return False


def _axis_tick_width(axis, which: str):
    try:
        ticks = axis.get_major_ticks() if which == "major" else axis.get_minor_ticks()
        if ticks:
            return float(ticks[0].tick1line.get_linewidth())
    except Exception:
        pass
    return None


def _build_operando_figure():
    fig, ax = plt.subplots(figsize=(8.0, 6.0))
    Z = np.linspace(0.0, 1.0, 40 * 50).reshape(40, 50)
    im = ax.imshow(
        Z, aspect="auto", origin="lower", extent=(10.0, 40.0, 0.0, 20.0), cmap="viridis"
    )
    cbar = fig.colorbar(im, ax=ax)
    ec_ax = fig.add_axes((0.78, 0.1, 0.18, 0.8))
    (ln,) = ec_ax.plot(np.linspace(3.0, 4.2, 30), np.linspace(0.0, 20.0, 30), color="C0")
    ec_ax._ec_line = ln
    ec_ax.set_xlabel("Voltage (V)")
    ec_ax.set_ylabel("Time (h)")
    ec_ax.yaxis.tick_right()
    ec_ax.yaxis.set_label_position("right")
    ax.set_xlabel("2θ (°)")
    ax.set_ylabel("Time (h)")
    ax._custom_labels = {"x": "2θ (°)", "y": "Time (h)"}
    return fig, ax, im, cbar, ec_ax


def _push(hist, fig, ax, im, cbar, ec_ax, note=""):
    return op_snapshot(
        state_history=hist,
        fig=fig,
        ax=ax,
        im=im,
        cbar=cbar,
        ec_ax=ec_ax,
        get_spine_visible=_get_spine_visible,
        axis_tick_width=_axis_tick_width,
        note=note,
    )


def _restore(hist, fig, ax, im, cbar, ec_ax):
    op_restore(
        state_history=hist,
        fig=fig,
        ax=ax,
        im=im,
        cbar=cbar,
        ec_ax=ec_ax,
        set_fonts=_noop,
        operando_font_artists=lambda: [],
        maybe_reapply_dqdv_2d_contour=_noop,
        restore_dqdv_2d_operando_labels=_noop,
    )


def test_operando_undo_single_pop_restores_first_edit():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    hist: list = []
    assert _push(hist, fig, ax, im, cbar, ec_ax, note="baseline")
    assert len(hist) == 1
    im.set_cmap("plasma")
    im._operando_cmap_name = "plasma"
    _restore(hist, fig, ax, im, cbar, ec_ax)
    assert len(hist) == 0
    assert getattr(im, "_operando_cmap_name", None) == "viridis" or im.get_cmap().name == "viridis"
    plt.close(fig)


def test_operando_style_exports_and_applies_ec_curve_alpha():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    ln = ec_ax._ec_line
    ln.set_alpha(0.35)
    cfg, _ = OS.build_operando_ec_style_config_v2(fig, ax, im, cbar, ec_ax, "ps")
    assert cfg["ec"]["curve"].get("alpha") == 0.35

    ln.set_alpha(1.0)
    apply_operando_ec_style_config(cfg, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax)
    assert ln.get_alpha() == 0.35
    plt.close(fig)


def test_operando_undo_restores_ec_curve_alpha():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    ln = ec_ax._ec_line
    ln.set_alpha(0.4)
    hist: list = []
    _push(hist, fig, ax, im, cbar, ec_ax, note="alpha")
    ln.set_alpha(1.0)
    _restore(hist, fig, ax, im, cbar, ec_ax)
    assert ln.get_alpha() == 0.4
    plt.close(fig)


def test_operando_undo_clears_empty_operando_labels():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    ax._custom_labels = {"x": "", "y": ""}
    ax.set_xlabel("")
    ax.set_ylabel("")
    hist: list = []
    _push(hist, fig, ax, im, cbar, ec_ax, note="labels")
    ax.set_xlabel("KEEP")
    ax.set_ylabel("KEEP")
    ax._custom_labels = {"x": "KEEP", "y": "KEEP"}
    _restore(hist, fig, ax, im, cbar, ec_ax)
    assert ax.get_xlabel() == ""
    assert ax.get_ylabel() == ""
    plt.close(fig)


def test_operando_style_only_ps_omits_geometry_and_ions_abs():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    ec_ax._ions_abs = np.linspace(0.0, 1.0, 30)
    cfg, ext = OS.build_operando_ec_style_config_v2(fig, ax, im, cbar, ec_ax, "ps")
    assert ext == ".bps"
    assert cfg["kind"] == "operando_ec_style"
    assert "geometry" not in cfg
    assert "canvas_size" not in (cfg.get("figure") or {})
    assert "ions_abs" not in (cfg.get("ec") or {})
    plt.close(fig)


def test_operando_session_roundtrips_colorbar_tick_side(session_path):
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    cbar.ax.yaxis.set_ticks_position("right")
    cbar.ax.yaxis.set_label_position("right")
    path = session_path("op_cb_side.pkl")
    dump_operando_session(
        path, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax, skip_confirm=True
    )
    with open(path, "rb") as fh:
        sess = pickle.load(fh)
    assert sess["colorbar"]["ticks_left"] is False
    assert sess["colorbar"]["label_left"] is False
    result = load_operando_session(path)
    assert result is not None
    _fig2, _ax2, _im2, cbar2, _ec2 = result
    assert cbar2.ax.yaxis.get_label_position() == "right"
    plt.close(fig)
    plt.close(_fig2)


def test_operando_session_empty_cif_clears_on_reload(session_path):
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    ax._operando_cif_tick_series = [
        ("Li", "dummy.cif", [20.0, 30.0], None, None, "#ff0000")
    ]
    ax._operando_cif_hkl_label_map = {}
    path = session_path("op_cif_clear.pkl")
    dump_operando_session(
        path, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax, skip_confirm=True
    )
    # Simulate cleared CIF, then overwrite session
    ax._operando_cif_tick_series = []
    dump_operando_session(
        path, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax, skip_confirm=True
    )
    with open(path, "rb") as fh:
        sess = pickle.load(fh)
    assert "cif" in sess
    assert sess["cif"]["tick_series"] == []
    # Seed a figure path that would otherwise keep stale CIF if key omitted
    result = load_operando_session(path)
    assert result is not None
    _fig2, ax2, *_rest = result
    assert list(getattr(ax2, "_operando_cif_tick_series", None) or []) == []
    plt.close(fig)
    plt.close(_fig2)


def test_operando_psg_includes_geometry_and_empty_cif_clear_key():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    ax._operando_cif_tick_series = []
    cfg, ext = OS.build_operando_ec_style_config_v2(fig, ax, im, cbar, ec_ax, "psg")
    assert ext == ".bpsg"
    assert cfg["kind"] == "operando_ec_style_geom"
    assert "geometry" in cfg
    assert "cif" in cfg
    assert cfg["cif"].get("tick_series") == []
    plt.close(fig)

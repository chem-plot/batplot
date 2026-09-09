"""Hard gates for operando contour + EC geometry keys across p / i / s / b."""

from __future__ import annotations

import pickle

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.operando import style as OS
from batplot.plot_modes.operando.layout import (
    _apply_group_layout_inches,
    _ensure_fixed_params,
    _get_geometry_snapshot,
)
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
        return None
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
    ax._stored_xlabel = "2θ (°)"
    ax._stored_ylabel = "Time (h)"
    # Seed fixed inch attrs like interactive layout does.
    _ensure_fixed_params(fig, ax, cbar.ax, ec_ax)
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


def test_operando_ps_omits_view_geometry_and_does_not_apply_clim_or_reverse():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    im.set_clim(0.2, 0.8)
    ax.set_ylim(20, 0)  # reversed
    ec_ax.set_ylim(20, 0)
    cfg, ext = OS.build_operando_ec_style_config_v2(fig, ax, im, cbar, ec_ax, "ps")
    assert ext == ".bps"
    assert cfg["kind"] == "operando_ec_style"
    assert "geometry" not in cfg
    assert "axes_geometry" not in cfg
    assert "canvas_size" not in (cfg.get("figure") or {})
    assert "intensity_range" not in (cfg.get("operando") or {})
    assert "y_reversed" not in (cfg.get("operando") or {})
    assert "y_reversed" not in (cfg.get("ec") or {})

    fig2, ax2, im2, cbar2, ec_ax2 = _build_operando_figure()
    im2.set_clim(0.0, 1.0)
    ax2.set_ylim(0, 20)
    ec_ax2.set_ylim(0, 20)
    # Legacy hitchhike keys must still be ignored for style-only kind.
    cfg["operando"]["intensity_range"] = [0.2, 0.8]
    cfg["operando"]["y_reversed"] = True
    cfg["ec"]["y_reversed"] = True
    apply_operando_ec_style_config(cfg, fig=fig2, ax=ax2, im=im2, cbar=cbar2, ec_ax=ec_ax2)
    assert im2.get_clim() == (0.0, 1.0)
    assert ax2.get_ylim()[0] < ax2.get_ylim()[1]
    assert ec_ax2.get_ylim()[0] < ec_ax2.get_ylim()[1]
    plt.close(fig)
    plt.close(fig2)


def test_operando_psg_roundtrips_layout_limits_clim_and_reverse():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, 4.0, 3.0, 0.25, 0.15, 0.20, 1.5)
    cbar.ax._cb_h_offset_in = 0.05
    ec_ax._ec_h_offset_in = -0.03
    _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, 4.0, 3.0, 0.25, 0.15, 0.20, 1.5)
    ax.set_xlim(12.0, 35.0)
    ax.set_ylim(18.0, 2.0)  # reversed
    ec_ax.set_xlim(3.1, 4.0)
    ec_ax.set_ylim(15.0, 1.0)
    im.set_clim(0.1, 0.9)

    cfg, ext = OS.build_operando_ec_style_config_v2(fig, ax, im, cbar, ec_ax, "psg")
    assert ext == ".bpsg"
    assert cfg["kind"] == "operando_ec_style_geom"
    assert abs(cfg["geometry"]["op_w_in"] - 4.0) < 1e-6
    assert abs(cfg["geometry"]["ec_w_in"] - 1.5) < 1e-6
    assert abs(cfg["geometry"]["cb_h_offset"] - 0.05) < 1e-6
    assert abs(cfg["geometry"]["ec_h_offset"] - (-0.03)) < 1e-6
    assert cfg["operando"]["y_reversed"] is True
    assert cfg["operando"]["intensity_range"] == [0.1, 0.9]
    assert cfg["axes_geometry"]["operando"]["xlim"] == [12.0, 35.0]
    assert cfg["axes_geometry"]["ec"]["xlim"] == [3.1, 4.0]

    fig2, ax2, im2, cbar2, ec_ax2 = _build_operando_figure()
    apply_operando_ec_style_config(cfg, fig=fig2, ax=ax2, im=im2, cbar=cbar2, ec_ax=ec_ax2)
    assert abs(float(ax2._fixed_ax_w_in) - 4.0) < 1e-6
    assert abs(float(cbar2.ax._cb_h_offset_in) - 0.05) < 1e-6
    assert ax2.get_xlim() == (12.0, 35.0)
    assert ax2.get_ylim()[0] > ax2.get_ylim()[1]
    assert ec_ax2.get_xlim() == (3.1, 4.0)
    assert abs(im2.get_clim()[0] - 0.1) < 1e-9
    assert abs(im2.get_clim()[1] - 0.9) < 1e-9
    plt.close(fig)
    plt.close(fig2)


def test_operando_axes_geometry_accepts_tuple_limits_and_clears_empty_labels():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    cfg, _ = OS.build_operando_ec_style_config_v2(fig, ax, im, cbar, ec_ax, "psg")
    cfg["axes_geometry"] = {
        "operando": {
            "xlim": (11.0, 30.0),
            "ylim": (1.0, 19.0),
            "xlabel": "",
            "ylabel": "",
        },
        "ec": {
            "xlim": (3.2, 4.1),
            "ylim": (2.0, 18.0),
            "xlabel": "",
            "ylabel": "",
        },
    }
    apply_operando_ec_style_config(cfg, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax)
    assert ax.get_xlim() == (11.0, 30.0)
    assert ax.get_ylim() == (1.0, 19.0)
    assert ax.get_xlabel() == ""
    assert ax.get_ylabel() == ""
    assert ec_ax.get_xlabel() == ""
    assert ec_ax.get_xlim() == (3.2, 4.1)
    plt.close(fig)


def test_operando_geometry_snapshot_prefers_stored_labels_when_hidden():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax._stored_xlabel = "Stored X"
    ax._stored_ylabel = "Stored Y"
    ec_ax.set_xlabel("")
    ec_ax.set_ylabel("")
    ec_ax._stored_xlabel = "EC X"
    ec_ax._stored_ylabel = "EC Y"
    snap = _get_geometry_snapshot(ax, ec_ax)
    assert snap["operando"]["xlabel"] == "Stored X"
    assert snap["operando"]["ylabel"] == "Stored Y"
    assert snap["ec"]["xlabel"] == "EC X"
    assert snap["ec"]["ylabel"] == "EC Y"
    plt.close(fig)


def test_operando_session_preserves_empty_ylabel(session_path):
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    ax.set_ylabel("")
    ax._stored_ylabel = ""
    path = session_path("op_empty_ylabel.pkl")
    dump_operando_session(
        path, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax, skip_confirm=True
    )
    with open(path, "rb") as fh:
        sess = pickle.load(fh)
    assert sess["operando"]["labels"]["ylabel"] == ""
    result = load_operando_session(path)
    assert result is not None
    _fig2, ax2, *_rest = result
    assert ax2.get_ylabel() == ""
    plt.close(fig)
    plt.close(_fig2)


def test_operando_session_layout_inches_roundtrip(session_path):
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, 3.5, 2.8, 0.22, 0.12, 0.18, 1.2)
    cbar.ax._cb_h_offset_in = 0.04
    _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, 3.5, 2.8, 0.22, 0.12, 0.18, 1.2)
    path = session_path("op_layout.pkl")
    dump_operando_session(
        path, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax, skip_confirm=True
    )
    with open(path, "rb") as fh:
        sess = pickle.load(fh)
    assert abs(sess["layout_inches"]["ax_w_in"] - 3.5) < 1e-6
    assert abs(sess["layout_inches"]["cb_h_offset"] - 0.04) < 1e-6
    result = load_operando_session(path)
    assert result is not None
    _fig2, ax2, _im2, cbar2, _ec2 = result
    assert abs(float(ax2._fixed_ax_w_in) - 3.5) < 1e-6
    assert abs(float(cbar2.ax._cb_h_offset_in) - 0.04) < 1e-6
    plt.close(fig)
    plt.close(_fig2)


def test_operando_undo_restores_limits_and_layout_after_edit():
    fig, ax, im, cbar, ec_ax = _build_operando_figure()
    ax.set_xlim(10, 40)
    ax.set_ylim(0, 20)
    hist: list = []
    assert _push(hist, fig, ax, im, cbar, ec_ax, note="baseline")
    ax.set_xlim(15, 25)
    ax.set_ylim(5, 10)
    _apply_group_layout_inches(fig, ax, cbar.ax, ec_ax, 5.0, 4.0, 0.3, 0.2, 0.25, 2.0)
    _restore(hist, fig, ax, im, cbar, ec_ax)
    assert ax.get_xlim() == (10.0, 40.0)
    assert ax.get_ylim() == (0.0, 20.0)
    plt.close(fig)

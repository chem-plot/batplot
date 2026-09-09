"""Scoped batch sync for CPC / XY / operando — no hitchhiking of peer-local style."""

from __future__ import annotations

import matplotlib.pyplot as plt
import pytest
from matplotlib.colors import to_hex

from batplot.plot_modes.batch_session.batch_scoped_sync import deep_merge_keys
from batplot.plot_modes.batch_session.cpc_batch_helpers import (
    apply_cpc_colors_only,
    apply_cpc_file_visibility_only,
    apply_cpc_labels_only,
    apply_cpc_wasd_chrome_only,
)
from batplot.plot_modes.batch_session.ec_batch_helpers import (
    apply_ec_file_visibility_only,
    apply_ec_line_chrome_only,
)
from batplot.plot_modes.batch_session.load import CpcPanel, EcPanel, OperandoPanel
from batplot.plot_modes.batch_session.menu_cpc import _capture_panel as cpc_capture
from batplot.plot_modes.batch_session.operando_batch_helpers import (
    apply_operando_cif_colors_only,
    apply_operando_colormap_only,
    apply_operando_ec_curve_only,
    apply_operando_ec_grid_only,
    apply_operando_ec_labels_only,
    apply_operando_labels_only,
    apply_operando_spine_colors_only,
    apply_operando_visibility_only,
    apply_operando_wasd_chrome_only,
)
from batplot.plot_modes.batch_session.xy_batch_helpers import merge_xy_line_chrome_cfg
from batplot.plot_modes.electrochem.colors import set_ec_file_visibility


def test_deep_merge_keeps_peer_local_keys():
    peer = {"kind": "x", "a": 1, "b": 2, "nested": {"x": 1, "y": 2}, "geometry": {"xlim": [0, 1]}}
    ref = {"kind": "x_geom", "a": 9, "b": 8, "nested": {"x": 7, "y": 6}, "geometry": {"xlim": [3, 4]}}
    out = deep_merge_keys(
        peer,
        ref,
        top_keys=frozenset({"a"}),
        nested_keys={"nested": frozenset({"x"})},
        force_kind="x",
        drop_geometry=True,
    )
    assert out["kind"] == "x"
    assert out["a"] == 9
    assert out["b"] == 2
    assert out["nested"]["x"] == 7
    assert out["nested"]["y"] == 2
    assert "geometry" not in out


def test_cpc_wasd_sync_keeps_peer_series_color():
    from test_cpc_roundtrip import _build_cpc_figure

    fig1, ax1, ax2a, sc_c1, sc_d1, sc_e1, _ = _build_cpc_figure()
    fig2, ax2, ax2b, sc_c2, sc_d2, sc_e2, _ = _build_cpc_figure()
    p1 = CpcPanel(
        path="a.pkl", fig=fig1, ax=ax1, ax2=ax2a,
        sc_charge=sc_c1, sc_discharge=sc_d1, sc_eff=sc_e1,
    )
    p2 = CpcPanel(
        path="b.pkl", fig=fig2, ax=ax2, ax2=ax2b,
        sc_charge=sc_c2, sc_discharge=sc_d2, sc_eff=sc_e2,
    )
    try:
        sc_c1.set_facecolor("#ff0000")
        sc_c2.set_facecolor("#00aa00")
        fig1._cpc_wasd_state = {
            "top": {"spine": True, "ticks": True, "labels": False, "title": False, "minor": False},
            "bottom": {"spine": True, "ticks": True, "labels": True, "title": True, "minor": False},
            "left": {"spine": True, "ticks": True, "labels": True, "title": True, "minor": False},
            "right": {"spine": True, "ticks": False, "labels": False, "title": True, "minor": False},
        }
        cfg = cpc_capture(p1)
        apply_cpc_wasd_chrome_only(p2, cfg)
        assert to_hex(sc_c2.get_facecolor()) == "#00aa00"
    finally:
        plt.close(fig1)
        plt.close(fig2)


def test_cpc_color_sync_keeps_peer_labels():
    from test_cpc_roundtrip import _build_cpc_figure

    fig1, ax1, ax2a, sc_c1, sc_d1, sc_e1, _ = _build_cpc_figure()
    fig2, ax2, ax2b, sc_c2, sc_d2, sc_e2, _ = _build_cpc_figure()
    ax1.set_xlabel("Ref X")
    ax1._stored_xlabel = "Ref X"
    ax2.set_xlabel("Peer X")
    ax2._stored_xlabel = "Peer X"
    p1 = CpcPanel(
        path="a.pkl", fig=fig1, ax=ax1, ax2=ax2a,
        sc_charge=sc_c1, sc_discharge=sc_d1, sc_eff=sc_e1,
    )
    p2 = CpcPanel(
        path="b.pkl", fig=fig2, ax=ax2, ax2=ax2b,
        sc_charge=sc_c2, sc_discharge=sc_d2, sc_eff=sc_e2,
    )
    try:
        sc_c1.set_facecolor("#ff0000")
        sc_c2.set_facecolor("#00aa00")
        cfg = cpc_capture(p1)
        apply_cpc_colors_only(p2, cfg)
        assert ax2.get_xlabel() == "Peer X"
        assert to_hex(sc_c2.get_facecolor()) == "#ff0000"
    finally:
        plt.close(fig1)
        plt.close(fig2)


def test_cpc_labels_only_unchanged():
    from test_cpc_roundtrip import _build_cpc_figure

    fig1, ax1, ax2a, sc_c1, sc_d1, sc_e1, _ = _build_cpc_figure()
    fig2, ax2, ax2b, sc_c2, sc_d2, sc_e2, _ = _build_cpc_figure()
    ax1.set_xlabel("New")
    ax1._stored_xlabel = "New"
    ax2.set_xlabel("Old")
    p1 = CpcPanel(
        path="a.pkl", fig=fig1, ax=ax1, ax2=ax2a,
        sc_charge=sc_c1, sc_discharge=sc_d1, sc_eff=sc_e1,
    )
    p2 = CpcPanel(
        path="b.pkl", fig=fig2, ax=ax2, ax2=ax2b,
        sc_charge=sc_c2, sc_discharge=sc_d2, sc_eff=sc_e2,
    )
    try:
        sc_c2.set_facecolor("#00aa00")
        apply_cpc_labels_only(p2, cpc_capture(p1))
        assert ax2.get_xlabel() == "New"
        assert to_hex(sc_c2.get_facecolor()) == "#00aa00"
    finally:
        plt.close(fig1)
        plt.close(fig2)


def test_xy_line_chrome_merge_keeps_colors():
    peer = {
        "kind": "xy_style_geom",
        "grid": False,
        "geometry": {"xlim": [0, 1]},
        "spines": {"bottom": {"linewidth": 1.0, "color": "#111111", "visible": True}},
        "ticks": {"x_major_width": 1.0, "spacing": {"x": 1}},
        "lines": [
            {"index": 0, "color": "#00aa00", "linewidth": 1.0, "linestyle": "-", "marker": "None"},
        ],
    }
    ref = {
        "kind": "xy_style_geom",
        "grid": True,
        "geometry": {"xlim": [9, 10]},
        "spines": {"bottom": {"linewidth": 2.5, "color": "#ff0000", "visible": True}},
        "ticks": {"x_major_width": 2.0, "spacing": {"x": 99}},
        "lines": [
            {"index": 0, "color": "#ff0000", "linewidth": 3.0, "linestyle": "--", "marker": "o"},
        ],
    }
    out = merge_xy_line_chrome_cfg(peer, ref)
    assert out["kind"] == "xy_style"
    assert "geometry" not in out
    assert out["grid"] is True
    assert out["spines"]["bottom"]["linewidth"] == 2.5
    assert out["spines"]["bottom"]["color"] == "#111111"
    assert out["ticks"]["x_major_width"] == 2.0
    assert out["ticks"]["spacing"]["x"] == 1
    assert out["lines"][0]["linewidth"] == 3.0
    assert out["lines"][0]["linestyle"] == "--"
    assert out["lines"][0]["color"] == "#00aa00"


def _operando_pair():
    import numpy as np

    panels = []
    for path, cmap, clim in (("a.pkl", "viridis", (0.1, 0.9)), ("b.pkl", "plasma", (0.2, 0.8))):
        fig, ax = plt.subplots()
        Z = np.array([[0.0, 1.0], [0.5, 0.25]])
        im = ax.imshow(Z, cmap=cmap, vmin=clim[0], vmax=clim[1])
        im._operando_cmap_name = cmap  # type: ignore[attr-defined]
        cax = fig.add_axes([0.92, 0.1, 0.03, 0.8])
        cbar = fig.colorbar(im, cax=cax)
        ec_ax = fig.add_axes([0.1, 0.1, 0.2, 0.8])
        (ln,) = ec_ax.plot([3.0, 4.0], [0.0, 1.0], color="#00aa00", lw=1.0)
        ec_ax._ec_line = ln  # type: ignore[attr-defined]
        ax.set_xlabel(f"X-{path}")
        ax.set_ylabel(f"Y-{path}")
        ax._custom_labels = {"x": f"X-{path}", "y": f"Y-{path}"}
        ec_ax.set_xlabel(f"EX-{path}")
        ec_ax.set_ylabel(f"EY-{path}")
        panels.append(OperandoPanel(path=path, fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax))
    return panels[0], panels[1]


def test_operando_colormap_only_keeps_clim_and_labels(capsys):
    p1, p2 = _operando_pair()
    try:
        p1.im._operando_cmap_name = "magma"  # type: ignore[attr-defined]
        from batplot.plot_modes.operando.colors import apply_operando_colormap

        apply_operando_colormap(p1.im, "magma")
        ref_cfg = {
            "kind": "operando_ec_style",
            "version": 2,
            "operando": {
                "cmap": "magma",
                "custom_labels": {"x": "Hijack", "y": "Hijack"},
                "intensity_range": [0.0, 99.0],
                "y_reversed": True,
            },
        }
        ylim_before = p2.ax.get_ylim()
        assert apply_operando_colormap_only(p2, ref_cfg) is True
        assert getattr(p2.im, "_operando_cmap_name") == "magma"
        assert p2.im.get_clim() == pytest.approx((0.2, 0.8))
        assert p2.ax.get_xlabel() == "X-b.pkl"
        assert p2.ax.get_ylim() == pytest.approx(ylim_before)  # reverse not hitchhiked
        out = capsys.readouterr().out
        assert "Applied intensity range" not in out
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_operando_labels_only_keeps_cmap_clim():
    p1, p2 = _operando_pair()
    try:
        ref_cfg = {
            "kind": "operando_ec_style",
            "operando": {
                "cmap": "magma",
                "custom_labels": {"x": "Synced X", "y": "Synced Y"},
                "intensity_range": [0.0, 99.0],
            },
        }
        assert apply_operando_labels_only(p2, ref_cfg) is True
        assert p2.ax.get_xlabel() == "Synced X"
        assert p2.ax.get_ylabel() == "Synced Y"
        assert getattr(p2.im, "_operando_cmap_name") == "plasma"
        assert p2.im.get_clim() == pytest.approx((0.2, 0.8))
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_operando_ec_curve_visibility_grid_spine_wasd_scoped():
    p1, p2 = _operando_pair()
    try:
        ln1 = p1.ec_ax._ec_line  # type: ignore[attr-defined]
        ln2 = p2.ec_ax._ec_line  # type: ignore[attr-defined]
        ln1.set_color("#ff0000")
        ln1.set_linewidth(3.5)
        p1.cbar.ax.set_visible(False)
        p1.ec_ax.set_visible(False)
        p1.ax.spines["bottom"].set_linewidth(2.5)
        p1.ax.spines["bottom"].set_color("#112233")
        p2.ax.spines["bottom"].set_color("#00aa00")
        p2.ax.spines["bottom"].set_linewidth(1.0)

        assert apply_operando_ec_curve_only(
            p2,
            {"version": 2, "ec": {"curve": {"color": "#ff0000", "linewidth": 3.5}}},
        )
        assert to_hex(ln2.get_color()) == "#ff0000"
        assert ln2.get_linewidth() == pytest.approx(3.5)
        assert p2.im.get_clim() == pytest.approx((0.2, 0.8))

        assert apply_operando_visibility_only(
            p2,
            {
                "colorbar": {"visible": False},
                "ec": {"visible": False, "custom_labels": {"x": "Nope"}, "grid": {"visible": True}},
            },
        )
        assert p2.cbar.ax.get_visible() is False
        assert p2.ec_ax.get_visible() is False
        assert p2.ec_ax.get_xlabel() == "EX-b.pkl"  # labels not hitchhiked

        assert apply_operando_ec_grid_only(
            p2, {"ec": {"grid": {"visible": True, "alpha": 0.5, "color": "0.4", "linestyle": ":", "which": "major"}}}
        )
        assert getattr(p2.ec_ax, "_ec_grid", {}).get("visible") is True

        assert apply_operando_spine_colors_only(
            p2,
            {"version": 2, "operando": {"spines": {"bottom": {"color": "#112233", "linewidth": 9.0}}}},
        )
        assert to_hex(p2.ax.spines["bottom"].get_edgecolor()) == "#112233"
        assert p2.ax.spines["bottom"].get_linewidth() == pytest.approx(1.0)

        assert apply_operando_wasd_chrome_only(
            p2,
            {
                "version": 2,
                "operando": {
                    "spines": {"bottom": {"linewidth": 2.5, "color": "#ff00ff", "visible": True}},
                    "wasd_state": {
                        "top": {"spine": True, "ticks": False, "labels": False, "title": False, "minor": False},
                        "bottom": {"spine": True, "ticks": True, "labels": True, "title": True, "minor": False},
                        "left": {"spine": True, "ticks": True, "labels": True, "title": True, "minor": False},
                        "right": {"spine": True, "ticks": False, "labels": False, "title": False, "minor": False},
                    },
                },
            },
        )
        # Widths owned by ``l``; colors by ``k`` — ``t`` must hitchhike neither.
        assert p2.ax.spines["bottom"].get_linewidth() == pytest.approx(1.0)
        assert to_hex(p2.ax.spines["bottom"].get_edgecolor()) == "#112233"
        assert p2.im.get_clim() == pytest.approx((0.2, 0.8))
        assert getattr(p2.im, "_operando_cmap_name") == "plasma"
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_operando_cif_colors_only_updates_series_color():
    p1, p2 = _operando_pair()
    try:
        series = [("A", "/tmp/a.cif", [1.0], None, None, "#111111")]
        p2.ax._operando_cif_tick_series = list(series)
        p1.ax._operando_cif_tick_series = [("A", "/tmp/a.cif", [1.0], None, None, "#ff0000")]
        ok = apply_operando_cif_colors_only(
            p2,
            {
                "cif": {
                    "colors": ["#ff0000"],
                    "show_hkl": True,
                    "show_titles": False,
                    "intensity_range": [0, 99],  # must be ignored (not a cif key used)
                },
                "operando": {"intensity_range": [0.0, 99.0], "cmap": "magma"},
            },
        )
        assert ok is True
        assert p2.ax._operando_cif_tick_series[0][-1] == "#ff0000"
        assert p2.fig._operando_cif_show_hkl is True
        assert p2.fig._operando_cif_show_titles is False
        assert p2.im.get_clim() == pytest.approx((0.2, 0.8))
        assert getattr(p2.im, "_operando_cmap_name") == "plasma"
    finally:
        plt.close(p1.fig)
        plt.close(p2.fig)


def test_ec_file_visibility_reshow_restores_peer_curves():
    fig1, ax1 = plt.subplots()
    fig2, ax2 = plt.subplots()
    try:
        (c1a,) = ax1.plot([0, 1], [0, 1], color="C0")
        (c1b,) = ax1.plot([0, 1], [1, 0], color="C1")
        (c2a,) = ax2.plot([0, 1], [0, 1], color="C0")
        (c2b,) = ax2.plot([0, 1], [1, 0], color="C1")
        fd1 = [
            {"filename": "a", "visible": True, "cycle_lines": {1: {"charge": c1a, "discharge": None}}},
            {"filename": "b", "visible": True, "cycle_lines": {1: {"charge": c1b, "discharge": None}}},
        ]
        fd2 = [
            {"filename": "a", "visible": True, "cycle_lines": {1: {"charge": c2a, "discharge": None}}},
            {"filename": "b", "visible": True, "cycle_lines": {1: {"charge": c2b, "discharge": None}}},
        ]
        p1 = EcPanel(path="a.pkl", fig=fig1, ax=ax1, cycle_lines={}, file_data=fd1)
        p2 = EcPanel(path="b.pkl", fig=fig2, ax=ax2, cycle_lines={}, file_data=fd2)
        set_ec_file_visibility(fd1[1], False)
        set_ec_file_visibility(fd2[1], False)
        assert c2b.get_visible() is False
        # Re-show file 2 on ref, sync visibility to peer.
        set_ec_file_visibility(fd1[1], True)
        assert apply_ec_file_visibility_only(p2, {"file_visibility": [True, True]}) is True
        assert c2b.get_visible() is True
        assert fd2[1]["visible"] is True
    finally:
        plt.close(fig1)
        plt.close(fig2)


def test_ec_line_chrome_strips_marker_colors():
    fig, ax = plt.subplots()
    try:
        (ln,) = ax.plot([0, 1], [0, 1], color="#00aa00", lw=1.0)
        p = EcPanel(
            path="a.pkl", fig=fig, ax=ax,
            cycle_lines={1: {"charge": ln, "discharge": None}}, file_data=None,
        )
        ref_cfg = {
            "kind": "ec_style",
            "curve_linewidth": 2.5,
            "curve_markers": {
                "linestyle": "--",
                "marker": "o",
                "markersize": 8.0,
                "markerfacecolor": "#ff0000",
                "markeredgecolor": "#ff0000",
            },
            "grid": False,
            "spines": {},
            "ticks": {},
        }
        assert apply_ec_line_chrome_only(p, ref_cfg) is True
        assert ln.get_linewidth() == pytest.approx(2.5)
        assert to_hex(ln.get_color()) == "#00aa00"
    finally:
        plt.close(fig)


def test_cpc_visibility_only_merges_visible_flag():
    from test_cpc_roundtrip import _build_cpc_figure

    fig1, ax1, ax2a, sc_c1, sc_d1, sc_e1, _ = _build_cpc_figure()
    fig2, ax2, ax2b, sc_c2, sc_d2, sc_e2, _ = _build_cpc_figure()
    fd1 = [
        {"filename": "a", "visible": True, "sc_charge": sc_c1, "sc_discharge": sc_d1, "sc_eff": sc_e1},
        {"filename": "b", "visible": False, "sc_charge": sc_c1, "sc_discharge": sc_d1, "sc_eff": sc_e1},
    ]
    fd2 = [
        {"filename": "a", "visible": True, "sc_charge": sc_c2, "sc_discharge": sc_d2, "sc_eff": sc_e2},
        {"filename": "b", "visible": True, "sc_charge": sc_c2, "sc_discharge": sc_d2, "sc_eff": sc_e2},
    ]
    p1 = CpcPanel(
        path="a.pkl", fig=fig1, ax=ax1, ax2=ax2a,
        sc_charge=sc_c1, sc_discharge=sc_d1, sc_eff=sc_e1, file_data=fd1,
    )
    p2 = CpcPanel(
        path="b.pkl", fig=fig2, ax=ax2, ax2=ax2b,
        sc_charge=sc_c2, sc_discharge=sc_d2, sc_eff=sc_e2, file_data=fd2,
    )
    try:
        cfg = cpc_capture(p1)
        assert apply_cpc_file_visibility_only(p2, cfg) is True
        assert fd2[1]["visible"] is False
    finally:
        plt.close(fig1)
        plt.close(fig2)


def test_operando_ec_labels_apply_axis_text():
    fig, ax = plt.subplots()
    try:
        im = ax.imshow([[0.0, 1.0], [0.5, 0.2]])
        cax = fig.add_axes([0.92, 0.1, 0.03, 0.8])
        cbar = fig.colorbar(im, cax=cax)
        ec_ax = fig.add_axes([0.1, 0.1, 0.2, 0.8])
        ec_ax.set_xlabel("Old X")
        ec_ax.set_ylabel("Old Y")
        ec_ax._ec_y_mode = "time"
        panel = OperandoPanel(
            path="a.pkl", fig=fig, ax=ax, im=im, cbar=cbar, ec_ax=ec_ax
        )
        ref_cfg = {
            "kind": "operando_ec_style",
            "ec": {
                "custom_labels": {"x": "Potential (V)", "y_time": "Time (h)", "y_ions": None},
                "y_mode": "time",
                "wasd_state": {
                    "bottom": {"title": True},
                    "right": {"title": True},
                },
            },
        }
        assert apply_operando_ec_labels_only(panel, ref_cfg) is True
        assert ec_ax.get_xlabel() == "Potential (V)"
        assert ec_ax.get_ylabel() == "Time (h)"
    finally:
        plt.close(fig)

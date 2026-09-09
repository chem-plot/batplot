"""Hard gates for EC + CPC geometry keys across p / i / s / b."""

from __future__ import annotations

import json
import pickle

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.cpc import style as CS
from batplot.plot_modes.cpc.session import dump_cpc_session, load_cpc_session
from batplot.plot_modes.cpc.snapshots import _apply_cpc_geometry_snapshot, _get_geometry_snapshot
from batplot.plot_modes.electrochem import style as ES
from batplot.plot_modes.electrochem.session import dump_ec_session, load_ec_session
from batplot.plot_modes.electrochem.style_apply import apply_ec_style_config


def _make_ec_fig():
    fig, ax = plt.subplots(figsize=(8.0, 6.0))
    (ln_c,) = ax.plot([0, 1], [3.0, 3.5], color="C0")
    (ln_d,) = ax.plot([0, 1], [3.5, 3.0], color="C1")
    cycle_lines = {1: {"charge": ln_c, "discharge": ln_d}}
    ax.set_xlabel("Capacity")
    ax.set_ylabel("Potential")
    ax._stored_xlabel = "Capacity"
    ax._stored_ylabel = "Potential"
    return fig, ax, cycle_lines


def _make_cpc_fig():
    fig, ax = plt.subplots(figsize=(8.0, 6.0))
    ax2 = ax.twinx()
    sc_c = ax.scatter([1, 2], [100, 110], marker="s")
    sc_d = ax.scatter([1, 2], [90, 95], marker="s")
    sc_e = ax2.scatter([1, 2], [90, 92], marker="^")
    ax.set_xlabel("Cycle number")
    ax.set_ylabel("Capacity")
    ax2.set_ylabel("Efficiency (%)")
    file_data = [
        {
            "filename": "a.txt",
            "display_name": "a",
            "visible": True,
            "eff_inverted": False,
            "sc_charge": sc_c,
            "sc_discharge": sc_d,
            "sc_eff": sc_e,
        }
    ]
    return fig, ax, ax2, sc_c, sc_d, sc_e, file_data


def test_ec_session_dump_subplot_margins_match_live_set_position(session_path):
    fig, ax, cycle_lines = _make_ec_fig()
    ax.set_position([0.25, 0.30, 0.55, 0.50])
    live = ax.get_position().bounds
    path = session_path("ec_live_frame.pkl")
    dump_ec_session(path, fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)
    with open(path, "rb") as fh:
        sess = pickle.load(fh)
    spm = sess["subplot_margins"]
    assert abs(spm["left"] - live[0]) < 1e-9
    assert abs(spm["bottom"] - live[1]) < 1e-9
    assert abs((spm["right"] - spm["left"]) - live[2]) < 1e-9
    plt.close(fig)


def test_ec_session_load_prefers_axes_bbox_over_stale_margins(session_path):
    fig, ax, cycle_lines = _make_ec_fig()
    ax.set_position([0.22, 0.28, 0.50, 0.45])
    path = session_path("ec_bbox_authority.pkl")
    dump_ec_session(path, fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)
    with open(path, "rb") as fh:
        sess = pickle.load(fh)
    sess["subplot_margins"] = {"left": 0.05, "right": 0.99, "bottom": 0.05, "top": 0.99}
    sess["frame_size"] = (7.5, 5.5)
    sess["figure"]["frame_size"] = (7.5, 5.5)
    with open(path, "wb") as fh:
        pickle.dump(sess, fh)
    res = load_ec_session(path)
    assert res is not None
    fig2, ax2 = res[0], res[1]
    b = ax2.get_position().bounds
    assert abs(b[0] - 0.22) < 1e-6
    assert abs(b[1] - 0.28) < 1e-6
    assert abs(b[2] - 0.50) < 1e-6
    assert abs(b[3] - 0.45) < 1e-6
    plt.close(fig)
    plt.close(fig2)


def test_ec_psg_geometry_clears_empty_labels_and_accepts_tuple_limits():
    fig, ax, cycle_lines = _make_ec_fig()
    ax.set_xlabel("KEEP")
    ax.set_ylabel("KEEP")
    geom = ES._get_geometry_snapshot(fig, ax)
    geom["xlabel"] = ""
    geom["ylabel"] = ""
    geom["xlim"] = (0.5, 1.5)  # tuple, not list
    geom["ylim"] = (2.5, 4.5)
    cfg = ES._get_style_snapshot(fig, ax, cycle_lines, {}, file_data=None)
    cfg["kind"] = "ec_style_geom"
    cfg["geometry"] = geom
    apply_ec_style_config(
        cfg,
        fig=fig,
        ax=ax,
        cycle_lines=cycle_lines,
        file_data=None,
        is_multi_file=False,
        tick_state={},
    )
    assert ax.get_xlabel() == ""
    assert ax.get_ylabel() == ""
    assert ax._stored_xlabel == ""
    assert ax.get_xlim() == (0.5, 1.5)
    assert ax.get_ylim() == (2.5, 4.5)
    plt.close(fig)


def test_ec_geometry_snapshot_prefers_stored_labels_when_hidden():
    fig, ax, cycle_lines = _make_ec_fig()
    ax.xaxis.label.set_visible(False)
    ax.yaxis.label.set_visible(False)
    ax.set_xlabel("")  # live artist empty; stored should win
    geom = ES._get_geometry_snapshot(fig, ax)
    assert geom["xlabel"] == "Capacity"
    assert geom["ylabel"] == "Potential"
    plt.close(fig)


def test_ec_geometry_snapshot_keeps_intentionally_empty_stored_labels():
    fig, ax, cycle_lines = _make_ec_fig()
    ax._stored_xlabel = ""
    ax._stored_ylabel = ""
    ax.set_xlabel("LIVE")
    ax.set_ylabel("LIVE")
    geom = ES._get_geometry_snapshot(fig, ax)
    assert geom["xlabel"] == ""
    assert geom["ylabel"] == ""
    plt.close(fig)


def test_ec_undo_restores_axes_bbox_after_set_position():
    from batplot.plot_modes.electrochem.undo_state import ec_push_state, ec_restore_state

    def _noop(*_a, **_k):
        return None

    fig, ax, cycle_lines = _make_ec_fig()
    ax.set_position([0.15, 0.20, 0.70, 0.60])
    hist: list = []
    ec_push_state(
        state_history=hist,
        fig=fig,
        ax=ax,
        tick_state={},
        cycle_lines=cycle_lines,
        file_data=None,
        is_multi_file=False,
        note="geom",
    )
    ax.set_position([0.30, 0.30, 0.40, 0.40])
    ec_restore_state(
        state_history=hist,
        fig=fig,
        ax=ax,
        tick_state={},
        cycle_lines=cycle_lines,
        file_data=None,
        is_multi_file=False,
        apply_nice_ticks=_noop,
        apply_wasd_state=_noop,
        update_tick_visibility=_noop,
        apply_display_mode=_noop,
        apply_font_family=_noop,
        apply_font_size=_noop,
        ec_font_artists=lambda *_a, **_k: [],
    )
    b = ax.get_position().bounds
    assert abs(b[0] - 0.15) < 1e-6
    assert abs(b[2] - 0.70) < 1e-6
    plt.close(fig)


def test_ec_style_only_ps_strips_canvas_keys():
    from batplot.plot_modes.electrochem.actions import (
        ElectrochemActionContext,
        _build_ec_style_export_config,
    )

    fig, ax, cycle_lines = _make_ec_fig()
    snap = ES._get_style_snapshot(fig, ax, cycle_lines, {}, file_data=None)
    assert "canvas_size" in (snap.get("figure") or {})
    ctx = ElectrochemActionContext(
        fig=fig,
        ax=ax,
        cycle_lines=cycle_lines,
        file_data=[],
        tick_state={},
        source_paths=[],
        all_cycles=[1],
        is_dqdv=False,
        is_multi_file=False,
        menu_title="EC",
        canvas_mode=False,
        print_menu=lambda *_a, **_k: None,
        push_state=lambda *_a, **_k: None,
        pop_undo=lambda: None,
        restore_state=lambda: None,
        format_file_timestamp=lambda *_a, **_k: "",
        savefig_plot_window=lambda *_a, **_k: None,
        rebuild_legend=lambda *_a, **_k: None,
        get_style_snapshot=lambda *_a, **_k: dict(snap),
        get_geometry_snapshot=ES._get_geometry_snapshot,
        print_style_snapshot=lambda *_a, **_k: None,
        export_style_dialog=lambda *_a, **_k: None,
        apply_font_family=lambda *_a, **_k: None,
        apply_font_size=lambda *_a, **_k: None,
        apply_spine_color=lambda *_a, **_k: None,
        iter_cycle_lines=lambda *_a, **_k: [],
        apply_cycle_styles=lambda *_a, **_k: None,
        apply_stored_smooth_settings=lambda *_a, **_k: None,
        sanitize_legend_offset=lambda _fig, xy: xy,
        apply_file_display_names_to_legend=lambda *_a, **_k: None,
        apply_display_mode=lambda *_a, **_k: None,
        ui_position_top_xlabel=lambda *_a, **_k: None,
        ui_position_bottom_xlabel=lambda *_a, **_k: None,
        ui_position_left_ylabel=lambda *_a, **_k: None,
        ui_position_right_ylabel=lambda *_a, **_k: None,
        apply_legend_position=lambda *_a, **_k: None,
        set_legend_user_pref=lambda *_a, **_k: None,
    )
    cfg, ext = _build_ec_style_export_config(ctx, "ps")
    assert ext == ".bps"
    assert cfg["kind"] == "ec_style"
    assert "geometry" not in cfg
    fig_block = cfg.get("figure") or {}
    assert "canvas_size" not in fig_block
    assert "axes_fraction" not in fig_block
    plt.close(fig)


def test_cpc_session_dump_subplot_margins_match_live_set_position(session_path):
    fig, ax, ax2, sc_c, sc_d, sc_e, file_data = _make_cpc_fig()
    ax.set_position([0.25, 0.30, 0.55, 0.50])
    ax2.set_position(ax.get_position())
    live = ax.get_position().bounds
    path = session_path("cpc_live_frame.pkl")
    dump_cpc_session(
        path,
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
        file_data=file_data,
        skip_confirm=True,
    )
    with open(path, "rb") as fh:
        sess = pickle.load(fh)
    spm = sess["figure"]["subplot_margins"]
    assert abs(spm["left"] - live[0]) < 1e-9
    assert abs(spm["bottom"] - live[1]) < 1e-9
    plt.close(fig)


def test_cpc_session_load_prefers_axes_bbox_over_stale_margins(session_path):
    fig, ax, ax2, sc_c, sc_d, sc_e, file_data = _make_cpc_fig()
    ax.set_position([0.22, 0.28, 0.50, 0.45])
    ax2.set_position(ax.get_position())
    path = session_path("cpc_bbox_authority.pkl")
    dump_cpc_session(
        path,
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
        file_data=file_data,
        skip_confirm=True,
    )
    with open(path, "rb") as fh:
        sess = pickle.load(fh)
    sess["figure"]["subplot_margins"] = {
        "left": 0.05, "right": 0.99, "bottom": 0.05, "top": 0.99
    }
    sess["figure"]["frame_size"] = (7.5, 5.5)
    with open(path, "wb") as fh:
        pickle.dump(sess, fh)
    res = load_cpc_session(path)
    assert res is not None
    fig2, ax_b = res[0], res[1]
    b = ax_b.get_position().bounds
    assert abs(b[0] - 0.22) < 1e-6
    assert abs(b[1] - 0.28) < 1e-6
    assert abs(b[2] - 0.50) < 1e-6
    assert abs(b[3] - 0.45) < 1e-6
    plt.close(fig)
    plt.close(fig2)


def test_cpc_session_empty_labels_roundtrip(session_path):
    fig, ax, ax2, sc_c, sc_d, sc_e, file_data = _make_cpc_fig()
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax2.set_ylabel("")
    path = session_path("cpc_empty_labels.pkl")
    dump_cpc_session(
        path,
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
        file_data=file_data,
        skip_confirm=True,
    )
    res = load_cpc_session(path)
    assert res is not None
    _fig2, ax_b, ax2_b = res[0], res[1], res[2]
    assert ax_b.get_xlabel() == ""
    assert ax_b.get_ylabel() == ""
    assert ax2_b.get_ylabel() == ""
    plt.close(fig)
    plt.close(_fig2)


def test_cpc_psg_apply_syncs_ax2_position_and_geometry_tuple_limits():
    fig, ax, ax2, sc_c, sc_d, sc_e, file_data = _make_cpc_fig()
    cfg = CS._style_snapshot(fig, ax, ax2, sc_c, sc_d, sc_e, file_data=file_data)
    cfg["kind"] = "cpc_style_geom"
    cfg["figure"]["axes_fraction"] = [0.20, 0.25, 0.60, 0.55]
    cfg["geometry"] = {
        "xlabel": "X",
        "ylabel_left": "YL",
        "ylabel_right": "YR",
        "xlim": (0.0, 4.0),
        "ylim_left": (80.0, 120.0),
        "ylim_right": (85.0, 100.0),
    }
    CS._apply_style(fig, ax, ax2, sc_c, sc_d, sc_e, cfg, file_data=file_data)
    _apply_cpc_geometry_snapshot(ax, ax2, cfg["geometry"])
    b = ax.get_position().bounds
    b2 = ax2.get_position().bounds
    assert abs(b[0] - 0.20) < 1e-6
    assert all(abs(x - y) < 1e-6 for x, y in zip(b, b2))
    assert ax.get_xlim() == (0.0, 4.0)
    assert ax.get_ylim() == (80.0, 120.0)
    assert ax2.get_ylim() == (85.0, 100.0)
    plt.close(fig)


def test_cpc_style_only_ps_strips_canvas_keys():
    from batplot.plot_modes.cpc.actions import CpcActionContext, _build_cpc_style_export_config

    fig, ax, ax2, sc_c, sc_d, sc_e, file_data = _make_cpc_fig()
    snap = CS._style_snapshot(fig, ax, ax2, sc_c, sc_d, sc_e, file_data=file_data)
    assert "axes_fraction" in (snap.get("figure") or {})
    ctx = CpcActionContext(
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
        file_data=file_data,
        file_paths=[],
        is_multi_file=False,
        tick_state={},
        safe_input=lambda *a, **k: "q",
        colorize_prompt=lambda s: s,
        colorize_inline_commands=lambda s: s,
        print_menu=lambda *a, **k: None,
        choose_save_path=lambda *a, **k: None,
        choose_style_file=lambda *a, **k: None,
        list_files_in_subdirectory=lambda *a, **k: [],
        get_organized_path=lambda *a, **k: "",
        ensure_exact_case_filename=lambda s: s,
        natural_sort_key=lambda s: s,
        dump_cpc_session=lambda *a, **k: None,
        format_file_timestamp=lambda s: s,
        rebuild_legend=lambda *a, **k: None,
        style_snapshot=lambda *a, **k: dict(snap),
        apply_style=lambda *a, **k: None,
        get_geometry_snapshot=_get_geometry_snapshot,
        push_state=lambda *a, **k: None,
        pop_undo=lambda *a, **k: None,
        restore_state=lambda *a, **k: None,
    )
    cfg, ext = _build_cpc_style_export_config(ctx, "ps")
    assert ext == ".bps"
    assert cfg["kind"] == "cpc_style"
    assert "geometry" not in cfg
    fig_block = cfg.get("figure") or {}
    assert "canvas_size" not in fig_block
    assert "axes_fraction" not in fig_block
    plt.close(fig)


def test_cpc_geometry_snapshot_prefers_stored_labels_when_hidden():
    fig, ax, ax2, sc_c, sc_d, sc_e, file_data = _make_cpc_fig()
    ax._stored_xlabel = "Cycle number"
    ax._stored_ylabel = "Capacity"
    ax2._stored_ylabel = "Efficiency (%)"
    ax.set_xlabel("")
    ax.set_ylabel("")
    ax2.set_ylabel("")
    geom = _get_geometry_snapshot(ax, ax2)
    assert geom["xlabel"] == "Cycle number"
    assert geom["ylabel_left"] == "Capacity"
    assert geom["ylabel_right"] == "Efficiency (%)"
    plt.close(fig)


def test_cpc_undo_restores_geometry_limits_and_labels():
    from batplot.plot_modes.cpc.snapshots import push_cpc_state, restore_cpc_state

    fig, ax, ax2, sc_c, sc_d, sc_e, file_data = _make_cpc_fig()
    ax.set_xlim(0, 5)
    ax.set_ylim(50, 150)
    ax2.set_ylim(80, 100)
    ax.set_xlabel("X0")
    ax.set_ylabel("YL0")
    ax2.set_ylabel("YR0")
    ax._stored_xlabel = "X0"
    ax._stored_ylabel = "YL0"
    ax2._stored_ylabel = "YR0"
    hist: list = []
    tick_state = {}
    push_cpc_state(
        hist,
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
        file_data=file_data,
        tick_state=tick_state,
        note="geom",
    )
    ax.set_xlim(1, 2)
    ax.set_ylim(1, 2)
    ax2.set_ylim(1, 2)
    ax.set_xlabel("CHANGED")
    ax.set_ylabel("CHANGED")
    ax2.set_ylabel("CHANGED")
    assert restore_cpc_state(
        hist,
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
        file_data=file_data,
        tick_state=tick_state,
        update_ticks_func=lambda: None,
    )
    assert ax.get_xlim() == (0.0, 5.0)
    assert ax.get_ylim() == (50.0, 150.0)
    assert ax2.get_ylim() == (80.0, 100.0)
    assert ax.get_xlabel() == "X0"
    assert ax2.get_ylabel() == "YR0"
    plt.close(fig)


def test_cpc_set_position_sync_helper_keeps_ax2_locked():
    """Mirrors post-``g`` twin sync used by interactive/batch CPC geometry."""
    fig, ax, ax2, sc_c, sc_d, sc_e, file_data = _make_cpc_fig()
    ax.set_position([0.18, 0.22, 0.55, 0.48])
    ax2.set_position([0.05, 0.05, 0.20, 0.20])  # desynced twin
    ax2.set_position(ax.get_position())
    assert all(
        abs(a - b) < 1e-9
        for a, b in zip(ax.get_position().bounds, ax2.get_position().bounds)
    )
    plt.close(fig)

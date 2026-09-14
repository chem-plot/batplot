"""Spine/title colors must survive p/i/s/b and stay complete across modes."""

from __future__ import annotations

import pickle
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

from batplot.plot_modes.electrochem.style import (
    apply_dual_top_axis_style,
    capture_dual_top_axis,
    _get_style_snapshot,
)
from batplot.plot_modes.common.style_routing import apply_ec_style_dict
from batplot.ui import (
    finalize_spine_colors,
    finalize_spine_colors_cpc,
    set_spine_side_color,
)


def _rgb(c):
    from matplotlib.colors import to_rgb

    return tuple(round(v, 5) for v in to_rgb(c))


def _make_dual_gc_fig():
    fig, ax = plt.subplots()
    ax.plot([0.0, 100.0], [3.0, 4.0])
    ax.set_xlabel("Specific Capacity (mAh g$^{-1}$)")
    ax.set_ylabel("Potential (V)")
    sec = ax.secondary_xaxis("top", functions=(lambda x: x / 162.5, lambda x: x * 162.5))
    sec.set_xlabel("Number of ions (C / 162.5 mAh g$^{-1}$)")
    fig._xaxis_secondary = sec
    fig._xaxis_mode = "dual"
    fig._xaxis_c_theoretical = 162.5
    fig._gc_capacity_mode = "per_cycle"
    return fig, ax, sec


def test_set_spine_side_color_on_primary_syncs_secondary():
    fig, ax, sec = _make_dual_gc_fig()
    set_spine_side_color(ax, "top", "green", fig=fig)
    fig.canvas.draw()
    finalize_spine_colors(fig, ax, draw=True)
    g = _rgb("green")
    assert _rgb(sec.spines["top"].get_edgecolor()) == g
    assert _rgb(sec.xaxis.label.get_color()) == g
    assert _rgb(ax.spines["top"].get_edgecolor()) == g
    plt.close(fig)


def test_top_spine_color_does_not_recolor_bottom_xlabel():
    """XY: coloring top spine must not change the bottom axis title color."""
    fig, ax = plt.subplots()
    ax.plot([0.0, 1.0], [0.0, 1.0])
    ax.set_xlabel(r"Q ($\mathrm{\AA}^{-1}$)")
    ax.set_ylabel("Intensity")
    set_spine_side_color(ax, "bottom", "#0000ff", fig=fig)
    set_spine_side_color(ax, "left", "#ff0000", fig=fig)
    set_spine_side_color(ax, "top", "#d47cbe", fig=fig)
    fig.canvas.draw()
    assert _rgb(ax.spines["bottom"].get_edgecolor()) == _rgb("#0000ff")
    assert _rgb(ax.spines["top"].get_edgecolor()) == _rgb("#d47cbe")
    assert _rgb(ax.xaxis.label.get_color()) == _rgb("#0000ff")
    assert _rgb(ax.yaxis.label.get_color()) == _rgb("#ff0000")
    plt.close(fig)


def test_old_pkl_hitchhiked_title_color_heals_on_restore():
    """Old dumps that saved top-spine color as xlabel_color must heal to bottom."""
    import pickle
    import tempfile
    from pathlib import Path

    from batplot.ui import (
        heal_axis_label_colors_dict,
        heal_restored_axis_title_color,
        set_spine_side_color,
    )

    top_c = "#d47cbe"
    bottom_c = "#0000ff"
    left_c = "#ff0000"
    right_c = "#00aa00"

    # Heal helper: hitchhiked title == opposite spine → matching spine wins
    assert _rgb(
        heal_restored_axis_title_color(
            top_c, matching_spine_color=bottom_c, opposite_spine_color=top_c
        )
    ) == _rgb(bottom_c)
    # Intentional distinct title color is preserved
    assert _rgb(
        heal_restored_axis_title_color(
            "#123456", matching_spine_color=bottom_c, opposite_spine_color=top_c
        )
    ) == _rgb("#123456")

    healed = heal_axis_label_colors_dict(
        {"x": top_c, "y": right_c},
        {
            "top": {"color": top_c},
            "bottom": {"color": bottom_c},
            "left": {"color": left_c},
            "right": {"color": right_c},
        },
    )
    assert _rgb(healed["x"]) == _rgb(bottom_c)
    assert _rgb(healed["y"]) == _rgb(left_c)

    # Simulate EC-style restore: apply spines then heal hitchhiked xlabel_color
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_xlabel("Q")
    ax.set_ylabel("I")
    sp_meta = {
        "top": {"color": top_c, "visible": True},
        "bottom": {"color": bottom_c, "visible": True},
        "left": {"color": left_c, "visible": True},
        "right": {"color": right_c, "visible": True},
    }
    blob = {
        "version": 2,
        "axis": {
            "xlabel": "Q",
            "ylabel": "I",
            "xlabel_color": top_c,  # hitchhiked
            "ylabel_color": right_c,  # hitchhiked onto left title
        },
        "spines": sp_meta,
    }
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "legacy_hitchhike.pkl"
        with p.open("wb") as fh:
            pickle.dump(blob, fh, protocol=4)
        with p.open("rb") as fh:
            sess = pickle.load(fh)

    for name, spec in sess["spines"].items():
        set_spine_side_color(ax, name, spec["color"], fig=fig)
    healed_x = heal_restored_axis_title_color(
        sess["axis"]["xlabel_color"],
        matching_spine_color=sess["spines"]["bottom"]["color"],
        opposite_spine_color=sess["spines"]["top"]["color"],
    )
    healed_y = heal_restored_axis_title_color(
        sess["axis"]["ylabel_color"],
        matching_spine_color=sess["spines"]["left"]["color"],
        opposite_spine_color=sess["spines"]["right"]["color"],
    )
    ax.xaxis.label.set_color(healed_x)
    ax.yaxis.label.set_color(healed_y)
    fig.canvas.draw()
    assert _rgb(ax.spines["top"].get_edgecolor()) == _rgb(top_c)
    assert _rgb(ax.spines["bottom"].get_edgecolor()) == _rgb(bottom_c)
    assert _rgb(ax.xaxis.label.get_color()) == _rgb(bottom_c)
    assert _rgb(ax.yaxis.label.get_color()) == _rgb(left_c)
    plt.close(fig)


def test_wasd_spine_colors_isolate_axis_titles_all_modes():
    """Each WASD side recolors only its own spine (+ matching-side title)."""
    from batplot.plot_modes.histo.spines import set_histo_spine_color
    from batplot.plot_modes.operando.spine_colors import apply_operando_spine_color
    from batplot.plot_modes.xy.spines import apply_xy_spine_color, ensure_xy_tick_state

    colors = {
        "top": "#cc0000",
        "bottom": "#0033aa",
        "left": "#00aa00",
        "right": "#aa00aa",
    }

    def _paint_wasd(apply_fn):
        for side, col in colors.items():
            apply_fn(side, col)

    # --- XY (labels on bottom/left) ---
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ts = ensure_xy_tick_state(ax, {})
    _paint_wasd(lambda s, c: apply_xy_spine_color(fig, ax, ts, s, c))
    fig.canvas.draw()
    for side, col in colors.items():
        assert _rgb(ax.spines[side].get_edgecolor()) == _rgb(col)
    assert _rgb(ax.xaxis.label.get_color()) == _rgb(colors["bottom"])
    assert _rgb(ax.yaxis.label.get_color()) == _rgb(colors["left"])
    plt.close(fig)

    # --- Histogram ---
    fig, ax = plt.subplots()
    ax.hist([1, 2, 2, 3])
    ax.set_xlabel("Size")
    ax.set_ylabel("Count")
    _paint_wasd(lambda s, c: set_histo_spine_color(fig, ax, s, c))
    fig.canvas.draw()
    for side, col in colors.items():
        assert _rgb(ax.spines[side].get_edgecolor()) == _rgb(col)
    assert _rgb(ax.xaxis.label.get_color()) == _rgb(colors["bottom"])
    assert _rgb(ax.yaxis.label.get_color()) == _rgb(colors["left"])
    plt.close(fig)

    # --- Operando + EC (ylabel on right): left must not steal EC title ---
    fig = plt.figure()
    ax = fig.add_subplot(121)
    ec = fig.add_subplot(122)
    ax.imshow([[0.0, 1.0], [1.0, 0.0]])
    ax.set_xlabel("Q")
    ax.set_ylabel("Scan")
    ec.plot([1.0, 2.0], [3.0, 2.0])
    ec.set_xlabel("Capacity")
    ec.set_ylabel("Potential")
    ec.yaxis.tick_right()
    ec.yaxis.set_label_position("right")
    _paint_wasd(lambda s, c: apply_operando_spine_color(fig, ax, s, c, peer_ax=ec))
    _paint_wasd(lambda s, c: apply_operando_spine_color(fig, ec, s, c, peer_ax=ax))
    fig.canvas.draw()
    for side, col in colors.items():
        assert _rgb(ax.spines[side].get_edgecolor()) == _rgb(col)
        assert _rgb(ec.spines[side].get_edgecolor()) == _rgb(col)
    assert _rgb(ax.xaxis.label.get_color()) == _rgb(colors["bottom"])
    assert _rgb(ax.yaxis.label.get_color()) == _rgb(colors["left"])
    assert _rgb(ec.xaxis.label.get_color()) == _rgb(colors["bottom"])
    assert _rgb(ec.yaxis.label.get_color()) == _rgb(colors["right"])
    plt.close(fig)

    # --- Dual GC: top colors secondary title; primary bottom title stays ---
    fig, ax, sec = _make_dual_gc_fig()
    set_spine_side_color(ax, "bottom", colors["bottom"], fig=fig)
    set_spine_side_color(ax, "left", colors["left"], fig=fig)
    set_spine_side_color(ax, "right", colors["right"], fig=fig)
    set_spine_side_color(ax, "top", colors["top"], fig=fig)
    fig.canvas.draw()
    finalize_spine_colors(fig, ax, draw=True)
    assert _rgb(ax.xaxis.label.get_color()) == _rgb(colors["bottom"])
    assert _rgb(ax.yaxis.label.get_color()) == _rgb(colors["left"])
    assert _rgb(sec.xaxis.label.get_color()) == _rgb(colors["top"])
    assert _rgb(ax.spines["top"].get_edgecolor()) == _rgb(colors["top"])
    plt.close(fig)

    # --- CPC twin: right title on ax2 only ---
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    ax.set_xlabel("Cycle")
    ax.set_ylabel("Capacity")
    ax2 = ax.twinx()
    ax2.plot([0, 1], [1, 0])
    ax2.set_ylabel("Efficiency")
    ax2.yaxis.set_label_position("right")
    set_spine_side_color(ax, "bottom", colors["bottom"], fig=fig)
    set_spine_side_color(ax, "left", colors["left"], fig=fig)
    set_spine_side_color(ax, "top", colors["top"], fig=fig)
    set_spine_side_color(ax2, "right", colors["right"], fig=fig)
    fig.canvas.draw()
    assert _rgb(ax.xaxis.label.get_color()) == _rgb(colors["bottom"])
    assert _rgb(ax.yaxis.label.get_color()) == _rgb(colors["left"])
    assert _rgb(ax2.yaxis.label.get_color()) == _rgb(colors["right"])
    # Left on primary must not recolor right twin title
    set_spine_side_color(ax, "left", "#112233", fig=fig)
    fig.canvas.draw()
    assert _rgb(ax.yaxis.label.get_color()) == _rgb("#112233")
    assert _rgb(ax2.yaxis.label.get_color()) == _rgb(colors["right"])
    plt.close(fig)


def test_style_snapshot_and_apply_preserves_dual_top_color(tmp_path: Path):
    fig, ax, sec = _make_dual_gc_fig()
    set_spine_side_color(sec, "top", "#008000", fig=fig)
    tick_state = {
        "bx": True,
        "tx": True,
        "ly": True,
        "ry": False,
        "b_ticks": True,
        "t_ticks": True,
        "l_ticks": True,
        "r_ticks": False,
        "b_labels": True,
        "t_labels": True,
        "l_labels": True,
        "r_labels": False,
    }
    snap = _get_style_snapshot(fig, ax, {}, tick_state)
    assert snap["xaxis_dual"]["top_axis"]["spine_color"] is not None
    # New figure, recreate dual, import style
    fig2, ax2 = plt.subplots()
    ax2.plot([0.0, 50.0], [3.0, 3.5])
    fig2._xaxis_mode = "capacity"
    # silent avoids interactive ions prompt under pytest capture
    apply_ec_style_dict(snap, fig2, ax2, cycle_lines={}, silent=True)
    # Direct dual restore path (same as session/undo after recreate)
    sec2 = ax2.secondary_xaxis("top", functions=(lambda x: x / 162.5, lambda x: x * 162.5))
    fig2._xaxis_secondary = sec2
    fig2._xaxis_mode = "dual"
    apply_dual_top_axis_style(sec2, snap["xaxis_dual"]["top_axis"], fig=fig2)
    finalize_spine_colors(fig2, ax2, draw=True)
    g = _rgb("#008000")
    assert _rgb(sec2.spines["top"].get_edgecolor()) == g
    assert _rgb(sec2.xaxis.label.get_color()) == g
    assert _rgb(ax2.spines["top"].get_edgecolor()) == g
    plt.close(fig)
    plt.close(fig2)


def test_apply_dual_top_axis_style_with_fig_syncs_parent():
    fig, ax, sec = _make_dual_gc_fig()
    cfg = {
        "xlabel": "ions",
        "xlabel_visible": True,
        "label_color": "#ff0000",
        "spine_visible": True,
        "spine_color": "#ff0000",
    }
    apply_dual_top_axis_style(sec, cfg, fig=fig)
    finalize_spine_colors(fig, ax, draw=True)
    assert _rgb(sec.spines["top"].get_edgecolor()) == _rgb("red")
    assert _rgb(ax.spines["top"].get_edgecolor()) == _rgb("red")
    assert _rgb(sec.xaxis.label.get_color()) == _rgb("red")
    plt.close(fig)


def test_cpc_top_xlabel_text_gets_spine_color():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    ax.plot([1, 2], [10, 20])
    ax2.plot([1, 2], [0.9, 0.8])
    fig._cpc_spine_colors = {"top": "#0000ff"}
    ax._top_xlabel_text = ax.text(0.5, 1.02, "Cycle number", transform=ax.transAxes)
    set_spine_side_color(ax, "top", "#0000ff", fig=fig)
    finalize_spine_colors_cpc(fig, ax, ax2, draw=True)
    assert _rgb(ax._top_xlabel_text.get_color()) == _rgb("blue")
    plt.close(fig)


def test_capture_dual_top_axis_includes_colors():
    fig, ax, sec = _make_dual_gc_fig()
    set_spine_side_color(sec, "top", "green", fig=fig)
    cap = capture_dual_top_axis(fig, ax)
    assert cap is not None
    assert _rgb(cap["spine_color"]) == _rgb("green")
    assert _rgb(cap["label_color"]) == _rgb("green")
    plt.close(fig)


def test_xy_undo_reseals_spine_colors_after_tick_params():
    """XY ``b`` must not leave black tick marks after restoring spine colors."""
    from batplot.plot_modes.xy.spines import apply_xy_spine_color
    from batplot.plot_modes.xy.undo_state import xy_push_state, xy_restore_state

    fig, ax = plt.subplots()
    ax.plot([0, 1], [1, 2])
    tick_state = {
        "b_ticks": True, "b_labels": True, "bx": True,
        "l_ticks": True, "l_labels": True, "ly": True,
        "t_ticks": False, "t_labels": False, "tx": False,
        "r_ticks": False, "r_labels": False, "ry": False,
    }
    ax._saved_tick_state = dict(tick_state)
    apply_xy_spine_color(fig, ax, tick_state, "left", "red")
    hist: list = []

    class _Args:
        stack = False

    xy_push_state(
        state_history=hist,
        fig=fig,
        ax=ax,
        tick_state=tick_state,
        labels=["c1"],
        delta=0.0,
        x_data_list=[[0, 1]],
        y_data_list=[[1, 2]],
        orig_y=[[1, 2]],
        offsets_list=[0.0],
        x_full_list=[[0, 1]],
        raw_y_full_list=[[1, 2]],
        label_text_objects=[],
        bp=None,
        cif_series_for_session=lambda: [],
        iter_lines=lambda: list(enumerate(ax.lines)),
        note="baseline",
    )
    apply_xy_spine_color(fig, ax, tick_state, "left", "blue")
    ax.tick_params(axis="y", which="major", width=2.0, colors="black")
    xy_restore_state(
        state_history=hist,
        fig=fig,
        ax=ax,
        args=_Args(),
        tick_state=tick_state,
        labels=["c1"],
        x_data_list=[[0, 1]],
        y_data_list=[[1, 2]],
        orig_y=[[1, 2]],
        offsets_list=[0.0],
        x_full_list=[[0, 1]],
        raw_y_full_list=[[1, 2]],
        label_text_objects=[],
        bp=None,
        delta=0.0,
        use_Q=False,
        use_2th=True,
        file_wavelength_info={},
        cif_globals={},
        sync_legacy_tick_keys=lambda *a, **k: None,
        update_tick_visibility=lambda *a, **k: None,
        sync_fonts=lambda *a, **k: None,
        position_top_xlabel=lambda *a, **k: None,
        position_right_ylabel=lambda *a, **k: None,
        update_ylabel_for_derivative=lambda *a, **k: None,
        sync_fig_cif_tick_series=lambda *a, **k: None,
        line=lambda i: ax.lines[i],
        nlines=lambda: len(ax.lines),
    )
    assert _rgb(ax.spines["left"].get_edgecolor()) == _rgb("red")
    for tick in ax.yaxis.get_major_ticks():
        ln = getattr(tick, "tick1line", None)
        if ln is not None and ln.get_visible():
            assert _rgb(ln.get_color()) == _rgb("red")
            break
    plt.close(fig)


def test_operando_dual_pane_spine_colors_independent_and_finalize():
    """Operando heatmap + EC must keep distinct left spine colors after finalize."""
    from batplot.ui import finalize_spine_colors_for_axes

    fig, ax = plt.subplots()
    ec_ax = fig.add_axes((0.8, 0.1, 0.15, 0.8))
    set_spine_side_color(ax, "left", "red", fig=fig)
    set_spine_side_color(ec_ax, "left", "blue", fig=fig)
    finalize_spine_colors_for_axes(
        fig,
        [(ax, None), (ec_ax, None)],
        draw=True,
    )
    assert _rgb(ax.spines["left"].get_edgecolor()) == _rgb("red")
    assert _rgb(ec_ax.spines["left"].get_edgecolor()) == _rgb("blue")
    assert _rgb(getattr(ax, "_bp_spine_side_colors")["left"]) == _rgb("red")
    assert _rgb(getattr(ec_ax, "_bp_spine_side_colors")["left"]) == _rgb("blue")
    plt.close(fig)


def test_histo_snapshot_missing_spine_colors_captures_from_artists():
    from batplot.plot_modes.histo.spines import (
        apply_histo_spine_snapshot,
        set_histo_spine_color,
    )

    fig, ax = plt.subplots()
    ax.bar([0, 1], [1, 2])
    set_histo_spine_color(fig, ax, "left", "green")
    # Simulate old snap without spine_colors key; clear fig store first.
    if hasattr(fig, "_histo_spine_colors"):
        delattr(fig, "_histo_spine_colors")
    apply_histo_spine_snapshot(fig, ax, {"tick_state": {}})
    assert _rgb(fig._histo_spine_colors.get("left")) == _rgb("green")
    assert _rgb(ax.spines["left"].get_edgecolor()) == _rgb("green")
    plt.close(fig)


def test_cpc_session_dumps_explicit_spine_colors(tmp_path: Path):
    from batplot.plot_modes.cpc.session import dump_cpc_session

    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc_c = ax.scatter([1, 2], [10, 20], c=["#111111"])
    sc_d = ax.scatter([1, 2], [9, 18], c=["#222222"])
    sc_e = ax2.scatter([1, 2], [0.9, 0.95], c=["#333333"])
    fig._cpc_spine_colors = {"left": "#ff0000", "right": "#0000ff"}
    set_spine_side_color(ax, "left", "#ff0000", fig=fig)
    set_spine_side_color(ax2, "right", "#0000ff", fig=fig)
    pkl = tmp_path / "cpc_spine.pkl"
    dump_cpc_session(
        str(pkl),
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
        skip_confirm=True,
    )
    with open(pkl, "rb") as f:
        sess = pickle.load(f)
    assert "spine_colors" in sess
    assert _rgb(sess["spine_colors"]["left"]) == _rgb("red")
    assert _rgb(sess["spine_colors"]["right"]) == _rgb("blue")
    plt.close(fig)

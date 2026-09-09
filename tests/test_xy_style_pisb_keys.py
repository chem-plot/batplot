"""Hard gates for XY style keys across p / i / s / b.

Covers recent gaps: font extras undo, style-only margins, axis title texts,
dual-Y undo metadata, derivative ylabel authority, batch line alpha chrome.
"""

from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from batplot.plot_modes.common.font_extras import (
    apply_fig_font_weight,
    apply_fig_text_highlight,
    get_fig_font_weight,
    get_fig_text_highlight,
)
from batplot.plot_modes.common.fonts import collect_fig_font_artists
from batplot.plot_modes.xy import style as ST
from batplot.plot_modes.xy.undo_state import xy_push_state, xy_restore_state


class _Args:
    stack = False
    xaxis = "2theta"
    wl = None


def _noop(*_a, **_k):
    return None


def _push_restore_common(fig, ax, hist, labels=None):
    labels = labels or ["c1"]
    xy_push_state(
        state_history=hist,
        fig=fig,
        ax=ax,
        tick_state={
            "b_ticks": True,
            "b_labels": True,
            "bx": True,
            "l_ticks": True,
            "l_labels": True,
            "ly": True,
            "t_ticks": False,
            "t_labels": False,
            "tx": False,
            "r_ticks": False,
            "r_labels": False,
            "ry": False,
        },
        labels=labels,
        delta=0.0,
        x_data_list=[np.array([0.0, 1.0])],
        y_data_list=[np.array([1.0, 2.0])],
        orig_y=[np.array([1.0, 2.0])],
        offsets_list=[0.0],
        x_full_list=[np.array([0.0, 1.0])],
        raw_y_full_list=[np.array([1.0, 2.0])],
        label_text_objects=[],
        bp=None,
        cif_series_for_session=lambda: [],
        iter_lines=lambda: list(enumerate(ax.lines)),
        note="baseline",
    )


def _restore(fig, ax, hist):
    return xy_restore_state(
        state_history=hist,
        fig=fig,
        ax=ax,
        args=_Args(),
        tick_state={
            "b_ticks": True,
            "b_labels": True,
            "bx": True,
            "l_ticks": True,
            "l_labels": True,
            "ly": True,
            "t_ticks": False,
            "t_labels": False,
            "tx": False,
            "r_ticks": False,
            "r_labels": False,
            "ry": False,
        },
        labels=["c1"],
        x_data_list=[np.array([0.0, 1.0])],
        y_data_list=[np.array([1.0, 2.0])],
        orig_y=[np.array([1.0, 2.0])],
        offsets_list=[0.0],
        x_full_list=[np.array([0.0, 1.0])],
        raw_y_full_list=[np.array([1.0, 2.0])],
        label_text_objects=[],
        bp=None,
        delta=0.0,
        use_Q=False,
        use_2th=True,
        file_wavelength_info={},
        cif_globals={},
        sync_legacy_tick_keys=_noop,
        update_tick_visibility=_noop,
        sync_fonts=_noop,
        position_top_xlabel=_noop,
        position_right_ylabel=_noop,
        update_ylabel_for_derivative=lambda order, cur, is_reversed=False, **k: f"d{order}({cur})",
        sync_fig_cif_tick_series=_noop,
        line=lambda i: ax.lines[i],
        nlines=lambda: len(ax.lines),
    )


def test_xy_undo_restores_font_extras():
    fig, ax = plt.subplots()
    ax.plot([0, 1], [1, 2])
    ax.set_xlabel("X")
    artists = collect_fig_font_artists(ax, fig)
    apply_fig_font_weight(fig, artists, "bold")
    apply_fig_text_highlight(fig, artists, True, fc="yellow", alpha=0.7, pad=0.3)
    hist: list = []
    _push_restore_common(fig, ax, hist)
    apply_fig_font_weight(fig, artists, "normal")
    apply_fig_text_highlight(fig, artists, False)
    assert get_fig_font_weight(fig) == "normal"
    _restore(fig, ax, hist)
    assert get_fig_font_weight(fig) == "bold"
    assert get_fig_text_highlight(fig) is True
    plt.close(fig)


def test_xy_style_only_ps_does_not_apply_margins(tmp_path):
    fig, ax = plt.subplots(figsize=(6.0, 4.0))
    ax.plot([0, 1], [1, 2])
    fig.subplots_adjust(left=0.20, right=0.90, bottom=0.20, top=0.90)
    before = dict(fig.subplotpars.__dict__)
    style_path = tmp_path / "style.bps"
    ST.export_style_config(
        str(style_path),
        fig,
        ax,
        [np.array([1, 2])],
        ["c1"],
        0.0,
        _Args(),
        {},
        [0.0],
        overwrite_path=str(style_path),
        force_kind="ps",
    )
    payload = json.loads(style_path.read_text(encoding="utf-8"))
    assert payload["kind"] == "xy_style"
    # Style-only must not hitchhike canvas/frame/margins (parity with EC/CPC).
    assert "margins" not in payload
    fig_block = payload.get("figure") or {}
    assert "size" not in fig_block
    assert "frame_size" not in fig_block
    assert "axes_fraction" not in fig_block
    # Move axes, then import style-only — live frame must stay put.
    fig.subplots_adjust(left=0.05, right=0.99, bottom=0.05, top=0.99)
    ST.apply_style_config(
        str(style_path),
        fig,
        ax,
        [np.array([0, 1])],
        [np.array([1, 2])],
        [np.array([1, 2])],
        [0.0],
        [],
        _Args(),
        {},
        ["c1"],
        update_labels_func=_noop,
    )
    after = fig.subplotpars
    assert abs(after.left - 0.05) < 1e-6
    assert abs(after.right - 0.99) < 1e-6
    assert abs(before["left"] - 0.20) < 1e-6
    plt.close(fig)


def test_xy_undo_restores_axis_title_text_overrides():
    fig, ax = plt.subplots()
    ax.plot([0, 1], [1, 2])
    ax.set_xlabel("BottomX")
    ax.set_ylabel("LeftY")
    ax._top_xlabel_on = True
    ax._top_xlabel_text_override = "TopX"
    ax._right_ylabel_on = True
    ax._right_ylabel_text_override = "RightY"
    hist: list = []
    _push_restore_common(fig, ax, hist)
    ax._top_xlabel_text_override = "CHANGED"
    ax._right_ylabel_text_override = "CHANGED"
    ax.set_xlabel("CHANGED")
    ax.set_ylabel("CHANGED")
    _restore(fig, ax, hist)
    assert ax._top_xlabel_text_override == "TopX"
    assert ax._right_ylabel_text_override == "RightY"
    assert ax.get_xlabel() == "BottomX"
    assert ax.get_ylabel() == "LeftY"
    plt.close(fig)


def test_xy_undo_restores_dual_y_metadata():
    fig, ax = plt.subplots()
    (ln0,) = ax.plot([0, 1], [1, 2], label="a")
    (ln1,) = ax.plot([0, 1], [2, 3], label="b")
    fig._xy_lines_by_curve = [ln0, ln1]
    ST._apply_xy_dual_y_layout(fig, ax, frozenset({1}), use_top_x=True)
    assert getattr(fig, "_xy_use_top_x") is True
    hist: list = []
    _push_restore_common(fig, ax, hist, labels=["a", "b"])
    ST._apply_xy_dual_y_layout(fig, ax, frozenset(), use_top_x=False)
    assert not getattr(fig, "_xy_right_y_curve_indices", frozenset())
    _restore(fig, ax, hist)
    assert frozenset(getattr(fig, "_xy_right_y_curve_indices", frozenset())) == frozenset({1})
    assert bool(getattr(fig, "_xy_use_top_x", False)) is True
    plt.close(fig)


def test_xy_undo_derivative_does_not_clobber_axis_title_texts():
    fig, ax = plt.subplots()
    ax.plot([0, 1], [1, 2])
    ax.set_ylabel("CustomY")
    fig._derivative_order = 1
    hist: list = []
    _push_restore_common(fig, ax, hist)
    ax.set_ylabel("TEMP")
    fig._derivative_order = 2
    _restore(fig, ax, hist)
    assert ax.get_ylabel() == "CustomY"
    plt.close(fig)


def test_xy_batch_line_chrome_merges_alpha():
    from batplot.plot_modes.batch_session.xy_batch_helpers import merge_xy_line_chrome_cfg

    peer = {
        "kind": "xy_style",
        "lines": [{"index": 0, "color": "#00aa00", "alpha": 1.0, "linewidth": 1.0}],
    }
    ref = {
        "kind": "xy_style_geom",
        "lines": [{"index": 0, "color": "#ff0000", "alpha": 0.35, "linewidth": 2.5}],
    }
    out = merge_xy_line_chrome_cfg(peer, ref)
    assert out["lines"][0]["alpha"] == 0.35
    assert out["lines"][0]["linewidth"] == 2.5
    assert out["lines"][0]["color"] == "#00aa00"


def test_xy_export_prefers_ax2_right_ylabel(tmp_path):
    fig, ax = plt.subplots()
    (ln0,) = ax.plot([0, 1], [1, 2])
    (ln1,) = ax.plot([0, 1], [3, 4])
    fig._xy_lines_by_curve = [ln0, ln1]
    ST._apply_xy_dual_y_layout(fig, ax, frozenset({1}), use_top_x=False)
    ax2 = getattr(fig, "_xy_ax2")
    assert ax2 is not None
    ax2.set_ylabel("RightAxisY")
    style_path = tmp_path / "ry.bps"
    ST.export_style_config(
        str(style_path),
        fig,
        ax,
        [np.array([1, 2]), np.array([3, 4])],
        ["a", "b"],
        0.0,
        _Args(),
        {},
        [0.0, 0.0],
        overwrite_path=str(style_path),
        force_kind="psg",
    )
    payload = json.loads(style_path.read_text(encoding="utf-8"))
    assert payload["axis_title_texts"]["right_y"] == "RightAxisY"
    assert payload["right_y_curve_indices"] == [1]
    plt.close(fig)


def test_xy_export_cif_flags_from_fig_attrs(tmp_path):
    import sys

    fig, ax = plt.subplots()
    ax.plot([0, 1], [1, 2])
    fig._bp_show_cif_titles = False
    fig._bp_show_cif_hkl = True
    fig._bp_cif_set_visible = [True, False]
    # Process-global leftovers must not override the figure being exported.
    main = sys.modules.get("__main__")
    had_hkl = main is not None and hasattr(main, "show_cif_hkl")
    had_vis = main is not None and hasattr(main, "cif_set_visible")
    prev_hkl = getattr(main, "show_cif_hkl", None) if had_hkl else None
    prev_vis = getattr(main, "cif_set_visible", None) if had_vis else None
    if main is not None:
        main.show_cif_hkl = False
        main.cif_set_visible = [False, False]
    cif_series = [
        ("phase a", "a.cif", [1.0], None, 5.0, "#ff0000"),
        ("phase b", "b.cif", [2.0], None, 5.0, "#0000ff"),
    ]
    style_path = tmp_path / "cif.bps"
    try:
        ST.export_style_config(
            str(style_path),
            fig,
            ax,
            [np.array([1, 2])],
            ["c1"],
            0.0,
            _Args(),
            {},
            [0.0],
            cif_tick_series=cif_series,
            overwrite_path=str(style_path),
            force_kind="ps",
        )
        payload = json.loads(style_path.read_text(encoding="utf-8"))
        assert payload["show_cif_titles"] is False
        assert payload["show_cif_hkl"] is True
        assert payload["cif_set_visible"] == [True, False]
    finally:
        if main is not None:
            if had_hkl:
                main.show_cif_hkl = prev_hkl
            elif hasattr(main, "show_cif_hkl"):
                delattr(main, "show_cif_hkl")
            if had_vis:
                main.cif_set_visible = prev_vis
            elif hasattr(main, "cif_set_visible"):
                delattr(main, "cif_set_visible")
        plt.close(fig)

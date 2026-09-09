"""Regression gates for final deep-audit residual undo/CLI cracks."""

from __future__ import annotations

from types import SimpleNamespace

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot.cli_save import save_xy_session
from batplot.plot_modes.common.menus import run_legend_position_menu
from batplot.plot_modes.cpc.colors import apply_capacity_color_tokens
from batplot.plot_modes.operando.visibility import _set_colorbar_label_text
from batplot.plot_modes.xy.smoothing import run_smoothing_menu


def test_cpc_color_dry_run_rejects_bad_index():
    fig, ax = plt.subplots()
    file_data = [{"sc_charge": ax.scatter([1], [1])}]
    ok = apply_capacity_color_tokens(
        ["99:red"], fig=fig, file_data=file_data, palette_opts=["tab10"], commit=False
    )
    assert ok is False
    plt.close(fig)


def test_colorbar_label_q_does_not_snapshot():
    fig, ax = plt.subplots()
    im = ax.imshow(np.ones((2, 2)))
    cbar = fig.colorbar(im, ax=ax)
    snaps = []
    changed = _set_colorbar_label_text(
        im=im,
        cbar=cbar,
        safe_input=lambda *_a, **_k: "q",
        colorize_prompt=lambda s: s,
        snapshot=lambda note: snaps.append(note),
    )
    assert changed is False
    assert snaps == []
    plt.close(fig)


def test_legend_open_does_not_write_offset_attr():
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1], label="a")
    leg = ax.legend()
    written = {}

    def set_pos(xy):
        written["xy"] = xy

    run_legend_position_menu(
        fig=fig,
        get_legend=lambda: leg,
        get_position=lambda: None,
        set_position=set_pos,
        sanitize_offset=lambda xy: None if xy is None else tuple(xy),
        toggle_legend=lambda: None,
        apply_position=lambda: None,
        push_state=lambda *_a, **_k: None,
        safe_input=lambda *_a, **_k: "q",
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
    )
    assert "xy" not in written
    plt.close(fig)


def test_sm_zero_process_pops_undo():
    fig, ax = plt.subplots()
    hist = ["keep"]
    pops = []

    def push(note):
        hist.append(note)

    def pop():
        pops.append(hist.pop())

    # No last settings → prompts N, M, start_row directly.
    feeds = iter([
        "r",   # reduce
        "1",   # delete/skip
        "1",   # N
        "0",   # M
        "99",  # start row past end → processed==0
        "q",   # back reduce
        "q",   # back sm
    ])

    run_smoothing_menu(
        fig=fig,
        x_data_list=[np.array([0.0, 1.0])],
        y_data_list=[np.array([0.0, 1.0])],
        offsets_list=[0.0],
        ensure_original_data=lambda: None,
        reset_to_original=lambda: (False, 0, 0),
        apply_data_changes=lambda: None,
        update_full_processed_data=lambda: None,
        get_last_reduce_rows_settings=lambda *_a, **_k: {},
        save_last_reduce_rows_settings=lambda *_a, **_k: None,
        get_last_smooth_settings_from_config=lambda: {},
        save_last_smooth_settings_to_config=lambda *_a, **_k: None,
        push_state=push,
        safe_input=lambda *_a, **_k: next(feeds),
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
        pop_undo=pop,
    )
    assert hist == ["keep"]
    assert pops
    plt.close(fig)


def test_cli_xy_dump_failure_does_not_stamp(tmp_path):
    fig, ax = plt.subplots()
    ax.plot([0, 1], [0, 1])
    args = SimpleNamespace(stack=False, autoscale=False, norm=False, files=[], xaxis="Q")
    bad = tmp_path / "missing" / "x.pkl"
    fig._last_session_save_path = None  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError):
        save_xy_session(
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
        )
    assert getattr(fig, "_last_session_save_path", None) in (None, "")
    plt.close(fig)

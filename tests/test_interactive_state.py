"""Tests for shared interactive state helpers.

These helpers are intentionally small and pure. They protect the duplicated
WASD tick-state bookkeeping that caused recent regressions in operando undo and
session load paths.
"""

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator, NullLocator

from batplot.plot_modes.common.interactive_state import (
    build_saved_tick_state,
    right_y_major_visibility,
    x_tickparam_keys,
    y_tickparam_keys,
)
from batplot.plot_modes.common.terminal import (
    colorize_inline_commands,
    colorize_prompt,
    colorize_single_key_inline_commands,
)
from batplot.plot_modes.common.menus import (
    run_axis_limit_menu,
    run_dispatch_menu,
    run_font_menu,
    run_legend_position_menu,
)
from batplot.plot_modes.common.fonts import (
    apply_font_family_to_artists,
    apply_font_size_to_artists,
    axis_text_artists,
    legend_text_artists,
    set_font_family_defaults,
    set_font_size_default,
)
from batplot.plot_modes.common.menu_rendering import (
    append_last_action_shortcuts,
    colorize_menu_item,
    print_menu_columns,
)
from batplot.plot_modes.common.files import format_file_timestamp
from batplot.plot_modes.common.smoothing import savgol_smooth
from batplot.plot_modes.common.sources import (
    file_data_source_paths,
    normalize_source_paths,
)
from batplot.plot_modes.common.title_offsets import (
    capture_title_offsets,
    reset_title_offsets,
    restore_title_offsets,
)
from batplot.plot_modes.common.spines import (
    apply_changed_side_title_positions,
    apply_flat_tick_params,
    apply_frame_and_tick_widths,
    apply_wasd_spines,
    apply_wasd_tick_params,
    default_flat_tick_state,
    keep_yaxis_label_on_side,
    legacy_tick_state_to_flat,
    parse_frame_tick_widths,
    run_spine_tick_menu,
    sync_tick_state_from_wasd,
    wasd_to_tick_state,
)
from batplot.plot_modes.electrochem.dqdv_2d import (
    _dqdv_2d_row_tick_indices,
    _dqdv_2d_voltage_tick_formatter,
)


def test_tickparam_key_mapping_matches_matplotlib_sides():
    assert x_tickparam_keys("top") == ("tick2On", "label2On")
    assert x_tickparam_keys("bottom") == ("tick1On", "label1On")
    assert y_tickparam_keys("left") == ("tick1On", "label1On")
    assert y_tickparam_keys("right") == ("tick2On", "label2On")


def test_build_saved_tick_state_uses_explicit_side_defaults():
    wasd = {
        "top": {"minor": True},
        "bottom": {},
        "left": {},
        "right": {"title": True},
    }
    defaults = {
        "top": False,
        "bottom": True,
        "left": True,
        "right": False,
    }

    out = build_saved_tick_state(wasd, tick_defaults=defaults, label_defaults=defaults)

    assert out["t_ticks"] is False
    assert out["t_labels"] is False
    assert out["mtx"] is True
    assert out["b_ticks"] is True
    assert out["b_labels"] is True
    assert out["l_ticks"] is True
    assert out["l_labels"] is True
    assert out["r_ticks"] is False
    assert out["r_labels"] is False


def test_build_saved_tick_state_allows_resolved_overrides():
    wasd = {"right": {"ticks": False, "labels": False}, "left": {}}
    out = build_saved_tick_state(
        wasd,
        tick_defaults={"right": False, "left": False},
        label_defaults={"right": False, "left": False},
        overrides={
            "r_ticks": True,
            "r_labels": True,
            "l_ticks": False,
            "l_labels": False,
        },
    )

    assert out["r_ticks"] is True
    assert out["r_labels"] is True
    assert out["l_ticks"] is False
    assert out["l_labels"] is False


def test_right_y_major_visibility_reads_displayed_tick2_state():
    fig, ax = plt.subplots()
    ax.plot([1, 2], [3, 4])
    ax.yaxis.tick_right()
    ax.yaxis.set_label_position("right")

    ticks_on, labels_on = right_y_major_visibility(ax, default=(False, False))

    assert ticks_on is True
    assert labels_on is True


def test_apply_wasd_tick_params_preserves_both_y_sides():
    fig, ax = plt.subplots()
    ax.plot([1, 2], [3, 4])
    wasd = {
        "top": {"ticks": False, "minor": False, "labels": False},
        "bottom": {"ticks": True, "minor": False, "labels": True},
        "left": {"ticks": True, "minor": True, "labels": True},
        "right": {"ticks": True, "minor": True, "labels": True},
    }

    apply_wasd_tick_params(ax, wasd)
    fig.canvas.draw()

    ticks = ax.yaxis.get_major_ticks()
    assert any(tick.tick1line.get_visible() for tick in ticks)
    assert any(tick.tick2line.get_visible() for tick in ticks)
    assert any(tick.label1.get_visible() for tick in ticks)
    assert any(tick.label2.get_visible() for tick in ticks)


def test_frame_tick_width_helpers_apply_to_multiple_axes():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()

    assert parse_frame_tick_widths("2") == (2.0, 2.0, 1.2)
    assert np.allclose(parse_frame_tick_widths("1.5 3"), (1.5, 3.0, 2.1))

    apply_frame_and_tick_widths([ax, ax2], frame_width=1.5, major_width=2.0, minor_width=1.0)

    assert ax.spines["left"].get_linewidth() == 1.5
    assert ax2.spines["right"].get_linewidth() == 1.5
    assert ax.xaxis._major_tick_kw["width"] == 2.0
    assert ax2.yaxis._minor_tick_kw["width"] == 1.0


def test_legend_position_menu_updates_position_and_toggle_callbacks():
    fig, ax = plt.subplots()
    ax.plot([1, 2], [3, 4], label="cycle")
    ax.legend()
    position = {"xy": (0.0, 0.0)}
    toggles = []
    applied = []
    states = []
    inputs = iter(["t", "p", "w", "x", "2.5", "q", "q", "q"])

    def _sanitize(xy):
        if xy is None or len(xy) != 2:
            return None
        x_val, y_val = float(xy[0]), float(xy[1])
        if abs(x_val) > 10 or abs(y_val) > 10:
            return None
        return (x_val, y_val)

    run_legend_position_menu(
        fig=fig,
        get_legend=ax.get_legend,
        get_position=lambda: position["xy"],
        set_position=lambda xy: position.__setitem__("xy", xy),
        sanitize_offset=_sanitize,
        toggle_legend=lambda: toggles.append(True),
        apply_position=lambda: applied.append(position["xy"]),
        push_state=states.append,
        safe_input=lambda _prompt: next(inputs),
        colorize_menu=lambda text: text,
        colorize_prompt=lambda text: text,
    )

    assert toggles == [True]
    assert states == ["legend-toggle", "legend-position", "legend-position"]
    assert applied == [(0.0, 0.1), (2.5, 0.1)]
    assert position["xy"] == (2.5, 0.1)


def test_font_helpers_apply_family_and_size_to_common_artists():
    fig, ax = plt.subplots()
    ax.plot([1, 2], [3, 4], label="cycle")
    ax.set_xlabel("Capacity")
    ax.set_ylabel("Voltage")
    ax.set_title("Title")
    ax.text(0.5, 0.5, "note")
    legend = ax.legend()

    set_font_family_defaults("DejaVu Sans", sans_serif_stack=True)
    set_font_size_default(13)
    artists = axis_text_artists(ax, include_title=True, include_axes_texts=True)
    artists.extend(legend_text_artists(legend))
    apply_font_family_to_artists(artists, "DejaVu Sans")
    apply_font_size_to_artists(artists, 13)

    assert plt.rcParams["font.sans-serif"][0] == "DejaVu Sans"
    assert plt.rcParams["font.size"] == 13
    assert ax.xaxis.label.get_fontfamily()[0] == "DejaVu Sans"
    assert ax.title.get_fontsize() == 13
    assert legend.get_texts()[0].get_fontsize() == 13


def test_colorize_prompt_preserves_command_text():
    out = colorize_prompt("Choose (s=size, f=family, q=return): ")

    assert "\033[96ms\033[0m=size" in out
    assert "\033[96mf\033[0m=family" in out
    assert "\033[96mq\033[0m=return" in out


def test_colorize_inline_commands_highlights_common_keys():
    out = colorize_inline_commands("ly : left axis\nq: back\n'use all'")

    assert "\033[96mly\033[0m :" in out
    assert "\033[96mq\033[0m:" in out
    assert "'\033[96muse all\033[0m'" in out


def test_single_key_inline_colorizer_keeps_operando_style():
    out = colorize_single_key_inline_commands("t=toggle, a=alpha, q: back")

    assert "\033[96mt\033[0m=toggle" in out
    assert "\033[96ma\033[0m=alpha" in out
    assert "\033[96mq\033[0m: back" in out


def test_menu_rendering_appends_overwrite_shortcuts_and_columns(capsys):
    class FigureState:
        _last_session_save_path = "last.pkl"
        _last_style_export_path = "last.bpsg"
        _last_figure_export_path = "last.svg"

    options = ["q: quit"]
    append_last_action_shortcuts(options, FigureState())
    assert options[-4:] == [
        "os: overwrite session",
        "ops: overwrite style",
        "opsg: overwrite style+geom",
        "oe: overwrite figure",
    ]

    print_menu_columns(
        title="Demo Menu",
        columns=[("(Options)", options)],
        min_widths=(12,),
    )
    out = capsys.readouterr().out
    assert "Demo Menu" in out
    assert "\033[96mos\033[0m: overwrite session" in out
    assert colorize_menu_item("p: print") == "\033[96mp\033[0m: print"


def test_format_file_timestamp_handles_existing_and_missing_files(tmp_path):
    source = tmp_path / "data.txt"
    source.write_text("example\n")

    assert len(format_file_timestamp(str(source))) == len("2026-06-03 13:23")
    assert format_file_timestamp(str(tmp_path / "missing.txt")) == ""


def test_savgol_smooth_preserves_shape_and_small_inputs():
    y = np.array([1.0, 2.0, 10.0, 2.0, 1.0])
    smoothed = savgol_smooth(y, window=5, poly=2)

    assert smoothed.shape == y.shape
    assert not np.shares_memory(smoothed, y)
    assert savgol_smooth(np.array([1.0, 2.0]), window=5, poly=2).tolist() == [1.0, 2.0]


def test_title_offset_helpers_capture_restore_reset():
    fig, ax = plt.subplots()
    ax._top_xlabel_manual_offset_y_pts = 2.5
    ax._right_ylabel_manual_offset_x_pts = -1.25

    captured = capture_title_offsets(ax)
    assert captured["top_y"] == 2.5
    assert captured["right_x"] == -1.25

    reset_title_offsets(ax)
    assert ax._top_xlabel_manual_offset_y_pts == 0.0
    assert ax._right_ylabel_manual_offset_x_pts == 0.0

    restore_title_offsets(ax, {"top": 4.0, "right": 3.0})
    assert ax._top_xlabel_manual_offset_y_pts == 4.0
    assert ax._right_ylabel_manual_offset_x_pts == 3.0


def test_source_helpers_preserve_unique_absolute_paths(tmp_path):
    source = tmp_path / "data.csv"
    source.write_text("x,y\n1,2\n")

    paths = normalize_source_paths([source, str(source), tmp_path / "missing.csv"], require_file=True)

    assert paths == [str(source.resolve())]
    assert file_data_source_paths([{"filepath": source}, {"filepath": source}]) == [str(source.resolve())]


def test_dqdv_2d_tick_helpers_limit_labels_and_format_voltage():
    idx = _dqdv_2d_row_tick_indices(100, max_ticks=10)
    assert len(idx) <= 10
    assert idx[0] == 0
    assert idx[-1] == 99

    fmt = _dqdv_2d_voltage_tick_formatter(2.0, 4.0, 2.0)
    assert fmt(0.0) == "4"
    assert fmt(2.0) == "2"
    assert fmt(4.0) == "4"


def test_flat_tick_state_helpers_match_xy_defaults():
    state = default_flat_tick_state()

    assert state["b_ticks"] is True
    assert state["b_labels"] is True
    assert state["t_ticks"] is False
    assert state["r_labels"] is False
    assert state["bx"] is True
    assert state["tx"] is False

    restored = legacy_tick_state_to_flat({"tx": True, "mly": True})
    assert restored["t_ticks"] is True
    assert restored["t_labels"] is True
    assert restored["mtx"] is False
    assert restored["mly"] is True


def test_wasd_to_tick_state_preserves_mode_defaults():
    wasd = {
        "bottom": {"ticks": False, "labels": True, "minor": True},
        "right": {"ticks": True, "labels": False},
    }
    state = wasd_to_tick_state(
        wasd,
        tick_defaults={"top": False, "bottom": True, "left": True, "right": True},
        label_defaults={"top": False, "bottom": True, "left": True, "right": True},
    )

    assert state["b_ticks"] is False
    assert state["b_labels"] is True
    assert state["mbx"] is True
    assert state["bx"] is False
    assert state["r_ticks"] is True
    assert state["r_labels"] is False
    assert state["ry"] is False


def test_sync_tick_state_from_wasd_updates_existing_mapping():
    tick_state = {"bx": True, "old_key": "kept"}
    sync_tick_state_from_wasd(
        tick_state,
        {"left": {"ticks": False, "labels": False, "minor": True}},
        tick_defaults={"top": False, "bottom": True, "left": True, "right": False},
        label_defaults={"top": False, "bottom": True, "left": True, "right": False},
    )

    assert tick_state["old_key"] == "kept"
    assert tick_state["l_ticks"] is False
    assert tick_state["l_labels"] is False
    assert tick_state["mly"] is True
    assert tick_state["ly"] is False


def test_apply_flat_tick_params_sets_major_and_minor_visibility():
    fig, ax = plt.subplots()
    state = default_flat_tick_state()
    state.update({"t_ticks": True, "t_labels": True, "mtx": True, "mry": True})

    apply_flat_tick_params(ax, state)
    fig.canvas.draw()

    xtick = ax.xaxis.get_major_ticks()[0]
    assert xtick.tick2line.get_visible() is True
    assert xtick.label2.get_visible() is True
    assert ax.xaxis.get_minor_locator().__class__.__name__ == "AutoMinorLocator"


def test_apply_wasd_helpers_keep_mode_specific_y_ownership():
    fig, ax = plt.subplots()
    wasd = {
        "top": {"spine": False, "ticks": True, "minor": False, "labels": True},
        "left": {"spine": True, "ticks": True, "minor": True, "labels": True},
        "right": {"spine": True, "ticks": True, "minor": True, "labels": True},
    }

    apply_wasd_spines(ax, wasd)
    apply_wasd_tick_params(ax, wasd, y_sides=("left",), y_mode="left")
    fig.canvas.draw()

    assert ax.spines["top"].get_visible() is False
    ytick = ax.yaxis.get_major_ticks()[0]
    assert ytick.tick1line.get_visible() is True
    assert ytick.label1.get_visible() is True
    assert ytick.tick2line.get_visible() is False
    assert ytick.label2.get_visible() is False


def test_apply_changed_side_title_positions_preserves_none_vs_empty_set():
    calls = []

    apply_changed_side_title_positions(
        None,
        bottom=lambda: calls.append("bottom"),
        top=lambda: calls.append("top"),
        left=lambda: calls.append("left"),
        right=lambda: calls.append("right"),
    )
    assert calls == ["bottom", "top", "left", "right"]

    calls.clear()
    apply_changed_side_title_positions(
        set(),
        bottom=lambda: calls.append("bottom"),
        top=lambda: calls.append("top"),
        left=lambda: calls.append("left"),
        right=lambda: calls.append("right"),
    )
    assert calls == []


def test_apply_changed_side_title_positions_runs_only_requested_callbacks():
    calls = []

    applied = apply_changed_side_title_positions(
        {"left", "right"},
        bottom=lambda: calls.append("bottom"),
        top=lambda: calls.append("top"),
        left=lambda: calls.append("left"),
        right=lambda: calls.append("right"),
    )

    assert applied == {"left", "right"}
    assert calls == ["left", "right"]


def test_keep_yaxis_label_on_side_does_not_change_tick_visibility():
    fig, ax = plt.subplots()
    ax.yaxis.tick_right()
    ax.tick_params(axis="y", right=False, labelright=False)
    ax.set_ylabel("EC current")
    fig.canvas.draw()

    keep_yaxis_label_on_side(ax, "right", visible=True)
    fig.canvas.draw()

    tick = ax.yaxis.get_major_ticks()[0]
    assert ax.yaxis.get_label_position() == "right"
    assert ax.yaxis.label.get_visible() is True
    assert tick.tick2line.get_visible() is False
    assert tick.label2.get_visible() is False


def test_run_spine_tick_menu_dispatches_standard_toggle():
    fig, ax = plt.subplots()
    wasd = {
        "top": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "right": {"spine": False, "ticks": False, "minor": False, "labels": False, "title": False},
    }
    calls = []
    inputs = iter(["s2", "q"])

    def fake_input(_prompt):
        return next(inputs)

    def sync_tick_state():
        calls.append(("sync", wasd["bottom"]["ticks"]))

    def apply_wasd(changed_sides):
        calls.append(("apply", changed_sides))

    run_spine_tick_menu(
        fig=fig,
        wasd=wasd,
        safe_input=fake_input,
        colorize_prompt=lambda text: text,
        colorize_inline_commands=lambda text: text,
        push_state=lambda label: calls.append(("push", label)),
        sync_tick_state=sync_tick_state,
        apply_wasd=apply_wasd,
        draw=lambda: calls.append(("draw", None)),
        axis_map={"x": ax.xaxis, "y": ax.yaxis},
        on_quit=lambda: calls.append(("quit", None)),
    )

    assert wasd["bottom"]["ticks"] is False
    assert ("push", "wasd-toggle") in calls
    assert ("sync", False) in calls
    assert ("apply", set()) in calls
    assert ("quit", None) in calls


def test_run_spine_tick_menu_accepts_legacy_tick_aliases():
    fig, _ax = plt.subplots()
    wasd = {
        "top": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "right": {"spine": False, "ticks": False, "minor": False, "labels": False, "title": False},
    }
    calls = []
    inputs = iter(["btcs bx mbx rt", "q"])

    run_spine_tick_menu(
        fig=fig,
        wasd=wasd,
        safe_input=lambda _prompt: next(inputs),
        colorize_prompt=lambda text: text,
        colorize_inline_commands=lambda text: text,
        push_state=lambda label: calls.append(("push", label)),
        sync_tick_state=lambda: calls.append(("sync", None)),
        apply_wasd=lambda changed_sides: calls.append(("apply", changed_sides)),
        draw=lambda: calls.append(("draw", None)),
        axis_map={"x": _ax.xaxis, "y": _ax.yaxis},
    )

    assert wasd["bottom"]["ticks"] is False
    assert wasd["bottom"]["labels"] is False
    assert wasd["bottom"]["minor"] is True
    assert wasd["right"]["title"] is True
    assert ("apply", {"bottom", "right"}) in calls


def test_run_spine_tick_menu_can_alias_unavailable_side_commands():
    fig, ax = plt.subplots()
    wasd = {
        "top": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "right": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
    }
    calls = []
    inputs = iter(["a4 a5 llb lt", "q"])

    run_spine_tick_menu(
        fig=fig,
        wasd=wasd,
        safe_input=lambda _prompt: next(inputs),
        colorize_prompt=lambda text: text,
        colorize_inline_commands=lambda text: text,
        push_state=lambda label: calls.append(("push", label)),
        sync_tick_state=lambda: calls.append(("sync", None)),
        apply_wasd=lambda changed_sides: calls.append(("apply", changed_sides)),
        draw=lambda: calls.append(("draw", None)),
        axis_map={"x": ax.xaxis, "y": ax.yaxis},
        side_aliases={"left": "right"},
    )

    assert wasd["left"]["labels"] is True
    assert wasd["left"]["title"] is True
    assert wasd["right"]["labels"] is True
    assert wasd["right"]["title"] is True
    assert ("apply", {"right"}) in calls


def test_run_spine_tick_menu_side_alias_keeps_non_title_toggles_from_repositioning():
    fig, ax = plt.subplots()
    wasd = {
        "top": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "right": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
    }
    calls = []
    inputs = iter(["a1 a2 a3 ll ltcs mly", "q"])

    run_spine_tick_menu(
        fig=fig,
        wasd=wasd,
        safe_input=lambda _prompt: next(inputs),
        colorize_prompt=lambda text: text,
        colorize_inline_commands=lambda text: text,
        push_state=lambda label: calls.append(("push", label)),
        sync_tick_state=lambda: calls.append(("sync", None)),
        apply_wasd=lambda changed_sides: calls.append(("apply", changed_sides)),
        draw=lambda: calls.append(("draw", None)),
        axis_map={"x": ax.xaxis, "y": ax.yaxis},
        side_aliases={"left": "right"},
    )

    assert wasd["left"]["spine"] is True
    assert wasd["left"]["ticks"] is True
    assert wasd["left"]["minor"] is False
    assert wasd["right"]["spine"] is True
    assert wasd["right"]["ticks"] is True
    assert wasd["right"]["minor"] is False
    assert ("apply", set()) in calls


def test_run_spine_tick_menu_minor_toggle_does_not_reposition_titles():
    fig, ax = plt.subplots()
    wasd = {
        "top": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "right": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
    }
    calls = []
    inputs = iter(["a3 mry", "q"])

    run_spine_tick_menu(
        fig=fig,
        wasd=wasd,
        safe_input=lambda _prompt: next(inputs),
        colorize_prompt=lambda text: text,
        colorize_inline_commands=lambda text: text,
        push_state=lambda label: calls.append(("push", label)),
        sync_tick_state=lambda: calls.append(("sync", None)),
        apply_wasd=lambda changed_sides: calls.append(("apply", changed_sides)),
        draw=lambda: calls.append(("draw", None)),
        axis_map={"x": ax.xaxis, "y": ax.yaxis},
    )

    assert wasd["left"]["minor"] is True
    assert wasd["right"]["minor"] is True
    assert ("apply", set()) in calls


def test_run_spine_tick_menu_changed_side_contract_for_all_toggle_commands():
    command_expectations = {
        **{f"{side}{prop}": set() for side in "wasd" for prop in "123"},
        **{
            "w4": {"top"}, "w5": {"top"},
            "a4": {"left"}, "a5": {"left"},
            "s4": {"bottom"}, "s5": {"bottom"},
            "d4": {"right"}, "d5": {"right"},
        },
        "bl": set(), "tl": set(), "ll": set(), "rl": set(),
        "btcs": set(), "ttcs": set(), "tics": set(), "ltcs": set(), "rtcs": set(),
        "mbx": set(), "mtx": set(), "mly": set(), "mry": set(),
        "blb": {"bottom"}, "tlb": {"top"}, "llb": {"left"}, "rlb": {"right"},
        "bt": {"bottom"}, "tt": {"top"}, "lt": {"left"}, "rt": {"right"},
        "bx": {"bottom"}, "tx": {"top"}, "ly": {"left"}, "ry": {"right"},
    }

    for command, expected_changed_sides in command_expectations.items():
        fig, ax = plt.subplots()
        wasd = {
            "top": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
            "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
            "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
            "right": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
        }
        calls = []
        inputs = iter([command, "q"])

        run_spine_tick_menu(
            fig=fig,
            wasd=wasd,
            safe_input=lambda _prompt: next(inputs),
            colorize_prompt=lambda text: text,
            colorize_inline_commands=lambda text: text,
            push_state=lambda _label: None,
            sync_tick_state=lambda: None,
            apply_wasd=lambda changed_sides: calls.append(changed_sides),
            draw=lambda: None,
            axis_map={"x": ax.xaxis, "y": ax.yaxis},
        )

        assert calls == [expected_changed_sides], command
        plt.close(fig)


def test_run_spine_tick_menu_non_toggle_commands_do_not_apply_wasd():
    commands = [
        ["list", "q"],
        ["p", "q"],
        ["n", "q", "q"],
        ["m", "q", "q"],
    ]

    for inputs_list in commands:
        fig, ax = plt.subplots()
        wasd = {
            "top": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
            "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
            "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
            "right": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
        }
        apply_calls = []
        inputs = iter(inputs_list)

        run_spine_tick_menu(
            fig=fig,
            wasd=wasd,
            safe_input=lambda _prompt: next(inputs),
            colorize_prompt=lambda text: text,
            colorize_inline_commands=lambda text: text,
            push_state=lambda _label: None,
            sync_tick_state=lambda: None,
            apply_wasd=lambda changed_sides: apply_calls.append(changed_sides),
            draw=lambda: None,
            axis_map={"x": ax.xaxis, "y": ax.yaxis},
        )

        assert apply_calls == [], inputs_list
        plt.close(fig)


def test_run_spine_tick_menu_supports_major_and_minor_interval_submenus():
    fig, ax = plt.subplots()
    wasd = {
        "top": {"spine": True, "ticks": False, "minor": False, "labels": False, "title": False},
        "bottom": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "left": {"spine": True, "ticks": True, "minor": False, "labels": True, "title": True},
        "right": {"spine": False, "ticks": False, "minor": False, "labels": False, "title": False},
    }
    inputs = iter(["n", "x 0.5 y 2", "q", "m", "x 4 y 0", "q", "q"])

    run_spine_tick_menu(
        fig=fig,
        wasd=wasd,
        safe_input=lambda _prompt: next(inputs),
        colorize_prompt=lambda text: text,
        colorize_inline_commands=lambda text: text,
        push_state=lambda _label: None,
        sync_tick_state=lambda: None,
        apply_wasd=lambda _changed_sides: None,
        draw=lambda: None,
        axis_map={"x": ax.xaxis, "y": ax.yaxis},
    )

    assert isinstance(ax.xaxis.get_major_locator(), MultipleLocator)
    assert ax.xaxis.get_major_locator()._edge.step == 0.5
    assert isinstance(ax.yaxis.get_major_locator(), MultipleLocator)
    assert ax.yaxis.get_major_locator()._edge.step == 2.0
    assert ax.xaxis.get_minor_locator().__class__.__name__ == "AutoMinorLocator"
    assert isinstance(ax.yaxis.get_minor_locator(), NullLocator)


def test_run_font_menu_dispatches_family_and_size_callbacks():
    inputs = iter(["f", "2", "s", "11.5", "q"])
    calls = []

    run_font_menu(
        safe_input=lambda _prompt: next(inputs),
        colorize_menu=lambda text: text,
        colorize_prompt=lambda text: text,
        get_current_family=lambda: "Arial",
        get_current_size=lambda: 10,
        apply_family=lambda family: calls.append(("family", family)),
        apply_size=lambda size: calls.append(("size", size)),
        fonts=["Arial", "Helvetica"],
    )

    assert calls == [("family", "Helvetica"), ("size", 11.5)]


def test_run_dispatch_menu_routes_choices_to_mode_handler():
    inputs = iter(["ly", "bad", "q"])
    calls = []

    run_dispatch_menu(
        prompt="Y target: ",
        options={"ly": "left axis", "ry": "right axis"},
        handle_choice=lambda choice: calls.append(choice),
        safe_input=lambda _prompt: next(inputs),
        colorize_menu=lambda text: text,
        colorize_prompt=lambda text: text,
    )

    assert calls == ["ly", "bad"]


def test_run_axis_limit_menu_handles_pair_upper_lower_and_auto():
    limits = [0.0, 10.0]
    inputs = iter(["2 8", "w", "9", "q", "s", "1", "q", "a", "q"])
    calls = []

    def set_limits(low, high):
        limits[:] = [low, high]
        calls.append(("set", low, high))

    run_axis_limit_menu(
        axis_name="X",
        prompt_name="X",
        get_limits=lambda: (limits[0], limits[1]),
        set_limits=set_limits,
        auto_limits=lambda: set_limits(0.0, 10.0),
        push_state=lambda label: calls.append(("push", label)),
        state_label="x-range",
        draw=lambda: calls.append(("draw", None)),
        safe_input=lambda _prompt: next(inputs),
        colorize_menu=lambda text: text,
        colorize_prompt=lambda text: text,
    )

    assert ("push", "x-range") in calls
    assert ("push", "x-range-auto") in calls
    assert limits == [0.0, 10.0]

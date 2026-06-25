"""Electrochemistry (GC capacity-vs-voltage) session round-trip tests."""

import builtins
import json

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.ticker import AutoMinorLocator, MultipleLocator

from batplot import session as S
from conftest import assert_allclose, loaded
from batplot.plot_modes.electrochem import actions as EA
from batplot.plot_modes.electrochem import colors as ECY
from batplot.plot_modes.electrochem import interactive as E
from batplot.plot_modes.electrochem import labels as EL
from batplot.plot_modes.electrochem import legend as EG
from batplot.plot_modes.electrochem import legend_order as ELO
from batplot.plot_modes.electrochem import line_style as ELS
from batplot.plot_modes.electrochem import spine_colors as ESC
from batplot.plot_modes.electrochem.menu import print_electrochem_menu


def _build_ec_figure():
    fig, ax = plt.subplots()
    cap = np.linspace(0.0, 150.0, 40)
    volt = np.linspace(3.0, 4.2, 40)
    charge, = ax.plot(cap, volt, color="#ff0000", lw=2.0, label="cycle 1 charge")
    discharge, = ax.plot(cap[::-1], volt, color="#0000ff", lw=1.5,
                         label="cycle 1 discharge")
    ax.set_xlabel("Capacity (mAh/g)")
    ax.set_ylabel("Voltage (V)")
    ax.set_xlim(0.0, 150.0)
    ax.set_ylim(3.0, 4.2)
    cycle_lines = {1: {"charge": charge, "discharge": discharge}}
    return fig, ax, cycle_lines, cap, volt


def test_dump_load_preserves_axes_and_data(session_path):
    fig, ax, cycle_lines, cap, volt = _build_ec_figure()
    p = session_path("ec.pkl")
    S.dump_ec_session(p, fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)

    result = S.load_ec_session(p)
    assert result is not None, "load_ec_session returned None"
    fig2, ax2, _meta = result

    assert_allclose(ax2.get_xlim(), (0.0, 150.0))
    assert_allclose(ax2.get_ylim(), (3.0, 4.2))
    assert ax2.get_xlabel() == "Capacity (mAh/g)"
    assert ax2.get_ylabel() == "Voltage (V)"
    # At least the two curves we created must be present.
    assert len(ax2.lines) >= 2


def test_dump_load_preserves_curve_data(session_path):
    fig, ax, cycle_lines, cap, volt = _build_ec_figure()
    p = session_path("ec_data.pkl")
    S.dump_ec_session(p, fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)

    fig2, ax2, _meta = loaded(S.load_ec_session(p))
    # Find a restored line whose x-extent matches the charge curve.
    xmaxes = [np.asarray(ln.get_xdata(), float).max() for ln in ax2.lines
              if np.asarray(ln.get_xdata(), float).size]
    assert any(abs(xm - 150.0) < 1e-6 for xm in xmaxes), (
        "charge curve capacity data not restored"
    )


def test_dump_load_preserves_tick_lengths(session_path):
    fig, ax, cycle_lines, cap, volt = _build_ec_figure()
    ax.xaxis.set_minor_locator(AutoMinorLocator())
    ax.tick_params(axis="both", which="major", length=9.0)
    ax.tick_params(axis="both", which="minor", length=6.3)
    fig._tick_lengths = {"major": 9.0, "minor": 6.3}
    p = session_path("ec_tick_lengths.pkl")

    S.dump_ec_session(p, fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)
    fig2, ax2, _meta = loaded(S.load_ec_session(p))
    fig2.canvas.draw()

    assert getattr(fig2, "_tick_lengths", {}) == {"major": 9.0, "minor": 6.3}
    assert ax2.xaxis.get_major_ticks()[0].tick1line.get_markersize() == 9.0


def test_dump_load_preserves_marker_styles(session_path):
    fig, ax, cycle_lines, cap, volt = _build_ec_figure()
    charge = cycle_lines[1]["charge"]
    discharge = cycle_lines[1]["discharge"]
    charge.set_marker("o")
    charge.set_markersize(6.5)
    charge.set_markerfacecolor("none")
    charge.set_markeredgecolor("#123456")
    discharge.set_marker("s")
    discharge.set_markersize(4.0)
    discharge.set_markerfacecolor("#abcdef")
    discharge.set_markeredgecolor("#654321")
    p = session_path("ec_marker_styles.pkl")

    S.dump_ec_session(p, fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)
    fig2, ax2, _meta = loaded(S.load_ec_session(p))

    restored_charge = ax2.lines[0]
    restored_discharge = ax2.lines[1]
    assert restored_charge.get_marker() == "o"
    assert restored_charge.get_markersize() == 6.5
    assert restored_charge.get_markeredgecolor() == "#123456"
    assert restored_discharge.get_marker() == "s"
    assert restored_discharge.get_markersize() == 4.0
    assert restored_discharge.get_markerfacecolor() == "#abcdef"


def test_dump_load_preserves_dqdv_smooth_and_ions_original_x(session_path):
    fig, ax, cycle_lines, cap, volt = _build_ec_figure()
    c_th = 150.0
    for parts in cycle_lines.values():
        for ln in parts.values():
            ln._orig_xdata_gc = np.asarray(ln.get_xdata(), float).copy()
            ln.set_xdata(np.asarray(ln.get_xdata(), float) / c_th)
    fig._xaxis_mode = "ions"
    fig._xaxis_c_theoretical = c_th
    fig._xaxis_swapped = False
    fig._dqdv_smooth_settings = {"method": "savgol", "window": 7, "poly": 2}
    p = session_path("ec_ions_smooth.pkl")

    S.dump_ec_session(p, fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)
    fig2, ax2, _meta = loaded(S.load_ec_session(p))

    restored_x = np.asarray(ax2.lines[0].get_xdata(), float)
    assert_allclose(restored_x.max(), cap.max() / c_th)
    assert getattr(fig2, "_dqdv_smooth_settings") == {"method": "savgol", "window": 7, "poly": 2}


def test_dqdv_2d_snapshot_preserves_interactive_style_state():
    fig, ax = plt.subplots()
    z = np.arange(20, dtype=float).reshape(4, 5)
    im = ax.imshow(z, aspect="auto", origin="lower", extent=(0.0, 2.0, -0.5, 3.5))
    cbar = fig.colorbar(im, ax=ax)
    ax.set_xlabel("Custom voltage")
    ax.set_ylabel("Custom row")
    ax.xaxis.labelpad = 13.0
    ax.spines["left"].set_linewidth(2.5)
    ax.spines["left"].set_edgecolor("#123456")
    ax.tick_params(axis="both", which="major", width=2.0, length=9.0, direction="in")
    ax.xaxis.set_major_locator(MultipleLocator(0.25))
    fig._tick_direction = "in"
    cbar.ax._colorbar_label = "Custom dQ/dV"
    fig._colorbar_label_mode = "normal"

    snap = E.build_dqdv_2d_snapshot(fig, ax, im, 2.0, 3.0, ["a", "b", "c", "d"], "dQ/dV", cbar)
    assert snap is not None
    restored = E.restore_dqdv_2d_companion_figure(snap)
    assert restored is not None
    fig2, ax2, im2, cbar2 = restored

    assert ax2.get_xlabel() == "Custom voltage"
    assert ax2.get_ylabel() == "Custom row"
    assert ax2.xaxis.labelpad == 13.0
    assert ax2.spines["left"].get_linewidth() == 2.5
    assert mcolors.to_hex(ax2.spines["left"].get_edgecolor()) == "#123456"
    assert getattr(fig2, "_tick_direction") == "in"
    assert type(ax2.xaxis.get_major_locator()).__name__ == "MultipleLocator"
    assert cbar2.ax._colorbar_label == "Custom dQ/dV"
    assert getattr(fig2, "_colorbar_label_mode") == "normal"


def test_style_snapshot_preserves_tick_lengths_for_import():
    fig, ax, cycle_lines, cap, volt = _build_ec_figure()
    fig._tick_lengths = {"major": 8.0, "minor": 5.6}
    fig._ec_display_mode = "discharge"

    cfg = E._get_style_snapshot(fig, ax, cycle_lines, tick_state={})

    assert cfg["ticks"]["lengths"] == {"major": 8.0, "minor": 5.6}
    assert cfg["display_mode"] == "discharge"


def test_style_import_applies_tick_lengths(session_path, monkeypatch):
    fig, ax, cycle_lines, cap, volt = _build_ec_figure()
    cfg = E._get_style_snapshot(fig, ax, cycle_lines, tick_state={})
    cfg["ticks"]["lengths"] = {"major": 7.0, "minor": 4.9}
    cfg["display_mode"] = "charge"
    cfg["xaxis_dual"] = {
        "mode": "dual",
        "c_theoretical": 150.0,
        "swapped": False,
        "top_axis": {
            "xlabel": "Custom top ions",
            "xlabel_visible": True,
            "label_color": "#123456",
            "spine_visible": True,
            "spine_color": "#654321",
        },
    }
    cfg["kind"] = "ec_style_geom"
    cfg["axes_geometry"] = {
        "xlabel": "Legacy capacity",
        "ylabel": "Legacy voltage",
        "xlim": [5.0, 55.0],
        "ylim": [3.1, 4.1],
    }
    cfg.pop("geometry", None)
    style_path = session_path("ec_style.bpsg")
    with open(style_path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh)

    monkeypatch.setattr(EA, "choose_style_file", lambda *_args, **_kwargs: style_path)
    monkeypatch.setattr(builtins, "input", lambda *_args, **_kwargs: "")
    tick_state = {
        "b_ticks": True,
        "b_labels": True,
        "t_ticks": False,
        "t_labels": False,
        "l_ticks": True,
        "l_labels": True,
        "r_ticks": False,
        "r_labels": False,
        "mbx": False,
        "mtx": False,
        "mly": False,
        "mry": False,
    }
    ctx = EA.ElectrochemActionContext(
        fig=fig,
        ax=ax,
        cycle_lines=cycle_lines,
        file_data=[],
        tick_state=tick_state,
        source_paths=[style_path],
        all_cycles=[1],
        is_dqdv=False,
        is_multi_file=False,
        menu_title="EC",
        canvas_mode=True,
        print_menu=lambda *_args, **_kwargs: None,
        push_state=lambda _note="": None,
        restore_state=lambda: None,
        format_file_timestamp=lambda _path: "",
        savefig_plot_window=lambda *_args, **_kwargs: None,
        rebuild_legend=lambda *_args, **_kwargs: None,
        get_style_snapshot=E._get_style_snapshot,
        get_geometry_snapshot=E._get_geometry_snapshot,
        print_style_snapshot=E._print_style_snapshot,
        export_style_dialog=lambda *_args, **_kwargs: None,
        apply_font_family=E._apply_font_family,
        apply_font_size=E._apply_font_size,
        apply_spine_color=lambda *_args, **_kwargs: None,
        iter_cycle_lines=E._iter_cycle_lines,
        apply_cycle_styles=E._apply_cycle_styles,
        apply_stored_smooth_settings=E._apply_stored_smooth_settings,
        sanitize_legend_offset=lambda _fig, xy: xy,
        apply_file_display_names_to_legend=lambda *_args, **_kwargs: None,
        apply_display_mode=lambda _mode: None,
        ui_position_top_xlabel=lambda *_args, **_kwargs: None,
        ui_position_bottom_xlabel=lambda *_args, **_kwargs: None,
        ui_position_left_ylabel=lambda *_args, **_kwargs: None,
        ui_position_right_ylabel=lambda *_args, **_kwargs: None,
        apply_legend_position=lambda *_args, **_kwargs: None,
        set_legend_user_pref=lambda *_args, **_kwargs: None,
    )

    EA.handle_import_style_command(ctx)
    fig.canvas.draw()

    assert getattr(fig, "_tick_lengths", {}) == {"major": 7.0, "minor": 4.9}
    assert getattr(fig, "_ec_display_mode") == "charge"
    assert ax.xaxis.get_major_ticks()[0].tick1line.get_markersize() == 7.0
    assert ax.get_xlabel() == "Legacy capacity"
    assert ax.get_ylabel() == "Legacy voltage"
    assert_allclose(ax.get_xlim(), (5.0, 55.0))
    assert_allclose(ax.get_ylim(), (3.1, 4.1))
    secax = getattr(fig, "_xaxis_secondary", None)
    assert secax is not None
    assert secax.get_xlabel() == "Custom top ions"
    assert mcolors.to_hex(secax.xaxis.label.get_color()) == "#123456"
    assert mcolors.to_hex(secax.spines["top"].get_edgecolor()) == "#654321"


def test_ec_style_snapshot_and_import_preserve_multifile_visibility_and_line_styles(session_path, monkeypatch):
    fig, ax, cycle_lines, cap, volt = _build_ec_figure()
    charge2, = ax.plot(cap, volt + 0.1, color="#111111", lw=1.0, label="file2 charge")
    discharge2, = ax.plot(cap[::-1], volt + 0.1, color="#222222", lw=1.0, label="file2 discharge")
    file2_lines = {1: {"charge": charge2, "discharge": discharge2}}
    file_data = [
        {"filename": "file1", "display_name": "file1", "visible": True, "cycle_lines": cycle_lines},
        {"filename": "file2", "display_name": "file2", "visible": False, "cycle_lines": file2_lines},
    ]
    charge2.set_marker("o")
    charge2.set_markersize(7.0)
    charge2.set_markerfacecolor("none")
    charge2.set_markeredgecolor("#abcdef")
    charge2.set_visible(False)
    discharge2.set_visible(False)
    cfg = E._get_style_snapshot(fig, ax, cycle_lines, tick_state={}, file_data=file_data)

    assert cfg["file_visibility"] == [True, False]
    assert cfg["cycle_styles_per_file"][1]["1"]["charge"]["marker"] == "o"
    assert cfg["cycle_styles_per_file"][1]["1"]["charge"]["markersize"] == 7.0

    file_data[1]["visible"] = True
    charge2.set_visible(True)
    discharge2.set_visible(True)
    charge2.set_marker("None")
    style_path = session_path("ec_multifile_style.bps")
    with open(style_path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh)
    monkeypatch.setattr(EA, "choose_style_file", lambda *_args, **_kwargs: style_path)
    ctx = EA.ElectrochemActionContext(
        fig=fig,
        ax=ax,
        cycle_lines=cycle_lines,
        file_data=file_data,
        tick_state={},
        source_paths=[style_path],
        all_cycles=[1],
        is_dqdv=False,
        is_multi_file=True,
        menu_title="EC",
        canvas_mode=True,
        print_menu=lambda *_args, **_kwargs: None,
        push_state=lambda _note="": None,
        restore_state=lambda: None,
        format_file_timestamp=lambda _path: "",
        savefig_plot_window=lambda *_args, **_kwargs: None,
        rebuild_legend=lambda *_args, **_kwargs: None,
        get_style_snapshot=E._get_style_snapshot,
        get_geometry_snapshot=E._get_geometry_snapshot,
        print_style_snapshot=E._print_style_snapshot,
        export_style_dialog=lambda *_args, **_kwargs: None,
        apply_font_family=E._apply_font_family,
        apply_font_size=E._apply_font_size,
        apply_spine_color=lambda *_args, **_kwargs: None,
        iter_cycle_lines=E._iter_cycle_lines,
        apply_cycle_styles=E._apply_cycle_styles,
        apply_stored_smooth_settings=E._apply_stored_smooth_settings,
        sanitize_legend_offset=lambda _fig, xy: xy,
        apply_file_display_names_to_legend=lambda *_args, **_kwargs: None,
        apply_display_mode=lambda _mode: None,
        ui_position_top_xlabel=lambda *_args, **_kwargs: None,
        ui_position_bottom_xlabel=lambda *_args, **_kwargs: None,
        ui_position_left_ylabel=lambda *_args, **_kwargs: None,
        ui_position_right_ylabel=lambda *_args, **_kwargs: None,
        apply_legend_position=lambda *_args, **_kwargs: None,
        set_legend_user_pref=lambda *_args, **_kwargs: None,
    )

    EA.handle_import_style_command(ctx)

    assert file_data[1]["visible"] is False
    assert charge2.get_visible() is False
    assert discharge2.get_visible() is False
    assert charge2.get_marker() == "o"
    assert charge2.get_markersize() == 7.0


def test_ec_line_style_helper_updates_curve_widths():
    fig, ax, cycle_lines, cap, volt = _build_ec_figure()
    states = []
    inputs = iter(["c", "3.25", "q"])

    ELS.run_ec_line_style_menu(
        fig=fig,
        ax=ax,
        cycle_lines=cycle_lines,
        file_data=[],
        current_file_idx=0,
        is_multi_file=False,
        is_dqdv=False,
        print_file_list=lambda *_args, **_kwargs: None,
        iter_cycle_lines=E._iter_cycle_lines,
        rebuild_legend=lambda _ax: None,
        apply_stored_smooth_settings=lambda *_args, **_kwargs: None,
        push_state=states.append,
        safe_input=lambda _prompt: next(inputs),
        colorize_menu=lambda text: text,
        colorize_prompt=lambda text: text,
    )

    assert states == ["curve-linewidth"]
    assert getattr(fig, "_ec_curve_linewidth") == 3.25
    assert cycle_lines[1]["charge"].get_linewidth() == 3.25
    assert cycle_lines[1]["discharge"].get_linewidth() == 3.25


def test_ec_rename_helper_updates_axis_and_file_labels():
    fig, ax, cycle_lines, cap, volt = _build_ec_figure()
    file_data = [{"filename": "file1", "display_name": "file1", "cycle_lines": cycle_lines}]
    states = []
    inputs = iter(["y", "New voltage", "f", "1", "Renamed file", "q", "q"])

    updated = EL.run_ec_rename_menu(
        fig=fig,
        ax=ax,
        file_data=file_data,
        tick_state={},
        push_state=states.append,
        rebuild_legend=lambda _ax: None,
        print_file_list=lambda *_args, **_kwargs: None,
        safe_input=lambda _prompt: next(inputs),
        colorize_menu=lambda text: text,
        colorize_prompt=lambda text: text,
        ui_position_top_xlabel=lambda *_args, **_kwargs: None,
        ui_position_bottom_xlabel=lambda *_args, **_kwargs: None,
        ui_position_left_ylabel=lambda *_args, **_kwargs: None,
        ui_position_right_ylabel=lambda *_args, **_kwargs: None,
    )

    assert updated == "New voltage"
    assert states == ["rename-y", "rename-file"]
    assert ax.get_ylabel() == "New voltage"
    assert file_data[0]["display_name"] == "Renamed file"
    assert cycle_lines[1]["charge"].get_label() == "Renamed file: 1"


def test_ec_spine_color_helper_updates_spine_and_tick_colors():
    fig, ax, cycle_lines, cap, volt = _build_ec_figure()
    states = []
    inputs = iter(["a:red", "q"])

    ESC.run_ec_spine_color_menu(
        fig=fig,
        ax=ax,
        tick_state={},
        apply_spine_color=E._apply_spine_color,
        push_state=states.append,
        safe_input=lambda _prompt: next(inputs),
        colorize_menu=lambda text: text,
        colorize_prompt=lambda text: text,
    )

    assert states == ["color-spine"]
    assert mcolors.to_hex(ax.spines["left"].get_edgecolor()) == "#ff0000"
    assert ax.yaxis.label.get_color() == "red"


def test_ec_legend_order_helper_reorders_multifile_state():
    fig, ax, cycle_lines, cap, volt = _build_ec_figure()
    file_data = [
        {"filename": "file1", "display_name": "file1", "visible": True, "cycle_lines": cycle_lines},
        {"filename": "file2", "display_name": "file2", "visible": True, "cycle_lines": cycle_lines},
    ]
    states = []
    redraws = []
    inputs = iter(["2 1", "q"])

    ELO.run_ec_legend_order_menu(
        fig=fig,
        ax=ax,
        file_data=file_data,
        is_multi_file=True,
        print_file_list=lambda *_args, **_kwargs: None,
        rebuild_legend=lambda _ax: redraws.append(True),
        push_state=states.append,
        safe_input=lambda _prompt: next(inputs),
    )

    assert states == ["rearrange-legend"]
    assert getattr(fig, "_ec_legend_file_order") == [1, 0]
    assert redraws == [True]


def test_ec_cycles_menu_applies_manual_cycle_color():
    fig, ax, cycle_lines, cap, volt = _build_ec_figure()
    states = []
    menus = []
    inputs = iter(["1:green", "q"])

    ECY.run_ec_cycles_menu(
        fig=fig,
        ax=ax,
        cycle_lines=cycle_lines,
        file_data=[],
        current_file_idx=0,
        all_cycles=[1],
        is_multi_file=False,
        is_dqdv=False,
        menu_title="EC",
        canvas_mode=True,
        print_file_list=lambda *_args, **_kwargs: None,
        print_menu=lambda *_args, **_kwargs: menus.append(True),
        colorize_menu=lambda text: text,
        colorize_inline_commands=lambda text: text,
        colorize_prompt=lambda text: text,
        safe_input=lambda _prompt: next(inputs),
        push_state=states.append,
        parse_fall_cycles_tokens=E._parse_fall_cycles_tokens,
        parse_per_file_cycle_tokens=E._parse_per_file_cycle_tokens,
        parse_file_palette_tokens=E._parse_file_palette_tokens,
        parse_cycle_tokens=E._parse_cycle_tokens,
        set_visible_cycles=E._set_visible_cycles,
        apply_colors=E._apply_colors,
        apply_curve_linewidth=E._apply_curve_linewidth,
        apply_stored_smooth_settings=E._apply_stored_smooth_settings,
        apply_display_mode=lambda _mode: None,
        rebuild_legend=lambda _ax: None,
        apply_nice_ticks=lambda: None,
    )

    assert states == ["cycles/colors"]
    assert mcolors.to_hex(cycle_lines[1]["charge"].get_color()) == "#008000"
    assert mcolors.to_hex(cycle_lines[1]["discharge"].get_color()) == "#008000"


def test_ec_cycle_parser_helpers_handle_ranges_and_file_palettes():
    assert ECY._expand_cycle_number_tokens(["5", "2-4", "8,10-9"]) == [2, 3, 4, 5, 8, 9, 10]
    mode, cycles, mapping, palette, use_all = ECY._parse_cycle_tokens(["2-4", "viridis"])
    assert mode == "palette"
    assert cycles == [2, 3, 4]
    assert mapping == {}
    assert palette == "viridis"
    assert use_all is False
    assert ECY._parse_file_palette_tokens(["f1-2", "plasma"], 3) == ([0, 1], "plasma")


def test_ec_legend_helpers_rebuild_visible_labels_and_sanitize_offsets():
    fig, ax, cycle_lines, cap, volt = _build_ec_figure()
    hidden, = ax.plot(cap, volt + 0.2, label="hidden")
    hidden.set_visible(False)
    ax.legend(title="Cycles")

    EG._rebuild_legend(ax)
    legend = ax.get_legend()

    assert legend is not None
    assert legend.get_title().get_text() == "Cycles"
    assert "hidden" not in [text.get_text() for text in legend.get_texts()]
    assert EG._sanitize_legend_offset(fig, (0.1, -0.1)) == (0.1, -0.1)
    assert EG._sanitize_legend_offset(fig, (999.0, 0.0)) is None


def test_ec_menu_printer_includes_mode_and_overwrite_shortcuts(capsys):
    fig, _ax = plt.subplots()
    fig._last_session_save_path = "last.pkl"
    fig._last_style_export_path = "last.bpsg"
    fig._last_figure_export_path = "last.png"

    print_electrochem_menu(
        3,
        is_dqdv=True,
        fig=fig,
        is_multi_file=True,
        menu_title="EC menu",
    )

    out = capsys.readouterr().out
    assert "EC menu" in out
    assert "sm" in out
    assert "2d" in out
    assert "v" in out
    assert "os" in out
    assert "ops" in out
    assert "opsg" in out
    assert "oe" in out

"""Multi-file EC color menu: file picker → exact single-file menu per file."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import colors as mcolors

import batplot.plot_modes.electrochem.colors as ECY
from batplot.color_utils import clear_blank_color_input_guard


def _build_multifile_figure(n_files: int = 2, cycles=(1, 2)):
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 10)
    file_data = []
    for fi in range(n_files):
        cycle_lines = {}
        for cyc in cycles:
            chg, = ax.plot(x, x + fi + cyc, color="#000000")
            dch, = ax.plot(x, x + fi + cyc + 0.5, color="#000000")
            cycle_lines[cyc] = {"charge": chg, "discharge": dch}
        file_data.append(
            {
                "filename": f"file{fi + 1}",
                "display_name": f"file{fi + 1}",
                "visible": True,
                "cycle_lines": cycle_lines,
            }
        )
    return fig, ax, file_data


def _run_menu(fig, ax, file_data, inputs, states):
    it = iter(inputs)
    all_cycles = sorted({c for f in file_data for c in f["cycle_lines"]})
    ECY.run_ec_cycles_menu(
        fig=fig,
        ax=ax,
        cycle_lines=file_data[0]["cycle_lines"],
        file_data=file_data,
        current_file_idx=0,
        all_cycles=all_cycles,
        is_multi_file=True,
        is_dqdv=False,
        menu_title="EC",
        canvas_mode=True,
        print_file_list=lambda *_a, **_k: None,
        print_menu=lambda *_a, **_k: None,
        colorize_menu=lambda text: text,
        colorize_inline_commands=lambda text: text,
        colorize_prompt=lambda text: text,
        safe_input=lambda _prompt: next(it),
        push_state=states.append,
        parse_fall_cycles_tokens=ECY._parse_fall_cycles_tokens,
        parse_per_file_cycle_tokens=ECY._parse_per_file_cycle_tokens,
        parse_file_palette_tokens=ECY._parse_file_palette_tokens,
        parse_cycle_tokens=ECY._parse_cycle_tokens,
        set_visible_cycles=ECY._set_visible_cycles,
        apply_colors=ECY._apply_colors,
        apply_curve_linewidth=ECY._apply_curve_linewidth,
        apply_stored_smooth_settings=lambda *_a, **_k: None,
        apply_display_mode=lambda _mode: None,
        rebuild_legend=lambda _ax: None,
        apply_nice_ticks=lambda: None,
    )


def _charge_hex(file_data, fi, cyc):
    return mcolors.to_hex(file_data[fi]["cycle_lines"][cyc]["charge"].get_color())


def test_picker_edits_only_the_chosen_file():
    clear_blank_color_input_guard()
    fig, ax, file_data = _build_multifile_figure()
    states = []
    try:
        # Pick file 2, apply 1:red inside it, back to picker, quit.
        _run_menu(fig, ax, file_data, ["2", "1:red", "q", "q"], states)
        assert states == ["cycles/colors"]
        assert _charge_hex(file_data, 1, 1) == "#ff0000"
        # Same single-file semantics: 1:red selects cycle 1 within file 2.
        assert file_data[1]["cycle_lines"][1]["charge"].get_visible()
        assert not file_data[1]["cycle_lines"][2]["charge"].get_visible()
        # File 1 completely untouched (colors and visibility).
        assert _charge_hex(file_data, 0, 1) == "#000000"
        assert _charge_hex(file_data, 0, 2) == "#000000"
        assert file_data[0]["cycle_lines"][1]["charge"].get_visible()
        assert file_data[0]["cycle_lines"][2]["charge"].get_visible()
    finally:
        plt.close(fig)


def test_picker_palette_applies_within_chosen_file_only():
    clear_blank_color_input_guard()
    fig, ax, file_data = _build_multifile_figure()
    states = []
    try:
        _run_menu(fig, ax, file_data, ["1", "all viridis", "q", "q"], states)
        assert states == ["cycles/colors"]
        # Palette gradient within file 1: cycles differ.
        assert _charge_hex(file_data, 0, 1) != _charge_hex(file_data, 0, 2)
        # File 2 untouched.
        assert _charge_hex(file_data, 1, 1) == "#000000"
        assert _charge_hex(file_data, 1, 2) == "#000000"
    finally:
        plt.close(fig)


def test_picker_numeric_palette_shortcut_works():
    """Palette by number (e.g. '2' = Set2) must work inside the file menu."""
    clear_blank_color_input_guard()
    fig, ax, file_data = _build_multifile_figure()
    states = []
    try:
        _run_menu(fig, ax, file_data, ["1", "all 2", "q", "q"], states)
        assert states == ["cycles/colors"]
        assert _charge_hex(file_data, 0, 1) != "#000000"
    finally:
        plt.close(fig)


def test_picker_edit_files_one_after_another():
    clear_blank_color_input_guard()
    fig, ax, file_data = _build_multifile_figure()
    states = []
    try:
        _run_menu(
            fig, ax, file_data,
            ["1", "1:red", "q", "2", "1:blue", "q", "q"],
            states,
        )
        assert states == ["cycles/colors", "cycles/colors"]
        assert _charge_hex(file_data, 0, 1) == "#ff0000"
        assert _charge_hex(file_data, 1, 1) == "#0000ff"
    finally:
        plt.close(fig)


def test_picker_rejects_invalid_input_without_side_effects():
    clear_blank_color_input_guard()
    fig, ax, file_data = _build_multifile_figure()
    states = []
    try:
        # Old advanced syntax and out-of-range numbers are simply rejected.
        _run_menu(fig, ax, file_data, ["fall viridis", "1:red", "9", "0", "q"], states)
        assert states == []
        for fi in range(2):
            for cyc in (1, 2):
                assert _charge_hex(file_data, fi, cyc) == "#000000"
                assert file_data[fi]["cycle_lines"][cyc]["charge"].get_visible()
    finally:
        plt.close(fig)


def test_picker_accepts_fN_style_number():
    clear_blank_color_input_guard()
    fig, ax, file_data = _build_multifile_figure()
    states = []
    try:
        # Typing f2 instead of 2 also works.
        _run_menu(fig, ax, file_data, ["f2", "1:red", "q", "q"], states)
        assert _charge_hex(file_data, 1, 1) == "#ff0000"
        assert _charge_hex(file_data, 0, 1) == "#000000"
    finally:
        plt.close(fig)


def test_picker_blank_and_q_exit():
    clear_blank_color_input_guard()
    fig, ax, file_data = _build_multifile_figure()
    states = []
    try:
        _run_menu(fig, ax, file_data, [""], states)  # blank exits picker
        _run_menu(fig, ax, file_data, ["q"], states)
        assert states == []
    finally:
        plt.close(fig)


def test_picker_allows_editing_hidden_file_with_note(capsys):
    clear_blank_color_input_guard()
    fig, ax, file_data = _build_multifile_figure()
    file_data[1]["visible"] = False
    states = []
    try:
        _run_menu(fig, ax, file_data, ["2", "1:red", "q", "q"], states)
        out = capsys.readouterr().out
        assert "hidden" in out
        assert _charge_hex(file_data, 1, 1) == "#ff0000"
        assert _charge_hex(file_data, 0, 1) == "#000000"
    finally:
        plt.close(fig)


def test_picker_works_in_cv_mode():
    """CV cycle_lines store bare Line2D (no charge/discharge dict)."""
    clear_blank_color_input_guard()
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 10)
    file_data = []
    for fi in range(2):
        cycle_lines = {}
        for cyc in (1, 2):
            ln, = ax.plot(x, x + fi + cyc, color="#000000")
            cycle_lines[cyc] = ln
        file_data.append(
            {
                "filename": f"cv{fi + 1}",
                "display_name": f"cv{fi + 1}",
                "visible": True,
                "cycle_lines": cycle_lines,
            }
        )
    states = []
    try:
        _run_menu(fig, ax, file_data, ["1", "2:red", "q", "q"], states)
        assert states == ["cycles/colors"]
        assert mcolors.to_hex(file_data[0]["cycle_lines"][2].get_color()) == "#ff0000"
        assert mcolors.to_hex(file_data[1]["cycle_lines"][2].get_color()) == "#000000"
    finally:
        plt.close(fig)


def test_picker_edit_lands_in_session_lines_state():
    """p/i/s/b: session capture reads artist colors, so the edit must show up."""
    from batplot.plot_modes.electrochem.session import _ec_cycle_lines_to_lines_state

    clear_blank_color_input_guard()
    fig, ax, file_data = _build_multifile_figure()
    states = []
    try:
        _run_menu(fig, ax, file_data, ["2", "1:red", "q", "q"], states)
        state_f2 = _ec_cycle_lines_to_lines_state(file_data[1]["cycle_lines"])
        assert state_f2[1]["charge"]["style"]["color"] == "#ff0000"
        assert state_f2[1]["charge"]["style"]["visible"] is True
        state_f1 = _ec_cycle_lines_to_lines_state(file_data[0]["cycle_lines"])
        assert state_f1[1]["charge"]["style"]["color"] == "#000000"
        assert state_f1[1]["charge"]["style"]["visible"] is True
    finally:
        plt.close(fig)


def test_multifile_status_has_no_misleading_total_line(capsys):
    clear_blank_color_input_guard()
    fig, ax, file_data = _build_multifile_figure()
    states = []
    try:
        _run_menu(fig, ax, file_data, ["q"], states)
        out = capsys.readouterr().out
        assert "(of" not in out  # no "N (of M total)" sum-vs-union line
        assert "(2 visible cycles)" in out
        assert "f1:" in out and "f2:" in out
    finally:
        plt.close(fig)


def test_single_file_mode_unchanged():
    """is_multi_file=False must go straight to the classic menu (no picker)."""
    clear_blank_color_input_guard()
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 10)
    cycle_lines = {}
    for cyc in (1, 2):
        chg, = ax.plot(x, x + cyc, color="#000000")
        dch, = ax.plot(x, x + cyc + 0.5, color="#000000")
        cycle_lines[cyc] = {"charge": chg, "discharge": dch}
    states = []
    it = iter(["1:green", "q"])
    try:
        ECY.run_ec_cycles_menu(
            fig=fig,
            ax=ax,
            cycle_lines=cycle_lines,
            file_data=[],
            current_file_idx=0,
            all_cycles=[1, 2],
            is_multi_file=False,
            is_dqdv=False,
            menu_title="EC",
            canvas_mode=True,
            print_file_list=lambda *_a, **_k: None,
            print_menu=lambda *_a, **_k: None,
            colorize_menu=lambda text: text,
            colorize_inline_commands=lambda text: text,
            colorize_prompt=lambda text: text,
            safe_input=lambda _prompt: next(it),
            push_state=states.append,
            parse_fall_cycles_tokens=ECY._parse_fall_cycles_tokens,
            parse_per_file_cycle_tokens=ECY._parse_per_file_cycle_tokens,
            parse_file_palette_tokens=ECY._parse_file_palette_tokens,
            parse_cycle_tokens=ECY._parse_cycle_tokens,
            set_visible_cycles=ECY._set_visible_cycles,
            apply_colors=ECY._apply_colors,
            apply_curve_linewidth=ECY._apply_curve_linewidth,
            apply_stored_smooth_settings=lambda *_a, **_k: None,
            apply_display_mode=lambda _mode: None,
            rebuild_legend=lambda _ax: None,
            apply_nice_ticks=lambda: None,
        )
        assert states == ["cycles/colors"]
        assert mcolors.to_hex(cycle_lines[1]["charge"].get_color()) == "#008000"
        # Map input still selects: cycle 2 hidden (classic behavior).
        assert not cycle_lines[2]["charge"].get_visible()
    finally:
        plt.close(fig)

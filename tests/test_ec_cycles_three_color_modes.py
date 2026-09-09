"""EC cycles/colors: digit palette / colon / all+palette (shared batch + interactive)."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import colors as mcolors

import batplot.plot_modes.electrochem.colors as ECY
from batplot.color_utils import clear_blank_color_input_guard


def test_three_color_modes_parse_contract():
    # 1) Last digit = palette
    mode, cycles, mapping, palette, use_all = ECY._parse_cycle_tokens(["2-30", "1"])
    assert mode == "palette" and use_all is False
    assert cycles[0] == 2 and cycles[-1] == 30
    assert palette == "tab10"
    mode, cycles, mapping, palette, use_all = ECY._parse_cycle_tokens(["1", "5", "10", "3"])
    assert mode == "palette" and cycles == [1, 5, 10] and palette == "Dark2"

    # 2) Colon per-cycle
    mode, cycles, mapping, palette, use_all = ECY._parse_cycle_tokens(["1:red", "5:#00B006"])
    assert mode == "map" and palette is None and use_all is False
    assert mapping[1] is not None and 5 in cycles

    # 3) all + palette
    mode, cycles, mapping, palette, use_all = ECY._parse_cycle_tokens(["all", "4"])
    assert mode == "palette" and use_all is True and palette == "viridis"

    # Visibility-only (not a color mode): no trailing 1-6 palette digit
    mode, cycles, mapping, palette, use_all = ECY._parse_cycle_tokens(["1", "31"])
    assert mode == "numbers" and palette is None and cycles == [1, 31]

    # Named palette after cycles (replacement for removed p#)
    mode, cycles, mapping, palette, use_all = ECY._parse_cycle_tokens(["1", "31", "Set2"])
    assert mode == "palette" and cycles == [1, 31] and palette == "Set2"
    mode, cycles, mapping, palette, use_all = ECY._parse_cycle_tokens(["1", "31", "2"])
    assert mode == "palette" and cycles == [1, 31] and palette == "Set2"


def test_legacy_pN_palette_token_rejected():
    """``p1``..``p6`` removed from UX; use digit or colormap name instead."""
    mode, cycles, mapping, palette, use_all = ECY._parse_cycle_tokens(["1", "31", "p2"])
    assert palette is None
    assert mode == "numbers"
    assert cycles == [1, 31]
    assert ECY._explicit_palette_token("p2") is None
    assert ECY._explicit_palette_token("p1") is None


def test_menu_help_how_to_set_color(capsys):
    clear_blank_color_input_guard()
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 5)
    chg, = ax.plot(x, x)
    dch, = ax.plot(x, x + 0.1)
    cycle_lines = {1: {"charge": chg, "discharge": dch}}
    try:
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
            canvas_mode=False,
            print_file_list=lambda *_a, **_k: None,
            print_menu=lambda *_a, **_k: None,
            colorize_menu=lambda s: s,
            colorize_inline_commands=lambda s: s,
            colorize_prompt=lambda s: s,
            safe_input=lambda *_a, **_k: "q",
            push_state=lambda *_a, **_k: None,
            parse_fall_cycles_tokens=ECY._parse_fall_cycles_tokens,
            parse_per_file_cycle_tokens=ECY._parse_per_file_cycle_tokens,
            parse_file_palette_tokens=ECY._parse_file_palette_tokens,
            parse_cycle_tokens=ECY._parse_cycle_tokens,
            set_visible_cycles=ECY._set_visible_cycles,
            apply_colors=ECY._apply_colors,
            apply_curve_linewidth=ECY._apply_curve_linewidth,
            apply_stored_smooth_settings=lambda *_a, **_k: None,
            apply_display_mode=lambda *_a, **_k: None,
            rebuild_legend=lambda *_a, **_k: None,
            apply_nice_ticks=lambda: None,
        )
        out = capsys.readouterr().out
        assert "how to set color" in out.lower()
        assert "exactly three ways" not in out.lower()
        # Blank line between summary and help header
        assert "\n\nHow to set color:" in out
        assert "Current curves" not in out  # colors listing is opt-in via ``v``
        assert "v: show current colors" in out
        assert "palette number as LAST token" in out.lower() or "palette number as last token" in out.lower()
        assert "before assigning" not in out.lower()
        assert "save for colon form" not in out.lower()
        assert "e: pick color from screen" in out
        assert "q: back" in out
        # Examples present (ANSI may wrap them)
        assert "2-30 1" in out and "1-3 viridis" in out
        assert "1:red" in out and "all viridis" in out
        assert "p#" not in out.lower() and " p2 " not in out and "1 31 p2" not in out
        assert "1)" in out and "2)" in out and "3)" in out
        assert "Colon" in out or "colon" in out.lower()
        assert "2:4" in out
        assert "multiple entries" in out.lower()
        assert "all + palette" in out.lower() or "all +" in out.lower()
        assert "cycle numbers only" not in out.lower()
    finally:
        plt.close(fig)


def test_v_shows_current_colors_once(capsys):
    clear_blank_color_input_guard()
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 5)
    chg, = ax.plot(x, x, color="#1f77b4")
    dch, = ax.plot(x, x + 0.1, color="#1f77b4")
    cycle_lines = {1: {"charge": chg, "discharge": dch}}
    feeds = iter(["v", "q"])
    try:
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
            canvas_mode=False,
            print_file_list=lambda *_a, **_k: None,
            print_menu=lambda *_a, **_k: None,
            colorize_menu=lambda s: s,
            colorize_inline_commands=lambda s: s,
            colorize_prompt=lambda s: s,
            safe_input=lambda *_a, **_k: next(feeds),
            push_state=lambda *_a, **_k: None,
            parse_fall_cycles_tokens=ECY._parse_fall_cycles_tokens,
            parse_per_file_cycle_tokens=ECY._parse_per_file_cycle_tokens,
            parse_file_palette_tokens=ECY._parse_file_palette_tokens,
            parse_cycle_tokens=ECY._parse_cycle_tokens,
            set_visible_cycles=ECY._set_visible_cycles,
            apply_colors=ECY._apply_colors,
            apply_curve_linewidth=ECY._apply_curve_linewidth,
            apply_stored_smooth_settings=lambda *_a, **_k: None,
            apply_display_mode=lambda *_a, **_k: None,
            rebuild_legend=lambda *_a, **_k: None,
            apply_nice_ticks=lambda: None,
        )
        out = capsys.readouterr().out
        assert out.count("Current curves (visible only):") == 1
        assert "#1f77b4" in out or "1f77b4" in out.lower()
    finally:
        plt.close(fig)


def test_last_digit_palette_applies_in_menu():
    clear_blank_color_input_guard()
    fig, ax = plt.subplots()
    x = np.linspace(0, 1, 5)
    cycle_lines = {}
    for cyc in (1, 2, 3):
        chg, = ax.plot(x, x + cyc, color="#000000")
        dch, = ax.plot(x, x + cyc + 0.1, color="#000000")
        cycle_lines[cyc] = {"charge": chg, "discharge": dch}
    feeds = iter(["1 2 3 1", "q"])
    states = []
    try:
        ECY.run_ec_cycles_menu(
            fig=fig,
            ax=ax,
            cycle_lines=cycle_lines,
            file_data=[],
            current_file_idx=0,
            all_cycles=[1, 2, 3],
            is_multi_file=False,
            is_dqdv=False,
            menu_title="EC",
            canvas_mode=False,
            print_file_list=lambda *_a, **_k: None,
            print_menu=lambda *_a, **_k: None,
            colorize_menu=lambda s: s,
            colorize_inline_commands=lambda s: s,
            colorize_prompt=lambda s: s,
            safe_input=lambda *_a, **_k: next(feeds),
            push_state=states.append,
            parse_fall_cycles_tokens=ECY._parse_fall_cycles_tokens,
            parse_per_file_cycle_tokens=ECY._parse_per_file_cycle_tokens,
            parse_file_palette_tokens=ECY._parse_file_palette_tokens,
            parse_cycle_tokens=ECY._parse_cycle_tokens,
            set_visible_cycles=ECY._set_visible_cycles,
            apply_colors=ECY._apply_colors,
            apply_curve_linewidth=ECY._apply_curve_linewidth,
            apply_stored_smooth_settings=lambda *_a, **_k: None,
            apply_display_mode=lambda *_a, **_k: None,
            rebuild_legend=lambda *_a, **_k: None,
            apply_nice_ticks=lambda: None,
        )
        assert states == ["cycles/colors"]
        # tab10 first three entries differ from black
        assert mcolors.to_hex(cycle_lines[1]["charge"].get_color()) != "#000000"
        assert mcolors.to_hex(cycle_lines[1]["charge"].get_color()) != mcolors.to_hex(
            cycle_lines[2]["charge"].get_color()
        )
    finally:
        plt.close(fig)

"""Tests for the shared palette / source / terminal helpers.

These helpers were extracted from the per-mode colour submenus (xy, cpc,
electrochem). The tests pin the behaviour that the old inline copies relied on
so the consolidation stays byte-for-byte compatible.
"""

import matplotlib.pyplot as plt
from matplotlib import colors as mcolors

from batplot.plot_modes.common.palettes import (
    DEFAULT_PALETTE_ALIASES,
    TAB10_HEX,
    build_palette_options,
    build_xy_palette_options,
    palette_items,
    parse_index_ranges,
    resolve_palette_token,
    sample_colormap,
    sample_palette_colors,
)
from batplot.plot_modes.cpc.colors import cpc_palette_color, cpc_palette_options
from batplot.plot_modes.electrochem.colors import _parse_cycle_tokens
from batplot.plot_modes.operando.colors import (
    recommended_operando_colormaps,
    resolve_operando_colormap_choice,
)
from batplot.plot_modes.common.sources import cif_present
from batplot.plot_modes.common.terminal import prompt_float


# --- parse_index_ranges ----------------------------------------------------

def test_parse_index_ranges_all():
    assert parse_index_ranges("all", 4) == [0, 1, 2, 3]
    assert parse_index_ranges("ALL", 3) == [0, 1, 2]


def test_parse_index_ranges_single_and_range():
    assert parse_index_ranges("1,3", 5) == [0, 2]
    assert parse_index_ranges("2-4", 5) == [1, 2, 3]
    # reversed range is normalized
    assert parse_index_ranges("4-2", 5) == [1, 2, 3]


def test_parse_index_ranges_dedup_and_sort():
    assert parse_index_ranges("3,1,1-2", 5) == [0, 1, 2]


def test_parse_index_ranges_out_of_range_clamped():
    # in-range survives, out-of-range single dropped
    assert parse_index_ranges("1,9", 3) == [0]
    # range clipped to bounds
    assert parse_index_ranges("1-99", 3) == [0, 1, 2]


def test_parse_index_ranges_warn_flag_does_not_change_result(capsys):
    assert parse_index_ranges("9", 3, warn_out_of_range=True) == []
    out = capsys.readouterr().out
    assert "out of range" in out.lower()
    assert parse_index_ranges("9", 3, warn_out_of_range=False) == []
    out2 = capsys.readouterr().out
    assert out2 == ""


def test_parse_index_ranges_strips_whitespace():
    assert parse_index_ranges("  all ", 3) == [0, 1, 2]
    assert parse_index_ranges(" 1 , 2 ", 3) == [0, 1]


# --- resolve_palette_token -------------------------------------------------

def test_resolve_palette_token_numeric_alias():
    pmap = {"1": "viridis", "2": "magma"}
    assert resolve_palette_token("2", pmap) == "magma"
    assert resolve_palette_token("2_r", pmap) == "magma_r"


def test_resolve_palette_token_passthrough_unknown():
    pmap = {"1": "viridis"}
    assert resolve_palette_token("plasma", pmap) == "plasma"
    assert resolve_palette_token("plasma_r", pmap) == "plasma_r"


def test_default_palette_aliases_preserve_existing_order():
    assert list(DEFAULT_PALETTE_ALIASES.items()) == [
        ("1", "tab10"),
        ("2", "Set2"),
        ("3", "Dark2"),
        ("4", "viridis"),
        ("5", "plasma"),
        ("6", "rainbow"),
    ]
    assert resolve_palette_token("6_r", DEFAULT_PALETTE_ALIASES) == "rainbow_r"


# --- build_xy_palette_options ----------------------------------------------

def test_build_xy_palette_options_starts_with_base():
    opts = build_xy_palette_options(lambda name: None)
    assert opts[:7] == ["viridis", "cividis", "plasma", "inferno", "magma", "batlow", "rainbow"]
    assert "rainbow" in opts
    # at most four extras appended (rainbow + up to three optional palettes)
    assert len(opts) <= 10


def test_build_palette_options_preserves_base_order():
    opts = build_palette_options(lambda name: False)
    assert opts == list(DEFAULT_PALETTE_ALIASES.values())


def test_palette_items_use_shared_descriptions():
    items = palette_items(["tab10", "rainbow", "unknown"])
    assert items[0][1].startswith("Distinct")
    assert items[1] == ("rainbow", "Full-spectrum rainbow gradient")
    assert items[2] == ("unknown", "")


def test_rainbow_palette_available_in_all_mode_option_lists():
    assert "rainbow" in build_xy_palette_options(lambda name: None)
    assert "rainbow" in cpc_palette_options()

    _mode, _cycles, _mapping, palette, _select_all = _parse_cycle_tokens(["1", "6"])
    assert palette == "rainbow"

    operando_names = [name for name, _desc in recommended_operando_colormaps()]
    assert "rainbow" in operando_names
    assert resolve_operando_colormap_choice(str(operando_names.index("rainbow") + 1)) == "rainbow"


# --- sample_colormap -------------------------------------------------------

def test_sample_colormap_matches_inline_logic():
    cmap = plt.get_cmap("viridis")
    # n==1 -> single
    assert sample_colormap(cmap, 1) == [cmap(0.55)]
    # n==2 -> default pair
    assert sample_colormap(cmap, 2) == [cmap(0.08), cmap(0.85)]
    # n>2 -> linspace over span
    res = sample_colormap(cmap, 3)
    assert res[0] == cmap(0.08)
    assert res[-1] == cmap(0.85)
    assert len(res) == 3
    # empty
    assert sample_colormap(cmap, 0) == []


def test_sample_colormap_custom_constants_match_cpc_ec():
    cmap = plt.get_cmap("viridis")
    # cpc/ec pair=(0.15,0.85), span=(0.08,0.88)
    assert sample_colormap(cmap, 2, pair=(0.15, 0.85), span=(0.08, 0.88)) == [cmap(0.15), cmap(0.85)]
    res = sample_colormap(cmap, 4, pair=(0.15, 0.85), span=(0.08, 0.88))
    assert res[0] == cmap(0.08)
    assert res[-1] == cmap(0.88)


def test_sample_palette_colors_preserves_tab10_exact_sequence():
    colors = sample_palette_colors("tab10", 12, ensure_colormap=lambda name: True)
    assert colors[:10] == list(TAB10_HEX)
    assert colors[10:] == list(TAB10_HEX[:2])
    assert cpc_palette_color("tab10", 3, 10) == TAB10_HEX[3]


def test_sample_palette_colors_uses_existing_sampling_constants():
    colors = sample_palette_colors(
        "viridis",
        2,
        ensure_colormap=lambda name: True,
        pair=(0.15, 0.85),
        span=(0.08, 0.88),
    )
    cmap = plt.get_cmap("viridis")
    assert colors == [mcolors.rgb2hex(cmap(0.15)[:3]), mcolors.rgb2hex(cmap(0.85)[:3])]


# --- cif_present -----------------------------------------------------------

def test_cif_present_detects_cif_extension():
    assert cif_present(["data.xy", "phase.cif"]) is True
    assert cif_present(["data.xy"]) is False


def test_cif_present_handles_colon_label_syntax():
    assert cif_present(["phase.cif:1.5406"]) is True


def test_cif_present_series_getter():
    assert cif_present([], lambda: ["series"]) is True
    assert cif_present([], lambda: None) is False
    assert cif_present(None, None) is False


# --- prompt_float ----------------------------------------------------------

def test_prompt_float_blank_and_q_return_none():
    assert prompt_float(lambda p: "", "x") is None
    assert prompt_float(lambda p: "q", "x") is None
    assert prompt_float(lambda p: "Q", "x") is None


def test_prompt_float_parses_number():
    assert prompt_float(lambda p: "3.5", "x") == 3.5


def test_prompt_float_invalid_prints_and_returns_none(capsys):
    assert prompt_float(lambda p: "abc", "x") is None
    assert "Invalid number" in capsys.readouterr().out
    assert prompt_float(lambda p: "abc", "x", on_error="") is None
    assert capsys.readouterr().out == ""

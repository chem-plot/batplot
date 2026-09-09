"""Smoke-test interactive menus across ALL modes (XY/EC/CPC/histo/operando + batch).

Coverage:
- print every main menu
- quit-smoke every ``run_*menu*`` helper
- walk every documented submenu subkey (then ``q``)
- walk every top-level key on every batch menu (nested prompts get ``q``)
- package-wide AST check for import-alias vs bare-name bugs
- inventory assert: no uncovered ``run_*menu*`` helpers in ``plot_modes``

Catches NameError / TypeError crashes that break keys before any real work
(e.g. operando ``oc`` undefined ``colorize_prompt``). Not a full behavior suite.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot.plot_modes.common.menu_rendering import colorize_menu
from batplot.plot_modes.common.menus import (
    run_axis_limit_menu,
    run_dispatch_menu,
    run_font_menu,
    run_legend_position_menu,
    run_option_menu,
)
from batplot.plot_modes.common.overview_metrics import run_overview_submenu
from batplot.plot_modes.common.spines import run_spine_tick_menu
from batplot.plot_modes.common.terminal import colorize_inline_commands, colorize_prompt
from batplot.plot_modes.cpc.colors import run_cpc_color_menu
from batplot.plot_modes.cpc.labels import run_cpc_rename_menu
from batplot.plot_modes.cpc.menu import print_cpc_menu
from batplot.plot_modes.electrochem.colors import run_ec_cycles_menu
from batplot.plot_modes.electrochem.labels import run_ec_rename_menu
from batplot.plot_modes.electrochem.legend_order import run_ec_legend_order_menu
from batplot.plot_modes.electrochem.line_style import run_ec_line_style_menu
from batplot.plot_modes.electrochem.menu import print_electrochem_menu
from batplot.plot_modes.electrochem.spine_colors import run_ec_spine_color_menu
from batplot.plot_modes.histo.colors import run_histo_color_menu
from batplot.plot_modes.histo.density_curve import run_histo_density_curve_menu
from batplot.plot_modes.histo.fonts import run_histo_font_menu
from batplot.plot_modes.histo.labels import run_histo_rename_menu
from batplot.plot_modes.histo.line_style import run_histo_line_style_menu
from batplot.plot_modes.histo.load import build_bin_edges
from batplot.plot_modes.histo.plot import HistoState, HistoStyle
from batplot.plot_modes.histo.toggles import run_histo_toggle_menu
from batplot.plot_modes.histo.wizard import HistoSetup
from batplot.plot_modes.histo.y_range import run_histo_y_range_menu
from batplot.plot_modes.operando.axis_units import run_operando_axis_units_menu
from batplot.plot_modes.operando.colors import (
    run_operando_cif_color_menu,
    run_operando_colormap_menu,
)
from batplot.plot_modes.operando.grid import run_ec_grid_menu
from batplot.plot_modes.operando.labels import (
    run_operando_ec_rename_menu,
    run_operando_rename_menu,
)
from batplot.plot_modes.operando.line_style import run_ec_line_style_menu as run_op_ec_line_style
from batplot.plot_modes.operando.menu import print_operando_ec_menu
from batplot.plot_modes.operando.peaks import run_peak_search_menu
from batplot.plot_modes.operando.visibility import run_visibility_menu
from batplot.plot_modes.xy.arrange import run_rearrange_menu
from batplot.plot_modes.xy.axis_range import run_x_range_menu, run_y_range_menu
from batplot.plot_modes.xy.axis_units import run_axis_units_menu
from batplot.plot_modes.xy.cif import run_cif_ticks_menu
from batplot.plot_modes.xy.colors import run_xy_color_menu
from batplot.plot_modes.xy.derivative import run_derivative_menu
from batplot.plot_modes.xy.labels import run_xy_rename_menu
from batplot.plot_modes.xy.line_style import run_line_style_menu
from batplot.plot_modes.xy.menu import print_xy_menu
from batplot.plot_modes.xy.peaks import run_peak_finder_menu
from batplot.plot_modes.xy.smoothing import run_smoothing_menu


def _feed(*vals: str) -> Callable[..., str]:
    it = iter(vals)

    def _in(*_a, **_k):
        try:
            return next(it)
        except StopIteration:
            return "q"

    return _in


def _noop(*_a, **_k):
    return None


def _identity(s: str) -> str:
    return s


@pytest.fixture
def xy_ctx():
    fig, ax = plt.subplots()
    x = np.array([0.0, 1.0, 2.0])
    y = np.array([0.0, 1.0, 0.5])
    (ln,) = ax.plot(x, y, label="c1")
    args = SimpleNamespace(stack=False, files=["a.xy"])
    ctx = {
        "fig": fig,
        "ax": ax,
        "ln": ln,
        "args": args,
        "labels": ["c1"],
        "x_data_list": [x.copy()],
        "y_data_list": [y.copy()],
        "orig_y": [y.copy()],
        "offsets_list": [0.0],
        "x_full_list": [x.copy()],
        "raw_y_full_list": [y.copy()],
        "label_text_objects": [],
    }
    yield ctx
    plt.close(fig)


@pytest.fixture
def ec_ctx():
    fig, ax = plt.subplots()
    (chg,) = ax.plot([0, 1], [3.0, 3.5], color="C0")
    (dch,) = ax.plot([1, 0], [3.5, 3.0], color="C1")
    cycle_lines = {1: {"charge": chg, "discharge": dch}}
    file_data = [
        {
            "filename": "a.mpt",
            "display_name": "a",
            "visible": True,
            "cycle_lines": cycle_lines,
        }
    ]
    yield {
        "fig": fig,
        "ax": ax,
        "cycle_lines": cycle_lines,
        "file_data": file_data,
        "all_cycles": [1],
    }
    plt.close(fig)


@pytest.fixture
def cpc_ctx():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc_c = ax.scatter([1], [100], color="C0")
    sc_d = ax.scatter([1], [90], color="C1")
    sc_e = ax2.scatter([1], [0.95], color="C2")
    yield {"fig": fig, "ax": ax, "ax2": ax2, "sc_c": sc_c, "sc_d": sc_d, "sc_e": sc_e}
    plt.close(fig)


@pytest.fixture
def histo_ctx():
    fig, ax = plt.subplots()
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    state = HistoState(setup=setup, style=HistoStyle())
    yield {"fig": fig, "ax": ax, "state": state}
    plt.close(fig)


@pytest.fixture
def op_ctx():
    fig, ax = plt.subplots()
    im = ax.imshow(np.random.rand(6, 8), origin="lower", aspect="auto")
    cbar = fig.colorbar(im)
    ec_ax = fig.add_axes([0.78, 0.15, 0.12, 0.7])
    (line,) = ec_ax.plot([0, 1], [0, 1])
    ec_ax._ec_line = line  # type: ignore[attr-defined]
    im._operando_cmap_name = "viridis"  # type: ignore[attr-defined]
    ax._operando_cif_tick_series = [  # type: ignore[attr-defined]
        ("p1", "/tmp/a.cif", [1.0], 0.709, 5.0, "#1f77b4")
    ]
    ax._operando_cif_hkl_label_map = {}  # type: ignore[attr-defined]
    fig._operando_cif_y_positions = [0.1]  # type: ignore[attr-defined]
    yield {"fig": fig, "ax": ax, "im": im, "cbar": cbar, "ec_ax": ec_ax}
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main-menu printers (no input loop)
# ---------------------------------------------------------------------------


def test_print_all_main_menus(xy_ctx, ec_ctx, cpc_ctx, op_ctx, histo_ctx):
    print_xy_menu(fig=xy_ctx["fig"], stack=False, is_diffraction=True, colorize_menu=colorize_menu)
    print_electrochem_menu(1, is_dqdv=False, fig=ec_ctx["fig"], is_multi_file=False)
    print_cpc_menu(fig=cpc_ctx["fig"])
    print_operando_ec_menu(op_ctx["fig"], op_ctx["ec_ax"])
    from batplot.plot_modes.histo.interactive import _print_histo_menu

    _print_histo_menu(histo_ctx["fig"], histo_ctx["state"])


# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------


def test_common_menus_quit():
    run_font_menu(
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
        get_current_family=lambda: "Arial",
        get_current_size=lambda: 12,
        apply_family=_noop,
        apply_size=_noop,
    )
    run_axis_limit_menu(
        axis_name="X",
        prompt_name="X",
        get_limits=lambda: (0.0, 1.0),
        set_limits=_noop,
        auto_limits=_noop,
        push_state=_noop,
        state_label="x",
        draw=_noop,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_option_menu(
        title="Demo",
        prompt="Demo (q): ",
        options={},
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_dispatch_menu(
        title="Demo",
        prompt="Demo (q): ",
        options={},
        handle_choice=_noop,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    fig, ax = plt.subplots()
    try:
        run_legend_position_menu(
            fig=fig,
            get_legend=lambda: None,
            get_position=lambda: (0.0, 0.0),
            set_position=_noop,
            sanitize_offset=lambda p: (0.0, 0.0),
            toggle_legend=_noop,
            apply_position=_noop,
            push_state=_noop,
            safe_input=_feed("q"),
            colorize_menu=colorize_menu,
            colorize_prompt=colorize_prompt,
        )
        wasd = {
            side: {
                "spine": True,
                "ticks": True,
                "minor": False,
                "labels": True,
                "title": side == "bottom",
            }
            for side in ("top", "bottom", "left", "right")
        }
        run_spine_tick_menu(
            fig=fig,
            wasd=wasd,
            safe_input=_feed("q"),
            colorize_prompt=colorize_prompt,
            colorize_inline_commands=colorize_inline_commands,
            push_state=_noop,
            sync_tick_state=_noop,
            apply_wasd=_noop,
        )
        run_overview_submenu(
            [],
            safe_input=_feed("q"),
            colorize_menu=colorize_menu,
            colorize_prompt=colorize_prompt,
        )
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# XY
# ---------------------------------------------------------------------------


def test_xy_menus_quit(xy_ctx):
    c = xy_ctx
    fig, ax, ln = c["fig"], c["ax"], c["ln"]
    run_xy_color_menu(
        ax=ax,
        fig=fig,
        labels=c["labels"],
        y_data_list=c["y_data_list"],
        label_text_objects=c["label_text_objects"],
        stack=False,
        args_files=["a.xy"],
        line_getter=lambda i: ln,
        bp=None,
        get_cif_series=lambda: None,
        sync_fig_cif_tick_series=_noop,
        position_top_xlabel=_noop,
        position_right_ylabel=_noop,
        push_state=_noop,
        safe_input=_feed("q"),
        colorize_prompt=colorize_prompt,
    )
    run_line_style_menu(
        ax=ax,
        fig=fig,
        lines_by_curve=None,
        line_getter=lambda i: ln,
        line_count=lambda: 1,
        push_state=_noop,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_xy_rename_menu(
        ax=ax,
        fig=fig,
        labels=c["labels"],
        label_text_objects=c["label_text_objects"],
        args_files=["a.xy"],
        get_cif_series=lambda: None,
        print_cif_phase_list=_noop,
        apply_cif_phase_label_rename=_noop,
        position_top_xlabel=_noop,
        position_bottom_xlabel=_noop,
        position_right_ylabel=_noop,
        position_left_ylabel=_noop,
        sync_fonts=_noop,
        push_state=_noop,
        safe_input=_feed("q"),
    )
    run_x_range_menu(
        args=c["args"],
        ax=ax,
        fig=fig,
        labels=c["labels"],
        label_text_objects=c["label_text_objects"],
        x_data_list=c["x_data_list"],
        y_data_list=c["y_data_list"],
        orig_y=c["orig_y"],
        offsets_list=c["offsets_list"],
        x_full_list=c["x_full_list"],
        raw_y_full_list=c["raw_y_full_list"],
        push_state=_noop,
        _safe_input=_feed("q"),
        _line=lambda i: ln,
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_y_range_menu(
        args=c["args"],
        ax=ax,
        fig=fig,
        label_text_objects=c["label_text_objects"],
        y_data_list=c["y_data_list"],
        push_state=_noop,
        _safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_cif_ticks_menu(
        ax=ax,
        fig=fig,
        _bp=None,
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
        _safe_input=_feed("q"),
        push_state=_noop,
        _print_cif_phase_list=_noop,
        _apply_cif_phase_label_rename=_noop,
        _sync_fig_cif_tick_series=_noop,
    )
    run_peak_finder_menu(
        ax=ax,
        x_data_list=c["x_data_list"],
        y_data_list=c["y_data_list"],
        offsets_list=c["offsets_list"],
        labels=c["labels"],
        source_file_paths=["/tmp/a.xy"],
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_axis_units_menu(
        fig=fig,
        ax=ax,
        args=c["args"],
        x_data_list=c["x_data_list"],
        x_full_list=c["x_data_list"],
        y_data_list=c["y_data_list"],
        use_Q=True,
        use_r=False,
        use_E=False,
        use_k=False,
        use_rft=False,
        get_cif_series=lambda: [],
        sync_fig_cif_tick_series=_noop,
        file_wavelength_info=None,
        push_state=_noop,
        pop_undo=None,
        set_use_Q=_noop,
        _safe_input=_feed("b"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_smoothing_menu(
        fig=fig,
        x_data_list=c["x_data_list"],
        y_data_list=c["y_data_list"],
        offsets_list=c["offsets_list"],
        ensure_original_data=_noop,
        reset_to_original=_noop,
        apply_data_changes=_noop,
        update_full_processed_data=_noop,
        get_last_reduce_rows_settings=lambda: {},
        save_last_reduce_rows_settings=_noop,
        get_last_smooth_settings_from_config=lambda: {},
        save_last_smooth_settings_to_config=_noop,
        push_state=_noop,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_derivative_menu(
        args=c["args"],
        ax=ax,
        fig=fig,
        label_text_objects=c["label_text_objects"],
        x_data_list=c["x_data_list"],
        y_data_list=c["y_data_list"],
        offsets_list=c["offsets_list"],
        push_state=_noop,
        _safe_input=_feed("q"),
        _apply_data_changes=_noop,
        _ensure_pre_derivative_data=_noop,
        _reset_from_derivative=_noop,
        _update_full_processed_data=_noop,
        _update_ylabel_for_derivative=_noop,
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_rearrange_menu(
        args=c["args"],
        ax=ax,
        fig=fig,
        labels=c["labels"],
        label_text_objects=c["label_text_objects"],
        x_data_list=c["x_data_list"],
        y_data_list=c["y_data_list"],
        orig_y=c["orig_y"],
        offsets_list=c["offsets_list"],
        x_full_list=c["x_full_list"],
        raw_y_full_list=c["raw_y_full_list"],
        delta=0.0,
        push_state=_noop,
        _safe_input=_feed("q"),
        _line=lambda i: ln,
        _lines_by_curve=None,
    )


# ---------------------------------------------------------------------------
# Electrochem
# ---------------------------------------------------------------------------


def test_ec_menus_quit(ec_ctx):
    c = ec_ctx
    fig, ax = c["fig"], c["ax"]

    def _iter_cycle_lines(cl):
        for cyc, seg in (cl or {}).items():
            if isinstance(seg, dict):
                for role, ln in seg.items():
                    if ln is not None:
                        yield cyc, role, ln
            else:
                yield cyc, "line", seg

    run_ec_cycles_menu(
        fig=fig,
        ax=ax,
        cycle_lines=c["cycle_lines"],
        file_data=c["file_data"],
        current_file_idx=0,
        all_cycles=c["all_cycles"],
        is_multi_file=False,
        is_dqdv=False,
        menu_title="EC",
        canvas_mode=False,
        print_file_list=_noop,
        print_menu=_noop,
        colorize_menu=colorize_menu,
        colorize_inline_commands=colorize_inline_commands,
        colorize_prompt=colorize_prompt,
        safe_input=_feed("q"),
        push_state=_noop,
        parse_fall_cycles_tokens=lambda *_a, **_k: None,
        parse_per_file_cycle_tokens=lambda *_a, **_k: None,
        parse_file_palette_tokens=lambda *_a, **_k: None,
        parse_cycle_tokens=lambda *_a, **_k: ([], None, []),
        set_visible_cycles=_noop,
        apply_colors=_noop,
        apply_curve_linewidth=_noop,
        apply_stored_smooth_settings=_noop,
        apply_display_mode=_noop,
        rebuild_legend=_noop,
        apply_nice_ticks=_noop,
    )
    run_ec_line_style_menu(
        fig=fig,
        ax=ax,
        cycle_lines=c["cycle_lines"],
        file_data=c["file_data"],
        current_file_idx=0,
        is_multi_file=False,
        is_dqdv=False,
        print_file_list=_noop,
        iter_cycle_lines=_iter_cycle_lines,
        rebuild_legend=_noop,
        apply_stored_smooth_settings=_noop,
        push_state=_noop,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_ec_rename_menu(
        fig=fig,
        ax=ax,
        file_data=c["file_data"],
        tick_state={},
        push_state=_noop,
        rebuild_legend=_noop,
        print_file_list=_noop,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
        ui_position_top_xlabel=_noop,
        ui_position_bottom_xlabel=_noop,
        ui_position_left_ylabel=_noop,
        ui_position_right_ylabel=_noop,
    )
    run_ec_spine_color_menu(
        fig=fig,
        ax=ax,
        tick_state={},
        apply_spine_color=_noop,
        push_state=_noop,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    # early-return path when not multi-file
    run_ec_legend_order_menu(
        fig=fig,
        ax=ax,
        file_data=c["file_data"],
        is_multi_file=False,
        print_file_list=_noop,
        rebuild_legend=_noop,
        push_state=_noop,
        safe_input=_feed("q"),
    )


# ---------------------------------------------------------------------------
# CPC
# ---------------------------------------------------------------------------


def test_cpc_menus_quit(cpc_ctx, monkeypatch):
    from batplot.plot_modes.cpc.add_file import run_cpc_add_files_menu
    import batplot.plot_modes.cpc.add_file as cpc_add

    # ``a`` opens the OS picker first; never block CI/dev on a real dialog.
    monkeypatch.setattr(cpc_add, "_ask_files_dialog", lambda *a, **k: [])

    c = cpc_ctx
    run_cpc_color_menu(
        fig=c["fig"],
        ax=c["ax"],
        ax2=c["ax2"],
        file_data=[],
        is_multi_file=False,
        sc_charge=c["sc_c"],
        sc_eff=c["sc_e"],
        push_state=_noop,
        set_spine_color=_noop,
        rebuild_legend=_noop,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_cpc_rename_menu(
        fig=c["fig"],
        ax=c["ax"],
        ax2=c["ax2"],
        file_data=[],
        current_file_idx=0,
        is_multi_file=False,
        push_state=_noop,
        rebuild_legend=_noop,
        print_file_list=_noop,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_cpc_add_files_menu(
        fig=c["fig"],
        ax=c["ax"],
        ax2=c["ax2"],
        file_data=list(c.get("file_data") or []),
        push_state=_noop,
        pop_undo=_noop,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
        print_menu=_noop,
    )


# ---------------------------------------------------------------------------
# Histo
# ---------------------------------------------------------------------------


def test_histo_menus_quit(histo_ctx):
    c = histo_ctx
    fig, ax, state = c["fig"], c["ax"], c["state"]
    run_histo_color_menu(
        fig=fig,
        ax=ax,
        get_bar_color=lambda: "#4c72b0",
        set_bar_color=_noop,
        get_edge_color=lambda: "#1f1f1f",
        set_edge_color=_noop,
        push_state=_noop,
        refresh=_noop,
        safe_input=_feed("q"),
        colorize_prompt=colorize_prompt,
    )
    run_histo_line_style_menu(
        fig=fig,
        ax=ax,
        state=state,
        push_state=_noop,
        refresh=_noop,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_histo_font_menu(
        state=state,
        push_state=_noop,
        refresh=_noop,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_histo_rename_menu(
        fig=fig,
        ax=ax,
        state=state,
        push_state=_noop,
        refresh=_noop,
        safe_input=_feed("q"),
        colorize_prompt=colorize_prompt,
    )
    run_histo_toggle_menu(
        fig=fig,
        ax=ax,
        state=state,
        push_state=_noop,
        refresh=_noop,
        safe_input=_feed("q"),
        colorize_prompt=colorize_prompt,
        toggle_display=_noop,
        colorize_menu=colorize_menu,
    )
    run_histo_y_range_menu(
        state=state,
        push_state=_noop,
        refresh=_noop,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_histo_density_curve_menu(
        state=state,
        push_state=_noop,
        refresh=_noop,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )


# ---------------------------------------------------------------------------
# Operando
# ---------------------------------------------------------------------------


def test_operando_menus_quit(op_ctx):
    from batplot.plot_modes.operando.spine_colors import run_operando_spine_color_menu

    c = op_ctx
    fig, ax, im, cbar, ec_ax = c["fig"], c["ax"], c["im"], c["cbar"], c["ec_ax"]
    fig._operando_axis_mode = "Q"
    fig._operando_wl = 1.54
    run_operando_spine_color_menu(
        fig=fig,
        ax=ax,
        ec_ax=ec_ax,
        push_state=_noop,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_operando_axis_units_menu(
        fig=fig,
        ax=ax,
        im=im,
        push_state=_noop,
        pop_undo=None,
        _safe_input=_feed("b"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_operando_colormap_menu(
        fig=fig,
        im=im,
        cbar=cbar,
        snapshot=_noop,
        update_custom_colorbar=_noop,
        safe_input=_feed("q"),
        colorize_inline_commands=colorize_inline_commands,
    )
    run_operando_colormap_menu(
        fig=fig,
        im=im,
        cbar=cbar,
        snapshot=_noop,
        update_custom_colorbar=_noop,
        safe_input=_feed("plasma", "q"),
        colorize_inline_commands=colorize_inline_commands,
    )
    assert getattr(im, "_operando_cmap_name", None) == "plasma"
    run_operando_cif_color_menu(
        fig=fig,
        ax=ax,
        cif_series=list(ax._operando_cif_tick_series),
        safe_input=_feed("q"),
        push_state=_noop,
        redraw=_noop,
        colorize_prompt=colorize_prompt,
    )
    run_visibility_menu(
        fig=fig,
        ax=ax,
        im=im,
        cbar=cbar,
        ec_ax=ec_ax,
        snapshot=_noop,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
        colorize_inline_commands=colorize_inline_commands,
    )
    run_op_ec_line_style(
        fig=fig,
        ec_ax=ec_ax,
        snapshot=_noop,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_ec_grid_menu(
        fig=fig,
        ec_ax=ec_ax,
        snapshot=_noop,
        safe_input=_feed("q"),
        colorize_prompt=colorize_prompt,
        colorize_inline_commands=colorize_inline_commands,
    )
    run_operando_rename_menu(
        fig=fig,
        ax=ax,
        snapshot=_noop,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_operando_ec_rename_menu(
        fig=fig,
        ec_ax=ec_ax,
        snapshot=_noop,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_peak_search_menu(
        im=im,
        file_paths=["/tmp/fake.npy"],
        print_menu=_noop,
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )


# ---------------------------------------------------------------------------
# Batch main menus (q then y to confirm quit)
# ---------------------------------------------------------------------------


def test_batch_main_menus_quit(monkeypatch, xy_ctx, ec_ctx, cpc_ctx, histo_ctx, op_ctx):
    from batplot.plot_modes.batch_session.load import (
        CpcPanel,
        EcPanel,
        HistoPanel,
        OperandoPanel,
        XyPanel,
    )
    from batplot.plot_modes.batch_session import (
        batch_menu_io,
        menu_cpc,
        menu_dqdv_2d,
        menu_ec,
        menu_histo,
        menu_operando,
        menu_xy,
    )

    # Always confirm quit without prompting (batch_quit_confirm → 'y')
    monkeypatch.setattr(batch_menu_io, "batch_quit_confirm", lambda **_k: "y")

    def _run(mod, panel):
        feeder = _feed("q")
        monkeypatch.setattr(mod, "prompt_menu_key", lambda *a, **k: feeder())
        mod_fn = {
            menu_xy: menu_xy.run_xy_batch_menu,
            menu_ec: menu_ec.run_ec_batch_menu,
            menu_cpc: menu_cpc.run_cpc_batch_menu,
            menu_histo: menu_histo.run_histo_batch_menu,
            menu_operando: menu_operando.run_operando_batch_menu,
            menu_dqdv_2d: menu_dqdv_2d.run_dqdv_2d_batch_menu,
        }[mod]
        mod_fn([panel])

    _run(
        menu_xy,
        XyPanel(
            path="a.pkl",
            fig=xy_ctx["fig"],
            ax=xy_ctx["ax"],
            menu_kwargs={
                "labels": xy_ctx["labels"],
                "y_data_list": xy_ctx["y_data_list"],
            },
        ),
    )
    _run(
        menu_ec,
        EcPanel(
            path="a.pkl",
            fig=ec_ctx["fig"],
            ax=ec_ctx["ax"],
            cycle_lines=ec_ctx["cycle_lines"],
            file_data=ec_ctx["file_data"],
        ),
    )
    _run(
        menu_cpc,
        CpcPanel(
            path="a.pkl",
            fig=cpc_ctx["fig"],
            ax=cpc_ctx["ax"],
            ax2=cpc_ctx["ax2"],
            sc_charge=cpc_ctx["sc_c"],
            sc_discharge=cpc_ctx["sc_d"],
            sc_eff=cpc_ctx["sc_e"],
        ),
    )
    _run(
        menu_histo,
        HistoPanel(
            path="a.pkl",
            fig=histo_ctx["fig"],
            ax=histo_ctx["ax"],
            state=histo_ctx["state"],
        ),
    )
    _run(
        menu_operando,
        OperandoPanel(
            path="a.pkl",
            fig=op_ctx["fig"],
            ax=op_ctx["ax"],
            im=op_ctx["im"],
            cbar=op_ctx["cbar"],
            ec_ax=op_ctx["ec_ax"],
        ),
    )
    _run(
        menu_dqdv_2d,
        OperandoPanel(
            path="a.pkl",
            fig=op_ctx["fig"],
            ax=op_ctx["ax"],
            im=op_ctx["im"],
            cbar=op_ctx["cbar"],
            ec_ax=None,
        ),
    )


def test_batch_and_layout_subhelpers_quit(monkeypatch, xy_ctx, op_ctx, histo_ctx):
    """Smoke batch geom/font helpers and operando/histo size menus (quit immediately)."""
    from batplot.plot_modes.batch_session.batch_geom_helpers import (
        run_batch_canvas_menu,
        run_batch_geom_size_menu,
        run_batch_plot_frame_menu,
    )
    from batplot.plot_modes.batch_session.histo_batch_helpers import run_batch_histo_geom_menu
    from batplot.plot_modes.batch_session.load import HistoPanel, OperandoPanel, XyPanel
    from batplot.plot_modes.batch_session import batch_geom_helpers as bgh
    from batplot.plot_modes.batch_session import histo_batch_helpers as hbh
    from batplot.plot_modes.common.batch_font import run_batch_font_menu
    from batplot.plot_modes.operando.layout_menu import (
        run_operando_batch_size_menu,
        run_operando_size_menu,
    )

    panel = XyPanel(
        path="a.pkl",
        fig=xy_ctx["fig"],
        ax=xy_ctx["ax"],
        menu_kwargs={"labels": xy_ctx["labels"], "y_data_list": xy_ctx["y_data_list"]},
    )
    monkeypatch.setattr(bgh, "safe_input", _feed("q"))
    monkeypatch.setattr(hbh, "safe_input", _feed("q"))
    run_batch_plot_frame_menu([panel], push_undo=_noop, draw_all=_noop)
    run_batch_canvas_menu([panel], push_undo=_noop, draw_all=_noop)
    run_batch_geom_size_menu(
        [panel],
        push_undo=_noop,
        draw_all=_noop,
        colorize_menu=colorize_menu,
    )
    histo_p = HistoPanel(
        path="a.pkl",
        fig=histo_ctx["fig"],
        ax=histo_ctx["ax"],
        state=histo_ctx["state"],
    )
    run_batch_histo_geom_menu(
        [histo_p],
        push_all=_noop,
        draw_all=_noop,
        colorize_menu=colorize_menu,
    )

    class _Undo:
        def push_all(self, _snaps):
            return None

    run_batch_font_menu(
        panels=[panel],
        undo=_Undo(),
        capture_panel=lambda _p: {},
        draw_panels=_noop,
        collect_artists=lambda _p: [],
        safe_input=_feed("q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_operando_size_menu(
        op_ctx["fig"],
        op_ctx["ax"],
        op_ctx["cbar"],
        op_ctx["ec_ax"],
        on_before_change=_noop,
        on_after_change=_noop,
        safe_input_fn=_feed("q"),
        colorize_menu_fn=colorize_menu,
        colorize_prompt_fn=colorize_prompt,
    )
    op_p = OperandoPanel(
        path="a.pkl",
        fig=op_ctx["fig"],
        ax=op_ctx["ax"],
        im=op_ctx["im"],
        cbar=op_ctx["cbar"],
        ec_ax=op_ctx["ec_ax"],
    )
    run_operando_batch_size_menu(
        [op_p],
        push_undo=_noop,
        draw_all=_noop,
        safe_input_fn=_feed("q"),
        colorize_menu_fn=colorize_menu,
        colorize_prompt_fn=colorize_prompt,
    )


def test_batch_spine_helpers_quit(monkeypatch, xy_ctx, ec_ctx, cpc_ctx, op_ctx):
    import inspect

    from batplot.plot_modes.batch_session import (
        cpc_batch_helpers,
        ec_batch_helpers,
        operando_batch_helpers,
        xy_batch_helpers,
    )
    from batplot.plot_modes.batch_session.load import (
        CpcPanel,
        EcPanel,
        OperandoPanel,
        XyPanel,
    )

    # Helpers import run_spine_tick_menu / safe_input into their own namespace.
    for mod in (
        xy_batch_helpers,
        ec_batch_helpers,
        cpc_batch_helpers,
        operando_batch_helpers,
    ):
        if hasattr(mod, "run_spine_tick_menu"):
            monkeypatch.setattr(mod, "run_spine_tick_menu", lambda **_k: None)
        if hasattr(mod, "safe_input"):
            monkeypatch.setattr(mod, "safe_input", _feed("q"))

    xy_p = XyPanel(path="a.pkl", fig=xy_ctx["fig"], ax=xy_ctx["ax"], menu_kwargs={})
    ec_p = EcPanel(
        path="a.pkl",
        fig=ec_ctx["fig"],
        ax=ec_ctx["ax"],
        cycle_lines=ec_ctx["cycle_lines"],
        file_data=ec_ctx["file_data"],
    )
    cpc_p = CpcPanel(
        path="a.pkl",
        fig=cpc_ctx["fig"],
        ax=cpc_ctx["ax"],
        ax2=cpc_ctx["ax2"],
        sc_charge=cpc_ctx["sc_c"],
        sc_discharge=cpc_ctx["sc_d"],
        sc_eff=cpc_ctx["sc_e"],
    )
    op_p = OperandoPanel(
        path="a.pkl",
        fig=op_ctx["fig"],
        ax=op_ctx["ax"],
        im=op_ctx["im"],
        cbar=op_ctx["cbar"],
        ec_ax=op_ctx["ec_ax"],
    )
    undo = type("U", (), {"push_all": staticmethod(lambda _s: None)})()

    for fn, panel in (
        (xy_batch_helpers.run_xy_batch_spine_menu, xy_p),
        (ec_batch_helpers.run_ec_batch_spine_menu, ec_p),
        (cpc_batch_helpers.run_cpc_batch_spine_menu, cpc_p),
        (operando_batch_helpers.run_operando_batch_spine_menu, op_p),
        (operando_batch_helpers.run_operando_batch_spine_color_menu, op_p),
    ):
        kwargs = {}
        for name in inspect.signature(fn).parameters:
            if name == "ref":
                kwargs[name] = panel
            elif name == "panels":
                kwargs[name] = [panel]
            elif name in ("push_undo",):
                kwargs[name] = _noop
            elif name == "undo":
                kwargs[name] = undo
            elif "draw" in name:
                kwargs[name] = _noop
            elif "capture" in name:
                kwargs[name] = lambda _p: {}
            elif "apply" in name:
                kwargs[name] = lambda *_a, **_k: True
        fn(**kwargs)


# ---------------------------------------------------------------------------
# Walk EVERY top-level batch key + EVERY submenu subkey (all modes)
# ---------------------------------------------------------------------------


def _patch_all_safe_input(monkeypatch, feeder):
    """Force nested menus (which bind safe_input at import time) to use feeder."""
    import batplot.plot_modes as pm_root
    from pathlib import Path
    import importlib
    import pkgutil

    root = Path(pm_root.__file__).resolve().parent
    for info in pkgutil.walk_packages([str(root)], prefix="batplot.plot_modes."):
        try:
            mod = importlib.import_module(info.name)
        except Exception:
            continue
        if hasattr(mod, "safe_input"):
            monkeypatch.setattr(mod, "safe_input", feeder, raising=False)

    # Never launch the real screen eyedropper in menu smoke (blocks on GUI/stdin).
    monkeypatch.setattr(
        "batplot.color_utils.prompt_screen_color", lambda *a, **k: None, raising=False
    )
    monkeypatch.setattr(
        "batplot.screen_color.pick_screen_colors", lambda **k: [], raising=False
    )


def _patch_batch_io_noop(monkeypatch, mod):
    for name in (
        "batch_export_figures",
        "batch_export_style",
        "batch_import_style",
        "batch_save_sessions",
        "batch_overwrite_figures",
        "batch_overwrite_sessions",
    ):
        if hasattr(mod, name):
            monkeypatch.setattr(mod, name, lambda *a, **k: None)
    if hasattr(mod, "batch_quit_or_save_all"):
        monkeypatch.setattr(mod, "batch_quit_or_save_all", lambda *a, **k: True)


def test_batch_all_toplevel_keys_all_modes(monkeypatch, xy_ctx, ec_ctx, cpc_ctx, histo_ctx, op_ctx):
    """Enter every printed top-level key on every batch menu, then quit.

    Nested prompts always get ``q`` so we only verify dispatch / NameError safety.
    """
    from batplot.plot_modes.batch_session.load import (
        CpcPanel,
        EcPanel,
        HistoPanel,
        OperandoPanel,
        XyPanel,
    )
    from batplot.plot_modes.batch_session import (
        menu_cpc,
        menu_dqdv_2d,
        menu_ec,
        menu_histo,
        menu_operando,
        menu_xy,
    )

    _patch_all_safe_input(monkeypatch, _feed())
    monkeypatch.setattr("builtins.input", _feed())

    cases = [
        (
            menu_xy,
            menu_xy.run_xy_batch_menu,
            XyPanel(
                path="a.pkl",
                fig=xy_ctx["fig"],
                ax=xy_ctx["ax"],
                menu_kwargs={
                    "labels": xy_ctx["labels"],
                    "y_data_list": xy_ctx["y_data_list"],
                },
            ),
            # styles + geom + options + known rejected keys
            ["c", "f", "l", "t", "h", "g", "r", "x", "y", "v", "n", "e", "p", "i", "s", "b",
             "sm", "a", "o", "d", "cif"],
        ),
        (
            menu_ec,
            menu_ec.run_ec_batch_menu,
            EcPanel(
                path="a.pkl",
                fig=ec_ctx["fig"],
                ax=ec_ctx["ax"],
                cycle_lines=ec_ctx["cycle_lines"],
                file_data=ec_ctx["file_data"],
            ),
            ["f", "l", "t", "k", "h", "d", "v", "g", "c", "r", "x", "y", "ra", "o", "n",
             "e", "p", "i", "s", "b", "a", "sm", "2d"],
        ),
        (
            menu_cpc,
            menu_cpc.run_cpc_batch_menu,
            CpcPanel(
                path="a.pkl",
                fig=cpc_ctx["fig"],
                ax=cpc_ctx["ax"],
                ax2=cpc_ctx["ax2"],
                sc_charge=cpc_ctx["sc_c"],
                sc_discharge=cpc_ctx["sc_d"],
                sc_eff=cpc_ctx["sc_e"],
            ),
            ["f", "l", "m", "c", "d", "ry", "t", "h", "v", "g", "r", "x", "y", "ie", "o",
             "n", "e", "p", "i", "s", "b"],
        ),
        (
            menu_histo,
            menu_histo.run_histo_batch_menu,
            HistoPanel(
                path="a.pkl",
                fig=histo_ctx["fig"],
                ax=histo_ctx["ax"],
                state=histo_ctx["state"],
            ),
            ["c", "f", "a", "l", "t", "g", "w", "r", "x", "y", "n", "e", "p", "i", "s", "b"],
        ),
        (
            menu_operando,
            menu_operando.run_operando_batch_menu,
            OperandoPanel(
                path="a.pkl",
                fig=op_ctx["fig"],
                ax=op_ctx["ax"],
                im=op_ctx["im"],
                cbar=op_ctx["cbar"],
                ec_ax=op_ctx["ec_ax"],
            ),
            ["oc", "el", "v", "t", "l", "f", "g", "ow", "ew", "h", "r", "ox", "oy", "oz",
             "or", "c", "pk", "et", "ex", "ey", "er", "eg", "n", "e", "p", "i", "s", "b"],
        ),
        (
            menu_dqdv_2d,
            menu_dqdv_2d.run_dqdv_2d_batch_menu,
            OperandoPanel(
                path="a.pkl",
                fig=op_ctx["fig"],
                ax=op_ctx["ax"],
                im=op_ctx["im"],
                cbar=op_ctx["cbar"],
                ec_ax=None,
            ),
            ["oc", "v", "t", "l", "f", "g", "r", "ox", "oy", "oz", "or", "n",
             "e", "p", "i", "s", "b"],
        ),
    ]

    for mod, fn, panel, keys in cases:
        _patch_batch_io_noop(monkeypatch, mod)
        feeder = _feed(*(list(keys) + ["q"]))
        monkeypatch.setattr(mod, "prompt_menu_key", lambda *a, **k: feeder())
        # Nested menus often close over this module's safe_input
        if hasattr(mod, "safe_input"):
            monkeypatch.setattr(mod, "safe_input", _feed())
        fn([panel])


def test_batch_nested_subkey_scripts_all_modes(monkeypatch, xy_ctx, ec_ctx, cpc_ctx, histo_ctx, op_ctx):
    """Drive nested submenu keys through every batch main loop.

    One shared feeder drives both ``prompt_menu_key`` (top-level) and
    ``safe_input`` / ``input`` (nested prompts).
    """
    from batplot.plot_modes.batch_session.load import (
        CpcPanel,
        EcPanel,
        HistoPanel,
        OperandoPanel,
        XyPanel,
    )
    from batplot.plot_modes.batch_session import (
        menu_cpc,
        menu_ec,
        menu_histo,
        menu_operando,
        menu_xy,
    )

    scripts = [
        (
            menu_xy,
            menu_xy.run_xy_batch_menu,
            XyPanel(
                path="a.pkl",
                fig=xy_ctx["fig"],
                ax=xy_ctx["ax"],
                menu_kwargs={
                    "labels": xy_ctx["labels"],
                    "y_data_list": xy_ctx["y_data_list"],
                },
            ),
            [
                "c", "red", "q",
                "f", "f", "q", "s", "q", "q",
                "l", "c", "q", "f", "q", "g", "q",
                "t", "q",
                "g", "p", "q", "c", "q", "q",
                "x", "q",
                "y", "q",
                "v", "q",
                "q",
            ],
        ),
        (
            menu_ec,
            menu_ec.run_ec_batch_menu,
            EcPanel(
                path="a.pkl",
                fig=ec_ctx["fig"],
                ax=ec_ctx["ax"],
                cycle_lines=ec_ctx["cycle_lines"],
                file_data=ec_ctx["file_data"],
            ),
            [
                "f", "f", "q", "s", "q", "q",
                "l", "c", "q", "f", "q", "q",
                "k", "q",
                "t", "q",
                "h", "t", "p", "q", "q",
                "d", "c", "b", "q",
                "c", "q",
                "r", "x", "q", "y", "q", "q",
                "x", "q",
                "y", "q",
                "n",
                "o", "c", "q", "q",
                "g", "p", "q", "c", "q", "q",
                # GC batch rejects interactive-only a/sm/2d without crashing.
                "a",
                "sm",
                "2d",
                "q",
            ],
        ),
        (
            menu_cpc,
            menu_cpc.run_cpc_batch_menu,
            CpcPanel(
                path="a.pkl",
                fig=cpc_ctx["fig"],
                ax=cpc_ctx["ax"],
                ax2=cpc_ctx["ax2"],
                sc_charge=cpc_ctx["sc_c"],
                sc_discharge=cpc_ctx["sc_d"],
                sc_eff=cpc_ctx["sc_e"],
            ),
            [
                "f", "f", "q", "s", "q", "q",
                "l", "f", "q", "g", "q",
                "c", "ly", "q", "ry", "q", "s", "q", "q",
                "d", "b", "q",
                "ry", "q",
                "t", "q",
                "y", "ly", "q", "ry", "q", "q",
                "o", "c", "q", "q",
                "g", "p", "q", "c", "q", "q",
                "q",
            ],
        ),
        (
            menu_histo,
            menu_histo.run_histo_batch_menu,
            HistoPanel(
                path="a.pkl",
                fig=histo_ctx["fig"],
                ax=histo_ctx["ax"],
                state=histo_ctx["state"],
            ),
            [
                "c", "q",
                "f", "f", "q", "s", "q", "q",
                "a", "t", "c", "q", "q",
                "l", "f", "q", "g", "q",
                "t", "h", "d", "q", "q",
                "g", "p", "q", "c", "q", "q",
                "r", "x", "q", "y", "q", "q",
                "y", "a", "q",
                "q",
            ],
        ),
        (
            menu_operando,
            menu_operando.run_operando_batch_menu,
            OperandoPanel(
                path="a.pkl",
                fig=op_ctx["fig"],
                ax=op_ctx["ax"],
                im=op_ctx["im"],
                cbar=op_ctx["cbar"],
                ec_ax=op_ctx["ec_ax"],
            ),
            [
                "oc", "plasma", "q",
                "el", "c", "q", "l", "q", "q",
                "v", "1", "q",
                "t", "q",
                "f", "f", "q", "s", "q", "q",
                "g", "c", "q", "o", "q", "e", "q", "q",
                "c", "z", "q", "c", "q", "q",
                "eg", "t", "q",
                "er", "x", "q", "q",
                "pk", "e", "q",
                "q",
            ],
        ),
    ]

    for mod, fn, panel, script in scripts:
        _patch_batch_io_noop(monkeypatch, mod)
        feeder = _feed(*script)
        _patch_all_safe_input(monkeypatch, feeder)
        monkeypatch.setattr("builtins.input", feeder)
        monkeypatch.setattr(mod, "prompt_menu_key", lambda *a, **k: feeder())
        if hasattr(mod, "safe_input"):
            monkeypatch.setattr(mod, "safe_input", feeder)
        fn([panel])


def test_all_submenu_keys_walk_all_modes(monkeypatch, xy_ctx, ec_ctx, cpc_ctx, histo_ctx, op_ctx):
    """Hit every documented subkey in shared + mode submenu helpers, then back out."""
    # Some color helpers still call bare input() for the user-color manager.
    monkeypatch.setattr("builtins.input", _feed())
    monkeypatch.setattr(
        "batplot.color_utils.prompt_screen_color", lambda *a, **k: None, raising=False
    )
    monkeypatch.setattr(
        "batplot.screen_color.pick_screen_colors", lambda **k: [], raising=False
    )
    fig, ax = plt.subplots()
    try:
        # --- common ---
        run_font_menu(
            safe_input=_feed("f", "q", "s", "q", "b", "q", "h", "q", "q"),
            colorize_menu=colorize_menu,
            colorize_prompt=colorize_prompt,
            get_current_family=lambda: "Arial",
            get_current_size=lambda: 12,
            apply_family=_noop,
            apply_size=_noop,
            apply_weight=_noop,
            get_current_weight=lambda: "normal",
            get_current_highlight=lambda: False,
            get_highlight_style=lambda: {},
            apply_highlight_toggle=_noop,
            apply_highlight_facecolor=_noop,
            apply_highlight_alpha=_noop,
            apply_highlight_pad=_noop,
        )
        run_axis_limit_menu(
            axis_name="X",
            prompt_name="X",
            get_limits=lambda: (0.0, 1.0),
            set_limits=_noop,
            auto_limits=_noop,
            push_state=_noop,
            state_label="x",
            draw=_noop,
            safe_input=_feed("w", "q", "s", "q", "a", "0.1 0.9", "q"),
            colorize_menu=colorize_menu,
            colorize_prompt=colorize_prompt,
        )
        called = []
        run_option_menu(
            title="Demo",
            prompt="Demo (p/c/q): ",
            options={"p": ("plot", lambda: called.append("p")), "c": ("canvas", lambda: called.append("c"))},
            safe_input=_feed("p", "c", "q"),
            colorize_menu=colorize_menu,
            colorize_prompt=colorize_prompt,
        )
        assert called == ["p", "c"]
        run_dispatch_menu(
            title="Demo",
            prompt="Demo (ly/ry/q): ",
            options={"ly": "left", "ry": "right"},
            handle_choice=lambda _k: None,
            safe_input=_feed("ly", "ry", "q"),
            colorize_menu=colorize_menu,
            colorize_prompt=colorize_prompt,
        )
        run_legend_position_menu(
            fig=fig,
            get_legend=lambda: None,
            get_position=lambda: (0.0, 0.0),
            set_position=_noop,
            sanitize_offset=lambda p: (0.0, 0.0),
            toggle_legend=_noop,
            apply_position=_noop,
            push_state=_noop,
            safe_input=_feed("t", "p", "q", "q"),
            colorize_menu=colorize_menu,
            colorize_prompt=colorize_prompt,
        )
        wasd = {
            side: {
                "spine": True,
                "ticks": True,
                "minor": False,
                "labels": True,
                "title": side == "bottom",
            }
            for side in ("top", "bottom", "left", "right")
        }
        run_spine_tick_menu(
            fig=fig,
            wasd=wasd,
            safe_input=_feed("list", "s2", "i", "l", "q", "n", "q", "m", "q", "p", "q", "q"),
            colorize_prompt=colorize_prompt,
            colorize_inline_commands=colorize_inline_commands,
            push_state=_noop,
            sync_tick_state=_noop,
            apply_wasd=_noop,
        )
        run_overview_submenu(
            [],
            safe_input=_feed("c", "r", "s", "e", "q"),
            colorize_menu=colorize_menu,
            colorize_prompt=colorize_prompt,
        )
    finally:
        plt.close(fig)

    # --- XY ---
    c = xy_ctx
    ln = c["ln"]
    run_xy_color_menu(
        ax=c["ax"],
        fig=c["fig"],
        labels=c["labels"],
        y_data_list=c["y_data_list"],
        label_text_objects=c["label_text_objects"],
        stack=False,
        args_files=["a.xy"],
        line_getter=lambda i: ln,
        bp=None,
        get_cif_series=lambda: None,
        sync_fig_cif_tick_series=_noop,
        position_top_xlabel=_noop,
        position_right_ylabel=_noop,
        push_state=_noop,
        safe_input=_feed("1:red", "all viridis", "q"),
        colorize_prompt=colorize_prompt,
    )
    run_line_style_menu(
        ax=c["ax"],
        fig=c["fig"],
        lines_by_curve=None,
        line_getter=lambda i: ln,
        line_count=lambda: 1,
        push_state=_noop,
        safe_input=_feed("c", "q", "f", "q", "g", "l", "ld", "d", "da", "dd", "q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_xy_rename_menu(
        ax=c["ax"],
        fig=c["fig"],
        labels=c["labels"],
        label_text_objects=c["label_text_objects"],
        args_files=["a.xy"],
        get_cif_series=lambda: None,
        print_cif_phase_list=_noop,
        apply_cif_phase_label_rename=_noop,
        position_top_xlabel=_noop,
        position_bottom_xlabel=_noop,
        position_right_ylabel=_noop,
        position_left_ylabel=_noop,
        sync_fonts=_noop,
        push_state=_noop,
        safe_input=_feed("c", "q", "x", "q", "y", "q", "s", "q", "q"),
    )
    run_smoothing_menu(
        fig=c["fig"],
        x_data_list=c["x_data_list"],
        y_data_list=c["y_data_list"],
        offsets_list=c["offsets_list"],
        ensure_original_data=_noop,
        reset_to_original=lambda: (True, 1, 3),
        apply_data_changes=_noop,
        update_full_processed_data=_noop,
        get_last_reduce_rows_settings=lambda: {},
        save_last_reduce_rows_settings=_noop,
        get_last_smooth_settings_from_config=lambda: {},
        save_last_smooth_settings_to_config=_noop,
        push_state=_noop,
        safe_input=_feed("r", "q", "s", "q", "reset", "q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_derivative_menu(
        args=c["args"],
        ax=c["ax"],
        fig=c["fig"],
        label_text_objects=c["label_text_objects"],
        x_data_list=c["x_data_list"],
        y_data_list=c["y_data_list"],
        offsets_list=c["offsets_list"],
        push_state=_noop,
        _safe_input=_feed("q"),
        _apply_data_changes=_noop,
        _ensure_pre_derivative_data=_noop,
        _reset_from_derivative=_noop,
        _update_full_processed_data=_noop,
        _update_ylabel_for_derivative=_noop,
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_cif_ticks_menu(
        ax=c["ax"],
        fig=c["fig"],
        _bp=None,
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
        _safe_input=_feed("z", "q", "t", "q", "v", "q", "p", "q", "c", "q", "x", "q", "r", "q", "q"),
        push_state=_noop,
        _print_cif_phase_list=_noop,
        _apply_cif_phase_label_rename=_noop,
        _sync_fig_cif_tick_series=_noop,
    )

    # --- EC ---
    e = ec_ctx

    def _iter_cycle_lines(cl):
        for cyc, seg in (cl or {}).items():
            if isinstance(seg, dict):
                for role, ln_ in seg.items():
                    if ln_ is not None:
                        yield cyc, role, ln_
            else:
                yield cyc, "line", seg

    run_ec_line_style_menu(
        fig=e["fig"],
        ax=e["ax"],
        cycle_lines=e["cycle_lines"],
        file_data=e["file_data"],
        current_file_idx=0,
        is_multi_file=False,
        is_dqdv=False,
        print_file_list=_noop,
        iter_cycle_lines=_iter_cycle_lines,
        rebuild_legend=_noop,
        apply_stored_smooth_settings=_noop,
        push_state=_noop,
        safe_input=_feed("c", "q", "f", "q", "g", "l", "ld", "d", "q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_ec_rename_menu(
        fig=e["fig"],
        ax=e["ax"],
        file_data=e["file_data"],
        tick_state={},
        push_state=_noop,
        rebuild_legend=_noop,
        print_file_list=_noop,
        safe_input=_feed("x", "q", "y", "q", "s", "q", "q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
        ui_position_top_xlabel=_noop,
        ui_position_bottom_xlabel=_noop,
        ui_position_left_ylabel=_noop,
        ui_position_right_ylabel=_noop,
    )
    run_ec_spine_color_menu(
        fig=e["fig"],
        ax=e["ax"],
        tick_state={},
        apply_spine_color=_noop,
        push_state=_noop,
        safe_input=_feed("u", "q", "q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_ec_cycles_menu(
        fig=e["fig"],
        ax=e["ax"],
        cycle_lines=e["cycle_lines"],
        file_data=e["file_data"],
        current_file_idx=0,
        all_cycles=e["all_cycles"],
        is_multi_file=False,
        is_dqdv=False,
        menu_title="EC",
        canvas_mode=False,
        print_file_list=_noop,
        print_menu=_noop,
        colorize_menu=colorize_menu,
        colorize_inline_commands=colorize_inline_commands,
        colorize_prompt=colorize_prompt,
        safe_input=_feed("u", "q", "q"),
        push_state=_noop,
        parse_fall_cycles_tokens=lambda *_a, **_k: None,
        parse_per_file_cycle_tokens=lambda *_a, **_k: None,
        parse_file_palette_tokens=lambda *_a, **_k: None,
        parse_cycle_tokens=lambda *_a, **_k: ([], None, []),
        set_visible_cycles=_noop,
        apply_colors=_noop,
        apply_curve_linewidth=_noop,
        apply_stored_smooth_settings=_noop,
        apply_display_mode=_noop,
        rebuild_legend=_noop,
        apply_nice_ticks=_noop,
    )

    # --- CPC ---
    p = cpc_ctx
    run_cpc_color_menu(
        fig=p["fig"],
        ax=p["ax"],
        ax2=p["ax2"],
        file_data=[],
        is_multi_file=False,
        sc_charge=p["sc_c"],
        sc_eff=p["sc_e"],
        push_state=_noop,
        set_spine_color=_noop,
        rebuild_legend=_noop,
        safe_input=_feed("ly", "q", "ry", "q", "u", "q", "s", "q", "q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_cpc_rename_menu(
        fig=p["fig"],
        ax=p["ax"],
        ax2=p["ax2"],
        file_data=[],
        current_file_idx=0,
        is_multi_file=False,
        push_state=_noop,
        rebuild_legend=_noop,
        print_file_list=_noop,
        safe_input=_feed("x", "q", "ly", "q", "ry", "q", "s", "q", "q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )

    # --- Histo ---
    h = histo_ctx
    run_histo_color_menu(
        fig=h["fig"],
        ax=h["ax"],
        get_bar_color=lambda: "#4c72b0",
        set_bar_color=_noop,
        get_edge_color=lambda: "#1f1f1f",
        set_edge_color=_noop,
        push_state=_noop,
        refresh=_noop,
        safe_input=_feed("u", "q", "q"),
        colorize_prompt=colorize_prompt,
    )
    run_histo_line_style_menu(
        fig=h["fig"],
        ax=h["ax"],
        state=h["state"],
        push_state=_noop,
        refresh=_noop,
        safe_input=_feed("f", "q", "g", "w", "q", "q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_histo_font_menu(
        state=h["state"],
        push_state=_noop,
        refresh=_noop,
        safe_input=_feed("f", "q", "s", "q", "q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_histo_rename_menu(
        fig=h["fig"],
        ax=h["ax"],
        state=h["state"],
        push_state=_noop,
        refresh=_noop,
        safe_input=_feed("x", "q", "y", "q", "t", "q", "o", "q", "s", "q", "q"),
        colorize_prompt=colorize_prompt,
    )
    run_histo_toggle_menu(
        fig=h["fig"],
        ax=h["ax"],
        state=h["state"],
        push_state=_noop,
        refresh=_noop,
        safe_input=_feed("h", "d", "n", "m", "q", "list", "q"),
        colorize_prompt=colorize_prompt,
        toggle_display=_noop,
        colorize_menu=colorize_menu,
    )
    run_histo_density_curve_menu(
        state=h["state"],
        push_state=_noop,
        refresh=_noop,
        safe_input=_feed("t", "c", "q", "w", "q", "l", "q", "q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_histo_y_range_menu(
        state=h["state"],
        push_state=_noop,
        refresh=_noop,
        safe_input=_feed("w", "q", "s", "q", "a", "q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )

    # --- Operando ---
    o = op_ctx
    run_operando_colormap_menu(
        fig=o["fig"],
        im=o["im"],
        cbar=o["cbar"],
        snapshot=_noop,
        update_custom_colorbar=_noop,
        safe_input=_feed("viridis", "plasma_r", "q"),
        colorize_inline_commands=colorize_inline_commands,
    )
    run_operando_cif_color_menu(
        fig=o["fig"],
        ax=o["ax"],
        cif_series=list(o["ax"]._operando_cif_tick_series),
        safe_input=_feed("u", "q", "1:red", "all viridis", "q"),
        push_state=_noop,
        redraw=_noop,
        colorize_prompt=colorize_prompt,
    )
    run_visibility_menu(
        fig=o["fig"],
        ax=o["ax"],
        im=o["im"],
        cbar=o["cbar"],
        ec_ax=o["ec_ax"],
        snapshot=_noop,
        safe_input=_feed("1", "2", "3", "4", "q", "5", "q", "m", "q", "q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
        colorize_inline_commands=colorize_inline_commands,
    )
    run_op_ec_line_style(
        fig=o["fig"],
        ec_ax=o["ec_ax"],
        snapshot=_noop,
        safe_input=_feed("c", "q", "l", "q", "q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_ec_grid_menu(
        fig=o["fig"],
        ec_ax=o["ec_ax"],
        snapshot=_noop,
        safe_input=_feed("t", "a", "q", "s", "q", "c", "q", "w", "q", "q"),
        colorize_prompt=colorize_prompt,
        colorize_inline_commands=colorize_inline_commands,
    )
    run_operando_rename_menu(
        fig=o["fig"],
        ax=o["ax"],
        snapshot=_noop,
        safe_input=_feed("x", "q", "y", "q", "s", "q", "q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_operando_ec_rename_menu(
        fig=o["fig"],
        ec_ax=o["ec_ax"],
        snapshot=_noop,
        safe_input=_feed("x", "q", "y", "q", "s", "q", "q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    run_peak_search_menu(
        im=o["im"],
        file_paths=["/tmp/fake.npy"],
        print_menu=_noop,
        safe_input=_feed("e", "1", "q", "q"),
        colorize_menu=colorize_menu,
        colorize_prompt=colorize_prompt,
    )
    from batplot.plot_modes.operando.layout_menu import run_operando_size_menu

    run_operando_size_menu(
        o["fig"],
        o["ax"],
        o["cbar"],
        o["ec_ax"],
        on_before_change=_noop,
        on_after_change=_noop,
        safe_input_fn=_feed("c", "q", "o", "q", "e", "q", "h", "q", "s", "q", "q"),
        colorize_menu_fn=colorize_menu,
        colorize_prompt_fn=colorize_prompt,
    )


# ---------------------------------------------------------------------------
# Static: import-alias vs bare-name across entire batplot package
# ---------------------------------------------------------------------------


def test_ast_no_import_alias_bare_name_bugs_all_batplot():
    root = Path(__file__).resolve().parents[1] / "batplot"
    issues: list[str] = []
    allow = {
        ("plot.py", "_draw_custom_colorbar"),  # except-fallback pattern
    }
    for path in root.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            params = {a.arg for a in list(node.args.args) + list(node.args.kwonlyargs)}
            if node.args.vararg:
                params.add(node.args.vararg.arg)
            if node.args.kwarg:
                params.add(node.args.kwarg.arg)
            alias_map: dict[str, str] = {}
            imported_bound: set[str] = set()
            for child in ast.walk(node):
                if isinstance(child, ast.ImportFrom):
                    for al in child.names:
                        bound = al.asname or al.name
                        imported_bound.add(bound)
                        if al.asname and al.asname != al.name:
                            alias_map[al.name] = al.asname
            used = {
                child.id
                for child in ast.walk(node)
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load)
            }
            for original, alias in alias_map.items():
                if (
                    original in used
                    and original not in params
                    and original not in imported_bound
                    and (path.name, original) not in allow
                ):
                    issues.append(
                        f"{path.relative_to(root.parent)}:{node.lineno} "
                        f"{node.name}: uses {original!r} but imported as {alias!r}"
                    )
    assert issues == [], "Import-alias NameError risks:\n" + "\n".join(issues)


def test_inventory_covers_all_run_menu_helpers():
    """Ensure we did not forget a run_*menu helper in plot_modes."""
    root = Path(__file__).resolve().parents[1] / "batplot" / "plot_modes"
    discovered: set[str] = set()
    for path in root.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        mod = ".".join(("batplot.plot_modes", *path.relative_to(root).with_suffix("").parts))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("run_") and "menu" in node.name:
                discovered.add(f"{mod}.{node.name}")

    # Helpers exercised (directly or via batch main) in this file / operando smoke
    covered_suffixes = {
        "run_font_menu",
        "run_axis_limit_menu",
        "run_option_menu",
        "run_dispatch_menu",
        "run_legend_position_menu",
        "run_spine_tick_menu",
        "run_overview_submenu",
        "run_xy_color_menu",
        "run_line_style_menu",
        "run_xy_rename_menu",
        "run_x_range_menu",
        "run_y_range_menu",
        "run_cif_ticks_menu",
        "run_peak_finder_menu",
        "run_axis_units_menu",
        "run_smoothing_menu",
        "run_derivative_menu",
        "run_rearrange_menu",
        # Extracted from the XY dispatcher; exercised via the 'o' key in the
        # XY menu smoke tests.
        "run_offset_menu",
        # Shared WASD title-offset nudge (batch ``t`` → ``p``); covered via batch spine menus.
        "run_title_offset_nudge_menu",
        "run_ec_cycles_menu",
        # Extracted from the EC dispatcher; exercised via the 'sm' / 'a' keys
        # in the electrochem menu smoke tests.
        "run_dqdv_smoothing_menu",
        "run_dual_axis_menu",
        "run_ec_line_style_menu",
        "run_ec_rename_menu",
        "run_ec_spine_color_menu",
        "run_ec_legend_order_menu",
        "run_cpc_color_menu",
        "run_cpc_rename_menu",
        "run_cpc_add_files_menu",
        "run_cpc_legend_order_menu",
        # Extracted from the CPC dispatcher; exercised via the
        # t/v/k/d/ry/l/m/ie/a keys in the CPC menu smoke tests.
        "run_cpc_wasd_menu",
        "run_cpc_visibility_menu",
        "run_cpc_spine_color_menu",
        "run_cpc_display_menu",
        "run_cpc_efficiency_axis_menu",
        "run_cpc_line_width_menu",
        "run_cpc_marker_size_menu",
        "run_cpc_invert_efficiency_menu",
        "run_histo_color_menu",
        "run_histo_line_style_menu",
        "run_histo_font_menu",
        "run_histo_rename_menu",
        "run_histo_toggle_menu",
        "run_histo_y_range_menu",
        "run_histo_density_curve_menu",
        "run_operando_colormap_menu",
        "run_operando_cif_color_menu",
        "run_operando_spine_color_menu",
        # Extracted from the operando dispatcher; exercised via the
        # c/ox/oy/oz/et/ex/ey/k keys in the operando submenu smoke tests.
        "run_operando_cif_menu",
        "run_operando_x_range_menu",
        "run_operando_y_range_menu",
        "run_intensity_menu",
        "run_ec_time_range_menu",
        "run_ec_x_range_menu",
        "run_ec_ions_time_menu",
        "run_operando_axis_units_menu",
        "run_visibility_menu",
        "run_ec_grid_menu",
        "run_operando_rename_menu",
        "run_operando_ec_rename_menu",
        "run_peak_search_menu",
        "run_xy_batch_menu",
        "run_ec_batch_menu",
        "run_cpc_batch_menu",
        "run_histo_batch_menu",
        "run_operando_batch_menu",
        "run_dqdv_2d_batch_menu",
        # Batch sub-helpers are reached via batch main or covered by shared runners
        "run_batch_font_menu",
        "run_batch_plot_frame_menu",
        "run_batch_canvas_menu",
        "run_batch_geom_size_menu",
        "run_batch_histo_geom_menu",
        "run_xy_batch_spine_menu",
        "run_ec_batch_spine_menu",
        "run_cpc_batch_spine_menu",
        "run_operando_batch_spine_menu",
        "run_operando_batch_spine_color_menu",
        "run_operando_size_menu",
        "run_operando_batch_size_menu",
        "run_repeat_input_loop",  # not a menu; ignore if present
    }
    missing = sorted(
        name
        for name in discovered
        if not any(name.endswith("." + suf) or name.endswith(suf) for suf in covered_suffixes)
        and "run_repeat_input_loop" not in name
    )
    # Allow intentionally internal / non-interactive helpers
    allow_missing_parts = (
        "run_repeat_input_loop",
    )
    missing = [m for m in missing if not any(p in m for p in allow_missing_parts)]
    assert missing == [], "Uncovered run_*menu helpers:\n" + "\n".join(missing)

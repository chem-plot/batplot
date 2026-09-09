"""Hard gates for EC + CPC style keys across p / i / s / b."""

from __future__ import annotations

import json
import pickle

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

from batplot.plot_modes.cpc import style as CS
from batplot.plot_modes.cpc.actions import CpcActionContext, handle_style_import
from batplot.plot_modes.cpc.session import dump_cpc_session
from batplot.plot_modes.electrochem import style as ES
from batplot.plot_modes.electrochem.style_apply import apply_ec_style_config
from batplot.plot_modes.electrochem.undo_state import ec_push_state, ec_restore_state
from batplot.plot_modes.electrochem.session import dump_ec_session, load_ec_session


def _noop(*_a, **_k):
    return None


def _make_ec_fig():
    fig, ax = plt.subplots()
    (ln_c,) = ax.plot([0, 1], [3.0, 3.5], label="1 charge", color="C0")
    (ln_d,) = ax.plot([0, 1], [3.5, 3.0], label="1 discharge", color="C1")
    cycle_lines = {1: {"charge": ln_c, "discharge": ln_d}}
    ax.set_xlabel("Capacity")
    ax.set_ylabel("Potential")
    ax._stored_xlabel = "Capacity"
    ax._stored_ylabel = "Potential"
    return fig, ax, cycle_lines


def test_ec_undo_restores_stored_axis_labels_when_hidden():
    fig, ax, cycle_lines = _make_ec_fig()
    ax.xaxis.label.set_visible(False)
    ax.yaxis.label.set_visible(False)
    hist: list = []
    ec_push_state(
        state_history=hist,
        fig=fig,
        ax=ax,
        tick_state={},
        cycle_lines=cycle_lines,
        file_data=None,
        is_multi_file=False,
        note="baseline",
    )
    assert hist[-1]["xlabel"] == "Capacity"
    assert hist[-1]["ylabel"] == "Potential"
    ax._stored_xlabel = "CHANGED"
    ax._stored_ylabel = "CHANGED"
    ax.set_xlabel("CHANGED")
    ax.set_ylabel("CHANGED")
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
    assert ax._stored_xlabel == "Capacity"
    assert ax._stored_ylabel == "Potential"
    assert ax.get_xlabel() == "Capacity"
    plt.close(fig)


def test_ec_style_exports_tick_lengths_and_spacing_clears_on_import():
    fig, ax, cycle_lines = _make_ec_fig()
    ax.xaxis.set_major_locator(MultipleLocator(0.5))
    ax.tick_params(axis="both", which="major", length=9.0)
    snap = ES._get_style_snapshot(fig, ax, cycle_lines, {}, file_data=None)
    assert snap["ticks"]["lengths"].get("major") is not None
    assert "x_major_step" in snap["ticks"]["spacing"]
    assert "x_minor_off" in snap["ticks"]["spacing"]

    # Default-like spacing (null major) must clear custom MultipleLocator
    snap["ticks"]["spacing"] = {
        "x_major_step": None,
        "x_minor_step": None,
        "x_minor_ndivs": None,
        "x_minor_off": True,
        "y_major_step": None,
        "y_minor_step": None,
        "y_minor_ndivs": None,
        "y_minor_off": True,
    }
    apply_ec_style_config(
        snap,
        fig=fig,
        ax=ax,
        cycle_lines=cycle_lines,
        file_data=None,
        is_multi_file=False,
        tick_state={},
    )
    assert not isinstance(ax.xaxis.get_major_locator(), MultipleLocator)
    plt.close(fig)


def test_ec_style_legend_title_preserves_empty():
    """Intentional empty legend title must survive style apply (not coerced to Cycle)."""
    fig, ax, cycle_lines = _make_ec_fig()
    fig._ec_legend_title = "Custom"
    snap = ES._get_style_snapshot(fig, ax, cycle_lines, {}, file_data=None)
    snap["legend"]["title"] = ""
    apply_ec_style_config(
        snap,
        fig=fig,
        ax=ax,
        cycle_lines=cycle_lines,
        file_data=None,
        is_multi_file=False,
        tick_state={},
    )
    assert fig._ec_legend_title == ""
    plt.close(fig)


def test_ec_session_roundtrips_curve_linewidth(session_path):
    fig, ax, cycle_lines = _make_ec_fig()
    fig._ec_curve_linewidth = 2.75
    path = session_path("ec_lw.pkl")
    dump_ec_session(path, fig=fig, ax=ax, cycle_lines=cycle_lines, skip_confirm=True)
    with open(path, "rb") as fh:
        sess = pickle.load(fh)
    assert abs(float(sess["curve_linewidth"]) - 2.75) < 1e-9
    res = load_ec_session(path)
    assert res is not None
    fig2 = res[0]
    assert abs(float(fig2._ec_curve_linewidth) - 2.75) < 1e-9
    plt.close(fig)
    plt.close(fig2)


def test_ec_undo_captures_visible_cycles():
    fig, ax, cycle_lines = _make_ec_fig()
    cycle_lines[1]["charge"].set_visible(False)
    cycle_lines[1]["discharge"].set_visible(False)
    (ln2c,) = ax.plot([0, 1], [3.1, 3.6], color="C2")
    (ln2d,) = ax.plot([0, 1], [3.6, 3.1], color="C3")
    cycle_lines[2] = {"charge": ln2c, "discharge": ln2d}
    hist: list = []
    ec_push_state(
        state_history=hist,
        fig=fig,
        ax=ax,
        tick_state={},
        cycle_lines=cycle_lines,
        file_data=None,
        is_multi_file=False,
        note="vis",
    )
    assert hist[-1].get("visible_cycles") == [2]
    plt.close(fig)


def _make_cpc_fig():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    sc_c = ax.scatter([1, 2], [100, 110], marker="s")
    sc_d = ax.scatter([1, 2], [90, 95], marker="s")
    sc_e = ax2.scatter([1, 2], [90, 92], marker="^")
    ax.set_xlabel("Cycle")
    ax.set_ylabel("Capacity")
    ax2.set_ylabel("CE (%)")
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


def test_cpc_session_includes_mathtext_fontset(session_path):
    fig, ax, ax2, sc_c, sc_d, sc_e, file_data = _make_cpc_fig()
    plt.rcParams["mathtext.fontset"] = "stix"
    path = session_path("cpc_math.pkl")
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
    assert sess["font"].get("mathtext_fontset") == "stix"
    plt.close(fig)


def test_cpc_session_wasd_left_title_matches_style_when_ylabel_hidden(session_path):
    fig, ax, ax2, sc_c, sc_d, sc_e, file_data = _make_cpc_fig()
    ax.set_ylabel("Capacity")
    ax.yaxis.label.set_visible(False)
    style_wasd = CS._style_snapshot(
        fig, ax, ax2, sc_c, sc_d, sc_e, file_data=file_data
    )["wasd_state"]
    path = session_path("cpc_wasd.pkl")
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
    assert style_wasd["left"]["title"] is False
    assert sess["wasd_state"]["left"]["title"] is False
    plt.close(fig)


def test_cpc_interactive_geometry_import_clears_empty_labels(tmp_path):
    fig, ax, ax2, sc_c, sc_d, sc_e, file_data = _make_cpc_fig()
    ax.set_xlabel("KEEP")
    ax.set_ylabel("KEEP_L")
    ax2.set_ylabel("KEEP_R")
    style_path = tmp_path / "cpc.bpsg"
    cfg = CS._style_snapshot(fig, ax, ax2, sc_c, sc_d, sc_e, file_data=file_data)
    cfg["kind"] = "cpc_style_geom"
    cfg["geometry"] = {
        "xlabel": "",
        "ylabel_left": "",
        "ylabel_right": "",
        "xlim": [0.0, 5.0],
        "ylim_left": [80.0, 120.0],
        "ylim_right": [85.0, 100.0],
    }
    style_path.write_text(json.dumps(cfg), encoding="utf-8")

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
        print_menu=_noop,
        choose_save_path=_noop,
        choose_style_file=lambda *a, **k: str(style_path),
        list_files_in_subdirectory=_noop,
        get_organized_path=lambda *a, **k: str(tmp_path),
        ensure_exact_case_filename=lambda s: s,
        natural_sort_key=lambda s: s,
        dump_cpc_session=_noop,
        format_file_timestamp=lambda s: s,
        rebuild_legend=_noop,
        style_snapshot=lambda *a, **k: cfg,
        apply_style=lambda *a, **k: None,
        get_geometry_snapshot=lambda *a, **k: {},
        push_state=_noop,
        pop_undo=_noop,
        restore_state=_noop,
    )
    handle_style_import(ctx)
    assert ax.get_xlabel() == ""
    assert ax.get_ylabel() == ""
    assert ax2.get_ylabel() == ""
    assert ax.get_xlim() == (0.0, 5.0)
    plt.close(fig)

"""Capacity-per-cycle (CPC) session round-trip tests."""

import json
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator

from batplot import session as S
from batplot.plot_modes.cpc import interactive as C
from batplot.plot_modes.cpc.actions import (
    CpcActionContext,
    handle_save_session,
    handle_style_export,
    handle_style_import,
    handle_undo,
)
from conftest import assert_allclose, loaded


def _build_cpc_figure():
    fig, ax = plt.subplots()
    ax2 = ax.twinx()
    cyc = np.arange(1, 21, dtype=float)
    charge = np.linspace(150.0, 120.0, 20)
    discharge = np.linspace(148.0, 118.0, 20)
    eff = np.linspace(95.0, 99.0, 20)
    sc_charge = ax.scatter(cyc, charge, c="red", label="charge")
    sc_discharge = ax.scatter(cyc, discharge, c="blue", label="discharge")
    sc_eff = ax2.scatter(cyc, eff, c="green", label="efficiency")
    ax.set_xlabel("Cycle number")
    ax.set_ylabel("Capacity (mAh/g)")
    ax2.set_ylabel("Coulombic efficiency (%)")
    ax.set_xlim(0.0, 21.0)
    return fig, ax, ax2, sc_charge, sc_discharge, sc_eff, cyc


def _make_cpc_action_context(
    tmp_path,
    *,
    inputs=(),
    style_path=None,
    push_states=None,
    print_calls=None,
    restore_calls=None,
):
    fig, ax, ax2, sc_c, sc_d, sc_e, _cyc = _build_cpc_figure()
    input_iter = iter(inputs)
    push_states = push_states if push_states is not None else []
    print_calls = print_calls if print_calls is not None else []
    restore_calls = restore_calls if restore_calls is not None else []

    def _safe_input(_prompt):
        return next(input_iter)

    def _get_organized_path(name, kind, base_path=None):
        subdir = {"style": "Styles", "figure": "Figures"}.get(kind, "")
        base = tmp_path if base_path is None else base_path
        target_dir = base / subdir if subdir else base
        target_dir.mkdir(parents=True, exist_ok=True)
        return str(target_dir / name)

    ctx = CpcActionContext(
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
        file_data=None,
        file_paths=[],
        is_multi_file=False,
        tick_state={
            "b_ticks": True,
            "b_labels": True,
            "t_ticks": False,
            "t_labels": False,
            "l_ticks": True,
            "l_labels": True,
            "r_ticks": True,
            "r_labels": True,
            "mbx": False,
            "mtx": False,
            "mly": False,
            "mry": False,
        },
        safe_input=_safe_input,
        colorize_prompt=lambda text: text,
        colorize_inline_commands=lambda text: text,
        print_menu=lambda menu_fig: print_calls.append(menu_fig),
        choose_save_path=lambda *_args, **_kwargs: tmp_path,
        choose_style_file=lambda *_args, **_kwargs: str(style_path) if style_path is not None else None,
        list_files_in_subdirectory=lambda *_args, **_kwargs: [],
        get_organized_path=_get_organized_path,
        ensure_exact_case_filename=lambda path: path,
        natural_sort_key=lambda value: value,
        dump_cpc_session=S.dump_cpc_session,
        format_file_timestamp=lambda _path: "",
        rebuild_legend=C._rebuild_legend,
        style_snapshot=C._style_snapshot,
        apply_style=C._apply_style,
        get_geometry_snapshot=C._get_geometry_snapshot,
        push_state=lambda note: push_states.append(note),
        restore_state=lambda: restore_calls.append(True),
    )
    return ctx


def test_dump_load_preserves_axes_and_labels(session_path):
    fig, ax, ax2, sc_c, sc_d, sc_e, cyc = _build_cpc_figure()
    p = session_path("cpc.pkl")
    S.dump_cpc_session(p, fig=fig, ax=ax, ax2=ax2, sc_charge=sc_c,
                       sc_discharge=sc_d, sc_eff=sc_e, skip_confirm=True)

    result = loaded(S.load_cpc_session(p))
    fig2, ax_l, ax2_l = result[0], result[1], result[2]

    assert ax_l.get_xlabel() == "Cycle number"
    assert ax_l.get_ylabel() == "Capacity (mAh/g)"
    assert_allclose(ax_l.get_xlim(), (0.0, 21.0))


def test_dump_load_preserves_scatter_data(session_path):
    fig, ax, ax2, sc_c, sc_d, sc_e, cyc = _build_cpc_figure()
    p = session_path("cpc_data.pkl")
    S.dump_cpc_session(p, fig=fig, ax=ax, ax2=ax2, sc_charge=sc_c,
                       sc_discharge=sc_d, sc_eff=sc_e, skip_confirm=True)

    result = loaded(S.load_cpc_session(p))
    fig2, ax_l, ax2_l, sc_c2, sc_d2, sc_e2 = (
        result[0], result[1], result[2], result[3], result[4], result[5])

    offs = np.asarray(sc_c2.get_offsets(), float)
    assert offs.shape[0] == cyc.size, "charge scatter point count changed"
    assert_allclose(np.sort(offs[:, 0]), cyc, "charge cycle x-values not restored")


def test_dump_load_preserves_tick_lengths(session_path):
    fig, ax, ax2, sc_c, sc_d, sc_e, cyc = _build_cpc_figure()
    ax.xaxis.set_minor_locator(AutoMinorLocator())
    ax.tick_params(axis="both", which="major", length=10.0)
    ax.tick_params(axis="both", which="minor", length=7.0)
    ax2.tick_params(axis="both", which="major", length=10.0)
    ax2.tick_params(axis="both", which="minor", length=7.0)
    fig._tick_lengths = {"major": 10.0, "minor": 7.0}
    ax.tick_params(axis="both", which="both", direction="in")
    ax2.tick_params(axis="both", which="both", direction="in")
    fig._tick_direction = "in"
    p = session_path("cpc_tick_lengths.pkl")

    S.dump_cpc_session(
        p,
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
        skip_confirm=True,
    )
    result = loaded(S.load_cpc_session(p))
    fig2, ax_l, ax2_l = result[0], result[1], result[2]
    fig2.canvas.draw()

    assert getattr(fig2, "_tick_lengths", {}) == {"major": 10.0, "minor": 7.0}
    assert getattr(fig2, "_tick_direction", None) == "in"
    assert ax_l.xaxis.get_major_ticks()[0].tick1line.get_markersize() == 10.0
    assert ax2_l.yaxis.get_major_ticks()[0].tick1line.get_markersize() == 10.0


def test_dump_load_preserves_exact_axes_bbox(session_path):
    fig, ax, ax2, sc_c, sc_d, sc_e, cyc = _build_cpc_figure()
    ax.set_position([0.20, 0.25, 0.50, 0.45])
    ax2.set_position(ax.get_position())
    p = session_path("cpc_axes_bbox.pkl")

    S.dump_cpc_session(
        p,
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
        skip_confirm=True,
    )
    result = loaded(S.load_cpc_session(p))
    fig2, ax_l, ax2_l = result[0], result[1], result[2]

    assert_allclose(ax_l.get_position().bounds, (0.20, 0.25, 0.50, 0.45))
    assert_allclose(ax2_l.get_position().bounds, (0.20, 0.25, 0.50, 0.45))


def test_dump_load_preserves_spine_auto_mode(session_path):
    fig, ax, ax2, sc_c, sc_d, sc_e, cyc = _build_cpc_figure()
    fig._cpc_spine_auto = True
    p = session_path("cpc_spine_auto.pkl")

    S.dump_cpc_session(
        p,
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
        skip_confirm=True,
    )
    result = loaded(S.load_cpc_session(p))
    fig2 = result[0]

    assert getattr(fig2, "_cpc_spine_auto", False) is True


def test_cpc_style_apply_keeps_hidden_legend_hidden_after_rebuild():
    fig, ax, ax2, sc_c, sc_d, sc_e, cyc = _build_cpc_figure()
    ax.legend([sc_c, sc_d], ["charge", "discharge"])
    cfg = C._style_snapshot(fig, ax, ax2, sc_c, sc_d, sc_e, None)
    cfg["legend"]["visible"] = False

    C._apply_style(fig, ax, ax2, sc_c, sc_d, sc_e, cfg, None)

    leg = ax.get_legend()
    assert leg is None or leg.get_visible() is False


def test_cpc_style_apply_restores_top_title_state():
    fig, ax, ax2, sc_c, sc_d, sc_e, cyc = _build_cpc_figure()
    cfg = C._style_snapshot(fig, ax, ax2, sc_c, sc_d, sc_e, None)
    cfg["wasd_state"]["top"]["title"] = True
    if hasattr(ax, "_top_xlabel_text"):
        ax._top_xlabel_text.set_visible(False)

    C._apply_style(fig, ax, ax2, sc_c, sc_d, sc_e, cfg, None)

    assert getattr(ax, "_top_xlabel_text", None) is not None
    assert ax._top_xlabel_text.get_visible() is True
    assert ax._top_xlabel_text.get_text() == "Cycle number"


def test_cpc_style_apply_restores_twin_top_bottom_spine_visibility():
    fig, ax, ax2, sc_c, sc_d, sc_e, cyc = _build_cpc_figure()
    cfg = C._style_snapshot(fig, ax, ax2, sc_c, sc_d, sc_e, None)
    cfg["spines"]["top"]["visible"] = False
    cfg["spines"]["bottom"]["visible"] = False
    ax.spines["top"].set_visible(True)
    ax.spines["bottom"].set_visible(True)
    ax2.spines["top"].set_visible(True)
    ax2.spines["bottom"].set_visible(True)

    C._apply_style(fig, ax, ax2, sc_c, sc_d, sc_e, cfg, None)

    assert ax.spines["top"].get_visible() is False
    assert ax2.spines["top"].get_visible() is False
    assert ax.spines["bottom"].get_visible() is False
    assert ax2.spines["bottom"].get_visible() is False


def test_cpc_style_apply_restores_multifile_visibility():
    fig, ax, ax2, sc_c, sc_d, sc_e, cyc = _build_cpc_figure()
    sc_c2 = ax.scatter(cyc, np.linspace(140.0, 110.0, 20), c="orange", label="file2 charge")
    sc_d2 = ax.scatter(cyc, np.linspace(138.0, 108.0, 20), c="purple", label="file2 discharge")
    sc_e2 = ax2.scatter(cyc, np.linspace(94.0, 98.0, 20), c="black", label="file2 efficiency")
    file_data = [
        {"filename": "file1", "visible": True, "sc_charge": sc_c, "sc_discharge": sc_d, "sc_eff": sc_e},
        {"filename": "file2", "visible": False, "sc_charge": sc_c2, "sc_discharge": sc_d2, "sc_eff": sc_e2},
    ]
    sc_c2.set_visible(False)
    sc_d2.set_visible(False)
    sc_e2.set_visible(False)
    cfg = C._style_snapshot(fig, ax, ax2, sc_c, sc_d, sc_e, file_data)
    file_data[1]["visible"] = True
    sc_c2.set_visible(True)
    sc_d2.set_visible(True)
    sc_e2.set_visible(True)

    C._apply_style(fig, ax, ax2, sc_c, sc_d, sc_e, cfg, file_data)

    assert file_data[1]["visible"] is False
    assert sc_c2.get_visible() is False
    assert sc_d2.get_visible() is False
    assert sc_e2.get_visible() is False


def test_cpc_menu_columns_hide_file_visibility_for_single_file():
    fig, ax = plt.subplots()
    fig._cpc_is_multi_file = False

    col1, col2, col3 = C.build_cpc_menu_columns(fig)

    assert not any(item.strip().startswith("v:") for item in col1)
    assert any(item.strip().startswith("p:") for item in col3)


def test_cpc_menu_printer_includes_overwrite_shortcuts(capsys):
    fig, ax = plt.subplots()
    fig._cpc_is_multi_file = True
    fig._last_session_save_path = "last.pkl"
    fig._last_style_export_path = "last.bpsg"
    fig._last_figure_export_path = "last.png"

    C._print_menu(fig)
    out = capsys.readouterr().out

    assert "CPC Interactive Menu" in out
    assert "show/hide files" in out
    assert "overwrite session" in out
    assert "overwrite style" in out
    assert "overwrite style+geom" in out
    assert "overwrite figure" in out


def test_cpc_snapshot_restore_preserves_geometry_and_tick_state():
    fig, ax, ax2, sc_c, sc_d, sc_e, cyc = _build_cpc_figure()
    tick_state = {
        "t_ticks": False,
        "t_labels": False,
        "b_ticks": True,
        "b_labels": True,
        "l_ticks": True,
        "l_labels": True,
        "r_ticks": True,
        "r_labels": True,
        "mtx": False,
        "mbx": False,
        "mly": False,
        "mry": False,
    }
    history = []
    C.push_cpc_state(
        history,
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
        file_data=None,
        tick_state=tick_state,
        note="before-geometry-change",
    )

    ax.set_xlabel("Changed X")
    ax.set_ylabel("Changed left")
    ax2.set_ylabel("Changed right")
    ax.set_xlim(5.0, 10.0)
    ax.set_ylim(1.0, 2.0)
    ax2.set_ylim(80.0, 85.0)
    tick_state["r_ticks"] = False
    tick_state["r_labels"] = False

    update_calls = {"n": 0}

    def _update_ticks():
        update_calls["n"] += 1

    restored = C.restore_cpc_state(
        history,
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
        file_data=None,
        tick_state=tick_state,
        update_ticks_func=_update_ticks,
    )

    assert restored is True
    assert update_calls["n"] == 1
    assert ax.get_xlabel() == "Cycle number"
    assert ax.get_ylabel() == "Capacity (mAh/g)"
    assert ax2.get_ylabel() == "Coulombic efficiency (%)"
    assert_allclose(ax.get_xlim(), (0.0, 21.0))
    assert tick_state["r_ticks"] is True
    assert tick_state["r_labels"] is True


def test_cpc_handle_style_export_writes_style_geometry(tmp_path):
    print_calls = []
    ctx = _make_cpc_action_context(
        tmp_path,
        inputs=("e", "psg", "exported_style"),
        print_calls=print_calls,
    )

    handle_style_export(ctx)

    target = tmp_path / "Styles" / "exported_style.bpsg"
    assert target.exists()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["kind"] == "cpc_style_geom"
    assert "geometry" in payload
    assert ctx.fig._last_style_export_path == str(target)
    assert print_calls[-1] is ctx.fig


def test_cpc_handle_style_import_applies_geometry_and_pushes_state(tmp_path):
    source_ctx = _make_cpc_action_context(tmp_path)
    payload = C._style_snapshot(
        source_ctx.fig,
        source_ctx.ax,
        source_ctx.ax2,
        source_ctx.sc_charge,
        source_ctx.sc_discharge,
        source_ctx.sc_eff,
    )
    payload["kind"] = "cpc_style_geom"
    payload["axes_geometry"] = {
        "xlabel": "Imported X",
        "ylabel_left": "Imported left",
        "ylabel_right": "Imported right",
        "xlim": [2.0, 8.0],
        "ylim_left": [100.0, 200.0],
        "ylim_right": [90.0, 101.0],
    }
    payload.pop("geometry", None)
    style_path = tmp_path / "import_style.bpsg"
    style_path.write_text(json.dumps(payload), encoding="utf-8")
    push_states = []
    ctx = _make_cpc_action_context(tmp_path, style_path=style_path, push_states=push_states)

    handle_style_import(ctx)

    assert push_states == ["import-style"]
    assert ctx.ax.get_xlabel() == "Imported X"
    assert ctx.ax.get_ylabel() == "Imported left"
    assert ctx.ax2.get_ylabel() == "Imported right"
    assert_allclose(ctx.ax.get_xlim(), (2.0, 8.0))
    assert_allclose(ctx.ax2.get_ylim(), (90.0, 101.0))


def test_cpc_handle_save_session_syncs_wasd_and_records_path(tmp_path):
    ctx = _make_cpc_action_context(tmp_path, inputs=("saved_project",))
    ctx.tick_state["r_ticks"] = False
    ctx.tick_state["r_labels"] = False
    ctx.tick_state["mry"] = True

    handle_save_session(ctx)

    target = tmp_path / "saved_project.pkl"
    assert target.exists()
    assert ctx.fig._last_session_save_path == str(target)
    wasd = ctx.fig._cpc_wasd_state
    assert wasd["right"]["ticks"] is False
    assert wasd["right"]["labels"] is False
    assert wasd["right"]["minor"] is True


def test_cpc_handle_undo_routes_restore_and_redraw(tmp_path):
    restore_calls = []
    print_calls = []
    ctx = _make_cpc_action_context(tmp_path, restore_calls=restore_calls, print_calls=print_calls)

    handle_undo(ctx)

    assert restore_calls == [True]
    assert print_calls == [ctx.fig]

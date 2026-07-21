"""Tests for batch session mode."""

from __future__ import annotations

import json
from pathlib import Path

import pickle
from types import SimpleNamespace

import numpy as np
import matplotlib.pyplot as plt
import pytest

from batplot import session as S
from batplot.plot_modes.batch_session.batch_commands import (
    append_batch_io_shortcuts,
    batch_quit_confirm,
    prompt_style_source_index,
    run_batch_overwrite_sessions,
    run_batch_save_all,
)
from batplot.plot_modes.batch_session.batch_io import parse_panel_selection, prompt_panel_indices
from batplot.plot_modes.batch_session.common import SyncUndoStacks, session_figure_title, set_panel_figure_title
from batplot.plot_modes.batch_session.kinds import detect_session_kind, kind_label
from batplot.plot_modes.batch_session.batch_menu_helpers import (
    batch_io_menu_options,
    summarize_values,
)
from batplot.plot_modes.batch_session.histo_batch_helpers import (
    apply_plot_frame_to_all,
    frame_inches,
    parse_size_spec,
)
from batplot.plot_modes.batch_session.load import HistoPanel, load_batch_panels, validate_same_kind
from batplot.plot_modes.batch_session.xy_batch_helpers import dump_xy_panel
from batplot.plot_modes.histo.plot import build_histo_state, create_histo_figure
from batplot.plot_modes.histo.session import save_histo_session
from batplot.plot_modes.histo.wizard import HistoSetup
from batplot.plot_modes.histo.load import build_bin_edges
from conftest import assert_allclose, loaded


def test_parse_panel_selection_all():
    assert parse_panel_selection("all", 5) == [0, 1, 2, 3, 4]
    assert parse_panel_selection("a", 3) == [0, 1, 2]


def test_parse_panel_selection_ranges():
    assert parse_panel_selection("1 3", 5) == [0, 2]
    assert parse_panel_selection("2-4", 5) == [1, 2, 3]
    assert parse_panel_selection("q", 5) is None


def test_sync_undo_push_indices():
    undo = SyncUndoStacks(4)
    undo.push_all(["b0", "b1", "b2", "b3"])
    undo.push_all(["a0", "a1", "a2", "a3"])
    undo.push_all(["c0", "c1", "c2", "c3"])
    restored = []
    undo.undo_all(lambda i, snap: restored.append((i, snap)))
    assert restored == [(0, "c0"), (1, "c1"), (2, "c2"), (3, "c3")]


def test_sync_undo_blocks_baseline_only():
    """Batch undo must not pop the initial menu-entry snapshot when no edits were made."""
    undo = SyncUndoStacks(2)
    undo.push_all(["baseline_a", "baseline_b"])
    assert undo.can_undo() is False
    undo.push_all(["pre_edit_a", "pre_edit_b"])
    assert undo.can_undo() is True
    restored = []
    undo.undo_all(lambda i, snap: restored.append((i, snap)))
    assert restored == [(0, "pre_edit_a"), (1, "pre_edit_b")]
    assert undo.can_undo() is False


def test_detect_xy_kind(tmp_path):
    p = tmp_path / "xy.pkl"
    p.write_bytes(
        pickle.dumps({"version": 1, "x_data": [[1.0]], "y_data": [[1.0]]})
    )
    assert detect_session_kind(str(p)) == "xy"


def test_detect_histo_kind(tmp_path):
    p = tmp_path / "histo.pkl"
    p.write_bytes(pickle.dumps({"kind": "histo", "state": {}}))
    assert detect_session_kind(str(p)) == "histo"


def test_validate_same_kind_ok(tmp_path):
    a = tmp_path / "a.pkl"
    b = tmp_path / "b.pkl"
    payload = {"kind": "cpc", "version": 2}
    a.write_bytes(pickle.dumps(payload))
    b.write_bytes(pickle.dumps(payload))
    kind, _kinds, err = validate_same_kind([str(a), str(b)])
    assert err is None
    assert kind == "cpc"


def test_validate_mixed_kind_fails(tmp_path, capsys):
    a = tmp_path / "a.pkl"
    b = tmp_path / "b.pkl"
    a.write_bytes(pickle.dumps({"kind": "cpc", "version": 2}))
    b.write_bytes(pickle.dumps({"version": 1, "x_data": [1], "y_data": [1]}))
    kind, _kinds, err = validate_same_kind([str(a), str(b)])
    assert err == 1
    assert kind is None
    out = capsys.readouterr().out
    assert "same plot mode" in out
    assert kind_label("cpc") in out
    assert kind_label("xy") in out


def test_append_batch_io_shortcuts_session_only():
    opts: list[str] = []
    panel = type("P", (), {"fig": type("F", (), {"_last_session_save_path": "/tmp/a.pkl"})()})()
    append_batch_io_shortcuts(opts, [panel])
    assert "os: overwrite sessions" in opts
    assert not any("ops" in o for o in opts)


def test_batch_quit_confirm_save(monkeypatch):
    monkeypatch.setattr(
        "batplot.plot_modes.batch_session.batch_commands.safe_input",
        lambda *_a, **_k: "s",
    )
    assert batch_quit_confirm(allow_export=True) == "s"


def test_batch_quit_confirm_save_all_alias(monkeypatch):
    monkeypatch.setattr(
        "batplot.plot_modes.batch_session.batch_commands.safe_input",
        lambda *_a, **_k: "s all",
    )
    assert batch_quit_confirm(allow_export=True) is None


def test_run_batch_save_all_calls_each_panel(capsys, monkeypatch):
    saved: list[str] = []

    class Panel:
        def __init__(self, name: str):
            self.path = f"/tmp/{name}.pkl"
            self.fig = type("F", (), {})()

    panels = [Panel("a"), Panel("b")]
    monkeypatch.setattr(
        "batplot.plot_modes.batch_session.batch_io.safe_input",
        lambda *_a, **_k: "y",
    )
    run_batch_save_all(panels, lambda _p, path: saved.append(path))
    assert saved == ["/tmp/a.pkl", "/tmp/b.pkl"]
    out = capsys.readouterr().out
    assert "Saved [1]" in out
    assert "Saved [2]" in out


def _make_xy_pkl(path: str) -> None:
    x = np.linspace(10.0, 50.0, 101)
    y = np.sin(x / 5.0)
    fig, ax = plt.subplots()
    ax.plot(x, y, label="c1")
    args = SimpleNamespace(stack=False, xaxis="2theta")
    S.dump_session(
        path,
        fig=fig,
        ax=ax,
        x_data_list=[x],
        y_data_list=[y],
        orig_y=[y],
        x_full_list=[x],
        raw_y_full_list=[y],
        offsets_list=[0.0],
        labels=["c1"],
        delta=0.0,
        args=args,
        tick_state={},
        skip_confirm=True,
    )
    plt.close(fig)


def test_load_batch_xy_panels_and_dump(tmp_path):
    a = tmp_path / "a.pkl"
    b = tmp_path / "b.pkl"
    _make_xy_pkl(str(a))
    _make_xy_pkl(str(b))

    result = load_batch_panels([str(a), str(b)])
    assert not isinstance(result, int)
    assert result.kind == "xy"
    assert len(result.panels) == 2

    out = tmp_path / "a_saved.pkl"
    dump_xy_panel(result.panels[0], str(out))
    assert out.is_file()
    reloaded = loaded(S.load_xy_session(str(out)))
    assert len(reloaded[2].get("y_data_list") or []) == 1


def test_load_batch_histo_panels(tmp_path):
    values = np.array([1.0, 2.0, 2.5, 3.0, 8.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="Length",
        values=values,
        xmin=float(edges[0]),
        xmax=float(edges[-1]),
        bin_edges=edges,
    )
    csv_path = tmp_path / "data.csv"
    csv_path.write_text("Length\n1\n2\n2.5\n3\n8\n", encoding="utf-8")

    paths = []
    for name in ("h1.pkl", "h2.pkl"):
        state = build_histo_state(setup, source_path=str(csv_path))
        fig, ax, _meta = create_histo_figure(state)
        p = tmp_path / name
        save_histo_session(fig, ax, state, str(p))
        plt.close(fig)
        paths.append(str(p))

    result = load_batch_panels(paths)
    assert not isinstance(result, int)
    assert result.kind == "histo"
    assert len(result.panels) == 2
    for panel in result.panels:
        assert getattr(panel.fig, "_last_session_save_path", None)
        assert panel.state.source_path == str(csv_path)


def test_prompt_style_source_index_single_panel():
    panel = type("P", (), {"path": "a.pkl", "fig": object()})()
    assert prompt_style_source_index([panel]) == 0


def test_run_batch_overwrite_sessions_uses_loaded_path(tmp_path, monkeypatch):
    saved: list[tuple[str, str]] = []

    class Panel:
        def __init__(self, path: str):
            self.path = path
            self.fig = type("F", (), {})()

    p1 = Panel(str(tmp_path / "one.pkl"))
    p2 = Panel(str(tmp_path / "two.pkl"))

    def _save(panel, path):
        saved.append((panel.path, path))

    monkeypatch.setattr(
        "batplot.plot_modes.batch_session.batch_commands.confirm_previous_path",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "batplot.plot_modes.batch_session.batch_commands.safe_input",
        lambda *a, **k: "y",
    )
    run_batch_overwrite_sessions([p1, p2], _save)
    assert saved == [(p1.path, p1.path), (p2.path, p2.path)]


def test_append_batch_io_shortcuts_figure_overwrite():
    opts: list[str] = []
    fig = type("F", (), {"_last_figure_export_path": "/tmp/out.png"})()
    panel = type("P", (), {"fig": fig})()
    append_batch_io_shortcuts(opts, [panel])
    assert "oe: overwrite figures" in opts


def test_append_batch_io_shortcuts_all_overwrites():
    opts: list[str] = []
    fig = type(
        "F",
        (),
        {
            "_last_session_save_path": "/tmp/a.pkl",
            "_last_figure_export_path": "/tmp/out.png",
            "_last_style_export_path": "/tmp/style.bps",
        },
    )()
    panel = type("P", (), {"fig": fig})()
    append_batch_io_shortcuts(opts, [panel])
    assert "os: overwrite sessions" in opts
    assert "oe: overwrite figures" in opts
    assert "ops: overwrite style" in opts
    assert "opsg: overwrite style+geom" in opts


def test_batch_io_menu_options_labels():
    opts = batch_io_menu_options()
    assert "e: export figures" in opts
    assert "p: export style" in opts
    assert "i: import style" in opts
    assert "s: save sessions" in opts
    assert "b: undo" in opts
    assert not any("(" in o for o in opts)


def test_summarize_values_single_and_multi():
    assert summarize_values([0.95, 0.95]) == "0.95"
    assert summarize_values([0.8, 0.95]) == "0.8 / 0.95"


def test_parse_size_spec_parses_wh_and_3x3():
    assert parse_size_spec("3 3", 6.0, 4.0) == (3.0, 3.0)
    assert parse_size_spec("3x3", 6.0, 4.0) == (3.0, 3.0)
    assert parse_size_spec("q", 6.0, 4.0) is None


def test_apply_plot_frame_to_all_uses_absolute_inches():
    fig1, ax1 = plt.subplots(figsize=(8, 5.5))
    fig2, ax2 = plt.subplots(figsize=(10, 6))
    values = np.array([1.0, 2.0, 3.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="L",
        values=values,
        xmin=0.0,
        xmax=10.0,
        bin_edges=edges,
    )
    s1 = build_histo_state(setup)
    s2 = build_histo_state(setup)
    p1 = HistoPanel(path="a.pkl", fig=fig1, ax=ax1, state=s1)
    p2 = HistoPanel(path="b.pkl", fig=fig2, ax=ax2, state=s2)
    apply_plot_frame_to_all([p1, p2], 3.0, 3.0)
    w1, h1 = frame_inches(fig1, ax1)
    w2, h2 = frame_inches(fig2, ax2)
    plt.close(fig1)
    plt.close(fig2)
    assert w1 == pytest.approx(3.0, abs=0.05)
    assert h1 == pytest.approx(3.0, abs=0.05)
    assert w2 == pytest.approx(3.0, abs=0.05)
    assert h2 == pytest.approx(3.0, abs=0.05)


def test_session_figure_title_uses_pkl_basename():
    assert session_figure_title("/path/to/Length_histo.pkl") == "Length_histo.pkl"
    assert session_figure_title("plot.pkl") == "plot.pkl"


def test_set_panel_figure_title_uses_manager():
    calls: list[str] = []

    class _Manager:
        def set_window_title(self, title: str) -> None:
            calls.append(title)

    class _Canvas:
        manager = _Manager()

    class _Fig:
        canvas = _Canvas()

    panel = SimpleNamespace(path="/tmp/my_session.pkl", fig=_Fig())
    set_panel_figure_title(panel)
    assert calls == ["my_session.pkl"]


def test_prompt_panel_indices_enter_means_all(monkeypatch):
    panels = [object(), object(), object()]
    monkeypatch.setattr(
        "batplot.plot_modes.batch_session.batch_io.safe_input",
        lambda *_a, **_k: "",
    )
    assert prompt_panel_indices(panels, verb="test") == [0, 1, 2]


def test_run_batch_export_figures_one_panel(tmp_path, monkeypatch):
    exported: list[tuple[int, str]] = []

    class Panel:
        def __init__(self, name: str):
            self.path = str(tmp_path / name)
            self.fig = type("F", (), {})()

    panels = [Panel("histo_a.pkl"), Panel("histo_b.pkl")]

    monkeypatch.setattr(
        "batplot.plot_modes.batch_session.batch_io.prompt_panel_indices",
        lambda *_a, **_k: [0],
    )
    monkeypatch.setattr(
        "batplot.plot_modes.batch_session.batch_figure_io.choose_save_path",
        lambda *_a, **_k: str(tmp_path),
    )
    monkeypatch.setattr(
        "batplot.plot_modes.batch_session.batch_figure_io.list_files_in_subdirectory",
        lambda *_a, **_k: [],
    )
    monkeypatch.setattr(
        "batplot.plot_modes.batch_session.batch_figure_io.safe_input",
        lambda *_a, **_k: "",
    )

    from batplot.plot_modes.batch_session.batch_figure_io import run_batch_export_figures

    run_batch_export_figures(
        panels,
        lambda panel, path: exported.append((0, path)),
    )
    assert len(exported) == 1
    assert exported[0][1].endswith("histo_a.svg")


BATCH_MENU_FILES = (
    "batplot/plot_modes/batch_session/menu_histo.py",
    "batplot/plot_modes/batch_session/menu_xy.py",
    "batplot/plot_modes/batch_session/menu_ec.py",
    "batplot/plot_modes/batch_session/menu_cpc.py",
    "batplot/plot_modes/batch_session/menu_operando.py",
)


def test_all_batch_menus_share_io_handlers():
    """XY, EC, CPC, operando, and histo batch menus must use the same I/O layer."""
    repo = Path(__file__).resolve().parents[1]
    required = (
        "from .batch_menu_io import",
        "batch_quit_or_save_all",
        "batch_save_sessions",
        "batch_export_figures",
        "batch_import_style",
        "batch_export_style",
        "batch_overwrite_sessions",
        "batch_overwrite_figures",
        # I/O labels come from batch_options_menu_column → batch_io_menu_options
        "batch_options_menu_column(",
    )
    forbidden = ("s all", "default_all", "run_batch_save_sessions", "run_batch_save_all")
    for rel in BATCH_MENU_FILES:
        text = (repo / rel).read_text(encoding="utf-8")
        for token in required:
            assert token in text, f"{rel} missing {token!r}"
        for token in forbidden:
            assert token not in text, f"{rel} still contains forbidden {token!r}"


def test_batch_histo_toggle_syncs_from_reference():
    """Batch histo h-submenu toggles ref panel then copies state to all panels."""
    values = np.array([1.0, 2.0, 3.0])
    edges = build_bin_edges(0.0, 10.0, bin_width=2.0, n_bins=None)
    setup = HistoSetup(
        column_index=1,
        column_name="L",
        values=values,
        xmin=0.0,
        xmax=10.0,
        bin_edges=edges,
    )
    fig1, ax1, _ = create_histo_figure(build_histo_state(setup))
    fig2, ax2, _ = create_histo_figure(build_histo_state(setup))
    p1 = HistoPanel(path="a.pkl", fig=fig1, ax=ax1, state=build_histo_state(setup))
    p2 = HistoPanel(path="b.pkl", fig=fig2, ax=ax2, state=build_histo_state(setup))
    panels = [p1, p2]
    ref = panels[0]
    initial = ref.state.style.show_grid
    ref.state.style.show_grid = not initial
    for p in panels:
        p.state.style.show_grid = ref.state.style.show_grid
    assert p2.state.style.show_grid is (not initial)
    plt.close(fig1)
    plt.close(fig2)


def test_batch_cpc_capture_includes_geometry():
    from test_cpc_roundtrip import _build_cpc_figure
    from batplot.plot_modes.batch_session.load import CpcPanel
    from batplot.plot_modes.batch_session.menu_cpc import _capture_panel, _restore_panel

    fig, ax, ax2, sc_c, sc_d, sc_e, _cyc = _build_cpc_figure()
    panel = CpcPanel(
        path="cpc.pkl",
        fig=fig,
        ax=ax,
        ax2=ax2,
        sc_charge=sc_c,
        sc_discharge=sc_d,
        sc_eff=sc_e,
        file_data=None,
    )
    snap = _capture_panel(panel)
    assert "geometry" in snap
    assert snap["geometry"]["xlabel"] == ax.get_xlabel()

    ax.set_xlabel("Changed")
    ax.set_xlim(3.0, 7.0)
    _restore_panel(panel, snap)
    assert ax.get_xlabel() == snap["geometry"]["xlabel"]
    assert_allclose(ax.get_xlim(), tuple(snap["geometry"]["xlim"]))
    plt.close(fig)


def test_batch_xy_restore_applies_canvas_size(tmp_path):
    from batplot.plot_modes.batch_session.menu_xy import _apply_style_path, _capture_panel
    from batplot.plot_modes.batch_session.load import XyPanel

    a = tmp_path / "a.pkl"
    _make_xy_pkl(str(a))
    result = load_batch_panels([str(a)])
    assert not isinstance(result, int)
    panel = result.panels[0]
    snap = _capture_panel(panel)
    w, h = panel.fig.get_size_inches()
    panel.fig.set_size_inches(w + 2.0, h + 1.0)
    style_path = tmp_path / "style.bpsg"
    style_path.write_text(json.dumps(snap), encoding="utf-8")
    _apply_style_path(panel, str(style_path), keep_canvas_fixed=False)
    w2, h2 = panel.fig.get_size_inches()
    expected = snap["figure"]["size"]
    assert w2 == pytest.approx(float(expected[0]), abs=0.05)
    assert h2 == pytest.approx(float(expected[1]), abs=0.05)
    plt.close(panel.fig)


def test_batch_xy_export_writes_to_given_path(tmp_path):
    """Batch XY p export must use overwrite_path (no interactive re-prompt)."""
    from batplot.plot_modes.batch_session.menu_xy import _capture_panel
    from batplot.plot_modes.xy.style import export_style_config
    from batplot.plot_modes.xy.interactive import normalize_xy_menu_kwargs

    a = tmp_path / "a.pkl"
    _make_xy_pkl(str(a))
    result = load_batch_panels([str(a)])
    panel = result.panels[0]
    out = tmp_path / "panel.bpsg"
    kw = normalize_xy_menu_kwargs(panel.menu_kwargs)
    tick_state = {}
    cif_globals = kw.get("cif_globals") or {}
    export_style_config(
        str(out),
        panel.fig,
        panel.ax,
        kw.get("y_data_list") or [],
        kw.get("labels") or [],
        kw.get("delta", 0.0),
        kw.get("args"),
        tick_state,
        kw.get("offsets_list") or [],
        cif_tick_series=cif_globals.get("cif_tick_series"),
        label_text_objects=kw.get("label_text_objects") or [],
        overwrite_path=str(out),
        force_kind="psg",
    )
    assert out.is_file()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload.get("kind") == "xy_style_geom"
    plt.close(panel.fig)


def test_operando_export_includes_panel_gaps():
    import matplotlib.pyplot as plt
    import numpy as np
    from batplot.plot_modes.operando.style import build_operando_ec_style_config_v2

    fig, (ax, ec_ax) = plt.subplots(2, 1, figsize=(8, 6))
    data = np.random.rand(10, 10)
    im = ax.imshow(data)
    cbar = fig.colorbar(im, ax=ax)
    cfg, _ = build_operando_ec_style_config_v2(fig, ax, im, cbar, ec_ax, "ps")
    geom = cfg.get("geometry") or {}
    assert "cb_w_in" in geom
    assert "cb_gap_in" in geom
    assert "ec_gap_in" in geom
    plt.close(fig)


def test_ec_style_snapshot_includes_labelpads():
    import matplotlib.pyplot as plt
    from batplot.plot_modes.electrochem.style import _get_style_snapshot

    fig, ax = plt.subplots()
    ax.set_xlabel("X")
    ax.xaxis.labelpad = 12.5
    snap = _get_style_snapshot(fig, ax, {}, {})
    assert snap.get("labelpads", {}).get("x") == pytest.approx(12.5)
    plt.close(fig)


def test_xy_style_import_restores_dual_y_layout(tmp_path, fake_args):
    import matplotlib.pyplot as plt
    import numpy as np
    from batplot.plot_modes.xy.style import apply_style_config, export_style_config

    fig, ax = plt.subplots()
    x = np.linspace(0.0, 1.0, 20)
    ax.plot(x, x)
    ax.plot(x, 2 * x)
    fig._xy_lines_by_curve = [ax.lines[0], ax.lines[1]]
    fig._xy_right_y_curve_indices = frozenset()
    fig._xy_use_top_x = False
    fig._ro_active = False

    style_path = tmp_path / "dual.bps"
    export_style_config(
        str(style_path),
        fig,
        ax,
        [ax.lines[0].get_ydata(), ax.lines[1].get_ydata()],
        ["a", "b"],
        0.0,
        fake_args,
        {},
        [0.0, 0.0],
        overwrite_path=str(style_path),
        force_kind="ps",
    )
    cfg = json.loads(style_path.read_text(encoding="utf-8"))
    cfg["right_y_curve_indices"] = [1]
    cfg["txaxis"] = True
    style_path.write_text(json.dumps(cfg), encoding="utf-8")

    apply_style_config(
        str(style_path),
        fig,
        ax,
        [x, x],
        [x, 2 * x],
        [x, 2 * x],
        [0.0, 0.0],
        [],
        fake_args,
        {},
        ["a", "b"],
        update_labels_func=lambda *a, **k: None,
    )
    assert fig._xy_right_y_curve_indices == frozenset({1})
    assert fig._xy_use_top_x is True
    assert getattr(fig, "_xy_ax2", None) is not None
    plt.close(fig)


def test_operando_export_includes_colorbar_side_and_custom_labels():
    import matplotlib.pyplot as plt
    import numpy as np
    from batplot.plot_modes.operando.style import build_operando_ec_style_config_v2

    fig, (ax, ec_ax) = plt.subplots(2, 1, figsize=(8, 6))
    data = np.random.rand(10, 10)
    im = ax.imshow(data)
    cbar = fig.colorbar(im, ax=ax)
    cbar.ax.yaxis.set_ticks_position("left")
    cbar.ax.yaxis.set_label_position("left")
    ax._custom_labels = {"x": "Op X", "y": "Op Y"}
    ec_ax._custom_labels = {"x": "EC X", "y_time": "Time (h)", "y_ions": "Ions"}
    ec_ax._saved_time_ylim = (0.0, 12.0)
    cfg, _ = build_operando_ec_style_config_v2(fig, ax, im, cbar, ec_ax, "ps")
    assert cfg["colorbar"]["ticks_left"] is True
    assert cfg["colorbar"]["label_left"] is True
    assert cfg["operando"]["custom_labels"]["x"] == "Op X"
    assert cfg["ec"]["custom_labels"]["y_time"] == "Time (h)"
    assert cfg["ec"]["saved_time_ylim"] == [0.0, 12.0]
    plt.close(fig)


def test_ec_capture_cycle_styles_snapshot():
    import matplotlib.pyplot as plt
    from batplot.plot_modes.electrochem.style import capture_cycle_styles_snapshot

    fig, ax = plt.subplots()
    ln = ax.plot([0, 1], [0, 1], color="red", linewidth=2.5)[0]
    cycle_lines = {1: {"charge": ln, "discharge": None}}
    styles, per_file = capture_cycle_styles_snapshot(cycle_lines)
    assert "1" in styles
    assert styles["1"]["charge"]["color"] == "#ff0000"
    assert styles["1"]["charge"]["linewidth"] == pytest.approx(2.5)
    assert per_file is None
    plt.close(fig)

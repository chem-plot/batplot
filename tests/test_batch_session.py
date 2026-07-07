"""Tests for batch session mode."""

from __future__ import annotations

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
from batplot.plot_modes.batch_session.batch_io import parse_panel_selection
from batplot.plot_modes.batch_session.common import SyncUndoStacks
from batplot.plot_modes.batch_session.kinds import detect_session_kind, kind_label
from batplot.plot_modes.batch_session.load import load_batch_panels, validate_same_kind
from batplot.plot_modes.batch_session.xy_batch_helpers import dump_xy_panel
from batplot.plot_modes.histo.plot import build_histo_state, create_histo_figure
from batplot.plot_modes.histo.session import save_histo_session
from batplot.plot_modes.histo.wizard import HistoSetup
from batplot.plot_modes.histo.load import build_bin_edges
from conftest import loaded


def test_parse_panel_selection_all():
    assert parse_panel_selection("all", 5) == [0, 1, 2, 3, 4]
    assert parse_panel_selection("a", 3) == [0, 1, 2]


def test_parse_panel_selection_ranges():
    assert parse_panel_selection("1 3", 5) == [0, 2]
    assert parse_panel_selection("2-4", 5) == [1, 2, 3]
    assert parse_panel_selection("q", 5) is None


def test_sync_undo_push_indices():
    undo = SyncUndoStacks(4)
    undo.push_indices([0, 2], ["a", "b"])
    undo.push_indices([1], ["c"])
    restored = []
    undo.undo_all(lambda i, snap: restored.append((i, snap)))
    assert restored == [(0, "a"), (1, "c"), (2, "b")]


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
    assert "os: overwrite session(s)" in opts
    assert not any("ops" in o for o in opts)


def test_batch_quit_confirm_save(monkeypatch):
    monkeypatch.setattr(
        "batplot.plot_modes.batch_session.batch_commands.safe_input",
        lambda *_a, **_k: "s",
    )
    assert batch_quit_confirm(allow_export=True) == "s"


def test_batch_quit_confirm_save_all(monkeypatch):
    monkeypatch.setattr(
        "batplot.plot_modes.batch_session.batch_commands.safe_input",
        lambda *_a, **_k: "s all",
    )
    assert batch_quit_confirm(allow_export=True) == "s all"


def test_run_batch_save_all_calls_each_panel(capsys):
    saved: list[str] = []

    class Panel:
        def __init__(self, name: str):
            self.path = f"/tmp/{name}.pkl"

    panels = [Panel("a"), Panel("b")]
    run_batch_save_all(panels, lambda p: saved.append(p.path))
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


def test_append_batch_io_shortcuts_no_figure_overwrite():
    opts: list[str] = []
    fig = type("F", (), {"_last_figure_export_path": "/tmp/out.png"})()
    panel = type("P", (), {"fig": fig})()
    append_batch_io_shortcuts(opts, [panel])
    assert not any("oe" in o for o in opts)

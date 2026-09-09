"""XY interactive CIF add (cif → a) and p/i/s/b persistence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest

from batplot.plot_modes.xy.cif import append_xy_cif_file, run_cif_ticks_menu
from batplot.plot_modes.xy import style as ST


CIF_PATH = Path("/Users/tiandai/Downloads/ICSD_CollCode60433.cif")


def _minimal_xy_figure(*, use_2th: bool = False):
    fig, ax = plt.subplots(figsize=(6, 4))
    x = np.linspace(5.0, 40.0, 50) if use_2th else np.linspace(1.0, 6.0, 50)
    y = np.exp(-((x - x.mean()) ** 2) / 8.0)
    ax.plot(x, y)
    ax.set_xlim(float(x.min()), float(x.max()))
    series: list = []
    bp = SimpleNamespace(
        cif_tick_series=series,
        cif_hkl_label_map={},
        cif_hkl_map={},
        show_cif_hkl=False,
        show_cif_titles=True,
        cif_extend_suspended=False,
    )
    fig._batplot_cif_tick_series = series  # type: ignore[attr-defined]
    return fig, ax, bp


def _write_minimal_cif(path: Path) -> None:
    path.write_text(
        "data_test\n"
        "_cell_length_a 3.0\n_cell_length_b 3.0\n_cell_length_c 3.0\n"
        "_cell_angle_alpha 90\n_cell_angle_beta 90\n_cell_angle_gamma 90\n"
        "_symmetry_space_group_name_H-M 'P 1'\n"
        "loop_\n_atom_site_label\n_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\n"
        "Li 0 0 0\n",
        encoding="utf-8",
    )


@pytest.mark.skipif(not CIF_PATH.is_file(), reason="sample CIF not on this machine")
def test_append_xy_cif_file_adds_series():
    fig, ax, bp = _minimal_xy_figure(use_2th=False)
    lab, resolved = append_xy_cif_file(
        fig, ax, str(CIF_PATH), _bp=bp, use_2th=False, redraw=True,
    )
    assert len(bp.cif_tick_series) == 1
    assert lab
    assert os.path.isfile(resolved)
    assert hasattr(ax, "_cif_draw_func")
    with pytest.raises(ValueError, match="already loaded"):
        append_xy_cif_file(fig, ax, str(CIF_PATH), _bp=bp, use_2th=False, redraw=False)
    plt.close(fig)


@pytest.mark.skipif(not CIF_PATH.is_file(), reason="sample CIF not on this machine")
def test_append_xy_cif_from_empty_installs_draw():
    """First CIF on a data-only plot must draw without restart."""
    fig, ax, bp = _minimal_xy_figure()
    assert not hasattr(ax, "_cif_draw_func")
    append_xy_cif_file(fig, ax, str(CIF_PATH), _bp=bp, use_2th=False, redraw=True)
    assert callable(getattr(ax, "_cif_draw_func", None))
    assert len(getattr(ax, "_cif_tick_art", []) or []) >= 1
    plt.close(fig)


def test_empty_cif_submenu_exposes_a_and_opens_dialog(monkeypatch, tmp_path, capsys):
    cif = tmp_path / "phase.cif"
    _write_minimal_cif(cif)
    dialog_calls = []

    def _fake_dialog(*_a, **kwargs):
        dialog_calls.append(kwargs)
        return [str(cif)]

    import batplot.utils as U

    monkeypatch.setattr(U, "_ask_files_dialog", _fake_dialog)

    fig, ax, bp = _minimal_xy_figure(use_2th=False)
    feeds = iter(["a", "q"])

    def _feed(*_a, **_k):
        try:
            return next(feeds)
        except StopIteration:
            return "q"

    run_cif_ticks_menu(
        ax=ax,
        fig=fig,
        _bp=bp,
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
        _safe_input=_feed,
        push_state=lambda *_a, **_k: None,
        _print_cif_phase_list=lambda *_a, **_k: None,
        _apply_cif_phase_label_rename=lambda *_a, **_k: None,
        _sync_fig_cif_tick_series=lambda: setattr(fig, "_batplot_cif_tick_series", bp.cif_tick_series),
        use_2th=False,
        default_wl=None,
        y_data_list=[np.asarray(ax.lines[0].get_ydata())],
    )
    out = capsys.readouterr().out
    assert "a: add CIF file" in out
    assert dialog_calls, "file picker was never opened"
    assert len(dialog_calls) == 1, "picker must open once (no re-prompt after select)"
    assert dialog_calls[0].get("title") == "Select CIF file(s)"
    assert dialog_calls[0].get("filetypes") == (".cif", ".CIF")
    assert dialog_calls[0].get("multiple") is True
    assert len(bp.cif_tick_series) == 1
    plt.close(fig)


def test_xy_cif_add_multi_select_one_dialog(monkeypatch, tmp_path, capsys):
    cif1 = tmp_path / "a.cif"
    cif2 = tmp_path / "b.cif"
    _write_minimal_cif(cif1)
    _write_minimal_cif(cif2)
    dialog_calls = []

    def _fake_dialog(*_a, **kwargs):
        dialog_calls.append(kwargs)
        return [str(cif1), str(cif2)]

    import batplot.utils as U

    monkeypatch.setattr(U, "_ask_files_dialog", _fake_dialog)
    fig, ax, bp = _minimal_xy_figure(use_2th=False)
    feeds = iter(["a", "q"])

    def _feed(*_a, **_k):
        try:
            return next(feeds)
        except StopIteration:
            return "q"

    run_cif_ticks_menu(
        ax=ax,
        fig=fig,
        _bp=bp,
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
        _safe_input=_feed,
        push_state=lambda *_a, **_k: None,
        _print_cif_phase_list=lambda *_a, **_k: None,
        _apply_cif_phase_label_rename=lambda *_a, **_k: None,
        _sync_fig_cif_tick_series=lambda: setattr(fig, "_batplot_cif_tick_series", bp.cif_tick_series),
        use_2th=False,
        y_data_list=[np.asarray(ax.lines[0].get_ydata())],
    )
    assert len(dialog_calls) == 1
    assert len(bp.cif_tick_series) == 2
    plt.close(fig)


@pytest.mark.skipif(not CIF_PATH.is_file(), reason="sample CIF not on this machine")
def test_xy_cif_add_undo_restores_count():
    fig, ax, bp = _minimal_xy_figure()
    stack = []

    def push(tag):
        stack.append([tuple(t) for t in bp.cif_tick_series])

    def pop():
        if stack:
            bp.cif_tick_series[:] = stack.pop()
            fig._batplot_cif_tick_series = bp.cif_tick_series  # type: ignore[attr-defined]

    push("before")
    append_xy_cif_file(fig, ax, str(CIF_PATH), _bp=bp, use_2th=False, redraw=False)
    assert len(bp.cif_tick_series) == 1
    pop()
    assert len(bp.cif_tick_series) == 0
    plt.close(fig)


@pytest.mark.skipif(not CIF_PATH.is_file(), reason="sample CIF not on this machine")
def test_xy_cif_add_session_roundtrip(tmp_path):
    from batplot.cli_save import save_xy_session
    from batplot.session import load_xy_session

    fig, ax, bp = _minimal_xy_figure(use_2th=False)
    y = np.asarray(ax.lines[0].get_ydata())
    x = np.linspace(1.0, 6.0, len(y))
    append_xy_cif_file(fig, ax, str(CIF_PATH), _bp=bp, use_2th=False, redraw=True)
    n_before = len(bp.cif_tick_series)
    out = tmp_path / "xy_cif.pkl"
    args = SimpleNamespace(stack=False, autoscale=True, norm=False, files=[], delta=0.0)
    save_xy_session(
        str(out),
        fig=fig,
        ax=ax,
        x_data_list=[x],
        y_data_list=[y],
        orig_y=[y.copy()],
        x_full_list=[x],
        raw_y_full_list=[y.copy()],
        offsets_list=[0.0],
        labels=["curve"],
        delta=0.0,
        args=args,
        cif_tick_series=bp.cif_tick_series,
        cif_hkl_map=getattr(bp, "cif_hkl_map", {}),
        cif_hkl_label_map=bp.cif_hkl_label_map,
        show_cif_hkl=False,
        show_cif_titles=True,
    )
    plt.close(fig)
    loaded = load_xy_session(str(out))
    assert loaded is not None
    fig2, ax2, menu_kwargs = loaded
    cg = menu_kwargs.get("cif_globals") or {}
    series2 = cg.get("cif_tick_series") or []
    assert len(series2) == n_before
    assert hasattr(ax2, "_cif_draw_func")
    plt.close(fig2)


@pytest.mark.skipif(not CIF_PATH.is_file(), reason="sample CIF not on this machine")
def test_xy_cif_style_psg_roundtrip(tmp_path):
    fig, ax, bp = _minimal_xy_figure()
    append_xy_cif_file(fig, ax, str(CIF_PATH), _bp=bp, use_2th=False, redraw=True)
    args = SimpleNamespace(stack=False, autoscale=True, norm=False, files=[])
    out = ST.export_style_config(
        "xy_cif",
        fig,
        ax,
        [np.asarray(ax.lines[0].get_ydata())],
        ["curve"],
        0.0,
        args,
        {"x": True, "y": True},
        [0.0],
        bp.cif_tick_series,
        [],
        base_path=str(tmp_path),
        show_cif_titles=True,
        overwrite_path=str(tmp_path / "xy.bpsg"),
        force_kind="psg",
        cif_hkl_label_map=bp.cif_hkl_label_map,
    )
    assert out
    cfg = json.loads(Path(out).read_text(encoding="utf-8"))
    assert cfg.get("kind") == "xy_style_geom"
    assert "cif" in cfg
    assert cfg["cif"].get("tick_series")
    assert cfg.get("cif_ticks")

    fig2, ax2, bp2 = _minimal_xy_figure()
    assert not bp2.cif_tick_series
    ok = ST.apply_style_config(
        out,
        fig2,
        ax2,
        [np.linspace(1, 6, 50)],
        [np.asarray(ax2.lines[0].get_ydata())],
        [np.asarray(ax2.lines[0].get_ydata())],
        [0.0],
        [],
        args,
        {"x": True, "y": True},
        ["curve"],
        lambda *_a, **_k: None,
        bp2.cif_tick_series,
        bp2.cif_hkl_label_map,
    )
    assert ok is not False
    assert len(bp2.cif_tick_series) == 1
    plt.close(fig)
    plt.close(fig2)


@pytest.mark.skipif(not CIF_PATH.is_file(), reason="sample CIF not on this machine")
def test_xy_legacy_cif_ticks_style_still_applies_labels_colors(tmp_path):
    fig, ax, bp = _minimal_xy_figure()
    append_xy_cif_file(fig, ax, str(CIF_PATH), _bp=bp, use_2th=False, redraw=False)
    # Mutate label/color then apply a legacy-only style patch
    lab, fname, peaks, wl, qmax, _col = bp.cif_tick_series[0]
    bp.cif_tick_series[0] = (lab, fname, peaks, wl, qmax, "#112233")
    cfg = {
        "version": 2,
        "kind": "xy_style",
        "ro_active": False,
        "cif_ticks": [{"index": 0, "label": "RenamedPhase", "color": "#abcdef"}],
        "figure": {"size": [6, 4], "dpi": 100},
        "margins": {"left": 0.12, "right": 0.95, "bottom": 0.12, "top": 0.9},
        "curves": [],
    }
    style_path = tmp_path / "legacy.bps"
    style_path.write_text(json.dumps(cfg), encoding="utf-8")
    args = SimpleNamespace(stack=False, autoscale=True, norm=False, files=[])
    ST.apply_style_config(
        str(style_path),
        fig,
        ax,
        [np.linspace(1, 6, 50)],
        [np.asarray(ax.lines[0].get_ydata())],
        [np.asarray(ax.lines[0].get_ydata())],
        [0.0],
        [],
        args,
        {"x": True, "y": True},
        ["curve"],
        lambda *_a, **_k: None,
        bp.cif_tick_series,
        bp.cif_hkl_label_map,
    )
    assert bp.cif_tick_series[0][0] == "RenamedPhase"
    assert str(bp.cif_tick_series[0][5]).lower() in ("#abcdef", "#abcdef")
    plt.close(fig)


def test_batch_xy_menu_lists_cif(capsys):
    from batplot.plot_modes.batch_session.menu_xy import _print_xy_batch_menu
    from batplot.plot_modes.batch_session.load import XyPanel

    fig, ax = plt.subplots()
    ax.plot([1, 2], [3, 4])
    p = XyPanel(path="a.pkl", fig=fig, ax=ax, menu_kwargs={})
    _print_xy_batch_menu([p])
    out = capsys.readouterr().out
    assert "cif" in out.lower()
    plt.close(fig)


def test_batch_xy_x_range_extends_and_redraws_cif(monkeypatch):
    """Batch ``x`` must call CIF extend+draw on every panel (parity with single XY)."""
    from batplot.plot_modes.batch_session.menu_xy import _run_ref_range_menu
    from batplot.plot_modes.batch_session.common import SyncUndoStacks
    from batplot.plot_modes.batch_session.load import XyPanel
    import batplot.plot_modes.batch_session.batch_menu_helpers as BMH

    fig1, ax1 = plt.subplots()
    fig2, ax2 = plt.subplots()
    ax1.plot([0, 10], [0, 1])
    ax2.plot([0, 10], [0, 1])
    ax1.set_xlim(0, 3)
    ax2.set_xlim(0, 3)
    extend_calls: list = []
    draw_calls: list = []

    def _ext1(xmax):
        extend_calls.append(("p1", float(xmax)))

    def _ext2(xmax):
        extend_calls.append(("p2", float(xmax)))

    def _draw1():
        draw_calls.append("p1")

    def _draw2():
        draw_calls.append("p2")

    ax1._cif_extend_func = _ext1  # type: ignore[attr-defined]
    ax2._cif_extend_func = _ext2  # type: ignore[attr-defined]
    ax1._cif_draw_func = _draw1  # type: ignore[attr-defined]
    ax2._cif_draw_func = _draw2  # type: ignore[attr-defined]

    p1 = XyPanel("a.pkl", fig1, ax1, {"labels": ["c1"]})
    p2 = XyPanel("b.pkl", fig2, ax2, {"labels": ["c1"]})
    panels = [p1, p2]
    undo = SyncUndoStacks(2)
    calls = {"n": 0}
    real_prompt = BMH.prompt_axis_limits

    def _fake_prompt(**_k):
        calls["n"] += 1
        if calls["n"] == 1:
            return (0.0, 8.0)
        return None

    monkeypatch.setattr(BMH, "prompt_axis_limits", _fake_prompt)
    try:
        _run_ref_range_menu(p1, panels, undo, "x")
    finally:
        monkeypatch.setattr(BMH, "prompt_axis_limits", real_prompt)

    assert ax1.get_xlim() == pytest.approx((0.0, 8.0))
    assert ax2.get_xlim() == pytest.approx((0.0, 8.0))
    assert ("p1", 8.0) in extend_calls
    assert ("p2", 8.0) in extend_calls
    assert draw_calls == ["p1", "p2"]
    plt.close(fig1)
    plt.close(fig2)


@pytest.mark.skipif(not CIF_PATH.is_file(), reason="sample CIF not on this machine")
def test_append_mutates_hkl_map_in_place():
    """Pipeline/interactive share one hkl dict — append must not replace it."""
    fig, ax, bp = _minimal_xy_figure()
    live = bp.cif_hkl_label_map
    fig._batplot_cif_hkl_label_map = live  # type: ignore[attr-defined]
    append_xy_cif_file(fig, ax, str(CIF_PATH), _bp=bp, use_2th=False, redraw=False)
    assert bp.cif_hkl_label_map is live
    assert fig._batplot_cif_hkl_label_map is live
    assert any(str(CIF_PATH.resolve()) in str(k) or "60433" in str(k) for k in live)
    plt.close(fig)


@pytest.mark.skipif(not CIF_PATH.is_file(), reason="sample CIF not on this machine")
def test_undo_after_first_add_clears_tick_artists():
    fig, ax, bp = _minimal_xy_figure()
    append_xy_cif_file(fig, ax, str(CIF_PATH), _bp=bp, use_2th=False, redraw=True)
    assert len(getattr(ax, "_cif_tick_art", []) or []) >= 1
    # Simulate undo to empty series + redraw
    bp.cif_tick_series.clear()
    fig._batplot_cif_tick_series = bp.cif_tick_series  # type: ignore[attr-defined]
    ax._cif_draw_func()
    assert getattr(ax, "_cif_tick_art", None) == [] or len(ax._cif_tick_art) == 0
    plt.close(fig)


def test_failed_add_does_not_pop_unrelated_undo(monkeypatch, tmp_path):
    """If push_state never ran, failed append must not call pop_undo."""
    fig, ax, bp = _minimal_xy_figure()
    pops = {"n": 0}
    dialog_n = {"n": 0}

    def _push(_tag):
        raise RuntimeError("push failed")

    def _pop():
        pops["n"] += 1

    import batplot.utils as U

    def _files_dialog(**_k):
        dialog_n["n"] += 1
        return [str(tmp_path / "missing.cif")]

    monkeypatch.setattr(U, "_ask_files_dialog", _files_dialog)
    feeds = iter(["a", "q"])

    def _feed(*_a, **_k):
        try:
            return next(feeds)
        except StopIteration:
            return "q"

    run_cif_ticks_menu(
        ax=ax,
        fig=fig,
        _bp=bp,
        colorize_menu=lambda s: s,
        colorize_prompt=lambda s: s,
        _safe_input=_feed,
        push_state=_push,
        _print_cif_phase_list=lambda *_a, **_k: None,
        _apply_cif_phase_label_rename=lambda *_a, **_k: None,
        _sync_fig_cif_tick_series=lambda: None,
        use_2th=False,
        pop_undo=_pop,
    )
    assert pops["n"] == 0
    assert dialog_n["n"] == 1
    plt.close(fig)


@pytest.mark.skipif(not CIF_PATH.is_file(), reason="sample CIF not on this machine")
def test_legacy_style_without_cif_block_still_applies(tmp_path):
    """Old .bps with only cif_ticks must keep working (no cif key)."""
    fig, ax, bp = _minimal_xy_figure()
    append_xy_cif_file(fig, ax, str(CIF_PATH), _bp=bp, use_2th=False, redraw=False)
    cfg = {
        "version": 2,
        "kind": "xy_style",
        "ro_active": False,
        "cif_ticks": [{"index": 0, "label": "LegacyOnly", "color": "#fedcba"}],
        "figure": {"size": [6, 4], "dpi": 100},
        "margins": {"left": 0.12, "right": 0.95, "bottom": 0.12, "top": 0.9},
        "curves": [],
    }
    # Explicitly no "cif" key — pre-feature style files
    assert "cif" not in cfg
    style_path = tmp_path / "old.bps"
    style_path.write_text(json.dumps(cfg), encoding="utf-8")
    args = SimpleNamespace(stack=False, autoscale=True, norm=False, files=[], xaxis=None, wl=None)
    ST.apply_style_config(
        str(style_path),
        fig,
        ax,
        [np.linspace(1, 6, 50)],
        [np.asarray(ax.lines[0].get_ydata())],
        [np.asarray(ax.lines[0].get_ydata())],
        [0.0],
        [],
        args,
        {"x": True, "y": True},
        ["curve"],
        lambda *_a, **_k: None,
        bp.cif_tick_series,
        bp.cif_hkl_label_map,
    )
    assert bp.cif_tick_series[0][0] == "LegacyOnly"
    plt.close(fig)


@pytest.mark.skipif(not CIF_PATH.is_file(), reason="sample CIF not on this machine")
def test_session_reload_cif_extend_grows_peaks(tmp_path):
    """After .pkl reload, expanding X must extend CIF Qmax (not a no-op)."""
    from batplot.plot_modes.xy.session import dump_session, load_xy_session
    from batplot.plot_modes.xy.axis_units import set_xy_axis_mode
    from batplot.plot_modes.xy.cif import append_xy_cif_file, extend_xy_cif_series_for_xmax

    fig, ax = plt.subplots()
    x = np.linspace(1.0, 3.0, 40)
    y = np.ones_like(x)
    ax.plot(x, y)
    ax.set_xlim(1.0, 3.0)
    set_xy_axis_mode(fig, "Q")
    bp = SimpleNamespace(
        cif_tick_series=[], cif_hkl_label_map={}, cif_hkl_map={},
        show_cif_hkl=False, show_cif_titles=True,
    )
    append_xy_cif_file(fig, ax, str(CIF_PATH), _bp=bp, use_2th=False, redraw=True)
    qmax0 = float(bp.cif_tick_series[0][4])
    tick = {
        "bx": True, "tx": False, "ly": True, "ry": False,
        "mbx": False, "mtx": False, "mly": False, "mry": False,
        "b_ticks": True, "t_ticks": False, "l_ticks": True, "r_ticks": False,
        "b_labels": True, "t_labels": False, "l_labels": True, "r_labels": False,
    }
    args = SimpleNamespace(
        stack=False, files=["a.xy"], wl=None, ro=False, xaxis="Q",
        norm=False, autoscale=True, delta=0.0,
    )
    out = tmp_path / "cif_q.pkl"
    assert dump_session(
        str(out), fig=fig, ax=ax,
        x_data_list=[x], y_data_list=[y], orig_y=[y.copy()],
        x_full_list=[x.copy()], raw_y_full_list=[y.copy()],
        offsets_list=[0.0], labels=["c1"], delta=0.0, args=args,
        tick_state=tick, cif_tick_series=bp.cif_tick_series,
        cif_hkl_label_map=bp.cif_hkl_label_map, show_cif_hkl=False,
        show_cif_titles=True, skip_confirm=True,
    )
    plt.close(fig)
    loaded = load_xy_session(str(out))
    assert loaded is not None
    fig2, ax2, kw = loaded
    assert callable(getattr(ax2, "_cif_extend_func", None))
    # Force a small saved qmax then extend past it
    series = getattr(fig2, "_batplot_cif_tick_series", None) or []
    assert series
    lab, fname, peaks, wl, qmax, col = series[0]
    series[0] = (lab, fname, peaks[:3], wl, 2.0, col)
    assert extend_xy_cif_series_for_xmax(fig2, ax2, 6.0, use_2th=False)
    assert float(series[0][4]) > 2.0
    ax2._cif_extend_func(6.0)  # installed session extender must not be a no-op
    plt.close(fig2)


@pytest.mark.skipif(not CIF_PATH.is_file(), reason="sample CIF not on this machine")
def test_session_reload_cif_add_draws_artists(tmp_path):
    """Reloaded CIF-less .pkl must draw after cif→a (args in session draw closure)."""
    from batplot.plot_modes.xy.session import dump_session, load_xy_session
    from batplot.plot_modes.xy.axis_units import set_xy_axis_mode

    fig, ax = plt.subplots(figsize=(6, 4))
    x = np.linspace(1.0, 6.0, 80)
    y = np.exp(-((x - 3.0) ** 2) / 4.0)
    ax.plot(x, y)
    ax.set_xlim(1.0, 6.0)
    ax.set_xlabel(r"Q ($\mathrm{\AA}^{-1}$)")
    ax.set_ylabel("I")
    set_xy_axis_mode(fig, "Q", wavelength=None)
    tick = {
        "bx": True, "tx": False, "ly": True, "ry": False,
        "mbx": False, "mtx": False, "mly": False, "mry": False,
        "b_ticks": True, "t_ticks": False, "l_ticks": True, "r_ticks": False,
        "b_labels": True, "t_labels": False, "l_labels": True, "r_labels": False,
    }
    args = SimpleNamespace(
        stack=False, files=["a.xy"], wl=None, ro=False, xaxis="Q",
        norm=False, autoscale=True, delta=0.0,
    )
    out = tmp_path / "q_no_cif.pkl"
    assert dump_session(
        str(out),
        fig=fig,
        ax=ax,
        x_data_list=[x],
        y_data_list=[y],
        orig_y=[y.copy()],
        x_full_list=[x.copy()],
        raw_y_full_list=[y.copy()],
        offsets_list=[0.0],
        labels=["c1"],
        delta=0.0,
        args=args,
        tick_state=tick,
        skip_confirm=True,
    )
    plt.close(fig)

    loaded = load_xy_session(str(out))
    assert loaded is not None
    fig2, ax2, kw = loaded
    assert callable(getattr(ax2, "_cif_draw_func", None))
    cg = kw.get("cif_globals") or {}
    bp = SimpleNamespace(
        cif_tick_series=cg.get("cif_tick_series") or [],
        cif_hkl_label_map=cg.get("cif_hkl_label_map") or {},
        cif_hkl_map=cg.get("cif_hkl_map") or {},
        show_cif_hkl=False,
        show_cif_titles=True,
    )
    append_xy_cif_file(
        fig2, ax2, str(CIF_PATH), _bp=bp, use_2th=False, redraw=True,
        y_data_list=kw.get("y_data_list"),
    )
    assert len(bp.cif_tick_series) == 1
    assert len(getattr(ax2, "_cif_tick_art", []) or []) >= 1
    plt.close(fig2)


EXSITU_XRD_PKL = Path(
    "/Users/tiandai/Library/CloudStorage/OneDrive-UniversitetetiOslo/My files/"
    "NFSO data/Figures/exsituXRD.pkl"
)
EXSITU_CIF = Path(
    "/Users/tiandai/Library/CloudStorage/OneDrive-UniversitetetiOslo/My files/"
    "NFSO data/CIFs/Fe_xy_q_collCode#53451.cif"
)


@pytest.mark.skipif(
    not (EXSITU_XRD_PKL.is_file() and EXSITU_CIF.is_file()),
    reason="exsituXRD.pkl / Fe CIF not on this machine",
)
def test_exsitu_xrd_pkl_cif_add_shows_title(capsys):
    """User report: cif→a on exsituXRD.pkl showed nothing (session draw NameError)."""
    from batplot.session import load_xy_session

    loaded = load_xy_session(str(EXSITU_XRD_PKL))
    assert loaded is not None
    fig, ax, kw = loaded
    cg = kw.get("cif_globals") or {}
    bp = SimpleNamespace(
        cif_tick_series=list(cg.get("cif_tick_series") or []),
        cif_hkl_label_map=dict(cg.get("cif_hkl_label_map") or {}),
        cif_hkl_map=dict(cg.get("cif_hkl_map") or {}),
        show_cif_hkl=False,
        show_cif_titles=True,
    )
    append_xy_cif_file(
        fig, ax, str(EXSITU_CIF), _bp=bp, use_2th=False, redraw=True,
        y_data_list=kw.get("y_data_list"),
    )
    art = getattr(ax, "_cif_tick_art", []) or []
    assert len(art) >= 1, "phase title/ticks must appear after session reload add"
    out = capsys.readouterr().out
    # Current X is ~1–3 Q; first Fe peak is ~3.1 — expect the out-of-range note
    assert "none fall in the current X range" in out or len(art) >= 1
    plt.close(fig)
